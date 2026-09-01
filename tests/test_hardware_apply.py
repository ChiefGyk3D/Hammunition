# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Planning the hardware role: udev rules and group membership.

The plan writes nothing; it computes what an apply would do. These hold it to
the same narrow promises the rest of the engine keeps — idempotence (nothing
to add when already set up), disclosure (the exact rules content), and honest
detection that drives nothing (D-020).
"""

from __future__ import annotations

from pathlib import Path

from hammunition.hardware import plan_hardware, rules_file
from hammunition.hardware.detect import AttachedDevice
from hammunition.manifest.hardware import DeviceClass, DeviceManifest, HardwareDocumentation

DOCS = HardwareDocumentation(
    what_it_is="A software defined radio receiver used for wideband reception.",
    what_you_can_do_with_it="Receive and decode signals across a wide frequency range.",
    setup_steps="Plug it in, join plugdev, then log out and back in again.",
)


def _device(name: str, vendor: str, product: str, groups: list[str]) -> DeviceManifest:
    return DeviceManifest.model_validate(
        {
            "name": name,
            "summary": f"{name} test device",
            "vendor": "Example Ltd",
            "groups": groups,
            "documentation": DOCS,
            "usb_ids": [
                {
                    "vendor": vendor,
                    "product": product,
                    "description": f"{name} id",
                    "evidence": "Debian 13 /lib/udev/rules.d/40-example.rules",
                    "confirmed": True,
                    "node_kind": "libusb",
                }
            ],
            "udev": {"symlink": name, "group": "plugdev", "mode": "0660"},
        }
    )


def _catalog() -> tuple[dict[str, DeviceClass], dict[str, DeviceManifest]]:
    devices = {
        "alpha": _device("alpha", "1d50", "6089", ["plugdev"]),
        "beta": _device("beta", "0403", "6015", ["dialout", "plugdev"]),
    }
    return {}, devices


def test_the_rules_content_is_the_whole_catalog() -> None:
    classes, devices = _catalog()
    plan = plan_hardware(classes, devices, user="op", user_groups_now=frozenset(), attached=[])
    expected, _ = rules_file([*classes.values(), *devices.values()])
    assert plan.rules_content == expected
    assert plan.rules_content, "a catalog with udev bindings must produce rules"


def test_already_current_when_the_file_matches(tmp_path: Path) -> None:
    classes, devices = _catalog()
    content, _ = rules_file([*devices.values()])
    rules = tmp_path / "65-hammunition.rules"
    rules.write_text(content)
    plan = plan_hardware(
        classes,
        devices,
        user="op",
        user_groups_now=frozenset({"plugdev", "dialout"}),
        attached=[],
        rules_path=str(rules),
    )
    assert plan.rules_already_current
    assert plan.groups_to_add == []
    assert plan.is_noop


def test_groups_partition_on_current_membership() -> None:
    classes, devices = _catalog()
    plan = plan_hardware(
        classes, devices, user="op", user_groups_now=frozenset({"plugdev"}), attached=[]
    )
    assert plan.groups_to_add == ["dialout"]
    assert plan.groups_present == ["plugdev"]
    assert not plan.is_noop  # groups still to add


def test_a_missing_rules_file_is_not_current(tmp_path: Path) -> None:
    classes, devices = _catalog()
    plan = plan_hardware(
        classes,
        devices,
        user="op",
        user_groups_now=frozenset({"plugdev", "dialout"}),
        attached=[],
        rules_path=str(tmp_path / "does-not-exist.rules"),
    )
    assert not plan.rules_already_current
    assert not plan.is_noop


def test_detection_recognises_an_attached_catalog_device() -> None:
    classes, devices = _catalog()
    attached = [
        AttachedDevice(vendor="1d50", product="6089", product_string="Alpha"),
        AttachedDevice(vendor="dead", product="beef", product_string="Nothing we know"),
    ]
    plan = plan_hardware(
        classes, devices, user="op", user_groups_now=frozenset(), attached=attached
    )
    assert [m.name for m in plan.detected] == ["alpha"]
    assert [d.identifier for d in plan.unrecognised] == ["dead:beef"]


def test_class_groups_are_inherited_into_the_union() -> None:
    cls = DeviceClass.model_validate(
        {
            "kind": "class",
            "name": "sdr",
            "summary": "SDR class",
            "groups": ["plugdev"],
            "documentation": DOCS,
            "usb_ids": [
                {
                    "vendor": "1d50",
                    "product": "6089",
                    "description": "class id",
                    "evidence": "Debian 13 /lib/udev/rules.d/40-example.rules",
                    "confirmed": True,
                    "node_kind": "libusb",
                }
            ],
        }
    )
    member = DeviceManifest.model_validate(
        {
            "name": "member",
            "summary": "member device",
            "vendor": "Example Ltd",
            "device_class": "sdr",
            "groups": ["dialout"],
            "documentation": DOCS,
        }
    )
    plan = plan_hardware(
        {"sdr": cls}, {"member": member}, user="op", user_groups_now=frozenset(), attached=[]
    )
    # union of the member's own dialout and the class's plugdev
    assert plan.groups_to_add == ["dialout", "plugdev"]
