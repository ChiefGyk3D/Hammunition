# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A readable log of every run that changes state or runs long (D-077).

The transaction log (``state/log.py``) is the machine's record of what was done
and what ``uninstall`` stands on. It is JSON, it holds no command output, and a
dry run writes nothing to it. A ``navigation`` plan printed nothing for
twenty-five minutes (#197) and an install can run for hours with its output only
in a terminal; this module is the other half -- one plain-text file per run,
under ``<state dir>/logs/``, that an operator reads, ``tail -f``\\ s, or attaches
to an issue.

Line format, one event per line::

    2026-10-02T18:15:00.123Z out  Plan for 2 units ...

``<UTC timestamp> <tag> <text>``. Tags: ``meta`` (the run's own facts), ``out``
and ``err`` (what the engine printed on stdout and stderr, teed byte for byte:
the terminal sees exactly what it saw before), ``cmd`` (a command starting),
``cmd-out`` and ``cmd-err`` (that command's output, as it arrives), ``cmd-end``
(its exit code and duration) and ``result`` (the run's last line).

Rotation (:func:`rotate`) keeps :data:`MAX_FILES` files and :data:`MAX_BYTES`
bytes, oldest first, and never touches a run in progress: each run holds an
exclusive ``flock`` on its own file for its life, which the kernel drops when
the process dies however it dies, so "in progress" needs no pid file to go stale.
Both limits are constants, not station config: station values are the things
only the operator can supply (D-035), and a retention policy is not one.

A log that cannot be written never fails the run it describes; the run says so
once on stderr and carries on.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from hammunition.paths import (
    OperatorDirError,
    ensure_operator_dir,
    operator_for,
    state_dir,
)

__all__ = [
    "MAX_BYTES",
    "MAX_FILES",
    "RunInfo",
    "RunLog",
    "current",
    "list_runs",
    "logs_dir",
    "redact_argv",
    "rotate",
    "session",
]

#: At most this many run logs are kept; the oldest go first.
MAX_FILES = 30
#: At most this many bytes of run logs in total; the oldest go first.
MAX_BYTES = 200 * 1024 * 1024

_NAME = re.compile(r"^(\d{8}T\d{6}Z)-([a-z0-9-]+)-(\d+)\.log$")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_RESULT = re.compile(r"^\S+ result\s+exit=(\d+)\s+(\S.*)$")

#: Flags whose value is a station value or a place on the operator's network:
#: logged as the flag with ``<redacted>`` for its value. A callsign is the same
#: class of identifier as a hostname; the plan prints what it prints, and the
#: argv is not a second place for these.
_REDACTED_FLAGS = frozenset(
    {
        "--callsign",
        "--grid-square",
        "--node-alias",
        "--map-regions",
        "--rig-device",
        "--rig-owner",
        "--mirror",
    }
)

#: One run's log stops growing here (a `reference serve` can run for days);
#: the log says so once and the run goes on.
MAX_RUN_BYTES = 50 * 1024 * 1024

_EXIT_WORDS = {0: "ok", 1: "failed", 2: "refused", 3: "not confirmed"}

_active: RunLog | None = None


def current() -> RunLog | None:
    """The run log of the command in progress, or None."""
    return _active


def logs_dir(owner: str | None = None) -> Path:
    """``<state dir>/logs``, owner-aware like the transaction log (D-043)."""
    return state_dir(owner) / "logs"


def redact_argv(argv: Sequence[str]) -> list[str]:
    """*argv* with the value of every station flag replaced, both spellings."""
    out: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            out.append("<redacted>")
            hide_next = False
            continue
        flag, eq, _ = item.partition("=")
        if flag in _REDACTED_FLAGS:
            if eq:
                out.append(f"{flag}=<redacted>")
            else:
                out.append(item)
                hide_next = True
            continue
        out.append(item)
    return out


def _stamp(now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _clean(text: str) -> str:
    return _ANSI.sub("", text)


class RunLog:
    """One run's log file. Write-through: every line is flushed as it is made."""

    def __init__(self, path: Path, handle: IO[str]) -> None:
        self.path = path
        self._handle = handle
        self._lock = threading.Lock()
        self._partial: dict[str, str] = {}
        self._closed = False
        self._scrub: list[str] = []
        self._written = 0
        self._truncated = False
        self.exit_code: int | None = None
        """The status the run is about to return; set by the caller."""

    # -- writing -----------------------------------------------------------

    def write(self, tag: str, text: str) -> None:
        """One timestamped line per line of *text*."""
        with self._lock:
            self._emit(tag, text)

    def set_scrub(self, values: Sequence[str]) -> None:
        """Station values to replace with ``<redacted>`` in every line logged.

        The plan and its errors print the station (a region in a data plan, a
        rejected callsign, the mirror), so redacting the argv alone would be
        redacting the one place that does not matter. Values shorter than
        three characters are ignored: they would eat ordinary words."""
        unique = {v for v in values if len(v) >= 3}
        with self._lock:
            self._scrub = sorted(unique, key=len, reverse=True)

    def _scrubbed(self, line: str) -> str:
        for value in self._scrub:
            line = re.sub(re.escape(value), "<redacted>", line, flags=re.IGNORECASE)
        return line

    def _emit(self, tag: str, text: str) -> None:
        if self._closed:
            return
        stamp = _stamp()
        try:
            for line in text.split("\n"):
                if tag != "result" and self._written > MAX_RUN_BYTES:
                    if not self._truncated:
                        self._handle.write(
                            f"{stamp} meta    log truncated at {MAX_RUN_BYTES} bytes\n"
                        )
                        self._truncated = True
                    break
                out = f"{stamp} {tag:<7} {self._scrubbed(line)}\n"
                self._handle.write(out)
                self._written += len(out)
            self._handle.flush()
        except (OSError, ValueError):
            self._closed = True  # a full disk must not fail the run it describes

    def feed(self, tag: str, chunk: str) -> None:
        """Stream text in as written: whole lines are logged, the tail waits.

        A carriage return discards what came before it on the line, so the
        in-place counter of :mod:`hammunition.progress` leaves its start and
        finish lines in the log and not a line per redraw.
        """
        with self._lock:
            buffered = (self._partial.get(tag, "") + chunk).replace("\r\n", "\n")
            *lines, rest = buffered.split("\n")
            for line in lines:
                line = line[:-1] if line.endswith("\r") else line
                self._emit(tag, _clean(line.rsplit("\r", 1)[-1]))
            tail = rest.rsplit("\r", 1)[-1]
            self._partial[tag] = tail if tail else rest

    def flush_partial(self) -> None:
        with self._lock:
            for tag, rest in list(self._partial.items()):
                if rest:
                    self._emit(tag, _clean(rest))
            self._partial.clear()

    def command_start(self, argv: Sequence[str]) -> float:
        self.write("cmd", "$ " + " ".join(argv))
        return time.monotonic()

    def step_start(self, index: int, count: int, description: str) -> None:
        self.write("meta", f"step {index}/{count}: {description}")

    def command_output(self, stream: str, line: str) -> None:
        self.write("cmd-out" if stream == "out" else "cmd-err", _clean(line.rstrip("\n")))

    def command_end(self, argv: Sequence[str], returncode: int, began: float) -> None:
        self.write(
            "cmd-end",
            f"exit={returncode} elapsed={time.monotonic() - began:.1f}s  {argv[0] if argv else ''}",
        )

    def close(self, exit_code: int | None, began: float) -> None:
        self.flush_partial()
        if exit_code is not None:
            word = _EXIT_WORDS.get(exit_code, "failed")
            self.write("result", f"exit={exit_code} {word} elapsed={time.monotonic() - began:.1f}s")
        with self._lock:
            self._closed = True
            with contextlib.suppress(OSError):
                self._handle.close()  # drops the flock too


class _Tee:
    """A text stream that writes through to *real* and feeds the run log."""

    def __init__(self, real: Any, run: RunLog, tag: str) -> None:
        self._real = real
        self._run = run
        self._tag = tag

    def write(self, text: str) -> int:
        written = self._real.write(text)
        self._run.feed(self._tag, text)
        return int(written) if written is not None else len(text)

    def writelines(self, lines: Any) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        self._real.flush()

    def __getattr__(self, name: str) -> Any:
        # isatty, fileno, encoding, reconfigure: the terminal's own answers,
        # so progress and line buffering behave exactly as they did.
        return getattr(self._real, name)


def _open(path: Path, owner: str | None) -> RunLog:
    """Create *path* exclusively, 0600, locked, and give it to the operator."""
    parent = path.parent
    ensure_operator_dir(parent, owner)
    with contextlib.suppress(OSError):
        # Semgrep: a deliberate mode (0755/0644 on installed files and launchers, 0700 private); nothing group- or world-writable.
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
        os.chmod(parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        entry = operator_for(path, owner)
        if entry is not None:
            os.fchown(fd, entry.pw_uid, entry.pw_gid)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle = os.fdopen(fd, "w", encoding="utf-8", errors="replace", buffering=1)
    except BaseException:
        os.close(fd)
        raise
    return RunLog(path, handle)


def _is_running(path: Path) -> bool:
    """Whether a live process holds the file's lock (it is a run in progress)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _ours(directory: Path) -> list[Path]:
    try:
        names = sorted(p for p in directory.iterdir() if _NAME.match(p.name))
    except OSError:
        return []
    return [p for p in names if p.is_file() and not p.is_symlink()]


def rotate(
    directory: Path, *, max_files: int = MAX_FILES, max_bytes: int = MAX_BYTES, room: int = 1
) -> list[Path]:
    """Remove the oldest logs until *room* more fit under both limits.

    Returns what was removed. A run in progress is never removed, however old:
    it is skipped and the next oldest goes instead. Files whose names are not
    ours are not counted and not touched.
    """
    files = _ours(directory)
    sizes = {p: _size(p) for p in files}
    total = sum(sizes.values())
    count = len(files)
    removed: list[Path] = []
    for path in files:
        if count + room <= max_files and total <= max_bytes:
            break
        if _is_running(path):
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(path)
        count -= 1
        total -= sizes[path]
    return removed


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


@dataclass(frozen=True)
class RunInfo:
    """One run log as ``hammunition logs`` lists it."""

    path: Path
    started: str  # ISO 8601 UTC, from the file name
    command: str
    pid: int
    size: int
    result: str  # ``ok``, ``failed``, ``refused``, ``not confirmed``, ``running``, ``incomplete``
    exit_code: int | None


def _read_result(path: Path) -> tuple[int | None, str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            handle.seek(max(0, end - 4096))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None, "unreadable"
    for line in reversed(tail.splitlines()):
        found = _RESULT.match(line)
        if found:
            return int(found.group(1)), found.group(2).split(" elapsed=")[0]
    return None, "running" if _is_running(path) else "incomplete"


def list_runs(directory: Path) -> list[RunInfo]:
    """Every run log under *directory*, newest first."""
    runs: list[RunInfo] = []
    for path in _ours(directory):
        match = _NAME.match(path.name)
        if match is None:  # pragma: no cover - _ours filtered on it
            continue
        stamp, command, pid = match.groups()
        started = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).isoformat()
        code, result = _read_result(path)
        runs.append(
            RunInfo(
                path=path,
                started=started,
                command=command,
                pid=int(pid),
                size=_size(path),
                result=result,
                exit_code=code,
            )
        )
    runs.reverse()
    return runs


def total_size(directory: Path) -> int:
    return sum(_size(p) for p in _ours(directory))


def _slug(command: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", command.lower()).strip("-")
    return slug or "run"


@contextlib.contextmanager
def session(
    *,
    command: str,
    argv: Sequence[str],
    owner: str | None,
    version: str,
) -> Iterator[RunLog | None]:
    """Log everything the command prints and runs, and restore the streams.

    Yields the :class:`RunLog` -- or None when it could not be created, after
    saying so once on stderr. The caller sets ``run.exit_code`` to the status
    it is about to return; the ``result`` line is written from it on the way
    out, and a run that dies by exception or ``SystemExit`` still gets one.
    """
    import sys

    global _active
    began = time.monotonic()
    directory = logs_dir(owner)
    try:
        rotate(directory)
        now = datetime.now(UTC)
        path = directory / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{_slug(command)}-{os.getpid()}.log"
        run = _open(path, owner)
    except (OSError, OperatorDirError) as exc:
        with contextlib.suppress(OSError, ValueError):
            sys.stderr.write(f"note: no run log for this command ({exc}); it runs unlogged.\n")
        yield None
        return
    run.write("meta", f"hammunition {version}")
    run.write("meta", f"command: {command}")
    run.write("meta", "argv: " + " ".join(redact_argv(argv)))
    run.write("meta", f"pid={os.getpid()} euid={os.geteuid()}")
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout = _Tee(real_out, run, "out")
    sys.stderr = _Tee(real_err, run, "err")
    _active = run
    code: int | None = None
    try:
        yield run
        code = run.exit_code
    except KeyboardInterrupt:
        code = 1
        run.write("meta", "interrupted")
        raise
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        raise
    except BaseException as exc:
        import traceback

        run.write("meta", "crashed: " + "".join(traceback.format_exception(exc)).rstrip())
        code = 70
        raise
    finally:
        _active = None
        sys.stdout, sys.stderr = real_out, real_err
        run.close(code, began)
