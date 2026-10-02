# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`hardware apply` and `unapply` writing and removing the helper's two lists, and
the hand-over of the helper itself.  D-056 amended 2026-10-02.

The commands run for real against temporary paths (`install`, `rm`); nothing
touches /etc or a real helper.
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import pwd
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest

from hammunition.backends.base import Command, CommandResult
from hammunition.distro import Target
from hammunition.hardware import devctl_export as de
from hammunition.hardware import polkit
from test_cli import TARGET, _hardware_plan, _polkit_artifacts

cli = importlib.import_module("hammunition.cli.main")
ME = pwd.getpwuid(os.getuid()).pw_name


class _Runner:
    def __init__(self) -> None:
        self.ran: list[Command] = []

    def run(self, command: Command) -> CommandResult:
        self.ran.append(command)
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


def _machine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    polkit_artifacts: Any = None,
    with_export: bool = True,
) -> _Runner:
    step = de.plan_devctl_export({}, {}, time_unit="ntpsec.service") if with_export else None
    base = _hardware_plan(
        tmp_path, polkit=polkit_artifacts or _polkit_artifacts(tmp_path, helper_current=True)
    )
    plan = dataclasses.replace(base, devctl_export=step)
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr("hammunition.hardware.plan_hardware", lambda *a, **k: plan)
    monkeypatch.setattr(cli, "_load_hardware_catalog", lambda args: ({}, {}))
    monkeypatch.setattr(cli, "operator", lambda args: ME)
    monkeypatch.setattr(cli, "user_groups", lambda user: frozenset())
    _Log.entries = []
    monkeypatch.setattr(cli, "TransactionLog", _Log)
    monkeypatch.setattr("hammunition.hardware.power.KEPT_RULES", str(tmp_path / "kept.rules"))
    monkeypatch.setattr("hammunition.hardware.linger.LINGER_RECORD", tmp_path / "no-linger")
    runner = _Runner()
    monkeypatch.setattr(cli, "SubprocessRunner", lambda *a, **k: runner)
    return runner


def _apply(*extra: str) -> int:
    return int(cli.main(["hardware", "apply", "--yes", *extra]))


def test_apply_writes_both_lists_logs_each_and_reads_them_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devctl_export_files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _machine(tmp_path, monkeypatch)
    assert _apply() == cli.EXIT_OK
    assert Path(de.DEVICES_PATH).read_text().startswith(de.HEADER)
    assert "gpsd.socket" in Path(de.SERVICES_PATH).read_text()
    assert [c.argv[0] for c in runner.ran] == ["install", "install"]
    assert [e["event"] for e in _Log.entries] == ["devctl_export", "devctl_export"]
    assert all(e["version"] == 1 and e["argv"] for e in _Log.entries)
    out = capsys.readouterr().out
    assert de.DEVICES_PATH in out and de.SERVICES_PATH in out
    assert "Done and verified." in out


def test_a_second_apply_has_nothing_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, devctl_export_files: Path
) -> None:
    _machine(tmp_path, monkeypatch)
    assert _apply() == cli.EXIT_OK
    runner = _machine(tmp_path, monkeypatch)  # re-plans from what is now on disk
    assert _apply() == cli.EXIT_OK
    assert runner.ran == []


def test_the_dry_run_prints_both_files_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devctl_export_files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _machine(tmp_path, monkeypatch)
    assert cli.main(["hardware", "apply", "--dry-run"]) == cli.EXIT_OK
    assert runner.ran == []
    assert not Path(de.DEVICES_PATH).exists()
    out = capsys.readouterr().out
    assert f"{de.DEVICES_PATH} (root-owned 0644)" in out
    assert "- name: gpsd" in out and "unit: gpsd.socket" in out
    assert f"install -D -m 0644 '<staging>/devctl-services.yaml' {de.SERVICES_PATH}" in out


def test_a_failed_readback_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devctl_export_files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _machine(tmp_path, monkeypatch)
    real = runner.run

    def corrupting(command: Command) -> CommandResult:
        result = real(command)
        if command.argv[-1] == de.SERVICES_PATH:
            Path(de.SERVICES_PATH).write_text(de.HEADER + "\nservices: []\n")
        return result

    monkeypatch.setattr(runner, "run", corrupting)
    assert _apply() == cli.EXIT_FAILED
    assert f"{de.SERVICES_PATH} on disk does not match" in capsys.readouterr().err


def test_a_handed_over_helper_is_disclosed_and_not_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devctl_export_files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    handed = dataclasses.replace(
        _polkit_artifacts(tmp_path, helper_current=True),
        handed_over="hammunition-devctl contract 1",
    )
    runner = _machine(tmp_path, monkeypatch, polkit_artifacts=handed, with_export=False)
    assert cli.main(["hardware", "apply", "--dry-run"]) == cli.EXIT_OK
    out = " ".join(capsys.readouterr().out.split())
    assert "hammunition-tray" in out and "hammunition-devctl contract 1" in out
    assert "Will install the privileged helper" not in out
    assert runner.ran == []


def test_a_handed_over_noop_apply_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    handed = dataclasses.replace(
        _polkit_artifacts(tmp_path, helper_current=True),
        handed_over="hammunition-devctl contract 1",
    )
    _machine(tmp_path, monkeypatch, polkit_artifacts=handed, with_export=False)
    assert cli.main(["hardware", "apply", "--yes"]) == cli.EXIT_OK
    assert "hammunition-tray" in " ".join(capsys.readouterr().out.split())


def test_unapply_takes_back_both_lists_and_only_those(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devctl_export_files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _machine(tmp_path, monkeypatch)
    assert _apply() == cli.EXIT_OK
    runner.ran.clear()
    assert cli.main(["hardware", "unapply", "--yes"]) == cli.EXIT_OK
    assert not Path(de.DEVICES_PATH).exists() and not Path(de.SERVICES_PATH).exists()
    assert [" ".join(c.argv) for c in runner.ran] == [
        f"rm -f {de.DEVICES_PATH}",
        f"rm -f {de.SERVICES_PATH}",
    ]
    assert Path(de.DEVICES_PATH).parent.exists()
    assert "Done and verified." in capsys.readouterr().out


def test_unapply_dry_run_names_the_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devctl_export_files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _machine(tmp_path, monkeypatch)
    assert _apply() == cli.EXIT_OK
    runner.ran.clear()
    capsys.readouterr()
    assert cli.main(["hardware", "unapply", "--dry-run"]) == cli.EXIT_OK
    assert runner.ran == []
    out = capsys.readouterr().out
    assert de.DEVICES_PATH in out and de.SERVICES_PATH in out
    assert Path(de.DEVICES_PATH).exists()


def test_unapply_leaves_a_list_hammunition_did_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devctl_export_files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _machine(tmp_path, monkeypatch)
    Path(de.SERVICES_PATH).parent.mkdir(parents=True)
    Path(de.SERVICES_PATH).write_text("services: []\n")
    assert cli.main(["hardware", "unapply", "--yes"]) == cli.EXIT_OK
    assert runner.ran == []
    assert Path(de.SERVICES_PATH).read_text() == "services: []\n"
    assert "Nothing to remove" in capsys.readouterr().out


def test_unapply_never_removes_a_helper_that_is_now_the_trays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The log says the engine once wrote the helper; the tray has replaced it since.
    The run says what it left and does not claim the log records nothing (review I4)."""
    helper = tmp_path / "hammunition-devctl"
    helper.write_text("the tray's wrapper\n")
    monkeypatch.setattr(cli, "HELPER_PATH", str(helper))
    monkeypatch.setattr(polkit, "HELPER_PATH", str(helper))
    monkeypatch.setattr(
        polkit, "installed_helper_version", lambda *a, **k: "hammunition-devctl contract 1"
    )
    _machine(tmp_path, monkeypatch, with_export=False)
    _Log.entries = [
        {
            "event": "hardware_artifacts",
            "version": 1,
            "files": [{"path": str(helper), "mode": "0755"}],
        }
    ]
    assert cli.main(["hardware", "unapply", "--yes"]) == cli.EXIT_OK
    assert helper.read_text() == "the tray's wrapper\n"
    out = " ".join(capsys.readouterr().out.split())
    assert "hammunition-tray" in out
    assert f"The log records {helper} as written by an earlier apply; it is left in place" in out
    assert "records no hardware artefacts" not in out
