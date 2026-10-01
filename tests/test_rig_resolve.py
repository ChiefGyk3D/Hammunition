# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resolving a rig value against the catalog and this machine's hamlib.  D-073 §4."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.manifest.hardware import DeviceManifest
from hammunition.manifest.load import load_hardware
from hammunition.rig import RigError, check_rig_baud, resolve_rig

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "hardware"


def _devices() -> dict[str, DeviceManifest]:
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
    res = resolve_rig("hamlib:3073", _devices(), model_lister=lambda: {3073: (1200, 115200)})
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


def test_elide_serial_mid_string() -> None:
    from hammunition.rig import elide_serial

    cmd = "rigctld -r /dev/serial/by-id/usb-Silicon_Labs_CP2105_ABC123-if00-port0 -s 38400"
    out = elide_serial(cmd)
    assert "ABC123" not in out
    assert "…" in out
    assert "-s 38400" in out  # the rest of the line is untouched


def test_elide_serial_at_end() -> None:
    from hammunition.rig import elide_serial

    out = elide_serial("/dev/serial/by-id/usb-Silicon_Labs_CP2105_ABC123-if00-port0")
    assert "ABC123" not in out and out.endswith("-if00-port0")


def test_hamlib_with_a_non_numeric_model_is_a_rig_error() -> None:
    # Review I6: `int()` must not raise a bare ValueError the CLI won't catch.
    with pytest.raises(RigError):
        resolve_rig("hamlib:abc", _devices(), model_lister=lambda: {3073: (1200, 115200)})


def test_rigctl_absent_is_a_rig_error_not_a_traceback() -> None:
    # Review I6: a missing rigctl must surface as a RigError, not FileNotFoundError.
    def missing() -> dict[int, tuple[int, int]]:
        raise FileNotFoundError("rigctl")

    with pytest.raises(RigError):
        resolve_rig("hamlib:3073", _devices(), model_lister=missing)
