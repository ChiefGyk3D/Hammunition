# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What is actually plugged in.  D-020, M4.

**D-020**: profile resolution consults detected hardware, because the catalog
carries twelve per-device SoapySDR modules and a user needs one. Deciding which
one needs knowing what is attached.

Read from **sysfs, not `lsusb`.** Three reasons, in order of weight:

* `lsusb` is `usbutils`, a package that may not be installed, and shelling out
  to a tool to learn something the kernel already published in a file is a
  dependency for nothing.
* Its output format is for people. Parsing it is a screen-scrape that breaks
  when someone's locale or version differs.
* `/sys/bus/usb/devices/` gives the descriptor fields directly and identically
  everywhere, including in a container where `lsusb` may see nothing at all.

**What this is not.** It does not decide anything. It reports what the bus says
and what the catalog recognises, and the caller decides what to do with that.
Detection driving installation automatically would be the wrong shape: an
operator who plugs in a colleague's HackRF has not asked for the SDR profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping

    from hammunition.manifest.hardware import DeviceClass, DeviceManifest

__all__ = ["AttachedDevice", "match_catalog", "read_usb_bus"]

USB_DEVICES = Path("/sys/bus/usb/devices")


@dataclass(frozen=True)
class AttachedDevice:
    """One USB device the kernel is reporting."""

    vendor: str
    product: str
    manufacturer: str | None = None
    product_string: str | None = None
    serial: str | None = None

    @property
    def identifier(self) -> str:
        return f"{self.vendor}:{self.product}"

    def describe(self) -> str:
        name = self.product_string or "(no product string)"
        maker = f"{self.manufacturer} " if self.manufacturer else ""
        return f"{self.identifier}  {maker}{name}"


def _read(path: Path) -> str | None:
    try:
        value = path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return value or None


def read_usb_bus(root: Path | None = None) -> list[AttachedDevice]:
    """Every USB device sysfs reports, deduplicated by identifier and serial.

    An absent or unreadable `/sys/bus/usb/devices` yields an empty list rather
    than raising: a container without USB passthrough is a normal place to run
    this, and it is not an error there.
    """
    base = root or USB_DEVICES
    if not base.is_dir():
        return []

    seen: dict[tuple[str, str, str | None], AttachedDevice] = {}
    for entry in sorted(base.iterdir()):
        vendor = _read(entry / "idVendor")
        product = _read(entry / "idProduct")
        if not vendor or not product:
            # Interfaces and root hubs have no idVendor. Skipping them is what
            # makes this a list of devices rather than of every sysfs node.
            continue
        device = AttachedDevice(
            vendor=vendor.lower(),
            product=product.lower(),
            manufacturer=_read(entry / "manufacturer"),
            product_string=_read(entry / "product"),
            serial=_read(entry / "serial"),
        )
        seen.setdefault((device.vendor, device.product, device.serial), device)
    return list(seen.values())


@dataclass(frozen=True)
class Match:
    """A catalog entry the bus appears to contain."""

    name: str
    attached: AttachedDevice
    ambiguous: bool
    """True when the identifier is one the catalog records as shared. The match
    is a candidate rather than a conclusion, and saying which is the point."""


def _distinctive_product_strings(
    entries: Mapping[str, DeviceClass | DeviceManifest],
) -> set[tuple[str, str, str]]:
    """Which (vendor, product, product_string) triples actually identify one device.

    A product string only resolves an ambiguous identifier if it is not itself
    generic, and the catalog can answer that: **if two entries record the same
    string for the same identifier, the string distinguishes nothing.**

    `303a:1001` is the case that forced this. It is the ESP32-S3's USB-JTAG
    peripheral, shared by 49 LoRa board definitions, and three entries —
    Clip-Boy, Free-WiLi 2 and Minino — record its product string as
    "USB JTAG/serial debug unit", because that is Espressif's default and every
    one of those boards reports it. Treating a match on it as confirmation told
    the operator they had a Clip-Boy when they had a Minino, with no hint that
    two other entries had claimed the same device.
    """
    seen: dict[tuple[str, str, str], int] = {}
    for entry in entries.values():
        for usb_id in entry.usb_ids:
            if usb_id.product_string:
                key = (usb_id.vendor.lower(), usb_id.product or "", usb_id.product_string)
                seen[key] = seen.get(key, 0) + 1
    return {key for key, count in seen.items() if count == 1}


def match_catalog(
    attached: list[AttachedDevice],
    entries: Mapping[str, DeviceClass | DeviceManifest],
) -> tuple[list[Match], list[AttachedDevice]]:
    """Split what is attached into (recognised, unrecognised).

    **A match on an ambiguous identifier is reported as ambiguous, not
    resolved.** `0403:6001` is an FTDI bridge in dozens of products; claiming it
    is the catalog's device because the numbers agree is the same mistake a udev
    rule keyed on it alone would make (D-028). Where the catalog records a
    `product_string` for the identifier and the bus reports one, they are
    compared — that is what turns a candidate into a conclusion.
    """
    distinctive = _distinctive_product_strings(entries)
    matches: list[Match] = []
    claimed: set[int] = set()

    for index, device in enumerate(attached):
        for name, entry in sorted(entries.items()):
            for usb_id in entry.usb_ids:
                if not usb_id.confirmed:
                    continue
                if usb_id.vendor.lower() != device.vendor:
                    continue
                if usb_id.product and usb_id.product.lower() != device.product:
                    continue

                ambiguous = usb_id.ambiguity is not None
                if ambiguous and usb_id.product_string and device.product_string:
                    if usb_id.product_string != device.product_string:
                        continue  # a different product sharing the identifier
                    key = (usb_id.vendor.lower(), usb_id.product or "", usb_id.product_string)
                    if key in distinctive:
                        ambiguous = False

                matches.append(Match(name=name, attached=device, ambiguous=ambiguous))
                claimed.add(index)

    unrecognised = [d for i, d in enumerate(attached) if i not in claimed]
    return matches, unrecognised
