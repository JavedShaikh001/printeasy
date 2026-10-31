"""Work out which network this computer is on, and whether it is private or public."""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass

import psutil

from . import config
from .util import IS_MAC, IS_WINDOWS, powershell, run


@dataclass
class NetworkInfo:
    connected: bool
    ip: str = ""
    netmask: str = ""
    gateway: str = ""
    interface: str = ""
    kind: str = ""              # "Wi-Fi", "Cable (Ethernet)" or ""
    wifi_name: str = ""
    os_category: str = ""       # what the OS says: "private", "public" or ""
    mode: str = "private"       # what PrintEasy will actually use
    mode_known: bool = False    # False = we should ask the person once

    @property
    def network(self) -> ipaddress.IPv4Network | None:
        try:
            return ipaddress.ip_network(f"{self.ip}/{self.netmask}", strict=False)
        except ValueError:
            return None

    @property
    def key(self) -> str:
        """A stable name for this network, used to remember the person's choice."""
        return self.wifi_name or (f"cable-{self.gateway}" if self.gateway else "unknown")

    @property
    def display_name(self) -> str:
        if self.wifi_name:
            return f"Wi-Fi “{self.wifi_name}”"
        if self.kind:
            return self.kind
        return "your network"


def local_ip() -> str:
    """The address this computer uses to reach the outside world (no packets are sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def _interface_for(ip: str) -> tuple[str, str]:
    for name, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET and a.address == ip:
                return name, a.netmask or "255.255.255.0"
    return "", "255.255.255.0"


def _guess_kind(iface: str) -> str:
    n = iface.lower()
    if any(k in n for k in ("wi-fi", "wifi", "wlan", "wireless", "wlp", "airport")):
        return "Wi-Fi"
    if IS_MAC and n == "en0":
        return "Wi-Fi"           # en0 is Wi-Fi on almost every modern Mac
    if any(k in n for k in ("eth", "en", "ethernet", "lan")):
        return "Cable (Ethernet)"
    return ""


def default_gateway() -> str:
    if IS_WINDOWS:
        r = powershell("(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric |"
                       " Select-Object -First 1).NextHop", timeout=15)
        return r.out.strip()
    if IS_MAC:
        r = run(["route", "-n", "get", "default"], timeout=10)
        m = re.search(r"gateway:\s*([\d.]+)", r.out)
        return m.group(1) if m else ""
    r = run(["ip", "route", "show", "default"], timeout=10)
    m = re.search(r"default via ([\d.]+)", r.out)
    return m.group(1) if m else ""


def windows_network_category() -> str:
    r = powershell("(Get-NetConnectionProfile | Where-Object {$_.IPv4Connectivity -ne 'Disconnected'} |"
                   " Select-Object -First 1).NetworkCategory", timeout=15)
    cat = r.out.strip().lower()
    if cat in ("private", "domainauthenticated"):
        return "private"
    if cat == "public":
        return "public"
    return ""


def detect() -> NetworkInfo:
    ip = local_ip()
    if not ip or ip.startswith("127."):
        return NetworkInfo(connected=False)

    iface, mask = _interface_for(ip)
    kind = _guess_kind(iface)
    from .wifi import current_wifi_name   # local import avoids a circular import
    ssid = current_wifi_name()
    if ssid:
        kind = "Wi-Fi"

    info = NetworkInfo(connected=True, ip=ip, netmask=mask, gateway=default_gateway(),
                       interface=iface, kind=kind, wifi_name=ssid)
    if IS_WINDOWS:
        info.os_category = windows_network_category()

    settings = config.load()
    if settings.network_mode in ("private", "public"):
        info.mode, info.mode_known = settings.network_mode, True
    elif info.key in settings.network_modes:
        info.mode, info.mode_known = settings.network_modes[info.key], True
    elif info.os_category:
        info.mode, info.mode_known = info.os_category, True
    else:
        # macOS and Linux don't label networks, so we ask the person once per network.
        info.mode, info.mode_known = "private", False
    return info


def remember_mode(info: NetworkInfo, mode: str) -> None:
    s = config.load()
    s.network_modes[info.key] = mode
    config.save(s)


def subnet_hosts(info: NetworkInfo, limit: int = 1024) -> list[str]:
    """Every address on the local network, capped so we never scan huge networks."""
    net = info.network
    if net is None:
        return []
    if net.num_addresses > limit:
        # Big office network: just scan the /24 around this computer.
        net = ipaddress.ip_network(f"{info.ip}/24", strict=False)
    return [str(h) for h in net.hosts() if str(h) != info.ip]
