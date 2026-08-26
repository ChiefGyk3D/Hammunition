#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/device-naming.md — the by-id accounting.

This project spent its early hardware work on persistent udev symlinks, on the
stated grounds that plug order should stop mattering. Then a Proxmark3 capture
forced the question the other way round: systemd's `60-serial.rules` already
composes `/dev/serial/by-id/` paths out of the manufacturer, product and serial
descriptor strings, per unit, with no help from anybody. If that covers the
catalog, most of our symlink work is redundant and should be retired.

So this counts rather than argues. Per device, three questions:

1. **Does `/dev/serial/by-id/` give it a stable path?**  Only for `serial`
   interfaces — it is systemd's *serial* rule and nothing else feeds it.
2. **Does this catalog add anything?**  A symlink, permissions, an interface
   map, or an honest note that nothing solves the case.
3. **Where by-id is insufficient, why?**  The interesting column, and the one
   that changed the plan.

The answer the numbers give is not "by-id wins" and not "symlinks win". It is
that stable naming was never the hard part: permissions, libusb devices that
have no `/dev/serial` entry at all, identical units, and unlabelled ports are,
and by-id addresses exactly one of those four.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.hardware import DeviceClass, DeviceManifest, UsbId  # noqa: E402
from hammunition.manifest.load import load_hardware  # noqa: E402

OUT = REPO_ROOT / "docs" / "reference" / "device-naming.md"

# Why by-id does not settle a device, most severe first. Ordered so a device
# reports the strongest reason it is not covered.
REASONS: list[tuple[str, str]] = [
    (
        "no-serial-subsystem",
        "No `/dev/serial/` entry exists. The device is claimed by libusb, or by "
        "a storage/HID class driver, and systemd's serial rule never sees it.",
    ),
    (
        "no-unit-serial",
        "It is a serial device, but supplies no per-unit serial. by-id composes "
        "its path from manufacturer, product and serial, so two of these "
        "collide *there* exactly as they would under a naive symlink.",
    ),
    (
        "unlabelled-ports",
        "One interface presents several ports. by-id hands out a stable path "
        "for each and labels none of them; a stable path to a port you cannot "
        "identify is not an answer.",
    ),
    (
        "unrecorded",
        "Nobody has recorded what kind of interface this is, so the question "
        "cannot be answered yet. Counted as uncovered rather than assumed away.",
    ),
]
REASON_ORDER = [r for r, _ in REASONS]


def reasons_for(ids: list[UsbId]) -> list[str]:
    """Every way by-id fails to settle this device, from its identifiers."""
    found: set[str] = set()
    if not any(i.confirmed for i in ids):
        # No confirmed identifier at all. Not "covered by by-id" — unanswerable,
        # and an unanswered question counts as uncovered rather than as settled.
        return ["unrecorded"]
    for i in ids:
        if not i.confirmed:
            continue
        if i.node_kind is None:
            found.add("unrecorded")
        elif i.node_kind != "serial":
            found.add("no-serial-subsystem")
        elif i.reports_serial is False:
            found.add("no-unit-serial")
        if i.ports > 1 and not i.port_roles:
            found.add("unlabelled-ports")
    return [r for r in REASON_ORDER if r in found]


def by_id_answer(ids: list[UsbId]) -> str:
    confirmed = [i for i in ids if i.confirmed]
    if not confirmed:
        return "unknown"
    serial = [i for i in confirmed if i.node_kind == "serial"]
    if not serial:
        return "no"
    if len(serial) < len(confirmed):
        return "partly"
    return "yes"


def ours_answer(dev: DeviceManifest, cls: DeviceClass | None) -> tuple[str, list[str]]:
    """What this catalog contributes beyond a stable path.

    Counts what a device *inherits* from its class as well as what it declares.
    A badge that gets its groups, flasher and console tooling from `badgelife`
    is no less served for not repeating them, and reading only the device file
    reported two of them as contributing nothing at all.
    """
    adds: list[str] = []
    udev = dev.udev or (cls.udev if cls else None)
    groups = list(dev.groups) + (list(cls.groups) if cls else [])
    packages = list(dev.packages) + (list(cls.packages) if cls else [])
    firmware = list(dev.firmware) + (list(cls.firmware) if cls else [])
    if udev is not None:
        adds.append(f"symlink `/dev/{udev.symlink}`")
    if groups or (udev is not None and udev.tag_uaccess):
        adds.append("access")
    if dev.composite:
        adds.append("interface map")
    if packages:
        adds.append("packages")
    if firmware:
        adds.append("firmware mode")
    if dev.identification_gap:
        adds.append("documented gap")
    return ("yes" if adds else "no"), adds


def main() -> int:
    classes, devices = load_hardware(REPO_ROOT / "catalog" / "hardware")
    rows = []
    for dev in sorted(devices.values(), key=lambda d: d.name):
        ids = list(dev.usb_ids)
        cls = classes.get(dev.device_class) if dev.device_class else None
        if cls is not None:
            ids += list(cls.usb_ids)
        answer = by_id_answer(ids)
        ours, adds = ours_answer(dev, cls)
        rows.append((dev, answer, ours, adds, reasons_for(ids)))

    n = len(rows)
    by_id_yes = sum(1 for r in rows if r[1] == "yes")
    by_id_partly = sum(1 for r in rows if r[1] == "partly")
    by_id_no = sum(1 for r in rows if r[1] == "no")
    by_id_unknown = sum(1 for r in rows if r[1] == "unknown")
    symlinked = [r for r in rows if r[0].udev is not None]
    insufficient = [r for r in rows if r[4]]
    reason_counts = {r: sum(1 for row in rows if r in row[4]) for r, _ in REASONS}
    # The claim the reframe rests on: does any symlink duplicate a by-id path?
    overlap = [r for r in symlinked if r[1] in ("yes", "partly")]

    out: list[str] = []
    w = out.append
    w("<!-- Generated by scripts/gen_device_naming.py. Do not edit by hand. -->")
    w("")
    w("# Device naming: what `/dev/serial/by-id/` covers, and what it does not")
    w("")
    w(f"Generated {date.today().isoformat()} from `catalog/hardware/`. {n} devices.")
    w("")
    w("This project's stated highest-value hardware feature was persistent udev")
    w("symlinks by serial. A Proxmark3 capture put that in doubt, because")
    w("systemd's `60-serial.rules` already composes `/dev/serial/by-id/` paths")
    w("from the descriptor strings, per unit, with no help from us — and if that")
    w("covers the catalog, our symlink work is redundant.")
    w("")
    w("So this is an accounting rather than an argument. Three questions per")
    w("device, and the third column is the one that changed the plan.")
    w("")
    w("## The counts")
    w("")
    w("| | Devices |")
    w("|---|---|")
    w(f"| Get a `/dev/serial/by-id/` path for every confirmed identifier | **{by_id_yes}** |")
    w(f"| Get one for some identifiers and not others | **{by_id_partly}** |")
    w(f"| Get none at all — nothing they present is a serial interface | **{by_id_no}** |")
    w(f"| Not yet recorded either way | **{by_id_unknown}** |")
    w(
        f"| **Where by-id is insufficient for at least one reason** | **{len(insufficient)} of {n}** |"
    )
    w(f"| Carry a udev symlink from this catalog | **{len(symlinked)}** |")
    w(f"| …of which duplicate a path by-id would have given anyway | **{len(overlap)}** |")
    w("")
    if not overlap:
        w("**The last row is the finding.** Every symlink this catalog emits is on a")
        w("device with no `/dev/serial/by-id/` entry at all. The two mechanisms have")
        w("not overlapped once — not by design, which makes it worth stating: the")
        w("symlinks were written for SDRs, and SDRs are libusb devices that systemd's")
        w("serial rule never sees. Nothing here is redundant, and nothing here was")
        w("the main event either.")
    else:
        names = ", ".join(f"`{r[0].name}`" for r in overlap)
        w(f"**{len(overlap)} symlink(s) duplicate a by-id path**: {names}. Each needs")
        w("a reason to exist beyond stability, or should be retired.")
    w("")
    w("## Why by-id is insufficient, by reason")
    w("")
    w("A device can hit more than one, so these do not sum to the row above.")
    w("")
    w("| Reason | Devices | What it means |")
    w("|---|---|---|")
    for code, prose in REASONS:
        w(f"| `{code}` | {reason_counts[code]} | {prose} |")
    w("")
    w("## Per device")
    w("")
    w("`by-id` — does systemd give it a stable path. `Ours` — what this catalog")
    w("adds on top. `Insufficient because` — empty means by-id genuinely settles it")
    w("and we should not be inventing work.")
    w("")
    w("| Device | by-id | Ours | Insufficient because |")
    w("|---|---|---|---|")
    for dev, answer, _ours, adds, why in rows:
        add_s = ", ".join(adds) if adds else "—"
        why_s = ", ".join(f"`{r}`" for r in why) if why else "—"
        w(f"| `{dev.name}` | {answer} | {add_s} | {why_s} |")
    w("")
    w("## What this changes")
    w("")
    w("`by-id` gives a stable path. It does not give:")
    w("")
    w("- **Permissions.** A device only root can open is unusable however stable")
    w("  its path. This is what actually stops people, and by-id does nothing for")
    w("  it. Group membership and `uaccess` tagging are ours.")
    w("- **Non-serial devices.** Every SDR in this catalog, the Ubertooth and the")
    w("  Proxmark in client mode are libusb devices with no `/dev/serial/` entry")
    w("  at all.")
    w("- **Identical units.** A device supplying no per-unit serial collides in")
    w("  by-id exactly as it would under a naive symlink. `/dev/serial/by-path/`")
    w("  separates them and is topology, so it changes when the cable moves.")
    w("- **Knowing which interface is which.** A multi-port device gets a stable")
    w("  path per port and a label on none of them.")
    w("")
    w("So the hardware layer's value is permissions, composite-device mapping,")
    w("firmware-mode identification, and honest documentation of the cases nothing")
    w("solves. Symlinks are one tactic, used where the evidence supports one —")
    w("which, so far, is exactly where by-id cannot reach.")
    w("")
    OUT.write_text("\n".join(out))
    print(
        f"wrote {OUT.relative_to(REPO_ROOT)}: {n} devices, "
        f"{len(insufficient)} where by-id is insufficient, "
        f"{len(symlinked)} symlinks, {len(overlap)} overlapping"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
