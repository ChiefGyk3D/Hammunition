# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import contextlib
import threading
import time

import urwid

from hammunition.console.worker import SyncBackground, ThreadBackground


def test_sync_background_delivers_a_result_or_an_error() -> None:
    got: list[tuple[object, object]] = []
    SyncBackground().submit(lambda: 41 + 1, lambda r, e: got.append((r, e)))
    bad = ValueError("x")

    def boom() -> int:
        raise bad

    SyncBackground().submit(boom, lambda r, e: got.append((r, e)))
    assert got == [(42, None), (None, bad)]


def test_thread_background_runs_off_the_ui_thread_and_delivers_on_the_loop() -> None:
    event_loop = urwid.SelectEventLoop()
    loop = urwid.MainLoop(urwid.SolidFill(" "), event_loop=event_loop)
    bg = ThreadBackground()
    bg.attach(loop)
    main = threading.get_ident()
    seen: dict[str, object] = {}

    def work() -> str:
        seen["worker"] = threading.get_ident()
        time.sleep(0.05)
        return "done"

    def done(result: str | None, error: BaseException | None) -> None:
        seen["delivered_on"] = threading.get_ident()
        seen["result"], seen["error"] = result, error
        raise urwid.ExitMainLoop

    def give_up(*_: object) -> None:
        raise urwid.ExitMainLoop

    bg.submit(work, done)
    event_loop.alarm(5, give_up)  # a hung worker fails the test instead of hanging it
    with contextlib.suppress(urwid.ExitMainLoop):
        event_loop.run()  # the event loop alone: no screen, no terminal needed
    assert seen["worker"] != main and seen["delivered_on"] == main
    assert (seen["result"], seen["error"]) == ("done", None)
