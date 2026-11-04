#!/usr/bin/env python3
"""
Android Connect 2.1 — Ponto de Entrada Principal (Maximização Automática).
"""
import sys
from qt_compat import QApplication, QMainWindow, QStackedWidget, exec_app
from styles import SettingsStore, generate_theme
from adb_backend import AdbController
from ui_connect import ConnectionScreen
from ui_manager import DualPaneManagerScreen


class AndroidConnectMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Android Connect — Gerenciador Dual-Pane")
        self.resize(1520, 920)
        self.setMinimumSize(1024, 680)

        self.settings = SettingsStore()
        self.adb = AdbController()

        fam = self.settings.data.get("font_family")
        sz = self.settings.data.get("font_size", 12)
        self.setStyleSheet(generate_theme(is_root=False, font_family=fam, font_size=sz))

        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        self.connect_screen = ConnectionScreen(
            self.adb,
            self.settings,
            on_connected_callback=self._switch_to_manager,
            parent=self
        )
        self.manager_screen = DualPaneManagerScreen(
            self.adb,
            self.settings,
            on_back_to_connect=self._switch_to_connect,
            parent=self
        )

        self.stack.addWidget(self.connect_screen)
        self.stack.addWidget(self.manager_screen)
        self.stack.setCurrentWidget(self.connect_screen)

    def _switch_to_manager(self, _serial):
        self.manager_screen.refresh_all()
        self.stack.setCurrentWidget(self.manager_screen)

    def _switch_to_connect(self):
        self.connect_screen.refresh_devices()
        self.stack.setCurrentWidget(self.connect_screen)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Android Connect")
    win = AndroidConnectMainWindow()
    # Abre maximizado por padrao nativamente para aproveitar toda a tela do notebook
    win.showMaximized()
    sys.exit(exec_app(app))


if __name__ == "__main__":
    main()
