# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""udev rule generation, and the three things it refuses to emit.

**Permissions are the headline** (D-029). A rule that grants access is what
decides whether a device works without `sudo`; a symlink is a convenience for
the subset of devices with evidence supporting one. The tests are weighted the
same way.

The refusals each correspond to a bug this project has already had, so they are
asserted rather than trusted:

* an unset `serial_suffix` emits no symlink (**D-028** — the Proxmark3 case,
  and it used to default to `true`, arming it for every device added after);
* an unconfirmed identifier is never written into a rule, because a rule on a
  guessed pair silently never matches;
* an ambiguous identifier with nothing to disambiguate on emits no rule at all.

The `match_product` test is here because the generator got it wrong first: it
applied the binding's product string to every identifier, which would have made
the HackRF One's Jawbreaker and rad1o rules match nothing. That was found by
reading the generated file, which is why it is now a test.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.hardware import rules_file, rules_for  # noqa: E402
from hammunition.manifest.hardware import DeviceManifest  # noqa: E402
from hammunition.manifest.load import load_hardware  # noqa: E402

HARDWARE = REPO_ROOT / "catalog" / "hardware"


@pytest.fixture(scope="module")
def catalog() -> tuple[dict[str, Any], dict[str, Any]]:
    return load_hardware(HARDWARE)


def _device(**overrides: Any) -> DeviceManifest:
    base: dict[str, Any] = {
        "name": "thing",
        "vendor": "Nobody",
        "summary": "A device that exists to be turned into a rule",
        "usb_ids": [
            {
                "vendor": "1d50",
                "product": "6089",
                "description": "The thing",
                "evidence": "lsusb on the maintainer's bench, 2026-08-29",
                "node_kind": "libusb",
            }
        ],
        "udev": {"symlink": "thing", "serial_suffix": False},
        "documentation": {
            "what_it_is": "Stands in for a real device in the hardware catalog.",
            "what_you_can_do_with_it": "Prove the rule generator emits what it should.",
            "setup_steps": "Nothing; it is a fixture and not hardware anyone owns.",
        },
    }
    base.update(overrides)
    return DeviceManifest.model_validate(base)


# ---------------------------------------------------------------------------
# Permissions, which are the point
# ---------------------------------------------------------------------------


def test_a_rule_grants_access_before_it_names_anything() -> None:
    rules = rules_for(_device())
    line = next(x for x in rules.lines if x.startswith("SUBSYSTEM"))
    assert 'MODE="0660"' in line
    assert 'GROUP="plugdev"' in line
    assert 'TAG+="uaccess"' in line, (
        "the logged-in seat should get access without group membership; group "
        "membership stays as the fallback for headless and non-logind systems"
    )


def test_a_serial_device_is_matched_on_tty_not_usb() -> None:
    """A USB-serial adapter's node is a tty. A rule on SUBSYSTEM=="usb" would
    apply to the parent device and not to the node anyone opens."""
    device = _device(
        usb_ids=[
            {
                "vendor": "10c4",
                "product": "ea60",
                "description": "A CP2102 bridge",
                "evidence": "lsusb, 2026-08-29",
                "node_kind": "serial",
            }
        ]
    )
    line = next(x for x in rules_for(device).lines if x.startswith("SUBSYSTEM"))
    assert line.startswith('SUBSYSTEM=="tty"')


# ---------------------------------------------------------------------------
# The three refusals
# ---------------------------------------------------------------------------


def test_an_unset_serial_suffix_emits_no_symlink() -> None:
    """D-028. `null` means nobody checked, and a suffix with nothing to append
    produces a broken or nondeterministic name."""
    device = _device(udev={"symlink": "thing", "serial_suffix": None})
    rules = rules_for(device)
    assert not any("SYMLINK" in line for line in rules.lines)
    assert rules.lines, "permissions should still be applied"
    assert any("nobody has checked" in o.why for o in rules.omissions)


def test_a_claimed_serial_with_no_evidence_cannot_be_written_at_all() -> None:
    """Better than the generator refusing it: the SCHEMA refuses it, so the
    state never reaches a rule. `serial_suffix: true` requires a confirmed
    identifier recording `reports_serial`, because a suffix with nothing to
    append produces a broken or nondeterministic name.

    The generator keeps its own check as belt-and-braces for a manifest built
    in memory rather than loaded, which is how the tests above make theirs.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="reports_serial"):
        _device(udev={"symlink": "thing", "serial_suffix": True})


def test_an_unconfirmed_identifier_never_reaches_a_rule() -> None:
    """A rule on a guessed pair silently never matches, and the operator sees a
    device that enumerates, works as root and has no symlink — which is
    indistinguishable from a bad cable.

    The schema permits an unconfirmed identifier only alongside an
    `identification_gap` saying what is unknown and who could close it. The
    generator then emits nothing for it, which is the second half of the same
    rule.
    """
    device = _device(
        usb_ids=[
            {
                "vendor": "dead",
                "product": "beef",
                "description": "A pair somebody read in a forum post",
                "evidence": "documentation only; no hardware was attached",
                "confirmed": False,
            }
        ],
        identification_gap="the USB identifier this device actually presents",
        gap_closure="unverified_by_maintainer",
    )
    rules = rules_for(device)
    assert not rules.lines
    assert any("no confirmed USB identifier" in o.why for o in rules.omissions)


def test_a_symlink_cannot_be_pinned_to_an_ambiguous_identifier() -> None:
    """The schema refuses this outright, which is stronger than the generator
    refusing it. `/dev/badge` on a CP2102 claiming the rig cable is the case
    D-028 was written about."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="do not identify a device"):
        _device(
            usb_ids=[
                {
                    "vendor": "0403",
                    "product": "6001",
                    "description": "An FTDI bridge, used by everything",
                    "evidence": "archive udev sweep, 2026-08-28",
                    "ambiguity": {
                        "basis": "vendor_chip_default",
                        "evidence": "appears in archive udev rules for unrelated devices",
                        "also_used_by": ["a rig cable", "a programmer"],
                    },
                }
            ]
        )


def test_an_ambiguous_identifier_with_nothing_to_narrow_on_emits_no_rule() -> None:
    """With no symlink asked for the schema allows it, and the generator is
    what declines to write a rule that would claim other hardware."""
    device = _device(
        udev=None,
        usb_ids=[
            {
                "vendor": "0403",
                "product": "6001",
                "description": "An FTDI bridge, used by everything",
                "evidence": "archive udev sweep, 2026-08-28",
                "ambiguity": {
                    "basis": "vendor_chip_default",
                    "evidence": "appears in archive udev rules for unrelated devices",
                    "also_used_by": ["a rig cable", "a programmer"],
                },
            }
        ],
    )
    # No binding at all means no rules and nothing to explain: the device is
    # documented, not wired up. That is a legitimate state and most of the
    # hardware catalog is in it.
    assert not rules_for(device).lines


# ---------------------------------------------------------------------------
# The bug that reading the output caught
# ---------------------------------------------------------------------------


def test_a_product_string_is_applied_only_where_it_disambiguates(
    catalog: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """HackRF One declares `match_product: "HackRF One"` to separate itself
    from the HackRF Pro on the shared 1d50:6089. Applying that to its
    Jawbreaker (604b) and rad1o (cc15) identifiers -- which report `HackRF
    Jawbreaker` and `rad1o` -- would make both rules silently never match.

    The first version of the generator did exactly that.
    """
    _classes, devices = catalog
    lines = [x for x in rules_for(devices["hackrf-one"]).lines if x.startswith("SUBSYSTEM")]
    shared = next(x for x in lines if '"6089"' in x)
    jawbreaker = next(x for x in lines if '"604b"' in x)
    rad1o = next(x for x in lines if '"cc15"' in x)

    assert 'ATTRS{product}=="HackRF One"' in shared, "the ambiguous id must be narrowed"
    assert "ATTRS{product}" not in jawbreaker, "an unambiguous id must not be narrowed"
    assert "ATTRS{product}" not in rad1o


def test_two_devices_sharing_an_identifier_get_different_rules(
    catalog: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """HackRF One and HackRF Pro both use 1d50:6089 and must not collide."""
    _classes, devices = catalog
    one = next(x for x in rules_for(devices["hackrf-one"]).lines if '"6089"' in x)
    pro = next(x for x in rules_for(devices["hackrf-pro"]).lines if '"6089"' in x)
    assert one != pro
    assert 'ATTRS{product}=="HackRF One"' in one
    assert 'ATTRS{product}=="HackRF Pro"' in pro
    assert 'SYMLINK+="hackrf-$attr{serial}"' in one
    assert 'SYMLINK+="hackrf-pro-$attr{serial}"' in pro


# ---------------------------------------------------------------------------
# Against the real catalog
# ---------------------------------------------------------------------------


def test_the_real_catalog_produces_rules_and_explains_every_gap(
    catalog: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    classes, devices = catalog
    text, omissions = rules_file(list(classes.values()) + list(devices.values()))
    assert text, "the hardware catalog produced no rules at all"
    assert 'TAG+="uaccess"' in text

    # Every entry that declares a udev binding either appears in the file or is
    # named in an omission. Silence about a device is the thing to prevent.
    named = {o.subject.split()[0] for o in omissions}
    for name, entry in {**classes, **devices}.items():
        if entry.udev is None:
            continue
        assert f"# {name} —" in text or name in named, f"{name} was neither emitted nor explained"


def test_no_rule_carries_an_unsubstituted_placeholder(
    catalog: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """`$attr{serial}` is udev's own syntax and is expected. A stray Python
    format field is not, and would produce a rule that never matches."""
    classes, devices = catalog
    text, _ = rules_file(list(classes.values()) + list(devices.values()))
    assert "{}" not in text
    for line in text.splitlines():
        if line.startswith("SUBSYSTEM"):
            assert "None" not in line, f"a None leaked into a rule: {line}"


# ---------------------------------------------------------------------------
# Detection — what is actually plugged in
# ---------------------------------------------------------------------------


def test_sysfs_is_read_rather_than_lsusb(tmp_path: Path) -> None:
    """`lsusb` is a package that may not be installed, its output is formatted
    for people, and a container may see nothing through it. sysfs gives the
    descriptor fields directly and identically everywhere."""
    from hammunition.hardware import read_usb_bus

    bus = tmp_path / "devices"
    device = bus / "1-2"
    device.mkdir(parents=True)
    (device / "idVendor").write_text("1D50\n")
    (device / "idProduct").write_text("6089\n")
    (device / "product").write_text("HackRF One\n")
    (device / "serial").write_text("0000abcd\n")
    # An interface directory, which has no idVendor and must be skipped.
    (bus / "1-2:1.0").mkdir()

    found = read_usb_bus(bus)
    assert len(found) == 1, "an interface directory was counted as a device"
    assert found[0].vendor == "1d50", "identifiers are normalised to lowercase"
    assert found[0].product_string == "HackRF One"
    assert found[0].serial == "0000abcd"


def test_an_absent_usb_tree_is_not_an_error(tmp_path: Path) -> None:
    """A container without USB passthrough is a normal place to run this."""
    from hammunition.hardware import read_usb_bus

    assert read_usb_bus(tmp_path / "nothing here") == []


def test_a_generic_product_string_does_not_resolve_ambiguity(
    catalog: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The bug this caught on real hardware.

    `303a:1001` is the ESP32-S3's USB-JTAG peripheral, shared by 49 LoRa board
    definitions. Clip-Boy, Free-WiLi 2 and Minino all record its product string
    as "USB JTAG/serial debug unit", because that is Espressif's default and
    every one of those boards reports it. The matcher treated a match on it as
    confirmation, so plugging in a Minino reported an unambiguous Clip-Boy —
    while two other entries had silently claimed the same device.

    A product string resolves an identifier only if the catalog shows it
    belongs to exactly one entry.
    """
    from hammunition.hardware import AttachedDevice, match_catalog

    classes, devices = catalog
    espressif = AttachedDevice(
        vendor="303a", product="1001", product_string="USB JTAG/serial debug unit"
    )
    matches, _unknown = match_catalog([espressif], {**classes, **devices})

    assert len(matches) > 1, "this identifier is shared; the fixture assumes several claim it"
    assert all(m.ambiguous for m in matches), (
        "every claim on a shared identifier with a generic product string must "
        f"stay a candidate: {[(m.name, m.ambiguous) for m in matches]}"
    )


def test_a_distinctive_product_string_does_resolve_ambiguity(
    catalog: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The other half: HackRF One and Pro share 1d50:6089 and report different
    product strings, so the string genuinely tells them apart."""
    from hammunition.hardware import AttachedDevice, match_catalog

    classes, devices = catalog
    pro = AttachedDevice(vendor="1d50", product="6089", product_string="HackRF Pro")
    matches, _unknown = match_catalog([pro], {**classes, **devices})

    resolved = [m for m in matches if not m.ambiguous]
    assert [m.name for m in resolved] == ["hackrf-pro"], (
        f"the product string should have picked exactly one entry: {matches}"
    )


def test_unrecognised_devices_are_reported_rather_than_dropped(
    catalog: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Most of what is on a bus is a hub, a keyboard or a webcam. Saying so is
    better than an empty answer that looks like a failed scan."""
    from hammunition.hardware import AttachedDevice, match_catalog

    classes, devices = catalog
    keyboard = AttachedDevice(vendor="046d", product="c53a", product_string="USB Receiver")
    matches, unknown = match_catalog([keyboard], {**classes, **devices})
    assert not matches
    assert unknown == [keyboard]
