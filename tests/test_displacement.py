# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Rules for software that displaces a distribution's choice.  D-022.

The first instance is an editor and feels minor. The pattern is not: it recurs
for dump1090-mutability against readsb, for vendor SDR drivers against the
distribution's, and for anything where upstream ships newer than the archive.
These assert the rule rather than the instance.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.base import Command
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import PackageManifest

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "packages"
FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")


@pytest.fixture(scope="module")
def catalog() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG)


def _with_repos(catalog: dict[str, PackageManifest]) -> list[PackageManifest]:
    return [m for m in catalog.values() if m.apt_repos]


def test_third_party_repos_pin_a_full_fingerprint(catalog: dict[str, PackageManifest]) -> None:
    """A short key id is forgeable. Pin all forty hex digits."""
    for manifest in _with_repos(catalog):
        for repo in manifest.apt_repos:
            assert FINGERPRINT.match(repo.key_fingerprint), (
                f"{manifest.name}: repo {repo.name!r} fingerprint "
                f"{repo.key_fingerprint!r} is not 40 uppercase hex digits"
            )


def test_third_party_repos_explain_the_scope_of_what_is_granted(
    catalog: dict[str, PackageManifest],
) -> None:
    """D-022: adding a vendor repo is larger than installing one package.

    The rationale is shown to the operator before the repo is added, so it has
    to say what is actually being granted, not just name a URL.
    """
    for manifest in _with_repos(catalog):
        for repo in manifest.apt_repos:
            assert len(repo.rationale) >= 100, (
                f"{manifest.name}: repo {repo.name!r} rationale is too short to "
                f"have disclosed anything"
            )
            assert "update" in repo.rationale.lower(), (
                f"{manifest.name}: repo {repo.name!r} rationale must say the "
                f"vendor gains the ability to ship updates"
            )


def test_packages_adding_a_repo_are_never_a_default(
    catalog: dict[str, PackageManifest],
) -> None:
    """D-022 rule 5: opt-in, and not in any getting-started profile."""
    for manifest in _with_repos(catalog):
        assert manifest.recommended_default is False, (
            f"{manifest.name} adds a third-party repository and must not be a recommended default"
        )


def test_adding_a_repo_is_a_declared_reversible_modification(
    catalog: dict[str, PackageManifest],
) -> None:
    """Rule 2: never silently, and reversible with a stated command."""
    for manifest in _with_repos(catalog):
        mods = [m for m in manifest.system_modifications if m.kind == "apt_pin"]
        assert mods, f"{manifest.name} adds a repo but declares no system_modification"
        for mod in mods:
            assert mod.reversible, f"{manifest.name}: adding a repo must be reversible"
            assert mod.reverse_hint and "rm " in mod.reverse_hint, (
                f"{manifest.name}: reverse_hint must give the actual command"
            )


def test_displacement_never_purges(catalog: dict[str, PackageManifest]) -> None:
    """Rule 1: coexistence is the default.

    AHRL removes the distribution's librtlsdr with no record. Nothing in this
    catalog purges a distribution package as a side effect of installing
    something else.
    """
    for manifest in catalog.values():
        purges = [m for m in manifest.system_modifications if m.kind == "package_purge"]
        assert not purges, (
            f"{manifest.name} purges a package as part of installing. D-022: "
            f"removal is a separate act the operator asks for."
        )


def test_the_vscode_instance_documents_both_sides(catalog: dict[str, PackageManifest]) -> None:
    """Rule 4: state the distribution's reasoning as a reason, not an obstacle."""
    manifest = catalog["code"]
    problems = (manifest.documentation.known_problems or "").lower()
    for phrase in ("proprietary", "telemetry", "vscodium"):
        assert phrase in problems, f"the trade-off must name {phrase!r}"
    why = manifest.documentation.why_you_want_it.lower()
    assert "marketplace" in why, "the functional counter-argument must be stated"


def test_the_vscode_instance_does_not_remove_vscodium(
    catalog: dict[str, PackageManifest],
) -> None:
    manifest = catalog["code"]
    assert "codium" not in manifest.conflicts_with_repo_package
    assert "codium" not in " ".join(m.detail for m in manifest.system_modifications).lower()


# ---------------------------------------------------------------------------
# The consumer for conflicts_with_repo_package (2026-08-30): the split is
# decided by method — a vendor .deb collides at the dpkg level and is refused
# at plan time; a source build shadows on PATH and is disclosed.
# ---------------------------------------------------------------------------


def _conflicting_manifest(method_block: dict[str, Any]) -> PackageManifest:

    base: dict[str, Any] = {
        "name": "clasher",
        "version": "1.0",
        "summary": "Fixture that declares a repo conflict",
        "categories": ["digital-modes"],
        "conflicts_with_repo_package": ["distro-owned"],
        "install": [{"install": method_block}],
        "update": {"probe": {"method": "none"}, "strategy": "manual"},
        "documentation": {
            "what_it_does": "Exists so the conflict consumer has a unit.",
            "why_you_want_it": "You do not; the suite does.",
            "upstream_url": "https://example.invalid/",
        },
    }
    return PackageManifest.model_validate(base)


def _plan_with_conflict(tmp_path: Path, method_block: dict[str, Any], installed: bool) -> Any:

    from hammunition.distro import Target
    from hammunition.plan import resolve
    from test_plan import _apt  # reuse the fake-apt helper

    manifest = _conflicting_manifest(method_block)
    known = {
        "distro-owned": "1.0" if installed else None,
        "clasher": None,
        "git": None,
        "build-essential": None,
    }
    apt = _apt(tmp_path, known)
    return resolve(
        ["clasher"],
        catalog={"clasher": manifest},
        profiles={},
        target=Target(distro="debian", version="13", arch="x86_64"),
        apt=apt,
        user="op",
    )


DEB_BLOCK: dict[str, Any] = {
    "method": "binary",
    "artifact": {"url": "https://example.org/x.deb", "sha256": "0" * 64},
    "format": "deb",
    "deb_package": "vendor-unit",
}
GIT_BLOCK: dict[str, Any] = {
    "method": "git",
    "repo": "https://example.org/x",
    "ref": "1.0",
    "build_system": "make",
}


def test_a_vendor_deb_conflicting_with_an_installed_package_is_refused(tmp_path: Path) -> None:
    import pytest as _pytest

    from hammunition.plan import PlanError

    with _pytest.raises(PlanError, match="collides with installed distribution"):
        _plan_with_conflict(tmp_path, DEB_BLOCK, installed=True)


def test_a_source_build_shadowing_an_installed_package_is_disclosed_not_refused(
    tmp_path: Path,
) -> None:
    plan = _plan_with_conflict(tmp_path, GIT_BLOCK, installed=True)
    assert plan.packages[0].displaces == ("distro-owned",)


def test_an_uninstalled_conflict_is_silent(tmp_path: Path) -> None:
    plan = _plan_with_conflict(tmp_path, DEB_BLOCK, installed=False)
    assert plan.packages[0].displaces == ()


# ---------------------------------------------------------------------------
# The same conflict, arriving inside the transaction (2026-09-02): on a clean
# machine nothing is installed, so the check above is silent, and the apt
# step then installs the conflicting package minutes before the .deb lands.
# ---------------------------------------------------------------------------


def _plan_with_in_transaction_conflict(tmp_path: Path, pulled_in: set[str]) -> Any:
    from hammunition.distro import Target
    from hammunition.plan import resolve
    from test_plan import _apt, _manifest

    clasher = _conflicting_manifest(DEB_BLOCK)
    # An ordinary apt unit whose dependency chain (per the simulated apt
    # below) brings in the package the .deb collides with -- jtdx to
    # wsjtx-improved's wsjtx-data.
    puller = _manifest(
        name="puller", install=[{"install": {"method": "apt", "packages": ["puller"]}}]
    )
    known: dict[str, str | None] = {"distro-owned": None, "clasher": None, "puller": None}
    apt = _apt(tmp_path, known)

    class SimulatingApt(type(apt)):  # type: ignore[misc]
        def simulate(self, packages: Any, *, release: str | None = None) -> Any:
            from hammunition.backends.apt import AptSimulation

            assert "puller" in packages
            return AptSimulation(
                ok=True, installs={p: frozenset({"stable"}) for p in ("puller", *pulled_in)}
            )

    apt.__class__ = SimulatingApt
    return resolve(
        ["clasher", "puller"],
        catalog={"clasher": clasher, "puller": puller},
        profiles={},
        target=Target(distro="debian", version="13", arch="x86_64"),
        apt=apt,
        user="op",
    )


def test_a_vendor_deb_conflicting_with_what_the_transaction_installs_is_refused(
    tmp_path: Path,
) -> None:
    """`digital-modes` on a clean Kali: `jtdx` pulled `wsjtx-data`, the
    `wsjtx-improved` .deb then collided with it at the dpkg step. The plan
    had passed, because nothing was installed when it looked."""
    from hammunition.plan import PlanError

    with pytest.raises(PlanError) as excinfo:
        _plan_with_in_transaction_conflict(tmp_path, pulled_in={"distro-owned"})
    text = str(excinfo.value)
    assert "this same transaction would install: distro-owned" in text
    assert "leave out either clasher" in text


def test_an_apt_step_that_does_not_pull_the_conflict_is_silent(tmp_path: Path) -> None:
    plan = _plan_with_in_transaction_conflict(tmp_path, pulled_in={"something-else"})
    assert [p.name for p in plan.packages] == ["clasher", "puller"]


def test_every_transaction_with_apt_work_is_simulated_once_before_anything_runs(
    tmp_path: Path,
) -> None:
    """The first version asked apt's resolver only when a vendor .deb declared
    a conflict, to spare every operator one apt call. The same night a clean
    Parrot failed six of fifteen profiles at the apt step, after the plan had
    passed, over a downgrade only the resolver could see (D-038). One call
    per transaction is the price of D-016 meaning what it says."""
    from hammunition.backends.base import RecordingRunner
    from test_plan import _apt, _resolve

    apt = _apt(tmp_path, {"example": None})
    _resolve(tmp_path, ["example"], apt=apt)
    assert isinstance(apt.runner, RecordingRunner)
    simulations = [c for c in apt.runner.commands if "--simulate" in c.argv]
    assert len(simulations) == 1
    assert simulations[0].argv[-1] == "example"
    assert not simulations[0].requires_root


def test_a_transaction_with_nothing_outstanding_is_not_simulated(tmp_path: Path) -> None:
    """Everything already installed: apt would say so and be right, and the
    call would be the one D-016 does not need."""
    from hammunition.backends.base import RecordingRunner
    from test_plan import _apt, _resolve

    apt = _apt(tmp_path, {"example": "1.0-1"})
    _resolve(tmp_path, ["example"], apt=apt)
    assert isinstance(apt.runner, RecordingRunner)
    assert not [c for c in apt.runner.commands if "--simulate" in c.argv]


def test_parse_simulation_keeps_inst_lines_only_and_drops_the_arch() -> None:
    from hammunition.backends.apt import parse_simulation

    out = (
        "NOTE: This is only a simulation!\n"
        "Inst wsjtx-data (2.7.0+repack-1 Debian:13.1/stable [all])\n"
        "Inst jtdx:i386 (2.2.159 Debian:13.1/stable [i386])\n"
        "Remv old-thing [1.0]\n"
        "Conf wsjtx-data (2.7.0+repack-1 Debian:13.1/stable [all])\n"
    )
    assert parse_simulation(out) == {
        "wsjtx-data": frozenset({"stable"}),
        "jtdx": frozenset({"stable"}),
    }


def test_parse_simulation_reads_every_archive_a_version_is_offered_from() -> None:
    """Parrot's `Inst` lines, 2026-09-02: a backports-only package names one
    archive; a version that main and security both carry names both, and
    is *not* counted as coming from either alone."""
    from hammunition.backends.apt import AptSimulation, parse_simulation

    out = (
        "Inst cmake (3.31.6-2~bpo13+1 Parrot 7 Echo Parakeet:parrot-backports [amd64])\n"
        "Inst libkrb5-dev (1.21.3-5+deb13u1 Parrot 7 Echo Parakeet:parrot, "
        "Parrot 7 Echo Parakeet:parrot-security [amd64])\n"
        "Inst wsjtx-data (2.7.0+repack-1 Debian:13.1/stable [all])\n"
    )
    installs = parse_simulation(out)
    assert installs["cmake"] == {"parrot-backports"}
    assert installs["libkrb5-dev"] == {"parrot", "parrot-security"}
    assert installs["wsjtx-data"] == {"stable"}
    assert AptSimulation(ok=True, installs=installs).from_archive("parrot-backports") == ("cmake",)
    assert AptSimulation(ok=True, installs=installs).from_archive("parrot") == ()


# ---------------------------------------------------------------------------
# What apt would REMOVE (issue #42, D-022)
# ---------------------------------------------------------------------------

# `apt-get install --simulate --yes -- wsjtx-improved` on a Kali guest with
# the archive's `wsjtx 3.0.2+dfsg-2` installed, 2026-09-07. The archive's
# `wsjtx-improved` carries `Breaks: wsjtx` and its `-data` breaks
# `wsjtx-data`, so apt resolves the request by removing all three.
KALI_REMV = (
    "NOTE: This is only a simulation!\n"
    "Remv wsjtx [3.0.2+dfsg-2]\n"
    "Remv wsjtx-data [3.0.2+dfsg-2]\n"
    "Remv wsjtx-doc [3.0.2+dfsg-2]\n"
    "Inst wsjtx-improved-data (3.1.0+260522+repack-1 kali-rolling [all])\n"
    "Inst wsjtx-improved (3.1.0+260522+repack-1 kali-rolling [amd64])\n"
    "Inst wsjtx-improved-doc (3.1.0+260522+repack-1 kali-rolling [all])\n"
    "Conf wsjtx-improved-data (3.1.0+260522+repack-1 kali-rolling [all])\n"
)


def test_parse_removals_reads_the_recorded_remv_lines_and_drops_the_arch() -> None:
    """The parser read only `Inst` lines and said so in its docstring; the
    exact transcript above passed through it with the three removals unseen."""
    from hammunition.backends.apt import parse_removals

    assert parse_removals(KALI_REMV) == {
        "wsjtx": "3.0.2+dfsg-2",
        "wsjtx-data": "3.0.2+dfsg-2",
        "wsjtx-doc": "3.0.2+dfsg-2",
    }
    assert parse_removals("Remv jtdx:i386 [2.2.159]\n") == {"jtdx": "2.2.159"}
    assert parse_removals("Inst x (1 a [all])\nConf x (1 a [all])\n") == {}


def test_simulate_carries_what_apt_would_remove() -> None:
    from hammunition.backends import AptBackend, CommandResult
    from hammunition.backends.base import RecordingRunner

    argv = ("apt-get", "install", "--simulate", "--yes", "--", "wsjtx-improved")
    runner = RecordingRunner(
        {shlex.join(argv): CommandResult(argv=argv, returncode=0, stdout=KALI_REMV, stderr="")}
    )
    simulation = AptBackend(runner).simulate(["wsjtx-improved"])
    assert simulation.ok
    assert set(simulation.installs) == {
        "wsjtx-improved",
        "wsjtx-improved-data",
        "wsjtx-improved-doc",
    }
    assert simulation.removes == {
        "wsjtx": "3.0.2+dfsg-2",
        "wsjtx-data": "3.0.2+dfsg-2",
        "wsjtx-doc": "3.0.2+dfsg-2",
    }


def _plan_with_removal(tmp_path: Path, removes: dict[str, str], *, declared: bool) -> Any:
    from hammunition.distro import Target
    from hammunition.plan import resolve
    from test_plan import _apt, _manifest

    displacer = _manifest(
        name="displacer",
        install=[{"install": {"method": "apt", "packages": ["displacer"]}}],
        conflicts_with_repo_package=["distro-owned"] if declared else [],
    )
    apt = _apt(tmp_path, {"displacer": None, "distro-owned": "1.0-1"})

    class SimulatingApt(type(apt)):  # type: ignore[misc]
        def simulate(self, packages: Any, *, release: str | None = None) -> Any:
            from hammunition.backends.apt import AptSimulation

            return AptSimulation(
                ok=True, installs={"displacer": frozenset({"stable"})}, removes=dict(removes)
            )

    apt.__class__ = SimulatingApt
    return resolve(
        ["displacer"],
        catalog={"displacer": displacer},
        profiles={},
        target=Target(distro="kali", version="rolling", arch="x86_64"),
        apt=apt,
        user="op",
    )


def test_an_apt_step_that_would_remove_an_installed_package_is_refused(tmp_path: Path) -> None:
    """D-022: coexist, disclose, never remove silently. The archive's
    `wsjtx-improved` cannot coexist with `wsjtx` (`Breaks:`), so apt removes
    it; the plan says which package, which version, and which unit, and stops
    on an untouched machine. The operator removes it, or leaves the unit out."""
    from hammunition.plan import PlanError

    with pytest.raises(PlanError) as excinfo:
        _plan_with_removal(tmp_path, {"distro-owned": "1.0-1"}, declared=True)
    text = str(excinfo.value)
    assert "displacer" in text
    assert "distro-owned (1.0-1)" in text
    assert "sudo apt-get remove distro-owned" in text


def test_a_removal_no_manifest_declares_is_refused_and_named_as_a_manifest_gap(
    tmp_path: Path,
) -> None:
    """The same refusal when nothing in the transaction declared the conflict:
    the removal is still named, and so is the field that should have named it."""
    from hammunition.plan import PlanError

    with pytest.raises(PlanError) as excinfo:
        _plan_with_removal(tmp_path, {"distro-owned": "1.0-1"}, declared=False)
    text = str(excinfo.value)
    assert "distro-owned (1.0-1)" in text
    assert "conflicts_with_repo_package" in text


def test_an_apt_step_that_removes_nothing_is_silent(tmp_path: Path) -> None:
    plan = _plan_with_removal(tmp_path, {}, declared=True)
    assert [p.name for p in plan.packages] == ["displacer"]


def test_the_apt_install_step_never_lets_apt_remove(tmp_path: Path) -> None:
    """Belt to the plan's braces: if the real solve disagrees with the
    simulation, apt errors (`Packages need to be removed but remove is
    disabled`, exit 100) instead of removing."""
    from hammunition.backends import AptBackend
    from hammunition.backends.base import RecordingRunner

    (command,) = AptBackend(RecordingRunner()).install_commands(["wsjtx-improved"])
    assert "--no-remove" in command.argv
    assert command.argv.index("--no-remove") < command.argv.index("--")


def test_the_post_fetch_simulate_never_lets_apt_remove(tmp_path: Path) -> None:
    """The executor's second simulate runs over the fetched .deb and the apt
    step together, after the plan has already refused every named removal;
    it asks the resolver the same question the install step will, so it is
    asked with the same flag."""
    from hammunition.backends import AptBackend
    from hammunition.backends.base import RecordingRunner
    from hammunition.execute import commands_for
    from hammunition.plan import InstallPlan, PlannedPackage
    from test_binary_backend import TARGET, _backend, _manifest

    manifest = _manifest("https://example.invalid/x.deb", "0" * 64, "deb", binaries=[])
    plan = InstallPlan(
        target=TARGET,
        packages=(
            PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=("libdep",)),
        ),
    )
    steps = commands_for(plan, AptBackend(RecordingRunner()), binary=_backend(tmp_path))
    simulate = next(s for s in steps if isinstance(s, Command) and "--simulate" in s.argv)
    assert "--no-remove" in simulate.argv
