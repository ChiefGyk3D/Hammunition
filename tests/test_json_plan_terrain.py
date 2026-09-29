# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan's Terrain block, text and JSON from one view.  D-061.

The existing goldens (``plan-install-text``, ``plan-maps-text``) are
unchanged by this block; ``plan-terrain-text`` pins it. Synthetic regions
(``atlantis/*``) and synthetic tiles near 0/0 only.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

from hammunition.backends.dem import DemResolution, RegionTiles, TerrainDisclosure
from hammunition.backends.regions import MapDisclosure
from hammunition.copernicus import TileFile, tile_url
from hammunition.distro import Target
from hammunition.geofabrik import RegionFile
from hammunition.manifest.schema import PackageManifest
from hammunition.plan import InstallPlan, PlannedPackage
from json_support import assert_golden_text

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)
SHA = "30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4"
A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM"
C = "Copernicus_DSM_COG_10_S01_00_W001_00_DEM"
DOCS = {
    "what_it_does": "Stands in for a unit in the terrain golden test.",
    "why_you_want_it": "Every line of the Terrain block needs something to show.",
    "upstream_url": "https://example.invalid/",
}
OSM = {"licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright"}
COP = {
    "licence": "Copernicus DEM licence",
    "licence_url": "https://spacedata.copernicus.eu/",
}


def _unit(name: str, install: dict[str, Any], depends: list[str] | None = None) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "station",
            "summary": f"The {name} fixture",
            "categories": ["navigation-maps"],
            "depends": depends or [],
            "install": [{"install": install}],
            "update": {"probe": {"method": "none"}},
            "documentation": DOCS,
        }
    )


def _derived(name: str, converter: str, source: str) -> PackageManifest:
    install = {"method": "derived", "converter": converter, "source": source}
    return _unit(name, {**install, **(COP if source == "dem-copernicus" else OSM)}, [source])


def _region(name: str, size: int) -> RegionFile:
    return RegionFile(
        f"atlantis/{name}",
        "260101",
        f"https://example.invalid/atlantis/{name}-260101.osm.pbf",
        size,
        SHA,
        None,
    )


OCEANIA, LEMURIA = _region("oceania", 52_428_800), _region("lemuria", 10_485_760)


def terrain_plan(*, idle: bool = False) -> tuple[InstallPlan, MapDisclosure, TerrainDisclosure]:
    units = [
        _unit("osm-regions", {"method": "osm-regions", "provider": "geofabrik", **OSM}),
        _derived("osm-garmin", "mkgmap", "osm-regions"),
        _derived("osm-routino", "routino-planetsplitter", "osm-regions"),
        _unit("dem-copernicus", {"method": "dem-tiles", "provider": "copernicus-glo30", **COP}),
        _derived("dem-qmapshack", "gdal-dem", "dem-copernicus"),
    ]
    plan = InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(manifest=u, block=u.install[0], apt_packages=()) for u in units
        ),
    )
    maps = MapDisclosure(fetch=(), current=(OCEANIA, LEMURIA), kept=())
    resolution = DemResolution(
        regions=(
            RegionTiles(OCEANIA.region, OCEANIA.slug, (A, B), 2),
            RegionTiles(LEMURIA.region, LEMURIA.slug, (C,), 0),
        ),
        fetch=()
        if idle
        else (
            TileFile(A, tile_url(A), 39_138_429, SHA, None),
            TileFile(C, tile_url(C), 25_165_824, None, "0123456789abcdef0123456789abcdef"),
        ),
        current=(A, B, C) if idle else (B,),
    )
    terrain = TerrainDisclosure(
        resolution=resolution,
        licence=COP["licence"],
        licence_url=COP["licence_url"],
        garmin=() if idle else (OCEANIA,),
        routino_regions=0 if idle else 2,
        routino_total=0 if idle else OCEANIA.size + LEMURIA.size,
        contours=0 if idle else 2,
        drawing=not idle,
    )
    return plan, maps, terrain


def test_the_terrain_block_is_pinned_byte_for_byte() -> None:
    plan, maps, terrain = terrain_plan()
    lines = cli.render_plan(plan, [], euid=1000, maps=maps, terrain=terrain)
    assert_golden_text("plan-terrain-text", "\n".join(lines) + "\n")


def test_without_terrain_the_map_section_is_what_piece_1_printed() -> None:
    plan, maps, _terrain = terrain_plan()
    text = "\n".join(cli.render_plan(plan, [], euid=1000, maps=maps))
    assert "Terrain" not in text and "QMapShack" not in text


def test_the_json_carries_every_value_the_terrain_text_shows() -> None:
    from hammunition.interface.envelope import dumps, target_view
    from hammunition.interface.plan import PlanDocument, build_install_view

    plan, maps, terrain = terrain_plan()
    view = build_install_view(plan, [], euid=1000, maps=maps, terrain=terrain)
    doc = PlanDocument(
        action="install",
        requested=("navigation",),
        outcome="planned",
        target=target_view(plan.target),
        blockers=(),
        install=view,
        removal=None,
    )
    body = json.loads(dumps(doc))["install"]["maps"]["terrain"]
    assert [t["tile"] for t in body["fetch"]] == [A, C]
    assert [t["verified_by"] for t in body["fetch"]] == [
        "sha256, pinned by Hammunition",
        "MD5 from the publisher's object metadata; not pinned by Hammunition",
    ]
    assert body["regions"][0] == {
        "region": "atlantis/oceania",
        "tiles": 2,
        "sea": 2,
        "download": 39_138_429,
        "download_human": "39.1 MB",
    }
    assert body["routino_regions"] == 2 and body["contours"] == 2
    assert body["estimate_note"] == "measured on one region"


def test_each_unit_reads_already_installed_only_when_it_has_nothing_to_do() -> None:
    from hammunition.interface.plan import build_install_view

    plan, maps, terrain = terrain_plan()
    busy = {
        p.name: p.state
        for p in build_install_view(plan, [], euid=1000, maps=maps, terrain=terrain).packages
    }
    assert busy == {
        "osm-regions": "already installed",
        "osm-garmin": "will convert",
        "osm-routino": "will convert",
        "dem-copernicus": "will fetch+install",
        "dem-qmapshack": "will convert",
    }
    plan, maps, terrain = terrain_plan(idle=True)
    idle = {
        p.name: p.state
        for p in build_install_view(plan, [], euid=1000, maps=maps, terrain=terrain).packages
    }
    assert set(idle.values()) == {"already installed"}
