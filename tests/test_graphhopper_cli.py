# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""GraphHopper's units through ``hammunition install --dry-run``.  D-076.

The phone tests' machine (no real apt, no network, an unprivileged operator),
Vermont as the one region, and the catalog's own manifests. Nothing is
fetched, built or written.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from hammunition.station import Station, save_station
from test_phone_cli import REPO
from test_phone_cli import _catalog as phone_catalog
from test_phone_cli import _machine as phone_machine


def _catalog(tmp_path: Path) -> str:
    root = Path(phone_catalog(tmp_path))
    for unit in ("graphhopper", "graphhopper-graph"):
        shutil.copy(REPO / "catalog" / "packages" / f"{unit}.yaml", root / "packages")
    return str(root)


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    return phone_machine(monkeypatch, tmp_path)


def test_the_dry_run_shows_the_jar_the_build_and_the_ledger_in_text_and_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _machine(monkeypatch, tmp_path)
    argv = ["--catalog", _catalog(tmp_path), "install", "--dry-run", "graphhopper-graph"]
    assert cli.main(argv) == 0
    text = capsys.readouterr().out
    assert "Fetch graphhopper" in text and "graphhopper-web-11.1.jar" in text
    assert "Stage graphhopper as graphhopper-web-11.1.jar (mode 0644)" in text
    assert "Build GraphHopper's route graph" in text and "1.2 GB of memory" in text
    assert "import" in text and "sac_scale" in text
    assert text.count("[check-route-graph]") == 1
    assert cli.main([*argv, "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    states = {u["name"]: u["state"] for u in doc["install"]["packages"]}
    assert states["graphhopper-graph"] == "will convert"
    assert not (tmp_path / "share").exists(), "a dry run writes nothing"


def test_typed_with_no_regions_the_graph_is_refused_naming_the_remedy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """It is in no profile, so it is only ever typed: D-039 refuses a typed
    name the station cannot satisfy, with the remedy, and changes nothing."""
    cli = _machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST"),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    catalog = _catalog(tmp_path)
    argv = ["--catalog", catalog, "install", "--dry-run", "--json", "graphhopper-graph"]
    assert cli.main(argv) == 2
    doc = json.loads(capsys.readouterr().out)
    assert [b["subject"] for b in doc["blockers"]] == ["graphhopper-graph"]
    assert "--map-regions" in doc["blockers"][0]["remedy"]
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "graphhopper"]) == 0
    assert "graphhopper-web-11.1.jar" in capsys.readouterr().out


def test_a_disk_short_of_the_graph_names_its_factor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.backends.terrain import combined_shortfall

    cli = _machine(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli,
        "combined_shortfall",
        lambda maps, terrain, **kw: combined_shortfall(maps, terrain, free_at=lambda path: 0, **kw),
    )
    argv = ["--catalog", _catalog(tmp_path), "install", "--dry-run", "graphhopper-graph"]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "route graph at 3.7x" in err and "measured on one region" in err


def test_the_comaps_disk_check_counts_the_graph_in_the_same_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.backends.comaps_maps import maps_shortfall
    from hammunition.backends.terrain import combined_shortfall
    from hammunition.comaps import CdnProbe, load_pins
    from hammunition.routing_plan import GraphRun

    cli = _machine(monkeypatch, tmp_path)
    catalog = Path(_catalog(tmp_path))
    shutil.copy(REPO / "catalog" / "packages" / "comaps-maps.yaml", catalog / "packages")
    shutil.copytree(REPO / "catalog" / "data", catalog / "data", dirs_exist_ok=True)
    pins = load_pins(catalog)
    monkeypatch.setattr(
        CdnProbe,
        "head",
        lambda self, url: (200, pins.maps[url.rsplit("/", 1)[1].removesuffix(".mwm")].size),
    )
    monkeypatch.setattr(
        GraphRun, "needs", lambda self, plan, *, prefix: {tmp_path / "graph-needs": 76}
    )

    graph_needs: dict[Path, int] = {}
    combined = combined_shortfall

    def allow_combined(maps: Any, terrain: Any, **kwargs: Any) -> str | None:
        nonlocal graph_needs
        graph_needs = kwargs["graph"]
        return combined(maps, terrain, free_at=lambda _path: 10**18, **kwargs)

    monkeypatch.setattr(cli, "combined_shortfall", allow_combined)
    shortfall = maps_shortfall
    expected: dict[str, int] = {}

    def check_maps(needs: Any, beside: Any) -> str | None:
        extras = beside or {}
        graph = sum(graph_needs.values())
        assert graph > 0
        graph_amount_already_counted = sum(
            min(extras.get(path, 0), amount) for path, amount in graph_needs.items()
        )
        free = sum(needs.values()) + sum(extras.values()) - graph_amount_already_counted
        expected.update(free=free, graph=graph)
        return shortfall(needs, beside, free_at=lambda _path: free, device_of=lambda _path: 1)

    monkeypatch.setattr(cli, "maps_shortfall", check_maps)
    argv = [
        "--catalog",
        str(catalog),
        "install",
        "--dry-run",
        "graphhopper-graph",
        "comaps-maps",
    ]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "not enough disk space for CoMaps' maps" in err
    assert f"({expected['free'] + expected['graph']} bytes) is needed" in err
    assert f"({expected['free']} bytes) is free" in err


def test_the_disk_needs_count_the_graph_twice_and_the_merged_input() -> None:
    from hammunition.backends.graphhopper import GraphConverter
    from hammunition.backends.staging import Staging
    from hammunition.distro import Target
    from hammunition.manifest.load import load_catalog
    from hammunition.plan import InstallPlan, PlannedPackage
    from hammunition.routing_plan import GraphRun
    from test_graphhopper_converter import LEMURIA, OCEANIA

    catalog = load_catalog(REPO / "catalog" / "packages")
    m = catalog["graphhopper-graph"]
    planned = PlannedPackage(manifest=m, block=m.install[0], apt_packages=())
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"), packages=(planned,)
    )
    staging = Path("/nonexistent/staging")
    prefix = Path("/nonexistent/prefix")
    one = GraphRun(
        ledger=None,  # type: ignore[arg-type]
        graph=GraphConverter(prefix=prefix, files=[OCEANIA], staging=Staging(staging)),
    )
    assert one.needs(plan, prefix=prefix) == {staging: 37, prefix: 37}
    two = GraphRun(
        ledger=None,  # type: ignore[arg-type]
        graph=GraphConverter(prefix=prefix, files=[OCEANIA, LEMURIA], staging=Staging(staging)),
    )
    assert two.needs(plan, prefix=prefix) == {staging: 74 + 20, prefix: 74}


def test_the_jar_the_plan_installs_is_the_one_the_record_will_name() -> None:
    from hammunition.distro import Target
    from hammunition.manifest.load import load_catalog
    from hammunition.plan import InstallPlan, PlannedPackage
    from hammunition.routing_plan import graphhopper_jar

    catalog = load_catalog(REPO / "catalog" / "packages")
    packages = tuple(
        PlannedPackage(manifest=catalog[n], block=catalog[n].install[0], apt_packages=())
        for n in ("graphhopper", "graphhopper-graph")
    )
    target = Target(distro="debian", version="13", arch="x86_64")
    assert graphhopper_jar(InstallPlan(target=target, packages=packages)) == (
        "graphhopper-web-11.1.jar"
    )
    assert graphhopper_jar(InstallPlan(target=target, packages=packages[1:])) is None


def test_update_names_the_graph_in_the_rebuild_command() -> None:
    from hammunition.update import BEHIND_PIN, UpdateReport, UpdateRow, rebuild_command

    rows = (
        UpdateRow("osm-regions", BEHIND_PIN, "a newer map is pinned", "reinstall"),
        UpdateRow("graphhopper-graph", "unknown", "no comparison for this method", "reinstall"),
    )
    assert rebuild_command(UpdateReport(rows=rows, upstream_declared=())) == (
        "hammunition install osm-regions osm-navit graphhopper-graph"
    )
    rows = (
        UpdateRow("graphhopper", BEHIND_PIN, "a newer jar is pinned", "reinstall"),
        UpdateRow("graphhopper-graph", "unknown", "no comparison for this method", "reinstall"),
    )
    assert rebuild_command(UpdateReport(rows=rows, upstream_declared=())) == (
        "hammunition install graphhopper graphhopper-graph"
    )


def test_leftover_map_data_includes_the_graph(tmp_path: Path) -> None:
    from hammunition.cli.main import leftover_maps_note
    from hammunition.distro import Target
    from hammunition.plan import NO_MAP_REGIONS, Deferral, InstallPlan

    out = tmp_path / "share" / "hammunition" / "data" / "graphhopper-graph"
    out.mkdir(parents=True)
    (out / "graph.source").write_text("converter: graphhopper-import 1\n")
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(),
        deferrals=(
            Deferral("graphhopper-graph", "will not be installed", NO_MAP_REGIONS, "", "package"),
        ),
    )
    note = leftover_maps_note(plan, tmp_path)
    assert note is not None and "graphhopper-graph" in note
