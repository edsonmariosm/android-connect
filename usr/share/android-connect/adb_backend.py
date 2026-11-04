"""
Backend ADB Wi-Fi, Arquivos Locais, Inspecao Segura de ZIP/APK e Modo Root.
"""
import os
import re
import shlex
import shutil
import stat
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_private_runtime_dir() -> Path:
    """Cria e retorna um diretorio temporario isolado por UID com permissao estrita 0700 (CWE-377)."""
    uid = os.getuid() if hasattr(os, "getuid") else 0
    base = Path(f"/tmp/android_connect_{uid}")
    if base.is_symlink():
        raise RuntimeError("Diretório temporário inseguro (symlink detectado).")
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    return base


def is_valid_target(ip: str, port: str) -> bool:
    if not isinstance(ip, str) or not isinstance(port, str):
        return False
    ip_clean = ip.strip()
    port_clean = port.strip()
    if not ip_clean or not port_clean.isdigit():
        return False
    port_num = int(port_clean)
    if not (1 <= port_num <= 65535):
        return False
    parts = ip_clean.split(".")
    if all(p.isdigit() for p in parts):
        return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)
    if re.match(r"^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*$", ip_clean) and not parts[-1].isdigit() and len(ip_clean) <= 253:
        return True
    return False


def validate_single_filename(name: str) -> Tuple[bool, str]:
    """Valida nome de arquivo/pasta contra Path Traversal, caracteres nulos ou barras (CWE-22)."""
    if not isinstance(name, str):
        return False, "Nome inválido."
    cleaned = name.strip()
    if not cleaned:
        return False, "O nome não pode estar vazio."
    if cleaned in (".", ".."):
        return False, "Nome reservado pelo sistema."
    if "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
        return False, "O nome não pode conter barras ('/' ou '\\') nem caracteres de controle."
    if len(cleaned.encode("utf-8")) > 255:
        return False, "O nome excede o limite de 255 bytes."
    return True, cleaned


@dataclass
class FileEntry:
    name: str
    path: str
    is_dir: bool
    is_symlink: bool = False
    is_archive: bool = False
    size: int = 0
    permissions: str = "---------"
    perm_label: str = "Padrão"
    modified: str = ""
    owner: str = ""

    @property
    def human_size(self) -> str:
        if self.is_dir:
            return "<PASTA>"
        s = float(max(0, self.size))
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if s < 1024.0 or unit == "TB":
                return f"{int(s)} B" if unit == "B" else f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{self.size} B"


def classify_perm_label(octal_or_rwx: str) -> str:
    s = str(octal_or_rwx)
    if "777" in s or "rwxrwxrwx" in s:
        return "Acesso Total"
    if "755" in s or "rwxr-xr-x" in s:
        return "Padrão do Sistema"
    if "644" in s or "rw-r--r--" in s or "664" in s:
        return "Leitura e Escrita"
    if "666" in s or "rw-rw-rw-" in s:
        return "Leitura e Escrita"
    if "444" in s or "r--r--r--" in s or "400" in s:
        return "Apenas Leitura"
    if "000" in s or "---------" in s or "600" in s or "700" in s:
        return "Restrito"
    return "Personalizado"


class AdbController:
    def __init__(self):
        self.device_serial: Optional[str] = None
        self.root_enabled: bool = False
        self.sudo_password: Optional[str] = None
        self.android_has_su: bool = False

    def _run_cmd(self, args: List[str], timeout: int = 25, input_text: Optional[str] = None) -> Tuple[bool, str]:
        try:
            proc = subprocess.run(
                args,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return proc.returncode == 0, out.strip()
        except FileNotFoundError:
            return False, f"Programa '{args[0]}' não encontrado no computador."
        except subprocess.TimeoutExpired:
            return False, "Tempo limite esgotado."
        except Exception as exc:
            return False, str(exc)

    def _adb_base(self) -> List[str]:
        if self.device_serial:
            return ["adb", "-s", self.device_serial]
        return ["adb"]

    def pair_device(self, ip: str, port: str, code: str) -> Tuple[bool, str]:
        if not is_valid_target(ip, port):
            return False, "Endereço IP ou porta inválidos."
        code_clean = str(code).strip()
        if not code_clean.isdigit() or len(code_clean) != 6:
            return False, "O código deve conter exatamente 6 dígitos numéricos."
        target = f"{ip.strip()}:{port.strip()}"
        ok, out = self._run_cmd(["adb", "pair", target, code_clean], timeout=25)
        if "Successfully paired" in out or (ok and "error" not in out.lower() and "failed" not in out.lower()):
            return True, f"Celular vinculado com sucesso em {target}"
        return False, out or f"Falha ao vincular em {target}"

    def connect_device(self, ip: str, port: str = "5555") -> Tuple[bool, str]:
        if not is_valid_target(ip, port):
            return False, "Endereço IP ou porta inválidos."
        target = f"{ip.strip()}:{port.strip()}"
        ok, out = self._run_cmd(["adb", "connect", target], timeout=15)
        if "connected to" in out.lower() and "unable" not in out.lower() and "failed" not in out.lower():
            self.device_serial = target
            return True, out
        return False, out or f"Não foi possível conectar a {target}"

    def list_devices(self) -> List[Tuple[str, str]]:
        ok, out = self._run_cmd(["adb", "devices", "-l"], timeout=8)
        if not ok:
            return []
        devices = []
        for line in out.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] in ("device", "unauthorized", "offline"):
                devices.append((parts[0], " ".join(parts[1:])))
        return devices

    def verify_local_sudo(self, password: str) -> Tuple[bool, str]:
        if not isinstance(password, str) or not password:
            return False, "A senha não pode estar vazia."
        ok, _ = self._run_cmd(["sudo", "-S", "-k", "true"], timeout=8, input_text=password + "\n")
        if ok:
            self.sudo_password = password
            return True, "Senha do computador confirmada."
        return False, "Senha incorreta."

    def test_android_root(self) -> Tuple[bool, str]:
        if not self.device_serial:
            self.android_has_su = False
            return True, "Acesso Total ativo no computador."
        self._run_cmd(self._adb_base() + ["root"], timeout=8)
        ok_id, out_id = self._run_cmd(self._adb_base() + ["shell", "id"], timeout=8)
        if ok_id and "uid=0(root)" in out_id:
            self.android_has_su = False
            return True, "Acesso Total ativo no celular."
        ok_su, out_su = self._run_cmd(self._adb_base() + ["shell", "su -c id"], timeout=8)
        if ok_su and "uid=0(root)" in out_su:
            self.android_has_su = True
            return True, "Acesso Total ativo no celular."
        self.android_has_su = False
        return False, "Celular sem permissão de superusuário (apenas computador com Acesso Total)."

    def set_root_mode(self, enabled: bool, password: Optional[str] = None) -> Tuple[bool, str]:
        if not enabled:
            self.root_enabled = False
            self.sudo_password = None
            self.android_has_su = False
            return True, "Acesso Total Desativado."
        ok_sudo, msg_sudo = self.verify_local_sudo(password or "")
        if not ok_sudo:
            self.root_enabled = False
            return False, msg_sudo
        self.root_enabled = True
        _, msg_andro = self.test_android_root()
        return True, f"{msg_sudo}\n{msg_andro}"

    def run_android_shell(self, shell_cmd: str, timeout: int = 25) -> Tuple[bool, str]:
        if self.root_enabled and self.android_has_su:
            wrapped = f"su -c {shlex.quote(shell_cmd)}"
            return self._run_cmd(self._adb_base() + ["shell", wrapped], timeout=timeout)
        return self._run_cmd(self._adb_base() + ["shell", shell_cmd], timeout=timeout)

    def get_storage_info(self, is_remote: bool, path: str = "/") -> Tuple[int, int, str]:
        try:
            if not is_remote:
                check_path = path.split("::")[0] if "::" in path else path
                statv = os.statvfs(check_path if os.path.exists(check_path) else "/")
                total = statv.f_blocks * statv.f_frsize
                free = statv.f_bavail * statv.f_frsize
                used = total - free
                pct = int((used / total) * 100) if total else 0
                human_free = f"{free / (1024**3):.1f} GB livres de {total / (1024**3):.1f} GB ({pct}%)"
                return used, total, human_free
            if not self.device_serial:
                return 0, 0, "Desconectado"
            ok, out = self.run_android_shell("df -h /data /sdcard 2>/dev/null")
            if ok and out:
                lines = out.strip().splitlines()
                if len(lines) >= 2:
                    cols = lines[-1].split()
                    if len(cols) >= 5:
                        return 1, 1, f"{cols[3]} livres de {cols[1]} ({cols[4]} usado)"
            return 0, 0, "Espaço indisponível"
        except Exception:
            return 0, 0, "---"

    def list_archive(self, archive_path: str, subpath: str = "") -> Tuple[bool, List[FileEntry], str]:
        entries: List[FileEntry] = []
        if not os.path.isfile(archive_path):
            return False, [], "Pacote não encontrado."
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                clean_sub = subpath.strip("/")
                prefix = (clean_sub + "/") if clean_sub else ""
                dirs_seen = set()
                for info in zf.infolist():
                    norm_name = os.path.normpath(info.filename).lstrip("/")
                    if norm_name.startswith(".."):
                        continue
                    if prefix and not norm_name.startswith(prefix):
                        continue
                    rel = norm_name[len(prefix):] if prefix else norm_name
                    if not rel or rel == ".":
                        continue
                    parts = rel.strip("/").split("/")
                    first = parts[0]
                    if len(parts) > 1 or info.is_dir():
                        if first not in dirs_seen:
                            dirs_seen.add(first)
                            entries.append(FileEntry(
                                name=first,
                                path=f"{archive_path}::{prefix}{first}",
                                is_dir=True,
                                size=0,
                                permissions="drwxr-xr-x",
                                perm_label="Pasta do Pacote",
                                modified=""
                            ))
                    else:
                        dt = info.date_time
                        mod = f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d} {dt[3]:02d}:{dt[4]:02d}"
                        entries.append(FileEntry(
                            name=first,
                            path=f"{archive_path}::{prefix}{first}",
                            is_dir=False,
                            size=max(0, info.file_size),
                            permissions="-rw-r--r--",
                            perm_label="Item do Pacote",
                            modified=mod
                        ))
            entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
            return True, entries, f"{archive_path}::{clean_sub}"
        except Exception as exc:
            return False, [], f"Pacote inválido ou corrompido: {exc}"

    def extract_archive_member(self, virtual_path: str, dest_dir: str) -> Tuple[bool, str]:
        """Extrai um item de dentro de um .zip/.apk com protecao anti-Zip-Slip (CWE-22)."""
        if "::" not in virtual_path:
            return False, "Caminho de pacote inválido."
        arch_path, member = virtual_path.split("::", 1)
        member = member.strip("/")
        if not member or ".." in member.split("/"):
            return False, "Caminho interno inválido."
        try:
            dest_root = Path(dest_dir).resolve()
            dest_root.mkdir(parents=True, exist_ok=True)
            target_file = (dest_root / os.path.basename(member)).resolve()
            if dest_root not in target_file.parents and target_file != dest_root:
                return False, "Bloqueio de segurança: tentativa de escrita fora da pasta destino."
            with zipfile.ZipFile(arch_path, "r") as zf:
                with zf.open(member, "r") as src, open(target_file, "wb") as dst:
                    shutil.copyfileobj(src, dst, length=65536)
            return True, str(target_file)
        except KeyError:
            return False, "Não é possível extrair pastas inteiras diretamente; entre na pasta e selecione os arquivos."
        except Exception as exc:
            return False, str(exc)

    def list_local_dir(self, dir_path: str) -> Tuple[bool, List[FileEntry], str]:
        if "::" in dir_path:
            arch, sub = dir_path.split("::", 1)
            return self.list_archive(arch, sub)

        p = Path(dir_path).expanduser().resolve()
        entries: List[FileEntry] = []
        try:
            for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                try:
                    st = item.lstat()
                    is_dir = item.is_dir()
                    is_link = item.is_symlink()
                    is_arch = (not is_dir) and item.name.lower().endswith((".zip", ".apk", ".jar"))
                    perms = stat.filemode(st.st_mode)
                    octal = oct(st.st_mode)[-3:]
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    entries.append(FileEntry(
                        name=item.name,
                        path=str(item),
                        is_dir=is_dir,
                        is_symlink=is_link,
                        is_archive=is_arch,
                        size=0 if is_dir else st.st_size,
                        permissions=perms,
                        perm_label=classify_perm_label(octal),
                        modified=mtime
                    ))
                except PermissionError:
                    entries.append(FileEntry(
                        name=item.name,
                        path=str(item),
                        is_dir=False,
                        permissions="d?????????",
                        perm_label="Restrito"
                    ))
            return True, entries, str(p)
        except PermissionError:
            if self.root_enabled and self.sudo_password:
                ok, out = self._run_cmd(
                    ["sudo", "-S", "ls", "-la", "--time-style=+%Y-%m-%d %H:%M", str(p)],
                    input_text=self.sudo_password + "\n"
                )
                if ok:
                    return True, self._parse_ls_output(out, str(p)), str(p)
            return False, [], f"Acesso negado a '{p}'. Ative o Acesso Total para abrir esta pasta."
        except Exception as exc:
            return False, [], str(exc)

    def list_android_dir(self, remote_path: str) -> Tuple[bool, List[FileEntry], str]:
        if "::" in remote_path:
            arch, sub = remote_path.split("::", 1)
            return self.list_archive(arch, sub)
        if not self.device_serial:
            return False, [], "Nenhum celular conectado."
        clean_path = remote_path if remote_path.startswith("/") else "/" + remote_path
        cmd_path = clean_path if clean_path.endswith("/") else clean_path + "/"
        ok, out = self.run_android_shell(f"ls -la {shlex.quote(cmd_path)}")
        if not ok or "Permission denied" in out or "No such file" in out:
            return False, [], out or f"Erro ao abrir {clean_path}"
        entries = self._parse_ls_output(out, clean_path.rstrip("/") or "/")
        return True, entries, clean_path.rstrip("/") or "/"

    def _parse_ls_output(self, raw_ls: str, base_dir: str) -> List[FileEntry]:
        entries: List[FileEntry] = []
        dirs: List[FileEntry] = []
        files: List[FileEntry] = []

        for line in raw_ls.splitlines():
            line = line.strip()
            if not line or line.startswith("total "):
                continue
            parts = line.split(None, 7)
            if len(parts) < 6:
                continue
            perms = parts[0]
            if perms[0] not in "-dlcbps":
                continue

            try:
                date_idx = -1
                tokens = line.split()
                for idx, tok in enumerate(tokens):
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", tok):
                        date_idx = idx
                        break
                if date_idx != -1 and date_idx + 2 < len(tokens):
                    size_tok = tokens[date_idx - 1]
                    size_val = int(size_tok) if size_tok.isdigit() else 0
                    mod_str = f"{tokens[date_idx]} {tokens[date_idx + 1]}"
                    time_tok = tokens[date_idx + 1]
                    pos = line.find(time_tok, line.find(tokens[date_idx]))
                    name_part = line[pos + len(time_tok):].strip()
                else:
                    size_val = 0
                    mod_str = ""
                    name_part = parts[-1]

                is_symlink = perms.startswith("l")
                if " -> " in name_part:
                    name_part = name_part.split(" -> ")[0].strip()
                if name_part in (".", "..") or not name_part:
                    continue

                is_dir = perms.startswith("d") or (is_symlink and "." not in os.path.basename(name_part))
                is_arch = (not is_dir) and name_part.lower().endswith((".zip", ".apk", ".jar"))
                full_path = f"{base_dir.rstrip('/')}/{name_part}"
                entry = FileEntry(
                    name=name_part,
                    path=full_path,
                    is_dir=is_dir,
                    is_symlink=is_symlink,
                    is_archive=is_arch,
                    size=0 if is_dir else size_val,
                    permissions=perms,
                    perm_label=classify_perm_label(perms),
                    modified=mod_str
                )
                if is_dir:
                    dirs.append(entry)
                else:
                    files.append(entry)
            except Exception:
                continue

        dirs.sort(key=lambda e: e.name.lower())
        files.sort(key=lambda e: e.name.lower())
        entries.extend(dirs)
        entries.extend(files)
        return entries

    def global_search(self, base_dir: str, term: str, is_remote: bool, max_results: int = 200) -> List[FileEntry]:
        results: List[FileEntry] = []
        if not isinstance(term, str):
            return results
        term_clean = term.strip().lower()
        if not term_clean:
            return results

        clean_base = base_dir.split("::")[0] if "::" in base_dir else base_dir
        if not is_remote:
            root_p = Path(clean_base).resolve()
            if not root_p.is_dir():
                root_p = root_p.parent
            try:
                count = 0
                for root, dirs, files in os.walk(root_p):
                    for name in dirs + files:
                        if term_clean in name.lower():
                            fp = os.path.join(root, name)
                            is_d = os.path.isdir(fp)
                            try:
                                sz = 0 if is_d else os.path.getsize(fp)
                            except Exception:
                                sz = 0
                            results.append(FileEntry(
                                name=name,
                                path=fp,
                                is_dir=is_d,
                                is_archive=(not is_d) and name.lower().endswith((".zip", ".apk", ".jar")),
                                size=sz,
                                perm_label="Encontrado"
                            ))
                            count += 1
                            if count >= max_results:
                                return results
            except Exception:
                pass
        else:
            if not self.device_serial:
                return []
            safe_term = re.sub(r"[^a-zA-Z0-9._-]", "", term_clean)
            if not safe_term:
                return []
            cmd = f"find {shlex.quote(clean_base)} -iname {shlex.quote('*' + safe_term + '*')} 2>/dev/null | head -n {int(max_results)}"
            ok, out = self.run_android_shell(cmd, timeout=30)
            if ok and out:
                for line in out.splitlines():
                    fp = line.strip()
                    if fp and fp.startswith("/"):
                        name = os.path.basename(fp)
                        results.append(FileEntry(
                            name=name,
                            path=fp,
                            is_dir=False,
                            is_archive=name.lower().endswith((".zip", ".apk", ".jar")),
                            perm_label="Encontrado no Celular"
                        ))
        return results

    def push_item(self, local_path: str, remote_dir: str) -> Tuple[bool, str]:
        if not self.device_serial:
            return False, "Celular desconectado."
        if "::" in local_path:
            tmp_dir = get_private_runtime_dir() / "extract_push"
            ok_ex, extracted = self.extract_archive_member(local_path, str(tmp_dir))
            if not ok_ex:
                return False, extracted
            local_path = extracted

        name = os.path.basename(local_path.rstrip("/"))
        target = f"{remote_dir.rstrip('/')}/{name}"
        ok, out = self._run_cmd(self._adb_base() + ["push", local_path, target], timeout=180)
        if ok:
            return True, f"Enviado para {target}"
        if self.root_enabled:
            safe_stage_name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
            stage = f"/data/local/tmp/_stage_{safe_stage_name}"
            ok_s, _ = self._run_cmd(self._adb_base() + ["push", local_path, stage], timeout=180)
            if ok_s:
                ok_mv, out_mv = self.run_android_shell(
                    f"cp -r {shlex.quote(stage)} {shlex.quote(target)} && rm -rf {shlex.quote(stage)}"
                )
                if ok_mv:
                    return True, f"Enviado com Acesso Total para {target}"
                return False, out_mv
        return False, out

    def pull_item(self, remote_path: str, local_dest: str) -> Tuple[bool, str]:
        if "::" in remote_path:
            return self.extract_archive_member(remote_path, local_dest if os.path.isdir(local_dest) else os.path.dirname(local_dest))
        if not self.device_serial:
            return False, "Celular desconectado."
        ok, out = self._run_cmd(self._adb_base() + ["pull", remote_path, local_dest], timeout=180)
        if ok:
            return True, f"Salvo em {local_dest}"
        if self.root_enabled:
            name = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(remote_path.rstrip("/")))
            stage = f"/data/local/tmp/_pull_{name}"
            ok_cp, _ = self.run_android_shell(
                f"cp -r {shlex.quote(remote_path)} {shlex.quote(stage)} && chmod -R 666 {shlex.quote(stage)}"
            )
            if ok_cp:
                ok_pl, out_pl = self._run_cmd(self._adb_base() + ["pull", stage, local_dest], timeout=180)
                self.run_android_shell(f"rm -rf {shlex.quote(stage)}")
                if ok_pl:
                    return True, f"Salvo com Acesso Total em {local_dest}"
                return False, out_pl
        return False, out

    def rename_item(self, old_path: str, new_name: str, is_remote: bool) -> Tuple[bool, str]:
        if "::" in old_path:
            return False, "Não é possível renomear itens diretamente dentro de um pacote fechado."
        valid, clean_name = validate_single_filename(new_name)
        if not valid:
            return False, clean_name
        parent = os.path.dirname(old_path.rstrip("/"))
        new_path = os.path.join(parent, clean_name) if not is_remote else f"{parent.rstrip('/')}/{clean_name}"
        if old_path == new_path:
            return True, "Nome mantido."
        if is_remote:
            return self.run_android_shell(f"mv {shlex.quote(old_path)} {shlex.quote(new_path)}")
        try:
            if os.path.exists(new_path):
                return False, f"Já existe um item chamado '{clean_name}'."
            os.rename(old_path, new_path)
            return True, "Renomeado com sucesso."
        except PermissionError:
            if self.root_enabled and self.sudo_password:
                return self._run_cmd(["sudo", "-S", "mv", "-n", old_path, new_path], input_text=self.sudo_password + "\n")
            return False, "Permissão negada."
        except Exception as exc:
            return False, str(exc)

    def mkdir_item(self, base_dir: str, folder_name: str, is_remote: bool) -> Tuple[bool, str]:
        if "::" in base_dir:
            return False, "Não é possível criar pastas dentro de um pacote fechado."
        valid, clean_name = validate_single_filename(folder_name)
        if not valid:
            return False, clean_name
        target = f"{base_dir.rstrip('/')}/{clean_name}" if is_remote else os.path.join(base_dir, clean_name)
        if is_remote:
            return self.run_android_shell(f"mkdir -p {shlex.quote(target)}")
        try:
            os.makedirs(target, exist_ok=True)
            return True, "Pasta criada."
        except PermissionError:
            if self.root_enabled and self.sudo_password:
                return self._run_cmd(["sudo", "-S", "mkdir", "-p", target], input_text=self.sudo_password + "\n")
            return False, "Permissão negada."
        except Exception as exc:
            return False, str(exc)

    def create_empty_file(self, base_dir: str, file_name: str, is_remote: bool) -> Tuple[bool, str]:
        if "::" in base_dir:
            return False, "Não é possível criar arquivos dentro de um pacote fechado."
        valid, clean_name = validate_single_filename(file_name)
        if not valid:
            return False, clean_name
        target = f"{base_dir.rstrip('/')}/{clean_name}" if is_remote else os.path.join(base_dir, clean_name)
        if is_remote:
            return self.run_android_shell(f"touch {shlex.quote(target)}")
        try:
            Path(target).touch(exist_ok=True)
            return True, "Documento criado."
        except PermissionError:
            if self.root_enabled and self.sudo_password:
                return self._run_cmd(["sudo", "-S", "touch", target], input_text=self.sudo_password + "\n")
            return False, "Permissão negada."
        except Exception as exc:
            return False, str(exc)

    def chmod_item(self, path: str, mode_octal: str, is_remote: bool) -> Tuple[bool, str]:
        if "::" in path:
            return False, "Não aplicável a itens internos de pacotes."
        clean_octal = str(mode_octal).strip()
        if not re.match(r"^[0-7]{3,4}$", clean_octal):
            return False, "Nível de acesso inválido."
        if clean_octal in ("777", "0777") and not self.root_enabled:
            return False, "O nível Acesso Total requer que o botão Acesso Total esteja ativo."
        if is_remote:
            return self.run_android_shell(f"chmod -R {shlex.quote(clean_octal)} {shlex.quote(path)}")
        try:
            os.chmod(path, int(clean_octal, 8))
            return True, "Nível de acesso atualizado."
        except PermissionError:
            if self.root_enabled and self.sudo_password:
                return self._run_cmd(["sudo", "-S", "chmod", "-R", clean_octal, path], input_text=self.sudo_password + "\n")
            return False, "Permissão negada."
        except Exception as exc:
            return False, str(exc)

    def delete_item(self, path: str, is_remote: bool, permanent_root: bool = False) -> Tuple[bool, str]:
        if "::" in path:
            return False, "Não é permitido apagar arquivos dentro de um pacote fechado."
        norm = os.path.normpath(path.strip())
        protected = {
            "/", "/system", "/data", "/sdcard", "/storage", "/etc", "/usr",
            "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys", "/var",
            os.path.normpath(os.path.expanduser("~"))
        }
        if norm in protected or norm == "/":
            return False, "Proteção de segurança: Não é permitido apagar pastas vitais do sistema."
        if permanent_root and not self.root_enabled:
            return False, "Exclusão definitiva requer Acesso Total ativo."
        if is_remote:
            if permanent_root and self.root_enabled:
                cmd = (
                    f"if [ -f {shlex.quote(norm)} ] && command -v shred >/dev/null 2>&1; then "
                    f"shred -f -u -z -n 1 {shlex.quote(norm)}; else rm -rf {shlex.quote(norm)}; fi && sync"
                )
                return self.run_android_shell(cmd)
            return self.run_android_shell(f"rm -rf {shlex.quote(norm)}")

        try:
            if permanent_root and self.root_enabled and self.sudo_password:
                if os.path.isfile(norm) and shutil.which("shred"):
                    return self._run_cmd(["sudo", "-S", "shred", "-f", "-u", "-z", "-n", "1", norm], input_text=self.sudo_password + "\n")
                return self._run_cmd(["sudo", "-S", "rm", "-rf", norm], input_text=self.sudo_password + "\n")
            if os.path.isdir(norm) and not os.path.islink(norm):
                shutil.rmtree(norm)
            else:
                os.remove(norm)
            return True, "Item apagado."
        except PermissionError:
            if self.root_enabled and self.sudo_password:
                return self._run_cmd(["sudo", "-S", "rm", "-rf", norm], input_text=self.sudo_password + "\n")
            return False, "Permissão negada."
        except Exception as exc:
            return False, str(exc)
