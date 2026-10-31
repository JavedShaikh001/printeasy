"""Simple line icons drawn as SVG, so they look sharp at any size on every OS."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" '
         'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">')

PATHS = {
    "printer": '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/>'
               '<path d="M7 14h10v7H7z"/><circle cx="17.5" cy="12" r=".6" fill="{c}"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/>',
    "usb": '<path d="M12 3v14"/><path d="m9 6 3-3 3 3"/><path d="M12 13 7 10V8"/><circle cx="7" cy="7" r="1.2"/>'
           '<path d="m12 15 5-3V9.5"/><rect x="15.8" y="7.3" width="2.4" height="2.4"/><circle cx="12" cy="19" r="2"/>',
    "wifi": '<path d="M2 8.8a15 15 0 0 1 20 0"/><path d="M5 12.4a10 10 0 0 1 14 0"/>'
            '<path d="M8.5 15.9a5 5 0 0 1 7 0"/><circle cx="12" cy="19.3" r=".9" fill="{c}"/>',
    "apps": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17.5 14v7M14 17.5h7"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r=".8" fill="{c}"/>'
            '<circle cx="4" cy="12" r=".8" fill="{c}"/><circle cx="4" cy="18" r=".8" fill="{c}"/>',
    "lifebuoy": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>'
                '<path d="m5.6 5.6 3.6 3.6M14.8 14.8l3.6 3.6M18.4 5.6l-3.6 3.6M9.2 14.8l-3.6 3.6"/>',
    "check": '<path d="M4 12.5 9.5 18 20 6.5"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12.3 2.8 2.8L16.3 9"/>',
    "alert": '<path d="M12 3 2 20h20z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.3" r=".6" fill="{c}"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r=".6" fill="{c}"/>',
    "x_circle": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "back": '<path d="M15 5 8 12l7 7"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8l-5.4 2.9 1.1-6.1-4.5-4.2 6.1-.8z"/>',
    "star_fill": '<path fill="{c}" d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8l-5.4 2.9 1.1-6.1-4.5-4.2 6.1-.8z"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "home": '<path d="M3 11 12 3l9 8"/><path d="M5 9.5V21h14V9.5"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "pin": '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.7-4.4L3 9"/><path d="M3 4v5h5"/><path d="M4 13a8 8 0 0 0 14.7 4.4L21 15"/><path d="M21 20v-5h-5"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "page": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
}


def svg(name: str, color: str = "#1f2328", width: float = 1.8) -> str:
    body = PATHS[name].replace("{c}", color)
    return _HEAD.format(c=color, w=width) + body + "</svg>"


def pixmap(name: str, size: int = 32, color: str = "#1f2328", width: float = 1.8, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color, width).encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = "#1f2328", size: int = 24) -> QIcon:
    return QIcon(pixmap(name, size, color))


APP_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect x="8" y="8" width="240" height="240" rx="56" fill="#0F6E64"/>
  <path d="M84 104V58h88v46" fill="#F7F3EA"/>
  <rect x="44" y="100" width="168" height="80" rx="18" fill="#F7F3EA"/>
  <rect x="80" y="150" width="96" height="62" rx="6" fill="#FFFFFF" stroke="#0F6E64" stroke-width="8"/>
  <path d="M100 178l14 14 32-32" fill="none" stroke="#E8A33D" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="182" cy="126" r="8" fill="#E8A33D"/>
</svg>"""


def app_icon() -> QIcon:
    renderer = QSvgRenderer(QByteArray(APP_ICON_SVG.encode()))
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, s, s))
        p.end()
        ic.addPixmap(pm)
    return ic
