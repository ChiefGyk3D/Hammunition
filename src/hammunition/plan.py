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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from hammunition.backends import IMPLEMENTED_METHODS, IMPLEMENTED_MODIFICATIONS, AptBackend
from hammunition.distro import Target
from hammunition.manifest.schema import (
    ConsentGate,
    InstallBlock,
    PackageManifest,
    ProfileManifest,
    Status,
)

__all__ = [
    "Blocker",
    "GroupMembership",
    "InstallPlan",
    "PlanError",
    "PlannedPackage",
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

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def outstanding(self) -> tuple[str, ...]:
        """apt packages not already present."""
        return tuple(p for p in self.apt_packages if p not in self.already_installed)


@dataclass(frozen=True)
class InstallPlan:
    """Everything that will happen, before any of it does."""

    target: Target
    packages: tuple[PlannedPackage, ...]
    group_memberships: tuple[GroupMembership, ...] = ()
    consent_gates: tuple[tuple[str, ConsentGate], ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def apt_to_install(self) -> tuple[str, ...]:
        """The union of outstanding apt packages, sorted and de-duplicated."""
        seen: set[str] = set()
        for planned in self.packages:
            seen.update(planned.outstanding)
        return tuple(sorted(seen))

    @property
    def is_empty(self) -> bool:
        """Nothing to install and nothing to change — a legitimate outcome."""
        return not self.apt_to_install and not self.group_memberships


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


def _check_engine_capability(manifest: PackageManifest, block: InstallBlock) -> list[Blocker]:
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

    if manifest.apt_repos:
        names = ", ".join(repo.name for repo in manifest.apt_repos)
        found.append(
            Blocker(
                subject=manifest.name,
                reason=f"requires third-party apt repositories ({names}) that this engine cannot add yet",
                remedy=(
                    "adding a repository with a pinned signing key is a disclosed system "
                    "modification of its own and is not implemented; install it by hand or "
                    "choose a package that does not need one"
                ),
            )
        )

    if manifest.config_files:
        variables = sorted(manifest.station_variables)
        found.append(
            Blocker(
                subject=manifest.name,
                reason=(
                    "writes templated configuration"
                    + (f" needing station values ({', '.join(variables)})" if variables else "")
                ),
                remedy=(
                    "station-local configuration — callsign, grid square, rig device paths — "
                    "is the open design question this manifest is waiting on (DESIGN.md §15.3)"
                ),
            )
        )

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


def resolve(
    names: Sequence[str],
    *,
    catalog: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    target: Target,
    apt: AptBackend,
    user: str,
) -> InstallPlan:
    """Build a complete plan, or raise :class:`PlanError` listing every blocker.

    The apt probe happens once, at the end, for every distro package the whole
    transaction needs — the manifests' own apt packages and their ``depends``
    together. One probe means one answer about the machine's apt state rather
    than N answers taken at N different moments.
    """
    blockers: list[Blocker] = []

    wanted, gates = _expand_requests(names, catalog, profiles, blockers)
    _pull_catalog_dependencies(wanted, catalog)

    if not wanted:
        if blockers:
            raise PlanError(blockers)
        return InstallPlan(target=target, packages=())

    ordered = _order(wanted, catalog, blockers)

    resolved: list[tuple[PackageManifest, InstallBlock, tuple[str, ...]]] = []
    for name in ordered:
        manifest = catalog[name]

        status = _status_blocker(manifest)
        if status is not None:
            blockers.append(status)
            continue

        block = manifest.resolve(target.distro, target.version, target.arch)
        if block is None:
            blockers.append(
                Blocker(
                    subject=name,
                    reason=(
                        f"declares no install block matching {target.distro} "
                        f"{target.version or '(no version)'} on {target.arch}"
                    ),
                    remedy=(
                        "this target is genuinely unsupported for this package; the catalog "
                        "says so rather than pretending otherwise"
                    ),
                )
            )
            continue

        capability = _check_engine_capability(manifest, block)
        if capability:
            blockers.extend(capability)
            continue

        # Only apt reaches here — _check_engine_capability rejects everything else.
        assert block.install.method == "apt"
        packages = (*block.install.packages, *manifest.depends)
        resolved.append((manifest, block, tuple(dict.fromkeys(packages))))

    # -- one apt probe for the whole transaction ---------------------------
    all_apt = sorted({p for _, _, packages in resolved for p in packages})
    states = {}
    if all_apt:
        if not apt.lists_populated():
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
            states = apt.probe(all_apt)
            for manifest, _, packages in resolved:
                missing = [p for p in packages if p not in states or not states[p].known]
                if missing:
                    origin = {p: "depends" for p in manifest.depends}
                    detail = ", ".join(f"{p} ({origin.get(p, 'install')})" for p in sorted(missing))
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

    if blockers:
        raise PlanError(blockers)

    planned = tuple(
        PlannedPackage(
            manifest=manifest,
            block=block,
            apt_packages=packages,
            already_installed=tuple(p for p in packages if p in states and states[p].is_installed),
            requested_by=tuple(dict.fromkeys(wanted[manifest.name])),
        )
        for manifest, block, packages in resolved
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
    )
