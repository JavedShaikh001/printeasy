"""Tests that run on any computer (no printer needed).   python -m pytest tests"""
from __future__ import annotations

import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())     # keep tests away from real settings

from printeasy.core import apps, config, discovery, ipp, wifi       # noqa: E402
from printeasy.core.config import AppRule                             # noqa: E402
from printeasy.core.network import NetworkInfo, subnet_hosts          # noqa: E402
from printeasy.core.util import CmdResult                             # noqa: E402


# ----------------------------------------------------------------------------- IPP
def test_ipp_request_roundtrip():
    req = ipp.build_request(ipp.GET_PRINTER_ATTRIBUTES, "ipp://1.2.3.4:631/ipp/print",
                            requested=["printer-name", "printer-state"], request_id=7)
    assert req[:4] == b"\x02\x00\x00\x0b"
    assert struct.unpack(">I", req[4:8])[0] == 7
    _, attrs = ipp.parse_response(req)
    assert attrs["printer-uri"] == ["ipp://1.2.3.4:631/ipp/print"]
    assert attrs["requested-attributes"] == ["printer-name", "printer-state"]


def test_ipp_summary_from_fake_printer_response():
    from tests.fake_printer import ipp_response
    reply = ipp_response(ipp.build_request(ipp.GET_PRINTER_ATTRIBUTES, "ipp://x/ipp/print"), "10.0.0.9")
    status, attrs = ipp.parse_response(reply)
    s = ipp.summarise(attrs, "10.0.0.9", 631, "/ipp/print", False)
    assert status == 0
    assert s["model"] == "Acme InkJet 5000"
    assert s["state"] == "Ready"
    assert s["ink"] == [("Black", 64), ("Cyan", 8)]
    assert s["uri"] == "ipp://10.0.0.9:631/ipp/print"


# ----------------------------------------------------------------------------- network
def test_public_network_never_scans(monkeypatch):
    called = []
    monkeypatch.setattr(discovery, "mdns_browse", lambda *a: called.append("mdns") or [])
    monkeypatch.setattr(discovery, "scan_hosts", lambda *a, **k: called.append("scan") or {})
    net = NetworkInfo(connected=True, ip="10.1.1.5", netmask="255.255.255.0", mode="public")
    assert discovery.find_printers(net) == []
    assert called == []


def test_big_networks_are_limited_to_nearby_addresses():
    net = NetworkInfo(connected=True, ip="10.20.30.40", netmask="255.255.0.0")
    hosts = subnet_hosts(net)
    assert len(hosts) == 253 and all(h.startswith("10.20.30.") for h in hosts)


# ----------------------------------------------------------------------------- Wi-Fi parsing
WINDOWS_NETSH = """
SSID 1 : HomeNet
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    BSSID 1                 : aa:bb:cc:dd:ee:ff
         Signal             : 82%
SSID 2 : DIRECT-4F-HP OfficeJet 8020
    Authentication          : WPA2-Personal
    BSSID 1                 : 11:22:33:44:55:66
         Signal             : 60%
SSID 3 : CoffeeShop
    Authentication          : Open
    BSSID 1                 : 66:55:44:33:22:11
         Signal             : 30%
"""


def test_windows_wifi_scan(monkeypatch):
    monkeypatch.setattr(wifi, "IS_WINDOWS", True)
    monkeypatch.setattr(wifi, "IS_MAC", False)
    monkeypatch.setattr(wifi, "current_wifi_name", lambda: "HomeNet")
    monkeypatch.setattr(wifi, "run", lambda *a, **k: CmdResult(True, WINDOWS_NETSH, "", 0))
    nets, problem = wifi.scan()
    assert problem == ""
    by = {n.ssid: n for n in nets}
    assert nets[0].ssid == "HomeNet" and nets[0].connected
    assert by["DIRECT-4F-HP OfficeJet 8020"].is_printer
    assert by["DIRECT-4F-HP OfficeJet 8020"].setup_page == "http://192.168.223.1/"
    assert by["CoffeeShop"].secure is False and by["CoffeeShop"].signal == 30


def test_linux_wifi_scan_handles_escaped_colons(monkeypatch):
    monkeypatch.setattr(wifi, "IS_WINDOWS", False)
    monkeypatch.setattr(wifi, "IS_MAC", False)
    monkeypatch.setattr(wifi, "which", lambda n: True)
    monkeypatch.setattr(wifi, "current_wifi_name", lambda: "")
    out = "My\\:Net:77:WPA2\nCanon_ij_1234:55:\n"
    monkeypatch.setattr(wifi, "run", lambda *a, **k: CmdResult(True, out, "", 0))
    nets, _ = wifi.scan()
    names = {n.ssid: n for n in nets}
    assert "My:Net" in names and names["My:Net"].signal == 77
    assert names["Canon_ij_1234"].is_printer and not names["Canon_ij_1234"].secure


# ----------------------------------------------------------------------------- per-app printers
def test_rule_matching():
    word = AppRule("Microsoft Word", "winword.exe", "Office Laser")
    assert apps.rule_matches(word, "WINWORD.EXE", [r"C:\Program Files\Microsoft Office\WINWORD.EXE"])
    assert not apps.rule_matches(word, "excel.exe", [])
    lo = AppRule("LibreOffice Writer", "libreoffice", "Colour")
    assert apps.rule_matches(lo, "soffice.bin", ["/usr/lib/libreoffice/program/soffice.bin"])


class FakeBackend:
    def __init__(self):
        self.current = "Home Printer"
        self.calls = []

    def default(self):
        return self.current

    def set_default(self, name):
        self.calls.append(name)
        self.current = name
        from printeasy.core.system_printers import Result
        return Result(True, "ok", name)


def test_rule_engine_switches_and_restores():
    eng = apps.RuleEngine.__new__(apps.RuleEngine)       # skip thread setup
    eng.backend, eng.on_switch = FakeBackend(), None
    eng._baseline = eng._applied = eng._last_rule_app = None
    rule = AppRule("Photos", "photos.exe", "Colour Printer")
    eng._apply(rule)
    assert eng.backend.current == "Colour Printer"
    eng._restore()
    assert eng.backend.current == "Home Printer"


def test_rule_engine_respects_manual_change():
    eng = apps.RuleEngine.__new__(apps.RuleEngine)
    eng.backend, eng.on_switch = FakeBackend(), None
    eng._baseline = eng._applied = eng._last_rule_app = None
    eng._apply(AppRule("Photos", "photos.exe", "Colour Printer"))
    eng.backend.current = "Office Laser"                 # person picked a printer themselves
    eng._restore()
    assert eng.backend.current == "Office Laser"


def test_settings_roundtrip():
    s = config.load()
    s.set_rules([AppRule("Word", "winword.exe", "Laser")])
    s.network_modes["HomeNet"] = "private"
    config.save(s)
    s2 = config.load()
    assert s2.rules()[0].printer == "Laser" and s2.network_modes["HomeNet"] == "private"


def test_cups_queue_names_are_safe():
    from printeasy.core.system_printers import _clean_name
    assert _clean_name("Kitchen Printer #2 / upstairs") == "Kitchen_Printer_2_upstairs"
