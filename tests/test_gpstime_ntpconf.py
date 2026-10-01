# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""ntp.conf is a dpkg conffile: every edit is marked and comes back exactly.  D-058."""

from __future__ import annotations

import itertools

import pytest

from hammunition.gpstime import files
from hammunition.gpstime.mode import MODES, Mode, Route, TimeError
from hammunition.gpstime.ntpconf import OFF, WAS, changes, restore, transform

ROUTES = [
    Route(tos_in_ntp_d=a, auto_prefers_pools=b)
    for a, b in itertools.product((False, True), repeat=2)
]
POOLS = [f"pool {n}.debian.pool.ntp.org iburst" for n in range(4)]


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", MODES)
def test_restore_undoes_every_mode_exactly(debian_ntp_conf: str, mode: Mode, route: Route) -> None:
    assert restore(transform(debian_ntp_conf, mode, route)) == debian_ntp_conf


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", MODES)
def test_transform_is_idempotent(debian_ntp_conf: str, mode: Mode, route: Route) -> None:
    once = transform(debian_ntp_conf, mode, route)
    assert transform(once, mode, route) == once


@pytest.mark.parametrize("route", ROUTES)
def test_any_mode_reaches_any_other(debian_ntp_conf: str, route: Route) -> None:
    for a, b in itertools.product(MODES, repeat=2):
        assert transform(transform(debian_ntp_conf, a, route), b, route) == transform(
            debian_ntp_conf, b, route
        )


def test_ntp_only_leaves_the_file_byte_identical(debian_ntp_conf: str) -> None:
    assert transform(debian_ntp_conf, "ntp-only") == debian_ntp_conf


def test_gps_only_leaves_no_live_source_line(debian_ntp_conf: str) -> None:
    out = transform(debian_ntp_conf, "gps-only")
    assert [ln for ln in out.splitlines() if ln.startswith(("pool ", "server "))] == []
    for pool in POOLS:
        assert f"{OFF}{pool}" in out.splitlines()


def test_the_conffile_route_disables_the_tos_line(debian_ntp_conf: str) -> None:
    out = transform(debian_ntp_conf, "gps-only", Route(tos_in_ntp_d=False, auto_prefers_pools=True))
    assert f"{OFF}tos minclock 4 minsane 3" in out.splitlines()
    assert "tos minclock 4 minsane 3" not in out.splitlines()
    assert "tos maxclock 11" in out.splitlines(), "only the minclock/minsane line moves"


def test_the_ntp_d_route_leaves_the_tos_line_alone(debian_ntp_conf: str) -> None:
    out = transform(debian_ntp_conf, "gps-only", Route(tos_in_ntp_d=True, auto_prefers_pools=True))
    assert "tos minclock 4 minsane 3" in out.splitlines()


def test_auto_prefers_each_pool_and_keeps_the_original_above_it(debian_ntp_conf: str) -> None:
    lines = transform(
        debian_ntp_conf, "auto", Route(tos_in_ntp_d=True, auto_prefers_pools=True)
    ).splitlines()
    for pool in POOLS:
        at = lines.index(f"{WAS}{pool}")
        assert lines[at + 1] == f"{pool} prefer"


def test_auto_without_pool_preference_touches_no_source(debian_ntp_conf: str) -> None:
    out = transform(debian_ntp_conf, "auto", Route(tos_in_ntp_d=True, auto_prefers_pools=False))
    assert out == debian_ntp_conf


def test_a_source_already_preferred_is_not_preferred_twice() -> None:
    text = "tos minclock 4 minsane 3\nserver 192.0.2.10 iburst prefer\n"
    assert transform(text, "auto", Route(tos_in_ntp_d=True, auto_prefers_pools=True)) == text


def test_comments_that_mention_pool_and_server_are_untouched(debian_ntp_conf: str) -> None:
    out = transform(debian_ntp_conf, "gps-only")
    assert "# server time.cloudflare.com nts" in out.splitlines()
    assert "# pool: <https://www.pool.ntp.org/join.html>" in out.splitlines()


def test_a_missing_tos_line_refuses_naming_the_file(debian_ntp_conf: str) -> None:
    text = debian_ntp_conf.replace("tos minclock 4 minsane 3\n", "")
    with pytest.raises(TimeError) as caught:
        transform(text, "gps-only", Route(tos_in_ntp_d=False, auto_prefers_pools=True))
    assert files.NTP_CONF in str(caught.value)
    assert "tos minclock N minsane N" in str(caught.value)


def test_no_source_lines_refuses_gps_only_but_not_ntp_only() -> None:
    text = "tos minclock 4 minsane 3\n"
    with pytest.raises(TimeError, match="no `pool` or `server` line"):
        transform(text, "gps-only")
    assert transform(text, "ntp-only") == text


def test_a_hand_edited_preferred_copy_refuses_restore(debian_ntp_conf: str) -> None:
    """Review Focus 2: never guess which of two lines the operator meant."""
    applied = transform(debian_ntp_conf, "auto", Route(tos_in_ntp_d=True, auto_prefers_pools=True))
    edited = applied.replace(
        "pool 1.debian.pool.ntp.org iburst prefer", "pool 1.debian.pool.ntp.org prefer"
    )
    with pytest.raises(TimeError, match="edited by hand") as caught:
        restore(edited)
    assert "line" in str(caught.value) and files.NTP_CONF in str(caught.value)
    with pytest.raises(TimeError, match="edited by hand"):
        transform(edited, "ntp-only")


def test_a_file_without_a_trailing_newline_round_trips(debian_ntp_conf: str) -> None:
    text = debian_ntp_conf.rstrip("\n")
    assert restore(transform(text, "gps-only")) == text


def test_changes_lists_only_the_lines_that_move(debian_ntp_conf: str) -> None:
    moved = changes(debian_ntp_conf, transform(debian_ntp_conf, "gps-only"))
    assert "- tos minclock 4 minsane 3" in moved
    assert f"+ {OFF}tos minclock 4 minsane 3" in moved
    assert all(line.startswith(("- ", "+ ")) for line in moved)
    assert len(moved) == 10  # the tos line and four pools, each out and back in
