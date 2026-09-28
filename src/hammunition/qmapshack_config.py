# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""QMapShack's per-user configuration, told where Hammunition's maps are.  D-061.

QMapShack keeps its settings in ``$XDG_CONFIG_HOME/QLandkarte/QMapShack.conf``,
a Qt INI file, and finds maps, elevation and Routino databases only in the
directories listed there. The ``qmapshack-offline`` launcher runs
:func:`ensure_paths` before starting it: each of our directories is added to
its key if absent; a value already there is kept, in its place; nothing
else in the file is touched, byte for byte. Per-user and unprivileged, like
the menu files (D-050).

The keys were read from QMapShack 1.17.1's own binary on 2026-09-28: the
map and DEM lists are top-level settings (``mapPath``, ``demPaths``, which
Qt writes under ``[General]``; the binary has no ``Canvas`` group string),
the Routino list is ``Route/routino/paths`` (``[Route]`` ``routino\\paths``);
the map file filter is ``*.vrt|*.jnx|*.img|*.rmap|*.wmts|*.tms|*.gemf`` and
the DEM filter ``*.vrt|*.wcs``. A list value is Qt's comma-separated form.

A file it cannot read as that shape -- a line that is neither a section, a
comment nor ``key=value``, or one of our keys holding a quoted or ``@``-typed
value -- is refused by name and left untouched, rather than rewritten on a
guess.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["QmsConfigError", "Wanted", "config_path", "ensure_paths", "wanted"]


class QmsConfigError(Exception):
    """The configuration is not a shape this edits safely."""


@dataclass(frozen=True)
class Wanted:
    section: str
    key: str
    paths: tuple[str, ...]


def wanted(data: Path) -> tuple[Wanted, ...]:
    """The directories under *data* (``<prefix>/share/hammunition/data``)."""
    return (
        Wanted(
            "General",
            "mapPath",
            (str(data / "osm-garmin"), str(data / "dem-qmapshack" / "contours")),
        ),
        Wanted("General", "demPaths", (str(data / "dem-qmapshack" / "dem"),)),
        Wanted("Route", "routino\\paths", (str(data / "osm-routino"),)),
    )


def config_path(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    base = environ.get("XDG_CONFIG_HOME") or str((home or Path.home()) / ".config")
    return Path(base) / "QLandkarte" / "QMapShack.conf"


def _items(value: str, section: str, key: str) -> list[str]:
    stripped = value.strip()
    if stripped.startswith("@") or '"' in stripped:
        raise QmsConfigError(
            f"[{section}] {key} holds {stripped[:80]!r}, a value this launcher does not "
            f"edit; add the paths by hand in QMapShack's setup"
        )
    return [item.strip() for item in stripped.split(",") if item.strip()]


def ensure_paths(text: str, wants: Sequence[Wanted]) -> str:
    """*text* with every wanted path present under its key; nothing else changed."""
    for want in wants:
        for path in want.paths:
            if "," in path or '"' in path or path.startswith("@") or "\n" in path:
                raise QmsConfigError(f"{path!r} cannot be written as a Qt list entry")
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"  # only kept if something is added after it
    section = "General"
    headers: dict[str, int] = {}
    keys: dict[tuple[str, str], int] = {}
    for number, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped[0] in ";#":
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            headers[section] = number
            continue
        if "=" not in stripped:
            raise QmsConfigError(
                f"line {number + 1} is neither a [section] nor key=value: {stripped[:80]!r}"
            )
        keys[(section, stripped.split("=", 1)[0].strip())] = number
    appended: dict[str, list[str]] = {}
    inserts: dict[int, list[str]] = {}
    changed = False
    for want in wants:
        at = keys.get((want.section, want.key))
        if at is not None:
            raw = lines[at]
            value = raw.split("=", 1)[1]
            items = _items(value, want.section, want.key)
            missing = [p for p in want.paths if p not in items]
            if missing:
                ending = raw[len(raw.rstrip("\r\n")) :]
                lines[at] = f"{want.key}={', '.join([*items, *missing])}{ending}"
                changed = True
            continue
        entry = f"{want.key}={', '.join(want.paths)}\n"
        if want.section in headers:
            end = _section_end(lines, headers[want.section])
            inserts.setdefault(end, []).append(entry)
        else:
            appended.setdefault(want.section, []).append(entry)
    for index in sorted(inserts, reverse=True):
        lines[index:index] = inserts[index]
    for name, entries in appended.items():
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(f"[{name}]\n")
        lines.extend(entries)
    if not (changed or inserts or appended):
        return text
    return "".join(lines)


def _section_end(lines: Sequence[str], header: int) -> int:
    """The index just after the last non-blank line of the section at *header*."""
    end = header + 1
    for index in range(header + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        if stripped:
            end = index + 1
    return end
