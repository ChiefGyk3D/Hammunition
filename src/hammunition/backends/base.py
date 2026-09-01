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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "Action",
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

    cwd: Path | None = None
    """Where to run it. ``./configure`` has no meaning without one.

    The alternative is ``sh -c 'cd X && ./configure'``, which would put a shell
    back into a module whose first stated property is that ``shell=True`` is
    unrepresentable. A directory passed to :func:`subprocess.run` is not a
    shell, so this stays a plain argv.
    """

    stdin: str | None = None
    """Fed to the process on standard input. Its one use is
    ``debconf-set-selections``, which reads preseed answers from stdin — a plain
    argv with no file to leave behind. Never a secret; the plan prints that
    input is supplied but not its bytes."""

    def argv_for(self, *, euid: int, sudo: Sequence[str] = ("sudo",)) -> tuple[str, ...]:
        """The argv actually executed, with escalation applied if it is needed.

        Already being root is not the same as not needing root, so the flag
        stays true and only the prefix disappears.

        When escalation happens, ``env`` rides *inside* the sudo boundary as
        ``sudo env K=V argv...``. Merging it into the parent process's
        environment does not survive sudo: default sudoers has ``env_reset``
        and ``DEBIAN_FRONTEND`` is not in ``env_keep``, so apt would run
        without the one variable whose absence turns a debconf question into
        an invisible prompt behind ``capture_output`` -- the exact hang this
        module documents itself as preventing.
        """
        if self.requires_root and euid != 0:
            carried = tuple(f"{k}={v}" for k, v in sorted(self.env.items()))
            if carried:
                return (*sudo, "env", *carried, *self.argv)
            return (*sudo, *self.argv)
        return self.argv

    def display(self, *, euid: int = 0, sudo: Sequence[str] = ("sudo",)) -> str:
        """A copy-pasteable rendering of exactly what will run.

        ``cwd`` is rendered as a leading ``cd`` because a build command's
        meaning depends on where it runs: printing ``./configure`` without
        saying where would be an incomplete disclosure of a step that is about
        to modify a machine, and an operator reproducing the plan by hand would
        run it in the wrong place.
        """
        if self.requires_root and euid != 0:
            # Escalated: the env is already inside the argv, via `env`.
            rendered = shlex.join(self.argv_for(euid=euid, sudo=sudo))
        else:
            prefix = "".join(f"{k}={shlex.quote(v)} " for k, v in sorted(self.env.items()))
            rendered = prefix + shlex.join(self.argv_for(euid=euid, sudo=sudo))
        if self.stdin is not None:
            # Disclose that input is fed, and what it is at a glance (a single
            # short preseed line is shown; anything longer is summarised), but
            # keep the rendering a real pipe an operator could reproduce.
            one_line = self.stdin.strip()
            shown = one_line if "\n" not in one_line and len(one_line) <= 120 else "…preseed…"
            rendered = f"printf %s {shlex.quote(shown)} | {rendered}"
        if self.cwd is not None:
            return f"cd {shlex.quote(str(self.cwd))} && {rendered}"
        return rendered


@dataclass(frozen=True)
class Action:
    """Something the engine does *itself*, in process, rather than by exec.

    Two steps of a source build have no honest argv: verifying a download's
    digest, and unpacking an archive. Both could be shelled out — ``sha256sum``,
    ``tar -x`` — and both are safer done here, where the file handle and the
    extraction filter are ours and a redirect or a member named ``../..`` cannot
    be someone else's default. See :mod:`hammunition.fetch` and the source
    backend.

    Making them a peer of :class:`Command` rather than a separate mechanism is
    the point. A plan is a list of steps; the dry run prints them and the real
    run performs them, from the *same* objects. Describing an in-process step in
    prose in the plan and doing it in code at run time would be the second code
    path this module exists to avoid, and CLAUDE.md requires ``--dry-run`` to be
    complete and accurate rather than approximate.

    ``perform`` returns a one-line outcome for the transcript and the log, and
    raises :class:`BackendError` to fail the transaction exactly as a non-zero
    exit does.
    """

    kind: str
    """Machine-readable: ``fetch``, ``extract``. Recorded in the log."""

    description: str
    """Plain language, shown above the step. Says *why*."""

    detail: str
    """What it will do, concretely — a URL, a path. Shown in place of an argv."""

    perform: Callable[[], str]
    requires_root: bool = False

    def display(self, *, euid: int = 0, sudo: Sequence[str] = ("sudo",)) -> str:
        """Rendered for the plan. Bracketed so it cannot be mistaken for a
        shell command an operator could paste — it is not one, and printing it
        as though it were would be its own small lie."""
        del euid, sudo  # an in-process step is never escalated by prefixing
        return f"[{self.kind}] {self.detail}"


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
                cwd=command.cwd,
                input=command.stdin,
            )
        except FileNotFoundError as exc:
            raise BackendError(
                f"{argv[0]!r} is not on PATH, so {command.description.lower()} cannot "
                f"be attempted. This is a missing prerequisite, not a package that is "
                f"unavailable."
            ) from exc
        except NotADirectoryError as exc:
            raise BackendError(
                f"{command.cwd} is not a directory, so {command.description.lower()} "
                f"cannot be attempted"
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
