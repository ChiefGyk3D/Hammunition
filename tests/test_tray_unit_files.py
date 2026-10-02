# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tray units install the tray's helper, and write nothing of it as catalog data.

D-056 amended 2026-10-02. The helper lives in hammunition-tray; its 0.5.0
release published no .deb, so both tray units pin the tag's archive and the
engine installs the helper from it through a `devctl_helper` block (the wrapper
bakes in an interpreter and the polkit file may be a package's, so neither is
ever a catalog `config_files` entry: that absence is still held here).

What is checked, each of it falsifiable:

* the pin is the measured tag archive (digest, tag, one URL for both units);
* the helper's module list and every placed file are exactly what the pinned
  archive ships (skipped, naming the reason, when the archive is not cached);
* the manifests say why the helper is a block and not a file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.hardware.polkit import HELPER_PATH, POLICY_PATH
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import BinaryInstall, PackageManifest

CATALOG = Path(__file__).resolve().parent.parent / "catalog"
UNITS = ("hammunition-tray", "hammunition-tray-qt")
TAG_URL = "https://github.com/ChiefGyk3D/hammunition-tray/archive/refs/tags/v0.5.0.tar.gz"
TAG_SHA = "614148fb4241e88ca007885d01ef97d0752c8cd47b6e57337e2ee12ab3bfc438"


@pytest.fixture(scope="module")
def packages() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG / "packages")


def _install(packages: dict[str, PackageManifest], unit: str) -> BinaryInstall:
    block = packages[unit].install[0].install
    assert isinstance(block, BinaryInstall)
    return block


@pytest.mark.parametrize("unit", UNITS)
def test_no_tray_unit_writes_the_wrapper_or_the_polkit_action(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    written = {c.path for c in packages[unit].config_files}
    assert HELPER_PATH not in written and POLICY_PATH not in written, (
        f"{unit} writes the helper's wrapper or polkit action as a catalog file; they are "
        f"the engine's `devctl_helper` block (the wrapper bakes in an interpreter a catalog "
        f"file cannot name, and a file a package owns is never written over)"
    )


@pytest.mark.parametrize("unit", UNITS)
def test_both_units_pin_the_measured_tag_archive(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    install = _install(packages, unit)
    assert packages[unit].version == "0.5.0"
    assert install.format == "tarball"
    assert install.artifact.url == TAG_URL
    assert install.artifact.sha256 == TAG_SHA


@pytest.mark.parametrize("unit", UNITS)
def test_each_unit_installs_the_helper_and_names_the_contract_it_needs(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    helper = _install(packages, unit).devctl_helper
    assert helper is not None and helper.source == "devctl" and helper.min_contract == 1


def test_the_two_units_carry_the_same_helper_block(packages: dict[str, PackageManifest]) -> None:
    """One owns it at a time; a block that drifted would install a different
    helper depending on which unit ran first."""
    assert (
        _install(packages, "hammunition-tray").devctl_helper
        == _install(packages, "hammunition-tray-qt").devctl_helper
    )


@pytest.mark.parametrize("unit", UNITS)
def test_the_manifest_says_why_the_helper_is_a_block(unit: str) -> None:
    text = (CATALOG / "packages" / f"{unit}.yaml").read_text()
    assert "THE HELPER (D-056, amended 2026-10-02)" in text
    assert "It is NOT a catalog `config_files` entry" in text


@pytest.mark.parametrize("unit", UNITS)
def test_the_units_declare_what_the_deb_depended_on(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    """Installing from the archive has no apt to pull the Depends line in."""
    wanted = {
        "hammunition-tray": {
            "plasma-workspace",
            "qml6-module-org-kde-plasma-plasma5support",
            "qml6-module-org-kde-kirigami",
            "qml6-module-org-kde-notifications",
            "pkexec",
        },
        "hammunition-tray-qt": {"python3-pyqt6", "pkexec"},
    }[unit]
    assert set(packages[unit].depends) == wanted


def test_every_file_the_deb_would_have_shipped_is_placed(
    packages: dict[str, PackageManifest], pinned_tray: Path
) -> None:
    """The applet and the Qt tray's package are the archive's own files, all of
    them: a file upstream adds is not silently left out of the install."""
    applet = {p.source for p in _install(packages, "hammunition-tray").placements}
    shipped_applet = {
        str(p.relative_to(pinned_tray))
        for p in (pinned_tray / "plasmoid" / "package").rglob("*")
        if p.is_file()
    }
    assert shipped_applet <= applet, f"unplaced applet files: {sorted(shipped_applet - applet)}"

    qt = {p.source for p in _install(packages, "hammunition-tray-qt").placements}
    shipped_qt = {
        str(p.relative_to(pinned_tray)) for p in (pinned_tray / "qt").rglob("*") if p.is_file()
    }
    assert shipped_qt <= qt, f"unplaced Qt files: {sorted(shipped_qt - qt)}"


def test_every_placement_source_exists_in_the_archive(
    packages: dict[str, PackageManifest], pinned_tray: Path
) -> None:
    for unit in UNITS:
        for placement in _install(packages, unit).placements:
            assert (pinned_tray / placement.source).is_file(), f"{unit}: {placement.source}"


def test_the_qt_script_finds_its_package_where_the_placements_put_it(
    packages: dict[str, PackageManifest], pinned_tray: Path
) -> None:
    """The script puts one absolute directory on its import path; a placement
    elsewhere would install a tray that cannot import itself."""
    script = (pinned_tray / "qt" / "hammunition-tray-qt").read_text()
    assert 'sys.path.insert(0, "/usr/share/hammunition-tray-qt")' in script
    dests = {p.dest for p in _install(packages, "hammunition-tray-qt").placements}
    assert "/usr/share/hammunition-tray-qt/hammunition_tray_qt/tray.py" in dests
