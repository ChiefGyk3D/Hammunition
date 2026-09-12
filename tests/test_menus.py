# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The D-036 menu layer: one taxonomy, per-user, both measured mechanisms."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from hammunition.manifest.schema import PackageManifest
from hammunition.menus import (
    Category,
    DesktopIdLister,
    MenuPaths,
    MenuPrefixError,
    Placement,
    gnome_commands,
    menu_steps,
    place_installed_entries,
    render_menu,
    resolve_menu_prefix,
    root_menu_prefixes,
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


# ---------------------------------------------------------------------------
# Which root menu the merged file is for
# ---------------------------------------------------------------------------


def _roots(tmp_path: Path, *names: str) -> Path:
    menus = tmp_path / "xdg" / "menus"
    menus.mkdir(parents=True)
    for name in names:
        (menus / f"{name}applications.menu").write_text("<Menu/>\n")
    return tmp_path / "xdg"


def test_the_installed_root_menus_are_the_prefixes(tmp_path: Path) -> None:
    """Parrot carries four; the maintainer's laptop and Debian one; a server none."""
    xdg = _roots(tmp_path, "kf5-", "mate-", "plasma-", "xfce-")
    assert root_menu_prefixes([xdg]) == ["kf5-", "mate-", "plasma-", "xfce-"]
    assert root_menu_prefixes([_roots(tmp_path / "srv")]) == []


def test_an_explicit_prefix_wins_then_the_session_then_the_one_root(tmp_path: Path) -> None:
    xdg = _roots(tmp_path, "gnome-")
    assert resolve_menu_prefix("plasma-", "xfce-", [xdg]) == "plasma-"
    assert resolve_menu_prefix(None, "xfce-", [xdg]) == "xfce-"
    assert resolve_menu_prefix(None, None, [xdg]) == "gnome-"
    assert resolve_menu_prefix(None, "", [xdg]) == "gnome-", "an empty variable is unset"
    assert resolve_menu_prefix("", None, [xdg]) == "", "an explicit empty prefix is a choice"


def test_several_root_menus_and_no_session_variable_is_a_refusal_that_names_them(
    tmp_path: Path,
) -> None:
    """The empty prefix used to be written here and merged into nothing on
    every measured machine. Guessing which of Parrot's four desktops the
    operator logs into writes the menu for the ones they do not."""
    xdg = _roots(tmp_path, "plasma-", "xfce-")
    with pytest.raises(MenuPrefixError, match=r"--menu-prefix 'plasma-'.*--menu-prefix 'xfce-'"):
        resolve_menu_prefix(None, None, [xdg])


def test_no_root_menu_at_all_is_a_refusal(tmp_path: Path) -> None:
    with pytest.raises(MenuPrefixError, match="no root menu"):
        resolve_menu_prefix(None, None, [_roots(tmp_path)])


def test_a_bare_root_menu_means_the_empty_prefix(tmp_path: Path) -> None:
    assert resolve_menu_prefix(None, None, [_roots(tmp_path, "")]) == ""


# ---------------------------------------------------------------------------
# Issue #64: Parrot's `parrot-menu` rewrites the launcher set from an apt
# DPkg::Post-Invoke hook after every apt run, removing the packaged entry and
# writing `parrot-<package>.desktop` in its place. `dpkg -L` still lists the
# shipped file, so placing by that list put two filenames in the Plasma tree
# that did not exist on the field laptop (chirp, wireshark; 2026-09-12).
# ---------------------------------------------------------------------------


def _entry(directory: Path, name: str) -> None:
    (directory / name).write_text("[Desktop Entry]\nType=Application\n")


def test_a_shipped_entry_absent_on_disk_is_placed_by_the_distribution_replacement(
    tmp_path: Path,
) -> None:
    from hammunition.menus import on_disk

    _entry(tmp_path, "parrot-chirp.desktop")
    found = on_disk("chirp", ["chirp.desktop"], tmp_path)
    assert found.ids == ("parrot-chirp.desktop",)
    assert found.replaced == (("chirp.desktop", "parrot-chirp.desktop"),)
    assert found.missing == ()


def test_a_shipped_entry_absent_with_no_replacement_is_reported_not_placed(
    tmp_path: Path,
) -> None:
    from hammunition.menus import on_disk

    found = on_disk("chirp", ["chirp.desktop"], tmp_path)
    assert found.ids == ()
    assert found.replaced == ()
    assert found.missing == ("chirp.desktop",)


def test_entries_present_on_disk_pass_through_unchanged(tmp_path: Path) -> None:
    from hammunition.menus import on_disk

    _entry(tmp_path, "flrig.desktop")
    _entry(tmp_path, "parrot-flrig.desktop")  # a replacement is irrelevant when the original exists
    found = on_disk("flrig", ["flrig.desktop"], tmp_path)
    assert found.ids == ("flrig.desktop",)
    assert found.replaced == ()
    assert found.missing == ()


def test_placement_places_the_replacement_and_carries_what_happened(tmp_path: Path) -> None:
    _entry(tmp_path, "parrot-chirp.desktop")
    _entry(tmp_path, "flrig.desktop")
    manifests = [
        _manifest("chirp", ["rig-control"]),
        _manifest("flrig", ["rig-control"]),
        _manifest("gone", ["sdr"]),
    ]
    placement = place_installed_entries(
        manifests,
        _lister(
            {
                "chirp": ["chirp.desktop"],
                "flrig": ["flrig.desktop"],
                "gone": ["gone.desktop"],
            }
        ),
        applications_dir=tmp_path,
    )
    assert placement.by_category == {"rig-control": ("flrig.desktop", "parrot-chirp.desktop")}
    assert placement.claimed == ("flrig.desktop", "parrot-chirp.desktop")
    assert placement.replaced == (("chirp", "chirp.desktop", "parrot-chirp.desktop"),)
    assert placement.missing == (("gone", "gone.desktop"),)


def test_the_summary_names_replacements_and_missing_entries_so_a_count_cannot_lie() -> None:
    from hammunition.menus import placement_summary

    placement = Placement(
        by_category={"rig-control": ("flrig.desktop", "parrot-chirp.desktop")},
        claimed=("flrig.desktop", "parrot-chirp.desktop"),
        replaced=(("chirp", "chirp.desktop", "parrot-chirp.desktop"),),
        missing=(("gone", "gone.desktop"),),
    )
    lines = placement_summary(placement)
    assert any("chirp.desktop" in line and "parrot-chirp.desktop" in line for line in lines)
    assert any("gone.desktop" in line and "not placed" in line for line in lines)


def test_a_placement_without_a_disk_check_reports_nothing_replaced_or_missing() -> None:
    placement = place_installed_entries(
        [_manifest("flrig", ["rig-control"])], _lister({"flrig": ["flrig.desktop"]})
    )
    assert placement.replaced == ()
    assert placement.missing == ()


# ---------------------------------------------------------------------------
# D-050: a two-level tree in a declared order (Parrot's shape), and an entry
# for every installed unit so the launcher's search finds all of it.
# ---------------------------------------------------------------------------


def _groups() -> list[Any]:
    from hammunition.menus import Group

    return [
        Group(order=1, name="station", title="Station", summary="The desk", categories=("sdr",)),
        Group(
            order=2, name="packet", title="Packet & EMCOMM", summary="Air", categories=("packet",)
        ),
    ]


def test_the_vocabulary_loads_groups_in_declared_order_with_their_categories(
    tmp_path: Path,
) -> None:
    from hammunition.menus import load_vocabulary

    (tmp_path / "categories.yaml").write_text(
        "categories:\n"
        "  - name: sdr\n    title: SDR\n    summary: Receivers\n"
        "  - name: packet\n    summary: AX.25\n"
        "groups:\n"
        "  - order: 2\n    name: packet\n    title: Packet\n    summary: Air\n"
        "    categories: [packet]\n"
        "  - order: 1\n    name: station\n    title: Station\n    summary: Desk\n"
        "    categories: [sdr]\n"
    )
    vocabulary = load_vocabulary(tmp_path / "categories.yaml")
    assert [g.name for g in vocabulary.groups] == ["station", "packet"]
    assert vocabulary.groups[0].categories == ("sdr",)
    assert [c.name for c in vocabulary.categories] == ["sdr", "packet"]
    assert vocabulary.categories[0].title == "SDR"


def test_the_tree_nests_each_category_under_its_group_in_the_declared_order() -> None:
    xml = render_menu(CATS, groups=_groups())
    # root, Ham Radio, one per group, one per category
    assert xml.count("<Menu>") == 1 + 1 + 2 + len(CATS)
    station = xml.index("<Name>hammunition-group-station</Name>")
    packet_group = xml.index("<Name>hammunition-group-packet</Name>")
    assert station < packet_group, "groups appear in declared order"
    sdr = xml.index("<Name>hammunition-sdr</Name>")
    assert station < sdr < packet_group, "sdr is nested inside the station group"
    assert "hammunition-group-station.directory" in xml
    layout = xml[xml.index("<Layout>") : xml.index("</Layout>")]
    assert layout.index("hammunition-group-station") < layout.index("hammunition-group-packet")


def test_a_category_in_no_group_renders_at_the_top_level_beside_the_groups() -> None:
    """The vocabulary test forbids it in the shipped file; the renderer must
    still put the entry somewhere visible rather than drop it."""
    only_station = [_groups()[0]]
    xml = render_menu(CATS, groups=only_station)
    assert xml.count("<Menu>") == 1 + 1 + 1 + len(CATS)
    assert "<Name>hammunition-packet</Name>" in xml


def test_steps_write_a_directory_entry_per_group(tmp_path: Path) -> None:
    paths = MenuPaths(menus_dir=tmp_path / "menus", directories_dir=tmp_path / "dirs")
    for step in menu_steps(CATS, paths, menu_prefix="plasma-", groups=_groups()):
        step.perform()
    body = (tmp_path / "dirs" / "hammunition-group-packet.directory").read_text()
    assert "Name=Packet & EMCOMM" in body and "Comment=Air" in body


def _exes(table: dict[str, list[str]]) -> Callable[[str], list[str]]:
    return lambda package: table.get(package, [])


def test_an_installed_unit_with_no_entry_gets_one_from_its_sole_executable() -> None:
    from hammunition.menus import cli_entries

    result = cli_entries(
        [_manifest("tcpdump", ["rf-security"])],
        Placement.empty(),
        _exes({"tcpdump": ["/usr/bin/tcpdump"]}),
    )
    [entry] = result.entries
    assert entry.unit == "tcpdump"
    assert entry.exec == "/usr/bin/tcpdump"
    assert entry.desktop_id == "hammunition-cli-tcpdump.desktop"
    assert result.skipped == ()


def test_the_executable_named_like_the_unit_wins_over_its_siblings() -> None:
    from hammunition.menus import cli_entries

    result = cli_entries(
        [_manifest("aircrack-ng", ["rf-security"])],
        Placement.empty(),
        _exes(
            {
                "aircrack-ng": [
                    "/usr/bin/airodump-ng",
                    "/usr/bin/aircrack-ng",
                    "/usr/bin/aireplay-ng",
                ]
            }
        ),
    )
    assert [e.exec for e in result.entries] == ["/usr/bin/aircrack-ng"]


def test_several_executables_and_none_named_like_the_unit_is_skipped_and_said() -> None:
    """rtl-sdr on the field laptop: six tools, none called rtl-sdr. Guessing
    rtl_sdr over rtl_fm is a coin toss; a `launchers` block in the manifest
    is the fix, and the summary names the unit so someone writes one."""
    from hammunition.menus import cli_entries

    result = cli_entries(
        [_manifest("rtl-sdr", ["sdr"])],
        Placement.empty(),
        _exes({"rtl-sdr": ["/usr/bin/rtl_fm", "/usr/bin/rtl_sdr", "/usr/bin/rtl_power"]}),
    )
    assert result.entries == ()
    [(unit, why)] = result.skipped
    assert unit == "rtl-sdr" and "3 executables" in why


def test_units_that_already_have_an_entry_or_a_launcher_get_no_cli_entry() -> None:
    from hammunition.menus import cli_entries

    placed = Placement(by_category={"sdr": ("x.desktop",)}, claimed=("x.desktop",), units=("gqrx",))
    with_launcher = _manifest(
        "hamclock", ["station"], launchers=[{"name": "hamclock", "exec": "hamclock"}]
    )
    result = cli_entries(
        [_manifest("gqrx", ["sdr"]), with_launcher],
        placed,
        _exes({"gqrx": ["/usr/bin/gqrx"], "hamclock": ["/usr/bin/hamclock"]}),
    )
    assert result.entries == () and result.skipped == ()


def test_a_unit_that_is_not_installed_is_neither_an_entry_nor_a_skip() -> None:
    from hammunition.menus import cli_entries

    result = cli_entries([_manifest("absent", ["sdr"])], Placement.empty(), _exes({}))
    assert result.entries == () and result.skipped == ()


def test_the_generated_entry_is_searchable_and_carries_the_catalog_markers() -> None:
    from hammunition.menus import cli_entries, render_cli_entry

    [entry] = cli_entries(
        [_manifest("tcpdump", ["rf-security", "workstation"])],
        Placement.empty(),
        _exes({"tcpdump": ["/usr/bin/tcpdump"]}),
    ).entries
    body = render_cli_entry(entry)
    assert "Name=tcpdump\n" in body
    assert "Comment=Fixture tcpdump\n" in body
    assert "Exec=/usr/bin/tcpdump\n" in body
    assert "Terminal=true\n" in body
    assert "X-Hammunition-rf-security" in body and "X-Hammunition-workstation" in body
    assert "Keywords=" in body and "rf-security" in body.split("Keywords=")[1]
    assert "X-Hammunition-Package=tcpdump\n" in body


def test_cli_entry_steps_write_the_new_and_prune_the_stale(tmp_path: Path) -> None:
    from hammunition.menus import cli_entries, cli_entry_steps

    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "hammunition-cli-gone.desktop").write_text(
        "[Desktop Entry]\n"
    )  # from a unit since removed
    (apps / "hammunition-mshv.desktop").write_text(
        "[Desktop Entry]\n"
    )  # a launcher: not ours to prune
    result = cli_entries(
        [_manifest("tcpdump", ["rf-security"])],
        Placement.empty(),
        _exes({"tcpdump": ["/usr/bin/tcpdump"]}),
    )
    for step in cli_entry_steps(result, apps):
        step.perform()
    assert (apps / "hammunition-cli-tcpdump.desktop").exists()
    assert not (apps / "hammunition-cli-gone.desktop").exists()
    assert (apps / "hammunition-mshv.desktop").exists()


def test_placement_records_which_units_received_an_entry() -> None:
    placement = place_installed_entries(
        [_manifest("flrig", ["rig-control"]), _manifest("cli-only", ["packet"])],
        _lister({"flrig": ["flrig.desktop"], "cli-only": []}),
    )
    assert placement.units == ("flrig",)


def test_plasma_gets_its_cache_rebuilt_and_other_desktops_get_the_hint() -> None:
    from hammunition.menus import refresh_command

    found = {"kbuildsycoca6": "/usr/bin/kbuildsycoca6"}
    command = refresh_command("plasma-", which=lambda n: found.get(n))
    assert command is not None and command.argv == ("/usr/bin/kbuildsycoca6",)
    assert not command.requires_root
    assert refresh_command("kf5-", which=lambda n: found.get(n)) is not None
    assert refresh_command("xfce-", which=lambda n: found.get(n)) is None
    assert refresh_command("plasma-", which=lambda n: None) is None


def test_a_unit_whose_only_executables_live_in_sbin_is_a_service_not_an_entry() -> None:
    """gpsd on the field laptop: the generated entry ran /usr/sbin/gpsd in a
    terminal, which is a daemon systemd already owns, not an application.
    sbin is for the system; a unit with nothing outside it gets no entry,
    and the summary says why rather than counting a launcher that would
    only ever fail."""
    from hammunition.menus import cli_entries

    result = cli_entries(
        [_manifest("gpsd", ["station"])],
        Placement.empty(),
        _exes({"gpsd": ["/usr/sbin/gpsd", "/usr/sbin/gpsdctl"]}),
    )
    assert result.entries == ()
    [(unit, why)] = result.skipped
    assert unit == "gpsd" and "sbin" in why and "service" in why


def test_an_sbin_sibling_does_not_stop_the_bin_executable_named_like_the_unit() -> None:
    from hammunition.menus import cli_entries

    result = cli_entries(
        [_manifest("hcxdumptool", ["rf-security"])],
        Placement.empty(),
        _exes({"hcxdumptool": ["/usr/sbin/hcxdumptool-helper", "/usr/bin/hcxdumptool"]}),
    )
    assert [e.exec for e in result.entries] == ["/usr/bin/hcxdumptool"]
