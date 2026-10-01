# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The federal and worldwide files behind the infrastructure layers.  D-075.

Three are D-049 data units, read from where they install:

- **FAA NASR** ``APT_CSV.zip``: ``APT_BASE.csv``, every landing site with
  decimal coordinates (:func:`read_nasr`).
- **EIA-860M**, the monthly generator inventory: its ``Operating`` sheet,
  streamed row by row and grouped into plants (:func:`read_eia`).
- **WRI's Global Power Plant Database** v1.3.0, outside the US only, where
  EIA-860M is this month's and WRI's US rows are EIA's of 2019
  (:func:`read_wri`).

Two are fetched only when the operator asks, through D-064's fetch, and
parsed from memory:

- **FCC Antenna Structure Registration** ``r_tower.zip``: ``RA.dat`` and
  ``CO.dat`` only. ``EN.dat``, which holds the owners' contact names, e-mail
  addresses and telephone numbers, is never opened, and of ``RA`` the
  signature and address fields are never kept (:func:`parse_fcc_asr`).
- **NOAA Weather Radio**'s ``ccl-data.js``: frequency, power, WFO and each
  county's SAME code; the live ``status`` is never read
  (:func:`parse_nwr`).

Every layout was measured on the publishers' own files by the spike of
2026-10-01. Every file is kept to the station's regions' boxes, and every
row left out is counted by reason, numbered by its place in the file.
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import IO

from .infra import Box, InfraInputError, Point, in_boxes
from .repeaters import _position

__all__ = [
    "FCC_ASR_LIMIT",
    "FCC_ASR_URL",
    "MEMBER_LIMIT",
    "NO_POSITION",
    "NWR_LIMIT",
    "NWR_PAD",
    "NWR_URL",
    "UNITS",
    "SourceRead",
    "Unit",
    "parse_fcc_asr",
    "parse_nwr",
    "read_eia",
    "read_nasr",
    "read_wri",
]

NO_POSITION = "no usable position"
#: No archive member is read past this, decompressed: EIA's largest sheet
#: is 56 MB and FCC's ``RA.dat`` 56 MB (the spike).
MEMBER_LIMIT = 256 * 1024 * 1024

#: The FCC's weekly complete ASR file: 37,810,019 B on 2026-09-27, no
#: checksum published (ETag only).
FCC_ASR_URL = "https://data.fcc.gov/download/pub/uls/complete/r_tower.zip"
FCC_ASR_LIMIT = 128 * 1024 * 1024
#: The data behind NWS's station tables: 754,735 B on 2026-10-01.
NWR_URL = "https://www.weather.gov/source/nwr/JS/ccl-data.js"
NWR_LIMIT = 8 * 1024 * 1024
#: A transmitter this far outside a box is kept: measured on Delaware and
#: Vermont, 0.5 degree missed one of Vermont's twelve covering transmitters
#: and 1.0 missed none.
NWR_PAD = 1.0


@dataclass(frozen=True)
class SourceRead:
    """One source read into one layer."""

    layer_id: str
    name: str
    licence: str
    source: str
    day: date
    points: tuple[Point, ...]
    read: int
    skipped: dict[str, list[int]]
    outside: int
    notes: tuple[str, ...] = field(default=())


class _Skips:
    def __init__(self) -> None:
        self.by: dict[str, list[int]] = {}

    def add(self, reason: str, number: int) -> None:
        self.by.setdefault(reason, []).append(number)


def _zip(raw: bytes | Path, what: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(raw) if isinstance(raw, bytes) else raw)
    except (zipfile.BadZipFile, OSError) as exc:
        raise InfraInputError(f"{what} is not a zip archive ({exc})") from None


def _open(archive: zipfile.ZipFile, name: str, what: str) -> IO[bytes]:
    """*name* from *archive*, refused when absent or larger than the cap."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        raise InfraInputError(f"{what} holds no {name}") from None
    if info.file_size > MEMBER_LIMIT:
        raise InfraInputError(f"{what}: {name} is larger than {MEMBER_LIMIT} bytes; refused")
    return archive.open(name)


def _float(text: object) -> float | None:
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def _title(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())


def _number(value: float) -> str:
    return f"{value:.1f}".removesuffix(".0")


# --- FAA NASR --------------------------------------------------------------------------

_SITE_TYPES = {
    "A": "airport",
    "H": "heliport",
    "C": "seaplane base",
    "U": "ultralight park",
    "G": "gliderport",
    "B": "balloonport",
}
_SITE_STATUS = {"O": "operational", "CI": "closed indefinitely", "CP": "closed permanently"}
_SITE_USE = {"PU": "public use", "PR": "private use"}
_NASR_COLUMNS = (
    "EFF_DATE",
    "SITE_TYPE_CODE",
    "ARPT_ID",
    "ARPT_NAME",
    "LAT_DECIMAL",
    "LONG_DECIMAL",
)


def read_nasr(path: Path, boxes: Sequence[Box]) -> SourceRead:
    """``APT_BASE.csv`` from the NASR APT zip: every landing site in the
    boxes, its type, status, use, elevation and ICAO id. Dated by its
    ``EFF_DATE``, the 28-day cycle."""
    what = str(path)
    with _zip(path, what) as archive, _open(archive, "APT_BASE.csv", what) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
        missing = [c for c in _NASR_COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise InfraInputError(
                f"{what}: not the NASR APT_BASE.csv (no {', '.join(missing)} column)"
            )
        points: list[Point] = []
        skips = _Skips()
        read = outside = 0
        cycles: set[str] = set()
        for row in reader:
            read += 1
            line = reader.line_num
            cycles.add(row["EFF_DATE"].strip())
            where = _position(row["LAT_DECIMAL"], row["LONG_DECIMAL"])
            if where is None:
                skips.add(NO_POSITION, line)
                continue
            if not in_boxes(where[0], where[1], boxes):
                outside += 1
                continue
            ident = row["ARPT_ID"].strip()
            kind = _SITE_TYPES.get(row["SITE_TYPE_CODE"].strip(), "landing site")
            details = [
                _SITE_STATUS.get((row.get("ARPT_STATUS") or "").strip(), ""),
                _SITE_USE.get((row.get("FACILITY_USE_CODE") or "").strip(), ""),
            ]
            elevation = _float(row.get("ELEV") or "")
            if elevation is not None:
                details.append(f"elevation {_number(elevation)} ft")
            if (row.get("ICAO_ID") or "").strip():
                details.append(f"ICAO {row['ICAO_ID'].strip()}")
            if (row.get("CITY") or "").strip():
                details.append(_title(row["CITY"]))
            details.append(f"FAA {ident}")
            points.append(
                Point(
                    f"{_title(row['ARPT_NAME'])} ({ident})",
                    kind,
                    where[0],
                    where[1],
                    tuple(d for d in details if d),
                )
            )
    day = _nasr_day(cycles, what)
    return SourceRead(
        layer_id="faa-airports",
        name=f"Airports and heliports (FAA NASR {day.isoformat()})",
        licence=f"FAA NASR {day.isoformat()}, public domain",
        source=f"FAA NASR {day.isoformat()}",
        day=day,
        points=tuple(points),
        read=read,
        skipped=skips.by,
        outside=outside,
    )


def _nasr_day(cycles: set[str], what: str) -> date:
    days = []
    for text in cycles:
        try:
            days.append(datetime.strptime(text, "%Y/%m/%d").date())
        except ValueError:
            continue
    if not days:
        raise InfraInputError(f"{what}: no EFF_DATE says which NASR cycle this is")
    return max(days)


# --- EIA-860M ---------------------------------------------------------------------------

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_CELL = re.compile(r"[A-Z]+")
_AS_OF = re.compile(r"as of ([A-Za-z]+) (\d{4})")
_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]  # fmt: skip


def _xml(handle: IO[bytes], what: str) -> Iterator[ET.Element]:
    """Elements of *handle* as they end. A DOCTYPE is refused before any
    parsing, looked for in the bytes the archive member has buffered (a
    declaration comes before the root element): no workbook part needs one
    (D-064's rule)."""
    peek = getattr(handle, "peek", None)
    head: bytes = peek(4096)[:4096] if callable(peek) else b""
    if b"<!DOCTYPE" in head.upper() or b"<!ENTITY" in head.upper():
        raise InfraInputError(f"{what}: XML with a DOCTYPE or ENTITY declaration is refused")
    try:
        for _, element in ET.iterparse(handle, events=("end",)):
            yield element
    except ET.ParseError as exc:
        raise InfraInputError(f"{what}: does not parse: {exc}") from None


def _sheet_rows(path: Path, sheet: str) -> Iterator[list[str]]:
    """The rows of *sheet* in the workbook at *path*, as text, streamed."""
    what = str(path)
    with _zip(path, what) as archive:
        with _open(archive, "xl/workbook.xml", what) as handle:
            sheets = {
                e.get("name"): e.get(_REL) for e in _xml(handle, what) if e.tag == f"{_MAIN}sheet"
            }
        if sheet not in sheets:
            raise InfraInputError(
                f"{what}: no {sheet} sheet (it has {', '.join(map(str, sheets))})"
            )
        with _open(archive, "xl/_rels/workbook.xml.rels", what) as handle:
            targets = {e.get("Id"): e.get("Target", "") for e in _xml(handle, what)}
        target = targets.get(sheets[sheet], "")
        member = "xl/" + target.lstrip("/").removeprefix("xl/")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with _open(archive, "xl/sharedStrings.xml", what) as handle:
                for e in _xml(handle, what):
                    if e.tag == f"{_MAIN}si":
                        shared.append("".join(t.text or "" for t in e.iter(f"{_MAIN}t")))
                        e.clear()
        with _open(archive, member, what) as handle:
            for row in _xml(handle, what):
                if row.tag != f"{_MAIN}row":
                    continue
                cells: dict[int, str] = {}
                for c in row.findall(f"{_MAIN}c"):
                    match = _CELL.match(c.get("r", ""))
                    if match is None:
                        continue
                    col = 0
                    for ch in match.group(0):
                        col = col * 26 + ord(ch) - 64
                    v = c.find(f"{_MAIN}v")
                    if c.get("t") == "s" and v is not None and (v.text or "").isdigit():
                        index = int(v.text or "0")
                        value = shared[index] if index < len(shared) else ""
                    elif c.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in c.iter(f"{_MAIN}t"))
                    else:
                        value = v.text or "" if v is not None else ""
                    cells[col - 1] = value
                row.clear()
                yield [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []


@dataclass
class _Plant:
    """One plant's generators, as they are read: its first row and cells."""

    row: int
    cells: dict[str, str]
    mw: float = 0.0
    count: int = 0
    tech: list[str] = field(default_factory=list)


def read_eia(path: Path, boxes: Sequence[Box]) -> SourceRead:
    """EIA-860M's ``Operating`` sheet: one point a plant in the boxes, with
    its generators' nameplate capacity summed and their technologies.
    Dated by the sheet's own title, "as of <Month> <YYYY>"."""
    what = str(path)
    month: date | None = None
    header: list[str] | None = None
    plants: dict[str, _Plant] = {}
    order: list[str] = []
    skips = _Skips()
    read = 0
    for number, row in enumerate(_sheet_rows(path, "Operating"), start=1):
        if header is None:
            text = " ".join(row)
            found = _AS_OF.search(text)
            if found and found.group(1).lower() in _MONTHS:
                month = date(int(found.group(2)), _MONTHS.index(found.group(1).lower()) + 1, 1)
            if "Plant ID" in row and "Latitude" in row and "Longitude" in row:
                header = [h.strip() for h in row]
            continue
        if not any(cell.strip() for cell in row):
            continue
        cells = {name: (row[i].strip() if i < len(row) else "") for i, name in enumerate(header)}
        if not cells.get("Plant ID"):
            continue  # a footnote under the table
        read += 1
        plant = cells["Plant ID"]
        if plant not in plants:
            plants[plant] = _Plant(number, cells)
            order.append(plant)
        entry = plants[plant]
        entry.mw += _float(cells.get("Nameplate Capacity (MW)")) or 0
        entry.count += 1
        if cells.get("Technology") and cells["Technology"] not in entry.tech:
            entry.tech.append(cells["Technology"])
    if header is None:
        raise InfraInputError(
            f"{what}: its Operating sheet has no header with Plant ID, Latitude and Longitude"
        )
    if month is None:
        raise InfraInputError(f"{what}: its Operating sheet does not say which month it is")
    points: list[Point] = []
    outside = 0
    for plant in order:
        entry = plants[plant]
        cells = entry.cells
        where = _position(cells.get("Latitude"), cells.get("Longitude"))
        if where is None:
            skips.add(NO_POSITION, entry.row)
            continue
        if not in_boxes(where[0], where[1], boxes):
            outside += 1
            continue
        count = entry.count
        details = [
            f"{_number(entry.mw)} MW nameplate",
            f"{count} generator{'s' if count != 1 else ''}",
            ", ".join(entry.tech),
            f"operator {cells.get('Entity Name', '')}" if cells.get("Entity Name") else "",
            f"EIA plant {plant}",
        ]
        points.append(
            Point(
                cells.get("Plant Name") or f"EIA plant {plant}",
                "power plant",
                where[0],
                where[1],
                tuple(d for d in details if d),
            )
        )
    stamp = f"{month:%b} {month.year}"
    return SourceRead(
        layer_id="eia-plants",
        name=f"Power plants (EIA-860M {stamp})",
        # EIA asks for exactly this acknowledgment, with the publication date.
        licence=f"Source: U.S. Energy Information Administration ({stamp}), public domain",
        source=f"U.S. Energy Information Administration ({stamp})",
        day=month,
        points=tuple(points),
        read=read,
        skipped=skips.by,
        outside=outside,
    )


# --- WRI ---------------------------------------------------------------------------------

WRI_LICENCE = "WRI Global Power Plant Database v1.3.0 (2021), CC BY 4.0"
_WRI_MEMBER = "global_power_plant_database.csv"
#: The CSV's own modification date in the v1.3.0 zip.
WRI_DAY = date(2021, 6, 2)


def read_wri(path: Path, boxes: Sequence[Box]) -> SourceRead:
    """WRI's plants in the boxes, outside the US only: in the US its rows are
    EIA's data of 2019, and EIA-860M is this month's."""
    what = str(path)
    with _zip(path, what) as archive, _open(archive, _WRI_MEMBER, what) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
        needed = ("country", "name", "gppd_idnr", "capacity_mw", "latitude", "longitude")
        missing = [c for c in needed if c not in (reader.fieldnames or ())]
        if missing:
            raise InfraInputError(f"{what}: not WRI's plant list (no {', '.join(missing)} column)")
        points: list[Point] = []
        skips = _Skips()
        read = outside = us = 0
        for row in reader:
            read += 1
            where = _position(row["latitude"], row["longitude"])
            if where is None:
                skips.add(NO_POSITION, reader.line_num)
                continue
            if not in_boxes(where[0], where[1], boxes):
                outside += 1
                continue
            if row["country"].strip() == "USA":
                us += 1
                continue
            capacity = _float(row["capacity_mw"])
            fuels = [
                f for f in (row.get(k, "").strip() for k in ("primary_fuel", "other_fuel1")) if f
            ]
            details = [
                f"{_number(capacity)} MW" if capacity is not None else "",
                ", ".join(fuels),
                f"owner {row['owner'].strip()}" if (row.get("owner") or "").strip() else "",
                f"since {row['commissioning_year'].split('.')[0]}"
                if (row.get("commissioning_year") or "").strip()
                else "",
                f"WRI {row['gppd_idnr'].strip()}",
            ]
            points.append(
                Point(
                    row["name"].strip() or f"WRI {row['gppd_idnr']}",
                    "power plant",
                    where[0],
                    where[1],
                    tuple(d for d in details if d),
                )
            )
    notes = (
        (
            f"{us} plant{'s' if us != 1 else ''} in the US left out: EIA-860M covers the US "
            f"(`--from-eia`), with this month's data where WRI's US rows are EIA's of 2019",
        )
        if us
        else ()
    )
    return SourceRead(
        layer_id="wri-plants",
        name="Power plants (WRI GPPD v1.3.0, 2021, CC BY 4.0)",
        licence=WRI_LICENCE,
        source="WRI Global Power Plant Database v1.3.0, CC BY 4.0",
        day=WRI_DAY,
        points=tuple(points),
        read=read,
        skipped=skips.by,
        outside=outside,
        notes=notes,
    )


# --- FCC ASR ------------------------------------------------------------------------------

FCC_LICENCE = "FCC Antenna Structure Registration, US Government work, public domain"
#: ``RA.dat``'s fields, 0-based, measured on the 2026-09-27 file. Only these
#: are read; the signature (17-22) and street address (23) never are.
_RA_REG, _RA_USI, _RA_STATUS, _RA_BUILT, _RA_GONE = 3, 4, 8, 12, 13
_RA_CITY, _RA_STATE = 24, 25
_RA_AGL, _RA_AMSL, _RA_TYPE = 30, 31, 32
_ASR_STATUS = {"C": "constructed", "G": "granted"}
_ASR_TYPES = {
    "TOWER": "tower",
    "MTOWER": "monopole tower",
    "LTOWER": "lattice tower",
    "GTOWER": "guyed tower",
    "MAST": "mast",
    "POLE": "pole",
    "TANK": "tank",
    "B": "building",
    "BANT": "building with antenna",
    "TREE": "tree",
}
_COUNTS_DATE = re.compile(r"([A-Z][a-z]{2}) +(\d{1,2}) [\d:]+ [A-Z]+ (\d{4})")


def _lines(archive: zipfile.ZipFile, name: str, what: str) -> Iterator[list[str]]:
    with _open(archive, name, what) as raw:
        for line in io.TextIOWrapper(raw, encoding="latin-1", newline=""):
            text = line.rstrip("\r\n")
            if text:
                yield text.split("|")


def _dms(fields: Sequence[str], at: int) -> float | None:
    parts = [_float(fields[at + i]) if at + i < len(fields) else None for i in range(3)]
    if parts[0] is None:
        return None
    value = parts[0] + (parts[1] or 0) / 60 + (parts[2] or 0) / 3600
    hemisphere = fields[at + 3] if at + 3 < len(fields) else ""
    return -value if hemisphere in ("S", "W") else value


def parse_fcc_asr(
    raw: bytes, url: str, boxes: Sequence[Box], *, fetched: datetime, sha256: str
) -> SourceRead:
    """The structures in the boxes whose registration is constructed or
    granted, not dismantled, with a structure coordinate."""
    archive = _zip(raw, url)
    names = set(archive.namelist())
    if not {"RA.dat", "CO.dat"} <= names:
        raise InfraInputError(f"{url}: not the FCC ASR archive (no RA.dat and CO.dat)")
    day = fetched.date()
    if "counts" in names:
        with _open(archive, "counts", url) as handle:
            found = _COUNTS_DATE.search(handle.read(4096).decode("latin-1"))
        if found:
            day = datetime.strptime(" ".join(found.groups()), "%b %d %Y").date()
    coordinates: dict[str, tuple[float, float]] = {}
    for fields in _lines(archive, "CO.dat", url):
        if len(fields) < 15 or fields[5] != "T":
            continue
        lat, lon = _dms(fields, 6), _dms(fields, 11)
        where = _position(lat, lon) if lat is not None and lon is not None else None
        if where is not None:
            coordinates.setdefault(fields[4], where)
    points: list[Point] = []
    skips = _Skips()
    read = outside = 0
    for number, fields in enumerate(_lines(archive, "RA.dat", url), start=1):
        if fields[0] != "RA" or len(fields) <= _RA_TYPE:
            continue
        read += 1
        if fields[_RA_GONE].strip():
            skips.add("dismantled", number)
            continue
        status = _ASR_STATUS.get(fields[_RA_STATUS].strip())
        if status is None:
            skips.add("not constructed or granted", number)
            continue
        where = coordinates.get(fields[_RA_USI])
        if where is None:
            skips.add("no structure coordinates", number)
            continue
        if not in_boxes(where[0], where[1], boxes):
            outside += 1
            continue
        code = fields[_RA_TYPE].strip()
        agl, amsl = _float(fields[_RA_AGL]), _float(fields[_RA_AMSL])
        details = [
            f"{_number(agl)} m above ground" if agl is not None else "",
            f"{_number(amsl)} m above sea level" if amsl is not None else "",
            status,
            f"type {code}" if code else "",
            ", ".join(x for x in (_title(fields[_RA_CITY]), fields[_RA_STATE].strip()) if x),
            f"registration {fields[_RA_REG].strip()}",
        ]
        points.append(
            Point(
                f"ASR {fields[_RA_REG].strip()}",
                _ASR_TYPES.get(code, "structure"),
                where[0],
                where[1],
                tuple(d for d in details if d),
            )
        )
    return SourceRead(
        layer_id="fcc-towers",
        name=f"FCC towers (unverified, {day.isoformat()})",
        licence=FCC_LICENCE,
        source="FCC Antenna Structure Registration, unverified",
        day=day,
        points=tuple(points),
        read=read,
        skipped=skips.by,
        outside=outside,
        notes=(
            f"fetched {fetched.isoformat()}, sha256 {sha256}: not verifiable, the FCC "
            f"publishes no checksum; only the registration and coordinate records were read",
        ),
    )


# --- NOAA Weather Radio --------------------------------------------------------------------

NWR_LICENCE = "NOAA/NWS, public domain, not an official NWS product"


def parse_nwr(
    raw: bytes, url: str, boxes: Sequence[Box], *, fetched: datetime, sha256: str
) -> SourceRead:
    """The transmitters within :data:`NWR_PAD` of a box: frequency, power,
    WFO and each county's SAME code. ``status`` is never read."""
    text = raw.decode("utf-8", errors="replace")
    start = text.find("[", text.find("cclData"))
    end = text.rfind("]")
    data: object = None
    if "cclData" in text and 0 <= start < end:
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, list):
        raise InfraInputError(f"{url}: not the NWS transmitter list (a cclData array)")
    points: list[Point] = []
    skips = _Skips()
    read = outside = 0
    for number, item in enumerate(data, start=1):
        if not isinstance(item, Mapping):
            skips.add("not a transmitter entry", number)
            continue
        read += 1
        where = _position(item.get("lat"), item.get("lon"))
        if where is None:
            skips.add(NO_POSITION, number)
            continue
        if not in_boxes(where[0], where[1], boxes, pad=NWR_PAD):
            outside += 1
            continue
        call = str(item.get("callsign") or "").strip()
        freq = str(item.get("freq") or "").strip()
        counties = [
            " ".join(str(c.get(k) or "").strip() for k in ("same", "county", "st") if c.get(k))
            for c in item.get("counties") or ()
            if isinstance(c, Mapping)
        ]
        wfo = str(item.get("wfo") or "").replace("|", ", ").strip()
        site = ", ".join(
            x
            for x in (
                str(item.get("sitename") or "").strip(),
                str(item.get("sitestate") or "").strip(),
            )
            if x
        )
        details = [
            f"{freq} MHz" if freq else "",
            f"{str(item.get('power') or '').strip()} W" if item.get("power") else "",
            f"site {site}" if site else "",
            f"WFO {wfo}" if wfo else "",
            f"SAME {', '.join(counties)}" if counties else "",
        ]
        points.append(
            Point(
                " ".join(x for x in (call, freq) if x) or "NWR transmitter",
                "NOAA Weather Radio transmitter",
                where[0],
                where[1],
                tuple(d for d in details if d),
            )
        )
    day = fetched.date()
    return SourceRead(
        layer_id="nwr",
        name=f"NOAA Weather Radio (unverified, fetched {day.isoformat()})",
        licence=NWR_LICENCE,
        source="NOAA/NWS, unverified, not an official NWS product",
        day=day,
        points=tuple(points),
        read=read,
        skipped=skips.by,
        outside=outside,
        notes=(
            f"fetched {fetched.isoformat()}, sha256 {sha256}: not verifiable, NWS publishes "
            f"no checksum; each transmitter's live status was dropped (it changes with every "
            f"outage), so check a transmitter is on the air before you rely on it",
        ),
    )


# --- the data units --------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """A data unit an import reads: where its file installs, and how."""

    unit: str
    file: Path
    what: str
    size: str
    licence_short: str
    format: str
    read: Callable[[Path, Sequence[Box]], SourceRead]


UNITS: dict[str, Unit] = {
    "nasr": Unit(
        "faa-nasr-airports",
        Path("faa-nasr-airports") / "APT_CSV.zip",
        "FAA NASR airport file",
        "about 8 MB",
        "public domain",
        "faa-nasr-apt",
        read_nasr,
    ),
    "eia": Unit(
        "eia-860m",
        Path("eia-860m") / "eia860m.xlsx",
        "EIA-860M workbook",
        "about 14 MB",
        "public domain",
        "eia-860m",
        read_eia,
    ),
    "wri": Unit(
        "wri-power-plants",
        Path("wri-power-plants") / "global_power_plant_database.zip",
        "WRI Global Power Plant Database",
        "about 4.2 MB",
        "CC BY 4.0",
        "wri-gppd",
        read_wri,
    ),
}
