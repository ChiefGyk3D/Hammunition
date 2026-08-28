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
import os
import pwd
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from hammunition.backends import (
    AptBackend,
    AptPackageState,
    BackendError,
    Command,
    CommandRunner,
)
from hammunition.plan import InstallPlan
from hammunition.state import TransactionLog

__all__ = [
    "EffectCheck",
    "ExecutionReport",
    "PackageProber",
    "Verification",
    "commands_for",
    "execute",
    "user_groups",
    "verify_effects",
]


class PackageProber(Protocol):
    """Anything that can answer what apt knows about a set of packages *now*.

    :class:`~hammunition.backends.AptBackend` satisfies this structurally. The
    protocol exists so :func:`verify_effects` can be tested against a fake that
    returns a chosen state, rather than only against a live apt.
    """

    def probe(self, packages: Sequence[str]) -> dict[str, AptPackageState]: ...


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
class EffectCheck:
    """One thing a command claimed to do, re-probed after it exited 0.

    D-031: a tool reporting success is not evidence it did anything. ``apt-get``
    can exit 0 having installed nothing a held or broken package silently
    denied; ``gpasswd`` exits 0 whether or not the membership took. So the
    effect is read back from the same source resolution used pre-flight —
    ``apt-cache policy`` for a package, the group database for a membership —
    and the answer, not the exit status, is what the log records.
    """

    kind: str
    """``"package"`` or ``"group"``."""

    subject: str
    """The package name, or ``"user:group"``."""

    confirmed: bool
    detail: str
    """What was found, phrased for the log and the operator alike."""

    def to_log_entry(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "confirmed": self.confirmed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Verification:
    """The post-run effect check across every package and membership."""

    checks: tuple[EffectCheck, ...]

    @property
    def confirmed(self) -> tuple[EffectCheck, ...]:
        return tuple(c for c in self.checks if c.confirmed)

    @property
    def discrepancies(self) -> tuple[EffectCheck, ...]:
        """Commands that exited 0 without producing the effect they claimed."""
        return tuple(c for c in self.checks if not c.confirmed)

    @property
    def ok(self) -> bool:
        return not self.discrepancies


def verify_effects(
    plan: InstallPlan,
    prober: PackageProber | None,
    *,
    group_lookup: Callable[[str], frozenset[str]] = user_groups,
) -> Verification:
    """Read back whether the transaction's stated effects actually hold.

    Called only on the success path — after every command exited 0 — because
    that is precisely where D-031 bites: nothing else in the run would notice a
    command that succeeded and did nothing. The end state is checked, not the
    delta, so a membership the run skipped as already-present is confirmed too;
    the question is "is the machine as the plan promised", not "did each command
    move it".

    The package half needs ``prober``; without one, only group memberships are
    checked. Packages are then simply absent from ``checks`` rather than
    reported as failures — an unasked question, not a failed one.
    """
    checks: list[EffectCheck] = []

    wanted = plan.apt_to_install
    if wanted and prober is not None:
        states = prober.probe(wanted)
        for name in wanted:
            state = states.get(name)
            installed = state is not None and state.is_installed
            checks.append(
                EffectCheck(
                    kind="package",
                    subject=name,
                    confirmed=installed,
                    detail=(
                        f"installed {state.installed}"
                        if installed and state is not None
                        else "apt-get exited 0 but apt reports the package not installed"
                    ),
                )
            )

    groups_now = {m.user: group_lookup(m.user) for m in plan.group_memberships}
    for membership in plan.group_memberships:
        present = membership.group in groups_now.get(membership.user, frozenset())
        checks.append(
            EffectCheck(
                kind="group",
                subject=f"{membership.user}:{membership.group}",
                confirmed=present,
                detail=(
                    "membership present in the group database"
                    if present
                    else "gpasswd exited 0 but the membership is absent from the group database"
                ),
            )
        )

    return Verification(checks=tuple(checks))


@dataclass(frozen=True)
class ExecutionReport:
    """What actually happened. Partial success is reported explicitly (D-016)."""

    completed: tuple[Command, ...]
    failed: Command | None
    stderr: str
    verification: Verification | None = None
    """The post-run effect check, when one was performed (D-031). ``None`` when
    the run failed before completion, or when no prober was supplied."""

    @property
    def ok(self) -> bool:
        return self.failed is None

    @property
    def verified(self) -> bool:
        """Whether every claimed effect was confirmed. A run with no
        verification is *not* verified — the caller must not read a missing
        check as a passing one."""
        return self.verification is not None and self.verification.ok


def execute(
    commands: Sequence[Command],
    runner: CommandRunner,
    *,
    log: TransactionLog,
    plan: InstallPlan,
    echo: Callable[[str], None] | None = None,
    euid: int | None = None,
    prober: PackageProber | None = None,
    group_lookup: Callable[[str], frozenset[str]] = user_groups,
) -> ExecutionReport:
    """Run every command, stopping at the first failure.

    Each command is logged *before* it runs and its outcome logged after. That
    ordering matters: a run killed mid-``apt-get`` leaves a record that the
    command was started, which is exactly the state an operator needs to see
    and the state a log written only on success would hide.

    ``euid`` is whose the run is, so the echoed line matches the process
    table -- an unprivileged run says ``sudo apt-get ...``, not ``apt-get
    ...``. Defaults to the real euid.

    ``prober`` re-reads apt after the run to confirm the packages actually
    landed (D-031). When supplied, the effect check runs on the success path
    and its result is recorded in ``transaction_end`` — the record ``uninstall``
    will trust, which must not say "installed" on the strength of an exit code
    alone. Group memberships are always re-read from ``group_lookup``; the
    package half needs the prober, so omitting it verifies groups only.
    """
    write = echo if echo is not None else (lambda _line: None)
    shown_as = os.geteuid() if euid is None else euid

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
        write(f"  $ {command.display(euid=shown_as)}")
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
        try:
            result = runner.run(command)
        except BackendError as exc:
            # A missing binary (no sudo in a minimal container, no gpasswd) is
            # a failure of this transaction, not a crash of the engine: it gets
            # the same transaction_failed record and the same exit-code
            # contract as a command that ran and returned non-zero. Letting it
            # escape as a traceback left the log saying command_begin with no
            # ending, which is the log lying by omission.
            log.append(
                {
                    "event": "transaction_failed",
                    "version": 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "argv": list(command.argv),
                    "error": str(exc),
                    "completed": len(completed),
                }
            )
            return ExecutionReport(completed=tuple(completed), failed=command, stderr=str(exc))
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

    # Every command exited 0. D-031: that is not yet evidence the machine
    # changed. Re-read the effects from the same sources resolution used, and
    # let the confirmed state -- not the exit code -- be what the log records.
    verification: Verification | None = None
    if prober is not None or plan.group_memberships:
        try:
            verification = verify_effects(plan, prober, group_lookup=group_lookup)
        except BackendError as exc:
            # The re-probe itself failed -- apt worked for the install a moment
            # ago and does not now. That is not "the package is missing"; it is
            # "we could not confirm", and the honest record is unverified, not a
            # claim either way. Fail toward flagging it.
            verification = Verification(
                checks=(
                    EffectCheck(
                        kind="verification",
                        subject="apt-cache policy",
                        confirmed=False,
                        detail=f"the post-run effect check could not run: {exc}",
                    ),
                )
            )

    end_entry: dict[str, object] = {
        "event": "transaction_end",
        "version": 2,
        "timestamp": datetime.now(UTC).isoformat(),
        "completed": len(completed),
    }
    if verification is not None:
        end_entry["verified"] = verification.ok
        end_entry["checks"] = [c.to_log_entry() for c in verification.checks]
    log.append(end_entry)
    return ExecutionReport(
        completed=tuple(completed), failed=None, stderr="", verification=verification
    )
