"""Device catalog schema.  D-020.

D-020 says detected hardware drives profile resolution. This is the data that
makes that possible: what a device *is*, how the kernel sees it, what groups and
udev rules it needs, and which packages make it useful.

One invariant the type system enforces, for the same reason ``RemoteArtifact``
requires a checksum: **a USB identifier cannot be asserted without saying where
it came from.** A wrong VID:PID produces a udev rule that silently never
matches, and the operator has no way to tell that from a broken cable. So every
``UsbId`` carries evidence, and a device with no confirmed identifier must say
so in ``identification_gap`` rather than ship a guess.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from .schema import SLUG, ManifestError, Strict

__all__ = [
    "DeviceClass",
    "DeviceManifest",
    "Firmware",
    "UdevBinding",
    "UsbId",
]

HEX4 = re.compile(r"^[0-9a-f]{4}$")
UDEV_MODE = re.compile(r"^0[0-7]{3}$")


class UsbId(Strict):
    """One USB vendor/product pair, with its provenance.

    ``product`` may be None to match every product of a vendor — occasionally
    correct (a vendor with one product line) and usually lazy, so it needs the
    same evidence as anything else.
    """

    vendor: str = Field(description="4 hex digits, lowercase.")
    product: str | None = None
    description: str = Field(min_length=3)
    evidence: str = Field(
        min_length=10,
        description=(
            "Where this identifier came from: a distribution udev rule, an "
            "upstream source file, a URL, or an lsusb capture from real hardware."
        ),
    )
    confirmed: bool = True

    @model_validator(mode="after")
    def _check(self) -> UsbId:
        for value, field in ((self.vendor, "vendor"), (self.product, "product")):
            if value is not None and not HEX4.match(value):
                raise ManifestError(f"USB {field} {value!r} must be 4 lowercase hex digits")
        if self.confirmed and "unconfirmed" in self.evidence.lower():
            raise ManifestError(
                f"USB id {self.vendor}:{self.product} is marked confirmed but its "
                f"evidence says otherwise"
            )
        return self

    def __str__(self) -> str:
        return f"{self.vendor}:{self.product or '*'}"


class UdevBinding(Strict):
    """How the device should appear in /dev.

    The whole point of the hardware role, per CLAUDE.md: a persistent name so
    plug order stops mattering and downstream configuration can reference a
    stable path.
    """

    symlink: str = Field(description="Base name under /dev, e.g. 'catsniffer'.")
    serial_suffix: bool = Field(
        default=True,
        description=(
            "Append the device serial, giving /dev/<symlink>-<serial>. Required "
            "when more than one of the same model may be attached; harmless when "
            "not, and the engine also emits the unsuffixed name when exactly one "
            "device matches."
        ),
    )
    mode: str = "0660"
    group: str = "plugdev"
    tag_uaccess: bool = Field(
        default=True,
        description=(
            'Emit TAG+="uaccess" so the logged-in seat gets access without '
            "group membership. Group membership stays as the fallback for "
            "headless and non-systemd-logind systems."
        ),
    )

    @model_validator(mode="after")
    def _check(self) -> UdevBinding:
        if not SLUG.match(self.symlink):
            raise ManifestError(f"udev symlink {self.symlink!r} must be a lowercase slug")
        if not UDEV_MODE.match(self.mode):
            raise ManifestError(f"udev mode {self.mode!r} must be 4-digit octal, e.g. 0660")
        return self


class Firmware(Strict):
    """Flashing or firmware-management tooling for a device."""

    kind: Literal["dfu", "esptool", "uf2", "bootloader_button", "vendor_tool", "openocd"]
    packages: list[str] = Field(default_factory=list)
    dfu_usb_id: UsbId | None = Field(
        default=None,
        description="Many devices enumerate differently in bootloader mode.",
    )
    note: str = Field(min_length=10)


class HardwareDocumentation(Strict):
    """Required by CLAUDE.md: per-device setup is a documented deliverable."""

    what_it_is: str = Field(min_length=20)
    what_you_can_do_with_it: str = Field(min_length=20)
    setup_steps: str = Field(min_length=20)
    known_problems: str | None = None
    upstream_url: str | None = None


class _DeviceCommon(Strict):
    groups: list[str] = Field(
        default_factory=list,
        description="Group membership required for non-root access.",
    )
    packages: list[str] = Field(
        default_factory=list, description="Catalog packages that make it useful."
    )
    firmware: list[Firmware] = Field(default_factory=list)
    udev: UdevBinding | None = None
    documentation: HardwareDocumentation


class DeviceClass(_DeviceCommon):
    """A family of devices with identical Linux-side needs.

    Written because conference badges are the clearest case: an ESP32-S3 badge,
    a CP210x badge and a CH340 badge differ in silicon and not at all in what
    Linux needs to talk to them. Build the class once and every badge works;
    a specific badge then becomes a worked example rather than a special case.
    """

    kind: Literal["class"] = "class"
    name: str
    summary: str
    usb_ids: list[UsbId] = Field(
        min_length=1, description="Bridge chips and native-USB identifiers."
    )

    @model_validator(mode="after")
    def _check(self) -> DeviceClass:
        if not SLUG.match(self.name):
            raise ManifestError(f"device class name {self.name!r} must be a lowercase slug")
        return self


class DeviceManifest(_DeviceCommon):
    """One physical device."""

    kind: Literal["device"] = "device"
    name: str
    summary: str
    vendor: str
    device_class: str | None = Field(
        default=None, description="Inherits that class's ids, groups, packages and tooling."
    )
    usb_ids: list[UsbId] = Field(default_factory=list)
    identification_gap: str | None = Field(
        default=None,
        description="What is unknown about how this device enumerates, and why.",
    )
    status: Literal["supported", "untested", "planned"] = "untested"

    @model_validator(mode="after")
    def _check(self) -> DeviceManifest:
        if not SLUG.match(self.name):
            raise ManifestError(f"device name {self.name!r} must be a lowercase slug")

        confirmed = [i for i in self.usb_ids if i.confirmed]
        if not confirmed and not self.device_class and not self.identification_gap:
            raise ManifestError(
                f"device {self.name!r} has no confirmed USB identifier, no device_class "
                f"to inherit one from, and no identification_gap explaining what is "
                f"unknown. Guessing a VID:PID produces a udev rule that silently never "
                f"matches, which is indistinguishable from a bad cable."
            )
        if self.udev and self.udev.serial_suffix is False and len(confirmed) > 1:
            raise ManifestError(
                f"device {self.name!r} matches several USB ids but pins an unsuffixed "
                f"symlink; two attached devices would race for the same /dev name"
            )
        if self.status == "supported" and not confirmed and not self.device_class:
            raise ManifestError(
                f"device {self.name!r} claims status 'supported' with no confirmed "
                f"USB identifier — D-018: do not claim what has not been tested"
            )
        return self
