"""Give a printer a fixed network address so it stops 'going offline'."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..core import ipassign
from ..core.discovery import Printer
from .widgets import Banner, Busy, Card, Page, button, clear_layout, info_row, label, open_url, run_in_background


class AddressPage(Page):
    def __init__(self, ctx):
        super().__init__("Stop the printer's address from changing",
                         "Your router gives every device a number (an address). Sometimes it gives the printer a "
                         "new one, and the computer can't find it any more. Giving the printer a fixed address "
                         "stops that for good.")
        self.ctx = ctx
        self.printer: Printer | None = None
        self.plan = None

        self.who = label("", "SectionTitle")
        self.body.addWidget(self.who)
        self.busy = Busy()
        self.body.addWidget(self.busy)
        self.banner = Banner()
        self.body.addWidget(self.banner)

        self.settings_card = Card()
        self.settings_card.lay.addWidget(label("The settings to use", "CardTitle"))
        self.settings_card.lay.addWidget(label("PrintEasy checked your network and picked a free address "
                                               "that your router is unlikely to give to anything else.", "Muted"))
        self.rows = QVBoxLayout()
        holder = QWidget()
        holder.setLayout(self.rows)
        self.settings_card.lay.addWidget(holder)
        self.body.addWidget(self.settings_card)

        a = Card()
        a.lay.addWidget(label("Option A (recommended): set it on the printer", "CardTitle"))
        a.lay.addWidget(label(
            "<b>1.</b> Press <b>Open printer's settings page</b>. It opens in your web browser.<br>"
            "<b>2.</b> Find <b>Network</b> → <b>TCP/IP</b> or <b>IPv4</b> (sometimes you need to sign in; "
            "the password is often on a sticker on the printer).<br>"
            "<b>3.</b> Change <b>Automatic / DHCP</b> to <b>Manual / Static</b>.<br>"
            "<b>4.</b> Type in the settings above (use the Copy buttons) and save.<br>"
            "<b>5.</b> Come back here and press <b>I've done it — check now</b>."))
        arow = QHBoxLayout()
        self.printer_page_btn = button("Open printer's settings page", "Primary", "external",
                                       on_click=lambda: open_url(self.plan.printer_page) if self.plan else None)
        arow.addWidget(self.printer_page_btn)
        arow.addStretch(1)
        a.lay.addLayout(arow)
        self.body.addWidget(a)

        b = Card()
        b.lay.addWidget(label("Option B: reserve it on your router", "CardTitle"))
        b.lay.addWidget(label(
            "Open your router's page, find <b>DHCP reservation</b> (also called <b>Address reservation</b> "
            "or <b>Static lease</b>), and add the printer using its <b>hardware address</b> and the "
            "<b>new address</b> above. Restart the printer afterwards.", "Muted"))
        brow = QHBoxLayout()
        brow.addWidget(button("Open router page", icon_name="external",
                              on_click=lambda: open_url(self.plan.router_page) if self.plan and self.plan.router_page else None))
        brow.addStretch(1)
        b.lay.addLayout(brow)
        self.body.addWidget(b)

        check = Card()
        check.lay.addWidget(label("Finished?", "CardTitle"))
        crow = QHBoxLayout()
        self.check_btn = button("I've done it — check now", "Primary", "check", on_click=self.verify)
        crow.addWidget(self.check_btn)
        crow.addStretch(1)
        check.lay.addLayout(crow)
        self.check_banner = Banner()
        check.lay.addWidget(self.check_banner)
        self.body.addWidget(check)
        self.finish()

    def set_printer(self, printer: Printer):
        self.printer = printer
        self.plan = None
        self.who.setText(f"Printer: {printer.title}  (now at {printer.ip})")
        self.check_banner.set("info", "")
        clear_layout(self.rows)
        net = self.ctx.net
        if net is None or not net.connected:
            self.banner.set("bad", "This computer isn't connected to a network.")
            return
        net_range = net.network
        import ipaddress
        try:
            same = net_range is not None and ipaddress.ip_address(printer.ip) in net_range
        except ValueError:
            same = False
        if not same:
            self.banner.set("warn", f"This printer ({printer.ip}) is on a different network from this computer "
                                    f"({net.ip}). The settings below are for this computer's network.")
        else:
            self.banner.set("info", "")
        self.busy.start("Finding a free address on your network…", True)
        run_in_background(ipassign.plan, net, printer.ip, printer.web_page, on_done=self._show,
                          on_fail=lambda m: (self.busy.stop(), self.banner.set("bad", m)))

    def _show(self, plan):
        self.busy.stop()
        self.plan = plan
        clear_layout(self.rows)
        if plan.suggested_ip == plan.current_ip:
            self.banner.set("warn", "Couldn't find a spare address, so keep the printer's current one and make it "
                                    "fixed using the same steps.")
        self.rows.addWidget(info_row("New address (IP address)", plan.suggested_ip))
        self.rows.addWidget(info_row("Subnet mask", plan.netmask))
        self.rows.addWidget(info_row("Gateway (router)", plan.gateway))
        self.rows.addWidget(info_row("DNS server", plan.dns))
        self.rows.addWidget(info_row("Printer's hardware address (MAC)", plan.mac_address))

    def verify(self):
        if not self.plan:
            return
        self.check_btn.setEnabled(False)
        self.check_banner.set("info", f"Checking that the printer answers at {self.plan.suggested_ip}…")
        run_in_background(self._verify_work, self.plan.suggested_ip, self.printer.installed_as if self.printer else "",
                          on_done=self._verified, on_fail=lambda m: self.check_banner.set("bad", m))

    def _verify_work(self, ip, installed_as):
        if not ipassign.answers_at(ip):
            return False, ""
        if installed_as:
            res = self.ctx.backend.repoint(installed_as, ip)
            return True, res.message
        return True, ""

    def _verified(self, out):
        ok, msg = out
        self.check_btn.setEnabled(True)
        if ok:
            self.check_banner.set("good", "<b>Done!</b> The printer now has a fixed address and won't get lost again. "
                                          + (msg or ""))
            self.ctx.printers_changed()
        else:
            self.check_banner.set("warn", "The printer isn't answering at the new address yet. Printers often need a "
                                          "restart — turn it off and on, wait a minute, then check again.")
