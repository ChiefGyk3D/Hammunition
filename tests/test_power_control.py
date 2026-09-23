# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Device power control: the catalog block, the planner, and the executor.

The block is data that can never be a command (D-056): `method` and `quiet`
are fixed enums, so a manifest cannot smuggle a shell line through them.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from hammunition.hardware.detect import AttachedDevice, Match
from hammunition.hardware.power import (
    PowerError,
    PowerPlan,
    Write,
    execute,
    guard,
    parkable,
    plan_park,
    plan_wake,
)
from hammunition.manifest.hardware import (
    DeviceClass,
    HardwareDocumentation,
    PowerControl,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

DOCS = HardwareDocumentation(
    what_it_is="A USB GNSS receiver reporting position and time over a serial port.",
    what_you_can_do_with_it="Feed position and time to the whole station through gpsd.",
    setup_steps="Install gpsd, join dialout, log out and back in, then run cgps.",
)

NOTE = "gpsd handles hot-unplug itself, so nothing else needs quieting here."


@pytest.fixture
def sysfs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthetic device tree that guard() will accept.

    The planner and executor call guard() on every path they write, which is
    the point of it -- so a test tree outside the real bus roots has to be
    named as a root rather than the check removed. guard()'s own tests still
    run against the real ALLOWED_ROOTS, so the shipped behaviour stays pinned.
    """
    from hammunition.hardware import power

    monkeypatch.setattr(power, "ALLOWED_ROOTS", (*power.ALLOWED_ROOTS, str(tmp_path)))
    return tmp_path


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


def _bus(tmp_path: Path, address: str = "1-4", authorized: str = "1") -> AttachedDevice:
    """A synthetic sysfs tree shaped like the real one: the device node, its
    `authorized` file, and a `power/control` subdirectory."""
    node = tmp_path / address
    (node / "power").mkdir(parents=True)
    (node / "idVendor").write_text("1546\n")
    (node / "idProduct").write_text("01a7\n")
    (node / "authorized").write_text(f"{authorized}\n")
    (node / "power" / "control").write_text("on\n")
    return AttachedDevice(vendor="1546", product="01a7", sysfs_path=str(node))


def _entries(power: dict[str, object] | None) -> dict[str, DeviceClass]:
    return {"gps-receiver": DeviceClass.model_validate(_class(power))}


def test_a_matched_attached_device_with_the_block_is_parkable(tmp_path: Path) -> None:
    device = _bus(tmp_path)
    entries = _entries({"method": "usb_deauthorize", "note": NOTE})
    found, skipped = parkable(
        [Match(name="gps-receiver", attached=device, ambiguous=False)], entries
    )
    assert skipped == []
    assert len(found) == 1
    assert found[0].name == "gps-receiver"
    assert found[0].sysfs_path == device.sysfs_path
    assert found[0].parked is False


def test_a_device_without_the_block_is_not_parkable(tmp_path: Path) -> None:
    found, skipped = parkable(
        [Match(name="gps-receiver", attached=_bus(tmp_path), ambiguous=False)],
        _entries(None),
    )
    assert found == []
    assert skipped == []


def test_an_ambiguous_match_is_still_parkable(tmp_path: Path) -> None:
    """D-028 governs naming a device, not unplugging one. Parking a
    mis-identified USB device is a reversible unplug, not a claim on it."""
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(tmp_path), ambiguous=True)],
        _entries({"method": "usb_deauthorize", "note": NOTE}),
    )
    assert len(found) == 1


def test_parked_is_read_from_sysfs(tmp_path: Path) -> None:
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(tmp_path, authorized="0"), ambiguous=False)],
        _entries({"method": "usb_deauthorize", "note": NOTE}),
    )
    assert found[0].parked is True


def test_an_unreadable_authorized_file_is_skipped_with_a_reason(tmp_path: Path) -> None:
    """Review Focus 5. Not every bus exposes `authorized`, and a device can
    vanish between the listing and the read. Reporting it as not-parked would
    show a wake switch for something that cannot be parked."""
    device = _bus(tmp_path)
    (Path(device.sysfs_path or "") / "authorized").unlink()
    found, skipped = parkable(
        [Match(name="gps-receiver", attached=device, ambiguous=False)],
        _entries({"method": "usb_deauthorize", "note": NOTE}),
    )
    assert found == []
    assert len(skipped) == 1
    assert skipped[0][0] == "gps-receiver"
    assert "authorized" in skipped[0][1]


def test_a_record_with_no_sysfs_path_is_skipped_with_a_reason() -> None:
    found, skipped = parkable(
        [Match(name="gps-receiver", attached=AttachedDevice("1546", "01a7"), ambiguous=False)],
        _entries({"method": "usb_deauthorize", "note": NOTE}),
    )
    assert found == []
    assert skipped and "sysfs" in skipped[0][1]


def test_two_of_the_same_class_both_appear_with_their_own_addresses(tmp_path: Path) -> None:
    """Review Focus 2. Two u-blox pucks are two parkables, not one."""
    entries = _entries({"method": "usb_deauthorize", "note": NOTE})
    matches = [
        Match(name="gps-receiver", attached=_bus(tmp_path, address=a), ambiguous=False)
        for a in ("1-4", "1-5")
    ]
    found, _ = parkable(matches, entries)
    assert len(found) == 2
    assert {p.sysfs_path for p in found} == {str(tmp_path / "1-4"), str(tmp_path / "1-5")}


def test_plan_park_writes_authorized_then_power_control(sysfs_root: Path) -> None:
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(sysfs_root), ambiguous=False)],
        _entries({"method": "usb_deauthorize", "quiet": [], "note": NOTE}),
    )
    node = sysfs_root / "1-4"
    assert plan_park(found[0]).writes == (
        Write(path=str(node / "authorized"), value="0"),
        Write(path=str(node / "power" / "control"), value="auto"),
    )


def test_plan_wake_writes_only_authorized(sysfs_root: Path) -> None:
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(sysfs_root, authorized="0"), ambiguous=False)],
        _entries({"method": "usb_deauthorize", "note": NOTE}),
    )
    assert plan_wake(found[0]).writes == (
        Write(path=str(sysfs_root / "1-4" / "authorized"), value="1"),
    )


def test_a_plan_records_whether_it_is_hushing_or_restoring(sysfs_root: Path) -> None:
    """restore=not park is live code with nothing exercising it since the
    quiet-verbs test it used to ride along on was replaced by the refusal
    test below -- a device with an empty quiet list is the only shape that
    still reaches a built PowerPlan to check it on."""
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(sysfs_root), ambiguous=False)],
        _entries({"method": "usb_deauthorize", "quiet": [], "note": NOTE}),
    )
    assert plan_park(found[0]).restore is False
    assert plan_wake(found[0]).restore is True
    assert plan_park(found[0]).quiet == ()


def test_a_quiet_verb_is_refused_until_a_device_needs_one(sysfs_root: Path) -> None:
    """Schema-valid, and refused, on the same grounds as pci_runtime: the only
    consumer is a WWAN modem whose own method ships refused."""
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(sysfs_root), ambiguous=False)],
        _entries(
            {
                "method": "usb_deauthorize",
                "quiet": ["networkmanager_autoconnect"],
                "note": NOTE,
            }
        ),
    )
    with pytest.raises(PowerError, match="not implemented"):
        plan_park(found[0])


def test_pci_runtime_is_refused_until_a_card_proves_it(tmp_path: Path) -> None:
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(tmp_path), ambiguous=False)],
        _entries({"method": "pci_runtime", "note": "D3cold via d3cold_allowed."}),
    )
    with pytest.raises(PowerError, match="not implemented"):
        plan_park(found[0])


def test_guard_accepts_a_real_usb_node() -> None:
    assert guard("/sys/bus/usb/devices/1-4/authorized")


def test_guard_refuses_a_traversal() -> None:
    """Review Focus 1, the under-matching half: `..` must never be a way out,
    and it must be refused *before* any resolution, because on a machine
    without that node `resolve()` silently produces a path that looks fine."""
    for escape in (
        "/sys/bus/usb/devices/../../../etc/shadow",
        "/sys/bus/usb/devices/1-4/../../../../etc/shadow",
        "/etc/shadow",
        "/sys/bus/usb/devices",
        "/sys/class/net/wlan0/authorized",
    ):
        with pytest.raises(PowerError, match="outside"):
            guard(escape)


def test_guard_refuses_a_root_writable_node_that_is_not_ours() -> None:
    """Under the right root and still not ours. Every USB node carries
    driver/ and subsystem/ symlinks the kernel made, and they are writable."""
    for sibling in (
        "/sys/bus/usb/devices/1-4/driver/unbind",
        "/sys/bus/usb/devices/1-4/subsystem/drivers_probe",
        "/sys/bus/usb/devices/1-4/remove",
    ):
        with pytest.raises(PowerError):
            guard(sibling)


def test_guard_refuses_a_leaf_reached_through_an_intermediate_segment() -> None:
    """The bypass a bare suffix match allows. `driver` and `subsystem` are
    kernel-made symlinks on every USB node, so a path ending in a permitted
    leaf can still point clean out of the node it claims to be inside."""
    for escape in (
        "/sys/bus/usb/devices/1-4/driver/authorized",
        "/sys/bus/usb/devices/1-4/subsystem/power/control",
        "/sys/bus/usb/devices/1-4/foo/power/control",
        "/sys/bus/usb/devices/1-4/driver/module/parameters/authorized",
    ):
        with pytest.raises(PowerError):
            guard(escape)


def test_guard_refuses_a_component_merely_ending_in_a_leaf_name() -> None:
    for near_miss in (
        "/sys/bus/usb/devices/1-4/notauthorized",
        "/sys/bus/usb/devices/1-4/authorized_default",
        "/sys/bus/usb/devices/authorized",
    ):
        with pytest.raises(PowerError):
            guard(near_miss)


def test_guard_still_accepts_exactly_the_two_real_writes() -> None:
    assert guard("/sys/bus/usb/devices/1-4/authorized")
    assert guard("/sys/bus/usb/devices/1-4/power/control")
    assert guard("/sys/bus/pci/devices/0000:00:14.0/power/control")
    # normpath collapses these to the same node, so they are the same write.
    assert guard("/sys/bus/usb/devices//1-4/authorized")
    assert guard("/sys/bus/usb/devices/./1-4/authorized")


def test_guard_never_touches_the_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    """The containment check is lexical, and this is the test that says so.

    A real device node is a symlink into /sys/devices, so a guard that
    resolved its argument would refuse every device on the machine. The
    previous version of this test asserted that by naming a bus address and
    expecting it to pass -- which proved nothing, because the address did not
    exist on the test machine and a non-strict resolve() leaves a nonexistent
    component alone. Asserting that no resolution is attempted at all cannot
    pass against a resolving implementation on any machine.

    Patches only `Path.resolve` and `os.path.realpath` -- the two functions
    that actually follow a symlink, which is the property being pinned.
    `os.path.abspath` does not follow symlinks and was never part of that
    property; patching it too caught pytest's own traceback formatter (which
    calls `os.path.abspath` while rendering a failure) in the same trap and
    turned a real regression into a pytest INTERNALERROR instead of a clean
    FAILED.
    """

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("guard() resolved a path; it must stay lexical")

    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(os.path, "realpath", forbidden)
    assert guard("/sys/bus/usb/devices/1-4/authorized")


def test_execute_writes_and_reads_back(sysfs_root: Path) -> None:
    node = sysfs_root / "1-4"
    (node / "power").mkdir(parents=True)
    (node / "authorized").write_text("1\n")
    plan = PowerPlan(
        writes=(Write(path=str(node / "authorized"), value="0"),), quiet=(), restore=False
    )
    assert execute(plan) == []
    assert (node / "authorized").read_text().strip() == "0"


def test_execute_fails_when_the_readback_does_not_match(
    sysfs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-031. A write that returned without raising is not evidence."""
    node = sysfs_root / "1-4"
    node.mkdir()
    target = node / "authorized"
    target.write_text("1\n")

    real = Path.write_text

    def lying_write(self: Path, data: str, *args: object, **kwargs: object) -> int:
        if self == target:
            return len(data)  # claims success, changes nothing
        return real(self, data, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", lying_write)
    plan = PowerPlan(writes=(Write(path=str(target), value="0"),), quiet=(), restore=False)
    problems = execute(plan)
    assert problems and "authorized" in problems[0]


def test_execute_shells_out_to_nothing_when_there_are_no_quiet_verbs(
    sysfs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This is now a permanent guarantee rather than a case that depends on an
    empty quiet list: the networkmanager_autoconnect verb is refused at plan
    time (see test_a_quiet_verb_is_refused_until_a_device_needs_one), so
    execute() has no quiet-verb step left and can never reach subprocess for
    any reason. Patching the real subprocess.run, not
    hammunition.hardware.power.subprocess.run, because that name no longer
    exists -- power.py does not import subprocess at all any more, and this
    test would otherwise pass vacuously against a module that had regained
    the import without regaining a caller.
    """

    def exploding_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("execute() shelled out; there is no quiet-verb step left")

    monkeypatch.setattr(subprocess, "run", exploding_run)
    node = sysfs_root / "1-4"
    node.mkdir()
    (node / "authorized").write_text("1\n")
    plan = PowerPlan(
        writes=(Write(path=str(node / "authorized"), value="0"),), quiet=(), restore=False
    )
    assert execute(plan) == []


def test_execute_refuses_a_write_outside_the_device_roots(tmp_path: Path) -> None:
    """The guard is called at the write, not only where the plan was built.
    This test fails if execute() stops calling guard() -- which is how the
    check silently became dead code once already."""
    escape = tmp_path / "shadow"
    escape.write_text("original\n")
    plan = PowerPlan(writes=(Write(path=str(escape), value="pwned"),), quiet=(), restore=False)
    with pytest.raises(PowerError, match="outside"):
        execute(plan)
    assert escape.read_text() == "original\n", "nothing may be written before the refusal"


def test_the_shipped_gps_receiver_class_is_parkable() -> None:
    """The one catalog entry this branch marks parkable. A branch that adds
    the machinery and marks nothing has shipped nothing."""
    from hammunition.manifest.load import load_hardware

    classes, _ = load_hardware(REPO_ROOT / "catalog" / "hardware")
    control = classes["gps-receiver"].power_control
    assert control is not None
    assert control.method == "usb_deauthorize"
    assert control.quiet == []
    assert len(control.note) >= 10


def test_no_other_catalog_entry_is_parkable_yet() -> None:
    """pci_runtime ships refused and no wwan-modem class exists on this
    branch. A second parkable entry appearing here is a thing to notice."""
    from hammunition.manifest.load import load_hardware

    classes, devices = load_hardware(REPO_ROOT / "catalog" / "hardware")
    parkables = [
        name for name, entry in {**classes, **devices}.items() if entry.power_control is not None
    ]
    assert parkables == ["gps-receiver"]
