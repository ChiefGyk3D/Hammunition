# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A menu a newcomer can navigate (D-054).

Field laptop, 2026-09-13, the maintainer's own read of the D-050 tree: it is
a great start and it is still hard to locate things. Measured: GNU Radio's
21 entries sat inline in both SDR and Digital Modes; 47 generated entries
were named after their units (`tlf`, `wwl`, `atlc`); the groups read as
catalog jargon. Three levers, each tested here: a unit may gather its
entries into its own submenu, a generated entry may carry a title, and the
vocabulary's groups say in plain words what is inside.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402
from hammunition.menus import (  # noqa: E402
    Category,
    CliEntry,
    Group,
    MenuPaths,
    cli_entries,
    gnome_commands,
    load_vocabulary,
    menu_steps,
    place_installed_entries,
    placement_summary,
    render_cli_entry,
    render_menu,
)

DOCS = {
    "what_it_does": "Stands in for a unit under the menu tests.",
    "why_you_want_it": "To measure where its entries land.",
    "upstream_url": "https://example.invalid/",
}


def _manifest(name: str, categories: list[str], **extra: Any) -> PackageManifest:
    body: dict[str, Any] = {
        "name": name,
        "version": "1",
        "summary": f"The {name} toolkit",
        "categories": categories,
        "install": [{"install": {"method": "apt", "packages": [name]}}],
        "update": {"probe": {"method": "apt_policy"}},
        "documentation": DOCS,
    }
    body.update(extra)
    return PackageManifest.model_validate(body)


TOOLKIT = [f"gr_tool{i}.desktop" for i in range(21)]


def _lister(package: str) -> list[str]:
    return {"gnuradio": TOOLKIT, "gqrx": ["gqrx.desktop"]}.get(package, [])


# --- a unit's own submenu ------------------------------------------------------


def test_a_submenu_unit_is_placed_once_under_its_first_category_and_never_inline() -> None:
    gr = _manifest("gnuradio", ["sdr", "digital-modes"], menu_submenu="GNU Radio")
    gqrx = _manifest("gqrx", ["sdr"])
    placement = place_installed_entries([gr, gqrx], _lister)
    assert placement.by_category == {"sdr": ("gqrx.desktop",)}
    (sub,) = placement.submenus
    assert (sub.unit, sub.title, sub.category) == ("gnuradio", "GNU Radio", "sdr")
    assert sub.ids == tuple(sorted(TOOLKIT))
    assert set(TOOLKIT) <= set(placement.claimed), "the catch-all must still exclude them"
    assert "gnuradio" in placement.units, "no generated entry is added on top"
    assert any(
        "21 entries gathered into the 'GNU Radio' submenu" in line
        for line in placement_summary(placement)
    )


def test_the_tree_nests_the_submenu_inside_the_category_with_its_own_directory(
    tmp_path: Path,
) -> None:
    gr = _manifest("gnuradio", ["sdr", "digital-modes"], menu_submenu="GNU Radio")
    placement = place_installed_entries([gr], _lister)
    cats = [Category("sdr", "r", "SDR", "radio"), Category("digital-modes", "d", "Digital Modes")]
    body = render_menu(cats, placement)
    sdr = body.index("<Name>hammunition-sdr</Name>")
    nested = body.index("<Name>hammunition-unit-gnuradio</Name>")
    digital = body.index("<Name>hammunition-digital-modes</Name>")
    assert sdr < nested < digital, "nested inside SDR, and Digital Modes gets nothing"
    assert body.count("gr_tool0.desktop") == 2, "once in the submenu, once in the catch-all Exclude"
    assert "<Directory>hammunition-unit-gnuradio.directory</Directory>" in body
    paths = MenuPaths(menus_dir=tmp_path / "menus", directories_dir=tmp_path / "dirs")
    steps = menu_steps(cats, paths, menu_prefix="", placement=placement)
    for step in steps:
        step.perform()
    directory = (tmp_path / "dirs" / "hammunition-unit-gnuradio.directory").read_text()
    assert "Name=GNU Radio\n" in directory
    assert "Comment=The gnuradio toolkit" in directory
    assert "Icon=radio" in directory, "the category's icon, so the submenu matches its parent"


def test_gnome_flattens_the_submenu_into_the_group_folder_because_it_cannot_nest() -> None:
    gr = _manifest("gnuradio", ["sdr"], menu_submenu="GNU Radio")
    placement = place_installed_entries([gr], _lister)
    group = Group(order=1, name="sdr", title="SDR", summary="s", categories=("sdr",))
    script = " ".join(str(a) for cmd in gnome_commands(placement, [group]) for a in cmd.argv)
    assert "gr_tool0.desktop" in script


# --- a generated entry with a readable name -------------------------------------


def test_a_generated_entry_shows_the_menu_title_and_keeps_the_unit_for_search() -> None:
    tlf = _manifest("tlf", ["contest"], menu_title="Contest logger (tlf)")
    placement = place_installed_entries([tlf], lambda _p: [])
    generated = cli_entries([tlf], placement, executables=lambda _p: ["/usr/bin/tlf"])
    (entry,) = generated.entries
    body = render_cli_entry(entry)
    assert "Name=Contest logger (tlf)\n" in body
    assert "Keywords=contest;tlf;" in body
    assert entry.desktop_id == "hammunition-cli-tlf.desktop"


def test_without_a_title_the_unit_name_still_stands() -> None:
    entry = CliEntry(unit="gqrx", exec="/usr/bin/gqrx", comment="c", categories=("sdr",))
    assert "Name=gqrx\n" in render_cli_entry(entry)


# --- the shipped vocabulary --------------------------------------------------------


def test_the_shipped_groups_read_in_plain_words_and_cover_every_category() -> None:
    vocabulary = load_vocabulary(REPO_ROOT / "catalog" / "categories.yaml")
    titles = [g.title for g in vocabulary.groups if g.menu]
    assert titles == [
        "Operate the Station",
        "Digital Modes & Morse",
        "Packet, Mesh & Emergency Comms",
        "SDR & Listening",
        "Satellites & Propagation",
        "Antennas, Bench & Programming",
        "RF Security & Research",
        "Learn & Practise",
    ]
    grouped = [c for g in vocabulary.groups for c in g.categories]
    assert sorted(grouped) == sorted(c.name for c in vocabulary.categories)
    assert len(grouped) == len(set(grouped)), "a category sits in exactly one group"
    by_name = {c.name: c for c in vocabulary.categories}
    # the jargon tags carry a gloss a newcomer can read
    assert by_name["cw"].title == "CW (Morse)"
    assert by_name["aircraft"].title == "Aircraft (ADS-B, ACARS, Airband)"
    assert by_name["sstv-atv"].title == "SSTV, Fax & Amateur TV"
    assert by_name["nbems"].title == "NBEMS Messaging"


def test_gnuradio_is_the_one_measured_toolkit_and_declares_its_submenu() -> None:
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    assert catalog["gnuradio"].menu_submenu == "GNU Radio"
