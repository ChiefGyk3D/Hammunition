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

:func:`register_brouter` (D-063) points QMapShack's local BRouter at
Hammunition's: the group is ``Route/brouter`` (``brouter\\<key>`` under
``[Route]``), keys read from QMapShack 1.17.1's source
(``CRouterBRouterSetup.cpp`` at tag ``V_1.17.1``). QMapShack's ``save()``
writes every one of them on exit, so an absent key cannot be told from one at
its default; a ``localDir`` that is absent, QMapShack's default ``.``, or
already ours means no other local BRouter was set up, and then every key it
needs is set to ours. Any other ``localDir`` is the operator's own BRouter and
nothing is touched. When the tree is ours, ``localHost`` and
``localBindLocalonly`` are loopback whatever they held: QMapShack passes the
host to BRouter only with "bind to hostname only" on, and BRouter otherwise
listens on every interface. ``localJava`` is set only when absent or empty
(a QMapShack run before Java was installed saves it empty, and BRouter then
reads as not installed for good). A quoted or ``@``-typed value in one of
these keys is not ours and leaves BRouter alone, never refusing the launch.
``Route/current``, which router the Routing dock shows, is the operator's.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "BRouterSetup",
    "QmsConfigError",
    "Wanted",
    "config_path",
    "ensure_paths",
    "register_brouter",
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
        # D-068: the US Topo mosaic, one ustopo.vrt, beside the Garmin maps.
        Wanted("Canvas", "mapPath", (*_map_paths(data), str(data / "ustopo-qmapshack"))),
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
            if not raw:
                # Emptied by a removal above, which is how the area switch swaps one
                # directory for another under the same key (D-082).
                lines[at] = f"{want.key}={', '.join(want.paths)}\n"
                changed = True
                continue
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


#: QMapShack 1.17.1's group for its BRouter settings, as a ``[Route]`` key prefix.
BROUTER = "brouter\\"
#: QMapShack 1.17.1's own defaults (``CRouterBRouterSetup.h``) for the keys
#: this sets; a key at its default was never chosen by the operator.
BROUTER_DEFAULTS = {
    "installMode": "online",
    "localDir": ".",
    "localBRouterJar": "brouter.jar",
    "localSegmentsDir": "segments4",
    "localHost": "127.0.0.1",
    "localBindLocalonly": "true",
}
LOOPBACK = "127.0.0.1"
#: Characters Qt quotes or escapes in an INI string; a path holding one is not
#: written, rather than written in a form Qt would read back differently.
_QT_SPECIAL = frozenset(',;="\\#\n\r\t')


@dataclass(frozen=True)
class BRouterSetup:
    """Hammunition's BRouter as QMapShack is to run it."""

    tree: Path
    """BRouter's installed tree: ``localDir``, holding the jar and ``profiles2``."""
    jar: str
    """The jar's file name in the tree."""
    segments: Path
    """The routing files' directory."""
    java: str | None
    """``java`` on the PATH, or None."""

    def values(self) -> dict[str, str]:
        return {
            "installMode": "local",
            "localDir": str(self.tree),
            "localBRouterJar": self.jar,
            "localSegmentsDir": str(self.segments),
            "localHost": LOOPBACK,
            "localBindLocalonly": "true",
        }


def _plain(value: str) -> bool:
    return (
        value.isascii()
        and value == value.strip()
        and not value.startswith("@")
        and not any(c in _QT_SPECIAL for c in value)
    )


def register_brouter(text: str, setup: BRouterSetup) -> tuple[str, list[str]]:
    """*text* with QMapShack's local BRouter pointed at *setup*, and what was
    done, one line each; *text* itself and a line saying why when it is the
    operator's own BRouter or a value is not one this edits."""
    ours = setup.values()
    for value in (*ours.values(), setup.java or ""):
        if value and not _plain(value):
            return text, [f"BRouter not registered: {value!r} cannot be written as a Qt value"]
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    headers, keys = _scan(lines)
    current: dict[str, str | None] = {}
    for name in (*ours, "localJava"):
        at = keys.get(("Route", BROUTER + name))
        current[name] = None if at is None else lines[at].split("=", 1)[1].strip()
    for name, held in current.items():
        if held and not _plain(held):
            return text, [
                f"BRouter not registered: [Route] {BROUTER}{name} holds {held[:60]!r}, "
                f"a value this launcher does not edit; QMapShack's BRouter setup is left "
                f"as it is"
            ]
    directory = current["localDir"]
    if directory not in (None, "", BROUTER_DEFAULTS["localDir"], ours["localDir"]):
        return text, [
            f"QMapShack's BRouter is set up for {directory}, not Hammunition's; left as it "
            f"is. Set its directory to {setup.tree} in QMapShack's BRouter setup to use "
            f"the routing files built from your regions"
        ]
    wanted = dict(ours)
    if not current["localJava"] and setup.java:
        wanted["localJava"] = setup.java
    notes: list[str] = []
    if current["installMode"] == "online":
        notes.append("QMapShack's BRouter switched from online to local")
    if current["localHost"] not in (None, LOOPBACK) or current["localBindLocalonly"] not in (
        None,
        "true",
    ):
        notes.append("QMapShack's BRouter bound to 127.0.0.1 only")
    inserts: list[str] = []
    changed = False
    for name, value in wanted.items():
        at = keys.get(("Route", BROUTER + name))
        if at is None:
            inserts.append(f"{BROUTER}{name}={value}\n")
            continue
        raw = lines[at]
        if raw.split("=", 1)[1].strip() == value:
            continue
        lines[at] = f"{BROUTER}{name}={value}" + raw[len(raw.rstrip("\r\n")) :]
        changed = True
    if not (changed or inserts):
        return text, []
    if inserts:
        if "Route" in headers:
            end = _section_end(lines, headers["Route"])
            lines[end:end] = inserts
        else:
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.extend(["[Route]\n", *inserts])
    if not current["localJava"] and not setup.java:
        notes.append("java was not found on the PATH; QMapShack will say BRouter is not installed")
    return "".join(lines), [
        f"registering Hammunition's BRouter for QMapShack (local, 127.0.0.1 only, "
        f"routing files in {setup.segments}); pick BRouter in the Routing dock to use it",
        *notes,
    ]


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
