# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``hammunition`` command.

``argparse`` rather than a dependency: the CLI surface is four verbs, and a
tool whose whole pitch is "you can read what it is going to do to your machine"
should be installable without pulling anything extra in to parse its own
arguments.

The verbs are ``install``, ``uninstall``, ``list``, ``status``, ``show`` and
``station``, all with the M1 property intact: what the engine cannot do it says
so, by name. Three backends measured and scheduled for 1.0 are not written
(venv, pipx, CPAN), and a package needing one is refused with the backend named
rather than skipped. CLAUDE.md forbids a shim
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
import textwrap
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path

from hammunition.backends import (
    AptBackend,
    BackendError,
    BinaryBackend,
    GitBackend,
    SourceBackend,
    SubprocessRunner,
    VenvBackend,
)
from hammunition.consent import (
    ConsentDeclined,
    ConsentUnavailable,
    render_disclosure,
    resolve_consent,
)
from hammunition.distro import DetectionError, Target
from hammunition.execute import Step, commands_for, execute, run_removal
from hammunition.fetch import Fetcher
from hammunition.manifest.load import CatalogError, load_catalog, load_profiles
from hammunition.manifest.schema import AptInstall, PackageManifest, ProfileManifest, Status
from hammunition.paths import build_root, user_bin_dir, venv_root
from hammunition.plan import InstallPlan, PlanError, resolve
from hammunition.state import (
    RemovalError,
    TransactionLog,
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
            state = "already installed" if not planned.outstanding else "will install"
            lines.append(f"  {planned.name:<28} {state:<18} [{why}]")
            for apt_package in planned.apt_packages:
                mark = "+" if apt_package in planned.outstanding else "="
                # A build dependency is installed like any other apt package but
                # is not the software that was asked for, and saying so is the
                # difference between "glfer needs GTK2" and "glfer is GTK2".
                note = "  (to build)" if apt_package in planned.build_only else ""
                lines.append(f"      {mark} {apt_package}{note}")
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

    try:
        plan = resolve(
            args.names,
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
    venv = VenvBackend(venv_root=venv_root(user or None), bin_dir=user_bin_dir(user or None))
    commands = commands_for(
        plan, apt, refresh=args.refresh, source=source, git=git, binary=binary,
        venv=venv, config_staging=builds,
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
    report = execute(commands, runner, log=log, plan=plan, echo=print, euid=euid, prober=apt)
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
    # Probe every package the request could touch, so the plan partitions on
    # what is installed now rather than on what the log said at install time.
    probe_set: set[str] = set()
    for name in args.names:
        for unit in profiles[name].packages if name in profiles else [name]:
            manifest = packages.get(unit)
            if manifest is None:
                continue
            block = manifest.resolve(target.distro, target.version, target.arch)
            if block is not None and isinstance(block.install, AptInstall):
                probe_set.update(block.install.packages)
    try:
        states = apt.probe(sorted(probe_set)) if probe_set else {}
        plan = plan_removal(
            args.names,
            catalog=packages,
            profiles=profiles,
            target=target,
            attributed=attributed,
            states=states,
        )
    except RemovalError as exc:
        print(str(exc), file=sys.stderr)
        print("\nNothing was changed.", file=sys.stderr)
        return EXIT_UNPLANNABLE
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    euid = os.geteuid()
    commands = apt.remove_commands(plan.apt_packages)

    print(f"Target: {target.describe()}\n")
    if plan.to_remove:
        print(f"Removing ({len(plan.to_remove)} unit(s)):")
        for unit, unit_packages in plan.to_remove.items():
            print(f"  {unit:28} - {' '.join(unit_packages)}")
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
            "Alpha. The apt, source, git and binary backends exist and the "
            "install/configure/remove cycle is VM-verified on Parrot, Kali and "
            "Debian 13; a package needing venv, pipx or CPAN is refused by name."
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
    sub = parser.add_subparsers(dest="command", required=True)

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
        "uninstall", help="remove what Hammunition itself installed (apt only, D-004)"
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
    parser = build_parser()
    args = parser.parse_args(argv)
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
