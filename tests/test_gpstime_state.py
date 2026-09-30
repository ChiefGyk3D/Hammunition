# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the clock follows, from ntpsec's own answers, with no privilege.  D-058."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.base import CommandResult, RecordingRunner
from hammunition.gpstime import files
from hammunition.gpstime.mode import render_mode_file
from hammunition.gpstime.state import (
    APPARMOR_RULE,
    JSON_KEYS,
    TimeState,
    describe,
    dhcp_config_in_use,
    format_duration,
    gather,
    gps_from,
    grants_installed,
    has_rtc,
    parse_peers,
    run_ntpq,
)
from hammunition.hardware.power import Parkable

HEADER = (
    "     remote           refid      st t when poll reach   delay   offset   jitter\n"
    "===============================================================================\n"
)
POOL = " 0.debian.pool.n .POOL.          16 p    -   64    0   0.0000   0.0000   0.0001\n"
NET_SELECTED = (
    HEADER
    + POOL
    + (
        "*192.0.2.10      192.0.2.1        2 u   14   64  377  38.3837  -4.4277   4.6614\n"
        "+192.0.2.11      192.0.2.2        2 u   20   64  377  42.9649  -7.9074  12.5186\n"
        " SHM(0)          .GPS.            0 l    3   16  377   0.0000  81.2000   2.1000\n"
    )
)
GPS_SELECTED = (
    HEADER
    + POOL
    + (
        " 192.0.2.10      192.0.2.1        2 u  900   64    0  38.3837  -4.4277   4.6614\n"
        "*SHM(0)          .GPS.            0 l    3   16  377   0.0000   1.2000   2.1000\n"
    )
)
NOTHING_SELECTED = (
    HEADER
    + POOL
    + (" 192.0.2.10      192.0.2.1        2 u  900   64    0  38.3837  -4.4277   4.6614\n")
)
RV = (
    "associd=0 status=0615 leap_none, sync_ntp, 1 event, clock_sync,\n"
    "leap=00, stratum=3, precision=-24, rootdelay=39.223, rootdisp=37.185,\n"
    "rootdist=41.314, refid=192.0.2.10,\n"
    "reftime=ee64fbdf.6ef30ae5 2026-09-28T14:44:47.433Z, tc=10, peer=17771,\n"
    "offset=-4.462676, frequency=4.451, sys_jitter=2.105615, clk_jitter=2.011446,\n"
    'clock=ee65000f.24d1750b 2026-09-28T15:02:39.143Z, processor="x86_64",\n'
    'system="Linux", version="ntpd ntpsec-1.2.3",\n'
)
RV_NEVER = RV.replace(
    "reftime=ee64fbdf.6ef30ae5 2026-09-28T14:44:47.433Z",
    "reftime=00000000.00000000 1900-01-01T00:00:00.000Z",
)


def _ntpq(
    peers: str | None, rv: str | None
) -> tuple[Callable[[tuple[str, ...]], str | None], list[tuple[str, ...]]]:
    asked: list[tuple[str, ...]] = []

    def answer(args: tuple[str, ...]) -> str | None:
        asked.append(args)
        if args == ("-pn",):
            return peers
        if args == ("-c", "rv"):
            return rv
        return None

    return answer, asked


def _gps(name: str = "gps-receiver", parked: bool = False, address: str = "1-4") -> Parkable:
    return Parkable(
        name=name,
        summary="USB GNSS receivers",
        method="usb_deauthorize",
        quiet=(),
        sysfs_path=f"/sys/bus/usb/devices/{address}",
        identifier="1546:01a7",
        parked=parked,
    )


def test_the_selected_network_peer_is_followed(time_files: Path) -> None:
    ntpq, _ = _ntpq(NET_SELECTED, RV)
    state = gather(gps="awake", ntpq=ntpq)
    assert state.following == "network"
    assert state.offset_ms == pytest.approx(-4.4277)
    assert state.holdover_seconds is None
    assert state.last_source == "network"


def test_a_selected_shm_peer_is_the_gps(time_files: Path) -> None:
    ntpq, _ = _ntpq(GPS_SELECTED, RV.replace("refid=192.0.2.10", "refid=GPS"))
    state = gather(gps="awake", ntpq=ntpq)
    assert state.following == "gps"
    assert state.last_source == "gps"


def test_nothing_selected_is_holdover_measured_from_ntpds_own_clock(time_files: Path) -> None:
    ntpq, _ = _ntpq(NOTHING_SELECTED, RV)
    state = gather(gps="parked", ntpq=ntpq)
    assert state.following == "none"
    assert state.last_sync == datetime(2026, 9, 28, 14, 44, 47, 433000, tzinfo=UTC)
    assert state.holdover_seconds == 1071  # 15:02:39.143 - 14:44:47.433


def test_never_synchronised_has_no_holdover_age(time_files: Path) -> None:
    ntpq, _ = _ntpq(NOTHING_SELECTED, RV_NEVER)
    state = gather(gps="absent", ntpq=ntpq)
    assert state.following == "none"
    assert state.last_sync is None and state.holdover_seconds is None


def test_ntpq_is_always_asked_numerically(time_files: Path) -> None:
    """Review Focus 1: `ntpq -p` without -n waits on reverse DNS, and offline
    there is none."""
    ntpq, asked = _ntpq(NET_SELECTED, RV)
    gather(gps="awake", ntpq=ntpq)
    assert asked == [("-pn",), ("-c", "rv")]


def test_run_ntpq_goes_through_the_runner_with_the_argv_given() -> None:
    runner = RecordingRunner(
        {"ntpq -pn": CommandResult(argv=("ntpq", "-pn"), returncode=0, stdout="x", stderr="")}
    )
    assert run_ntpq(("-pn",), runner) == "x"
    assert runner.commands[0].argv == ("ntpq", "-pn")
    assert not runner.commands[0].requires_root


def test_a_silent_ntpd_is_unknown_with_a_reason(time_files: Path) -> None:
    ntpq, _ = _ntpq(None, None)
    state = gather(gps="awake", ntpq=ntpq)
    assert state.following == "unknown"
    assert any("systemctl status ntpsec" in p for p in state.problems)


def test_without_ntpsec_nothing_is_asked(time_files: Path) -> None:
    Path(files.NTP_CONF).unlink()
    ntpq, asked = _ntpq(NET_SELECTED, RV)
    state = gather(gps="awake", ntpq=ntpq)
    assert state.daemon is None and state.following == "unknown"
    assert asked == []


def test_an_unreadable_mode_file_reads_as_auto_with_the_reason(time_files: Path) -> None:
    Path(files.TIME_CONFIG).parent.mkdir(parents=True)
    Path(files.TIME_CONFIG).write_text("mode: sometimes\n")
    ntpq, _ = _ntpq(NET_SELECTED, RV)
    state = gather(gps="awake", ntpq=ntpq)
    assert (state.mode, state.mode_set) == ("auto", False)
    assert any("not a time mode" in p for p in state.problems)


def test_a_set_mode_is_reported_as_set(time_files: Path) -> None:
    Path(files.TIME_CONFIG).parent.mkdir(parents=True)
    Path(files.TIME_CONFIG).write_text(render_mode_file("gps-only"))
    ntpq, _ = _ntpq(NET_SELECTED, RV)
    assert gather(gps="awake", ntpq=ntpq).mode_set


def test_gps_from_the_parkable_survey() -> None:
    assert gps_from([]) == "absent"
    assert gps_from([_gps(name="hackrf")]) == "absent"
    assert gps_from([_gps(parked=True)]) == "parked"
    assert gps_from([_gps(parked=True), _gps(parked=False, address="1-5")]) == "awake"


def test_has_rtc(time_files: Path) -> None:
    assert has_rtc()
    (Path(files.RTC_CLASS) / "rtc0").rmdir()
    assert not has_rtc()
    Path(files.RTC_CLASS).rmdir()
    assert not has_rtc()


def test_grants_need_the_dropin_and_where_apparmor_is_in_use_the_rule(time_files: Path) -> None:
    assert not grants_installed()
    Path(files.DROPIN).parent.mkdir(parents=True)
    Path(files.DROPIN).write_text("[Service]\n")
    assert grants_installed(), "no AppArmor profile: the drop-in is the whole grant"
    Path(files.APPARMOR_PROFILE).parent.mkdir(parents=True)
    Path(files.APPARMOR_PROFILE).write_text("profile\n")
    Path(files.APPARMOR_LOCAL).parent.mkdir(parents=True)
    Path(files.APPARMOR_LOCAL).write_text("")
    assert not grants_installed()
    Path(files.APPARMOR_LOCAL).write_text(f"{APPARMOR_RULE}\n")
    assert grants_installed()


def test_a_dhcp_config_counts_unless_it_is_ignored(time_files: Path) -> None:
    assert not dhcp_config_in_use()
    Path(files.DHCP_CONF).parent.mkdir(parents=True)
    Path(files.DHCP_CONF).write_text("pool 192.0.2.1\n")
    Path(files.NTPSEC_DEFAULT).parent.mkdir(parents=True)
    Path(files.NTPSEC_DEFAULT).write_text('NTPD_OPTS="-g"\nIGNORE_DHCP=""\n')
    assert dhcp_config_in_use()
    Path(files.NTPSEC_DEFAULT).write_text('NTPD_OPTS="-g"\nIGNORE_DHCP="yes"\n')
    assert not dhcp_config_in_use()


def test_the_json_is_the_trays_contract(time_files: Path) -> None:
    ntpq, _ = _ntpq(NOTHING_SELECTED, RV)
    body = gather(gps="parked", ntpq=ntpq).as_json()
    assert tuple(body) == JSON_KEYS
    assert json.loads(json.dumps(body))["last_sync"] == "2026-09-28T14:44:47.433000+00:00"


def test_parse_peers_skips_the_header_and_reads_the_tally() -> None:
    peers = parse_peers(NET_SELECTED)
    assert [p.tally for p in peers] == [" ", "*", "+", " "]
    assert peers[3].remote == "SHM(0)" and peers[3].refid == ".GPS."


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(45, "0 min"), (1071, "17 min"), (11_520, "3 h 12 min"), (187_200, "2 d 4 h")],
)
def test_format_duration(seconds: int, text: str) -> None:
    assert format_duration(seconds) == text


BASE = TimeState(
    mode="auto",
    mode_set=False,
    daemon="ntpsec",
    gps="awake",
    following="network",
    offset_ms=-4.4,
    last_sync=datetime(2026, 9, 28, 14, 44, tzinfo=UTC),
    last_source="network",
    holdover_seconds=None,
    rtc=True,
    grants=True,
    dhcp_config=False,
    problems=(),
)


def _state(**over: Any) -> TimeState:
    return replace(BASE, **over)


def test_describe_says_holdover_since_when_and_from_what() -> None:
    text = "\n".join(describe(_state(following="none", holdover_seconds=1071)))
    assert "Holdover since 14:44 UTC (17 min)" in text
    assert "last synchronised from the network" in text


def test_describe_names_the_rtc_fix() -> None:
    assert any("RTC module" in ln for ln in describe(_state(rtc=False)))


def test_describe_names_the_gap_on_a_target_without_ntpsec() -> None:
    text = "\n".join(describe(_state(daemon=None, following="unknown")))
    assert "not ntpsec" in text and "D-058" in text


def test_describe_says_a_parked_receiver_turns_gps_time_off() -> None:
    assert any("parked" in ln and "off" in ln for ln in describe(_state(gps="parked")))


def test_describe_points_at_hardware_apply_when_the_grants_are_missing() -> None:
    assert any("hardware apply" in ln for ln in describe(_state(grants=False)))


def test_a_conffile_left_by_apt_remove_is_not_ntpsec(time_files: Path) -> None:
    """Final review I3: `apt remove ntpsec` keeps /etc/ntpsec/ntp.conf; the
    daemon is gone, so the gap is named and ntpq is not asked."""
    Path(files.NTPD).unlink()
    ntpq, asked = _ntpq(NET_SELECTED, RV)
    state = gather(gps="awake", ntpq=ntpq)
    assert state.daemon is None
    assert asked == []
