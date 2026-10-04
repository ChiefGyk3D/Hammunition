# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The standalone console unit is retired: the console is `hammunition console` (#302)."""

from pathlib import Path

import yaml

from hammunition.cli.main import load_all
from hammunition.manifest.schema import RetireReason, Status

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "catalog" / "packages" / "hammunition-console.yaml"


def test_the_unit_validates_as_retired_and_names_the_issue() -> None:
    packages, _ = load_all(ROOT / "catalog")
    unit = packages["hammunition-console"]
    assert unit.status is Status.retired and unit.retire_reason is RetireReason.world_changed
    assert unit.status_reason is not None
    assert "hammunition console" in unit.status_reason and "#302" in unit.status_reason


def test_it_is_in_no_profile_and_carries_no_launcher() -> None:
    for path in (ROOT / "catalog" / "profiles").glob("*.yaml"):
        assert "hammunition-console" not in path.read_text(), path.name
    assert yaml.safe_load(MANIFEST.read_text()).get("launchers") in (None, [])


def test_the_install_block_stays_so_an_uninstall_can_find_what_v0_1_0_placed() -> None:
    data = yaml.safe_load(MANIFEST.read_text())
    assert {b["install"]["method"] for b in data["install"]} == {"binary"}
    assert data["install"][0]["install"]["artifact"]["sha256"] != "0" * 64
