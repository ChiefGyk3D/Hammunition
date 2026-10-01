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
from hammunition.country_boundaries import BoundarySource
from hammunition.desktop import Desktop
from hammunition.distro import Target
from hammunition.manifest.schema import AptRepo, ConfigFile, ConsentGate, PackageManifest
from hammunition.plan import Deferral, GroupMembership, InstallPlan, PlannedPackage, RepoAddition
from hammunition.userservice import HEADER, PlannedUserService
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
        user_services=(
            PlannedUserService(
                name="hammunition-rigctld",
                description="hamlib rigctld for the station's rig",
                exec_argv=(
                    "/usr/bin/rigctld",
                    "-m",
                    "1035",
                    "-r",
                    "/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0",
                    "-s",
                    "38400",
                    "-T",
                    "127.0.0.1",
                    "-t",
                    "4532",
                ),
                unit_body=HEADER + "\n[Service]\nExecStart=/usr/bin/rigctld\n",
                device_path="/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0",
                filled_from=("rig", "rig_baud", "rig_device"),
                listens=(("127.0.0.1", 4532),),
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


BOUNDARY = BoundarySource(
    path=Path("/usr/local/share/hammunition/data/country-boundaries/ne.geojson"),
    url="https://example.invalid/ne_10m_admin_0_countries.geojson",
    size=13_287_234,
    sha256="239eec57ac17f100a11e2536cffc56752c318b50ae765b0918ff7aab4ce8f255",
    licence="Public domain (Natural Earth's terms of use)",
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
        # The address-search fix: region-one's country is known and its
        # border is merged; region-current's is not, and it was built by an
        # older converter.
        boundaries=BOUNDARY,
        countries={"test-land/region-one": ("TL",)},
        converter_changed=frozenset({"test-land-region-current"}),
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


def test_the_map_section_discloses_the_border_merge_and_minus_u() -> None:
    """D-057 amendment: the boundary download (size, licence, how it is
    checked), the merge step, maptool's -U, and a converter-changed rebuild
    are all in the plan, in the view and in the text rendered from it."""
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view

    plan, maps = maps_plan()
    view = build_install_view(plan, [], euid=1000, maps=maps)
    assert view.maps is not None and view.maps.boundaries is not None
    border = view.maps.boundaries
    assert (border.size, border.size_human) == (13_287_234, "13.3 MB")
    assert border.verified_by == "sha256, pinned by Hammunition"
    assert border.licence.startswith("Public domain")
    assert view.maps.unknown_country is True
    one, current = view.maps.convert
    assert (one.countries, one.converter_changed) == (("TL",), False)
    assert (current.countries, current.converter_changed) == ((), True)
    text = "\n".join(render_plan_view(view, target=target_view(plan.target)))
    assert "about 47.2 MB  border: TL" in text
    assert "about 9.4 MB  border: none known  (converter changed)" in text
    assert "osmium merge" in text and "-U" in text
    assert "13.3 MB" in text and "sha256, pinned by Hammunition" in text


def test_without_a_boundary_file_the_plan_still_says_minus_u() -> None:
    import dataclasses

    from hammunition.interface.plan import build_install_view

    plan, maps = maps_plan()
    bare = dataclasses.replace(maps, boundaries=None, countries={})
    view = build_install_view(plan, [], euid=1000, maps=bare)
    assert view.maps is not None and view.maps.boundaries is None
    text = "\n".join(cli.render_plan(plan, [], euid=1000, maps=bare))
    assert "-U" in text and "border:" not in text and "osmium" not in text


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
    # What the file is filled from is named, so a dry run is a faithful
    # summary of it -- by the value's name, never the value.
    assert doc.install is not None
    (line,) = doc.install.config_files
    assert line.fills == ("callsign",)


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


# The Packages list and the Map regions section must agree (bench,
# 2026-09-28): with every region installed and current and every Navit map
# built, the Packages list said `will fetch+install` and `will convert` one
# screen above "already installed, current". Synthetic regions only.


def _state_plan(**disclosure: Any) -> tuple[InstallPlan, Any]:
    from hammunition.backends.regions import MapDisclosure

    plan, _maps = maps_plan()
    fields = {"fetch": (), "current": (), "kept": (), "convert": ()}
    return plan, MapDisclosure(**{**fields, **disclosure})


def _states(plan: InstallPlan, maps: Any) -> tuple[dict[str, str], str]:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view

    view = build_install_view(plan, [], euid=1000, maps=maps)
    text = "\n".join(render_plan_view(view, target=target_view(plan.target)))
    return {p.name: p.state for p in view.packages}, text


def _line(name: str, state: str) -> str:
    return f"  {name:<28} {state:<18} ["


def test_every_region_current_and_every_map_built_reads_already_installed() -> None:
    one = _region("test-land/region-one", 1_048_576, pinned=True)
    two = _region("test-land/region-two", 2_097_152, pinned=True)
    plan, maps = _state_plan(current=(one, two))
    states, text = _states(plan, maps)
    assert states == {"osm-regions": "already installed", "osm-navit": "already installed"}
    assert _line("osm-regions", "already installed") in text
    assert _line("osm-navit", "already installed") in text
    assert "already installed, current:" in text
    assert "will fetch+install" not in text and "will convert" not in text


def test_a_region_to_fetch_keeps_the_fetch_and_convert_wording() -> None:
    one = _region("test-land/region-one", 1_048_576, pinned=True)
    two = _region("test-land/region-two", 2_097_152, pinned=True)
    plan, maps = _state_plan(fetch=(two,), current=(one,), convert=(two,))
    states, text = _states(plan, maps)
    assert states == {"osm-regions": "will fetch+install", "osm-navit": "will convert"}
    assert _line("osm-regions", "will fetch+install") in text
    assert _line("osm-navit", "will convert") in text


def test_current_regions_with_a_map_still_to_build_say_so_per_unit() -> None:
    one = _region("test-land/region-one", 1_048_576, pinned=True)
    plan, maps = _state_plan(current=(one,), convert=(one,))
    states, _text = _states(plan, maps)
    assert states == {"osm-regions": "already installed", "osm-navit": "will convert"}


def test_a_region_that_could_not_be_checked_is_not_called_current() -> None:
    from hammunition.backends.regions import KeptRegion

    one = _region("test-land/region-one", 1_048_576, pinned=True)
    kept = KeptRegion(
        region="test-land/region-kept", slug="test-land-region-kept", snapshot="250101", reason="x"
    )
    plan, maps = _state_plan(current=(one,), kept=(kept,))
    states, _text = _states(plan, maps)
    assert states == {"osm-regions": "will fetch+install", "osm-navit": "will convert"}


def test_no_disclosure_keeps_the_method_wording() -> None:
    plan, _maps = maps_plan()
    states, _text = _states(plan, None)
    assert states == {"osm-regions": "will fetch+install", "osm-navit": "will convert"}


def test_the_json_package_state_agrees_with_the_map_section() -> None:
    from hammunition.interface.envelope import dumps, target_view
    from hammunition.interface.plan import PlanDocument, build_install_view

    one = _region("test-land/region-one", 1_048_576, pinned=True)
    plan, maps = _state_plan(current=(one,))
    doc = PlanDocument(
        action="install",
        requested=("navigation",),
        outcome="planned",
        target=target_view(plan.target),
        blockers=(),
        install=build_install_view(plan, [], euid=1000, maps=maps),
        removal=None,
    )
    import json

    body = json.loads(dumps(doc))["install"]
    assert {p["name"]: p["state"] for p in body["packages"]} == {
        "osm-regions": "already installed",
        "osm-navit": "already installed",
    }
    assert [r["nothing_to_do"] for r in body["maps"]["current"]] == [True]
