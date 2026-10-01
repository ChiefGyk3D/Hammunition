# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig class and the FT-991A / UV-50PRO entries load and carry their rig data."""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.load import load_hardware

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "hardware"


def _load() -> tuple[dict[str, object], dict[str, object]]:
    classes, devices = load_hardware(CATALOG)
    return classes, devices


def test_rig_class_carries_dialout_and_the_cp2105() -> None:
    classes, _ = _load()
    rig = classes["rig"]
    assert "dialout" in rig.groups
    pairs = {(i.vendor, i.product) for i in rig.usb_ids}
    assert ("10c4", "ea70") in pairs
    cp2105 = next(i for i in rig.usb_ids if i.product == "ea70")
    assert cp2105.ambiguity is not None


def test_ft_991a_is_a_cat_rig_at_model_1035() -> None:
    _, devices = _load()
    ft = devices["yaesu-ft-991a"]
    assert ft.device_class == "rig"
    assert ft.rig is not None
    assert ft.rig.kind == "cat"
    assert ft.rig.hamlib_model == 1035
    assert ft.rig.cat is not None
    assert ft.rig.cat.baud == (4800, 38400)
    assert ft.status == "untested"


def test_uv_50pro_is_a_ptt_only_rig() -> None:
    _, devices = _load()
    uv = devices["btech-uv-50pro"]
    assert uv.device_class == "rig"
    assert uv.rig is not None
    assert uv.rig.kind == "ptt_only"
    assert uv.rig.ptt_only is not None
    assert uv.rig.ptt_only.vox is True
    assert uv.usb_ids == []  # no USB interface of its own
