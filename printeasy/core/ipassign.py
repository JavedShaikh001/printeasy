"""Keep a printer's network address from changing.

The most common reason a working printer suddenly "goes offline" is that the router
hands it a new address. The fix is to give it a fixed address. There is no single
standard way to change a printer's address from outside, so PrintEasy:

  1. works out a free address on this network that is unlikely to be handed out,
  2. shows the exact settings to type in (address, mask, gateway, DNS),
  3. opens the printer's own settings page (or the router page) for the person,
  4. afterwards checks that the printer answers on the new address and updates
     this computer to use it.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .network import NetworkInfo
from .util import IS_MAC, IS_WINDOWS, run


@dataclass
class AddressPlan:
    current_ip: str
    suggested_ip: str
    netmask: str
    gateway: str
    dns: str
    mac_address: str
    printer_page: str
    router_page: str


def _ping(ip: str) -> bool:
    if IS_WINDOWS:
        cmd = ["ping", "-n", "1", "-w", "600", ip]
    elif IS_MAC:
        cmd = ["ping", "-c", "1", "-W", "600", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    r = run(cmd, timeout=4)
    return r.ok and ("ttl=" in r.out.lower())


def _any_port(ip: str) -> bool:
    for port in (80, 443, 445, 631, 9100, 62078):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            if s.connect_ex((ip, port)) == 0:
                return True
        except OSError:
            pass
        finally:
            s.close()
    return False


def in_use(ip: str) -> bool:
    return _ping(ip) or _any_port(ip) or bool(mac_for(ip))


def mac_for(ip: str) -> str:
    """Hardware (MAC) address of a device we've talked to recently. Routers need this for reservations."""
    if IS_WINDOWS:
        r = run(["arp", "-a", ip], timeout=5)
    elif IS_MAC:
        r = run(["arp", "-n", ip], timeout=5)
    else:
        r = run(["ip", "neigh", "show", ip], timeout=5)
        if not r.ok:
            r = run(["arp", "-n", ip], timeout=5)
    m = re.search(r"([0-9a-fA-F]{1,2}[:-]){5}[0-9a-fA-F]{1,2}", r.out)
    if not m:
        return ""
    parts = re.split("[:-]", m.group(0))
    return ":".join(p.zfill(2) for p in parts).upper()


def candidate_ips(net: NetworkInfo) -> list[str]:
    """Addresses near the top of the range: most routers hand out addresses from the bottom/middle."""
    n = net.network
    if n is None:
        return []
    hosts = list(n.hosts())
    if len(hosts) > 254:
        n = ipaddress.ip_network(f"{net.ip}/24", strict=False)
        hosts = list(n.hosts())
    taken = {net.ip, net.gateway}
    preferred = [h for h in hosts if 200 <= int(str(h).split(".")[-1]) <= 249] or hosts[-40:]
    return [str(h) for h in preferred if str(h) not in taken]


def find_free_ip(net: NetworkInfo, avoid: set[str] | None = None) -> str:
    avoid = avoid or set()
    candidates = [c for c in candidate_ips(net) if c not in avoid][:40]
    with ThreadPoolExecutor(max_workers=20) as pool:
        busy = list(pool.map(in_use, candidates))
    for ip, used in zip(candidates, busy):
        if not used:
            return ip
    return ""


def plan(net: NetworkInfo, printer_ip: str, printer_page: str = "") -> AddressPlan:
    _ping(printer_ip)                         # make sure it's in the ARP table so we can read its MAC
    return AddressPlan(
        current_ip=printer_ip,
        suggested_ip=find_free_ip(net, {printer_ip}) or printer_ip,
        netmask=net.netmask,
        gateway=net.gateway,
        dns=net.gateway,
        mac_address=mac_for(printer_ip),
        printer_page=printer_page or f"http://{printer_ip}/",
        router_page=f"http://{net.gateway}/" if net.gateway else "",
    )


def answers_at(ip: str) -> bool:
    for port in (631, 9100, 515, 80):
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
