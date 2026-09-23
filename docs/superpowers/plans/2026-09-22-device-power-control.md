# Device power control (plan 1: Hammunition) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A device the hardware catalog marks parkable can be put into a low-power detached state and brought back, without a reboot, from the CLI, the app menu, and (in a second repository) a Plasma tray switch — all three through one privileged helper behind one polkit action.

**Architecture:** An optional `power_control` block on a `DeviceClass`/`DeviceManifest` names a *method* from a fixed enum, never a command, so the catalog stays pure data. A new engine module `hammunition.hardware.power` turns a matched, attached, parkable device into an ordered list of `(path, value)` sysfs writes; a new console script `hammunition-devctl` is the only thing that runs as root, re-deriving everything itself rather than trusting argv. `hardware apply` installs the helper wrapper and the polkit action beside the udev rules. Parked state is never persisted: a reboot resets sysfs and `state` reports the truth from sysfs.

**Tech Stack:** Python 3.11+, pydantic v2 (`Strict`, `extra="forbid"`, `frozen=True`), argparse, pytest, `mypy --strict`, `ruff==0.16.5`. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-09-22-device-power-control-design.md`

## Global Constraints

- `mypy --strict` is a hard gate; every new function is fully annotated. `[tool.mypy] files = ["src", "tests", "scripts"]`.
- `ruff check` and `ruff format --check` are gates; `ruff==0.16.5` exactly; line-length 100; lint selects `E,F,W,I,UP,B,SIM,ANN,RUF`.
- Every new file starts with the two SPDX lines. Engine files: `GPL-3.0-or-later`. Catalog files: `CC0-1.0`.
- **D-031, verify the effect not the exit status.** Every sysfs write is re-read after writing and compared; a mismatch is a failure. A `write_text()` that returned without raising is not evidence.
- **The catalog can never carry a command.** `method` and `quiet` are `Literal` enums validated by pydantic. A string that is not in the enum fails validation with a message naming the field.
- **Nothing ships that has not been run.** `pci_runtime` is schema-valid and refused at runtime with "not implemented"; no `wwan-modem` class is added on this branch.
- Parked state is **not** persisted. No systemd unit, no state file, no boot-time reconciliation.
- Exit codes follow `docs/reference/cli.md`: `EXIT_OK=0`, `EXIT_FAILED=1`, `EXIT_UNPLANNABLE=2`, `EXIT_CONSENT=3` (all already defined in `src/hammunition/cli/main.py:126-129`).
- The maintainer's callsign and grid square never appear in a file, a test, a doc or a commit. This feature never reads station config.
- Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. `scripts/check_commit_claims.py` runs over every commit in the PR.

## Review Focus

Five things the spec implies but does not pin, each most likely to bite a real operator, most likely first. Each has a test assigned to the task that owns the code.

1. **`/sys/bus/usb/devices/1-4` is itself a symlink** into `/sys/devices/pci0000:00/…`. A containment check written as `Path(p).resolve().is_relative_to("/sys/bus/usb/devices")` refuses *every real device*, and one written without `resolve()` accepts `/sys/bus/usb/devices/../../../etc/shadow`. The check must resolve the candidate **and** accept the resolved form, by requiring that the *unresolved* path's parent is exactly an allowed root and the final component contains no separator or `..`. → Task 3.
2. **Two receivers of the same class attached at once.** `parkable()` keyed by catalog name yields two `Parkable` objects both named `gps-receiver`, and `park gps-receiver` then means either. The helper must refuse an ambiguous name, naming both sysfs addresses and telling the operator to pass the address. → Task 3 (planner) and Task 4 (helper refusal).
3. **`PKEXEC_UID` absent, empty, or not an integer.** The quiet verbs run as the invoking user by honouring it; under `sudo` rather than `pkexec` it is simply not set. A `int(os.environ["PKEXEC_UID"])` raises `KeyError`/`ValueError` and takes the whole park down after the hardware write already happened. Absent must mean "run the verb as the current user, report it", never a crash. → Task 3.
4. **Unplug and replug between `state` and `park`.** The USB address is reused or changes; a `Parkable.sysfs_path` cached from an earlier `state` call may now be a different device or gone. The helper re-reads sysfs itself and refuses "not attached" rather than writing to a path that exists but is someone else's device — checked by comparing the vendor:product at the path against the catalog match. → Task 4.
5. **`authorized` absent or unreadable.** Not every bus exposes it, and a device can disappear between `is_dir()` and `read_text()`. `parked` must report honestly (`None` → not parkable, reported with why) rather than raising or defaulting to `False`, which would show a wake switch for a device that cannot be parked. → Task 3.

---

## File Structure

**Create:**
- `src/hammunition/hardware/power.py` — the parkable model, planner, executor, path guard. No I/O beyond sysfs reads/writes; knows nothing about argparse or polkit.
- `src/hammunition/cli/devctl.py` — the `hammunition-devctl` entry point. The only code that runs as root. Re-derives everything from sysfs and the catalog; trusts nothing from argv but a name.
- `src/hammunition/hardware/polkit.py` — renders the polkit action XML and the wrapper script, and computes their install plan. Separate from `apply.py` because `apply.py` is already the udev-and-groups planner and this is a third artefact family with its own content and its own removal.
- `tests/test_power_control.py` — schema, planner, executor, path guard.
- `tests/test_devctl.py` — the helper's argv handling and refusals.
- `tests/test_polkit_artifacts.py` — rendered XML/wrapper content and the apply/unapply plan.
- `docs/hardware/power-control.md` — the operator-facing page.

**Modify:**
- `src/hammunition/manifest/hardware.py` — add `PowerControl`, `PowerMethod`, `QuietVerb`; add the `power_control` field to `_DeviceCommon`; export them.
- `src/hammunition/hardware/detect.py` — add `sysfs_path` to `AttachedDevice`; populate it in `read_usb_bus`.
- `src/hammunition/hardware/__init__.py` — re-export the new names.
- `src/hammunition/hardware/apply.py` — `HardwarePlan` gains the polkit artefacts; `plan_hardware` computes them.
- `src/hammunition/cli/main.py` — `hardware park|wake|state|unapply` commands and parsers; `cmd_hardware_apply` installs and logs the two artefacts.
- `src/hammunition/menus.py` — `device_entries()` and `device_entry_steps()`.
- `pyproject.toml` — the second `[project.scripts]` entry.
- `catalog/hardware/classes/gps-receiver.yaml` — the `power_control` block.
- `docs/reference/cli.md`, `docs/DECISIONS.md`, `docs/hardware/gps-receiver-class.md` (generated).

## Open question for the maintainer, to settle before Task 6

The spec (§4) says the helper and policy are "removed by `uninstall`". **`uninstall` cannot do this as written.** `cmd_uninstall` (`src/hammunition/cli/main.py:1184`) takes package or profile *names* and drives `plan_removal`, which resolves them against `catalog/packages` and `catalog/profiles`. There is no unit named `hardware`, and `hardware apply` writes no transaction-log entry today — the udev rules it has written since M4 are not logged and not removable either.

This plan implements **`hammunition hardware unapply`**: symmetric with `apply`, removes exactly what the transaction log records this feature installed, and does not distort `uninstall`'s package semantics. The alternative — teaching `uninstall` the literal name `hardware` — puts a non-package into the package namespace where a catalog unit could later collide with it.

Task 6 is written for `unapply`. If the maintainer prefers the `uninstall` route, Task 6 changes and nothing else does.

---

## Task 1: The `power_control` catalog block

**Files:**
- Modify: `src/hammunition/manifest/hardware.py` (add models near `UdevBinding`; add field to `_DeviceCommon`; extend `__all__`)
- Test: `tests/test_power_control.py` (create)

**Interfaces:**
- Consumes: `Strict`, `ManifestError` from `hammunition.manifest.schema`; `_DeviceCommon` in this file.
- Produces: `PowerMethod = Literal["usb_deauthorize", "pci_runtime"]`; `QuietVerb = Literal["networkmanager_autoconnect"]`; `class PowerControl(Strict)` with `method: PowerMethod`, `quiet: list[QuietVerb] = []`, `note: str`; `_DeviceCommon.power_control: PowerControl | None = None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_power_control.py`:

```python
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
        DeviceClass.model_validate(
            _class({"method": "run_this_script", "note": NOTE})
        )
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_power_control.py -v`
Expected: FAIL — `ImportError: cannot import name 'PowerControl' from 'hammunition.manifest.hardware'`

- [ ] **Step 3: Write minimal implementation**

In `src/hammunition/manifest/hardware.py`, add after the `UdevBinding` class:

```python
PowerMethod = Literal["usb_deauthorize", "pci_runtime"]
"""How the engine parks a device. A name, never a command.

``usb_deauthorize`` writes ``0`` to the device's ``authorized`` and ``auto`` to
its ``power/control``; the kernel drops the interfaces and every consumer sees
an ordinary unplug. ``pci_runtime`` is reserved for MHI/PCIe cards and is
refused at runtime until a card has proved it here (D-056).
"""

QuietVerb = Literal["networkmanager_autoconnect"]
"""A consumer to hush before parking and restore on wake.

A closed set for the same reason ``PowerMethod`` is one: the catalog is data,
and an open string here would be a place to put a command. Each verb is
implemented by the engine and named by the manifest.
"""


class PowerControl(Strict):
    """What it takes to park this device, and what the operator will observe.

    The whole point of the fixed enums is that a manifest cannot describe *how*
    to park something -- only *which* of the ways the engine already implements
    applies to it. A catalog that could carry a shell line would be the
    intertwined install logic this project exists to replace (D-001).
    """

    method: PowerMethod
    quiet: list[QuietVerb] = Field(
        default_factory=list,
        description="Consumers to hush before parking and restore on wake, in order.",
    )
    note: str = Field(
        min_length=10,
        description=(
            "Prose for the generated device page: what the operator will observe "
            "when this device is parked, and why nothing further is needed."
        ),
    )
```

In `_DeviceCommon`, add after the `udev: UdevBinding | None = None` line:

```python
    power_control: PowerControl | None = Field(
        default=None,
        description=(
            "Present when this device can be parked and woken (D-056). Absent "
            "means it appears on no power-control surface at all -- there is no "
            "'parkable by default', because parking a rig cable mid-QSO is not "
            "a thing to discover by accident."
        ),
    )
```

Add `"PowerControl"`, `"PowerMethod"`, `"QuietVerb"` to `__all__`, in the existing alphabetical order.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_power_control.py -v && python -m mypy src/hammunition/manifest/hardware.py && python -m ruff check src tests && python -m ruff format --check src tests`
Expected: 8 passed; mypy clean; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add src/hammunition/manifest/hardware.py tests/test_power_control.py
git commit -m "$(cat <<'MSG'
Schema: a device can declare how it is parked, as data and never a command

power_control names a method from a fixed enum, so a manifest can say which
of the ways the engine implements applies to a device and cannot say how to
park one. pci_runtime is valid here and refused at runtime until a card has
proved it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 2: `AttachedDevice` remembers where it was read from

**Files:**
- Modify: `src/hammunition/hardware/detect.py:47-70` (the dataclass and `read_usb_bus`)
- Test: `tests/test_hardware.py` (append)

**Interfaces:**
- Produces: `AttachedDevice.sysfs_path: str | None = None`, the `/sys/bus/usb/devices/<addr>` directory the record was read from; `None` when a caller supplied the record by hand.

**Why a new field rather than re-deriving:** the planner needs the exact node it read, and re-finding it by `(vendor, product, serial)` is the D-028 mistake in a new place — two identical dongles would both match the first address.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hardware.py`:

```python
def test_read_usb_bus_records_the_node_it_read_each_device_from(tmp_path: Path) -> None:
    for address, product in (("1-4", "01a7"), ("2-1", "6089")):
        node = tmp_path / address
        node.mkdir()
        (node / "idVendor").write_text("1546\n")
        (node / "idProduct").write_text(f"{product}\n")

    by_id = {d.identifier: d for d in read_usb_bus(tmp_path)}
    assert by_id["1546:01a7"].sysfs_path == str(tmp_path / "1-4")
    assert by_id["1546:6089"].sysfs_path == str(tmp_path / "2-1")


def test_a_hand_built_attached_device_has_no_sysfs_path() -> None:
    assert AttachedDevice(vendor="1546", product="01a7").sysfs_path is None


def test_two_identical_dongles_keep_their_own_addresses(tmp_path: Path) -> None:
    """Deduplication is by (vendor, product, serial); two with *different*
    serials are two devices and each must remember its own node."""
    for address, serial in (("1-4", "AAAA"), ("1-5", "BBBB")):
        node = tmp_path / address
        node.mkdir()
        (node / "idVendor").write_text("1546\n")
        (node / "idProduct").write_text("01a7\n")
        (node / "serial").write_text(f"{serial}\n")

    paths = sorted(d.sysfs_path or "" for d in read_usb_bus(tmp_path))
    assert paths == [str(tmp_path / "1-4"), str(tmp_path / "1-5")]
```

Ensure `from hammunition.hardware.detect import AttachedDevice, read_usb_bus` and `from pathlib import Path` are imported at the top of the file; add whichever is missing.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_hardware.py -k sysfs_path -v`
Expected: FAIL — `TypeError: AttachedDevice.__init__() got an unexpected keyword argument 'sysfs_path'` or `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

In `src/hammunition/hardware/detect.py`, add to `AttachedDevice` after `serial`:

```python
    sysfs_path: str | None = None
    """The ``/sys/bus/usb/devices/<addr>`` node this record was read from.

    Kept because the power planner must write to *the node it read*, not to one
    re-found by identifier: two identical dongles share an identifier and
    differ only in address, so re-deriving would park whichever the search hit
    first. ``None`` when a caller supplied the record rather than the bus.
    """
```

In `read_usb_bus`, pass it when constructing the device:

```python
        device = AttachedDevice(
            vendor=vendor.lower(),
            product=product.lower(),
            manufacturer=_read(entry / "manufacturer"),
            product_string=_read(entry / "product"),
            serial=_read(entry / "serial"),
            sysfs_path=str(entry),
        )
```

The dedup key `(device.vendor, device.product, device.serial)` is unchanged: the path is a property of the record, not part of its identity.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_hardware.py tests/test_hardware_apply.py tests/test_udev_generation.py -v && python -m mypy src/hammunition/hardware/detect.py`
Expected: all pass; mypy clean. (Run the neighbouring suites too: `AttachedDevice` is constructed in several tests and a required field would break them — it is optional for exactly that reason.)

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add src/hammunition/hardware/detect.py tests/test_hardware.py
git commit -m "$(cat <<'MSG'
Detection: a device remembers the sysfs node it was read from

The power planner must write to the node it read. Re-finding one by
identifier is the D-028 mistake in a new place: two identical dongles share
an identifier and differ only in address, so a search would park whichever
came first.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 3: `hammunition.hardware.power` — parkable, plan, execute

**Files:**
- Create: `src/hammunition/hardware/power.py`
- Modify: `src/hammunition/hardware/__init__.py`
- Test: `tests/test_power_control.py` (append)

**Interfaces:**
- Consumes: `Match`, `AttachedDevice` from `.detect`; `DeviceClass`, `DeviceManifest`, `PowerControl` from `hammunition.manifest.hardware`.
- Produces:
  - `ALLOWED_ROOTS: tuple[str, ...]`
  - `class PowerError(Exception)`
  - `@dataclass(frozen=True) class Parkable`: `name: str`, `summary: str`, `method: PowerMethod`, `quiet: tuple[QuietVerb, ...]`, `sysfs_path: str`, `identifier: str`, `parked: bool`
  - `@dataclass(frozen=True) class Write`: `path: str`, `value: str`
  - `@dataclass(frozen=True) class PowerPlan`: `writes: tuple[Write, ...]`, `quiet: tuple[QuietVerb, ...]`, `restore: bool`
  - `def guard(path: str) -> str`
  - `def parkable(matches, entries) -> tuple[list[Parkable], list[tuple[str, str]]]` — (parkables, skipped `(name, why)`)
  - `def plan_park(p: Parkable) -> PowerPlan`
  - `def plan_wake(p: Parkable) -> PowerPlan`
  - `def execute(plan: PowerPlan, *, uid: int | None = None) -> list[str]` — returns problems, empty on success

- [ ] **Step 1: Write the failing test**

Append to `tests/test_power_control.py`:

```python
import subprocess
from pathlib import Path

from hammunition.hardware.detect import AttachedDevice, Match
from hammunition.hardware.power import (
    PowerError,
    Write,
    execute,
    guard,
    parkable,
    plan_park,
    plan_wake,
)


def _bus(tmp_path: Path, address: str = "1-4", authorized: str = "1") -> AttachedDevice:
    """A synthetic sysfs tree shaped like the real one: the device node, its
    `authorized` file, and a `power/control` subdirectory."""
    node = tmp_path / address
    (node / "power").mkdir(parents=True)
    (node / "idVendor").write_text("1546\n")
    (node / "idProduct").write_text("01a7\n")
    (node / "authorized").write_text(f"{authorized}\n")
    (node / "power" / "control").write_text("on\n")
    return AttachedDevice(
        vendor="1546", product="01a7", sysfs_path=str(node)
    )


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


def test_execute_fails_when_the_readback_does_not_match(tmp_path: Path, monkeypatch) -> None:
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
    tmp_path: Path, monkeypatch
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

    def fake_run(argv, *args, **kwargs):
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
    tmp_path: Path, monkeypatch
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
```

Add `PowerPlan` to the `from hammunition.hardware.power import ...` line.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_power_control.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hammunition.hardware.power'`

- [ ] **Step 3: Write minimal implementation**

Create `src/hammunition/hardware/power.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Parking and waking a catalogued device.  D-056.

Turning a ``power_control`` block into the exact sysfs writes it means, and
performing them with the effect verified afterwards rather than the exit
status trusted (D-031).

**Nothing here is persisted.** A reboot resets sysfs, every device wakes, and
:func:`parkable` reads the truth back from the bus. There is no state file to
go stale and nothing to reconcile at boot, which is the whole reason this is
three small functions rather than a daemon.

**Nothing here knows about polkit, argparse or the tray.** It is given matched
devices and returns writes. The privileged boundary is
:mod:`hammunition.cli.devctl`; the surfaces are the CLI, the menu and an applet
in another repository. All three go through the same planner so all three
disclose the same thing.
"""

from __future__ import annotations

import os
import pwd
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hammunition.manifest.hardware import PowerMethod, QuietVerb

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping

    from hammunition.hardware.detect import Match
    from hammunition.manifest.hardware import DeviceClass, DeviceManifest

__all__ = [
    "ALLOWED_ROOTS",
    "Parkable",
    "PowerError",
    "PowerPlan",
    "Write",
    "execute",
    "guard",
    "plan_park",
    "plan_wake",
    "parkable",
]

ALLOWED_ROOTS = ("/sys/bus/usb/devices", "/sys/bus/pci/devices")
"""The only directories a device node may sit directly beneath.

Two, not one, because ``pci_runtime`` is schema-valid now and its helper
support lands with the card that proves it. A root added here without a
method that uses it widens the guard for nothing.
"""


class PowerError(Exception):
    """A park or wake could not be planned or performed."""


@dataclass(frozen=True)
class Write:
    """One sysfs file and the value to put in it."""

    path: str
    value: str


@dataclass(frozen=True)
class PowerPlan:
    """The ordered writes a park or wake means, and the consumers to hush."""

    writes: tuple[Write, ...]
    quiet: tuple[QuietVerb, ...]
    restore: bool
    """False on a park (hush the consumer), True on a wake (restore it)."""


@dataclass(frozen=True)
class Parkable:
    """A catalogued device, attached now, that can be parked."""

    name: str
    summary: str
    method: PowerMethod
    quiet: tuple[QuietVerb, ...]
    sysfs_path: str
    identifier: str
    """``vendor:product`` as the bus reported it, so a caller can confirm the
    node still holds the same device before writing to it."""

    parked: bool

    @property
    def address(self) -> str:
        """The bus address alone (``1-4``), which is what distinguishes two
        devices of the same class and so what the operator types."""
        return Path(self.sysfs_path).name


def guard(path: str) -> str:
    """Refuse any path that is not a file inside a device node under an allowed root.

    **The trap this exists for is that a real device node is itself a
    symlink.** ``/sys/bus/usb/devices/1-4`` points into
    ``/sys/devices/pci0000:00/…``, so the obvious containment check --
    ``Path(p).resolve().is_relative_to(root)`` -- refuses every device on the
    machine. Written the other obvious way, without resolving, it accepts
    ``…/devices/../../../etc/shadow``.

    So neither: the *lexical* path is normalised without touching the
    filesystem (``os.path.normpath`` collapses ``..`` textually), and the
    result must sit strictly below one of the roots. What the node is a
    symlink to is then irrelevant, because we never followed it.
    """
    normalised = os.path.normpath(path)
    for root in ALLOWED_ROOTS:
        prefix = root.rstrip("/") + "/"
        if normalised.startswith(prefix) and len(normalised) > len(prefix):
            return normalised
    raise PowerError(
        f"{path!r} is outside the device roots this may write to "
        f"({', '.join(ALLOWED_ROOTS)}). A power-control write goes to a device "
        f"node and nowhere else; refusing before any write, not after."
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return None


def parkable(
    matches: list[Match],
    entries: Mapping[str, DeviceClass | DeviceManifest],
) -> tuple[list[Parkable], list[tuple[str, str]]]:
    """Which matched, attached devices can be parked — and which cannot, with why.

    An **ambiguous** match (D-028) is parkable. D-028 governs giving a device a
    persistent name, where being wrong is silent and permanent; parking is a
    reversible unplug of a device the operator has named, and being wrong is
    immediately visible and undone by ``wake``.

    A device the catalog does not mark parkable is not skipped-with-a-reason;
    it simply is not one, and returning it as a refusal would fill the report
    with every device on the bus.
    """
    found: list[Parkable] = []
    skipped: list[tuple[str, str]] = []
    for match in matches:
        entry = entries.get(match.name)
        if entry is None or entry.power_control is None:
            continue
        if not match.attached.sysfs_path:
            skipped.append(
                (match.name, "no sysfs node recorded for it, so there is nothing to write to")
            )
            continue
        node = Path(match.attached.sysfs_path)
        state = _read(node / "authorized")
        if state is None:
            skipped.append(
                (
                    match.name,
                    f"{node / 'authorized'} could not be read, so whether it is parked "
                    f"is unknown; not every bus exposes it and the device may have "
                    f"been unplugged",
                )
            )
            continue
        found.append(
            Parkable(
                name=match.name,
                summary=entry.summary,
                method=entry.power_control.method,
                quiet=tuple(entry.power_control.quiet),
                sysfs_path=str(node),
                identifier=match.attached.identifier,
                parked=state == "0",
            )
        )
    return found, skipped


def _usb_writes(p: Parkable, *, park: bool) -> tuple[Write, ...]:
    node = Path(p.sysfs_path)
    if park:
        return (
            Write(path=guard(str(node / "authorized")), value="0"),
            Write(path=guard(str(node / "power" / "control")), value="auto"),
        )
    # Waking writes `authorized` alone. Restoring power/control to "on" would
    # undo a runtime-PM setting the operator or a udev rule may own -- the
    # DW5930e on the field laptop has exactly such a rule -- and an authorized
    # device is not suspended in any case.
    return (Write(path=guard(str(node / "authorized")), value="1"),)


def _plan(p: Parkable, *, park: bool) -> PowerPlan:
    if p.method == "pci_runtime":
        raise PowerError(
            f"{p.name!r} declares method 'pci_runtime', which is not implemented. "
            f"It is schema-valid so a wwan-modem class can carry it, and it ships "
            f"refused until a card has proved it here: nothing is shipped that has "
            f"not been run."
        )
    return PowerPlan(writes=_usb_writes(p, park=park), quiet=p.quiet, restore=not park)


def plan_park(p: Parkable) -> PowerPlan:
    """The writes that detach ``p`` and let its port suspend."""
    return _plan(p, park=True)


def plan_wake(p: Parkable) -> PowerPlan:
    """The writes that bring ``p`` back."""
    return _plan(p, park=False)


def _invoking_uid() -> int | None:
    """The user behind ``pkexec``, or None when there is no such user.

    ``PKEXEC_UID`` is set by pkexec and by nothing else, so under ``sudo`` or a
    direct root invocation it is simply absent. That is a normal way to run the
    helper, not an error, and it must never raise: by the time the quiet verbs
    run the hardware write has already happened, which is the worst moment in
    the whole operation to take an exception.
    """
    raw = os.environ.get("PKEXEC_UID")
    if not raw:
        return None
    try:
        uid = int(raw)
    except ValueError:
        return None
    try:
        pwd.getpwuid(uid)
    except KeyError:
        return None
    return uid


def _nm_autoconnect(*, restore: bool, uid: int | None) -> str:
    """Set ``connection.autoconnect`` on the profiles NetworkManager would
    bring up, so a parked device is not woken by an autoconnect a second later.

    Runs as the invoking user where there is one: NetworkManager profiles are
    per-user for a user-owned connection, and doing this as root would edit the
    system's rather than the operator's.
    """
    value = "yes" if restore else "no"
    argv = ["nmcli", "--terse", "--fields", "NAME", "connection", "show"]
    prefix: list[str] = []
    if uid is not None:
        prefix = ["setpriv", "--reuid", str(uid), "--regid", str(uid), "--clear-groups", "--"]
    try:
        listed = subprocess.run(  # noqa: S603 - fixed argv, shell=False
            [*prefix, *argv], capture_output=True, text=True, check=False
        )
    except (FileNotFoundError, PermissionError) as exc:
        return f"networkmanager_autoconnect: could not run nmcli ({exc}); nothing hushed"
    if listed.returncode != 0:
        return (
            f"networkmanager_autoconnect: nmcli exited {listed.returncode}; "
            f"no profile was changed"
        )
    names = [n for n in listed.stdout.splitlines() if n.strip()]
    for name in names:
        subprocess.run(  # noqa: S603 - fixed argv, shell=False
            [*prefix, "nmcli", "connection", "modify", name, "connection.autoconnect", value],
            capture_output=True,
            text=True,
            check=False,
        )
    return f"networkmanager_autoconnect: set autoconnect {value} on {len(names)} profile(s)"


def execute(plan: PowerPlan, *, uid: int | None = None) -> list[str]:
    """Perform the plan. Returns the problems; an empty list is success.

    **The hardware writes come first and the quiet verbs after** (or, on a
    wake, the verbs after too). A verb is a courtesy to a consumer, not a
    precondition of the hardware step, so a machine with no NetworkManager
    still parks its GPS.

    Every write is read back and compared. D-031: ``write_text`` returning a
    byte count is not evidence that a byte reached the device.
    """
    problems: list[str] = []
    for write in plan.writes:
        target = Path(guard(write.path))
        try:
            target.write_text(write.value)
        except OSError as exc:
            problems.append(f"{write.path}: could not write {write.value!r} ({exc})")
            continue
        seen = _read(target)
        if seen != write.value:
            problems.append(
                f"{write.path}: wrote {write.value!r} and read back {seen!r} — "
                f"the write reported success and did not take"
            )
    resolved = _invoking_uid() if uid is None else uid
    for verb in plan.quiet:
        if verb == "networkmanager_autoconnect":
            outcome = _nm_autoconnect(restore=plan.restore, uid=resolved)
            if "could not" in outcome or "exited" in outcome:
                problems.append(outcome)
    return problems
```

In `src/hammunition/hardware/__init__.py`, add to the imports and `__all__`:

```python
from .power import Parkable, PowerError, PowerPlan, Write, execute, guard, parkable, plan_park, plan_wake
```

with `"Parkable"`, `"PowerError"`, `"PowerPlan"`, `"Write"`, `"execute"`, `"guard"`, `"parkable"`, `"plan_park"`, `"plan_wake"` added to `__all__` in the existing sorted order.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_power_control.py -v && python -m mypy src/hammunition/hardware/power.py && python -m ruff check src tests && python -m ruff format --check src tests`
Expected: all pass; mypy clean; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add src/hammunition/hardware/power.py src/hammunition/hardware/__init__.py tests/test_power_control.py
git commit -m "$(cat <<'MSG'
Power control: a parkable device, its writes, and their verified effect

The planner turns a power_control block into ordered sysfs writes and the
executor re-reads each one, because a write that returned a byte count is not
evidence a byte reached the device (D-031).

The path guard is lexical on purpose. A real device node is itself a symlink
into /sys/devices, so resolving the candidate and demanding the result stay
under the bus root refuses every device on the machine; not normalising at all
accepts a traversal. normpath collapses `..` without touching the filesystem,
and we never follow the link.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 4: `hammunition-devctl`, the privileged helper

**Files:**
- Create: `src/hammunition/cli/devctl.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `tests/test_devctl.py` (create)

**Interfaces:**
- Consumes: `parkable`, `plan_park`, `plan_wake`, `execute`, `PowerError` from `hammunition.hardware.power`; `read_usb_bus`, `match_catalog` from `hammunition.hardware.detect`; `load_hardware` from `hammunition.manifest.load`; `find_catalog` from `hammunition.cli.main`.
- Produces: `def main(argv: list[str] | None = None) -> int`; `def resolve(name: str, found: list[Parkable]) -> Parkable`.

**What makes this the security boundary:** it takes a *name* from an unprivileged caller and nothing else. Every path it writes is one it derived itself by re-reading sysfs and the catalog in this process. An argv that named a path would be a way to write anywhere as root.

- [ ] **Step 1: Write the failing test**

Create `tests/test_devctl.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged helper: what it accepts, and everything it refuses.

This is the only code in the project that runs as root on an operator's
desktop at the press of a switch, so its refusals are the feature. It takes a
name and derives every path itself.
"""

from __future__ import annotations

import json

import pytest

from hammunition.cli.devctl import main, resolve
from hammunition.hardware.power import Parkable, PowerError


def _parkable(name: str, address: str, parked: bool = False) -> Parkable:
    return Parkable(
        name=name,
        summary=f"{name} summary",
        method="usb_deauthorize",
        quiet=(),
        sysfs_path=f"/sys/bus/usb/devices/{address}",
        identifier="1546:01a7",
        parked=parked,
    )


def test_resolve_finds_the_only_device_of_that_name() -> None:
    found = [_parkable("gps-receiver", "1-4")]
    assert resolve("gps-receiver", found).address == "1-4"


def test_resolve_refuses_a_name_that_is_not_parkable() -> None:
    with pytest.raises(PowerError, match="not a parkable"):
        resolve("hackrf", [_parkable("gps-receiver", "1-4")])


def test_resolve_names_what_is_parkable_when_it_refuses() -> None:
    with pytest.raises(PowerError, match="gps-receiver"):
        resolve("hackrf", [_parkable("gps-receiver", "1-4")])


def test_resolve_refuses_an_ambiguous_name_naming_both_addresses() -> None:
    """Review Focus 2. Two pucks attached: `park gps-receiver` means either,
    and picking one silently parks the wrong receiver."""
    found = [_parkable("gps-receiver", "1-4"), _parkable("gps-receiver", "1-5")]
    with pytest.raises(PowerError) as caught:
        resolve("gps-receiver", found)
    message = str(caught.value)
    assert "1-4" in message and "1-5" in message


def test_resolve_accepts_an_address_to_disambiguate() -> None:
    found = [_parkable("gps-receiver", "1-4"), _parkable("gps-receiver", "1-5")]
    assert resolve("gps-receiver@1-5", found).address == "1-5"


def test_resolve_refuses_an_address_that_is_not_attached() -> None:
    with pytest.raises(PowerError, match="1-9"):
        resolve("gps-receiver@1-9", [_parkable("gps-receiver", "1-4")])


def test_state_prints_json_a_tray_can_read(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([_parkable("gps-receiver", "1-4", parked=True)], []),
    )
    assert main(["state"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "name": "gps-receiver",
            "summary": "gps-receiver summary",
            "address": "1-4",
            "identifier": "1546:01a7",
            "method": "usb_deauthorize",
            "parked": True,
        }
    ]


def test_state_is_valid_json_when_nothing_is_parkable(capsys, monkeypatch) -> None:
    """The applet parses this on a 5 s timer. An empty survey printing a
    human sentence instead of `[]` is a parse error every five seconds."""
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    assert main(["state"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_state_reports_skipped_devices_on_stderr_not_in_the_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([], [("gps-receiver", "authorized could not be read")]),
    )
    assert main(["state"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "authorized" in captured.err


def test_park_refuses_an_unknown_name_with_exit_2(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey", lambda: ([_parkable("gps-receiver", "1-4")], [])
    )
    assert main(["park", "hackrf"]) == 2
    assert "not a parkable" in capsys.readouterr().err


def test_park_refuses_a_device_whose_node_now_holds_something_else(capsys, monkeypatch) -> None:
    """Review Focus 4. Unplug and replug between `state` and `park` and the
    address can be reused by a different device. The helper re-surveys, so the
    stale name is simply gone -- it must say so, not write to the address."""
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    assert main(["park", "gps-receiver"]) == 2
    assert "not a parkable" in capsys.readouterr().err


def test_an_unknown_verb_is_refused() -> None:
    with pytest.raises(SystemExit):
        main(["incinerate", "gps-receiver"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_devctl.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hammunition.cli.devctl'`

- [ ] **Step 3: Write minimal implementation**

Create `src/hammunition/cli/devctl.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition-devctl`` — the one thing here that runs as root.  D-056.

Three verbs, ``park NAME``, ``wake NAME`` and ``state``, reached through one
polkit action. Every caller -- the CLI, a menu entry, the Plasma applet in
``hammunition-tray`` -- runs *this*, so there is one privileged path to review
rather than three.

**It takes a name and derives everything else itself.** It re-reads the USB
bus and the catalog in this process and computes the paths it writes; an argv
that carried a path would be a way to write anywhere on the system as root,
and an argv that carried a *plan* would be the same thing spelled longer. The
name is the only thing an unprivileged caller supplies, and a name that is not
a parkable attached device is refused before anything happens.

It never reads the operator's station config. Parking a GPS has nothing to do
with a callsign and this process has no business holding one.
"""

from __future__ import annotations

import argparse
import json
import sys

from hammunition.hardware.power import (
    Parkable,
    PowerError,
    execute,
    parkable,
    plan_park,
    plan_wake,
)

__all__ = ["main", "resolve"]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNPLANNABLE = 2


def _survey() -> tuple[list[Parkable], list[tuple[str, str]]]:
    """What is parkable on this machine right now, read fresh from the bus.

    Fresh on every invocation, never cached and never taken from the caller:
    between an applet's poll and the switch being flipped a device can be
    unplugged, and a USB address can be reused by something else entirely.
    """
    from hammunition.cli.main import find_catalog
    from hammunition.hardware.detect import match_catalog, read_usb_bus
    from hammunition.manifest.load import load_hardware

    classes, devices = load_hardware(find_catalog(None) / "hardware")
    entries = {**classes, **devices}
    matches, _ = match_catalog(read_usb_bus(), entries)
    return parkable(matches, entries)


def resolve(name: str, found: list[Parkable]) -> Parkable:
    """The one parkable device ``name`` refers to, or a refusal that says why.

    ``NAME`` or ``NAME@ADDRESS``. Two receivers of the same class are two
    parkable devices with one catalog name between them, and picking one
    silently would park whichever the bus happened to list first -- so an
    ambiguous name is refused with both addresses, and the operator says which.
    """
    wanted, _, address = name.partition("@")
    candidates = [p for p in found if p.name == wanted]
    if address:
        candidates = [p for p in candidates if p.address == address]
        if not candidates:
            raise PowerError(
                f"no parkable device {wanted!r} at address {address!r} is attached. "
                f"Attached: {_listing(found)}"
            )
    if not candidates:
        raise PowerError(
            f"{name!r} is not a parkable attached device. Parkable now: {_listing(found)}"
        )
    if len(candidates) > 1:
        addresses = ", ".join(f"{p.name}@{p.address}" for p in candidates)
        raise PowerError(
            f"{wanted!r} names {len(candidates)} attached devices and would be a "
            f"guess: {addresses}. Name one of those instead."
        )
    return candidates[0]


def _listing(found: list[Parkable]) -> str:
    if not found:
        return "nothing (no catalogued parkable device is attached)"
    return ", ".join(f"{p.name}@{p.address}" for p in sorted(found, key=lambda p: p.address))


def _do(verb: str, name: str) -> int:
    found, skipped = _survey()
    for unit, why in skipped:
        print(f"note: {unit} is not parkable right now: {why}", file=sys.stderr)
    try:
        target = resolve(name, found)
        plan = plan_park(target) if verb == "park" else plan_wake(target)
    except PowerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    problems = execute(plan)
    for problem in problems:
        print(f"unverified: {problem}", file=sys.stderr)
    return EXIT_FAILED if problems else EXIT_OK


def _state() -> int:
    found, skipped = _survey()
    for unit, why in skipped:
        print(f"note: {unit} is not parkable right now: {why}", file=sys.stderr)
    # Always a JSON array, including when it is empty: the applet parses this
    # every five seconds and a human sentence here is a parse error every five
    # seconds.
    print(
        json.dumps(
            [
                {
                    "name": p.name,
                    "summary": p.summary,
                    "address": p.address,
                    "identifier": p.identifier,
                    "method": p.method,
                    "parked": p.parked,
                }
                for p in sorted(found, key=lambda p: (p.name, p.address))
            ]
        )
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hammunition-devctl",
        description=(
            "Park and wake catalogued devices. Runs as root through polkit; "
            "called by `hammunition hardware`, by the generated menu entries, "
            "and by the Plasma applet in hammunition-tray."
        ),
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb, help_text in (
        ("park", "detach a device and let its port suspend"),
        ("wake", "bring a parked device back"),
    ):
        p = sub.add_parser(verb, help=help_text)
        p.add_argument(
            "name",
            metavar="NAME",
            help="catalog name, or NAME@ADDRESS when two of a kind are attached",
        )
    sub.add_parser("state", help="JSON: every parkable attached device and whether it is parked")

    args = parser.parse_args(argv)
    if args.verb == "state":
        return _state()
    verb: str = args.verb
    return _do(verb, args.name)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

In `pyproject.toml`, under `[project.scripts]`:

```toml
[project.scripts]
hammunition = "hammunition.cli.main:main"
# The privileged half, reached through one polkit action (D-056). Separate
# from `hammunition` so the thing pkexec is pointed at is three verbs over
# sysfs, not the whole engine with its installer, its network fetches and its
# station config.
hammunition-devctl = "hammunition.cli.devctl:main"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_devctl.py -v && python -m mypy src/hammunition/cli/devctl.py && python -m ruff check src tests && python -m ruff format --check src tests`
Expected: 12 passed; mypy clean; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add src/hammunition/cli/devctl.py tests/test_devctl.py pyproject.toml
git commit -m "$(cat <<'MSG'
hammunition-devctl: the one privileged path, and what it refuses

Takes a name and derives every path it writes by re-reading the bus and the
catalog in this process. An argv carrying a path would be a way to write
anywhere as root.

Two receivers of one class are two parkable devices with one catalog name
between them, so an ambiguous name is refused with both addresses rather than
parking whichever the bus listed first. `state` is always a JSON array,
including when empty: the applet parses it every five seconds.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 5: `hardware park`, `hardware wake`, `hardware state`

**Files:**
- Modify: `src/hammunition/cli/main.py` (three commands after `cmd_hardware_apply`, three parsers after `p_hw_apply`)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `Command`, `SubprocessRunner` from `hammunition.backends.base`; `EXIT_*` constants; `HELPER_PATH` from `hammunition.hardware.polkit` (Task 6 — until then, define it in Task 5 and import it from `polkit.py` in Task 6; to avoid a forward dependency, **Task 5 defines `HELPER_PATH` in `src/hammunition/hardware/polkit.py` as its first line of code and Task 6 builds the rest of that module around it**).
- Produces: `cmd_hardware_park`, `cmd_hardware_wake`, `cmd_hardware_state`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_hardware_park_refuses_when_the_helper_is_not_installed(capsys, monkeypatch) -> None:
    """Exit 2, naming the missing artefact and the command that installs it.
    A pkexec against a path that does not exist gives the operator an
    authentication prompt followed by 'command not found', which is the worst
    of both."""
    from hammunition.cli import main as cli

    monkeypatch.setattr(cli, "HELPER_PATH", "/nonexistent/hammunition-devctl")
    assert cli.main(["hardware", "park", "gps-receiver"]) == 2
    err = capsys.readouterr().err
    assert "/nonexistent/hammunition-devctl" in err
    assert "hardware apply" in err


def test_hardware_park_prints_the_pkexec_line_and_stops_on_dry_run(
    capsys, monkeypatch, tmp_path
) -> None:
    from hammunition.cli import main as cli

    helper = tmp_path / "hammunition-devctl"
    helper.write_text("#!/bin/sh\n")
    helper.chmod(0o755)
    monkeypatch.setattr(cli, "HELPER_PATH", str(helper))

    class Exploding:
        def run(self, command):  # pragma: no cover - must not be reached
            raise AssertionError("a dry run executed something")

    monkeypatch.setattr(cli, "SubprocessRunner", lambda *a, **k: Exploding())
    assert cli.main(["hardware", "park", "gps-receiver", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "pkexec" in out
    assert str(helper) in out
    assert "Dry run" in out


def test_hardware_park_maps_a_dismissed_prompt_to_exit_3(capsys, monkeypatch, tmp_path) -> None:
    """pkexec exits 126 when the dialog is dismissed. That is a declined
    consent, not a failure: nothing was written and exit 3 says so."""
    from hammunition.backends.base import CommandResult
    from hammunition.cli import main as cli

    helper = tmp_path / "hammunition-devctl"
    helper.write_text("#!/bin/sh\n")
    helper.chmod(0o755)
    monkeypatch.setattr(cli, "HELPER_PATH", str(helper))

    class Dismissing:
        def run(self, command):
            return CommandResult(argv=tuple(command.argv), returncode=126, stdout="", stderr="")

    monkeypatch.setattr(cli, "SubprocessRunner", lambda *a, **k: Dismissing())
    assert cli.main(["hardware", "park", "gps-receiver"]) == 3
    assert "nothing was changed" in capsys.readouterr().err.lower()


def test_hardware_state_needs_no_privilege_and_prints_a_table(capsys, monkeypatch) -> None:
    from hammunition.cli import main as cli

    monkeypatch.setattr(
        cli,
        "_survey_parkables",
        lambda args: (
            [
                type(
                    "P",
                    (),
                    {
                        "name": "gps-receiver",
                        "address": "1-4",
                        "summary": "USB GNSS receivers",
                        "parked": True,
                    },
                )()
            ],
            [],
        ),
    )
    assert cli.main(["hardware", "state"]) == 0
    out = capsys.readouterr().out
    assert "gps-receiver" in out and "parked" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_cli.py -k hardware_park -v`
Expected: FAIL — `AttributeError: module 'hammunition.cli.main' has no attribute 'HELPER_PATH'`

- [ ] **Step 3: Write minimal implementation**

First create `src/hammunition/hardware/polkit.py` with only its constants (Task 6 fills in the rest):

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged artefacts ``hardware apply`` installs for power control. D-056."""

from __future__ import annotations

# Declared whole here although Task 6 supplies the last four names: ruff's
# RUF022 wants one sorted literal, and `__all__ += [...]` later is not one.
__all__ = [
    "ACTION_ID",
    "HELPER_PATH",
    "POLICY_PATH",
    "PolkitArtifacts",
    "plan_polkit",
    "policy_xml",
    "wrapper_script",
]

HELPER_PATH = "/usr/local/libexec/hammunition-devctl"
"""Where pkexec is pointed. A fixed path under the shared prefix, because a
polkit action annotates an absolute executable and a venv's path is not one
an operator's policy file should have to follow across an upgrade."""

ACTION_ID = "com.chiefgyk3d.hammunition.devctl"
POLICY_PATH = f"/usr/share/polkit-1/actions/{ACTION_ID}.policy"
```

Then in `src/hammunition/cli/main.py`, add the import near the other hardware imports at module level:

```python
from hammunition.hardware.polkit import HELPER_PATH
```

and add after `cmd_hardware_apply`:

```python
def _survey_parkables(args: argparse.Namespace) -> tuple[list[Parkable], list[tuple[str, str]]]:
    """What is parkable, read unprivileged. The same survey the helper does.

    Reading sysfs and the catalog needs no privilege; only *writing* does. So
    `hardware state` answers without a prompt, and `park`/`wake` can refuse a
    name before raising an authentication dialog for something that was never
    going to work.
    """
    from hammunition.hardware.detect import match_catalog, read_usb_bus
    from hammunition.hardware.power import parkable

    classes, devices = _load_hardware_catalog(args)
    entries: dict[str, DeviceClass | DeviceManifest] = {**classes, **devices}
    matches, _ = match_catalog(read_usb_bus(), entries)
    return parkable(matches, entries)


def cmd_hardware_state(args: argparse.Namespace) -> int:
    """Which catalogued devices can be parked, and which are parked now."""
    found, skipped = _survey_parkables(args)
    for unit, why in skipped:
        print(f"  {unit}: not parkable right now — {why}")
    if not found:
        print(
            "No parkable device is attached. A device is parkable when its catalog "
            "entry carries a power_control block and it is plugged in now."
        )
        return EXIT_OK
    print(f"{'device':24} {'address':10} {'state':8} summary")
    for p in sorted(found, key=lambda p: (p.name, p.address)):
        print(f"{p.name:24} {p.address:10} {'parked' if p.parked else 'awake':8} {p.summary}")
    print("\n`hammunition hardware park NAME` / `wake NAME`. A reboot wakes everything.")
    return EXIT_OK


def _power_verb(args: argparse.Namespace, verb: str) -> int:
    """Disclose the privileged call and every write it will cause, then run it."""
    from hammunition.hardware.power import PowerError, plan_park, plan_wake

    helper = Path(HELPER_PATH)
    if not helper.is_file():
        print(
            f"error: the privileged helper is not installed at {HELPER_PATH}.\n"
            f"`hammunition hardware apply` installs it, together with the polkit "
            f"action that authorises it.",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE

    found, skipped = _survey_parkables(args)
    for unit, why in skipped:
        print(f"note: {unit} is not parkable right now — {why}", file=sys.stderr)
    from hammunition.cli.devctl import resolve

    try:
        target = resolve(args.name, found)
        plan = plan_park(target) if verb == "park" else plan_wake(target)
    except PowerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE

    command = Command(
        argv=("pkexec", HELPER_PATH, verb, f"{target.name}@{target.address}"),
        description=f"{verb.capitalize()} {target.name} at {target.address}",
    )
    print(f"{verb.capitalize()}ing {target.name} ({target.summary}) at {target.address}\n")
    print("Writes this will cause:")
    for write in plan.writes:
        print(f"  {write.path} <- {write.value}")
    for verb_name in plan.quiet:
        print(f"  {verb_name}: {'restore' if plan.restore else 'hush'} the consumer")
    print(f"\n  # {command.description}\n  $ {command.display()}")

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK

    result = SubprocessRunner().run(command)
    if result.returncode in (126, 127):
        print(
            "The authentication prompt was dismissed; nothing was changed.",
            file=sys.stderr,
        )
        return EXIT_CONSENT
    if result.returncode == EXIT_UNPLANNABLE:
        print(result.stderr.strip() or "the helper refused the request", file=sys.stderr)
        return EXIT_UNPLANNABLE
    if result.returncode != 0:
        print(result.stderr.strip()[:400] or f"helper exited {result.returncode}", file=sys.stderr)
        return EXIT_FAILED
    print(f"\nDone and verified. `hammunition hardware state` shows {target.name} now.")
    return EXIT_OK


def cmd_hardware_park(args: argparse.Namespace) -> int:
    """Detach a device and let its port suspend. Reversed by `wake` or a reboot."""
    return _power_verb(args, "park")


def cmd_hardware_wake(args: argparse.Namespace) -> int:
    """Bring a parked device back."""
    return _power_verb(args, "wake")
```

Add `Parkable` to the `TYPE_CHECKING` imports at the top of `main.py`:

```python
if TYPE_CHECKING:
    from hammunition.hardware.power import Parkable
```

And the parsers, after `p_hw_apply.set_defaults(func=cmd_hardware_apply)`:

```python
    p_hw_state = hardware_sub.add_parser(
        "state", help="which devices can be parked, and which are parked now"
    )
    p_hw_state.set_defaults(func=cmd_hardware_state)

    for verb, helptext in (
        ("park", "detach a device and let its port suspend (D-056)"),
        ("wake", "bring a parked device back"),
    ):
        p_verb = hardware_sub.add_parser(verb, help=helptext)
        p_verb.add_argument(
            "name",
            metavar="NAME",
            help="catalog name, or NAME@ADDRESS when two of a kind are attached",
        )
        p_verb.add_argument(
            "--dry-run",
            action="store_true",
            help="print the privileged call and every write it would cause, then stop",
        )
        p_verb.set_defaults(func=cmd_hardware_park if verb == "park" else cmd_hardware_wake)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_cli.py -v && python -m mypy src && python -m ruff check src tests && python -m ruff format --check src tests`
Expected: all pass; mypy clean; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add src/hammunition/cli/main.py src/hammunition/hardware/polkit.py tests/test_cli.py
git commit -m "$(cat <<'MSG'
CLI: hardware park, wake and state

state needs no privilege, because reading sysfs does not: only writing does.
park and wake resolve the name and print every write before raising an
authentication dialog, so a name that was never going to work is refused
without prompting for a password first.

pkexec's 126 and 127 are a dismissed prompt, which is a declined consent and
not a failure: exit 3, nothing written.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 6: `hardware apply` installs the helper and the policy; `hardware unapply` removes them

**Files:**
- Modify: `src/hammunition/hardware/polkit.py` (the renderers and the plan)
- Modify: `src/hammunition/hardware/apply.py` (`HardwarePlan` gains two fields)
- Modify: `src/hammunition/cli/main.py` (`cmd_hardware_apply`, new `cmd_hardware_unapply`)
- Test: `tests/test_polkit_artifacts.py` (create)

**Interfaces:**
- Produces: `def wrapper_script(interpreter: str) -> str`; `def policy_xml() -> str`; `@dataclass(frozen=True) class PolkitArtifacts` with `helper_path: str`, `helper_content: str`, `policy_path: str`, `policy_content: str`, `helper_current: bool`, `policy_current: bool`; `def plan_polkit(interpreter: str | None = None) -> PolkitArtifacts`.
- Consumes: `HELPER_PATH`, `ACTION_ID`, `POLICY_PATH` from Task 5.

- [ ] **Step 1: Write the failing test**

Create `tests/test_polkit_artifacts.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The two privileged artefacts hardware apply installs, and their removal."""

from __future__ import annotations

import shlex
from xml.etree import ElementTree

from hammunition.hardware.polkit import (
    ACTION_ID,
    HELPER_PATH,
    POLICY_PATH,
    plan_polkit,
    policy_xml,
    wrapper_script,
)


def test_the_policy_is_well_formed_xml() -> None:
    root = ElementTree.fromstring(policy_xml())
    assert root.tag == "policyconfig"


def test_the_policy_declares_exactly_one_action_with_our_id() -> None:
    root = ElementTree.fromstring(policy_xml())
    actions = root.findall("action")
    assert len(actions) == 1
    assert actions[0].get("id") == ACTION_ID


def test_the_policy_prompts_once_then_stays_quiet_for_the_session() -> None:
    root = ElementTree.fromstring(policy_xml())
    defaults = root.find("action/defaults")
    assert defaults is not None
    assert defaults.findtext("allow_active") == "auth_self_keep"
    assert defaults.findtext("allow_inactive") == "auth_admin"
    assert defaults.findtext("allow_any") == "auth_admin"


def test_the_policy_annotates_the_wrapper_path_it_authorises() -> None:
    root = ElementTree.fromstring(policy_xml())
    annotations = {
        a.get("key"): (a.text or "") for a in root.findall("action/annotate")
    }
    assert annotations["org.freedesktop.policykit.exec.path"] == HELPER_PATH
    assert annotations["org.freedesktop.policykit.exec.allow_gui"] == "true"


def test_the_wrapper_execs_the_interpreter_that_owns_the_package() -> None:
    """A venv install's entry point is not on root's PATH, and polkit
    annotates an absolute path. The wrapper is the stable indirection."""
    body = wrapper_script("/opt/hammunition/.venv/bin/python3")
    assert body.startswith("#!/bin/sh\n")
    assert "/opt/hammunition/.venv/bin/python3" in body
    assert "hammunition.cli.devctl" in body
    assert body.rstrip().endswith('"$@"')


def test_the_wrapper_quotes_an_interpreter_path_with_a_space() -> None:
    body = wrapper_script("/home/op/my venv/bin/python3")
    assert shlex.quote("/home/op/my venv/bin/python3") in body


def test_the_plan_names_both_artefacts_at_their_fixed_paths() -> None:
    artefacts = plan_polkit(interpreter="/usr/bin/python3")
    assert artefacts.helper_path == HELPER_PATH
    assert artefacts.policy_path == POLICY_PATH


def test_the_plan_is_a_noop_when_both_files_already_match(tmp_path, monkeypatch) -> None:
    """Idempotence: apply twice and the second run has nothing to do."""
    helper = tmp_path / "hammunition-devctl"
    policy = tmp_path / "action.policy"
    monkeypatch.setattr("hammunition.hardware.polkit.HELPER_PATH", str(helper))
    monkeypatch.setattr("hammunition.hardware.polkit.POLICY_PATH", str(policy))
    helper.write_text(wrapper_script("/usr/bin/python3"))
    policy.write_text(policy_xml())

    artefacts = plan_polkit(interpreter="/usr/bin/python3")
    assert artefacts.helper_current is True
    assert artefacts.policy_current is True


def test_the_plan_is_not_a_noop_when_the_interpreter_moved(tmp_path, monkeypatch) -> None:
    helper = tmp_path / "hammunition-devctl"
    monkeypatch.setattr("hammunition.hardware.polkit.HELPER_PATH", str(helper))
    monkeypatch.setattr("hammunition.hardware.polkit.POLICY_PATH", str(tmp_path / "p.policy"))
    helper.write_text(wrapper_script("/old/venv/bin/python3"))

    assert plan_polkit(interpreter="/new/venv/bin/python3").helper_current is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_polkit_artifacts.py -v`
Expected: FAIL — `ImportError: cannot import name 'plan_polkit'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/hammunition/hardware/polkit.py`:

```python
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

def wrapper_script(interpreter: str) -> str:
    """A three-line shell wrapper that execs the helper's module.

    Needed because polkit annotates an *absolute executable path* and the
    package's own entry point may live in a venv that root's PATH knows
    nothing about, at a path that changes when the engine is reinstalled.
    The wrapper is the fixed thing the policy names; the interpreter inside it
    is rewritten by the next ``apply``.
    """
    return (
        "#!/bin/sh\n"
        "# Installed by `hammunition hardware apply` (D-056). Do not edit: the\n"
        "# polkit action at "
        + POLICY_PATH
        + "\n# authorises this exact path, and the next apply rewrites this file.\n"
        "exec " + shlex.quote(interpreter) + " -m hammunition.cli.devctl \"$@\"\n"
    )


def policy_xml() -> str:
    """One action, authorising one executable. The battery applet's shape.

    ``auth_self_keep`` on an active session: the operator authenticates once
    and the session stays authorised, because a tray switch that asks for a
    password on every flip is a tray switch nobody uses. Inactive and remote
    sessions get ``auth_admin``, because parking someone else's GPS over SSH
    is not a thing a password prompt should make easy.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>Hammunition</vendor>
  <vendor_url>https://github.com/ChiefGyk3D/Hammunition</vendor_url>
  <action id="{ACTION_ID}">
    <description>Park or wake a radio device</description>
    <message>Authentication is required to change a device's power state</message>
    <icon_name>preferences-system-power</icon_name>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_self_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">{HELPER_PATH}</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
"""


@dataclass(frozen=True)
class PolkitArtifacts:
    """The two files power control needs on the machine, and whether they are current."""

    helper_path: str
    helper_content: str
    policy_path: str
    policy_content: str
    helper_current: bool
    policy_current: bool

    @property
    def is_noop(self) -> bool:
        return self.helper_current and self.policy_current


def _current(path: str, content: str) -> bool:
    try:
        return Path(path).read_text() == content
    except (OSError, UnicodeDecodeError):
        return False


def plan_polkit(interpreter: str | None = None) -> PolkitArtifacts:
    """What an apply would install, and whether it is already installed.

    ``interpreter`` defaults to the interpreter running this process, which is
    by construction the one that can import the package.
    """
    python = interpreter or sys.executable
    helper = wrapper_script(python)
    policy = policy_xml()
    return PolkitArtifacts(
        helper_path=HELPER_PATH,
        helper_content=helper,
        policy_path=POLICY_PATH,
        policy_content=policy,
        helper_current=_current(HELPER_PATH, helper),
        policy_current=_current(POLICY_PATH, policy),
    )
```

In `src/hammunition/hardware/apply.py`, add to `HardwarePlan`:

```python
    polkit: PolkitArtifacts
    """The helper wrapper and polkit action power control needs (D-056)."""
```

and adjust `is_noop`:

```python
    @property
    def is_noop(self) -> bool:
        return self.rules_already_current and not self.groups_to_add and self.polkit.is_noop
```

and in `plan_hardware`, compute and pass `polkit=plan_polkit()`, importing it at the top.

In `cmd_hardware_apply`, after the rules commands and before the group loop, add:

```python
    staged_polkit = Path(tempfile.gettempdir()) / "hammunition"
    if not plan.polkit.helper_current:
        print(f"Will install the privileged helper to {plan.polkit.helper_path}")
        commands.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0755",
                    str(staged_polkit / "hammunition-devctl"),
                    plan.polkit.helper_path,
                ),
                description=f"Install the power-control helper to {plan.polkit.helper_path}",
                requires_root=True,
            )
        )
    if not plan.polkit.policy_current:
        print(f"Will install the polkit action to {plan.polkit.policy_path}")
        commands.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    str(staged_polkit / "devctl.policy"),
                    plan.polkit.policy_path,
                ),
                description=(
                    f"Install the polkit action authorising {plan.polkit.helper_path}"
                ),
                requires_root=True,
            )
        )
```

Stage both files beside the udev staging write, verify both by readback in the D-031 block, and append a transaction-log entry after success:

```python
    if not plan.polkit.is_noop:
        TransactionLog(owner=user).append(
            {
                "event": "hardware_artifacts",
                "version": 1,
                "files": [
                    {"path": plan.polkit.helper_path, "mode": "0755"},
                    {"path": plan.polkit.policy_path, "mode": "0644"},
                ],
            }
        )
```

Add `cmd_hardware_unapply` after `cmd_hardware_apply`:

```python
def cmd_hardware_unapply(args: argparse.Namespace) -> int:
    """Remove the privileged artefacts an apply installed, and nothing else.

    Not part of ``uninstall``: that command resolves names against the package
    and profile catalogs and there is no unit named ``hardware`` to give it
    (D-056). This removes exactly what the transaction log records *we* put
    there -- never a path we merely expect to exist, because a file at the
    helper's path that we did not write belongs to whoever did.

    The udev rules file is deliberately left alone. It is declarative, it is
    harmless for a device that is not attached, and removing it would take
    away device access an operator is still using. Power control is the
    reversible part; permissions are not.
    """
    user = operator(args)
    if not user:
        print("error: could not determine whose transaction log to read.", file=sys.stderr)
        return EXIT_FAILED

    recorded: list[str] = []
    for entry in TransactionLog(owner=user).read():
        if entry.get("event") != "hardware_artifacts":
            continue
        for item in entry.get("files", []):
            path = item.get("path")
            if isinstance(path, str) and path not in recorded:
                recorded.append(path)

    if not recorded:
        print(
            "Nothing to remove: the transaction log records no hardware artefacts "
            "installed by Hammunition for this user."
        )
        return EXIT_OK

    present = [p for p in recorded if Path(p).exists()]
    gone = [p for p in recorded if p not in present]
    for path in gone:
        print(f"Already absent: {path}")
    if not present:
        print("Nothing to do: every recorded artefact is already gone.")
        return EXIT_OK

    commands = [
        Command(
            argv=("rm", "-f", path),
            description=f"Remove the power-control artefact at {path}",
            requires_root=True,
        )
        for path in present
    ]
    euid = os.geteuid()
    print(f"\nCommands ({len(commands)}):")
    for command in commands:
        print(f"  # {command.description}")
        print(f"  $ {command.display(euid=euid)}")
    print(
        "\nThe udev rules file is not touched: it is declarative, harmless for a "
        "device that is not attached, and removing it would take away device "
        "access you are still using."
    )

    if args.dry_run:
        print("\nDry run: nothing above was executed.")
        return EXIT_OK
    if not args.yes and not _prompt("\nProceed with the commands above?"):
        print("Aborted. Nothing was changed.")
        return EXIT_OK

    runner = SubprocessRunner()
    print("\nRunning:")
    for command in commands:
        print(f"  $ {command.display(euid=euid)}")
        result = runner.run(command)
        if result.returncode != 0:
            print(f"error: {result.stderr.strip()[:300]}", file=sys.stderr)
            return EXIT_FAILED

    # D-031: `rm` exiting 0 is not evidence the file is gone.
    still_there = [p for p in present if Path(p).exists()]
    if still_there:
        for path in still_there:
            print(f"  unverified: {path} is still present", file=sys.stderr)
        return EXIT_FAILED

    print("\nDone and verified. `hammunition hardware apply` reinstalls them.")
    return EXIT_OK
```

Register the parser beside the others:

```python
    p_hw_unapply = hardware_sub.add_parser(
        "unapply", help="remove the power-control helper and polkit action (D-056)"
    )
    p_hw_unapply.add_argument(
        "--dry-run", action="store_true", help="print what would be removed, then stop"
    )
    p_hw_unapply.add_argument("--yes", action="store_true", help="skip the confirmation")
    p_hw_unapply.add_argument(
        "--user",
        default=None,
        help="operator whose transaction log to read (default: $SUDO_USER, else $USER)",
    )
    p_hw_unapply.set_defaults(func=cmd_hardware_unapply)
```

Add a test to `tests/test_cli.py` pinning the "never a path we did not record" promise:

```python
def test_hardware_unapply_removes_nothing_the_log_does_not_record(capsys, monkeypatch) -> None:
    """A file sitting at the helper's path that we did not write belongs to
    whoever did. An empty log means an empty removal, not a guess."""
    from hammunition.cli import main as cli

    class EmptyLog:
        def __init__(self, **kwargs: object) -> None: ...

        def read(self):
            return iter(())

    monkeypatch.setattr(cli, "TransactionLog", EmptyLog)
    monkeypatch.setattr(cli, "operator", lambda args: "op")
    assert cli.main(["hardware", "unapply"]) == 0
    assert "Nothing to remove" in capsys.readouterr().out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_polkit_artifacts.py tests/test_hardware_apply.py tests/test_cli.py -v && python -m mypy src && python -m ruff check src tests && python -m ruff format --check src tests`
Expected: all pass. `test_hardware_apply.py` constructs `HardwarePlan` — a required new field breaks it, so add `polkit=plan_polkit()` to those constructions in the same commit.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add src/hammunition/hardware/polkit.py src/hammunition/hardware/apply.py src/hammunition/cli/main.py tests/test_polkit_artifacts.py tests/test_hardware_apply.py
git commit -m "$(cat <<'MSG'
hardware apply installs the helper and its polkit action; unapply removes them

Both files are disclosed in the plan, verified by readback, and recorded in
the transaction log. Removal is `hardware unapply` rather than `uninstall`:
uninstall resolves package and profile names against the catalog, and there
is no unit named hardware to give it.

auth_self_keep on an active session, because a tray switch that asks for a
password on every flip is a tray switch nobody uses; auth_admin for inactive
and remote ones.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 7: Two menu entries per parkable attached device

**Files:**
- Modify: `src/hammunition/menus.py` (after `cli_entry_steps`)
- Modify: `src/hammunition/cli/main.py` (`cmd_menus_apply`)
- Test: `tests/test_menus.py` (append)

**Interfaces:**
- Produces: `@dataclass(frozen=True) class DeviceEntry` with `device: str`, `address: str`, `verb: str`, `title: str`, `comment: str`, `categories: tuple[str, ...]`, and `desktop_id` → `hammunition-device-{device}-{verb}.desktop`; `def device_entries(parkables, entries, manifests, hidden) -> tuple[DeviceEntry, ...]`; `def device_entry_steps(entries, applications_dir, icons) -> list[Action]`.

**Two decisions this task locks in:**
- **A separate desktop-id family.** `cli_entry_steps` prunes every `hammunition-cli-*.desktop` this run did not produce. Naming device entries into that family would make them each other's stale files. `hammunition-device-*.desktop` gets its own prune with the same rule.
- **The category comes from the device's first package.** A `DeviceClass` carries no `categories` — that is a package-manifest field. `gps-receiver` declares `packages: [gpsd, gpsd-clients, gpsd-tools]`, and `gpsd-clients` declares `categories: [gps-gnss]`, which is what "beside `cgps`" means in the spec. First package that resolves to a visible category wins; a device whose packages yield none gets no entry, reported.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_menus.py`:

```python
def test_a_parkable_device_gets_a_park_and_a_wake_entry() -> None:
    from hammunition.menus import device_entries

    entries = device_entries(
        parkables=[_parkable_stub("gps-receiver", "1-4", "USB GNSS receivers")],
        entries={"gps-receiver": _device_class_stub(["gpsd-clients"])},
        manifests={"gpsd-clients": _manifest_stub("gpsd-clients", ["gps-gnss"])},
        hidden=frozenset(),
    )
    assert [e.verb for e in entries] == ["park", "wake"]
    assert all(e.categories == ("gps-gnss",) for e in entries)


def test_the_titles_carry_what_the_entry_does_then_the_command() -> None:
    """D-054: a generated entry reads `Title (command)`, because `tlf` told
    an operator nothing about what tlf is."""
    from hammunition.menus import device_entries

    entries = device_entries(
        parkables=[_parkable_stub("gps-receiver", "1-4", "USB GNSS receivers")],
        entries={"gps-receiver": _device_class_stub(["gpsd-clients"])},
        manifests={"gpsd-clients": _manifest_stub("gpsd-clients", ["gps-gnss"])},
        hidden=frozenset(),
    )
    titles = [e.title for e in entries]
    assert titles == [
        "Park GPS receiver (hammunition hardware park gps-receiver)",
        "Wake GPS receiver (hammunition hardware wake gps-receiver)",
    ]


def test_the_desktop_ids_are_their_own_family_not_the_cli_one() -> None:
    """cli_entry_steps prunes every hammunition-cli-*.desktop it did not
    produce this run. Device entries in that family would delete each other."""
    from hammunition.menus import device_entries

    entries = device_entries(
        parkables=[_parkable_stub("gps-receiver", "1-4", "USB GNSS receivers")],
        entries={"gps-receiver": _device_class_stub(["gpsd-clients"])},
        manifests={"gpsd-clients": _manifest_stub("gpsd-clients", ["gps-gnss"])},
        hidden=frozenset(),
    )
    ids = {e.desktop_id for e in entries}
    assert ids == {
        "hammunition-device-gps-receiver-park.desktop",
        "hammunition-device-gps-receiver-wake.desktop",
    }
    assert not any(i.startswith("hammunition-cli-") for i in ids)


def test_two_of_a_kind_get_addressed_entries() -> None:
    from hammunition.menus import device_entries

    entries = device_entries(
        parkables=[
            _parkable_stub("gps-receiver", "1-4", "USB GNSS receivers"),
            _parkable_stub("gps-receiver", "1-5", "USB GNSS receivers"),
        ],
        entries={"gps-receiver": _device_class_stub(["gpsd-clients"])},
        manifests={"gpsd-clients": _manifest_stub("gpsd-clients", ["gps-gnss"])},
        hidden=frozenset(),
    )
    assert len({e.desktop_id for e in entries}) == 4
    assert "gps-receiver@1-5" in [e.exec for e in entries][-1]


def test_a_device_whose_packages_have_no_visible_category_gets_no_entry() -> None:
    from hammunition.menus import device_entries

    assert (
        device_entries(
            parkables=[_parkable_stub("gps-receiver", "1-4", "USB GNSS receivers")],
            entries={"gps-receiver": _device_class_stub(["gpsd-clients"])},
            manifests={"gpsd-clients": _manifest_stub("gpsd-clients", ["gps-gnss"])},
            hidden=frozenset({"gps-gnss"}),
        )
        == ()
    )


def test_stale_device_entries_are_pruned(tmp_path) -> None:
    from hammunition.menus import device_entry_steps

    stale = tmp_path / "hammunition-device-old-receiver-park.desktop"
    stale.write_text("[Desktop Entry]\n")
    steps = device_entry_steps((), tmp_path, None)
    for step in steps:
        step.perform()
    assert not stale.exists()
```

Write the three `_*_stub` helpers at the top of the appended block, using `Parkable` from `hammunition.hardware.power` and the test file's existing manifest-building helper if one exists; otherwise `PackageManifest.model_validate` with the minimum required fields.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_menus.py -k device -v`
Expected: FAIL — `ImportError: cannot import name 'device_entries' from 'hammunition.menus'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/hammunition/menus.py`, modelled closely on `CliEntry`/`cli_entry_steps`:

```python
@dataclass(frozen=True)
class DeviceEntry:
    """A park or wake entry for one attached parkable device.

    Its own desktop-id family, not ``hammunition-cli-*``: that family's prune
    removes every entry the current run did not produce, so a device entry
    living there would be deleted by the next ``menus apply`` as a stale CLI
    entry -- and a park entry is not a CLI entry for a *unit* in any case.
    """

    device: str
    address: str
    verb: str
    title: str
    comment: str
    categories: tuple[str, ...]
    qualified: bool
    """True when two of this device are attached, so the entry must name the
    address; a single device's entry stays typeable."""

    @property
    def target(self) -> str:
        return f"{self.device}@{self.address}" if self.qualified else self.device

    @property
    def exec(self) -> str:
        return f"hammunition hardware {self.verb} {self.target}"

    @property
    def desktop_id(self) -> str:
        suffix = f"-{self.address}" if self.qualified else ""
        return f"hammunition-device-{self.device}{suffix}-{self.verb}.desktop"
```

```python
def _device_categories(
    entry: DeviceClass | DeviceManifest,
    manifests: Mapping[str, PackageManifest],
    hidden: frozenset[str],
) -> tuple[str, ...]:
    """Where a device's entries go: its first package that has a visible category.

    A device class carries no ``categories`` of its own -- that is a package
    field -- so the placement comes from what the device is *for*.
    ``gps-receiver`` declares gpsd, gpsd-clients and gpsd-tools, and
    gpsd-clients is in ``gps-gnss``, which is where ``cgps`` already sits and
    so where somebody looking for their GPS will look.
    """
    for package in entry.packages:
        manifest = manifests.get(package)
        if manifest is None:
            continue
        visible = tuple(c for c in manifest.categories if c not in hidden)
        if visible:
            return visible[:1]
    return ()


def _title_case(summary: str) -> str:
    """The device's summary as a menu title: its first clause, trimmed.

    ``"USB GNSS receivers -- position for APRS and grid squares"`` becomes
    ``"USB GNSS receivers"``. A menu entry is a label, not a sentence.
    """
    head = summary.split(" -- ")[0].split(" \u2014 ")[0].split(",")[0].strip()
    return head[:48].rstrip()


def device_entries(
    parkables: Sequence[Parkable],
    entries: Mapping[str, DeviceClass | DeviceManifest],
    manifests: Mapping[str, PackageManifest],
    hidden: frozenset[str],
) -> tuple[DeviceEntry, ...]:
    """A park entry and a wake entry for each parkable device attached now.

    Attached *now*, because an entry for a device that is not plugged in would
    fail the moment it was clicked, and a menu full of entries that cannot
    work is the unfindable menu D-050 and D-054 were written to fix.
    """
    counts: dict[str, int] = {}
    for p in parkables:
        counts[p.name] = counts.get(p.name, 0) + 1

    built: list[DeviceEntry] = []
    for p in sorted(parkables, key=lambda p: (p.name, p.address)):
        entry = entries.get(p.name)
        if entry is None:
            continue
        categories = _device_categories(entry, manifests, hidden)
        if not categories:
            continue
        label = _title_case(p.summary)
        qualified = counts[p.name] > 1
        for verb in ("park", "wake"):
            candidate = DeviceEntry(
                device=p.name,
                address=p.address,
                verb=verb,
                title="",
                comment=p.summary,
                categories=categories,
                qualified=qualified,
            )
            # D-054: what it does, then the command. `tlf` told an operator
            # nothing; `Park GPS receiver (hammunition hardware park ...)`
            # says what will happen and what to type to repeat it.
            built.append(
                replace(
                    candidate,
                    title=f"{verb.capitalize()} {label} ({candidate.exec})",
                )
            )
    return tuple(built)


def render_device_entry(entry: DeviceEntry, icons: Mapping[str, str] | None = None) -> str:
    markers = ";".join(f"X-Hammunition-{c}" for c in entry.categories)
    keywords = ";".join((*entry.categories, entry.device, entry.verb, "power"))
    icon = next((icons[c] for c in entry.categories if icons and c in icons), None)
    icon_line = f"Icon={icon}\n" if icon else ""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"{icon_line}"
        f"Name={entry.title}\n"
        f"Comment={entry.comment}\n"
        f"Exec={entry.exec}\n"
        "Terminal=true\n"
        f"Categories={markers};\n"
        f"Keywords={keywords};\n"
        f"X-Hammunition-Device={entry.device}\n"
        "X-Hammunition-Generated=device\n"
    )


def device_entry_steps(
    entries: Sequence[DeviceEntry],
    applications_dir: Path,
    icons: Mapping[str, str] | None = None,
) -> list[Action]:
    """Write this run's device entries; prune ours that this run did not produce.

    Same rule as :func:`cli_entry_steps` and a separate family, so the two
    prunes cannot delete each other's entries. A device that is no longer
    attached loses its entries at the next ``menus apply``, which is correct:
    the entry would not have worked.
    """
    wanted = {entry.desktop_id for entry in entries}
    steps = [
        Action(
            kind="menu",
            description=f"Write the {entry.verb} entry for {entry.device} ({entry.address})",
            detail=str(applications_dir / entry.desktop_id),
            perform=partial(
                _write, applications_dir / entry.desktop_id, render_device_entry(entry, icons)
            ),
        )
        for entry in entries
    ]
    for stale in sorted(applications_dir.glob("hammunition-device-*.desktop")):
        if stale.name not in wanted:
            steps.append(
                Action(
                    kind="menu",
                    description=f"Remove a power-control entry no longer applicable: {stale.name}",
                    detail=str(stale),
                    perform=partial(_remove, stale),
                )
            )
    return steps
```

Add `from dataclasses import replace` and `Sequence` to the imports at the top of `menus.py`, and `Parkable` plus `DeviceClass`/`DeviceManifest` under `TYPE_CHECKING`.

In `cmd_menus_apply`, after the `cli_entry_steps` extension:

```python
    classes, devices = _load_hardware_catalog(args)
    hw_entries: dict[str, DeviceClass | DeviceManifest] = {**classes, **devices}
    from hammunition.hardware.detect import match_catalog, read_usb_bus
    from hammunition.hardware.power import parkable as parkable_devices

    hw_matches, _ = match_catalog(read_usb_bus(), hw_entries)
    found, _ = parkable_devices(hw_matches, hw_entries)
    device_generated = device_entries(found, hw_entries, manifests, hidden)
    steps.extend(device_entry_steps(device_generated, applications, vocabulary.icons))
```

and add `{len(device_generated)} power-control entries for parkable devices attached now` to the summary line.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_menus.py tests/test_menu_findability.py tests/test_launchers.py -v && python -m mypy src && python -m ruff check src tests && python -m ruff format --check src tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add src/hammunition/menus.py src/hammunition/cli/main.py tests/test_menus.py
git commit -m "$(cat <<'MSG'
Menus: a park and a wake entry per parkable device attached at apply time

Their own desktop-id family. The CLI family's prune removes every entry the
current run did not produce, so device entries living there would be deleted
by the next apply as stale CLI entries.

The category comes from the device's first package that has one: a device
class carries no categories, and gpsd-clients puts these beside cgps under
gps-gnss, which is where somebody looking for their GPS will look.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 8: The catalog block on `gps-receiver`, and the regenerated page

**Files:**
- Modify: `catalog/hardware/classes/gps-receiver.yaml`
- Modify: `docs/hardware/gps-receiver-class.md` (generated — never hand-edited)
- Test: `tests/test_docs_generated.py` (already asserts regeneration is a no-op)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_power_control.py` (add `REPO_ROOT = Path(__file__).resolve().parent.parent` near the top of the file if it is not already there — the convention at `tests/test_cli.py:25`; a CWD-relative path passes from the repo root and fails from anywhere else):

```python
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
        name
        for name, entry in {**classes, **devices}.items()
        if entry.power_control is not None
    ]
    assert parkables == ["gps-receiver"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_power_control.py -k shipped -v`
Expected: FAIL — `AssertionError: assert None is not None`

- [ ] **Step 3: Write minimal implementation**

In `catalog/hardware/classes/gps-receiver.yaml`, after the `groups:`/`packages:` lines and before `documentation:`:

```yaml
# D-056. The receiver draws power whether or not anything is reading it, and on
# a laptop that matters. Parking it writes 0 to the device's `authorized` and
# lets the port suspend; the kernel drops the interfaces and every consumer
# sees an ordinary unplug. Nothing is persisted: a reboot wakes it again.
power_control:
  method: usb_deauthorize
  quiet: []
  note: >-
    gpsd handles hot-unplug itself — Debian ships USBAUTO="true" in
    /etc/default/gpsd — so nothing needs quieting before the port goes down,
    and the receiver reappears at /dev/gpsN on wake with no action from you.
    `cgps` will report no fix while it is parked, which is what a parked
    receiver looks like from the outside.
```

Then regenerate the page:

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
python scripts/gen_hardware_reference.py
```

If `gen_hardware_reference.py` does not render `power_control`, extend it to emit a "Power control" section from `method` and `note`, and re-run. Confirm `--check` is honoured and writes nothing:

```bash
python scripts/gen_hardware_reference.py --check && git diff --quiet docs/hardware/ && echo "check wrote nothing"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_power_control.py tests/test_docs_generated.py -v && python scripts/check_doc_links.py`
Expected: all pass; the generated page names power control; `--check` is a no-op.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add catalog/hardware/classes/gps-receiver.yaml docs/hardware/gps-receiver-class.md scripts/gen_hardware_reference.py
git commit -m "$(cat <<'MSG'
Catalog: the GPS receiver is parkable, and the page says what that looks like

The one entry this branch marks. gpsd handles hot-unplug itself, so the quiet
list is empty and the note says what the operator will see: cgps reporting no
fix, and /dev/gpsN back on wake.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Task 9: Documentation and D-056

**Files:**
- Create: `docs/hardware/power-control.md`
- Modify: `docs/reference/cli.md` (after the `hardware apply` section; and the exit-code table if `unapply` needs a line)
- Modify: `docs/DECISIONS.md` (D-056)
- Modify: `CLAUDE.md` (one row in the decisions table)

**The feature is not done without this.** CLAUDE.md is explicit: a system modification is documented with what changes, why, how to inspect it, and how to reverse it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_docs_generated.py` (the file already defines `REPO_ROOT` at line 27 — use it, never a CWD-relative path):

```python
def test_the_cli_reference_documents_the_power_verbs() -> None:
    text = (REPO_ROOT / "docs" / "reference" / "cli.md").read_text()
    for verb in ("hardware park", "hardware wake", "hardware state", "hardware unapply"):
        assert verb in text, f"{verb} is undocumented"


def test_the_power_control_page_covers_the_four_required_things() -> None:
    """CLAUDE.md: every system modification says what changes, why, how to
    inspect it afterwards, and how to reverse it."""
    text = (REPO_ROOT / "docs" / "hardware" / "power-control.md").read_text()
    for needle in (
        "/usr/local/libexec/hammunition-devctl",
        "/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy",
        "pkaction",
        "hardware unapply",
        "hammunition-tray",
    ):
        assert needle in text, f"power-control.md does not mention {needle}"


def test_d056_is_recorded() -> None:
    assert "D-056" in (REPO_ROOT / "docs" / "DECISIONS.md").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_docs_generated.py -k "power or d056 or cli_reference" -v`
Expected: FAIL — `FileNotFoundError: docs/hardware/power-control.md`

- [ ] **Step 3: Write minimal implementation**

Write `docs/hardware/power-control.md` covering, in this order: what parking is and what it is not; which devices are parkable and why the catalog decides that rather than a flag; the two files `hardware apply` installs, at their exact paths, with their modes and contents summarised; the three verbs and their exit codes; how to inspect afterwards (`hammunition hardware state`, `lsusb`, `pkaction --action-id com.chiefgyk3d.hammunition.devctl --verbose`, `cat /sys/bus/usb/devices/<addr>/authorized`); how to reverse (`wake`, a reboot, `hammunition hardware unapply`); the **optional** polkit rule that removes the prompt entirely for the active user, written out in full and explicitly never installed by us; and a pointer to `hammunition-tray` for the tray switch.

Add the `hammunition hardware park|wake NAME [--dry-run]`, `hammunition hardware state` and `hammunition hardware unapply` sections to `docs/reference/cli.md` in the style of the neighbouring `hardware apply` section, each naming its exit codes.

Write **D-056** in `docs/DECISIONS.md`: the polkit boundary (a helper rather than `sudo hammunition`, because pkexec authorises an absolute executable and the engine is not a thing to authorise wholesale); why not a D-Bus service yet (three callers, one helper, one action; C is the shape to grow into at a dozen controls); why parked state is not persisted (sysfs is the truth and there is nothing to reconcile); why `pci_runtime` ships refused (nothing ships that has not been run); why the applet is a separate repository (it is a client of the engine, and a non-Hammunition user can be pointed at it); and **why removal is `hardware unapply` and not `uninstall`** (uninstall resolves names against the package and profile catalogs, and there is no unit named hardware).

Add one row to the CLAUDE.md decisions table:

```
| Device power control | `power_control` on the manifest names a method from a fixed enum; one helper behind one polkit action serves the CLI, the menu and the tray; nothing persisted; removal by `hardware unapply` | The catalog can never carry a command, and a reboot is the only reconciliation needed (**D-056**) |
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/chiefgyk3d/src/Hammunition-devctl && python -m pytest tests/test_docs_generated.py -v && python scripts/check_doc_links.py && python -m pytest -q`
Expected: all pass; the link checker validates the new page's markdown links **and its backticked repo paths**.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
git add docs/hardware/power-control.md docs/reference/cli.md docs/DECISIONS.md CLAUDE.md tests/test_docs_generated.py
git commit -m "$(cat <<'MSG'
D-056: the polkit boundary, and the page that says what it does to a machine

What changes, why, how to inspect it and how to reverse it, per CLAUDE.md.
The optional polkit rule that removes the prompt is written out in full and
explicitly never installed by us.

Removal is `hardware unapply` and the decision says why: uninstall resolves
names against the package and profile catalogs, and there is no unit named
hardware to give it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Final gate before the PR

```bash
cd /home/chiefgyk3d/src/Hammunition-devctl
python -m pytest -q 2>&1 | tee /tmp/claude-1000/gate.log; echo "pytest=$?"
python -m mypy 2>&1 | tee -a /tmp/claude-1000/gate.log; echo "mypy=$?"
python -m ruff check src tests scripts && python -m ruff format --check src tests scripts
python scripts/check_doc_links.py
python scripts/audit_gitignore.py
```

Capture to a log and test the exit code; never `gate | grep && push`.

**Not green until CI says so.** Pin reviews and udev rule citations are weekly, not per-PR. This branch changes no pin and no hardware citation, but it does change a hardware manifest, so run `gh workflow run ci.yml --ref device-power-control` and wait for it before calling the branch green.

**Bench verification is a separate step and comes after the merge.** `docs/reference/bench-verification-5430.md` gets its line **only** after park and wake have actually been run against the u-blox receiver on the field laptop. Until then, no claim about hardware behaviour on the field target is a claim.
