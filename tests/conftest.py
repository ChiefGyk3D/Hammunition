# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Suite-wide guarantees.

**No test reaches the network.** `hammunition.fetch` is the first code here that
can make an outbound connection, and a fetch test that quietly fell through to
the real internet would be slow, flaky, and — worse — would stop testing the
thing it names. So every socket to anywhere but loopback is blocked for the
whole suite: a test that tries gets a clear failure rather than a timeout, and
the network seam stays a seam because nothing can bypass it.

This is a property of the suite, not of any one test, which is why it is
enforced here rather than asserted in one place (CLAUDE.md: *prove properties,
not just behaviour*). Loopback stays open so a future test may bind a local
server if it needs one.

**No test asks the machine's package manager.** The same shape one layer down:
`apt-get --simulate` and `apt-cache policy` are unprivileged and answer at
plan time, so a test that mocks part of the apt backend and not all of it
runs the rest against whatever machine it is on. That is exactly what
happened when D-038 added the simulate step — the CLI dry-run test passed on
every dev box and GitHub runner, where a `git` package exists, and failed in
all four target containers, whose apt lists are empty. Blocking `apt-get`,
`apt-cache`, `apt`, `dpkg`, `dpkg-query` and `sudo` at the real runner makes
that a failure everywhere, naming the mock to add. Compilers, tar and the
rest stay open: the source-build tests run real builds on purpose.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from hammunition.backends.base import Command, CommandResult, SubprocessRunner

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_run = SubprocessRunner.run

MACHINE_QUERIES = frozenset({"apt-get", "apt-cache", "apt", "dpkg", "dpkg-query", "sudo"})


class MachineQueried(RuntimeError):
    """A test ran a package-manager or privileged command on the host."""


@pytest.fixture(autouse=True, scope="session")
def _no_machine_queries() -> Any:
    def guard(self: SubprocessRunner, command: Command) -> CommandResult:
        if command.argv and command.argv[0] in MACHINE_QUERIES:
            raise MachineQueried(
                f"the test suite blocked {command.argv[0]!r} ({command.description}). "
                f"Tests must not ask the machine's package manager: give the backend a "
                f"RecordingRunner, or monkeypatch every AptBackend method the code "
                f"under test reaches (lists_populated, probe and simulate at plan "
                f"time), so the result is the same in every target container."
            )
        return _real_run(self, command)

    SubprocessRunner.run = guard  # type: ignore[method-assign]
    try:
        yield
    finally:
        SubprocessRunner.run = _real_run  # type: ignore[method-assign]


def _loopback(address: Any) -> bool:
    """Whether *address* is loopback, for the address families that have one."""
    if not isinstance(address, tuple) or not address:
        # AF_UNIX and friends: a filesystem path, not the network.
        return True
    host = address[0]
    if not isinstance(host, str):
        return False
    return host in {"127.0.0.1", "::1", "localhost"} or host.startswith("127.")


class NetworkBlocked(RuntimeError):
    """A test tried to open a non-loopback connection."""


@pytest.fixture(autouse=True, scope="session")
def _no_network() -> Any:
    def guard(self: socket.socket, address: Any) -> Any:
        if not _loopback(address):
            raise NetworkBlocked(
                f"the test suite blocked a connection to {address!r}. Tests must not "
                f"reach the network: inject a fake Transport (hammunition.fetch) or "
                f"a RecordingRunner instead of letting a fetch fall through to the "
                f"real internet."
            )
        return _real_connect(self, address)

    def guard_ex(self: socket.socket, address: Any) -> Any:
        if not _loopback(address):
            raise NetworkBlocked(f"the test suite blocked a connection to {address!r}")
        return _real_connect_ex(self, address)

    socket.socket.connect = guard  # type: ignore[assignment,method-assign]
    socket.socket.connect_ex = guard_ex  # type: ignore[assignment,method-assign]
    try:
        yield
    finally:
        socket.socket.connect = _real_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = _real_connect_ex  # type: ignore[method-assign]
