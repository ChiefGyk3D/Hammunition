# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""One PaneScreen in a real urwid loop, for tests/test_pane_pty.py only.

Usage: python -m console.pane_harness -- ARGV...   Writes the pane's exit code to
the file named by HARNESS_RESULT when the operator presses Enter after it ends."""

from __future__ import annotations

import os
import sys

import urwid

from hammunition.console.pane import PaneScreen

from .helpers import FakeContext


def main(argv: list[str]) -> int:
    result_path = os.environ["HARNESS_RESULT"]
    ctx = FakeContext()
    box: list[urwid.MainLoop] = []

    def on_exit(code: int | None) -> None:
        with open(result_path, "w", encoding="utf-8") as handle:
            handle.write(f"{code}\n")
        raise urwid.ExitMainLoop

    def unhandled(key: str) -> None:
        # what the Shell does with a key a pane hands up: q quits, b and esc leave
        if key in ("q", "b", "esc"):
            raise urwid.ExitMainLoop

    loop = urwid.MainLoop(urwid.SolidFill(" "), unhandled_input=unhandled)
    box.append(loop)
    pane = PaneScreen(ctx, argv, "harness", on_exit, loop=loop)
    loop.widget = pane.widget()
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1 :]))
