"""Pick which printer each program uses."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget)

from ..core import apps, autostart, config
from ..core.config import AppRule
from . import icons, theme
from .widgets import Banner, Busy, Card, Page, button, clear_layout, label, run_in_background


class AddRuleDialog(QDialog):
    def __init__(self, parent, app_list: list, printers: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Choose a printer for a program")
        self.setMinimumSize(560, 620)
        self.app_list = app_list
        self.result_rule: AppRule | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        lay.addWidget(label("1. Pick the program", "SectionTitle"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type to search, e.g. Word, Photos, Chrome")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        for a in app_list:
            it = QListWidgetItem(a.name)
            it.setData(Qt.UserRole, a)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)

        lay.addWidget(label("2. Pick the printer it should use", "SectionTitle"))
        self.printer = QComboBox()
        self.printer.addItems(printers)
        lay.addWidget(self.printer)

        self.banner = Banner()
        lay.addWidget(self.banner)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", on_click=self.reject))
        ok = button("Save", "Primary", "check", on_click=self._save)
        row.addWidget(ok)
        lay.addLayout(row)
        self.search.setFocus()

    def _filter(self, text):
        t = text.lower().strip()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _save(self):
        it = self.list.currentItem()
        if it is None or it.isHidden():
            self.banner.set("warn", "Please click a program in the list first.")
            return
        if not self.printer.currentText():
            self.banner.set("warn", "There are no printers set up yet. Connect a printer first.")
            return
        a = it.data(Qt.UserRole)
        self.result_rule = AppRule(app_name=a.name, match=a.match, printer=self.printer.currentText())
        self.accept()


class AppsPage(Page):
    def __init__(self, ctx):
        super().__init__("Choose a printer for each program",
                         "For example: Word prints to the office laser printer, and Photos prints to the colour "
                         "printer. PrintEasy quietly switches your main printer while you're using that program, "
                         "and switches it back when you're done.")
        self.ctx = ctx
        self.app_cache = None

        self.support = Banner()
        self.body.addWidget(self.support)

        settings = config.load()
        self.enabled = QCheckBox("Switch printers automatically")
        self.enabled.setChecked(settings.rules_enabled)
        self.enabled.toggled.connect(self._toggle_enabled)
        self.at_login = QCheckBox("Start PrintEasy when I turn on my computer (needed for this to keep working)")
        self.at_login.setChecked(settings.start_at_login)
        self.at_login.toggled.connect(self._toggle_login)
        opts = Card()
        opts.lay.addWidget(self.enabled)
        opts.lay.addWidget(self.at_login)
        self.body.addWidget(opts)

        self.rules_box = QVBoxLayout()
        self.rules_box.setSpacing(8)
        holder = QWidget()
        holder.setLayout(self.rules_box)
        self.body.addWidget(holder)

        self.busy = Busy()
        self.banner = Banner()
        self.body.addWidget(self.busy)
        self.body.addWidget(self.banner)
        row = QHBoxLayout()
        self.add_btn = button("Add a program", "Primary", "plus", on_click=self.add_rule)
        row.addWidget(self.add_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.finish()

    def on_show(self):
        if not apps.foreground_supported():
            self.support.set("warn", "On this Linux desktop PrintEasy can't see which window is in front, so it "
                                     "switches printers based on which of these programs you opened most recently.")
        self.render()

    def render(self):
        clear_layout(self.rules_box)
        rules = config.load().rules()
        if not rules:
            self.rules_box.addWidget(label("No programs added yet.", "Muted"))
            return
        for i, r in enumerate(rules):
            card = Card(padding=12)
            row = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(icons.pixmap("apps", 26, theme.ACCENT))
            row.addWidget(ic)
            row.addWidget(label(f"<b>{r.app_name}</b> &nbsp;→&nbsp; prints to <b>{r.printer}</b>"), 1)
            row.addWidget(button("Remove", "Danger", "trash", icon_color=theme.BAD,
                                 on_click=lambda i=i: self.remove(i)))
            card.lay.addLayout(row)
            self.rules_box.addWidget(card)

    def add_rule(self):
        self.add_btn.setEnabled(False)
        self.busy.start("Getting the list of programs on this computer…", True)
        run_in_background(self._load_lists, on_done=self._open_dialog,
                          on_fail=lambda m: (self.busy.stop(), self.add_btn.setEnabled(True), self.banner.set("bad", m)))

    def _load_lists(self):
        if self.app_cache is None:
            self.app_cache = apps.list_apps()
        printers = [p.name for p in self.ctx.backend.list_installed()]
        return self.app_cache, printers

    def _open_dialog(self, out):
        self.busy.stop()
        self.add_btn.setEnabled(True)
        app_list, printers = out
        if not printers:
            self.banner.set("warn", "Connect a printer first, then come back here.")
            return
        dlg = AddRuleDialog(self, app_list, printers)
        if dlg.exec() == QDialog.Accepted and dlg.result_rule:
            s = config.load()
            rules = [r for r in s.rules() if r.match != dlg.result_rule.match]
            rules.append(dlg.result_rule)
            s.set_rules(rules)
            if not s.start_at_login:
                s.start_at_login = True
                autostart.set_enabled(True)
                self.at_login.setChecked(True)
            config.save(s)
            self.banner.set("good", f"Saved. {dlg.result_rule.app_name} will print to "
                                    f"“{dlg.result_rule.printer}”.")
            self.ctx.rules_changed()
            self.render()

    def remove(self, index):
        s = config.load()
        rules = s.rules()
        if 0 <= index < len(rules):
            rules.pop(index)
            s.set_rules(rules)
            config.save(s)
        self.ctx.rules_changed()
        self.render()

    def _toggle_enabled(self, on):
        s = config.load()
        s.rules_enabled = on
        config.save(s)
        self.ctx.rules_changed()

    def _toggle_login(self, on):
        s = config.load()
        s.start_at_login = on
        config.save(s)
        if not autostart.set_enabled(on):
            self.banner.set("bad", "Couldn't change the start-up setting on this computer.")
