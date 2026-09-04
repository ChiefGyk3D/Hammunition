# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pre-flight resolution.  D-016.

Everything is resolved before anything is done, and every failure is reported
together. This is one module rather than a step inside ``install`` because
D-016 makes it a distinct phase with its own contract:

    Resolve everything for the whole transaction, report every failure
    together, then install — do not discover failures one package at a time,
    mid-run.

The failure this prevents is the defining defect of the prior art. AHRL has no
``set -e`` and checks no exit status across 3,911 lines, so every ``apt
install`` may fail and the script proceeds; ``bin/find_errors_ahrl`` exists to
grep a 2.5-hour transcript for error strings *afterwards*, and its own comment
concedes it does not catch everything.

D-016 also names four dependency lines in AHRL that are suspected to be failing
silently today — ``fftw2`` (FFTW **2**), ``libgtk2.0-dev`` (EOL),
``python3-tksnack``, and an **OCaml** binding fldigi does not use. All four are
apt package names in a dependency list, which is why
:func:`resolve` puts a manifest's ``depends`` through apt rather than trusting
it. A dependency nobody has ever checked is not a dependency, it is a comment.

A plan is data. It knows what would happen and can say so completely; it does
not know how to do any of it. That is what makes ``--dry-run`` complete by
construction rather than by discipline — the dry run prints the same plan the
installer executes.
"""

from __future__ import annotations

import pwd
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from hammunition.backends import (
    IMPLEMENTED_BINARY_FORMATS,
    IMPLEMENTED_METHODS,
    IMPLEMENTED_MODIFICATIONS,
    AptBackend,
    AptPackageState,
    AptSimulation,
)
from hammunition.backends.apt import downgrades_refused
from hammunition.backends.apt_repo import AptRepoBackend, RepoState
from hammunition.backends.source import IMPLEMENTED_BUILD_SYSTEMS
from hammunition.distro import Target
from hammunition.kernel import (
    DESCRIBE,
    KERNEL_REMOVAL,
    NO_MODULE_BUILD,
    USERSPACE_PATH,
    KernelProbe,
)
from hammunition.manifest.schema import (
    AptInstall,
    AptRepo,
    BinaryInstall,
    ConfigFile,
    ConsentGate,
    GitInstall,
    InstallBlock,
    NodeInstall,
    PackageManifest,
    ProfileManifest,
    SourceInstall,
    Status,
)
from hammunition.station import Station

__all__ = [
    "Blocker",
    "Deferral",
    "GroupMembership",
    "InstallPlan",
    "PlanError",
    "PlannedPackage",
    "RepoAddition",
    "resolve",
]

REQUESTED_DIRECTLY = "requested"


@dataclass(frozen=True)
class Blocker:
    """One reason the transaction cannot proceed.

    ``remedy`` is separate from ``reason`` on purpose: an error that says what
    is wrong without saying what to do about it is the kind of check people
    learn to route around.
    """

    subject: str
    reason: str
    remedy: str | None = None

    def render(self) -> str:
        line = f"{self.subject}: {self.reason}"
        if self.remedy:
            line += f"\n    → {self.remedy}"
        return line


@dataclass(frozen=True)
class Deferral:
    """Something the transaction will NOT do, without refusing to proceed.

    The distinction from :class:`Blocker` is the whole of D-035. A blocker means
    the machine must not be touched. A deferral means most of what was asked for
    happens and one part does not, named precisely, with what would let it.

    Templated configuration missing a station value is the case this exists for:
    a `packet` profile of nineteen packages used to refuse entirely because
    `linbpq` did not know a callsign. Nineteen packages installed and one file
    not written is a better outcome than nothing installed, and it is only
    honest if the unwritten file is reported rather than skipped.

    Q-017 extended it to a *profile member the target does not offer*: on
    Ubuntu 24.04 `listening` withheld nineteen installable units over four the
    archive does not carry. Same shape, same rule -- most of what was asked
    for happens, the part that does not is named, and `status` keeps naming it.
    """

    subject: str
    what: str
    """What will not happen."""
    why: str
    """What is missing."""
    remedy: str
    """What the operator can do about it."""
    kind: str = "config"
    """``config`` (D-035: a file not written) or ``package`` (Q-017: a profile
    member not installed). Recorded in the transaction log so `status` can
    tell them apart."""

    def render(self) -> str:
        return f"{self.subject}: {self.what}\n    why: {self.why}\n    → {self.remedy}"

    def to_log_entry(self) -> dict[str, str]:
        return {"kind": self.kind, "subject": self.subject, "what": self.what, "why": self.why}


class PlanError(Exception):
    """Resolution failed. Carries every blocker, never just the first."""

    def __init__(self, blockers: Sequence[Blocker]) -> None:
        self.blockers = tuple(blockers)
        body = "\n".join(f"  {b.render()}" for b in self.blockers)
        noun = "problem" if len(self.blockers) == 1 else "problems"
        super().__init__(f"{len(self.blockers)} {noun} block this transaction:\n{body}")


@dataclass(frozen=True)
class GroupMembership:
    """A group the operator will be added to, and why it matters."""

    group: str
    user: str
    package: str
    description: str
    detail: str
    reverse_hint: str | None


@dataclass(frozen=True)
class PlannedPackage:
    """One catalog package, resolved against this target."""

    manifest: PackageManifest
    block: InstallBlock
    apt_packages: tuple[str, ...]
    """The distro packages this resolves to, ``depends`` included."""

    already_installed: tuple[str, ...] = ()
    requested_by: tuple[str, ...] = (REQUESTED_DIRECTLY,)

    build_only: tuple[str, ...] = ()
    """Of `apt_packages`, the ones that are `build_depends`.

    They are installed like any other apt package -- a build needs its
    toolchain present -- but they are not the software the operator asked for,
    and the plan says so. Reporting `libgtk2.0-dev` in the same breath as
    `glfer` would misdescribe what was installed and, later, what `uninstall`
    may safely remove."""

    displaces: tuple[str, ...] = ()
    """Declared `conflicts_with_repo_package` entries that are installed NOW.

    D-022: coexist and disclose, never remove silently. A source build that
    shadows the distro's binary on PATH is disclosed in the plan; a vendor
    .deb that would collide at the dpkg file level is refused before anything
    runs -- that split is decided at planning, from the same probe as
    everything else."""

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def outstanding(self) -> tuple[str, ...]:
        """apt packages not already present."""
        return tuple(p for p in self.apt_packages if p not in self.already_installed)


@dataclass(frozen=True)
class RepoAddition:
    """One third-party apt repository this transaction will add.  D-040.

    Decided at plan time from the file system and the apt probe: the unit's
    own packages have no candidate in the archive as configured, and the
    repository's two files are absent. A repository already present with
    this engine's content is not added again; one present with anybody
    else's content is a refusal, never an overwrite.
    """

    unit: str
    repo: AptRepo
    sources: str
    """``/etc/apt/sources.list.d/<name>.sources`` -- the path, for disclosure."""
    keyring: str
    """``/etc/apt/keyrings/<name>.gpg`` -- likewise."""
    packages: tuple[str, ...]
    """The apt packages this repository is expected to supply."""


@dataclass(frozen=True)
class InstallPlan:
    """Everything that will happen, before any of it does."""

    target: Target
    packages: tuple[PlannedPackage, ...]
    group_memberships: tuple[GroupMembership, ...] = ()
    consent_gates: tuple[tuple[str, ConsentGate], ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
    deferrals: tuple[Deferral, ...] = ()
    """Parts of the request that will not happen, and why. D-035."""

    config_files: tuple[tuple[str, ConfigFile, str], ...] = ()
    """(package, config file, rendered body) for every file that WILL be written."""

    apt_release: str | None = None
    """``--target-release`` for the apt step, when the transaction resolves only
    from a release the target already installs from (D-038). None otherwise."""

    apt_from_release: tuple[str, ...] = ()
    """Of everything the apt step unpacks, the packages that come from
    ``apt_release`` and nowhere else -- measured by apt's simulation, disclosed
    in the plan."""

    apt_repos: tuple[RepoAddition, ...] = ()
    """Third-party repositories added before the apt step, each behind its
    own consent gate (D-040). Their packages are in ``apt_to_install`` but
    were not part of the plan-time simulate: apt cannot resolve from a
    repository it does not have yet, so the executor simulates again after
    ``apt-get update``."""

    @property
    def repo_supplied(self) -> frozenset[str]:
        """apt packages that only exist once a repository above is added."""
        return frozenset(p for addition in self.apt_repos for p in addition.packages)

    @property
    def apt_to_install(self) -> tuple[str, ...]:
        """The union of outstanding apt packages, sorted and de-duplicated."""
        seen: set[str] = set()
        for planned in self.packages:
            seen.update(planned.outstanding)
        return tuple(sorted(seen))

    @property
    def debconf_selections(self) -> tuple[str, ...]:
        """Preseed lines to apply before apt runs, from packages being installed.

        Only from packages with outstanding apt work — preseeding for a package
        that is already installed would answer a question that was answered at
        its install, and re-running would not change what is on disk. Order
        follows the packages; duplicates are dropped keeping first sight.
        """
        seen: dict[str, None] = {}
        for planned in self.packages:
            if planned.outstanding:
                for line in planned.manifest.debconf_selections:
                    seen.setdefault(line, None)
        return tuple(seen)

    @property
    def reconfigure_after(self) -> tuple[str, ...]:
        """Packages to dpkg-reconfigure after the apt install, from installs only."""
        seen: dict[str, None] = {}
        for planned in self.packages:
            if planned.outstanding:
                for pkg in planned.manifest.reconfigure_after:
                    seen.setdefault(pkg, None)
        return tuple(seen)

    @property
    def is_empty(self) -> bool:
        """Nothing to install and nothing to change — a legitimate outcome."""
        return not self.apt_to_install and not self.group_memberships and not self.apt_repos


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _expand_requests(
    names: Sequence[str],
    catalog: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    blockers: list[Blocker],
) -> tuple[dict[str, list[str]], list[tuple[str, ConsentGate]]]:
    """Turn requested names into ``package -> who asked for it``.

    A name that is both a profile and a package would be ambiguous; the loader
    keeps the two namespaces separate and nothing in the catalog collides, so
    profiles are checked first and a collision is reported rather than
    silently preferred.
    """
    wanted: dict[str, list[str]] = {}
    gates: list[tuple[str, ConsentGate]] = []

    for name in names:
        if name in profiles and name in catalog:
            blockers.append(
                Blocker(
                    subject=name,
                    reason="is the name of both a profile and a package, so the request is ambiguous",
                    remedy="rename one of them in the catalog; the engine will not guess",
                )
            )
            continue
        if name in profiles:
            profile = profiles[name]
            if profile.consent is not None:
                gates.append((profile.name, profile.consent))
            for package in profile.packages:
                wanted.setdefault(package, []).append(f"profile {profile.name}")
            continue
        if name in catalog:
            wanted.setdefault(name, []).append(REQUESTED_DIRECTLY)
            continue
        blockers.append(
            Blocker(
                subject=name,
                reason="is not a package or profile in the catalog",
                remedy="`hammunition list` shows everything the catalog contains",
            )
        )
    return wanted, gates


def _pull_catalog_dependencies(
    wanted: dict[str, list[str]], catalog: Mapping[str, PackageManifest]
) -> None:
    """Follow ``depends`` entries that name other catalog packages.

    ``depends`` holds names in two namespaces, which is a wart in the schema
    rather than a design: every entry in the catalog today (``libhamlib4``,
    ``gnuradio``) is a distro package name, and D-016's whole evidence table is
    about distro package names in dependency lists. But a manifest may
    legitimately depend on another manifest, so a name the catalog knows is
    treated as a catalog package and pulled in, and everything else is verified
    against apt by :func:`resolve`. Both are checked; neither is assumed.
    """
    queue = list(wanted)
    while queue:
        current = queue.pop()
        manifest = catalog.get(current)
        if manifest is None:
            continue
        for dependency in manifest.depends:
            if dependency in catalog and dependency not in wanted:
                wanted[dependency] = [f"dependency of {current}"]
                queue.append(dependency)


def _order(
    names: Iterable[str], catalog: Mapping[str, PackageManifest], blockers: list[Blocker]
) -> list[str]:
    """Order by ``after``, which is sequencing and not dependency (D-003 shape).

    ``wsjtx-improved`` is ``after: [wsjtx]`` because both builds emit a binary
    called ``wsjtx`` and the later one must win. An ``after`` naming a package
    not in this transaction is not an error — it is a constraint that is
    already satisfied by absence.
    """
    remaining = sorted(names)
    present = set(remaining)
    ordered: list[str] = []
    placed: set[str] = set()

    while remaining:
        ready = [
            name
            for name in remaining
            if all(
                predecessor in placed
                for predecessor in catalog[name].after
                if predecessor in present
            )
        ]
        if not ready:
            blockers.append(
                Blocker(
                    subject=", ".join(remaining),
                    reason="`after` constraints form a cycle, so no install order exists",
                    remedy="break the cycle in the catalog; `after` is ordering, not dependency",
                )
            )
            ordered.extend(remaining)
            break
        ordered.extend(ready)
        placed.update(ready)
        remaining = [name for name in remaining if name not in placed]

    return ordered


def _build_depends_of(manifest: PackageManifest) -> set[str]:
    """Every apt name that appears as a build dependency anywhere in *manifest*.

    Used only to label a missing package in a blocker, so an operator is told
    that `fftw2` is something glfer needs to *build* rather than something it
    needs to run. Across all blocks rather than the resolved one, because the
    label is cosmetic and a name that is a build dependency on any target is a
    build dependency for the purpose of that sentence.
    """
    return {name for block in manifest.install for name in block.build_depends}


def _check_engine_capability(
    manifest: PackageManifest, block: InstallBlock, *, repos_supported: bool = False
) -> list[Blocker]:
    """Refuse, by name, anything this engine build cannot actually do.

    Never a warning and never a skip. CLAUDE.md forbids a shim that makes an
    unsupported combination appear to work, and reporting a package as
    installable when the backend for it does not exist is that shim wearing a
    different hat.
    """
    found: list[Blocker] = []
    method = block.install.method

    if method not in IMPLEMENTED_METHODS:
        found.append(
            Blocker(
                subject=manifest.name,
                reason=(
                    f"resolves to the {method!r} backend on this target, and this engine "
                    f"build implements only {', '.join(sorted(IMPLEMENTED_METHODS))}"
                ),
                remedy=(
                    f"the {method!r} backend is measured and scheduled for 1.0 "
                    f"(DESIGN.md §6); it is not written yet"
                ),
            )
        )

    if isinstance(block.install, SourceInstall | GitInstall) and method in IMPLEMENTED_METHODS:
        # D-016: everything the run cannot do is found before anything is done.
        # The backend raises on these too, but discovering them after the apt
        # step has already installed a toolchain is exactly the fix-one-re-run
        # shape resolution exists to prevent.
        source: SourceInstall | GitInstall = block.install
        if source.build_system not in IMPLEMENTED_BUILD_SYSTEMS:
            found.append(
                Blocker(
                    subject=manifest.name,
                    reason=(
                        f"builds with {source.build_system!r}, which this engine build "
                        f"does not implement (it implements "
                        f"{', '.join(sorted(IMPLEMENTED_BUILD_SYSTEMS))})"
                    ),
                    remedy=(
                        "no manifest in the catalog uses it, so this is an unimplemented "
                        "gap rather than a regression (D-014)"
                    ),
                )
            )
        if isinstance(source, SourceInstall):
            undiffed = [p.file for p in source.patches if not p.unified_diff]
            if undiffed:
                found.append(
                    Blocker(
                        subject=manifest.name,
                        reason=(
                            f"declares patches for {', '.join(undiffed)} with no "
                            f"unified_diff to apply"
                        ),
                        remedy=(
                            "a description alone cannot be applied; building unpatched "
                            "source would produce a binary the manifest does not describe"
                        ),
                    )
                )

    if isinstance(block.install, BinaryInstall):
        # The format is checked here rather than only in the backend, so an
        # AppImage is a plan-time refusal naming the gap rather than a failure
        # partway through a transaction.
        if block.install.format not in IMPLEMENTED_BINARY_FORMATS:
            found.append(
                Blocker(
                    subject=manifest.name,
                    reason=(
                        f"is a {block.install.format!r} artifact, which this engine "
                        f"build cannot install"
                    ),
                    remedy=(
                        "AppImage is post-1.0 (SCOPE.md); it is refused by name rather "
                        "than skipped, so the gap stays visible"
                    ),
                )
            )
        elif (
            block.install.format != "deb"
            and not manifest.binaries
            and not block.install.install_tree
        ):
            found.append(
                Blocker(
                    subject=manifest.name,
                    reason=(
                        "is a prebuilt archive or executable that names no `binaries` "
                        "and no `install_tree`"
                    ),
                    remedy=(
                        "declare what the artifact contains and what it should be called; "
                        "unpacking it otherwise installs nothing while reporting success"
                    ),
                )
            )

    if manifest.apt_repos and not repos_supported:
        # The backend exists (D-040); a caller that plans without one -- a
        # test, a bare `resolve` -- still gets the named refusal rather than
        # a plan that silently assumes the repository will appear.
        names = ", ".join(repo.name for repo in manifest.apt_repos)
        found.append(
            Blocker(
                subject=manifest.name,
                reason=f"requires third-party apt repositories ({names}) and this plan has no repository backend",
                remedy=(
                    "adding a repository with a pinned signing key is a disclosed system "
                    "modification of its own; plan with an AptRepoBackend, or install it by "
                    "hand"
                ),
            )
        )

    # `config_files` is deliberately NOT a blocker any more. A templated file
    # whose station values are unknown becomes a Deferral: the package installs
    # and the file is reported as not written. See D-035 and `_plan_config`.

    for modification in manifest.system_modifications:
        if modification.kind not in IMPLEMENTED_MODIFICATIONS:
            found.append(
                Blocker(
                    subject=manifest.name,
                    reason=f"needs a {modification.kind!r} system modification this engine cannot perform",
                    remedy=modification.description.strip(),
                )
            )

    return found


def _plan_config(
    manifest: PackageManifest, station: Station
) -> tuple[list[tuple[str, ConfigFile, str]], list[Deferral]]:
    """Render this manifest's templated config, or defer what cannot be rendered.

    Every file is all-or-nothing: a config file written with some values
    substituted and others left as `{station.callsign}` is worse than no file,
    because it looks configured. So a file missing one value is deferred whole.
    """
    writable: list[tuple[str, ConfigFile, str]] = []
    deferred: list[Deferral] = []
    for config in manifest.config_files:
        wanted = config.station_variables
        unknown = station.missing(wanted)
        if unknown:
            deferred.append(
                Deferral(
                    subject=manifest.name,
                    what=f"will not write {config.path}",
                    why="station values not set: " + ", ".join(unknown),
                    remedy=(
                        "run `hammunition station set --"
                        + " --".join(f"{v.replace('_', '-')} <value>" for v in unknown)
                        + "` and install again, or write the file by hand. The package "
                        "itself installs either way."
                    ),
                )
            )
            continue
        body = config.template
        for variable in wanted:
            value = station.get(variable)
            assert value is not None  # `missing` above proved it
            body = body.replace("{station." + variable + "}", value)
        writable.append((manifest.name, config, body))
    return writable, deferred


def _status_blocker(manifest: PackageManifest) -> Blocker | None:
    """A package we have recorded as not working does not get installed quietly."""
    if manifest.status is Status.supported:
        return None
    verdict = manifest.status_verdict.value if manifest.status_verdict else "unrecorded"
    when = manifest.status_date.isoformat() if manifest.status_date else "no date"
    return Blocker(
        subject=manifest.name,
        reason=f"is marked {manifest.status.value} ({verdict}, {when}): {manifest.status_reason}",
        remedy=(
            "if this verdict is stale, re-test it and update the manifest — "
            "an inherited verdict counts against us (PARITY-POLICY.md, M5)"
        ),
    )


#: A Debian version string's upstream major and minor: an optional epoch, then
#: two dotted numbers. ``20.19.2+dfsg1-1`` -> (20, 19);
#: ``1:18.19.1+dfsg-6ubuntu5`` -> (18, 19). The minor matters: ``require()``
#: of an ES module works from 20.19 and not from 20.18, and openhamclock's
#: server needs it.
_MAJOR_MINOR = re.compile(r"^(?:\d+:)?(\d+)\.(\d+)")


def node_version(version: str) -> tuple[int, int] | None:
    match = _MAJOR_MINOR.match(version.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def _check_node_floor(
    manifest: PackageManifest, install: NodeInstall, nodejs: AptPackageState | None
) -> Blocker | str:
    """The D-037 gate: a Blocker below the floor, a disclosure note at or above it.

    The version that counts is the one the run will have: what is installed
    now, else what apt would install. ``nodejs`` is in the transaction's own
    tool dependencies, so an archive with no candidate at all is already a
    no-candidate blocker by the time this runs; that case is repeated here in
    D-037's words rather than left to the generic one.
    """
    floor = install.node_min_version
    floor_parsed = node_version(floor)
    assert floor_parsed is not None  # the schema's pattern guarantees MAJOR.MINOR
    version = nodejs.installed or nodejs.candidate if nodejs is not None else None
    found = node_version(version) if version else None
    source = "installed" if nodejs is not None and nodejs.installed else "the archive's candidate"
    if version is None or found is None:
        return Blocker(
            subject=manifest.name,
            reason=(
                f"is a Node.js application needing Node {floor} or newer, and this "
                f"distribution offers no nodejs package"
            ),
            remedy=(
                "Node is only ever taken from the distribution, never fetched (D-037); "
                "a release of this distribution that carries nodejs, or skip this unit"
            ),
        )
    if found < floor_parsed:
        return Blocker(
            subject=manifest.name,
            reason=(
                f"is a Node.js application needing Node {floor} or newer, and this "
                f"distribution's nodejs is {version} ({source}): "
                f"{found[0]}.{found[1]} is below the floor"
            ),
            remedy=(
                "Node is only ever taken from the distribution, never fetched (D-037); "
                "a newer release of this distribution carries a newer nodejs, or skip "
                "this unit"
            ),
        )
    return (
        f"{manifest.name} is a Node.js application: it needs Node {floor} or newer "
        f"(this machine: nodejs {version}, {source}) and its build fetches its "
        f"dependency closure from registry.npmjs.org, each package verified against "
        f"the sha512 pins in the lock file inside the sha256-verified source archive. "
        f"No package lifecycle scripts run during the build."
    )


def _resolve_from_installed_release(
    apt: AptBackend, packages: Sequence[str], failed: AptSimulation
) -> tuple[AptSimulation, str, tuple[str, ...]] | Blocker:
    """The D-038 retry: when apt refuses because it would have to downgrade
    something already installed, ask again from the release that installed it.

    A clean Parrot 7.3 has 197 of its 3,801 packages from `parrot-backports`,
    pinned at 599 against the archive's 600 -- newer Qt, GTK, curl, ALSA for
    the desktop. Every `-dev` package for those libraries carries an exact-
    version dependency, so the archive's default `libcurl4-openssl-dev` (8.14)
    needs `libcurl4t64` 8.14 where 8.21 is installed, and apt will not
    downgrade a library to build against it. Nor should it. The `-dev` at 8.21
    is in backports beside the library; `--target-release parrot-backports`
    is apt's own way to prefer it, and it is what a Parrot user types.

    So: the packages apt refused to downgrade name the release, the release
    is tried once, and the result is either a resolved transaction with the
    packages it takes from that release listed by name -- the plan discloses
    them, the operator sees them before anything runs -- or the same refusal,
    reported with apt's own words. Two releases, or none, is a refusal too:
    nothing is guessed. The transaction is never widened silently: `-t`
    prefers that release only for packages this transaction installs, and the
    simulation says exactly which.
    """
    culprits = downgrades_refused(failed.error)
    releases = sorted({r for p in culprits if (r := apt.installed_archive(p)) is not None})
    refusal = Blocker(
        subject="apt",
        reason=f"cannot resolve this transaction as one apt-get install:\n{_indent(failed.error)}",
        remedy=(
            "the packages named above are the chain; `apt-get install --simulate` "
            "with the same list reproduces it. Leave out the unit that needs the "
            "unsatisfiable package, or fix the machine's apt state -- the plan "
            "will not start a transaction apt has already said it cannot finish (D-016)"
        ),
    )
    if len(releases) != 1:
        return refusal
    release = releases[0]
    retried = apt.simulate(packages, release=release)
    if not retried.ok:
        return refusal
    return retried, release, retried.from_archive(release)


def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _target_deferral(name: str, wanted: Mapping[str, Sequence[str]], why: str) -> Deferral:
    """Q-017: a profile member this target does not offer, deferred by name.

    Only for a member the operator did not ask for by name -- ``wanted`` says
    who asked -- and only for a reason true of the *target*: no candidate on
    this release for the unit's own packages, no install block for this
    distro or architecture, a Node floor the distribution's package is below.
    The caller decides the reason qualifies; this only phrases it.
    """
    via = ", ".join(w for w in wanted[name] if w != REQUESTED_DIRECTLY)
    return Deferral(
        subject=name,
        what=f"will not be installed ({via})",
        why=why,
        remedy=(
            f"the rest installs without it; `hammunition install {name}` shows the "
            f"refusal in full, and a release that carries it needs no change here"
        ),
        kind="package",
    )


def _plan_repos(
    manifest: PackageManifest,
    install: AptInstall,
    repos: AptRepoBackend,
    missing: Sequence[str],
    own: set[str],
    notes: list[str],
) -> list[RepoAddition] | Blocker:
    """D-040: decide whether this unit's declared repositories are added.

    Returns the additions -- possibly none -- or one blocker. The
    repositories are added only when the unit's *own* apt packages have no
    candidate: a target that already carries them is left as it is and told
    so (D-022), and a missing ``depends`` is never a reason to add somebody
    else's repository. Each repository is read from the file system:

    * absent -- added, and its packages leave the plan-time simulate, which
      cannot see a repository apt does not have yet;
    * ours -- both files carry exactly what this engine writes, so the
      candidate should exist and does not: the archive index is stale, and
      the fix is ``--refresh``, never a second copy of the file;
    * foreign -- a file of the same name with anybody else's content, which
      is never overwritten.
    """
    own_missing = sorted(p for p in missing if p in own)
    if not own_missing:
        for repo in manifest.apt_repos:
            if repos.state(repo, unit=manifest.name) is RepoState.absent:
                notes.append(
                    f"{manifest.name}: the archive already offers {', '.join(install.packages)}; "
                    f"the {repo.name} repository the manifest declares is not added (D-022)"
                )
        return []
    additions: list[RepoAddition] = []
    for repo in manifest.apt_repos:
        files = repos.files_for(repo)
        state = repos.state(repo, unit=manifest.name)
        if state is RepoState.foreign:
            return Blocker(
                subject=manifest.name,
                reason=(
                    f"{files.sources} or {files.keyring} already exists and is not this "
                    f"engine's work; apt has no candidate for {', '.join(own_missing)}"
                ),
                remedy=(
                    f"a file another tool or operator wrote is never overwritten (D-040): "
                    f"inspect both, and either remove them or install {manifest.name} by hand"
                ),
            )
        if state is RepoState.ours:
            return Blocker(
                subject=manifest.name,
                reason=(
                    f"the {repo.name} repository is already configured at {files.sources} "
                    f"and apt still has no candidate for {', '.join(own_missing)}"
                ),
                remedy=(
                    "the package index is stale or the repository does not carry the "
                    "package for this release; run `hammunition install --refresh` "
                    "(apt-get update) and read what apt says about the source"
                ),
            )
        additions.append(
            RepoAddition(
                unit=manifest.name,
                repo=repo,
                sources=str(files.sources),
                keyring=str(files.keyring),
                packages=tuple(own_missing),
            )
        )
    return additions


def resolve(
    names: Sequence[str],
    *,
    catalog: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    target: Target,
    apt: AptBackend,
    user: str,
    refresh: bool = False,
    station: Station | None = None,
    repos: AptRepoBackend | None = None,
    kernel: KernelProbe | None = None,
) -> InstallPlan:
    """Build a complete plan, or raise :class:`PlanError` listing every blocker.

    The apt probe happens once, at the end, for every distro package the whole
    transaction needs — the manifests' own apt packages and their ``depends``
    together. One probe means one answer about the machine's apt state rather
    than N answers taken at N different moments.

    ``kernel`` is the running kernel's module tree, consulted only for units
    that declare ``requires_kernel``; ``None`` means it was not read, which is
    disclosed on those units rather than assumed either way.
    """
    blockers: list[Blocker] = []
    deferrals: list[Deferral] = []
    config_files: list[tuple[str, ConfigFile, str]] = []
    station = station if station is not None else Station()

    wanted, gates = _expand_requests(names, catalog, profiles, blockers)
    _pull_catalog_dependencies(wanted, catalog)

    if not wanted:
        if blockers:
            raise PlanError(blockers)
        return InstallPlan(target=target, packages=())

    ordered = _order(wanted, catalog, blockers)

    # Q-017: a member that reached the request only through a profile (or as a
    # dependency of one) may be deferred when the target does not offer it. A
    # name the operator typed is never deferred -- asking for it by name is
    # asking to see the refusal.
    deferrable = {name for name in ordered if REQUESTED_DIRECTLY not in wanted[name]}
    deferred: dict[str, Deferral] = {}
    repo_additions: list[RepoAddition] = []
    target_name = target.pretty_name or f"{target.distro} {target.version}".strip()

    # (manifest, block, every apt package it needs, which of those are build-only)
    resolved: list[tuple[PackageManifest, InstallBlock, tuple[str, ...], tuple[str, ...]]] = []
    for name in ordered:
        manifest = catalog[name]

        status = _status_blocker(manifest)
        if status is not None:
            blockers.append(status)
            continue

        block = manifest.resolve(target.distro, target.version, target.arch)
        if block is None:
            where = f"{target.distro} {target.version or '(no version)'} on {target.arch}"
            if name in deferrable:
                deferred[name] = _target_deferral(
                    name, wanted, f"the catalog declares no install block matching {where}"
                )
                continue
            blockers.append(
                Blocker(
                    subject=name,
                    reason=f"declares no install block matching {where}",
                    remedy=(
                        "this target is genuinely unsupported for this package; the catalog "
                        "says so rather than pretending otherwise"
                    ),
                )
            )
            continue

        capability = _check_engine_capability(manifest, block, repos_supported=repos is not None)
        if capability:
            blockers.extend(capability)
            continue

        writable, unwritable = _plan_config(manifest, station)
        config_files.extend(writable)
        deferrals.extend(unwritable)

        # apt and source reach here; _check_engine_capability rejects the rest.
        # A source build needs its `build_depends` from apt before it can start,
        # and those go through the same pre-flight candidate check as everything
        # else -- which is the whole point. glfer's build_depends name `fftw2`
        # and `libgtk2.0-dev`, two of D-016's four suspected-stale dependency
        # lines; nothing in AHRL ever asked apt whether they still exist.
        # `depends` holds names in two namespaces (see _pull_catalog_dependencies).
        # One naming another manifest has already been pulled into the plan as a
        # catalog package and must NOT also be asked of apt: `libacars` is ours
        # and apt has never heard of it, so probing it would report the
        # transaction unsatisfiable because a package we are about to build from
        # source is not in the archive.
        distro_depends = tuple(d for d in manifest.depends if d not in catalog)
        # Tools the ENGINE's own method needs, owned here rather than left to
        # every manifest to remember: a git build needs git, an applied patch
        # needs patch(1). Found the hard way — the first campaign against a
        # fresh baseline failed all four git units at `git init`, because
        # every earlier VM had git only as a leftover of manual testing.
        # AHRL's install_source_libs was this idea as a blanket; per-method
        # injection keeps the plan honest about who needs what.
        tool_depends: tuple[str, ...] = ()
        if block.install.method == "git":
            tool_depends = ("git",)
        elif block.install.method == "source" and getattr(block.install, "patches", None):
            tool_depends = ("patch",)
        elif block.install.method == "node":
            # The distribution's Node and npm, never fetched (D-037). Riding
            # the probe below is what makes "absent" a named refusal rather
            # than a failed `npm` exec halfway through.
            tool_depends = ("nodejs", "npm")
            if block.install.patches:
                tool_depends = (*tool_depends, "patch")
        if getattr(block.install, "autoreconf", False):
            tool_depends = (*tool_depends, "autoconf", "automake", "libtool")
        # The toolchain is the engine's tool as much as git is. wsjtx never
        # declared cmake or a compiler and built on five targets anyway,
        # because js8call in the same profile is a git build there and
        # declares both; on Pop!_OS 24.04 js8call comes from apt, nothing
        # else asked for cmake, and digital-modes died at command 27 with
        # 'cmake' not on PATH (2026-09-04). Measured the same day on the
        # Debian 13 baseline, which ships no gcc: 33 of the catalog's 39
        # source/git manifests list build-essential by hand and four C/C++
        # builds (fldigi, glfer, mshv, wsjtx) rely on a neighbour for it --
        # mshv's own note records the order-dependence. So every compiled
        # build gets build-essential, and a cmake build gets cmake. qmake is
        # not injected: all six qmake manifests declare qt5-qmake themselves.
        if block.install.method in ("source", "git"):
            tool_depends = (*tool_depends, "build-essential")
            if getattr(block.install, "build_system", None) == "cmake":
                tool_depends = (*tool_depends, "cmake")
        if block.install.method == "apt":
            packages = (*block.install.packages, *distro_depends)
            build_only: tuple[str, ...] = ()
        else:
            packages = (*block.build_depends, *tool_depends, *distro_depends)
            build_only = tuple(dict.fromkeys((*block.build_depends, *tool_depends)))
        resolved.append((manifest, block, tuple(dict.fromkeys(packages)), build_only))

    # -- one apt probe for the whole transaction ---------------------------
    # Declared repo conflicts ride the same probe: the plan needs to know
    # whether each is installed NOW. They are deliberately excluded from the
    # no-candidate check below -- a conflict package missing from the archive
    # is a fine state, not a blocker.
    all_conflicts = sorted(
        {c for manifest, _, _, _ in resolved for c in manifest.conflicts_with_repo_package}
    )
    all_apt = sorted({p for _, _, packages, _ in resolved for p in packages})
    states = {}
    notes: list[str] = []
    # `or all_conflicts`: a unit with nothing to apt-install (a pure vendor
    # .deb) still needs the probe to know whether its declared conflicts are
    # installed -- the gate that skipped it left the wsjtx-improved refusal
    # untested until this line existed.
    if all_apt or all_conflicts:
        if not apt.lists_populated():
            if refresh:
                # --refresh puts `apt-get update` at the head of this same run,
                # so empty lists are a sequencing fact, not a blocker -- refusing
                # here would tell the operator to pass the flag they just passed.
                # What is genuinely lost is the pre-flight candidate check:
                # nothing can know what apt will offer until update has run, so
                # the plan discloses the gap instead of silently skipping the
                # check (D-016 wants the resolution honest, not decorative).
                notes.append(
                    "apt has no package lists yet; --refresh runs apt-get update "
                    "first, so which packages actually have candidates cannot be "
                    "known before this plan executes. A package apt does not "
                    "offer will fail the apt-get install step rather than being "
                    "caught here."
                )
            else:
                blockers.append(
                    Blocker(
                        subject="apt",
                        reason=(
                            "has no package lists, so every package would resolve as unknown. "
                            "Reporting them all as unobtainable would be a confident lie"
                        ),
                        remedy="run `sudo apt-get update`, or pass --refresh to do it as part of this run",
                    )
                )
        else:
            states = apt.probe(sorted({*all_apt, *all_conflicts}))
            for manifest, block, packages, _ in resolved:
                missing = [p for p in packages if p not in states or not states[p].known]
                own = (
                    set(block.install.packages) if isinstance(block.install, AptInstall) else set()
                )
                if (
                    manifest.apt_repos
                    and repos is not None
                    and isinstance(block.install, AptInstall)
                ):
                    # D-040: the archive as configured has no candidate for
                    # the unit's own packages, and the manifest names where
                    # they come from. Decided here, from the same probe, so
                    # a target that already offers the package -- Parrot's
                    # own codium -- never gets a repository it does not need
                    # (D-022), and a repository added under our name by an
                    # earlier run is recognised rather than re-added.
                    repo_outcome = _plan_repos(manifest, block.install, repos, missing, own, notes)
                    if isinstance(repo_outcome, Blocker):
                        blockers.append(repo_outcome)
                        continue
                    repo_additions.extend(repo_outcome)
                    if repo_outcome:
                        missing = [p for p in missing if p not in own]
                if missing:
                    origin = {p: "depends" for p in manifest.depends if p not in catalog}
                    origin.update({p: "build_depends" for p in _build_depends_of(manifest)})
                    detail = ", ".join(f"{p} ({origin.get(p, 'install')})" for p in sorted(missing))
                    # Q-017: the unit's OWN apt packages absent from this
                    # release is the target's gap. A missing `depends` or
                    # `build_depends` is the manifest's, and stays a blocker
                    # -- deferral drawn wider than that swallows defects.
                    if manifest.name in deferrable and set(missing) <= own:
                        deferred[manifest.name] = _target_deferral(
                            manifest.name,
                            wanted,
                            f"apt on {target_name} has no candidate for {', '.join(sorted(missing))}",
                        )
                        continue
                    blockers.append(
                        Blocker(
                            subject=manifest.name,
                            reason=f"apt has no candidate for {detail}",
                            remedy=(
                                "the package may have been renamed, may need a component "
                                "this machine has not enabled, or may not exist on this "
                                "release — D-016 names four AHRL dependency lines that had "
                                "gone stale exactly this way"
                            ),
                        )
                    )

    # -- Node.js floor, from the same probe (D-037) -------------------------
    # Disclosed as a requirement, refused when the distribution's Node is
    # absent or too old. Never fetched: the remedy is a newer release of the
    # distribution or skipping the unit, and the plan says so.
    for manifest, block, _, _ in resolved:
        if not isinstance(block.install, NodeInstall):
            continue
        if not states:
            notes.append(
                f"{manifest.name} needs Node.js {block.install.node_min_version} or newer "
                f"from the distribution's nodejs package, and with no apt lists the "
                f"version on offer cannot be checked before this plan executes."
            )
            continue
        outcome = _check_node_floor(manifest, block.install, states.get("nodejs"))
        if isinstance(outcome, Blocker):
            # Q-017: the distribution's Node being absent or below the floor
            # is true of the target, so a profile member defers on it.
            if manifest.name in deferrable:
                # The blocker's reason reads on from its subject; the deferral
                # prints `why:` on its own line, so name the subject again.
                deferred[manifest.name] = _target_deferral(
                    manifest.name, wanted, f"{manifest.name} {outcome.reason}"
                )
            else:
                blockers.append(outcome)
        else:
            notes.append(outcome)

    # -- Kernel subsystems the unit cannot work without ---------------------
    # A fact about the machine, not the target: one Pop!_OS 24.04 VM has
    # AX.25 in its 7.0.11 module tree and not in its 7.1.5 one (2026-09-04).
    # So it is read here, never written into the capability matrix, and a
    # profile member whose kernel lacks it defers the way a target gap does.
    for manifest, _, _, _ in resolved:
        for feature in manifest.requires_kernel:
            what = DESCRIBE[feature]
            present = None if kernel is None else kernel.available(feature)
            if present is True:
                continue
            if kernel is None or present is None:
                which = f" {kernel.release}" if kernel is not None else ""
                notes.append(
                    f"{manifest.name} needs {what}, which cannot be checked on this "
                    f"machine: no module tree for the running kernel{which} is readable."
                )
                continue
            why = f"needs {what}, which kernel {kernel.release} does not carry -- {KERNEL_REMOVAL}"
            if manifest.name in deferrable:
                deferred[manifest.name] = _target_deferral(
                    manifest.name, wanted, f"{manifest.name} {why}"
                )
            else:
                blockers.append(
                    Blocker(
                        subject=manifest.name,
                        reason=why,
                        remedy=(
                            f"a distribution kernel that still carries it (Debian 13's 6.12, "
                            f"Parrot 7.3's and Ubuntu 26.04's 7.0 do); {USERSPACE_PATH}; "
                            f"{NO_MODULE_BUILD}"
                        ),
                    )
                )

    # -- Q-017: the deferred set closes over catalog dependencies -----------
    # pythonprop depends on voacapl; a target that lacks voacapl cannot have
    # pythonprop either, however present its own package is. A dependent the
    # operator asked for by name is refused, naming the dependency.
    changed = True
    while changed:
        changed = False
        for manifest, _, _, _ in resolved:
            if manifest.name in deferred:
                continue
            gone = sorted(d for d in manifest.depends if d in deferred)
            if not gone:
                continue
            why = f"depends on {', '.join(gone)}, which this target does not offer"
            if manifest.name in deferrable:
                deferred[manifest.name] = _target_deferral(manifest.name, wanted, why)
                changed = True
            else:
                blockers.append(
                    Blocker(
                        subject=manifest.name,
                        reason=why,
                        remedy=(
                            f"`hammunition install {gone[0]}` shows why; there is no "
                            f"installing the dependent without it"
                        ),
                    )
                )
                # Not `changed`: a blocker ends the plan, and its dependents
                # would only repeat the same refusal.

    # A profile whose every member is deferred is refused, not deferred: a
    # plan that installs nothing and reports a success is the shape D-031
    # exists to catch, one layer up.
    for name in names:
        profile = profiles.get(name)
        if profile is None or name in catalog:
            continue
        members = [p for p in profile.packages if p in catalog]
        if members and all(m in deferred for m in members):
            blockers.append(
                Blocker(
                    subject=name,
                    reason=(
                        f"every member of this profile is unavailable on {target_name}: "
                        f"{', '.join(members)}"
                    ),
                    remedy=(
                        "the profile has nothing to install here; each member's own "
                        "reason is listed by `hammunition install <member>`"
                    ),
                )
            )

    if deferred:
        deferrals.extend(deferred[name] for name in ordered if name in deferred)
        # A deferred member's configuration is neither written nor reported
        # as unwritten: there is no package for the file to belong to.
        config_files = [c for c in config_files if c[0] not in deferred]
        deferrals = [d for d in deferrals if not (d.kind == "config" and d.subject in deferred)]
        resolved = [r for r in resolved if r[0].name not in deferred]
        all_apt = sorted({p for _, _, packages, _ in resolved for p in packages})

    # -- declared conflicts against what is installed now (D-022) ----------
    for manifest, block, _, _ in resolved:
        installed_conflicts = [
            c
            for c in manifest.conflicts_with_repo_package
            if c in states and states[c].is_installed
        ]
        if not installed_conflicts:
            continue
        if isinstance(block.install, BinaryInstall) and block.install.format == "deb":
            names = ", ".join(installed_conflicts)
            blockers.append(
                Blocker(
                    subject=manifest.name,
                    reason=(
                        f"its vendor .deb collides with installed distribution package(s): {names}"
                    ),
                    remedy=(
                        f"remove them first (sudo apt-get remove {names}) or skip this "
                        f"unit -- the alternative is a dpkg file collision partway "
                        f"through the transaction, which is how this rule was measured "
                        f"(wsjtx-improved vs wsjtx-data, 2026-08-30)"
                    ),
                )
            )

    # -- the apt step, resolved by apt itself before anything runs ---------
    # `apt-cache policy` says a package has a candidate; only apt's resolver
    # says the whole set installs together. Two measured ways it does not:
    # a clean Kali, 2026-09-02, where `digital-modes` planned clean and then
    # failed at the dpkg step (jtdx brought `wsjtx-data`, the `wsjtx-improved`
    # .deb collided with it minutes later); and a clean Parrot the same night,
    # where five of fifteen profiles failed at the apt step itself because a
    # `-dev` package's exact-version dependency could not be met without
    # downgrading a library Parrot ships from its backports (D-038). Both are
    # D-016 defects -- the plan passed, the machine was touched, the failure
    # came after -- and one `--simulate` of the outstanding set answers both.
    # It is asked only when everything else has resolved: a simulation of a
    # set with a missing candidate fails for the reason already listed.
    from_repos = {p for addition in repo_additions for p in addition.packages}
    outstanding_apt = [
        p for p in all_apt if not (p in states and states[p].is_installed) and p not in from_repos
    ]
    apt_release: str | None = None
    apt_from_release: tuple[str, ...] = ()
    simulation = AptSimulation(ok=True)
    if outstanding_apt and states and not blockers:
        simulation = apt.simulate(outstanding_apt)
        if not simulation.ok:
            retried = _resolve_from_installed_release(apt, outstanding_apt, simulation)
            if isinstance(retried, Blocker):
                blockers.append(retried)
            else:
                simulation, apt_release, apt_from_release = retried

    # -- declared conflicts against what this transaction itself installs --
    # The check above sees what is installed NOW; on a clean machine that is
    # nothing, and the simulation is the only thing that knows what the apt
    # step pulls in.
    if simulation.ok:
        for manifest, block, _, _ in resolved:
            if not (isinstance(block.install, BinaryInstall) and block.install.format == "deb"):
                continue
            hit = sorted(
                c for c in manifest.conflicts_with_repo_package if c in simulation.installs
            )
            if not hit:
                continue
            names = ", ".join(hit)
            blockers.append(
                Blocker(
                    subject=manifest.name,
                    reason=(
                        f"its vendor .deb collides with distribution package(s) this same "
                        f"transaction would install: {names}"
                    ),
                    remedy=(
                        f"leave out either {manifest.name} or whatever needs {names} (apt-get "
                        f"install --simulate names the chain) -- the alternative is a "
                        f"dpkg file collision after the apt step has already run"
                    ),
                )
            )

    if blockers:
        raise PlanError(blockers)

    planned = tuple(
        PlannedPackage(
            manifest=manifest,
            block=block,
            apt_packages=packages,
            already_installed=tuple(p for p in packages if p in states and states[p].is_installed),
            requested_by=tuple(dict.fromkeys(wanted[manifest.name])),
            build_only=build_only,
            displaces=tuple(
                c
                for c in manifest.conflicts_with_repo_package
                if c in states and states[c].is_installed
            ),
        )
        for manifest, block, packages, build_only in resolved
    )

    # An empty operator name is how `gpasswd --add '' wireshark` got built on the
    # first real run: root in a container with neither $USER nor $SUDO_USER set.
    # A privilege change aimed at nobody is not a no-op worth tolerating, and it
    # is exactly the shape D-016 wants caught during resolution rather than
    # discovered by reading the command that is about to run.
    needs_user = [
        (item.manifest.name, modification.group)
        for item in planned
        for modification in item.manifest.system_modifications
        if modification.kind == "group_membership"
    ]
    if needs_user and not user:
        groups = ", ".join(sorted({g for _, g in needs_user if g}))
        blockers.append(
            Blocker(
                subject=", ".join(sorted({name for name, _ in needs_user})),
                reason=(
                    f"needs the operator added to {groups}, and no operator could be "
                    f"identified ($SUDO_USER and $USER are both unset)"
                ),
                remedy="pass --user <name> to say who should be added to the group",
            )
        )
        raise PlanError(blockers)

    # An operator that names no real account is caught here, not after apt has
    # already run. `gpasswd --add nosuchuser dialout` fails, but user_groups()
    # returns an empty set for an unknown name ("about to be added anyway"), so
    # nothing upstream noticed until the privileged command failed mid-
    # transaction, on a machine apt had already changed. D-016: a failure is a
    # report before anything happens, never a surprise halfway through.
    if needs_user and user:
        try:
            pwd.getpwnam(user)
        except KeyError:
            groups = ", ".join(sorted({g for _, g in needs_user if g}))
            blockers.append(
                Blocker(
                    subject=", ".join(sorted({name for name, _ in needs_user})),
                    reason=(
                        f"needs the operator {user!r} added to {groups}, but {user!r} "
                        f"is not a user on this system"
                    ),
                    remedy="pass --user <name> naming an account that exists",
                )
            )
            raise PlanError(blockers) from None

    memberships = tuple(
        GroupMembership(
            group=modification.group,
            user=user,
            package=item.manifest.name,
            description=modification.description.strip(),
            detail=modification.detail.strip(),
            reverse_hint=modification.reverse_hint,
        )
        for item in planned
        for modification in item.manifest.system_modifications
        if modification.kind == "group_membership" and modification.group is not None
    )

    return InstallPlan(
        target=target,
        packages=planned,
        group_memberships=memberships,
        consent_gates=tuple(gates),
        notes=tuple(notes),
        deferrals=tuple(deferrals),
        config_files=tuple(config_files),
        apt_release=apt_release,
        apt_from_release=apt_from_release,
        apt_repos=tuple(repo_additions),
    )
