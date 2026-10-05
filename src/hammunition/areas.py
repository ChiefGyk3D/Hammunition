# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The area of operations: what is loaded against what is drawn.  D-082.

An operator loads every state and region on the possible roster at home, and
on arrival makes *one* of them the active one. Loading and drawing are two
things: the files stay on disk, and ``active_areas`` in the station config
says which of them QMapShack, Navit and the browser map are told about.

An **area** is a US state code (``OH``; a RepeaterBook ``state_id`` such as
``CA01`` elsewhere) or a map region name (``north-america/us/ohio``). One state
and one region can be the same ground: ``OH`` and ``north-america/us/ohio`` are
tied through the postal-code table, so ``maps activate OH`` draws Ohio's
repeaters *and* Ohio's map. Nothing else is inferred: a region that merely
contains a state (a Geofabrik ``midwest``) is activated by its own name.

``active_areas`` unset means everything loaded is active, which is what the
engine did before the switch; an empty list means nothing is. A layer that
belongs to no area (the operator's own import, ACMA, OpenStreetMap's repeaters,
an infrastructure theme) is always active.

QMapShack reads a *directory* of ``.poi`` files, so a subset is a directory of
symbolic links to the active areas' files, ``overlays/active-poi``. The links
are derived state, written and removed only by this module, and the files they
point at are never touched.

Infrastructure layers are kept per region (D-075, amended for #327): the file
name carries the extract's slug (``infra-osm-medical-north-america-us-ohio.poi``)
and :func:`hammunition.infra.layer_area` names it, so the rule here takes
exactly the active regions' files. A merged layer, written before the split or
with ``--merged``, has no area and is always active."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .repeaterbook import US_STATE_NAMES
from .repeaters import is_area_code
from .station import Station

__all__ = [
    "Active",
    "PoiLinks",
    "plan_poi_links",
    "poi_links_dir",
    "state_region",
    "sync_poi_links",
]

#: Geofabrik's path to a US state's extract.
US_PREFIX = "north-america/us/"


def _slug(region: str) -> str:
    return region.replace("/", "-")


def state_region(code: str) -> str | None:
    """The map region that is the same ground as a US state code, or None
    for any other area code."""
    name = US_STATE_NAMES.get(code)
    return None if name is None else US_PREFIX + name.replace(" ", "-")


@dataclass(frozen=True)
class Active:
    """The active areas, as the station holds them. ``tokens`` None is
    everything; empty is nothing."""

    tokens: tuple[str, ...] | None = None

    @classmethod
    def from_station(cls, station: Station) -> Active:
        return cls(station.active_areas)

    @property
    def everything(self) -> bool:
        return self.tokens is None

    def state(self, code: str) -> bool:
        """Whether the state (or ``state_id``) *code* is active, directly or
        through the region that is the same ground."""
        if self.tokens is None or code in self.tokens:
            return True
        region = state_region(code)
        if region is None:
            return False
        name = region.removeprefix(US_PREFIX)
        return any(t in (region, name) for t in self.tokens)

    def area(self, area: str | None, universe: Sequence[str] = ()) -> bool:
        """A layer's area: None (it belongs to no area) is always active; a
        state code is a state; anything else is a region path or file slug."""
        if area is None or self.tokens is None:
            return True
        if is_area_code(area):
            return self.state(area)
        return self.region_slug(_slug(area), universe)

    def region_slugs(self, universe: Sequence[str] = ()) -> frozenset[str] | None:
        """The file-name slugs (``north-america-us-ohio``) of the active map
        regions, or None for everything. *universe* is the station's map
        regions, which a bare word (``ohio``) is looked up in."""
        if self.tokens is None:
            return None
        slugs: set[str] = set()
        for token in self.tokens:
            if "/" in token:
                slugs.add(_slug(token))
                continue
            region = state_region(token)
            if region is not None:  # a code
                slugs.add(_slug(region))
                continue
            slugs.update(_slug(r) for r in universe if r.rsplit("/", 1)[-1] == token)
            slugs.add(token)  # a one-word region path (a country: ``monaco``)
        return frozenset(slugs)

    def region(self, region: str, universe: Sequence[str] = ()) -> bool:
        slugs = self.region_slugs(universe)
        return True if slugs is None else _slug(region) in slugs

    def region_slug(self, slug: str, universe: Sequence[str] = ()) -> bool:
        slugs = self.region_slugs(universe)
        return True if slugs is None else slug in slugs

    def unloaded(self, states: Sequence[str], regions: Sequence[str]) -> tuple[str, ...]:
        """The tokens that match nothing loaded: *states* are the state codes
        with layers on disk and *regions* the region names (or file slugs) on
        disk. They are accepted all the same: the operator may fetch them next."""
        if self.tokens is None:
            return ()
        on_disk = {_slug(r) for r in regions}
        out = []
        for token in self.tokens:
            if token in states or Active((token,)).region_slugs(regions) & on_disk:  # type: ignore[operator]
                continue
            if _region_state(token) in states:
                continue
            out.append(token)
        return tuple(out)


def _region_state(token: str) -> str | None:
    """The state code that is the same ground as the region *token*."""
    for code in US_STATE_NAMES:
        region = state_region(code)
        if region is not None and token in (region, region.removeprefix(US_PREFIX)):
            return code
    return None


# --- QMapShack's directory of links --------------------------------------------------------


def poi_links_dir(overlays: Path) -> Path:
    """``overlays/active-poi``: what QMapShack's ``poiPaths`` names while a
    subset is active."""
    return overlays / "active-poi"


@dataclass(frozen=True)
class PoiLinks:
    """What the links directory should hold, and what it holds."""

    directory: Path
    wanted: dict[str, Path]  # link name -> the .poi file it points at
    add: tuple[str, ...]
    drop: tuple[str, ...]
    kept: tuple[str, ...]


def _poi_targets(
    repeater_dir: Path, infra_dir: Path, active: Active, universe: Sequence[str] = ()
) -> dict[str, Path]:
    from . import infra, repeaters

    found: dict[str, Path] = {}
    for layer_id in repeaters.known_layers(repeater_dir):
        poi = repeater_dir / repeaters.layer_files(layer_id)[1]
        if poi.is_file() and active.area(repeaters.layer_area(layer_id)):
            found[poi.name] = poi
    for layer_id in infra.known_layers(infra_dir):
        poi = infra_dir / infra.layer_files(layer_id)[1]
        if poi.is_file() and active.area(infra.layer_area(layer_id), universe):
            found[poi.name] = poi
    return found


def plan_poi_links(
    overlays: Path,
    repeater_dir: Path,
    infra_dir: Path,
    active: Active,
    universe: Sequence[str] = (),
) -> PoiLinks:
    """What :func:`sync_poi_links` would do. Reads, writes nothing. With
    everything active no link is wanted: QMapShack is pointed at the layer
    directories themselves, as before the switch."""
    directory = poi_links_dir(overlays)
    wanted = {} if active.everything else _poi_targets(repeater_dir, infra_dir, active, universe)
    have: dict[str, str] = {}
    with contextlib.suppress(OSError):
        for entry in directory.iterdir():
            if entry.is_symlink():
                have[entry.name] = os.readlink(entry)
    keep = tuple(n for n, target in wanted.items() if have.get(n) == str(target))
    add = tuple(n for n in wanted if n not in keep)
    drop = tuple(n for n in have if n not in wanted)
    return PoiLinks(directory, wanted, add, drop, keep)


def sync_poi_links(plan: PoiLinks) -> None:
    """Make the links directory match *plan*. Only symbolic links are ever
    removed; a file somebody put there stays, and so does every ``.poi``
    a link pointed at."""
    directory = plan.directory
    if plan.wanted and not directory.exists():
        # A deliberate private mode: the links directory is the operator's alone. Semgrep
        # reads a suppression only on the line it covers, so the marker sits on each.
        directory.mkdir(parents=True, mode=0o700)  # nosemgrep
        # fmt: off
        os.chmod(directory, 0o700)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
        # fmt: on
    for name in (*plan.drop, *(n for n in plan.add if (directory / n).is_symlink())):
        with contextlib.suppress(FileNotFoundError):
            (directory / name).unlink()
    for name in plan.add:
        if (directory / name).exists():
            continue  # a real file in the way: left alone
        (directory / name).symlink_to(plan.wanted[name])
    if not plan.wanted:
        with contextlib.suppress(OSError):
            directory.rmdir()  # only when empty


# --- what is loaded -----------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedLayer:
    """One thing on disk for an area, as the engine measures it."""

    id: str
    kind: str  # repeaters, extract, navit, tiles
    rows: int | None
    size_bytes: int
    day: str | None
    files: tuple[str, ...]


@dataclass(frozen=True)
class LoadedArea:
    area: str
    kind: str  # state, region
    layers: tuple[LoadedLayer, ...]


#: A region's files under the data directory: unit, suffix, kind.
REGION_FILES = (
    ("osm-regions", ".osm.pbf", "extract"),
    ("osm-navit", ".bin", "navit"),
    ("osm-pmtiles", ".pmtiles", "tiles"),
)


def _day_of(path: Path) -> str:
    import datetime

    return datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()


def _size(paths: Sequence[Path]) -> int:
    total = 0
    for path in paths:
        with contextlib.suppress(OSError):
            total += path.stat().st_size
    return total


def collect(
    repeater_dir: Path, infra_dir: Path, data: Path, map_regions: Sequence[str] = ()
) -> tuple[tuple[LoadedArea, ...], tuple[str, ...]]:
    """Every area with files on disk, and the layers that belong to no area.

    States come from the per-state repeater layers, regions from the extracts,
    converted Navit maps and vector tiles under *data* (``<prefix>/share/
    hammunition/data``). Sizes are the files' on-disk sizes, dates the layer's
    own or the file's. Reads only. Region names are the station's
    ``map_regions`` where one matches a file, else the file's slug."""
    from . import infra, repeaters

    by_area: dict[tuple[str, str], list[LoadedLayer]] = {}
    names_of = {_slug(r): r for r in map_regions}
    always: list[str] = []
    for layer_id in repeaters.present_layers(repeater_dir):
        area = repeaters.layer_area(layer_id)
        if area is None:
            always.append(layer_id)
            continue
        names = repeaters.layer_files(layer_id)
        files = [repeater_dir / n for n in names if (repeater_dir / n).is_file()]
        rows: int | None = None
        try:
            layer = repeaters.read_layer_rows(repeater_dir / names[3])
            rows, day = len(layer.rows), layer.day.isoformat()
        except (OSError, ValueError):
            day = _day_of(files[0]) if files else ""
        by_area.setdefault((area, "state"), []).append(
            LoadedLayer(
                layer_id, "repeaters", rows, _size(files), day or None, tuple(map(str, files))
            )
        )
    for layer_id in infra.present_layers(infra_dir):
        area = infra.layer_area(layer_id)
        if area is None:
            always.append(layer_id)
            continue
        files = [infra_dir / n for n in infra.layer_files(layer_id) if (infra_dir / n).is_file()]
        kind = "state" if is_area_code(area) else "region"
        if kind == "region":
            area = names_of.get(area, area)
        by_area.setdefault((area, kind), []).append(
            LoadedLayer(layer_id, "infra", None, _size(files), None, tuple(map(str, files)))
        )
    slugs: dict[str, list[LoadedLayer]] = {}
    for unit, suffix, kind in REGION_FILES:
        folder = data / unit
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob(f"*{suffix}")):
            if not path.is_file() or path.is_symlink():
                continue
            slug = path.name.removesuffix(suffix)
            slugs.setdefault(slug, []).append(
                LoadedLayer(kind, kind, None, _size([path]), _day_of(path), (str(path),))
            )
    for slug, layers in slugs.items():
        by_area.setdefault((names_of.get(slug, slug), "region"), []).extend(layers)
    states = sorted(k for k in by_area if k[1] == "state")
    regions = sorted(k for k in by_area if k[1] == "region")
    return (
        tuple(LoadedArea(a, k, tuple(by_area[(a, k)])) for a, k in (*states, *regions)),
        tuple(always),
    )
