"""Wi-Fi: see nearby networks, connect to one, and spot printers' own setup networks."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

from .util import IS_MAC, IS_WINDOWS, friendly_error, run, which

# Names printers use for their own temporary Wi-Fi (setup mode or Wi-Fi Direct)
PRINTER_WIFI_PATTERNS = [
    r"^DIRECT-", r"^HP-Setup", r"^HP-Print", r"^HP .*Setup", r"^Canon_ij_", r"^Canon[-_ ]",
    r"^EPSON", r"^Epson", r"^Brother", r"^BRW", r"^Xerox", r"^Lexmark", r"^Samsung.*Setup",
    r"^KYOCERA", r"^Ricoh", r"^RICOH", r"^Pantum", r"^Setup-",
]

# Where each brand's setup page usually lives while you're on its setup Wi-Fi
SETUP_PAGES = {
    "hp": "http://192.168.223.1/",
    "canon": "http://192.168.0.1/",
    "epson": "http://192.168.223.1/",
    "brother": "http://192.168.118.1/",
}


@dataclass
class WifiNetwork:
    ssid: str
    signal: int = 0           # 0-100
    secure: bool = True
    connected: bool = False

    @property
    def is_printer(self) -> bool:
        return any(re.search(p, self.ssid, re.I) for p in PRINTER_WIFI_PATTERNS)

    @property
    def bars(self) -> str:
        n = 4 if self.signal >= 75 else 3 if self.signal >= 50 else 2 if self.signal >= 25 else 1
        return "●" * n + "○" * (4 - n)

    @property
    def setup_page(self) -> str:
        low = self.ssid.lower()
        for brand, url in SETUP_PAGES.items():
            if brand in low or (brand == "brother" and low.startswith("brw")):
                return url
        return ""


@dataclass
class WifiResult:
    ok: bool
    message: str


# ---------------------------------------------------------------------------- current network
def current_wifi_name() -> str:
    if IS_WINDOWS:
        r = run(["netsh", "wlan", "show", "interfaces"], timeout=10)
        for line in r.out.splitlines():
            m = re.match(r"\s*SSID\s*:\s*(.+)$", line)     # skips BSSID because of the \s*SSID anchor
            if m and "BSSID" not in line:
                return m.group(1).strip()
        return ""
    if IS_MAC:
        dev = mac_wifi_device()
        r = run(["networksetup", "-getairportnetwork", dev], timeout=10, english=True)
        m = re.search(r"Current Wi-Fi Network:\s*(.+)", r.out)
        if m:
            return m.group(1).strip()
        r = run(["ipconfig", "getsummary", dev], timeout=10)
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", r.out, re.M)
        if m and "<redacted>" not in m.group(1):
            return m.group(1).strip()
        return ""
    if which("nmcli"):
        r = run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=10, english=True)
        for line in r.out.splitlines():
            if line.startswith("yes:"):
                return _nm_unescape(line[4:])
    if which("iwgetid"):
        return run(["iwgetid", "-r"], timeout=5).out.strip()
    return ""


def mac_wifi_device() -> str:
    r = run(["networksetup", "-listallhardwareports"], timeout=10, english=True)
    m = re.search(r"Hardware Port: (?:Wi-Fi|AirPort)\s*\nDevice: (\S+)", r.out)
    return m.group(1) if m else "en0"


def _nm_unescape(s: str) -> str:
    return s.replace("\\:", ":").replace("\\\\", "\\")


def _nm_split(line: str) -> list[str]:
    return [_nm_unescape(p) for p in re.split(r"(?<!\\):", line)]


# ---------------------------------------------------------------------------- scanning
def scan() -> tuple[list[WifiNetwork], str]:
    """Return (networks, problem). problem is a plain-English note when scanning isn't possible."""
    current = current_wifi_name()
    nets: dict[str, WifiNetwork] = {}

    if IS_WINDOWS:
        r = run(["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=20)
        if "location" in r.out.lower() and "permission" in r.out.lower():
            return [], ("Windows needs Location turned on to list Wi-Fi networks. "
                        "Open Settings → Privacy & security → Location and turn it on.")
        ssid = None
        for line in r.out.splitlines():
            m = re.match(r"^SSID \d+ : (.*)$", line.strip())
            if m:
                ssid = m.group(1).strip()
                if ssid:
                    nets.setdefault(ssid, WifiNetwork(ssid))
                continue
            if ssid and ssid in nets:
                m = re.match(r"\s*Signal\s*:\s*(\d+)%", line)
                if m:
                    nets[ssid].signal = max(nets[ssid].signal, int(m.group(1)))
                m = re.match(r"\s*Authentication\s*:\s*(.+)", line)
                if m:
                    nets[ssid].secure = m.group(1).strip().lower() != "open"
    elif IS_MAC:
        r = run(["system_profiler", "SPAirPortDataType"], timeout=40, english=True)
        section = r.out.split("Other Local Wi-Fi Networks:", 1)
        if len(section) == 2:
            name = None
            for line in section[1].splitlines():
                if re.match(r"^\s{12}\S.*:$", line):
                    name = line.strip()[:-1]
                    nets.setdefault(name, WifiNetwork(name))
                elif name:
                    m = re.search(r"Signal / Noise:\s*(-?\d+) dBm", line)
                    if m:
                        dbm = int(m.group(1))
                        nets[name].signal = max(0, min(100, 2 * (dbm + 100)))
                    m = re.search(r"Security:\s*(.+)", line)
                    if m:
                        nets[name].secure = "none" not in m.group(1).lower()
                elif line.strip() and not line.startswith(" " * 12):
                    break
        if current:
            nets.setdefault(current, WifiNetwork(current, signal=80))
    elif which("nmcli"):
        r = run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"],
                timeout=30, english=True)
        for line in r.out.splitlines():
            parts = _nm_split(line)
            if len(parts) >= 3 and parts[0]:
                n = nets.setdefault(parts[0], WifiNetwork(parts[0]))
                n.signal = max(n.signal, int(parts[1] or 0))
                n.secure = parts[2] not in ("", "--")
    else:
        return [], "This computer doesn't have a Wi-Fi tool PrintEasy knows how to use (NetworkManager)."

    for n in nets.values():
        n.connected = n.ssid == current
    ordered = sorted(nets.values(), key=lambda n: (not n.connected, not n.is_printer, -n.signal))
    if not ordered:
        return [], "No Wi-Fi networks found. Check that Wi-Fi is turned on."
    return ordered, ""


# ---------------------------------------------------------------------------- connecting
def connect(ssid: str, password: str = "") -> WifiResult:
    if IS_WINDOWS:
        return _connect_windows(ssid, password)
    if IS_MAC:
        dev = mac_wifi_device()
        cmd = ["networksetup", "-setairportnetwork", dev, ssid] + ([password] if password else [])
        r = run(cmd, timeout=45, english=True)
        bad = "could not find" in r.out.lower() or "failed" in r.out.lower() or "error" in r.out.lower()
        if r.ok and not bad:
            return WifiResult(True, f"Connected to “{ssid}”.")
        return WifiResult(False, _wifi_error(r.out or r.err))
    if which("nmcli"):
        if not password:
            saved = run(["nmcli", "-t", "-f", "NAME", "con", "show"], timeout=10, english=True)
            if ssid in [_nm_unescape(l) for l in saved.out.splitlines()]:
                r = run(["nmcli", "con", "up", "id", ssid], timeout=60, english=True)
                if r.ok:
                    return WifiResult(True, f"Connected to “{ssid}”.")
        cmd = ["nmcli", "dev", "wifi", "connect", ssid] + (["password", password] if password else [])
        r = run(cmd, timeout=60, english=True)
        if r.ok:
            return WifiResult(True, f"Connected to “{ssid}”.")
        return WifiResult(False, _wifi_error(r.err or r.out))
    return WifiResult(False, "This computer doesn't have a Wi-Fi tool PrintEasy knows how to use.")


def _windows_has_profile(ssid: str) -> bool:
    r = run(["netsh", "wlan", "show", "profiles"], timeout=10)
    return any(line.split(":", 1)[-1].strip() == ssid for line in r.out.splitlines() if ":" in line)


def _connect_windows(ssid: str, password: str) -> WifiResult:
    if not password and _windows_has_profile(ssid):
        # Saved network: reuse the password Windows already knows.
        r = run(["netsh", "wlan", "connect", f"name={ssid}"], timeout=30)
        if not r.ok:
            return WifiResult(False, _wifi_error(r.out or r.err))
        return _wait_for(ssid)
    auth, enc = ("WPA2PSK", "AES") if password else ("open", "none")
    key = (f"<sharedKey><keyType>passPhrase</keyType><protected>false</protected>"
           f"<keyMaterial>{escape(password)}</keyMaterial></sharedKey>") if password else ""
    hex_ssid = ssid.encode("utf-8").hex().upper()
    xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{escape(ssid)}</name>
  <SSIDConfig><SSID><hex>{hex_ssid}</hex><name>{escape(ssid)}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>auto</connectionMode>
  <MSM><security>
    <authEncryption><authentication>{auth}</authentication><encryption>{enc}</encryption><useOneX>false</useOneX></authEncryption>
    {key}
  </security></MSM>
</WLANProfile>"""
    fd, path = tempfile.mkstemp(suffix=".xml", prefix="printeasy_wifi_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(xml)
        add = run(["netsh", "wlan", "add", "profile", f"filename={path}", "user=current"], timeout=20)
    finally:
        try:
            os.remove(path)          # the file contains the password, so never leave it behind
        except OSError:
            pass
    if not add.ok:
        return WifiResult(False, _wifi_error(add.out or add.err))
    r = run(["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"], timeout=30)
    if not r.ok:
        return WifiResult(False, _wifi_error(r.out or r.err))
    return _wait_for(ssid)


def _wait_for(ssid: str) -> WifiResult:
    import time
    for _ in range(15):
        time.sleep(1)
        if current_wifi_name() == ssid:
            return WifiResult(True, f"Connected to “{ssid}”.")
    return WifiResult(False, "Couldn't join that Wi-Fi. Please check the password and try again.")


def _wifi_error(text: str) -> str:
    low = (text or "").lower()
    if "password" in low or "secrets" in low or "key" in low or "802-11-wireless-security" in low:
        return "That Wi-Fi password didn't work. Please check it and try again."
    if "not found" in low or "no network" in low:
        return "That Wi-Fi network isn't in range any more."
    return friendly_error(text)
