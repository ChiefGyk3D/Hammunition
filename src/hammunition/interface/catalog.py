# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``list`` and ``show`` as data: what the catalog offers.  D-059."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from hammunition.backends.base import (
    BackendError,
    Command,
    CommandRunner,
    SubprocessRunner,
)
from hammunition.consent import render_disclosure
from hammunition.distro import DetectionError, Target
from hammunition.interface.envelope import Strict, TargetView, described, target_view
from hammunition.manifest.schema import AptInstall, PackageManifest, ProfileManifest

__all__ = [
    "CatalogDocument",
    "ProfileDocument",
    "UnitDocument",
    "build_catalog",
    "build_profile",
    "build_unit",
    "detect_target",
    "human_size",
    "installed_apt_bytes",
    "render_catalog",
    "render_profile",
]


def detect_target() -> Target | None:
    """The target, or None where /etc/os-release cannot be read."""
    try:
        return Target.detect()
    except DetectionError:
        return None


@dataclass(frozen=True)
class ProfileDocs(Strict):
    """The documentation every profile carries (CLAUDE.md)."""

    what_it_installs: str = described("what the profile installs")
    why_together: str = described("why those things belong together")
    deliberately_excludes: str = described("what it leaves out, and why")
    manual_configuration: str = described("what the operator still sets up by hand")
    disk_footprint_hint: str | None = described("a disk estimate, when the profile states one")


@dataclass(frozen=True)
class ProfileEntry(Strict):
    """One profile in the catalog."""

    name: str = described("the profile")
    summary: str = described("one line")
    stage: str = described("`1.0` or `post-1.0`")
    packages: tuple[str, ...] = described("its member units")
    consent_gated: bool = described("installing it presents a consent gate (D-021)")
    documentation: ProfileDocs = described("its documentation")
    members: int = described("how many catalog units the profile names; no target filtering")
    installed: int = described(
        "how many of those the transaction log records as installed here (the same reading "
        "`status` reports as `completed`); 0 when the log is absent"
    )
    installed_size_bytes: int | None = described(
        "the sum of dpkg's `Installed-Size` (KiB, converted to bytes) over the installed members "
        "whose install method on this target is apt; null when dpkg is unavailable or no "
        "installed member is apt. Source, git, binary and data members contribute nothing in "
        "this release, so the figure is a floor, not the profile's disk use"
    )


@dataclass(frozen=True)
class PackageEntry(Strict):
    """One unit in the catalog."""

    name: str = described("the unit")
    version: str = described("the manifest's version")
    summary: str = described("one line")
    categories: tuple[str, ...] = described("its tags")
    status: str = described("`supported`, `broken`, `retired` or `unverifiable`")
    methods: tuple[str, ...] = described("the install method of every block, in manifest order")
    resolves_here: str | None = described(
        "the method that resolves on this target; null when none does or the target is unknown"
    )


@dataclass(frozen=True)
class CatalogDocument(Strict):
    """Every profile and unit the catalog offers, and what resolves here."""

    KIND: ClassVar[str] = "catalog"

    what: str = described("`all`, `packages` or `profiles`, as asked")
    target: TargetView | None = described("the system; null when /etc/os-release is unreadable")
    profiles: tuple[ProfileEntry, ...] = described("by name; empty when `what` is `packages`")
    packages: tuple[PackageEntry, ...] = described("by name; empty when `what` is `profiles`")


@dataclass(frozen=True)
class ConsentView(Strict):
    """A profile's consent gate, as `show` discloses it."""

    env_var: str = described("the scripted-consent variable")
    risk_categories: tuple[str, ...] = described("the capabilities disclosed")
    disclosure: str = described("the exact text the gate shows")


@dataclass(frozen=True)
class SuggestionView(Strict):
    """A choice the profile offers when nothing already answers it."""

    name: str = described("what is suggested, e.g. a logger")
    reason: str = described("why")
    options: tuple[str, ...] = described("the units offered")
    recommended: str | None = described("the default choice")
    detect_commands: tuple[str, ...] = described("commands whose presence means one is installed")


@dataclass(frozen=True)
class ProfileDocument(Strict):
    """One profile, everything `show` prints, disclosure included."""

    KIND: ClassVar[str] = "profile"

    name: str = described("the profile")
    summary: str = described("one line")
    stage: str = described("`1.0` or `post-1.0`")
    documentation: ProfileDocs = described("its documentation")
    consent: ConsentView | None = described("its consent gate; null when ungated")
    packages: tuple[str, ...] = described("its member units")
    suggests_one_of: tuple[SuggestionView, ...] = described("choices it offers")


@dataclass(frozen=True)
class UnitDocument(Strict):
    """One unit's manifest. JSON only: the text `show` describes profiles."""

    KIND: ClassVar[str] = "unit"

    name: str = described("the unit")
    resolves_here: str | None = described("the method that resolves on this target")
    manifest: dict[str, Any] = described(
        "the manifest as its YAML sets it, unset fields left out; every field is documented in "
        "docs/reference/schema.md"
    )


def _docs(profile: ProfileManifest) -> ProfileDocs:
    d = profile.documentation
    return ProfileDocs(
        what_it_installs=d.what_it_installs.strip(),
        why_together=d.why_together.strip(),
        deliberately_excludes=d.deliberately_excludes.strip(),
        manual_configuration=d.manual_configuration.strip(),
        disk_footprint_hint=d.disk_footprint_hint.strip() if d.disk_footprint_hint else None,
    )


def _resolves(manifest: PackageManifest, target: Target | None) -> str | None:
    if target is None:
        return None
    block = manifest.resolve(target.distro, target.version, target.arch)
    return block.install.method if block else None


def human_size(size: int) -> str:
    """Bytes as the terminal shows them: `512 B`, `2.0 MiB`."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def installed_apt_bytes(names: Collection[str], runner: CommandRunner) -> int | None:
    """Total `Installed-Size` of *names* in bytes, from one `dpkg-query` call.

    dpkg reports KiB. None when dpkg cannot be run or exits non-zero with
    nothing printed (a name dpkg does not know makes it exit 1 but still print
    the others, which are summed).
    """
    sizes = _sizes(names, runner) if names else {}
    return sum(v for v in sizes.values() if v is not None) if sizes else None


def _apt_packages(manifest: PackageManifest, target: Target | None) -> tuple[str, ...]:
    if target is None:
        return ()
    block = manifest.resolve(target.distro, target.version, target.arch)
    if block is None or not isinstance(block.install, AptInstall):
        return ()
    return tuple(block.install.packages)


def build_catalog(
    what: str,
    packages: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    target: Target | None,
    *,
    installed: Collection[str] = (),
    runner: CommandRunner | None = None,
) -> CatalogDocument:
    here = frozenset(installed)
    apt_of = {name: _apt_packages(packages[name], target) for name in here if name in packages}
    wanted = {pkg for names in apt_of.values() for pkg in names}
    sizes_wanted = what in {"profiles", "all"} and bool(wanted)
    size_by_name: dict[str, int | None] = {}
    if sizes_wanted:
        # One call over every name at once; per-profile sums are made from it.
        size_by_name = _sizes(wanted, runner or SubprocessRunner())
    return CatalogDocument(
        what=what,
        target=target_view(target) if target is not None else None,
        profiles=tuple(
            ProfileEntry(
                name=name,
                summary=profiles[name].summary,
                stage=profiles[name].stage,
                packages=tuple(profiles[name].packages),
                consent_gated=profiles[name].consent is not None,
                documentation=_docs(profiles[name]),
                members=len(profiles[name].packages),
                installed=sum(1 for p in profiles[name].packages if p in here),
                installed_size_bytes=_profile_size(profiles[name], apt_of, size_by_name),
            )
            for name in sorted(profiles)
        )
        if what in {"profiles", "all"}
        else (),
        packages=tuple(
            PackageEntry(
                name=name,
                version=packages[name].version,
                summary=packages[name].summary,
                categories=tuple(packages[name].categories),
                status=packages[name].status.value,
                methods=tuple(block.install.method for block in packages[name].install),
                resolves_here=_resolves(packages[name], target),
            )
            for name in sorted(packages)
        )
        if what in {"packages", "all"}
        else (),
    )


def _sizes(names: Collection[str], runner: CommandRunner) -> dict[str, int | None]:
    """Per-name bytes, one dpkg-query call; names dpkg did not report are absent."""
    command = Command(
        argv=("dpkg-query", "-W", "-f=${Package}\t${Installed-Size}\n", *sorted(names)),
        description="Read the installed size of the apt packages a profile's units installed",
    )
    try:
        result = runner.run(command)
    except (BackendError, OSError):
        return {}
    out: dict[str, int | None] = {}
    for line in result.stdout.splitlines():
        pkg, _tab, size = line.partition("\t")
        if size.strip().isdigit():
            out[pkg.strip()] = int(size) * 1024
    return out


def _profile_size(
    profile: ProfileManifest,
    apt_of: Mapping[str, tuple[str, ...]],
    size_by_name: Mapping[str, int | None],
) -> int | None:
    names = {pkg for unit in profile.packages for pkg in apt_of.get(unit, ())}
    found = [size_by_name[n] for n in sorted(names) if size_by_name.get(n) is not None]
    return sum(s for s in found if s is not None) if found else None


def render_catalog(doc: CatalogDocument) -> list[str]:
    """``list`` as the terminal shows it."""
    lines: list[str] = []
    if doc.what in {"profiles", "all"}:
        lines.append(f"Profiles ({len(doc.profiles)}):")
        for profile in doc.profiles:
            gate = "  [consent gate]" if profile.consent_gated else ""
            size = (
                f"  {human_size(profile.installed_size_bytes)}"
                if profile.installed_size_bytes is not None
                else ""
            )
            lines.append(
                f"  {profile.name:<16} {profile.stage:<9} {profile.members:>3} pkg"
                f"  installed {profile.installed} of {profile.members}{size}{gate}"
            )
            lines.append(f"      {profile.summary}")
        lines.append("")
    if doc.what in {"packages", "all"}:
        lines.append(f"Packages ({len(doc.packages)}):")
        for package in doc.packages:
            where = "?" if doc.target is None else package.resolves_here or "unsupported here"
            flag = "" if package.status == "supported" else f"  [{package.status}]"
            lines.append(f"  {package.name:<28} {where:<18}{flag}")
            lines.append(f"      {package.summary}")
    return lines


def build_profile(profile: ProfileManifest) -> ProfileDocument:
    gate = profile.consent
    return ProfileDocument(
        name=profile.name,
        summary=profile.summary,
        stage=profile.stage,
        documentation=_docs(profile),
        consent=ConsentView(
            env_var=gate.env_var,
            risk_categories=tuple(c.value for c in gate.risk_categories),
            disclosure=render_disclosure(gate, profile.name),
        )
        if gate is not None
        else None,
        packages=tuple(profile.packages),
        suggests_one_of=tuple(
            SuggestionView(
                name=g.name,
                reason=g.reason,
                options=tuple(g.options),
                recommended=g.recommended,
                detect_commands=tuple(g.detect_commands),
            )
            for g in profile.suggests_one_of
        ),
    )


def render_profile(doc: ProfileDocument) -> list[str]:
    """``show`` as the terminal shows it."""
    d = doc.documentation
    lines = [
        f"{doc.name} — {doc.summary}",
        f"stage: {doc.stage}",
        "",
        d.what_it_installs,
        "",
        "Why together:",
        f"  {d.why_together}",
        "",
        "Deliberately excludes:",
        f"  {d.deliberately_excludes}",
        "",
        "You still configure by hand:",
        f"  {d.manual_configuration}",
    ]
    if doc.consent is not None:
        lines += ["", doc.consent.disclosure]
    lines += ["", f"Packages ({len(doc.packages)}):"]
    lines += [f"  {name}" for name in doc.packages]
    return lines


def build_unit(manifest: PackageManifest, target: Target | None) -> UnitDocument:
    return UnitDocument(
        name=manifest.name,
        resolves_here=_resolves(manifest, target),
        manifest=manifest.model_dump(mode="json", exclude_unset=True),
    )
