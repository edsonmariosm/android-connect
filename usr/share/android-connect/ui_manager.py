"""
Gerenciador Dual-Pane Inteligente (Computador e Celular) — Versão 2.1 Auditada e Ampliada.
"""
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from qt_compat import (
    Qt, QSize, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QFrame,
    QMenu, QMessageBox, QInputDialog, QHeaderView, QProgressBar,
    QAbstractItemView, QCursor, load_svg_icon, exec_dialog, exec_menu
)
from adb_backend import AdbController, FileEntry, get_private_runtime_dir
from temp_watcher import LiveTempEditorManager
from ui_dialogs import (
    SettingsDialog, MiniTextEditorDialog, QuickPreviewDialog,
    BatchRenameDialog, GlobalSearchDialog, PermissionChmodDialog
)


class FilePaneWidget(QWidget):
    """Painel individual com layout ampliado, ícones 24x24, busca, filtro, ordenação e indicador de espaço."""
    def __init__(
        self,
        title: str,
        is_remote: bool,
        initial_path: str,
        adb_ctrl: AdbController,
        on_context_action,
        on_double_click_file,
        on_status_message,
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.is_remote = is_remote
        self.current_path = initial_path
        self.adb = adb_ctrl
        self.on_context_action = on_context_action
        self.on_double_click_file = on_double_click_file
        self.on_status_message = on_status_message
        self.entries_map: Dict[str, FileEntry] = {}
        self.all_entries: List[FileEntry] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QFrame(self)
        header.setObjectName("PaneHeaderRemote" if self.is_remote else "PaneHeaderLocal")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        title_lbl = QLabel(self.title)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #FFFFFF;")
        top_row.addWidget(title_lbl)

        top_row.addStretch(1)

        self.storage_lbl = QLabel("")
        self.storage_lbl.setStyleSheet("font-size: 12px; color: #CBD5E1; padding-right: 6px;")
        top_row.addWidget(self.storage_lbl)

        new_doc_btn = QPushButton("")
        new_doc_btn.setIcon(load_svg_icon("note_add.svg"))
        new_doc_btn.setIconSize(QSize(20, 20))
        new_doc_btn.setToolTip("Novo Documento")
        new_doc_btn.setObjectName("IconButton")
        new_doc_btn.clicked.connect(self._create_new_doc)
        top_row.addWidget(new_doc_btn)

        new_folder_btn = QPushButton("")
        new_folder_btn.setIcon(load_svg_icon("new_folder.svg"))
        new_folder_btn.setIconSize(QSize(20, 20))
        new_folder_btn.setToolTip("Nova Pasta")
        new_folder_btn.setObjectName("IconButton")
        new_folder_btn.clicked.connect(lambda: self.on_context_action("mkdir", [], self.is_remote))
        top_row.addWidget(new_folder_btn)

        search_btn = QPushButton("")
        search_btn.setIcon(load_svg_icon("search.svg"))
        search_btn.setIconSize(QSize(20, 20))
        search_btn.setToolTip("Pesquisa Global")
        search_btn.setObjectName("IconButton")
        search_btn.clicked.connect(self._open_global_search)
        top_row.addWidget(search_btn)

        h_layout.addLayout(top_row)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        # Botão subir pasta estritamente com o ícone SVG (sem texto)
        up_btn = QPushButton("")
        up_btn.setIcon(load_svg_icon("up.svg"))
        up_btn.setIconSize(QSize(22, 22))
        up_btn.setToolTip("Voltar para a pasta anterior")
        up_btn.setObjectName("IconButton")
        up_btn.clicked.connect(self.navigate_up)
        nav_row.addWidget(up_btn)

        self.path_edit = QLineEdit(self.current_path)
        self.path_edit.returnPressed.connect(lambda: self.navigate_to(self.path_edit.text().strip()))
        nav_row.addWidget(self.path_edit, 1)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtrar na pasta...")
        self.filter_edit.setFixedWidth(190)
        self.filter_edit.textChanged.connect(self._apply_filter)
        nav_row.addWidget(self.filter_edit)

        refresh_btn = QPushButton("")
        refresh_btn.setIcon(load_svg_icon("refresh.svg"))
        refresh_btn.setIconSize(QSize(20, 20))
        refresh_btn.setToolTip("Atualizar lista")
        refresh_btn.setObjectName("IconButton")
        refresh_btn.clicked.connect(self.refresh)
        nav_row.addWidget(refresh_btn)

        h_layout.addLayout(nav_row)
        layout.addWidget(header)

        self.tree = QTreeWidget(self)
        self.tree.setIconSize(QSize(24, 24))
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Nome", "Tamanho", "Nível de Acesso", "Data de Modificação"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setSortingEnabled(True)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
            if hasattr(QAbstractItemView, "SelectionMode")
            else QAbstractItemView.ExtendedSelection
        )

        header_v = self.tree.header()
        if hasattr(QHeaderView, "ResizeMode"):
            header_v.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header_v.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header_v.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header_v.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.tree.itemClicked.connect(self._on_single_click)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
            if hasattr(Qt, "ContextMenuPolicy")
            else Qt.CustomContextMenu
        )
        self.tree.customContextMenuRequested.connect(self._on_right_click)

        layout.addWidget(self.tree, 1)

    def navigate_up(self):
        if "::" in self.current_path:
            arch, sub = self.current_path.split("::", 1)
            parts = [p for p in sub.strip("/").split("/") if p]
            if len(parts) > 1:
                new_sub = "/".join(parts[:-1])
                self.navigate_to(f"{arch}::{new_sub}")
            else:
                self.navigate_to(os.path.dirname(arch) or "/")
            return
        parent = os.path.dirname(self.current_path.rstrip("/")) or "/"
        self.navigate_to(parent)

    def navigate_to(self, target_path: str):
        if not target_path:
            return
        self.current_path = target_path
        self.path_edit.setText(target_path)
        self.refresh()

    def refresh(self):
        self.tree.clear()
        self.entries_map.clear()
        self.all_entries.clear()

        _, _, st_str = self.adb.get_storage_info(self.is_remote, self.current_path)
        self.storage_lbl.setText(st_str)

        if self.is_remote:
            ok, entries, resolved = self.adb.list_android_dir(self.current_path)
        else:
            ok, entries, resolved = self.adb.list_local_dir(self.current_path)

        if not ok:
            self.on_status_message(f"[{'Celular' if self.is_remote else 'Computador'}] {resolved}")
            return

        self.current_path = resolved
        self.path_edit.setText(resolved)
        self.all_entries = list(entries)
        self._populate_tree(entries)

    def _populate_tree(self, entries: List[FileEntry]):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole

        if self.current_path != "/":
            up_item = QTreeWidgetItem(["..", "", "", ""])
            up_item.setIcon(0, load_svg_icon("up.svg"))
            up_item.setData(0, role, "__UP__")
            self.tree.addTopLevelItem(up_item)

        for entry in entries:
            ext = entry.name.lower().rsplit(".", 1)[-1] if "." in entry.name else ""
            if entry.is_dir:
                icon_name = "folder.svg"
            elif ext in ("zip", "jar", "tar", "gz"):
                icon_name = "zip.svg"
            elif ext == "apk":
                icon_name = "apk.svg"
            elif ext in ("html", "xml", "json", "sh", "py", "c", "cpp", "js", "css"):
                icon_name = "html.svg"
            else:
                icon_name = "file.svg"

            item = QTreeWidgetItem([
                entry.name,
                entry.human_size,
                entry.perm_label,
                entry.modified
            ])
            item.setIcon(0, load_svg_icon(icon_name))
            item.setData(0, role, entry.path)
            self.entries_map[entry.path] = entry
            self.tree.addTopLevelItem(item)

        self.tree.setSortingEnabled(True)
        self.on_status_message(f"{len(entries)} item(ns) em {self.current_path}")

    def _apply_filter(self, text: str):
        t = text.strip().lower()
        if not t:
            self._populate_tree(self.all_entries)
            return
        filtered = [e for e in self.all_entries if t in e.name.lower()]
        self._populate_tree(filtered)

    def selected_entries(self) -> List[FileEntry]:
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        res = []
        for item in self.tree.selectedItems():
            p = item.data(0, role)
            if p and p != "__UP__" and p in self.entries_map:
                res.append(self.entries_map[p])
        return res

    def _on_single_click(self, item: QTreeWidgetItem, _col: int):
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        p = item.data(0, role)
        if p == "__UP__":
            return
        entry = self.entries_map.get(p)
        if entry:
            self.on_status_message(f"Selecionado: {entry.name}  •  {entry.human_size}  •  {entry.perm_label}")

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        p = item.data(0, role)
        if p == "__UP__":
            self.navigate_up()
            return
        entry = self.entries_map.get(p)
        if not entry:
            return

        if entry.is_archive:
            if not self.is_remote:
                self.navigate_to(f"{entry.path}::")
            else:
                # Para pacotes remotos (.zip/.apk), baixa em cache seguro e abre como pasta
                cache_dir = get_private_runtime_dir() / "remote_archives"
                cache_dir.mkdir(parents=True, exist_ok=True)
                safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", entry.name)
                local_arch = str(cache_dir / safe_name)
                ok, msg = self.adb.pull_item(entry.path, local_arch)
                if ok and os.path.isfile(local_arch):
                    self.navigate_to(f"{local_arch}::")
                else:
                    QMessageBox.warning(self, "Erro ao Abrir Pacote", msg)
            return

        if entry.is_dir:
            self.navigate_to(entry.path)
        else:
            self.on_double_click_file(entry, self.is_remote)

    def _create_new_doc(self):
        name, ok = QInputDialog.getText(self, "Novo Documento", "Nome do novo documento (ex: notas.txt):")
        if not ok:
            return
        if not name.strip():
            QMessageBox.warning(self, "Nome Inválido", "O nome do documento não pode estar vazio.")
            return
        success, msg = self.adb.create_empty_file(self.current_path, name.strip(), self.is_remote)
        if success:
            self.refresh()
        else:
            QMessageBox.warning(self, "Não foi possível criar", msg)

    def _open_global_search(self):
        dlg = GlobalSearchDialog(self.current_path, self.is_remote, self.adb, on_select_callback=self._jump_to_searched, parent=self)
        exec_dialog(dlg)

    def _jump_to_searched(self, full_path: str):
        if not self.is_remote and os.path.isdir(full_path):
            self.navigate_to(full_path)
        else:
            parent = os.path.dirname(full_path.rstrip("/")) or "/"
            self.navigate_to(parent)

    def _on_right_click(self, _pos):
        entries = self.selected_entries()
        menu = QMenu(self)

        direction = "Copiar para o Computador" if self.is_remote else "Copiar para o Celular"
        move_dir = "Mover para o Computador" if self.is_remote else "Mover para o Celular"

        act_copy = menu.addAction(load_svg_icon("download.svg" if self.is_remote else "upload.svg"), direction)
        act_move = menu.addAction(load_svg_icon("sync.svg"), move_dir)
        menu.addSeparator()

        is_single = len(entries) == 1
        is_folder = is_single and entries[0].is_dir

        act_preview = None
        act_mini_edit = None
        if not is_folder:
            act_preview = menu.addAction(load_svg_icon("visibility.svg"), "Pré-visualizar (Espaço)")
            act_mini_edit = menu.addAction(load_svg_icon("edit.svg"), "Editar no Mini Editor")

        open_label = "Abrir Pasta" if is_folder else "Abrir no Computador"
        act_open = menu.addAction(load_svg_icon("folder.svg" if is_folder else "file_open.svg"), open_label)

        menu.addSeparator()
        act_rename = menu.addAction(load_svg_icon("edit.svg"), "Renomear")
        act_mkdir = menu.addAction(load_svg_icon("new_folder.svg"), "Nova Pasta")
        act_new_file = menu.addAction(load_svg_icon("note_add.svg"), "Novo Documento")
        act_chmod = menu.addAction(load_svg_icon("key.svg"), "Controle de Acesso")

        menu.addSeparator()
        act_delete = menu.addAction(load_svg_icon("delete_forever.svg"), "Apagar")

        act_shred = None
        if self.adb.root_enabled:
            act_shred = menu.addAction(load_svg_icon("block.svg"), "Apagar Definitivamente")

        chosen = exec_menu(menu, QCursor.pos())
        if not chosen:
            return

        if chosen == act_copy:
            self.on_context_action("copy", entries, self.is_remote)
        elif chosen == act_move:
            self.on_context_action("move", entries, self.is_remote)
        elif act_preview and chosen == act_preview and entries:
            self.on_context_action("preview", entries, self.is_remote)
        elif act_mini_edit and chosen == act_mini_edit and len(entries) == 1:
            self.on_context_action("mini_edit", entries, self.is_remote)
        elif chosen == act_open and len(entries) == 1:
            e = entries[0]
            if e.is_dir:
                self.navigate_to(e.path)
            else:
                self.on_double_click_file(e, self.is_remote)
        elif chosen == act_rename:
            self.on_context_action("rename", entries, self.is_remote)
        elif chosen == act_mkdir:
            self.on_context_action("mkdir", entries, self.is_remote)
        elif chosen == act_new_file:
            self._create_new_doc()
        elif chosen == act_chmod and entries:
            self.on_context_action("chmod", entries, self.is_remote)
        elif chosen == act_delete and entries:
            self.on_context_action("delete", entries, self.is_remote)
        elif act_shred and chosen == act_shred and entries:
            self.on_context_action("delete_permanent", entries, self.is_remote)


class DualPaneManagerScreen(QWidget):
    """Tela Principal Dual-Pane Ampliada com tema dinâmico, configurações e tratamento completo de erros."""
    def __init__(self, adb_ctrl: AdbController, settings_store, on_back_to_connect, parent=None):
        super().__init__(parent)
        self.adb = adb_ctrl
        self.settings = settings_store
        self.on_back_to_connect = on_back_to_connect
        self.temp_editor = LiveTempEditorManager(
            self.adb,
            on_modified_callback=self._prompt_overwrite_remote,
            parent=self
        )
        self.temp_editor.backup_enabled = bool(self.settings.data.get("backup_enabled", True))
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 10)
        main_layout.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        conn_btn = QPushButton("Trocar Celular")
        conn_btn.setIcon(load_svg_icon("sync.svg"))
        conn_btn.setIconSize(QSize(20, 20))
        conn_btn.clicked.connect(self.on_back_to_connect)
        top_bar.addWidget(conn_btn)

        self.device_badge = QLabel("Celular: Desconectado")
        self.device_badge.setStyleSheet("font-weight: bold; color: #38BDF8; padding-left: 8px; font-size: 14px;")
        top_bar.addWidget(self.device_badge)

        top_bar.addStretch(1)

        compare_btn = QPushButton("Comparar Pastas")
        compare_btn.setIcon(load_svg_icon("compare.svg"))
        compare_btn.setIconSize(QSize(20, 20))
        compare_btn.setToolTip("Comparar itens entre Computador e Celular")
        compare_btn.clicked.connect(self._compare_folders)
        top_bar.addWidget(compare_btn)

        settings_btn = QPushButton("Configurações")
        settings_btn.setIcon(load_svg_icon("settings.svg"))
        settings_btn.setIconSize(QSize(20, 20))
        settings_btn.setToolTip("Preferências de fonte, conexão e segurança")
        settings_btn.clicked.connect(self._open_settings)
        top_bar.addWidget(settings_btn)

        self.root_btn = QPushButton("Acesso Total: Desativado")
        self.root_btn.setObjectName("RootToggleFalse")
        self.root_btn.setIcon(load_svg_icon("block.svg"))
        self.root_btn.setIconSize(QSize(20, 20))
        self.root_btn.setCursor(Qt.CursorShape.PointingHandCursor if hasattr(Qt, "CursorShape") else Qt.PointingHandCursor)
        self.root_btn.clicked.connect(self._toggle_root)
        top_bar.addWidget(self.root_btn)

        main_layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal if hasattr(Qt, "Orientation") else Qt.Horizontal, self)
        splitter.setHandleWidth(8)

        self.local_pane = FilePaneWidget(
            title="COMPUTADOR",
            is_remote=False,
            initial_path=str(Path.home()),
            adb_ctrl=self.adb,
            on_context_action=self._handle_action,
            on_double_click_file=self._handle_open_file,
            on_status_message=self._set_status
        )

        self.remote_pane = FilePaneWidget(
            title="CELULAR",
            is_remote=True,
            initial_path="/sdcard",
            adb_ctrl=self.adb,
            on_context_action=self._handle_action,
            on_double_click_file=self._handle_open_file,
            on_status_message=self._set_status
        )

        splitter.addWidget(self.local_pane)
        splitter.addWidget(self.remote_pane)
        splitter.setSizes([750, 750])

        main_layout.addWidget(splitter, 1)

        self.status_lbl = QLabel(
            "Atalhos: Tab (alternar painel)  •  Espaço (pré-visualizar)  •  F5 (copiar)  •  F6 (mover)  •  F7 (nova pasta)  •  Delete (apagar)"
        )
        self.status_lbl.setStyleSheet("color: #94A3B8; padding: 4px 6px;")
        main_layout.addWidget(self.status_lbl)

    def refresh_all(self):
        s = self.adb.device_serial or "Modo Somente Computador"
        self.device_badge.setText(f"Celular: {s}")
        self.local_pane.refresh()
        self.remote_pane.refresh()

    def _set_status(self, text: str):
        self.status_lbl.setText(text)

    def keyPressEvent(self, event):
        key = event.key()
        active_pane = self.remote_pane if self.remote_pane.tree.hasFocus() else self.local_pane
        entries = active_pane.selected_entries()

        if key == (Qt.Key.Key_Tab if hasattr(Qt, "Key") else Qt.Key_Tab):
            if self.local_pane.tree.hasFocus():
                self.remote_pane.tree.setFocus()
            else:
                self.local_pane.tree.setFocus()
        elif key == (Qt.Key.Key_Space if hasattr(Qt, "Key") else Qt.Key_Space):
            if entries:
                self._handle_action("preview", entries, active_pane.is_remote)
        elif key == (Qt.Key.Key_F5 if hasattr(Qt, "Key") else Qt.Key_F5):
            if entries:
                self._handle_action("copy", entries, active_pane.is_remote)
        elif key == (Qt.Key.Key_F6 if hasattr(Qt, "Key") else Qt.Key_F6):
            if entries:
                self._handle_action("move", entries, active_pane.is_remote)
        elif key == (Qt.Key.Key_F7 if hasattr(Qt, "Key") else Qt.Key_F7):
            self._handle_action("mkdir", [], active_pane.is_remote)
        elif key in ((Qt.Key.Key_Delete if hasattr(Qt, "Key") else Qt.Key_Delete),
                     (Qt.Key.Key_F8 if hasattr(Qt, "Key") else Qt.Key_F8)):
            if entries:
                self._handle_action("delete", entries, active_pane.is_remote)
        else:
            super().keyPressEvent(event)

    def _apply_current_theme(self):
        from styles import generate_theme
        top_win = self.window()
        fam = self.settings.data.get("font_family")
        sz = self.settings.data.get("font_size", 12)
        use_green = self.adb.root_enabled and bool(self.settings.data.get("theme_dynamic", True))
        top_win.setStyleSheet(generate_theme(is_root=use_green, font_family=fam, font_size=sz))

    def _toggle_root(self):
        if self.adb.root_enabled:
            self.adb.set_root_mode(False)
            self.root_btn.setText("Acesso Total: Desativado")
            self.root_btn.setObjectName("RootToggleFalse")
            self.root_btn.setIcon(load_svg_icon("block.svg"))
            self._apply_current_theme()
            QMessageBox.information(self, "Acesso Total Desativado", "O programa voltou ao modo de segurança padrão.")
            self.refresh_all()
            return

        pwd_mode = QLineEdit.EchoMode.Password if hasattr(QLineEdit, "EchoMode") else QLineEdit.Password
        pwd, ok = QInputDialog.getText(
            self,
            "Senha do Computador",
            "Digite a senha do seu computador para ativar o Acesso Total:",
            pwd_mode
        )
        if not ok or not pwd:
            return

        ok_root, msg = self.adb.set_root_mode(True, pwd)
        if ok_root:
            self.root_btn.setText("Acesso Total: Ativo")
            self.root_btn.setObjectName("RootToggleTrue")
            self.root_btn.setIcon(load_svg_icon("key.svg"))
            self._apply_current_theme()
            QMessageBox.information(self, "Acesso Total Ativado", msg)
            self.refresh_all()
        else:
            QMessageBox.critical(self, "Senha Incorreta", msg)

    def _open_settings(self):
        def apply_cb(new_cfg):
            self.settings.save(new_cfg)
            self.temp_editor.backup_enabled = bool(self.settings.data.get("backup_enabled", True))
            self._apply_current_theme()
            fam = self.settings.data.get("font_family")
            sz = self.settings.data.get("font_size")
            self._set_status(f"Configurações salvas — Fonte: {fam} ({sz}pt)")

        dlg = SettingsDialog(self.settings.data, on_apply_settings_cb=apply_cb, parent=self)
        exec_dialog(dlg)

    def _compare_folders(self):
        local_map = {e.name: e for e in self.local_pane.all_entries if not e.is_dir}
        remote_map = {e.name: e for e in self.remote_pane.all_entries if not e.is_dir}

        only_pc = set(local_map.keys()) - set(remote_map.keys())
        only_phone = set(remote_map.keys()) - set(local_map.keys())
        common = set(local_map.keys()) & set(remote_map.keys())
        diff_size = {n for n in common if local_map[n].size != remote_map[n].size}

        msg = (
            f"<b>Comparação entre as pastas abertas:</b><br><br>"
            f"• Arquivos exclusivos do Computador: <b>{len(only_pc)}</b><br>"
            f"• Arquivos exclusivos do Celular: <b>{len(only_phone)}</b><br>"
            f"• Arquivos com mesmo nome e tamanho diferente: <b>{len(diff_size)}</b><br>"
            f"• Arquivos idênticos em ambos: <b>{len(common) - len(diff_size)}</b>"
        )
        QMessageBox.information(self, "Comparação de Pastas", msg)

    def _handle_open_file(self, entry: FileEntry, is_remote: bool):
        if not is_remote:
            if "::" in entry.path:
                tmp_dir = get_private_runtime_dir() / "open_arch"
                ok, res = self.adb.extract_archive_member(entry.path, str(tmp_dir))
                if not ok:
                    QMessageBox.warning(self, "Aviso", res)
                    return
                target = res
            else:
                target = entry.path
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        ok, res = self.temp_editor.open_remote_file_in_tmp(entry.path)
        if not ok:
            QMessageBox.warning(self, "Aviso", res)

    def _prompt_overwrite_remote(self, local_path: str, remote_path: str):
        yes_btn = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
        no_btn = QMessageBox.StandardButton.No if hasattr(QMessageBox, "StandardButton") else QMessageBox.No

        name = os.path.basename(remote_path)
        ans = QMessageBox.question(
            self,
            "Salvar Alterações no Celular",
            f"Você salvou alterações em '{name}'.\n\nDeseja atualizar o arquivo no celular com a nova versão?",
            yes_btn | no_btn
        )
        if ans == yes_btn:
            dest_dir = os.path.dirname(remote_path.rstrip("/")) or "/"
            ok, msg = self.adb.push_item(local_path, dest_dir)
            if ok:
                self.remote_pane.refresh()
            else:
                QMessageBox.critical(self, "Erro ao Salvar no Celular", msg)
        self.temp_editor.mark_prompt_finished(local_path)

    def _execute_two_phase_batch_rename(self, plan: List[Tuple[FileEntry, str]], is_remote: bool) -> List[str]:
        """Executa renomeação em lote em 2 fases para evitar colisão de nomes entre arquivos da lista."""
        errors: List[str] = []
        staging: List[Tuple[str, str, str]] = []
        token = uuid.uuid4().hex[:6]

        for idx, (item, final_name) in enumerate(plan):
            if item.name == final_name:
                continue
            tmp_name = f"._ac_ren_{token}_{idx}_{final_name}"
            ok, msg = self.adb.rename_item(item.path, tmp_name, is_remote)
            if ok:
                parent = os.path.dirname(item.path.rstrip("/"))
                tmp_path = os.path.join(parent, tmp_name) if not is_remote else f"{parent.rstrip('/')}/{tmp_name}"
                staging.append((tmp_path, final_name, item.name))
            else:
                errors.append(f"{item.name}: {msg}")

        for tmp_path, final_name, orig_name in staging:
            ok, msg = self.adb.rename_item(tmp_path, final_name, is_remote)
            if not ok:
                self.adb.rename_item(tmp_path, orig_name, is_remote)
                errors.append(f"{orig_name} -> {final_name}: {msg}")

        return errors

    def _handle_action(self, action: str, entries: List[FileEntry], from_remote: bool):
        if action == "mkdir":
            pane = self.remote_pane if from_remote else self.local_pane
            name, ok = QInputDialog.getText(self, "Nova Pasta", "Nome da nova pasta:")
            if ok and name.strip():
                success, msg = self.adb.mkdir_item(pane.current_path, name.strip(), from_remote)
                if not success:
                    QMessageBox.warning(self, "Não foi possível criar a pasta", msg)
                pane.refresh()
            return

        if not entries:
            return

        if action == "copy":
            dest_pane = self.local_pane if from_remote else self.remote_pane
            errors = []
            for e in entries:
                if from_remote:
                    ok, msg = self.adb.pull_item(e.path, dest_pane.current_path)
                else:
                    ok, msg = self.adb.push_item(e.path, dest_pane.current_path)
                if not ok:
                    errors.append(f"{e.name}: {msg}")
            self.refresh_all()
            if errors:
                QMessageBox.warning(self, "Aviso na Cópia", "\n".join(errors[:5]))

        elif action == "move":
            dest_pane = self.local_pane if from_remote else self.remote_pane
            errors = []
            for e in entries:
                if from_remote:
                    ok, msg = self.adb.pull_item(e.path, dest_pane.current_path)
                else:
                    ok, msg = self.adb.push_item(e.path, dest_pane.current_path)
                if ok:
                    ok_del, msg_del = self.adb.delete_item(e.path, from_remote)
                    if not ok_del:
                        errors.append(f"{e.name} (copiado, mas não removido da origem): {msg_del}")
                else:
                    errors.append(f"{e.name}: {msg}")
            self.refresh_all()
            if errors:
                QMessageBox.warning(self, "Aviso ao Mover", "\n".join(errors[:5]))

        elif action == "preview":
            if not entries:
                QMessageBox.information(self, "Aviso", "Selecione um arquivo para pré-visualizar.")
                return
            e = entries[0]
            if e.is_dir:
                QMessageBox.information(self, "Aviso", "Pastas não possuem pré-visualização; dê duplo clique para abrir.")
                return

            priv_dir = get_private_runtime_dir() / "preview"
            priv_dir.mkdir(parents=True, exist_ok=True)
            clean_name = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(e.name))
            tmp_p = str(priv_dir / f"prev_{clean_name}")
            cleanup_after = False

            if "::" in e.path:
                ok, res = self.adb.extract_archive_member(e.path, str(priv_dir))
                if not ok:
                    QMessageBox.warning(self, "Erro ao Abrir Item do Pacote", f"Não foi possível extrair para prévia: {res}")
                    return
                p_to_show = res
                cleanup_after = True
            elif from_remote:
                ok, msg = self.adb.pull_item(e.path, tmp_p)
                if not ok:
                    QMessageBox.warning(self, "Erro ao Baixar Arquivo", f"Não foi possível baixar para prévia: {msg}")
                    return
                p_to_show = tmp_p
                cleanup_after = True
            else:
                p_to_show = e.path
                if not os.path.isfile(p_to_show):
                    QMessageBox.warning(self, "Arquivo Inacessível", f"O arquivo não foi encontrado no computador: {p_to_show}")
                    return

            def open_externally():
                self.on_double_click_file(e, from_remote)

            dlg = QuickPreviewDialog(e, p_to_show, on_open_external_cb=open_externally, parent=self)
            exec_dialog(dlg)
            if cleanup_after and p_to_show and os.path.isfile(p_to_show):
                try:
                    os.remove(p_to_show)
                except Exception:
                    pass

        elif action == "mini_edit":
            e = entries[0]
            if e.is_dir or "::" in e.path:
                QMessageBox.information(self, "Aviso", "Selecione um arquivo comum para editar.")
                return
            priv_dir = get_private_runtime_dir() / "miniedit"
            priv_dir.mkdir(parents=True, exist_ok=True)
            clean_name = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(e.name))
            tmp_p = str(priv_dir / f"edit_{clean_name}")

            if from_remote:
                ok, msg = self.adb.pull_item(e.path, tmp_p)
                if not ok:
                    QMessageBox.warning(self, "Erro ao Baixar Arquivo", msg)
                    return
                local_file = tmp_p
            else:
                local_file = e.path

            content = ""
            if os.path.isfile(local_file):
                try:
                    with open(local_file, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception as exc:
                    QMessageBox.warning(self, "Erro de Leitura", str(exc))
                    return

            def save_cb(new_text: str) -> Tuple[bool, str]:
                try:
                    with open(local_file, "w", encoding="utf-8") as f:
                        f.write(new_text)
                    if from_remote:
                        ok_p, msg_p = self.adb.push_item(local_file, os.path.dirname(e.path))
                        if not ok_p:
                            return False, msg_p
                    self.refresh_all()
                    return True, "Salvo"
                except Exception as ex:
                    return False, str(ex)

            dlg = MiniTextEditorDialog(e.name, content, save_cb, parent=self)
            exec_dialog(dlg)
            if from_remote and os.path.isfile(tmp_p):
                try:
                    os.remove(tmp_p)
                except Exception:
                    pass

        elif action == "rename":
            if len(entries) == 1:
                e = entries[0]
                new_n, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=e.name)
                if ok and new_n.strip():
                    success, msg = self.adb.rename_item(e.path, new_n.strip(), from_remote)
                    if not success:
                        QMessageBox.warning(self, "Erro ao Renomear", msg)
                    self.refresh_all()
            else:
                dlg = BatchRenameDialog(entries, parent=self)
                if exec_dialog(dlg):
                    plan = dlg.get_rename_plan()
                    errors = self._execute_two_phase_batch_rename(plan, from_remote)
                    self.refresh_all()
                    if errors:
                        QMessageBox.warning(self, "Avisos na Renomeação em Lote", "\n".join(errors[:5]))

        elif action == "chmod":
            dlg = PermissionChmodDialog(root_active=self.adb.root_enabled, parent=self)
            if exec_dialog(dlg):
                octal = dlg.get_selected_octal()
                errors = []
                for e in entries:
                    ok, msg = self.adb.chmod_item(e.path, octal, from_remote)
                    if not ok:
                        errors.append(f"{e.name}: {msg}")
                self.refresh_all()
                if errors:
                    QMessageBox.warning(self, "Aviso de Permissão", "\n".join(errors[:5]))

        elif action == "delete":
            if bool(self.settings.data.get("confirm_delete", True)):
                yes_btn = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
                no_btn = QMessageBox.StandardButton.No if hasattr(QMessageBox, "StandardButton") else QMessageBox.No
                ans = QMessageBox.question(
                    self, "Confirmar Exclusão", f"Deseja apagar {len(entries)} item(ns) selecionado(s)?", yes_btn | no_btn
                )
                if ans != yes_btn:
                    return
            errors = []
            for e in entries:
                ok, msg = self.adb.delete_item(e.path, from_remote)
                if not ok:
                    errors.append(f"{e.name}: {msg}")
            self.refresh_all()
            if errors:
                QMessageBox.warning(self, "Erro ao Apagar", "\n".join(errors[:5]))

        elif action == "delete_permanent":
            if not self.adb.root_enabled:
                return
            yes_btn = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
            no_btn = QMessageBox.StandardButton.No if hasattr(QMessageBox, "StandardButton") else QMessageBox.No
            ans = QMessageBox.critical(
                self,
                "Apagar Definitivamente",
                f"Você está prestes a apagar definitivamente {len(entries)} item(ns) da memória.\n\nEssa ação não pode ser desfeita. Deseja continuar?",
                yes_btn | no_btn
            )
            if ans == yes_btn:
                errors = []
                for e in entries:
                    ok, msg = self.adb.delete_item(e.path, from_remote, permanent_root=True)
                    if not ok:
                        errors.append(f"{e.name}: {msg}")
                self.refresh_all()
                if errors:
                    QMessageBox.critical(self, "Erro ao Apagar Definitivamente", "\n".join(errors[:5]))
