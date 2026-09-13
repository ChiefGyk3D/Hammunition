# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""`installed_files`: declared effects of a build's own install rule.

libacars is a library: its cmake install rule leaves a `.so`, a symlink and
a pkg-config file under the prefix and no executable. With nothing to
declare in `binaries` the engine had no effect to check (D-031), could
never decide the build as already installed (D-051), and `update` called it
unknown. The field names what the install rule leaves; the engine checks
it, and never copies or removes it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends.apt import AptPackageState  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import build_effects_present, verify_effects  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import ManifestError, PackageManifest  # noqa: E402
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402
from hammunition.update import BEHIND_PIN, UNKNOWN, report  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")
DOCS = {
    "what_it_does": "Stands in for a library with no executable.",
    "why_you_want_it": "To prove a declared file is read back.",
    "upstream_url": "https://example.invalid/",
}


def _lib(**overrides: Any) -> PackageManifest:
    data: dict[str, Any] = {
        "name": "libthing",
        "version": "2.2.1",
        "summary": "A shared library",
        "categories": ["listening"],
        "install": [
            {
                "install": {
                    "method": "git",
                    "repo": "https://example.invalid/libthing",
                    "ref": "v2.2.1",
                    "build_system": "cmake",
                }
            }
        ],
        "installed_files": ["lib/libthing-2.so.2", "lib/pkgconfig/libthing-2.pc"],
        "update": {"probe": {"method": "none"}, "strategy": "rebuild"},
        "documentation": DOCS,
    }
    data.update(overrides)
    return PackageManifest.model_validate(data)


def _plan(manifest: PackageManifest) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )


# --- the schema refuses what cannot be an effect under the prefix -----------


@pytest.mark.parametrize("bad", ["/usr/local/lib/x.so", "lib/../etc/x", "bin/x", ""])
def test_a_path_that_is_not_a_relative_effect_under_the_prefix_is_refused(bad: str) -> None:
    with pytest.raises((ValidationError, ManifestError), match="installed_files"):
        _lib(installed_files=[bad])


def test_installed_files_on_a_unit_with_no_build_of_its_own_is_refused() -> None:
    with pytest.raises((ValidationError, ManifestError), match="installed_files"):
        _lib(install=[{"install": {"method": "apt", "packages": ["libthing2"]}}])


# --- the effect check reads them back ---------------------------------------


def test_verify_effects_confirms_each_declared_file_and_names_a_missing_one(
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "lib" / "pkgconfig").mkdir(parents=True)
    (prefix / "lib" / "libthing-2.so.2").write_bytes(b"\x7fELF")
    verification = verify_effects(_plan(_lib()), None, prefix=prefix)
    files = {c.subject: c for c in verification.checks if c.kind == "file"}
    assert files["libthing:lib/libthing-2.so.2"].confirmed
    assert not files["libthing:lib/pkgconfig/libthing-2.pc"].confirmed
    assert "does not exist" in files["libthing:lib/pkgconfig/libthing-2.pc"].detail


# --- D-051 and update can now decide a unit with no executable ---------------


def test_a_library_is_decidable_once_its_files_are_declared(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    planned = _plan(_lib()).packages[0]
    assert build_effects_present(planned, prefix=prefix) is False
    (prefix / "lib" / "pkgconfig").mkdir(parents=True)
    (prefix / "lib" / "libthing-2.so.2").write_bytes(b"\x7fELF")
    (prefix / "lib" / "pkgconfig" / "libthing-2.pc").write_text("Name: libthing\n")
    assert build_effects_present(planned, prefix=prefix) is True


def test_without_the_declaration_the_same_unit_is_undecidable() -> None:
    planned = _plan(_lib(installed_files=[])).packages[0]
    assert build_effects_present(planned, prefix=Path("/nonexistent")) is None


def test_update_reports_the_library_by_its_pin_instead_of_unknown() -> None:
    states: dict[str, AptPackageState] = {}
    undeclared = report(
        _plan(_lib(installed_files=[])), apt_states=states, present={"libthing": None}, built=()
    )
    assert undeclared.rows[0].state == UNKNOWN
    declared = report(_plan(_lib()), apt_states=states, present={"libthing": True}, built=())
    assert declared.rows[0].state == BEHIND_PIN
    assert "ref v2.2.1" in declared.rows[0].detail


# --- the catalog's own case ---------------------------------------------------


def test_libacars_declares_what_its_install_rule_leaves() -> None:
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    assert catalog["libacars"].installed_files == [
        "lib/libacars-2.so.2",
        "lib/libacars-2.so",
        "lib/pkgconfig/libacars-2.pc",
    ]
    assert [b.install_as for b in catalog["fl-moxgen"].binaries] == ["fl_moxgen"]
