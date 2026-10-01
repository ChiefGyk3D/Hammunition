# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""SPLAT's terrain in the run, the plan and the disk check.  D-061, amended
2026-10-02.

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
from hammunition.backends.terrain import SDF_BYTES, SDF_SCRATCH_BYTES, TerrainWork, terrain_needs
from hammunition.fetch import Fetcher
from hammunition.plan import InstallPlan, PlannedPackage
from hammunition.terrain_plan import build_terrain_run, splat_source
from test_json_plan_terrain import COP, OCEANIA, TARGET, _unit, terrain_plan

cli = importlib.import_module("hammunition.cli.main")

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM"
THREE = "USGS_13_n01e000"


def _splat(alternative: str | None = None) -> Any:
    block: dict[str, Any] = {
        "method": "derived",
        "converter": "splat-sdf",
        "source": "dem-copernicus",
        **COP,
    }
    depends = ["dem-copernicus"]
    if alternative is not None:
        block["alternative"] = alternative
        depends.append(alternative)
    return _unit("splat-sdf", block, depends)


def _plan(*units: Any) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(manifest=u, block=u.install[0], apt_packages=()) for u in units
        ),
    )


def _resolution(*tiles: str) -> DemResolution:
    return DemResolution(regions=(RegionTiles(OCEANIA.region, OCEANIA.slug, tiles, 0),))


def _run(tmp_path: Path, **kw: Any) -> Any:
    kw.setdefault("resolution", _resolution(A, B))
    return build_terrain_run(
        prefix=tmp_path,
        builds=tmp_path / "builds",
        owner=None,
        runner=None,
        fetcher=Fetcher(tmp_path / "cache"),
        files=[OCEANIA],
        keep=frozenset(),
        regions=MapLedger(),
        **kw,
    )


def test_the_run_discloses_the_tiles_and_counts_the_disk(tmp_path: Path) -> None:
    run = _run(tmp_path)
    assert "splat-sdf" in run.converters
    plan = _plan(_splat())
    disclosed = run.disclosure(plan)
    assert disclosed is not None
    assert (disclosed.splat_tiles, disclosed.splat_building) == (2, True)
    needs = run.needs(plan, cache=tmp_path / "cache", prefix=tmp_path)
    assert needs[tmp_path / "builds" / "splat-sdf"] == SDF_SCRATCH_BYTES
    assert needs[tmp_path] == 2 * SDF_BYTES


def test_nothing_planned_means_nothing_disclosed_or_counted(tmp_path: Path) -> None:
    needs = terrain_needs(
        TerrainWork(),
        cache=tmp_path / "cache",
        garmin_staging=tmp_path / "g",
        routino_staging=tmp_path / "r",
        contour_staging=tmp_path / "c",
        prefix=tmp_path / "p",
        splat_staging=tmp_path / "s",
    )
    assert not any(needs.values())
    assert _run(tmp_path).disclosure(_plan()) is None


def test_3dep_chosen_draws_from_the_block_s_alternative(tmp_path: Path) -> None:
    plan = _plan(_splat("dem-3dep"))
    assert splat_source(plan) == "dem-3dep"
    assert splat_source(_plan(_splat())) is None
    three = _resolution(THREE)
    run = _run(tmp_path, bare_earth=three, dem_source="3dep", splat_source="dem-3dep")
    assert run.splat.resolution == three and run.splat.source_unit == "dem-3dep"
    copernicus = _run(tmp_path, bare_earth=three, dem_source="copernicus", splat_source="dem-3dep")
    assert copernicus.splat.resolution.tiles == (A, B) and copernicus.splat.source_unit is None


def _with_splat(tiles: int) -> tuple[Any, Any, Any]:
    plan, maps, terrain = terrain_plan()
    plan = InstallPlan(
        target=plan.target,
        packages=(
            *plan.packages,
            PlannedPackage(manifest=_splat(), block=_splat().install[0], apt_packages=()),
        ),
    )
    return plan, maps, replace(terrain, splat_tiles=tiles, splat_building=bool(tiles))


def test_the_text_says_what_is_made_for_splat_and_signal_server() -> None:
    plan, maps, terrain = _with_splat(3)
    text = "\n".join(cli.render_plan(plan, [], euid=1000, maps=maps, terrain=terrain))
    assert "  Built for SPLAT! and Signal-Server (sizes an estimate, measured on one tile):" in text
    assert (
        "    SDF terrain for 3 tile(s)  about 21.0 MB (both resolutions, bzip2), with up to "
        "0.10 GB of scratch at a time"
    ) in text
    plan, maps, terrain = _with_splat(0)
    text = "\n".join(cli.render_plan(plan, [], euid=1000, maps=maps, terrain=terrain))
    assert "SPLAT" not in text


def test_the_json_carries_the_same_numbers_and_a_current_unit_reads_installed() -> None:
    from hammunition.interface.envelope import dumps, target_view
    from hammunition.interface.plan import PlanDocument, build_install_view

    plan, maps, terrain = _with_splat(3)
    view = build_install_view(plan, [], euid=1000, maps=maps, terrain=terrain)
    doc = PlanDocument(
        action="install",
        requested=("antenna",),
        outcome="planned",
        target=target_view(plan.target),
        blockers=(),
        install=view,
        removal=None,
    )
    body = json.loads(dumps(doc))["install"]["maps"]["terrain"]
    assert (body["splat_tiles"], body["splat_estimate"]) == (3, 3 * SDF_BYTES)
    assert body["splat_estimate_human"] == "21.0 MB"
    assert {p.name: p.state for p in view.packages}["splat-sdf"] == "will convert"
    plan, maps, terrain = _with_splat(0)
    view = build_install_view(plan, [], euid=1000, maps=maps, terrain=terrain)
    assert {p.name: p.state for p in view.packages}["splat-sdf"] == "already installed"
