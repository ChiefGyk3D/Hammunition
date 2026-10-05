# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The console's own configuration. It holds the last screen, the colour theme and
whether the first-run checklist was dismissed, and nothing else: never a station
value (the engine's station config is where those live)."""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR_NAME = "hammunition-console"
SCREENS = ("home", "install", "station", "secrets", "logs", "update", "help")
THEMES = ("dark", "light")


@dataclass
class Config:
    last_screen: str = "home"
    theme: str = "dark"
    walkthrough_dismissed: bool = False


def config_dir(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME") or Path.home()) / ".config")
    return Path(base) / CONFIG_DIR_NAME


def config_path(environ: Mapping[str, str] | None = None) -> Path:
    return config_dir(environ) / "config.toml"


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return Config()
    cfg = Config()
    screen, theme, dismissed = (
        data.get(k) for k in ("last_screen", "theme", "walkthrough_dismissed")
    )
    if isinstance(screen, str) and screen in SCREENS:
        cfg.last_screen = screen
    if isinstance(theme, str) and theme in THEMES:
        cfg.theme = theme
    if isinstance(dismissed, bool):
        cfg.walkthrough_dismissed = dismissed
    return cfg


def _dump(cfg: Config) -> str:
    return (
        f"last_screen = {json.dumps(cfg.last_screen)}\n"
        f"theme = {json.dumps(cfg.theme)}\n"
        f"walkthrough_dismissed = {'true' if cfg.walkthrough_dismissed else 'false'}\n"
    )


def save(cfg: Config, path: Path | None = None) -> bool:
    """Write atomically, 0600 in a 0700 directory. False when it could not (never raises)."""
    path = path or config_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_dump(cfg))
        os.replace(tmp, path)
    except OSError:
        return False
    return True
