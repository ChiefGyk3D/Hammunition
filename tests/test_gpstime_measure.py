# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``time measure``: the GPS takeover and the PPS pulses, read-only (issue #310).

``ppstest`` is a shell script on a PATH of its own; ``ntpq`` is replaced at
``run_ntpq`` because the suite blocks the real binary.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.gpstime import measure

cli = importlib.import_module("hammunition.cli.main")

HEADER = (
    "     remote           refid      st t when poll reach   delay   offset   jitter\n"
    "==============================================================================\n"
)


def peers(gps: str, *network: str) -> str:
    rows = [f"{gps[0]}SHM(0)          .GPS.            0 l    5   16   {gps[1:]}"]
    rows += [f"{n[0]}203.0.113.{i}  .NTP.  2 u   30   64  {n[1:]}" for i, n in enumerate(network)]
    return HEADER + "\n".join(rows) + "\n"


# tally+reach  delay offset jitter
GPS_REJECTED = "x377    0.000  -21.000  1.0"
GPS_SELECTED = "*377    0.000  -2.500  0.5"
NET_UP = "*377   10.100   -0.500   0.2"
NET_DOWN = "-0   0.000   0.000   0.0"


def test_a_sample_reads_gps_the_system_peer_and_the_best_network_peer() -> None:
    s = measure.sample(peers(GPS_REJECTED, NET_UP, "-377  11.0  1.0  0.1"), 30.0)
    assert s.gps is not None and s.gps.tally == "x" and s.gps.offset_ms == -21.0
    assert s.selected == "203.0.113.0" and not s.gps_selected
    assert s.network is not None and s.network.tally == "*"
    assert (s.network_reaching, s.network_total) == (2, 2)


def test_the_gps_as_system_peer_is_recognised() -> None:
    s = measure.sample(peers(GPS_SELECTED, NET_DOWN), 90.0)
    assert s.gps_selected and s.selected == "SHM(0)"
    assert (s.network_reaching, s.network_total) == (0, 1)


def test_a_sample_line_names_every_part() -> None:
    line = measure.describe_sample(measure.sample(peers(GPS_REJECTED, NET_UP), 60.0))
    assert "t+   60s" in line and "follows 203.0.113.0" in line
    assert "GPS xSHM(0) reach 377 offset -21.000 ms" in line
    assert "network *203.0.113.0 reach 377" in line and "(1/1 reaching)" in line


def test_no_gps_peer_and_no_network_peer_are_absent_not_errors() -> None:
    s = measure.sample(HEADER, 0.0)
    assert s.gps is None and s.network is None and s.selected is None
    assert "GPS absent" in measure.describe_sample(s)


def _run(texts: list[str | None]) -> tuple[list[measure.Sample] | None, list[float], list[str]]:
    feed = iter(texts)
    slept: list[float] = []
    said: list[str] = []
    got = measure.measure(
        lambda: next(feed),
        minutes=len(texts) * 30 / 60 - 0.5,
        interval=30.0,
        sleep=slept.append,
        emit=said.append,
    )
    return got, slept, said


def test_measure_takes_one_sample_per_interval_and_sleeps_between() -> None:
    texts: list[str | None] = [
        peers(GPS_REJECTED, NET_UP),
        peers(GPS_REJECTED, NET_DOWN),
        peers(GPS_SELECTED, NET_DOWN),
    ]
    got, slept, said = _run(texts)
    assert got is not None and [s.elapsed for s in got] == [0.0, 30.0, 60.0]
    assert slept == [30.0, 30.0] and len(said) == 3


def test_a_silent_ntpq_is_noted_and_all_silence_is_none() -> None:
    got, _, said = _run([None, peers(GPS_REJECTED, NET_UP)])
    assert got is not None and len(got) == 1 and "ntpq did not answer" in said[0]
    assert _run([None, None])[0] is None


def test_an_interrupt_ends_the_run_with_what_was_collected() -> None:
    calls = iter([peers(GPS_REJECTED, NET_UP)])

    def read() -> str | None:
        try:
            return next(calls)
        except StopIteration:
            raise KeyboardInterrupt from None

    said: list[str] = []
    got = measure.measure(read, minutes=5, interval=1.0, sleep=lambda _s: None, emit=said.append)
    assert got is not None and len(got) == 1 and "interrupted" in said[-1]


def test_takeover_is_timed_from_the_first_sample_the_gps_is_selected() -> None:
    samples = [
        measure.sample(peers(GPS_REJECTED, NET_UP), 0.0),
        measure.sample(peers(GPS_REJECTED, NET_DOWN), 30.0),
        measure.sample(peers(GPS_SELECTED, NET_DOWN), 90.0),
    ]
    summary = measure.summarise(samples)
    assert summary.gps_selected_at == 90.0 and summary.network_gone_at == 30.0
    assert summary.gps_offset_range_ms == (-21.0, -2.5) and summary.gps_selected_last
    text = "\n".join(measure.verdict(summary))
    assert "became the system peer 90 s into the run" in text


def test_with_the_network_up_the_gps_is_never_selected_by_design() -> None:
    summary = measure.summarise([measure.sample(peers(GPS_REJECTED, NET_UP), 0.0)] * 2)
    assert summary.gps_selected_at is None and summary.network_ever_reaching
    assert "rejects the GPS while it has network peers" in "\n".join(measure.verdict(summary))


def test_network_gone_but_no_takeover_says_to_run_longer() -> None:
    summary = measure.summarise([measure.sample(peers(GPS_REJECTED, NET_DOWN), 0.0)])
    assert "run longer" in "\n".join(measure.verdict(summary))


def test_no_gps_refclock_in_ntpq_says_gps_time_is_not_configured() -> None:
    text = "\n".join(measure.verdict(measure.summarise([measure.sample(HEADER, 0.0)])))
    assert "never appeared" in text and "not configured" in text


# ---- PPS --------------------------------------------------------------------


def _tool(directory: Path, name: str, body: str) -> None:
    directory.mkdir(exist_ok=True)
    tool = directory / name
    tool.write_text(f"#!/bin/sh\n{body}\n")
    tool.chmod(0o755)


@pytest.fixture
def pps_machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "pps0").write_text("")
    sysfs = tmp_path / "sys"
    entry = sysfs / "class" / "pps" / "pps0"
    entry.mkdir(parents=True)
    (entry / "name").write_text("acm0\n")
    (entry / "path").write_text("/dev/ttyACM0\n")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")
    return {"dev": dev, "sysfs": sysfs, "bin": tmp_path / "bin"}


def test_real_pulses_are_counted_from_the_sequence_numbers(pps_machine: dict[str, Path]) -> None:
    _tool(
        pps_machine["bin"],
        "ppstest",
        'echo "ok, found 1 source(s), now start fetching data..."\n'
        "for i in 1 2 3 4; do\n"
        '  echo "source 0 - assert 17$i.000000123, sequence: $i - clear  0.000000000, sequence: 0"\n'
        "  sleep 0.2\n"
        "done\nsleep 30",
    )
    r = measure.run_ppstest(1.5, sysfs=str(pps_machine["sysfs"]), dev=str(pps_machine["dev"]))
    assert r.error is None and r.pulses == 4 and r.device_present
    assert r.devices == ("pps0 (name acm0, path /dev/ttyACM0)",)


def test_timeouts_are_no_pulses(pps_machine: dict[str, Path]) -> None:
    _tool(
        pps_machine["bin"],
        "ppstest",
        'while true; do echo "time_pps_fetch() error -1 (Connection timed out)"; sleep 0.2; done',
    )
    r = measure.run_ppstest(1.0, sysfs=str(pps_machine["sysfs"]), dev=str(pps_machine["dev"]))
    assert r.pulses == 0 and r.error is not None and "no pulses" in r.error


def test_a_ppstest_that_exits_at_once_reports_what_it_said(pps_machine: dict[str, Path]) -> None:
    _tool(
        pps_machine["bin"], "ppstest", 'echo "unable to open device: Permission denied" >&2; exit 1'
    )
    r = measure.run_ppstest(5.0, sysfs=str(pps_machine["sysfs"]), dev=str(pps_machine["dev"]))
    assert r.error is not None and "Permission denied" in r.error


def test_a_missing_ppstest_and_a_missing_device_are_said(
    pps_machine: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(pps_machine["bin"]))  # no ppstest, no stdbuf
    r = measure.run_ppstest(1.0, sysfs=str(pps_machine["sysfs"]), dev=str(pps_machine["dev"]))
    assert r.ppstest is None and r.error is not None and "pps-tools" in r.error
    _tool(pps_machine["bin"], "ppstest", "exit 0")
    (pps_machine["dev"] / "pps0").unlink()
    r = measure.run_ppstest(1.0, sysfs=str(pps_machine["sysfs"]), dev=str(pps_machine["dev"]))
    assert not r.device_present and r.error == "/dev/pps0 does not exist"


# ---- the command --------------------------------------------------------------


def test_the_command_samples_and_prints_the_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The suite blocks a real `ntpq` (conftest.MachineQueried); `run_ntpq` has its own tests.
    monkeypatch.setattr(
        "hammunition.gpstime.state.run_ntpq", lambda _args, runner=None: peers(GPS_REJECTED, NET_UP)
    )
    monkeypatch.setattr("hammunition.gpstime.state.ntpsec_installed", lambda: True)
    rc = cli.main(["time", "measure", "--minutes", "0.02", "--interval", "0.5"])
    text = capsys.readouterr().out
    assert rc == 0
    assert text.count("follows 203.0.113.0") == 3  # t+0, 0.5, 1.0 within 1.2 s
    assert "rejects the GPS while it has network peers" in text


def test_the_command_refuses_without_ntpsec_and_with_nonsense(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("hammunition.gpstime.state.ntpsec_installed", lambda: False)
    assert cli.main(["time", "measure"]) == 2
    assert "ntpsec is not installed" in capsys.readouterr().err
    assert cli.main(["time", "measure", "--minutes", "0"]) == 2


def test_the_command_has_no_json_form(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["time", "measure", "--json"]) == 2
    assert '"kind": "error"' in capsys.readouterr().out.replace('":"', '": "')


def test_measure_is_not_a_logged_run_and_writes_no_state() -> None:
    import argparse

    args = argparse.Namespace(command="time", time_command="measure", json=False)
    assert cli._loggable(args) is False


def test_pps_flag_prints_the_pulse_verdict_or_the_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "hammunition.gpstime.state.run_ntpq", lambda _args, runner=None: peers(GPS_REJECTED, NET_UP)
    )
    monkeypatch.setattr("hammunition.gpstime.state.ntpsec_installed", lambda: True)
    asked: list[float] = []

    def fake(seconds: float, **_k: object) -> measure.PpsResult:
        asked.append(seconds)
        return measure.PpsResult(
            True, ("pps0 (name acm0, path /dev/ttyACM0)",), "/x", 58, seconds, None, ("l",)
        )

    monkeypatch.setattr(measure, "run_ppstest", fake)
    args = [
        "time",
        "measure",
        "--minutes",
        "0.01",
        "--interval",
        "0.5",
        "--pps",
        "--pps-seconds",
        "7",
    ]
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert asked == [7.0] and "58 pulse(s) in 7 s: the PPS source is real." in out
    assert "/sys/class/pps: pps0 (name acm0" in out

    monkeypatch.setattr(
        measure,
        "run_ppstest",
        lambda s, **_k: measure.PpsResult(
            False, (), None, 0, s, "ppstest is not installed (package pps-tools)", ()
        ),
    )
    assert cli.main(args) == 0
    assert "ppstest is not installed (package pps-tools)" in capsys.readouterr().out
