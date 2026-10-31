"""Start PrintEasy quietly (in the tray) when the person logs in, so app printer rules keep working."""
from __future__ import annotations

import os
import sys

from .util import IS_MAC, IS_WINDOWS

LABEL = "com.printeasy.app"


def _launch_command() -> list[str]:
    if getattr(sys, "frozen", False):            # installed app
        exe = sys.executable
        if IS_MAC and ".app/Contents/MacOS/" in exe:
            return [exe, "--tray"]
        return [exe, "--tray"]
    return [sys.executable, "-m", "printeasy", "--tray"]


def set_enabled(enabled: bool) -> bool:
    try:
        if IS_WINDOWS:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if enabled:
                cmd = " ".join(f'"{c}"' if " " in c else c for c in _launch_command())
                winreg.SetValueEx(key, "PrintEasy", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "PrintEasy")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        elif IS_MAC:
            path = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
            if enabled:
                import plistlib
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    plistlib.dump({"Label": LABEL, "ProgramArguments": _launch_command(),
                                   "RunAtLoad": True, "KeepAlive": False}, fh)
            elif os.path.exists(path):
                os.remove(path)
        else:
            path = os.path.expanduser("~/.config/autostart/printeasy.desktop")
            if enabled:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                cmd = " ".join(f'"{c}"' if " " in c else c for c in _launch_command())
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("[Desktop Entry]\nType=Application\nName=PrintEasy\n"
                             f"Exec={cmd}\nIcon=printeasy\nX-GNOME-Autostart-enabled=true\n")
            elif os.path.exists(path):
                os.remove(path)
        return True
    except OSError:
        return False
