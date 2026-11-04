"""
Tela de conexao e pareamento com layout ampliado.
"""
from qt_compat import (
    Qt, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QDialog, QMessageBox, QComboBox, load_svg_icon, exec_dialog
)


class SixDigitPairDialog(QDialog):
    def __init__(self, adb_ctrl, initial_ip: str = "", parent=None):
        super().__init__(parent)
        self.adb = adb_ctrl
        self.setWindowTitle("Vincular Celular com Código")
        self.setModal(True)
        self.setFixedSize(580, 440)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 28, 28, 28)

        card = QFrame(self)
        card.setObjectName("LoginCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(16)

        title = QLabel("Digite o Código do Celular")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)

        subtitle = QLabel("No celular, abra Opções do Desenvolvedor > Depuração por Wi-Fi > Parear com código.")
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        addr_row = QHBoxLayout()
        addr_row.setSpacing(12)
        self.ip_input = QLineEdit(initial_ip or "192.168.1.")
        self.ip_input.setPlaceholderText("IP (ex: 192.168.1.50)")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("Porta (ex: 37123)")
        self.port_input.setFixedWidth(180)

        addr_row.addWidget(QLabel("IP:"))
        addr_row.addWidget(self.ip_input, 1)
        addr_row.addWidget(QLabel("Porta:"))
        addr_row.addWidget(self.port_input)
        card_layout.addLayout(addr_row)

        card_layout.addWidget(QLabel("Código de 6 dígitos:"))
        digits_row = QHBoxLayout()
        digits_row.setSpacing(12)
        digits_row.addStretch(1)
        self.digit_boxes = []
        for idx in range(6):
            box = QLineEdit()
            box.setObjectName("PairDigitBox")
            box.setFixedSize(64, 68)
            box.setMaxLength(1)
            box.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
            box.textChanged.connect(lambda text, i=idx: self._on_digit_typed(i, text))
            self.digit_boxes.append(box)
            digits_row.addWidget(box)
        digits_row.addStretch(1)
        card_layout.addLayout(digits_row)

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        card_layout.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setMinimumHeight(44)
        cancel_btn.clicked.connect(self.reject)
        self.pair_btn = QPushButton("Confirmar Vinculação")
        self.pair_btn.setObjectName("PairBtn")
        self.pair_btn.setMinimumHeight(44)
        self.pair_btn.clicked.connect(self._execute_pair)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.pair_btn)
        card_layout.addLayout(btn_row)

        root_layout.addWidget(card)

    def _on_digit_typed(self, index: int, text: str):
        if text and not text.isdigit():
            self.digit_boxes[index].setText("")
            return
        if len(text) == 1 and index < 5:
            self.digit_boxes[index + 1].setFocus()
            self.digit_boxes[index + 1].selectAll()

    def _execute_pair(self):
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        code = "".join(b.text().strip() for b in self.digit_boxes)
        if not ip or not port or len(code) != 6:
            self.status_lbl.setText("Preencha o IP, a porta e todos os 6 dígitos.")
            return
        self.status_lbl.setText("Vinculando celular...")
        self.repaint()
        ok, msg = self.adb.pair_device(ip, port, code)
        if ok:
            QMessageBox.information(self, "Celular Vinculado", msg)
            self.accept()
        else:
            self.status_lbl.setText(f"Erro: {msg}")


class ConnectionScreen(QWidget):
    def __init__(self, adb_ctrl, settings_store, on_connected_callback, parent=None):
        super().__init__(parent)
        self.adb = adb_ctrl
        self.settings = settings_store
        self.on_connected_callback = on_connected_callback
        self._build_ui()
        if self.settings.data.get("mdns_discovery", True):
            self.refresh_devices()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 48, 48, 48)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)

        card = QFrame(self)
        card.setObjectName("LoginCard")
        card.setFixedWidth(560)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(40, 38, 40, 38)
        c_layout.setSpacing(16)

        title = QLabel("Conectar ao Celular")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)

        subtitle = QLabel("Informe o endereço IP e a porta da conexão sem fio do seu celular.")
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)

        c_layout.addWidget(title)
        c_layout.addWidget(subtitle)

        last_ip = str(self.settings.data.get("last_ip", "192.168.1.100"))
        def_port = str(self.settings.data.get("default_port", "5555"))

        self.ip_edit = QLineEdit(last_ip)
        self.port_edit = QLineEdit(def_port)
        c_layout.addWidget(QLabel("Endereço IP:"))
        c_layout.addWidget(self.ip_edit)
        c_layout.addWidget(QLabel("Porta:"))
        c_layout.addWidget(self.port_edit)

        connect_btn = QPushButton("Conectar Celular")
        connect_btn.setObjectName("PrimaryBtn")
        connect_btn.setMinimumHeight(48)
        connect_btn.clicked.connect(self._handle_connect)
        c_layout.addWidget(connect_btn)

        pair_btn = QPushButton("Vincular Novo Celular (Código de 6 Dígitos)")
        pair_btn.setObjectName("PairBtn")
        pair_btn.setMinimumHeight(44)
        pair_btn.clicked.connect(self._open_pair_dialog)
        c_layout.addWidget(pair_btn)

        dev_row = QHBoxLayout()
        self.dev_combo = QComboBox()
        self.dev_combo.setMinimumHeight(38)
        ref_btn = QPushButton("Atualizar")
        ref_btn.setMinimumHeight(38)
        ref_btn.clicked.connect(self.refresh_devices)
        use_btn = QPushButton("Usar")
        use_btn.setMinimumHeight(38)
        use_btn.clicked.connect(self._use_device)
        dev_row.addWidget(self.dev_combo, 1)
        dev_row.addWidget(ref_btn)
        dev_row.addWidget(use_btn)
        c_layout.addWidget(QLabel("Celulares encontrados:"))
        c_layout.addLayout(dev_row)

        offline_btn = QPushButton("Abrir Gerenciador de Arquivos")
        offline_btn.setMinimumHeight(42)
        offline_btn.clicked.connect(lambda: self.on_connected_callback(None))
        c_layout.addWidget(offline_btn)

        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter)
        c_layout.addWidget(self.feedback)

        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def refresh_devices(self):
        self.dev_combo.clear()
        devs = self.adb.list_devices()
        if not devs:
            self.dev_combo.addItem("Nenhum celular ativo", "")
        else:
            for s, d in devs:
                self.dev_combo.addItem(f"{s} ({d})", s)

    def _open_pair_dialog(self):
        dlg = SixDigitPairDialog(self.adb, initial_ip=self.ip_edit.text().strip(), parent=self)
        if exec_dialog(dlg):
            self.ip_edit.setText(dlg.ip_input.text().strip())
            self.refresh_devices()

    def _handle_connect(self):
        ip = self.ip_edit.text().strip()
        port = self.port_edit.text().strip() or str(self.settings.data.get("default_port", "5555"))
        if not ip:
            self.feedback.setText("Informe o endereço IP do celular.")
            return
        self.feedback.setText(f"Conectando a {ip}:{port}...")
        self.repaint()
        ok, msg = self.adb.connect_device(ip, port)
        if ok:
            if self.settings.data.get("auto_connect", True):
                self.settings.save({"last_ip": ip, "default_port": port})
            self.on_connected_callback(f"{ip}:{port}")
        else:
            self.feedback.setText(f"Não foi possível conectar: {msg}")

    def _use_device(self):
        s = self.dev_combo.currentData()
        if s:
            self.adb.device_serial = s
            self.on_connected_callback(s)
