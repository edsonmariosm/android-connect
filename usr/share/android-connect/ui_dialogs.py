import queue
import threading
"""
Diálogos inteligentes do Android Connect 2.1 (Layout Ampliado e Auditado):
- Mini editor de texto embutido (920x640)
- Prévia rápida de imagens, textos e pacotes (840x600)
- Renomeador em lote com suporte a $x, $pacote, &!, &? e prevenção de colisão (640x440)
- Busca global recursiva (840x560)
- Controle de acesso visual com Acesso Total restrito ao modo Root (520x380)
- Configurações com pesquisa instantânea, tópicos e persistência JSON (820x560)
"""
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from qt_compat import (
    Qt, QApplication, QThread, QTimer, pyqtSignal, QWidget, QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QProgressBar, QRadioButton, QButtonGroup,
    QCheckBox, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QMessageBox, QScrollArea, QPixmap, load_svg_icon, exec_dialog
)
from adb_backend import FileEntry, validate_single_filename


class MiniTextEditorDialog(QDialog):
    """Mini editor de texto integrado com layout ampliado e salvamento validado."""
    def __init__(self, title: str, initial_content: str, on_save_callback: Callable[[str], Tuple[bool, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editor de Texto — {title}")
        self.resize(920, 640)
        self.setMinimumSize(700, 480)
        self.on_save = on_save_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        lbl = QLabel(f"Editando: {title}")
        lbl.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 16px;")
        header.addWidget(lbl)
        header.addStretch(1)

        save_btn = QPushButton("Salvar Alterações")
        save_btn.setIcon(load_svg_icon("save.svg"))
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self._save_and_close)
        header.addWidget(save_btn)

        layout.addLayout(header)

        self.editor = QTextEdit(self)
        self.editor.setPlainText(initial_content)
        self.editor.setStyleSheet(
            "background-color: #0B1120; color: #F8FAFC; font-family: monospace; font-size: 14px; padding: 10px;"
        )
        layout.addWidget(self.editor, 1)

    def _save_and_close(self):
        ok, msg = self.on_save(self.editor.toPlainText())
        if ok:
            QMessageBox.information(self, "Salvo", "Alterações salvas com sucesso.")
            self.accept()
        else:
            QMessageBox.warning(self, "Erro ao Salvar", msg or "Não foi possível salvar o arquivo.")


class QuickPreviewDialog(QDialog):
    """
    Pré-visualização universal e resiliente:
    - Imagens: exibição renderizada proporcional com zoom confortável
    - Textos/Código/Configs/Scripts: leitor integrado limpo
    - Formatos binários/não suportados: fallback seguro que explica o motivo
      e oferece botão direto para abrir no aplicativo padrão do notebook.
    """
    def __init__(self, entry: FileEntry, local_path: str, on_open_external_cb: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Pré-visualização — {entry.name}")
        self.resize(840, 600)
        self.setMinimumSize(640, 440)
        self.local_path = local_path
        self.on_open_external = on_open_external_cb

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        info = QLabel(f"{entry.name}  •  {entry.human_size}  •  {entry.perm_label}")
        info.setStyleSheet("font-weight: bold; color: #10B981; font-size: 15px;")
        layout.addWidget(info)

        ext = entry.name.lower().rsplit(".", 1)[-1] if "." in entry.name else ""
        IMAGE_EXTS = {"png", "jpg", "jpeg", "bmp", "gif", "svg", "webp", "ico"}
        TEXT_EXTS = {
            "txt", "md", "json", "xml", "html", "htm", "css", "js", "ts", "py",
            "sh", "bash", "c", "cpp", "h", "hpp", "java", "kt", "rs", "go",
            "yaml", "yml", "ini", "conf", "cfg", "log", "prop", "properties", "csv"
        }

        # 1. Tratamento de Imagem
        if ext in IMAGE_EXTS and os.path.isfile(local_path):
            scroll = QScrollArea(self)
            img_lbl = QLabel()
            pix = QPixmap(local_path)
            if not pix.isNull():
                aspect = Qt.AspectRatioMode.KeepAspectRatio if hasattr(Qt, "AspectRatioMode") else Qt.KeepAspectRatio
                img_lbl.setPixmap(pix.scaled(760, 480, aspect, Qt.TransformationMode.SmoothTransformation if hasattr(Qt, "TransformationMode") else Qt.SmoothTransformation))
                img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
                scroll.setWidget(img_lbl)
                scroll.setWidgetResizable(True)
                layout.addWidget(scroll, 1)
            else:
                self._show_fallback_view(layout, entry, "O formato da imagem é incompatível ou o arquivo está corrompido.")
        # 2. Tratamento de Texto / Codigo / Logs
        elif ext in TEXT_EXTS and os.path.isfile(local_path):
            text_view = QTextEdit(self)
            text_view.setReadOnly(True)
            text_view.setStyleSheet("background-color: #0B1120; color: #E2E8F0; font-family: monospace; font-size: 13px; padding: 10px;")
            try:
                with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(65536)
                text_view.setPlainText(content or "(Arquivo vazio)")
                layout.addWidget(text_view, 1)
            except Exception as exc:
                self._show_fallback_view(layout, entry, f"Falha na leitura do texto: {exc}")
        # 3. Fallback Universal para outros tipos (PDF, Videos, Audios, APK, Binarios)
        else:
            motivo = (
                f"O arquivo tem a extensão '.{ext}', que não possui pré-visualizador interno embutido."
                if ext else "Este arquivo não possui extensão reconhecida para prévia direta."
            )
            self._show_fallback_view(layout, entry, motivo)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        if self.on_open_external:
            ext_btn = QPushButton("Abrir no Aplicativo do Computador")
            ext_btn.setIcon(load_svg_icon("file_open.svg"))
            ext_btn.setObjectName("PrimaryBtn")
            ext_btn.setMinimumHeight(42)
            ext_btn.clicked.connect(self._do_open_external)
            btn_row.addWidget(ext_btn)

        btn_row.addStretch(1)

        close_btn = QPushButton("Fechar")
        close_btn.setMinimumHeight(42)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _show_fallback_view(self, layout: QVBoxLayout, entry: FileEntry, motivo: str):
        card = QFrame(self)
        card.setObjectName("LoginCard")
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(28, 28, 28, 28)
        c_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_svg_icon("file_open.svg").pixmap(48, 48))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_lay.addWidget(icon_lbl)

        warn_title = QLabel("Pré-visualização Direta Não Disponível")
        warn_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #38BDF8;")
        warn_title.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_lay.addWidget(warn_title)

        reason_lbl = QLabel(motivo)
        reason_lbl.setWordWrap(True)
        reason_lbl.setStyleSheet("color: #94A3B8; font-size: 13px;")
        reason_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_lay.addWidget(reason_lbl)

        tip_lbl = QLabel("Clique no botão abaixo para abrir diretamente com o programa padrão do seu computador.")
        tip_lbl.setWordWrap(True)
        tip_lbl.setStyleSheet("color: #E2E8F0; font-weight: bold; font-size: 13px;")
        tip_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_lay.addWidget(tip_lbl)

        layout.addWidget(card, 1)

    def _do_open_external(self):
        self.accept()
        if self.on_open_external:
            self.on_open_external()


class BatchRenameDialog(QDialog):
    """
    Renomeador em lote com separação de nome.pacote e expressões:
    - $pacote = preserva o radical/pacote original do arquivo
    - $x = sequência numérica (1, 2, 3...)
    - &! = ordem ascendente (A-Z)
    - &? = ordem descendente (Z-A)
    """
    def __init__(self, entries: List[FileEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Renomear em Lote")
        self.resize(640, 440)
        self.setMinimumSize(560, 400)
        self.entries = list(entries)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        lbl = QLabel(f"Renomeando {len(self.entries)} itens selecionados")
        lbl.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 16px;")
        layout.addWidget(lbl)

        info = QLabel(
            "Expressões disponíveis:\n"
            "• $pacote = Mantém o nome/pacote base de cada item\n"
            "• $x = Número sequencial (1, 2, 3...)\n"
            "• &! = Ordenar em ordem ascendente (A-Z)\n"
            "• &? = Ordenar em ordem descendente (Z-A)\n"
            "A extensão final (.apk, .zip, .txt) é mantida automaticamente."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #94A3B8;")
        layout.addWidget(info)

        self.pattern_edit = QLineEdit("$pacote_$x &!")
        self.pattern_edit.setPlaceholderText("Ex: $pacote_$x &!  ou  Arquivo_$x &?")
        layout.addWidget(QLabel("Padrão do novo nome:"))
        layout.addWidget(self.pattern_edit)

        self.preview_lbl = QLabel("")
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setStyleSheet("color: #10B981; font-weight: bold;")
        layout.addWidget(self.preview_lbl)

        self.pattern_edit.textChanged.connect(self._update_preview)
        self._update_preview()

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Aplicar Renomeação")
        apply_btn.setObjectName("PrimaryBtn")
        apply_btn.setMinimumHeight(40)
        apply_btn.clicked.connect(self._validate_and_accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _split_package_and_ext(filename: str) -> Tuple[str, str]:
        """Separa nome.pacote da extensao final (ex: com.app.modulo.apk -> ('com.app.modulo', '.apk'))."""
        if "." in filename and not filename.startswith("."):
            dot_idx = filename.rfind(".")
            return filename[:dot_idx], filename[dot_idx:]
        return filename, ""

    def _sort_entries(self, pattern: str) -> List[FileEntry]:
        items = list(self.entries)
        if "&?" in pattern:
            items.sort(key=lambda e: e.name.lower(), reverse=True)
        elif "&!" in pattern:
            items.sort(key=lambda e: e.name.lower(), reverse=False)
        return items

    def _generate_names(self) -> List[Tuple[FileEntry, str]]:
        pat = self.pattern_edit.text().strip() or "$pacote_$x"
        sorted_items = self._sort_entries(pat)
        clean_pat = pat.replace("&!", "").replace("&?", "").strip() or "$pacote_$x"
        result: List[Tuple[FileEntry, str]] = []
        used_names = set()

        for idx, entry in enumerate(sorted_items, start=1):
            pkg_base, ext = self._split_package_and_ext(entry.name)
            candidate_base = clean_pat.replace("$pacote", pkg_base)
            if "$x" in candidate_base:
                candidate_base = candidate_base.replace("$x", str(idx))
            elif "$pacote" not in clean_pat:
                candidate_base = f"{candidate_base}_{idx}"

            # Remove barras ou caracteres proibidos
            candidate_base = re.sub(r"[/\\:\x00]", "_", candidate_base).strip() or f"Item_{idx}"
            final_name = f"{candidate_base}{ext}"
            while final_name.lower() in used_names:
                final_name = f"{candidate_base}_{idx}{ext}"
                idx += 1
            used_names.add(final_name.lower())
            result.append((entry, final_name))
        return result

    def _update_preview(self):
        names = self._generate_names()
        if names:
            first = f"{names[0][0].name}  ->  {names[0][1]}"
            last = f"{names[-1][0].name}  ->  {names[-1][1]}" if len(names) > 1 else ""
            txt = f"Prévia: {first}" + (f"\nÚltimo: {last}" if last else "")
            self.preview_lbl.setText(txt)

    def _validate_and_accept(self):
        plan = self._generate_names()
        for _, new_n in plan:
            ok, msg = validate_single_filename(new_n)
            if not ok:
                QMessageBox.warning(self, "Nome Inválido", msg)
                return
        self.accept()

    def get_rename_plan(self) -> List[Tuple[FileEntry, str]]:
        return self._generate_names()


class GlobalSearchDialog(QDialog):
    """Busca recursiva em todas as subpastas com janela ampliada (840x560)."""
    def __init__(self, base_dir: str, is_remote: bool, adb_ctrl, on_select_callback, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pesquisa Global de Arquivos e Pastas")
        self.resize(840, 560)
        self.setMinimumSize(680, 440)
        self.base_dir = base_dir
        self.is_remote = is_remote
        self.adb = adb_ctrl
        self.on_select = on_select_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel(f"Local da pesquisa: {'[Celular]' if is_remote else '[Computador]'} {base_dir}")
        header.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 15px;")
        layout.addWidget(header)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Digite o nome do arquivo ou pasta...")
        self.search_edit.returnPressed.connect(self._do_search)

        find_btn = QPushButton("Pesquisar")
        find_btn.setIcon(load_svg_icon("search.svg"))
        find_btn.setObjectName("PrimaryBtn")
        find_btn.setMinimumHeight(40)
        find_btn.clicked.connect(self._do_search)

        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(find_btn)
        layout.addLayout(search_row)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Nome", "Caminho Completo"])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._on_item_chosen)
        layout.addWidget(self.tree, 1)

        self.status = QLabel("Digite um nome acima e pressione Enter.")
        layout.addWidget(self.status)

    def _do_search(self):
        term = self.search_edit.text().strip()
        if not term:
            QMessageBox.warning(self, "Aviso", "Digite um nome para pesquisar.")
            return
        self.status.setText("Pesquisando em todas as subpastas...")
        self.tree.clear()
        results = run_with_loading(
            self,
            "Pesquisando Arquivos",
            f"Procurando por '{term}' nas subpastas...",
            lambda _prog: self.adb.global_search(self.base_dir, term, self.is_remote),
            total_steps=0
        )
        self.status.setText(f"{len(results)} resultado(s) encontrado(s). Dê duplo clique para abrir o local.")
        if not results:
            QMessageBox.information(self, "Pesquisa Concluída", f"Nenhum item encontrado para '{term}'.")
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        for r in results:
            it = QTreeWidgetItem([r.name, r.path])
            it.setIcon(0, load_svg_icon("folder.svg" if r.is_dir else "file.svg"))
            it.setData(0, role, r.path)
            self.tree.addTopLevelItem(it)

    def _on_item_chosen(self, item, _col):
        role = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
        p = item.data(0, role)
        if p:
            self.on_select(p)
            self.accept()


class PermissionChmodDialog(QDialog):
    """Controle de acesso com nomes legíveis e Acesso Total condicionado ao modo Root."""
    def __init__(self, root_active: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Controle de Acesso")
        self.resize(520, 380)
        self.setMinimumSize(460, 340)
        self.root_active = root_active

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Escolha o Nível de Permissão:")
        title.setStyleSheet("font-weight: bold; color: #F8FAFC; font-size: 16px;")
        layout.addWidget(title)

        self.group = QButtonGroup(self)

        self.rb_read = QRadioButton("Apenas Leitura — Protege contra modificações")
        self.rb_rw = QRadioButton("Leitura e Escrita — Padrão para documentos e fotos")
        self.rb_exec = QRadioButton("Padrão do Sistema — Permite abrir pastas e programas")
        self.rb_full = QRadioButton("Acesso Total — Leitura, escrita e execução liberadas")

        self.rb_rw.setChecked(True)

        self.group.addButton(self.rb_read, 444)
        self.group.addButton(self.rb_rw, 644)
        self.group.addButton(self.rb_exec, 755)
        self.group.addButton(self.rb_full, 777)

        layout.addWidget(self.rb_read)
        layout.addWidget(self.rb_rw)
        layout.addWidget(self.rb_exec)

        if self.root_active:
            layout.addWidget(self.rb_full)
        else:
            lock_row = QHBoxLayout()
            lock_icon = QLabel()
            lock_icon.setPixmap(load_svg_icon("block.svg").pixmap(18, 18))
            lock_info = QLabel("O nível Acesso Total só fica disponível quando o botão Acesso Total está ativo.")
            lock_info.setWordWrap(True)
            lock_info.setStyleSheet("color: #64748B;")
            lock_row.addWidget(lock_icon)
            lock_row.addWidget(lock_info, 1)
            layout.addLayout(lock_row)

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Aplicar Permissão")
        apply_btn.setObjectName("PrimaryBtn")
        apply_btn.setMinimumHeight(40)
        apply_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

    def get_selected_octal(self) -> str:
        btn_id = self.group.checkedId()
        if btn_id == 777 and not self.root_active:
            return "755"
        return str(btn_id) if btn_id > 0 else "755"


class SettingsDialog(QDialog):
    """
    Janela de Configurações ampliada (820x560) com pesquisa por palavra-chave,
    tópicos laterais e persistência real em ~/.config/android-connect/settings.json.
    """
    def __init__(self, current_settings: Dict[str, Any], on_apply_settings_cb: Callable[[Dict[str, Any]], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.resize(820, 560)
        self.setMinimumSize(720, 480)
        self.current = dict(current_settings)
        self.on_apply = on_apply_settings_cb

        from styles import detect_system_font
        sys_fam, sys_sz = detect_system_font()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        search_row = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(load_svg_icon("search.svg").pixmap(22, 22))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Pesquisar opção ou tópico (ex: fonte, tamanho, porta, backup, maximizar)...")
        self.search_edit.textChanged.connect(self._filter_settings)
        search_row.addWidget(search_icon)
        search_row.addWidget(self.search_edit, 1)
        layout.addLayout(search_row)

        content_split = QHBoxLayout()
        content_split.setSpacing(16)

        self.topics_list = QTreeWidget(self)
        self.topics_list.setHeaderHidden(True)
        self.topics_list.setFixedWidth(230)

        self.item_appearance = QTreeWidgetItem(["Interface e Fonte"])
        self.item_appearance.setIcon(0, load_svg_icon("visibility.svg"))
        self.item_network = QTreeWidgetItem(["Conexão e Rede"])
        self.item_network.setIcon(0, load_svg_icon("sync.svg"))
        self.item_security = QTreeWidgetItem(["Segurança e Arquivos"])
        self.item_security.setIcon(0, load_svg_icon("key.svg"))

        self.topics_list.addTopLevelItem(self.item_appearance)
        self.topics_list.addTopLevelItem(self.item_network)
        self.topics_list.addTopLevelItem(self.item_security)

        content_split.addWidget(self.topics_list)

        self.pages_stack = QStackedWidget(self)

        # Página 1: Interface e Fonte
        page1 = QWidget()
        p1_lay = QVBoxLayout(page1)
        p1_lay.setContentsMargins(14, 6, 14, 14)
        p1_lay.setSpacing(14)

        p1_title = QLabel("Interface, Layout e Fonte")
        p1_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #38BDF8;")
        p1_lay.addWidget(p1_title)

        self.font_sync_chk = QCheckBox(f"Sincronizar automaticamente com a fonte do notebook ({sys_fam})")
        self.font_sync_chk.setChecked(bool(self.current.get("auto_sync_font", True)))
        p1_lay.addWidget(self.font_sync_chk)

        font_custom_row = QHBoxLayout()
        self.custom_font_edit = QLineEdit(str(self.current.get("font_family", sys_fam)))
        self.font_size_spin = QLineEdit(str(self.current.get("font_size", sys_sz)))
        self.font_size_spin.setFixedWidth(65)
        font_custom_row.addWidget(QLabel("Fonte:"))
        font_custom_row.addWidget(self.custom_font_edit, 1)
        font_custom_row.addWidget(QLabel("Tamanho (pt):"))
        font_custom_row.addWidget(self.font_size_spin)
        p1_lay.addLayout(font_custom_row)

        self.theme_chk = QCheckBox("Mudar para o tema Verde Escuro quando o Acesso Total estiver ativo")
        self.theme_chk.setChecked(bool(self.current.get("theme_dynamic", True)))
        p1_lay.addWidget(self.theme_chk)

        self.max_chk = QCheckBox("Abrir janela principal sempre maximizada")
        self.max_chk.setChecked(bool(self.current.get("start_maximized", True)))
        p1_lay.addWidget(self.max_chk)
        p1_lay.addStretch(1)

        # Página 2: Conexão e Rede
        page2 = QWidget()
        p2_lay = QVBoxLayout(page2)
        p2_lay.setContentsMargins(14, 6, 14, 14)
        p2_lay.setSpacing(14)

        p2_title = QLabel("Conexão Sem Fio")
        p2_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #10B981;")
        p2_lay.addWidget(p2_title)

        self.auto_connect_chk = QCheckBox("Lembrar último endereço IP utilizado")
        self.auto_connect_chk.setChecked(bool(self.current.get("auto_connect", True)))
        p2_lay.addWidget(self.auto_connect_chk)

        p2_lay.addWidget(QLabel("Porta padrão de conexão:"))
        self.default_port_edit = QLineEdit(str(self.current.get("default_port", "5555")))
        p2_lay.addWidget(self.default_port_edit)

        self.mdns_chk = QCheckBox("Listar automaticamente celulares já ativos ao abrir")
        self.mdns_chk.setChecked(bool(self.current.get("mdns_discovery", True)))
        p2_lay.addWidget(self.mdns_chk)
        p2_lay.addStretch(1)

        # Página 3: Segurança e Arquivos
        page3 = QWidget()
        p3_lay = QVBoxLayout(page3)
        p3_lay.setContentsMargins(14, 6, 14, 14)
        p3_lay.setSpacing(14)

        p3_title = QLabel("Segurança e Proteção de Arquivos")
        p3_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #F59E0B;")
        p3_lay.addWidget(p3_title)

        self.backup_before_edit_chk = QCheckBox("Guardar cópia de segurança antes de salvar edições no celular")
        self.backup_before_edit_chk.setChecked(bool(self.current.get("backup_enabled", True)))
        p3_lay.addWidget(self.backup_before_edit_chk)

        self.confirm_del_chk = QCheckBox("Pedir confirmação antes de apagar arquivos ou pastas")
        self.confirm_del_chk.setChecked(bool(self.current.get("confirm_delete", True)))
        p3_lay.addWidget(self.confirm_del_chk)

        self.protect_sys_chk = QCheckBox("Bloquear exclusão de pastas vitais do sistema (Proteção permanente)")
        self.protect_sys_chk.setChecked(True)
        self.protect_sys_chk.setEnabled(False)
        p3_lay.addWidget(self.protect_sys_chk)
        p3_lay.addStretch(1)

        self.pages_stack.addWidget(page1)
        self.pages_stack.addWidget(page2)
        self.pages_stack.addWidget(page3)

        content_split.addWidget(self.pages_stack, 1)
        layout.addLayout(content_split, 1)

        self.topics_list.itemClicked.connect(lambda item, _col=0: self._on_topic_clicked(item))
        self.topics_list.currentItemChanged.connect(lambda curr, _prev=None: self._on_topic_clicked(curr))
        self.topics_list.setCurrentItem(self.item_appearance)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setMinimumHeight(42)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Aplicar e Salvar")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setMinimumHeight(42)
        save_btn.clicked.connect(self._apply_and_close)

        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _on_topic_clicked(self, item):
        if not item:
            return
        idx = self.topics_list.indexOfTopLevelItem(item)
        if idx >= 0:
            self.pages_stack.setCurrentIndex(idx)

    def _filter_settings(self, text: str):
        t = text.strip().lower()
        if not t:
            self.item_appearance.setHidden(False)
            self.item_network.setHidden(False)
            self.item_security.setHidden(False)
            return

        match_app = any(t in w for w in ["fonte", "aparencia", "aparência", "interface", "letra", "tamanho", "tema", "verde", "maximizar", "layout"])
        match_net = any(t in w for w in ["conexao", "conexão", "rede", "porta", "ip", "pareamento", "wi-fi", "wifi", "celular"])
        match_sec = any(t in w for w in ["seguranca", "segurança", "backup", "arquivo", "apagar", "exclusao", "exclusão", "acesso", "proteger"])

        self.item_appearance.setHidden(not match_app)
        self.item_network.setHidden(not match_net)
        self.item_security.setHidden(not match_sec)

        if match_app:
            self.pages_stack.setCurrentIndex(0)
            self.topics_list.setCurrentItem(self.item_appearance)
        elif match_net:
            self.pages_stack.setCurrentIndex(1)
            self.topics_list.setCurrentItem(self.item_network)
        elif match_sec:
            self.pages_stack.setCurrentIndex(2)
            self.topics_list.setCurrentItem(self.item_security)

    def _apply_and_close(self):
        from styles import detect_system_font
        sys_fam, sys_sz = detect_system_font()

        if self.font_sync_chk.isChecked():
            font_family = sys_fam
        else:
            font_family = self.custom_font_edit.text().strip() or sys_fam

        raw_sz = self.font_size_spin.text().strip()
        font_size = int(raw_sz) if raw_sz.isdigit() and 9 <= int(raw_sz) <= 24 else sys_sz

        raw_port = self.default_port_edit.text().strip()
        default_port = raw_port if raw_port.isdigit() and 1 <= int(raw_port) <= 65535 else "5555"

        self.on_apply({
            "font_family": font_family,
            "font_size": font_size,
            "auto_sync_font": self.font_sync_chk.isChecked(),
            "theme_dynamic": self.theme_chk.isChecked(),
            "start_maximized": self.max_chk.isChecked(),
            "auto_connect": self.auto_connect_chk.isChecked(),
            "default_port": default_port,
            "mdns_discovery": self.mdns_chk.isChecked(),
            "backup_enabled": self.backup_before_edit_chk.isChecked(),
            "confirm_delete": self.confirm_del_chk.isChecked(),
        })
        self.accept()


class LoadingProgressDialog(QDialog):
    """
    Pop-up de Carregamento Assíncrono com Progresso Real por Quantidade de Itens:
    - Permite atualizar dinamicamente o total de arquivos após escanear subpastas
    - Mostra porcentagem exata + contador (ex: "64% (32/50 itens)") na barra de progresso
    """
    def __init__(
        self,
        title: str,
        initial_text: str,
        task_fn: Callable[[Callable[..., None]], Any],
        total_steps: int = 0,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(520, 235)
        self.task_fn = task_fn
        self.total_steps = int(total_steps)
        self._pulse_val = 15
        self._pulse_dir = 5
        self._can_close = False

        self.msg_queue: "queue.Queue[Tuple[int, int, str]]" = queue.Queue()
        self.result: Any = None
        self.error: Optional[BaseException] = None
        self._worker_done = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        card = QFrame(self)
        card.setObjectName("LoginCard")
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(24, 22, 24, 22)
        c_lay.setSpacing(12)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #38BDF8;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_lay.addWidget(self.title_lbl)

        self.detail_lbl = QLabel(initial_text)
        self.detail_lbl.setWordWrap(True)
        self.detail_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        self.detail_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_lay.addWidget(self.detail_lbl)

        self.counter_lbl = QLabel("")
        self.counter_lbl.setStyleSheet("color: #10B981; font-weight: bold; font-size: 12px;")
        self.counter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_lay.addWidget(self.counter_lbl)

        self.progress = QProgressBar(self)
        self.progress.setMinimumHeight(22)
        self.progress.setRange(0, 100)
        self.progress.setValue(0 if self.total_steps > 0 else 15)
        self.progress.setTextVisible(True)
        c_lay.addWidget(self.progress)

        layout.addWidget(card)

        self._worker_thread = threading.Thread(target=self._run_worker, daemon=True)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(45)
        self.poll_timer.timeout.connect(self._on_timer_tick)

    def report_progress(self, step: int, text: str = "", new_total: Optional[int] = None):
        tot = int(new_total) if new_total is not None else self.total_steps
        self.msg_queue.put((int(step), tot, str(text)))

    def _run_worker(self):
        try:
            self.result = self.task_fn(self.report_progress)
        except BaseException as exc:
            self.error = exc
        finally:
            self._worker_done = True

    def start_and_exec(self):
        self.poll_timer.start()
        self._worker_thread.start()
        exec_dialog(self)
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10.0)
        self._drain_queue()

    def _drain_queue(self):
        while not self.msg_queue.empty():
            try:
                step, tot, detail_text = self.msg_queue.get_nowait()
                if tot > 0:
                    self.total_steps = tot
                if detail_text:
                    self.detail_lbl.setText(detail_text)
                if self.total_steps > 0:
                    clamped_step = max(0, min(step, self.total_steps))
                    pct = int((clamped_step / max(1, self.total_steps)) * 100)
                    self.progress.setTextVisible(True)
                    self.progress.setValue(pct)
                    self.counter_lbl.setText(f"Progresso: {clamped_step} de {self.total_steps} item(ns) ({pct}%)")
            except Exception:
                break

    def _on_timer_tick(self):
        self._drain_queue()
        if self.total_steps <= 0 and not self._worker_done:
            self._pulse_val += self._pulse_dir
            if self._pulse_val >= 95:
                self._pulse_val = 95
                self._pulse_dir = -5
            elif self._pulse_val <= 10:
                self._pulse_val = 10
                self._pulse_dir = 5
            self.progress.setValue(self._pulse_val)

        if self._worker_done:
            self.poll_timer.stop()
            self._can_close = True
            self.progress.setValue(100)
            self.accept()

    def reject(self):
        if self._can_close:
            super().reject()


def run_with_loading(
    parent,
    title: str,
    initial_text: str,
    task_fn: Callable[[Callable[..., None]], Any],
    total_steps: int = 0
) -> Any:
    """
    Abre o pop-up modal LoadingProgressDialog na thread principal enquanto
    executa `task_fn(report_progress)` em segundo plano.
    """
    dlg = LoadingProgressDialog(
        title=title,
        initial_text=initial_text,
        task_fn=task_fn,
        total_steps=total_steps,
        parent=parent
    )
    dlg.start_and_exec()
    if dlg.error is not None:
        raise dlg.error
    return dlg.result

