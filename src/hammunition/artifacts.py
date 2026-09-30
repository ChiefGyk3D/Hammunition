# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every remote data artifact the engine would fetch for a selection, with
no station and no install.  D-070.

``hammunition artifacts`` is Hammunition Bunker's one source of what to
mirror, so this resolves exactly as the plan does -- the same Geofabrik pins,
freshness and fallback (:func:`hammunition.geofabrik.resolve`), the same
outlines, tile list and tile pins (:mod:`hammunition.copernicus`) -- with
three differences, each on purpose:

- the selection is given, never read from station config;
- nothing installed on this machine is read, so the listing is the same on
  every machine (the plan skips what is installed; a mirror wants it all);
- a region or tile that cannot be resolved is an entry saying why, not a
  refusal of the whole listing.

Pure apart from the injected probes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from .backends.data import data_name
from .copernicus import (
    CopernicusError,
    TileProbe,
    load_tile_list,
    parse_poly,
    resolve_tile,
    select,
    squares_touching,
)
from .copernicus import load_pins as load_tile_pins
from .geofabrik import BASE, GeofabrikError, Probe
from .geofabrik import load_pins as load_region_pins
from .geofabrik import resolve as resolve_region
from .interface.artifacts import ArtifactEntry
from .manifest.schema import DataInstall, DemTilesInstall, PackageManifest, RegionalDataInstall
from .terrain_plan import PINS as TILE_PINS
from .terrain_plan import TILE_LIST

__all__ = ["SelectionError", "fetching_units", "list_artifacts", "select_units"]

FETCHING = (DataInstall, RegionalDataInstall, DemTilesInstall)
REGION_PINS = Path("data") / "geofabrik-pins.yaml"
NO_REGIONS = (
    "no map regions given: pass --map-regions with Geofabrik region paths "
    "(`hammunition maps regions` lists them)"
)


class SelectionError(Exception):
    """The selection names something that cannot be listed."""


def _blocks(manifest: PackageManifest) -> list[DataInstall | RegionalDataInstall | DemTilesInstall]:
    return [b.install for b in manifest.install if isinstance(b.install, FETCHING)]


def fetching_units(catalog: Mapping[str, PackageManifest]) -> tuple[str, ...]:
    """Every unit with a ``data``, ``osm-regions`` or ``dem-tiles`` block, sorted."""
    return tuple(sorted(name for name, m in catalog.items() if _blocks(m)))


def select_units(
    catalog: Mapping[str, PackageManifest], requested: Sequence[str]
) -> tuple[str, ...]:
    """*requested* in order, once each, or every fetching unit when empty.
    A name not in the catalog, or naming a unit that fetches no data, is
    refused by name: the operator typed it (D-039)."""
    if not requested:
        return fetching_units(catalog)
    unknown = [n for n in requested if n not in catalog]
    idle = [n for n in requested if n in catalog and not _blocks(catalog[n])]
    problems = []
    if unknown:
        problems.append(f"not in the catalog: {', '.join(unknown)}")
    if idle:
        problems.append(
            f"fetches no remote data artifact (not a data, osm-regions or dem-tiles unit): "
            f"{', '.join(idle)}"
        )
    if problems:
        raise SelectionError("; ".join(problems))
    return tuple(dict.fromkeys(requested))


def _licence(text: str) -> str:
    return " ".join(text.split())


def _deferred(unit: str, name: str | None, licence: str, reason: str) -> ArtifactEntry:
    return ArtifactEntry(
        unit=unit,
        name=name,
        url=None,
        check=None,
        digest=None,
        checksum_url=None,
        size=None,
        licence=licence,
        deferred=reason,
    )


def _data(unit: str, blocks: Sequence[DataInstall]) -> list[ArtifactEntry]:
    out: dict[str, ArtifactEntry] = {}
    for block in blocks:
        for artifact in block.artifacts:
            name = data_name(artifact)
            entry = ArtifactEntry(
                unit=unit,
                name=name,
                url=artifact.url,
                check="sha256",
                digest=artifact.sha256,
                checksum_url=None,
                size=artifact.size,
                licence=_licence(block.licence),
                deferred=None,
            )
            seen = out.get(name)
            if seen is None:
                out[name] = entry
            elif seen.digest != entry.digest:
                # Two install blocks, one name, different bytes: a mirror has
                # one path for both, so the second cannot be listed.
                out[f"{name}\0{artifact.sha256}"] = _deferred(
                    unit,
                    name,
                    entry.licence,
                    f"another artifact of {unit} has the same name and different bytes "
                    f"({seen.url}); a mirror serves one file per name",
                )
    return list(out.values())


def _regions(
    unit: str,
    licence: str,
    regions: Sequence[str],
    freshness: str,
    *,
    today: date,
    catalog_root: Path,
    probe: Probe,
) -> list[ArtifactEntry]:
    pins_path = catalog_root / REGION_PINS
    pins = load_region_pins(pins_path) if pins_path.is_file() else {}
    out: list[ArtifactEntry] = []
    for region in regions:
        try:
            found = resolve_region(region, freshness, today=today, pins=pins, probe=probe)
        except (GeofabrikError, OSError) as exc:
            out.append(_deferred(unit, region, licence, str(exc)))
            continue
        out.append(
            ArtifactEntry(
                unit=unit,
                name=region,
                url=found.url,
                check="sha256" if found.sha256 else "md5-publisher",
                digest=found.sha256 or found.md5,
                checksum_url=None if found.sha256 else f"{found.url}.md5",
                size=found.size,
                licence=licence,
                deferred=None,
            )
        )
    return out


def _tiles(
    unit: str,
    licence: str,
    regions: Sequence[str],
    *,
    catalog_root: Path,
    region_probe: Probe,
    tile_probe: TileProbe,
) -> list[ArtifactEntry]:
    try:
        tile_list = load_tile_list(catalog_root / TILE_LIST)
        pins_path = catalog_root / TILE_PINS
        pins = load_tile_pins(pins_path) if pins_path.is_file() else {}
    except (CopernicusError, OSError) as exc:
        return [_deferred(unit, None, licence, f"the carried tile data cannot be read: {exc}")]
    out: list[ArtifactEntry] = []
    wanted: set[str] = set()
    for region in regions:
        try:
            outer, holes = parse_poly(region_probe.text(f"{BASE}/{region}.poly"))
            tiles, _unpublished = select(squares_touching(outer, holes), tile_list)
        except (GeofabrikError, CopernicusError, OSError) as exc:
            out.append(_deferred(unit, region, licence, f"its outline could not be read: {exc}"))
            continue
        wanted.update(tiles)
    for name in sorted(wanted):
        try:
            tile = resolve_tile(name, pins=pins, probe=tile_probe)
        except (CopernicusError, OSError) as exc:
            out.append(_deferred(unit, name, licence, str(exc)))
            continue
        out.append(
            ArtifactEntry(
                unit=unit,
                name=name,
                url=tile.url,
                check="sha256" if tile.sha256 else "etag-md5",
                digest=tile.sha256 or tile.md5,
                checksum_url=None if tile.sha256 else tile.url,
                size=tile.size,
                licence=licence,
                deferred=None,
            )
        )
    return out


def list_artifacts(
    units: Sequence[str],
    *,
    regions: Sequence[str],
    freshness: str,
    catalog: Mapping[str, PackageManifest],
    catalog_root: Path,
    today: date,
    region_probe: Probe,
    tile_probe: TileProbe,
) -> tuple[ArtifactEntry, ...]:
    """Every artifact of *units* for *regions* at *freshness*, in unit order."""
    out: list[ArtifactEntry] = []
    for unit in units:
        blocks = _blocks(catalog[unit])
        data = [b for b in blocks if isinstance(b, DataInstall)]
        if data:
            out.extend(_data(unit, data))
            continue
        block = blocks[0]
        assert not isinstance(block, DataInstall)
        licence = _licence(block.licence)
        if not regions:
            out.append(_deferred(unit, None, licence, NO_REGIONS))
        elif isinstance(block, RegionalDataInstall):
            out.extend(
                _regions(
                    unit,
                    licence,
                    regions,
                    freshness,
                    today=today,
                    catalog_root=catalog_root,
                    probe=region_probe,
                )
            )
        else:
            out.extend(
                _tiles(
                    unit,
                    licence,
                    regions,
                    catalog_root=catalog_root,
                    region_probe=region_probe,
                    tile_probe=tile_probe,
                )
            )
    return tuple(out)
