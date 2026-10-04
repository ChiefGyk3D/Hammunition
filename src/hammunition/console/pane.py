# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""An embedded terminal that runs the real engine command, so sudo's password
prompt, the group choice and any consent `yes` reach the engine untouched, typed
by a person. The console does not read the pane's input, echo it or inject keys."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import urwid

from hammunition.console import guard
from hammunition.console.context import Context
from hammunition.console.screens.base import Screen

RUNNER = Path(__file__).with_name("runner.py")


@dataclass(frozen=True)
class PaneSpec:
    command: list[str]
    env: dict[str, str]


def build_pane_spec(argv: Sequence[str], status_path: str, environ: Mapping[str, str]) -> PaneSpec:
    checked = guard.checked_argv(argv)
    env = guard.scrubbed_environ(environ)
    # No TERM default here: urwid.Terminal forces TERM=linux in the child whatever it is given
    # (measured on urwid 2.6.16), so a default would be a no-op.
    return PaneSpec([sys.executable, str(RUNNER), status_path, "--", *checked], env)


def read_exit_status(path: str) -> int | None:
    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _end_group(pid: int, grace: float = 3.0) -> None:
    """End the runner and everything it started, then reap it.

    urwid's Terminal.terminate() signals only the runner and then blocks in waitpid,
    forever when SIGHUP was inherited as ignored, and the engine behind the runner
    depends on the pty closing to be hung up at all. The runner (a session leader,
    so its group is its pid) forwards SIGHUP to its group; SIGKILL to the whole
    group follows when anything is left after the grace period.
    """
    for sig, wait in ((signal.SIGHUP, grace), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(pid, sig)
        except OSError:
            break
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                done, _ = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                return
            if done:
                with contextlib.suppress(OSError):
                    os.killpg(pid, signal.SIGKILL)  # anything the runner's child left behind
                return
            time.sleep(0.02)


class _PaneFrame(urwid.WidgetWrap):
    """All keys go to the program until it exits; then Enter continues. Nothing else leaves the pane."""

    def __init__(self, owner: PaneScreen, inner: urwid.Widget) -> None:
        self._owner = owner
        super().__init__(inner)

    def keypress(self, size: Any, key: str) -> str | None:
        if self._owner.finished:
            if key == "enter":
                self._owner.finish()
                return None
            return key
        # While the program runs every key is the program's, without exception: whatever
        # Terminal hands back (it returns unmapped keys until its keygrab engages) is
        # dropped here, never passed up to the shell, which would pop the pane or quit.
        super().keypress(size, key)
        return None


class PaneScreen(Screen):
    name = "pane"

    def __init__(
        self,
        ctx: Context,
        argv: Sequence[str],
        title: str,
        on_exit: Callable[[int | None], None],
        *,
        loop: urwid.MainLoop,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(ctx)
        self.title = title
        self.finished = False
        self._done = False
        self.exit_code: int | None = None
        self._on_exit = on_exit
        self._dir = tempfile.mkdtemp(prefix="hammunition-console-")
        self._status = os.path.join(self._dir, "status")
        spec = build_pane_spec(argv, self._status, os.environ if environ is None else environ)
        self._banner = urwid.Text(
            "Every key goes to the program, including Ctrl-C. This screen cannot be left until it ends."
        )
        self._terminal = urwid.Terminal(spec.command, env=spec.env, main_loop=loop)
        # urwid's Terminal keeps "ctrl a" as an escape key and swallows the first one, and
        # hands mapped keys (arrows, space) back until a printable key engages its keygrab.
        # Engage the grab from the start and make the escape key one nobody can type.
        self._terminal.escape_sequence = "<never typed>"
        self._terminal.keygrab = True
        urwid.connect_signal(self._terminal, "closed", self._closed)
        self._frame = _PaneFrame(
            self, urwid.Frame(self._terminal, footer=urwid.AttrMap(self._banner, "footer"))
        )

    def widget(self) -> urwid.Widget:
        return self._frame

    def _closed(self, *_: object) -> None:
        self.exit_code = read_exit_status(self._status)
        self.finished = True
        said = (
            f"exit code {self.exit_code}"
            if self.exit_code is not None
            else "no exit code (the program was cut off)"
        )
        self._banner.set_text(f"Finished with {said}. Press Enter to continue.")

    def finish(self) -> None:
        if self._done:
            return
        self._done = True
        shutil.rmtree(self._dir, ignore_errors=True)
        self._on_exit(self.exit_code)

    def on_hangup(self) -> None:
        """The console's own terminal closed: close the pty, as the terminal closing would."""
        # urwid 2.6 forks the child on first render; before that there is no pid to end,
        # and Terminal.terminate() raises on it.
        pid = getattr(self._terminal, "pid", None)
        if pid is not None and pid > 0:
            _end_group(pid)
            self._terminal.terminate()
        shutil.rmtree(self._dir, ignore_errors=True)
