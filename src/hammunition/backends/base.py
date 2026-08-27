# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Commands, and the seam that lets them be executed or merely described.

``--dry-run`` must be complete and accurate rather than approximate
(CLAUDE.md, Security requirements). The only way to keep that true as the
engine grows is to make the dry run and the real run read the *same* objects:
a :class:`Command` is built once by a backend, and is then either printed or
handed to a runner. There is no second code path that reconstructs what would
have happened, because a second code path is a thing that drifts.

Three properties the types themselves carry:

* **argv, never a shell string.** ``shell=True`` is unrepresentable here. This
  is the same posture the manifest schema takes by having no ``method: script``
  — piping remote content into a shell is not merely discouraged, it cannot be
  expressed.
* **Privilege is declared per command.** CLAUDE.md drops to the user where
  possible and escalates only for apt and udev. ``requires_root`` says which is
  which, and :meth:`Command.argv_for` is the single place ``sudo`` is added, so
  a command cannot acquire privilege by accident.
* **What ran is what was shown.** :meth:`Command.display` renders the exact
  argv, escalation included, so the operator's transcript and the transaction
  log agree with the process table.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "BackendError",
    "Command",
    "CommandResult",
    "CommandRunner",
    "RecordingRunner",
    "SubprocessRunner",
]


class BackendError(Exception):
    """A backend could not do its job. Always fatal — D-016 forbids continuing."""


@dataclass(frozen=True)
class Command:
    """One process to run, described in the operator's terms."""

    argv: tuple[str, ...]
    description: str
    """Plain language, shown above the command. Says *why*, not what."""

    requires_root: bool = False
    env: Mapping[str, str] = field(default_factory=dict)
    """Extra environment. ``DEBIAN_FRONTEND=noninteractive`` and nothing secret."""

    def argv_for(self, *, euid: int, sudo: Sequence[str] = ("sudo",)) -> tuple[str, ...]:
        """The argv actually executed, with escalation applied if it is needed.

        Already being root is not the same as not needing root, so the flag
        stays true and only the prefix disappears.
        """
        if self.requires_root and euid != 0:
            return (*sudo, *self.argv)
        return self.argv

    def display(self, *, euid: int = 0, sudo: Sequence[str] = ("sudo",)) -> str:
        """A copy-pasteable rendering of exactly what will run."""
        prefix = "".join(f"{k}={shlex.quote(v)} " for k, v in sorted(self.env.items()))
        return prefix + shlex.join(self.argv_for(euid=euid, sudo=sudo))


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@runtime_checkable
class CommandRunner(Protocol):
    """Executes a :class:`Command`, or pretends to.

    Every path that touches the system goes through this, which is what lets
    the test suite assert what *would* have been run without a container and
    without root.
    """

    def run(self, command: Command) -> CommandResult: ...


class SubprocessRunner:
    """The real one. ``shell=False`` always; there is no option to change it."""

    def __init__(self, *, euid: int | None = None, sudo: Sequence[str] = ("sudo",)) -> None:
        self.euid = os.geteuid() if euid is None else euid
        self.sudo = tuple(sudo)

    def run(self, command: Command) -> CommandResult:
        argv = command.argv_for(euid=self.euid, sudo=self.sudo)
        env = {**os.environ, **command.env}
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        except FileNotFoundError as exc:
            raise BackendError(
                f"{argv[0]!r} is not on PATH, so {command.description.lower()} cannot "
                f"be attempted. This is a missing prerequisite, not a package that is "
                f"unavailable."
            ) from exc
        except PermissionError as exc:
            raise BackendError(f"not permitted to execute {argv[0]!r}: {exc}") from exc
        return CommandResult(
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class RecordingRunner:
    """Records commands and replays canned output. For tests and for ``--dry-run``.

    Unscripted commands return an empty success by default. That is right for a
    dry run — nothing should be *executing* — and tests that care assert on
    :attr:`commands` rather than on what came back.
    """

    def __init__(self, responses: Mapping[str, CommandResult] | None = None) -> None:
        self.commands: list[Command] = []
        self.responses = dict(responses or {})

    def run(self, command: Command) -> CommandResult:
        self.commands.append(command)
        key = shlex.join(command.argv)
        if key in self.responses:
            return self.responses[key]
        return CommandResult(argv=command.argv, returncode=0, stdout="", stderr="")
