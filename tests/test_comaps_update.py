# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``update`` for CoMaps' maps: offline against the pin, and ``--upstream``
against the CDN, which keeps a map version for months, not forever.  D-069.

Counts only, never a map id: which maps are installed says which regions.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hammunition.comaps import ComapsError, MapFile, MapPin, load_pins
from hammunition.update import BEHIND_PIN, NOT_INSTALLED, UP_TO_DATE, UPSTREAM_PROBES, mwm_state
from hammunition.upstream import CURRENT, EXPIRED, EXPIRING, UNANSWERED, probe_comaps_maps, render

REPO_ROOT = Path(__file__).resolve().parent.parent
PINS = load_pins(REPO_ROOT / "catalog")


def _file(name: str, size: int) -> MapFile:
    return MapFile(MapPin(name, size, "A" * 27 + "="), f"https://x.invalid/{name}.mwm", 260830)


def _put(where: Path, version: int, name: str, size: int) -> None:
    (where / str(version)).mkdir(parents=True, exist_ok=True)
    with (where / str(version) / f"{name}.mwm").open("wb") as fh:
        fh.truncate(size)


def test_every_map_at_its_pin_is_up_to_date(tmp_path: Path) -> None:
    files = [_file("US_Vermont", 10), _file("US_Delaware", 20)]
    _put(tmp_path, 260830, "US_Vermont", 10)
    _put(tmp_path, 260830, "US_Delaware", 20)
    state, detail = mwm_state(files, tmp_path, unmapped=0)
    assert state == UP_TO_DATE and "2 map(s)" in detail
    assert "Vermont" not in detail and "Delaware" not in detail


def test_a_map_at_another_version_is_behind_the_pin(tmp_path: Path) -> None:
    _put(tmp_path, 260501, "US_Vermont", 9)
    state, detail = mwm_state([_file("US_Vermont", 10)], tmp_path, unmapped=0)
    assert state == BEHIND_PIN and "install comaps-maps" in detail


def test_a_missing_map_is_not_installed_and_unmapped_regions_are_counted(tmp_path: Path) -> None:
    state, detail = mwm_state([_file("US_Vermont", 10)], tmp_path, unmapped=2)
    assert state == NOT_INSTALLED
    assert "2 region(s)" in detail


def test_the_probe_is_an_upstream_kind() -> None:
    assert "comaps_maps" in UPSTREAM_PROBES


def _probe(answer: tuple[int, int] | Exception, today: date) -> tuple[str, str]:
    def head(url: str) -> tuple[int, int]:
        assert url.endswith(f"/{PINS.series}/{PINS.version}/World.mwm")
        if isinstance(answer, Exception):
            raise answer
        return answer

    row = probe_comaps_maps("comaps-maps", PINS, head=head, today=today)
    assert row.catalog == str(PINS.version) and row.method == "comaps_maps"
    return row.state, row.detail


WORLD = PINS.maps["World"].size


def test_a_published_young_version_is_current() -> None:
    state, detail = _probe((200, WORLD), date(2026, 9, 30))
    assert state == CURRENT
    assert "2026-08-30" in detail


def test_a_version_ninety_days_old_is_flagged_as_expiring() -> None:
    state, detail = _probe((200, WORLD), date(2026, 11, 28))
    assert state == EXPIRING == "pin expiring"
    assert "four months" in detail and "scripts/gen_comaps_pins.py" in detail


def test_a_version_the_cdn_dropped_is_expired_even_behind_a_200() -> None:
    for answer in [(404, 0), (200, 1234)]:
        state, detail = _probe(answer, date(2026, 12, 31))
        assert state == EXPIRED == "pin expired"
        assert "scripts/gen_comaps_pins.py" in detail


def test_an_unreachable_cdn_is_unanswered() -> None:
    state, _detail = _probe(ComapsError("no route"), date(2026, 9, 30))
    assert state == UNANSWERED


def test_the_summary_counts_expired_and_expiring_pins() -> None:
    from hammunition.upstream import UpstreamRow

    rows = [
        UpstreamRow("comaps-maps", "comaps_maps", "260830", None, EXPIRED, "gone"),
        UpstreamRow("other", "comaps_maps", "260830", "260830", EXPIRING, "soon"),
    ]
    text = render(rows)
    assert "1 pin(s) expired" in text and "1 pin(s) expiring" in text
    assert "CoMaps" in text


def test_update_end_to_end_counts_maps_and_flags_an_expired_pin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib
    import shutil

    from hammunition.comaps import CdnProbe
    from hammunition.station import Station, save_station
    from json_support import FIXTURE_CATALOG
    from test_comaps_maps import COMAPS_MAPS
    from test_json_install import _machine

    cli = importlib.import_module("hammunition.cli.main")
    _machine(monkeypatch, tmp_path)
    catalog = tmp_path / "catalog"
    shutil.copytree(FIXTURE_CATALOG, catalog)
    shutil.copytree(REPO_ROOT / "catalog" / "data", catalog / "data", dirs_exist_ok=True)
    (catalog / "packages" / "comaps-maps.yaml").write_text(COMAPS_MAPS)
    save_station(
        Station(map_regions=("north-america/us/vermont",)),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    prefix = tmp_path / "prefix"
    real = cli.SourceBackend
    monkeypatch.setattr(cli, "SourceBackend", lambda *a, **k: real(*a, **{**k, "prefix": prefix}))
    _put(
        prefix / "share/hammunition/data/comaps-maps",
        260830,
        "US_Vermont",
        PINS.maps["US_Vermont"].size,
    )
    monkeypatch.setattr(CdnProbe, "head", lambda self, url: (404, 0))
    assert cli.main(["--catalog", str(catalog), "update", "comaps-maps", "--upstream"]) == 0
    out = capsys.readouterr().out
    row = next(
        ln for ln in out.splitlines() if ln.strip().startswith("comaps-maps") and "up to date" in ln
    )
    assert "1 map(s)" in row
    assert "pin expired" in out and "1 pin(s) expired" in out
    assert "Vermont" not in out and "vermont" not in out
