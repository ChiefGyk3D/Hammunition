# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Repeater overlays from the operator's own export, converted here.  D-064.

The operator exports repeaters from a source they hold an account with
(RepeaterBook's website export, as GPX or CSV), types their own list, or asks
for hearham.com's open list; this reads it and writes three overlays into
``$XDG_DATA_HOME/hammunition/overlays/repeaters/``: a GPX for QMapShack's
File → Load and for phones, a Mapsforge ``.poi`` that QMapShack keeps as a POI
collection, and a Navit textfile map. Nothing here fetches anything, except
:func:`fetch_hearham`, and only when the operator runs
``maps repeaters fetch-hearham``.

Not a D-049 data unit: an export is neither fetched by the engine nor
pinnable, and RepeaterBook's terms forbid anyone else holding it. The files
are the operator's, mode 0600, never under the root prefix and never in the
transaction log.

Inputs are recognised from their content (:func:`read_input`). A CHIRP CSV
and a CHIRP radio image carry no coordinates -- CHIRP's own RepeaterBook
query was measured to drop Lat/Long and keep "near <city>" -- so both are
refused by name, as are a RepeaterBook CSV without Lat and Long, and KML,
which is deferred (the same data as the GPX). Guessing a position from a town
name would invent one.
"""

from __future__ import annotations

import contextlib
import csv
import dataclasses
import hashlib
import http.client
import io
import json
import math
import os
import re
import sqlite3
import stat
import struct
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

__all__ = [
    "ALL_SOURCES",
    "BRANDMEISTER",
    "DIREWOLF",
    "ETCC",
    "FILES",
    "HAND",
    "HAND_HEADER",
    "HEARD_LAYERS",
    "HEARHAM",
    "HEARHAM_URL",
    "LAYERS",
    "OPEN_REPEATER",
    "OSM",
    "REPEATERBOOK_CSV",
    "REPEATERBOOK_GPX",
    "SUFFIXES",
    "AllSources",
    "Layer",
    "ParsedInput",
    "PoiPoint",
    "Repeater",
    "RepeaterFetchError",
    "RepeaterInputError",
    "Skip",
    "all_sources_name",
    "export_date",
    "fetch_hearham",
    "fetch_list",
    "gpx_text",
    "hearham_layer_name",
    "hearham_licence",
    "layer_files",
    "layer_name",
    "licence_text",
    "merge",
    "navit_text",
    "nudge",
    "overlay_dir",
    "overlays_root",
    "parse_exported",
    "present_layers",
    "read_input",
    "read_inputs",
    "read_layer_rows",
    "rebuild_all",
    "remove_layer",
    "write_layer",
    "write_poi",
    "write_poi_points",
]

# The four inputs, by the name the text and the JSON document carry.
REPEATERBOOK_GPX = "repeaterbook-gpx"
REPEATERBOOK_CSV = "repeaterbook-csv"
HEARHAM = "hearham-json"
HAND = "hand-csv"
# D-074's sources, each read into its own layer (``repeater_sources``).
OPEN_REPEATER = "open-repeater-json"
OSM = "osm-extract"
ETCC = "etcc-csv"
BRANDMEISTER = "brandmeister-json"
DIREWOLF = "direwolf-log"

#: The hand-typed CSV's header, exactly (D-064).
HAND_HEADER = (
    "callsign",
    "output_mhz",
    "offset_mhz",
    "tone",
    "mode",
    "lat",
    "lon",
    "name",
    "notes",
)

#: One layer per source (D-074), each under its own stem in the one
#: directory. ``export`` is D-064's layer: ``import FILE...`` and
#: ``fetch-hearham`` write it, under D-064's names.
LAYERS: dict[str, str] = {
    "export": "repeaters",
    "open-repeater": "repeaters-open-repeater",
    "osm": "repeaters-osm",
    "etcc": "repeaters-etcc",
    "brandmeister": "repeaters-brandmeister",
    "aprs-heard": "repeaters-aprs-heard",
}
#: What this station heard is evidence, not a directory: never in the
#: all-sources file.
HEARD_LAYERS = ("aprs-heard",)
#: The suffixes of a layer's files: GPX, POI, Navit textfile, and the rows as
#: data, which is what the all-sources file is rebuilt from.
SUFFIXES = (".gpx", ".poi", ".navit.txt", ".rows.json")
#: The directory layers joined, GPX only (D-074).
ALL_SOURCES = "repeaters-all.gpx"


def layer_files(layer_id: str) -> tuple[str, str, str, str]:
    """The four file names of *layer_id*, in :data:`SUFFIXES` order."""
    try:
        stem = LAYERS[layer_id]
    except KeyError:
        raise ValueError(
            f"no repeater layer {layer_id!r}; the layers are {', '.join(LAYERS)}"
        ) from None
    gpx, poi, navit, rows = (stem + suffix for suffix in SUFFIXES)
    return gpx, poi, navit, rows


#: The files D-064's layer is, in the order they are written and listed.
FILES = layer_files("export")

#: hearham.com's whole-world list: unauthenticated JSON, about 9.5 MB and
#: 22,698 rows on 2026-09-29, no ETag. Tests point this at a loopback server.
HEARHAM_URL = "https://hearham.com/api/repeaters/v1"
#: Bounded, so a misbehaving server cannot be read into memory without limit.
HEARHAM_LIMIT = 64 * 1024 * 1024

#: CHIRP's image metadata marker, from chirp_common.py (chirp 1:20250530).
CHIRP_MAGIC = b"\x00\xffchirp\xeeimg\x00\x01"
CHIRP_CSV_HEAD = ("location", "name", "frequency", "duplex")
#: The first columns of Direwolf's ``-l`` log and of the ETCC CSV, lower-cased
#: (both measured, D-074).
DIREWOLF_HEAD = ("chan", "utime", "isotime")
ETCC_HEAD = ("call", "band", "chan", "txmhz", "rxmhz")

#: A QMapShack built-in waypoint symbol (the SJJB communications tower), so
#: nothing is written into QMapShack's own directories.
GPX_SYMBOL = "Tall Tower"
#: Navit's own tower icon, shipped by the navit package.
NAVIT_ICON = "/usr/share/navit/icons/tower.png"
#: Has a label in the stock layout's "POI Labels" layer; poi_communication has none.
NAVIT_TYPE = "poi_custom0"
POI_CATEGORY = "Amateur radio repeaters"

SOURCE_NAMES = {
    REPEATERBOOK_GPX: "RepeaterBook export. Data courtesy of RepeaterBook.com",
    REPEATERBOOK_CSV: "RepeaterBook export. Data courtesy of RepeaterBook.com",
    HEARHAM: "hearham.com, unverified",
    HAND: "your own list",
    OPEN_REPEATER: "Open Repeater, CC0",
    OSM: "OpenStreetMap contributors, ODbL",
    ETCC: "RSGB ETCC (ukrepeater.net), unverified",
    BRANDMEISTER: "BrandMeister, unverified",
    DIREWOLF: "heard off the air by this station (APRS object)",
}

REPEATERBOOK_TERMS = "repeaterbook.com/about/legal"
REPEATERBOOK_LICENCE = (
    "Data courtesy of RepeaterBook.com. Exported by you for your own personal, "
    "non-commercial use under RepeaterBook's export terms "
    "(repeaterbook.com/wiki/doku.php?id=exports): the data may not be redistributed "
    "in any form. Hammunition converts it on this machine only and never uploads, "
    "shares or bundles it; the overlay files are yours under the same terms. "
    "Positions are approximate: do not use them to visit a repeater site. "
    f"RepeaterBook's terms: {REPEATERBOOK_TERMS}"
)
HAND_LICENCE = "Your own data. Hammunition adds nothing to it and sends it nowhere."


def hearham_licence(when: str, sha256: str) -> str:
    """hearham's disclosure. *when* is ``Fetched <time>`` or ``Read from <file>``."""
    return (
        "hearham.com states no licence for this data (its terms page is a service "
        "agreement; the Repeater-START app's GPL covers code, not data). Carried under "
        "D-033: used on your request, never redistributed. hearham: 'Under no "
        "circumstances should this be relied upon for medical emergencies, or any "
        f"other life-and-death operations.' {when}, sha256 {sha256}, not verifiable."
    )


def licence_text(fmt: str) -> str:
    """The text printed at import for an export or a hand list."""
    if fmt in (REPEATERBOOK_GPX, REPEATERBOOK_CSV):
        return REPEATERBOOK_LICENCE
    if fmt == HAND:
        return HAND_LICENCE
    raise ValueError(f"{fmt}: use hearham_licence(), which needs the observed digest")


class RepeaterInputError(Exception):
    """An input this does not read, named with the reason."""


class RepeaterFetchError(Exception):
    """hearham's list could not be fetched, or was not what it serves."""


@dataclass(frozen=True)
class Repeater:
    """One repeater, as read. ``output_hz`` 0 and ``callsign`` empty only for
    a GPX waypoint whose name gave neither; ``label`` is then its name."""

    callsign: str
    output_hz: int
    lat: float
    lon: float
    source: str
    offset_hz: int | None = None
    tone: str = ""
    mode: str = ""
    place: str = ""
    notes: str = ""
    use: str = ""
    status: str = ""
    updated: str = ""
    label: str = ""
    #: Other sources that list the same machine, best first: set only in the
    #: all-sources file (D-074), where rows from several layers are joined.
    also: tuple[str, ...] = ()

    def label_text(self) -> str:
        """``N0CALL 146.940``: what the map draws beside the icon."""
        if self.callsign and self.output_hz:
            return f"{self.callsign} {format_mhz(self.output_hz)}"
        return self.label or self.callsign

    def key(self) -> tuple[str, int, float, float]:
        """Callsign + output Hz + position to 0.01° (about 1 km). D-064."""
        who = self.callsign or self.label.strip().upper()
        return (who, self.output_hz, round(self.lat, 2) + 0.0, round(self.lon, 2) + 0.0)

    def description(self) -> str:
        """The waypoint's ``<desc>``: offset, tone, mode, use, status, place,
        notes, then the source."""
        parts: list[str] = []
        if self.output_hz:
            parts.append(f"{format_mhz(self.output_hz)} MHz")
        if self.offset_hz is not None:
            parts.append(f"offset {self.offset_hz / 1e6:+.3f} MHz")
        parts.append(f"tone {self.tone}" if self.tone else "no tone")
        for value in (self.mode, self.use and f"use {self.use}", self.status, self.place):
            if value:
                parts.append(value)
        if self.notes:
            parts.append(self.notes)
        parts.append(f"Source: {SOURCE_NAMES[self.source]}")
        if self.also:
            parts.append("also listed by " + ", ".join(SOURCE_NAMES[s] for s in self.also))
        return "; ".join(parts)


def format_mhz(hz: int) -> str:
    """Three decimals at least, more only when the frequency needs them."""
    whole, _, frac = f"{hz / 1e6:.6f}".partition(".")
    frac = frac.rstrip("0").ljust(3, "0")
    return f"{whole}.{frac}"


@dataclass(frozen=True)
class Skip:
    """Rows of one input left out for one reason; ``first`` are line (CSV),
    row (JSON) or waypoint (GPX) numbers, the first five."""

    reason: str
    count: int
    first: tuple[int, ...]


@dataclass(frozen=True)
class ParsedInput:
    path: Path
    format: str
    read: int
    rows: tuple[Repeater, ...]
    skipped: tuple[Skip, ...]
    sha256: str
    mtime: float


class _Skips:
    def __init__(self) -> None:
        self._by: dict[str, list[int]] = {}

    def add(self, reason: str, number: int) -> None:
        self._by.setdefault(reason, []).append(number)

    def result(self) -> tuple[Skip, ...]:
        return tuple(Skip(r, len(n), tuple(n[:5])) for r, n in self._by.items())


# --- reading -------------------------------------------------------------------

_CALLSIGN = re.compile(r"\b(?:[A-Z]{1,2}|[0-9][A-Z]|[A-Z][0-9])[0-9][A-Z]{1,4}\b")
_FREQUENCY = re.compile(r"(?<![\d.])(\d{2,4}\.\d{1,6})(?![\d.])")
_NO_TONE = {"", "0", "0.0", "0.00", "none", "csq"}
_NO_POSITION = "no usable position"
_NO_CALLSIGN = "no callsign"
_BAD_FREQUENCY = "no usable output frequency"


def _position(lat: object, lon: object) -> tuple[float, float] | None:
    try:
        la = float(lat)  # type: ignore[arg-type]
        lo = float(lon)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(la) and math.isfinite(lo)):
        return None
    if abs(la) > 90 or abs(lo) > 180 or (la == 0 and lo == 0):
        return None
    return la, lo


def _hz(mhz: object) -> int | None:
    try:
        value = float(str(mhz).strip())
    except ValueError:
        return None
    # 1 to 10,000 MHz: a frequency typed in Hz or kHz is refused, not
    # labelled "146940000.000" (review, 2026-09-29).
    if not math.isfinite(value) or not 1 <= value <= 10_000:
        return None
    return round(value * 1_000_000)


def _offset_hz(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    try:
        return round(float(text) * 1_000_000)
    except ValueError:
        return None


def _clean(text: object) -> str:
    return " ".join(str(text or "").split())


def _tone(encode: str, decode: str = "") -> str:
    enc, dec = _clean(encode), _clean(decode)
    enc = "" if enc.lower() in _NO_TONE else enc
    dec = "" if dec.lower() in _NO_TONE else dec
    if enc and dec and dec != enc:
        return f"{enc} (decode {dec})"
    return enc or (f"decode {dec}" if dec else "")


def read_input(path: Path) -> ParsedInput:
    """*path* read as one of the four inputs, or :class:`RepeaterInputError`."""
    try:
        raw = path.read_bytes()
        mtime = path.stat().st_mtime
    except OSError as exc:
        raise RepeaterInputError(f"{path}: cannot read it: {exc.strerror or exc}") from None
    digest = hashlib.sha256(raw).hexdigest()
    if path.suffix.lower() == ".img" or CHIRP_MAGIC in raw:
        raise RepeaterInputError(
            f"{path}: a CHIRP radio image holds a radio's memories and no coordinates, "
            f"so there is nothing to put on a map. Export GPX from RepeaterBook's site "
            f"instead, or type your own list (docs/guides/offline-navigation.md)"
        )
    if path.suffix.lower() in (".kml", ".kmz"):
        raise _kml(path)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _unknown(path, "it is not UTF-8 text") from None
    head = text.lstrip()
    if head.startswith("<"):
        fmt, read, rows, skips = _read_xml(path, text)
    elif head.startswith(("[", "{")):
        fmt, read, rows, skips = _read_json(path, text)
    else:
        fmt, read, rows, skips = _read_csv(path, text)
    return ParsedInput(
        path=path,
        format=fmt,
        read=read,
        rows=tuple(rows),
        skipped=skips.result(),
        sha256=digest,
        mtime=mtime,
    )


def read_inputs(paths: Sequence[Path]) -> tuple[ParsedInput, ...]:
    """Every input read, or one :class:`RepeaterInputError` naming each refused."""
    parsed: list[ParsedInput] = []
    refused: list[str] = []
    for path in paths:
        try:
            parsed.append(read_input(path))
        except RepeaterInputError as exc:
            refused.append(str(exc))
    if refused:
        raise RepeaterInputError("\n".join(refused))
    return tuple(parsed)


def _kml(path: Path) -> RepeaterInputError:
    return RepeaterInputError(
        f"{path}: KML is not read yet (deferred: it is the same data as RepeaterBook's "
        f"GPX export). Export GPX from the same search instead"
    )


def _unknown(path: Path, why: str) -> RepeaterInputError:
    return RepeaterInputError(
        f"{path}: not an input this reads ({why}). It reads a RepeaterBook GPX export, a "
        f"RepeaterBook CSV export with Lat and Long columns, hearham.com's JSON as served, "
        f"or your own CSV with the header {','.join(HAND_HEADER)}"
    )


Parsed = tuple[str, int, list[Repeater], _Skips]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_xml(path: Path, text: str) -> Parsed:
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise RepeaterInputError(
            f"{path}: XML with a DOCTYPE or ENTITY declaration is refused; no GPX needs one"
        )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise _unknown(path, f"XML that does not parse: {exc}") from None
    name = _local(root.tag)
    if name == "kml":
        raise _kml(path)
    if name != "gpx":
        raise _unknown(path, f"XML whose root is <{name}>")
    rows: list[Repeater] = []
    skips = _Skips()
    read = 0
    for element in root.iter():
        if _local(element.tag) != "wpt":
            continue
        read += 1
        children = {_local(c.tag): _clean(c.text) for c in element}
        where = _position(element.get("lat"), element.get("lon"))
        if where is None:
            skips.add(_NO_POSITION, read)
            continue
        wpt_name = children.get("name", "")
        desc = children.get("desc", "")
        cmt = children.get("cmt", "")
        found_call = _search(_CALLSIGN, wpt_name.upper(), desc.upper())
        found_freq = _gpx_frequency(wpt_name, desc)
        hz = _hz(found_freq) if found_freq else None
        if not (found_call and hz):
            # Kept under its own name, or the callsign found, keyed on that.
            wpt_name = wpt_name or found_call
            found_call, hz = "", 0
        if not wpt_name:
            skips.add(_NO_CALLSIGN, read)
            continue
        notes = "; ".join(x for x in (desc, cmt if cmt != desc else "") if x)
        rows.append(
            Repeater(
                callsign=found_call,
                output_hz=hz or 0,
                lat=where[0],
                lon=where[1],
                source=REPEATERBOOK_GPX,
                notes=notes,
                label=wpt_name,
            )
        )
    return REPEATERBOOK_GPX, read, rows, skips


def _search(pattern: re.Pattern[str], *texts: str) -> str:
    for text in texts:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""


#: Where a repeater's output can be, in MHz: the amateur bands with
#: repeaters (10 m to 23 cm, the widest allocation of any region) and GMRS,
#: which RepeaterBook also lists. A tone (67.0 to 254.1), a DCS code or a
#: coordinate in a GPX ``<desc>`` falls outside them -- except a longitude
#: in 144 to 148 or 420 to 450, which is why a number followed by "MHz" is
#: preferred in ``<desc>`` (review, 2026-09-29).
_REPEATER_BANDS = (
    (28.0, 29.7),
    (50.0, 54.0),
    (70.0, 71.0),
    (144.0, 148.0),
    (219.0, 225.0),
    (420.0, 450.0),
    (462.0, 468.0),
    (902.0, 928.0),
    (1240.0, 1300.0),
)
_MHZ = re.compile(r"(?<![\d.])(\d{2,4}\.\d{1,6})\s*MHz", re.IGNORECASE)


def _in_band(text: str) -> bool:
    value = float(text)
    return any(low <= value <= high for low, high in _REPEATER_BANDS)


def _gpx_frequency(name: str, desc: str) -> str:
    """The output frequency in a waypoint's name, else in its ``<desc>``:
    there, one written with "MHz" first, then any in a repeater band."""
    for pattern, text in ((_FREQUENCY, name), (_MHZ, desc), (_FREQUENCY, desc)):
        for match in pattern.finditer(text):
            if _in_band(match.group(1)):
                return match.group(1)
    return ""


def _read_json(path: Path, text: str) -> Parsed:
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _unknown(path, f"JSON that does not parse: {exc}") from None
    wanted = {"callsign", "frequency", "latitude", "longitude"}

    def entry(item: object) -> bool:
        return isinstance(item, dict) and wanted <= item.keys()

    if isinstance(data, dict) and data.get("source") == "Open Repeater":
        raise RepeaterInputError(
            f"{path}: an Open Repeater file is its own layer (D-074); import it with "
            f"`hammunition maps repeaters import --from-open-repeater {path}`"
        )

    # One odd entry is skipped and counted; a list with no entry of hearham's
    # shape at all is not hearham's list (review, 2026-09-29).
    if not isinstance(data, list) or not any(entry(item) for item in data):
        raise _unknown(path, "JSON that is not hearham's list of repeaters")
    rows: list[Repeater] = []
    skips = _Skips()
    for number, item in enumerate(data, start=1):
        if not entry(item):
            skips.add("not a repeater entry", number)
            continue
        where = _position(item.get("latitude"), item.get("longitude"))
        if where is None:
            skips.add(_NO_POSITION, number)
            continue
        call = _clean(item.get("callsign")).upper()
        if not call:
            skips.add(_NO_CALLSIGN, number)
            continue
        frequency = item.get("frequency")
        if not isinstance(frequency, int) or isinstance(frequency, bool) or frequency <= 0:
            skips.add(_BAD_FREQUENCY, number)
            continue
        offset = item.get("offset")
        operational = item.get("operational")
        rows.append(
            Repeater(
                callsign=call,
                output_hz=frequency,
                lat=where[0],
                lon=where[1],
                source=HEARHAM,
                offset_hz=offset
                if isinstance(offset, int) and not isinstance(offset, bool)
                else None,
                tone=_tone(str(item.get("encode") or ""), str(item.get("decode") or "")),
                mode=_clean(item.get("mode")).upper(),
                place=_clean(item.get("city")),
                notes=_clean(item.get("description"))[:200],
                status=(
                    "operational"
                    if operational == 1
                    else "not operational"
                    if operational == 0
                    else ""
                ),
            )
        )
    return HEARHAM, len(data), rows, skips


def _read_csv(path: Path, text: str) -> Parsed:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        raise _unknown(path, "it is empty") from None
    names = [h.strip().lower() for h in header]
    if tuple(names[:4]) == CHIRP_CSV_HEAD:
        raise RepeaterInputError(
            f"{path}: a CHIRP CSV carries no coordinates: CHIRP's RepeaterBook query keeps "
            f"only 'near <city>' in its Comment column (measured), and a position guessed "
            f"from a town name would be invented. Export GPX from RepeaterBook's site instead"
        )
    if tuple(names) == HAND_HEADER:
        return _read_hand(reader)
    if tuple(names[:3]) == DIREWOLF_HEAD:
        raise RepeaterInputError(
            f"{path}: a Direwolf log is its own layer, what this station heard (D-074); "
            f"import it with `hammunition maps repeaters import --from-direwolf-log {path}`"
        )
    if tuple(names[:5]) == ETCC_HEAD:
        raise RepeaterInputError(
            f"{path}: the RSGB ETCC list is its own layer (D-074); "
            f"`hammunition maps repeaters fetch-etcc` fetches and converts it"
        )
    columns = set(names)
    if {"callsign", "frequency", "lat", "long"} <= columns:
        return _read_repeaterbook(reader, names)
    if {"callsign", "frequency"} <= columns:
        raise RepeaterInputError(
            f"{path}: a RepeaterBook CSV with no Lat and Long columns has nothing to place "
            f"on a map. Export GPX from the same search, which always carries positions"
        )
    raise _unknown(path, f"a CSV whose header is {','.join(header)[:120]!r}")


def _read_hand(reader: Any) -> Parsed:
    rows: list[Repeater] = []
    skips = _Skips()
    read = 0
    for record in reader:
        if not any(cell.strip() for cell in record):
            continue
        read += 1
        line = reader.line_num
        cells = dict(zip(HAND_HEADER, [*record, *[""] * len(HAND_HEADER)], strict=False))
        where = _position(cells["lat"], cells["lon"])
        if where is None:
            skips.add(_NO_POSITION, line)
            continue
        call = _clean(cells["callsign"]).upper()
        if not call:
            skips.add(_NO_CALLSIGN, line)
            continue
        hz = _hz(cells["output_mhz"])
        if hz is None:
            skips.add(_BAD_FREQUENCY, line)
            continue
        rows.append(
            Repeater(
                callsign=call,
                output_hz=hz,
                lat=where[0],
                lon=where[1],
                source=HAND,
                offset_hz=_offset_hz(cells["offset_mhz"]),
                tone=_tone(cells["tone"]),
                mode=_clean(cells["mode"]),
                place=_clean(cells["name"]),
                notes=_clean(cells["notes"]),
            )
        )
    return HAND, read, rows, skips


def _read_repeaterbook(reader: Any, names: list[str]) -> Parsed:
    rows: list[Repeater] = []
    skips = _Skips()
    read = 0
    for record in reader:
        if not any(cell.strip() for cell in record):
            continue
        read += 1
        line = reader.line_num
        cells = {n: v.strip() for n, v in zip(names, record, strict=False)}
        where = _position(cells.get("lat"), cells.get("long"))
        if where is None:
            skips.add(_NO_POSITION, line)
            continue
        call = _clean(cells.get("callsign")).upper()
        if not call:
            skips.add(_NO_CALLSIGN, line)
            continue
        hz = _hz(cells.get("frequency", ""))
        if hz is None:
            skips.add(_BAD_FREQUENCY, line)
            continue
        entry = _hz(cells.get("input freq", ""))
        pl, tsq = cells.get("pl", ""), cells.get("tsq", "")
        tone = _tone(pl)
        if tsq and tsq != pl and tsq.lower() not in _NO_TONE:
            tone = f"{tone} (TSQ {tsq})" if tone else f"TSQ {tsq}"
        place = ", ".join(x for x in (cells.get("nearest city"), cells.get("landmark")) if x)
        rows.append(
            Repeater(
                callsign=call,
                output_hz=hz,
                lat=where[0],
                lon=where[1],
                source=REPEATERBOOK_CSV,
                offset_hz=None if entry is None else entry - hz,
                tone=tone,
                place=place,
                use=cells.get("use", ""),
                status=cells.get("operational status", ""),
                updated=cells.get("last update", ""),
            )
        )
    return REPEATERBOOK_CSV, read, rows, skips


# --- merging and naming ------------------------------------------------------------


def _updated(value: str) -> datetime | None:
    """*value* as a naive UTC time to compare by: an ISO date with or without
    a time (Direwolf's ``isotime``, Brandmeister's ``last_seen``), or a
    RepeaterBook ``MM/DD/YYYY``."""
    value = value.strip()
    with contextlib.suppress(ValueError):
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return when.astimezone(UTC).replace(tzinfo=None) if when.tzinfo else when
    with contextlib.suppress(ValueError):
        day = date.fromisoformat(value[:10])
        return datetime(day.year, day.month, day.day)
    with contextlib.suppress(ValueError):
        return datetime.strptime(value, "%m/%d/%Y")
    return None


def merge(rows: Iterable[Repeater]) -> tuple[tuple[Repeater, ...], int]:
    """One row per key, in first-seen order, and how many were merged away.

    The newer ``Last Update`` wins when both rows carry one; otherwise the
    first read stays."""
    kept: dict[tuple[str, int, float, float], Repeater] = {}
    merged = 0
    for row in rows:
        key = row.key()
        old = kept.get(key)
        if old is None:
            kept[key] = row
            continue
        merged += 1
        new_day, old_day = _updated(row.updated), _updated(old.updated)
        if new_day is not None and old_day is not None and new_day > old_day:
            kept[key] = row
    return tuple(kept.values()), merged


def parse_exported(text: str) -> date:
    """``--exported``'s value, or ValueError naming the form."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"--exported {text!r}: give the date as YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"--exported {text!r}: not a date; give it as YYYY-MM-DD") from None


def export_date(paths: Sequence[Path], override: date | None) -> date:
    """*override*, else the oldest input's modification date (D-031: the
    input's date, never the day of the run)."""
    if override is not None:
        return override
    return min(date.fromtimestamp(p.stat().st_mtime) for p in paths)


def layer_name(day: date) -> str:
    return f"Repeaters (own export {day.isoformat()}, personal use)"


def hearham_layer_name(day: date) -> str:
    return f"Repeaters (hearham {day.isoformat()}, unverified)"


# --- writing ----------------------------------------------------------------------

GPX_NS = "http://www.topografix.com/GPX/1/1"


def gpx_text(layer: str, description: str, rows: Sequence[Repeater]) -> str:
    """GPX 1.1: the layer in ``<metadata>``, one ``<wpt>`` per repeater."""
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<gpx version="1.1" creator="hammunition" xmlns="{GPX_NS}">',
        f"  <metadata><name>{escape(layer)}</name><desc>{escape(description)}</desc></metadata>",
    ]
    for row in rows:
        out.append(
            f'  <wpt lat="{row.lat:.5f}" lon="{row.lon:.5f}">'
            f"<name>{escape(row.label_text())}</name>"
            f"<desc>{escape(row.description())}</desc>"
            f"<src>{escape(SOURCE_NAMES[row.source])}</src>"
            f"<sym>{GPX_SYMBOL}</sym><type>repeater</type></wpt>"
        )
    out.append("</gpx>")
    return "\n".join(out) + "\n"


def _navit_label(text: str) -> str:
    return "".join(ch for ch in text.replace('"', "'") if ch.isprintable())


def navit_text(rows: Sequence[Repeater]) -> str:
    """Navit's textfile map: ``lon lat type=... label="..." icon_src="..."``."""
    return "".join(
        f'{row.lon:.5f} {row.lat:.5f} type={NAVIT_TYPE} label="{_navit_label(row.label_text())}" '
        f'icon_src="{NAVIT_ICON}"\n'
        for row in rows
    )


def _f32(value: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


def _step32(value: float, up: bool) -> float:
    """The float32 next to *value* (itself a float32), upwards or downwards."""
    if value == 0.0:
        tiny = float(struct.unpack("<f", struct.pack("<I", 1))[0])
        return tiny if up else -tiny
    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    bits += 1 if (value > 0) == up else -1
    return float(struct.unpack("<f", struct.pack("<I", bits))[0])


#: SQLite's rtree (``rtreeValueDown``/``rtreeValueUp`` in rtree.c): a value
#: whose float32 lands on the wrong side is scaled by 1 ± 2**-23 and cast
#: again, which can move it more than one float32 step.
_TOWARDS = 1.0 - 1.0 / 8388608.0
_AWAY = 1.0 + 1.0 / 8388608.0


def _down32(value: float) -> float:
    """What SQLite's rtree stores as a box's minimum."""
    single = _f32(value)
    if single > value:
        single = _f32(value * (_AWAY if value < 0 else _TOWARDS))
    return single


def _up32(value: float) -> float:
    """What it stores as the maximum."""
    single = _f32(value)
    if single < value:
        single = _f32(value * (_TOWARDS if value < 0 else _AWAY))
    return single


def _line(tenths: int) -> float:
    """A tile line as QMapShack binds it: ``QString::number(x / 10., 'f')``."""
    return float(f"{tenths / 10.0:f}")


def _in_one_tile(value: float) -> bool:
    low, high = _down32(value), _up32(value)
    near = math.floor(value * 10)
    return any(_line(t) <= low and high < _line(t + 1) for t in (near - 1, near, near + 1))


def nudge(value: float, limit: float) -> float:
    """*value*, or the nearest float32 just inside the tile north or east of
    the 0.1° line it straddles.

    QMapShack reads a ``.poi`` by 0.1° tile, asking for boxes with
    ``min >= tile`` and ``max < tile + 0.1``, and SQLite's rtree keeps each
    box as float32 rounded outwards: a point whose box straddles a line is in
    neither tile and is never drawn (measured in the spike). The band around
    a line grows with the coordinate (about ±2e-5° at 180°: review, 2026-09-29),
    so it is computed, not fixed. Moved to the float32 one step inside the
    tile above the line -- below it at the edge of the world -- the point is
    in exactly one tile, at most a few metres from where it was."""
    if _in_one_tile(value):
        return value
    line = _line(round(value * 10))
    moved = _step32(_up32(line), True)
    if moved > limit or not _in_one_tile(moved):
        moved = _step32(_down32(line), False)
    if not _in_one_tile(moved):  # pragma: no cover - a tile is 0.1°, an ulp 1.5e-5°
        raise ValueError(f"{value} cannot be placed in one 0.1-degree tile")
    return moved


_POI_SCHEMA = (
    "CREATE TABLE metadata (name TEXT, value TEXT)",
    "CREATE TABLE poi_categories (id INTEGER, name TEXT, parent INTEGER, PRIMARY KEY (id))",
    "CREATE TABLE poi_data (id INTEGER, data TEXT, PRIMARY KEY (id))",
    "CREATE TABLE poi_category_map (id INTEGER, category INTEGER, PRIMARY KEY (id, category))",
    "CREATE VIRTUAL TABLE poi_index USING rtree(id, minLat, maxLat, minLon, maxLon)",
)


def _poi_value(text: str) -> str:
    return " ".join(text.replace("\r", " ").split())


@dataclass(frozen=True)
class PoiPoint:
    """One point of a Mapsforge POI file: where, what it is called, its
    description, and the one ``key=value`` tag it is filed under."""

    lat: float
    lon: float
    name: str
    description: str
    tag: str


def write_poi(
    path: Path,
    layer: str,
    comment: str,
    day: date,
    rows: Sequence[Repeater],
    *,
    nudge: bool = True,
) -> None:
    """A Mapsforge POI database (version 2) QMapShack's ``CPoiFilePOI`` reads:
    one category, every repeater in it. *path* must not exist."""
    points = [
        PoiPoint(
            r.lat,
            r.lon,
            r.label_text(),
            r.description(),
            "communication:amateur_radio:repeater=yes",
        )
        for r in rows
    ]
    write_poi_points(path, layer, comment, day, points, category=POI_CATEGORY, nudge=nudge)


def write_poi_points(
    path: Path,
    layer: str,
    comment: str,
    day: date,
    points: Sequence[PoiPoint],
    *,
    category: str,
    nudge: bool = True,
) -> None:
    """A Mapsforge POI database (version 2) QMapShack's ``CPoiFilePOI`` reads:
    one *category*, every point in it. *path* must not exist. The repeater
    layers (D-064) and the infrastructure layers (D-075) both write through
    this, so there is one float32 nudge."""
    move = _nudge if nudge else (lambda value, limit: value)
    placed = [(move(p.lat, 90.0), move(p.lon, 180.0)) for p in points]
    # Padded, so one point still makes a box with an area: QMapShack skips
    # a file whose bounds do not intersect the tile, and a zero-width
    # rectangle intersects nothing.
    pad = 0.001
    bounds = (
        min(p[0] for p in placed) - pad,
        min(p[1] for p in placed) - pad,
        max(p[0] for p in placed) + pad,
        max(p[1] for p in placed) + pad,
    )
    stamp = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    db = sqlite3.connect(path)
    try:
        with db:
            for statement in _POI_SCHEMA:
                db.execute(statement)
            db.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                [
                    ("bounds", ",".join(f"{v:.6f}" for v in bounds)),
                    ("comment", f"{layer}. {comment}"),
                    ("date", str(stamp)),
                    ("language", "en"),
                    ("version", "2"),
                    ("ways", "false"),
                    ("writer", "hammunition"),
                ],
            )
            db.executemany(
                "INSERT INTO poi_categories VALUES (?, ?, ?)",
                [(0, "root", None), (1, category, 0)],
            )
            for number, (point, (lat, lon)) in enumerate(zip(points, placed, strict=True), start=1):
                data = "\r".join(
                    (
                        f"name={_poi_value(point.name)}",
                        f"description={_poi_value(point.description)}",
                        point.tag,
                    )
                )
                db.execute("INSERT INTO poi_data VALUES (?, ?)", (number, data))
                db.execute("INSERT INTO poi_category_map VALUES (?, 1)", (number,))
                db.execute(
                    "INSERT INTO poi_index VALUES (?, ?, ?, ?, ?)", (number, lat, lat, lon, lon)
                )
    finally:
        db.close()


_nudge = nudge


# --- the store ------------------------------------------------------------------------


def overlays_root(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    """``$XDG_DATA_HOME/hammunition/overlays``: the operator's, never root's prefix."""
    base = environ.get("XDG_DATA_HOME") or str((home or Path.home()) / ".local" / "share")
    return Path(base) / "hammunition" / "overlays"


def overlay_dir(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    return overlays_root(environ, home) / "repeaters"


@dataclass(frozen=True)
class Layer:
    name: str
    description: str
    day: date
    rows: tuple[Repeater, ...] = field(default=())


def _own_dir(where: Path) -> None:
    """*where* as a directory of ours, mode 0700; a link or a file refused."""
    if where.is_symlink():
        raise OSError(f"{where} is a symbolic link; left as it is")
    where.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileExistsError):
        where.mkdir(mode=0o700)
    info = os.lstat(where)
    if not stat.S_ISDIR(info.st_mode):
        raise OSError(f"{where} is not a directory; left as it is")
    # The uid this process's new files get, read with getuid: the CLI has
    # already refused an effective root (a real root never gets here), and a
    # test that fakes geteuid to reach that refusal must not also make the
    # directory it just created look like someone else's (CI runs as root).
    if info.st_uid != os.getuid():
        raise OSError(f"{where} is not yours; left as it is")
    os.chmod(where, 0o700)


def _temporary(where: Path, name: str) -> Path:
    fd, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=where)
    os.close(fd)
    return Path(temporary)


def _rows_text(layer: Layer) -> str:
    """The layer as data: what the all-sources file is rebuilt from."""
    return (
        json.dumps(
            {
                "layer": layer.name,
                "description": layer.description,
                "day": layer.day.isoformat(),
                "rows": [{**dataclasses.asdict(row), "also": list(row.also)} for row in layer.rows],
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )


def _write_staged(where: Path, texts: Mapping[str, str], poi: tuple[str, Layer] | None) -> None:
    """Each file to a temporary name, then every one renamed into place,
    mode 0600; on any failure nothing of this write is left."""
    staged: list[tuple[Path, Path]] = []
    names = [*texts, *([poi[0]] if poi else [])]
    try:
        for name in names:
            temporary = _temporary(where, name)
            staged.append((temporary, where / name))
            if name in texts:
                temporary.write_text(texts[name], encoding="utf-8")
            elif poi is not None:
                layer = poi[1]
                temporary.unlink()  # sqlite creates it afresh
                write_poi(temporary, layer.name, layer.description, layer.day, layer.rows)
            os.chmod(temporary, 0o600)
        for temporary, final in staged:
            os.replace(temporary, final)
    except BaseException:
        for temporary, _ in staged:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
        raise


def write_layer(where: Path, layer: Layer, layer_id: str = "export") -> tuple[Path, ...]:
    """*layer_id*'s four files written into *where*, each to a temporary name
    and renamed over the old one, mode 0600; returned in :data:`SUFFIXES`
    order. Every other layer's files stay as they are."""
    names = layer_files(layer_id)
    _own_dir(where)
    texts = {
        names[0]: gpx_text(layer.name, layer.description, layer.rows),
        names[2]: navit_text(layer.rows),
        names[3]: _rows_text(layer),
    }
    _write_staged(where, texts, (names[1], layer))
    return tuple(where / name for name in names)


def present_layers(where: Path) -> tuple[str, ...]:
    """The layers whose GPX is in *where*, in :data:`LAYERS` order."""
    return tuple(i for i in LAYERS if (where / layer_files(i)[0]).is_file())


def remove_layer(where: Path, layer_id: str | None = None) -> tuple[Path, ...]:
    """Delete *layer_id*'s files, or every layer's and the all-sources file
    when it is None, and *where* when it is left empty; the files removed,
    each layer in :data:`SUFFIXES` order. Anything else in it stays."""
    if where.is_symlink():
        raise OSError(f"{where} is a symbolic link; left as it is")
    ids = [layer_id] if layer_id is not None else list(LAYERS)
    names = [n for i in ids for n in layer_files(i)]
    if layer_id is None:
        names.append(ALL_SOURCES)
    removed: list[Path] = []
    for name in names:
        path = where / name
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
            removed.append(path)
    # What an import killed between its writes and its renames leaves.
    with contextlib.suppress(FileNotFoundError):
        for leftover in where.iterdir():
            if any(leftover.name.startswith(f".{name}.") for name in names):
                with contextlib.suppress(FileNotFoundError):
                    leftover.unlink()
    with contextlib.suppress(FileNotFoundError, OSError):
        where.rmdir()  # only when empty
    return tuple(removed)


_ROW_FIELDS = {f.name for f in dataclasses.fields(Repeater)}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_row_types(item: Mapping[str, Any]) -> None:
    """Every field of a row read back has the type :class:`Repeater` writes,
    or ValueError naming the field: a string latitude or offset would fail
    later, inside the merge or the GPX writer, and ``true`` is not 1 Hz
    (final review, 2026-10-01)."""
    for name, value in item.items():
        if name == "output_hz":
            ok = _is_int(value)
        elif name == "offset_hz":
            ok = value is None or _is_int(value)
        elif name in ("lat", "lon"):
            ok = _is_int(value) or isinstance(value, float)
        elif name == "also":
            ok = isinstance(value, list) and all(isinstance(s, str) for s in value)
        else:
            ok = isinstance(value, str)
        if not ok:
            raise ValueError(f"field {name} holds {value!r}, not what this writes")


def read_layer_rows(path: Path) -> Layer:
    """A ``.rows.json`` read back, or ValueError naming what is wrong. The
    operator's own file: read defensively, every field checked."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        rows: list[Repeater] = []
        for item in data["rows"]:
            if not isinstance(item, dict) or set(item) - _ROW_FIELDS:
                raise ValueError("a row with fields this does not write")
            _check_row_types(item)
            also = tuple(item.get("also") or ())
            row = Repeater(**{**item, "also": also})
            for source in (row.source, *also):
                if source not in SOURCE_NAMES:
                    raise ValueError(f"an unknown source {source!r}")
            if _position(row.lat, row.lon) is None:
                raise ValueError("a row without a usable position")
            rows.append(row)
        return Layer(
            name=str(data["layer"]),
            description=str(data["description"]),
            day=date.fromisoformat(str(data["day"])),
            rows=tuple(rows),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{path.name} cannot be read: {exc}") from None


@dataclass(frozen=True)
class AllSources:
    """What :func:`rebuild_all` did. ``path`` is None when fewer than two
    directory layers could be read, and the file is then absent."""

    path: Path | None
    name: str = ""
    layers: tuple[str, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()
    written: int = 0
    merged: int = 0
    #: The file, when this rebuild deleted it (fewer than two layers left).
    removed: Path | None = None


def all_sources_name(day: date) -> str:
    return f"Repeaters (all sources, {day.isoformat()})"


def rebuild_all(where: Path) -> AllSources:
    """``repeaters-all.gpx``: every directory layer in *where* joined by the
    cross-source precedence (:func:`hammunition.repeater_sources.cross_merge`),
    written when two or more can be read and deleted otherwise. Dated by the
    oldest layer it joins; its description carries every one's licence."""
    from .repeater_sources import cross_merge

    used: list[tuple[str, Layer]] = []
    skipped: list[tuple[str, str]] = []
    for layer_id in present_layers(where):
        if layer_id in HEARD_LAYERS:
            continue
        rows_path = where / layer_files(layer_id)[3]
        if not rows_path.is_file():
            skipped.append(
                (layer_id, "written before D-074 kept its rows as data; re-import it to include it")
            )
            continue
        try:
            used.append((layer_id, read_layer_rows(rows_path)))
        except ValueError as exc:
            skipped.append((layer_id, str(exc)))
    target = where / ALL_SOURCES
    if len(used) < 2:
        removed = None
        with contextlib.suppress(FileNotFoundError):
            target.unlink()
            removed = target
        return AllSources(
            None, layers=tuple(i for i, _ in used), skipped=tuple(skipped), removed=removed
        )
    rows, merged = cross_merge(layer.rows for _, layer in used)
    day = min(layer.day for _, layer in used)
    name = all_sources_name(day)
    description = " ".join(layer.description for _, layer in used)
    _own_dir(where)
    _write_staged(where, {ALL_SOURCES: gpx_text(name, description, rows)}, None)
    return AllSources(
        path=target,
        name=name,
        layers=tuple(i for i, _ in used),
        skipped=tuple(skipped),
        written=len(rows),
        merged=merged,
    )


# --- hearham -----------------------------------------------------------------------------


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is followed only to HTTPS (the loopback test server aside,
    which is plain HTTP and never redirects)."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise RepeaterFetchError(f"refused a redirect to {newurl}: not HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_hearham(
    url: str = HEARHAM_URL, *, timeout: float = 60.0, limit: int = HEARHAM_LIMIT
) -> tuple[bytes, str, datetime]:
    """hearham's list as served, its observed sha256 and when it was fetched."""
    return fetch_list(url, timeout=timeout, limit=limit)


def fetch_list(
    url: str, *, timeout: float = 60.0, limit: int, user_agent: str = "hammunition"
) -> tuple[bytes, str, datetime]:
    """A list fetched on the operator's request (hearham, D-064; the ETCC
    and Brandmeister, D-074): the bytes as served, their observed sha256 and
    when they arrived. *user_agent* is sent as given: the FCC's server
    refused a bare ``hammunition`` (403) and served a descriptive one
    (D-075, one HEAD each on 2026-10-01).

    Built from :class:`~urllib.request.OpenerDirector` with only the HTTP
    handlers, so no ``file:`` URL is served; TLS verified by default. Nothing
    fetched is trusted: it is parsed like any operator file."""
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(),
        _HttpsOnlyRedirect(),
        urllib.request.HTTPErrorProcessor(),
        urllib.request.HTTPDefaultErrorHandler(),
    ):
        opener.add_handler(handler)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with opener.open(request, timeout=timeout) as response:
            body: bytes = response.read(limit + 1)
    except RepeaterFetchError:
        raise
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise RepeaterFetchError(f"could not fetch {url}: {exc!r}") from None
    if len(body) > limit:
        raise RepeaterFetchError(f"{url} answered with more than {limit} bytes; refused")
    return body, hashlib.sha256(body).hexdigest(), datetime.now(UTC).replace(microsecond=0)
