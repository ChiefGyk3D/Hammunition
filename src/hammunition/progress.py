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

import contextlib
import os
import re
import shutil
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import IO, Generic, TypeVar

__all__ = [
    "CHECK_WORKERS",
    "LiveStatus",
    "Outcome",
    "Progress",
    "activate_live",
    "current_live",
    "elapsed_text",
    "run_checks",
    "say",
]

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

_SAY_LOCK = threading.Lock()


def say(line: str, stream: IO[str] | None = None) -> None:
    """One whole line on stderr, under the same rule as :class:`Progress`:
    spoken at a terminal or when ``HAMMUNITION_PROGRESS=1`` forces it, silent
    otherwise. Used for a retry (#200), which can happen from any worker, so
    it takes a lock and clears a same-line counter first on a terminal."""
    out = stream if stream is not None else sys.stderr
    if os.environ.get("HAMMUNITION_PROGRESS") != "1":
        try:
            if not out.isatty():
                return
        except (AttributeError, ValueError):
            return
    try:
        tty = out.isatty()
    except (AttributeError, ValueError):
        tty = False
    with _SAY_LOCK:
        Progress._write(out, ("\r\033[2K" if tty else "") + line + "\n")


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


# ---------------------------------------------------------------------------
# Live feedback while a command runs (#270)
# ---------------------------------------------------------------------------

#: Seconds a command runs before the status line first appears.
LIVE_AFTER = 2.0
#: Seconds between status-line refreshes.
LIVE_INTERVAL = 1.0

_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def elapsed_text(seconds: float) -> str:
    """``42s``, ``1m 42s``, ``2h 05m``: what the status line says it has waited."""
    whole = int(seconds)
    if whole < 60:
        return f"{whole}s"
    if whole < 3600:
        return f"{whole // 60}m {whole % 60:02d}s"
    return f"{whole // 3600}h {whole % 3600 // 60:02d}m"


def _plain(line: str) -> str:
    """One output line with escapes and controls gone, and only what follows
    the last carriage return (a progress meter rewriting itself); indentation
    is kept."""
    text = line.rstrip("\r\n").rsplit("\r", 1)[-1]
    return _CONTROL.sub("", _ESCAPES.sub("", text)).rstrip()


def _clean_line(line: str) -> str:
    """:func:`_plain` for a status line, where leading space is wasted room."""
    return _plain(line).strip()


class LiveStatus:
    """The one writer that owns the terminal line while a command runs.

    While a command runs longer than :data:`LIVE_AFTER` seconds on a terminal,
    one status line -- ``  … 1m 42s  <last output line>`` -- is rewritten in
    place every :data:`LIVE_INTERVAL` seconds under the ``$`` line, and erased
    when the command ends. With *verbose* every output line is written as it
    arrives instead. Anything else the run prints while a command is running
    (the sudo keepalive's warning, D-062) goes through :meth:`print`, which
    erases the status line first, so two writers never interleave.

    Everything written here goes to the *terminal itself*, not through the run
    log's tee (D-077): the log already receives every output line from the
    runner, so what the operator sees live can never change what is logged.
    When stdout is not a terminal and *verbose* is off, nothing is written and
    :attr:`active` is false, so the runner behaves exactly as before.
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        *,
        verbose: bool = False,
        after: float = LIVE_AFTER,
        interval: float = LIVE_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._stream = stream
        self.verbose = verbose
        self._after = after
        self._interval = interval
        self._clock = clock
        self._lock = threading.RLock()
        self._began = 0.0
        self._last = ""
        self._shown = False
        self._running = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _out(self) -> IO[str]:
        stream = self._stream if self._stream is not None else sys.stdout
        return getattr(stream, "_real", stream)  # the terminal, never the log's tee

    def _tty(self) -> bool:
        try:
            return bool(self._out().isatty())
        except (AttributeError, ValueError):
            return False

    @property
    def active(self) -> bool:
        """Whether the runner needs to read output as it arrives for this."""
        return self.verbose or self._tty()

    def _width(self) -> int:
        try:
            columns = os.get_terminal_size(self._out().fileno()).columns
        except (OSError, ValueError, AttributeError):
            columns = 0
        return columns if columns > 0 else shutil.get_terminal_size().columns

    def _erase(self) -> None:
        if self._shown:
            Progress._write(self._out(), "\r\033[2K")
            self._shown = False

    def _draw(self) -> None:
        if self.verbose or not self._tty():
            return
        elapsed = self._clock() - self._began
        if elapsed < self._after:
            return
        head = f"  … {elapsed_text(elapsed)}  "
        room = max(0, self._width() - len(head) - 1)
        tail = self._last
        if len(tail) > room:
            tail = tail[: max(0, room - 1)] + "…" if room > 1 else ""
        Progress._write(self._out(), "\r\033[2K" + head + tail)
        self._shown = True

    # -- a command's life --------------------------------------------------

    @contextlib.contextmanager
    def command(self) -> Iterator[None]:
        """Wrap one running command: start the refresh, erase it afterwards."""
        with self._lock:
            self._began = self._clock()
            self._last = ""
            self._running = True
        self._stop = threading.Event()
        stop = self._stop
        if not self.verbose and self._tty():
            self._thread = threading.Thread(target=self._tick, args=(stop,), daemon=True)
            self._thread.start()
        try:
            yield
        finally:
            stop.set()
            if self._thread is not None:
                self._thread.join()
                self._thread = None
            with self._lock:
                self._running = False
                self._erase()

    def _tick(self, stop: threading.Event) -> None:
        while not stop.wait(self._interval):
            with self._lock:
                if stop.is_set():
                    return
                self._draw()

    def output(self, line: str) -> None:
        """One line the command wrote, from either pipe."""
        with self._lock:
            if self.verbose:
                Progress._write(self._out(), "    " + _plain(line) + "\n")
                return
            cleaned = _clean_line(line)
            if cleaned:
                self._last = cleaned

    def print(self, text: str, *, err: bool = False) -> None:
        """A line of the run's own, written through the same lock: the status
        line is erased first, and redrawn by the next refresh."""
        with self._lock:
            self._erase()
            stream = sys.stderr if err else sys.stdout
            print(text, file=stream, flush=True)


_live: LiveStatus | None = None


def current_live() -> LiveStatus | None:
    """The status writer of the command in progress, or None."""
    return _live


@contextlib.contextmanager
def activate_live(live: LiveStatus) -> Iterator[LiveStatus]:
    global _live
    previous, _live = _live, live
    try:
        yield live
    finally:
        _live = previous
