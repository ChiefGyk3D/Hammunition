# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the plan says while it waits on the network (#197).

A plan asks publishers questions before it prints anything -- one ``HEAD`` per
terrain tile, per US Topo sheet, per Kiwix book -- because each answer is part
of what the plan discloses (D-061, D-066, D-068, D-069). With hundreds of
tiles that is minutes of silence, and an operator at the keyboard cannot tell a
working dry run from a hung one.

Two small pieces, both here:

* :class:`Progress` writes to **stderr only**, so ``--json`` keeps its single
  document on stdout (D-059) and a pipe of the plan is unchanged. It speaks
  when stderr is a terminal, or when ``HAMMUNITION_PROGRESS=1`` forces it, so
  logs and CI stay clean by default.
* :func:`run_checks` runs a list of independent checks :data:`CHECK_WORKERS`
  at a time and hands the outcomes back **in input order**, each one a value
  or the exception that check raised, so a caller's per-item error reporting
  is exactly what it was when the loop was sequential.

Thread-safety: every probe passed to :func:`run_checks` by the plan
(``S3Probe``, ``UrllibProbe``, ``CdnProbe``, ``KiwixProbe``, ``GatewayProbe``)
holds only an immutable ``OpenerDirector`` and a timeout, builds a request and
a connection per call, and keeps no cache, so one instance is shared by the
workers without a lock. ``hammunition.fetch.Fetcher`` is not involved: plan-time
checks are probes, not downloads. A new probe given to :func:`run_checks` must
keep to that.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import IO, Generic, TypeVar

__all__ = ["CHECK_WORKERS", "Outcome", "Progress", "run_checks"]

#: How many plan-time checks are in flight at once. Four: a publisher's bucket
#: answers four requests from one address without complaint, and the wait for
#: hundreds of tiles drops by about that factor; it is not a tuning knob.
CHECK_WORKERS = 4

#: The most often the same-line counter is rewritten on a terminal.
INTERVAL = 0.5
#: A forced, non-terminal stream (a log) gets a counter line this often.
LOG_INTERVAL = 5.0

T = TypeVar("T")
R = TypeVar("R")


class Progress:
    """One line saying what is being waited on, a counter, and an elapsed time.

    ``start(label, total)`` prints ``checking <total> <label> (needs the
    network)…``; ``tick()`` counts one item done (safe from several threads);
    ``done()`` prints ``checked <total> <label> in <seconds> s``. Nothing is
    printed for ``total == 0``.
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._stream = stream
        self._clock = clock
        self._lock = threading.Lock()
        self._label = ""
        self._total = 0
        self._count = 0
        self._began = 0.0
        self._last = 0.0
        self._counter_written = False
        self._tty = False
        self._on = False

    def _enabled(self, stream: IO[str]) -> bool:
        if os.environ.get("HAMMUNITION_PROGRESS") == "1":
            return True
        try:
            return stream.isatty()
        except (AttributeError, ValueError):
            return False

    def start(self, label: str, total: int) -> None:
        stream = self._stream if self._stream is not None else sys.stderr
        with self._lock:
            self._label, self._total, self._count = label, total, 0
            self._counter_written = False
            self._on = total > 0 and self._enabled(stream)
            if not self._on:
                return
            try:
                self._tty = stream.isatty()
            except (AttributeError, ValueError):
                self._tty = False
            self._began = self._last = self._clock()
            self._write(stream, f"checking {total} {label} (needs the network)…\n")

    def tick(self) -> None:
        stream = self._stream if self._stream is not None else sys.stderr
        with self._lock:
            self._count += 1
            if not self._on:
                return
            now = self._clock()
            if now - self._last < (INTERVAL if self._tty else LOG_INTERVAL):
                return
            self._last = now
            line = f"  {self._count}/{self._total}"
            self._write(stream, ("\r" + line) if self._tty else line + "\n")
            self._counter_written = self._tty

    def done(self) -> None:
        stream = self._stream if self._stream is not None else sys.stderr
        with self._lock:
            if not self._on:
                return
            elapsed = self._clock() - self._began
            clear = "\r\033[2K" if self._counter_written else ""
            self._write(stream, f"{clear}checked {self._total} {self._label} in {elapsed:.1f} s\n")
            self._on = False

    @staticmethod
    def _write(stream: IO[str], text: str) -> None:
        try:
            try:
                stream.write(text)
            except UnicodeEncodeError:
                stream.write(text.replace("…", "..."))  # an ASCII stderr
            stream.flush()
        except (OSError, ValueError):
            pass  # a closed stderr must not fail a plan


@dataclass(frozen=True)
class Outcome(Generic[R]):
    """One check's result: its value, or the exception it raised."""

    value: R | None = None
    error: BaseException | None = None

    def get(self) -> R:
        """The value, or raise what the check raised, where the caller's own
        ``except`` for that item is."""
        if self.error is not None:
            raise self.error
        return self.value  # type: ignore[return-value]


def run_checks(
    items: Sequence[T],
    check: Callable[[T], R],
    *,
    label: str,
    workers: int = CHECK_WORKERS,
    progress: Progress | None = None,
) -> list[Outcome[R]]:
    """``check(item)`` for every item, *workers* at a time, outcomes in input
    order. An exception from one check is that item's outcome; the others
    still run. *label* completes the sentence ``checking N <label> (needs the
    network)…`` and names the publisher and the kind of thing asked."""
    if not items:
        return []
    bar = progress if progress is not None else Progress()
    bar.start(label, len(items))

    def one(item: T) -> Outcome[R]:
        try:
            outcome: Outcome[R] = Outcome(value=check(item))
        except Exception as exc:  # reported per item, re-raised by Outcome.get
            outcome = Outcome(error=exc)
        bar.tick()
        return outcome

    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            return list(pool.map(one, items))
    finally:
        bar.done()
