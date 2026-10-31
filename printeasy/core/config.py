"""Saved settings: network mode, app-to-printer rules, known networks."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field

from .util import config_dir

_LOCK = threading.Lock()


@dataclass
class AppRule:
    app_name: str            # what the person sees, e.g. "Microsoft Word"
    match: str               # process / executable name used to recognise it, e.g. "winword.exe"
    printer: str             # installed printer name to use while this app is in front


@dataclass
class Settings:
    # "auto" = follow what the operating system says, or "private" / "public"
    network_mode: str = "auto"
    # Remember the mode chosen for each network (key = network name / gateway)
    network_modes: dict = field(default_factory=dict)
    app_rules: list = field(default_factory=list)          # list[dict] of AppRule
    rules_enabled: bool = True
    start_at_login: bool = False
    first_run_done: bool = False

    # --- helpers ---------------------------------------------------------
    def rules(self) -> list[AppRule]:
        out = []
        for r in self.app_rules:
            try:
                out.append(AppRule(**r))
            except TypeError:
                continue
        return out

    def set_rules(self, rules: list[AppRule]) -> None:
        self.app_rules = [asdict(r) for r in rules]


def _path() -> str:
    return os.path.join(config_dir(), "settings.json")


def load() -> Settings:
    with _LOCK:
        try:
            with open(_path(), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            known = {k: v for k, v in data.items() if k in Settings.__dataclass_fields__}
            return Settings(**known)
        except (OSError, ValueError, TypeError):
            return Settings()


def save(settings: Settings) -> None:
    with _LOCK:
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(settings), fh, indent=2)
        os.replace(tmp, _path())
