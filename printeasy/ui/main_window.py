"""The main window, home screen, network-mode question and system tray."""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout, QMainWindow, QMenu,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..core import apps, config, network
from ..core.system_printers import backend
from . import icons, theme
from .page_address import AddressPage
from .page_apps import AppsPage
from .page_find import FindPage
from .page_fix import FixPage
from .page_mine import MyPrintersPage
from .page_usb import UsbPage
from .page_wifi import WifiPage
from .widgets import Banner, Page, Tile, button, label, run_in_background


class ModeDialog(QDialog):
    """Asks, in plain words, whether this is a trusted network."""

    def __init__(self, parent, net):
        super().__init__(parent)
        self.setWindowTitle("Where are you?")
        self.setMinimumWidth(540)
        self.choice = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 22)
        lay.setSpacing(12)
        lay.addWidget(label("Where are you right now?", "PageTitle"))
        lay.addWidget(label(f"This computer is connected to {net.display_name}. PrintEasy only searches "
                            "networks you trust.", "Muted"))
        home = button("  At home or at work  (private network)", "Primary", "home", on_click=lambda: self._pick("private"))
        home.setMinimumHeight(54)
        pub = button("  Somewhere public: café, hotel, airport, library", icon_name="globe",
                     on_click=lambda: self._pick("public"))
        pub.setMinimumHeight(54)
        lay.addWidget(home)
        lay.addWidget(pub)
        lay.addWidget(label("On a public network PrintEasy won't scan for devices. You can still connect a printer "
                            "by typing its address, or with a USB cable.", "Small"))

    def _pick(self, mode):
        self.choice = mode
        self.accept()


class HomePage(Page):
    def __init__(self, ctx):
        super().__init__("What would you like to do?", "")
        self.ctx = ctx
        self.status = Banner()
        self.body.addWidget(self.status)
        grid = QGridLayout()
        grid.setSpacing(14)
        tiles = [
            ("search", "Find a printer", "Find printers on your Wi-Fi or network and connect in one click.", "find"),
            ("usb", "Plug in with USB", "Connect a printer that's plugged straight into this computer.", "usb"),
            ("wifi", "Wi-Fi setup", "Join Wi-Fi, or help a new printer get onto your Wi-Fi.", "wifi"),
            ("apps", "Printer for each program", "e.g. Word uses the office printer, Photos uses the colour one.", "apps"),
            ("list", "My printers", "Pick your main printer, print a test page, or remove one.", "mine"),
            ("lifebuoy", "It stopped working", "Check for the common problems and fix them automatically.", "fix"),
        ]
        for i, (ic, title, text, page) in enumerate(tiles):
            grid.addWidget(Tile(ic, title, text, lambda p=page: ctx.go(p)), i // 2, i % 2)
        self.body.addLayout(grid)
        self.finish()

    def on_show(self):
        run_in_background(self.ctx.backend.default, on_done=self._show_default)

    def _show_default(self, name):
        if name:
            self.status.set("good", f"Your main printer is <b>{name}</b>.")
        else:
            self.status.set("info", "No main printer yet. Start with <b>Find a printer</b> or <b>Plug in with USB</b>.")


class Ctx(QObject):
    """Shared state and actions every page can use."""
    network_changed = Signal()
    toast = Signal(str)

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window
        self.backend = backend()
        self.net: network.NetworkInfo | None = None

    def go(self, page: str, arg=None):
        self.window.show_page(page, arg)

    def refresh_network(self, ask_if_unknown: bool = True):
        def done(net):
            self.net = net
            self.network_changed.emit()
            if ask_if_unknown and net.connected and not net.mode_known:
                self.ask_mode()
        run_in_background(network.detect, on_done=done)

    def ask_mode(self):
        if not self.net or not self.net.connected:
            return
        dlg = ModeDialog(self.window, self.net)
        if dlg.exec() == QDialog.Accepted and dlg.choice:
            self.change_mode(dlg.choice)

    def change_mode(self, mode: str):
        if not self.net:
            return
        network.remember_mode(self.net, mode)
        self.net.mode, self.net.mode_known = mode, True
        self.network_changed.emit()

    def test_page(self, name: str):
        run_in_background(self.backend.test_page, name, on_done=lambda r: self.toast.emit(r.message))

    def printers_changed(self):
        pass

    def rules_changed(self):
        self.window.restart_rules()


class MainWindow(QMainWindow):
    _switched = Signal(str)

    def __init__(self, start_hidden: bool = False):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(980, 760)
        self.setMinimumSize(720, 560)
        self.ctx = Ctx(self)
        self.history: list[str] = []
        self.engine = None
        self._quitting = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 10, 16, 10)
        self.back = button("Back", "Back", "back", on_click=self.go_back)
        self.back.hide()
        tl.addWidget(self.back)
        logo = label("")
        logo.setPixmap(icons.app_icon().pixmap(30, 30))
        tl.addWidget(logo)
        tl.addWidget(label(APP_NAME, "AppTitle"))
        tl.addStretch(1)
        self.chip = button("Checking network…", "Chip", "wifi", on_click=self.ctx.ask_mode)
        self.chip.setToolTip("Click to change whether this is a home/work or public network")
        tl.addWidget(self.chip)
        root.addWidget(top)

        self.toast = Banner()
        tw = QWidget()
        twl = QVBoxLayout(tw)
        twl.setContentsMargins(20, 10, 20, 0)
        twl.addWidget(self.toast)
        root.addWidget(tw)
        self.toast_timer = QTimer(self, singleShot=True, interval=7000, timeout=lambda: self.toast.set("info", ""))

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.pages = {
            "home": HomePage(self.ctx), "find": FindPage(self.ctx), "usb": UsbPage(self.ctx),
            "wifi": WifiPage(self.ctx), "apps": AppsPage(self.ctx), "mine": MyPrintersPage(self.ctx),
            "fix": FixPage(self.ctx), "address": AddressPage(self.ctx),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)

        self.ctx.network_changed.connect(self._update_chip)
        self.ctx.toast.connect(self.show_toast)
        self._switched.connect(self._notify_switch)

        self._setup_tray()
        self.show_page("home", remember=False)
        self.ctx.refresh_network(ask_if_unknown=not start_hidden)
        self.restart_rules()
        # Re-check the network now and then (people move between home and café)
        self.net_timer = QTimer(self, interval=60_000, timeout=lambda: self.ctx.refresh_network(False))
        self.net_timer.start()

    # ------------------------------------------------------------------ navigation
    def show_page(self, name: str, arg=None, remember: bool = True):
        current = self._current_name()
        if remember and current and current != name:
            self.history.append(current)
        page = self.pages[name]
        if name == "address" and arg is not None:
            page.set_printer(arg)
        self.stack.setCurrentWidget(page)
        self.back.setVisible(name != "home")
        page.on_show()

    def _current_name(self) -> str:
        w = self.stack.currentWidget()
        return next((k for k, v in self.pages.items() if v is w), "")

    def go_back(self):
        target = self.history.pop() if self.history else "home"
        self.show_page(target, remember=False)

    def show_toast(self, text: str):
        kind = "bad" if any(w in text.lower() for w in ("couldn't", "didn't", "wrong", "not ")) else "good"
        self.toast.set(kind, text)
        self.toast_timer.start()

    def _update_chip(self):
        net = self.ctx.net
        if not net or not net.connected:
            self.chip.setText("Not connected")
            self.chip.setIcon(icons.icon("wifi", theme.BAD))
        else:
            where = "Home/work" if net.mode == "private" else "Public"
            self.chip.setText(f"{net.wifi_name or net.kind or 'Network'} • {where}")
            self.chip.setIcon(icons.icon("home" if net.mode == "private" else "globe", theme.ACCENT))
        page = self.stack.currentWidget()
        if hasattr(page, "refresh_mode"):
            page.refresh_mode()

    # ------------------------------------------------------------------ per-app rules
    def restart_rules(self):
        if self.engine:
            self.engine.stop()
            self.engine.restore_now()
            self.engine = None
        s = config.load()
        if s.rules_enabled and s.rules():
            self.engine = apps.RuleEngine(on_switch=self._switched.emit)
            self.engine.start()

    def _notify_switch(self, text: str):
        if self.tray and self.tray.isVisible() and not self.isVisible():
            self.tray.showMessage(APP_NAME, text, icons.app_icon(), 4000)
        elif self.isVisible():
            self.show_toast(text)

    # ------------------------------------------------------------------ tray
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Open PrintEasy", self.bring_to_front)
        menu.addAction("My printers", lambda: (self.bring_to_front(), self.show_page("mine")))
        menu.addSeparator()
        menu.addAction("Quit PrintEasy", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.bring_to_front()
                                    if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()

    def bring_to_front(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        s = config.load()
        if not self._quitting and self.tray and s.rules_enabled and s.rules():
            # Keep running in the tray so per-program printers keep working.
            e.ignore()
            self.hide()
            if not getattr(self, "_told_tray", False):
                self.tray.showMessage(APP_NAME, "PrintEasy is still running here so your program printers keep "
                                                "working. Right-click this icon to quit.", icons.app_icon(), 6000)
                self._told_tray = True
            return
        self.quit_app()

    def quit_app(self):
        self._quitting = True
        if self.engine:
            self.engine.stop()
            self.engine.restore_now()
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()


def version_text() -> str:
    return f"{APP_NAME} {__version__}"
