# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Drive a program in a real pseudo-terminal and wait for text on its screen.

urwid redraws with cursor movement, so spaces and the order of partial updates are
not reliable: matching ignores all whitespace and escape sequences, and each
expect() looks only past what the previous one matched."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import termios
import time
from collections.abc import Mapping, Sequence

ANSI = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]"
)


def squash(text: str) -> str:
    return re.sub(r"\s+", "", ANSI.sub("", text))


class PtyProcess:
    def __init__(
        self, argv: Sequence[str], env: Mapping[str, str], *, rows: int = 30, cols: int = 100
    ) -> None:
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.proc = subprocess.Popen(
            list(argv),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=dict(env),
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave)
        self.raw = ""
        self._consumed = 0

    def send(self, text: str) -> None:
        os.write(self.master, text.encode())

    def _pump(self, timeout: float) -> None:
        ready, _, _ = select.select([self.master], [], [], timeout)
        if not ready:
            return
        try:
            data = os.read(self.master, 65536)
        except OSError:  # EIO once the child side closes
            return
        self.raw += data.decode("utf-8", "replace")

    def expect(self, needle: str, timeout: float = 20.0) -> None:
        want = squash(needle)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            seen = squash(self.raw)
            at = seen.find(want, self._consumed)
            if at >= 0:
                self._consumed = at + len(want)
                return
            self._pump(0.2)
        tail = ANSI.sub("", self.raw)[-1500:]
        raise AssertionError(f"timed out waiting for {needle!r}; last output:\n{tail}")

    def wait(self, timeout: float = 15.0) -> int:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            code = self.proc.poll()
            if code is not None:
                return code
            self._pump(0.1)
        raise AssertionError(
            f"process did not exit; last output:\n{ANSI.sub('', self.raw)[-1500:]}"
        )

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        os.close(self.master)
