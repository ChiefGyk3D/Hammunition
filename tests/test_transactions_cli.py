# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The chronological transaction history command. D-077."""

from __future__ import annotations

import fcntl
import importlib
import json
import os
from pathlib import Path
from typing import Any

from hammunition import runlog
from hammunition.state import TransactionLog, log_path
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")


def _write(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def _begin(
    event: str,
    timestamp: str,
    packages: list[str],
    *,
    deferred: list[dict[str, str]] | None = None,
    run_log: str | None = None,
) -> dict[str, Any]:
    return {
        "event": event,
        "version": 2,
        "timestamp": timestamp,
        "packages": packages,
        "deferred": deferred or [],
        **({"run_log": run_log} if run_log is not None else {}),
    }


def test_transaction_begin_records_the_active_run_log(monkeypatch: Any, tmp_path: Path) -> None:
    run_log = runlog._open(tmp_path / "logs" / "20261003T120000Z-install-123.log", None)
    monkeypatch.setattr(runlog, "_active", run_log)
    transaction_log = TransactionLog(tmp_path / "state" / "transactions.jsonl")
    try:
        transaction_log.append({"event": "transaction_begin", "version": 2})
        assert next(transaction_log.read())["run_log"] == str(run_log.path)
    finally:
        run_log.close(None, 0)


def test_transactions_reads_archives_then_live_and_reports_in_progress(
    monkeypatch: Any, tmp_path: Path, capsys: Any
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")

    path = log_path()
    path.parent.mkdir(parents=True)
    archive_one = path.with_name("transactions-000001-20260901T120000Z.jsonl")
    archive_two = path.with_name("transactions-000002-20260902T120000Z.jsonl")
    _write(
        archive_one,
        [
            _begin("transaction_begin", "2026-09-01T12:00:00+00:00", ["fixture-apt"]),
            {"event": "transaction_end", "timestamp": "2026-09-01T12:05:00+00:00"},
        ],
    )
    _write(
        archive_two,
        [
            _begin("transaction_begin", "2026-09-02T12:00:00+00:00", ["fixture-failed"]),
            {"event": "transaction_failed", "timestamp": "2026-09-02T12:05:00+00:00"},
            _begin("uninstall_begin", "2026-09-02T12:06:00+00:00", ["fixture-aborted"]),
        ],
    )

    run_log_dir = path.parent / "logs"
    run_log_dir.mkdir()
    run_log = run_log_dir / "20260903T120000Z-install-123.log"
    descriptor = os.open(run_log, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert runlog.list_runs(run_log_dir)[0].result == "running"
        monkeypatch.setattr(runlog, "logs_dir", lambda _owner=None: run_log_dir)
        _write(
            path,
            [
                _begin(
                    "transaction_begin",
                    "2026-09-03T12:00:00+00:00",
                    ["fixture-node"],
                    deferred=[{"kind": "package", "subject": "fixture-deferred"}],
                    run_log=str(run_log),
                )
            ],
        )

        assert cli.main(["transactions", "--json"]) == 0
        document = parse_one(capsys.readouterr().out)
        validate(document)
        assert document["kind"] == "transactions"
        transactions = document["transactions"]
        assert [row["id"] for row in transactions] == [1, 2, 3, 4]
        assert [row["command"] for row in transactions] == [
            "install",
            "install",
            "uninstall",
            "install",
        ]
        assert [row["units"] for row in transactions] == [
            ["fixture-apt"],
            ["fixture-failed"],
            ["fixture-aborted"],
            ["fixture-node"],
        ]
        assert [row["result"] for row in transactions] == [
            "ok",
            "failed",
            "aborted",
            "in-progress",
        ]
        assert transactions[0]["ended"] == "2026-09-01T12:05:00+00:00"
        assert transactions[2]["ended"] is None
        assert transactions[3]["deferred"] == ["fixture-deferred"]
        assert transactions[0]["log"] is None
        assert transactions[3]["log"] == str(run_log)

        assert cli.main(["transactions"]) == 0
        text = capsys.readouterr().out
        assert (
            text.index("fixture-apt")
            < text.index("fixture-failed")
            < text.index("fixture-aborted")
            < text.index("fixture-node")
        )
        assert "in-progress" in text and "fixture-deferred" in text
        assert str(run_log) in text

        assert cli.main(["transactions", "--last", "2", "--json"]) == 0
        latest = parse_one(capsys.readouterr().out)["transactions"]
        assert [row["id"] for row in latest] == [3, 4]
    finally:
        os.close(descriptor)
