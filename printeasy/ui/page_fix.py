"""'My printer stopped working': check the usual problems and fix what we can."""
from __future__ import annotations

import socket

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..core import discovery, ipp
from . import icons, theme
from .widgets import Busy, Card, Page, button, clear_layout, label, run_in_background

ICON_FOR = {"good": ("check_circle", theme.GOOD), "warn": ("alert", theme.WARN),
            "bad": ("x_circle", theme.BAD), "info": ("info", theme.ACCENT)}


def _answers(ip: str) -> bool:
    for port in (631, 9100, 515):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        try:
            if s.connect_ex((ip, port)) == 0:
                return True
        except OSError:
            pass
        finally:
            s.close()
    return False


class FixPage(Page):
    def __init__(self, ctx):
        super().__init__("My printer stopped working",
                         "PrintEasy will check the usual problems one by one and fix what it can.")
        self.ctx = ctx
        row = QHBoxLayout()
        self.go_btn = button("Check everything", "Primary", "search", on_click=self.run_checks)
        row.addWidget(self.go_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.busy = Busy()
        self.body.addWidget(self.busy)
        self.out = QVBoxLayout()
        self.out.setSpacing(8)
        holder = QWidget()
        holder.setLayout(self.out)
        self.body.addWidget(holder)
        self.finish()

    def on_show(self):
        clear_layout(self.out)

    def run_checks(self):
        self.go_btn.setEnabled(False)
        clear_layout(self.out)
        self.busy.start("Checking…")
        net = self.ctx.net
        run_in_background(self._work, net, on_progress=self.busy.update, on_done=self._show,
                          on_fail=lambda m: self._show([("bad", "Something went wrong", m, None)]))

    def _work(self, net, progress):
        """Returns a list of (kind, title, detail, action) where action is (button text, callable) or None."""
        b = self.ctx.backend
        out = []
        progress(5, "Checking the network connection…")
        if net is None or not net.connected:
            out.append(("bad", "This computer isn't on a network",
                        "Connect to your Wi-Fi first.", ("Open Wi-Fi", lambda: self.ctx.go("wifi"))))
            return out
        out.append(("good", "Connected to " + net.display_name, "", None))

        progress(15, "Looking at your printers…")
        installed = b.list_installed()
        if not installed:
            out.append(("warn", "No printers are set up on this computer",
                        "Let's find yours.", ("Find a printer", lambda: self.ctx.go("find"))))
            return out
        default = next((i for i in installed if i.is_default), None)
        if default:
            out.append(("good", f"Main printer: {default.name}", "", None))
        else:
            out.append(("warn", "No main printer is chosen",
                        "Programs may not know where to print.", ("Choose one", lambda: self.ctx.go("mine"))))

        network_ones = [i for i in installed if i.location and i.location[0].isdigit()]
        lost = []
        for n, i in enumerate(network_ones):
            progress(25 + int(40 * n / max(1, len(network_ones))), f"Checking {i.name}…")
            if _answers(i.location):
                info = ipp.query(i.location, 631, timeout=3)
                detail = ""
                kind = "good"
                if info:
                    if info.get("state", "").startswith("Stopped"):
                        kind, detail = "warn", "The printer says it needs attention (paper jam, empty tray or a cover open?)."
                    low = [f"{nm} {v}%" for nm, v in info.get("ink", []) if v <= 10]
                    if low:
                        kind = "warn"
                        detail += (" " if detail else "") + "Low ink/toner: " + ", ".join(low)
                out.append((kind, f"{i.name} is answering", detail,
                            ("Print a test page", lambda n=i.name: self.ctx.test_page(n))))
            else:
                lost.append(i)

        if lost and net.mode == "private":
            progress(70, "Some printers didn't answer — searching the network for them…")
            found = discovery.find_printers(net)
            for i in lost:
                match = self._guess_new_address(i, found, {x.location for x in installed})
                if match:
                    out.append(("warn", f"{i.name} moved to a new address ({match.ip})",
                                "The router gave it a new number. Fix it now, then give it a fixed address "
                                "so it doesn't happen again.",
                                ("Fix it", lambda n=i.name, p=match: self._repoint(n, p))))
                else:
                    out.append(("bad", f"{i.name} isn't answering",
                                "Check it's switched on and on the same Wi-Fi. Turn it off and on, then check again.",
                                ("Printer Wi-Fi help", lambda: self.ctx.go("wifi"))))
        elif lost:
            for i in lost:
                out.append(("warn", f"{i.name} isn't answering",
                            "You're on a public network, so the printer may simply be on a different network.", None))
        progress(100, "Done")
        return out

    @staticmethod
    def _guess_new_address(installed, found, taken):
        name = installed.name.lower().replace("_", " ")
        candidates = [p for p in found if p.ip not in taken]
        for p in candidates:
            for label_text in (p.name, p.model):
                if label_text and (label_text.lower() in name or name in label_text.lower()):
                    return p
        words = [w for w in name.split() if len(w) > 3]
        for p in candidates:
            hay = f"{p.name} {p.model}".lower()
            if words and sum(w in hay for w in words) >= max(1, len(words) // 2):
                return p
        return candidates[0] if len(candidates) == 1 else None

    def _repoint(self, name, printer):
        self.busy.start("Fixing…", True)

        def after(res):
            self.busy.stop()
            self.out.insertWidget(0, self._row("good" if res.ok else "bad", res.message, "", None))
            if res.ok:
                self.ctx.printers_changed()
                self.out.insertWidget(1, self._row(
                    "info", "Stop this from happening again", "Give the printer a fixed address.",
                    ("Do it now", lambda: self.ctx.go("address", printer))))
        run_in_background(self.ctx.backend.repoint, name, printer.ip, on_done=after)

    def _show(self, results):
        self.busy.stop()
        self.go_btn.setEnabled(True)
        self.go_btn.setText("Check again")
        clear_layout(self.out)
        for kind, title, detail, action in results:
            self.out.addWidget(self._row(kind, title, detail, action))

    def _row(self, kind, title, detail, action):
        card = Card(padding=12)
        row = QHBoxLayout()
        ic = QLabel()
        name, color = ICON_FOR[kind]
        ic.setPixmap(icons.pixmap(name, 26, color))
        ic.setFixedWidth(32)
        row.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(f"<b>{title}</b>"))
        if detail:
            col.addWidget(label(detail, "Muted"))
        row.addLayout(col, 1)
        if action:
            row.addWidget(button(action[0], on_click=action[1]))
        card.lay.addLayout(row)
        return card
