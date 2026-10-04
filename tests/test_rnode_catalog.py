# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `rnode` hardware entry: firmware, not a board.  Track C, D-080.

Closed from upstream's board lists, which name boards and no USB identifier, so
the entry claims no identifier, no symlink and no maintainer verification, and
inherits the serial-board class's permission story (D-027, D-028, D-029).
"""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.hardware import DeviceManifest
from hammunition.manifest.load import load_catalog, load_hardware
from hammunition.manifest.schema import VenvInstall

ROOT = Path(__file__).resolve().parent.parent


def _rnode() -> DeviceManifest:
    _, devices = load_hardware(ROOT / "catalog" / "hardware")
    return devices["rnode"]


def test_the_entry_claims_no_identifier_no_symlink_and_no_verification() -> None:
    rnode = _rnode()
    # `supported` is earned by an identifier of its own (D-018, D-027); there is none to confirm.
    assert rnode.status == "untested"
    assert rnode.maintainer_verified is None  # nobody here has run an RNode
    assert rnode.usb_ids == [] and rnode.udev is None  # D-028: a bridge chip names no /dev node
    assert rnode.gap_closure == "unverified_by_maintainer"
    assert rnode.identification_gap and "no USB identifier of its own" in rnode.identification_gap


def test_an_rnode_inherits_dialout_so_rnodeconf_can_open_the_port() -> None:
    """The first thing that fails for a new operator: `rnodeconf` cannot open
    /dev/ttyACM0 or /dev/ttyUSB0. The class gives the group; the entry must not
    override it with a list that lacks it."""
    classes, devices = load_hardware(ROOT / "catalog" / "hardware")
    rnode = devices["rnode"]
    assert rnode.device_class == "badgelife"
    assert rnode.groups == []  # inherits; an explicit list here would replace the class's
    assert "dialout" in classes["badgelife"].groups
    assert "dialout" in (rnode.documentation.setup_steps or "")


def test_the_flasher_it_names_is_installed_by_the_rns_unit() -> None:
    rnode = _rnode()
    assert rnode.packages == ["rns"]
    (firmware,) = rnode.firmware
    assert firmware.kind == "vendor_tool" and firmware.packages == ["rns"]
    (block,) = load_catalog(ROOT / "catalog" / "packages")["rns"].install
    assert isinstance(block.install, VenvInstall) and "rnodeconf" in block.install.expose


def test_the_legal_note_is_a_disclosure_not_a_ruling() -> None:
    """Part 97 and encryption: said, never adjudicated (D-021's rule for gates,
    applied to prose)."""
    problems = _rnode().documentation.known_problems
    assert problems is not None
    assert "Part 97" in problems and "stated as disclosure and not as a ruling" in problems
    assert "not for this catalog to say" in problems
    for forbidden in ("is legal", "is lawful on", "you may transmit", "is permitted"):
        assert forbidden not in problems
