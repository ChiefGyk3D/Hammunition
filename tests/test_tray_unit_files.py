# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tray units do not write the helper's files.  D-056 amended 2026-10-02.

The helper lives in hammunition-tray now, and so do its wrapper and polkit
action: `install.sh` from a checkout, or a `hammunition-devctl` .deb whose
postinst writes the wrapper and which owns the polkit file. A catalog
`config_files` entry for either would be wrong three ways (the manifests say
which), and written against the v0.4.0 pin, which ships no helper, it would
replace a working helper with one that exits 2. The review of this change
found exactly that, as a block that was live; this holds the absence.

When a unit is re-pinned to the tray release that ships the helper, that PR adds
the `hammunition-devctl` .deb as an install step and changes this test with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.hardware.polkit import HELPER_PATH, POLICY_PATH
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import PackageManifest

CATALOG = Path(__file__).resolve().parent.parent / "catalog"
UNITS = ("hammunition-tray", "hammunition-tray-qt")


@pytest.fixture(scope="module")
def packages() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG / "packages")


@pytest.mark.parametrize("unit", UNITS)
def test_no_tray_unit_writes_the_wrapper_or_the_polkit_action(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    written = {c.path for c in packages[unit].config_files}
    assert HELPER_PATH not in written and POLICY_PATH not in written, (
        f"{unit} writes the helper's wrapper or polkit action as a catalog file; they are "
        f"the tray's own (install.sh, or the hammunition-devctl .deb that owns the policy), "
        f"and the wrapper bakes in an interpreter a catalog file cannot name"
    )


@pytest.mark.parametrize("unit", UNITS)
def test_the_manifest_says_why_and_what_the_re_pin_adds(unit: str) -> None:
    text = (CATALOG / "packages" / f"{unit}.yaml").read_text()
    assert "DECLARES NO `config_files`" in text
    assert "hammunition-devctl` .deb as an install step" in text
