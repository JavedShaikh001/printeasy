"""Talk to the computer's own printer system.

Windows        -> Windows print spooler (PowerShell PrintManagement + CIM)
macOS + Linux  -> CUPS (lpadmin / lpstat / lpoptions / lp)
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass

from .discovery import Printer
from .util import (IS_MAC, IS_WINDOWS, friendly_error, powershell, powershell_admin,
                   ps_quote, run, run_as_admin, which)


@dataclass
class Installed:
    name: str
    location: str = ""        # IP address, "USB" or the raw port / device URI
    is_default: bool = False
    is_usb: bool = False
    status: str = ""
    driver: str = ""


@dataclass
class Result:
    ok: bool
    message: str
    printer_name: str = ""


def _clean_name(name: str, limit: int = 60) -> str:
    """CUPS queue names can't contain spaces, slashes or #."""
    n = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return (n or "Printer")[:limit]


TEST_PAGE_TEXT = (
    "\n\n        PrintEasy test page\n"
    "        ===================\n\n"
    "        If you can read this, your printer is connected and working.\n\n"
    "        You can close PrintEasy now.\n"
)


# ============================================================================ Windows
class WindowsBackend:
    def list_installed(self) -> list[Installed]:
        script = (
            "$def=(Get-CimInstance Win32_Printer -Filter 'Default=TRUE').Name;"
            "$ports=@{}; Get-PrinterPort | ForEach-Object { $ports[$_.Name]=$_.PrinterHostAddress };"
            "Get-Printer | ForEach-Object { [pscustomobject]@{"
            " name=$_.Name; port=$_.PortName; host=$ports[$_.PortName]; driver=$_.DriverName;"
            " status=[string]$_.PrinterStatus; default=($_.Name -eq $def) } } | ConvertTo-Json -Compress"
        )
        r = powershell(script, timeout=40)
        if not r.ok or not r.out.strip():
            return []
        data = json.loads(r.out)
        if isinstance(data, dict):
            data = [data]
        out = []
        for d in data:
            port = d.get("port") or ""
            if d["name"] in ("Microsoft Print to PDF", "Microsoft XPS Document Writer", "Fax", "OneNote (Desktop)",
                             "OneNote for Windows 10"):
                virtual = True
            else:
                virtual = port.upper().startswith(("PORTPROMPT", "NUL", "SHRFAX", "XPS")) or port == ""
            out.append(Installed(
                name=d["name"],
                location=d.get("host") or ("USB cable" if port.upper().startswith("USB") else
                                           "Saves a file instead of printing" if virtual else port),
                is_default=bool(d.get("default")),
                is_usb=port.upper().startswith("USB"),
                status=d.get("status") or "",
                driver=d.get("driver") or "",
            ))
        return out

    def default(self) -> str:
        r = powershell("(Get-CimInstance Win32_Printer -Filter 'Default=TRUE').Name", timeout=20)
        return r.out.strip()

    def set_default(self, name: str) -> Result:
        # Stop Windows from silently changing the default printer behind our back.
        powershell("Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Windows'"
                   " -Name LegacyDefaultPrinterMode -Value 1 -Type DWord", timeout=15)
        script = (f"$p=Get-CimInstance Win32_Printer | Where-Object {{$_.Name -eq {ps_quote(name)}}};"
                  "if(-not $p){throw 'not found'}; $r=Invoke-CimMethod -InputObject $p -MethodName SetDefaultPrinter;"
                  "$r.ReturnValue")
        r = powershell(script, timeout=20)
        if r.ok and r.out.strip() in ("0", ""):
            return Result(True, f"“{name}” is now your main printer.", name)
        return Result(False, friendly_error(r.err or r.out))

    def add_network(self, p: Printer, name: str) -> Result:
        ip = p.ip
        # 1) Driverless IPP (Windows 10/11 built-in "Microsoft IPP Class Driver")
        if p.uri.startswith(("ipp://", "ipps://")):
            url = p.uri.replace("ipps://", "https://", 1).replace("ipp://", "http://", 1)
            r = powershell_admin(f"Add-Printer -Name {ps_quote(name)} -IppURL {ps_quote(url)}")
            if r.ok:
                return Result(True, f"“{name}” is ready to use.", name)
            if "cancel" in (r.err or "").lower() or "closed the permission" in (r.err or ""):
                return Result(False, friendly_error(r.err))

        # 2) Classic TCP/IP port + a driver Windows already has for this model
        port_name = f"IP_{ip}"
        model = (p.model or "").replace("'", "")
        script = f"""
$port={ps_quote(port_name)}; $ip={ps_quote(ip)}; $name={ps_quote(name)}; $model={ps_quote(model)}
if (-not (Get-PrinterPort -Name $port -ErrorAction SilentlyContinue)) {{
  Add-PrinterPort -Name $port -PrinterHostAddress $ip
}}
$driver = $null
if ($model) {{
  $driver = (Get-PrinterDriver | Where-Object {{ $_.Name -like "*$model*" }} | Select-Object -First 1).Name
  if (-not $driver) {{ try {{ Add-PrinterDriver -Name $model; $driver = $model }} catch {{}} }}
}}
if (-not $driver) {{
  foreach ($d in 'Microsoft PCL6 Class Driver','Microsoft PS Class Driver','Generic / Text Only') {{
    try {{ Add-PrinterDriver -Name $d -ErrorAction Stop; $driver = $d; break }} catch {{}}
  }}
}}
Add-Printer -Name $name -PortName $port -DriverName $driver
"""
        r = powershell_admin(script)
        if r.ok:
            return Result(True, f"“{name}” is ready to use.", name)
        return Result(False, "Windows couldn't add this printer automatically. "
                             "Use “Open Windows printer setup” to finish. "
                             f"(Details: {friendly_error(r.err)})")

    def add_usb(self, p: Printer, name: str) -> Result:
        # Windows installs USB printers itself; we just ask it to look again and fetch drivers.
        r = powershell_admin("pnputil /scan-devices | Out-Null; Start-Sleep -Seconds 8")
        if not r.ok:
            return Result(False, friendly_error(r.err))
        names = [i.name for i in self.list_installed() if i.is_usb]
        if names:
            return Result(True, f"“{names[0]}” is ready to use.", names[0])
        return Result(False, "Windows found the printer but is still getting its driver. "
                             "Leave it plugged in for a minute, then press “Check again”.")

    def repoint(self, name: str, new_ip: str) -> Result:
        """Point an installed printer at a new network address (after its address changed)."""
        script = f"""
$name={ps_quote(name)}; $ip={ps_quote(new_ip)}
$p = Get-Printer -Name $name
if ($p.DriverName -like '*IPP Class*') {{
  Remove-Printer -Name $name
  Add-Printer -Name $name -IppURL ("http://" + $ip + ":631/ipp/print")
}} else {{
  $port = "IP_" + $ip
  if (-not (Get-PrinterPort -Name $port -ErrorAction SilentlyContinue)) {{ Add-PrinterPort -Name $port -PrinterHostAddress $ip }}
  Set-Printer -Name $name -PortName $port
}}
"""
        r = powershell_admin(script)
        return Result(r.ok, f"“{name}” now uses address {new_ip}." if r.ok else friendly_error(r.err), name)

    def remove(self, name: str) -> Result:
        r = powershell_admin(f"Remove-Printer -Name {ps_quote(name)}")
        return Result(r.ok, "Printer removed." if r.ok else friendly_error(r.err))

    def test_page(self, name: str) -> Result:
        script = (f"$p=Get-CimInstance Win32_Printer | Where-Object {{$_.Name -eq {ps_quote(name)}}};"
                  "(Invoke-CimMethod -InputObject $p -MethodName PrintTestPage).ReturnValue")
        r = powershell(script, timeout=30)
        ok = r.ok and r.out.strip() in ("0", "")
        return Result(ok, "Test page sent. Check your printer!" if ok else friendly_error(r.err or r.out))

    def open_system_settings(self) -> None:
        run(["cmd", "/c", "start", "ms-settings:printers"], timeout=10)

    def open_add_printer_wizard(self) -> None:
        run(["rundll32", "printui.dll,PrintUIEntry", "/il"], timeout=10)

    def usb_devices(self) -> list[Printer]:
        script = (
            "Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPDeviceID -like 'USBPRINT*' -or "
            "($_.PNPClass -eq 'Printer' -and $_.PNPDeviceID -like 'USB*') } | "
            "Select-Object Name,PNPDeviceID,Status | ConvertTo-Json -Compress"
        )
        r = powershell(script, timeout=30)
        if not r.ok or not r.out.strip():
            return []
        data = json.loads(r.out)
        if isinstance(data, dict):
            data = [data]
        installed = self.list_installed()
        out = []
        for d in data:
            pr = Printer(name=d.get("Name") or "USB printer", connection="usb",
                         usb_id=d.get("PNPDeviceID", ""), found_by="Plugged in with USB",
                         state="Working" if d.get("Status") == "OK" else "Needs a driver")
            for i in installed:
                if i.is_usb and (i.name.lower() in pr.name.lower() or pr.name.lower() in i.name.lower()):
                    pr.installed_as = i.name
            out.append(pr)
        return out


# ============================================================================ CUPS (macOS + Linux)
class CupsBackend:
    def available(self) -> bool:
        return which("lpstat")

    def list_installed(self) -> list[Installed]:
        if not self.available():
            return []
        default = self.default()
        uris = {}
        for line in run(["lpstat", "-v"], english=True).out.splitlines():
            m = re.match(r"device for (\S+):\s*(\S+)", line)
            if m:
                uris[m.group(1)] = m.group(2)
        out = []
        for line in run(["lpstat", "-p"], english=True).out.splitlines():
            m = re.match(r"printer (\S+) (?:is )?(\w+)", line)
            if not m:
                continue
            name = m.group(1)
            uri = uris.get(name, "")
            host = re.search(r"://(?:[^@/]*@)?([^:/]+)", uri)
            is_usb = uri.startswith("usb:") or "localhost:6" in uri   # ipp-usb uses localhost:60000+
            out.append(Installed(
                name=name,
                location="USB cable" if is_usb else (host.group(1) if host else uri),
                is_default=(name == default),
                is_usb=is_usb,
                status={"idle": "Ready", "printing": "Printing", "disabled": "Turned off"}.get(m.group(2), m.group(2)),
            ))
        return out

    def default(self) -> str:
        r = run(["lpstat", "-d"], english=True)
        m = re.search(r"destination:\s*(\S+)", r.out)
        return m.group(1) if m else ""

    def set_default(self, name: str) -> Result:
        r = run(["lpoptions", "-d", name])
        if r.ok:
            return Result(True, f"“{name}” is now your main printer.", name)
        return Result(False, friendly_error(r.err))

    def _lpadmin(self, args: list[str]) -> Result:
        cmd = ["lpadmin"] + args
        r = run(cmd, timeout=60)
        if not r.ok and ("forbidden" in r.err.lower() or "not authorized" in r.err.lower()
                         or "permission" in r.err.lower() or "unauthorized" in r.err.lower()):
            r = run_as_admin(cmd, "PrintEasy needs your password to add a printer.")
        return Result(r.ok, "" if r.ok else friendly_error(r.err or r.out))

    def find_driver(self, model: str) -> str:
        """Find an installed driver (PPD) that matches the printer model, if any."""
        if not model:
            return ""
        r = run(["lpinfo", "--make-and-model", model, "-m"], timeout=60, english=True)
        lines = [l.split(" ", 1)[0] for l in r.out.splitlines() if l.strip()]
        return lines[0] if lines else ""

    def _generic_driver_args(self) -> list[str]:
        if IS_MAC:
            ppd = ("/System/Library/Frameworks/ApplicationServices.framework/Versions/A/Frameworks/"
                   "PrintCore.framework/Resources/Generic.ppd")
            return ["-P", ppd] if os.path.exists(ppd) else ["-m", "raw"]
        return ["-m", "drv:///sample.drv/generic.ppd"]

    def add_network(self, p: Printer, name: str) -> Result:
        from .discovery import _port_open
        queue = _clean_name(name)
        base = ["-p", queue, "-E", "-D", name, "-L", p.location or p.ip]
        ports = set(p.ports) | {port for port in (9100, 515) if p.ip and _port_open(p.ip, port, 1.0)}
        is_ipp = p.uri.startswith(("ipp://", "ipps://"))
        attempts = []
        if is_ipp:
            attempts.append(base + ["-v", p.uri, "-m", "everywhere"])          # 1. driverless (best)
        drv = self.find_driver(p.model)
        if drv:                                                                # 2. maker's driver, if installed
            attempts.append(base + ["-v", p.uri or f"socket://{p.ip}:9100", "-m", drv])
        if 9100 in ports:                                                      # 3. plain "raw" printing
            attempts.append(base + ["-v", f"socket://{p.ip}:9100"] + self._generic_driver_args())
        elif 515 in ports:
            attempts.append(base + ["-v", f"lpd://{p.ip}/queue"] + self._generic_driver_args())
        elif is_ipp:
            attempts.append(base + ["-v", p.uri] + self._generic_driver_args())
        elif p.uri:
            attempts.append(base + ["-v", p.uri] + self._generic_driver_args())

        last = Result(False, "This printer didn't answer in a way we understand.")
        for args in attempts:
            last = self._lpadmin(args)
            if last.ok:
                run(["cupsenable", queue])
                run(["cupsaccept", queue])
                return Result(True, f"“{name}” is ready to use.", queue)
            if "closed the permission" in last.message:
                break
            run(["lpadmin", "-x", queue])          # tidy up a half-made printer before the next try
        if not attempts:
            return last
        return Result(False, "This printer couldn't be set up automatically. "
                             f"Try “Open the computer's printer settings”. (Details: {last.message})")

    def add_usb(self, p: Printer, name: str) -> Result:
        queue = _clean_name(name)
        uri = p.usb_id
        if uri.startswith("ipp://"):                    # IPP-over-USB printer exposed by ipp-usb
            r = self._lpadmin(["-p", queue, "-E", "-D", name, "-v", uri, "-m", "everywhere"])
        else:
            drv = self.find_driver(p.model or p.name)
            driver_args = ["-m", drv] if drv else self._generic_driver_args()
            r = self._lpadmin(["-p", queue, "-E", "-D", name, "-v", uri] + driver_args)
        if r.ok:
            return Result(True, f"“{name}” is ready to use.", queue)
        return r

    def repoint(self, name: str, new_ip: str) -> Result:
        uri = ""
        for line in run(["lpstat", "-v", name], english=True).out.splitlines():
            m = re.match(r"device for \S+:\s*(\S+)", line)
            if m:
                uri = m.group(1)
        if not uri:
            return Result(False, "Couldn't find that printer on this computer.")
        new_uri = re.sub(r"(://(?:[^@/]*@)?)([^:/]+)", lambda m: m.group(1) + new_ip, uri, count=1)
        r = self._lpadmin(["-p", name, "-v", new_uri])
        return Result(r.ok, f"“{name}” now uses address {new_ip}." if r.ok else r.message, name)

    def remove(self, name: str) -> Result:
        r = self._lpadmin(["-x", name])
        return Result(r.ok, "Printer removed." if r.ok else r.message)

    def test_page(self, name: str) -> Result:
        candidates = ["/usr/share/cups/data/testprint", "/usr/share/cups/data/default-testpage.pdf"]
        page = next((c for c in candidates if os.path.exists(c)), None)
        if not page:
            fd, page = tempfile.mkstemp(suffix=".txt", prefix="printeasy_test_")
            with os.fdopen(fd, "w") as fh:
                fh.write(TEST_PAGE_TEXT)
        r = run(["lp", "-d", name, "-t", "PrintEasy test page", page], timeout=30)
        return Result(r.ok, "Test page sent. Check your printer!" if r.ok else friendly_error(r.err))

    def open_system_settings(self) -> None:
        if IS_MAC:
            run(["open", "x-apple.systempreferences:com.apple.Print-Scan-Settings.extension"], timeout=10)
        else:
            for cmd in (["system-config-printer"], ["gnome-control-center", "printers"],
                        ["xdg-open", "http://localhost:631/"]):
                if which(cmd[0]):
                    import subprocess
                    subprocess.Popen(cmd)
                    return

    def open_add_printer_wizard(self) -> None:
        self.open_system_settings()

    def usb_devices(self) -> list[Printer]:
        r = run(["lpinfo", "-v", "--include-schemes", "usb"], timeout=40, english=True)
        if not r.ok:
            r = run_as_admin(["lpinfo", "-v", "--include-schemes", "usb"], "PrintEasy needs permission to look for USB printers.")
        out = []
        installed = self.list_installed()
        for line in r.out.splitlines():
            m = re.match(r"direct (usb://\S+)", line.strip())
            if not m:
                continue
            uri = m.group(1)
            nm = re.sub(r"\?.*$", "", uri.split("usb://", 1)[1]).replace("/", " ").replace("%20", " ")
            pr = Printer(name=nm, model=nm, connection="usb", usb_id=uri, found_by="Plugged in with USB")
            for i in installed:
                if i.is_usb:
                    pr.installed_as = pr.installed_as or i.name
            out.append(pr)
        # IPP-over-USB printers (modern printers) appear as local network printers via ipp-usb
        for i in installed:
            if i.is_usb and not any(p.installed_as == i.name for p in out):
                out.append(Printer(name=i.name, connection="usb", installed_as=i.name, found_by="Plugged in with USB"))
        return out


def backend():
    return WindowsBackend() if IS_WINDOWS else CupsBackend()


def match_installed(printers: list[Printer], installed: list[Installed]) -> None:
    """Mark which found printers are already set up on this computer."""
    for p in printers:
        for i in installed:
            if p.ip and p.ip == i.location:
                p.installed_as = i.name
                break
