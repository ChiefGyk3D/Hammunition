# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan as data: what ``install`` and ``uninstall`` will do.  D-059.

:func:`build_install_view` turns a resolved :class:`~hammunition.plan.InstallPlan`
and its steps into an :class:`InstallPlanView`; :func:`render_plan_view` prints
it, byte for byte what ``render_plan`` printed before the view existed (the
golden text test holds that); ``install --dry-run --json`` emits it inside a
:class:`PlanDocument`. The removal side is the same shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from hammunition.backends import Action
from hammunition.backends.data import human_size
from hammunition.backends.dem import TerrainDisclosure
from hammunition.backends.regions import ESTIMATE, MapDisclosure, bin_estimate
from hammunition.backends.terrain import (
    CONTOUR_BYTES,
    CONTOUR_SCRATCH_BYTES,
    GARMIN_FACTOR,
    MEASURED,
    ROUTINO_FACTOR,
    garmin_estimate,
    routino_estimate,
)
from hammunition.consent import repo_env_var
from hammunition.desktop import Desktop, describe_set
from hammunition.execute import Step
from hammunition.geofabrik import PINNED, RegionFile
from hammunition.interface.envelope import Strict, TargetView, described
from hammunition.interface.text import wrap
from hammunition.manifest.schema import (
    AptInstall,
    BinaryInstall,
    DataInstall,
    DemTilesInstall,
    DerivedDataInstall,
    GitInstall,
    NodeInstall,
    RegionalDataInstall,
    SourceInstall,
    VenvInstall,
)
from hammunition.plan import Blocker, InstallPlan, PlannedPackage
from hammunition.state import RemovalPlan

__all__ = [
    "PlanDocument",
    "build_install_view",
    "build_removal_view",
    "plan_state",
    "refused_plan",
    "render_plan_view",
    "render_removal_view",
]

NOT_REVERSED = (
    "Not reversed, by design: dependencies apt pulled in (run "
    "`sudo apt autoremove` to clear orphans), group memberships, and any "
    "config files written — all recorded in the transaction log (D-004)."
)


def plan_state(
    planned: PlannedPackage,
    built: frozenset[str] = frozenset(),
    maps: MapDisclosure | None = None,
    terrain: TerrainDisclosure | None = None,
) -> str:
    """What the plan will do to this unit, in two words.

    "already installed" is apt's answer and only apt's: it means every apt
    package the block names is present. A source or binary unit's apt list is
    its build dependencies, or nothing at all, so for those it was saying
    "already installed" one line above a build -- sdrangel's .deb block on
    the Ubuntu 26.04 VM read that way (2026-09-02). The one carve-out is a
    vendor .deb the plan has attributed to this engine and dpkg still holds
    (#63): nothing is planned for it, and the line says so.

    The map units answer from the map disclosure, so this line and the Map
    regions section cannot disagree (bench, 2026-09-28): ``osm-regions`` is
    "already installed" when every selected region is installed and current,
    nothing to fetch and none that could not be checked; ``osm-navit`` when,
    on top of that, no map is left to convert. With no disclosure the plan
    knows nothing about the regions, and the method's wording stands.

    Piece 2's units (D-061) answer from the terrain disclosure the same way:
    ``dem-copernicus`` when no tile is fetched, each converter when it has
    nothing to build this run.
    """
    method = planned.block.install
    if maps is not None and (maps.current or maps.kept or maps.fetch):
        regions_current = not maps.fetch and not maps.kept
        if isinstance(method, RegionalDataInstall) and regions_current:
            return "already installed"
        if (
            isinstance(method, DerivedDataInstall)
            and method.converter == "navit-maptool"
            and regions_current
            and not maps.convert
        ):
            return "already installed"
    if terrain is not None:
        if isinstance(method, DemTilesInstall) and not terrain.resolution.fetch:
            return "already installed"
        if isinstance(method, DerivedDataInstall):
            idle = {
                "mkgmap": not terrain.garmin,
                "routino-planetsplitter": not terrain.routino_regions,
                "gdal-dem": not terrain.drawing,
            }
            if idle.get(method.converter, False):
                return "already installed"
    if isinstance(method, AptInstall):
        return "already installed" if not planned.outstanding else "will install"
    if isinstance(method, BinaryInstall) and planned.deb_installed:
        return "already installed"
    if planned.name in built:
        return "already installed"  # built at this pin, D-051
    if isinstance(method, SourceInstall | GitInstall):
        return "will build"
    if isinstance(method, VenvInstall):
        return "will install"  # into its own venv, reported by the venv step
    if isinstance(method, NodeInstall):
        return "will build"
    if isinstance(method, DerivedDataInstall):
        return "will convert"
    return "will fetch+install"


@dataclass(frozen=True)
class AptLine(Strict):
    """One apt package a unit resolves to."""

    package: str = described("the apt package name")
    outstanding: bool = described("not installed yet; `+` in the text, `=` when already present")
    build_only: bool = described("a build dependency, not the software asked for")


@dataclass(frozen=True)
class PackageLine(Strict):
    """One catalog unit in the plan."""

    name: str = described("the catalog unit")
    method: str = described("the install method of the block that resolved here")
    state: str = described(
        "`will install`, `will build`, `will fetch+install`, `will convert` or `already installed`; "
        "a map unit reads `already installed` only when the map section says nothing is left to do"
    )
    requested_by: tuple[str, ...] = described(
        "`requested`, or the profiles and units that pulled it in"
    )
    apt: tuple[AptLine, ...] = described(
        "the apt packages it resolves to, build dependencies included"
    )


@dataclass(frozen=True)
class DisplacedLine(Strict):
    """An installed distribution package a unit displaces or shadows (D-022)."""

    package: str = described("the distribution package, which stays installed")
    declared_by: str = described("the unit whose manifest declares the conflict")


@dataclass(frozen=True)
class ReleaseSection(Strict):
    """apt packages taken from another release this machine installs from (D-038)."""

    release: str = described("the `--target-release` the apt step runs with")
    packages: tuple[str, ...] = described("the packages that come from that release")


@dataclass(frozen=True)
class NoRecommendsSection(Strict):
    """apt packages installed by a second command without Recommends (D-052)."""

    units: tuple[str, ...] = described("the units whose manifests asked for it")
    packages: tuple[str, ...] = described("the packages that second command installs")


@dataclass(frozen=True)
class RepoLine(Strict):
    """A third-party apt repository the transaction adds, behind its own gate (D-040)."""

    name: str = described("the repository's name, which names its two files")
    unit: str = described("the unit that needs it")
    packages: tuple[str, ...] = described("the apt packages it is expected to supply")
    uri: str = described("the archive URI")
    suites: tuple[str, ...] = described("apt suites")
    components: tuple[str, ...] = described("apt components")
    key_fingerprint: str = described("the pinned signing-key fingerprint")
    sources: str = described("the .sources file written")
    keyring: str = described("the keyring file written")
    consent_env_var: str = described("must equal the key fingerprint for a scripted run")


@dataclass(frozen=True)
class DataArtifactLine(Strict):
    """One file of an offline dataset."""

    url: str = described("where it is fetched from")
    size: int = described("bytes, as declared and verified on fetch")
    size_human: str = described("the size as the text prints it")


@dataclass(frozen=True)
class DataLine(Strict):
    """An offline-data unit: sizes and licence, before anything downloads (D-049)."""

    unit: str = described("the data unit")
    total_size: int = described("bytes, every artifact together")
    total_human: str = described("the total as the text prints it")
    licence: str = described("the licence the data is under")
    licence_url: str = described("where that licence is stated")
    artifacts: tuple[DataArtifactLine, ...] = described("each file fetched")
    installs_under: str = described("where it is installed, relative to the prefix")


@dataclass(frozen=True)
class RegionLine(Strict):
    """One map region file."""

    region: str = described("the Geofabrik region path")
    snapshot: str = described("the dated snapshot")
    size: int = described("bytes")
    size_human: str = described("the size as the text prints it")
    verified_by: str = described("how the download is checked")
    nothing_to_do: bool = described("already installed and not being converted")


@dataclass(frozen=True)
class ConvertLine(Strict):
    """A region converted for Navit this run."""

    region: str = described("the Geofabrik region path")
    snapshot: str = described("the dated snapshot")
    estimate: int = described("bytes the converted map is estimated to take")
    estimate_human: str = described("that estimate as the text prints it")
    countries: tuple[str, ...] = described(
        "ISO 3166-1 alpha-2 codes whose closed border is merged into the region first; "
        "empty when none is known or there is no boundary file"
    )
    converter_changed: bool = described(
        "converted again only because an older converter built the installed map"
    )


@dataclass(frozen=True)
class BoundaryLine(Strict):
    """The country-border file merged into each region before conversion."""

    title: str = described("what the file is")
    url: str = described("where it is fetched from")
    size: int = described("bytes, as declared and verified on fetch")
    size_human: str = described("the size as the text prints it")
    licence: str = described("the licence the data is under")
    verified_by: str = described("how the download is checked")


@dataclass(frozen=True)
class KeptLine(Strict):
    """An installed region that could not be checked for a newer map; kept."""

    region: str = described("the Geofabrik region path")
    snapshot: str | None = described("the installed snapshot, when recorded")
    reason: str = described("why it could not be checked")


@dataclass(frozen=True)
class TerrainRegionLine(Strict):
    """The terrain tiles one region needs (D-061)."""

    region: str = described("the Geofabrik region path")
    tiles: int = described("tiles that exist for its outline")
    sea: int = described("squares of its outline with no tile: sea")
    download: int = described(
        "bytes of its tiles downloaded this run; a tile two regions share counts in both"
    )
    download_human: str = described("as the text prints it")


@dataclass(frozen=True)
class TileLine(Strict):
    """One terrain tile downloaded this run."""

    tile: str = described("the Copernicus GLO-30 tile name; it encodes a latitude and longitude")
    size: int = described("bytes")
    size_human: str = described("the size as the text prints it")
    verified_by: str = described("how the download is checked")


@dataclass(frozen=True)
class GarminLine(Strict):
    """A region mkgmap builds a Garmin map from this run."""

    region: str = described("the Geofabrik region path")
    snapshot: str = described("the dated snapshot")
    estimate: int = described("bytes the map is estimated to take")
    estimate_human: str = described("that estimate as the text prints it")


@dataclass(frozen=True)
class TerrainSectionView(Strict):
    """Terrain, and what is built for QMapShack (D-061). Names where the operator is: local only."""

    regions: tuple[TerrainRegionLine, ...] = described("tiles per region")
    fetch: tuple[TileLine, ...] = described("tiles downloaded this run")
    current: int = described("tiles already installed")
    licence: str = described("the elevation data's licence")
    licence_url: str = described("where it is stated")
    download_total: int = described("bytes of tiles downloaded")
    download_total_human: str = described("as the text prints it")
    garmin: tuple[GarminLine, ...] = described("Garmin maps built this run")
    routino_regions: int = described("regions the Routino database is rebuilt over; 0 when current")
    routino_estimate: int = described("bytes the rebuilt database is estimated to take")
    routino_estimate_human: str = described("as the text prints it")
    contours: int = described("tiles whose contours are drawn this run")
    contours_estimate: int = described("bytes those contours are estimated to take")
    contours_estimate_human: str = described("as the text prints it")
    disk_total: int = described("bytes: the tiles plus everything estimated to be built")
    disk_total_human: str = described("as the text prints it")
    estimate_note: str = described("how the estimates were measured")


@dataclass(frozen=True)
class MapSectionView(Strict):
    """The station's map regions (D-057). Names where the operator is: local only."""

    fetch: tuple[RegionLine, ...] = described("downloaded and installed this run")
    current: tuple[RegionLine, ...] = described("already installed at the resolved snapshot")
    convert: tuple[ConvertLine, ...] = described("converted for Navit this run")
    kept: tuple[KeptLine, ...] = described("could not be checked; the installed copy stays")
    licence: str = described("the map data's licence")
    licence_url: str = described("where it is stated")
    download_total: int = described("bytes downloaded")
    download_total_human: str = described("as the text prints it")
    disk_total: int = described("bytes: the download plus the estimated converted maps")
    disk_total_human: str = described("as the text prints it")
    estimate_note: str = described("how the conversion estimate was measured")
    terrain: TerrainSectionView | None = described(
        "terrain tiles and QMapShack's maps (D-061); null when no terrain unit is planned"
    )
    boundaries: BoundaryLine | None = described(
        "the country-border file merged into each region with osmium merge before "
        "maptool; null when the converter has none"
    )
    unknown_country: bool = described(
        "maptool runs with -U: a town outside every country boundary is indexed under "
        "the pseudo-country Unknown instead of being dropped"
    )


@dataclass(frozen=True)
class MembershipLine(Strict):
    """A group the operator is added to, and what it grants."""

    user: str = described("the account added")
    group: str = described("the group")
    package: str = described("the unit that needs it")
    detail: str = described("what membership grants")
    reverse_hint: str | None = described("how to undo it by hand, when the manifest says")


@dataclass(frozen=True)
class GateLine(Strict):
    """A consent gate the real run will present (D-021). Never answered through JSON."""

    profile: str = described("the gated profile")
    env_var: str = described("the scripted-consent variable the gate reads")
    risk_lines: tuple[str, ...] = described("one line per disclosed capability")


@dataclass(frozen=True)
class ConfigLine(Strict):
    """A configuration file the transaction writes."""

    unit: str = described("the unit whose manifest templates it")
    path: str = described("the file written")
    mode: str = described("its octal mode")
    append: bool = described("appended to rather than written")
    backup_existing: bool = described("an existing file is backed up first")


@dataclass(frozen=True)
class DesktopsReadView(Strict):
    """What the session files said, when a unit in the request is for particular desktops (D-060)."""

    desktops: tuple[str, ...] = described(
        "the desktops the catalog knows that the session files offer (`kde`, `xfce`, ...)"
    )
    unrecognised: tuple[str, ...] = described(
        "session files read that named no desktop the catalog knows (`cosmic.desktop`)"
    )
    summary: str = described("the line the text prints under the heading")


@dataclass(frozen=True)
class DeferralLine(Strict):
    """Part of the request that will not happen; the rest still does (D-035, D-039, D-060)."""

    kind: str = described(
        "`config` (a file not written) or `package` (a member not installed: the target lacks it, "
        "or, D-060, the machine has no session for the desktop it is for)"
    )
    subject: str = described("what is deferred")
    what: str = described("what will not happen")
    why: str = described("what is missing")
    remedy: str = described("what the operator can do about it")


@dataclass(frozen=True)
class RecordsLine(Strict):
    """Where the transaction log is written."""

    log: str = described("the transaction log file")
    handed_to: str | None = described("the operator it is chowned to, under sudo")


@dataclass(frozen=True)
class StepView(Strict):
    """One step, exactly as the real run performs it."""

    description: str = described("why the step runs")
    display: str = described("the line the text prints after `$`, copy-pasteable")
    argv: tuple[str, ...] = described(
        "the argv executed, escalation applied; empty for an in-process step"
    )
    action: str | None = described(
        "the in-process step's kind (`fetch`, `extract`, ...); null for a command"
    )
    requires_root: bool = described("whether it runs as root")


@dataclass(frozen=True)
class InstallPlanView(Strict):
    """Everything an install will do, section by section as the text prints it."""

    packages: tuple[PackageLine, ...] = described("every unit, in the order it installs")
    displaced: tuple[DisplacedLine, ...] = described("distribution packages displaced or shadowed")
    apt_release: ReleaseSection | None = described("present when apt resolves from another release")
    no_recommends: NoRecommendsSection | None = described(
        "present when a unit opted out of Recommends"
    )
    repos: tuple[RepoLine, ...] = described("third-party repositories added")
    data: tuple[DataLine, ...] = described("offline data downloaded")
    maps: MapSectionView | None = described(
        "the station's map regions (D-057); null when no map unit or nothing to disclose"
    )
    memberships: tuple[MembershipLine, ...] = described("group membership changes")
    consent_gates: tuple[GateLine, ...] = described("gates the real run presents")
    config_files: tuple[ConfigLine, ...] = described("configuration written")
    desktops_read: DesktopsReadView | None = described(
        "present when a unit in the request is for particular desktops and the session files "
        "were read (D-060); null otherwise"
    )
    deferrals: tuple[DeferralLine, ...] = described("what will NOT happen")
    notes: tuple[str, ...] = described("the plan's notes")
    records: RecordsLine | None = described("where the transaction log goes")
    commands: tuple[StepView, ...] = described("every step, in order")
    suggestion_notes: tuple[str, ...] = described(
        "what happened to the profiles' suggestion groups; the text prints these as `note:` lines"
    )
    region_notes: tuple[str, ...] = described(
        "notes from resolving the map regions; the text prints these as `note:` lines"
    )


@dataclass(frozen=True)
class UnitPackages(Strict):
    """A unit and apt packages."""

    unit: str = described("the catalog unit")
    packages: tuple[str, ...] = described("apt packages")


@dataclass(frozen=True)
class UnitFiles(Strict):
    """A unit and files."""

    unit: str = described("the catalog unit")
    paths: tuple[str, ...] = described("files on disk")


@dataclass(frozen=True)
class ArtifactLine(Strict):
    """A file or tree the removal deletes, and why it is this engine's to delete."""

    unit: str = described("the catalog unit")
    kind: str = described("`venv`, `tree`, `binary`, `wrapper`, `desktop-entry` or `apt-repo`")
    path: str = described("what is removed")
    basis: str = described("`namespaced`, `log` or `marker`: how it is known to be ours")


@dataclass(frozen=True)
class RemovalPlanView(Strict):
    """Everything an uninstall will do, section by section as the text prints it."""

    to_remove: tuple[UnitPackages, ...] = described("apt packages removed, per unit")
    artifacts: tuple[ArtifactLine, ...] = described("files and trees removed")
    left_unattributed: tuple[UnitFiles, ...] = described(
        "present, but the log does not attribute it"
    )
    left_foreign: tuple[UnitPackages, ...] = described("installed, but not by this engine")
    already_absent: tuple[UnitPackages, ...] = described("nothing to remove")
    not_reversed: str = described("what uninstall does not undo, by design (D-004)")
    commands: tuple[StepView, ...] = described("every step, in order")


@dataclass(frozen=True)
class BlockerLine(Strict):
    """One reason the transaction cannot be planned."""

    subject: str = described("what is blocked")
    reason: str = described("why")
    remedy: str | None = described("what to do about it")


@dataclass(frozen=True)
class PlanDocument(Strict):
    """The plan `install --dry-run` or `uninstall --dry-run` prints, as data.

    A refused transaction is still a `plan`, with `outcome: "refused"`, every
    blocker, and exit code 2. Includes the paths of files written for the
    operator; for local programs, not for pasting."""

    KIND: ClassVar[str] = "plan"

    action: str = described("`install` or `uninstall`")
    requested: tuple[str, ...] = described("the names given on the command line")
    outcome: str = described("`planned`, or `refused` with the blockers")
    target: TargetView = described("the system planned against")
    blockers: tuple[BlockerLine, ...] = described("empty unless refused")
    install: InstallPlanView | None = described(
        "the install plan; null for an uninstall or a refusal"
    )
    removal: RemovalPlanView | None = described(
        "the removal plan; null for an install or a refusal"
    )


def describe_sessions(desktops: frozenset[Desktop], unrecognised: tuple[str, ...]) -> str:
    """One line for what the session files said (D-060): the desktops the
    catalog knows, and any file read that named none of them, so a COSMIC or
    Sway machine is not reported as having no sessions."""
    files = ", ".join(unrecognised)
    names = "names" if len(unrecognised) == 1 else "name"
    if desktops:
        line = describe_set(desktops)
        if unrecognised:
            line += f"; also {files}, which {names} no desktop the catalog knows"
        return line
    if unrecognised:
        return f"none the catalog knows (read: {files})"
    return "none (no session files)"


def _desktops_read(plan: InstallPlan) -> DesktopsReadView | None:
    if plan.desktops_read is None:
        return None
    return DesktopsReadView(
        desktops=tuple(d.value for d in Desktop if d in plan.desktops_read),
        unrecognised=tuple(plan.sessions_unrecognised),
        summary=describe_sessions(plan.desktops_read, plan.sessions_unrecognised),
    )


def step_view(step: Step, *, euid: int) -> StepView:
    if isinstance(step, Action):
        return StepView(
            description=step.description,
            display=step.display(euid=euid),
            argv=(),
            action=step.kind,
            requires_root=step.requires_root,
        )
    return StepView(
        description=step.description,
        display=step.display(euid=euid),
        argv=tuple(step.argv_for(euid=euid)),
        action=None,
        requires_root=step.requires_root,
    )


def _terrain_section(terrain: TerrainDisclosure | None) -> TerrainSectionView | None:
    if terrain is None:
        return None
    resolution = terrain.resolution
    sizes = {t.name: t.size for t in resolution.fetch}
    download = sum(sizes.values())
    garmin = [
        GarminLine(
            region=f.region,
            snapshot=f.snapshot,
            estimate=garmin_estimate(f.size),
            estimate_human=human_size(garmin_estimate(f.size)),
        )
        for f in terrain.garmin
    ]
    routino = routino_estimate(terrain.routino_total)
    contours = terrain.contours * CONTOUR_BYTES
    disk = download + sum(g.estimate for g in garmin) + routino + contours
    return TerrainSectionView(
        regions=tuple(
            TerrainRegionLine(
                region=r.region,
                tiles=len(r.tiles),
                sea=r.sea,
                download=sum(sizes.get(name, 0) for name in r.tiles),
                download_human=human_size(sum(sizes.get(name, 0) for name in r.tiles)),
            )
            for r in resolution.regions
        ),
        fetch=tuple(
            TileLine(
                tile=t.name, size=t.size, size_human=human_size(t.size), verified_by=t.verified_by
            )
            for t in resolution.fetch
        ),
        current=len(resolution.current),
        licence=terrain.licence.strip(),
        licence_url=terrain.licence_url,
        download_total=download,
        download_total_human=human_size(download),
        garmin=tuple(garmin),
        routino_regions=terrain.routino_regions,
        routino_estimate=routino,
        routino_estimate_human=human_size(routino),
        contours=terrain.contours,
        contours_estimate=contours,
        contours_estimate_human=human_size(contours),
        disk_total=disk,
        disk_total_human=human_size(disk),
        estimate_note=MEASURED,
    )


def _map_section(
    plan: InstallPlan, maps: MapDisclosure | None, terrain: TerrainDisclosure | None = None
) -> MapSectionView | None:
    units = [
        p.block.install
        for p in plan.packages
        if isinstance(p.block.install, RegionalDataInstall | DerivedDataInstall)
    ]
    if not units or maps is None or not (maps.fetch or maps.current or maps.kept or maps.convert):
        return None
    # A current region still being converted is not "nothing to do"; nor is
    # one mkgmap builds from, or every region when Routino's database is
    # rebuilt over them all (D-061).
    converting = {f.slug for f in maps.convert}
    if terrain is not None:
        converting |= {f.slug for f in terrain.garmin}
        if terrain.routino_regions:
            converting |= {f.slug for f in (*maps.fetch, *maps.current)}

    def line(f: RegionFile, *, current: bool) -> RegionLine:
        return RegionLine(
            region=f.region,
            snapshot=f.snapshot,
            size=f.size,
            size_human=human_size(f.size),
            verified_by=f.verified_by,
            nothing_to_do=current and f.slug not in converting,
        )

    total = sum(f.size for f in maps.fetch)
    disk = total + sum(bin_estimate(f.size) for f in maps.convert)
    return MapSectionView(
        fetch=tuple(line(f, current=False) for f in maps.fetch),
        current=tuple(line(f, current=True) for f in maps.current),
        convert=tuple(
            ConvertLine(
                region=f.region,
                snapshot=f.snapshot,
                estimate=bin_estimate(f.size),
                estimate_human=human_size(bin_estimate(f.size)),
                countries=tuple(maps.countries.get(f.region, ()))
                if maps.boundaries is not None
                else (),
                converter_changed=f.slug in maps.converter_changed,
            )
            for f in maps.convert
        ),
        kept=tuple(
            KeptLine(region=k.region, snapshot=k.snapshot, reason=k.reason) for k in maps.kept
        ),
        licence=units[0].licence.strip(),
        licence_url=units[0].licence_url,
        download_total=total,
        download_total_human=human_size(total),
        disk_total=disk,
        disk_total_human=human_size(disk),
        estimate_note=ESTIMATE,
        boundaries=None
        if maps.boundaries is None
        else BoundaryLine(
            title=maps.boundaries.title,
            url=maps.boundaries.url,
            size=maps.boundaries.size,
            size_human=human_size(maps.boundaries.size),
            licence=maps.boundaries.licence,
            verified_by=PINNED,
        ),
        unknown_country=True,
        terrain=_terrain_section(terrain),
    )


def build_install_view(
    plan: InstallPlan,
    commands: Sequence[Step],
    *,
    euid: int,
    log_destination: Path | None = None,
    hands_log_to: str | None = None,
    built: frozenset[str] = frozenset(),
    suggestion_notes: Sequence[str] = (),
    maps: MapDisclosure | None = None,
    region_notes: Sequence[str] = (),
    terrain: TerrainDisclosure | None = None,
) -> InstallPlanView:
    data: list[DataLine] = []
    for planned in plan.packages:
        block = planned.block.install
        if not isinstance(block, DataInstall):
            continue
        total = sum(a.size for a in block.artifacts)
        data.append(
            DataLine(
                unit=planned.name,
                total_size=total,
                total_human=human_size(total),
                licence=block.licence.strip(),
                licence_url=block.licence_url,
                artifacts=tuple(
                    DataArtifactLine(url=a.url, size=a.size, size_human=human_size(a.size))
                    for a in block.artifacts
                ),
                installs_under=f"<prefix>/share/hammunition/data/{planned.name}/",
            )
        )
    return InstallPlanView(
        packages=tuple(
            PackageLine(
                name=p.name,
                method=p.block.install.method,
                state=plan_state(p, built, maps, terrain),
                requested_by=tuple(p.requested_by),
                apt=tuple(
                    AptLine(package=a, outstanding=a in p.outstanding, build_only=a in p.build_only)
                    for a in p.apt_packages
                ),
            )
            for p in plan.packages
        ),
        displaced=tuple(
            DisplacedLine(package=c, declared_by=p.name) for p in plan.packages for c in p.displaces
        ),
        apt_release=(
            ReleaseSection(release=plan.apt_release, packages=tuple(plan.apt_from_release))
            if plan.apt_release is not None
            else None
        ),
        no_recommends=(
            NoRecommendsSection(
                units=plan.apt_no_recommends_units, packages=plan.apt_to_install_no_recommends
            )
            if plan.apt_to_install_no_recommends
            else None
        ),
        repos=tuple(
            RepoLine(
                name=a.repo.name,
                unit=a.unit,
                packages=tuple(a.packages),
                uri=a.repo.uri,
                suites=tuple(a.repo.suites),
                components=tuple(a.repo.components),
                key_fingerprint=a.repo.key_fingerprint,
                sources=a.sources,
                keyring=a.keyring,
                consent_env_var=repo_env_var(a.repo),
            )
            for a in plan.apt_repos
        ),
        data=tuple(data),
        maps=_map_section(plan, maps, terrain),
        memberships=tuple(
            MembershipLine(
                user=m.user,
                group=m.group,
                package=m.package,
                detail=m.detail,
                reverse_hint=m.reverse_hint.strip() if m.reverse_hint else None,
            )
            for m in plan.group_memberships
        ),
        consent_gates=tuple(
            GateLine(profile=name, env_var=gate.env_var, risk_lines=tuple(gate.risk_lines))
            for name, gate in plan.consent_gates
        ),
        config_files=tuple(
            ConfigLine(
                unit=unit,
                path=config.path,
                mode=config.mode,
                append=config.append,
                backup_existing=config.backup_existing,
            )
            for unit, config, _body in plan.config_files
        ),
        desktops_read=_desktops_read(plan),
        deferrals=tuple(
            DeferralLine(kind=d.kind, subject=d.subject, what=d.what, why=d.why, remedy=d.remedy)
            for d in plan.deferrals
        ),
        notes=tuple(plan.notes),
        records=(
            RecordsLine(log=str(log_destination), handed_to=hands_log_to)
            if log_destination is not None
            else None
        ),
        commands=tuple(step_view(c, euid=euid) for c in commands),
        suggestion_notes=tuple(suggestion_notes),
        region_notes=tuple(region_notes),
    )


def render_plan_view(view: InstallPlanView, *, target: TargetView) -> list[str]:
    """The complete account of what will happen, as the terminal shows it."""
    lines = [f"Target: {target.description}", ""]

    if view.packages:
        lines.append(f"Packages ({len(view.packages)}):")
        for package in view.packages:
            why = ", ".join(package.requested_by)
            lines.append(f"  {package.name:<28} {package.state:<18} [{why}]")
            for apt in package.apt:
                mark = "+" if apt.outstanding else "="
                note = "  (to build)" if apt.build_only else ""
                lines.append(f"      {mark} {apt.package}{note}")
        lines.append("")

    if view.displaced:
        lines.append("Installed distribution packages displaced or shadowed (D-022):")
        for displaced in view.displaced:
            lines.append(
                f"  {displaced.package}  — declared by {displaced.declared_by}; the distribution "
                f"package stays installed, see that manifest's notes"
            )
        lines.append("")

    if view.apt_release is not None:
        release = view.apt_release.release
        lines.append(f"apt packages resolved from {release} (D-038):")
        lines.extend(
            wrap(
                f"apt refused the default release because a package this machine "
                f"already installs from {release} would have been "
                f"downgraded; the apt step runs with --target-release "
                f"{release}, which takes these from there:",
                indent="  ",
            )
        )
        for apt_package in view.apt_release.packages:
            lines.append(f"      {apt_package}")
        lines.append("")

    if view.no_recommends is not None:
        units = ", ".join(view.no_recommends.units)
        lines.append("apt packages installed without Recommends (D-052):")
        lines.extend(
            wrap(
                f"{units} asked for --no-install-recommends in the manifest, because the "
                f"Recommends of these packages conflict with software this target installs; "
                f"a second apt-get install carries the flag for them alone. Everything else "
                f"in this transaction keeps apt's defaults, and both commands run with "
                f"--no-remove:",
                indent="  ",
            )
        )
        for apt_package in view.no_recommends.packages:
            lines.append(f"      {apt_package}")
        lines.append("")

    if view.repos:
        lines.append("Third-party apt repositories that will be added (D-040):")
        for repo in view.repos:
            lines.append(f"  {repo.name}  [{repo.unit}: {', '.join(repo.packages)}]")
            lines.append(f"      {repo.uri}  {' '.join(repo.suites)}  {' '.join(repo.components)}")
            lines.append(f"      key {repo.key_fingerprint}")
            lines.append(f"      writes {repo.sources}")
            lines.append(f"      writes {repo.keyring}")
            lines.append(f"      consent: {repo.consent_env_var} must equal the key fingerprint")
        lines.append("")

    if view.data:
        lines.append("Offline data that will be downloaded and installed (D-049):")
        for data in view.data:
            lines.append(f"  {data.unit:<28} {data.total_human} total, licence: {data.licence}")
            lines.append(f"      stated at {data.licence_url}")
            for artifact in data.artifacts:
                lines.append(f"      {artifact.size_human:>9}  {artifact.url}")
            lines.append(f"      installs under {data.installs_under}")
        lines.append("")

    if view.maps is not None:
        # The station's regions, on the operator's own terminal: resolved
        # before this plan printed, so the dated file, its size and how it is
        # checked are known before anything is confirmed (D-057).
        maps = view.maps
        lines.append("Map regions, from station config (D-057):")
        if maps.fetch:
            lines.append("  will be downloaded and installed:")
            width = max(len(f.region) for f in maps.fetch)
            lines.extend(
                f"    {f.region:<{width}}  {f.snapshot}  {f.size_human:>9}  {f.verified_by}"
                for f in maps.fetch
            )
        if maps.current:
            lines.append("  already installed, current:")
            width = max(len(f.region) for f in maps.current)
            lines.extend(
                f"    {f.region:<{width}}  {f.snapshot}"
                + ("  (nothing to do)" if f.nothing_to_do else "")
                for f in maps.current
            )
        if maps.convert:
            lines.append(f"  will be converted for Navit (map sizes an {maps.estimate_note}):")
            width = max(len(f.region) for f in maps.convert)
            for f in maps.convert:
                border = ""
                if maps.boundaries is not None:
                    border = f"  border: {', '.join(f.countries) or 'none known'}"
                changed = "  (converter changed)" if f.converter_changed else ""
                lines.append(
                    f"    {f.region:<{width}}  {f.snapshot}  about {f.estimate_human}"
                    f"{border}{changed}"
                )
            if maps.boundaries is not None:
                lines.extend(
                    wrap(
                        "each region is first merged with its country's closed border "
                        "(osmium merge, in the staging directory, removed afterwards), so "
                        "maptool files its towns under the country and address search "
                        "finds them; maptool runs with -U, so a town the border misses is "
                        "indexed under the country Unknown, not dropped",
                        indent="      ",
                    )
                )
                border_file = maps.boundaries
                lines.extend(
                    wrap(
                        f"country borders: {border_file.title}, {border_file.size_human}, "
                        f"{border_file.licence}, {border_file.verified_by}",
                        indent="      ",
                    )
                )
            else:
                lines.extend(
                    wrap(
                        "maptool runs with -U, so a town outside every country boundary "
                        "is indexed under the country Unknown, not dropped",
                        indent="      ",
                    )
                )
        for kept in maps.kept:
            lines.append(
                f"  {kept.region}: could not check for a newer map; keeping the installed "
                f"{kept.snapshot or '(snapshot not recorded)'}"
            )
            lines.extend(wrap(kept.reason, indent="      "))
        lines.append(f"      licence: {maps.licence}, stated at {maps.licence_url}")
        lines.append(
            f"      download total: {maps.download_total_human}; about "
            f"{maps.disk_total_human} of disk with Navit's maps ({maps.estimate_note})"
        )
        lines.append("      installs under <prefix>/share/hammunition/data/")
        if maps.terrain is not None:
            lines.extend(_render_terrain(maps.terrain))
        lines.append("")

    if view.memberships:
        lines.append("Group membership changes:")
        for membership in view.memberships:
            lines.append(f"  {membership.user} → {membership.group}  ({membership.package})")
            lines.extend(wrap(membership.detail, indent="      "))
            if membership.reverse_hint is not None:
                lines.append(f"      reverse: {membership.reverse_hint}")
        lines.append("")

    if view.consent_gates:
        lines.append("Consent gates that will be presented:")
        for gate in view.consent_gates:
            lines.append(f"  {gate.profile} ({gate.env_var})")
            for risk in gate.risk_lines:
                wrapped = wrap(risk, indent="        ")
                lines.append("      - " + wrapped[0].strip())
                lines.extend(wrapped[1:])
        lines.append("")

    if view.config_files:
        lines.append("Configuration that will be written:")
        for config in view.config_files:
            backup = "existing file backed up" if config.backup_existing else "NOT backed up"
            verb = "appended to" if config.append else "written"
            lines.append(
                f"  {config.path}  ({verb}, mode {config.mode}, {backup})  [{config.unit}]"
            )
        lines.append("")

    if view.desktops_read is not None:
        # D-060: a unit in this request is for particular desktops, and what
        # decided it is on disk rather than in the caller's environment, so
        # the plan names both the files and what they said.
        lines.append(
            "Desktops read from session files (/usr/share/xsessions, /usr/share/wayland-sessions "
            "and the same under /usr/local/share):"
        )
        lines.append(f"  {view.desktops_read.summary}")
        lines.append("")

    if view.deferrals:
        # After the packages and before the notes: this is the part of the
        # request that will NOT happen, and burying it under a heading called
        # "notes" is how it stops being read. D-035.
        lines.append("Will NOT happen (the rest of the transaction still will):")
        for deferral in view.deferrals:
            lines.append(f"  {deferral.subject}: {deferral.what}")
            lines.extend(wrap(f"why: {deferral.why}", indent="      "))
            lines.extend(wrap(f"→ {deferral.remedy}", indent="      "))
        lines.append("")

    if view.notes:
        lines.append("Notes:")
        for note in view.notes:
            wrapped = wrap(note, indent="      ")
            lines.append("  - " + wrapped[0].strip())
            lines.extend(wrapped[1:])
        lines.append("")

    if view.records is not None:
        lines.append("Records:")
        lines.append(f"  transaction log written to {view.records.log}")
        if view.records.handed_to is not None:
            lines.append(
                f"  the log and any directories created for it are given to "
                f"{view.records.handed_to!r} (chown), since root is writing into their home"
            )
        lines.append("")

    lines.append(f"Commands ({len(view.commands)}):")
    if not view.commands:
        lines.append("  (none — everything this plan asks for is already in place)")
    for command in view.commands:
        lines.append(f"  # {command.description}")
        lines.append(f"  $ {command.display}")
    return lines


def _render_terrain(terrain: TerrainSectionView) -> list[str]:
    """The Terrain block, inside the map section (D-061)."""
    lines: list[str] = []
    if terrain.regions or terrain.fetch or terrain.current:
        lines.append("  Terrain, Copernicus GLO-30 elevation (D-061):")
    if terrain.regions:
        width = max(len(r.region) for r in terrain.regions)
        for region in terrain.regions:
            sea = f", {region.sea} square(s) of sea" if region.sea else ""
            fetch = f"; {region.download_human} to download" if region.download else ""
            lines.append(f"    {region.region:<{width}}  {region.tiles} tile(s){sea}{fetch}")
    if terrain.fetch:
        lines.append(
            f"    will be downloaded ({len(terrain.fetch)} tile(s), "
            f"{terrain.download_total_human}):"
        )
        width = max(len(t.tile) for t in terrain.fetch)
        lines.extend(
            f"      {t.tile:<{width}}  {t.size_human:>9}  {t.verified_by}" for t in terrain.fetch
        )
    if terrain.current:
        lines.append(f"    already installed: {terrain.current} tile(s)")
    if terrain.licence:
        lines.append(f"      licence: {terrain.licence}, stated at {terrain.licence_url}")
    built: list[str] = []
    if terrain.garmin:
        width = max(len(g.region) for g in terrain.garmin)
        built.extend(
            f"    Garmin map  {g.region:<{width}}  {g.snapshot}  about {g.estimate_human} "
            f"({GARMIN_FACTOR}x the download)"
            for g in terrain.garmin
        )
    if terrain.routino_regions:
        built.append(
            f"    Routino database over {terrain.routino_regions} region(s)  about "
            f"{terrain.routino_estimate_human} ({ROUTINO_FACTOR}x the downloads together)"
        )
    if terrain.contours:
        built.append(
            f"    contours for {terrain.contours} tile(s)  about "
            f"{terrain.contours_estimate_human}, with up to "
            f"{human_size(CONTOUR_SCRATCH_BYTES)} of scratch at a time"
        )
    if built:
        lines.append(f"  Built for QMapShack (sizes an estimate, {terrain.estimate_note}):")
        lines.extend(built)
    lines.append(
        f"      about {terrain.disk_total_human} of disk for terrain and QMapShack's maps "
        f"({terrain.estimate_note})"
    )
    return lines


def build_removal_view(
    plan: RemovalPlan, commands: Sequence[Step], *, euid: int
) -> RemovalPlanView:
    def shown(mapping: dict[str, list[str]]) -> tuple[UnitPackages, ...]:
        # The text lists a unit here only when it has packages, or is not
        # also being removed; the view carries exactly what the text shows.
        return tuple(
            UnitPackages(unit=unit, packages=tuple(packages))
            for unit, packages in mapping.items()
            if packages or unit not in plan.to_remove
        )

    return RemovalPlanView(
        to_remove=tuple(
            UnitPackages(unit=unit, packages=tuple(packages))
            for unit, packages in plan.to_remove.items()
        ),
        artifacts=tuple(
            ArtifactLine(unit=unit, kind=r.kind, path=str(r.path), basis=r.basis)
            for unit, removals in plan.artifacts.items()
            for r in removals
        ),
        left_unattributed=tuple(
            UnitFiles(unit=unit, paths=tuple(paths))
            for unit, paths in plan.left_unattributed.items()
        ),
        left_foreign=shown(plan.left_foreign),
        already_absent=shown(plan.already_absent),
        not_reversed=NOT_REVERSED,
        commands=tuple(step_view(c, euid=euid) for c in commands),
    )


def render_removal_view(view: RemovalPlanView, *, target: TargetView) -> list[str]:
    """What an uninstall will do, as the terminal shows it, up to the commands."""
    lines = [f"Target: {target.description}", ""]
    if view.to_remove:
        lines.append(f"Removing ({len(view.to_remove)} unit(s)):")
        for removal in view.to_remove:
            lines.append(f"  {removal.unit:28} - {' '.join(removal.packages)}")
    if view.artifacts:
        lines += ["", f"Removing artifacts ({len(view.artifacts)}):"]
        for artifact in view.artifacts:
            lines.append(
                f"  {artifact.unit:28} {artifact.kind:14} {artifact.path}  [{artifact.basis}]"
            )
    if view.left_unattributed:
        lines += ["", "Left in place — present, but the transaction log does not attribute it:"]
        for files in view.left_unattributed:
            for path in files.paths:
                lines.append(f"  {files.unit:28} {path}")
    for label, shown in (
        ("Left in place — installed, but not installed by Hammunition:", view.left_foreign),
        ("Already absent:", view.already_absent),
    ):
        if shown:
            lines += ["", label]
            for entry in shown:
                packages = " ".join(entry.packages) or "(nothing resolves here)"
                lines.append(f"  {entry.unit:28} {packages}")
    lines += ["", view.not_reversed]
    if view.commands:
        lines += ["", f"Commands ({len(view.commands)}):"]
        for command in view.commands:
            lines.append(f"  # {command.description}")
            lines.append(f"  $ {command.display}")
    else:
        lines += ["", "Nothing to do: none of this is installed, or none of it was ours."]
    return lines


def refused_plan(
    action: str, requested: Sequence[str], target: TargetView, blockers: Sequence[Blocker]
) -> PlanDocument:
    return PlanDocument(
        action=action,
        requested=tuple(requested),
        outcome="refused",
        target=target,
        blockers=tuple(
            BlockerLine(subject=b.subject, reason=b.reason, remedy=b.remedy) for b in blockers
        ),
        install=None,
        removal=None,
    )
