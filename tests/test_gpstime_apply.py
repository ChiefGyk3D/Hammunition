# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The root half of `time mode`: three guarded files, one restart, a rollback.  D-058."""

from __future__ import annotations

import fcntl
import os
import threading
import time
from pathlib import Path

import pytest

from hammunition.backends.base import CommandResult, RecordingRunner
from hammunition.gpstime import apply as time_apply
from hammunition.gpstime import files
from hammunition.gpstime.apply import apply_mode, guard_time
from hammunition.gpstime.mode import Route, TimeError, render_mode_file, render_ntp_d
from hammunition.gpstime.ntpconf import transform
from hammunition.hardware.power import PowerError, guard

CONFFILE = Route(tos_in_ntp_d=False, auto_prefers_pools=True)
FAILING_RESTART = {
    "systemctl restart ntpsec": CommandResult(
        argv=("systemctl", "restart", "ntpsec"), returncode=1, stdout="", stderr="Job failed"
    )
}


def test_a_mode_writes_three_files_and_restarts_ntpsec(
    time_files: Path, debian_ntp_conf: str
) -> None:
    runner = RecordingRunner()
    assert apply_mode("gps-only", route=CONFFILE, runner=runner) == []
    assert Path(files.NTP_D_FILE).read_text() == render_ntp_d("gps-only", CONFFILE)
    assert Path(files.NTP_CONF).read_text() == transform(debian_ntp_conf, "gps-only", CONFFILE)
    assert Path(files.TIME_CONFIG).read_text() == render_mode_file("gps-only")
    assert [c.argv for c in runner.commands] == [("systemctl", "restart", "ntpsec")]


def test_the_same_mode_twice_writes_nothing_and_restarts_nothing(time_files: Path) -> None:
    apply_mode("auto", route=CONFFILE, runner=RecordingRunner())
    runner = RecordingRunner()
    assert apply_mode("auto", route=CONFFILE, runner=runner) == []
    assert runner.commands == []


def test_ntp_only_after_gps_only_puts_the_conffile_back_byte_for_byte(
    time_files: Path, debian_ntp_conf: str
) -> None:
    apply_mode("gps-only", route=CONFFILE, runner=RecordingRunner())
    apply_mode("ntp-only", route=CONFFILE, runner=RecordingRunner())
    assert Path(files.NTP_CONF).read_text() == debian_ntp_conf


def test_without_ntpsec_it_refuses_and_creates_nothing(time_files: Path) -> None:
    Path(files.NTP_CONF).unlink()
    with pytest.raises(TimeError, match="ntpsec is not installed"):
        apply_mode("auto", runner=RecordingRunner())
    assert not Path(files.TIME_CONFIG).exists()


def test_a_missing_anchor_refuses_before_any_write(time_files: Path, debian_ntp_conf: str) -> None:
    Path(files.NTP_CONF).write_text(debian_ntp_conf.replace("tos minclock 4 minsane 3\n", ""))
    runner = RecordingRunner()
    with pytest.raises(TimeError, match="tos minclock N minsane N"):
        apply_mode("gps-only", route=CONFFILE, runner=runner)
    assert not Path(files.NTP_D_FILE).exists()
    assert not Path(files.TIME_CONFIG).exists()
    assert runner.commands == []


def test_a_failed_restart_puts_the_old_files_back(time_files: Path, debian_ntp_conf: str) -> None:
    """Review Focus 3."""
    runner = RecordingRunner(FAILING_RESTART)
    problems = apply_mode("gps-only", route=CONFFILE, runner=runner)
    assert len(problems) == 1
    assert "did not restart (Job failed)" in problems[0]
    assert "previous files were put back" in problems[0]
    assert "journalctl -u ntpsec -n 20" in problems[0]
    assert Path(files.NTP_CONF).read_text() == debian_ntp_conf
    assert not Path(files.NTP_D_FILE).exists()
    assert not Path(files.TIME_CONFIG).exists()
    assert len(runner.commands) == 2, "the old files are restarted on too"


def test_a_write_that_fails_part_way_puts_back_what_it_wrote(
    time_files: Path, debian_ntp_conf: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.rootfiles import atomic_write as real

    def refusing_the_conffile(path: Path, content: str, *, mode: int = 0o644) -> None:
        if str(path) == files.NTP_CONF and content != debian_ntp_conf:
            raise OSError("read-only file system")
        real(path, content, mode=mode)

    monkeypatch.setattr(time_apply, "atomic_write", refusing_the_conffile)
    runner = RecordingRunner()
    problems = apply_mode("gps-only", route=CONFFILE, runner=runner)
    assert problems and "previous files were put back" in problems[0]
    assert not Path(files.NTP_D_FILE).exists(), "the ntp.d file written first was taken back"
    assert Path(files.NTP_CONF).read_text() == debian_ntp_conf
    assert runner.commands == [], "nothing is restarted when nothing changed"


def test_two_runs_at_once_wait_for_each_other(time_files: Path) -> None:
    lock_dir = Path(files.TIME_CONFIG).parent
    lock_dir.mkdir(parents=True)
    fd = os.open(lock_dir, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    results: list[list[str]] = []
    worker = threading.Thread(
        target=lambda: results.append(apply_mode("auto", route=CONFFILE, runner=RecordingRunner()))
    )
    try:
        worker.start()
        time.sleep(0.3)
        assert not Path(files.TIME_CONFIG).exists(), "written while another run held the lock"
    finally:
        os.close(fd)
    worker.join(timeout=5)
    assert results == [[]]


def test_guard_time_admits_exactly_the_three_files(time_files: Path) -> None:
    for path in (files.TIME_CONFIG, files.NTP_D_FILE, files.NTP_CONF):
        assert guard_time(path) == path
    for path in (
        "/etc/shadow",
        files.NTP_D_DIR + "/../ntp.conf",
        files.DROPIN,
        files.APPARMOR_LOCAL,
        files.NTP_CONF + ".d",
    ):
        with pytest.raises(TimeError, match="not one of the three files"):
            guard_time(path)


def test_the_sysfs_guard_still_refuses_the_time_files(time_files: Path) -> None:
    for path in (files.NTP_CONF, files.NTP_D_FILE, files.TIME_CONFIG):
        with pytest.raises(PowerError):
            guard(path)


def test_a_conffile_without_ntpd_refuses_and_writes_nothing(time_files: Path) -> None:
    """Final review I3: after `apt remove ntpsec` the conffile stays."""
    Path(files.NTPD).unlink()
    runner = RecordingRunner()
    with pytest.raises(TimeError, match="ntpsec is not installed"):
        apply_mode("auto", runner=runner)
    assert not Path(files.TIME_CONFIG).exists()
    assert not Path(files.NTP_D_FILE).exists()
    assert runner.commands == []
