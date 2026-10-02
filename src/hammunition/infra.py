# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Infrastructure and EMCOMM layers on the operator's maps.  D-075.

One layer per source, as D-074 does for repeaters: eight layers filtered
out of the OpenStreetMap extracts the station already has (medical,
responders, supply, shelter candidates, transport, power, telecom, water),
and one each from FAA NASR, EIA-860M, WRI's plant list, FCC ASR and NOAA
Weather Radio (:mod:`hammunition.infra_sources`). Each layer is four files
in ``$XDG_DATA_HOME/hammunition/overlays/infra/``: a GPX for QMapShack's
File > Load and phones, a Mapsforge ``.poi`` QMapShack keeps as a POI
collection, a Navit textfile, and a GeoJSON the browser map draws (D-071).

The OpenStreetMap tag sets are the spike's (2026-10-01), measured on
Delaware and Vermont; what it ruled out (``amenity=shelter``, sirens,
defibrillators, assembly points, power towers and poles, generators,
hydrants, bridges, lines) is not a point here. The symbols are QMapShack
1.17.1's built-in names (``helpers/CWptIconManager.cpp``) and the icons are
files the ``navit`` package ships, so nothing is written into either
program's own directories.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from . import osm_pbf
from .repeaters import (
    GPX_NS,
    PoiPoint,
    _own_dir,
    _position,
    _temporary,
    overlays_root,
    write_poi_points,
)

__all__ = [
    "LAYERS",
    "NO_POSITION",
    "OSM_LAYERS",
    "OSM_LICENCE",
    "SHELTER_NOTE",
    "SUFFIXES",
    "Box",
    "Gathered",
    "InfraInputError",
    "InfraLayer",
    "Kind",
    "LayerSpec",
    "OsmLayer",
    "OsmRead",
    "Point",
    "filter_extract",
    "geojson_text",
    "gpx_text",
    "in_boxes",
    "layer_files",
    "navit_text",
    "osm_layer_name",
    "osmium_argv",
    "overlay_dir",
    "present_layers",
    "read_osm_xml",
    "region_boxes",
    "remove_layer",
    "write_layer",
]

#: The licence line of every OpenStreetMap layer, exactly (D-075).
OSM_LICENCE = "© OpenStreetMap contributors, ODbL 1.0"
OSM_SOURCE = "OpenStreetMap contributors, ODbL"
#: Ruling of 2026-10-01 (the maintainer's delegate): in the shelter
#: candidates' layer name and every one of their descriptions.
SHELTER_NOTE = "candidate, not a designated shelter"
NO_POSITION = "no usable position"
#: A layer's files: GPX, POI, Navit textfile, GeoJSON for the browser map.
SUFFIXES = (".gpx", ".poi", ".navit.txt", ".geojson")
NAVIT_ICONS = Path("/usr/share/navit/icons")

#: (west, south, east, north) in degrees; west > east crosses the antimeridian.
Box = tuple[float, float, float, float]


class InfraInputError(Exception):
    """An input this does not read, named with the reason."""


# --- the OpenStreetMap layers ------------------------------------------------------


@dataclass(frozen=True)
class Kind:
    """One kind of object: any of *tags* (``key``, values) matches, and
    *also*, when given, must hold too."""

    label: str
    tags: tuple[tuple[str, tuple[str, ...]], ...]
    also: Callable[[Mapping[str, str]], bool] | None = None

    def matches(self, tags: Mapping[str, str]) -> bool:
        hit = any(_has(tags, key, values) for key, values in self.tags)
        return hit and (self.also is None or self.also(tags))


@dataclass(frozen=True)
class OsmLayer:
    title: str
    kinds: tuple[Kind, ...]


def _has(tags: Mapping[str, str], key: str, values: Sequence[str]) -> bool:
    value = tags.get(key)
    if value is None:
        return False
    return any(v.strip() in values for v in value.split(";"))


def _communication(tags: Mapping[str, str]) -> bool:
    """The spike's "of which communication": a mast or tower is a telecom
    one only with ``tower:type=communication``, ``man_made=communications_tower``
    or a ``communication:*`` key (314 of Delaware's 426 masts and towers)."""
    return (
        _has(tags, "tower:type", ("communication",))
        or _has(tags, "man_made", ("communications_tower",))
        or any(k.startswith("communication:") for k in tags)
    )


def _k(label: str, key: str, *values: str) -> Kind:
    return Kind(label, ((key, values),))


#: The spike's "carry" rows, exactly (2026-10-01; Delaware / Vermont):
#: medical 187 / 199, responders 160 / 367, supply 573 / 885, shelter
#: candidates 671 / 1,801, transport 72 / 123, power 225 / 874, telecom
#: 314 / 174, water 163 / 105.
OSM_LAYERS: dict[str, OsmLayer] = {
    "medical": OsmLayer(
        "Medical",
        (
            _k("hospital", "amenity", "hospital"),
            _k("clinic", "amenity", "clinic", "doctors"),
            _k("pharmacy", "amenity", "pharmacy"),
        ),
    ),
    "responders": OsmLayer(
        "Responders",
        (
            _k("fire station", "amenity", "fire_station"),
            _k("police", "amenity", "police"),
            _k("ambulance station", "emergency", "ambulance_station"),
        ),
    ),
    "supply": OsmLayer(
        "Supply",
        (
            _k("fuel", "amenity", "fuel"),
            _k("supermarket", "shop", "supermarket"),
            _k("hardware", "shop", "hardware", "doityourself"),
            _k("charging station", "amenity", "charging_station"),
            _k("drinking water", "amenity", "drinking_water", "water_point"),
        ),
    ),
    "shelter-candidates": OsmLayer(
        "Shelter candidates",
        (
            _k("school", "amenity", "school"),
            _k("community centre", "amenity", "community_centre"),
            _k("town hall", "amenity", "townhall"),
            _k("place of worship", "amenity", "place_of_worship"),
        ),
    ),
    "transport": OsmLayer(
        "Transport",
        (
            _k("aerodrome", "aeroway", "aerodrome"),
            _k("helipad", "aeroway", "helipad", "heliport"),
            _k("railway station", "railway", "station", "halt"),
        ),
    ),
    "power": OsmLayer(
        "Power",
        (
            _k("substation", "power", "substation"),
            _k("power plant", "power", "plant"),
        ),
    ),
    "telecom": OsmLayer(
        "Telecom masts",
        (
            Kind(
                "communications mast",
                (
                    ("man_made", ("mast", "tower", "communications_tower")),
                    ("tower:type", ("communication",)),
                ),
                also=_communication,
            ),
        ),
    ),
    "water": OsmLayer(
        "Water",
        (
            _k("water works", "man_made", "water_works", "desalination_plant"),
            _k("wastewater plant", "man_made", "wastewater_plant"),
            _k("pumping station", "man_made", "pumping_station"),
            _k("water tower", "man_made", "water_tower"),
        ),
    ),
}


@dataclass(frozen=True)
class LayerSpec:
    """How a layer is drawn: QMapShack's symbol, Navit's type and icon, and
    the POI collection's category name."""

    title: str
    symbol: str
    navit_type: str
    navit_icon: str
    category: str


def _spec(title: str, symbol: str, number: str, icon: str, category: str) -> LayerSpec:
    return LayerSpec(title, symbol, f"poi_custom{number}", str(NAVIT_ICONS / icon), category)


#: Every layer, in the order they are listed and registered. ``poi_custom0``
#: is the repeaters' (D-064); each layer here has its own custom type, all
#: drawn and labelled by the stock layout's ``poi_custom*`` rules.
LAYERS: dict[str, LayerSpec] = {
    "osm-medical": _spec(
        "Medical", "Medical Facility", "1", "hospital.png", "Medical (OpenStreetMap)"
    ),
    "osm-responders": _spec(
        "Responders", "Block, Red", "2", "firebrigade.png", "Responders (OpenStreetMap)"
    ),
    "osm-supply": _spec("Supply", "Shopping Center", "3", "shopping.png", "Supply (OpenStreetMap)"),
    "osm-shelter-candidates": _spec(
        "Shelter candidates",
        "City Hall",
        "4",
        "townhall.png",
        f"Shelter candidates ({SHELTER_NOTE})",
    ),
    "osm-transport": _spec("Transport", "Airport", "5", "airport.png", "Transport (OpenStreetMap)"),
    "osm-power": _spec("Power", "Danger", "6", "danger.png", "Power (OpenStreetMap)"),
    "osm-telecom": _spec(
        "Telecom masts", "Tall Tower", "7", "communication.png", "Telecom masts (OpenStreetMap)"
    ),
    "osm-water": _spec("Water", "Water", "8", "drinking_water.png", "Water (OpenStreetMap)"),
    "faa-airports": _spec(
        "Airports and heliports", "Airport", "9", "airport.png", "Airports (FAA NASR)"
    ),
    "eia-plants": _spec("Power plants", "Danger", "a", "danger.png", "Power plants (EIA-860M)"),
    "wri-plants": _spec("Power plants", "Danger", "b", "danger.png", "Power plants (WRI)"),
    "fcc-towers": _spec("Towers", "Tall Tower", "c", "tower.png", "Towers (FCC ASR)"),
    "nwr": _spec("NOAA Weather Radio", "Information", "d", "information.png", "NOAA Weather Radio"),
}


def osm_layer_name(key: str, day: date) -> str:
    """``Medical (OpenStreetMap, ODbL, 2026-09-30)``; the shelter candidates
    carry the ruling's words in the name itself."""
    title = OSM_LAYERS[key].title
    if key == "shelter-candidates":
        return f"{title} (OpenStreetMap, ODbL, {day.isoformat()}; {SHELTER_NOTE})"
    return f"{title} (OpenStreetMap, ODbL, {day.isoformat()})"


# --- points and layers ------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    """One place: its name (or what it is, when it has none), its kind,
    where it is, and the facts worth a description."""

    name: str
    kind: str
    lat: float
    lon: float
    details: tuple[str, ...] = ()

    def description(self, source: str) -> str:
        return "; ".join((self.kind, *self.details, f"Source: {source}"))


@dataclass(frozen=True)
class InfraLayer:
    layer_id: str
    name: str
    licence: str
    #: The short source the waypoints name, e.g. ``OpenStreetMap contributors, ODbL``.
    source: str
    day: date
    points: tuple[Point, ...] = field(default=())


@dataclass(frozen=True)
class Gathered:
    """What one import or fetch read, ready to write: the layers (one with
    no point is removed rather than written), and what the document
    reports. ``skipped`` is (reason, count, first numbers)."""

    route: str
    licences: tuple[str, ...]
    inputs: tuple[tuple[str, str, str], ...]
    read: int
    skipped: tuple[tuple[str, int, tuple[int, ...]], ...]
    layers: tuple[InfraLayer, ...]
    outside: int = 0
    merged: int = 0
    notes: tuple[str, ...] = ()


def skip_counts(
    skipped: Mapping[str, Sequence[int]], *, numbered: bool = True
) -> tuple[tuple[str, int, tuple[int, ...]], ...]:
    """Skips as (reason, count, the first five numbers, or none)."""
    return tuple(
        (reason, len(numbers), tuple(numbers[:5]) if numbered else ())
        for reason, numbers in skipped.items()
    )


# --- reading osmium's output -------------------------------------------------------


@dataclass(frozen=True)
class OsmRead:
    """Points per wanted layer, objects read and skips by reason (reading
    numbers, never OSM ids: an id is a place)."""

    points: dict[str, list[Point]]
    read: int
    skipped: dict[str, list[int]]


def _volts(text: str) -> str:
    out = []
    for value in text.split(";"):
        try:
            out.append(f"{float(value.strip()) / 1000:g} kV")
        except ValueError:
            continue
    return ", ".join(out)


def _details(key: str, kind: str, tags: Mapping[str, str]) -> tuple[str, ...]:
    """What is worth saying about one object, by layer."""
    out: list[str] = []

    def put(text: str) -> None:
        if text and text not in out:
            out.append(text)

    if kind == "hospital" and _has(tags, "emergency", ("yes",)):
        put("emergency department")
    if key == "supply":
        if tags.get("brand") and tags.get("name") and tags["brand"] != tags["name"]:
            put(f"brand {tags['brand']}")
        if _has(tags, "fuel:diesel", ("yes",)):
            put("diesel")
        if tags.get("capacity") and kind == "charging station":
            put(f"capacity {tags['capacity']}")
    if key in ("medical", "supply") and tags.get("opening_hours"):
        put(f"hours {tags['opening_hours']}")
    if key == "power":
        volts = _volts(tags.get("voltage", ""))
        if volts:
            put(f"voltage {volts}")
        for tag, label in (
            ("plant:source", "source"),
            ("plant:output:electricity", "output"),
        ):
            if tags.get(tag):
                put(f"{label} {tags[tag]}")
    if key == "transport":
        for tag, label in (("icao", "ICAO"), ("faa", "FAA"), ("iata", "IATA")):
            if tags.get(tag):
                put(f"{label} {tags[tag]}")
    if key == "telecom":
        for tag, label in (
            ("communication:mobile_phone", "mobile phone"),
            ("communication:radio", "radio"),
            ("communication:television", "television"),
        ):
            if _has(tags, tag, ("yes",)):
                put(label)
        if tags.get("height"):
            put(f"height {tags['height']}")
    if key != "supply" and key != "shelter-candidates" and tags.get("operator"):
        put(f"operator {tags['operator']}")
    if key == "shelter-candidates":
        put(SHELTER_NOTE)
    return tuple(out)


def _display(kind: str, tags: Mapping[str, str]) -> str:
    name = " ".join((tags.get("name") or tags.get("brand") or "").split())
    return name or kind[:1].upper() + kind[1:]


def read_osm_xml(text: str, *, wanted: Sequence[str]) -> OsmRead:
    """OSM XML as ``osmium tags-filter -f osm`` writes it: matched objects
    and what they reference. A node is placed where it is, a way at the mean
    of its distinct nodes, a relation at the mean of its member nodes and
    its member ways' nodes."""
    upper = text.upper()  # D-064's rule: no OSM file needs either
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise InfraInputError("XML with a DOCTYPE or ENTITY declaration is refused")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise InfraInputError(f"osmium's output does not parse: {exc}") from None
    nodes: dict[str, tuple[float, float]] = {}
    ways: dict[str, list[str]] = {}
    for element in root:
        if element.tag == "node":
            where = _position(element.get("lat"), element.get("lon"))
            if where is not None:
                nodes[element.get("id", "")] = where
        elif element.tag == "way":
            refs = [nd.get("ref", "") for nd in element.iter("nd")]
            ways[element.get("id", "")] = list(dict.fromkeys(refs))
    layers = {key: OSM_LAYERS[key] for key in wanted}
    points: dict[str, list[Point]] = {key: [] for key in wanted}
    skipped: dict[str, list[int]] = {}
    read = 0
    for element in root:
        if element.tag not in ("node", "way", "relation"):
            continue
        tags = {t.get("k", ""): t.get("v", "") for t in element.iter("tag")}
        if not tags:
            continue
        hits = [
            (key, kind)
            for key, layer in layers.items()
            for kind in [next((k for k in layer.kinds if k.matches(tags)), None)]
            if kind is not None
        ]
        if not hits:
            continue  # a referenced node, or an object of a layer not asked for
        read += 1
        where = _place(element, nodes, ways)
        if where is None:
            skipped.setdefault(NO_POSITION, []).append(read)
            continue
        for key, kind in hits:
            points[key].append(
                Point(
                    _display(kind.label, tags),
                    kind.label,
                    where[0],
                    where[1],
                    _details(key, kind.label, tags),
                )
            )
    return OsmRead(points, read, skipped)


def _mean(points: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    if not points:
        return None
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _place(
    element: ET.Element,
    nodes: Mapping[str, tuple[float, float]],
    ways: Mapping[str, list[str]],
) -> tuple[float, float] | None:
    if element.tag == "node":
        return nodes.get(element.get("id", ""))
    if element.tag == "way":
        own = ways.get(element.get("id", ""), [])
        return _mean([nodes[r] for r in own if r in nodes])
    refs: list[str] = []
    for member in element.iter("member"):
        ref = member.get("ref", "")
        if member.get("type") == "node":
            refs.append(ref)
        elif member.get("type") == "way":
            refs += ways.get(ref, [])
    return _mean([nodes[r] for r in dict.fromkeys(refs) if r in nodes])


def osmium_argv(pbf: Path, out: Path, wanted: Sequence[str]) -> list[str]:
    """One ``osmium tags-filter`` over *pbf* for every wanted layer's keys,
    one expression per key and layer in the table's order."""
    expressions: list[str] = []
    for key in wanted:
        by_key: dict[str, list[str]] = {}
        for kind in OSM_LAYERS[key].kinds:
            for tag, values in kind.tags:
                known = by_key.setdefault(tag, [])
                known += [v for v in values if v not in known]
        for tag, joined in by_key.items():
            expression = f"nwr/{tag}={','.join(joined)}"
            if expression not in expressions:
                expressions.append(expression)
    return [
        "osmium",
        "tags-filter",
        str(pbf),
        *expressions,
        "-f",
        "osm",
        "-o",
        str(out),
        "--overwrite",
    ]


Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def filter_extract(
    pbf: Path,
    scratch: Path,
    wanted: Sequence[str],
    *,
    run: Runner | None = None,
    label: str = "the extract",
) -> OsmRead:
    """The wanted layers' objects in one region extract, filtered by osmium
    as the operator into *scratch*. Every message names the extract by
    *label*, never by its file: a region's name says where the operator is
    (D-057), and these messages get pasted (D-074's final review)."""
    out = scratch / "extract.infra.osm"
    try:
        result = (run or _run)(osmium_argv(pbf, out, wanted))
    except FileNotFoundError:
        raise InfraInputError(
            "osmium is not installed: it comes from the osmium-tool package, which "
            "`hammunition install osm-navit` installs (or `sudo apt install osmium-tool`)"
        ) from None
    if result.returncode != 0:
        said = result.stderr.strip().replace(str(pbf), label).replace(pbf.name, label)
        said = said.replace(pbf.name.removesuffix(".osm.pbf"), label)
        raise InfraInputError(
            f"osmium tags-filter failed on {label} (exit {result.returncode}): {said[:300]}"
        )
    try:
        text = out.read_text(encoding="utf-8")
    except OSError as exc:
        raise InfraInputError(
            f"osmium wrote nothing readable for {label}: {exc.strerror or 'unreadable'}"
        ) from None
    finally:
        out.unlink(missing_ok=True)
    return read_osm_xml(text, wanted=wanted)


# --- the station's regions -------------------------------------------------------


def extracts_dir(prefix: Path) -> Path:
    return prefix / "share" / "hammunition" / "data" / "osm-regions"


def region_boxes(prefix: Path) -> tuple[list[Box], list[str]]:
    """Each installed extract's header box (D-057's regions, as ``--from-osm``
    reads them), and a note for each one left out, named by its number."""
    pbfs = sorted(extracts_dir(prefix).glob("*.osm.pbf"))
    boxes: list[Box] = []
    notes: list[str] = []
    for number, path in enumerate(pbfs, start=1):
        label = f"region extract {number} of {len(pbfs)}"
        try:
            bbox = osm_pbf.header_bbox(path)
        except (OSError, osm_pbf.OsmPbfError):
            notes.append(f"{label} could not be read; left out")
            continue
        if bbox is None:
            notes.append(f"{label} has no bounding box in its header; left out")
            continue
        left, right, top, bottom = bbox
        boxes.append((left, bottom, right, top))
    return boxes, notes


def in_boxes(lat: float, lon: float, boxes: Sequence[Box], pad: float = 0.0) -> bool:
    """Whether (*lat*, *lon*) is in any box, each grown by *pad* degrees."""
    for west, south, east, north in boxes:
        if not south - pad <= lat <= north + pad:
            continue
        if west <= east:
            if west - pad <= lon <= east + pad:
                return True
        elif lon >= west - pad or lon <= east + pad:
            return True
    return False


# --- writing -----------------------------------------------------------------------


def _layer_spec(layer_id: str) -> LayerSpec:
    try:
        return LAYERS[layer_id]
    except KeyError:
        raise ValueError(
            f"no infrastructure layer {layer_id!r}; the layers are {', '.join(LAYERS)}"
        ) from None


def gpx_text(layer: InfraLayer) -> str:
    """GPX 1.1: the layer and its licence in ``<metadata>``, one ``<wpt>``
    per point with the layer's QMapShack symbol."""
    spec = _layer_spec(layer.layer_id)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<gpx version="1.1" creator="hammunition" xmlns="{GPX_NS}">',
        f"  <metadata><name>{escape(layer.name)}</name>"
        f"<desc>{escape(layer.licence)}</desc></metadata>",
    ]
    for point in layer.points:
        out.append(
            f'  <wpt lat="{point.lat:.5f}" lon="{point.lon:.5f}">'
            f"<name>{escape(point.name)}</name>"
            f"<desc>{escape(point.description(layer.source))}</desc>"
            f"<src>{escape(layer.source)}</src>"
            f"<sym>{escape(spec.symbol)}</sym><type>{escape(layer.layer_id)}</type></wpt>"
        )
    out.append("</gpx>")
    return "\n".join(out) + "\n"


def _navit_label(text: str) -> str:
    return "".join(ch for ch in text.replace('"', "'") if ch.isprintable())


def navit_text(layer: InfraLayer) -> str:
    """Navit's textfile map, one line a point, in the layer's own type."""
    spec = _layer_spec(layer.layer_id)
    return "".join(
        f'{p.lon:.5f} {p.lat:.5f} type={spec.navit_type} label="{_navit_label(p.name)}" '
        f'icon_src="{spec.navit_icon}"\n'
        for p in layer.points
    )


def geojson_text(layer: InfraLayer) -> str:
    """The layer as a GeoJSON FeatureCollection for the browser map, its
    name, licence and id as foreign members (RFC 7946 §6.1)."""
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(p.lon, 5), round(p.lat, 5)]},
            "properties": {
                "name": p.name,
                "kind": p.kind,
                "description": p.description(layer.source),
            },
        }
        for p in layer.points
    ]
    data = {
        "type": "FeatureCollection",
        "name": layer.name,
        "licence": layer.licence,
        "layer": layer.layer_id,
        "features": features,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


# --- the store ---------------------------------------------------------------------


def overlay_dir(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    """``$XDG_DATA_HOME/hammunition/overlays/infra``: the operator's own."""
    return overlays_root(environ, home) / "infra"


def layer_files(layer_id: str) -> tuple[str, str, str, str]:
    """The four file names of *layer_id*, in :data:`SUFFIXES` order."""
    _layer_spec(layer_id)
    gpx, poi, navit, geojson = (f"infra-{layer_id}{suffix}" for suffix in SUFFIXES)
    return gpx, poi, navit, geojson


def write_layer(where: Path, layer: InfraLayer) -> tuple[Path, ...]:
    """The layer's four files in *where*, each written to a temporary name
    and renamed over the old one, mode 0600; on any failure nothing of this
    write is left. Every other layer stays as it is."""
    if not layer.points:
        raise ValueError(f"{layer.layer_id}: no point to write")
    spec = _layer_spec(layer.layer_id)
    names = layer_files(layer.layer_id)
    _own_dir(where)
    texts = {
        names[0]: gpx_text(layer),
        names[2]: navit_text(layer),
        names[3]: geojson_text(layer),
    }
    staged: list[tuple[Path, Path]] = []
    try:
        for name in names:
            temporary = _temporary(where, name)
            staged.append((temporary, where / name))
            if name in texts:
                temporary.write_text(texts[name], encoding="utf-8")
            else:
                temporary.unlink()  # sqlite creates it afresh
                write_poi_points(
                    temporary,
                    layer.name,
                    layer.licence,
                    layer.day,
                    [
                        PoiPoint(
                            p.lat,
                            p.lon,
                            p.name,
                            p.description(layer.source),
                            f"hammunition:infra={layer.layer_id}",
                        )
                        for p in layer.points
                    ],
                    category=spec.category,
                )
            os.chmod(temporary, 0o600)
        for temporary, final in staged:
            os.replace(temporary, final)
    except BaseException:
        for temporary, _ in staged:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
        raise
    return tuple(where / name for name in names)


def present_layers(where: Path) -> tuple[str, ...]:
    """The layers whose GPX is in *where*, in :data:`LAYERS` order."""
    return tuple(i for i in LAYERS if (where / layer_files(i)[0]).is_file())


def layer_paths(where: Path, index: int) -> list[Path]:
    """Every present layer's file *index* (1, the ``.poi``; 2, the Navit
    textfile; 3, the GeoJSON), in layer order."""
    paths = [where / layer_files(i)[index] for i in LAYERS]
    return [p for p in paths if p.is_file()]


_LEFTOVER = re.compile(r"^\.infra-")


def remove_layer(where: Path, layer_id: str | None) -> tuple[Path, ...]:
    """Delete *layer_id*'s files, or every layer's when it is None, and
    *where* when it is left empty; the files removed, in order. Anything
    else in the directory stays."""
    if where.is_symlink():
        raise OSError(f"{where} is a symbolic link; left as it is")
    ids = [layer_id] if layer_id is not None else list(LAYERS)
    names = [n for i in ids for n in layer_files(i)]
    removed: list[Path] = []
    for name in names:
        path = where / name
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
            removed.append(path)
    # What a write killed between its writes and its renames leaves.
    with contextlib.suppress(FileNotFoundError):
        for leftover in where.iterdir():
            if _LEFTOVER.match(leftover.name) and any(
                leftover.name.startswith(f".{name}.") for name in names
            ):
                with contextlib.suppress(FileNotFoundError):
                    leftover.unlink()
    with contextlib.suppress(FileNotFoundError, OSError):
        where.rmdir()  # only when empty
    return tuple(removed)
