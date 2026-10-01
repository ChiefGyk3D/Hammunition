# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The RigBlock schema on radio device manifests.  D-073 §3b."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hammunition.manifest.hardware import RigBlock
from hammunition.manifest.schema import ManifestError


def test_cat_block_loads() -> None:
    rig = RigBlock.model_validate(
        {
            "hamlib_model": 1035,
            "cat": {
                "kind": "usb_cp2105_dual",
                "interface": "00",
                "baud": [4800, 38400],
                "handshake": "hardware",
            },
            "audio": "builtin_usb_codec",
            "ptt": ["cat", "rts"],
            "ptt_interface": "01",
        }
    )
    assert rig.kind == "cat"
    assert rig.hamlib_model == 1035
    assert rig.cat is not None
    assert rig.cat.baud == (4800, 38400)


def test_ptt_only_block_loads() -> None:
    rig = RigBlock.model_validate(
        {"ptt_only": {"lines": ["rts", "dtr"], "vox": True}, "audio": "external_interface"}
    )
    assert rig.kind == "ptt_only"
    assert rig.ptt_only is not None
    assert rig.ptt_only.vox is True


def test_cat_and_ptt_only_are_mutually_exclusive() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        RigBlock.model_validate(
            {
                "hamlib_model": 1035,
                "cat": {"kind": "usb_cp210x", "baud": [4800, 38400], "handshake": "none"},
                "ptt_only": {"lines": ["rts"]},
                "audio": "none",
            }
        )


def test_neither_cat_nor_ptt_only_is_refused() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        RigBlock.model_validate({"audio": "none"})


def test_cat_needs_both_model_and_port() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        RigBlock.model_validate({"hamlib_model": 1035, "audio": "none"})


def test_baud_range_must_be_ordered() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        RigBlock.model_validate(
            {
                "hamlib_model": 1035,
                "cat": {"kind": "usb_cp210x", "baud": [38400, 4800], "handshake": "none"},
                "audio": "none",
            }
        )
