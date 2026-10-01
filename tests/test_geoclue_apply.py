# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`hardware apply` and `unapply` writing and removing GeoClue's two files.  D-069.

The commands run for real against temporary paths: coreutils' `install`, `rm`
and `rmdir`, and a fake `systemd-tmpfiles` first on PATH that makes the
directory its `d` line names. `systemctl` is recorded, never run. Nothing
touches /etc, /run or a GeoClue.
"""

from __future__ import annotations

import importlib
import os
import pwd
import stat
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest

from fake_tools import calls, install_fakes
from hammunition import geoclue
from hammunition.backends.base import Command, CommandResult
from hammunition.distro import Target
from test_cli import TARGET, _hardware_plan, _polkit_artifacts

cli = importlib.import_module("hammunition.cli.main")
ME = pwd.getpwuid(os.getuid()).pw_name

TMPFILES_FAKE = (
    'awk \'$1 == "d" { print $2, $3 }\' "$2" | while read -r dir mode; do\n'
    '  mkdir -p "$dir" && chmod "$mode" "$dir"\n'
    "done"
)


class _Runner:
    """Runs each command as given (no sudo), except systemctl, which is recorded."""

    def __init__(self) -> None:
        self.ran: list[Command] = []

    def run(self, command: Command) -> CommandResult:
        self.ran.append(command)
        if command.argv[0] == "systemctl":
            return CommandResult(argv=command.argv, returncode=0, stdout="", stderr="")
        done = subprocess.run(command.argv, capture_output=True, text=True, check=False)
        return CommandResult(
            argv=command.argv, returncode=done.returncode, stdout=done.stdout, stderr=done.stderr
        )


class _Log:
    entries: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, **kwargs: object) -> None: ...

    def append(self, entry: dict[str, Any]) -> None:
        _Log.entries.append(entry)

    def read(self) -> Any:
        return iter(_Log.entries)


@pytest.fixture
def machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, geoclue_files: Path
) -> tuple[_Runner, Path]:
    """Every other half of `hardware apply` already in place, GeoClue installed."""
    plan = _hardware_plan(tmp_path, polkit=_polkit_artifacts(tmp_path))
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr("hammunition.hardware.plan_hardware", lambda *a, **k: plan)
    monkeypatch.setattr(cli, "_load_hardware_catalog", lambda args: ({}, {}))
    monkeypatch.setattr(cli, "operator", lambda args: ME)
    monkeypatch.setattr(cli, "user_groups", lambda user: frozenset())
    _Log.entries = []
    monkeypatch.setattr(cli, "TransactionLog", _Log)
    # unapply looks at the kept-off rules file; never the host's.
    monkeypatch.setattr("hammunition.hardware.power.KEPT_RULES", str(tmp_path / "kept.rules"))
    runner = _Runner()
    monkeypatch.setattr(cli, "SubprocessRunner", lambda *a, **k: runner)
    log = install_fakes(monkeypatch, tmp_path / "bin", {"systemd-tmpfiles": TMPFILES_FAKE})
    return runner, log


def _apply(*extra: str) -> int:
    return int(cli.main(["hardware", "apply", "--yes", *extra]))


def test_apply_writes_both_files_makes_the_directory_and_restarts_geoclue(
    machine: tuple[_Runner, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runner, log = machine
    assert _apply() == cli.EXIT_OK
    assert Path(geoclue.DROPIN).read_text() == geoclue.dropin_content()
    assert Path(geoclue.TMPFILES).read_text() == geoclue.tmpfiles_content(ME)
    mode = stat.S_IMODE(os.lstat(geoclue.SOCKET_DIR).st_mode)
    assert mode == 0o2750
    assert [c.argv[0] for c in runner.ran] == [
        "install",
        "install",
        "systemd-tmpfiles",
        "systemctl",
    ]
    assert runner.ran[-1].argv == ("systemctl", "try-restart", "geoclue")
    assert [command for _, command in calls(log)] == [
        f"systemd-tmpfiles --create {geoclue.TMPFILES}"
    ]
    assert [e["event"] for e in _Log.entries] == ["geoclue_files"] * 4
    out = " ".join(capsys.readouterr().out.split())
    assert geoclue.DROPIN in out and "journalctl -u geoclue | grep -i nmea" in out
    assert "Done and verified." in out


def test_a_second_apply_has_nothing_to_do(machine: tuple[_Runner, Path]) -> None:
    runner, _ = machine
    assert _apply() == cli.EXIT_OK
    runner.ran.clear()
    assert _apply() == cli.EXIT_OK
    assert runner.ran == []


def test_the_dry_run_prints_every_command_and_runs_none(
    machine: tuple[_Runner, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runner, _ = machine
    assert cli.main(["hardware", "apply", "--dry-run"]) == cli.EXIT_OK
    assert runner.ran == []
    assert not os.path.lexists(geoclue.DROPIN)
    out = capsys.readouterr().out
    assert f"systemd-tmpfiles --create {geoclue.TMPFILES}" in out
    assert "systemctl try-restart geoclue" in out
    for sentence in geoclue.DISCLOSURES:
        assert " ".join(sentence.split()) in " ".join(out.split())


def test_no_geoclue_leaves_it_alone(
    machine: tuple[_Runner, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runner, _ = machine
    assert _apply("--no-geoclue") == cli.EXIT_OK
    assert runner.ran == []
    assert not os.path.lexists(geoclue.DROPIN)


def test_a_dropin_someone_else_wrote_refuses_before_anything_runs(
    machine: tuple[_Runner, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runner, _ = machine
    Path(geoclue.DROPIN).parent.mkdir(parents=True)
    Path(geoclue.DROPIN).write_text("[network-nmea]\nenable=false\n")
    assert _apply() == cli.EXIT_UNPLANNABLE
    assert runner.ran == []
    assert "--no-geoclue" in capsys.readouterr().err


def test_a_failed_readback_is_reported(
    machine: tuple[_Runner, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """D-031: the fake makes the directory 0755, as a tmpfiles that ignored the
    mode would, and the run fails naming it."""
    install_fakes(
        monkeypatch,
        Path(geoclue.DAEMON).parent.parent / "bin2",
        {"systemd-tmpfiles": TMPFILES_FAKE.replace('chmod "$mode"', "chmod 0755")},
    )
    assert _apply() == cli.EXIT_FAILED
    assert f"{geoclue.SOCKET_DIR}: mode 0755" in capsys.readouterr().err


def test_unapply_takes_back_both_files_and_the_directory(
    machine: tuple[_Runner, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runner, _ = machine
    assert _apply() == cli.EXIT_OK
    runner.ran.clear()
    assert cli.main(["hardware", "unapply", "--yes"]) == cli.EXIT_OK
    assert not os.path.lexists(geoclue.DROPIN)
    assert not os.path.lexists(geoclue.TMPFILES)
    assert not os.path.lexists(geoclue.SOCKET_DIR)
    assert [" ".join(c.argv) for c in runner.ran] == [
        f"rm -f {geoclue.DROPIN}",
        f"rm -f {geoclue.TMPFILES}",
        f"rmdir {geoclue.SOCKET_DIR}",
        "systemctl try-restart geoclue",
    ]
    assert "Done and verified." in capsys.readouterr().out


def test_unapply_dry_run_names_the_geoclue_steps(
    machine: tuple[_Runner, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runner, _ = machine
    assert _apply() == cli.EXIT_OK
    runner.ran.clear()
    capsys.readouterr()
    assert cli.main(["hardware", "unapply", "--dry-run"]) == cli.EXIT_OK
    assert runner.ran == []
    out = capsys.readouterr().out
    assert f"rmdir {geoclue.SOCKET_DIR}" in out and "GeoClue" in out
    assert os.path.lexists(geoclue.DROPIN)


def test_unapply_with_nothing_of_geoclues_is_nothing_to_remove(
    machine: tuple[_Runner, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["hardware", "unapply", "--yes"]) == cli.EXIT_OK
    assert "Nothing to remove" in capsys.readouterr().out
