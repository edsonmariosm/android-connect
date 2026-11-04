"""
Estilos dinamicos QSS (Layout Ampliado), sincronizacao de fonte nativa e persistencia de configuracoes.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple


def detect_system_font() -> Tuple[str, int]:
    """Detecta a fonte e tamanho configurados no ambiente grafico Linux."""
    if shutil.which("gsettings"):
        try:
            res = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "font-name"],
                capture_output=True, text=True, timeout=2
            )
            raw = res.stdout.strip().strip("'").strip('"')
            if raw and raw != "nothing":
                parts = raw.rsplit(" ", 1)
                family = parts[0].replace("'", "").replace('"', "")
                size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 12
                return family, max(11, min(size + 1, 20))
        except Exception:
            pass

    for cmd in ["kreadconfig6", "kreadconfig5"]:
        if shutil.which(cmd):
            try:
                res = subprocess.run(
                    [cmd, "--group", "General", "--key", "font"],
                    capture_output=True, text=True, timeout=2
                )
                raw = res.stdout.strip()
                if raw:
                    parts = raw.split(",")
                    family = parts[0].replace("'", "").replace('"', "")
                    size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 12
                    return family, max(11, min(size + 1, 20))
            except Exception:
                pass

    if shutil.which("fc-match"):
        try:
            res = subprocess.run(
                ["fc-match", "-f", "%{family}\n"],
                capture_output=True, text=True, timeout=2
            )
            raw = res.stdout.strip().split(",")[0].replace("'", "").replace('"', "")
            if raw:
                return raw, 12
        except Exception:
            pass

    return "Ubuntu, Inter, Segoe UI, sans-serif", 12


SYS_FONT_FAMILY, SYS_FONT_SIZE = detect_system_font()


class SettingsStore:
    """Armazena e carrega preferências do usuário em ~/.config/android-connect/settings.json (0600)."""
    DEFAULT_SETTINGS: Dict[str, Any] = {
        "font_family": SYS_FONT_FAMILY,
        "font_size": SYS_FONT_SIZE,
        "auto_sync_font": True,
        "theme_dynamic": True,
        "auto_connect": True,
        "default_port": "5555",
        "last_ip": "192.168.1.100",
        "mdns_discovery": True,
        "backup_enabled": True,
        "confirm_delete": True,
        "start_maximized": True,
    }

    def __init__(self):
        cfg_root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        self.cfg_dir = cfg_root / "android-connect"
        self.cfg_file = self.cfg_dir / "settings.json"
        self.data: Dict[str, Any] = dict(self.DEFAULT_SETTINGS)
        self.load()

    def load(self) -> Dict[str, Any]:
        try:
            if self.cfg_file.is_file():
                raw = json.loads(self.cfg_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k, default_v in self.DEFAULT_SETTINGS.items():
                        val = raw.get(k, default_v)
                        if isinstance(default_v, bool):
                            self.data[k] = bool(val)
                        elif isinstance(default_v, int):
                            self.data[k] = int(val) if str(val).isdigit() else default_v
                        else:
                            self.data[k] = str(val)
        except Exception:
            self.data = dict(self.DEFAULT_SETTINGS)
        return self.data

    def save(self, updates: Dict[str, Any]) -> bool:
        try:
            self.cfg_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.cfg_dir, 0o700)
            for k, v in updates.items():
                if k in self.DEFAULT_SETTINGS:
                    self.data[k] = v
            self.cfg_file.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.chmod(self.cfg_file, 0o600)
            return True
        except Exception:
            return False


def get_base_css(font_family: str = None, font_size: int = None) -> str:
    fam = (font_family or SYS_FONT_FAMILY).replace("'", "").replace('"', "").replace(";", "")
    try:
        sz = max(10, min(int(font_size or SYS_FONT_SIZE), 24))
    except (ValueError, TypeError):
        sz = SYS_FONT_SIZE

    return f"""
QMainWindow, QWidget {{
    font-family: '{fam}', 'Ubuntu', 'Inter', sans-serif;
    font-size: {sz}pt;
}}

QLabel#TitleLabel {{
    font-size: {sz + 9}pt;
    font-weight: bold;
    color: #F8FAFC;
}}

QLabel#SubtitleLabel {{
    font-size: {sz}pt;
    color: #94A3B8;
}}

QLineEdit {{
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 9px 14px;
    min-height: 22px;
    selection-background-color: #0EA5E9;
}}

QLineEdit#PairDigitBox {{
    background-color: #090D16;
    border: 2px solid #334155;
    border-radius: 12px;
    font-size: 26px;
    font-weight: bold;
    color: #10B981;
    padding: 0px;
}}

QLineEdit#PairDigitBox:focus {{
    background-color: #111C2D;
    border: 2px solid #10B981;
}}

QPushButton {{
    border-radius: 10px;
    padding: 9px 16px;
    min-height: 22px;
    font-weight: 600;
}}

QPushButton#PrimaryBtn {{
    background-color: #10B981;
    border: none;
    color: #06281E;
    font-weight: bold;
}}
QPushButton#PrimaryBtn:hover {{
    background-color: #34D399;
}}

QPushButton#PairBtn {{
    background-color: #0EA5E9;
    border: none;
    color: #082F49;
    font-weight: bold;
}}
QPushButton#PairBtn:hover {{
    background-color: #38BDF8;
}}

QPushButton#IconButton {{
    padding: 7px;
    min-width: 36px;
    max-width: 40px;
    min-height: 36px;
}}

QProgressBar {{
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    font-size: 11px;
    font-weight: bold;
    height: 14px;
}}
QProgressBar::chunk {{
    background-color: #10B981;
    border-radius: 5px;
}}

QTreeWidget {{
    border: 1px solid #1E293B;
    border-radius: 8px;
    outline: none;
}}
QTreeWidget::item {{
    padding: 9px 6px;
    min-height: 28px;
    border-bottom: 1px solid #151F32;
}}
QTreeWidget::item:selected {{
    background-color: #1E3A8A;
    color: #FFFFFF;
}}

QHeaderView::section {{
    padding: 10px 12px;
    border: none;
    border-right: 1px solid #334155;
    font-weight: bold;
}}

QMenu {{
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 8px;
}}
QMenu::item {{
    padding: 9px 26px 9px 14px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: #0EA5E9;
    color: #082F49;
    font-weight: bold;
}}
"""


def generate_theme(is_root: bool = False, font_family: str = None, font_size: int = None) -> str:
    base = get_base_css(font_family, font_size)
    if is_root:
        return """
QMainWindow, QWidget {
    background-color: #04160E;
    color: #E2E8F0;
}
QFrame#LoginCard {
    background-color: #072619;
    border: 1px solid #10B981;
    border-radius: 18px;
}
QLineEdit {
    background-color: #020C08;
    color: #F8FAFC;
    border: 1px solid #10B981;
}
QPushButton {
    background-color: #072619;
    border: 1px solid #10B981;
    color: #E2E8F0;
}
QPushButton:hover {
    background-color: #0F3D2A;
}
QPushButton#RootToggleTrue {
    background-color: #064E3B;
    border: 1px solid #10B981;
    color: #A7F3D0;
    border-radius: 16px;
    padding: 8px 16px;
    font-weight: bold;
}
QFrame#PaneHeaderLocal {
    background-color: #0F2E22;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom: 2px solid #10B981;
}
QFrame#PaneHeaderRemote {
    background-color: #064E3B;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom: 2px solid #34D399;
}
QTreeWidget {
    background-color: #020C08;
    alternate-background-color: #04160E;
}
QHeaderView::section {
    background-color: #072619;
    color: #A7F3D0;
}
QMenu {
    background-color: #072619;
    border: 1px solid #10B981;
}
""" + base
    return """
QMainWindow, QWidget {
    background-color: #0F172A;
    color: #E2E8F0;
}
QFrame#LoginCard {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 18px;
}
QLineEdit {
    background-color: #0B1120;
    color: #F8FAFC;
}
QPushButton {
    background-color: #1E293B;
    border: 1px solid #334155;
    color: #E2E8F0;
}
QPushButton:hover {
    background-color: #334155;
}
QPushButton#RootToggleFalse {
    background-color: #1E293B;
    border: 1px solid #475569;
    color: #94A3B8;
    border-radius: 16px;
    padding: 8px 16px;
}
QFrame#PaneHeaderLocal {
    background-color: #172554;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom: 2px solid #38BDF8;
}
QFrame#PaneHeaderRemote {
    background-color: #064E3B;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom: 2px solid #10B981;
}
QTreeWidget {
    background-color: #0B1120;
    alternate-background-color: #111827;
}
QHeaderView::section {
    background-color: #1E293B;
    color: #94A3B8;
}
QMenu {
    background-color: #1E293B;
}
""" + base


THEME_DEFAULT = generate_theme(is_root=False)
THEME_ROOT = generate_theme(is_root=True)
