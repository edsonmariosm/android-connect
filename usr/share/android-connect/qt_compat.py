"""
Camada de compatibilidade transparente entre PyQt6 e PyQt5.
"""
import os

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher, QThread, pyqtSignal, QSize, QPoint
    from PyQt6.QtGui import QFont, QIcon, QColor, QAction, QKeySequence, QCursor, QPixmap
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGridLayout, QLabel, QLineEdit, QPushButton, QStackedWidget,
        QTreeWidget, QTreeWidgetItem, QSplitter, QFrame, QMessageBox,
        QInputDialog, QDialog, QFileDialog, QMenu, QCheckBox, QComboBox,
        QStatusBar, QHeaderView, QAbstractItemView, QProgressDialog,
        QProgressBar, QTextEdit, QScrollArea, QTabWidget, QRadioButton, QButtonGroup
    )
    IS_PYQT6 = True
except ImportError:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, QTimer, QFileSystemWatcher, QThread, pyqtSignal, QSize, QPoint
    from PyQt5.QtGui import QFont, QIcon, QColor, QKeySequence, QCursor, QPixmap
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGridLayout, QLabel, QLineEdit, QPushButton, QStackedWidget,
        QTreeWidget, QTreeWidgetItem, QSplitter, QFrame, QMessageBox,
        QInputDialog, QDialog, QFileDialog, QMenu, QCheckBox, QComboBox,
        QStatusBar, QHeaderView, QAbstractItemView, QProgressDialog, QAction,
        QProgressBar, QTextEdit, QScrollArea, QTabWidget, QRadioButton, QButtonGroup
    )
    IS_PYQT6 = False

_ICON_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def load_svg_icon(name: str) -> QIcon:
    if not name or "/" in name or "\\" in name or ".." in name:
        return QIcon()
    path = os.path.join(_ICON_BASE, name)
    if os.path.isfile(path):
        return QIcon(path)
    return QIcon()


def exec_dialog(dlg):
    return dlg.exec() if IS_PYQT6 else dlg.exec_()


def exec_app(app):
    return app.exec() if IS_PYQT6 else app.exec_()


def exec_menu(menu, pos):
    return menu.exec(pos) if IS_PYQT6 else menu.exec_(pos)
