# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resolving a rig value against the catalog and this machine's hamlib.  D-073 §4."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.manifest.load import load_hardware
from hammunition.rig import RigError, check_rig_baud, resolve_rig

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "hardware"


def _devices() -> dict[str, object]:
    _classes, devices = load_hardware(CATALOG)
    return devices


def test_resolve_a_catalogued_cat_rig() -> None:
    res = resolve_rig("yaesu-ft-991a", _devices())
    assert res.kind == "cat"
    assert res.hamlib_model == 1035
    assert res.baud_range == (4800, 38400)
    assert res.manifest_name == "yaesu-ft-991a"
    assert res.uncatalogued is False


def test_resolve_a_catalogued_ptt_only_rig() -> None:
    res = resolve_rig("btech-uv-50pro", _devices())
    assert res.kind == "ptt_only"
    assert res.hamlib_model is None
    assert res.baud_range is None


def test_resolve_an_uncatalogued_hamlib_model() -> None:
    res = resolve_rig(
        "hamlib:3073", _devices(), model_lister=lambda: {3073: (1200, 115200)}
    )
    assert res.kind == "cat"
    assert res.hamlib_model == 3073
    assert res.baud_range == (1200, 115200)
    assert res.uncatalogued is True
    assert res.manifest_name is None


def test_a_hamlib_model_this_machine_lacks_is_refused() -> None:
    with pytest.raises(RigError):
        resolve_rig("hamlib:9999", _devices(), model_lister=lambda: {})


def test_a_value_that_is_not_a_rig_is_refused_naming_the_rigs() -> None:
    with pytest.raises(RigError) as exc:
        resolve_rig("not-a-rig", _devices())
    assert "yaesu-ft-991a" in str(exc.value)


def test_a_device_that_is_not_a_rig_is_refused() -> None:
    # hackrf-pro exists but has no rig block.
    with pytest.raises(RigError):
        resolve_rig("hackrf-pro", _devices())


def test_check_rig_baud_in_and_out_of_range() -> None:
    assert check_rig_baud(4800, (4800, 38400)) is None
    problem = check_rig_baud(2400, (4800, 38400))
    assert problem is not None and "4800" in problem and "38400" in problem
