# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turning the hardware catalog into udev rules.  M4, D-028, D-029.

**Permissions are the headline, not symlinks.** CLAUDE.md used to call
persistent symlinks "the highest-value feature" and the accounting in
`docs/reference/device-naming.md` does not support that: systemd's
`60-serial.rules` already gives every USB *serial* device a stable
`/dev/serial/by-id/` path, and it gives nothing to the 12 of 21 catalogued
devices that are `libusb`, nothing to a Proxmark3 that supplies no serial to
compose a path from, and nothing to permissions. So the rule this emits first
and always is the one that decides whether the device works without `sudo`.

Three refusals are built in, and each is a bug this project has already had.

**A `serial_suffix` nobody has checked emits no symlink** (D-028). The field is
tri-state and `null` means unverified. A suffix with nothing to append produces
a broken or nondeterministic name -- the Proxmark3 failure -- and it used to
default to `true`, which armed that for every device added afterwards.

**An unconfirmed identifier is not written into a rule.** A rule built on a
guessed VID:PID silently never matches, and the operator sees a device that
enumerates, works as root, and has no symlink. That is indistinguishable from a
bad cable and there is no error message anywhere in the chain.

**An ambiguous identifier without `match_product` emits no rule at all.** A
generic bridge like `0403:6001` appears in dozens of devices; a rule keyed on it
alone would claim someone else's hardware. `/dev/badge` on a CP2102 taking the
rig cable is exactly the case D-028 was written about.

What is refused is reported rather than skipped: :class:`Omission` carries the
subject, what was not emitted and why, so a device with no rule says so instead
of appearing to be handled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from hammunition.manifest.hardware import DeviceClass, DeviceManifest, UsbId

__all__ = ["Omission", "RuleSet", "rules_file", "rules_for"]

#: Where generated rules go. Numbered below systemd's own 60-* so ours can
#: refine rather than fight, and above the 70-* range distributions use for
#: their own device policy.
RULES_PATH = "/etc/udev/rules.d/65-hammunition.rules"


@dataclass(frozen=True)
class Omission:
    """Something the catalog described and this deliberately did not emit."""

    subject: str
    what: str
    why: str

    def render(self) -> str:
        return f"{self.subject}: {self.what} — {self.why}"


@dataclass
class RuleSet:
    """Rules for one device, and an account of what was left out."""

    subject: str
    lines: list[str] = field(default_factory=list)
    omissions: list[Omission] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.lines


def _product_match(usb_id: UsbId, binding_product: str | None) -> str | None:
    """The product string to match on, or None if this identifier needs none.

    **Only an ambiguous identifier gets one**, and the string comes from the
    identifier itself where the catalog records one. Applying the binding's
    `match_product` to every identifier looks tidier and is wrong: HackRF One
    declares `match_product: "HackRF One"` to separate itself from the HackRF
    Pro on the shared `1d50:6089`, and putting that string on its Jawbreaker
    (`1d50:604b`) and rad1o (`1d50:cc15`) rules — which report `HackRF
    Jawbreaker` and `rad1o` — would make both silently never match.

    That is the exact failure this module exists to avoid, and it was caught by
    reading the generated file rather than by any test, which is why there is
    now a test.
    """
    if usb_id.ambiguity is None:
        return None
    return usb_id.product_string or binding_product


def _match(usb_id: UsbId, binding_product: str | None, binding_serial: str | None) -> str:
    """The match half of a rule, as udev keys."""
    parts = [f'ATTRS{{idVendor}}=="{usb_id.vendor}"']
    if usb_id.product:
        parts.append(f'ATTRS{{idProduct}}=="{usb_id.product}"')
    product = _product_match(usb_id, binding_product)
    if product:
        parts.append(f'ATTRS{{product}}=="{product}"')
    if binding_serial:
        parts.append(f'ATTRS{{serial}}=="{binding_serial}"')
    return ", ".join(parts)


def rules_for(entry: DeviceClass | DeviceManifest) -> RuleSet:
    """Rules for one catalog entry, with everything refused explained."""
    result = RuleSet(subject=entry.name)
    binding = entry.udev
    if binding is None:
        return result

    confirmed = [i for i in entry.usb_ids if i.confirmed]
    if not confirmed:
        result.omissions.append(
            Omission(
                subject=entry.name,
                what="no rule",
                why=(
                    "no confirmed USB identifier. A rule on a guessed pair silently "
                    "never matches, which an operator cannot tell from a bad cable"
                ),
            )
        )
        return result

    # A symlink needs both a decision and evidence for it.
    symlink: str | None = None
    if binding.serial_suffix is None:
        result.omissions.append(
            Omission(
                subject=entry.name,
                what=f"no /dev/{binding.symlink} symlink",
                why=(
                    "serial_suffix is unset, meaning nobody has checked whether this "
                    "device reports a serial. Permissions are still applied"
                ),
            )
        )
    elif binding.serial_suffix:
        if not any(i.reports_serial for i in confirmed):
            result.omissions.append(
                Omission(
                    subject=entry.name,
                    what=f"no /dev/{binding.symlink} symlink",
                    why=(
                        "serial_suffix is true but no confirmed identifier records "
                        "reports_serial, so the suffix would have nothing to append"
                    ),
                )
            )
        else:
            symlink = f"{binding.symlink}-$attr{{serial}}"
    else:
        symlink = binding.symlink

    result.lines.append(f"# {entry.name} — {entry.summary}")
    for usb_id in confirmed:
        if usb_id.ambiguity is not None and not _product_match(usb_id, binding.match_product):
            result.omissions.append(
                Omission(
                    subject=f"{entry.name} {usb_id.vendor}:{usb_id.product}",
                    what="no rule for this identifier",
                    why=(
                        f"ambiguous ({usb_id.ambiguity.basis}) and neither it nor the "
                        f"binding records a product string to disambiguate on, so the "
                        f"rule would claim other hardware too"
                    ),
                )
            )
            continue

        subsystem = "tty" if usb_id.node_kind == "serial" else "usb"
        assignments = [f'MODE="{binding.mode}"', f'GROUP="{binding.group}"']
        if binding.tag_uaccess:
            # The logged-in seat gets access without group membership. Group
            # membership stays as the fallback for headless and non-logind
            # systems, which is why both are emitted rather than one.
            assignments.append('TAG+="uaccess"')
        if symlink:
            assignments.append(f'SYMLINK+="{symlink}"')

        result.lines.append(f"# {usb_id.description}")
        result.lines.append(
            f'SUBSYSTEM=="{subsystem}", '
            + _match(usb_id, binding.match_product, binding.match_serial)
            + ", "
            + ", ".join(assignments)
        )
    if len(result.lines) == 1:  # only the heading survived
        result.lines.clear()
    return result


def rules_file(entries: list[DeviceClass | DeviceManifest]) -> tuple[str, list[Omission]]:
    """The complete rules file, and every omission across every entry."""
    header = [
        "# Generated by Hammunition from catalog/hardware/. Do not edit by hand:",
        "# `hammunition install` rewrites this file, and a hand edit is lost silently.",
        "#",
        "# Permissions first, symlinks only where the catalog has evidence for one.",
        "# A device here that has no symlink is not an oversight — see the project's",
        "# docs/reference/device-naming.md for what nothing solves.",
        "",
    ]
    body: list[str] = []
    omissions: list[Omission] = []
    for entry in sorted(entries, key=lambda e: e.name):
        ruleset = rules_for(entry)
        omissions.extend(ruleset.omissions)
        if not ruleset.is_empty:
            body.extend(ruleset.lines)
            body.append("")
    if not body:
        return "", omissions
    return "\n".join(header + body), omissions
