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

The key names were read from QMapShack 1.17.1's own binary on 2026-09-28,
and their group measured on the bench on 2026-09-29: QMapShack keeps the
map and DEM lists under ``[Canvas]`` (``mapPath``, ``demPaths``; on exit it
wrote ``@Invalid()`` there and ignored the same keys under ``[General]``,
where this launcher had first put them), and the Routino list under
``[Route]`` (``Route/routino/paths``, ``routino\\paths`` in the file), which
it kept. The map file filter is
``*.vrt|*.jnx|*.img|*.rmap|*.wmts|*.tms|*.gemf`` and the DEM filter
``*.vrt|*.wcs``. A list value is Qt's comma-separated form.

:func:`superseded` names where an earlier launcher wrote the two lists.
Given as ``remove=``, our own directories are taken out of those
``[General]`` keys, and a key left holding nothing is removed; any other
value in them, and every other key, stays. A ``[General]`` key this cannot
read is not ours and is left alone, never refused.

A file it cannot read as that shape -- a line that is neither a section, a
comment nor ``key=value``, or one of our keys holding a quoted or ``@``-typed
value -- is refused by name and left untouched, rather than rewritten on a
guess. The one ``@`` value read is ``@Invalid()``, which is how Qt writes an
empty list: a QMapShack run once with no maps holds it in every key edited
here, so it reads as the empty list and our paths replace it.

:func:`select_database` sets ``[Route] routino\\database`` to ``0`` when it
is absent or negative. Measured on the bench on 2026-09-29, and in QMapShack
1.17.1's source (``CRouterRoutino``): at startup it scans every
``routino\\paths`` directory for ``*-segments.mem``, loads what it finds
into the Routing dock's Database dropdown, and then selects the entry at the
index ``routino\\database`` holds. The operator's file held ``-1``: the
``hammunition`` database was loaded (its four ``.mem`` files were mapped in
the process) and the dropdown showed nothing selected, so ``calcRoute()``
found no database and gave up without a word. QMapShack writes the index
back on exit, so a ``-1`` left by any run that exited with an empty
dropdown -- one before the paths were set, say -- persists from then on.
Index 0 is the first database found, and ``routino\\paths`` holds one of
ours. A value of 0 or more is the operator's choice in QMapShack and stays;
one that is not a number stays too, since Qt reads it as 0 anyway. Like
every key here, it is written before QMapShack starts: a running QMapShack
overwrites the file when it exits.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "QmsConfigError",
    "Wanted",
    "config_path",
    "ensure_paths",
    "select_database",
    "superseded",
    "wanted",
]

#: Where QMapShack 1.17.1 keeps the Routing dock's Database index.
DATABASE_SECTION = "Route"
DATABASE_KEY = "routino\\database"


#: How Qt writes an empty QStringList (``iniEscapedStringList``; measured with
#: PyQt6's QSettings(IniFormat) on 2026-09-28). Every other ``@``-typed value
#: (``@Variant(...)``, ``@ByteArray(...)``) is still refused by key.
QT_EMPTY_LIST = "@Invalid()"


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
        Wanted("Canvas", "mapPath", _map_paths(data)),
        Wanted("Canvas", "demPaths", _dem_paths(data)),
        Wanted("Route", "routino\\paths", (str(data / "osm-routino"),)),
    )


def superseded(data: Path) -> tuple[Wanted, ...]:
    """Where the launcher wrote the map and DEM lists before 2026-09-29.

    QMapShack ignores them there; :func:`ensure_paths` takes them out when
    these are passed as ``remove=``.
    """
    return (
        Wanted("General", "mapPath", _map_paths(data)),
        Wanted("General", "demPaths", _dem_paths(data)),
    )


def _map_paths(data: Path) -> tuple[str, ...]:
    return (str(data / "osm-garmin"), str(data / "dem-qmapshack" / "contours"))


def _dem_paths(data: Path) -> tuple[str, ...]:
    return (str(data / "dem-qmapshack" / "dem"),)


def config_path(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    base = environ.get("XDG_CONFIG_HOME") or str((home or Path.home()) / ".config")
    return Path(base) / "QLandkarte" / "QMapShack.conf"


def _items(value: str, section: str, key: str) -> list[str]:
    stripped = value.strip()
    if stripped == QT_EMPTY_LIST:
        return []
    if stripped.startswith("@") or '"' in stripped:
        raise QmsConfigError(
            f"[{section}] {key} holds {stripped[:80]!r}, a value this launcher does not "
            f"edit; add the paths by hand in QMapShack's setup"
        )
    return [item.strip() for item in stripped.split(",") if item.strip()]


def ensure_paths(text: str, wants: Sequence[Wanted], *, remove: Sequence[Wanted] = ()) -> str:
    """*text* with every wanted path present under its key, and every path in
    *remove* taken out of its key; nothing else changed."""
    for want in wants:
        for path in want.paths:
            if "," in path or '"' in path or path.startswith("@") or "\n" in path:
                raise QmsConfigError(f"{path!r} cannot be written as a Qt list entry")
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"  # only kept if something is added after it
    headers, keys = _scan(lines)
    appended: dict[str, list[str]] = {}
    inserts: dict[int, list[str]] = {}
    changed = False
    for gone in remove:
        at = keys.get((gone.section, gone.key))
        if at is None:
            continue
        raw = lines[at]
        try:
            items = _items(raw.split("=", 1)[1], gone.section, gone.key)
        except QmsConfigError:
            continue  # not a value we wrote; left as it is
        kept = [item for item in items if item not in gone.paths]
        if len(kept) == len(items):
            continue
        ending = raw[len(raw.rstrip("\r\n")) :]
        lines[at] = f"{gone.key}={', '.join(kept)}{ending}" if kept else ""
        changed = True
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


def select_database(text: str) -> str:
    """*text* with ``[Route] routino\\database`` at 0 where it is absent or
    negative; nothing else changed, and *text* itself when nothing is."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"  # only kept if something is added after it
    headers, keys = _scan(lines)
    entry = f"{DATABASE_KEY}=0"
    at = keys.get((DATABASE_SECTION, DATABASE_KEY))
    if at is not None:
        raw = lines[at]
        try:
            index = int(raw.split("=", 1)[1].strip())
        except ValueError:
            return text  # Qt reads it as 0; not ours to rewrite
        if index >= 0:
            return text
        lines[at] = entry + raw[len(raw.rstrip("\r\n")) :]
        if not text.endswith("\n"):
            lines[-1] = lines[-1][:-1]  # a line changed in place: none added
    elif DATABASE_SECTION in headers:
        lines.insert(_section_end(lines, headers[DATABASE_SECTION]), entry + "\n")
    else:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.extend([f"[{DATABASE_SECTION}]\n", entry + "\n"])
    return "".join(lines)


def _scan(lines: Sequence[str]) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    """Each section's header line and each ``(section, key)``'s line, or
    :class:`QmsConfigError` for a line that is neither."""
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
    return headers, keys


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
