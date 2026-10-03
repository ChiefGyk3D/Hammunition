# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""BRouter's routing files in the run, the plan and ``update``.  D-063.

Synthetic regions (``atlantis/*``) and synthetic tiles near 0/0 only.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from hammunition.backends.dem import DemResolution, RegionTiles
from hammunition.backends.regions import MapLedger
from hammunition.backends.terrain import (
    BEF_BYTES,
    BROUTER_FACTOR,
    BROUTER_SCRATCH_FACTOR,
    ELEVATION_SCRATCH_BYTES,
    TerrainWork,
    brouter_estimate,
    terrain_needs,
)
from hammunition.fetch import Fetcher
from hammunition.plan import InstallPlan, PlannedPackage
from hammunition.terrain_plan import build_terrain_run
from hammunition.update import UpdateReport, UpdateRow, rebuild_command
from test_json_plan_terrain import LEMURIA, OCEANIA, OSM, TARGET, _unit, terrain_plan

cli = importlib.import_module("hammunition.cli.main")

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM"
MB = 1_000_000


def _segments() -> Any:
    return _unit(
        "brouter-segments",
        {
            "method": "derived",
            "converter": "brouter-mapcreator",
            "source": "osm-regions",
            "program": "brouter",
            "profiles": "brouter-mapcreator-profiles",
            "elevation": "dem-copernicus",
            **OSM,
        },
        ["osm-regions", "brouter", "brouter-mapcreator-profiles", "dem-copernicus"],
    )


def _plan(*units: Any) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(manifest=u, block=u.install[0], apt_packages=()) for u in units
        ),
    )


def _run(tmp_path: Path, resolution: DemResolution) -> Any:
    return build_terrain_run(
        prefix=tmp_path,
        builds=tmp_path / "builds",
        owner=None,
        runner=None,
        fetcher=Fetcher(tmp_path / "cache"),
        files=[OCEANIA, LEMURIA],
        keep=frozenset(),
        regions=MapLedger(),
        resolution=resolution,
    )


def test_the_run_discloses_the_rebuild_its_tiles_and_squares(tmp_path: Path) -> None:
    resolution = DemResolution(regions=(RegionTiles(OCEANIA.region, OCEANIA.slug, (A, B), 0),))
    run = _run(tmp_path, resolution)
    assert "brouter-mapcreator" in run.converters
    plan = _plan(_segments())
    disclosed = run.disclosure(plan)
    assert disclosed is not None
    assert disclosed.brouter_regions == 2
    assert disclosed.brouter_total == OCEANIA.size + LEMURIA.size
    assert (disclosed.brouter_tiles, disclosed.brouter_squares) == (2, 1)
    needs = run.needs(plan, cache=tmp_path / "cache", prefix=tmp_path)
    total = OCEANIA.size + LEMURIA.size
    assert needs[tmp_path / "builds" / "brouter-segments"] == round(
        BROUTER_SCRATCH_FACTOR * total
        + total  # two regions: the merged input
        + ELEVATION_SCRATCH_BYTES
        + BEF_BYTES
        + brouter_estimate(total)
    )
    assert needs[tmp_path] == brouter_estimate(total)


def test_one_region_and_no_tiles_count_no_merge_and_no_elevation(tmp_path: Path) -> None:
    needs = terrain_needs(
        TerrainWork(brouter=100 * MB, brouter_regions=1),
        cache=tmp_path / "cache",
        garmin_staging=tmp_path / "garmin",
        routino_staging=tmp_path / "routino",
        contour_staging=tmp_path / "contours",
        prefix=tmp_path / "prefix",
        brouter_staging=tmp_path / "brouter",
    )
    assert needs[tmp_path / "brouter"] == BROUTER_SCRATCH_FACTOR * 100 * MB + 20 * MB
    assert needs[tmp_path / "prefix"] == 20 * MB
    assert BROUTER_FACTOR == 0.2


def _with_brouter(*, tiles: int = 3) -> tuple[Any, Any, Any]:
    plan, maps, terrain = terrain_plan()
    plan = InstallPlan(
        target=plan.target,
        packages=(
            *plan.packages,
            PlannedPackage(manifest=_segments(), block=_segments().install[0], apt_packages=()),
        ),
    )
    total = OCEANIA.size + LEMURIA.size
    return (
        plan,
        maps,
        replace(terrain, brouter_regions=2, brouter_total=total, brouter_tiles=tiles),
    )


def test_the_text_says_what_is_built_and_that_brouter_de_is_not_used() -> None:
    plan, maps, terrain = _with_brouter()
    text = "\n".join(cli.render_plan(plan, [], euid=1000, maps=maps, terrain=terrain))
    assert (
        "    BRouter routing files over 2 region(s)  about 12.6 MB (0.2x the downloads "
        "together), elevation from 3 tile(s); built here, never downloaded from brouter.de"
    ) in text
    plan, maps, terrain = _with_brouter(tiles=0)
    text = "\n".join(cli.render_plan(plan, [], euid=1000, maps=maps, terrain=terrain))
    assert "no elevation (flat)" in text


def test_the_json_carries_the_same_numbers() -> None:
    from hammunition.interface.envelope import dumps, target_view
    from hammunition.interface.plan import PlanDocument, build_install_view

    plan, maps, terrain = _with_brouter()
    view = build_install_view(plan, [], euid=1000, maps=maps, terrain=terrain)
    doc = PlanDocument(
        action="install",
        requested=("navigation",),
        outcome="planned",
        step_count=len(view.commands),
        target=target_view(plan.target),
        blockers=(),
        install=view,
        removal=None,
    )
    body = json.loads(dumps(doc))["install"]["maps"]["terrain"]
    total = OCEANIA.size + LEMURIA.size
    assert body["brouter_regions"] == 2 and body["brouter_tiles"] == 3
    assert body["brouter_estimate"] == brouter_estimate(total)
    assert body["brouter_estimate_human"] == "12.6 MB"
    states = {p.name: p.state for p in view.packages}
    assert states["brouter-segments"] == "will convert"
    *_, idle = terrain_plan(idle=True)
    plan, maps, _busy = _with_brouter()
    view = build_install_view(plan, [], euid=1000, maps=maps, terrain=idle)
    assert {p.name: p.state for p in view.packages}["brouter-segments"] == "already installed"


def test_the_update_footer_names_the_routing_files_when_they_are_installed() -> None:
    from hammunition.update import BEHIND_PIN

    rows = (
        UpdateRow("osm-regions", BEHIND_PIN, "1 region installed; 1 behind the pin", "reinstall"),
        UpdateRow("brouter-segments", "unknown", "no comparison for this method", "reinstall"),
    )
    assert rebuild_command(UpdateReport(rows=rows, upstream_declared=())) == (
        "hammunition install osm-regions osm-navit brouter-segments"
    )


def test_a_new_brouter_alone_names_the_routing_files_in_the_rebuild_command() -> None:
    from hammunition.update import BEHIND_PIN

    rows = (
        UpdateRow("brouter", BEHIND_PIN, "1.7.10 installed; 1.7.11 pinned", "reinstall"),
        UpdateRow("brouter-segments", "unknown", "no comparison for this method", "reinstall"),
    )
    assert rebuild_command(UpdateReport(rows=rows, upstream_declared=())) == (
        "hammunition install brouter brouter-segments"
    )


def test_the_plan_s_pins_are_the_planned_jar_and_filters_version() -> None:
    from hammunition.backends.brouter import InputPins
    from hammunition.terrain_plan import brouter_pins

    brouter = _unit(
        "brouter",
        {
            "method": "binary",
            "artifact": {"url": "https://example.invalid/b.zip", "sha256": "a" * 64},
            "format": "zip",
            "install_tree": True,
            "tree_marker": "brouter-1.7.11-all.jar",
        },
    )
    filters = _unit(
        "brouter-mapcreator-profiles",
        {
            "method": "data",
            "artifacts": [
                {
                    "url": "https://example.invalid/all.brf",
                    "sha256": "a" * 64,
                    "size": 1,
                    "install_as": "all.brf",
                }
            ],
            "licence": "MIT",
            "licence_url": "https://example.invalid/LICENSE",
        },
    )
    plan = _plan(brouter, filters, _segments())
    assert brouter_pins(plan) == InputPins(jar="brouter-1.7.11-all.jar", profiles="station")
    assert brouter_pins(_plan(brouter)) == InputPins()
