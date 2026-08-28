# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pre-flight resolution.  D-016.

The contract under test is not "the planner resolves packages". It is:

* every failure is reported **together**, not the first one;
* a package the engine cannot install is **refused by name**, never skipped;
* a manifest's ``depends`` is **checked against apt**, because D-016's evidence
  is four AHRL dependency lines that have been silently failing for years;
* nothing is executed to find any of this out.

The last one is why every test here uses a recording runner. A planner that
needed a real apt to be tested would be a planner nobody tested.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import AptBackend, RecordingRunner  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.manifest.schema import PackageManifest, ProfileManifest  # noqa: E402
from hammunition.plan import PlanError, resolve  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")


def _manifest(**overrides: Any) -> PackageManifest:
    base: dict[str, Any] = {
        "name": "example",
        "version": "1.0",
        "summary": "An example package",
        "categories": ["digital-modes"],
        "install": [{"install": {"method": "apt", "packages": ["example"]}}],
        "update": {"probe": {"method": "apt_policy"}},
        "documentation": {
            "what_it_does": "Does an example thing for the purposes of testing.",
            "why_you_want_it": "Because the test suite requires a valid manifest.",
            "upstream_url": "https://example.invalid/",
        },
    }
    base.update(overrides)
    return PackageManifest.model_validate(base)


def _profile(**overrides: Any) -> ProfileManifest:
    base: dict[str, Any] = {
        "name": "example-profile",
        "summary": "An example profile",
        "packages": ["example"],
        "documentation": {
            "what_it_installs": "An example package, for the purposes of testing.",
            "why_together": "They are together because the test needs them to be.",
            "deliberately_excludes": "Everything else.",
            "manual_configuration": "Nothing at all.",
        },
    }
    base.update(overrides)
    return ProfileManifest.model_validate(base)


def _apt(tmp_path: Path, known: dict[str, str | None], *, populated: bool = True) -> AptBackend:
    """An apt that knows exactly *known*: name -> installed version, or None."""
    lists = tmp_path / ("lists-populated" if populated else "lists-empty")
    lists.mkdir(exist_ok=True)
    if populated:
        (lists / "example.invalid_dists_trixie_main_binary-amd64_Packages").touch()

    class Apt(AptBackend):
        def probe(self, packages: Any) -> Any:
            from hammunition.backends.apt import AptPackageState

            return {
                name: AptPackageState(name=name, installed=known[name], candidate="1.0")
                for name in packages
                if name in known
            }

    return Apt(RecordingRunner(), lists_dir=lists)


def _resolve(tmp_path: Path, names: list[str], **kwargs: Any) -> Any:
    catalog = kwargs.pop("catalog", {"example": _manifest()})
    profiles = kwargs.pop("profiles", {})
    known = kwargs.pop("known", {"example": None})
    return resolve(
        names,
        catalog=catalog,
        profiles=profiles,
        target=kwargs.pop("target", TARGET),
        apt=kwargs.pop("apt", None) or _apt(tmp_path, known),
        user=kwargs.pop("user", "operator"),
    )


# ---------------------------------------------------------------------------
# The happy path exists, and it does not touch the machine
# ---------------------------------------------------------------------------


def test_a_plain_package_resolves(tmp_path: Path) -> None:
    plan = _resolve(tmp_path, ["example"])
    assert [p.name for p in plan.packages] == ["example"]
    assert plan.apt_to_install == ("example",)


def test_an_already_installed_package_produces_no_work(tmp_path: Path) -> None:
    """Idempotency: every operation is safe to re-run (CLAUDE.md)."""
    plan = _resolve(tmp_path, ["example"], known={"example": "1.0"})
    assert plan.apt_to_install == ()
    assert plan.is_empty


def test_resolution_executes_nothing(tmp_path: Path) -> None:
    apt = _apt(tmp_path, {"example": None})
    _resolve(tmp_path, ["example"], apt=apt)
    runner = apt.runner
    assert isinstance(runner, RecordingRunner)
    assert [c for c in runner.commands if c.requires_root] == []


def test_a_profile_expands_and_says_who_asked(tmp_path: Path) -> None:
    plan = _resolve(
        tmp_path,
        ["example-profile"],
        profiles={"example-profile": _profile()},
    )
    assert plan.packages[0].requested_by == ("profile example-profile",)


# ---------------------------------------------------------------------------
# D-016: every failure at once
# ---------------------------------------------------------------------------


def test_all_blockers_are_reported_together_not_just_the_first(tmp_path: Path) -> None:
    """The single most important property in this module.

    AHRL's defining defect is discovering failures one at a time, mid-run, and
    proceeding past each. Reporting only the first blocker would be the same
    shape: the operator fixes it, re-runs, and meets the next one.

    Three *different* failure modes, chosen so they all reach the final report
    rather than an early exit. The first version of this test used three
    unknown names, which bail out of ``resolve`` before the loop and left the
    check passing against a deliberately broken planner — the exact "silently
    passing on the input it exists to catch" failure the standing rule in
    CLAUDE.md is about.
    """
    catalog = {
        "unbuildable": _manifest(
            name="unbuildable",
            install=[
                {
                    "install": {
                        "method": "git",
                        "repo": "https://example.invalid/x.git",
                        "ref": "v1.0",
                        "build_system": "cmake",
                    }
                }
            ],
        ),
        "known-broken": _manifest(
            name="known-broken",
            status="broken",
            status_reason="fails to build against current wxWidgets",
            status_date="2026-08-01",
            status_verdict="tested",
        ),
        "elsewhere-only": _manifest(
            name="elsewhere-only",
            install=[
                {
                    "when": {"distro": ["parrot"]},
                    "install": {"method": "apt", "packages": ["elsewhere-only"]},
                }
            ],
        ),
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, sorted(catalog), catalog=catalog, known={})

    assert len(exc.value.blockers) == 3
    assert {b.subject for b in exc.value.blockers} == set(catalog)


def test_unknown_names_are_all_reported_together_too(tmp_path: Path) -> None:
    """The early-exit path has its own report, and it gathers as well."""
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["nope-one", "nope-two", "nope-three"])
    assert len(exc.value.blockers) == 3


def test_an_unknown_name_is_a_blocker_with_a_remedy(tmp_path: Path) -> None:
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["nosuch"])
    blocker = exc.value.blockers[0]
    assert "not a package or profile" in blocker.reason
    assert blocker.remedy and "list" in blocker.remedy


# ---------------------------------------------------------------------------
# D-016: depends goes through apt
# ---------------------------------------------------------------------------


def test_depends_is_installed_alongside_the_package(tmp_path: Path) -> None:
    catalog = {"example": _manifest(depends=["libhamlib4"])}
    plan = _resolve(
        tmp_path,
        ["example"],
        catalog=catalog,
        known={"example": None, "libhamlib4": None},
    )
    assert plan.apt_to_install == ("example", "libhamlib4")


def test_a_dependency_apt_has_never_heard_of_stops_the_run(tmp_path: Path) -> None:
    """This is the fftw2 / libgtk2.0-dev / libportaudio-ocaml-dev case.

    D-016 names four AHRL dependency lines suspected of failing silently. The
    only reason nobody knows is that nothing ever asked apt.
    """
    catalog = {"example": _manifest(depends=["fftw2"])}
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog=catalog, known={"example": None})
    reason = exc.value.blockers[0].reason
    assert "no candidate for fftw2" in reason
    assert "depends" in reason, "the report must say the name came from `depends`"


def test_a_depends_naming_another_manifest_pulls_it_in(tmp_path: Path) -> None:
    catalog = {
        "example": _manifest(depends=["helper"]),
        "helper": _manifest(
            name="helper", install=[{"install": {"method": "apt", "packages": ["helper"]}}]
        ),
    }
    plan = _resolve(
        tmp_path,
        ["example"],
        catalog=catalog,
        known={"example": None, "helper": None},
    )
    assert {p.name for p in plan.packages} == {"example", "helper"}


# ---------------------------------------------------------------------------
# Refusals, always by name
# ---------------------------------------------------------------------------


def test_a_method_with_no_backend_is_refused_by_name(tmp_path: Path) -> None:
    """Not skipped. A capability matrix reporting coverage the engine does not
    have is the shim CLAUDE.md forbids."""
    catalog = {
        "example": _manifest(
            install=[
                {
                    "install": {
                        "method": "git",
                        "repo": "https://example.invalid/x.git",
                        "ref": "v1.0",
                        "build_system": "cmake",
                    }
                }
            ]
        )
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog=catalog)
    assert "'git' backend" in exc.value.blockers[0].reason


def test_an_unsupported_target_is_refused_rather_than_shimmed(tmp_path: Path) -> None:
    catalog = {
        "example": _manifest(
            install=[
                {
                    "when": {"distro": ["parrot"]},
                    "install": {"method": "apt", "packages": ["example"]},
                }
            ]
        )
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog=catalog)
    assert "no install block matching debian 13" in exc.value.blockers[0].reason


def test_a_package_recorded_as_broken_is_not_installed_quietly(tmp_path: Path) -> None:
    catalog = {
        "example": _manifest(
            status="broken",
            status_reason="fails to build against current wxWidgets",
            status_date="2026-08-01",
            status_verdict="tested",
        )
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog=catalog)
    assert "marked broken" in exc.value.blockers[0].reason


def test_a_third_party_repo_is_refused_until_the_engine_can_pin_a_key(tmp_path: Path) -> None:
    catalog = {
        "example": _manifest(
            apt_repos=[
                {
                    "name": "vendor",
                    "uri": "https://example.invalid/apt",
                    "suites": ["stable"],
                    "components": ["main"],
                    "key_url": "https://example.invalid/key.gpg",
                    "key_fingerprint": "0" * 40,
                    "rationale": "x" * 40,
                }
            ]
        )
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog=catalog)
    assert "third-party apt repositories" in exc.value.blockers[0].reason


def test_an_unimplemented_system_modification_is_refused(tmp_path: Path) -> None:
    catalog = {
        "example": _manifest(
            system_modifications=[
                {
                    "kind": "udev_rule",
                    "description": "Writes a udev rule",
                    "detail": "installs 60-example.rules",
                    "reversible": True,
                }
            ]
        )
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog=catalog)
    assert "'udev_rule'" in exc.value.blockers[0].reason


def test_empty_apt_lists_are_reported_as_such_not_as_missing_packages(tmp_path: Path) -> None:
    """Answering 'none of these packages exist' on a fresh image is a lie."""
    apt = _apt(tmp_path, {}, populated=False)
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], apt=apt)
    blocker = exc.value.blockers[0]
    assert blocker.subject == "apt"
    assert blocker.remedy and "apt-get update" in blocker.remedy


def test_refresh_turns_the_empty_lists_blocker_into_a_disclosed_note(tmp_path: Path) -> None:
    """The blocker's own remedy says "pass --refresh". For the first shipped
    version, resolve() never learned the flag existed, so a fresh machine got
    an error telling the operator to pass the flag they had just passed --
    there was no way to install anything except running apt-get update by
    hand, contradicting both the blocker text and docs/reference/cli.md."""
    apt = _apt(tmp_path, {}, populated=False)
    plan = resolve(
        ["example"],
        catalog={"example": _manifest()},
        profiles={},
        target=TARGET,
        apt=apt,
        user="operator",
        refresh=True,
    )
    assert plan.apt_to_install == ("example",)
    # The lost pre-flight candidate check is disclosed, not silently skipped.
    assert plan.notes and "cannot be known" in plan.notes[0]


def test_refresh_with_populated_lists_still_probes(tmp_path: Path) -> None:
    """--refresh on a machine with lists is an update, not an excuse to skip
    the candidate check that is still perfectly possible."""
    apt = _apt(tmp_path, {"example": None})
    plan = resolve(
        ["example"],
        catalog={"example": _manifest()},
        profiles={},
        target=TARGET,
        apt=apt,
        user="operator",
        refresh=True,
    )
    assert plan.apt_to_install == ("example",)
    assert not plan.notes


# ---------------------------------------------------------------------------
# Group membership
# ---------------------------------------------------------------------------


def _with_group(**extra: Any) -> PackageManifest:
    return _manifest(
        system_modifications=[
            {
                "kind": "group_membership",
                "group": "dialout",
                "description": "Adds the operator to dialout",
                "detail": "serial access",
                "reversible": True,
            }
        ],
        **extra,
    )


def test_a_group_membership_is_planned_with_its_group(tmp_path: Path) -> None:
    plan = _resolve(tmp_path, ["example"], catalog={"example": _with_group()})
    assert plan.group_memberships[0].group == "dialout"
    assert plan.group_memberships[0].user == "operator"


def test_no_operator_means_no_privilege_change(tmp_path: Path) -> None:
    """`gpasswd --add '' wireshark` is what this test exists to prevent; it was
    built for real on the first end-to-end run, as root in a container with
    neither $USER nor $SUDO_USER set."""
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog={"example": _with_group()}, user="")
    assert "no operator could be identified" in exc.value.blockers[0].reason


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_after_orders_the_transaction(tmp_path: Path) -> None:
    """wsjtx-improved is `after: [wsjtx]` because both emit a binary called
    wsjtx and the later one must win."""
    catalog = {
        "wsjtx": _manifest(
            name="wsjtx", install=[{"install": {"method": "apt", "packages": ["wsjtx"]}}]
        ),
        "wsjtx-improved": _manifest(
            name="wsjtx-improved",
            after=["wsjtx"],
            install=[{"install": {"method": "apt", "packages": ["wsjtx-improved"]}}],
        ),
    }
    plan = _resolve(
        tmp_path,
        ["wsjtx-improved", "wsjtx"],
        catalog=catalog,
        known={"wsjtx": None, "wsjtx-improved": None},
    )
    assert [p.name for p in plan.packages] == ["wsjtx", "wsjtx-improved"]


def test_an_after_naming_an_absent_package_is_satisfied_by_absence(tmp_path: Path) -> None:
    catalog = {"example": _manifest(after=["not-in-this-transaction"])}
    plan = _resolve(tmp_path, ["example"], catalog=catalog)
    assert [p.name for p in plan.packages] == ["example"]


def test_an_ordering_cycle_is_reported_rather_than_looping(tmp_path: Path) -> None:
    # Two-character names because a Debian package name must be at least two
    # characters (policy 5.6.1) and the schema now holds manifests to that --
    # these strings become argv for a privileged apt-get.
    catalog = {
        "aa": _manifest(
            name="aa", after=["bb"], install=[{"install": {"method": "apt", "packages": ["aa"]}}]
        ),
        "bb": _manifest(
            name="bb", after=["aa"], install=[{"install": {"method": "apt", "packages": ["bb"]}}]
        ),
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["aa", "bb"], catalog=catalog, known={"aa": None, "bb": None})
    assert any("cycle" in b.reason for b in exc.value.blockers)


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def test_a_gated_profile_carries_its_gate_into_the_plan(tmp_path: Path) -> None:
    profile = _profile(
        name="gated",
        consent={
            "env_var": "HAMMUNITION_ACCEPT_TESTING",
            "risk_categories": ["unlicensed_transmission"],
            "disclosure": "This software can drive connected hardware to transmit radio energy.",
            "affirmation": "Do you affirm you hold the authorization you need?",
        },
    )
    plan = _resolve(tmp_path, ["gated"], profiles={"gated": profile})
    assert plan.consent_gates[0][0] == "gated"
    assert plan.consent_gates[0][1].env_var == "HAMMUNITION_ACCEPT_TESTING"
