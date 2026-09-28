# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan as data: ``install``/``uninstall --dry-run --json``.  D-059.

The text plan is the operator's whole disclosure, so the refactor that makes
it render from a dataclass must not move a byte: the golden text below was
captured from ``render_plan`` *before* the refactor and is compared after it.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import Action, Command
from hammunition.desktop import Desktop
from hammunition.distro import Target
from hammunition.manifest.schema import AptRepo, ConfigFile, ConsentGate, PackageManifest
from hammunition.plan import Deferral, GroupMembership, InstallPlan, PlannedPackage, RepoAddition
from json_support import assert_golden_text

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)


def _unit(name: str, install: dict[str, Any], **extra: Any) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": f"The {name} fixture",
            "categories": ["digital-modes"],
            "install": [{"install": install, **extra}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a unit in the plan golden test.",
                "why_you_want_it": "Every section of the plan needs something to show.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def rich_plan() -> tuple[InstallPlan, list[Any]]:
    """An install plan with every section of the text populated."""
    apt = _unit("fixture-apt", {"method": "apt", "packages": ["fixture-apt", "libfixture1"]})
    quiet = _unit(
        "fixture-quiet",
        {"method": "apt", "packages": ["fixture-quiet"], "install_recommends": False},
    )
    source = _unit(
        "fixture-source",
        {
            "method": "source",
            "source": {
                "url": "https://example.invalid/fixture-source-2.1.tar.gz",
                "sha256": "30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4",
            },
            "build_system": "autotools",
        },
        build_depends=["build-essential"],
    )
    data = _unit(
        "fixture-data",
        {
            "method": "data",
            "artifacts": [
                {
                    "url": "https://example.invalid/cty.dat",
                    "sha256": "30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4",
                    "size": 1_433_600,
                    "install_as": "cty.dat",
                }
            ],
            "licence": "free with notice ",
            "licence_url": "https://example.invalid/licence",
        },
    )
    repo = AptRepo(
        name="fixture-repo",
        uri="https://example.invalid/apt",
        suites=["stable"],
        components=["main"],
        key_url="https://example.invalid/key.asc",
        key_fingerprint="0123456789ABCDEF0123456789ABCDEF01234567",
        rationale="The fixture archive is the only source of fixture-repo-tool.",
    )
    gate = ConsentGate.model_validate(
        {
            "env_var": "HAMMUNITION_ACCEPT_FIXTURE_GATED",
            "risk_categories": ["identifier_collection"],
            "disclosure": "This fixture stands in for software that can receive identifiers.",
            "affirmation": "Do you affirm that you have the authorization you need?",
        }
    )
    plan = InstallPlan(
        target=TARGET,
        packages=(
            PlannedPackage(
                manifest=apt,
                block=apt.install[0],
                apt_packages=("fixture-apt", "libfixture1"),
                already_installed=("libfixture1",),
                requested_by=("fixture-station",),
                displaces=("fixture-apt-legacy",),
            ),
            PlannedPackage(manifest=quiet, block=quiet.install[0], apt_packages=("fixture-quiet",)),
            PlannedPackage(
                manifest=source,
                block=source.install[0],
                apt_packages=("build-essential",),
                build_only=("build-essential",),
            ),
            PlannedPackage(manifest=data, block=data.install[0], apt_packages=()),
        ),
        group_memberships=(
            GroupMembership(
                group="dialout",
                user="op",
                package="fixture-apt",
                description="serial access",
                detail="Lets the operator open serial ports: rig CAT cables, TNCs and GPS "
                "receivers. It also grants every other serial device on the machine.",
                reverse_hint="sudo gpasswd -d op dialout ",
            ),
        ),
        consent_gates=(("fixture-gated", gate),),
        notes=("fixture-source shadows nothing on PATH; this note is here to be wrapped " * 2,),
        deferrals=(
            Deferral(
                subject="fixture-apt",
                what="/etc/fixture.conf not written",
                why="no callsign set",
                remedy="hammunition station set --callsign N0TST",
            ),
            Deferral(
                subject="fixture-tray",
                what="will not be installed (profile fixture-station)",
                why="for KDE Plasma; this machine has no KDE Plasma session (it has: Xfce)",
                remedy="the rest installs without it; on a machine that gains a KDE Plasma "
                "session, `hammunition install fixture-station` again picks it up",
                kind="package",
            ),
        ),
        desktops_read=frozenset({Desktop.xfce}),
        sessions_unrecognised=("sway.desktop",),
        config_files=(
            (
                "fixture-apt",
                ConfigFile(path="/etc/fixture-apt.conf", template="call {station.callsign}"),
                "call N0TST",
            ),
        ),
        apt_release="trixie-backports",
        apt_from_release=("libfixture1",),
        apt_repos=(
            RepoAddition(
                unit="fixture-apt",
                repo=repo,
                sources="/etc/apt/sources.list.d/fixture-repo.sources",
                keyring="/etc/apt/keyrings/fixture-repo.gpg",
                packages=("fixture-repo-tool",),
            ),
        ),
    )
    commands: list[Any] = [
        Command(
            argv=("apt-get", "install", "--yes", "--", "fixture-apt"),
            description="Install the apt packages",
            requires_root=True,
        ),
        Action(
            kind="fetch",
            description="Fetch and verify the fixture-source tarball",
            detail="https://example.invalid/fixture-source-2.1.tar.gz",
            perform=lambda: "fetched",
        ),
    ]
    return plan, commands


def test_the_text_plan_is_unchanged_byte_for_byte() -> None:
    plan, commands = rich_plan()
    lines = cli.render_plan(
        plan,
        commands,
        euid=1000,
        built=frozenset(),
        log_destination=Path("/home/op/.local/state/hammunition/transactions.jsonl"),
        hands_log_to="op",
    )
    assert_golden_text("plan-install-text", "\n".join(lines) + "\n")


def test_every_section_of_the_fixture_is_populated() -> None:
    """Guards the guard: a section left empty in the fixture is a section the
    byte-for-byte test does not cover."""
    plan, _commands = rich_plan()
    for name in (f.name for f in dataclasses.fields(plan)):
        assert getattr(plan, name), f"rich_plan() leaves {name} empty"
    assert plan.apt_to_install_no_recommends


@pytest.mark.parametrize("euid", [0, 1000])
def test_the_rendered_plan_names_every_command(euid: int) -> None:
    plan, commands = rich_plan()
    text = "\n".join(cli.render_plan(plan, commands, euid=euid))
    for command in commands:
        assert command.display(euid=euid) in text


# The map section (D-057), captured from #121's own rendering before the move.
# Synthetic regions: a region is station data and no real one belongs here.


def _catalog_unit(name: str) -> PackageManifest:
    import yaml

    root = Path(__file__).resolve().parent.parent
    return PackageManifest.model_validate(
        yaml.safe_load((root / "catalog" / "packages" / f"{name}.yaml").read_text())
    )


def _region(region: str, size: int, *, pinned: bool) -> Any:
    from hammunition.geofabrik import RegionFile

    return RegionFile(
        region=region,
        snapshot="260101",
        url=f"https://example.invalid/{region}-260101.osm.pbf",
        size=size,
        sha256="30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4"
        if pinned
        else None,
        md5=None if pinned else "0123456789abcdef0123456789abcdef",
    )


def maps_plan() -> tuple[InstallPlan, Any]:
    from hammunition.backends.regions import KeptRegion, MapDisclosure

    regions = _catalog_unit("osm-regions")
    navit = _catalog_unit("osm-navit")
    fetched = _region("test-land/region-one", 52_428_800, pinned=True)
    longer = _region("test-land/a-longer-region-name", 3_145_728, pinned=False)
    current = _region("test-land/region-current", 10_485_760, pinned=True)
    idle = _region("test-land/idle", 1_048_576, pinned=True)
    maps = MapDisclosure(
        fetch=(fetched, longer),
        current=(current, idle),
        kept=(
            KeptRegion(
                region="test-land/region-kept",
                slug="test-land-region-kept",
                snapshot="250101",
                reason="The index did not answer; the installed map stays as it is, "
                "and this reason is long enough to be wrapped onto a second line.",
            ),
            KeptRegion(
                region="test-land/region-unrecorded",
                slug="test-land-region-unrecorded",
                snapshot=None,
                reason="No snapshot was recorded for it.",
            ),
        ),
        convert=(fetched, current),
    )
    plan = InstallPlan(
        target=TARGET,
        packages=(
            PlannedPackage(manifest=regions, block=regions.install[0], apt_packages=()),
            PlannedPackage(manifest=navit, block=navit.install[0], apt_packages=()),
        ),
    )
    return plan, maps


def test_the_map_section_text_is_unchanged_byte_for_byte() -> None:
    plan, maps = maps_plan()
    lines = cli.render_plan(plan, [], euid=1000, maps=maps)
    assert_golden_text("plan-maps-text", "\n".join(lines) + "\n")


def test_no_map_section_without_a_disclosure() -> None:
    plan, _maps = maps_plan()
    assert "Map regions" not in "\n".join(cli.render_plan(plan, [], euid=1000))


def test_the_map_section_is_in_the_view_and_renders_from_it() -> None:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view

    plan, maps = maps_plan()
    view = build_install_view(plan, [], euid=1000, maps=maps)
    assert view.maps is not None
    assert [f.region for f in view.maps.fetch] == [
        "test-land/region-one",
        "test-land/a-longer-region-name",
    ]
    assert [f.nothing_to_do for f in view.maps.current] == [False, True]
    assert view.maps.kept[1].snapshot is None
    assert view.maps.convert[0].estimate > 0
    text = "\n".join(render_plan_view(view, target=target_view(plan.target))) + "\n"
    assert text == (Path(__file__).parent / "fixtures" / "json" / "plan-maps-text.txt").read_text()


def test_a_disclosure_with_nothing_in_it_is_no_map_section() -> None:
    from hammunition.backends.regions import MapDisclosure
    from hammunition.interface.plan import build_install_view

    plan, _maps = maps_plan()
    empty = MapDisclosure(fetch=(), current=(), kept=())
    assert build_install_view(plan, [], euid=1000, maps=empty).maps is None


def test_the_plan_document_never_carries_a_rendered_config_file() -> None:
    """The ruling: the plan carries what the text prints, and the text prints a
    config file's path, never its rendered body -- which holds the callsign."""
    from hammunition.interface.envelope import dumps, target_view
    from hammunition.interface.plan import PlanDocument, build_install_view

    plan, commands = rich_plan()
    rendered = plan.config_files[0][2]
    assert "N0TST" in rendered
    doc = PlanDocument(
        action="install",
        requested=("fixture-station",),
        outcome="planned",
        target=target_view(plan.target),
        blockers=(),
        install=build_install_view(plan, commands, euid=1000),
        removal=None,
    )
    text = dumps(doc)
    assert "/etc/fixture-apt.conf" in text
    assert rendered not in text
    assert "template" not in text


def test_the_navit_config_step_reads_the_same_in_the_text_and_the_json(tmp_path: Path) -> None:
    """#130's Navit step names the centre and the follow; it is a step
    description, so the view carries it verbatim and the text prints it."""
    from hammunition.geofabrik import RegionFile
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view
    from test_regions_backend import _converted, _derived, _install_region, navit_manifest

    region = RegionFile(
        "test-land/region-one", "260101", "https://example.invalid/r.osm.pbf", 10, None, None
    )
    _install_region(tmp_path, region)
    _converted(tmp_path, region)
    navit = navit_manifest()
    block = navit.install[0].install
    steps: list[Any] = _derived(tmp_path, [region]).steps(navit, block)  # type: ignore[arg-type]
    config_step = steps[-1]
    assert "centred on the first region" in config_step.description
    assert 'follow="1"' in config_step.description
    plan, _maps = maps_plan()
    view = build_install_view(plan, steps, euid=1000)
    assert view.commands[-1].description == config_step.description
    text = "\n".join(render_plan_view(view, target=target_view(plan.target)))
    assert f"  # {config_step.description}" in text
