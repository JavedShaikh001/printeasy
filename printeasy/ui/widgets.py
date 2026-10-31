"""Reusable building blocks for PrintEasy's screens."""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import icons, theme


# ---------------------------------------------------------------------------- background work
class _Signals(QObject):
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn: Callable, *args, with_progress: bool = False):
        super().__init__()
        self.fn, self.args, self.with_progress = fn, args, with_progress
        self.signals = _Signals()

    def run(self):
        try:
            if self.with_progress:
                res = self.fn(*self.args, progress=lambda p, m: self.signals.progress.emit(p, m))
            else:
                res = self.fn(*self.args)
            self.signals.done.emit(res)
        except Exception as exc:   # show something human, keep details for support
            traceback.print_exc()
            self.signals.failed.emit(f"Something unexpected happened: {exc}")


_ACTIVE: set = set()   # keep signal objects alive until the job finishes


def run_in_background(fn: Callable, *args, on_done: Callable[[Any], None] | None = None,
                      on_fail: Callable[[str], None] | None = None,
                      on_progress: Callable[[int, str], None] | None = None) -> None:
    """Run slow work (network scans, printer commands) without freezing the window."""
    job = _Job(fn, *args, with_progress=on_progress is not None)
    sig = job.signals
    _ACTIVE.add(sig)

    def finish(cb, value):
        _ACTIVE.discard(sig)
        if cb:
            cb(value)

    sig.done.connect(lambda v: finish(on_done, v))
    sig.failed.connect(lambda e: finish(on_fail, e))
    if on_progress:
        sig.progress.connect(on_progress)
    QThreadPool.globalInstance().start(job)


# ---------------------------------------------------------------------------- small widgets
def label(text: str = "", obj: str = "", wrap: bool = True, selectable: bool = False) -> QLabel:
    lbl = QLabel(text)
    if obj:
        lbl.setObjectName(obj)
    lbl.setWordWrap(wrap)
    lbl.setTextFormat(Qt.RichText if "<" in text else Qt.PlainText)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


def button(text: str, kind: str = "", icon_name: str = "", on_click: Callable | None = None,
           icon_color: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if icon_name:
        color = icon_color or ("#FFFFFF" if kind == "Primary" else theme.ACCENT if kind == "Link" else theme.INK)
        b.setIcon(icons.icon(icon_name, color))
    b.setCursor(Qt.PointingHandCursor)
    if on_click:
        b.clicked.connect(lambda *_: on_click())
    return b


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def copy_text(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class Card(QFrame):
    def __init__(self, parent=None, padding: int = 18, spacing: int = 10):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(spacing)


class Tile(QFrame):
    """A big clickable square on the home screen."""

    def __init__(self, icon_name: str, title: str, text: str, on_click: Callable):
        super().__init__()
        self.setObjectName("Tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.on_click = on_click
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 18)
        lay.setSpacing(8)
        badge = QLabel()
        badge.setFixedSize(48, 48)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background:{theme.ACCENT_SOFT}; border-radius:12px;")
        badge.setPixmap(icons.pixmap(icon_name, 28, theme.ACCENT))
        lay.addWidget(badge)
        lay.addWidget(label(title, "TileTitle"))
        lay.addWidget(label(text, "Muted"))
        lay.addStretch(1)
        self.setAccessibleName(title)
        self.setFocusPolicy(Qt.StrongFocus)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_click()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.on_click()
        else:
            super().keyPressEvent(e)


class Banner(QFrame):
    """A coloured message box: good / warn / bad / info."""

    def __init__(self, kind: str = "info", text: str = ""):
        super().__init__()
        self.icon = QLabel()
        self.icon.setFixedWidth(28)
        self.icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.text = label("")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        lay.addWidget(self.icon)
        lay.addWidget(self.text, 1)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.set(kind, text)

    def set(self, kind: str, text: str) -> None:
        bg, fg, ic = theme.BANNER.get(kind, theme.BANNER["info"])
        self.setStyleSheet(f"Banner {{ background:{bg}; border-radius:12px; }} QLabel {{ color:{fg}; font-size:15px; }}")
        self.icon.setPixmap(icons.pixmap(ic, 22, fg))
        if "<a " in text:
            text = text.replace("<a ", f"<a style='color:{fg}; font-weight:600;' ")
        self.text.setTextFormat(Qt.RichText if "<" in text else Qt.PlainText)
        self.text.setText(text)
        self.setVisible(bool(text))


class Busy(QWidget):
    """Progress bar with a friendly sentence underneath."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(12)
        self.msg = label("", "Muted")
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)
        self.hide()

    def start(self, msg: str, indeterminate: bool = False):
        self.bar.setRange(0, 0 if indeterminate else 100)
        self.bar.setValue(0)
        self.msg.setText(msg)
        self.show()

    def update(self, pct: int, msg: str):
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 100)
        self.bar.setValue(pct)
        if msg:
            self.msg.setText(msg)

    def stop(self):
        self.hide()


class Page(QWidget):
    """A scrollable screen with a big title and a short plain-English intro."""

    def __init__(self, title: str, intro: str = ""):
        super().__init__()
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("ScrollBody")
        scroll.setWidget(body)
        outer.addWidget(scroll)

        wrap = QHBoxLayout(body)
        wrap.setContentsMargins(28, 22, 28, 28)
        column = QWidget()
        column.setMaximumWidth(880)
        wrap.addStretch(1)
        wrap.addWidget(column, 100)
        wrap.addStretch(1)

        self.body = QVBoxLayout(column)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(14)
        self.title_label = label(title, "PageTitle")
        self.body.addWidget(self.title_label)
        self.intro_label = label(intro, "PageIntro")
        self.intro_label.setVisible(bool(intro))
        self.body.addWidget(self.intro_label)

    def finish(self):
        self.body.addStretch(1)

    # called by the main window when this page is shown
    def on_show(self):
        pass


def info_row(name: str, value: str, copyable: bool = True) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 2, 0, 2)
    n = label(name, "Muted")
    n.setFixedWidth(210)
    shown = value or "—"
    v = label(f"<b>{shown}</b>", selectable=True)
    lay.addWidget(n)
    lay.addWidget(v, 1)
    if copyable and value:
        b = button("Copy", icon_name="copy")
        b.setToolTip(f"Copy {value}")
        b.clicked.connect(lambda: (copy_text(value), b.setText("Copied")))
        lay.addWidget(b)
    return w
