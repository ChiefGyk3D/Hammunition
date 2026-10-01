# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The time mode and the two files it is written to.  D-058."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.gpstime import files
from hammunition.gpstime.mode import (
    DEFAULT_MODE,
    GPS_MODES,
    HELPER_HEADER,
    MODES,
    NMEA_TIME1,
    ROUTE,
    Mode,
    Route,
    TimeError,
    as_mode,
    parse_mode_file,
    read_mode,
    render_mode_file,
    render_ntp_d,
)


def test_the_modes_are_the_maintainers_four_and_auto_is_the_default() -> None:
    assert MODES == ("auto", "prefer-gps", "ntp-only", "gps-only")
    assert DEFAULT_MODE == "auto"
    assert frozenset({"auto", "prefer-gps", "gps-only"}) == GPS_MODES


@pytest.mark.parametrize("value", ["gps", "AUTO", "auto; rm -rf /", "", None, 3])
def test_as_mode_refuses_anything_but_the_four(value: object) -> None:
    with pytest.raises(TimeError, match="not a time mode"):
        as_mode(value)


@pytest.mark.parametrize("mode", MODES)
def test_the_mode_file_round_trips(mode: Mode) -> None:
    text = render_mode_file(mode)
    assert text.startswith(HELPER_HEADER)
    assert parse_mode_file(text) == mode


def test_an_unknown_mode_in_the_file_refuses() -> None:
    with pytest.raises(TimeError, match="not a time mode"):
        parse_mode_file("mode: gps\n")


def test_extra_keys_in_the_file_refuse() -> None:
    with pytest.raises(TimeError, match="exactly one key"):
        parse_mode_file("mode: auto\nserver: 192.0.2.1\n")


def test_a_file_that_is_not_yaml_refuses() -> None:
    with pytest.raises(TimeError, match="not YAML"):
        parse_mode_file("mode: [\n")


def test_an_unset_mode_is_auto_and_says_it_was_never_set(time_files: Path) -> None:
    assert read_mode() == ("auto", False)


def test_a_set_mode_is_read_back(time_files: Path) -> None:
    path = Path(files.TIME_CONFIG)
    path.parent.mkdir(parents=True)
    path.write_text(render_mode_file("gps-only"))
    assert read_mode() == ("gps-only", True)


def test_ntp_only_has_no_refclock() -> None:
    text = render_ntp_d("ntp-only")
    assert "refclock" not in "".join(ln for ln in text.splitlines() if not ln.startswith("#"))


def test_auto_raises_the_refclock_stratum() -> None:
    assert f"refclock shm unit 0 refid GPS time1 {NMEA_TIME1} stratum 10\n" in render_ntp_d("auto")


def test_prefer_gps_prefers_the_refclock() -> None:
    assert f"refclock shm unit 0 refid GPS time1 {NMEA_TIME1} prefer\n" in render_ntp_d(
        "prefer-gps"
    )


def test_gps_only_has_the_plain_refclock() -> None:
    assert f"refclock shm unit 0 refid GPS time1 {NMEA_TIME1}\n" in render_ntp_d("gps-only")


@pytest.mark.parametrize("mode", ["auto", "prefer-gps", "gps-only"])
def test_the_tos_line_is_in_the_file_only_on_the_ntp_d_route(mode: Mode) -> None:
    on = render_ntp_d(mode, Route(tos_in_ntp_d=True, auto_prefers_pools=True))
    off = render_ntp_d(mode, Route(tos_in_ntp_d=False, auto_prefers_pools=True))
    assert "tos minclock 1 minsane 1\n" in on
    assert "tos" not in off


@pytest.mark.parametrize("mode", MODES)
def test_every_live_line_of_the_ntp_d_file_comes_from_the_mode(mode: Mode) -> None:
    live = [ln for ln in render_ntp_d(mode).splitlines() if ln and not ln.startswith("#")]
    for line in live:
        assert line.startswith(("refclock shm unit 0 refid GPS time1 ", "tos minclock 1 minsane 1"))


def test_the_route_and_time1_are_the_values_task_9_measured() -> None:
    """Changed only by Task 9's bench record, with the measurement cited in D-058."""
    assert Route(tos_in_ntp_d=False, auto_prefers_pools=True) == ROUTE
    assert NMEA_TIME1 == "0.000"


def test_no_test_sees_the_hosts_time_files() -> None:
    """Review Focus 5: the autouse fixture has repointed every path."""
    for name, default in files.PATHS.items():
        assert getattr(files, name) != default
        assert not Path(getattr(files, name)).exists()
