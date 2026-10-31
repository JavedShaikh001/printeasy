"""Find printers on the network (private) or by address (public)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..core import discovery
from ..core.discovery import Printer
from ..core.system_printers import match_installed
from . import icons, theme
from .connect_dialog import ConnectDialog
from .widgets import Banner, Busy, Card, Page, button, clear_layout, label, open_url, run_in_background


class PrinterCard(Card):
    def __init__(self, ctx, printer: Printer, on_connect, on_fix_address=None):
        super().__init__()
        self.lay.setSpacing(6)
        top = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.pixmap("usb" if printer.connection == "usb" else "printer", 40, theme.ACCENT))
        pic.setFixedSize(48, 48)
        pic.setAlignment(Qt.AlignCenter)
        top.addWidget(pic, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(printer.title, "CardTitle"))
        if printer.subtitle:
            text.addWidget(label(printer.subtitle, "Muted"))
        extra = []
        if printer.state:
            extra.append(f"Status: {printer.state}")
        if printer.ink:
            extra.append("Ink/toner: " + ", ".join(f"{n} {v}%" for n, v in printer.ink[:4]))
        if extra:
            text.addWidget(label(" • ".join(extra), "Small"))
        top.addLayout(text, 1)

        actions = QVBoxLayout()
        if printer.installed_as:
            done = label(f"<span style='color:{theme.GOOD}'><b>✓ Already connected</b></span>")
            done.setAlignment(Qt.AlignRight)
            actions.addWidget(done)
            actions.addWidget(button("Print a test page", icon_name="page",
                                     on_click=lambda: ctx.test_page(printer.installed_as)))
        else:
            actions.addWidget(button("Connect", "Primary", "plus", on_click=lambda: on_connect(printer)))
        top.addLayout(actions)
        self.lay.addLayout(top)

        if printer.connection != "usb" and printer.ip:
            links = QHBoxLayout()
            links.addSpacing(56)
            if on_fix_address:
                links.addWidget(button("Stop this printer's address from changing", "Link", "pin",
                                       on_click=lambda: on_fix_address(printer)))
            if printer.web_page:
                links.addWidget(button("Open printer's settings page", "Link", "external",
                                       on_click=lambda: open_url(printer.web_page)))
            links.addStretch(1)
            self.lay.addLayout(links)


class FindPage(Page):
    def __init__(self, ctx):
        super().__init__("Find a printer on your network",
                         "PrintEasy looks for printers that are on the same Wi-Fi or cable network as this computer.")
        self.ctx = ctx
        self.searching = False

        self.mode_banner = Banner()
        self.mode_banner.text.linkActivated.connect(self._mode_link)
        self.body.addWidget(self.mode_banner)

        row = QHBoxLayout()
        self.search_btn = button("Search again", "Primary", "refresh", on_click=self.search)
        row.addWidget(self.search_btn)
        row.addStretch(1)
        self.body.addLayout(row)

        self.busy = Busy()
        self.body.addWidget(self.busy)
        self.result_banner = Banner()
        self.body.addWidget(self.result_banner)

        self.results = QVBoxLayout()
        self.results.setSpacing(12)
        holder = QWidget()
        holder.setLayout(self.results)
        self.body.addWidget(holder)

        # Manual address -----------------------------------------------------
        manual = Card()
        manual.lay.addWidget(label("Know the printer's address?", "CardTitle"))
        manual.lay.addWidget(label("Most printers can print or show their address (it looks like 192.168.1.25) "
                                   "from their own menu, usually under Network or Wi-Fi settings.", "Muted"))
        mrow = QHBoxLayout()
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("e.g. 192.168.1.25")
        self.addr.returnPressed.connect(self.check_address)
        mrow.addWidget(self.addr, 1)
        mrow.addWidget(button("Find it", icon_name="search", on_click=self.check_address))
        manual.lay.addLayout(mrow)
        self.manual_banner = Banner()
        manual.lay.addWidget(self.manual_banner)
        self.body.addWidget(manual)

        tips = Card()
        tips.lay.addWidget(label("Printer not showing up?", "CardTitle"))
        tips.lay.addWidget(label(
            "1. Make sure the printer is switched on and not showing an error.<br>"
            "2. Make sure the printer is on the <b>same Wi-Fi</b> as this computer. "
            "A new printer may not be on Wi-Fi yet — use <b>Wi-Fi setup</b> on the home screen.<br>"
            "3. Some printers go to sleep. Press any button on the printer and search again.<br>"
            "4. If the printer has a cable, you can plug it into this computer instead (USB).", ""))
        trow = QHBoxLayout()
        trow.addWidget(button("Set up printer Wi-Fi", icon_name="wifi", on_click=lambda: ctx.go("wifi")))
        trow.addWidget(button("Use a USB cable instead", icon_name="usb", on_click=lambda: ctx.go("usb")))
        trow.addStretch(1)
        tips.lay.addLayout(trow)
        self.body.addWidget(tips)
        self.finish()

    # ------------------------------------------------------------------
    def on_show(self):
        self.refresh_mode()
        if not self.searching:
            self.search()

    def refresh_mode(self):
        net = self.ctx.net
        if net is None or not net.connected:
            self.mode_banner.set("warn", "This computer isn't connected to Wi-Fi or a network cable right now.")
        elif net.mode == "public":
            self.mode_banner.set("warn",
                                 f"You're on a <b>public network</b> ({net.display_name}). To keep you safe, PrintEasy "
                                 "won't search it automatically. Type the printer's address below, or "
                                 "<a href='private'>tell PrintEasy this is your home or work network</a>.")
        else:
            self.mode_banner.set("info", f"Searching {net.display_name}. "
                                         "<a href='mode'>Not your home or work network?</a>")

    def _mode_link(self, href: str):
        if href == "private":
            self.ctx.change_mode("private")
        else:
            self.ctx.ask_mode()

    def search(self):
        net = self.ctx.net
        clear_layout(self.results)
        self.result_banner.set("info", "")
        if net is None or not net.connected or net.mode == "public":
            self.search_btn.setEnabled(net is not None and net.connected and net.mode != "public")
            return
        self.searching = True
        self.search_btn.setEnabled(False)
        self.busy.start("Starting the search…")
        run_in_background(self._find, net, on_progress=self.busy.update,
                          on_done=self._show, on_fail=self._fail)

    def _find(self, net, progress):
        printers = discovery.find_printers(net, progress)
        match_installed(printers, self.ctx.backend.list_installed())
        return printers

    def _show(self, printers):
        self.searching = False
        self.busy.stop()
        self.search_btn.setEnabled(True)
        clear_layout(self.results)
        if not printers:
            self.result_banner.set("warn", "No printers found on this network. Check the tips below, "
                                           "or type the printer's address.")
            return
        n = len(printers)
        self.result_banner.set("good", f"Found {n} printer{'s' if n != 1 else ''}.")
        for p in printers:
            self.results.addWidget(PrinterCard(self.ctx, p, self.connect, self.fix_address))

    def _fail(self, msg):
        self.searching = False
        self.busy.stop()
        self.search_btn.setEnabled(True)
        self.result_banner.set("bad", msg)

    def check_address(self):
        text = self.addr.text().strip()
        if not text:
            self.manual_banner.set("warn", "Please type the printer's address first.")
            return
        self.manual_banner.set("info", f"Looking for a printer at {text}…")
        run_in_background(discovery.check_address, text, on_done=self._address_result,
                          on_fail=lambda m: self.manual_banner.set("bad", m))

    def _address_result(self, printer):
        if printer is None:
            self.manual_banner.set("bad", "No printer answered at that address. Check the number, "
                                          "and that the printer is on and on the same network.")
            return
        match_installed([printer], self.ctx.backend.list_installed())
        self.manual_banner.set("good", "Found it!")
        self.results.insertWidget(0, PrinterCard(self.ctx, printer, self.connect, self.fix_address))

    def connect(self, printer: Printer):
        dlg = ConnectDialog(self, self.ctx, printer)
        dlg.exec()
        if dlg.connected_name:
            self.search()

    def fix_address(self, printer: Printer):
        self.ctx.go("address", printer)
