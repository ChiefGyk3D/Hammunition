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


# --- a source build's own entry lives in the local prefix -------------------------


def test_a_built_units_entry_in_the_local_prefix_is_placed_by_its_declared_names(
    tmp_path: Path,
) -> None:
    local = tmp_path / "local"
    local.mkdir()
    for name in ("fldigi", "flarq", "wsjtx", "message_aggregator"):
        (local / f"{name}.desktop").write_text("[Desktop Entry]\nType=Application\n")
    fldigi = _manifest(
        "fldigi",
        ["keyboard-modes"],
        binaries=[{"produced": "fldigi", "install_as": "fldigi"}],
        provides=["flarq"],
    )
    wsjtx = _manifest("wsjtx", ["weak-signal"])
    placement = place_installed_entries(
        [fldigi, wsjtx], lambda _p: [], built_applications_dir=local
    )
    assert placement.by_category == {
        "keyboard-modes": ("flarq.desktop", "fldigi.desktop"),
        "weak-signal": ("wsjtx.desktop",),
    }
    assert placement.built == (
        ("fldigi", "flarq.desktop"),
        ("fldigi", "fldigi.desktop"),
        ("wsjtx", "wsjtx.desktop"),
    )
    assert "wsjtx" in placement.units, "no generated entry on top of the real one"
    assert not any("message_aggregator" in i for i in placement.claimed), "nothing names it"
    assert any(
        "wsjtx.desktop placed from the local prefix" in line
        for line in placement_summary(placement)
    )


def test_without_a_local_prefix_nothing_changes(tmp_path: Path) -> None:
    wsjtx = _manifest("wsjtx", ["weak-signal"])
    placement = place_installed_entries([wsjtx], lambda _p: [])
    assert placement.by_category == {} and placement.built == ()


# --- a launcher entry follows its manifest, not the day it was installed ----------


def test_a_launcher_entry_with_stale_markers_is_re_rendered_from_the_manifest(
    tmp_path: Path,
) -> None:
    from hammunition.menus import refresh_launcher_entries

    apps = tmp_path / "apps"
    apps.mkdir()
    hill = _manifest(
        "hammunition-hill",
        ["dashboards"],
        launchers=[
            {
                "name": "hammunition-hill",
                "exec": "x-www-browser http://127.0.0.1:8073",
                "title": "Hammunition Hill dashboard",
            }
        ],
    )
    entry = apps / "hammunition-hammunition-hill.desktop"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nIcon=map-globe\nName=hammunition-hill\n"
        "Comment=old\nExec=/home/op/.local/bin/hammunition-hill\nTerminal=false\n"
        "Categories=HamRadio;Science;X-Hammunition-station;\nX-Hammunition-Package=hammunition-hill\n"
    )
    steps = refresh_launcher_entries([hill], apps)
    assert [s.detail for s in steps] == [str(entry)]
    for s in steps:
        s.perform()
    text = entry.read_text()
    assert "X-Hammunition-dashboards;" in text and "X-Hammunition-station" not in text
    assert "Name=Hammunition Hill dashboard\n" in text
    assert "Exec=/home/op/.local/bin/hammunition-hill\n" in text, "the wrapper path is kept"
    # a second pass finds nothing to do, and a manifest with no entry on disk is skipped
    assert refresh_launcher_entries([hill], apps) == []
    assert (
        refresh_launcher_entries(
            [_manifest("ghost", ["aprs"], launchers=[{"name": "ghost", "exec": "ghost"}])], apps
        )
        == []
    )


# --- every installed unit, built ones included ----------------------------------


def test_a_built_unit_gets_a_generated_entry_from_its_declared_binary(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "linbpq").write_text("#!/bin/sh\n")
    (prefix / "bin" / "acarsdec").write_text("#!/bin/sh\n")
    (prefix / "bin" / "acars-extra").write_text("#!/bin/sh\n")
    linbpq = _manifest(
        "linbpq", ["packet-nodes"], binaries=[{"produced": "linbpq", "install_as": "linbpq"}]
    )
    acars = _manifest(
        "acarsdec",
        ["aircraft"],
        binaries=[
            {"produced": "acarsdec", "install_as": "acarsdec"},
            {"produced": "extra", "install_as": "acars-extra"},
        ],
    )
    ghost = _manifest("ghost", ["aprs"], binaries=[{"produced": "ghost", "install_as": "ghost"}])
    placement = place_installed_entries([linbpq, acars, ghost], lambda _p: [])
    generated = cli_entries(
        [linbpq, acars, ghost], placement, executables=lambda _p: [], prefix=prefix
    )
    by_unit = {e.unit: e for e in generated.entries}
    assert by_unit["linbpq"].exec == str(prefix / "bin" / "linbpq")
    assert by_unit["acarsdec"].exec == str(prefix / "bin" / "acarsdec"), "named like the unit wins"
    assert "ghost" not in by_unit, "declared but not on disk is not installed"


def test_a_launcher_declared_after_install_is_written_at_apply_time(tmp_path: Path) -> None:
    from hammunition.menus import missing_launcher_steps

    bins, apps, prefix = tmp_path / "bin", tmp_path / "apps", tmp_path / "prefix"
    rtl = _manifest(
        "rtl-sdr",
        ["sdr-hardware"],
        launchers=[{"name": "rtl_test", "exec": "rtl_test -t", "terminal": True}],
    )
    absent = _manifest(
        "absent", ["sdr-hardware"], launchers=[{"name": "absent_tool", "exec": "absent_tool"}]
    )
    steps = missing_launcher_steps(
        [rtl, absent],
        bin_dir=bins,
        applications_dir=apps,
        prefix=prefix,
        installed=lambda p: p == "rtl-sdr",
    )
    assert [s.kind for s in steps] == ["wrapper", "desktop-entry"], "only the installed unit"
    for s in steps:
        s.perform()
    assert (bins / "rtl_test").is_file() and (apps / "hammunition-rtl_test.desktop").is_file()
    assert (
        missing_launcher_steps(
            [rtl], bin_dir=bins, applications_dir=apps, prefix=prefix, installed=lambda p: True
        )
        == []
    )


def test_a_venv_units_launcher_is_left_to_install(tmp_path: Path) -> None:
    from hammunition.menus import missing_launcher_steps

    venv_unit = _manifest(
        "pyt",
        ["sdr-receivers"],
        install=[
            {
                "install": {
                    "method": "venv",
                    "python": ">=3.12",
                    "requirements": ["pyt==1.0 --hash=sha256:" + "0" * 64],
                }
            }
        ],
        launchers=[{"name": "pyt", "exec": "exec {venv}/bin/python -m pyt"}],
    )
    assert (
        missing_launcher_steps(
            [venv_unit],
            bin_dir=tmp_path,
            applications_dir=tmp_path,
            prefix=tmp_path,
            installed=lambda p: True,
        )
        == []
    )
