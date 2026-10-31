"""Small helpers shared by every part of PrintEasy."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass

SYSTEM = platform.system()          # "Windows", "Darwin" or "Linux"
IS_WINDOWS = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"

# Hide the black console window that would otherwise flash on Windows.
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


@dataclass
class CmdResult:
    ok: bool
    out: str
    err: str
    code: int


def run(cmd: list[str], timeout: float = 30, input_text: str | None = None,
        english: bool = False) -> CmdResult:
    """Run a command and never raise; always return a CmdResult.

    english=True forces English output so we can read it reliably (CUPS tools are translated).
    """
    env = None
    if english:
        env = dict(os.environ, LC_ALL="C", LANG="C")
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
            creationflags=_NO_WINDOW,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        return CmdResult(p.returncode == 0, p.stdout or "", p.stderr or "", p.returncode)
    except FileNotFoundError:
        return CmdResult(False, "", f"'{cmd[0]}' is not installed on this computer.", 127)
    except subprocess.TimeoutExpired:
        return CmdResult(False, "", "This took too long and was stopped.", 124)
    except Exception as exc:  # pragma: no cover - defensive
        return CmdResult(False, "", str(exc), 1)


def powershell(script: str, timeout: float = 60) -> CmdResult:
    """Run a PowerShell snippet (Windows only)."""
    return run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
        timeout=timeout,
    )


def windows_is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def powershell_admin(script: str, timeout: float = 180) -> CmdResult:
    """Run PowerShell with administrator rights (shows the normal Windows "Yes/No" box once).

    The script runs in a separate elevated window, so its output is passed back through a file.
    """
    if windows_is_admin():
        return powershell(script, timeout)
    import tempfile
    import uuid
    tmpdir = tempfile.gettempdir()
    tag = uuid.uuid4().hex
    script_path = os.path.join(tmpdir, f"printeasy_{tag}.ps1")
    out_path = os.path.join(tmpdir, f"printeasy_{tag}.out")
    wrapped = (
        "$ErrorActionPreference='Stop'\n"
        "try {\n" + script + "\n"
        f"  'PRINTEASY_OK' | Out-File -FilePath {ps_quote(out_path)} -Encoding utf8 -Append\n"
        "} catch {\n"
        f"  ('PRINTEASY_ERR ' + $_.Exception.Message) | Out-File -FilePath {ps_quote(out_path)} -Encoding utf8 -Append\n"
        "}\n"
    )
    with open(script_path, "w", encoding="utf-8-sig") as fh:
        fh.write(wrapped)
    launcher = (
        "try { Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
        f"'-NoProfile','-ExecutionPolicy','Bypass','-File',{ps_quote(script_path)} }} "
        "catch { Write-Error 'cancelled'; exit 1 }"
    )
    r = powershell(launcher, timeout)
    text = ""
    try:
        with open(out_path, "r", encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError:
        pass
    for p in (script_path, out_path):
        try:
            os.remove(p)
        except OSError:
            pass
    if not r.ok and not text:
        return CmdResult(False, "", "You closed the permission box, so nothing was changed.", 1)
    if "PRINTEASY_OK" in text:
        return CmdResult(True, text.replace("PRINTEASY_OK", "").strip(), "", 0)
    err = text.split("PRINTEASY_ERR", 1)[-1].strip() if "PRINTEASY_ERR" in text else r.err
    return CmdResult(False, "", err or "Windows didn't finish the change.", 1)


def ps_quote(value: str) -> str:
    """Quote a value for safe use inside a PowerShell single-quoted string."""
    return "'" + value.replace("'", "''") + "'"


def which(name: str) -> bool:
    return shutil.which(name) is not None


def run_as_admin(cmd: list[str], reason: str = "PrintEasy needs permission to change printer settings.",
                 timeout: float = 120) -> CmdResult:
    """Run a command with administrator rights, showing the normal OS password prompt.

    Windows: the installed app already runs elevated when needed (UAC), so run directly.
    macOS:  osascript "with administrator privileges" shows the standard password box.
    Linux:  pkexec shows the desktop password box; falls back to a direct run.
    """
    if IS_WINDOWS:
        raise ValueError("On Windows use powershell_admin()")
    if IS_MAC:
        import shlex
        shell_cmd = " ".join(shlex.quote(c) for c in cmd)
        script = (f'do shell script {applescript_quote(shell_cmd)} '
                  f'with prompt {applescript_quote(reason)} with administrator privileges')
        return run(["osascript", "-e", script], timeout=timeout)
    # Linux: try without elevation first (users in the lpadmin group can manage printers)
    first = run(cmd, timeout=timeout)
    if first.ok or not which("pkexec"):
        return first
    return run(["pkexec"] + cmd, timeout=timeout)


def applescript_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def config_dir() -> str:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    path = os.path.join(base, "PrintEasy")
    os.makedirs(path, exist_ok=True)
    return path


def resource_path(*parts: str) -> str:
    """Find bundled files both when running from source and from a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def friendly_error(err: str) -> str:
    """Turn raw tool output into something a non-technical person can read."""
    e = (err or "").strip()
    low = e.lower()
    if not e:
        return "Something went wrong, but the computer didn't say what."
    if "access is denied" in low or "not permitted" in low or "forbidden" in low or "permission" in low:
        return "The computer didn't allow this. Please try again and say Yes to the permission box."
    if "user canceled" in low or "cancelled" in low or "(-128)" in low or "dismissed" in low:
        return "You closed the permission box, so nothing was changed."
    if "not installed" in low:
        return e
    first_line = e.splitlines()[0]
    return first_line[:240]
