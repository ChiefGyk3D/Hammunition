# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan says which source each data download tries first, and
``install --no-mirror`` ignores the station's mirror for one run.  D-070."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.station import Station, save_station
from json_support import REPO_ROOT, parse_one, validate
from test_json_install import _machine, cli

CATALOG = REPO_ROOT / "catalog"
MIRROR = "http://bunker.lan:8080/"
AT_MIRROR = f"{MIRROR}country-files/"


def _plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    station: Station | None,
    *flags: str,
) -> tuple[int, str]:
    _machine(monkeypatch, tmp_path)
    if station is not None:
        save_station(station, path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml")
    rc = cli.main(["--catalog", str(CATALOG), "install", "--dry-run", *flags, "country-files"])
    return rc, capsys.readouterr().out


def _fetch_steps(doc: dict[str, object]) -> list[dict[str, object]]:
    install = doc["install"]
    assert isinstance(install, dict)
    return [s for s in install["commands"] if s["action"] == "fetch"]


def test_with_a_mirror_the_plan_names_it_and_each_fetch_tries_it_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _plan(monkeypatch, tmp_path, capsys, Station(mirror=MIRROR), "--json")
    doc = parse_one(out)
    validate(doc)
    assert rc == 0
    assert doc["install"]["mirror"] == {
        "url": MIRROR,
        "ignored": False,
        "text": doc["install"]["mirror"]["text"],
    }
    (fetch,) = _fetch_steps(doc)
    sources = fetch["sources"]
    assert isinstance(sources, list) and len(sources) == 2
    assert sources[0] == f"{AT_MIRROR}bigcty-20260906.zip"
    assert sources[1].startswith("https://www.country-files.com/")


def test_the_text_plan_prints_the_mirror_section_and_the_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _plan(monkeypatch, tmp_path, capsys, Station(mirror=MIRROR))
    assert rc == 0
    assert "Data mirror (D-070):" in out
    assert MIRROR in out and "LAN mirror first" in out
    assert f"{AT_MIRROR}bigcty-20260906.zip, then https://www.country-files.com/" in out


def test_no_mirror_ignores_it_for_the_run_and_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _plan(monkeypatch, tmp_path, capsys, Station(mirror=MIRROR), "--no-mirror", "--json")
    doc = parse_one(out)
    assert rc == 0
    assert doc["install"]["mirror"]["ignored"] is True
    (fetch,) = _fetch_steps(doc)
    sources = fetch["sources"]
    assert isinstance(sources, list) and len(sources) == 1
    assert "mirror" not in str(fetch["description"])


@pytest.mark.parametrize("flags", [(), ("--no-mirror",)])
def test_with_no_mirror_set_there_is_no_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
) -> None:
    rc, out = _plan(monkeypatch, tmp_path, capsys, None, *flags, "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["install"]["mirror"] is None
    rc, text = _plan(monkeypatch, tmp_path, capsys, None, *flags)
    assert "Data mirror" not in text and "LAN mirror" not in text
