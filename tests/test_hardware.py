# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Device catalog tests.  D-020.

The invariant worth testing is the one about evidence. A wrong VID:PID produces
a udev rule that silently never matches, and an operator cannot tell that from a
bad cable — so the schema refuses an identifier with no provenance, and refuses
a device that has neither a confirmed identifier nor an honest statement of what
is unknown.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hammunition.manifest.hardware import (
    DeviceManifest,
    HardwareDocumentation,
    UdevBinding,
    UsbId,
)
from hammunition.manifest.load import CatalogError, load_catalog, load_hardware
from hammunition.manifest.schema import ManifestError

HARDWARE = Path(__file__).resolve().parent.parent / "catalog" / "hardware"

DOCS = HardwareDocumentation(
    what_it_is="A software defined radio receiver used for wideband reception.",
    what_you_can_do_with_it="Receive and decode signals across a wide frequency range.",
    setup_steps="Plug it in, join plugdev, then log out and back in again.",
)


def device(**overrides: object) -> DeviceManifest:
    data: dict[str, object] = {
        "name": "example",
        "summary": "An example device",
        "vendor": "Example Ltd",
        "documentation": DOCS,
    }
    data.update(overrides)
    return DeviceManifest.model_validate(data)


CONFIRMED = UsbId(
    vendor="1d50",
    product="6089",
    description="HackRF One",
    evidence="Debian 13 /lib/udev/rules.d/60-libhackrf0.rules",
)


# ---------------------------------------------------------------------------
# No guessing
# ---------------------------------------------------------------------------


def test_a_device_may_not_be_silent_about_unknown_identifiers() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        device()


def test_stating_the_gap_is_enough() -> None:
    d = device(
        identification_gap="Not verified against hardware; run lsusb and record it.",
        gap_closure="maintainer_hardware",
    )
    assert d.usb_ids == []


def test_a_gap_must_say_who_can_close_it() -> None:
    """A gap nobody can close is a different work item from one lsusb settles.

    Every gap in the catalog once ended in "run lsusb and record it", including
    two devices no one on the project owns. Prose could not carry the
    difference; the field has to.
    """
    with pytest.raises((ManifestError, ValidationError)):
        device(identification_gap="No identifier confirmed against real hardware.")


def test_closure_without_a_gap_is_meaningless() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        device(usb_ids=[CONFIRMED], gap_closure="unverified_by_maintainer")


def test_closure_is_a_closed_set() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        device(
            identification_gap="No identifier confirmed against real hardware.",
            gap_closure="ask_around",
        )


def test_inheriting_a_class_is_enough() -> None:
    assert device(device_class="badgelife").device_class == "badgelife"


def test_usb_id_requires_evidence() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        UsbId(vendor="1d50", product="6089", description="HackRF One", evidence="")


def test_usb_id_rejects_malformed_hex() -> None:
    for vendor, product in (("1D50", "6089"), ("1d5", "6089"), ("1d50", "60890")):
        with pytest.raises((ManifestError, ValidationError)):
            UsbId(
                vendor=vendor,
                product=product,
                description="x",
                evidence="a udev rule shipped by Debian",
            )


def test_confirmed_may_not_contradict_its_own_evidence() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        UsbId(
            vendor="303a",
            product="1001",
            description="ESP32-S3 native USB",
            evidence="unconfirmed; not verified against hardware",
            confirmed=True,
        )


def test_supported_status_requires_a_confirmed_identifier() -> None:
    """D-018: do not claim what has not been tested."""
    with pytest.raises((ManifestError, ValidationError)):
        device(status="supported", identification_gap="Nobody has attached one.")


def test_supported_status_is_allowed_with_evidence() -> None:
    assert device(status="supported", usb_ids=[CONFIRMED]).status == "supported"


# ---------------------------------------------------------------------------
# Persistent naming
# ---------------------------------------------------------------------------


def test_multiple_ids_may_not_share_an_unsuffixed_symlink() -> None:
    """Two attached devices would race for the same /dev name."""
    second = UsbId(
        vendor="1d50",
        product="604b",
        description="HackRF Jawbreaker",
        evidence="Debian 13 /lib/udev/rules.d/60-libhackrf0.rules",
    )
    with pytest.raises((ManifestError, ValidationError)):
        device(
            usb_ids=[CONFIRMED, second],
            udev=UdevBinding(symlink="hackrf", serial_suffix=False),
        )


def test_udev_mode_must_be_octal() -> None:
    for mode in ("660", "0999", "rw-rw----"):
        with pytest.raises((ManifestError, ValidationError)):
            UdevBinding(symlink="thing", mode=mode)


# ---------------------------------------------------------------------------
# The real catalog
# ---------------------------------------------------------------------------


def test_hardware_catalog_loads() -> None:
    classes, devices = load_hardware(HARDWARE)
    assert "badgelife" in classes
    assert {"hackrf-one", "rtl-sdr", "clip-boy", "proxmark3"} <= set(devices)


def test_every_class_reference_resolves() -> None:
    classes, devices = load_hardware(HARDWARE)
    for device_entry in devices.values():
        if device_entry.device_class:
            assert device_entry.device_class in classes


def test_dangling_class_reference_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "orphan.yaml").write_text(
        "kind: device\n"
        "name: orphan\n"
        "summary: references a class that is not there\n"
        "vendor: nobody\n"
        "device_class: does-not-exist\n"
        "documentation:\n"
        "  what_it_is: A device entry used only to exercise validation here.\n"
        "  what_you_can_do_with_it: Nothing; it exists to be rejected by the loader.\n"
        "  setup_steps: There are none, because this device does not exist.\n"
    )
    with pytest.raises(CatalogError) as excinfo:
        load_hardware(tmp_path)
    assert "does-not-exist" in str(excinfo.value)


def test_unconfirmed_identifiers_are_visibly_unconfirmed() -> None:
    """The badgelife ESP32 entry is the honest-gap worked example."""
    classes, _ = load_hardware(HARDWARE)
    esp = [i for i in classes["badgelife"].usb_ids if i.vendor == "303a"]
    assert esp and not esp[0].confirmed
    assert "lsusb" in esp[0].evidence.lower()


def test_devices_without_confirmed_ids_are_not_marked_supported() -> None:
    _, devices = load_hardware(HARDWARE)
    for name, entry in devices.items():
        if entry.status == "supported":
            assert any(i.confirmed for i in entry.usb_ids), (
                f"{name} claims support with no confirmed USB identifier"
            )


def test_the_maintainers_kit_is_represented() -> None:
    """Every device named in CLAUDE.md's hardware context has an entry."""
    _, devices = load_hardware(HARDWARE)
    for name in (
        "hackrf-one",
        "catsniffer-v3",
        "free-wili-2",
        "minino",
        "clip-boy",
        "proxmark3",
        "meshtastic",
        "uconsole",
        "krakensdr",
    ):
        assert name in devices, f"{name} is in the maintainer's kit but has no entry"


def test_every_catalogued_gap_declares_its_closure() -> None:
    """The generated gap report groups by closure, so an unset one hides a device."""
    _, devices = load_hardware(HARDWARE)
    for name, entry in devices.items():
        assert bool(entry.identification_gap) == bool(entry.gap_closure), name


def test_devices_the_maintainer_does_not_own_do_not_ask_for_an_lsusb() -> None:
    """LimeSDR and PlutoSDR are not on the bench; the entries must not imply they are.

    Both once told the reader to attach hardware that does not exist here, which
    reads as a task for the maintainer and is a task for a contributor.
    """
    _, devices = load_hardware(HARDWARE)
    for name in ("limesdr", "plutosdr"):
        assert devices[name].gap_closure == "unverified_by_maintainer", name


def test_every_package_a_device_names_has_a_manifest() -> None:
    """The profile cross-check's blind spot, found by looking for it.

    `load_profiles` catches a profile naming an undefined package. Nothing
    caught a *device* doing it, and 21 were dangling -- the SoapySDR modules,
    the vendor host tools, the Meshtastic clients. A device entry saying
    "these packages make it useful" is the same kind of promise a profile makes.
    """
    packages = load_catalog(HARDWARE.parent / "packages")
    classes, devices = load_hardware(HARDWARE)
    for entry in (*classes.values(), *devices.values()):
        referenced = set(entry.packages)
        for firmware in entry.firmware:
            referenced |= set(firmware.packages)
        missing = sorted(referenced - set(packages))
        assert not missing, f"{entry.name} names packages with no manifest: {missing}"
