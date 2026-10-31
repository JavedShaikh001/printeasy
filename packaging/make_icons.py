"""Render the app icon to PNG / ICO (Windows) / ICNS (macOS).   python packaging/make_icons.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from printeasy.ui.icons import APP_ICON_SVG

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(out, exist_ok=True)
app = QGuiApplication(sys.argv)
r = QSvgRenderer(QByteArray(APP_ICON_SVG.encode()))
img = QImage(1024, 1024, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img); p.setRenderHint(QPainter.Antialiasing); r.render(p, QRectF(0, 0, 1024, 1024)); p.end()
png = os.path.join(out, "printeasy.png")
img.save(png)
from PIL import Image
im = Image.open(png)
im.resize((256, 256), Image.LANCZOS).save(os.path.join(out, "printeasy-256.png"))
im.save(os.path.join(out, "printeasy.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
im.save(os.path.join(out, "printeasy.icns"))
print("icons written to", out)
