"""Colours and styles. Large text and strong contrast, so it's easy to read for everyone."""

INK = "#1F2328"
MUTED = "#5A6270"
PAPER = "#F7F5F0"
CARD = "#FFFFFF"
LINE = "#E3DED3"
ACCENT = "#0F6E64"          # deep teal
ACCENT_DARK = "#0A5049"
ACCENT_SOFT = "#E3F1EE"
WARM = "#E8A33D"
GOOD = "#1E7B34"
GOOD_SOFT = "#E6F4E8"
WARN = "#9A5B00"
WARN_SOFT = "#FCF1DC"
BAD = "#B42318"
BAD_SOFT = "#FDECEA"

STYLE = f"""
QWidget {{ color: {INK}; font-size: 15px; }}
QMainWindow, QDialog, #Page, QScrollArea, #ScrollBody {{ background: {PAPER}; }}
QScrollArea {{ border: none; }}

#TopBar {{ background: {CARD}; border-bottom: 1px solid {LINE}; }}
#AppTitle {{ font-size: 19px; font-weight: 700; }}
#PageTitle {{ font-size: 26px; font-weight: 700; }}
#PageIntro {{ font-size: 16px; color: {MUTED}; }}
#SectionTitle {{ font-size: 18px; font-weight: 700; margin-top: 6px; }}
#Muted {{ color: {MUTED}; }}
#Small {{ color: {MUTED}; font-size: 13px; }}

#Card, #Tile {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
#Tile:hover {{ border: 2px solid {ACCENT}; }}
#TileTitle {{ font-size: 17px; font-weight: 700; }}
#CardTitle {{ font-size: 17px; font-weight: 700; }}

QPushButton {{
  background: {CARD}; border: 1px solid #C9C2B4; border-radius: 10px;
  padding: 9px 16px; font-size: 15px; font-weight: 600; min-height: 22px;
}}
QPushButton:hover {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
QPushButton:pressed {{ background: #CFE6E1; }}
QPushButton:disabled {{ color: #9AA0A6; border-color: {LINE}; background: #F1EFEA; }}
QPushButton#Primary {{ background: {ACCENT}; color: white; border: none; padding: 11px 22px; font-size: 16px; }}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#Primary:disabled {{ background: #9CC3BD; color: #F2F6F5; }}
QPushButton#Link {{ background: transparent; border: none; color: {ACCENT}; padding: 4px 2px; text-decoration: underline; }}
QPushButton#Link:hover {{ color: {ACCENT_DARK}; }}
QPushButton#Danger {{ color: {BAD}; }}
QPushButton#Danger:hover {{ background: {BAD_SOFT}; border-color: {BAD}; }}
QPushButton#Chip {{ border-radius: 16px; padding: 6px 14px; font-weight: 600; font-size: 14px; }}
QPushButton#Back {{ border: none; background: transparent; font-size: 15px; padding: 6px 10px; }}
QPushButton#Back:hover {{ background: {ACCENT_SOFT}; }}

QLineEdit, QComboBox {{
  background: {CARD}; border: 1px solid #C9C2B4; border-radius: 10px; padding: 9px 12px; font-size: 16px;
}}
QLineEdit:focus, QComboBox:focus {{ border: 2px solid {ACCENT}; }}
QComboBox QAbstractItemView {{ font-size: 15px; selection-background-color: {ACCENT_SOFT}; selection-color: {INK}; }}

QProgressBar {{ background: #ECE8DF; border: none; border-radius: 6px; height: 12px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}

QCheckBox {{ spacing: 10px; font-size: 15px; }}
QCheckBox::indicator {{ width: 22px; height: 22px; }}

QListWidget {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; font-size: 15px; padding: 4px; }}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {INK}; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 10px 18px; font-size: 15px; font-weight: 600; color: {MUTED};
               border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {INK}; border-bottom: 3px solid {ACCENT}; }}

QToolTip {{ background: {INK}; color: white; border: none; padding: 6px 8px; font-size: 13px; }}
"""

BANNER = {
    "good": (GOOD_SOFT, GOOD, "check_circle"),
    "warn": (WARN_SOFT, WARN, "alert"),
    "bad": (BAD_SOFT, BAD, "x_circle"),
    "info": (ACCENT_SOFT, ACCENT_DARK, "info"),
}
