"""The 'Connect this printer' window: name it, make it the main printer, print a test page."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLineEdit, QVBoxLayout

from ..core.discovery import Printer
from ..core.system_printers import Result
from .widgets import Banner, Busy, button, label, run_in_background


class ConnectDialog(QDialog):
    def __init__(self, parent, ctx, printer: Printer):
        super().__init__(parent)
        self.ctx, self.printer = ctx, printer
        self.setWindowTitle("Connect printer")
        self.setMinimumWidth(520)
        self.setModal(True)
        self.connected_name = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 22)
        lay.setSpacing(12)
        lay.addWidget(label(f"Connect “{printer.title}”", "PageTitle"))
        lay.addWidget(label(printer.subtitle, "Muted"))

        lay.addWidget(label("What would you like to call it?", "SectionTitle"))
        self.name = QLineEdit(self._suggest_name())
        self.name.setMaxLength(60)
        lay.addWidget(self.name)
        lay.addWidget(label("This is the name you'll see when you press Print in any program.", "Small"))

        has_main = bool(ctx.backend.default())
        self.make_main = QCheckBox("Make this my main printer")
        self.make_main.setChecked(not has_main)
        self.test = QCheckBox("Print a test page when it's ready")
        self.test.setChecked(True)
        lay.addWidget(self.make_main)
        lay.addWidget(self.test)

        self.busy = Busy()
        self.banner = Banner()
        lay.addWidget(self.busy)
        lay.addWidget(self.banner)

        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel = button("Cancel", on_click=self.reject)
        self.go = button("Connect", "Primary", "check", on_click=self.start)
        self.go.setDefault(True)
        row.addWidget(self.cancel)
        row.addWidget(self.go)
        lay.addLayout(row)
        self.name.selectAll()
        self.name.setFocus()

    def _suggest_name(self) -> str:
        base = self.printer.name or self.printer.model or "My printer"
        for junk in ("._ipp._tcp.local.", "(", "["):
            base = base.split(junk)[0]
        return base.strip()[:60] or "My printer"

    def start(self):
        if self.go.text() == "Done":
            self.accept()
            return
        name = self.name.text().strip()
        if not name:
            self.banner.set("warn", "Please type a name for the printer.")
            return
        self.go.setEnabled(False)
        self.cancel.setEnabled(False)
        self.name.setEnabled(False)
        self.banner.set("info", "")
        self.busy.start("Setting up the printer. If your computer asks for permission, please say Yes.", True)
        run_in_background(self._work, name, self.make_main.isChecked(), self.test.isChecked(),
                          on_done=self._finished, on_fail=self._failed)

    def _work(self, name: str, make_main: bool, test: bool) -> tuple[Result, list[str]]:
        b = self.ctx.backend
        res = b.add_usb(self.printer, name) if self.printer.connection == "usb" else b.add_network(self.printer, name)
        notes = []
        if res.ok:
            queue = res.printer_name or name
            if make_main:
                d = b.set_default(queue)
                notes.append("It's now your main printer." if d.ok else d.message)
            if test:
                t = b.test_page(queue)
                notes.append("A test page is on its way — check the printer." if t.ok else t.message)
        return res, notes

    def _finished(self, out):
        res, notes = out
        self.busy.stop()
        self.cancel.setEnabled(True)
        if res.ok:
            self.connected_name = res.printer_name or self.name.text().strip()
            self.banner.set("good", f"<b>All set!</b> {res.message}<br>" + "<br>".join(notes))
            self.go.setText("Done")
            self.go.setEnabled(True)
            self.cancel.hide()
            self.ctx.printers_changed()
        else:
            self.banner.set("bad", res.message)
            self.go.setText("Try again")
            self.go.setEnabled(True)
            self.name.setEnabled(True)
            self.cancel.setText("Close")

    def _failed(self, msg: str):
        self.busy.stop()
        self.banner.set("bad", msg)
        self.go.setEnabled(True)
        self.cancel.setEnabled(True)
        self.name.setEnabled(True)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and not self.cancel.isEnabled():
            return
        super().keyPressEvent(e)
