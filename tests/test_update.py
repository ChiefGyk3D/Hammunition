# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""`hammunition update`: installed versus the catalog, as a report. D-053.

Every manifest has carried an update block since D-010 and nothing read it.
The report compares apt units against the local lists and built units
against the catalog's pin through the D-051 attribution, runs nothing, and
says plainly that upstream was not asked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends.apt import AptPackageState  # noqa: E402
from hammunition.cli.main import build_parser, cmd_update  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402
from hammunition.update import (  # noqa: E402
    BEHIND_PIN,
    CANDIDATE_DIFFERS,
    MANUAL,
    NOT_INSTALLED,
    ON_INSTALL,
    UNKNOWN,
    UP_TO_DATE,
    render,
    report,
    requested_units,
)

TARGET = Target(distro="debian", version="13", arch="x86_64")


def _manifest(name: str, install: dict[str, Any], **extra: Any) -> PackageManifest:
    body: dict[str, Any] = {
        "name": name,
        "version": "1.0",
        "summary": "Fixture",
        "categories": ["sdr"],
        "install": [{"install": install}],
        "update": {"probe": {"method": "none"}, "strategy": "reinstall"},
        "documentation": {
            "what_it_does": "Stands in for a unit under the update report.",
            "why_you_want_it": "To measure the report.",
            "upstream_url": "https://example.invalid/",
        },
    }
    body.update(extra)
    return PackageManifest.model_validate(body)


def _apt(name: str, *packages: str, strategy: str = "apt_upgrade") -> PackageManifest:
    return _manifest(
        name,
        {"method": "apt", "packages": list(packages)},
        update={"probe": {"method": "apt_policy"}, "strategy": strategy},
    )


def _git(name: str, ref: str = "v1.0", probe: str = "github_tags") -> PackageManifest:
    return _manifest(
        name,
        {
            "method": "git",
            "repo": "https://example.invalid/thing",
            "ref": ref,
            "build_system": "cmake",
        },
        binaries=[{"produced": name, "install_as": name}],
        update={"probe": {"method": probe}, "strategy": "rebuild"},
    )


def _plan(*manifests: PackageManifest, **flags: Any) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(
                manifest=m,
                block=m.install[0],
                apt_packages=(),
                **{k: v for k, v in flags.items() if k in PlannedPackage.__dataclass_fields__},
            )
            for m in manifests
        ),
    )


def _state(name: str, installed: str | None, candidate: str | None) -> AptPackageState:
    return AptPackageState(name=name, installed=installed, candidate=candidate)


# --- apt units -------------------------------------------------------------


def test_an_apt_unit_whose_candidate_matches_is_up_to_date() -> None:
    rep = report(
        _plan(_apt("rtl-sdr", "rtl-sdr")),
        apt_states={"rtl-sdr": _state("rtl-sdr", "2.0.1-1", "2.0.1-1")},
        present={},
        built=(),
    )
    (row,) = rep.rows
    assert row.state == UP_TO_DATE
    assert "2.0.1-1" in row.detail
    assert rep.upgradable == ()


def test_an_apt_unit_whose_candidate_differs_names_both_versions_and_the_package() -> None:
    rep = report(
        _plan(_apt("gqrx", "gqrx-sdr", "libvolk")),
        apt_states={
            "gqrx-sdr": _state("gqrx-sdr", "2.17.5-1", "2.17.6-1"),
            "libvolk": _state("libvolk", "3.1-1", "3.1-1"),
        },
        present={},
        built=(),
    )
    (row,) = rep.rows
    assert row.state == CANDIDATE_DIFFERS
    assert "gqrx-sdr 2.17.5-1 -> 2.17.6-1" in row.detail
    assert row.upgradable == ("gqrx-sdr",)
    # the command offers only the differing package, upgrade-only, no removal
    text = render(rep, lists_note="x")
    assert "apt-get install --yes --only-upgrade --no-remove -- gqrx-sdr" in text
    assert "libvolk" not in text.split("--only-upgrade")[1]


def test_an_apt_unit_with_a_package_missing_is_not_installed() -> None:
    rep = report(
        _plan(_apt("x", "pkg-a", "pkg-b")),
        apt_states={"pkg-a": _state("pkg-a", "1", "1"), "pkg-b": _state("pkg-b", None, "1")},
        present={},
        built=(),
    )
    assert rep.rows[0].state == NOT_INSTALLED
    assert rep.rows[0].detail == "pkg-b"


def test_an_installed_apt_package_with_no_candidate_is_disclosed_not_called_stale() -> None:
    # A package installed from a repository no longer configured: apt has no
    # candidate. That is not "up to date" in the ordinary sense and not a
    # pending upgrade either; the row says exactly what apt knows.
    rep = report(
        _plan(_apt("x", "pkg-a")),
        apt_states={"pkg-a": _state("pkg-a", "1", None)},
        present={},
        built=(),
    )
    assert rep.rows[0].state == UP_TO_DATE
    assert "no candidate in the archive as configured: pkg-a" in rep.rows[0].detail


# --- built units -----------------------------------------------------------


def test_a_build_attributed_at_this_pin_is_up_to_date() -> None:
    rep = report(_plan(_git("thing")), apt_states={}, present={"thing": True}, built=("thing",))
    assert rep.rows[0].state == UP_TO_DATE
    assert "ref v1.0" in rep.rows[0].detail


def test_a_build_on_disk_but_not_attributed_is_behind_the_pin_and_install_is_the_remedy() -> None:
    rep = report(_plan(_git("thing", ref="v2.0")), apt_states={}, present={"thing": True}, built=())
    (row,) = rep.rows
    assert row.state == BEHIND_PIN
    assert "ref v2.0" in row.detail
    assert "hammunition install thing" in render(rep, lists_note="x")


def test_a_build_whose_effects_are_absent_is_not_installed() -> None:
    rep = report(_plan(_git("thing")), apt_states={}, present={"thing": False}, built=())
    assert rep.rows[0].state == NOT_INSTALLED


def test_a_build_that_declares_nothing_checkable_is_unknown_not_guessed() -> None:
    rep = report(_plan(_git("thing")), apt_states={}, present={"thing": None}, built=())
    assert rep.rows[0].state == UNKNOWN
    assert "declares no binaries and no tree marker" in rep.rows[0].detail


def test_upstream_probes_are_named_but_not_consulted() -> None:
    rep = report(
        _plan(_git("thing", probe="github_release")),
        apt_states={},
        present={"thing": True},
        built=(),
    )
    assert rep.upstream_declared == ("thing",)
    text = render(rep, lists_note="x")
    assert "Upstream was not consulted: 1 unit(s)" in text
    assert "Nothing above was executed." in text.splitlines()[-1]


# --- other strategies --------------------------------------------------------


def test_a_manual_strategy_shows_its_cadence_hint() -> None:
    m = _manifest(
        "hand",
        {"method": "apt", "packages": ["hand"]},
        update={
            "probe": {"method": "none"},
            "strategy": "manual",
            "cadence_hint": "check the vendor page each spring",
        },
    )
    rep = report(_plan(m), apt_states={}, present={}, built=())
    assert rep.rows[0].state == MANUAL
    assert rep.rows[0].detail == "check the vendor page each spring"


def test_a_venv_unit_is_rechecked_on_install_rather_than_compared_offline() -> None:
    m = _manifest(
        "pyt",
        {
            "method": "venv",
            "python": ">=3.12",
            "requirements": ["pyt==1.0 --hash=sha256:" + "0" * 64],
        },
        update={"probe": {"method": "pypi"}, "strategy": "reinstall"},
    )
    rep = report(_plan(m), apt_states={}, present={}, built=())
    assert rep.rows[0].state == ON_INSTALL


# --- the default request comes from the log ----------------------------------


def test_requested_units_reads_every_begin_including_failed_ones() -> None:
    # The field laptop's first full install failed after its apt step and
    # still installed a thousand packages; a default that read only clean
    # endings hid ninety units. The report looks at apt and the disk anyway.
    entries: list[dict[str, Any]] = [
        {"event": "transaction_begin", "packages": ["a", "b"]},
        {"event": "transaction_end"},
        {"event": "transaction_begin", "packages": ["c"]},
        {"event": "transaction_failed"},
        {"event": "transaction_begin", "packages": ["d", "a"]},
        {"event": "transaction_end"},
        {"event": "transaction_begin", "packages": ["e"]},  # interrupted: no ending
    ]
    assert requested_units(entries) == ("a", "b", "c", "d", "e")


def test_a_manual_hint_is_cut_to_its_first_sentence() -> None:
    m = _manifest(
        "hand",
        {"method": "apt", "packages": ["hand"]},
        update={
            "probe": {"method": "none"},
            "strategy": "manual",
            "cadence_hint": "Upstream posts numbered zips; re-pin by hand. Note the URL moved.",
        },
    )
    rep = report(_plan(m), apt_states={}, present={}, built=())
    assert (
        rep.rows[0].detail == "Upstream posts numbered zips; re-pin by hand. (more in the manifest)"
    )


def test_the_summary_line_counts_every_state_once() -> None:
    rep = report(
        _plan(_apt("u", "pkg-u"), _git("g")),
        apt_states={"pkg-u": _state("pkg-u", "1", "2")},
        present={"g": True},
        built=("g",),
    )
    text = render(rep, lists_note="last refreshed today")
    assert "1 up to date, 1 with a different apt candidate, 0 behind the catalog's pin" in text
    assert "apt lists: last refreshed today" in text


# --- the command exists ------------------------------------------------------


def test_update_is_a_subcommand_with_optional_names() -> None:
    args = build_parser().parse_args(["update"])
    assert args.func is cmd_update
    assert args.names == []
    args = build_parser().parse_args(["update", "sdr", "rtl-sdr"])
    assert args.names == ["sdr", "rtl-sdr"]
