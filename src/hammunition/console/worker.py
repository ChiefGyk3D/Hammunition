# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run blocking work (the engine's reads) off the UI thread and hand the result
back on it. The urwid loop's own file watching is the hand-off, so nothing but
the main thread ever touches a widget."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

import urwid

T = TypeVar("T")
Done = Callable[[Any, "BaseException | None"], None]


class Background(Protocol):
    def submit(
        self, call: Callable[[], T], done: Callable[[T | None, BaseException | None], None]
    ) -> None: ...


class SyncBackground:
    """Runs the call at once, in the caller's thread. For tests."""

    def submit(
        self, call: Callable[[], T], done: Callable[[T | None, BaseException | None], None]
    ) -> None:
        try:
            result = call()
        except Exception as exc:
            done(None, exc)
            return
        done(result, None)


class ThreadBackground:
    def __init__(self) -> None:
        self._loop: urwid.MainLoop | None = None

    def attach(self, loop: urwid.MainLoop) -> None:
        self._loop = loop

    def submit(
        self, call: Callable[[], T], done: Callable[[T | None, BaseException | None], None]
    ) -> None:
        loop = self._loop
        if loop is None:
            raise RuntimeError("ThreadBackground.attach(loop) was not called")
        outcome: list[tuple[Any, BaseException | None]] = []
        read_fd, write_fd = os.pipe()
        handle: Any = None

        def on_readable() -> None:
            os.read(read_fd, 1)
            loop.remove_watch_file(handle)
            os.close(read_fd)
            os.close(write_fd)
            result, error = outcome[0]
            done(result, error)

        handle = loop.watch_file(read_fd, on_readable)

        def work() -> None:
            try:
                outcome.append((call(), None))
            except Exception as exc:
                outcome.append((None, exc))
            finally:
                os.write(write_fd, b"x")

        threading.Thread(target=work, daemon=True).start()
