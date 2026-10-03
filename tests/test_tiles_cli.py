# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The vector-tile units through ``hammunition install --dry-run``.  D-071.

The phone tests' machine (no real apt, no network, an unprivileged operator),
Vermont as the one region, and the catalog's own manifests. The fake apt
offers tilemaker at the version the test names. Nothing is fetched, built or
written.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import AptBackend, AptPackageState
from test_phone_cli import REPO
from test_phone_cli import _catalog as phone_catalog
from test_phone_cli import _machine as phone_machine


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tilemaker: str) -> Any:
    cli = phone_machine(monkeypatch, tmp_path)
    monkeypatch.setattr(
        AptBackend,
        "probe",
        lambda self, pkgs: {
            p: AptPackageState(
                name=p, installed=None, candidate=tilemaker if p == "tilemaker" else "1.0"
            )
            for p in pkgs
        },
    )
    return cli


def _catalog(tmp_path: Path) -> str:
    root = Path(phone_catalog(tmp_path))
    for unit in ("vector-map-kit", "osm-pmtiles", "gdal-bin"):
        shutil.copy(REPO / "catalog" / "packages" / f"{unit}.yaml", root / "packages")
    return str(root)


def test_the_dry_run_shows_the_kit_the_build_and_the_ledger_in_text_and_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _machine(monkeypatch, tmp_path, "3.0.0-1")
    argv = ["--catalog", _catalog(tmp_path), "install", "--dry-run", "osm-pmtiles"]
    assert cli.main(argv) == 0
    text = capsys.readouterr().out
    assert "Build the vector-tile map of north-america/us/vermont" in text
    assert "tilemaker --input" in text and "ogr2ogr" in text
    assert "Fetch vector-map-kit data (43.7 MB" in text
    assert "only the listed members" in text
    assert text.count("[check-vector-tiles]") == 1
    assert cli.main([*argv, "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    states = {u["name"]: u["state"] for u in doc["install"]["packages"]}
    assert states["osm-pmtiles"] == "will convert"
    assert not (tmp_path / "share").exists(), "a dry run writes nothing"


def test_tilemaker_2_4_refuses_the_unit_typed_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _machine(monkeypatch, tmp_path, "2.4.0-1build3")
    argv = ["--catalog", _catalog(tmp_path), "install", "--dry-run", "osm-pmtiles"]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "tilemaker 3.0 or newer" in err and "2.4.0-1build3" in err


def test_a_disk_short_of_the_tiles_needs_names_their_factors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.backends.terrain import combined_shortfall

    cli = _machine(monkeypatch, tmp_path, "3.0.0-1")
    monkeypatch.setattr(
        cli,
        "combined_shortfall",
        lambda maps, terrain, **kw: combined_shortfall(maps, terrain, free_at=lambda path: 0, **kw),
    )
    argv = ["--catalog", _catalog(tmp_path), "install", "--dry-run", "osm-pmtiles"]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "vector-tile maps" in err and "not measured" in err


def test_the_books_disk_check_counts_tiles_in_the_same_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from dataclasses import replace

    from hammunition.backends.kiwix import books_shortfall
    from hammunition.backends.terrain import combined_shortfall
    from hammunition.kiwix import KiwixProbe
    from hammunition.station import load_station, save_station
    from hammunition.tiles_plan import TilesRun

    cli = _machine(monkeypatch, tmp_path, "3.0.0-1")
    catalog = Path(_catalog(tmp_path))
    shutil.copy(REPO / "catalog" / "packages" / "kiwix-library.yaml", catalog / "packages")
    shutil.copytree(REPO / "catalog" / "data", catalog / "data", dirs_exist_ok=True)
    station_path = tmp_path / "xdg_config_home" / "hammunition" / "station.yml"
    save_station(
        replace(load_station(station_path), reference_books=("ham.stackexchange.com_en_all",)),
        path=station_path,
    )
    monkeypatch.setattr(KiwixProbe, "head", lambda self, url: 200)
    monkeypatch.setattr(
        TilesRun, "needs", lambda self, plan, *, prefix: {tmp_path / "tile-needs": 58}
    )

    tile_needs: dict[Path, int] = {}
    combined = combined_shortfall

    def allow_combined(maps: Any, terrain: Any, **kwargs: Any) -> str | None:
        nonlocal tile_needs
        tile_needs = kwargs["tiles"]
        return combined(maps, terrain, free_at=lambda _path: 10**18, **kwargs)

    monkeypatch.setattr(cli, "combined_shortfall", allow_combined)
    shortfall = books_shortfall
    expected: dict[str, int] = {}

    def check_books(needs: Any, others: Any) -> str | None:
        extras = others or {}
        tiles = sum(tile_needs.values())
        assert tiles > 0
        tile_amount_already_counted = sum(
            min(extras.get(path, 0), amount) for path, amount in tile_needs.items()
        )
        free = sum(needs.values()) + sum(extras.values()) - tile_amount_already_counted
        expected.update(free=free, tiles=tiles)
        return shortfall(needs, others, free_at=lambda _path: free, device_of=lambda _path: 1)

    monkeypatch.setattr(cli, "books_shortfall", check_books)
    argv = [
        "--catalog",
        str(catalog),
        "install",
        "--dry-run",
        "osm-pmtiles",
        "kiwix-library",
    ]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "not enough disk space for the reference books" in err
    assert f"({expected['free'] + expected['tiles']} bytes) is needed" in err
    assert f"({expected['free']} bytes) is free" in err


def test_update_names_the_tiles_in_the_rebuild_command() -> None:
    from hammunition.update import BEHIND_PIN, UpdateReport, UpdateRow, rebuild_command

    rows = (
        UpdateRow("osm-regions", BEHIND_PIN, "a newer map is pinned", "reinstall"),
        UpdateRow("osm-pmtiles", "unknown", "no comparison for this method", "reinstall"),
    )
    assert rebuild_command(UpdateReport(rows=rows, upstream_declared=())) == (
        "hammunition install osm-regions osm-navit osm-pmtiles"
    )


def test_leftover_map_data_includes_the_tiles(tmp_path: Path) -> None:
    from hammunition.cli.main import leftover_maps_note
    from hammunition.distro import Target
    from hammunition.plan import NO_MAP_REGIONS, Deferral, InstallPlan

    out = tmp_path / "share" / "hammunition" / "data" / "osm-pmtiles"
    out.mkdir(parents=True)
    (out / "north-america-us-vermont.pmtiles").write_bytes(b"PMTiles")
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(),
        deferrals=(
            Deferral("osm-pmtiles", "will not be installed", NO_MAP_REGIONS, "", "package"),
        ),
    )
    note = leftover_maps_note(plan, tmp_path)
    assert note is not None and "osm-pmtiles" in note
