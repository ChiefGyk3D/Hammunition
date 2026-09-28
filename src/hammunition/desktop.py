# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which desktops a machine has, and which one the caller is in.  D-060.

**Installed** desktops are read from the session files every display manager
lists, ``/usr/share/xsessions/*.desktop`` and
``/usr/share/wayland-sessions/*.desktop``. They are files on disk, so they
answer the same under ``sudo`` as outside it, which ``XDG_CURRENT_DESKTOP``
does not: sudo resets the environment, and the variable is gone. The planner
reads only these (and only through an argument, so tests and containers are
deterministic).

Each file's ``DesktopNames=`` key is read first -- ``;``-separated, as in the
desktop-entry spec (``GNOME;GNOME-Classic``). Two packages were measured
shipping session files without the key (Debian 13, 2026-09-28):
``openbox-lxde-session`` (``LXDE.desktop``) and ``cinnamon-common``
(``cinnamon.desktop``, ``cinnamon2d.desktop``, ``cinnamon-wayland.desktop``).
Those stems, and only those, fall back to a table; any other file without the
key (``lightdm-xsession``, ``openbox``) is not a desktop this module names and
is ignored rather than guessed at.

The **current** desktop, from ``XDG_CURRENT_DESKTOP``, is for callers where
the session matters -- menus and ``doctor`` -- never for the plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

__all__ = [
    "SESSION_DIRS",
    "Desktop",
    "current_desktop",
    "describe",
    "describe_set",
    "installed_desktops",
]


class Desktop(StrEnum):
    """The desktops a manifest's ``desktops`` field may name."""

    kde = "kde"
    gnome = "gnome"
    xfce = "xfce"
    lxqt = "lxqt"
    lxde = "lxde"
    mate = "mate"
    cinnamon = "cinnamon"


# Session directories, relative to the root the caller passes.
SESSION_DIRS: Final = ("usr/share/xsessions", "usr/share/wayland-sessions")

# `DesktopNames` / `XDG_CURRENT_DESKTOP` element, lower-cased -> Desktop.
_BY_NAME: Final = MappingProxyType(
    {
        "kde": Desktop.kde,
        "gnome": Desktop.gnome,
        "xfce": Desktop.xfce,
        "lxqt": Desktop.lxqt,
        "lxde": Desktop.lxde,
        "mate": Desktop.mate,
        "x-cinnamon": Desktop.cinnamon,
        "cinnamon": Desktop.cinnamon,
    }
)

# Session-file stems measured shipping no `DesktopNames` (Debian 13,
# 2026-09-28). Exact and case-sensitive: this is a record of what two
# packages ship, not a pattern.
_BY_STEM: Final = MappingProxyType(
    {
        "LXDE": Desktop.lxde,
        "cinnamon": Desktop.cinnamon,
        "cinnamon2d": Desktop.cinnamon,
        "cinnamon-wayland": Desktop.cinnamon,
    }
)

_DISPLAY: Final = MappingProxyType(
    {
        Desktop.kde: "KDE Plasma",
        Desktop.gnome: "GNOME",
        Desktop.xfce: "Xfce",
        Desktop.lxqt: "LXQt",
        Desktop.lxde: "LXDE",
        Desktop.mate: "MATE",
        Desktop.cinnamon: "Cinnamon",
    }
)


def describe(desktop: Desktop) -> str:
    """The name people use for it: ``KDE Plasma``, ``Xfce``, ``LXQt``."""
    return _DISPLAY[desktop]


def describe_set(desktops: frozenset[Desktop] | set[Desktop]) -> str:
    """Several desktops in enum order, joined for a sentence; ``none`` when empty."""
    if not desktops:
        return "none"
    return ", ".join(describe(d) for d in Desktop if d in desktops)


def _desktop_names(text: str) -> list[str] | None:
    """The ``DesktopNames`` elements of the ``[Desktop Entry]`` group, or None
    when the group does not carry the key."""
    group = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
            continue
        if group != "Desktop Entry" or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "DesktopNames":
            return [v.strip() for v in value.split(";") if v.strip()]
    return None


def _from_file(path: Path) -> set[Desktop]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # Unreadable is not a desktop we can name. The effect is visible: a
        # unit for that desktop is deferred by name, never installed blind.
        return set()
    names = _desktop_names(text)
    if names is None:
        stem = _BY_STEM.get(path.stem)
        return {stem} if stem is not None else set()
    return {_BY_NAME[n.lower()] for n in names if n.lower() in _BY_NAME}


def installed_desktops(root: Path = Path("/")) -> frozenset[Desktop]:
    """Every desktop a session file under ``root`` offers.

    An absent directory is not an error: a container or a server has neither,
    and the answer there is the empty set.
    """
    found: set[Desktop] = set()
    for relative in SESSION_DIRS:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.desktop")):
            found |= _from_file(path)
    return frozenset(found)


def current_desktop(environ: Mapping[str, str]) -> Desktop | None:
    """The first recognised element of ``XDG_CURRENT_DESKTOP`` (``:``-separated,
    ``ubuntu:GNOME``), or None when it is unset or names nothing recognised."""
    for element in environ.get("XDG_CURRENT_DESKTOP", "").split(":"):
        desktop = _BY_NAME.get(element.strip().lower())
        if desktop is not None:
            return desktop
    return None
