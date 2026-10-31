"""Wi-Fi: connect this computer, and help put a new printer on the home Wi-Fi."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget)

from ..core import wifi
from ..core.wifi import WifiNetwork
from . import icons, theme
from .widgets import Banner, Busy, Card, Page, button, clear_layout, label, open_url, run_in_background


class PasswordDialog(QDialog):
    def __init__(self, parent, ssid: str):
        super().__init__(parent)
        self.setWindowTitle("Wi-Fi password")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.addWidget(label(f"Password for “{ssid}”", "CardTitle"))
        lay.addWidget(label("It's often printed on a sticker on the back or bottom of your router.", "Muted"))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.returnPressed.connect(self.accept)
        lay.addWidget(self.pw)
        show = button("Show password", "Link")
        show.clicked.connect(lambda: (self.pw.setEchoMode(QLineEdit.Normal), show.hide()))
        lay.addWidget(show, 0, Qt.AlignLeft)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", on_click=self.reject))
        ok = button("Join", "Primary", on_click=self.accept)
        ok.setDefault(True)
        row.addWidget(ok)
        lay.addLayout(row)

    def password(self) -> str:
        return self.pw.text()


class NetworkRow(Card):
    def __init__(self, net: WifiNetwork, on_join):
        super().__init__(padding=12)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("printer" if net.is_printer else "wifi", 26, theme.ACCENT))
        row.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        title = net.ssid + ("  — a printer's own Wi-Fi" if net.is_printer else "")
        col.addWidget(label(f"<b>{title}</b>"))
        sub = f"Signal {net.bars}" + ("  •  Password needed" if net.secure else "  •  Open network")
        col.addWidget(label(sub, "Small"))
        row.addLayout(col, 1)
        if net.connected:
            row.addWidget(label(f"<span style='color:{theme.GOOD}'><b>✓ Connected</b></span>"))
        else:
            row.addWidget(button("Join", icon_name="lock" if net.secure else "wifi", on_click=lambda: on_join(net)))
        self.lay.addLayout(row)


class WifiPage(Page):
    def __init__(self, ctx):
        super().__init__("Wi-Fi", "Get this computer and your printer onto the same Wi-Fi.")
        self.ctx = ctx
        self.nets: list[WifiNetwork] = []

        self.current = Banner()
        self.body.addWidget(self.current)

        tabs = QTabWidget()
        tabs.addTab(self._computer_tab(), "Connect this computer")
        tabs.addTab(self._printer_tab(), "Put a new printer on Wi-Fi")
        self.body.addWidget(tabs)
        self.finish()

    # ------------------------------------------------------------- computer tab
    def _computer_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        row = QHBoxLayout()
        self.scan_btn = button("Look for Wi-Fi networks", "Primary", "refresh", on_click=self.scan)
        row.addWidget(self.scan_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.busy = Busy()
        self.banner = Banner()
        lay.addWidget(self.busy)
        lay.addWidget(self.banner)
        self.list = QVBoxLayout()
        self.list.setSpacing(8)
        lay.addLayout(self.list)
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------- printer tab
    def _printer_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(12)

        easy = Card()
        easy.lay.addWidget(label("Easiest way: use the printer's own screen", "CardTitle"))
        easy.lay.addWidget(label(
            "If your printer has a screen, open its <b>Wi-Fi</b> or <b>Wireless setup</b> menu, "
            "pick your home Wi-Fi and type its password. Then come back and press "
            "<b>Find a printer</b> on the home screen."))
        easy.lay.addWidget(label("No screen? Many printers have a <b>WPS</b> (Wi-Fi) button: hold it for 3 seconds, "
                                 "then press the WPS button on your router within 2 minutes.", "Muted"))
        lay.addWidget(easy)

        setup = Card()
        setup.lay.addWidget(label("No screen and no WPS? Use the printer's setup Wi-Fi", "CardTitle"))
        setup.lay.addWidget(label(
            "New printers often make their own temporary Wi-Fi (names like <b>DIRECT-…</b>, "
            "<b>HP-Setup…</b>, <b>Canon_ij_…</b>). PrintEasy can walk you through it:"))
        self.setup_list = QVBoxLayout()
        setup.lay.addLayout(self.setup_list)
        self.setup_banner = Banner()
        setup.lay.addWidget(self.setup_banner)
        lay.addWidget(setup)
        lay.addStretch(1)
        self.home_ssid = ""
        return w

    def on_show(self):
        self.scan()

    def scan(self):
        self.scan_btn.setEnabled(False)
        self.busy.start("Looking for Wi-Fi networks nearby…", True)
        self.banner.set("info", "")
        run_in_background(self._scan_work, on_done=self._show, on_fail=self._fail)

    @staticmethod
    def _scan_work():
        nets, problem = wifi.scan()
        return nets, problem, wifi.current_wifi_name()

    def _show(self, out):
        nets, problem, current = out
        self.busy.stop()
        self.scan_btn.setEnabled(True)
        self.nets = nets
        if current:
            self.current.set("good", f"This computer is on the Wi-Fi “{current}”.")
            if not any(n.is_printer and n.ssid == current for n in nets):
                self.home_ssid = current
        else:
            self.current.set("warn", "This computer isn't on Wi-Fi right now.")
        clear_layout(self.list)
        if problem:
            self.banner.set("warn", problem)
        for n in nets[:25]:
            self.list.addWidget(NetworkRow(n, self.join))
        self._fill_setup_list()

    def _fill_setup_list(self):
        clear_layout(self.setup_list)
        printers = [n for n in self.nets if n.is_printer]
        if not printers:
            self.setup_list.addWidget(label(
                "No printer setup Wi-Fi nearby right now. Turn the printer on, put it in Wi-Fi setup mode "
                "(see its manual, often by holding the Wi-Fi button), then press <b>Look for Wi-Fi networks</b>.",
                "Muted"))
            return
        for n in printers:
            box = QVBoxLayout()
            box.addWidget(label(f"<b>{n.ssid}</b>"))
            steps = QHBoxLayout()
            steps.addWidget(button("1. Join printer's Wi-Fi", on_click=lambda n=n: self.join(n)))
            page = n.setup_page or "http://192.168.223.1/"
            steps.addWidget(button("2. Open its setup page", icon_name="external", on_click=lambda p=page: open_url(p)))
            steps.addWidget(button("3. Back to my Wi-Fi", on_click=self.rejoin_home))
            steps.addStretch(1)
            box.addLayout(steps)
            box.addWidget(label("On the setup page, choose your home Wi-Fi and type its password. "
                                "The printer will restart and join it. Then press step 3.", "Small"))
            self.setup_list.addLayout(box)

    def _fail(self, msg):
        self.busy.stop()
        self.scan_btn.setEnabled(True)
        self.banner.set("bad", msg)

    def join(self, net: WifiNetwork):
        pw = ""
        if net.secure and not net.connected:
            dlg = PasswordDialog(self, net.ssid)
            if dlg.exec() != QDialog.Accepted:
                return
            pw = dlg.password()
            if not pw and not net.is_printer:
                self.banner.set("warn", "A password is needed for that Wi-Fi.")
                return
        if not net.is_printer:
            self.home_ssid = net.ssid
        target = self.setup_banner if net.is_printer else self.banner
        target.set("info", f"Joining “{net.ssid}”…")
        run_in_background(wifi.connect, net.ssid, pw, on_done=lambda r: self._joined(r, target),
                          on_fail=lambda m: target.set("bad", m))

    def _joined(self, res, target):
        target.set("good" if res.ok else "bad", res.message)
        if res.ok:
            self.ctx.refresh_network()
            self.scan()

    def rejoin_home(self):
        if not self.home_ssid:
            self.setup_banner.set("warn", "Pick your home Wi-Fi from the list on the first tab.")
            return
        self.setup_banner.set("info", f"Joining “{self.home_ssid}” again…")
        run_in_background(wifi.connect, self.home_ssid, "", on_done=self._back_home,
                          on_fail=lambda m: self.setup_banner.set("bad", m))

    def _back_home(self, res):
        if res.ok:
            self.setup_banner.set("good", "You're back on your Wi-Fi. Now let's find the printer.")
            self.ctx.refresh_network()
            self.ctx.go("find")
        else:
            self.setup_banner.set("warn", "Couldn't rejoin automatically. Pick your Wi-Fi on the first tab.")
