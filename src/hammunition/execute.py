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
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Protocol

from hammunition.backends import (
    Action,
    AptBackend,
    AptPackageState,
    AptRepoBackend,
    BackendError,
    BinaryBackend,
    Command,
    CommandRunner,
    GitBackend,
    NodeBackend,
    SourceBackend,
    VenvBackend,
)
from hammunition.distro import Target
from hammunition.launchers import launcher_steps
from hammunition.manifest.schema import (
    BinaryInstall,
    GitInstall,
    InstallBlock,
    NodeInstall,
    SourceInstall,
    VenvInstall,
)
from hammunition.plan import InstallPlan
from hammunition.state import RemovalPlan, TransactionLog

#: One entry in a plan: a process to run, or something the engine does itself.
#: `--dry-run` prints these and a real run performs them, from the same objects.
Step = Command | Action

__all__ = [
    "EffectCheck",
    "ExecutionReport",
    "PackageProber",
    "Step",
    "Verification",
    "commands_for",
    "execute",
    "run_removal",
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


def _declares_installed_binaries(block: InstallBlock) -> bool:
    """Whether a block's `binaries` name files the run puts at ``<prefix>/bin``.

    True of source and git builds, and of binary units other than a ``.deb``
    (whose contents apt places; its ``deb_package`` is what apt is asked
    about instead, in ``verify_effects``). A venv's entry points
    are wrappers in the operator's ``~/.local/bin`` and are not `binaries`.
    """
    method = block.install
    if isinstance(method, SourceInstall | GitInstall):
        return True
    return isinstance(method, BinaryInstall) and method.format != "deb"


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


def write_config(path: Path, body: str, mode: int, *, append: bool, backup: bool) -> str:
    """Write one templated configuration file. Returns a one-line outcome.

    Backing up first is the default and matters: these paths belong to the
    distribution's packages as often as to us, and overwriting an operator's
    hand-tuned `/etc/ax25/axports` without a copy would be the kind of damage
    no transaction log can undo.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = ""
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + ".hammunition-backup")
        if not backup_path.exists():
            shutil.copy2(path, backup_path)
            saved = f", previous contents saved to {backup_path.name}"
        else:
            saved = f", {backup_path.name} already exists and was left alone"
    if append and path.exists():
        with path.open("a") as handle:
            handle.write(body if body.endswith("\n") else body + "\n")
        action = "appended to"
    else:
        path.write_text(body if body.endswith("\n") else body + "\n")
        action = "wrote"
    os.chmod(path, mode)
    return f"{action} {path} (mode {mode:04o}){saved}"


def stage_config(staging: Path, target: Path, body: str, *, append: bool) -> str:
    """Render the *final* contents of a root-owned config into a staging file.

    The staged file is complete — for an append, the target's current contents
    plus the new block — so the privileged step is a plain ``install`` of a
    finished file, never a shell redirect or an in-place edit run as root.
    """
    if append and target.exists():
        try:
            existing = target.read_text()
        except OSError as exc:
            raise BackendError(
                f"{target} must be read to append to it, and that failed: "
                f"{exc.strerror}. Nothing was staged."
            ) from exc
        body = existing + ("" if existing.endswith("\n") else "\n") + body
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_text(body if body.endswith("\n") else body + "\n")
    os.chmod(staging, 0o600)
    return f"staged {target} contents at {staging}"


def config_steps(plan: InstallPlan, *, staging_root: Path | None = None) -> list[Step]:
    """The steps that write each config file the plan resolved. Never a partial file.

    `plan.config_files` holds only what could be fully rendered — a file
    missing a station value is a Deferral and never reaches here, because a
    config written with `{station.callsign}` still in it looks configured and
    is not.

    A path the operator can write gets one in-process Action, as before. A
    root-owned path (``/etc/bpq32.cfg``) cannot be written in-process by an
    unprivileged engine — the first Parrot VM run proved it with a
    ``PermissionError`` — so it becomes commands the runner can elevate: stage
    the finished contents unprivileged, ``cp -a`` the existing file to its
    backup (only when one exists and no backup does, decided at plan time,
    matching what the in-process path has always done), then
    ``install -m MODE`` the staged file into place. Every step is printed by
    ``--dry-run`` exactly as it will run.
    """
    steps: list[Step] = []
    staging_dir = (staging_root or Path(tempfile.gettempdir())) / "config-staging"
    for package, config, body in plan.config_files:
        path = Path(config.path)
        mode = int(config.mode, 8)
        verb = "Append" if config.append else "Write"
        # Writability of the nearest ancestor that exists, because that is the
        # directory mkdir -p would actually have to write into. Probing "/"
        # when the parent is merely not-yet-created classified a writable
        # tmp-dir target as root-only and routed it through sudo for nothing.
        probe = path.parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        needs_root = not os.access(probe, os.W_OK)
        if not needs_root:
            steps.append(
                Action(
                    kind="config",
                    description=f"{verb} {config.path} for {package}",
                    detail=(
                        f"mode {config.mode}, "
                        + ("existing file backed up" if config.backup_existing else "no backup")
                    ),
                    perform=partial(
                        write_config,
                        path,
                        body,
                        mode,
                        append=config.append,
                        backup=config.backup_existing,
                    ),
                )
            )
            continue

        staging = staging_dir / f"{package}{path.name and '-' + path.name}"
        steps.append(
            Action(
                kind="config",
                description=f"Render {config.path} for {package} into a staging file",
                detail=f"staged at {staging}, mode 0600; installed by the next command",
                perform=partial(stage_config, staging, path, body, append=config.append),
            )
        )
        backup_path = path.with_suffix(path.suffix + ".hammunition-backup")
        if config.backup_existing and path.exists() and not backup_path.exists():
            steps.append(
                Command(
                    argv=("cp", "-a", str(path), str(backup_path)),
                    description=f"Back up the existing {config.path} first",
                    requires_root=True,
                )
            )
        steps.append(
            Command(
                argv=("install", "-m", config.mode, str(staging), str(path)),
                description=f"{verb} {config.path} for {package} (mode {config.mode})",
                requires_root=True,
            )
        )
    return steps


def commands_for(
    plan: InstallPlan,
    apt: AptBackend,
    *,
    refresh: bool = False,
    current_groups: frozenset[str] | None = None,
    source: SourceBackend | None = None,
    git: GitBackend | None = None,
    binary: BinaryBackend | None = None,
    venv: VenvBackend | None = None,
    node: NodeBackend | None = None,
    repos: AptRepoBackend | None = None,
    config_staging: Path | None = None,
    launcher_bin: Path | None = None,
    launcher_applications: Path | None = None,
) -> list[Step]:
    """Every step this plan implies, in the order it will run.

    The order is not cosmetic. Every download runs first, before anything
    that changes the machine: a fetch is verified against the manifest's
    sha256 (D-018), so a wrong hash or a dead URL refuses on an untouched
    system rather than after apt has installed a toolchain for a build that
    will never start; and a vendor .deb, which apt can only resolve from
    its file, is simulated against the apt step once fetched and before
    either runs -- the half of the "plan passed, machine touched, then it
    failed" shape that D-038's plan-time simulate could not reach
    (`docs/reference/vm-campaign-ubuntu.md`, 2026-09-02). apt runs next
    because a source build needs its
    ``build_depends`` — its compiler, its headers — present before ``./configure``
    can succeed. Group membership comes last because several of these groups are
    created by the package being installed (Debian's ``wireshark-common`` creates
    ``wireshark``), so adding the operator first would fail on a group that does
    not exist yet.

    ``source`` and ``git`` are required if the plan holds a build of that kind,
    and an absence is an error rather than a silent skip — a plan that quietly dropped the one
    step that installs the software would report success having done nothing.
    """
    # Each backend's steps in build order; the fetches are lifted out below.
    builds: list[Step] = []
    for planned in plan.packages:
        block = planned.block.install
        if isinstance(block, SourceInstall):
            if source is None:
                raise BackendError(
                    f"{planned.name} is a source build and no source backend was supplied. "
                    f"Skipping it would report a successful run that installed nothing."
                )
            builds.extend(source.steps(planned.manifest, block))
        elif isinstance(block, GitInstall):
            if git is None:
                raise BackendError(
                    f"{planned.name} builds from git and no git backend was supplied. "
                    f"Skipping it would report a successful run that installed nothing."
                )
            builds.extend(git.steps(planned.manifest, block))
        elif isinstance(block, BinaryInstall):
            if binary is None:
                raise BackendError(
                    f"{planned.name} installs a prebuilt artifact and no binary backend "
                    f"was supplied. Skipping it would report a successful run that "
                    f"installed nothing."
                )
            builds.extend(binary.steps(planned.manifest, block))
        elif isinstance(block, VenvInstall):
            if venv is None:
                raise BackendError(
                    f"{planned.name} installs into a virtualenv and no venv backend "
                    f"was supplied. Skipping it would report a successful run that "
                    f"installed nothing."
                )
            builds.extend(venv.steps(planned.manifest, block))
        elif isinstance(block, NodeInstall):
            if node is None:
                raise BackendError(
                    f"{planned.name} is a Node.js application and no node backend "
                    f"was supplied. Skipping it would report a successful run that "
                    f"installed nothing."
                )
            builds.extend(node.steps(planned.manifest, block))

    # A `fetch` is an in-process download into the cache, verified before it
    # is kept; it needs nothing apt installs and touches nothing outside the
    # cache, so every one of them can go first. A git clone is a Command
    # that needs git from apt and stays where its backend put it.
    commands: list[Step] = [
        step for step in builds if isinstance(step, Action) and step.kind == "fetch"
    ]
    builds = [step for step in builds if not (isinstance(step, Action) and step.kind == "fetch")]

    # D-040: a repository's key is a fetch like any other and joins the
    # others at the front -- a key whose fingerprint is not the pinned one
    # refuses before anything is installed. The two files land next, then
    # apt-get update is forced, because a source apt has not read is a
    # source apt does not have.
    if plan.apt_repos and repos is None:
        raise BackendError(
            f"the plan adds the {', '.join(a.repo.name for a in plan.apt_repos)} "
            f"repositor{'y' if len(plan.apt_repos) == 1 else 'ies'} and no repository "
            f"backend was supplied. Skipping it would leave apt unable to install what "
            f"the plan promised."
        )
    if repos is not None:
        repo_steps: list[Step] = []
        for addition in plan.apt_repos:
            repo_steps.extend(repos.steps(addition.repo, unit=addition.unit))
        commands.extend(s for s in repo_steps if isinstance(s, Action) and s.kind == "fetch")
        commands.extend(s for s in repo_steps if not (isinstance(s, Action) and s.kind == "fetch"))

    if refresh or plan.apt_repos:
        commands.append(apt.refresh_command())

    # A vendor .deb is resolved by apt from its file, and the file does not
    # exist until its fetch has run -- so the plan's own simulate (D-038)
    # could not include it. This one can: it runs after every fetch and
    # before the apt step, over the apt packages and the downloaded .debs
    # together, and a refusal here is a refusal on an untouched machine.
    # `apt-get install ./file.deb` is what the binary backend runs later;
    # asking the same resolver the same question first is the whole idea.
    debs = [
        str(binary.fetcher.path_for(planned.block.install.artifact))
        for planned in plan.packages
        if binary is not None
        and isinstance(planned.block.install, BinaryInstall)
        and planned.block.install.format == "deb"
    ]
    # The same question again for a just-added repository: the plan-time
    # simulate left its packages out because apt had no index for them.
    # After the update, the resolver is asked about the whole apt step.
    if debs or plan.apt_repos:
        if debs and plan.apt_repos:
            why = (
                f"Ask apt whether the {len(debs)} downloaded .deb file(s) and the packages "
                f"from the added repositor{'y' if len(plan.apt_repos) == 1 else 'ies'} "
                f"resolve together with the apt step, before anything is installed"
            )
        elif debs:
            why = (
                f"Ask apt whether the {len(debs)} downloaded .deb file(s) resolve "
                f"together with the apt step, before anything is installed"
            )
        else:
            supplied = sorted(plan.repo_supplied)
            why = (
                f"Ask apt whether {', '.join(supplied)} resolve{'s' if len(supplied) == 1 else ''} "
                f"from the added repositor{'y' if len(plan.apt_repos) == 1 else 'ies'} together "
                f"with the apt step, before anything is installed"
            )
        commands.append(
            apt.simulate_command(
                (*plan.apt_to_install, *debs), release=plan.apt_release, description=why
            )
        )

    if plan.debconf_selections and plan.apt_to_install:
        # Before the apt install, never after: a package's postinst reads its
        # preseeded answers as it configures, so wireshark-common creates the
        # wireshark group and grants dumpcap its capabilities in one pass. Fed
        # on stdin — a plain argv with no file left on the machine.
        commands.append(
            Command(
                argv=("debconf-set-selections",),
                description="Preseed debconf answers so non-interactive installs pick the right defaults",
                requires_root=True,
                stdin="\n".join(plan.debconf_selections) + "\n",
            )
        )
    commands.extend(apt.install_commands(plan.apt_to_install, release=plan.apt_release))

    if plan.reconfigure_after and plan.apt_to_install:
        # After the whole apt transaction is settled, so a postinst action that
        # needs another just-installed package (wireshark-common's setcap needs
        # libcap2-bin) re-runs with everything present. Non-interactive: the
        # answer is already in the debconf DB from the preseed above.
        for pkg in plan.reconfigure_after:
            commands.append(
                Command(
                    argv=("dpkg-reconfigure", pkg),
                    description=f"Re-run {pkg}'s configuration now the whole transaction is present",
                    requires_root=True,
                    env={"DEBIAN_FRONTEND": "noninteractive"},
                )
            )

    commands.extend(builds)

    # Configuration is written after the software that reads it exists, so a
    # package's own postinst cannot overwrite what we put down, and before
    # group membership for the same reason the comment above gives.
    commands.extend(config_steps(plan, staging_root=config_staging))

    # Launchers after the software and its configuration exist. Generated
    # only when the caller supplies the per-user directories -- a caller that
    # does not (older tests, bare planning) gets plans identical to before.
    if launcher_bin is not None and launcher_applications is not None:
        for planned in plan.packages:
            commands.extend(
                launcher_steps(
                    planned.manifest,
                    bin_dir=launcher_bin,
                    applications_dir=launcher_applications,
                    venv_dir=(
                        venv.venv_root / planned.name
                        if venv is not None and isinstance(planned.block.install, VenvInstall)
                        else None
                    ),
                    node_wrapper=(
                        node.wrapper_for(planned.manifest, planned.block.install)
                        if node is not None and isinstance(planned.block.install, NodeInstall)
                        else None
                    ),
                )
            )

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
    prefix: Path | None = None,
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
    reported as failures — an unasked question, not a failed one. Likewise the
    built half needs ``prefix``: every source, git and non-deb binary unit that
    declares ``binaries`` is checked for an executable at
    ``<prefix>/bin/<install_as>``. Added the night js8call was found "confirmed"
    on four targets with nothing installed: its ``cmake --install`` has no
    rule for the executable, exits 0, and writes an empty install manifest.
    """
    checks: list[EffectCheck] = []

    if prefix is not None:
        for planned in plan.packages:
            if not _declares_installed_binaries(planned.block):
                continue
            for binary in planned.manifest.binaries:
                path = prefix / "bin" / binary.install_as
                present = path.is_file() and os.access(path, os.X_OK)
                checks.append(
                    EffectCheck(
                        kind="binary",
                        subject=f"{planned.name}:{binary.install_as}",
                        confirmed=present,
                        detail=(
                            f"executable at {path}"
                            if present
                            else (
                                f"the install step exited 0 but there is no executable at "
                                f"{path} -- the build has no install rule for it, or installs "
                                f"it under another name"
                            )
                        ),
                    )
                )

    # A vendor .deb's package is not in apt_to_install -- apt installed it
    # from a file, not from the archive -- and the binaries check above
    # skips deb formats because apt placed the contents. Until 2026-09-03
    # nobody then asked apt about it, and wsjtx-improved on Debian 13 ended
    # `verified: true` with `checks: []`. Its deb_package is the effect.
    deb_packages = tuple(
        sorted(
            {
                planned.block.install.deb_package
                for planned in plan.packages
                if isinstance(planned.block.install, BinaryInstall)
                and planned.block.install.format == "deb"
                and planned.block.install.deb_package is not None
            }
        )
    )
    wanted = tuple(sorted({*plan.apt_to_install, *deb_packages}))
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

    completed: tuple[Step, ...]
    failed: Step | None
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
    commands: Sequence[Step],
    runner: CommandRunner,
    *,
    log: TransactionLog,
    plan: InstallPlan,
    echo: Callable[[str], None] | None = None,
    euid: int | None = None,
    prober: PackageProber | None = None,
    group_lookup: Callable[[str], frozenset[str]] = user_groups,
    prefix: Path | None = None,
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
    package half needs the prober, so omitting it verifies groups only, and
    the built half needs ``prefix`` -- the install prefix whose ``bin`` every
    declared binary must be found under.
    """
    write = echo if echo is not None else (lambda _line: None)
    shown_as = os.geteuid() if euid is None else euid

    log.append(
        {
            "event": "transaction_begin",
            # Version 2 adds `deferred` (Q-017 / D-039): what the plan chose
            # NOT to do, so a `status` read later knows the run installed
            # eighteen of a profile's twenty-two on purpose, not by accident.
            "version": 2,
            "timestamp": datetime.now(UTC).isoformat(),
            "target": plan.target.to_log_entry(),
            "packages": [p.name for p in plan.packages],
            "apt_packages": list(plan.apt_to_install),
            "deferred": [d.to_log_entry() for d in plan.deferrals],
        }
    )

    completed: list[Step] = []
    for command in commands:
        write(f"  $ {command.display(euid=shown_as)}")

        if isinstance(command, Action):
            # An in-process step: same logging shape, same failure contract. It
            # is logged before it runs for the same reason a command is -- a run
            # killed mid-extraction must leave a record that extraction started.
            log.append(
                {
                    "event": "action_begin",
                    "version": 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "kind": command.kind,
                    "detail": command.detail,
                    "description": command.description,
                }
            )
            try:
                outcome = command.perform()
            except (BackendError, OSError) as exc:
                log.append(
                    {
                        "event": "transaction_failed",
                        "version": 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "kind": command.kind,
                        "detail": command.detail,
                        "error": str(exc),
                        "completed": len(completed),
                    }
                )
                return ExecutionReport(completed=tuple(completed), failed=command, stderr=str(exc))
            log.append(
                {
                    "event": "action_end",
                    "version": 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "kind": command.kind,
                    # Uninstall's file-attribution replay reads install-binary
                    # details back as destinations; an Action has no argv.
                    "detail": command.detail,
                    "outcome": outcome,
                }
            )
            if outcome:
                write(f"    {outcome}")
            completed.append(command)
            continue

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
    if prober is not None or plan.group_memberships or prefix is not None:
        try:
            verification = verify_effects(plan, prober, group_lookup=group_lookup, prefix=prefix)
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


#: What proves a file in the operator's home is the engine's own work:
#: the launcher wrapper's generated-by line, a desktop entry's package key,
#: or a venv wrapper's exec into the engine's own venv tree. A same-named
#: file carrying none of these predates us (or is the operator's), and the
#: removal step reports it and leaves it.
OURS_MARKERS = ("generated by hammunition", "X-Hammunition-Package=", "/hammunition/venvs/")


def _remove_if_ours(path: Path) -> str:
    """Unlink a wrapper or desktop entry only after reading our marker back."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return f"already absent: {path}"
    except (OSError, UnicodeDecodeError):
        return f"left in place: {path} is not readable as a generated file — not ours"
    if not any(marker in content for marker in OURS_MARKERS):
        return f"left in place: {path} carries no hammunition marker — not ours"
    path.unlink()
    return f"removed {path}"


def _remove_venv(path: Path) -> str:
    """Remove a per-user venv tree or its staged requirements file.

    Both are namespaced (``venvs/<unit>`` and ``venvs/<unit>.requirements.txt``).
    """
    if not path.exists():
        return f"already absent: {path}"
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return f"removed {path}"


def artifact_removal_steps(plan: RemovalPlan) -> list[Action | Command]:
    """The non-apt half of an uninstall, from the plan's artifact list.

    Trees and prefix binaries are root ``rm`` commands — the same argv shapes
    the attribution replay un-attributes, so removal and attribution stay one
    vocabulary. Venvs, wrappers and desktop entries are in-process actions:
    the venv path is namespaced, and the marker-based ones read the file back
    before unlinking, which a ``rm`` argv cannot express.
    """
    steps: list[Action | Command] = []
    for unit, removals in plan.artifacts.items():
        for removal in removals:
            if removal.kind in ("tree",):
                steps.append(
                    Command(
                        argv=("rm", "-rf", "--", str(removal.path)),
                        description=f"Remove {unit}'s installed tree ({removal.basis})",
                        requires_root=removal.requires_root,
                    )
                )
            elif removal.kind == "binary":
                steps.append(
                    Command(
                        argv=("rm", "-f", "--", str(removal.path)),
                        description=f"Remove {unit}'s installed binary ({removal.basis})",
                        requires_root=removal.requires_root,
                    )
                )
            elif removal.kind == "apt-repo":
                # D-040: the source file and the keyring the install wrote,
                # attributed from its own `install -D -m 0644` commands. The
                # caller runs apt-get update afterwards, so apt forgets the
                # repository in the same transaction that removes its files.
                steps.append(
                    Command(
                        argv=("rm", "-f", "--", str(removal.path)),
                        description=f"Remove the apt repository file {unit} added ({removal.basis})",
                        requires_root=removal.requires_root,
                    )
                )
            elif removal.kind == "venv":
                steps.append(
                    Action(
                        kind="remove-venv",
                        description=f"Remove {unit}'s virtualenv",
                        detail=str(removal.path),
                        perform=partial(_remove_venv, removal.path),
                    )
                )
            else:  # wrapper / desktop-entry: marker-verified
                steps.append(
                    Action(
                        kind=f"remove-{removal.kind}",
                        description=f"Remove {unit}'s {removal.kind} (only if ours)",
                        detail=str(removal.path),
                        perform=partial(_remove_if_ours, removal.path),
                    )
                )
    return steps


def run_removal(
    commands: Sequence[Command | Action],
    runner: CommandRunner,
    *,
    log: TransactionLog,
    plan: RemovalPlan,
    target: Target,
    echo: Callable[[str], None] | None = None,
    euid: int | None = None,
    prober: PackageProber | None = None,
) -> ExecutionReport:
    """Run a removal, with the same logging contract as :func:`execute`.

    Same before/after event ordering, same first-failure stop, and the same
    D-031 ending: the effect check re-reads apt and confirms the packages are
    *absent* — ``apt-get remove`` exiting 0 for a package a held dependency
    kept installed would otherwise be recorded as removed.

    Its terminal events are ``uninstall_begin`` / ``uninstall_end`` /
    ``uninstall_failed`` so a log reader can tell a removal from an install
    without parsing argv; the per-command events are the shared
    ``command_begin`` / ``command_end``, which is what lets attribution replay
    both directions from one event type.
    """
    write = echo if echo is not None else (lambda _line: None)
    shown_as = os.geteuid() if euid is None else euid

    log.append(
        {
            "event": "uninstall_begin",
            "version": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "target": target.to_log_entry(),
            "packages": list(plan.to_remove),
            "apt_packages": list(plan.apt_packages),
        }
    )

    completed: list[Step] = []
    declined: set[str] = set()
    for command in commands:
        write(f"  $ {command.display(euid=shown_as)}")

        if isinstance(command, Action):
            # Marker-verified unlinks and venv removals run in-process, with
            # the same before/after logging an install-side Action gets.
            log.append(
                {
                    "event": "action_begin",
                    "version": 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "kind": command.kind,
                    "detail": command.detail,
                    "description": command.description,
                }
            )
            try:
                outcome = command.perform()
            except (BackendError, OSError) as exc:
                log.append(
                    {
                        "event": "uninstall_failed",
                        "version": 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "kind": command.kind,
                        "detail": command.detail,
                        "error": str(exc),
                        "completed": len(completed),
                    }
                )
                return ExecutionReport(completed=tuple(completed), failed=command, stderr=str(exc))
            log.append(
                {
                    "event": "action_end",
                    "version": 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "kind": command.kind,
                    "detail": command.detail,
                    "outcome": outcome,
                }
            )
            if outcome:
                write(f"    {outcome}")
            if outcome.startswith("left in place"):
                # An honest refusal (no marker) is not a removal; the effect
                # check must not demand the path be gone.
                declined.add(command.detail)
            completed.append(command)
            continue

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
            log.append(
                {
                    "event": "uninstall_failed",
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
                    "event": "uninstall_failed",
                    "version": 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "argv": list(command.argv),
                    "returncode": result.returncode,
                    "completed": len(completed),
                }
            )
            return ExecutionReport(completed=tuple(completed), failed=command, stderr=result.stderr)
        completed.append(command)

    verification: Verification | None = None
    artifact_checks: list[EffectCheck] = []
    for unit, removals in plan.artifacts.items():
        for removal in removals:
            if str(removal.path) in declined:
                continue
            still_there = removal.path.exists() or removal.path.is_symlink()
            artifact_checks.append(
                EffectCheck(
                    kind=f"{removal.kind}_removed",
                    subject=f"{unit}: {removal.path}",
                    confirmed=not still_there,
                    detail="still present" if still_there else "no longer present",
                )
            )
    if artifact_checks and (prober is None or not plan.apt_packages):
        verification = Verification(checks=tuple(artifact_checks))
    if prober is not None and plan.apt_packages:
        try:
            states = prober.probe(plan.apt_packages)
            checks = list(artifact_checks)
            for package in plan.apt_packages:
                state = states.get(package)
                still_there = state is not None and state.is_installed
                checks.append(
                    EffectCheck(
                        kind="package_removed",
                        subject=package,
                        confirmed=not still_there,
                        detail=(
                            f"still installed at {state.installed}"
                            if still_there and state is not None
                            else "no longer installed"
                        ),
                    )
                )
            verification = Verification(checks=tuple(checks))
        except BackendError as exc:
            verification = Verification(
                checks=(
                    EffectCheck(
                        kind="verification",
                        subject="apt-cache policy",
                        confirmed=False,
                        detail=f"the post-removal effect check could not run: {exc}",
                    ),
                )
            )

    end_entry: dict[str, object] = {
        "event": "uninstall_end",
        "version": 1,
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
