# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Rotating ``transactions.jsonl`` into archives, with every reader unchanged.  D-077.

The property that matters is not that a file got smaller: it is that
``status``, ``update`` and ``uninstall`` -- which replay the whole log -- see
exactly the events they saw before, in the same order.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from hammunition.distro import Target
from hammunition.state import (
    TransactionLog,
    files_installed_by_hammunition,
    installed_by_hammunition,
)
from hammunition.state import log as statelog
from json_support import FIXTURE_CATALOG

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)


def _transaction(n: int, *, packages: list[str], end: bool = True) -> list[dict[str, Any]]:
    stamp = f"2026-09-{(n % 28) + 1:02d}T12:00:00+00:00"
    events: list[dict[str, Any]] = [
        {
            "event": "transaction_begin",
            "version": 2,
            "timestamp": stamp,
            "packages": packages,
            "apt_packages": packages,
            "deferred": [],
        },
        {"event": "command_begin", "version": 1, "argv": ["apt-get", "install", "--", *packages]},
        {
            "event": "command_end",
            "version": 1,
            "argv": ["apt-get", "install", "-y", "--", *packages],
            "returncode": 0,
        },
        {
            "event": "action_end",
            "version": 1,
            "kind": "install-binary",
            "detail": f"/usr/local/bin/tool{n}",
            "outcome": "installed",
        },
    ]
    if end:
        events.append({"event": "transaction_end", "version": 1, "completed": 2})
    return events


def _fill(log: TransactionLog, count: int) -> None:
    log.path.parent.mkdir(parents=True, exist_ok=True)
    for n in range(count):
        # Raw writes: appending a transaction_begin would itself rotate.
        with log.path.open("a", encoding="utf-8") as handle:
            for event in _transaction(n, packages=["fixture-apt"]):
                handle.write(json.dumps(event) + "\n")
        if n % 5 == 4:
            with log.path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "event": "command_end",
                            "version": 1,
                            "argv": ["apt-get", "remove", "-y", "--", "fixture-apt"],
                            "returncode": 0,
                        }
                    )
                    + "\n"
                )


@pytest.fixture
def log(tmp_path: Path) -> TransactionLog:
    return TransactionLog(tmp_path / "state" / "transactions.jsonl")


def test_rotation_moves_old_whole_transactions_and_keeps_the_newest(log: TransactionLog) -> None:
    _fill(log, 12)
    before = list(log.read())
    archive = log.rotate(threshold=0, keep=3)
    assert archive is not None and archive.exists()
    live = [json.loads(x) for x in log.path.read_text().splitlines()]
    assert sum(1 for e in live if e["event"] == "transaction_begin") == 3
    assert live[0]["event"] == "transaction_begin", "a transaction is never cut in half"
    assert list(log.read()) == before, "same events, same order"
    assert log.archives() == [archive]


def test_below_the_threshold_nothing_happens(log: TransactionLog) -> None:
    _fill(log, 12)
    assert log.rotate(threshold=10**9, keep=3) is None
    assert log.archives() == []


def test_fewer_transactions_than_keep_is_not_rotated(log: TransactionLog) -> None:
    _fill(log, 3)
    assert log.rotate(threshold=0, keep=5) is None


def test_two_rotations_read_back_in_order(log: TransactionLog) -> None:
    _fill(log, 10)
    first = log.rotate(threshold=0, keep=6)
    _fill(log, 10)
    expected = list(log.read())
    assert len(expected) == 2 * 10 * 5 + 2 * 2
    second = log.rotate(threshold=0, keep=4)
    assert first is not None and second is not None and first != second
    assert log.archives() == sorted([first, second])
    assert list(log.read()) == expected


def test_an_open_transaction_stays_in_the_live_file(log: TransactionLog) -> None:
    _fill(log, 6)
    with log.path.open("a", encoding="utf-8") as handle:
        for event in _transaction(99, packages=["running"], end=False):
            handle.write(json.dumps(event) + "\n")
    before = list(log.read())
    log.rotate(threshold=0, keep=2)
    live = [json.loads(x) for x in log.path.read_text().splitlines()]
    assert any(e.get("packages") == ["running"] for e in live)
    assert list(log.read()) == before


def test_the_replays_that_uninstall_stands_on_are_unchanged(log: TransactionLog) -> None:
    _fill(log, 14)
    apt_before = installed_by_hammunition(log)
    files_before = files_installed_by_hammunition(log)
    assert files_before, "the fixture must attribute something"
    log.rotate(threshold=0, keep=3)
    assert installed_by_hammunition(log) == apt_before
    assert files_installed_by_hammunition(log) == files_before


def _status(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    capsys: pytest.CaptureFixture[str],
    *flags: str,
) -> str:
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")
    assert cli.main(["--catalog", str(FIXTURE_CATALOG), "status", *flags]) == 0
    return capsys.readouterr().out.replace(str(state), "<state>")


def test_status_is_identical_before_and_after_a_rotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = TransactionLog(tmp_path / "hammunition" / "transactions.jsonl")
    _fill(log, 12)
    with log.path.open("a", encoding="utf-8") as handle:
        for event in _transaction(40, packages=["fixture-apt", "fixture-source"]):
            handle.write(json.dumps(event) + "\n")
    text_before = _status(monkeypatch, tmp_path, capsys)
    json_before = _status(monkeypatch, tmp_path, capsys, "--json")
    assert log.rotate(threshold=0, keep=2) is not None
    assert _status(monkeypatch, tmp_path, capsys) == text_before
    assert _status(monkeypatch, tmp_path, capsys, "--json") == json_before


def test_a_kill_after_the_archive_landed_does_not_double_the_events(log: TransactionLog) -> None:
    """Archive written, live file not yet shrunk: the intent file says so and
    readers skip the duplicated lines; the next rotation finishes the job."""
    _fill(log, 8)
    before = list(log.read())
    lines = log.path.read_text().splitlines(keepends=True)
    begins = [i for i, x in enumerate(lines) if '"transaction_begin"' in x]
    head = lines[: begins[-2]]
    archive = log.path.with_name("transactions-20260901T000000000000Z.jsonl")
    archive.write_text("".join(head))
    log.path.with_name(log.path.name + ".rotating").write_text(
        json.dumps({"archive": archive.name, "lines": len(head)})
    )
    assert list(log.read()) == before
    log.append({"event": "transaction_begin", "version": 2})  # finishes the rotation
    assert not log.path.with_name(log.path.name + ".rotating").exists()
    assert list(log.read())[:-1] == before


def test_a_kill_after_the_file_shrank_does_not_skip_live_events(log: TransactionLog) -> None:
    """Intent still present although the live file was already shrunk: its first
    lines are not the archive's, so nothing is skipped."""
    _fill(log, 8)
    before = list(log.read())
    archive = log.rotate(threshold=0, keep=2)
    assert archive is not None
    count = len(archive.read_text().splitlines())
    log.path.with_name(log.path.name + ".rotating").write_text(
        json.dumps({"archive": archive.name, "lines": count})
    )
    assert list(log.read()) == before


def test_a_kill_before_the_archive_landed_loses_nothing(log: TransactionLog) -> None:
    _fill(log, 8)
    before = list(log.read())
    log.path.with_name(log.path.name + ".rotating").write_text(
        json.dumps({"archive": "transactions-20260901T000000000000Z.jsonl", "lines": 5})
    )
    assert list(log.read()) == before


def test_a_transaction_begin_rotates_once_the_file_is_large(
    log: TransactionLog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(statelog, "ROTATE_BYTES", 1)
    monkeypatch.setattr(statelog, "KEEP_TRANSACTIONS", 2)
    _fill(log, 6)
    before = list(log.read())
    log.append({"event": "transaction_begin", "version": 2})
    assert len(log.archives()) == 1
    assert list(log.read()) == [*before, {"event": "transaction_begin", "version": 2}]


def test_an_ordinary_event_never_rotates(
    log: TransactionLog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(statelog, "ROTATE_BYTES", 1)
    _fill(log, 6)
    log.append({"event": "hardware_artifacts", "version": 1})
    assert log.archives() == []


def test_an_unreadable_archive_is_loud_not_skipped(log: TransactionLog) -> None:
    """Skipping history would report installed units as not installed."""
    _fill(log, 6)
    archive = log.rotate(threshold=0, keep=2)
    assert archive is not None
    archive.write_bytes(b"\xff\xfe not utf-8 \xff")
    with pytest.raises(UnicodeDecodeError):
        list(log.read())


def test_archives_are_private(log: TransactionLog) -> None:
    _fill(log, 6)
    archive = log.rotate(threshold=0, keep=2)
    assert archive is not None
    assert archive.stat().st_mode & 0o777 == 0o600
