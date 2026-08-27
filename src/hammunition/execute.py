# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turning a plan into commands, and running them.

``--dry-run`` must be complete and accurate rather than approximate, so the dry
run and the real run call :func:`commands_for` and get the *same list*. The dry
run prints it; the real run hands it to a runner. There is no code path that
reconstructs what would have happened, because a reconstruction is a thing that
drifts from the original and nobody notices until it matters.

Execution stops at the first failure. D-016: an unresolvable dependency is a
hard error that stops the run, never a warning the run continues past. The
transaction log records what completed, which is what ``uninstall`` reads —
D-004 promises a log and honest reporting, never rollback.
"""

from __future__ import annotations

import contextlib
import grp
import pwd
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from hammunition.backends import AptBackend, Command, CommandRunner
from hammunition.plan import InstallPlan
from hammunition.state import TransactionLog

__all__ = ["ExecutionReport", "commands_for", "execute", "user_groups"]


def user_groups(user: str) -> frozenset[str]:
    """Every group *user* belongs to, primary included.

    Read from the system's group database rather than by shelling out, so it
    works identically in a container with no ``id`` binary. An unknown user is
    not an error here: it means "belongs to nothing we know of", and the caller
    is about to add them to something anyway.
    """
    names: set[str] = set()
    try:
        entry = pwd.getpwnam(user)
    except KeyError:
        return frozenset()
    with contextlib.suppress(KeyError):
        names.add(grp.getgrgid(entry.pw_gid).gr_name)
    names.update(group.gr_name for group in grp.getgrall() if user in group.gr_mem)
    return frozenset(names)


def commands_for(
    plan: InstallPlan,
    apt: AptBackend,
    *,
    refresh: bool = False,
    current_groups: frozenset[str] | None = None,
) -> list[Command]:
    """Every command this plan implies, in the order it will run.

    Group membership comes after installation on purpose: several of these
    groups are created by the package being installed (Debian's
    ``wireshark-common`` creates ``wireshark``), so adding the operator first
    would fail on a group that does not exist yet.
    """
    commands: list[Command] = []
    if refresh:
        commands.append(apt.refresh_command())
    commands.extend(apt.install_commands(plan.apt_to_install))

    cache: dict[str, frozenset[str]] = {}
    for membership in plan.group_memberships:
        if current_groups is not None:
            groups = current_groups
        else:
            groups = cache.setdefault(membership.user, user_groups(membership.user))
        if membership.group in groups:
            # Idempotent: every operation is safe to re-run (CLAUDE.md).
            continue
        commands.append(
            Command(
                argv=("gpasswd", "--add", membership.user, membership.group),
                description=(
                    f"Add {membership.user} to the {membership.group!r} group "
                    f"for {membership.package}"
                ),
                requires_root=True,
            )
        )
    return commands


@dataclass(frozen=True)
class ExecutionReport:
    """What actually happened. Partial success is reported explicitly (D-016)."""

    completed: tuple[Command, ...]
    failed: Command | None
    stderr: str

    @property
    def ok(self) -> bool:
        return self.failed is None


def execute(
    commands: Sequence[Command],
    runner: CommandRunner,
    *,
    log: TransactionLog,
    plan: InstallPlan,
    echo: Callable[[str], None] | None = None,
) -> ExecutionReport:
    """Run every command, stopping at the first failure.

    Each command is logged *before* it runs and its outcome logged after. That
    ordering matters: a run killed mid-``apt-get`` leaves a record that the
    command was started, which is exactly the state an operator needs to see
    and the state a log written only on success would hide.
    """
    write = echo if echo is not None else (lambda _line: None)

    log.append(
        {
            "event": "transaction_begin",
            "version": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "target": plan.target.to_log_entry(),
            "packages": [p.name for p in plan.packages],
            "apt_packages": list(plan.apt_to_install),
        }
    )

    completed: list[Command] = []
    for command in commands:
        write(f"  $ {command.display()}")
        log.append(
            {
                "event": "command_begin",
                "version": 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "argv": list(command.argv),
                "requires_root": command.requires_root,
                "description": command.description,
            }
        )
        result = runner.run(command)
        log.append(
            {
                "event": "command_end",
                "version": 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "argv": list(command.argv),
                "returncode": result.returncode,
            }
        )
        if not result.ok:
            log.append(
                {
                    "event": "transaction_failed",
                    "version": 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "argv": list(command.argv),
                    "returncode": result.returncode,
                    "completed": len(completed),
                }
            )
            return ExecutionReport(completed=tuple(completed), failed=command, stderr=result.stderr)
        completed.append(command)

    log.append(
        {
            "event": "transaction_end",
            "version": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "completed": len(completed),
        }
    )
    return ExecutionReport(completed=tuple(completed), failed=None, stderr="")
