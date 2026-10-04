# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hardware gps-resume-report``: read-only, and right about what it reads (issue #177).

The fakes are the resume script's own (a loopback gpsd, a ``/dev`` and a sysfs
under tmp_path) plus a ``systemctl`` that prints ``show`` output.
"""

from __future__ import annotations

import functools
import importlib
import os
from pathlib import Path

import pytest

import test_gps_resume_script as fakes
from hammunition.hardware import gps_resume as gr
from hammunition.hardware import gps_resume_report as report
from hammunition.hardware import gps_resume_script as script
from json_support import parse_one, validate
from test_gps_resume import _applied

cli = importlib.import_module("hammunition.cli.main")

# The resume script's fakes, shared: a fixture is found by its name in this module.
FakeGpsd = fakes.FakeGpsd
alive = fakes.alive
_receiver = fakes._receiver
machine = fakes.machine
gpsd = fakes.gpsd
usb = fakes.usb

SHOW = (
    "LoadState=loaded\nUnitFileState=enabled\nActiveState=inactive\nResult=success\n"
    "ExecMainStatus=0\nActiveEnterTimestamp=Sun 2026-10-04 09:01:02 EDT\n"
    "ExecMainExitTimestamp=Sun 2026-10-04 09:01:30 EDT\n"
)


def _systemctl(tmp_path: Path, output: str = SHOW, code: int = 0) -> str:
    tool = tmp_path / "fake-systemctl"
    body = tmp_path / "show.txt"
    body.write_text(output)
    tool.write_text(f"#!/bin/sh\ncat {body}\nexit {code}\n")
    tool.chmod(0o755)
    return str(tool)


def _gather(
    m: dict[str, Path],
    server: FakeGpsd | None,
    tmp_path: Path,
    *,
    window: float = 1.0,
    systemctl: str | None = None,
) -> report.ResumeReport:
    return report.gather(
        dev=str(m["dev"]),
        sysfs=str(m["sysfs"]),
        port=server.port if server is not None else 9,
        timeout=1.0,
        data_window=window,
        systemctl=systemctl or _systemctl(tmp_path),
        log_path=str(m["runlog"]),
    )


def _installed(resume_files: Path, tmp_path: Path, m: dict[str, Path]) -> None:
    _applied(tmp_path)
    m["runlog"].write_text("gps-resume run started 2026-10-04T13:01:02Z\ndata check: ok\n")


def test_parse_show_reads_key_value_lines() -> None:
    assert report.parse_show("A=1\nB=two words\nnoequals\nC=\n") == {
        "A": "1",
        "B": "two words",
        "C": "",
    }


def test_a_current_step_and_a_live_receiver_have_no_findings(
    resume_files: Path,
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    tmp_path: Path,
) -> None:
    _installed(resume_files, tmp_path, machine)
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty]], watches=[alive(tty)])
    gpsd.append(server)
    r = _gather(machine, server, tmp_path)
    assert [f.state for f in r.files] == ["current", "current", "current"]
    assert r.enabled
    assert (r.unit.load_state, r.unit.result, r.unit.exec_main_status) == ("loaded", "success", "0")
    assert r.unit.active_enter == "Sun 2026-10-04 09:01:02 EDT"
    assert r.gpsd_devices == [tty]
    (rx,) = r.receivers
    assert rx.listed_by_gpsd is True and rx.data_seconds is not None
    assert (rx.usb.vendor, rx.usb.product, rx.usb.authorized) == ("1546", "01a9", "1")
    assert rx.usb.device is not None and rx.usb.device.endswith("3-5.1")  # never the hub
    assert r.log_present and r.log_lines[-1] == "data check: ok"
    assert r.findings == ()


def test_a_script_that_differs_says_to_re_run_apply(
    resume_files: Path, machine: dict[str, Path], tmp_path: Path
) -> None:
    _installed(resume_files, tmp_path, machine)
    Path(gr.SCRIPT).write_text(Path(gr.SCRIPT).read_text() + "# older\n")
    r = _gather(machine, None, tmp_path)
    assert r.files[0].state == "differs"
    assert any("re-run `hammunition hardware apply`" in f and gr.SCRIPT in f for f in r.findings)


def test_a_script_with_the_wrong_mode_is_not_current(
    resume_files: Path, machine: dict[str, Path], tmp_path: Path
) -> None:
    _installed(resume_files, tmp_path, machine)
    os.chmod(gr.SCRIPT, 0o644)
    assert _gather(machine, None, tmp_path).files[0].state == "wrong-mode"


def test_nothing_installed_reads_absent_and_names_apply(
    resume_files: Path, machine: dict[str, Path], tmp_path: Path
) -> None:
    r = _gather(
        machine,
        None,
        tmp_path,
        systemctl=_systemctl(tmp_path, "LoadState=not-found\nActiveState=inactive\n"),
    )
    assert [f.state for f in r.files] == ["absent"] * 3
    assert not r.enabled
    assert any("is not installed; run `hammunition hardware apply`" in f for f in r.findings)


def test_a_failed_last_run_is_reported_with_its_exit_status(
    resume_files: Path, machine: dict[str, Path], tmp_path: Path
) -> None:
    _installed(resume_files, tmp_path, machine)
    failed = SHOW.replace("Result=success", "Result=exit-code").replace(
        "ExecMainStatus=0", "ExecMainStatus=1"
    )
    r = _gather(machine, None, tmp_path, systemctl=_systemctl(tmp_path, failed))
    assert any("last run exited 1 (result exit-code)" in f for f in r.findings)


def test_a_silent_receiver_and_a_missing_gpsd_are_findings(
    resume_files: Path,
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    tmp_path: Path,
) -> None:
    _installed(resume_files, tmp_path, machine)
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    silent = FakeGpsd([[tty]], watches=[None])
    gpsd.append(silent)
    r = _gather(machine, silent, tmp_path, window=0.5)
    assert r.receivers[0].data_seconds is None
    assert any("was silent for 0.5 s" in f for f in r.findings)

    r = _gather(machine, None, tmp_path, window=0.5)
    assert r.gpsd_devices is None
    assert any("gpsd did not answer" in f for f in r.findings)
    assert r.receivers[0].listed_by_gpsd is None


def test_gpsd_not_listing_the_receiver_is_a_finding(
    resume_files: Path,
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    tmp_path: Path,
) -> None:
    _installed(resume_files, tmp_path, machine)
    _receiver(machine["dev"])
    server = FakeGpsd([[]], watches=[alive("x")])
    gpsd.append(server)
    r = _gather(machine, server, tmp_path, window=0.5)
    assert r.receivers[0].listed_by_gpsd is False
    assert any("gpsd does not list" in f for f in r.findings)


def test_no_receiver_attached_is_said_not_an_error(
    resume_files: Path, machine: dict[str, Path], gpsd: list[FakeGpsd], tmp_path: Path
) -> None:
    _installed(resume_files, tmp_path, machine)
    server = FakeGpsd([[]])
    gpsd.append(server)
    r = _gather(machine, server, tmp_path)
    assert r.receivers == ()
    assert r.findings == ()
    text = "\n".join(report_text(r))
    assert "no /dev/gpsN: no receiver attached, or it is parked" in text


def report_text(r: report.ResumeReport) -> list[str]:
    from hammunition.interface.gps_resume import (
        build_gps_resume_report,
        render_gps_resume_report,
    )

    return render_gps_resume_report(build_gps_resume_report(r))


def test_a_receiver_with_no_usb_parent_reports_why(
    resume_files: Path, machine: dict[str, Path], gpsd: list[FakeGpsd], tmp_path: Path
) -> None:
    _installed(resume_files, tmp_path, machine)
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty]], watches=[alive(tty)])
    gpsd.append(server)
    r = _gather(machine, server, tmp_path)
    assert r.receivers[0].usb.error == "/sys/class/tty/ttyACM0/device is absent"
    assert any("could not find the receiver's USB device" in f for f in r.findings)


def test_the_log_is_tailed_and_dated(
    resume_files: Path, machine: dict[str, Path], tmp_path: Path
) -> None:
    _installed(resume_files, tmp_path, machine)
    machine["runlog"].write_text("".join(f"line {i}\n" for i in range(100)))
    r = _gather(machine, None, tmp_path)
    assert len(r.log_lines) == report.LOG_TAIL and r.log_lines[-1] == "line 99"
    assert r.log_modified is not None and r.log_modified.endswith("Z")


def test_a_missing_log_is_said_and_is_a_finding_only_when_the_step_is_current(
    resume_files: Path, machine: dict[str, Path], tmp_path: Path
) -> None:
    _applied(tmp_path)
    r = _gather(machine, None, tmp_path)
    assert not r.log_present
    assert any("no log of a last run" in f for f in r.findings)
    assert "no log: the step has not run since boot" in "\n".join(report_text(r))


def test_an_unusable_systemctl_is_reported_not_raised(
    resume_files: Path, machine: dict[str, Path], tmp_path: Path
) -> None:
    r = _gather(machine, None, tmp_path, systemctl=str(tmp_path / "no-such-systemctl"))
    assert r.unit.error is not None and r.unit.load_state is None
    r = _gather(machine, None, tmp_path, systemctl=_systemctl(tmp_path, "boom\n", code=1))
    assert r.unit.error == "boom"


def _tree(root: Path) -> dict[str, tuple[float, bytes | None]]:
    return {
        str(p): (p.lstat().st_mtime, p.read_bytes() if p.is_file() and not p.is_symlink() else None)
        for p in sorted(root.rglob("*"))
    }


def test_the_report_never_writes_keys_or_changes_power(
    resume_files: Path,
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _installed(resume_files, tmp_path, machine)
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty]], watches=[None])
    gpsd.append(server)

    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("the report wrote something")

    monkeypatch.setattr(script, "write_value", refuse)
    monkeypatch.setattr(script, "open_log", refuse)
    monkeypatch.setattr(script, "run", refuse)  # no gpsdctl, no restart
    systemctl = _systemctl(tmp_path)
    before = {k: _tree(m) for k, m in (("sys", machine["sysfs"]), ("dev", machine["dev"]))}
    before["root"] = _tree(resume_files)
    _gather(machine, server, tmp_path, window=0.3, systemctl=systemctl)
    after = {k: _tree(m) for k, m in (("sys", machine["sysfs"]), ("dev", machine["dev"]))}
    after["root"] = _tree(resume_files)
    assert before == after
    assert (machine["sysfs"] / "devices").is_dir()
    for node in (machine["sysfs"] / "devices").rglob("authorized"):
        assert node.read_text() == "1\n"


def test_the_command_prints_a_table_and_a_valid_json_document(
    resume_files: Path,
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _installed(resume_files, tmp_path, machine)
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty]], watches=[alive(tty), alive(tty)])
    gpsd.append(server)
    systemctl = _systemctl(tmp_path)
    monkeypatch.setattr(
        report,
        "gather",
        functools.partial(
            report.gather,
            dev=str(machine["dev"]),
            sysfs=str(machine["sysfs"]),
            port=server.port,
            systemctl=systemctl,
            log_path=str(machine["runlog"]),
        ),
    )
    assert cli.main(["hardware", "gps-resume-report", "--data-window", "1"]) == 0
    out = capsys.readouterr().out
    assert "GPS resume step (issue #177)" in out
    assert "state" in out and "current" in out
    assert "1546:01a9" in out
    assert "Nothing to fix" in out

    assert cli.main(["hardware", "gps-resume-report", "--data-window", "1", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "gps-resume-report"
    assert doc["findings"] == [] and doc["gpsd_answered"] is True
    assert doc["receivers"][0]["usb"]["vendor"] == "1546"
