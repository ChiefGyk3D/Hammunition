# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The bound on US Topo end to end through `hammunition install`: the
walk-through line, the deferral without a grid square, the size consent that
`--yes` does not answer.  D-068 (amended 2026-10-02), issue #232.

Synthetic region and sheet near 0/0; the grid square is JJ00, whose centre is
about 70 km from the sheet. No network, and a real run stops before it runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hammunition.consent import TOPO_SIZE_ENV
from hammunition.station import Station, save_station
from test_json_plan_terrain import OCEANIA
from test_topo_cli import _catalog, _cli

STATION = Path("xdg_config_home") / "hammunition" / "station.yml"


def _station(tmp_path: Path, **values: Any) -> None:
    save_station(
        Station(callsign="N0TST", map_regions=(OCEANIA.region,), **values),
        path=tmp_path / STATION,
    )


def _dry(cli: Any, catalog: Path, *argv: str) -> int:
    return int(cli.main(["--catalog", str(catalog), "install", "--dry-run", *argv, "usgs-ustopo"]))


def test_the_default_says_what_it_chose_and_how_to_change_it_before_the_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _ = _cli(monkeypatch, tmp_path)
    _station(tmp_path, grid_square="JJ00")
    assert _dry(cli, _catalog(tmp_path)) == 0
    text = capsys.readouterr().out
    line = next(ln for ln in text.splitlines() if ln.startswith("note: US Topo: using"))
    assert line == (
        "note: US Topo: using a 100 km radius around your grid square (1 sheet, about 9.0 MB); "
        "`hammunition station set --topo-radius-km`, `--topo-regions` or `--topo-all` change this"
    )
    assert text.index(line) < text.index("Packages (")
    assert "selection: a 100 km radius around your grid square" in text
    assert "Fetch US Topo quad ZZ_Alpha_20240101" in text
    assert "asks you to type yes" not in text, "9 MB needs no extra consent"


def test_a_radius_too_small_for_the_sheet_plans_none_of_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, probe = _cli(monkeypatch, tmp_path)
    _station(tmp_path, grid_square="JJ00", topo_radius_km=10)
    assert _dry(cli, _catalog(tmp_path)) == 0
    text = capsys.readouterr().out
    assert "using a 10 km radius around your grid square (0 sheets" in text
    assert "ZZ_Alpha" not in text and probe.asked == []


def test_topo_all_takes_the_sheet_and_prints_the_size_sentence_and_the_ask(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _ = _cli(monkeypatch, tmp_path)
    _station(tmp_path, topo_all=True, topo_radius_km=1)
    catalog = _catalog(tmp_path)
    assert _dry(cli, catalog) == 0
    text = capsys.readouterr().out
    assert "US Topo: using every sheet of every region (--topo-all)" in text
    assert ("This installs 1 US Topo sheet: about 9.0 MB to download and the same on disk.") in text
    assert "The install asks you to type yes to that; --yes does not answer it." in text
    assert _dry(cli, catalog, "--json") == 0
    topo = json.loads(capsys.readouterr().out)["install"]["maps"]["terrain"]["topo"]
    assert topo["size_consent"].startswith("This installs 1 US Topo sheet")
    assert topo["selection"] == "every sheet of every region (--topo-all)"
    # With the mosaic planned the warped copies are in the disk figure.
    argv = ["--catalog", str(catalog), "install", "--dry-run", "ustopo-qmapshack"]
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert (
        "about 9.0 MB to download and about 18.0 MB of disk once the warped copies QMapShack "
        "reads are added."
    ) in out


def test_no_grid_square_defers_the_unit_by_name_and_says_how_to_fix_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, probe = _cli(monkeypatch, tmp_path)
    _station(tmp_path)
    assert _dry(cli, _catalog(tmp_path)) == 0
    text = capsys.readouterr().out
    assert "usgs-ustopo: will not choose which sheets or tiles to fetch this run" in text
    assert "no grid square is set" in text
    assert "`hammunition station set --grid-square <yours>`" in text
    assert "--topo-regions a,b" in text and "--topo-all" in text
    assert "Fetch US Topo quad" not in text and probe.asked == []
    assert "note: US Topo: using" not in text


def test_no_grid_square_keeps_what_is_installed_and_removes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.backends.regions import data_root
    from hammunition.backends.topo import RegionQuads, render_record
    from hammunition.ustopo import parse_index

    cli, _ = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    _station(tmp_path)
    out = data_root(tmp_path) / "usgs-ustopo"
    out.mkdir(parents=True)
    quad = parse_index((catalog / "data" / "ustopo-quads.txt").read_text()).quads[0]
    (out / f"{quad.name}.tif").write_bytes(b"x")
    (out / f"{OCEANIA.slug}.quads").write_text(render_record(RegionQuads(*_pair(), (quad,))))
    assert _dry(cli, catalog) == 0
    text = capsys.readouterr().out
    assert "no grid square is set" in text
    assert "Remove" not in text.split("Will NOT happen")[0].split("Packages")[1]
    assert "remove-data" not in text


def _pair() -> tuple[str, str]:
    return OCEANIA.region, OCEANIA.slug


def _real(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **station: Any
) -> tuple[Any, Path, list[str]]:
    """A real (not dry) run whose execution is replaced by a recorder, so a
    consent that passes is seen and nothing runs."""
    cli, _ = _cli(monkeypatch, tmp_path)
    _station(tmp_path, **station)
    ran: list[str] = []

    class Reached(Exception):
        pass

    def stop(*_a: Any, **_k: Any) -> None:
        ran.append("run")
        raise Reached

    monkeypatch.setattr(cli, "run_with_sudo_ticket", stop)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.delenv(TOPO_SIZE_ENV, raising=False)
    cli.Reached = Reached
    return cli, _catalog(tmp_path), ran


def test_yes_does_not_answer_the_size_for_topo_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, catalog, ran = _real(monkeypatch, tmp_path, topo_all=True)
    rc = cli.main(["--catalog", str(catalog), "install", "--yes", "usgs-ustopo"])
    captured = capsys.readouterr()
    assert rc == 3 and ran == []
    assert "--yes does not satisfy this" in captured.err
    assert f"{TOPO_SIZE_ENV}=1" in captured.err


def test_the_environment_answer_is_the_sheet_count_and_then_the_run_goes_ahead(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, catalog, ran = _real(monkeypatch, tmp_path, topo_all=True)
    monkeypatch.setenv(TOPO_SIZE_ENV, "1")
    with pytest.raises(cli.Reached):
        cli.main(["--catalog", str(catalog), "install", "--yes", "usgs-ustopo"])
    assert ran == ["run"]
    log = (tmp_path / "xdg_state_home" / "hammunition").rglob("*.jsonl")
    assert any('"profile": "us-topo-size"' in p.read_text() for p in log)


def test_a_bounded_default_under_10_gb_asks_nothing_extra(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, catalog, ran = _real(monkeypatch, tmp_path, grid_square="JJ00")
    with pytest.raises(cli.Reached):
        cli.main(["--catalog", str(catalog), "install", "--yes", "usgs-ustopo"])
    assert ran == ["run"]


def test_a_selection_over_10_gb_asks_even_without_topo_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import hammunition.topo_bound as bound

    cli, catalog, ran = _real(monkeypatch, tmp_path, grid_square="JJ00")
    monkeypatch.setattr(bound, "CONSENT_BYTES", 1_000_000)
    monkeypatch.setattr("hammunition.topo_plan.CONSENT_BYTES", 1_000_000)
    rc = cli.main(["--catalog", str(catalog), "install", "--yes", "usgs-ustopo"])
    assert rc == 3 and ran == []
    assert "This installs 1 US Topo sheet" in capsys.readouterr().err


def test_the_deferred_plan_does_not_claim_topo_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _ = _cli(monkeypatch, tmp_path)
    _station(tmp_path)
    assert _dry(cli, _catalog(tmp_path), "--json") == 0
    topo = json.loads(capsys.readouterr().out)["install"]["maps"]["terrain"]["topo"]
    assert "--topo-all" not in topo["selection"] and topo["size_consent"] is None
    assert "kept" in topo["selection"]
