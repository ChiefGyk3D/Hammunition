# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Suite-wide guarantees.

**No test reaches the network.** `hammunition.fetch` is the first code here that
can make an outbound connection, and a fetch test that quietly fell through to
the real internet would be slow, flaky, and — worse — would stop testing the
thing it names. So every socket to anywhere but loopback is blocked for the
whole suite: a test that tries gets a clear failure rather than a timeout, and
the network seam stays a seam because nothing can bypass it.

This is a property of the suite, not of any one test, which is why it is
enforced here rather than asserted in one place (CLAUDE.md: *prove properties,
not just behaviour*). Loopback stays open so a future test may bind a local
server if it needs one.

**No test asks the machine's package manager.** The same shape one layer down:
`apt-get --simulate` and `apt-cache policy` are unprivileged and answer at
plan time, so a test that mocks part of the apt backend and not all of it
runs the rest against whatever machine it is on. That is exactly what
happened when D-038 added the simulate step — the CLI dry-run test passed on
every dev box and GitHub runner, where a `git` package exists, and failed in
all four target containers, whose apt lists are empty. Blocking `apt-get`,
`apt-cache`, `apt`, `dpkg`, `dpkg-query` and `sudo` at the real runner makes
that a failure everywhere, naming the mock to add. Compilers, tar and the
rest stay open: the source-build tests run real builds on purpose.

**No test runs the real sudo, by either route.** The keepalive (D-062) runs
``sudo -v`` and ``sudo -n -v`` itself rather than through a runner, so it is
guarded separately: a ``sudo`` that resolves anywhere but under the test's
temporary directory -- a fake written by ``fake_tools.install_fakes`` --
fails the test. ``sudo -v`` on a developer's terminal would otherwise stop
the suite at a password prompt, and in CI it would quietly test nothing.
"""

from __future__ import annotations

import shutil
import socket
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

import hammunition.sudo_ticket as sudo_ticket
from hammunition.backends.base import Command, CommandResult, SubprocessRunner

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_run = SubprocessRunner.run
_real_sudo_run = sudo_ticket._run

MACHINE_QUERIES = frozenset(
    {
        "apt-get",
        "apt-cache",
        "apt",
        "dpkg",
        "dpkg-query",
        "sudo",
        "systemctl",
        "ntpq",
        "apparmor_parser",
    }
)


class MachineQueried(RuntimeError):
    """A test ran a package-manager or privileged command on the host."""


@pytest.fixture(autouse=True, scope="session")
def _no_machine_queries() -> Any:
    def guard(self: SubprocessRunner, command: Command) -> CommandResult:
        if command.argv and command.argv[0] in MACHINE_QUERIES:
            raise MachineQueried(
                f"the test suite blocked {command.argv[0]!r} ({command.description}). "
                f"Tests must not ask the machine's package manager: give the backend a "
                f"RecordingRunner, or monkeypatch every AptBackend method the code "
                f"under test reaches (lists_populated, probe and simulate at plan "
                f"time), so the result is the same in every target container."
            )
        return _real_run(self, command)

    SubprocessRunner.run = guard  # type: ignore[method-assign]
    try:
        yield
    finally:
        SubprocessRunner.run = _real_run  # type: ignore[method-assign]


def _fake(program: str) -> bool:
    """Whether *program* resolves on PATH to a file under the temp directory,
    or to nothing at all (the missing-sudo case is a test of its own)."""
    found = shutil.which(program)
    if found is None:
        return True
    return Path(found).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())


@pytest.fixture(autouse=True, scope="session")
def _no_real_sudo() -> Any:
    def guard(argv: Sequence[str], interactive: bool) -> int:
        if argv and not _fake(argv[0]):
            raise MachineQueried(
                f"the test suite blocked the real {argv[0]!r} ({' '.join(argv)}). Put a "
                f"fake sudo first on PATH with fake_tools.install_fakes, or pass "
                f"SudoKeepalive a run= function."
            )
        return _real_sudo_run(argv, interactive)

    sudo_ticket._run = guard
    try:
        yield
    finally:
        sudo_ticket._run = _real_sudo_run


def _loopback(address: Any) -> bool:
    """Whether *address* is loopback, for the address families that have one."""
    if not isinstance(address, tuple) or not address:
        # AF_UNIX and friends: a filesystem path, not the network.
        return True
    host = address[0]
    if not isinstance(host, str):
        return False
    return host in {"127.0.0.1", "::1", "localhost"} or host.startswith("127.")


class NetworkBlocked(RuntimeError):
    """A test tried to open a non-loopback connection."""


@pytest.fixture(autouse=True, scope="session")
def _no_network() -> Any:
    def guard(self: socket.socket, address: Any) -> Any:
        if not _loopback(address):
            raise NetworkBlocked(
                f"the test suite blocked a connection to {address!r}. Tests must not "
                f"reach the network: inject a fake Transport (hammunition.fetch) or "
                f"a RecordingRunner instead of letting a fetch fall through to the "
                f"real internet."
            )
        return _real_connect(self, address)

    def guard_ex(self: socket.socket, address: Any) -> Any:
        if not _loopback(address):
            raise NetworkBlocked(f"the test suite blocked a connection to {address!r}")
        return _real_connect_ex(self, address)

    socket.socket.connect = guard  # type: ignore[assignment,method-assign]
    socket.socket.connect_ex = guard_ex  # type: ignore[assignment,method-assign]
    try:
        yield
    finally:
        socket.socket.connect = _real_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = _real_connect_ex  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# GPS time (D-058): no test touches the host's time configuration
# ---------------------------------------------------------------------------

DEBIAN_NTP_CONF = """\
# /etc/ntpsec/ntp.conf, configuration for ntpd; see ntp.conf(5) for help

driftfile /var/lib/ntpsec/ntp.drift
leapfile /usr/share/zoneinfo/leap-seconds.list

# This should be maxclock 7, but the pool entries count towards maxclock.
tos maxclock 11

# Comment this out if you have a refclock and want it to be able to discipline
# the clock by itself (e.g. if the system is not connected to the network).
tos minclock 4 minsane 3

# Specify one or more NTP servers.

# Public NTP servers supporting Network Time Security:
# server time.cloudflare.com nts

# pool.ntp.org maps to about 1000 low-stratum NTP servers.  Your server will
# pick a different set every time it starts up.  Please consider joining the
# pool: <https://www.pool.ntp.org/join.html>
pool 0.debian.pool.ntp.org iburst
pool 1.debian.pool.ntp.org iburst
pool 2.debian.pool.ntp.org iburst
pool 3.debian.pool.ntp.org iburst

# By default, exchange time with everybody, but don't allow configuration.
restrict default kod nomodify noquery limited

# Local users may interrogate the ntp server more closely.
restrict 127.0.0.1
restrict ::1
"""
"""The lines of ntpsec 1.2.3's shipped ntp.conf that GPS time reads or edits,
copied from the package with the unrelated NTS and statistics comments left out."""


@pytest.fixture
def debian_ntp_conf() -> str:
    return DEBIAN_NTP_CONF


@pytest.fixture(autouse=True)
def _no_host_time_files(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Every GPS-time path points somewhere that does not exist, for every test.

    The field laptop runs this suite and has GPS time applied. A test that read
    its real /etc/ntpsec/ntp.conf would pass or fail by what that machine holds
    (CLAUDE.md: test the matrix, not your machine), and one that wrote there
    would be worse. Tests that want files request `time_files`. A test that
    writes here without it fails, naming the fixture to use.
    """
    from hammunition.gpstime import files

    root = tmp_path_factory.getbasetemp() / "host-time-files-absent"
    for name, default in files.PATHS.items():
        monkeypatch.setattr(files, name, str(root) + default)
    yield root
    if root.exists():
        shutil.rmtree(root)
        pytest.fail(
            "a test wrote GPS time files without the time_files fixture; request it "
            "so they land in that test's own tmp_path"
        )


@pytest.fixture
def time_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    debian_ntp_conf: str,
    _no_host_time_files: Path,
) -> Path:
    """A machine with ntpsec installed (its shipped ntp.conf and its daemon) and one
    hardware clock, under tmp_path."""
    from hammunition.gpstime import files

    root = tmp_path / "root"
    for name, default in files.PATHS.items():
        monkeypatch.setattr(files, name, str(root) + default)
    conf = Path(files.NTP_CONF)
    conf.parent.mkdir(parents=True)
    conf.write_text(debian_ntp_conf)
    ntpd = Path(files.NTPD)
    ntpd.parent.mkdir(parents=True)
    ntpd.write_text("")
    (Path(files.RTC_CLASS) / "rtc0").mkdir(parents=True)
    return root


@pytest.fixture(autouse=True)
def _no_host_geoclue_files(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Every GeoClue path (D-069) points somewhere that does not exist, for every test.

    The field laptop runs this suite with GeoClue installed and, once
    `hardware apply` has run there, Hammunition's drop-in in place: a test that
    read the real /etc/geoclue would answer by what that machine holds, and
    the tether would pick up the real socket path. Tests that want the files
    request `geoclue_files`; one that writes here without it fails.
    """
    from hammunition import geoclue

    root = tmp_path_factory.getbasetemp() / "host-geoclue-files-absent"
    for name, default in geoclue.PATHS.items():
        monkeypatch.setattr(geoclue, name, str(root) + default)
    yield root
    if root.exists():
        shutil.rmtree(root)
        pytest.fail(
            "a test wrote GeoClue files without the geoclue_files fixture; request it "
            "so they land in that test's own tmp_path"
        )


@pytest.fixture
def geoclue_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_host_geoclue_files: Path
) -> Path:
    """A machine with GeoClue installed (its daemon present), under tmp_path,
    whose ``geoclue`` group is the test account's own group, so the directory
    checks can pass without root."""
    import grp
    import os

    from hammunition import geoclue

    root = tmp_path / "root"
    for name, default in geoclue.PATHS.items():
        monkeypatch.setattr(geoclue, name, str(root) + default)
    monkeypatch.setattr(geoclue, "GROUP", grp.getgrgid(os.getgid()).gr_name)
    daemon = Path(geoclue.DAEMON)
    daemon.parent.mkdir(parents=True)
    daemon.write_text("")
    return root


# ---------------------------------------------------------------------------
# The GPS resume step (issue #177): no test reads or writes the host's unit
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_host_resume_files(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """The resume step's paths point somewhere that does not exist, for every
    test, for the reason `_no_host_time_files` gives: the field laptop runs this
    suite, and a plan that read its real /usr/local/libexec or /etc/systemd
    would test that machine. Tests that want files request `resume_files`."""
    from hammunition.hardware import gps_resume

    root = tmp_path_factory.getbasetemp() / "host-resume-files-absent"
    for name, default in gps_resume.PATHS.items():
        monkeypatch.setattr(gps_resume, name, str(root) + default)
    yield root
    if root.exists():
        shutil.rmtree(root)
        pytest.fail(
            "a test wrote GPS resume files without the resume_files fixture; request it "
            "so they land in that test's own tmp_path"
        )


@pytest.fixture
def resume_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_host_resume_files: Path
) -> Path:
    """A machine with gpsd installed and no resume step yet, under tmp_path."""
    from hammunition.hardware import gps_resume

    root = tmp_path / "resume-root"
    for name, default in gps_resume.PATHS.items():
        monkeypatch.setattr(gps_resume, name, str(root) + default)
    gpsd = Path(gps_resume.GPSD)
    gpsd.parent.mkdir(parents=True)
    gpsd.write_text("")
    return root
