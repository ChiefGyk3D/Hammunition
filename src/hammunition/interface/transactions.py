# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The transaction history document and its terminal rendering. D-077, D-059."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described

__all__ = ["TransactionEntry", "TransactionsDocument", "build_transactions", "render_transactions"]

_BEGIN_EVENTS: Mapping[str, tuple[str, str, str]] = {
    "transaction_begin": ("install", "transaction_end", "transaction_failed"),
    "uninstall_begin": ("uninstall", "uninstall_end", "uninstall_failed"),
}


@dataclass(frozen=True)
class TransactionEntry(Strict):
    """One install or uninstall recorded in the transaction log."""

    id: int = described("its one-based position in chronological transaction history")
    began: str = described("the begin event's ISO 8601 timestamp")
    ended: str | None = described("the matching end event's timestamp, or null without one")
    command: str = described("the command that began the transaction, such as `install`")
    units: tuple[str, ...] = described("unit names recorded by the begin event")
    deferred: tuple[str, ...] = described("unit names deferred by the begin event (D-039)")
    result: str = described("`ok`, `failed`, `aborted` or `in-progress`")
    log: str | None = described("the D-077 run-log path recorded at transaction start, or null")


@dataclass(frozen=True)
class TransactionsDocument(Strict):
    """The transaction history, oldest first, across archives and the live log."""

    KIND: ClassVar[str] = "transactions"

    transactions: tuple[TransactionEntry, ...] = described(
        "transaction rows in chronological order, oldest first"
    )


def _deferred_names(begin: Mapping[str, object]) -> tuple[str, ...]:
    raw = begin.get("deferred", [])
    if not isinstance(raw, (list, tuple)):
        return ()
    names: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            name = item.get("subject")
            if name is not None:
                names.append(str(name))
        elif isinstance(item, str):
            names.append(item)
    return tuple(names)


def build_transactions(
    entries: Sequence[Mapping[str, object]], *, running_logs: Collection[str] = ()
) -> TransactionsDocument:
    """Fold the transaction log's ordered events into one row per transaction."""
    rows: list[TransactionEntry] = []
    begin: Mapping[str, object] | None = None
    endings: tuple[str, str, str] | None = None
    terminal: Mapping[str, object] | None = None

    def finish() -> None:
        if begin is None or endings is None:
            return
        command, end_event, failed_event = endings
        matched = terminal is not None and terminal.get("event") in (end_event, failed_event)
        success = matched and terminal is not None and terminal.get("event") == end_event
        run_log = begin.get("run_log")
        run_log_path = str(run_log) if isinstance(run_log, str) else None
        raw_units = begin.get("packages", ())
        units = (
            tuple(str(name) for name in raw_units if name is not None)
            if isinstance(raw_units, (list, tuple))
            else ()
        )
        result = (
            "ok"
            if success
            else "failed"
            if matched
            else "in-progress"
            if run_log_path is not None and run_log_path in running_logs
            else "aborted"
        )
        rows.append(
            TransactionEntry(
                id=len(rows) + 1,
                began=str(begin.get("timestamp", "")),
                ended=(
                    str(terminal["timestamp"])
                    if matched and terminal is not None and terminal.get("timestamp") is not None
                    else None
                ),
                command=command,
                units=units,
                deferred=_deferred_names(begin),
                result=result,
                log=run_log_path,
            )
        )

    for entry in entries:
        event = entry.get("event")
        if isinstance(event, str) and event in _BEGIN_EVENTS:
            finish()
            begin = entry
            endings = _BEGIN_EVENTS[event]
            terminal = None
        elif begin is not None and endings is not None and event in endings[1:]:
            terminal = entry
            finish()
            begin = None
            endings = None
            terminal = None
    finish()
    return TransactionsDocument(transactions=tuple(rows))


def render_transactions(doc: TransactionsDocument) -> list[str]:
    """Render the same transaction rows as a table, newest last."""
    if not doc.transactions:
        return ["No transactions recorded."]

    columns = ("ID", "BEGAN", "ENDED", "COMMAND", "UNITS", "DEFERRED", "RESULT", "LOG")
    values = [
        (
            str(row.id),
            row.began or "—",
            row.ended or "—",
            row.command,
            ", ".join(row.units) or "—",
            ", ".join(row.deferred) or "—",
            row.result,
            row.log or "—",
        )
        for row in doc.transactions
    ]
    widths = tuple(
        max(len(columns[index]), *(len(row[index]) for row in values))
        for index in range(len(columns))
    )

    def line(row: Sequence[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()

    return [
        line(columns),
        "  ".join("-" * width for width in widths),
        *(line(row) for row in values),
    ]
