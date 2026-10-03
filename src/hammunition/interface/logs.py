# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``logs`` as data.  D-077, D-059.

The run logs a console or the tray can list and open: one entry per file under
``<state dir>/logs``, newest first. Nothing in a log is read to build the list
except its last line.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.backends.data import human_size
from hammunition.interface.envelope import Strict, described

__all__ = ["LogsDocument", "RunEntry", "render_logs"]


@dataclass(frozen=True)
class RunEntry(Strict):
    """One run's log file."""

    path: str = described("absolute path of the log; `tail -f` it while the run is going")
    started: str = described("ISO 8601 UTC time the run began, from the file's name")
    command: str = described(
        "the command as the file's name spells it: `install`, `hardware-apply`, `maps-qmapshack`"
    )
    pid: int = described("the process id of the run")
    size: int = described("bytes")
    result: str = described(
        "how the run ended: `ok`, `failed`, `refused` or `not confirmed` (the exit code's "
        "words), `running` (a live process holds the file), or `incomplete` (no result line "
        "and nothing holds the file: the run was killed)"
    )
    exit_code: int | None = described("the run's exit status; null for `running` and `incomplete`")


@dataclass(frozen=True)
class LogsDocument(Strict):
    """The run logs on this machine for this operator, newest first, and the
    limits rotation holds them to (D-077)."""

    KIND: ClassVar[str] = "logs"

    directory: str = described("the log directory, `<state dir>/logs`")
    total_bytes: int = described("bytes across every run log")
    max_files: int = described("rotation keeps at most this many run logs")
    max_bytes: int = described("rotation keeps at most this many bytes of run logs")
    runs: tuple[RunEntry, ...] = described("one entry per run log, newest first")


def render_logs(doc: LogsDocument) -> list[str]:
    """``logs`` as the terminal shows it."""
    if not doc.runs:
        return [f"No run logs yet in {doc.directory}."]
    lines = [
        f"{len(doc.runs)} run log(s) in {doc.directory} "
        f"({human_size(doc.total_bytes)}; keeps at most {doc.max_files} files "
        f"and {human_size(doc.max_bytes)}):"
    ]
    for run in doc.runs:
        when = run.started.replace("T", " ").replace("+00:00", " UTC")
        lines.append(f"  {when}  {run.command:<22} {human_size(run.size):>9}  {run.result}")
    lines.append("`hammunition logs --last` prints the newest; `--path` prints where it is.")
    return lines
