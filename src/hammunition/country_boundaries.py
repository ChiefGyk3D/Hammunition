# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Closed country boundaries for maptool, from Natural Earth.  D-057 amendment.

maptool files a town under a country only when the town lies inside that
country's ``admin_level=2`` boundary relation, tagged with ``ISO3166-1``
(``maptool/boundaries.c``, ``process_boundaries_setup``). A Geofabrik
sub-country extract carries only the in-region pieces of that relation, so
the polygon is open, maptool logs "Broken country polygon", and almost every
town is dropped from the search index -- about a dozen index items for a
US-state-sized region that draws a few thousand places (2026-09-28). maptool has no option to read
a boundary from anywhere else.

This module writes the boundary maptool needs as OSM XML, from Natural
Earth's 1:10m admin-0 countries (the ``country-boundaries`` data unit): per
country, one relation tagged ``type=boundary``, ``boundary=administrative``,
``admin_level=2``, ``name`` and ``ISO3166-1``, whose members are closed
rings of new nodes and ways -- outer rings, and inner rings where Natural
Earth has a hole (Lesotho in South Africa). Every id starts above
:data:`FIRST_ID`, nine quadrillion, far above any id OpenStreetMap has
issued, so a merged file never has two objects with one id. The standard
library only: ``json`` in, a string out, nothing executed.

A country is found by Natural Earth's ``ISO_A2_EH``, not ``ISO_A2``: the
latter is ``-99`` for France and Norway, among others. Every feature
carrying the code is one relation, so France's relation includes its
overseas parts.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import quoteattr

from .manifest.schema import DataInstall, PackageManifest

#: Every id written here is above this. OSM's ids are in the tens of
#: billions (2026); nine quadrillion leaves them room for a very long time
#: and still fits a signed 64-bit id, which osmium and maptool both use.
FIRST_ID = 9 * 10**15
#: OpenStreetMap caps a way at 2,000 nodes; a long ring is split into ways of
#: at most this many segments, each sharing its end node with the next.
WAY_SEGMENTS = 1900
SOURCE_TAG = "Natural Earth 1:10m admin-0 countries, v5.1.2"

Ring = tuple[tuple[float, float], ...]
"""(lon, lat) positions, not repeating the first at the end."""
Polygon = tuple[Ring, ...]
"""The outer ring, then any holes."""


class CountryBoundaryError(Exception):
    """The Natural Earth file is not the shape this module reads."""


@dataclass(frozen=True)
class BoundarySource:
    """The installed boundary file and what the plan says about it."""

    path: Path
    url: str
    size: int
    sha256: str
    licence: str
    title: str = "Natural Earth 1:10m admin-0 countries"


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    polygons: tuple[Polygon, ...]


@dataclass(frozen=True)
class Boundaries:
    """One region's synthesised boundaries."""

    xml: str
    relations: Mapping[str, int]
    """ISO code -> the relation id written for it."""
    missing: tuple[str, ...]
    """Codes asked for that Natural Earth has no feature for."""


def boundary_source(manifest: PackageManifest, prefix: Path) -> BoundarySource:
    """Where *manifest*, the unit a ``derived`` block names in ``boundaries``,
    installs its boundary file, and what the plan says about it.

    The unit must be a ``data`` unit of exactly one ``.geojson`` file; any
    other shape is refused by name, at plan time, before anything converts.
    """
    blocks = [entry.install for entry in manifest.install]
    artifacts = [a for b in blocks if isinstance(b, DataInstall) for a in b.artifacts]
    if (
        len(blocks) != 1
        or not isinstance(blocks[0], DataInstall)
        or len(artifacts) != 1
        or artifacts[0].format != "file"
        or not (artifacts[0].install_as or "").endswith(".geojson")
    ):
        raise CountryBoundaryError(
            f"{manifest.name} is named as a country-boundary unit, and is not a data unit "
            f"of one .geojson file"
        )
    artifact, block = artifacts[0], blocks[0]
    assert artifact.install_as is not None  # checked above
    return BoundarySource(
        path=prefix / "share" / "hammunition" / "data" / manifest.name / artifact.install_as,
        url=artifact.url,
        size=artifact.size,
        sha256=artifact.sha256,
        licence=" ".join(block.licence.split()),
    )


def _code(properties: Mapping[str, object]) -> str | None:
    for key in ("ISO_A2_EH", "ISO_A2"):
        value = properties.get(key)
        if isinstance(value, str) and len(value) == 2 and value.isalpha() and value.isupper():
            return value
    return None


def _ring(raw: object, name: str) -> Ring:
    if not isinstance(raw, list):
        raise CountryBoundaryError(f"{name}: a ring is not a list of positions")
    points: list[tuple[float, float]] = []
    for position in raw:
        if (
            not isinstance(position, list)
            or len(position) < 2
            or not all(isinstance(v, int | float) for v in position[:2])
        ):
            raise CountryBoundaryError(f"{name}: {position!r} is not a [lon, lat] position")
        lon, lat = float(position[0]), float(position[1])
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise CountryBoundaryError(f"{name}: {position!r} is off the globe")
        points.append((lon, lat))
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise CountryBoundaryError(f"{name}: a ring has fewer than three distinct positions")
    return tuple(points)


def _polygons(geometry: object, name: str) -> tuple[Polygon, ...]:
    if not isinstance(geometry, dict):
        raise CountryBoundaryError(f"{name}: no geometry")
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    raw: object
    if kind == "Polygon":
        raw = [coordinates]
    elif kind == "MultiPolygon":
        raw = coordinates
    else:
        raise CountryBoundaryError(f"{name}: geometry {kind!r} is not a Polygon or MultiPolygon")
    if not isinstance(raw, list) or not all(isinstance(p, list) and p for p in raw):
        raise CountryBoundaryError(f"{name}: malformed {kind} coordinates")
    return tuple(tuple(_ring(ring, name) for ring in polygon) for polygon in raw)


def read_countries(text: str) -> dict[str, Country]:
    """ISO 3166-1 alpha-2 code -> the country, from Natural Earth's GeoJSON.

    Features with no usable code (Somaliland, the Cyprus buffer zone, Bir
    Tawil: ``-99`` in both fields) name no country and are skipped. Features
    sharing a code are one country; its name is taken from the feature that
    is the country itself (``ADM0_A3`` equal to ``ISO_A3_EH``), else the first.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CountryBoundaryError(f"not valid JSON: {exc}") from exc
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        raise CountryBoundaryError("not a GeoJSON FeatureCollection")
    names: dict[str, str] = {}
    main: set[str] = set()
    parts: dict[str, list[Polygon]] = {}
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            raise CountryBoundaryError(f"a feature has no properties: {str(feature)[:80]}")
        code = _code(properties)
        if code is None:
            continue
        name = str(properties.get("NAME") or properties.get("ADMIN") or code)
        parts.setdefault(code, []).extend(_polygons(feature.get("geometry"), name))
        is_main = properties.get("ADM0_A3") == properties.get("ISO_A3_EH")
        if code not in names or (is_main and code not in main):
            names[code] = name
        if is_main:
            main.add(code)
    if not parts:
        # A release that renamed its code fields reads as no countries at all,
        # and every region would convert unmerged (review M-9).
        raise CountryBoundaryError("no feature carries an ISO_A2_EH or ISO_A2 country code")
    return {code: Country(code, names[code], tuple(parts[code])) for code in sorted(parts)}


def _chunks(ids: Sequence[int]) -> Iterable[Sequence[int]]:
    """A closed ring's node ids (last == first) as ways sharing end nodes."""
    for start in range(0, len(ids) - 1, WAY_SEGMENTS):
        yield ids[start : start + WAY_SEGMENTS + 1]


def boundary_xml(countries: Mapping[str, Country], codes: Sequence[str]) -> Boundaries:
    """OSM XML holding one closed ``admin_level=2`` relation per code.

    Written in id order -- nodes, then ways, then relations, each ascending
    -- which is the order ``osmium merge`` needs its inputs sorted in.
    """
    node_lines: list[str] = []
    way_lines: list[str] = []
    relation_lines: list[str] = []
    relations: dict[str, int] = {}
    missing: list[str] = []
    node_id = way_id = relation_id = FIRST_ID
    for code in codes:
        country = countries.get(code)
        if country is None:
            if code not in missing:
                missing.append(code)
            continue
        if code in relations:
            continue
        members: list[tuple[int, str]] = []
        for polygon in country.polygons:
            for index, ring in enumerate(polygon):
                ids: list[int] = []
                for lon, lat in ring:
                    node_id += 1
                    ids.append(node_id)
                    node_lines.append(
                        f' <node id="{node_id}" version="1" lat="{lat:.7f}" lon="{lon:.7f}"/>'
                    )
                ids.append(ids[0])  # closed on the same node
                role = "outer" if index == 0 else "inner"
                for chunk in _chunks(ids):
                    way_id += 1
                    members.append((way_id, role))
                    way_lines.append(f' <way id="{way_id}" version="1">')
                    way_lines.extend(f'  <nd ref="{ref}"/>' for ref in chunk)
                    way_lines.append(" </way>")
        relation_id += 1
        relations[code] = relation_id
        relation_lines.append(f' <relation id="{relation_id}" version="1">')
        relation_lines.extend(
            f'  <member type="way" ref="{ref}" role="{role}"/>' for ref, role in members
        )
        for key, value in (
            ("type", "boundary"),
            ("boundary", "administrative"),
            ("admin_level", "2"),
            ("name", country.name),
            ("ISO3166-1", code),
            ("source", SOURCE_TAG),
        ):
            relation_lines.append(f"  <tag k={quoteattr(key)} v={quoteattr(value)}/>")
        relation_lines.append(" </relation>")
    xml = "\n".join(
        [
            "<?xml version='1.0' encoding='UTF-8'?>",
            '<osm version="0.6" generator="hammunition">',
            *node_lines,
            *way_lines,
            *relation_lines,
            "</osm>",
            "",
        ]
    )
    return Boundaries(xml=xml, relations=relations, missing=tuple(missing))
