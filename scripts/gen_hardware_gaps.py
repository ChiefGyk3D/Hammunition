#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/hardware-gaps.md.

Every device in the catalog that cannot yet assert a USB identifier says so in
`identification_gap`, and the schema refuses to let one ship without also
saying **who can close it** (`gap_closure`). This turns those two fields into
the work list.

It exists because the gaps were indistinguishable in prose. Ten entries all
ended in some variant of "run lsusb and record it" — advice that is actionable
for a device on the maintainer's bench, useless for one nobody on the project
owns, and wrong for an entry that will never have a single identifier at all.
Two entries told the reader to attach hardware that does not exist here.

The unconfirmed-identifier section covers a different failure: an id that *is*
recorded but rests on documentation rather than on hardware. `UsbId.confirmed`
is False for those, and a rule built on a wrong pair silently never matches,
which an operator cannot tell from a broken cable.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.hardware import DeviceClass, DeviceManifest, UsbId  # noqa: E402
from hammunition.manifest.load import load_hardware  # noqa: E402

OUT = REPO_ROOT / "docs" / "reference" / "hardware-gaps.md"

HEADING = {
    "maintainer_hardware": (
        "Closable on the maintainer's bench",
        "The hardware is in the kit. One `lsusb` closes each of these and no "
        "contribution is needed — do not solicit one.",
    ),
    "unverified_by_maintainer": (
        "Unverified by the maintainer",
        "Carried because other operators have the device; the maintainer does "
        "not, so the gap cannot be closed here. This is deliberate, not a "
        "backlog — the entries stay and stay honest about why. `lsusb` output "
        "from an owner closes any of them.",
    ),
    "not_applicable": (
        "Not closable, and should not stay on a list",
        "No single identifier exists to record. `lsusb` against one unit would "
        "not close these, so leaving them as open tasks would keep them "
        "permanently open.",
    ),
}
ORDER = ("maintainer_hardware", "unverified_by_maintainer", "not_applicable")

# Curated, like the profile proposals in `gen_profile_sizing.py`: what each gap
# actually blocks, and when. The measured half of this document comes from the
# manifests; this half is judgement and is argued here rather than asserted.
#
# The distinction that matters is between a gap that blocks *shipping something*
# and a gap that blocks *nothing until the udev generator exists* (M4). Most are
# the latter, which is why none of this is urgent today.
BLOCKS: dict[str, tuple[str, str]] = {
    "proxmark3": (
        "Q-010 / M4",
        "The anchor device for the proposed `rfid` profile. The profile can be "
        "decided without it, but cannot claim `supported` for its only "
        "hardware, and the client needs the source backend regardless.",
    ),
    "catsniffer-v3": (
        "M4",
        "Covered by the badgelife class rules in the meantime, which is the "
        "point of having a class. Blocks only a pinned per-device symlink.",
    ),
    "clip-boy": ("M4", "Covered by the badgelife class. Blocks a pinned symlink only."),
    "minino": ("M4", "Covered by the badgelife class. Blocks a pinned symlink only."),
    "free-wili-2": (
        "M4",
        "Not asserted to be USB-serial at all, so the class is a guess rather "
        "than a cover. Worth an early lsusb for that reason alone.",
    ),
    "meshtastic": (
        "M4",
        "Closing it produces new per-board entries rather than an identifier on "
        "this one. Three boards in the kit means three captures.",
    ),
    "limesdr": ("post-1.0", "No SDR in the 1.0 profiles depends on it."),
    "plutosdr": (
        "post-1.0",
        "Its Soapy module is sid-only, so apt cannot install it on a stable "
        "base — the packaging gap blocks this device well before the identifier "
        "does.",
    ),
    "krakensdr": (
        "nothing",
        "Usable now through the confirmed RTL-SDR identifiers. Only a "
        "board-level control rule is missing, and nothing needs one.",
    ),
    "sdrplay-rsp": (
        "M4",
        "The recorded Mirics identifiers work for the open driver. What is "
        "unverified is the vendor-API path, which is post-1.0 anyway.",
    ),
    "uconsole": ("nothing", "Not a USB peripheral; there is nothing to record."),
}


def first_sentence(text: str) -> str:
    flat = " ".join(text.split())
    for end in (". ", "? "):
        if end in flat:
            return flat[: flat.index(end) + 1].strip()
    return flat


def render(classes: dict[str, DeviceClass], devices: dict[str, DeviceManifest]) -> str:
    gapped = [d for d in devices.values() if d.identification_gap]
    lines = [
        "# Hardware identification gaps",
        "",
        "Generated by `scripts/gen_hardware_gaps.py`. Do not edit by hand —",
        "regenerate.",
        "",
        f"**Generated:** {date.today().isoformat()}  ",
        f"**Devices in catalog:** {len(devices)} — "
        f"**{len(devices) - len(gapped)} with a confirmed identifier, "
        f"{len(gapped)} without**",
        "",
        "A device whose USB identifier is guessed produces a udev rule that "
        "silently never matches, which an operator cannot distinguish from a bad "
        "cable. So the catalog refuses to guess, and every gap is recorded here "
        "instead — with the one fact that decides whether it is anyone's work "
        "item: who is in a position to close it.",
        "",
        "## When these actually have to be closed",
        "",
        "Short answer: **none of them today.** The udev generator that would "
        "consume a confirmed identifier is M4 and is not written, so every gap "
        "below is currently inert. What follows is when each one stops being "
        "inert.",
        "",
        "| Device | Closure | Blocks | Until then |",
        "|---|---|---|---|",
    ]
    for device in sorted(gapped, key=lambda d: (ORDER.index(d.gap_closure or ""), d.name)):
        blocks, why = BLOCKS.get(device.name, ("?", "Not assessed."))
        lines.append(f"| `{device.name}` | {device.gap_closure} | **{blocks}** | {why} |")
    lines += [
        "",
        "`nothing` means the device is usable as catalogued and the gap is a "
        "completeness item. `M4` means it blocks a pinned per-device symlink and "
        "nothing sooner. Only one gap blocks a decision rather than an "
        "implementation, and even that one is a claim of support, not the "
        "decision itself.",
        "",
        "| Device | Status | What is missing |",
        "|---|---|---|",
    ]
    for device in sorted(gapped, key=lambda d: (ORDER.index(d.gap_closure or ""), d.name)):
        lines.append(
            f"| `{device.name}` | {device.status} "
            f"| {first_sentence(device.identification_gap or '')} |"
        )
    lines.append("")

    for closure in ORDER:
        members = [d for d in gapped if d.gap_closure == closure]
        if not members:
            continue
        title, blurb = HEADING[closure]
        lines += [f"## {title} — {len(members)}", "", blurb, ""]
        for device in sorted(members, key=lambda d: d.name):
            lines += [
                f"### `{device.name}`",
                "",
                f"{device.summary}",
                "",
                " ".join((device.identification_gap or "").split()),
                "",
            ]

    # Iterated separately rather than over a merged sequence: the two share a
    # base that declares neither `name` nor `usb_ids`, because a class must have
    # at least one identifier and a device may have none. Merging them would
    # widen both to the base and lose exactly that distinction.
    unconfirmed: list[tuple[str, str, UsbId]] = []
    for cls in classes.values():
        unconfirmed += [(f"class `{cls.name}`", str(u), u) for u in cls.usb_ids if not u.confirmed]
    for dev in devices.values():
        unconfirmed += [(f"device `{dev.name}`", str(u), u) for u in dev.usb_ids if not u.confirmed]

    lines += [
        f"## Recorded but unconfirmed identifiers — {len(unconfirmed)}",
        "",
        "These are different from the gaps above: an identifier **is** recorded "
        "and rules are generated from it, but it rests on documentation rather "
        "than on an `lsusb` capture. Each carries its provenance, and confirming "
        "one is a smaller job than filling a gap — the pair either matches "
        "attached hardware or it does not.",
        "",
        "| Where | VID:PID | What it is | Provenance |",
        "|---|---|---|---|",
    ]
    for where, pair, usb in sorted(unconfirmed, key=lambda row: row[1]):
        lines.append(
            f"| {where} | `{pair}` | {usb.description} | {' '.join(usb.evidence.split())} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    classes, devices = load_hardware(REPO_ROOT / "catalog" / "hardware")
    OUT.write_text(render(classes, devices))
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
