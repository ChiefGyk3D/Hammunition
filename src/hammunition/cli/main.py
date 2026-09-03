# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``hammunition`` command.

``argparse`` rather than a dependency: the CLI surface is four verbs, and a
tool whose whole pitch is "you can read what it is going to do to your machine"
should be installable without pulling anything extra in to parse its own
arguments.

The verbs are ``install``, ``uninstall``, ``list``, ``status``, ``show``,
``menus``, ``hardware`` and ``station``, all with the M1 property intact: what the engine cannot do it says
so, by name. Every backend the 1.0 measurement requires is written (apt, source,
git, binary, venv, and node by D-037); pipx and CPAN re-measured to zero and a
package declaring one is refused with the backend named rather than skipped. CLAUDE.md forbids a shim
that makes an unsupported combination appear to work, and a CLI that quietly
drops the packages it cannot handle is that shim.

Exit codes, because scripts read them:

==  ==============================================================
0   Success, or a dry run that resolved cleanly
1   A command failed while running, or the system is unsupported
2   The transaction could not be planned — every blocker is printed
3   A consent gate was declined, or could not be presented
==  ==============================================================
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import textwrap
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path

from hammunition.backends import (
    AptBackend,
    BackendError,
    BinaryBackend,
    Command,
    GitBackend,
    NodeBackend,
    SourceBackend,
    SubprocessRunner,
    VenvBackend,
)
from hammunition.backends.source import DEFAULT_PREFIX
from hammunition.consent import (
    ConsentDeclined,
    ConsentUnavailable,
    render_disclosure,
    resolve_consent,
)
from hammunition.distro import DetectionError, Target
from hammunition.execute import (
    Step,
    artifact_removal_steps,
    commands_for,
    execute,
    run_removal,
    user_groups,
)
from hammunition.fetch import Fetcher
from hammunition.manifest.hardware import DeviceClass, DeviceManifest
from hammunition.manifest.load import CatalogError, load_catalog, load_profiles
from hammunition.manifest.schema import (
    AptInstall,
    BinaryInstall,
    GitInstall,
    NodeInstall,
    PackageManifest,
    ProfileManifest,
    SourceInstall,
    Status,
    VenvInstall,
)
from hammunition.paths import applications_dir, build_root, node_root, user_bin_dir, venv_root
from hammunition.plan import InstallPlan, PlanError, PlannedPackage, resolve
from hammunition.state import (
    RemovalError,
    RemovalPaths,
    TransactionLog,
    files_installed_by_hammunition,
    installed_by_hammunition,
    log_path,
    plan_removal,
)
from hammunition.station import (
    STATION_FIELDS,
    Station,
    StationError,
    config_path,
    is_interactive,
    load_station,
    prompt_for,
    save_station,
)

__all__ = ["build_parser", "main"]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNPLANNABLE = 2
EXIT_CONSENT = 3


# ---------------------------------------------------------------------------
# Locating the catalog
# ---------------------------------------------------------------------------


def find_catalog(explicit: Path | None = None) -> Path:
    """Locate ``catalog/``.

    A git clone is the supported install today — the wheel carries the engine
    and the catalog is a separate tree — so the search walks up from this file
    looking for a checkout. ``--catalog`` and ``HAMMUNITION_CATALOG`` override
    it, and being unable to find one is a loud error rather than an empty
    catalog, because an empty catalog would make ``list`` print nothing and
    look like an answer.
    """
    if explicit is not None:
        candidate = explicit
    elif os.environ.get("HAMMUNITION_CATALOG"):
        candidate = Path(os.environ["HAMMUNITION_CATALOG"])
    else:
        for parent in Path(__file__).resolve().parents:
            if (parent / "catalog" / "packages").is_dir():
                return parent / "catalog"
        raise SystemExit(
            "could not find the catalog. Hammunition is installed from a git clone "
            "today; run it from the checkout, or pass --catalog /path/to/catalog "
            "(or set HAMMUNITION_CATALOG)."
        )
    if not (candidate / "packages").is_dir():
        raise SystemExit(f"{candidate} does not look like a catalog: no packages/ inside it")
    return candidate


def load_all(
    catalog_root: Path,
) -> tuple[dict[str, PackageManifest], dict[str, ProfileManifest]]:
    """Load packages and profiles, cross-checked. Every failure at once (D-016)."""
    packages = load_catalog(catalog_root / "packages")
    profiles = load_profiles(catalog_root / "profiles", packages)
    return packages, profiles


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _plan_state(planned: PlannedPackage) -> str:
    """What the plan will do to this unit, in two words.

    "already installed" is apt's answer and only apt's: it means every apt
    package the block names is present. A source or binary unit's apt list is
    its build dependencies, or nothing at all, so for those it was saying
    "already installed" one line above a build -- sdrangel's .deb block on
    the Ubuntu 26.04 VM read that way (2026-09-02).
    """
    method = planned.block.install
    if isinstance(method, AptInstall):
        return "already installed" if not planned.outstanding else "will install"
    if isinstance(method, SourceInstall | GitInstall):
        return "will build"
    if isinstance(method, VenvInstall):
        return "will install"  # into its own venv, reported by the venv step
    if isinstance(method, NodeInstall):
        return "will build"
    return "will fetch+install"


def render_plan(
    plan: InstallPlan,
    commands: Sequence[Step],
    *,
    euid: int,
    log_destination: Path | None = None,
    hands_log_to: str | None = None,
) -> list[str]:
    """The complete account of what will happen. Printed for every run.

    Not only for ``--dry-run``. An operator who is about to say yes should be
    reading the same text the dry run would have shown them, because a
    disclosure that appears only when you ask for it is one most people never
    see.

    ``log_destination`` and ``hands_log_to`` disclose the transaction log — a
    file written to the machine, and under ``sudo`` a file (and the directories
    on the way to it) chowned to the operator. CLAUDE.md: nothing happens to a
    machine that is not written down, before it happens. Showing the resolved
    path also makes a wrong one visible: if the operator does not resolve and
    the log falls back to ``/root``, the plan now says so instead of the
    fallback happening in silence.
    """
    lines = [f"Target: {plan.target.describe()}", ""]

    if plan.packages:
        lines.append(f"Packages ({len(plan.packages)}):")
        for planned in plan.packages:
            why = ", ".join(planned.requested_by)
            lines.append(f"  {planned.name:<28} {_plan_state(planned):<18} [{why}]")
            for apt_package in planned.apt_packages:
                mark = "+" if apt_package in planned.outstanding else "="
                # A build dependency is installed like any other apt package but
                # is not the software that was asked for, and saying so is the
                # difference between "glfer needs GTK2" and "glfer is GTK2".
                note = "  (to build)" if apt_package in planned.build_only else ""
                lines.append(f"      {mark} {apt_package}{note}")
        lines.append("")

    displacing = [(p.name, c) for p in plan.packages for c in p.displaces]
    if displacing:
        lines.append("Installed distribution packages displaced or shadowed (D-022):")
        for name, conflict in displacing:
            lines.append(
                f"  {conflict}  — declared by {name}; the distribution package stays "
                f"installed, see that manifest's notes"
            )
        lines.append("")

    if plan.apt_release is not None:
        # apt would not resolve the transaction from the default release
        # because a package already installed from another archive would have
        # to be downgraded, so the whole apt step is resolved from that archive
        # instead. Which packages that changes is the disclosure. D-038.
        lines.append(f"apt packages resolved from {plan.apt_release} (D-038):")
        lines.extend(
            _wrap(
                f"apt refused the default release because a package this machine "
                f"already installs from {plan.apt_release} would have been "
                f"downgraded; the apt step runs with --target-release "
                f"{plan.apt_release}, which takes these from there:",
                indent="  ",
            )
        )
        for apt_package in plan.apt_from_release:
            lines.append(f"      {apt_package}")
        lines.append("")

    if plan.group_memberships:
        lines.append("Group membership changes:")
        for membership in plan.group_memberships:
            lines.append(f"  {membership.user} → {membership.group}  ({membership.package})")
            lines.extend(_wrap(membership.detail, indent="      "))
            if membership.reverse_hint:
                lines.append(f"      reverse: {membership.reverse_hint.strip()}")
        lines.append("")

    if plan.consent_gates:
        lines.append("Consent gates that will be presented:")
        for profile_name, gate in plan.consent_gates:
            lines.append(f"  {profile_name} ({gate.env_var})")
            for risk in gate.risk_lines:
                wrapped = _wrap(risk, indent="        ")
                lines.append("      - " + wrapped[0].strip())
                lines.extend(wrapped[1:])
        lines.append("")

    if plan.config_files:
        lines.append("Configuration that will be written:")
        for package, config, _body in plan.config_files:
            backup = "existing file backed up" if config.backup_existing else "NOT backed up"
            verb = "appended to" if config.append else "written"
            lines.append(f"  {config.path}  ({verb}, mode {config.mode}, {backup})  [{package}]")
        lines.append("")

    if plan.deferrals:
        # Deliberately after the packages and before the notes: this is the
        # part of the request that will NOT happen, and burying it under a
        # heading called "notes" is how it stops being read. D-035.
        lines.append("Will NOT happen (the rest of the transaction still will):")
        for deferral in plan.deferrals:
            lines.append(f"  {deferral.subject}: {deferral.what}")
            lines.extend(_wrap(f"why: {deferral.why}", indent="      "))
            lines.extend(_wrap(f"→ {deferral.remedy}", indent="      "))
        lines.append("")

    if plan.notes:
        lines.append("Notes:")
        for note in plan.notes:
            wrapped = _wrap(note, indent="      ")
            lines.append("  - " + wrapped[0].strip())
            lines.extend(wrapped[1:])
        lines.append("")

    if log_destination is not None:
        lines.append("Records:")
        lines.append(f"  transaction log written to {log_destination}")
        if hands_log_to is not None:
            lines.append(
                f"  the log and any directories created for it are given to "
                f"{hands_log_to!r} (chown), since root is writing into their home"
            )
        lines.append("")

    lines.append(f"Commands ({len(commands)}):")
    if not commands:
        lines.append("  (none — everything this plan asks for is already in place)")
    for command in commands:
        lines.append(f"  # {command.description}")
        lines.append(f"  $ {command.display(euid=euid)}")
    return lines


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)

    target: Target | None
    try:
        target = Target.detect()
    except DetectionError:
        target = None

    if args.what in {"profiles", "all"}:
        print(f"Profiles ({len(profiles)}):")
        for name in sorted(profiles):
            profile = profiles[name]
            gate = "  [consent gate]" if profile.consent else ""
            print(f"  {name:<16} {profile.stage:<9} {len(profile.packages):>3} pkg{gate}")
            print(f"      {profile.summary}")
        print()

    if args.what in {"packages", "all"}:
        print(f"Packages ({len(packages)}):")
        for name in sorted(packages):
            manifest = packages[name]
            if target is None:
                where = "?"
            else:
                block = manifest.resolve(target.distro, target.version, target.arch)
                where = block.install.method if block else "unsupported here"
            flag = "" if manifest.status is Status.supported else f"  [{manifest.status.value}]"
            print(f"  {name:<28} {where:<18}{flag}")
            print(f"      {manifest.summary}")
    return EXIT_OK


def operator(args: argparse.Namespace) -> str:
    """Who this run is on behalf of.

    Used for two things that must agree: which account `gpasswd` adds to a
    group, and whose transaction log gets written. They were resolved
    separately, and under `sudo hammunition` the log went to root's home while
    the group membership went to the right person — so `hammunition status`,
    run afterwards as that person, reported no transactions at all.
    """
    return (
        getattr(args, "user", None) or os.environ.get("SUDO_USER") or os.environ.get("USER") or ""
    )


def cmd_status(args: argparse.Namespace) -> int:
    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"Target: unidentified — {exc}", file=sys.stderr)
        return EXIT_FAILED

    print(f"Target: {target.describe()}")
    print(
        "Debian family: "
        + ("yes" if target.is_debian_family else "no — installation is refused here")
    )

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    resolvable = sum(
        1
        for manifest in packages.values()
        if manifest.resolve(target.distro, target.version, target.arch) is not None
    )
    print(f"Catalog: {catalog_root}")
    print(f"  {len(packages)} packages, {resolvable} of which resolve on this target")
    print(f"  {len(profiles)} profiles")

    log = TransactionLog(owner=operator(args) or None)
    entries = list(log.read())
    print(f"Transaction log: {log.path}")
    if not entries:
        print("  no transactions recorded")
        return EXIT_OK

    # The most recent transaction, and how it actually ended. Reading only
    # transaction_begin and calling its packages "covered" reported a run that
    # died on package 3 of 20 as if all 20 landed — the one command whose job
    # is honest reporting, lying by omission. So find the last begin and the
    # first terminal event after it.
    begin_index = max(
        (i for i, e in enumerate(entries) if e.get("event") == "transaction_begin"),
        default=None,
    )
    print(f"  {len(entries)} entries")
    if begin_index is None:
        print("  no transaction start recorded (log holds only other events)")
        return EXIT_OK

    begin = entries[begin_index]
    intended = [str(p) for p in begin.get("apt_packages", [])]
    tail = entries[begin_index + 1 :]
    ended = next((e for e in tail if e.get("event") == "transaction_end"), None)
    failed = next((e for e in tail if e.get("event") == "transaction_failed"), None)

    if failed is not None:
        done = failed.get("completed", 0)
        print(
            f"  most recent transaction FAILED after {done} command(s); "
            f"{len(intended)} package(s) were intended, not necessarily installed"
        )
    elif ended is not None:
        print(
            f"  most recent transaction completed {ended.get('completed', 0)} "
            f"command(s); {len(intended)} package(s) intended"
        )
        # transaction_end version 2 carries the D-031 effect check. An older
        # log (version 1) has no `verified` key; treat its absence as "not
        # recorded" rather than inventing a verdict.
        if "verified" in ended:
            checks = ended.get("checks", [])
            unconfirmed = [c for c in checks if not c.get("confirmed", False)]
            if ended.get("verified"):
                print(f"  effects confirmed afterwards: {len(checks)} check(s) passed (D-031)")
            else:
                print(f"  UNVERIFIED: {len(unconfirmed)} effect(s) could not be confirmed:")
                for check in unconfirmed:
                    print(f"    {check.get('subject', '?')}: {check.get('detail', '')}")
    else:
        print(
            f"  most recent transaction did not record an ending (interrupted or "
            f"still running); {len(intended)} package(s) were intended"
        )
    for name in intended:
        print(f"    {name}")
    # transaction_begin version 2 records what the plan deferred (D-039): a
    # profile member this target's archive does not carry, or a station value
    # a config file needed and did not have. A version 1 entry has no key and
    # nothing is inferred from its absence.
    deferred = begin.get("deferred", [])
    if deferred:
        print(f"  deferred in that transaction, by design ({len(deferred)}):")
        for entry in deferred:
            print(
                f"    {entry.get('subject', '?')}: {entry.get('what', '')} -- {entry.get('why', '')}"
            )
    return EXIT_OK


def cmd_station_show(args: argparse.Namespace) -> int:
    """What is saved, and where. Says plainly when nothing is."""
    user = operator(args)
    path = config_path(user)
    try:
        station = load_station(owner=user)
    except StationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    print(f"Station configuration: {path}")
    if not path.exists():
        print("  (no file yet)")
    values = station.as_dict()
    if not values:
        print("\nNothing set. `hammunition station set --callsign <yours>` starts it off.")
        print("Nothing is invented on your behalf: a configuration file needing a value")
        print("you have not given is reported as not written, and the package still installs.")
        return EXIT_OK
    print()
    for field in sorted(STATION_FIELDS):
        value = station.get(field)
        print(f"  {field:<14} {value if value else '(not set)'}")
    return EXIT_OK


def cmd_station_set(args: argparse.Namespace) -> int:
    user = operator(args)
    try:
        current = load_station(owner=user)
    except StationError:
        current = Station()
    overrides = {
        field: value
        for field, value in (
            ("callsign", args.callsign),
            ("grid_square", args.grid_square),
            ("node_alias", args.node_alias),
        )
        if value
    }
    if not overrides:
        print(
            "error: nothing to set. Pass at least one of --callsign, --grid-square, --node-alias.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    try:
        station = Station(**{**current.as_dict(), **overrides})
    except StationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    path = save_station(station, owner=user)
    print(f"Saved to {path} (mode 0600).")
    for field in sorted(overrides):
        print(f"  {field:<14} {station.get(field)}")
    return EXIT_OK


def _station_for(
    args: argparse.Namespace,
    packages: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    user: str,
) -> Station:
    """The station values this run will use.

    Three sources, later winning: the saved file, then `--callsign` and friends,
    then a prompt — and the prompt happens only when the request actually needs
    a value, the terminal can answer, and `--yes` was not given. Asking for a
    callsign to install a spectrum analyser would be the kind of prompt people
    learn to dismiss, which is what makes the consent gates worthless.
    """
    try:
        station = load_station(owner=user)
    except StationError as exc:
        print(f"warning: {exc}", file=sys.stderr)
        print("  continuing without saved station values.", file=sys.stderr)
        station = Station()

    overrides = {
        field: value
        for field, value in (
            ("callsign", args.callsign),
            ("grid_square", args.grid_square),
            ("node_alias", args.node_alias),
        )
        if value
    }
    if overrides:
        station = Station(**{**station.as_dict(), **overrides})

    if args.yes or not is_interactive():
        return station

    needed: set[str] = set()
    for name in args.names:
        for package in profiles[name].packages if name in profiles else [name]:
            manifest = packages.get(package)
            if manifest is not None:
                needed |= manifest.station_variables
    outstanding = station.missing(needed)
    if not outstanding:
        return station

    print("Some configuration in this request needs values only you can supply.")
    print("Leave any blank to skip it — the package still installs and the file is not written.\n")
    station = prompt_for(outstanding, station)
    if station.as_dict():
        saved = save_station(station, owner=user)
        print(f"\nSaved to {saved} (mode 0600).\n")
    return station


def _apply_suggestions(
    names: list[str],
    profiles: Mapping[str, ProfileManifest],
    *,
    assume_yes: bool,
) -> tuple[list[str], list[str]]:
    """Resolve each requested profile's suggestion groups (Q-015 #1).

    Detection first: any of the group's ``detect_commands`` on PATH means the
    system already has an answer and it is respected — nothing offered,
    nothing installed. Only an interactive run without ``--yes`` gets the
    selection prompt, and skipping is always an option; a non-interactive run
    notes the skip instead of blocking (the D-035 shape). Returns the extra
    package names chosen and the notes to print with the plan.
    """
    import shutil

    extra: list[str] = []
    notes: list[str] = []
    for name in names:
        profile = profiles.get(name)
        if profile is None:
            continue
        for group in profile.suggests_one_of:
            found = next((c for c in group.detect_commands if shutil.which(c)), None)
            if found:
                notes.append(
                    f"{group.name}: `{found}` is already installed — respected, "
                    f"nothing offered ({name} profile)"
                )
                continue
            if assume_yes or not is_interactive():
                notes.append(
                    f"{group.name}: none detected and this run cannot ask — skipped. "
                    f"The {name} profile's docs list the options "
                    f"({', '.join(group.options)}); install one by name any time"
                )
                continue
            print(f"\nThe {name} profile suggests a {group.name}, and none was detected.")
            print(
                textwrap.fill(group.reason, width=78, initial_indent="  ", subsequent_indent="  ")
            )
            for index, option in enumerate(group.options, start=1):
                flag = "  (recommended)" if option == group.recommended else ""
                print(f"  [{index}] {option}{flag}")
            print("  [s] skip — install none")
            default = ""
            if group.recommended in group.options:
                default = str(group.options.index(group.recommended) + 1)
            prompt = f"Choose a {group.name} [1-{len(group.options)}/s]"
            prompt += f" (default {default}): " if default else ": "
            answer = input(prompt).strip().lower() or default
            if answer.isdigit() and 1 <= int(answer) <= len(group.options):
                chosen = group.options[int(answer) - 1]
                extra.append(chosen)
                notes.append(f"{group.name}: you chose {chosen}; added to this transaction")
            else:
                notes.append(f"{group.name}: skipped by choice")
    return extra, notes


def cmd_install(args: argparse.Namespace) -> int:
    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    if not target.is_debian_family:
        print(
            f"error: {target.describe()} is not Debian-family. Hammunition installs "
            f"through apt and will not pretend to support this system.",
            file=sys.stderr,
        )
        return EXIT_FAILED

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)

    runner = SubprocessRunner()
    apt = AptBackend(runner)
    user = operator(args)

    station = _station_for(args, packages, profiles, user)

    suggested, suggestion_notes = _apply_suggestions(args.names, profiles, assume_yes=args.yes)

    try:
        plan = resolve(
            [*args.names, *suggested],
            catalog=packages,
            profiles=profiles,
            target=target,
            apt=apt,
            user=user,
            refresh=args.refresh,
            station=station,
        )
    except PlanError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "\nNothing was changed. Resolution happens before installation so that a "
            "failure is a report rather than a half-installed machine (D-016).",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    euid = os.geteuid()
    # The artifact cache and the build tree belong to the operator, not to root:
    # under sudo they would otherwise land in /root, invisible to the person who
    # asked for the build and re-downloaded on their next unprivileged run. Same
    # reasoning as the transaction log, and the same helper resolves both.
    builds = build_root(user or None)
    source = SourceBackend(Fetcher(owner=user or None), build_root=builds)
    git = GitBackend(runner=runner, build_root=builds, prefix=source.prefix, jobs=source.jobs)
    binary = BinaryBackend(
        fetcher=source.fetcher, runner=runner, build_root=builds, prefix=source.prefix
    )
    venv = VenvBackend(
        venv_root=venv_root(user or None),
        bin_dir=user_bin_dir(user or None),
        fetcher=source.fetcher,
        build_root=builds,
        prefix=source.prefix,
    )
    node = NodeBackend(
        fetcher=source.fetcher,
        build_root=builds,
        node_root=node_root(user or None),
        bin_dir=user_bin_dir(user or None),
    )
    commands = commands_for(
        plan,
        apt,
        refresh=args.refresh,
        source=source,
        git=git,
        binary=binary,
        venv=venv,
        node=node,
        config_staging=builds,
        launcher_bin=user_bin_dir(user or None),
        launcher_applications=applications_dir(user or None),
    )
    # Disclose the log destination in the plan itself, so the file write (and,
    # under sudo, the chown to the operator) is shown before it happens rather
    # than surfacing after. A handoff only occurs when root is writing into
    # somebody else's home, which is exactly when log_path redirects.
    log_owner = user or None
    log_destination = log_path(log_owner)
    hands_log_to = (
        log_owner
        if (log_owner and euid == 0 and str(log_destination).startswith("/home"))
        else None
    )
    for note in suggestion_notes:
        print(f"note: {note}")
    for line in render_plan(
        plan,
        commands,
        euid=euid,
        log_destination=log_destination,
        hands_log_to=hands_log_to,
    ):
        print(line)

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK

    log = TransactionLog(owner=log_owner)

    # Consent gates come after the plan is printed and before anything runs.
    # --yes is passed so the call site documents that it does not help; the
    # gate never reads it (D-021).
    for profile_name, gate in plan.consent_gates:
        try:
            record = resolve_consent(
                gate,
                profile_name,
                environ=os.environ,
                prompt=_prompt if sys.stdin.isatty() else None,
                assume_yes=args.yes,
                actor=user or None,
            )
        except ConsentDeclined as exc:
            print(f"\n{exc}. Nothing was changed.", file=sys.stderr)
            return EXIT_CONSENT
        except ConsentUnavailable as exc:
            print(f"\n{exc}", file=sys.stderr)
            return EXIT_CONSENT
        log.append(record.to_log_entry())

    if not commands:
        print("\nNothing to do.")
        return EXIT_OK

    if not args.yes:
        print()
        if not _prompt("Proceed with the commands above?"):
            print("Aborted. Nothing was changed.")
            return EXIT_OK

    print("\nRunning:")
    # Pass apt as the prober so the run re-reads what it changed (D-031): an
    # exit code of 0 from apt-get or gpasswd is not evidence the package landed
    # or the membership took, and transaction_end is the record uninstall will
    # trust.
    report = execute(
        commands,
        runner,
        log=log,
        plan=plan,
        echo=print,
        euid=euid,
        prober=apt,
        prefix=source.prefix,
    )
    if log.ownership_error:
        # Not fatal — the commands ran — but not silent either. A log the
        # operator cannot append to fails on their next run instead of this one.
        print(f"\nWarning: {log.ownership_error}", file=sys.stderr)
    if report.ok and not report.verified and report.verification is not None:
        # Every command exited 0, but re-reading the effect found something it
        # claimed to do that did not happen. Fail loudly (CLAUDE.md): a green
        # exit code over a machine that did not actually change is the lie
        # D-031 exists to catch.
        print(
            f"\nCommands completed, but {len(report.verification.discrepancies)} "
            f"effect(s) could not be confirmed afterwards:",
            file=sys.stderr,
        )
        for check in report.verification.discrepancies:
            print(f"  {check.subject}: {check.detail}", file=sys.stderr)
        print(
            f"\nThe transaction log records this as unverified ({log.path}). "
            f"An exit code of 0 is not proof the change took (D-031).",
            file=sys.stderr,
        )
        return EXIT_FAILED
    if report.ok:
        print(f"\nDone. {len(report.completed)} command(s) completed and confirmed.")
        if plan.group_memberships:
            print(
                "Group membership does not apply to a session that is already open — "
                "log out and back in."
            )
        return EXIT_OK

    assert report.failed is not None
    print(
        f"\nFailed: {report.failed.display(euid=euid)}\n{report.stderr.strip()}",
        file=sys.stderr,
    )
    print(
        f"{len(report.completed)} command(s) completed before the failure and are "
        f"recorded in {log.path}. Hammunition does not roll back; it tells you what "
        f"it did (D-004).",
        file=sys.stderr,
    )
    return EXIT_FAILED


def cmd_uninstall(args: argparse.Namespace) -> int:
    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if not target.is_debian_family:
        print(
            f"error: {target.describe()} is not Debian-family; there is nothing "
            f"Hammunition could have installed here.",
            file=sys.stderr,
        )
        return EXIT_FAILED

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    runner = SubprocessRunner()
    apt = AptBackend(runner)
    user = operator(args)
    log = TransactionLog(owner=user or None)

    attributed = installed_by_hammunition(log)
    attributed_files = files_installed_by_hammunition(log)
    removal_paths = RemovalPaths(
        prefix=DEFAULT_PREFIX,
        venv_root=venv_root(user or None),
        bin_dir=user_bin_dir(user or None),
        applications_dir=applications_dir(user or None),
        node_root=node_root(user or None),
    )
    # Probe every package the request could touch, so the plan partitions on
    # what is installed now rather than on what the log said at install time.
    probe_set: set[str] = set()
    for name in args.names:
        for unit in profiles[name].packages if name in profiles else [name]:
            manifest = packages.get(unit)
            if manifest is None:
                continue
            block = manifest.resolve(target.distro, target.version, target.arch)
            if block is None:
                continue
            if isinstance(block.install, AptInstall):
                probe_set.update(block.install.packages)
            elif isinstance(block.install, BinaryInstall) and block.install.deb_package:
                probe_set.add(block.install.deb_package)
    try:
        states = apt.probe(sorted(probe_set)) if probe_set else {}
        plan = plan_removal(
            args.names,
            catalog=packages,
            profiles=profiles,
            target=target,
            attributed=attributed,
            states=states,
            paths=removal_paths,
            attributed_files=attributed_files,
            log=log,
        )
    except RemovalError as exc:
        print(str(exc), file=sys.stderr)
        print("\nNothing was changed.", file=sys.stderr)
        return EXIT_UNPLANNABLE
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    euid = os.geteuid()
    commands: list[Step] = list(apt.remove_commands(plan.apt_packages))
    commands.extend(artifact_removal_steps(plan))

    print(f"Target: {target.describe()}\n")
    if plan.to_remove:
        print(f"Removing ({len(plan.to_remove)} unit(s)):")
        for unit, unit_packages in plan.to_remove.items():
            print(f"  {unit:28} - {' '.join(unit_packages)}")
    if plan.artifacts:
        print(f"\nRemoving artifacts ({sum(len(a) for a in plan.artifacts.values())}):")
        for unit, removals in plan.artifacts.items():
            for removal in removals:
                print(f"  {unit:28} {removal.kind:14} {removal.path}  [{removal.basis}]")
    if plan.left_unattributed:
        print("\nLeft in place — present, but the transaction log does not attribute it:")
        for unit, files in plan.left_unattributed.items():
            for path in files:
                print(f"  {unit:28} {path}")
    for label, mapping in (
        ("Left in place — installed, but not installed by Hammunition:", plan.left_foreign),
        ("Already absent:", plan.already_absent),
    ):
        flat = {unit: pkgs for unit, pkgs in mapping.items() if pkgs or unit not in plan.to_remove}
        if flat:
            print(f"\n{label}")
            for unit, unit_packages in flat.items():
                print(f"  {unit:28} {' '.join(unit_packages) or '(nothing resolves here)'}")
    print(
        "\nNot reversed, by design: dependencies apt pulled in (run "
        "`sudo apt autoremove` to clear orphans), group memberships, and any "
        "config files written — all recorded in the transaction log (D-004)."
    )

    if commands:
        print(f"\nCommands ({len(commands)}):")
        for command in commands:
            print(f"  # {command.description}")
            print(f"  $ {command.display(euid=euid)}")
    else:
        print("\nNothing to do: none of this is installed, or none of it was ours.")
        return EXIT_OK

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK
    if not args.yes:
        print()
        if not _prompt("Proceed with the commands above?"):
            print("Aborted. Nothing was changed.")
            return EXIT_OK

    print("\nRunning:")
    report = run_removal(
        commands, runner, log=log, plan=plan, target=target, echo=print, euid=euid, prober=apt
    )
    if log.ownership_error:
        print(f"\nWarning: {log.ownership_error}", file=sys.stderr)
    if report.ok and not report.verified and report.verification is not None:
        print(
            f"\nCommands completed, but {len(report.verification.discrepancies)} "
            f"removal(s) could not be confirmed afterwards:",
            file=sys.stderr,
        )
        for check in report.verification.discrepancies:
            print(f"  {check.subject}: {check.detail}", file=sys.stderr)
        print(
            f"\nThe transaction log records this as unverified ({log.path}). "
            f"An exit code of 0 is not proof the change took (D-031).",
            file=sys.stderr,
        )
        return EXIT_FAILED
    if report.ok:
        print(f"\nDone. {len(report.completed)} command(s) completed and confirmed.")
        return EXIT_OK

    assert report.failed is not None
    print(
        f"\nFailed: {report.failed.display(euid=euid)}\n{report.stderr.strip()}",
        file=sys.stderr,
    )
    print(
        f"{len(report.completed)} command(s) completed before the failure and are "
        f"recorded in {log.path}.",
        file=sys.stderr,
    )
    return EXIT_FAILED


def cmd_menus_apply(args: argparse.Namespace) -> int:
    import yaml

    from hammunition.menus import (
        Category,
        MenuPaths,
        MenuPrefixError,
        gnome_commands,
        menu_steps,
        place_installed_entries,
        resolve_menu_prefix,
    )

    catalog_root = find_catalog(args.catalog)
    vocabulary = yaml.safe_load((catalog_root / "categories.yaml").read_text())["categories"]
    categories = [
        Category(name=c["name"], summary=c["summary"], title=c.get("title", "")) for c in vocabulary
    ]
    manifests, _ = load_all(catalog_root)
    placement = place_installed_entries(manifests.values())

    home = Path.home()
    paths = MenuPaths(
        menus_dir=Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "menus",
        directories_dir=Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
        / "desktop-directories",
    )
    config_dirs = [
        Path(d) for d in (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":") if d
    ]
    try:
        prefix = resolve_menu_prefix(
            args.menu_prefix, os.environ.get("XDG_MENU_PREFIX"), config_dirs
        )
    except MenuPrefixError as exc:
        print(f"Refusing to write a menu that nothing would read: {exc}", file=sys.stderr)
        return EXIT_FAILED
    steps = menu_steps(categories, paths, menu_prefix=prefix, placement=placement)

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    wants_gnome = "GNOME" in desktop.upper() or args.gnome
    placed = sum(len(v) for v in placement.by_category.values())
    print(
        f"Menu tree: {len(categories)} categories, menu prefix {prefix!r}; "
        f"{len(placement.claimed)} desktop entries from installed catalog packages "
        f"placed {placed} times by their manifests' categories (dpkg -L, this machine)"
    )
    for step in steps:
        print(f"  {step.display()}")
        outcome = step.perform()
        print(f"    {outcome}")
    if wants_gnome:
        runner = SubprocessRunner()
        print("GNOME app-folder (needs your session bus):")
        for command in gnome_commands(placement):
            # The two read-modify-write steps are python -c bodies; the
            # description says what they do and the body would fill a screen.
            shown = command.argv[:2] if command.argv[0] == "python3" else command.argv
            print(f"  # {command.description}\n  $ {' '.join(shown)} …")
            result = runner.run(command)
            if result.returncode != 0:
                print(
                    f"error: {result.stderr.strip()[:200]}\n"
                    f"GNOME folders live in dconf; run this inside your desktop "
                    f"session, not over bare SSH.",
                    file=sys.stderr,
                )
                return EXIT_FAILED
    else:
        print(
            "GNOME app-folder skipped: XDG_CURRENT_DESKTOP does not say GNOME "
            "(pass --gnome to force). The menu-spec files above serve Xfce and "
            "friends either way."
        )
    print("Done. Menus refresh on next login (or `xfce4-panel -r` / GNOME Shell reload).")
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    """Print the consent disclosure for a gated profile without installing it."""
    catalog_root = find_catalog(args.catalog)
    _, profiles = load_all(catalog_root)
    profile = profiles.get(args.profile)
    if profile is None:
        print(f"error: no profile named {args.profile!r}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    print(f"{profile.name} — {profile.summary}")
    print(f"stage: {profile.stage}")
    print(f"\n{profile.documentation.what_it_installs.strip()}")
    print(f"\nWhy together:\n  {profile.documentation.why_together.strip()}")
    print(f"\nDeliberately excludes:\n  {profile.documentation.deliberately_excludes.strip()}")
    print(f"\nYou still configure by hand:\n  {profile.documentation.manual_configuration.strip()}")
    if profile.consent is not None:
        print("\n" + render_disclosure(profile.consent, profile.name))
    print(f"\nPackages ({len(profile.packages)}):")
    for name in profile.packages:
        print(f"  {name}")
    return EXIT_OK


def _wrap(text: str, *, indent: str, width: int = 88) -> list[str]:
    """Wrap manifest prose to a readable width.

    The `detail` on a system modification is a paragraph — it has to be, since
    it is the operator's only account of what a group membership actually
    grants — and printing it as one 400-column line is how a disclosure becomes
    something nobody reads.
    """
    return textwrap.wrap(
        " ".join(text.split()),
        width=width,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def _prompt(text: str) -> bool:
    """Yes/no on the terminal. Anything that is not an explicit yes is a no."""
    print(text)
    try:
        answer = input("Type 'yes' to continue: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"yes", "y"}


# ---------------------------------------------------------------------------
# hardware — the permissions and udev half of the device role (D-029)
# ---------------------------------------------------------------------------


def _load_hardware_catalog(
    args: argparse.Namespace,
) -> tuple[dict[str, DeviceClass], dict[str, DeviceManifest]]:
    from hammunition.manifest.load import load_hardware

    catalog_root = find_catalog(args.catalog)
    return load_hardware(catalog_root / "hardware")


def cmd_hardware_list(args: argparse.Namespace) -> int:
    """What is plugged in, what the catalog recognises, and what it would set up."""
    from hammunition.hardware import plan_hardware

    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    classes, devices = _load_hardware_catalog(args)
    user = operator(args)
    groups_now = user_groups(user) if user else frozenset()
    plan = plan_hardware(classes, devices, user=user, user_groups_now=groups_now)

    print(f"Target: {target.describe()}\n")
    if plan.detected:
        print("Recognised devices attached:")
        for match in plan.detected:
            flag = "  (ambiguous identifier — could be another device)" if match.ambiguous else ""
            print(f"  {match.name:20} {match.attached.describe()}{flag}")
    else:
        print("No catalogued devices detected on the USB bus.")
    if plan.unrecognised:
        print("\nAttached but not in the catalog (a device we could add):")
        for dev in plan.unrecognised:
            print(f"  {dev.describe()}")
    print(
        f"\nudev rules: {len(plan.rules_content.splitlines())} lines for the whole "
        f"catalog would go to {plan.rules_path}"
        + (" — already current." if plan.rules_already_current else " (not yet applied).")
    )
    wanted = sorted(set(plan.groups_to_add) | set(plan.groups_present))
    if wanted:
        joined = ", ".join(
            f"{g} ✓" if g in plan.groups_present else f"{g} (missing)" for g in wanted
        )
        print(f"Access groups {user!r} needs: {joined}")
    print("\nRun `hammunition hardware apply` to write the rules and join the groups.")
    return EXIT_OK


def cmd_hardware_apply(args: argparse.Namespace) -> int:
    """Write the catalog's udev rules and join the device-access groups."""
    from hammunition.hardware import plan_hardware

    try:
        Target.detect()
    except DetectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    classes, devices = _load_hardware_catalog(args)
    user = operator(args)
    if not user:
        print("error: could not determine which user to set up.", file=sys.stderr)
        return EXIT_FAILED
    groups_now = user_groups(user)
    plan = plan_hardware(classes, devices, user=user, user_groups_now=groups_now)

    print(f"Hardware setup for {user!r}\n")
    if plan.omissions:
        print("Catalogued but deliberately not given a rule (see device-naming.md):")
        for om in plan.omissions[:8]:
            print(f"  {om.render()}")
        if len(plan.omissions) > 8:
            print(f"  … and {len(plan.omissions) - 8} more")
        print()

    if plan.is_noop:
        print(
            "Nothing to do: the rules file already matches and you are in every "
            "access group. Hardware setup is complete."
        )
        return EXIT_OK

    staging = Path(tempfile.gettempdir()) / "hammunition" / "udev-staging.rules"
    commands: list[Command] = []
    if not plan.rules_already_current:
        print(f"Will write {len(plan.rules_content.splitlines())} lines to {plan.rules_path}")
        commands += [
            Command(
                argv=("install", "-D", "-m", "0644", str(staging), str(plan.rules_path)),
                description=f"Install the generated rules to {plan.rules_path}",
                requires_root=True,
            ),
            Command(
                argv=("udevadm", "control", "--reload-rules"),
                description="Reload udev so the new rules take effect",
                requires_root=True,
            ),
            Command(
                argv=("udevadm", "trigger"),
                description="Apply the rules to devices already attached",
                requires_root=True,
            ),
        ]
    else:
        print(f"Rules file at {plan.rules_path} is already current.")
    for group in plan.groups_to_add:
        print(f"Will add {user!r} to the {group!r} group")
        commands.append(
            Command(
                argv=("gpasswd", "--add", user, group),
                description=f"Add {user} to {group} for device access",
                requires_root=True,
            )
        )

    euid = os.geteuid()
    print(f"\nCommands ({len(commands)}):")
    for command in commands:
        print(f"  # {command.description}")
        print(f"  $ {command.display(euid=euid)}")

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK
    if not args.yes and not _prompt("\nProceed with the commands above?"):
        print("Aborted. Nothing was changed.")
        return EXIT_OK

    if not plan.rules_already_current:
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_text(plan.rules_content)
        os.chmod(staging, 0o644)

    runner = SubprocessRunner()
    print("\nRunning:")
    for command in commands:
        print(f"  $ {command.display(euid=euid)}")
        result = runner.run(command)
        if result.returncode != 0:
            print(f"error: {result.stderr.strip()[:300]}", file=sys.stderr)
            print("Stopped. What ran above is applied; the rest is not.", file=sys.stderr)
            return EXIT_FAILED

    # D-031: verify the effect, not the exit status.
    problems: list[str] = []
    if not plan.rules_already_current:
        try:
            if Path(plan.rules_path).read_text() != plan.rules_content:
                problems.append(f"{plan.rules_path} on disk does not match what we wrote")
        except OSError as exc:
            problems.append(f"could not read back {plan.rules_path}: {exc}")
    after = user_groups(user)
    for group in plan.groups_to_add:
        if group not in after:
            problems.append(f"{user} is still not in {group}")
    if problems:
        for problem in problems:
            print(f"  unverified: {problem}", file=sys.stderr)
        return EXIT_FAILED

    print("\nDone and verified.")
    if plan.groups_to_add:
        print(
            f"Group membership ({', '.join(plan.groups_to_add)}) takes effect at your "
            f"next login — log out and back in before expecting device access."
        )
    return EXIT_OK


# ---------------------------------------------------------------------------
# doctor — a read-only health check
# ---------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    """Report what is ready and what is not yet set up. Changes nothing."""
    import shutil

    from hammunition.doctor import run_checks, summarize, writable_or_creatable
    from hammunition.hardware import RULES_PATH, plan_hardware, rules_file
    from hammunition.manifest.load import load_hardware
    from hammunition.paths import state_dir

    classes: dict[str, DeviceClass] = {}
    devices: dict[str, DeviceManifest] = {}

    user = operator(args)

    try:
        target = Target.detect()
        target_describe: str | None = target.describe()
        is_debian = target.is_debian_family
    except DetectionError:
        target_describe, is_debian = None, False

    catalog_counts: tuple[int, int] | None = None
    needed_groups: list[str] = []
    attached_recognised = 0
    try:
        catalog_root = find_catalog(args.catalog)
        packages, profiles = load_all(catalog_root)
        catalog_counts = (len(packages), len(profiles))
        classes, devices = load_hardware(catalog_root / "hardware")
        groups_now = user_groups(user) if user else frozenset()
        hw = plan_hardware(classes, devices, user=user or "", user_groups_now=groups_now)
        needed_groups = sorted(set(hw.groups_to_add) | set(hw.groups_present))
        attached_recognised = len(hw.detected)
    except (SystemExit, CatalogError, OSError):
        groups_now = frozenset()

    # python3 -m venv works iff the venv module imports and ensurepip is present.
    try:
        import ensurepip  # noqa: F401
        import venv  # noqa: F401

        has_venv_module = True
    except ImportError:
        has_venv_module = False

    local_bin = str(user_bin_dir(user or None))
    path_has_local_bin = local_bin in os.environ.get("PATH", "").split(os.pathsep)

    tools = {
        "cc": bool(shutil.which("cc") or shutil.which("gcc")),
        "git": bool(shutil.which("git")),
    }

    from hammunition.station import load_station

    try:
        station = load_station(owner=user or None)
        station_set = station.callsign is not None
    except Exception:
        station_set = False

    rules_applied = False
    rules_file_path = Path(RULES_PATH)
    if rules_file_path.exists() and (classes or devices):
        expected, _ = rules_file([*classes.values(), *devices.values()])
        try:
            rules_applied = rules_file_path.read_text() == expected
        except OSError:
            rules_applied = True  # present but unreadable-as-text: it exists

    log_dir = state_dir(user or None)
    log_dir_writable = writable_or_creatable(log_dir)

    checks = run_checks(
        target_describe=target_describe,
        is_debian_family=is_debian,
        catalog_counts=catalog_counts,
        has_venv_module=has_venv_module,
        path_has_local_bin=path_has_local_bin,
        tools=tools,
        groups_now=groups_now,
        needed_groups=needed_groups,
        station_set=station_set,
        rules_applied=rules_applied,
        attached_recognised=attached_recognised,
        log_dir_writable=log_dir_writable,
    )

    glyph = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}
    print("Hammunition health check\n")
    for check in checks:
        print(f"  [{glyph[check.status]}] {check.name:14} {check.detail}")
        if check.fix and check.status in ("fail", "warn"):
            print(f"      → {check.fix}")
    fails, warns, healthy = summarize(checks)
    print(f"\n{healthy} ok, {warns} to look at, {fails} blocking.")
    if fails:
        print("Fix the blocking items above before installing.")
        return EXIT_FAILED
    if warns:
        print("The engine works; the items marked ! limit what you can install until fixed.")
    else:
        print("Ready.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _engine_version() -> str:
    """The installed package version, or a marker when running uninstalled."""
    try:
        return metadata.version("hammunition")
    except metadata.PackageNotFoundError:
        return "0+uninstalled"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hammunition",
        description="Turn a Debian-family install into an amateur radio, SDR and RF workstation.",
        epilog=(
            "Alpha. The apt, source, git, binary, venv and node backends exist; the "
            "install/configure/remove cycle is VM-verified on Parrot, Kali and "
            "Debian 13 across the whole catalog. A package needing a third-party "
            "apt repository, pipx or CPAN is refused by name."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"hammunition {_engine_version()}",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        metavar="DIR",
        help="path to the catalog/ directory (default: found from the checkout)",
    )
    # Not required: a bare `hammunition` prints help and exits 0 (main handles
    # it), which is friendlier than argparse's "command is required" error for
    # someone running it for the first time to see what it does.
    sub = parser.add_subparsers(dest="command", required=False)

    p_list = sub.add_parser("list", help="show what the catalog contains")
    p_list.add_argument(
        "what",
        nargs="?",
        default="all",
        choices=("all", "packages", "profiles"),
        help="what to list (default: all)",
    )
    p_list.set_defaults(func=cmd_list)

    p_status = sub.add_parser("status", help="what this machine is, and what has been done to it")
    p_status.set_defaults(func=cmd_status)

    p_show = sub.add_parser("show", help="describe a profile, disclosure included")
    p_show.add_argument("profile")
    p_show.set_defaults(func=cmd_show)

    p_install = sub.add_parser("install", help="install packages or profiles")
    p_install.add_argument("names", nargs="+", metavar="NAME", help="package or profile names")
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve everything and print exactly what would run, then stop",
    )
    p_install.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation. Does NOT satisfy a consent gate (D-021)",
    )
    p_install.add_argument(
        "--refresh",
        action="store_true",
        help="run `apt-get update` as the first command of the transaction",
    )
    p_install.add_argument(
        "--user",
        default=None,
        help="operator to add to groups (default: $SUDO_USER, else $USER)",
    )
    # Station values. Supplying one here overrides the saved file for this run
    # and, if a prompt happens, is remembered.
    p_install.add_argument("--callsign", default=None, help="your callsign — it is transmitted")
    p_install.add_argument("--grid-square", default=None, help="Maidenhead locator, e.g. IO91wm")
    p_install.add_argument(
        "--node-alias", default=None, help="short packet node alias, up to six characters"
    )
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser(
        "uninstall", help="remove what Hammunition itself installed, by backend (D-004)"
    )
    p_uninstall.add_argument("names", nargs="+", metavar="NAME", help="package or profile names")
    p_uninstall.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve the removal and print exactly what would run, then stop",
    )
    p_uninstall.add_argument("--yes", action="store_true", help="skip the confirmation")
    p_uninstall.add_argument(
        "--user",
        default=None,
        help="operator whose transaction log to read (default: $SUDO_USER, else $USER)",
    )
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_menus = sub.add_parser("menus", help="curated desktop menus from the catalog (D-036)")
    menus_sub = p_menus.add_subparsers(dest="menus_command", required=True)
    p_menus_apply = menus_sub.add_parser(
        "apply", help="write the Ham Radio menu tree; on GNOME also the app-folder"
    )
    p_menus_apply.add_argument(
        "--gnome", action="store_true", help="apply the GNOME app-folder even if undetected"
    )
    p_menus_apply.add_argument(
        "--menu-prefix",
        default=None,
        metavar="PREFIX",
        help=(
            "which root menu to merge into (plasma-, xfce-, gnome-, ...); default "
            "$XDG_MENU_PREFIX, else the one root menu installed, else refuse"
        ),
    )
    p_menus_apply.set_defaults(func=cmd_menus_apply)

    p_doctor = sub.add_parser("doctor", help="read-only health check: is this machine ready?")
    p_doctor.add_argument("--user", default=None, help="whose setup to check")
    p_doctor.set_defaults(func=cmd_doctor)

    p_hardware = sub.add_parser(
        "hardware", help="detect devices; apply udev rules and groups (D-029)"
    )
    hardware_sub = p_hardware.add_subparsers(dest="hardware_command", required=True)

    p_hw_list = hardware_sub.add_parser("list", help="what is attached and what setup it needs")
    p_hw_list.add_argument("--user", default=None, help="whose group membership to check")
    p_hw_list.set_defaults(func=cmd_hardware_list)

    p_hw_apply = hardware_sub.add_parser(
        "apply", help="write the udev rules and join the device-access groups"
    )
    p_hw_apply.add_argument("--dry-run", action="store_true", help="print, change nothing")
    p_hw_apply.add_argument("--yes", action="store_true", help="skip the confirmation")
    p_hw_apply.add_argument("--user", default=None, help="whom to set up")
    p_hw_apply.set_defaults(func=cmd_hardware_apply)

    p_station = sub.add_parser("station", help="the values only you can supply")
    station_sub = p_station.add_subparsers(dest="station_command", required=True)

    p_station_show = station_sub.add_parser("show", help="print the saved station values")
    p_station_show.add_argument("--user", default=None, help="whose configuration to read")
    p_station_show.set_defaults(func=cmd_station_show)

    p_station_set = station_sub.add_parser("set", help="save station values")
    p_station_set.add_argument("--callsign", default=None)
    p_station_set.add_argument("--grid-square", default=None)
    p_station_set.add_argument("--node-alias", default=None)
    p_station_set.add_argument("--user", default=None, help="whose configuration to write")
    p_station_set.set_defaults(func=cmd_station_set)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Line-buffer stdout even when it is not a terminal. A whole-profile
    # install redirected to a file showed 0 bytes for the forty minutes it
    # ran (Kali VM, 2026-09-02): Python block-buffers a pipe, so every `$
    # command` header sat in memory while the child processes, which write
    # to the same descriptor directly, streamed past it -- a log that is
    # empty until exit, and then out of order. An install that is killed
    # mid-way loses the whole record. Line buffering costs nothing an
    # installer notices.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(line_buffering=True)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Bare `hammunition`: print the top-level help and exit cleanly, which
        # is friendlier than argparse's "command is required" error for someone
        # running it for the first time. (Group verbs keep required sub-verbs,
        # so `hammunition hardware` still gets argparse's standard message.)
        parser.print_help()
        return EXIT_OK
    try:
        result: int = args.func(args)
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    except StationError as exc:
        # A bad --callsign is operator input, not an engine fault: it gets the
        # validator's message and the planning exit code, never a traceback.
        # Found on the first Parrot VM run that passed one.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing further was run.", file=sys.stderr)
        return EXIT_FAILED
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
