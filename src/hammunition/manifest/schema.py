# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hammunition package manifest schema.

Shaped by measurement, not convention. Every field here exists because a real
unit in `docs/reference/ahrl-inventory.md` requires it; see `docs/DECISIONS.md`
D-010, D-012, D-015 and D-016 for the evidence behind each.

Two invariants the type system itself enforces, because they are security
requirements rather than preferences:

* There is no ``method: script``. Piping remote content into a shell is
  unrepresentable, not merely discouraged.
* ``RemoteArtifact`` requires ``sha256``. An unverified download cannot be
  expressed at all.
* A ``ConsentGate`` disclosure cannot contain legal-advice wording. D-021 says
  such wording is a defect; here it is a validation error.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ConsentGate",
    "InstallBlock",
    "ManifestError",
    "PackageManifest",
    "PinBasis",
    "PinReview",
    "ProfileManifest",
    "RiskCategory",
    "Selector",
    "Status",
]

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9._+-]*$")

# Debian policy §5.6.1: at least two characters, starting alphanumeric, from
# lowercase letters, digits, plus, minus and dot. The optional suffix is an
# architecture qualifier (`libc6:i386`, `foo:any`).
#
# Validated rather than taken on trust because these strings become argv for a
# root-privileged `apt-get install`. A manifest saying
#
#     packages: ["-o", "APT::Get::AllowUnauthenticated=true", "tio"]
#
# is not a package list; it is two apt options and a package, and D-009's
# community and local tiers mean manifests will arrive from people this project
# has not met. The pre-flight probe happens to catch that one -- apt-cache
# consumes the option and returns no stanza for it, so the "asked for, not
# returned" comparison reports it unobtainable -- but that is an incidental
# property of one code path, not an invariant. This project's posture elsewhere
# is to make the bad state unrepresentable (`method: script`, mandatory
# `sha256`), and a package name is a package name.
DEB_PACKAGE = re.compile(r"^[a-z0-9][a-z0-9+.-]+(?::[a-z0-9][a-z0-9-]*)?$")


def _check_package_names(names: Sequence[str], field: str) -> None:
    bad = [n for n in names if not DEB_PACKAGE.match(n)]
    if bad:
        raise ManifestError(
            f"{field} contains {bad!r}, which are not Debian package names. "
            f"These become argv for a privileged apt-get, so anything that is "
            f"not a package name is refused here rather than discovered later."
        )


ENDPOINT_REF = re.compile(r"\{endpoint:([a-z0-9_-]+)\}")
CONSENT_ENV = re.compile(r"^HAMMUNITION_ACCEPT_[A-Z0-9_]+$")
STATION_REF = re.compile(r"\{station\.([a-z0-9_]+)\}")


class ManifestError(ValueError):
    """Raised when a manifest is structurally valid but semantically wrong."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Selectors — (distro, version, arch) -> method.  D-002, D-012.
# ---------------------------------------------------------------------------


class Arch(StrEnum):
    x86_64 = "x86_64"
    aarch64 = "aarch64"
    armv7l = "armv7l"


class Selector(Strict):
    """Restricts an install block to some subset of targets.

    An empty selector matches everything and acts as the default. Resolution is
    first-match-wins in list order, so defaults belong last.
    """

    distro: list[str] | None = None
    distro_version: list[str] | None = None
    arch: list[Arch] | None = None

    def matches(self, distro: str, version: str, arch: str) -> bool:
        """An unset dimension matches anything; a set one must contain the value."""
        return (
            (not self.distro or distro in self.distro)
            and (not self.distro_version or version in self.distro_version)
            and (not self.arch or arch in [a.value for a in self.arch])
        )

    @property
    def is_default(self) -> bool:
        return not (self.distro or self.distro_version or self.arch)


# ---------------------------------------------------------------------------
# Verified artifacts.  D-004: no unverified downloads, ever.
# ---------------------------------------------------------------------------


class RemoteArtifact(Strict):
    """A file fetched over the network. Verification is not optional."""

    url: str
    sha256: str = Field(description="Mandatory. There is no unverified path.")
    signature_url: str | None = None
    signing_key_fingerprint: str | None = None

    @model_validator(mode="after")
    def _check(self) -> RemoteArtifact:
        if not SHA256.match(self.sha256):
            raise ManifestError(f"sha256 must be 64 lowercase hex chars: {self.sha256!r}")
        if not self.url.startswith(("https://", "http://")):
            raise ManifestError(f"url must be http(s): {self.url!r}")
        return self


class Patch(Strict):
    """An in-tree source edit. AHRL does these with sed; we declare them."""

    file: str
    description: str
    unified_diff: str | None = None


# ---------------------------------------------------------------------------
# Install methods.  Discriminated union on `method`.
# ---------------------------------------------------------------------------


class AptInstall(Strict):
    method: Literal["apt"] = "apt"
    packages: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> AptInstall:
        _check_package_names(self.packages, "apt packages")
        return self


class SourceInstall(Strict):
    """Build from a verified source archive."""

    method: Literal["source"] = "source"
    source: RemoteArtifact
    build_system: Literal["autotools", "cmake", "qmake", "make", "custom"]
    configure_args: list[str] = Field(default_factory=list)
    build_args: list[str] = Field(default_factory=list)
    compiler_flags: list[str] = Field(
        default_factory=list,
        description="e.g. -Wno-incompatible-pointer-types. Six AHRL units need these.",
    )
    project_file: str | None = Field(
        default=None,
        description="qmake .pro / cmake subdir. MSHV needs a different one per arch.",
    )
    patches: list[Patch] = Field(default_factory=list)
    build_dir: str | None = None


COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")

PinBasis = Literal["distribution_pin", "own_choice"]
"""Where a commit pin's choice of revision came from.

``distribution_pin``
    A distribution already packages this exact commit. **This is the preferred
    basis.** Kali and Parrot both package SDR++ at ``36ea9a1``: two
    distributions independently hit the same missing-tags problem and answered
    it the same way, which makes their commit a review signal upstream stopped
    providing. Pinning it also means a source build and an apt install are the
    same revision rather than two.

``own_choice``
    Nothing packages it and we had to choose. Legitimate, and more expensive: it
    is a judgement nobody else has vetted, so the rationale must say which
    distributions were checked and what they ship instead. Recording that we
    *had to* is the point -- the next reviewer should be able to see whether the
    situation has changed.
"""


class PinReview(Strict):
    """When a commit pin was last looked at, and by whom.  D-024.

    A tag carries an upstream signal: someone decided that revision was worth
    naming. A commit SHA carries none — it is perfectly pinned and perfectly
    arbitrary. When a project stops tagging, pinning a commit is the right
    answer, but it moves a judgement upstream stopped making onto us, and an
    unreviewed commit pin from four years ago is the same failure as an
    abandoned tag pointed the other way.

    So the judgement is recorded rather than implied. This is metadata about
    *our* decision, not about the software, which is why it lives beside the
    ref rather than in documentation.
    """

    last_reviewed: date
    reviewed_by: str = Field(
        min_length=2,
        description="Who looked. A name or handle, so the next reviewer knows who to ask.",
    )
    basis: PinBasis = Field(
        description=(
            "Where the choice of commit came from. `distribution_pin` is strongly "
            "preferred and must name the distributions; `own_choice` requires "
            "saying what was checked and found nothing."
        )
    )
    distributions: list[str] = Field(
        default_factory=list,
        description="Distributions packaging this exact commit. Required for `distribution_pin`.",
    )
    rationale: str = Field(
        min_length=30,
        description=(
            "Why THIS commit rather than any other, and what was checked. "
            "'HEAD at the time' is not a rationale; it is the absence of one."
        ),
    )
    cadence_days: int = Field(
        default=180,
        ge=30,
        le=730,
        description="How long this pin may stand before it must be looked at again.",
    )

    @model_validator(mode="after")
    def _basis(self) -> PinReview:
        if self.basis == "distribution_pin" and not self.distributions:
            raise ManifestError(
                "pin_review basis is 'distribution_pin' but names no distributions. "
                "The whole value of this basis is that somebody else vetted the "
                "revision; say who."
            )
        if self.basis == "own_choice":
            if self.distributions:
                raise ManifestError(
                    "pin_review basis is 'own_choice' but names distributions. If a "
                    "distribution packages this commit, the basis is distribution_pin."
                )
            if len(self.rationale) < 80:
                raise ManifestError(
                    "an 'own_choice' pin_review needs a fuller rationale: which "
                    "distributions were checked, what they ship instead, and why "
                    "this commit. Choosing a revision nobody else vetted is the "
                    "expensive path and the reasoning has to survive the next "
                    "reviewer (D-024)."
                )
        return self

    @property
    def due(self) -> date:
        from datetime import timedelta

        return self.last_reviewed + timedelta(days=self.cadence_days)

    def is_overdue(self, today: date) -> bool:
        return today > self.due


class GitInstall(Strict):
    """Build from a pinned git revision. `ref` must be immutable."""

    method: Literal["git"] = "git"
    repo: str
    ref: str = Field(description="Commit SHA or tag. Never a branch name.")
    build_system: Literal["autotools", "cmake", "qmake", "make", "custom"]
    configure_args: list[str] = Field(default_factory=list)
    compiler_flags: list[str] = Field(default_factory=list)
    pin_review: PinReview | None = Field(
        default=None,
        description="Required when `ref` is a commit SHA rather than a tag. D-024.",
    )

    @model_validator(mode="after")
    def _pinned(self) -> GitInstall:
        if self.ref in {"master", "main", "HEAD", "trunk", "develop"}:
            raise ManifestError(f"ref {self.ref!r} is a moving branch; pin a commit SHA or tag")
        if COMMIT_SHA.match(self.ref) and self.pin_review is None:
            raise ManifestError(
                f"ref {self.ref!r} is a commit SHA and needs a pin_review. A tag carries "
                f"an upstream signal that a revision was worth naming; a SHA carries none, "
                f"so pinning one moves a judgement upstream stopped making onto us. "
                f"Record when it was reviewed, by whom, and why this commit (D-024)."
            )
        if not COMMIT_SHA.match(self.ref) and self.pin_review is not None:
            raise ManifestError(
                f"ref {self.ref!r} is a tag, so pin_review does not apply -- upstream "
                f"already made the judgement this field exists to record"
            )
        return self


class BinaryInstall(Strict):
    """Vendor .deb, archive, or prebuilt executable."""

    method: Literal["binary"] = "binary"
    artifact: RemoteArtifact
    format: Literal["deb", "tarball", "zip", "executable", "appimage"]
    strip_components: int = 0


class VenvInstall(Strict):
    method: Literal["venv"] = "venv"
    requirements: list[str] = Field(min_length=1)
    python: str = ">=3.11"


class PipxInstall(Strict):
    method: Literal["pipx"] = "pipx"
    spec: str
    system_site_packages: bool = False


InstallMethod = Annotated[
    AptInstall | SourceInstall | GitInstall | BinaryInstall | VenvInstall | PipxInstall,
    Field(discriminator="method"),
]


class InstallBlock(Strict):
    """One (selector -> method) pair. The method itself varies, not just its
    argument — js8call is apt on Linux Mint 22.3 and a cmake build elsewhere."""

    when: Selector = Field(default_factory=Selector)
    install: InstallMethod
    build_depends: list[str] = Field(
        default_factory=list,
        description="apt packages needed to BUILD only. Never reported as installed.",
    )
    note: str | None = None

    @model_validator(mode="after")
    def _check(self) -> InstallBlock:
        _check_package_names(self.build_depends, "build_depends")
        return self


# ---------------------------------------------------------------------------
# Outputs: binaries, launchers, service endpoints.
# ---------------------------------------------------------------------------


class Binary(Strict):
    """Explicit build-output -> installed-name mapping.

    This is what dissolves the wsjtx / wsjtx_improved rename dance: both builds
    emit `wsjtx`, so AHRL renames around them. Declaring `install_as` makes the
    collision impossible instead of choreographed.
    """

    produced: str = Field(description="Path the build emits, relative to build dir.")
    install_as: str = Field(description="Final name in the install prefix.")


class ServiceEndpoint(Strict):
    """A remote service the software talks to.

    Exists because AHRL hardcodes `-b hamclock.com:80` into four generated
    launchers, and that host was reported to stop serving in June 2026. A dead
    upstream must be repointable by editing the catalog, not the launchers.
    """

    name: str
    default_url: str
    description: str
    user_configurable: bool = True
    note: str | None = None


class Launcher(Strict):
    """A generated wrapper script. 14 AHRL units need one."""

    name: str
    exec: str = Field(
        description="Command template. May reference {endpoint:NAME}.",
    )
    working_directory: str | None = None
    terminal: bool = False


# ---------------------------------------------------------------------------
# System modifications and config.  D-012, D-016.
# ---------------------------------------------------------------------------


class SystemModification(Strict):
    kind: Literal[
        "udev_rule",
        "modprobe_blacklist",
        "group_create",
        "group_membership",
        "foreign_arch",
        "package_purge",
        "apt_pin",
        "file_shadow",
    ]
    description: str
    detail: str
    reversible: bool
    reverse_hint: str | None = None
    group: str | None = Field(
        default=None,
        description=(
            "For `group_membership`: the group to add the operator to. Required "
            "there, and forbidden elsewhere."
        ),
    )

    @model_validator(mode="after")
    def _group_is_named(self) -> SystemModification:
        """A group membership names its group in a field, never in prose.

        This field exists because the engine needed the name and the only place
        it appeared was inside `detail`, where both manifests happened to write
        it in backticks. Scraping it back out worked on both, which is exactly
        what makes that kind of parser dangerous: adding an operator to the
        wrong group is a privilege change that does not announce itself, and
        the prose is free text that no test constrains.
        """
        if self.kind == "group_membership":
            if not self.group:
                raise ManifestError(
                    "a group_membership modification must name its group in `group`; "
                    "the engine adds the operator to it and will not infer the name "
                    "from the prose in `detail`"
                )
            if not SLUG.match(self.group):
                raise ManifestError(f"group must be a lowercase name: {self.group!r}")
        elif self.group is not None:
            raise ManifestError(
                f"`group` is only meaningful for group_membership, not {self.kind!r}"
            )
        return self

    @model_validator(mode="after")
    def _irreversible_explained(self) -> SystemModification:
        if not self.reversible and not self.reverse_hint:
            raise ManifestError(
                f"irreversible modification {self.kind!r} must explain why in reverse_hint"
            )
        return self


class ConfigFile(Strict):
    """Templated configuration written on the operator's behalf.

    AX.25 forces this into 1.0: its install appends
    `wl2k ${MYCALL} 1200 255 7 Winlink` to /etc/ax25/axports.
    """

    path: str
    template: str = Field(description="May reference {station.callsign} etc.")
    mode: str = "0644"
    append: bool = False
    backup_existing: bool = True

    @property
    def station_variables(self) -> set[str]:
        return set(STATION_REF.findall(self.template))


class AptRepo(Strict):
    """Third-party apt source. Key pinning is mandatory."""

    name: str
    uri: str
    suites: list[str]
    components: list[str]
    key_url: str
    key_fingerprint: str
    rationale: str = Field(description="Shown to the user before the repo is added.")


# ---------------------------------------------------------------------------
# Status, updates, toolkit risk.
# ---------------------------------------------------------------------------


class Status(StrEnum):
    supported = "supported"
    broken = "broken"
    retired = "retired"
    unverifiable = "unverifiable"


class VerdictSource(StrEnum):
    tested = "tested"
    inherited = "inherited"


class RetireReason(StrEnum):
    world_changed = "world_changed"
    never_worked = "never_worked"
    out_of_scope = "out_of_scope"


class UpdateProbe(Strict):
    """How to learn the upstream version.  D-010."""

    method: Literal["apt_policy", "github_release", "github_tags", "binary_version", "pypi", "none"]
    repo: str | None = None
    command: str | None = None
    pattern: str | None = None


class UpdateBlock(Strict):
    probe: UpdateProbe
    strategy: Literal["reinstall", "apt_upgrade", "rebuild", "manual"] = "reinstall"
    cadence_hint: str | None = None


class ToolkitRisk(Strict):
    """Standing exposure register.  D-015.

    The component list is derivable from build_depends; upstream port status and
    the date it was checked are not, which is the whole reason this exists.
    """

    framework: Literal["qt5", "qt6", "gtk2", "gtk3", "gtk4", "wx3.0", "wx3.2", "mono"]
    upstream_port_status: Literal["ported", "in_progress", "no_path", "unknown"]
    checked: date
    note: str | None = None


class Documentation(Strict):
    """Required by CLAUDE.md. A manifest without these cannot ship."""

    what_it_does: str = Field(min_length=20)
    why_you_want_it: str = Field(min_length=20)
    prerequisites: str | None = None
    known_problems: str | None = None
    upstream_url: str
    upstream_support: str | None = None


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------


class PackageManifest(Strict):
    name: str
    version: str
    summary: str
    categories: list[str] = Field(min_length=1, description="Flat tags, D-003.")

    install: list[InstallBlock] = Field(min_length=1)

    depends: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    conflicts_with_repo_package: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list, description="Ordering, not dependency.")

    binaries: list[Binary] = Field(default_factory=list)
    launchers: list[Launcher] = Field(default_factory=list)
    service_endpoints: list[ServiceEndpoint] = Field(default_factory=list)

    apt_repos: list[AptRepo] = Field(default_factory=list)
    system_modifications: list[SystemModification] = Field(default_factory=list)
    config_files: list[ConfigFile] = Field(default_factory=list)

    scope: Literal["system", "user"] = "system"
    status: Status = Status.supported
    status_reason: str | None = None
    status_date: date | None = None
    status_verdict: VerdictSource | None = None
    retire_reason: RetireReason | None = None
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    recommended_default: bool = True

    toolkit_risk: list[ToolkitRisk] = Field(default_factory=list)
    update: UpdateBlock
    documentation: Documentation

    # -- validators ---------------------------------------------------------

    @model_validator(mode="after")
    def _name_is_slug(self) -> PackageManifest:
        if not SLUG.match(self.name):
            raise ManifestError(f"name must be a lowercase slug: {self.name!r}")
        return self

    @model_validator(mode="after")
    def _dependency_names_are_package_names(self) -> PackageManifest:
        """`depends` reaches apt, so it is held to apt's naming rules.

        The field spans two namespaces — a catalog package or a distro one, and
        `plan._pull_catalog_dependencies` resolves which. Both are checked here
        because every catalog name is already a valid Debian package name, and
        the entries that are *not* catalog names go to `apt-cache policy` as
        argv. `conflicts_with_repo_package` names distro packages by
        definition; `provides` names what a build emits, which a later backend
        will resolve against apt the same way.
        """
        _check_package_names(self.depends, f"{self.name}: depends")
        _check_package_names(
            self.conflicts_with_repo_package, f"{self.name}: conflicts_with_repo_package"
        )
        return self

    @model_validator(mode="after")
    def _default_block_last(self) -> PackageManifest:
        for i, block in enumerate(self.install[:-1]):
            if block.when.is_default:
                raise ManifestError(
                    f"{self.name}: unconditional install block at index {i} shadows "
                    f"{len(self.install) - i - 1} later block(s); defaults go last"
                )
        return self

    @model_validator(mode="after")
    def _status_is_explained(self) -> PackageManifest:
        """D-005: a verdict without provenance is not a verdict."""
        if self.status is Status.supported:
            return self
        missing = [
            f
            for f, v in (
                ("status_reason", self.status_reason),
                ("status_date", self.status_date),
                ("status_verdict", self.status_verdict),
            )
            if v is None
        ]
        if missing:
            raise ManifestError(
                f"{self.name}: status={self.status.value} requires {', '.join(missing)}"
            )
        if self.status is Status.retired and self.retire_reason is None:
            raise ManifestError(
                f"{self.name}: retired requires retire_reason (world_changed | "
                f"never_worked | out_of_scope)"
            )
        return self

    @model_validator(mode="after")
    def _provides_excludes_self(self) -> PackageManifest:
        if self.name in self.provides:
            raise ManifestError(f"{self.name}: provides must not list the package itself")
        return self

    @model_validator(mode="after")
    def _endpoint_refs_declared(self) -> PackageManifest:
        """A launcher may not reference an endpoint the manifest does not declare."""
        declared = {e.name for e in self.service_endpoints}
        for launcher in self.launchers:
            for ref in ENDPOINT_REF.findall(launcher.exec):
                if ref not in declared:
                    raise ManifestError(
                        f"{self.name}: launcher {launcher.name!r} references "
                        f"undeclared endpoint {ref!r}"
                    )
        return self

    @model_validator(mode="after")
    def _binaries_unique(self) -> PackageManifest:
        names = [b.install_as for b in self.binaries]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ManifestError(f"{self.name}: duplicate install_as: {sorted(dupes)}")
        return self

    @model_validator(mode="after")
    def _apt_repo_needs_rationale(self) -> PackageManifest:
        for repo in self.apt_repos:
            if len(repo.rationale) < 20:
                raise ManifestError(
                    f"{self.name}: apt repo {repo.name!r} needs a real rationale; "
                    f"it is shown to the user before the repo is added"
                )
        return self

    # -- resolution ---------------------------------------------------------

    def resolve(self, distro: str, distro_version: str, arch: str) -> InstallBlock | None:
        """First matching install block, or None if this target is unsupported."""
        for block in self.install:
            if block.when.matches(distro, distro_version, arch):
                return block
        return None

    @property
    def station_variables(self) -> set[str]:
        out: set[str] = set()
        for cfg in self.config_files:
            out |= cfg.station_variables
        return out


# ---------------------------------------------------------------------------
# Consent gates and profiles.  D-021.
# ---------------------------------------------------------------------------


class RiskCategory(StrEnum):
    """What the software *can do* — never what any jurisdiction says about it.

    Capability is stable and observable. Legality is neither, and asserting it
    would make this project give legal advice it is not qualified to give.
    """

    unlicensed_transmission = "unlicensed_transmission"
    protected_communications = "protected_communications"
    identifier_collection = "identifier_collection"
    third_party_systems = "third_party_systems"
    spectrum_disruption = "spectrum_disruption"
    credential_recovery = "credential_recovery"


RISK_DISCLOSURES: dict[RiskCategory, str] = {
    RiskCategory.unlicensed_transmission: (
        "Can cause connected hardware to emit radio frequency energy, including on "
        "frequencies, at power levels, or in modes that may require a licence or "
        "other authorization."
    ),
    RiskCategory.protected_communications: (
        "Can receive, decode, store or display communications that may be protected "
        "from interception."
    ),
    RiskCategory.identifier_collection: (
        "Can collect identifiers associated with people or their devices, such as "
        "IMSI, IMEI, MAC addresses, or subscriber records."
    ),
    RiskCategory.third_party_systems: (
        "Can interact with, probe or test systems and networks that belong to someone else."
    ),
    RiskCategory.spectrum_disruption: (
        "Can degrade or deny service to other users of the radio spectrum, whether "
        "or not that is the intent."
    ),
    RiskCategory.credential_recovery: (
        "Can recover, crack or replay authentication material such as keys, "
        "passphrases or handshakes."
    ),
}

# Wording that turns a disclosure into an opinion about law. D-021 calls such
# wording a defect; making it a validation error means it cannot ship.
#
# Deliberately narrow. It targets adjudication ("this is illegal", "you may
# not") and jurisdiction ("under FCC rules"). It does NOT ban the words
# "licence" or "authorization", which are exactly what a disclosure must be
# able to say.
LEGAL_ADVICE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:is|are|would be|will be)\s+(?:il)?legal\b", "asserts what is or is not legal"),
    (r"\bunlawful\b", "asserts unlawfulness"),
    (r"\billegal\b", "asserts illegality"),
    (r"\bprohibited\b", "asserts prohibition"),
    (r"\bfelony\b|\bcriminal offen[cs]e\b", "characterises an offence"),
    (r"\byou may not\b|\byou are not allowed\b", "tells the user what they may do"),
    (r"\b(?:FCC|Ofcom|ETSI|ITU|CALEA|GDPR)\b", "names a specific regulator or statute"),
    (r"\bin (?:most|all|many) (?:countries|jurisdictions)\b", "generalises across jurisdictions"),
    (r"\bunder .{0,24}\blaw\b", "cites a body of law"),
    (r"\brequires? a licen[cs]e\b(?!\s+or)", "states a legal requirement as fact"),
)


class ConsentGate(Strict):
    """An affirmative opt-in that `--yes` cannot supply.  D-021.

    The gate discloses a capability and asks the operator to affirm they have
    the authorization they need. It does not decide for them in either
    direction — neither granting permission nor refusing on their behalf.
    """

    risk_categories: list[RiskCategory] = Field(min_length=1)
    env_var: str = Field(description="Scripted path. Separate from --yes, and recorded when used.")
    disclosure: str = Field(
        min_length=40,
        description="What the software can do. Capability, never legality.",
    )
    affirmation: str = Field(
        min_length=20,
        description="The question. Must ask about the operator's authorization.",
    )

    @model_validator(mode="after")
    def _check(self) -> ConsentGate:
        if not CONSENT_ENV.match(self.env_var):
            raise ManifestError(
                f"consent env_var {self.env_var!r} must match HAMMUNITION_ACCEPT_<NAME>; "
                f"a shared or generic variable would let one opt-in satisfy another gate"
            )
        if len(set(self.risk_categories)) != len(self.risk_categories):
            raise ManifestError("consent risk_categories contains duplicates")
        for text, field in ((self.disclosure, "disclosure"), (self.affirmation, "affirmation")):
            for pattern, why in LEGAL_ADVICE_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    raise ManifestError(
                        f"consent {field} reads as legal advice — it {why}. "
                        f"D-021: disclose the capability and ask about authorization; "
                        f"do not adjudicate. Offending text: {text[:80]!r}"
                    )
        if (
            "authoriz" not in self.affirmation.lower()
            and "authoris" not in self.affirmation.lower()
        ):
            raise ManifestError(
                "consent affirmation must ask the operator to affirm their "
                "authorization; anything else is a warning, not a gate"
            )
        return self

    @property
    def risk_lines(self) -> list[str]:
        """Canonical one-line disclosure per declared category."""
        return [f"{c.value}: {RISK_DISCLOSURES[c]}" for c in self.risk_categories]


class ProfileDocumentation(Strict):
    """Required by CLAUDE.md for every profile."""

    what_it_installs: str = Field(min_length=20)
    why_together: str = Field(min_length=20)
    deliberately_excludes: str = Field(min_length=10)
    manual_configuration: str = Field(min_length=10)
    disk_footprint_hint: str | None = None


class ProfileManifest(Strict):
    """A named bundle of packages.  Flat tags with overlap, D-003."""

    name: str
    summary: str
    packages: list[str] = Field(min_length=1)
    stage: Literal["1.0", "post-1.0"] = "1.0"
    consent: ConsentGate | None = None
    documentation: ProfileDocumentation

    @model_validator(mode="after")
    def _check(self) -> ProfileManifest:
        if not SLUG.match(self.name):
            raise ManifestError(f"profile name {self.name!r} must be a lowercase slug")
        if len(set(self.packages)) != len(self.packages):
            raise ManifestError(f"profile {self.name}: duplicate package entries")
        return self
