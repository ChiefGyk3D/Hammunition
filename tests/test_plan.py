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
        # A method with no backend. `pipx` rather than `venv`, which the engine
        # implements now (2026-08-30) -- the point of this entry is
        # "unimplemented", so it has to name something that still is.
        "unbuildable": _manifest(
            name="unbuildable",
            install=[{"install": {"method": "pipx", "spec": "example"}}],
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
            install=[{"install": {"method": "pipx", "spec": "example-tool"}}],
        )
    }
    with pytest.raises(PlanError) as exc:
        _resolve(tmp_path, ["example"], catalog=catalog)
    assert "'pipx' backend" in exc.value.blockers[0].reason


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


def _resolvable(monkeypatch: Any, name: str = "operator") -> None:
    """Make pwd.getpwnam accept the test's fake operator, so resolution's
    'is this a real user' check (which prevents a mid-transaction gpasswd
    failure) does not reject the placeholder every group test uses."""
    import pwd

    real = pwd.getpwnam

    def fake(n: str) -> Any:
        if n == name:
            return real("root")  # any real struct; only that it resolves matters
        return real(n)

    monkeypatch.setattr(pwd, "getpwnam", fake)


def test_a_group_membership_is_planned_with_its_group(tmp_path: Path, monkeypatch: Any) -> None:
    _resolvable(monkeypatch)
    plan = _resolve(tmp_path, ["example"], catalog={"example": _with_group()})
    assert plan.group_memberships[0].group == "dialout"
    assert plan.group_memberships[0].user == "operator"


def test_an_operator_that_names_no_account_is_blocked_before_apt_runs(
    tmp_path: Path,
) -> None:
    """`--user nosuchuser` used to sail through resolution — user_groups()
    returns {} for an unknown name — and fail on gpasswd mid-transaction,
    after apt had already changed the machine. D-016 wants it caught here."""
    with pytest.raises(PlanError) as exc:
        _resolve(
            tmp_path,
            ["example"],
            catalog={"example": _with_group()},
            user="nosuchuser-hammunition-test",
        )
    reason = exc.value.blockers[0].reason
    assert "is not a user on this system" in reason


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


# ---------------------------------------------------------------------------
# Source builds: build_depends go through the same pre-flight apt check
# ---------------------------------------------------------------------------


def _source_manifest(**install: Any) -> PackageManifest:
    block: dict[str, Any] = {
        "method": "source",
        "source": {"url": "https://example.invalid/example-1.0.tar.gz", "sha256": "a" * 64},
        "build_system": "autotools",
    }
    block.update(install)
    return _manifest(
        install=[{"install": block, "build_depends": ["libexample-dev", "fftw2"]}],
        update={"probe": {"method": "none"}},
    )


def test_build_depends_are_what_a_source_build_installs(tmp_path: Path) -> None:
    """A source build installs its toolchain from apt, not itself. The manifest's
    own name is not an apt package and must not be treated as one."""
    plan = _resolve(
        tmp_path,
        ["example"],
        catalog={"example": _source_manifest()},
        known={"libexample-dev": None, "fftw2": None},
    )
    planned = plan.packages[0]
    assert set(planned.apt_packages) == {"libexample-dev", "fftw2"}
    assert set(planned.build_only) == {"libexample-dev", "fftw2"}
    assert "example" not in planned.apt_packages


def test_a_stale_build_dependency_is_caught_before_anything_is_built(tmp_path: Path) -> None:
    """D-016's whole point, now reaching source builds. glfer's real
    build_depends name `fftw2` and `libgtk2.0-dev`, two of the four AHRL
    dependency lines suspected of having gone stale years ago — nothing in AHRL
    ever asked apt whether they still exist. This asks, before the compiler is
    installed rather than after it fails."""
    with pytest.raises(PlanError) as caught:
        _resolve(
            tmp_path,
            ["example"],
            catalog={"example": _source_manifest()},
            known={"libexample-dev": None},  # fftw2 has no candidate
        )
    message = str(caught.value)
    assert "fftw2" in message
    assert "build_depends" in message, "the blocker must say it is a build dependency"


def test_an_unimplemented_build_system_is_refused_during_resolution(tmp_path: Path) -> None:
    """Not mid-build. Discovering it after apt has already installed a toolchain
    is the fix-one-re-run shape resolution exists to prevent."""
    with pytest.raises(PlanError, match="custom"):
        _resolve(
            tmp_path,
            ["example"],
            catalog={"example": _source_manifest(build_system="custom")},
            known={"libexample-dev": None, "fftw2": None},
        )


def test_declared_patches_are_refused_during_resolution(tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="patch"):
        _resolve(
            tmp_path,
            ["example"],
            catalog={
                "example": _source_manifest(
                    patches=[{"file": "src/main.c", "description": "a patch we cannot apply"}]
                )
            },
            known={"libexample-dev": None, "fftw2": None},
        )


def test_a_depends_naming_another_manifest_is_not_asked_of_apt(tmp_path: Path) -> None:
    """`depends` holds names in two namespaces. One naming another manifest is
    pulled into the plan as a catalog package, and must not *also* be probed as
    a distro package — apt has never heard of `libacars`, so asking would report
    the transaction unsatisfiable because something we are about to build from
    source is not in the archive.

    Found by writing the real acarsdec manifest, which depends on our own
    libacars: the planner's docstring already described the intended behaviour
    and the code did the other thing.
    """
    library = _manifest(
        name="library",
        install=[
            {
                "install": {
                    "method": "source",
                    "source": {"url": "https://example.invalid/l.tar.gz", "sha256": "c" * 64},
                    "build_system": "cmake",
                },
                "build_depends": ["cmake"],
            }
        ],
        update={"probe": {"method": "none"}},
    )
    consumer = _manifest(
        name="consumer",
        depends=["library", "libreal-dev"],
        # `depends` pulls the catalog package in; `after` is what orders it.
        # They are separate on purpose (a runtime dependency need not build
        # first), which does mean a source library needs both — the real
        # acarsdec manifest declares both for exactly this reason.
        after=["library"],
        install=[
            {
                "install": {
                    "method": "source",
                    "source": {"url": "https://example.invalid/c.tar.gz", "sha256": "d" * 64},
                    "build_system": "cmake",
                },
                "build_depends": ["cmake"],
            }
        ],
        update={"probe": {"method": "none"}},
    )

    plan = _resolve(
        tmp_path,
        ["consumer"],
        catalog={"library": library, "consumer": consumer},
        known={"cmake": None, "libreal-dev": None},  # note: no "library"
    )

    names = [p.name for p in plan.packages]
    assert "library" in names, "the catalog dependency was not pulled in"
    assert names.index("library") < names.index("consumer"), "it must build first"
    assert "library" not in plan.apt_to_install, "a catalog package was sent to apt"
    assert "libreal-dev" in plan.apt_to_install, "a genuine distro dependency was dropped"
