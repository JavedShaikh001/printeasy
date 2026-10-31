"""Printers already set up on this computer: choose the main one, test, remove."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from . import icons, theme
from .widgets import Banner, Busy, Card, Page, button, clear_layout, label, run_in_background


class MyPrintersPage(Page):
    def __init__(self, ctx):
        super().__init__("My printers",
                         "These printers are already set up on this computer. "
                         "The one with the star is your main printer — programs use it unless you pick another.")
        self.ctx = ctx
        self.banner = Banner()
        self.busy = Busy()
        self.body.addWidget(self.banner)
        self.body.addWidget(self.busy)
        self.list = QVBoxLayout()
        self.list.setSpacing(10)
        holder = QWidget()
        holder.setLayout(self.list)
        self.body.addWidget(holder)
        row = QHBoxLayout()
        row.addWidget(button("Add another printer", "Primary", "plus", on_click=lambda: ctx.go("find")))
        row.addWidget(button("Open the computer's printer settings", "Link", "external",
                             on_click=ctx.backend.open_system_settings))
        row.addStretch(1)
        self.body.addLayout(row)
        self.finish()

    def on_show(self):
        self.load()

    def load(self):
        self.busy.start("Getting your printers…", True)
        run_in_background(self.ctx.backend.list_installed, on_done=self._show,
                          on_fail=lambda m: (self.busy.stop(), self.banner.set("bad", m)))

    def _show(self, printers):
        self.busy.stop()
        clear_layout(self.list)
        if not printers:
            self.banner.set("info", "No printers are set up yet. Press <b>Add another printer</b> to find one.")
            return
        self.banner.set("info", "")
        for p in sorted(printers, key=lambda p: (not p.is_default, p.name.lower())):
            card = Card(padding=14)
            row = QHBoxLayout()
            star = QLabel()
            star.setPixmap(icons.pixmap("star_fill" if p.is_default else "printer", 30,
                                        theme.WARM if p.is_default else theme.ACCENT))
            star.setFixedWidth(38)
            row.addWidget(star, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(p.name, "CardTitle"))
            bits = []
            if p.is_default:
                bits.append("<b>Main printer</b>")
            if p.location:
                bits.append(p.location if p.is_usb or not p.location[0].isdigit() else f"Network address {p.location}")
            if p.status:
                bits.append(p.status)
            col.addWidget(label(" • ".join(bits), "Muted"))
            row.addLayout(col, 1)
            if not p.is_default:
                row.addWidget(button("Make main printer", icon_name="star", on_click=lambda n=p.name: self.make_main(n)))
            row.addWidget(button("Test page", icon_name="page", on_click=lambda n=p.name: self.ctx.test_page(n)))
            row.addWidget(button("Remove", "Danger", "trash", icon_color=theme.BAD,
                                 on_click=lambda n=p.name: self.remove(n)))
            card.lay.addLayout(row)
            self.list.addWidget(card)

    def make_main(self, name):
        run_in_background(self.ctx.backend.set_default, name, on_done=self._result)

    def remove(self, name):
        ans = QMessageBox.question(self, "Remove printer",
                                   f"Remove “{name}” from this computer?\n\n"
                                   "You can always add it again later.")
        if ans == QMessageBox.Yes:
            self.busy.start("Removing…", True)
            run_in_background(self.ctx.backend.remove, name, on_done=self._result)

    def _result(self, res):
        self.busy.stop()
        self.banner.set("good" if res.ok else "bad", res.message)
        self.ctx.printers_changed()
        self.load()
