# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The D-036 menu layer: one taxonomy, per-user, both measured mechanisms."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hammunition.manifest.schema import PackageManifest
from hammunition.menus import (
    Category,
    DesktopIdLister,
    MenuPaths,
    Placement,
    gnome_commands,
    menu_steps,
    place_installed_entries,
    render_menu,
)

CATS = [
    Category(name="packet", summary="AX.25, Winlink and friends"),
    Category(name="sdr", summary="Software-defined receivers", title="SDR"),
]


def _manifest(name: str, categories: list[str], **extra: object) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": f"Fixture {name}",
            "categories": categories,
            "install": [{"install": {"method": "apt", "packages": [name]}}],
            "update": {"probe": {"method": "none"}, "strategy": "manual"},
            "documentation": {
                "what_it_does": "Exists so the placement is asserted.",
                "why_you_want_it": "You do not; the suite does.",
                "upstream_url": "https://example.invalid/",
            },
            **extra,
        }
    )


def _lister(shipped: dict[str, list[str]]) -> DesktopIdLister:
    return lambda package: shipped.get(package, [])


def test_the_menu_tree_includes_by_the_catalog_marker() -> None:
    xml = render_menu(CATS)
    assert "<Category>X-Hammunition-packet</Category>" in xml
    assert "<Category>X-Hammunition-sdr</Category>" in xml
    assert "hammunition-packet.directory" in xml
    assert xml.count("<Menu>") == 1 + 1 + len(CATS)  # root, Ham Radio, one per category


def test_steps_write_menu_and_every_directory_entry(tmp_path: Path) -> None:
    paths = MenuPaths(menus_dir=tmp_path / "menus", directories_dir=tmp_path / "dirs")
    steps = menu_steps(CATS, paths, menu_prefix="xfce-")
    for step in steps:
        step.perform()
    menu = tmp_path / "menus" / "xfce-applications-merged" / "hammunition.menu"
    assert "X-Hammunition-packet" in menu.read_text()
    top = (tmp_path / "dirs" / "hammunition-hamradio.directory").read_text()
    assert "Name=Ham Radio" in top
    sub = (tmp_path / "dirs" / "hammunition-packet.directory").read_text()
    assert "Name=Packet" in sub and "AX.25" in sub


def test_a_submenu_reads_by_its_vocabulary_title_not_a_title_cased_tag(
    tmp_path: Path,
) -> None:
    """Measured on the Kali VM's Xfce tree: `sdr` rendered "Sdr" and
    `hf-propagation` "Hf Propagation". The vocabulary carries the real one."""
    paths = MenuPaths(menus_dir=tmp_path / "menus", directories_dir=tmp_path / "dirs")
    for step in menu_steps(CATS, paths, menu_prefix=""):
        step.perform()
    assert "Name=SDR\n" in (tmp_path / "dirs" / "hammunition-sdr.directory").read_text()
    assert Category(name="hf-propagation", summary="x").label == "Hf Propagation"
    assert Category(name="hf-propagation", summary="x", title="HF Propagation").label == (
        "HF Propagation"
    )


def test_installed_package_entries_are_placed_under_every_category_of_their_manifest() -> None:
    """The Kali measurement: 43 distribution HamRadio entries scattered under
    Internet/Multimedia/Education/Other, 42 mapping back to a manifest by
    the package that shipped them."""
    manifests = [
        _manifest("fldigi", ["digital-modes", "nbems"]),
        _manifest("gqrx-sdr", ["sdr"]),
        _manifest("not-installed", ["sdr"]),
        _manifest("cli-only", ["packet"]),
    ]
    placement = place_installed_entries(
        manifests,
        _lister(
            {
                "fldigi": ["fldigi.desktop", "flarq.desktop"],
                "gqrx-sdr": ["dk.gqrx.gqrx.desktop"],
                "cli-only": [],
            }
        ),
    )
    assert placement.by_category == {
        "digital-modes": ("flarq.desktop", "fldigi.desktop"),
        "nbems": ("flarq.desktop", "fldigi.desktop"),
        "sdr": ("dk.gqrx.gqrx.desktop",),
    }
    assert placement.claimed == ("dk.gqrx.gqrx.desktop", "flarq.desktop", "fldigi.desktop")


def test_a_deb_unit_is_placed_by_its_deb_package_name() -> None:
    """gridtracker2 on Kali: the one of 43 that did not map through an apt
    block, because it is a binary .deb unit."""
    m = PackageManifest.model_validate(
        {
            "name": "gridtracker2",
            "version": "2.0",
            "summary": "Fixture",
            "categories": ["digital-modes"],
            "install": [
                {
                    "install": {
                        "method": "binary",
                        "artifact": {"url": "https://example.invalid/g.deb", "sha256": "0" * 64},
                        "format": "deb",
                        "deb_package": "gridtracker2",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}, "strategy": "manual"},
            "documentation": {
                "what_it_does": "Exists so the deb path is asserted.",
                "why_you_want_it": "You do not; the suite does.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    placement = place_installed_entries([m], _lister({"gridtracker2": ["gridtracker2.desktop"]}))
    assert placement.by_category == {"digital-modes": ("gridtracker2.desktop",)}


def test_the_tree_includes_placed_entries_by_filename_and_gathers_the_rest_at_the_top() -> None:
    placement = Placement(
        by_category={"sdr": ("dk.gqrx.gqrx.desktop",)},
        claimed=("dk.gqrx.gqrx.desktop", "hammunition-mshv.desktop"),
    )
    xml = render_menu(CATS, placement)
    sdr = xml[
        xml.index("<Name>hammunition-sdr</Name>") : xml.index(
            "</Menu>", xml.index("<Name>hammunition-sdr</Name>")
        )
    ]
    assert "<Filename>dk.gqrx.gqrx.desktop</Filename>" in sdr
    assert "<Category>X-Hammunition-sdr</Category>" in sdr
    top = xml[: xml.index("<Name>hammunition-packet</Name>")]
    assert "<Include><Category>HamRadio</Category></Include>" in top
    assert "<Exclude>" in top and "</Exclude>" in top
    assert xml.count("<Menu>") == 1 + 1 + len(CATS)


@pytest.mark.parametrize("claimed", [(), ("a.desktop",), ("a.desktop", "hammunition-b.desktop")])
def test_every_claimed_id_is_excluded_from_the_top_level_or_it_shows_twice(
    claimed: tuple[str, ...],
) -> None:
    """The spec shows an entry in every menu that includes it. A placed entry
    also carries HamRadio in the common case, so the top-level catch-all must
    exclude exactly the claimed set — a generated launcher included."""
    xml = render_menu(CATS, Placement(by_category={"sdr": claimed}, claimed=claimed))
    top = xml[: xml.index("<Name>hammunition-packet</Name>")]
    excluded = re.findall(r"<Filename>([^<]+)</Filename>", top)
    assert sorted(excluded) == sorted(claimed)
    if not claimed:
        assert "<Exclude>" not in xml


def test_the_placed_ids_are_unioned_into_the_gnome_folder_apps() -> None:
    placement = Placement(
        by_category={"sdr": ("dk.gqrx.gqrx.desktop",)}, claimed=("dk.gqrx.gqrx.desktop",)
    )
    commands = gnome_commands(placement)
    assert len(commands) == 4
    body = commands[-1].argv[2]
    assert "['dk.gqrx.gqrx.desktop']" in body and "if a not in value" in body
    assert len(gnome_commands(Placement.empty())) == 3
    assert len(gnome_commands()) == 3


def test_the_menu_prefix_is_honoured_because_a_wrong_one_merges_nothing(
    tmp_path: Path,
) -> None:
    paths = MenuPaths(menus_dir=tmp_path / "menus", directories_dir=tmp_path / "dirs")
    for step in menu_steps(CATS, paths, menu_prefix=""):
        step.perform()
    assert (tmp_path / "menus" / "applications-merged" / "hammunition.menu").exists()


def test_gnome_commands_append_and_never_replace_the_folder_list() -> None:
    register, name, categories = gnome_commands()
    assert register.argv[0] == "python3"
    body = register.argv[2]
    assert "if name not in value" in body and "value.append" in body
    assert name.argv[-1] == "Ham Radio"
    assert categories.argv[-1] == "['HamRadio']"
    assert all(not c.requires_root for c in gnome_commands())


def test_desktop_entries_carry_the_catalog_marker_categories(tmp_path: Path) -> None:
    """The join point: entries written by the launcher generator must carry
    the X- markers the menu tree includes by, or the tree is empty."""
    from hammunition.launchers import desktop_entry
    from hammunition.manifest.schema import PackageManifest

    m = PackageManifest.model_validate(
        {
            "name": "markable",
            "version": "1.0",
            "summary": "Fixture proving the marker join",
            "categories": ["packet", "sdr"],
            "install": [{"install": {"method": "apt", "packages": ["markable"]}}],
            "launchers": [{"name": "markable", "exec": "markable"}],
            "update": {"probe": {"method": "none"}, "strategy": "manual"},
            "documentation": {
                "what_it_does": "Exists so the marker join is asserted.",
                "why_you_want_it": "You do not; the suite does.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    entry = desktop_entry(m, m.launchers[0], tmp_path / "bin" / "markable")
    assert "X-Hammunition-packet" in entry
    assert "X-Hammunition-sdr" in entry
