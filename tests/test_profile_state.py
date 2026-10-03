# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``list --json`` profile entries carry install state (console spec E1)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.base import Command, CommandResult, RecordingRunner, SubprocessRunner
from hammunition.distro import Target
from hammunition.interface.catalog import human_size, installed_apt_bytes
from hammunition.state import TransactionLog, log_path
from json_support import FIXTURE_CATALOG, parse_one

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)


def _log(entries: list[dict[str, Any]]) -> None:
    log = TransactionLog(log_path())
    for entry in entries:
        log.append(entry)


INSTALLED_APT: list[dict[str, Any]] = [
    {"event": "transaction_begin", "version": 2, "packages": ["fixture-apt"], "apt_packages": []},
    {"event": "transaction_end", "version": 1, "completed": 1},
]
INSTALLED_BOTH: list[dict[str, Any]] = [
    {
        "event": "transaction_begin",
        "version": 2,
        "packages": ["fixture-apt", "fixture-source"],
        "apt_packages": [],
    },
    {"event": "transaction_end", "version": 1, "completed": 2},
]


def _profiles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    dpkg: CommandResult | None,
    *flags: str,
) -> tuple[list[Command], dict[str, dict[str, Any]], str]:
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")
    runner = RecordingRunner()
    monkeypatch.setattr(SubprocessRunner, "run", lambda self, command: runner.run(command))
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "list", "profiles", *flags])
    assert rc == 0
    out = capsys.readouterr().out
    docs = {}
    if "--json" in flags:
        docs = {p["name"]: p for p in parse_one(out)["profiles"]}
    return runner.commands, docs, out


def test_no_log_means_zero_installed_and_no_dpkg_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    commands, docs, _ = _profiles(monkeypatch, tmp_path, capsys, None, "--json")
    assert commands == []
    p = docs["fixture-station"]
    assert (p["members"], p["installed"], p["installed_size_bytes"]) == (2, 0, None)


def test_apt_member_size_is_summed_in_bytes_from_one_dpkg_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("USER", "root")
    monkeypatch.delenv("SUDO_USER", raising=False)
    _log(INSTALLED_BOTH)
    runner = RecordingRunner()

    def run(self: object, command: Command) -> CommandResult:
        runner.commands.append(command)
        return CommandResult(argv=command.argv, returncode=0, stdout="fixture-apt\t12\n", stderr="")

    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr(SubprocessRunner, "run", run)
    assert cli.main(["--catalog", str(FIXTURE_CATALOG), "list", "profiles", "--json"]) == 0
    docs = {p["name"]: p for p in parse_one(capsys.readouterr().out)["profiles"]}
    p = docs["fixture-station"]
    assert (p["members"], p["installed"], p["installed_size_bytes"]) == (2, 2, 12 * 1024)
    # one call, every name at once; the source unit is not asked about
    assert len(runner.commands) == 1
    assert runner.commands[0].argv == (
        "dpkg-query",
        "-W",
        "-f=${Package}\t${Installed-Size}\n",
        "fixture-apt",
    )
    assert docs["fixture-gated"]["installed"] == 1
    assert docs["fixture-gated"]["installed_size_bytes"] == 12 * 1024


def test_only_non_apt_members_installed_gives_null_size_and_no_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("USER", "root")
    monkeypatch.delenv("SUDO_USER", raising=False)
    _log(
        [
            {"event": "transaction_begin", "version": 2, "packages": ["fixture-source"]},
            {"event": "transaction_end", "version": 1, "completed": 1},
        ]
    )
    commands, docs, _ = _profiles(monkeypatch, tmp_path, capsys, None, "--json")
    assert commands == []
    p = docs["fixture-station"]
    assert (p["installed"], p["installed_size_bytes"]) == (1, None)


def test_dpkg_absent_gives_null_size(monkeypatch: pytest.MonkeyPatch) -> None:
    class Missing:
        def run(self, command: Command) -> CommandResult:
            from hammunition.backends.base import BackendError

            raise BackendError("dpkg-query: not found")

    assert installed_apt_bytes(["fixture-apt"], Missing()) is None


def test_failed_dpkg_gives_null_size() -> None:
    class Failing:
        def run(self, command: Command) -> CommandResult:
            return CommandResult(argv=command.argv, returncode=2, stdout="", stderr="x")

    assert installed_apt_bytes(["a"], Failing()) is None


def test_removed_unit_is_not_counted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("USER", "root")
    monkeypatch.delenv("SUDO_USER", raising=False)
    _log(
        [
            *INSTALLED_BOTH,
            {"event": "uninstall_begin", "version": 1, "packages": ["fixture-source"]},
            {"event": "uninstall_end", "version": 1, "completed": 1},
        ]
    )
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr(
        SubprocessRunner,
        "run",
        lambda self, c: CommandResult(
            argv=c.argv, returncode=0, stdout="fixture-apt\t1\n", stderr=""
        ),
    )
    assert cli.main(["--catalog", str(FIXTURE_CATALOG), "list", "profiles", "--json"]) == 0
    docs = {p["name"]: p for p in parse_one(capsys.readouterr().out)["profiles"]}
    assert docs["fixture-station"]["installed"] == 1


def test_text_shows_installed_n_of_m_and_a_human_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("USER", "root")
    monkeypatch.delenv("SUDO_USER", raising=False)
    _log(INSTALLED_APT)
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr(
        SubprocessRunner,
        "run",
        lambda self, c: CommandResult(
            argv=c.argv, returncode=0, stdout="fixture-apt\t2048\n", stderr=""
        ),
    )
    assert cli.main(["--catalog", str(FIXTURE_CATALOG), "list", "profiles"]) == 0
    out = capsys.readouterr().out
    assert "installed 1 of 2" in out and "2.0 MiB" in out


def test_human_size() -> None:
    assert human_size(512) == "512 B"
    assert human_size(2 * 1024 * 1024) == "2.0 MiB"
