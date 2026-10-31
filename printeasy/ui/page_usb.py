"""Connect a printer with a USB cable to this one computer."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .connect_dialog import ConnectDialog
from .page_find import PrinterCard
from .widgets import Banner, Busy, Card, Page, button, clear_layout, label, run_in_background


class UsbPage(Page):
    def __init__(self, ctx):
        super().__init__("Connect with a USB cable",
                         "Use this when the printer is plugged straight into this computer. "
                         "Only this computer will be able to use it.")
        self.ctx = ctx

        steps = Card()
        steps.lay.addWidget(label("Before you start", "CardTitle"))
        steps.lay.addWidget(label(
            "<b>1.</b> Plug the printer's USB cable into this computer.<br>"
            "<b>2.</b> Turn the printer on and wait until it stops making noise.<br>"
            "<b>3.</b> Press <b>Check for my printer</b>."))
        row = QHBoxLayout()
        self.check_btn = button("Check for my printer", "Primary", "search", on_click=self.check)
        row.addWidget(self.check_btn)
        row.addStretch(1)
        steps.lay.addLayout(row)
        self.body.addWidget(steps)

        self.busy = Busy()
        self.banner = Banner()
        self.body.addWidget(self.busy)
        self.body.addWidget(self.banner)
        self.results = QVBoxLayout()
        holder = QWidget()
        holder.setLayout(self.results)
        self.body.addWidget(holder)

        help_card = Card()
        help_card.lay.addWidget(label("Still not found?", "CardTitle"))
        help_card.lay.addWidget(label(
            "• Try a different USB port, ideally one directly on the computer (not a hub).<br>"
            "• Some printers come with a cable that only charges — use the printer's own cable.<br>"
            "• Unplug the cable, wait 10 seconds, plug it back in, then check again.", ""))
        help_card.lay.addWidget(button("Open the computer's printer settings", "Link", "external",
                                       on_click=ctx.backend.open_add_printer_wizard))
        self.body.addWidget(help_card)
        self.finish()

    def check(self):
        self.check_btn.setEnabled(False)
        clear_layout(self.results)
        self.banner.set("info", "")
        self.busy.start("Looking at the USB ports… (this can take up to a minute)", True)
        run_in_background(self.ctx.backend.usb_devices, on_done=self._show, on_fail=self._fail)

    def _show(self, printers):
        self.busy.stop()
        self.check_btn.setEnabled(True)
        if not printers:
            self.banner.set("warn", "No USB printer found yet. Check the cable and that the printer is on, "
                                    "then press Check again.")
            self.check_btn.setText("Check again")
            return
        self.banner.set("good", "Found your printer!" if len(printers) == 1 else f"Found {len(printers)} printers.")
        for p in printers:
            self.results.addWidget(PrinterCard(self.ctx, p, self.connect))

    def _fail(self, msg):
        self.busy.stop()
        self.check_btn.setEnabled(True)
        self.banner.set("bad", msg)

    def connect(self, printer):
        dlg = ConnectDialog(self, self.ctx, printer)
        dlg.exec()
        if dlg.connected_name:
            self.check()
