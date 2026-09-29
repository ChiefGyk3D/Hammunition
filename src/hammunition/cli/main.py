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
import contextlib
import os
import shutil
import stat
import sys
import tempfile
import textwrap
import traceback
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, TextIO, cast

from hammunition import navit_config
from hammunition.backends import (
    Action,
    AptBackend,
    AptRepoBackend,
    BackendError,
    BinaryBackend,
    Command,
    DataBackend,
    DerivedBackend,
    GitBackend,
    NodeBackend,
    RegionsBackend,
    SourceBackend,
    SubprocessRunner,
    VenvBackend,
)
from hammunition.backends.apt import stale_fetches
from hammunition.backends.dem import TerrainDisclosure
from hammunition.backends.regions import (
    KeptRegion,
    MapDisclosure,
    MapLedger,
    MapResolution,
    data_root,
    disk_needs,
    disk_shortfall,
    installed_slugs,
    installed_snapshot,
    region_current,
)
from hammunition.backends.source import DEFAULT_PREFIX
from hammunition.consent import (
    ConsentDeclined,
    ConsentUnavailable,
    resolve_consent,
    resolve_repo_consent,
)
from hammunition.country_boundaries import BoundarySource, CountryBoundaryError, boundary_source
from hammunition.desktop import current_desktop, scan_sessions
from hammunition.distro import DetectionError, Target
from hammunition.execute import (
    Step,
    already_built,
    artifact_removal_steps,
    build_dir,
    build_effects_present,
    commands_for,
    execute,
    run_removal,
    user_groups,
)
from hammunition.fetch import Fetcher
from hammunition.geofabrik import (
    BASE,
    GeofabrikError,
    Probe,
    RegionFile,
    UrllibProbe,
    current_pinned_snapshots,
    load_countries,
    load_pins,
    region_ids,
)
from hammunition.geofabrik import resolve as resolve_region
from hammunition.hardware.polkit import HELPER_PATH, POLICY_PATH, describe_refusal
from hammunition.interface import envelope
from hammunition.kernel import KernelProbe
from hammunition.manifest.hardware import DeviceClass, DeviceManifest
from hammunition.manifest.load import CatalogError, load_catalog, load_profiles
from hammunition.manifest.schema import (
    AptInstall,
    BinaryInstall,
    DerivedDataInstall,
    PackageManifest,
    ProfileManifest,
    RegionalDataInstall,
)
from hammunition.paths import applications_dir, build_root, node_root, user_bin_dir, venv_root
from hammunition.plan import NO_MAP_REGIONS, Blocker, InstallPlan, PlanError, resolve
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
    Station,
    StationError,
    config_path,
    is_interactive,
    load_station,
    prompt_for,
    save_station,
)
from hammunition.update import region_snapshots, render, report, requested_units
from hammunition.upstream import (
    NOT_UPSTREAM,
    http_get,
    parse_ls_remote,
    probe_upstream,
)
from hammunition.upstream import render as render_upstream

if TYPE_CHECKING:
    from hammunition.hardware.power import KeptEntry, Parkable
    from hammunition.upstream import UpstreamRow

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
    built: frozenset[str] = frozenset(),
    maps: MapDisclosure | None = None,
    terrain: TerrainDisclosure | None = None,
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

    Rendered from :class:`hammunition.interface.plan.InstallPlanView`, the same
    object ``install --dry-run --json`` emits (D-059), so the two cannot drift.
    """
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view

    view = build_install_view(
        plan,
        commands,
        euid=euid,
        log_destination=log_destination,
        hands_log_to=hands_log_to,
        built=built,
        maps=maps,
        terrain=terrain,
    )
    return render_plan_view(view, target=target_view(plan.target))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@envelope.json_capable()
def cmd_list(args: argparse.Namespace) -> int:
    from hammunition.interface.catalog import build_catalog, detect_target, render_catalog

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    doc = build_catalog(args.what, packages, profiles, detect_target())
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_catalog(doc):
        print(line)
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


@envelope.json_capable()
def cmd_status(args: argparse.Namespace) -> int:
    """What this machine is, what the catalog holds, and what has been done here.

    The most recent transaction is reported by how it actually ended, not by
    what it intended: reading only transaction_begin once reported a run that
    died on package 3 of 20 as if all 20 landed.
    """
    from hammunition.interface.status import build_status, render_status

    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"Target: unidentified — {exc}", file=sys.stderr)
        return EXIT_FAILED

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    log = TransactionLog(owner=operator(args) or None)
    doc = build_status(
        target=target,
        catalog_root=catalog_root,
        packages=packages,
        profiles=profiles,
        log_path=log.path,
        entries=list(log.read()),
    )
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_status(doc):
        print(line)
    return EXIT_OK


@envelope.json_capable()
def cmd_station_show(args: argparse.Namespace) -> int:
    """What is saved, and where. Says plainly when nothing is."""
    from hammunition.interface.station import build_station, render_station

    user = operator(args)
    try:
        station = load_station(owner=user)
    except StationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    doc = build_station(config_path(user), station)
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_station(doc):
        print(line)
    return EXIT_OK


def cmd_station_set(args: argparse.Namespace) -> int:
    user = operator(args)
    try:
        current = load_station(owner=user)
    except StationError:
        current = Station()
    # Checked before "nothing to set" and whether or not other flags are
    # given (fix round 1, M1): splitting "," or "" on ',' and stripping each
    # piece can legitimately produce zero regions -- a trailing comma, a
    # stray space, an empty string typed by habit -- and saving that
    # silently as "no regions" is indistinguishable from having meant it.
    # `--map-regions` is for setting regions, never for clearing them.
    if args.map_regions is not None:
        map_regions = tuple(r for r in (p.strip() for p in args.map_regions.split(",")) if r)
        if not map_regions:
            print(
                "error: --map-regions gave no regions after splitting on ',' and "
                "stripping whitespace; give at least one region, or to remove the "
                "maps, uninstall osm-navit and osm-regions.",
                file=sys.stderr,
            )
            return EXIT_FAILED
    else:
        map_regions = current.map_regions
    set_fields = [
        field
        for field, value in (
            ("callsign", args.callsign),
            ("grid_square", args.grid_square),
            ("node_alias", args.node_alias),
            ("map_regions", args.map_regions),
            ("map_freshness", args.map_freshness),
        )
        if value
    ]
    if not set_fields:
        print(
            "error: nothing to set. Pass at least one of --callsign, --grid-square, "
            "--node-alias, --map-regions, --map-freshness.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    try:
        station = Station(
            callsign=args.callsign or current.callsign,
            grid_square=args.grid_square or current.grid_square,
            node_alias=args.node_alias or current.node_alias,
            map_regions=map_regions,
            map_freshness=args.map_freshness or current.map_freshness,
        )
    except StationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    path = save_station(station, owner=user)
    print(f"Saved to {path} (mode 0600).")
    for field in sorted(set_fields):
        if field == "map_regions":
            print(f"  {field:<14} {len(station.map_regions)} set")
        elif field == "map_freshness":
            print(f"  {field:<14} {station.freshness}")
        else:
            print(f"  {field:<14} {station.get(field)}")
    return EXIT_OK


def _apt_lists_note(apt: AptBackend) -> str:
    """When the local package lists were last fetched, as a disclosure.

    The report compares against the archive as those lists describe it; a
    laptop that last ran `apt-get update` before a trip is comparing against
    the archive of that day, and the line says which day.
    """
    if not apt.lists_populated():
        return "no package lists fetched; every apt row above is comparing against nothing"
    newest = max(
        (entry.stat().st_mtime for entry in apt.lists_dir.iterdir() if "_Packages" in entry.name),
        default=None,
    )
    if newest is None:
        return "no package lists fetched; every apt row above is comparing against nothing"
    when = datetime.fromtimestamp(newest, tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return f"last refreshed {when} (`sudo apt-get update` refreshes them; this report does not)"


@envelope.json_capable()
def cmd_update(args: argparse.Namespace) -> int:
    """Installed versus the catalog, as a report. D-053: nothing runs."""
    from hammunition.interface.update import build_update

    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if not target.is_debian_family:
        print(f"error: {target.describe()} is not Debian-family.", file=sys.stderr)
        return EXIT_FAILED

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    runner = SubprocessRunner()
    apt = AptBackend(runner)
    user = operator(args)
    read_log = TransactionLog(owner=user or None)

    names = list(dict.fromkeys(args.names))
    from_log = not names
    if not names:
        names = list(requested_units(read_log.read()))
        if not names:
            if envelope.wanted(args):
                envelope.emit(
                    build_update(
                        target,
                        report(
                            InstallPlan(target=target, packages=()),
                            apt_states={},
                            present={},
                            built=(),
                        ),
                        lists_note=_apt_lists_note(apt),
                        from_log=True,
                        upstream=None,
                    )
                )
                return EXIT_OK
            print(f"Target: {target.describe()}")
            print(
                "Nothing to compare: the transaction log records no install request here "
                f"({read_log.path}). Name units or profiles to compare them anyway."
            )
            return EXIT_OK
        print(f"Comparing the {len(names)} unit(s) the transaction log has ever named here.")

    try:
        station = load_station(owner=user)
    except StationError:
        station = Station()
    repos = AptRepoBackend(owner=user or None)
    try:
        plan = resolve(
            names,
            catalog=packages,
            profiles=profiles,
            target=target,
            apt=apt,
            user=user,
            station=station,
            repos=repos,
            kernel=KernelProbe.detect(),
            desktops=scan_sessions(),
            log=read_log,
        )
    except PlanError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "\nNothing was compared. The report resolves the request the way install "
            "would, so a blocker here is the same blocker install would meet.",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    builds = build_root(user or None)
    source = SourceBackend(Fetcher(owner=user or None), build_root=builds, owner=user or None)
    git = GitBackend(
        runner=runner,
        build_root=builds,
        prefix=source.prefix,
        jobs=source.jobs,
        owner=source.owner,
    )
    binary = BinaryBackend(
        fetcher=source.fetcher,
        runner=runner,
        build_root=builds,
        prefix=source.prefix,
        owner=source.owner,
    )
    built = already_built(
        plan, log=read_log, prefix=source.prefix, source=source, git=git, binary=binary
    )
    present = {
        planned.name: build_effects_present(planned, prefix=source.prefix)
        for planned in plan.packages
        if build_dir(planned, source=source, git=git, binary=binary) is not None
    }
    apt_names: list[str] = []
    for planned in plan.packages:
        method = planned.block.install
        if isinstance(method, AptInstall):
            apt_names.extend(method.packages)
    try:
        states = apt.probe(list(dict.fromkeys(apt_names)))
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    # osm-regions, offline (D-053): each installed region's `.source`
    # sidecar against the pinned snapshot the station's own freshness mode
    # would resolve to today (fix round 1, I1) -- not the newest pin of any
    # snapshot, which reported a yearly install behind a monthly-shaped pin
    # forever. No fetch, no probe -- just what is on disk and what the
    # catalog carries.
    pins_path = catalog_root / "data" / "geofabrik-pins.yaml"
    current_pinned = (
        current_pinned_snapshots(
            station.freshness, date.today(), load_pins(pins_path), station.map_regions
        )
        if pins_path.is_file()
        else {}
    )
    regions_by_unit = {
        planned.name: region_snapshots(
            installed_slugs(data_root(source.prefix) / planned.name), current_pinned
        )
        for planned in plan.packages
        if isinstance(planned.block.install, RegionalDataInstall)
    }

    result = report(plan, apt_states=states, present=present, built=built, regions=regions_by_unit)
    lists_note = _apt_lists_note(apt)
    upstream = _upstream_rows(plan, runner) if args.upstream else None
    if envelope.wanted(args):
        envelope.emit(
            build_update(
                target, result, lists_note=lists_note, from_log=from_log, upstream=upstream
            )
        )
        return EXIT_OK
    print(f"Target: {target.describe()}")
    print(render(result, lists_note=lists_note, upstream_asked=bool(args.upstream)))
    if upstream is not None:
        print()
        print(render_upstream(upstream))
    return EXIT_OK


def _upstream_rows(plan: InstallPlan, runner: SubprocessRunner) -> list[UpstreamRow]:
    """D-053's second half: the catalog's pin against what upstream publishes.

    Opt-in because it is the one thing the engine does that talks to someone
    else's server. A GITHUB_TOKEN in the environment is sent to GitHub's API
    only, for the rate limit; tags come from `git ls-remote`, which needs no
    token on any host.
    """
    token = os.environ.get("GITHUB_TOKEN") or None

    def http(url: str) -> str:
        return http_get(url, token=token)

    def ls_remote(url: str) -> list[str]:
        result = runner.run(
            Command(
                argv=("git", "ls-remote", "--tags", "--refs", "--", url),
                description=f"List the tags at {url}",
                requires_root=False,
            )
        )
        if not result.ok:
            raise BackendError(f"git ls-remote exited {result.returncode}: {result.stderr.strip()}")
        return parse_ls_remote(result.stdout)

    rows = [
        probe_upstream(planned.manifest, http=http, ls_remote=ls_remote)
        for planned in plan.packages
    ]
    return [r for r in rows if r.state != NOT_UPSTREAM]


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


@envelope.json_capable()
def cmd_maps_regions(args: argparse.Namespace) -> int:
    """Every region Geofabrik's region index names, filtered by a substring.  D-057.

    Fetches the index only when this command runs -- network on request,
    like `update --upstream`, never as a side effect of any other command
    and never at import time. ``index-v1-nogeom.json`` (0.51 MB, measured
    2026-09-28) carries the same ``properties.urls.pbf`` shape
    :func:`hammunition.geofabrik.region_ids` reads as ``index-v1.json``
    (3.79 MB); fetching the smaller one is free (fix round 1, M6).
    """
    probe = UrllibProbe()
    try:
        index_json = probe.text(f"{BASE}/index-v1-nogeom.json")
        ids = region_ids(index_json)
    except GeofabrikError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    needle = (args.filter or "").casefold()
    matched = tuple(region for region in ids if needle in region.casefold())
    if envelope.wanted(args):
        from hammunition.interface.regions import RegionsDocument

        envelope.emit(RegionsDocument(filter=args.filter, regions=matched))
        return EXIT_OK
    for region in matched:
        print(region)
    return EXIT_OK


def _read_config_nofollow(path: Path) -> tuple[str, int | None]:
    """*path*'s text and mode, or ``("", None)`` when absent.

    Opened with ``O_NOFOLLOW``: a symbolic link in place of the file is
    refused, never read through and never renamed over, because what it
    points at is not a file this command created (the path-link.sh rule).
    Anything but a regular file is refused too. Raises :class:`OSError`
    with a message naming what was found.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if path.is_symlink():  # a dangling link: still not ours to replace
            raise OSError(f"{path} is a symbolic link; left as it is") from None
        return "", None
    except OSError as exc:
        if path.is_symlink():
            raise OSError(f"{path} is a symbolic link; left as it is") from None
        raise OSError(f"cannot read {path}: {exc.strerror or exc}") from None
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"{path} is not a regular file; left as it is")
        raw = handle.read()
    try:
        return raw.decode("utf-8"), stat.S_IMODE(info.st_mode)
    except UnicodeDecodeError:
        raise OSError(f"{path} is not UTF-8 text; left as it is") from None


def _replace_atomically(path: Path, text: str, mode: int | None) -> None:
    """Write *text* to a new file beside *path* and rename it over *path*.

    The temporary file is created exclusively (``mkstemp``) in the same
    directory, so the rename is atomic and nothing pre-planted at a fixed
    name is written through. An existing file's mode is kept; a new one is
    0600, as mkstemp creates it.
    """
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            if mode is not None:
                os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def cmd_maps_qmapshack(args: argparse.Namespace) -> int:
    """Name Hammunition's maps in QMapShack's own configuration, then start it.  D-061.

    What the ``qmapshack-offline`` launcher runs. Per-user: refused under
    root, whose configuration is not the operator's. Additive: a key is
    added or extended only with our directories, existing values stay where
    they are, and nothing else in the file changes; a file it cannot read,
    a symbolic link or anything but a regular file in its place is refused
    and left untouched, and QMapShack is then not started. No ``--json``
    form: it replaces itself with a GUI (D-059).
    """
    from hammunition.qmapshack_config import QmsConfigError, config_path, ensure_paths, wanted

    if os.geteuid() == 0:
        print(
            "error: QMapShack's configuration is per user; run this as yourself, not as root.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    path = config_path()
    not_started = "Nothing was changed and QMapShack was not started"
    try:
        text, mode = _read_config_nofollow(path)
    except OSError as exc:
        print(f"error: {exc}. {not_started}.", file=sys.stderr)
        return EXIT_FAILED
    try:
        updated = ensure_paths(text, wanted(data_root(DEFAULT_PREFIX)))
    except QmsConfigError as exc:
        print(
            f"error: {path}: {exc}. {not_started}; "
            f"add the directories in QMapShack's own setup, or move the file aside.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    if updated != text:
        print(
            f"adding Hammunition's map, elevation and routing directories to {path} "
            f"(existing entries kept)",
            file=sys.stderr,
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _replace_atomically(path, updated, mode)
        except OSError as exc:
            print(
                f"error: cannot write {path}: {exc.strerror or exc}. QMapShack was not started.",
                file=sys.stderr,
            )
            return EXIT_FAILED
    if args.configure_only:
        return EXIT_OK
    sys.stdout.flush()
    sys.stderr.flush()  # execvp discards whatever Python still buffers
    try:
        os.execvp("qmapshack", ["qmapshack"])
    except OSError as exc:
        print(
            f"error: cannot start qmapshack: {exc.strerror or exc}. "
            f"`hammunition install qmapshack` installs it.",
            file=sys.stderr,
        )
    return EXIT_FAILED


def cmd_maps_gps_tether(args: argparse.Namespace) -> int:
    """Serve gpsd's NMEA on 127.0.0.1:10110 for QMapShack's GPS Tether.  D-061.

    Loopback only, one client at a time, and only while the operator runs
    it; the argv is a fixed list, never a shell line. No ``--json`` form:
    it replaces itself with ``socat`` (D-059).
    """
    from hammunition.gps_tether import instructions, tether_argv

    print(instructions())
    sys.stdout.flush()  # execvp discards whatever Python still buffers
    try:
        os.execvp("socat", tether_argv())
    except OSError as exc:
        print(
            f"error: cannot start socat: {exc.strerror or exc}. "
            f"`hammunition install socat gpsd-clients` installs it and gpspipe.",
            file=sys.stderr,
        )
    return EXIT_FAILED


def resolve_map_regions(
    plan: InstallPlan,
    station: Station,
    catalog_root: Path,
    *,
    probe: Probe,
    today: date,
    installed: Path,
) -> MapResolution:
    """The station's map regions as dated, verifiable Geofabrik files.  D-057.

    Asked only when the plan holds a map unit -- the plan has already
    deferred or refused them when no regions are set -- and before the plan
    prints, because the dated file, its size and how it is verified are the
    disclosure.

    A region that cannot be resolved (offline, Geofabrik down, a 404) but is
    already installed under *installed* is kept as it is, and the plan says
    so (spec §8: no network leaves installed regions untouched). One that is
    not installed cannot be kept; every such region is named together in one
    :class:`GeofabrikError`.

    A **pinned** region resolves entirely from the pin list, no network
    asked at all (fix round 1, I3): offline, that looked like success, apt
    ran, and only then did the actual fetch fail, mid-transaction. So every
    region about to be fetched -- not already installed at its resolved
    snapshot, pinned or not -- is also HEAD-checked here, before the plan
    ever prints; a region already installed keeps today's behaviour and is
    never probed.
    """
    wanted = any(
        isinstance(p.block.install, RegionalDataInstall | DerivedDataInstall) for p in plan.packages
    )
    if not wanted or not station.map_regions:
        return MapResolution()
    notes: list[str] = []
    pins_path = catalog_root / "data" / "geofabrik-pins.yaml"
    if pins_path.is_file():
        pins = load_pins(pins_path)
    else:
        pins = {}
        notes.append(
            f"no Geofabrik pin list at {pins_path}; every map region is verified by "
            f"Geofabrik's MD5 only, and the plan says so beside each one."
        )
    files: list[RegionFile] = []
    kept: list[KeptRegion] = []
    refused: list[str] = []
    for region in station.map_regions:
        try:
            resolved = resolve_region(
                region, station.freshness, today=today, pins=pins, probe=probe
            )
        except (GeofabrikError, OSError) as exc:
            slug = region.replace("/", "-")
            pbf = installed / f"{slug}.osm.pbf"
            if pbf.is_file():
                kept.append(KeptRegion(region, slug, installed_snapshot(pbf), str(exc)))
            else:
                refused.append(f"  {region}: {exc}")
            continue
        pbf = installed / f"{resolved.slug}.osm.pbf"
        if not region_current(pbf, resolved):
            try:
                status, _, _ = probe.head(resolved.url)
                problem = (
                    None if status == 200 else f"{resolved.url} answered HTTP {status}, not 200"
                )
            except (GeofabrikError, OSError) as exc:
                # The probe's message already names the URL; not repeated.
                problem = str(exc)
            if problem is not None:
                # Spec §8: offline, an installed region stays installed. Only
                # a region with nothing installed is refused.
                if pbf.is_file():
                    kept.append(KeptRegion(region, resolved.slug, installed_snapshot(pbf), problem))
                else:
                    refused.append(f"  {region}: {problem}")
                continue
        files.append(resolved)
    if refused:
        raise GeofabrikError(
            f"{len(refused)} map region(s) could not be resolved and are not installed "
            f"already:\n" + "\n".join(refused)
        )
    return MapResolution(files=tuple(files), kept=tuple(kept), notes=tuple(notes))


def map_borders(
    plan: InstallPlan,
    catalog: Mapping[str, PackageManifest],
    catalog_root: Path,
    prefix: Path,
) -> tuple[BoundarySource | None, dict[str, tuple[str, ...]], list[str]]:
    """The country-border file and the region -> country table the Navit
    converter merges with (the address-search fix, D-057 amendment).

    Read at plan time with no network: the file is where the plan's
    ``boundaries`` unit installs it, and the table is
    ``catalog/data/geofabrik-countries.yaml``. A missing table is a note in
    the plan, and every region converts unmerged under -U; a boundaries
    unit of the wrong shape raises :class:`CountryBoundaryError`, which
    refuses the plan by name.
    """
    named = [
        p.block.install.boundaries
        for p in plan.packages
        if isinstance(p.block.install, DerivedDataInstall) and p.block.install.boundaries
    ]
    if not named:
        return None, {}, []
    unit = catalog.get(named[0])
    if unit is None:
        raise CountryBoundaryError(
            f"{named[0]} is named for country borders and is not in the catalog"
        )
    border = boundary_source(unit, prefix)
    table = catalog_root / "data" / "geofabrik-countries.yaml"
    if not table.is_file():
        return (
            border,
            {},
            [
                f"no region-to-country table at {table}, so no country border is merged: "
                f"every map converts with maptool -U alone, and address search files "
                f"its towns under Unknown."
            ],
        )
    try:
        return border, load_countries(table), []
    except GeofabrikError as exc:
        raise CountryBoundaryError(str(exc)) from exc


def map_work(
    plan: InstallPlan, regions: RegionsBackend, derived: DerivedBackend
) -> tuple[list[RegionFile], list[RegionFile]]:
    """(regions to download, regions to convert) for this plan."""
    downloads = [
        f
        for p in plan.packages
        if isinstance(p.block.install, RegionalDataInstall)
        for f in regions.pending(p.manifest)
    ]
    conversions = [
        f
        for p in plan.packages
        if isinstance(p.block.install, DerivedDataInstall)
        for f in derived.pending(p.manifest)
    ]
    return downloads, conversions


def leftover_maps_note(plan: InstallPlan, prefix: Path) -> str | None:
    """Map data still installed while no map regions are set, named with its removal."""
    units = sorted(d.subject for d in plan.deferrals if d.why == NO_MAP_REGIONS)
    found = [
        data_root(prefix) / unit
        for unit in units
        if any((data_root(prefix) / unit).glob("*.osm.pbf"))
        or any((data_root(prefix) / unit).glob("*.bin"))
    ]
    if not found:
        return None
    return (
        f"no map regions are set, and map data from an earlier install is still installed "
        f"under {', '.join(map(str, found))}. `hammunition uninstall {' '.join(units)}` "
        f"removes it; setting regions again keeps it current."
    )


def navit_config_blocker(plan: InstallPlan, stock: Path = navit_config.STOCK) -> str | None:
    """A Navit conversion with no Navit config to write from, found before it runs.

    The conversion can take hours; discovering at its end that
    ``/etc/navit/navit.xml`` is missing is the shape D-016 exists to prevent.
    Satisfied by the file being there, or by navit in this same transaction
    (apt runs before any conversion).
    """
    converting = [
        p.name
        for p in plan.packages
        if isinstance(p.block.install, DerivedDataInstall)
        and p.block.install.converter == "navit-maptool"
    ]
    if not converting or stock.is_file():
        return None
    if any(p.name == "navit" or "navit" in p.apt_packages for p in plan.packages):
        return None
    return (
        f"{', '.join(converting)} writes Navit's config from {stock}, which is not on this "
        f"machine, and navit is not in this transaction. Install navit first "
        f"(`hammunition install navit`), or ask for it in the same run."
    )


@envelope.json_capable(dry_run_only=True)
def cmd_install(args: argparse.Namespace) -> int:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import (
        PlanDocument,
        build_install_view,
        refused_plan,
        render_plan_view,
    )

    def refused(subject: str, reason: str) -> None:
        # A refusal after resolution is still a plan document, with the
        # reason the text printed (D-059); the exit code is unchanged.
        if envelope.wanted(args):
            envelope.emit(
                refused_plan("install", args.names, target_view(target), [Blocker(subject, reason)])
            )

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

    # The repository backend plans from the file system alone, so it is built
    # before resolve; its cache is the operator's, like every other fetch.
    repos = AptRepoBackend(owner=user or None)

    read_log = TransactionLog(owner=user or None)  # read-only until the plan is confirmed
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
            repos=repos,
            # The running kernel is a fact about this machine, not the target
            # (one Pop!_OS 24.04 VM has AX.25 under 7.0.11 and not under 7.1.5).
            kernel=KernelProbe.detect(),
            # Which desktops the session files offer (D-060): files on disk,
            # so the answer under sudo is the answer outside it.
            desktops=scan_sessions(),
            # Read-only here: whether a vendor .deb already on the machine is
            # ours to skip (#63). The same log is written to after the plan.
            log=read_log,
        )
    except PlanError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "\nNothing was changed. Resolution happens before installation so that a "
            "failure is a report rather than a half-installed machine (D-016).",
            file=sys.stderr,
        )
        if envelope.wanted(args):
            envelope.emit(refused_plan("install", args.names, target_view(target), exc.blockers))
        return EXIT_UNPLANNABLE
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    blocked = navit_config_blocker(plan)
    if blocked is not None:
        print(f"error: {blocked}", file=sys.stderr)
        print("\nNothing was changed.", file=sys.stderr)
        refused("navit configuration", blocked)
        return EXIT_UNPLANNABLE

    euid = os.geteuid()
    # The artifact cache and the build tree belong to the operator, not to root:
    # under sudo they would otherwise land in /root, invisible to the person who
    # asked for the build and re-downloaded on their next unprivileged run. Same
    # reasoning as the transaction log, and the same helper resolves both.
    builds = build_root(user or None)
    # An installed tree is handed to the same operator (D-043): MSHV and
    # radiosonde-auto-rx write beside their executables, and the hand-over is a
    # planned, logged step rather than a side effect of who unpacked the build.
    source = SourceBackend(Fetcher(owner=user or None), build_root=builds, owner=user or None)
    git = GitBackend(
        runner=runner,
        build_root=builds,
        prefix=source.prefix,
        jobs=source.jobs,
        owner=source.owner,
    )
    binary = BinaryBackend(
        fetcher=source.fetcher,
        runner=runner,
        build_root=builds,
        prefix=source.prefix,
        owner=source.owner,
    )
    venv = VenvBackend(
        venv_root=venv_root(user or None),
        bin_dir=user_bin_dir(user or None),
        fetcher=source.fetcher,
        build_root=builds,
        prefix=source.prefix,
        owner=source.owner,
    )
    node = NodeBackend(
        fetcher=source.fetcher,
        build_root=builds,
        node_root=node_root(user or None),
        bin_dir=user_bin_dir(user or None),
    )
    data = DataBackend(fetcher=source.fetcher, prefix=source.prefix, runner=runner)
    map_units = [p for p in plan.packages if isinstance(p.block.install, RegionalDataInstall)]
    try:
        resolution = resolve_map_regions(
            plan,
            station,
            catalog_root,
            probe=UrllibProbe(),
            today=date.today(),
            installed=data_root(source.prefix)
            / (map_units[0].name if map_units else "osm-regions"),
        )
    except GeofabrikError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("\nNothing was changed.", file=sys.stderr)
        refused("map regions", str(exc))
        return EXIT_UNPLANNABLE
    region_files = list(resolution.files)
    kept = frozenset(k.slug for k in resolution.kept)
    region_notes = list(resolution.notes)
    try:
        border, countries, border_notes = map_borders(plan, packages, catalog_root, source.prefix)
    except CountryBoundaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("\nNothing was changed.", file=sys.stderr)
        refused("country borders", str(exc))
        return EXIT_UNPLANNABLE
    region_notes.extend(border_notes)
    leftover = leftover_maps_note(plan, source.prefix)
    if leftover is not None:
        region_notes.append(leftover)
    # One ledger for both map backends: a region that did not install is not
    # converted, and the transaction ends naming every region that failed.
    ledger = MapLedger()
    regions = RegionsBackend(
        fetcher=source.fetcher,
        prefix=source.prefix,
        files=region_files,
        keep=kept,
        ledger=ledger,
        runner=runner,
    )
    # maptool runs as the operator into the operator's build tree; only the
    # install of its verified output into the prefix is privileged.
    map_staging = builds / "osm-navit"
    derived = DerivedBackend(
        prefix=source.prefix,
        files=region_files,
        keep=kept,
        staging=map_staging,
        ledger=ledger,
        owner=user or None,
        runner=runner,
        boundaries=border,
        countries=countries,
    )
    # Only regions not already installed at their snapshot are downloaded,
    # counted and listed as downloads (the dry run is the run); a region
    # installed but not yet converted still needs conversion space.
    pending, conversions = map_work(plan, regions, derived)
    changed = frozenset(
        slug
        for p in plan.packages
        if isinstance(p.block.install, DerivedDataInstall)
        for slug in derived.converter_changed(p.manifest)
    )
    maps = (
        resolution.disclosure(
            pending,
            conversions,
            boundaries=border,
            # As the converter will resolve them, parent paths included.
            countries={f.region: derived.codes_for(f) for f in region_files},
            converter_changed=changed,
        )
        if any(
            isinstance(p.block.install, RegionalDataInstall | DerivedDataInstall)
            for p in plan.packages
        )
        else None
    )
    if pending or conversions:
        # Refused at plan time, before anything is confirmed, with both numbers.
        short = disk_shortfall(
            disk_needs(
                pending,
                conversions,
                cache=source.fetcher.cache_dir,
                staging=map_staging,
                prefix=source.prefix,
            )
        )
        if short is not None:
            print(f"error: {short}", file=sys.stderr)
            print("\nNothing was changed.", file=sys.stderr)
            refused("disk space", short)
            return EXIT_UNPLANNABLE
    # D-051: a build present on disk that the log attributes to this engine
    # at the manifest's pin is already installed; its build steps are skipped.
    built = already_built(
        plan, log=read_log, prefix=source.prefix, source=source, git=git, binary=binary
    )
    commands = commands_for(
        plan,
        apt,
        refresh=args.refresh,
        skip_builds=built,
        source=source,
        git=git,
        binary=binary,
        venv=venv,
        node=node,
        data=data,
        regions=regions,
        derived=derived,
        repos=repos,
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
    view = build_install_view(
        plan,
        commands,
        euid=euid,
        built=built,
        log_destination=log_destination,
        hands_log_to=hands_log_to,
        suggestion_notes=suggestion_notes,
        maps=maps,
        region_notes=region_notes,
    )
    if envelope.wanted(args):
        # Reached only with --dry-run: main() refuses a real install under
        # --json before this command runs (D-059).
        envelope.emit(
            PlanDocument(
                action="install",
                requested=tuple(args.names),
                outcome="planned",
                target=target_view(target),
                blockers=(),
                install=view,
                removal=None,
            )
        )
        return EXIT_OK
    for note in (*suggestion_notes, *region_notes):
        print(f"note: {note}")
    for line in render_plan_view(view, target=target_view(plan.target)):
        print(line)

    print(
        "\nAfterwards: the Hammunition menu is re-applied for this user "
        "(per-user files, unprivileged, D-050)."
    )
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

    # One gate per repository, after the profile gates and under the same
    # rules: the environment answer is the pinned fingerprint itself, so an
    # automation that affirms it has necessarily read the disclosure. D-040.
    for addition in plan.apt_repos:
        try:
            record = resolve_repo_consent(
                addition.repo,
                addition.unit,
                sources=addition.sources,
                keyring=addition.keyring,
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
        launcher_bin=user_bin_dir(user or None),
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
        for line in refresh_menus_after_install(catalog_root):
            print(line)
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
    stale = stale_lists_diagnosis(report.failed, report.stderr)
    if stale:
        print(f"\n{stale}", file=sys.stderr)
    print(
        f"{len(report.completed)} command(s) completed before the failure and are "
        f"recorded in {log.path}. Hammunition does not roll back; it tells you what "
        f"it did (D-004).",
        file=sys.stderr,
    )
    return EXIT_FAILED


def stale_lists_diagnosis(failed: Command | Action, stderr: str) -> str | None:
    """What a 404 from ``apt-get install`` means, in the operator's terms.

    The plan's candidate check passed against the package lists on disk;
    the archive has since replaced a version those lists name; apt asked for
    the old file and was told it is gone. The catalog was right and the
    machine is unchanged -- apt fetches every archive before it unpacks
    any, so a fetch failure leaves nothing half-installed -- and the fix is
    the one apt itself hints at under the URLs. Six of fifteen profiles on
    a four-day-old Parrot guest failed exactly this way (2026-09-03), each
    report ending in seven ``Failed to fetch`` lines and no diagnosis.
    """
    if isinstance(failed, Action) or "apt-get" not in failed.argv or "install" not in failed.argv:
        return None
    missing = stale_fetches(stderr)
    if not missing:
        return None
    shown = ", ".join(missing[:3]) + (f" and {len(missing) - 3} more" if len(missing) > 3 else "")
    return (
        f"The package lists on this machine are older than the archive: apt asked for "
        f"{len(missing)} file(s) the mirror no longer has ({shown}). The plan resolved "
        f"against those lists, so the catalog is not at fault, and apt downloads every "
        f"archive before unpacking any, so this command installed nothing. Refresh the "
        f"lists and run the same install again: `sudo apt-get update`, or run without "
        f"--no-refresh so the transaction's own refresh does it first. If the refresh "
        f"did run, the mirror moved between the update and this fetch; run it again."
    )


@envelope.json_capable(dry_run_only=True)
def cmd_uninstall(args: argparse.Namespace) -> int:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import (
        BlockerLine,
        PlanDocument,
        build_removal_view,
        render_removal_view,
    )

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
        if envelope.wanted(args):
            envelope.emit(
                PlanDocument(
                    action="uninstall",
                    requested=tuple(args.names),
                    outcome="refused",
                    target=target_view(target),
                    blockers=(BlockerLine(subject="uninstall", reason=str(exc), remedy=None),),
                    install=None,
                    removal=None,
                )
            )
        return EXIT_UNPLANNABLE
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    euid = os.geteuid()
    commands: list[Step] = list(apt.remove_commands(plan.apt_packages))
    commands.extend(artifact_removal_steps(plan))
    if any(r.kind == "apt-repo" for removals in plan.artifacts.values() for r in removals):
        # The files are gone; apt's index still lists the repository until
        # it is read again. Same transaction, so `uninstall` leaves apt in
        # the state it found it (D-040).
        commands.append(apt.refresh_command())

    view = build_removal_view(plan, commands, euid=euid)
    if envelope.wanted(args):
        # Reached only with --dry-run (D-059).
        envelope.emit(
            PlanDocument(
                action="uninstall",
                requested=tuple(args.names),
                outcome="planned",
                target=target_view(target),
                blockers=(),
                install=None,
                removal=view,
            )
        )
        return EXIT_OK
    for line in render_removal_view(view, target=target_view(target)):
        print(line)
    if not commands:
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


def refresh_menus_after_install(catalog_root: Path) -> list[str]:
    """Re-apply the Hammunition menu for this user, quietly. D-050, round 3.

    After the full install on the field laptop, 42 of 60 tagged entries sat
    directly under *Hammunition*: placement happens at apply time, and the
    last apply predated the install. So a real install ends here. Per-user
    files only, unprivileged; a machine where no root menu can be decided
    gets a line saying so, never a failed install.
    """
    from hammunition.menus import (
        APPLICATIONS_DIR,
        LOCAL_APPLICATIONS_DIR,
        MenuPaths,
        MenuPrefixError,
        cli_entries,
        cli_entry_steps,
        decorate_entries,
        load_vocabulary,
        menu_steps,
        missing_launcher_steps,
        place_installed_entries,
        refresh_command,
        refresh_launcher_entries,
        resolve_menu_prefix,
    )

    home = Path.home()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    config_dirs = [
        Path(d) for d in (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":") if d
    ]
    try:
        prefix = resolve_menu_prefix(None, os.environ.get("XDG_MENU_PREFIX"), config_dirs)
    except MenuPrefixError as exc:
        return [
            f"Menu: not re-applied -- {exc}. Run `hammunition menus apply` in your desktop session."
        ]
    vocabulary = load_vocabulary(catalog_root / "categories.yaml")
    manifests, _ = load_all(catalog_root)
    hidden = vocabulary.hidden_categories
    placement = place_installed_entries(
        manifests.values(),
        applications_dir=APPLICATIONS_DIR,
        hidden=hidden,
        built_applications_dir=LOCAL_APPLICATIONS_DIR,
    )
    generated = cli_entries(manifests.values(), placement, hidden=hidden, prefix=DEFAULT_PREFIX)
    paths = MenuPaths(
        menus_dir=config_home / "menus", directories_dir=data_home / "desktop-directories"
    )
    applications = data_home / "applications"
    steps = menu_steps(
        vocabulary.categories,
        paths,
        menu_prefix=prefix,
        placement=placement,
        groups=vocabulary.groups,
    )
    steps += cli_entry_steps(generated, applications, vocabulary.icons)
    steps += missing_launcher_steps(
        manifests.values(),
        bin_dir=user_bin_dir(None),
        applications_dir=applications,
        prefix=DEFAULT_PREFIX,
    )
    steps += refresh_launcher_entries(manifests.values(), applications)
    steps += decorate_entries(applications, vocabulary.icons)
    for step in steps:
        step.perform()
    refresh = refresh_command(prefix)
    if refresh is not None:
        SubprocessRunner().run(refresh)
    placed = sum(len(v) for v in placement.by_category.values())
    return [
        f"Menu: re-applied for this user -- {len(placement.claimed)} entries placed "
        f"{placed} times, {len(generated.entries)} generated, {len(generated.skipped)} "
        f"without one (`hammunition menus apply` lists them)"
    ]


def cmd_menus_apply(args: argparse.Namespace) -> int:

    from hammunition.menus import (
        APPLICATIONS_DIR,
        LOCAL_APPLICATIONS_DIR,
        MenuPaths,
        MenuPrefixError,
        cli_entries,
        cli_entry_steps,
        decorate_entries,
        device_entries,
        device_entry_steps,
        gnome_commands,
        load_vocabulary,
        menu_steps,
        missing_launcher_steps,
        place_installed_entries,
        placement_summary,
        refresh_command,
        refresh_launcher_entries,
        resolve_menu_prefix,
    )

    catalog_root = find_catalog(args.catalog)
    vocabulary = load_vocabulary(catalog_root / "categories.yaml")
    categories, groups = vocabulary.categories, vocabulary.groups
    manifests, _ = load_all(catalog_root)
    hidden = vocabulary.hidden_categories
    placement = place_installed_entries(
        manifests.values(),
        applications_dir=APPLICATIONS_DIR,
        hidden=hidden,
        built_applications_dir=LOCAL_APPLICATIONS_DIR,
    )
    # D-050: every installed unit findable. Generated per user, beside the
    # launchers, from what dpkg says is on this machine's path.
    generated = cli_entries(manifests.values(), placement, hidden=hidden, prefix=DEFAULT_PREFIX)

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
    steps = menu_steps(categories, paths, menu_prefix=prefix, placement=placement, groups=groups)
    steps.extend(
        cli_entry_steps(generated, paths.directories_dir.parent / "applications", vocabulary.icons)
    )
    applications = paths.directories_dir.parent / "applications"
    steps.extend(
        missing_launcher_steps(
            manifests.values(),
            bin_dir=user_bin_dir(None),
            applications_dir=applications,
            prefix=DEFAULT_PREFIX,
        )
    )
    steps.extend(refresh_launcher_entries(manifests.values(), applications))
    steps.extend(decorate_entries(applications, vocabulary.icons))

    # D-050: a park/wake entry per catalogued device attached *today*. Built
    # from the same hardware match the CLI verbs use, so the menu never
    # offers a device that is not plugged in.
    classes, devices = _load_hardware_catalog(args)
    hw_entries: dict[str, DeviceClass | DeviceManifest] = {**classes, **devices}
    from hammunition.hardware.detect import match_catalog, read_usb_bus
    from hammunition.hardware.power import parkable as parkable_devices

    hw_matches, _ = match_catalog(read_usb_bus(), hw_entries)
    found, _ = parkable_devices(hw_matches, hw_entries)
    device_generated = device_entries(found, hw_entries, manifests, hidden)
    steps.extend(device_entry_steps(device_generated, applications, vocabulary.icons))

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    wants_gnome = "GNOME" in desktop.upper() or args.gnome
    placed = sum(len(v) for v in placement.by_category.values())
    print(
        f"Menu tree: {sum(g.menu for g in groups)} groups shown, {len(categories) - len(hidden)} categories, "
        f"menu prefix {prefix!r}; "
        f"{len(placement.claimed)} desktop entries from installed catalog packages "
        f"placed {placed} times by their manifests' categories (dpkg -L, checked on disk); "
        f"{len(generated.entries)} entries generated for installed units that ship none; "
        f"{len(device_generated)} power-control entries for parkable devices attached now"
    )
    for line in placement_summary(placement):
        print(line)
    for unit, why in generated.skipped:
        print(
            f"  {unit}: no entry generated -- {why}; a `launchers` block in its manifest is the fix"
        )
    for step in steps:
        print(f"  {step.display()}")
        outcome = step.perform()
        print(f"    {outcome}")
    if wants_gnome:
        runner = SubprocessRunner()
        print("GNOME app-folder (needs your session bus):")
        for command in gnome_commands(placement, groups):
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
    refresh = refresh_command(prefix)
    if refresh is not None:
        print(f"  # {refresh.description}\n  $ {' '.join(refresh.argv)}")
        result = SubprocessRunner().run(refresh)
        if result.returncode != 0:
            print(
                f"warning: {refresh.argv[0]} exited {result.returncode}; the menu shows at next login"
            )
        print("Done.")
    else:
        print("Done. Menus refresh on next login (or `xfce4-panel -r` / GNOME Shell reload).")
    return EXIT_OK


@envelope.json_capable()
def cmd_show(args: argparse.Namespace) -> int:
    """Print a profile, its consent disclosure included, without installing it.

    Under --json a unit's name is accepted too, and emits its manifest (D-059);
    the text form describes profiles only, as it always has.
    """
    from hammunition.interface.catalog import (
        build_profile,
        build_unit,
        detect_target,
        render_profile,
    )

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    profile = profiles.get(args.profile)
    if profile is None:
        manifest = packages.get(args.profile)
        if manifest is not None and envelope.wanted(args):
            envelope.emit(build_unit(manifest, detect_target()))
            return EXIT_OK
        print(f"error: no profile named {args.profile!r}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    doc = build_profile(profile)
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_profile(doc):
        print(line)
    return EXIT_OK


def _prompt(text: str) -> bool:
    """Yes/no on the terminal. Anything that is not an explicit yes is a no."""
    print(text)
    try:
        answer = input("Type 'yes' to continue: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"yes", "y"}


def _confirm_unsafe_interpreter(paths: list[str]) -> bool:
    """A typed `yes`, never `--yes` (D-021, D-056's ruling as amended).

    Installing the helper is never refused for this — it is the normal shape
    of a venv the operator owns — but it is asked at the keyboard every time,
    and a convenience flag cannot answer it.

    ``paths`` may name more than one offending component (the interpreter and
    the package tree can both be non-root-owned at once). Every one of them is
    disclosed, because a partial disclosure is not a disclosure. The answer is
    `yes`, not the path typed back: the path is printed directly above the
    prompt, so retyping it proved nothing a `yes` does not (2026-09-27
    amendment; D-040's fingerprint stays typed, because checking it against
    the vendor's published value is the point there).
    """
    joined = "\n".join(f"  {p}" for p in paths)
    print(
        f"\nWritable only by the account that owns it, not by root (the ordinary "
        f"shape of a venv the operator created; never refused for this alone):\n"
        f"{joined}\n"
        f"The polkit action about to be installed lets root run code reached "
        f"through one of these. Any active local session can authenticate once "
        f"and run it as root for a few minutes afterwards (auth_self_keep). "
        f"This is not refused, but `--yes` does not satisfy it."
    )
    try:
        answer = input("Proceed? [yes/no]: ").strip().lower()
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
            "Nothing to do: the rules file already matches, you are in every access "
            "group, and the power-control helper and its polkit action are already "
            "installed. Hardware setup is complete."
        )
        return EXIT_OK

    def build_commands(staging_root: str) -> tuple[list[Command], Command | None, Command | None]:
        """Commands as they would look staged under ``staging_root``.

        Called twice: once with a placeholder string for the disclosure and
        ``--dry-run`` preview, before any staging directory exists, and once
        for real with the actual `mkdtemp()` path once every gate below has
        been passed. Fix round 2: `--dry-run` must be a true no-op, and the
        old code called `mkdtemp()` -- a real filesystem side effect -- before
        the dry-run check even ran.
        """
        built: list[Command] = []
        if not plan.rules_already_current:
            built += [
                Command(
                    argv=(
                        "install",
                        "-D",
                        "-m",
                        "0644",
                        f"{staging_root}/udev-staging.rules",
                        str(plan.rules_path),
                    ),
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
        helper_cmd: Command | None = None
        policy_cmd: Command | None = None
        if not plan.polkit.helper_current:
            helper_cmd = Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0755",
                    f"{staging_root}/hammunition-devctl",
                    plan.polkit.helper_path,
                ),
                description=f"Install the power-control helper to {plan.polkit.helper_path}",
                requires_root=True,
            )
            built.append(helper_cmd)
        if not plan.polkit.policy_current:
            policy_cmd = Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    f"{staging_root}/devctl.policy",
                    plan.polkit.policy_path,
                ),
                description=(f"Install the polkit action authorising {plan.polkit.helper_path}"),
                requires_root=True,
            )
            built.append(policy_cmd)
        for group in plan.groups_to_add:
            built.append(
                Command(
                    argv=("gpasswd", "--add", user, group),
                    description=f"Add {user} to {group} for device access",
                    requires_root=True,
                )
            )
        return built, helper_cmd, policy_cmd

    if not plan.rules_already_current:
        print(f"Will write {len(plan.rules_content.splitlines())} lines to {plan.rules_path}")
    else:
        print(f"Rules file at {plan.rules_path} is already current.")
    if not plan.polkit.helper_current:
        print(
            f"Will install the privileged helper to {plan.polkit.helper_path}\n"
            f"  It execs {plan.polkit.interpreter} as root, through a polkit "
            f"action any active local session may satisfy once and keep "
            f"authorised for a few minutes afterwards "
            f"(allow_active=auth_self_keep)."
        )
    if not plan.polkit.policy_current:
        print(f"Will install the polkit action to {plan.polkit.policy_path}")
    for group in plan.groups_to_add:
        print(f"Will add {user!r} to the {group!r} group")

    preview_commands, preview_helper, preview_policy = build_commands("<staging>")
    installing_polkit = preview_helper is not None or preview_policy is not None
    """Whether this run installs *either* privileged artefact. Fix round 3:
    the helper and the policy are both routes to the same root-exec, and a
    policy-only apply (helper already current, only the action missing or
    stale) is the *worse* case, not a milder one -- installing the policy is
    exactly what turns an already-present helper into something an active
    session can authorise. Both refusal and confirmation below must gate on
    this, not on the helper alone."""
    euid = os.geteuid()
    print(f"\nCommands ({len(preview_commands)}):")
    for command in preview_commands:
        print(f"  # {command.description}")
        print(f"  $ {command.display(euid=euid)}")

    # Fix round 3: evaluated *before* the dry-run return, not after, so a
    # dry run on an unsafe tree reports the refusal a real run would give
    # rather than printing the full plan and exiting 0 -- CLAUDE.md's
    # "--dry-run must be complete and accurate, not approximate."
    #
    # Fix round 2: round 1 conflated "any local account can write it" with
    # "one specific non-root account owns it" into a single refusal, and a
    # devctl startup check that hard-refused on either broke the project's
    # own documented install -- a venv under $HOME is *always* non-root-owned.
    # Only the group/other-writable case is the actual escalation, and only
    # that one is refused outright, here at apply time.
    if installing_polkit and plan.polkit.must_refuse:
        print(
            f"error: refusing to install: {describe_refusal(plan.polkit.refusing_findings)}. "
            f"That is the escalation this project refuses outright rather than merely "
            f"confirms -- fix it, then re-run `hardware apply`.",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK

    # D-056's ruling: never refuse a wrapper that bakes in an interpreter or
    # package tree one non-root account owns — that is the normal shape of a
    # venv this project's own operator owns — but never let `--yes` wave it
    # through either (D-021). Asked at the keyboard, and only when either
    # privileged artefact is actually about to be (re)written. A yes here is
    # also the yes to the commands, so the operator is asked once, not twice.
    asked = installing_polkit and plan.polkit.needs_confirmation
    if asked and not _confirm_unsafe_interpreter(plan.polkit.confirmable_paths):
        print("Aborted: not confirmed. Nothing was changed.", file=sys.stderr)
        return EXIT_CONSENT

    if not asked and not args.yes and not _prompt("\nProceed with the commands above?"):
        print("Aborted. Nothing was changed.")
        return EXIT_OK

    # Only now, past every gate that could still end the run with nothing
    # written, does a staging directory actually get created. A fixed name
    # under the shared /tmp is not safe here: a privileged `install` command
    # reads back from this directory, and a predictable path lets a local
    # attacker pre-create it — /tmp's sticky bit does not protect a
    # subdirectory *they* own — and race our write, landing their own content
    # 0755 at the exact path polkit authorises. The D-031 readback further
    # down would only ever catch that after the bad file was already
    # installed as root. mkdtemp's name cannot be guessed in advance, and its
    # 0700 mode keeps every other account out entirely.
    staging_dir = Path(tempfile.mkdtemp(prefix="hammunition-hardware-"))
    try:
        commands, helper_command, policy_command = build_commands(str(staging_dir))

        if not plan.rules_already_current:
            staging = staging_dir / "udev-staging.rules"
            staging.write_text(plan.rules_content)
            os.chmod(staging, 0o644)
        if helper_command is not None:
            helper_staging = staging_dir / "hammunition-devctl"
            helper_staging.write_text(plan.polkit.helper_content)
            os.chmod(helper_staging, 0o755)
        if policy_command is not None:
            policy_staging = staging_dir / "devctl.policy"
            policy_staging.write_text(plan.polkit.policy_content)
            os.chmod(policy_staging, 0o644)

        runner = SubprocessRunner()
        print("\nRunning:")
        for command in commands:
            print(f"  $ {command.display(euid=euid)}")
            result = runner.run(command)
            if result.returncode != 0:
                print(f"error: {result.stderr.strip()[:300]}", file=sys.stderr)
                print("Stopped. What ran above is applied; the rest is not.", file=sys.stderr)
                return EXIT_FAILED

            # Recorded per artefact as soon as its own command succeeds, not
            # batched to the end: a later command in this same run (the
            # policy install, a gpasswd call) can still fail without leaving
            # an unrecorded root-owned file that `unapply` would then report
            # as nothing to remove. Logged *before* the D-031 readback below,
            # not after: a file the install really wrote but whose content we
            # then failed to confirm is exactly the file `unapply` most needs
            # to be able to remove -- fix round 2's residual on F4.
            if command is helper_command:
                TransactionLog(owner=user).append(
                    {
                        "event": "hardware_artifacts",
                        "version": 1,
                        "files": [{"path": plan.polkit.helper_path, "mode": "0755"}],
                    }
                )
                try:
                    matches = (
                        Path(plan.polkit.helper_path).read_text() == plan.polkit.helper_content
                    )
                except OSError as exc:
                    print(
                        f"  unverified: could not read back {plan.polkit.helper_path}: {exc}",
                        file=sys.stderr,
                    )
                    return EXIT_FAILED
                if not matches:
                    print(
                        f"  unverified: {plan.polkit.helper_path} on disk does not match "
                        f"what we wrote",
                        file=sys.stderr,
                    )
                    return EXIT_FAILED
            if command is policy_command:
                TransactionLog(owner=user).append(
                    {
                        "event": "hardware_artifacts",
                        "version": 1,
                        "files": [{"path": plan.polkit.policy_path, "mode": "0644"}],
                    }
                )
                try:
                    matches = (
                        Path(plan.polkit.policy_path).read_text() == plan.polkit.policy_content
                    )
                except OSError as exc:
                    print(
                        f"  unverified: could not read back {plan.polkit.policy_path}: {exc}",
                        file=sys.stderr,
                    )
                    return EXIT_FAILED
                if not matches:
                    print(
                        f"  unverified: {plan.polkit.policy_path} on disk does not match "
                        f"what we wrote",
                        file=sys.stderr,
                    )
                    return EXIT_FAILED

        # D-031 for the rules file and group membership. The polkit
        # artefacts were already verified — and logged — individually above,
        # as soon as their own command ran.
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
                f"Group membership ({', '.join(plan.groups_to_add)}) takes effect at "
                f"your next login — log out and back in before expecting device access."
            )
        return EXIT_OK
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def cmd_hardware_unapply(args: argparse.Namespace) -> int:
    """Remove the privileged artefacts an apply installed, and nothing else.

    Not part of ``uninstall``: that command resolves names against the package
    and profile catalogs and there is no unit named ``hardware`` to give it
    (D-056). This removes exactly what the transaction log records *we* put
    there -- never a path we merely expect to exist, because a file at the
    helper's path that we did not write belongs to whoever did.

    **Narrower still: only a path this command owns.** ``--user`` lets an
    operator read *another* account's transaction log, which that account can
    append to freely -- so a log is data, not an instruction, and a `path`
    entry in it is honoured only when it is exactly the helper or the policy
    path. Anything else the log names is reported and skipped, never removed,
    because a root ``rm -f`` for an arbitrary string an unprivileged account
    once wrote into its own log file is not a promise this command makes.

    The device-access udev rules file (D-029) is deliberately left alone. It
    is declarative, it is harmless for a device that is not attached, and
    removing it would take away device access an operator is still using.
    Power control is the reversible part; permissions are not.

    **The kept-off rules file (D-056) is different and is removed here.** It
    exists only because ``park`` was told to keep a device parked, and its
    entries are power-control intent, not permissions -- so if it is present
    it is removed along with the helper and the policy action, and udev is
    told to reload so every device it was holding parked wakes from the next
    boot.
    """
    from hammunition.hardware import RULES_PATH
    from hammunition.hardware.power import KEPT_RULES

    user = operator(args)
    if not user:
        print("error: could not determine whose transaction log to read.", file=sys.stderr)
        return EXIT_FAILED

    kept_present = Path(KEPT_RULES).exists()
    owned = {HELPER_PATH, POLICY_PATH}
    recorded: list[str] = []
    skipped: list[str] = []
    for entry in TransactionLog(owner=user).read():
        if entry.get("event") != "hardware_artifacts":
            continue
        files = entry.get("files")
        if not isinstance(files, list):
            # A malformed *known* event, not an unknown one -- state/log.py's
            # tolerance promise covers readers skipping events they don't
            # recognise, not a reader trusting the shape of one it does.
            continue
        for item in files:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not isinstance(path, str):
                continue
            if path not in owned:
                if path not in recorded and path not in skipped:
                    skipped.append(path)
                continue
            if path not in recorded:
                recorded.append(path)

    if not recorded and not skipped and not kept_present:
        print(
            "Nothing to remove: the transaction log records no hardware artefacts "
            "installed by Hammunition for this user."
        )
        return EXIT_OK

    for path in skipped:
        print(
            f"Skipped: the log names {path!r}, which this command does not own "
            f"(only the power-control helper and its polkit action are ever removed)."
        )
    if not recorded and not kept_present:
        print("Nothing to do: no artefact this command owns is recorded.")
        return EXIT_OK

    present = [p for p in recorded if Path(p).exists()]
    gone = [p for p in recorded if p not in present]
    for path in gone:
        print(f"Already absent: {path}")
    if not present and not kept_present:
        print("Nothing to do: every recorded artefact is already gone.")
        return EXIT_OK

    commands = [
        Command(
            argv=("rm", "-f", path),
            description=f"Remove the power-control artefact at {path}",
            requires_root=True,
        )
        for path in present
    ]
    if kept_present:
        commands.append(
            Command(
                argv=("rm", "-f", KEPT_RULES),
                description="Remove the kept-off entries, so every device wakes from the next boot",
                requires_root=True,
            )
        )
        commands.append(
            Command(
                argv=("udevadm", "control", "--reload"),
                description="Reload udev's rules",
                requires_root=True,
            )
        )
        present.append(KEPT_RULES)
    euid = os.geteuid()
    print(f"\nCommands ({len(commands)}):")
    for command in commands:
        print(f"  # {command.description}")
        print(f"  $ {command.display(euid=euid)}")
    if kept_present:
        print(
            f"\nRemoving {KEPT_RULES} removes the whole file, including any line in it "
            f"that Hammunition did not write."
        )
    print(
        f"\nThe device-access rules file, {RULES_PATH}, is not touched: it is "
        f"declarative, harmless for a device that is not attached, and removing it "
        f"would take away device access you are still using."
    )

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK
    if not args.yes and not _prompt("\nProceed with the commands above?"):
        print("Aborted. Nothing was changed.")
        return EXIT_OK

    runner = SubprocessRunner()
    print("\nRunning:")
    for command in commands:
        print(f"  $ {command.display(euid=euid)}")
        result = runner.run(command)
        if result.returncode != 0:
            print(f"error: {result.stderr.strip()[:300]}", file=sys.stderr)
            return EXIT_FAILED

    # D-031: `rm` exiting 0 is not evidence the file is gone.
    still_there = [p for p in present if Path(p).exists()]
    if still_there:
        for path in still_there:
            print(f"  unverified: {path} is still present", file=sys.stderr)
        return EXIT_FAILED

    after = []
    if any(p != KEPT_RULES for p in present):
        after.append("`hammunition hardware apply` reinstalls the helper and its polkit action.")
    if kept_present:
        after.append("Kept entries come back with `hammunition hardware park`.")
    print("\nDone and verified. " + " ".join(after))
    return EXIT_OK


def _survey_parkables(args: argparse.Namespace) -> tuple[list[Parkable], list[tuple[str, str]]]:
    """What is parkable, read unprivileged. The same survey the helper does.

    Reading sysfs and the catalog needs no privilege; only *writing* does. So
    `hardware state` answers without a prompt, and `park`/`wake` can refuse a
    name before raising an authentication dialog for something that was never
    going to work.
    """
    from hammunition.hardware.detect import match_catalog, read_usb_bus
    from hammunition.hardware.power import parkable

    classes, devices = _load_hardware_catalog(args)
    entries: dict[str, DeviceClass | DeviceManifest] = {**classes, **devices}
    matches, _ = match_catalog(read_usb_bus(), entries)
    return parkable(matches, entries)


def _kept_split(
    found: list[Parkable], kept: list[KeptEntry]
) -> tuple[list[tuple[Parkable, bool]], list[KeptEntry]]:
    """Each attached parkable with whether it is kept, and the kept entries
    with nothing attached.

    A device whose values will not validate as an entry is reported not kept
    and matched against nothing -- one odd device never drops the rest, the
    way devctl's ``state`` treats it.
    """
    from hammunition.hardware.power import PowerError, kept_entry

    rows: list[tuple[Parkable, bool]] = []
    mine: list[KeptEntry] = []
    for p in found:
        try:
            entry = kept_entry(p)
        except PowerError:
            rows.append((p, False))
            continue
        mine.append(entry)
        rows.append((p, any(e.same_device(entry) for e in kept)))
    absent = [e for e in kept if not any(e.same_device(m) for m in mine)]
    return rows, absent


@envelope.json_capable()
def cmd_hardware_state(args: argparse.Namespace) -> int:
    """Which catalogued devices can be parked, which are parked now, and which
    are kept parked across reboots — attached or not."""
    from hammunition.hardware.power import PowerError, read_kept
    from hammunition.interface.hardware import build_hardware, render_hardware

    found, skipped = _survey_parkables(args)
    kept_error: str | None = None
    try:
        kept = read_kept()
    except (OSError, PowerError) as exc:
        kept_error, kept = str(exc), []

    rows, absent = _kept_split(sorted(found, key=lambda p: (p.name, p.address)), kept)
    doc = build_hardware(rows, absent, skipped, kept_error)
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_hardware(doc):
        print(line)
    return EXIT_OK


def _power_verb(args: argparse.Namespace, verb: str) -> int:
    """Disclose the privileged call and every write it will cause, then run it."""
    from hammunition.hardware.power import (
        KEPT_RULES,
        PowerError,
        plan_forget,
        plan_park,
        plan_wake,
        read_kept,
    )

    helper = Path(HELPER_PATH)
    if not helper.is_file():
        print(
            f"error: the privileged helper is not installed at {HELPER_PATH}.\n"
            f"`hammunition hardware apply` installs it, together with the polkit "
            f"action that authorises it.",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE
    if shutil.which("pkexec") is None:
        print(
            "error: pkexec is not on PATH, so the privileged helper cannot be "
            "authorised. It comes from the `polkit` package (`pkexec` is in "
            "`policykit-1` on Debian-family targets). Without it, park and wake "
            "have no way to escalate; `hammunition hardware state` still works, "
            "because reading sysfs needs no privilege.",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE

    found, skipped = _survey_parkables(args)
    for unit, why in skipped:
        print(f"note: {unit} is not parkable right now — {why}", file=sys.stderr)
    from hammunition.cli.devctl import attached_named, resolve_kept
    from hammunition.cli.devctl import resolve as resolve_parkable

    keep = not getattr(args, "until_reboot", False)
    absent = False
    try:
        try:
            target = resolve_parkable(args.name, found)
        except PowerError:
            if verb != "wake" or attached_named(args.name, found):
                raise
            entry = resolve_kept(args.name, read_kept())
            plan = plan_forget(entry)
            absent = True
            label, address, summary = entry.name, entry.address, "not attached"
        else:
            plan = plan_park(target, keep=keep) if verb == "park" else plan_wake(target)
            label, address, summary = target.name, target.address, target.summary
    except PowerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE

    argv = ["pkexec", HELPER_PATH, verb]
    if verb == "park" and not keep:
        argv.append("--until-reboot")
    argv.append(f"{label}@{address}")
    command = Command(argv=tuple(argv), description=f"{verb.capitalize()} {label} at {address}")
    print(f"{verb.capitalize()}ing {label} ({summary}) at {address}\n")
    if plan.writes:
        print("Writes this will cause:")
        for write in plan.writes:
            print(f"  {write.path} <- {write.value}")
    if plan.keep is not None:
        print(f"\nIt stays parked across reboots. Added to {KEPT_RULES}:")
        print(f"  {plan.keep.rule()}")
    elif verb == "park":
        print(
            f"\nA reboot wakes it (--until-reboot): no kept entry is written, and "
            f"any kept entry for it is removed from {KEPT_RULES}."
        )
    elif plan.forget is not None:
        note = "It is not attached, so this will only" if absent else "This will also"
        print(f"\n{note} remove its kept entry from {KEPT_RULES}, if present.")
    print(f"\n  # {command.description}\n  $ {command.display()}")

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK

    try:
        result = SubprocessRunner().run(command)
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if result.returncode in (126, 127):
        print(
            "The authentication prompt was dismissed; nothing was changed.",
            file=sys.stderr,
        )
        return EXIT_CONSENT
    if result.returncode == EXIT_UNPLANNABLE:
        print(result.stderr.strip() or "the helper refused the request", file=sys.stderr)
        return EXIT_UNPLANNABLE
    if result.returncode != 0:
        print(result.stderr.strip()[:400] or f"helper exited {result.returncode}", file=sys.stderr)
        return EXIT_FAILED
    print(f"\nDone and verified. `hammunition hardware state` shows {label} now.")
    return EXIT_OK


def cmd_hardware_park(args: argparse.Namespace) -> int:
    """Detach a device and keep it parked across reboots, unless --until-reboot."""
    return _power_verb(args, "park")


def cmd_hardware_wake(args: argparse.Namespace) -> int:
    """Bring a parked device back."""
    return _power_verb(args, "wake")


# ---------------------------------------------------------------------------
# doctor — a read-only health check
# ---------------------------------------------------------------------------


@envelope.json_capable()
def cmd_doctor(args: argparse.Namespace) -> int:
    """Report what is ready and what is not yet set up. Changes nothing."""
    import shutil

    from hammunition.doctor import ROUTINO_TRANSLATIONS, run_checks, writable_or_creatable
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

    # This checkout's entry point: src/hammunition/cli/main.py -> the checkout
    # root is three parents above the package. Resolved, so a ~/.local/bin
    # link to it compares equal (D-059).
    checkout = Path(__file__).resolve().parents[3]
    engine_expected = str((checkout / ".venv" / "bin" / "hammunition").resolve())
    found_engine = shutil.which("hammunition")
    engine_on_path = str(Path(found_engine).resolve()) if found_engine else None
    # Where it was found, unresolved, and whether that is ~/.local/bin, so doctor
    # offers the relink only for our own link there and never for a file it
    # would clobber or one that shadows it from earlier on PATH.
    engine_found_in_local_bin = (
        found_engine is not None
        and Path(found_engine).parent.resolve() == Path(local_bin).resolve()
    )
    engine_found_link = (
        os.readlink(found_engine) if found_engine and Path(found_engine).is_symlink() else None
    )

    # bootstrap's own link in ~/.local/bin, whether or not that is on PATH yet:
    # a fresh account has the link before its next login puts the dir on PATH.
    linked = Path(local_bin) / "hammunition"
    engine_linked_in_local_bin = linked.is_symlink() and str(linked.resolve()) == engine_expected

    kept_attached: tuple[str, ...] = ()
    kept_absent: tuple[str, ...] = ()
    try:
        from hammunition.hardware.power import PowerError, read_kept

        found, _skipped = _survey_parkables(args)
        kept = read_kept()
        _rows, absent = _kept_split(found, kept)
        attached_now = [f"{e.name}@{e.address}" for e in kept if e not in absent]
        absent_now = [f"{e.name}@{e.address}" for e in absent]
        kept_attached = tuple(attached_now)
        kept_absent = tuple(absent_now)
    except (OSError, PowerError, CatalogError, SystemExit):
        kept_attached, kept_absent = (), ()

    sessions = scan_sessions()
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
        engine_on_path=engine_on_path,
        engine_expected=engine_expected,
        engine_found=found_engine,
        engine_found_in_local_bin=engine_found_in_local_bin,
        engine_found_link=engine_found_link,
        engine_linked_in_local_bin=engine_linked_in_local_bin,
        kept_attached=kept_attached,
        kept_absent=kept_absent,
        desktops_installed=sessions.desktops,
        sessions_unrecognised=sessions.unrecognised,
        desktop_current=current_desktop(os.environ),
        qmapshack_without_translations=(
            shutil.which("qmapshack") is not None and not Path(ROUTINO_TRANSLATIONS).is_file()
        ),
    )

    from hammunition.interface.doctor import build_doctor, render_doctor

    doc = build_doctor(checks)
    if envelope.wanted(args):
        envelope.emit(doc)
    else:
        for line in render_doctor(doc):
            print(line)
    return EXIT_FAILED if doc.fails else EXIT_OK


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _engine_version() -> str:
    """The installed package version, or a marker when running uninstalled."""
    return envelope.engine_version()


def _add_json_flag(parser: argparse.ArgumentParser, *, top: bool) -> None:
    """``--json`` on the top-level parser and on every subcommand, recursively.

    Accepted on both sides of the verb, ``hammunition --json status`` and
    ``hammunition status --json``. A subcommand's copy defaults to SUPPRESS,
    so an absent flag after the verb does not overwrite one given before it.
    Walked rather than listed, so a verb added later carries it without
    anyone remembering to (D-059).
    """
    parser.add_argument(
        "--json",
        action="store_true",
        default=False if top else argparse.SUPPRESS,
        help="print one JSON document on stdout instead of text (docs/reference/json-interface.md)",
    )
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                _add_json_flag(child, top=False)


def _disallow_abbrev(parser: argparse.ArgumentParser) -> None:
    """No abbreviated long option is ever accepted, here or on any
    subcommand, recursively.  D-059 (review round 1, Important 2).

    ``allow_abbrev`` defaults to True, so without this `--js` or `--dr`
    would silently stand in for `--json` or `--dry-run`. That is a real gate
    to defeat: `main()` separately routes on the *parsed* value of
    ``args.json`` rather than a text scan of argv, but a CLI that guards a
    real install and every consent gate behind an exact flag should not
    depend on that alone. ``allow_abbrev`` is a plain instance attribute
    argparse reads at parse time, so setting it after construction (as every
    subparser here is already built) works the same as passing it in.
    """
    parser.allow_abbrev = False
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                _disallow_abbrev(child)


def _json_requested(arguments: list[str]) -> bool:
    """Whether ``--json`` was actually given -- immune to abbreviation, and
    to every other flag this CLI defines -- with no side effect (no help
    text, no version, no exit).  D-059 (review round 1, Important 2).

    Used by `main()` to route before touching stdout, so it must not risk
    printing anything: a full parse of ``--help``/``--version`` writes to
    stdout before this function could know whether to redirect it. A tiny
    parser that knows only ``--json`` (`add_help=False`, so `-h`/`--help`
    is not even registered; `allow_abbrev=False`, so `--js` matches
    nothing) is the actual parsed answer to "did the operator ask for
    JSON", not a guess from scanning the raw tokens the old code used.
    """
    probe = _Probe(add_help=False, allow_abbrev=False)
    probe.add_argument("--json", action="store_true", default=False)
    try:
        parsed, _ = probe.parse_known_args(arguments)
    except _ProbeError:
        # `--json=VALUE`: the exact flag with a value it does not take. It is
        # a request for JSON all the same, so `_main_json` reports the full
        # parser's own error as a document (final review, Minor 1) rather
        # than the probe exiting 2 with nothing on stdout.
        return True
    return bool(parsed.json)


class _ProbeError(Exception):
    """The `--json` probe could not parse its one flag."""


class _Probe(argparse.ArgumentParser):
    """A parser whose errors raise instead of printing usage and exiting."""

    def error(self, message: str) -> NoReturn:
        raise _ProbeError(message)


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

    p_update = sub.add_parser(
        "update",
        help="installed versus the catalog, as a report; nothing runs (D-053)",
    )
    p_update.add_argument(
        "names",
        nargs="*",
        help="units or profiles to compare; default: everything the log says was installed here",
    )
    p_update.add_argument("--user", default=None, help="whose log and builds to read")
    p_update.add_argument(
        "--upstream",
        action="store_true",
        help=(
            "also ask upstream (GitHub, git tags, PyPI, a version file) whether the "
            "catalog's pin is current; the only network the report uses"
        ),
    )
    p_update.set_defaults(func=cmd_update)

    p_maps = sub.add_parser(
        "maps", help="offline maps: Geofabrik's regions (D-057), QMapShack and its GPS (D-061)"
    )
    maps_sub = p_maps.add_subparsers(dest="maps_command", required=True)

    p_maps_regions = maps_sub.add_parser(
        "regions",
        help="list Geofabrik's region paths; fetches the index only when run",
    )
    p_maps_regions.add_argument(
        "filter",
        nargs="?",
        default=None,
        help="case-insensitive substring to match; default: every region",
    )
    p_maps_regions.set_defaults(func=cmd_maps_regions)

    p_maps_qms = maps_sub.add_parser(
        "qmapshack",
        help="add Hammunition's maps to your QMapShack configuration, then start it (D-061)",
    )
    p_maps_qms.add_argument(
        "--configure-only",
        action="store_true",
        help="edit the configuration and do not start QMapShack",
    )
    p_maps_qms.set_defaults(func=cmd_maps_qmapshack)

    p_maps_tether = maps_sub.add_parser(
        "gps-tether",
        help="serve gpsd's NMEA on 127.0.0.1:10110 for QMapShack's GPS Tether (D-061)",
    )
    p_maps_tether.set_defaults(func=cmd_maps_gps_tether)

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
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "run `apt-get update` as the first command of the transaction, when the "
            "transaction has apt work (the default; D-044). --no-refresh skips it: a "
            "local mirror, or a station with no uplink"
        ),
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
        "apply", help="write the Hammunition menu tree; on GNOME one app-folder per group"
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

    p_hw_unapply = hardware_sub.add_parser(
        "unapply", help="remove the power-control helper and polkit action (D-056)"
    )
    p_hw_unapply.add_argument(
        "--dry-run", action="store_true", help="print what would be removed, then stop"
    )
    p_hw_unapply.add_argument("--yes", action="store_true", help="skip the confirmation")
    p_hw_unapply.add_argument(
        "--user",
        default=None,
        help="operator whose transaction log to read (default: $SUDO_USER, else $USER)",
    )
    p_hw_unapply.set_defaults(func=cmd_hardware_unapply)

    p_hw_state = hardware_sub.add_parser(
        "state", help="which devices can be parked, and which are parked now"
    )
    p_hw_state.set_defaults(func=cmd_hardware_state)

    for verb, helptext in (
        ("park", "detach a device and let its port suspend (D-056)"),
        ("wake", "bring a parked device back"),
    ):
        p_verb = hardware_sub.add_parser(verb, help=helptext)
        p_verb.add_argument(
            "name",
            metavar="NAME",
            help="catalog name, or NAME@ADDRESS when two of a kind are attached",
        )
        p_verb.add_argument(
            "--dry-run",
            action="store_true",
            help="print the privileged call and every write it would cause, then stop",
        )
        if verb == "park":
            p_verb.add_argument(
                "--until-reboot",
                action="store_true",
                help="park now, but let a reboot wake it (no kept entry)",
            )
        p_verb.set_defaults(func=cmd_hardware_park if verb == "park" else cmd_hardware_wake)

    p_station = sub.add_parser("station", help="the values only you can supply")
    station_sub = p_station.add_subparsers(dest="station_command", required=True)

    p_station_show = station_sub.add_parser("show", help="print the saved station values")
    p_station_show.add_argument("--user", default=None, help="whose configuration to read")
    p_station_show.set_defaults(func=cmd_station_show)

    p_station_set = station_sub.add_parser("set", help="save station values")
    p_station_set.add_argument("--callsign", default=None)
    p_station_set.add_argument("--grid-square", default=None)
    p_station_set.add_argument("--node-alias", default=None)
    p_station_set.add_argument(
        "--map-regions",
        default=None,
        help="comma-separated Geofabrik regions to carry offline maps for",
    )
    p_station_set.add_argument(
        "--map-freshness", default=None, choices=("yearly", "monthly", "latest")
    )
    p_station_set.add_argument("--user", default=None, help="whose configuration to write")
    p_station_set.set_defaults(func=cmd_station_set)

    _add_json_flag(parser, top=True)
    _disallow_abbrev(parser)
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    """Run the chosen command, turning operator-input errors into exit codes."""
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


def _exit_code(exc: SystemExit) -> int:
    """The status the interpreter would exit with for *exc*."""
    if exc.code is None:
        return EXIT_OK
    if isinstance(exc.code, int):
        return exc.code
    return EXIT_FAILED  # SystemExit("message") prints it and exits 1


def _main_json(arguments: list[str]) -> int:
    """``--json``: exactly one document on stdout, on every path.  D-059.

    Both standard streams point at a recording tee over the real stderr
    while the command runs, so nothing it prints can reach stdout; the
    document goes to the real stdout through :func:`envelope.emit`. A run
    that ends without one gets an error document with the same exit code.
    """
    real_stdout, real_stderr = sys.stdout, sys.stderr
    tee = envelope.Tee(real_stderr)
    sys.stdout = sys.stderr = cast(TextIO, tee)
    envelope.begin(real_stdout)
    try:
        try:
            args = build_parser().parse_args(arguments)
        except SystemExit as exc:
            code = _exit_code(exc)
            if code == EXIT_OK:
                return EXIT_OK  # --help or --version: printed to stderr, not a document
            envelope.emit(
                envelope.ErrorDocument(command="", exit_code=code, message=tee.text().strip())
            )
            return code
        command = envelope.command_name(args)
        why = envelope.refusal(args)
        if why is not None:
            # Bare `hammunition --json` keeps bare `hammunition`'s exit 0
            # (final review, Minor 2): no command is not a refused command.
            code = EXIT_OK if getattr(args, "func", None) is None else EXIT_UNPLANNABLE
            print(f"error: {why}", file=sys.stderr)
            envelope.emit(
                envelope.ErrorDocument(command=command, exit_code=code, message=tee.text().strip())
            )
            return code
        try:
            code = _dispatch(args)
        except SystemExit as exc:
            code = _exit_code(exc)
            if isinstance(exc.code, str):
                print(exc.code, file=sys.stderr)
        except Exception:
            # A bug in a command, or emit() itself raising -- json.dumps on
            # a non-serialisable field, say -- must not leave stdout empty
            # (review round 1, Important 1): the module's own promise is
            # "stdout parses as exactly one document on every path", and
            # `_dispatch` only catches CatalogError, StationError and
            # KeyboardInterrupt. The traceback goes to the real stderr
            # through the tee, loud rather than silently swallowed;
            # KeyboardInterrupt keeps its existing handling in `_dispatch`.
            traceback.print_exc(file=sys.stderr)
            code = EXIT_FAILED
        if not envelope.emitted():
            envelope.emit(
                envelope.ErrorDocument(command=command, exit_code=code, message=tee.text().strip())
            )
        return code
    finally:
        envelope.end()
        sys.stdout, sys.stderr = real_stdout, real_stderr


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
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _json_requested(arguments):
        return _main_json(arguments)
    parser = build_parser()
    args = parser.parse_args(arguments)
    if not getattr(args, "func", None):
        # Bare `hammunition`: print the top-level help and exit cleanly, which
        # is friendlier than argparse's "command is required" error for someone
        # running it for the first time. (Group verbs keep required sub-verbs,
        # so `hammunition hardware` still gets argparse's standard message.)
        parser.print_help()
        return EXIT_OK
    return _dispatch(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
