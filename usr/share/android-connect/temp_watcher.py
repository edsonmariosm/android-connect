"""
Gerenciador de abertura e edicao em tempo real com diretorio isolado 0700, auto-save e backup.
"""
import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Tuple
from qt_compat import QtCore, QFileSystemWatcher, QTimer
from adb_backend import get_private_runtime_dir


@dataclass
class WatchedSession:
    remote_path: str
    local_tmp_path: str
    backup_path: str
    last_sha256: str
    prompt_active: bool = False
    auto_save: bool = False


class LiveTempEditorManager(QtCore.QObject):
    def __init__(self, adb_ctrl, on_modified_callback: Callable[[str, str], None], parent=None):
        super().__init__(parent)
        self.adb = adb_ctrl
        self.on_modified_callback = on_modified_callback
        runtime_root = get_private_runtime_dir()
        self.base_tmp = runtime_root / "live"
        self.base_tmp.mkdir(parents=True, exist_ok=True)
        os.chmod(self.base_tmp, 0o700)

        self.backup_tmp = runtime_root / "backups"
        self.backup_tmp.mkdir(parents=True, exist_ok=True)
        os.chmod(self.backup_tmp, 0o700)

        self.backup_enabled: bool = True

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_event)
        self.watcher.addPath(str(self.base_tmp))

        self.sessions: Dict[str, WatchedSession] = {}
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1500)
        self.poll_timer.timeout.connect(self._check_all_sessions)
        self.poll_timer.start()

    @staticmethod
    def _file_sha256(path: str) -> str:
        if not os.path.isfile(path):
            return ""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def open_remote_file_in_tmp(self, remote_path: str) -> Tuple[bool, str]:
        path_hash = hashlib.sha256(remote_path.encode("utf-8")).hexdigest()[:12]
        raw_name = os.path.basename(remote_path)
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", raw_name) or "arquivo"
        session_dir = self.base_tmp / path_hash
        session_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(session_dir, 0o700)
        local_tmp_file = str(session_dir / safe_name)

        ok, msg = self.adb.pull_item(remote_path, local_tmp_file)
        if not ok or not os.path.isfile(local_tmp_file):
            return False, f"Falha ao preparar arquivo para edição:\n{msg}"

        os.chmod(local_tmp_file, 0o600)
        backup_file = str(self.backup_tmp / f"{path_hash}_{safe_name}.bak")
        if self.backup_enabled:
            shutil.copyfile(local_tmp_file, backup_file)
            os.chmod(backup_file, 0o600)

        initial_hash = self._file_sha256(local_tmp_file)
        self.sessions[local_tmp_file] = WatchedSession(
            remote_path=remote_path,
            local_tmp_path=local_tmp_file,
            backup_path=backup_file,
            last_sha256=initial_hash,
            prompt_active=False
        )
        self.watcher.addPath(str(session_dir))
        self.watcher.addPath(local_tmp_file)

        try:
            subprocess.Popen(["xdg-open", local_tmp_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            return False, f"Arquivo preparado, mas não abriu no programa externo: {exc}"
        return True, local_tmp_file

    def _on_file_event(self, path: str):
        if os.path.exists(path) and path not in self.watcher.files():
            self.watcher.addPath(path)
        self._inspect_session(path)

    def _check_all_sessions(self):
        for local_path in list(self.sessions.keys()):
            self._inspect_session(local_path)

    def _inspect_session(self, local_path: str):
        sess = self.sessions.get(local_path)
        if not sess or sess.prompt_active or not os.path.isfile(local_path):
            return
        cur_hash = self._file_sha256(local_path)
        if cur_hash and cur_hash != sess.last_sha256:
            sess.prompt_active = True
            sess.last_sha256 = cur_hash
            self.on_modified_callback(sess.local_tmp_path, sess.remote_path)

    def mark_prompt_finished(self, local_path: str):
        sess = self.sessions.get(local_path)
        if sess:
            sess.last_sha256 = self._file_sha256(local_path)
            sess.prompt_active = False
