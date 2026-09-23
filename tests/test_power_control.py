# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Device power control: the catalog block, the planner, and the executor.

The block is data that can never be a command (D-056): `method` and `quiet`
are fixed enums, so a manifest cannot smuggle a shell line through them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hammunition.manifest.hardware import (
    DeviceClass,
    HardwareDocumentation,
    PowerControl,
)

DOCS = HardwareDocumentation(
    what_it_is="A USB GNSS receiver reporting position and time over a serial port.",
    what_you_can_do_with_it="Feed position and time to the whole station through gpsd.",
    setup_steps="Install gpsd, join dialout, log out and back in, then run cgps.",
)

NOTE = "gpsd handles hot-unplug itself, so nothing else needs quieting here."


def _class(power: dict[str, object] | None) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": "gps-receiver",
        "summary": "USB GNSS receivers",
        "documentation": DOCS,
        "usb_ids": [
            {
                "vendor": "1546",
                "product": "01a7",
                "description": "u-blox 7 GNSS module",
                "evidence": "Debian 13 /usr/lib/udev/rules.d/60-gpsd.rules, gpsd 3.25.",
                "confirmed": True,
                "node_kind": "serial",
            }
        ],
    }
    if power is not None:
        entry["power_control"] = power
    return entry


def test_a_class_round_trips_a_power_control_block() -> None:
    entry = DeviceClass.model_validate(
        _class({"method": "usb_deauthorize", "quiet": [], "note": NOTE})
    )
    assert entry.power_control is not None
    assert entry.power_control.method == "usb_deauthorize"
    assert entry.power_control.quiet == []
    assert entry.power_control.note == NOTE


def test_an_entry_without_the_block_is_not_parkable() -> None:
    entry = DeviceClass.model_validate(_class(None))
    assert entry.power_control is None


def test_pci_runtime_is_schema_valid_so_a_wwan_class_can_carry_it() -> None:
    entry = DeviceClass.model_validate(
        _class({"method": "pci_runtime", "note": "D3cold via d3cold_allowed."})
    )
    assert entry.power_control is not None
    assert entry.power_control.method == "pci_runtime"


def test_an_unknown_method_is_refused_naming_the_field() -> None:
    with pytest.raises(ValidationError) as caught:
        DeviceClass.model_validate(_class({"method": "run_this_script", "note": NOTE}))
    assert "method" in str(caught.value)


def test_an_unknown_quiet_verb_is_refused_naming_the_field() -> None:
    with pytest.raises(ValidationError) as caught:
        DeviceClass.model_validate(
            _class({"method": "usb_deauthorize", "quiet": ["rm -rf /"], "note": NOTE})
        )
    assert "quiet" in str(caught.value)


def test_a_note_too_short_to_explain_anything_is_refused() -> None:
    with pytest.raises(ValidationError):
        DeviceClass.model_validate(_class({"method": "usb_deauthorize", "note": "n/a"}))


def test_the_block_forbids_extra_keys() -> None:
    with pytest.raises(ValidationError):
        DeviceClass.model_validate(
            _class({"method": "usb_deauthorize", "note": NOTE, "command": "echo hi"})
        )


def test_the_block_is_frozen() -> None:
    control = PowerControl(method="usb_deauthorize", note=NOTE)
    with pytest.raises(ValidationError):
        control.method = "pci_runtime"  # type: ignore[misc]
