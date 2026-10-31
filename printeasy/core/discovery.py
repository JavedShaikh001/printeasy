"""Find printers on the network.

Private network: listen for printers announcing themselves (Bonjour/mDNS) AND
                 check every address on the local network for printer ports.
Public network:  no scanning at all (scanning a café or hotel network is rude and
                 can be blocked); the person types the printer's address instead.
"""
from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from . import ipp
from .network import NetworkInfo, subnet_hosts

PRINTER_PORTS = {631: "IPP", 9100: "Raw (JetDirect)", 515: "LPD"}
MDNS_TYPES = ["_ipp._tcp.local.", "_ipps._tcp.local.", "_pdl-datastream._tcp.local.", "_printer._tcp.local."]

Progress = Callable[[int, str], None]   # (percent 0-100, message)


@dataclass
class Printer:
    name: str
    ip: str = ""
    model: str = ""
    uri: str = ""                 # how to send jobs to it, e.g. ipp://192.168.1.20:631/ipp/print
    connection: str = "network"   # "network" or "usb"
    state: str = ""
    location: str = ""
    web_page: str = ""
    ink: list = field(default_factory=list)
    ports: list = field(default_factory=list)
    found_by: str = ""
    installed_as: str = ""        # name of the matching printer already set up on this computer
    usb_id: str = ""              # device id for USB printers

    @property
    def title(self) -> str:
        return self.name or self.model or f"Printer at {self.ip}"

    @property
    def subtitle(self) -> str:
        bits = []
        if self.model and self.model != self.name:
            bits.append(self.model)
        if self.connection == "usb":
            bits.append("Plugged in with a USB cable")
        elif self.ip:
            bits.append(f"Network address {self.ip}")
        if self.location:
            bits.append(self.location)
        return " • ".join(bits)


# --------------------------------------------------------------------------- mDNS
def mdns_browse(seconds: float = 4.0) -> list[Printer]:
    try:
        from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
    except ImportError:
        return []

    found: dict[str, Printer] = {}
    zc = Zeroconf()

    def on_change(zeroconf, service_type, name, state_change):
        if state_change is not ServiceStateChange.Added:
            return
        info = zeroconf.get_service_info(service_type, name, timeout=2000)
        if not info:
            return
        addrs = info.parsed_addresses()
        ipv4 = [a for a in addrs if ":" not in a]
        if not ipv4:
            return
        ip = ipv4[0]
        props = {}
        for k, v in (info.properties or {}).items():
            try:
                props[k.decode()] = v.decode() if isinstance(v, bytes) else str(v)
            except (AttributeError, UnicodeDecodeError):
                continue
        friendly = name.split("._")[0].replace("\\032", " ")
        model = props.get("ty") or props.get("product", "").strip("()")
        p = found.get(ip) or Printer(name=friendly, ip=ip, found_by="Announced itself on the network")
        p.model = p.model or model
        p.location = p.location or props.get("note", "")
        p.web_page = p.web_page or props.get("adminurl", "")
        port = info.port or 0
        if port and port not in p.ports:
            p.ports.append(port)
        if service_type.startswith("_ipp") and not p.uri:
            scheme = "ipps" if service_type.startswith("_ipps") else "ipp"
            rp = props.get("rp", "ipp/print")
            p.uri = f"{scheme}://{ip}:{port}/{rp.lstrip('/')}"
        found[ip] = p

    browsers = [ServiceBrowser(zc, t, handlers=[on_change]) for t in MDNS_TYPES]
    try:
        time.sleep(seconds)
    finally:
        for b in browsers:
            b.cancel()
        zc.close()
    return list(found.values())


# --------------------------------------------------------------------------- port scan
def _port_open(ip: str, port: int, timeout: float) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def scan_hosts(hosts: list[str], progress: Progress | None = None, timeout: float = 0.6,
               workers: int = 128) -> dict[str, list[int]]:
    """Return {ip: [open printer ports]} for every host that has a printer port open."""
    results: dict[str, list[int]] = {}
    jobs = [(h, p) for h in hosts for p in PRINTER_PORTS]
    if not jobs:
        return results
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_port_open, h, p, timeout): (h, p) for h, p in jobs}
        for fut in as_completed(futures):
            h, p = futures[fut]
            done += 1
            if fut.result():
                results.setdefault(h, []).append(p)
            if progress and done % 64 == 0:
                progress(20 + int(60 * done / len(jobs)), "Checking every device on your network…")
    return results


def identify(ip: str, ports: list[int]) -> Printer:
    """Turn an address with open printer ports into a named Printer."""
    p = Printer(name="", ip=ip, ports=sorted(ports), found_by="Found by checking the network")
    if 631 in ports:
        info = ipp.query(ip, 631)
        if info:
            _apply_ipp(p, info)
            return p
    title = ipp.http_title(ip)
    p.name = title or f"Printer at {ip}"
    p.web_page = f"http://{ip}/"
    if 9100 in ports:
        p.uri = f"socket://{ip}:9100"
    elif 515 in ports:
        p.uri = f"lpd://{ip}/queue"
    return p


def _path_of(uri: str) -> str | None:
    if "://" not in uri:
        return None
    rest = uri.split("://", 1)[1]
    return "/" + rest.split("/", 1)[1] if "/" in rest else None


def _apply_ipp(p: Printer, info: dict) -> None:
    p.model = info.get("model") or p.model
    p.name = p.name or info.get("name") or p.model
    p.location = p.location or info.get("location", "")
    p.state = info.get("state", "")
    p.uri = p.uri or info.get("uri", "")
    p.web_page = p.web_page or info.get("web_page", "")
    p.ink = info.get("ink", [])


# --------------------------------------------------------------------------- main entry points
def find_printers(net: NetworkInfo, progress: Progress | None = None) -> list[Printer]:
    """Find network printers. Respects the private/public setting."""
    def say(pct, msg):
        if progress:
            progress(pct, msg)

    if not net.connected:
        say(100, "This computer isn't connected to a network.")
        return []
    if net.mode == "public":
        say(100, "Public network: automatic search is turned off for your safety.")
        return []

    say(5, "Listening for printers that announce themselves…")
    by_ip: dict[str, Printer] = {p.ip: p for p in mdns_browse(4.0)}

    say(20, "Checking every device on your network…")
    open_ports = scan_hosts(subnet_hosts(net), progress)

    say(80, "Getting printer names and models…")
    with ThreadPoolExecutor(max_workers=16) as pool:
        futs = {}
        for ip, ports in open_ports.items():
            if ip in by_ip:
                existing = by_ip[ip]
                existing.ports = sorted(set(existing.ports) | set(ports))
            else:
                futs[pool.submit(identify, ip, ports)] = ("new", ip)
        # Printers that announced themselves: ask for status and ink, and note their other ports
        for ip, p in by_ip.items():
            if ip not in open_ports:
                p.ports = sorted(set(p.ports) | {port for port in PRINTER_PORTS if _port_open(ip, port, 0.6)})
            if 631 in p.ports or p.uri.startswith("ipp"):
                futs[pool.submit(ipp.query, ip, 631, _path_of(p.uri))] = ("enrich", ip)
        for fut in as_completed(futs):
            kind, ip = futs[fut]
            res = fut.result()
            if kind == "new":
                by_ip[ip] = res
            elif res:
                _apply_ipp(by_ip[ip], res)

    say(100, "Done")
    return sorted(by_ip.values(), key=lambda p: tuple(int(x) for x in p.ip.split(".")) if p.ip else (999,))


def check_address(address: str, progress: Progress | None = None) -> Printer | None:
    """Look for a printer at one address the person typed in (works on any network)."""
    address = address.strip().replace("http://", "").replace("https://", "").split("/")[0]
    if progress:
        progress(10, f"Looking for a printer at {address}…")
    try:
        ip = socket.gethostbyname(address)
    except OSError:
        return None
    ports = [p for p in PRINTER_PORTS if _port_open(ip, p, 2.0)]
    if progress:
        progress(60, "Asking the printer about itself…")
    if not ports:
        return None
    printer = identify(ip, ports)
    printer.found_by = "Address typed in"
    if progress:
        progress(100, "Done")
    return printer
