# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The phone converters wired into a run: disk, plan state, uninstall, update.  D-067."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends.mapsforge import (
    MAP_SCRATCH_FACTOR,
    POI_SCRATCH_FACTOR,
    estimate,
)
from hammunition.backends.regions import MapLedger
from hammunition.backends.terrain import combined_shortfall
from hammunition.distro import Target
from hammunition.fetch import Fetcher
from hammunition.interface.plan import plan_state
from hammunition.manifest.schema import PackageManifest
from hammunition.phone_plan import PhoneRun, build_phone_run
from hammunition.plan import InstallPlan, PlannedPackage
from hammunition.state.uninstall import RemovalPaths, plan_removal
from hammunition.update import BEHIND_PIN, UpdateReport, UpdateRow, rebuild_command
from test_mapsforge import DELAWARE, JAR, JAR_NAME, VERMONT, FakeTransport, manifest

TARGET = Target(distro="debian", version="13", arch="x86_64")


def _plan(*manifests: PackageManifest) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(manifest=m, block=m.install[0], apt_packages=()) for m in manifests
        ),
    )


def _run(tmp_path: Path) -> PhoneRun:
    return build_phone_run(
        prefix=tmp_path / "prefix",
        builds=tmp_path / "builds",
        owner=None,
        runner=None,
        fetcher=Fetcher(tmp_path / "cache", transport=FakeTransport()),
        files=[VERMONT, DELAWARE],
        keep=frozenset(),
        regions=MapLedger(),
    )


def test_the_run_names_both_converters_and_shares_one_ledger(tmp_path: Path) -> None:
    run = _run(tmp_path)
    assert set(run.converters) == {"mapsforge-map", "mapsforge-poi"}
    assert run.map.ledger is run.poi.ledger
    assert run.map.staging.directory == tmp_path / "builds" / "mapsforge-map"


def test_the_disk_counts_the_largest_scratch_every_output_and_the_writer_once(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path)
    needs = run.needs(
        _plan(manifest("map"), manifest("poi")),
        cache=tmp_path / "cache",
        prefix=tmp_path / "prefix",
    )
    size = VERMONT.size
    assert needs[tmp_path / "builds" / "mapsforge-map"] == round(MAP_SCRATCH_FACTOR * size)
    assert needs[tmp_path / "builds" / "mapsforge-poi"] == round(POI_SCRATCH_FACTOR * size)
    assert needs[tmp_path / "cache"] == len(JAR)
    assert needs[tmp_path / "prefix"] == (
        2 * estimate("map", size) + 2 * estimate("poi", size) + len(JAR)
    )


def test_a_plan_without_phone_units_needs_nothing(tmp_path: Path) -> None:
    run = _run(tmp_path)
    assert run.needs(_plan(), cache=tmp_path, prefix=tmp_path) == {}
    assert run.idle(_plan()) == frozenset()


def test_the_disk_refusal_says_the_phone_factors_were_measured_on_one_region(
    tmp_path: Path,
) -> None:
    short = combined_shortfall(
        {},
        {},
        phone={tmp_path: 10**12},
        free_at=lambda _: 10,
        device_of=lambda _: 1,
    )
    assert short is not None
    assert "phone maps" in short and "measured on one region" in short
    assert "QMapShack" not in short, "no terrain was counted, so no terrain note"


def test_an_idle_phone_unit_says_already_installed(tmp_path: Path) -> None:
    run = _run(tmp_path)
    m = manifest("map")
    data = tmp_path / "prefix" / "share" / "hammunition" / "data" / "mapsforge-map"
    data.mkdir(parents=True)
    for region in (VERMONT, DELAWARE):
        (data / f"{region.slug}.map").write_bytes(b"m")
        (data / f"{region.slug}.map.source").write_text("260101\nconverter: mapsforge-map 1\n")
    plan = _plan(m, manifest("poi"))
    idle = run.idle(plan)
    assert idle == frozenset({"mapsforge-map"}), "the POI unit still has everything to build"
    states = [plan_state(p, idle=idle) for p in plan.packages]
    assert states == ["already installed", "will convert"]


def test_uninstall_removes_the_poi_writer_s_directory_with_the_data(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    jar = prefix / "share" / "hammunition" / "mapsforge-poi" / JAR_NAME
    jar.parent.mkdir(parents=True)
    jar.write_bytes(JAR)
    for unit in ("mapsforge-poi", "mapsforge-map"):
        (prefix / "share" / "hammunition" / "data" / unit).mkdir(parents=True)
    plan = plan_removal(
        ["mapsforge-poi", "mapsforge-map"],
        catalog={"mapsforge-poi": manifest("poi"), "mapsforge-map": manifest("map")},
        profiles={},
        target=TARGET,
        attributed=frozenset({"mapsforge-poi", "mapsforge-map"}),
        states={},
        paths=RemovalPaths(
            prefix=prefix,
            venv_root=tmp_path / "venvs",
            bin_dir=tmp_path / "bin",
            applications_dir=tmp_path / "apps",
        ),
    )
    poi = {(r.kind, r.path) for r in plan.artifacts["mapsforge-poi"]}
    assert poi == {
        ("tree", prefix / "share" / "hammunition" / "data" / "mapsforge-poi"),
        ("tree", prefix / "share" / "hammunition" / "mapsforge-poi"),
    }
    assert {(r.kind, r.path) for r in plan.artifacts["mapsforge-map"]} == {
        ("tree", prefix / "share" / "hammunition" / "data" / "mapsforge-map"),
    }


@pytest.mark.parametrize("installed", [("mapsforge-map",), ("mapsforge-map", "mapsforge-poi")])
def test_the_rebuild_footer_names_the_phone_units_that_are_installed(
    installed: tuple[str, ...],
) -> None:
    rows = (
        UpdateRow("osm-regions", BEHIND_PIN, "1 region installed; 1 behind the pin", "reinstall"),
        *(UpdateRow(u, "unknown", "no comparison for this method", "reinstall") for u in installed),
    )
    assert rebuild_command(UpdateReport(rows=rows, upstream_declared=())) == (
        f"hammunition install osm-regions osm-navit {' '.join(installed)}"
    )
