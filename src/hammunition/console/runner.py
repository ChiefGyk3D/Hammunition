# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run one command with this process's terminal, and record how it ended.

    runner.py STATUS_FILE -- COMMAND...

Started by the pane inside urwid.Terminal. It exists for two reasons: the
console must learn the child's exit status without relying on how any urwid
version reports a child's death, and Ctrl-C must reach the child, not kill the
thing watching it. A *handler* (not SIG_IGN) is installed for SIGINT: handlers
are reset to the default across exec, so the child still gets the default
action, while this process just waits.

A hang-up or termination (SIGHUP, SIGTERM) is the opposite case: it must end the
child too, even when this process inherited SIGHUP as ignored (nohup, some CI
supervisors), where waiting for the pty to close would wait forever. The signal is
sent to the whole process group the pty made (this process ignores it meanwhile),
and a child still alive after a grace period is killed outright.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

GRACE = 2.0


def _wait(proc: subprocess.Popen[bytes], stop: list[int]) -> int:
    deadline: float | None = None
    while True:
        try:
            return proc.wait(timeout=0.05)
        except subprocess.TimeoutExpired:
            pass
        if stop and deadline is None:
            deadline = time.monotonic() + GRACE
            _signal_group(stop[0])
        elif deadline is not None and time.monotonic() >= deadline:
            proc.kill()
            return proc.wait()


def _signal_group(number: int) -> None:
    """Tell every process in this group, this one included, which already ignores it."""
    previous = signal.signal(number, signal.SIG_IGN)
    try:
        os.killpg(os.getpgrp(), number)
    except OSError:
        pass
    finally:
        signal.signal(number, previous)


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "--":
        print("usage: runner.py STATUS_FILE -- COMMAND...", file=sys.stderr)
        return 2
    status_path, command = argv[0], argv[2:]
    signal.signal(signal.SIGINT, lambda *_: None)
    stop: list[int] = []
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, lambda number, _frame: stop.append(number))
    try:
        code = _wait(subprocess.Popen(command), stop)
    except FileNotFoundError:
        print(f"{command[0]}: command not found", file=sys.stderr)
        code = 127
    except OSError as exc:
        print(f"{command[0]}: cannot run ({exc.strerror})", file=sys.stderr)
        code = 126
    if code < 0:
        code = 128 + (-code)
    try:
        with open(status_path, "w", encoding="utf-8") as handle:
            handle.write(f"{code}\n")
    except OSError:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
