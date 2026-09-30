# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""sudo's cached credential, kept valid for the length of one transaction (D-062).

An unprivileged run escalates per command: :meth:`Command.argv_for` puts
``sudo`` in front of each root step and nothing else. sudo caches the
credential for ``timestamp_timeout`` minutes (15 on Debian), and a
transaction that alternates root steps with long operator-side work -- a
Navit conversion, a Garmin map, a Routino database -- outlives it. The next
root step then asks for the password again, on a terminal nobody is
watching: a ``navigation`` install on the field laptop waited 7.8 hours at
that prompt after 30 minutes of work (#137).

What this does, and all it does:

* ``sudo -v`` once, before the first step, interactively. The password is
  asked while the operator is still at the keyboard, by sudo itself, on the
  terminal. The engine never sees, stores or passes it.
* ``sudo -n -v`` from a background thread every :data:`KEEPALIVE_INTERVAL`
  seconds. ``-n`` means it can never prompt; it only extends a ticket that
  already exists. Its stdin is ``/dev/null``.
* Stops when the transaction ends, however it ends. The ticket is then left
  to expire on sudo's own schedule, never extended beyond the run.
* The first refresh that fails is reported once and the refresh stops. The
  next root step then prompts exactly as it did before this module existed.
  It never retries in a loop.

``timestamp_type`` does not matter. The refresh is a child of the same
process on the same controlling terminal as every root step, so a per-tty
ticket (Debian's default) is the ticket the steps use, and a global or
per-parent-process one is too.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType

from hammunition.backends.base import Action, Command

__all__ = [
    "KEEPALIVE_INTERVAL",
    "KeepaliveFailure",
    "SudoKeepalive",
    "keepalive_wanted",
]

#: Seconds between refreshes. sudo's compiled-in ``timestamp_timeout`` is 15
#: minutes, and ``sudo -l`` does not print a compiled-in default -- only a
#: ``Defaults`` line somebody wrote -- so the real value is not measurable
#: without reading sudoers as root. Four minutes stays inside every timeout
#: of five minutes or more; a site that sets it lower gets a failed refresh
#: reported once, and the prompts it had before.
KEEPALIVE_INTERVAL = 240.0

#: ``(argv, interactive) -> returncode``. Interactive means the terminal is
#: inherited, so sudo can ask; otherwise stdin is ``/dev/null`` and output is
#: discarded.
RunSudo = Callable[[Sequence[str], bool], int]


def keepalive_wanted(steps: Sequence[Command | Action], *, euid: int) -> bool:
    """Whether a transaction needs its ticket kept: run as a user, with at
    least one root step and at least one step that is not.

    Root already has no sudo to keep. A run whose every step is a root step
    re-uses the ticket on each, and one with no root step never asks.
    """
    if euid == 0:
        return False
    root = any(isinstance(s, Command) and s.requires_root for s in steps)
    operator = any(not s.requires_root for s in steps)
    return root and operator


def _run(argv: Sequence[str], interactive: bool) -> int:
    """Run sudo. A missing or unexecutable sudo is a failure, not a crash."""
    try:
        if interactive:
            return subprocess.run(list(argv), check=False).returncode
        return subprocess.run(
            list(argv),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
    except OSError:
        return 127


@dataclass(frozen=True)
class KeepaliveFailure:
    """The one refresh that failed, and how many succeeded before it."""

    argv: tuple[str, ...]
    returncode: int
    timestamp: str
    refreshes: int


class SudoKeepalive:
    """Validate once, then refresh on a timer until stopped. See the module."""

    def __init__(
        self,
        *,
        sudo: Sequence[str] = ("sudo",),
        interval: float = KEEPALIVE_INTERVAL,
        run: RunSudo | None = None,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        self.sudo = tuple(sudo)
        self.interval = interval
        self._runner = run
        self._warn = warn if warn is not None else (lambda _message: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._validated = False
        self._refreshes = 0
        self._failure: KeepaliveFailure | None = None

    @property
    def refreshes(self) -> int:
        """Refreshes that succeeded so far."""
        return self._refreshes

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _call(self, argv: Sequence[str], interactive: bool) -> int:
        # Looked up at call time, so the suite's guard on ``_run`` holds.
        return (self._runner or _run)(argv, interactive)

    def validate(self) -> bool:
        """``sudo -v`` on the operator's terminal: the one prompt of the run."""
        self._validated = self._call((*self.sudo, "-v"), True) == 0
        return self._validated

    def start(self) -> None:
        if not self._validated:
            raise RuntimeError("the sudo ticket was not validated; there is nothing to keep")
        if self._thread is not None:
            raise RuntimeError("the keepalive is already running")
        self._thread = threading.Thread(
            target=self._loop, name="hammunition-sudo-keepalive", daemon=True
        )
        self._thread.start()

    def _loop(self) -> None:
        argv = (*self.sudo, "-n", "-v")
        while not self._stop.wait(self.interval):
            returncode = self._call(argv, False)
            if returncode == 0:
                self._refreshes += 1
                continue
            self._failure = KeepaliveFailure(
                argv=argv,
                returncode=returncode,
                timestamp=datetime.now(UTC).isoformat(),
                refreshes=self._refreshes,
            )
            self._warn(
                f"`{' '.join(argv)}` exited {returncode}, so sudo's ticket is no longer "
                f"being kept valid (D-062). The next step that needs root may ask for "
                f"the password again, on this terminal."
            )
            return

    def stop(self) -> KeepaliveFailure | None:
        """End the refresh and wait for it. Returns the failure, if one ended it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        return self._failure

    def __enter__(self) -> SudoKeepalive:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()
