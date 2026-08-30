# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The D-036 menu layer: one taxonomy, per-user, both measured mechanisms."""

from __future__ import annotations

from pathlib import Path

from hammunition.menus import Category, MenuPaths, gnome_commands, menu_steps, render_menu

CATS = [
    Category(name="packet", summary="AX.25, Winlink and friends"),
    Category(name="sdr", summary="Software-defined receivers"),
]


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
