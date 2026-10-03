# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``mirror`` station key.  D-070.

A LAN address the verified fetch tries before the publisher. Checked for the
shape a fetchable base URL needs, never for whether it is on the LAN (a
hostname cannot be proved private without resolving it; the hash is the
check), and never allowed to carry a password.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.station import (
    STATION_FIELDS,
    Station,
    StationError,
    load_station,
    prompt_for,
    save_station,
)

cli = importlib.import_module("hammunition.cli.main")

MIRROR = "http://bunker.lan:8080/"


@pytest.mark.parametrize(
    "url", [MIRROR, "https://bunker.lan/hammunition", "http://192.168.1.20:8080"]
)
def test_a_mirror_url_is_kept_as_given(url: str) -> None:
    assert Station(mirror=url).mirror == url


def test_whitespace_around_a_mirror_is_dropped() -> None:
    assert Station(mirror=f"  {MIRROR} ").mirror == MIRROR


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://bunker.lan/",
        "file:///srv/bunker",
        "bunker.lan:8080",
        "http://",
        "http://user:secret@bunker.lan/",
        "http://user@bunker.lan/",
        "http://bunker.lan/?token=x",
        "http://bunker.lan/#top",
        "http://bunker lan/",
    ],
)
def test_a_mirror_that_is_not_a_plain_http_base_url_is_refused(bad: str) -> None:
    with pytest.raises(StationError, match="mirror"):
        Station(mirror=bad)


def test_the_mirror_is_not_a_template_variable() -> None:
    assert "mirror" not in STATION_FIELDS
    assert Station(mirror=MIRROR).get("mirror") is None


def test_the_mirror_round_trips_through_the_file(tmp_path: Path) -> None:
    path = tmp_path / "station.yml"
    save_station(Station(callsign="N0TST", mirror=MIRROR), path=path)
    assert load_station(path=path) == Station(callsign="N0TST", mirror=MIRROR)
    assert Station(mirror=MIRROR).as_dict() == {"mirror": MIRROR}


def test_prompting_for_a_callsign_keeps_the_mirror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "N0TST")
    station = prompt_for(["callsign"], Station(mirror=MIRROR))
    assert station.mirror == MIRROR and station.callsign == "N0TST"


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    return tmp_path / "hammunition" / "station.yml"


def test_station_set_mirror_saves_it_and_clear_mirror_removes_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    save_station(Station(callsign="N0TST"), path=path)
    assert cli.main(["station", "set", "--mirror", MIRROR]) == 0
    assert load_station(path=path) == Station(callsign="N0TST", mirror=MIRROR)
    assert MIRROR in capsys.readouterr().out
    assert cli.main(["station", "set", "--clear-mirror"]) == 0
    assert load_station(path=path) == Station(callsign="N0TST")
    assert "mirror" in capsys.readouterr().out


def test_station_set_refuses_a_bad_mirror_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    assert cli.main(["station", "set", "--mirror", "http://u:p@bunker.lan/"]) == 2
    assert not path.exists()
    assert "mirror" in capsys.readouterr().err


def test_mirror_and_clear_mirror_together_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.main(["station", "set", "--mirror", MIRROR, "--clear-mirror"])
    assert exc.value.code == 2


def test_station_show_prints_the_mirror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    save_station(Station(mirror=MIRROR), path=path)
    assert cli.main(["station", "show"]) == 0
    out = capsys.readouterr().out
    assert "mirror" in out and MIRROR in out
    assert "Nothing set" not in out


@pytest.mark.parametrize(
    "bad", ["http://bunker.lan:abc/", "http://bunker.lan:99999/", "http://[fd00::5/"]
)
def test_a_mirror_with_a_bad_port_or_host_is_a_station_error_not_a_crash(bad: str) -> None:
    with pytest.raises(StationError, match="mirror"):
        Station(mirror=bad)


def test_a_hand_edited_bad_mirror_is_a_named_error_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("callsign: N0TST\nmirror: 'http://[fd00::5/'\n")
    with pytest.raises(StationError):
        load_station(path=path)
    assert cli.main(["station", "show"]) == 1  # a named error, not a traceback
    assert "mirror" in capsys.readouterr().err
