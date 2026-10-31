"""Per-app default printers.

The person picks a program (e.g. Word) and a printer. While that program is the
window in front, PrintEasy makes that printer the computer's default, so the
program's Print button uses it. When they switch away, the previous default comes back.
"""
from __future__ import annotations

import glob
import json
import os
import plistlib
import re
import threading
from dataclasses import dataclass
from typing import Callable

import psutil

from . import config
from .config import AppRule
from .util import IS_LINUX, IS_MAC, IS_WINDOWS, powershell, run, which


@dataclass
class InstalledApp:
    name: str
    match: str      # executable name used to recognise the running program
    path: str = ""


SKIP_WORDS = ("uninstall", "readme", "help", "website", "release notes", "license", "documentation",
              "manual", "repair", "setup", "updater", "crash", "debug")


def _stem(path_or_name: str) -> str:
    base = os.path.basename(path_or_name.strip().strip('"'))
    for ext in (".exe", ".app", ".bin", ".sh", ".AppImage"):
        if base.lower().endswith(ext.lower()):
            base = base[: -len(ext)]
    return base.lower()


# Programs whose running process has a different name from their launcher
ALIASES = {
    "libreoffice": ["soffice", "soffice.bin"],
    "google-chrome": ["chrome"],
    "google-chrome-stable": ["chrome"],
    "firefox": ["firefox-bin", "firefox-esr"],
    "code": ["code", "electron"],
}


# ---------------------------------------------------------------------------- listing apps
def list_apps() -> list[InstalledApp]:
    if IS_WINDOWS:
        apps = _windows_apps()
    elif IS_MAC:
        apps = _mac_apps()
    else:
        apps = _linux_apps()
    seen, out = set(), []
    for a in sorted(apps, key=lambda a: a.name.lower()):
        key = (a.name.lower(), a.match)
        if key in seen or not a.match or any(w in a.name.lower() for w in SKIP_WORDS):
            continue
        seen.add(key)
        out.append(a)
    return out


def _windows_apps() -> list[InstalledApp]:
    script = r"""
$sh = New-Object -ComObject WScript.Shell
$dirs = @("$env:ProgramData\Microsoft\Windows\Start Menu\Programs", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs")
$out = foreach ($d in $dirs) {
  Get-ChildItem -Path $d -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
    try { $t = $sh.CreateShortcut($_.FullName).TargetPath } catch { $t = '' }
    if ($t -like '*.exe') { [pscustomobject]@{ name = $_.BaseName; target = $t } }
  }
}
$out | ConvertTo-Json -Compress
"""
    r = powershell(script, timeout=60)
    apps = []
    try:
        data = json.loads(r.out) if r.out.strip() else []
    except ValueError:
        data = []
    if isinstance(data, dict):
        data = [data]
    for d in data:
        target = d.get("target") or ""
        apps.append(InstalledApp(name=d.get("name", ""), match=os.path.basename(target).lower(), path=target))
    # Store (UWP) apps like Photos don't have shortcuts; add the common ones people print from.
    for name, exe in (("Photos", "photos.exe"), ("Microsoft Edge", "msedge.exe"), ("Notepad", "notepad.exe")):
        apps.append(InstalledApp(name=name, match=exe))
    return apps


def _mac_apps() -> list[InstalledApp]:
    apps = []
    roots = ["/Applications", "/Applications/Utilities", "/System/Applications",
             "/System/Applications/Utilities", os.path.expanduser("~/Applications")]
    for root in roots:
        for app in glob.glob(os.path.join(root, "*.app")):
            exe = os.path.basename(app)[:-4]
            try:
                with open(os.path.join(app, "Contents", "Info.plist"), "rb") as fh:
                    info = plistlib.load(fh)
                exe = info.get("CFBundleExecutable", exe)
                name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or os.path.basename(app)[:-4]
            except (OSError, plistlib.InvalidFileException, ValueError):
                name = os.path.basename(app)[:-4]
            apps.append(InstalledApp(name=name, match=exe.lower(), path=app))
    return apps


def _linux_apps() -> list[InstalledApp]:
    apps = []
    dirs = ["/usr/share/applications", "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
            "/var/lib/snapd/desktop/applications"]
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.desktop")):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            entry = text.split("[Desktop Entry]", 1)[-1].split("\n[", 1)[0]
            if re.search(r"^NoDisplay\s*=\s*true", entry, re.M) or re.search(r"^Type\s*=\s*(?!Application)", entry, re.M):
                continue
            name = re.search(r"^Name\s*=\s*(.+)$", entry, re.M)
            exe = re.search(r"^Exec\s*=\s*(.+)$", entry, re.M)
            if not name or not exe:
                continue
            tokens = [t for t in exe.group(1).split() if "=" not in t]
            if tokens and tokens[0] in ("env", "flatpak"):
                # flatpak run org.app.Name -> use the app id's last part
                tokens = [t for t in tokens if not t.startswith("-") and t not in ("env", "flatpak", "run")]
                cmd = tokens[0].split(".")[-1] if tokens else ""
            else:
                cmd = tokens[0] if tokens else ""
            apps.append(InstalledApp(name=name.group(1).strip(), match=_stem(cmd), path=f))
    return apps


# ---------------------------------------------------------------------------- which app is in front?
def foreground_process() -> tuple[str, list[str]] | None:
    """Return (process name, command line) of the window in front, or None if we can't tell."""
    pid = None
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            p = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            pid = p.value
        except Exception:
            pid = None
    elif IS_MAC:
        asn = run(["lsappinfo", "front"], timeout=3).out.strip()
        if asn:
            r = run(["lsappinfo", "info", "-only", "pid", asn], timeout=3)
            m = re.search(r"=\s*(\d+)", r.out)
            pid = int(m.group(1)) if m else None
    elif IS_LINUX and os.environ.get("DISPLAY") and which("xdotool"):
        r = run(["xdotool", "getactivewindow", "getwindowpid"], timeout=3)
        pid = int(r.out.strip()) if r.out.strip().isdigit() else None
    elif IS_LINUX and os.environ.get("DISPLAY") and which("xprop"):
        r = run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], timeout=3)
        m = re.search(r"window id # (0x[0-9a-f]+)", r.out)
        if m:
            r2 = run(["xprop", "-id", m.group(1), "_NET_WM_PID"], timeout=3)
            m2 = re.search(r"= (\d+)", r2.out)
            pid = int(m2.group(1)) if m2 else None
    if not pid:
        return None
    try:
        proc = psutil.Process(pid)
        return proc.name(), proc.cmdline()
    except (psutil.Error, OSError):
        return None


def foreground_supported() -> bool:
    if IS_WINDOWS or IS_MAC:
        return True
    return bool(os.environ.get("DISPLAY")) and os.environ.get("XDG_SESSION_TYPE", "x11") != "wayland" \
        and (which("xdotool") or which("xprop"))


def rule_matches(rule: AppRule, proc_name: str, cmdline: list[str]) -> bool:
    want = _stem(rule.match)
    if not want:
        return False
    names = {_stem(proc_name)}
    if cmdline:
        names.add(_stem(cmdline[0]))
    candidates = {want, *ALIASES.get(want, [])}
    return bool(names & {_stem(c) for c in candidates})


def running_rule(rules: list[AppRule]) -> AppRule | None:
    """Fallback when we can't see the window in front (e.g. Linux Wayland): newest running app with a rule."""
    best, best_time = None, 0.0
    for proc in psutil.process_iter(["name", "cmdline", "create_time"]):
        try:
            for r in rules:
                if rule_matches(r, proc.info["name"] or "", proc.info["cmdline"] or []):
                    if proc.info["create_time"] > best_time:
                        best, best_time = r, proc.info["create_time"]
        except (psutil.Error, TypeError):
            continue
    return best


# ---------------------------------------------------------------------------- background switcher
class RuleEngine(threading.Thread):
    """Watches the front window and switches the default printer to match the rules."""

    def __init__(self, on_switch: Callable[[str], None] | None = None, interval: float = 1.5):
        super().__init__(daemon=True, name="PrintEasyRules")
        from .system_printers import backend
        self.backend = backend()
        self.on_switch = on_switch
        self.interval = interval
        self._halt = threading.Event()
        self._baseline: str | None = None      # the person's normal default printer
        self._applied: str | None = None       # printer we switched to, if any
        self._last_rule_app: str | None = None

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        use_foreground = foreground_supported()
        while not self._halt.wait(self.interval):
            try:
                settings = config.load()
                rules = settings.rules() if settings.rules_enabled else []
                if not rules:
                    self._restore()
                    continue
                rule = None
                if use_foreground:
                    fg = foreground_process()
                    if fg is None:
                        continue
                    if "printeasy" in fg[0].lower():
                        continue                # don't flip printers while the person is in PrintEasy
                    rule = next((r for r in rules if rule_matches(r, fg[0], fg[1])), None)
                else:
                    rule = running_rule(rules)
                if rule:
                    self._apply(rule)
                else:
                    self._restore()
            except Exception:
                continue                        # never let the background helper crash the app

    def _apply(self, rule: AppRule) -> None:
        current = self.backend.default()
        if current == rule.printer:
            self._last_rule_app = rule.app_name
            return
        if self._applied is None:
            self._baseline = current
        elif current != self._applied:
            self._baseline = current            # person changed the default themselves; respect it
        res = self.backend.set_default(rule.printer)
        if res.ok:
            self._applied = rule.printer
            if self.on_switch and self._last_rule_app != rule.app_name:
                self.on_switch(f"{rule.app_name} will print to “{rule.printer}”")
            self._last_rule_app = rule.app_name

    def _restore(self) -> None:
        if self._applied is None:
            return
        current = self.backend.default()
        if current == self._applied and self._baseline and self._baseline != current:
            self.backend.set_default(self._baseline)
        self._applied = None
        self._last_rule_app = None

    def restore_now(self) -> None:
        self._restore()
