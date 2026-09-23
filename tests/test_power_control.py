# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Device power control: the catalog block, the planner, and the executor.

The block is data that can never be a command (D-056): `method` and `quiet`
are fixed enums, so a manifest cannot smuggle a shell line through them.
"""

from __future__ import annotations

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


def test_plan_park_writes_authorized_then_power_control(tmp_path: Path) -> None:
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(tmp_path), ambiguous=False)],
        _entries({"method": "usb_deauthorize", "quiet": [], "note": NOTE}),
    )
    node = tmp_path / "1-4"
    assert plan_park(found[0]).writes == (
        Write(path=str(node / "authorized"), value="0"),
        Write(path=str(node / "power" / "control"), value="auto"),
    )


def test_plan_wake_writes_only_authorized(tmp_path: Path) -> None:
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(tmp_path, authorized="0"), ambiguous=False)],
        _entries({"method": "usb_deauthorize", "note": NOTE}),
    )
    assert plan_wake(found[0]).writes == (
        Write(path=str(tmp_path / "1-4" / "authorized"), value="1"),
    )


def test_the_quiet_verbs_ride_on_the_plan(tmp_path: Path) -> None:
    found, _ = parkable(
        [Match(name="gps-receiver", attached=_bus(tmp_path), ambiguous=False)],
        _entries(
            {
                "method": "usb_deauthorize",
                "quiet": ["networkmanager_autoconnect"],
                "note": NOTE,
            }
        ),
    )
    assert plan_park(found[0]).quiet == ("networkmanager_autoconnect",)
    assert plan_park(found[0]).restore is False
    assert plan_wake(found[0]).restore is True


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


def test_guard_accepts_the_symlinked_node_every_real_device_is(tmp_path: Path) -> None:
    """Review Focus 1, the over-matching half. `/sys/bus/usb/devices/1-4` is a
    symlink into /sys/devices/pci..., so a containment check that resolves the
    candidate and demands the result still sit under the bus root refuses
    every device there is. This test fails against that implementation."""
    assert guard("/sys/bus/usb/devices/1-4/power/control")


def test_execute_writes_and_reads_back(tmp_path: Path) -> None:
    node = tmp_path / "1-4"
    (node / "power").mkdir(parents=True)
    (node / "authorized").write_text("1\n")
    plan = PowerPlan(
        writes=(Write(path=str(node / "authorized"), value="0"),), quiet=(), restore=False
    )
    assert execute(plan) == []
    assert (node / "authorized").read_text().strip() == "0"


def test_execute_fails_when_the_readback_does_not_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-031. A write that returned without raising is not evidence."""
    node = tmp_path / "1-4"
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


def test_execute_reports_a_missing_pkexec_uid_rather_than_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 3. Under sudo rather than pkexec, PKEXEC_UID is simply not
    set. Taking the whole park down after the hardware write already happened
    would be the worst possible moment to raise.

    **subprocess.run is stubbed, and that is not optional.** Unstubbed, this
    test runs `nmcli connection modify <every profile> connection.autoconnect
    no` against whatever machine runs the suite -- which on this project is
    the maintainer's own laptop. A test that disables autoconnect on every
    network profile is a destructive side effect, not a test.
    """
    monkeypatch.delenv("PKEXEC_UID", raising=False)
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="Wired\n", stderr="")

    monkeypatch.setattr("hammunition.hardware.power.subprocess.run", fake_run)

    node = tmp_path / "1-4"
    node.mkdir()
    (node / "authorized").write_text("1\n")
    plan = PowerPlan(
        writes=(Write(path=str(node / "authorized"), value="0"),),
        quiet=("networkmanager_autoconnect",),
        restore=False,
    )
    problems = execute(plan)
    assert (node / "authorized").read_text().strip() == "0", "the hardware step still ran"
    assert problems == [], "a missing PKEXEC_UID is a normal invocation, not a problem"
    assert calls, "the quiet verb should still have been attempted"
    assert not any("setpriv" in c[0] for c in calls), "no uid to drop to, so no setpriv"


def test_execute_shells_out_to_nothing_when_there_are_no_quiet_verbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The GPS receiver's quiet list is empty, which is the shipped case. It
    must reach no subprocess at all -- a park on a machine with no
    NetworkManager is the common one, not the exception."""

    def exploding_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("execute() shelled out with an empty quiet list")

    monkeypatch.setattr("hammunition.hardware.power.subprocess.run", exploding_run)
    node = tmp_path / "1-4"
    node.mkdir()
    (node / "authorized").write_text("1\n")
    plan = PowerPlan(
        writes=(Write(path=str(node / "authorized"), value="0"),), quiet=(), restore=False
    )
    assert execute(plan) == []
