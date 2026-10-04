# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's run logs: a list from `logs --json`, and a viewer for one file. The
viewer opens only a path the engine listed that lies inside the directory it
reported, and shows file text as inert text (every control character removed)."""

from __future__ import annotations

import os
from typing import Any

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean, first_line, human_size
from hammunition.console.screens.base import Row, Screen, text

TAIL_BYTES = 65536
MAX_LINES = 5000
FOLLOW_SECONDS = 1.0


def is_inside(path: str, directory: str) -> bool:
    """True only for an existing regular file strictly below the directory, symlinks resolved."""
    real, base = os.path.realpath(path), os.path.realpath(directory)
    try:
        if os.path.commonpath([real, base]) != base or real == base:
            return False
    except ValueError:
        return False
    return os.path.isfile(real)


def read_tail(path: str, max_bytes: int = TAIL_BYTES) -> tuple[str, int]:
    with open(path, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        start = max(0, size - max_bytes)
        handle.seek(start)
        data = handle.read()
    content = data.decode("utf-8", errors="replace")
    if start > 0 and "\n" in content:
        content = content.split("\n", 1)[1]
    return content, size


def read_from(path: str, offset: int, max_bytes: int = TAIL_BYTES) -> tuple[str, int] | None:
    """New text since offset, at most max_bytes: a larger unread gap is skipped to the
    last max_bytes (partial first line dropped). None when the file is gone."""
    try:
        with open(path, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            start = offset
            if size - offset > max_bytes:
                start = size - max_bytes
            handle.seek(start)
            data = handle.read(max_bytes)
    except FileNotFoundError:
        return None
    content = data.decode("utf-8", errors="replace")
    if start > offset and "\n" in content:
        content = content.split("\n", 1)[1]
    return content, start + len(data)


class LogViewScreen(Screen):
    name = "logview"

    def __init__(self, ctx: Context, path: str, directory: str, running: bool) -> None:
        super().__init__(ctx)
        self.title = clean(f"Log: {os.path.basename(path)}")
        self._path, self._directory = path, directory
        self.following = running
        self.note = ""
        self.lines: list[str] = []
        self._offset = 0
        self._started = False

    def on_show(self) -> None:
        if not self._started:
            self._started = True
            try:
                content, self._offset = read_tail(self._path)
            except OSError as exc:
                self.note = f"Could not read the log: {exc.strerror}"
                self.following = False
            else:
                self._append(content)
            if self.following:
                self.ctx.after(FOLLOW_SECONDS, self._tick)
        self.redraw()

    def on_hide(self) -> None:
        self.following = False

    def _append(self, content: str) -> None:
        self.lines += [clean(line) for line in content.splitlines()]
        del self.lines[:-MAX_LINES]

    def _tick(self) -> None:
        if not self.following:
            return
        gone = "The log was rotated away; no longer following."
        try:
            if not is_inside(self._path, self._directory):
                raise FileNotFoundError(self._path)
            chunk = read_from(self._path, self._offset)
            if chunk is None:
                raise FileNotFoundError(self._path)
            content, new_offset = chunk
            size = os.path.getsize(self._path)
            if size < self._offset:
                self.note, self.lines = "The log was truncated; showing it again from the end.", []
                content, new_offset = read_tail(self._path)
            elif size - self._offset > TAIL_BYTES:
                self.note = f"Skipped {size - self._offset - TAIL_BYTES} bytes of log that arrived between updates."
        except OSError:
            self.note, self.following = gone, False
            self.redraw()
            return
        self._offset = new_offset
        self._append(content)
        self.ctx.after(FOLLOW_SECONDS, self._tick)
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.note:
            rows.append(text(self.note, "warn"))
        rows += [text(line) for line in self.lines] or [text("(empty)", "dim")]
        self.set_rows(rows)
        if self.following and len(self._walker):
            self._walker.set_focus(len(self._walker) - 1)


class LogsScreen(Screen):
    name = "logs"
    title = "Logs"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.note = ""
        self._doc: Document | None = None

    def on_show(self) -> None:
        self.load("logs", lambda: self.ctx.engine.read("logs"), lambda d: setattr(self, "_doc", d))
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("logs") == "error":
            rows.append(text(self.errors["logs"], "fail"))
        elif self._doc is not None:
            runs = [r for r in (self._doc.body.get("runs") or []) if isinstance(r, dict)]
            if not runs:
                rows.append(text("No runs yet."))
            for run in runs:
                code = run.get("exit_code")
                row = Row(
                    f"{run.get('started') or '':<22} {run.get('command') or '?':<18} {run.get('result') or '?':<14} "
                    f"{human_size(run['size']) if isinstance(run.get('size'), int) else '':>9}  "
                    f"{code if isinstance(code, int) else '-'}",
                    run,
                )
                urwid.connect_signal(row, "activate", self._open)
                rows.append(row)
        else:
            rows.append(text("Reading the run logs..."))
        self.set_rows(rows)

    def _open(self, row: Row) -> None:
        run: Any = row.value
        directory = str(self._doc.body.get("directory", "")) if self._doc else ""
        path = run.get("path") if isinstance(run, dict) else None
        if not isinstance(path, str) or not directory or not is_inside(path, directory):
            self.note = f"Refused: {first_line(os.path.basename(str(path)))} is not inside the log directory the engine reported."
            self.redraw()
            return
        self.note = ""
        self.ctx.push(
            LogViewScreen(self.ctx, path, directory, running=run.get("result") == "running")
        )
