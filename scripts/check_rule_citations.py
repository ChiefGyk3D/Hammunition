#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check every citation of a distribution udev rule against the sweep.  D-031.

The gap this fills was stated in a commit message before it was closed: the
commit-claims hook catches a message describing work the commit does not
contain, and **nothing catches reading a column and believing it**. That is how
D-028's amendment came to say `dfu-util` disables `0483:df11` when dfu-util's
rule for that pair is live — a sweep row was read, a conclusion drawn, and the
file never opened.

Most of this catalog's identifiers cite a shipped rules file by name, which
makes the claim checkable against the same measurement the citation came from.
Three checks:

``pair is in that file``
    An identifier citing ``60-gpsd.rules`` must appear in the sweep under a
    package shipping a rules file of that name. Catches a pair attributed to
    the wrong package, and a pair that is not in the rule at all.
``disabled means disabled``
    A ``rejected_ids`` entry whose prose says the distribution disabled the
    rule must correspond to a sweep row with ``enabled=0`` **and a stated
    reason**. This is the exact claim that was wrong, and the exact distinction
    that was already in the data and went unused.
``enabled means enabled``
    Conversely, an identifier carried in ``usb_ids`` on the strength of a rules
    file must not be one the distribution commented out.

Not run when the probe is absent: the sweep output is gitignored measurement, so
a fresh clone has none and this reports that rather than passing silently.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.hardware import DeviceClass, UsbId  # noqa: E402
from hammunition.manifest.load import load_hardware  # noqa: E402

PROBE = REPO_ROOT / "reference" / "probes" / "udev-debian-13.tsv"
HARDWARE = REPO_ROOT / "catalog" / "hardware"

RULES_FILE = re.compile(r"\b([0-9a-z][0-9a-z.+_-]*\.rules)\b")
# Prose asserting the distribution switched the rule off. Deliberately generous:
# a false positive here costs a sentence rewrite, a false negative costs the bug
# this script exists for.
CLAIMS_DISABLED = re.compile(
    r"\bdisabled\b|\bcommented\s+out\b|\bswitched\s+(?:it\s+)?off\b", re.IGNORECASE
)


def load_sweep() -> tuple[dict[tuple[str, str, str], str], dict[tuple[str, str, str], str]]:
    """(rules_file, vendor, product) -> enabled, and -> reason."""
    enabled: dict[tuple[str, str, str], str] = {}
    reason: dict[tuple[str, str, str], str] = {}
    for line in PROBE.read_text(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) < 11:
            continue
        key = (parts[2], parts[3].lower(), parts[4].lower())
        # A pair enabled anywhere wins: a file may carry it live and also show a
        # commented alternative, which is dfu-util's shape exactly.
        if enabled.get(key) != "1":
            enabled[key] = parts[9]
        if parts[10]:
            reason[key] = parts[10]
    return enabled, reason


def cited_files(text: str) -> set[str]:
    return set(RULES_FILE.findall(text))


def check() -> list[str]:
    enabled, reason = load_sweep()
    known_files = {key[0] for key in enabled}
    classes, devices = load_hardware(HARDWARE)
    problems: list[str] = []

    # A pair is `distribution_disabled` only if some file really did comment it
    # out AND said why. Independent of which file the prose names, because the
    # basis is a claim about the archive rather than about one citation — and
    # because this is the exact claim that was wrong.
    disabled_with_reason = {
        (vendor, product)
        for (name, vendor, product), state in enabled.items()
        if state == "0" and reason.get((name, vendor, product))
    }

    def check_basis(where: str, usb: UsbId) -> None:
        if usb.ambiguity is None or usb.ambiguity.basis != "distribution_disabled":
            return
        if (usb.vendor.lower(), (usb.product or "").lower()) not in disabled_with_reason:
            problems.append(
                f"{where}: claims basis distribution_disabled, and no package in "
                f"the archive ships a commented-out rule for {usb} with a stated "
                f"reason. A commented-out rule with no reason is documentation."
            )

    def check_pair(where: str, usb: UsbId, text: str, *, expect_disabled: bool) -> None:
        for name in cited_files(text):
            if name not in known_files:
                # A rules file the sweep never saw: a different distribution, a
                # package not in Debian, or a typo. Reported, not fatal.
                problems.append(
                    f"{where}: cites {name}, which no package in the sweep ships. "
                    f"Either the file name is wrong or it is not in Debian 13."
                )
                continue
            key = (name, usb.vendor.lower(), (usb.product or "").lower())
            if key not in enabled:
                problems.append(
                    f"{where}: cites {name} as the source for {usb}, but that file "
                    f"does not contain that pair. This is the check's whole point — "
                    f"the citation was written from a row, not from the file."
                )
                continue
            live = enabled[key] == "1"
            if expect_disabled and live:
                problems.append(
                    f"{where}: says {name}'s rule for {usb} is disabled, and it is "
                    f"live. dfu-util's 0483:df11 read exactly this way: a live "
                    f'TAG+="uaccess" rule with a commented alternative below it.'
                )
            elif expect_disabled and not reason.get(key):
                problems.append(
                    f"{where}: says {name}'s rule for {usb} is disabled, and it is — "
                    f"with no stated reason. A commented-out rule without a reason is "
                    f"documentation, not a judgement about the identifier."
                )
            elif not expect_disabled and not live:
                problems.append(
                    f"{where}: carries {usb} citing {name}, where the rule is "
                    f"commented out. An identifier a distribution switched off is "
                    f"evidence about the pair, not a supported device."
                )

    for holder in (*classes.values(), *devices.values()):
        kind = "class" if isinstance(holder, DeviceClass) else "device"
        for usb in holder.usb_ids:
            text = usb.evidence + " " + (usb.ambiguity.evidence if usb.ambiguity else "")
            check_pair(f"{kind} {holder.name!r} {usb}", usb, text, expect_disabled=False)
            check_basis(f"{kind} {holder.name!r} {usb}", usb)
        # Firmware-mode identifiers are cited the same way and were not checked
        # in the first draft of this script — which is where the original wrong
        # claim actually lived, in dmr-radio's dfu_usb_id.
        for firmware in holder.firmware:
            if firmware.dfu_usb_id is None:
                continue
            usb = firmware.dfu_usb_id
            text = usb.evidence + " " + (usb.ambiguity.evidence if usb.ambiguity else "")
            check_pair(f"{kind} {holder.name!r} firmware {usb}", usb, text, expect_disabled=False)
            check_basis(f"{kind} {holder.name!r} firmware {usb}", usb)
        for rejected in holder.rejected_ids:
            text = f"{rejected.assumed_to_be} {rejected.why_rejected}"
            if not CLAIMS_DISABLED.search(text):
                continue
            where = f"{kind} {holder.name!r} rejected {rejected}"
            if cited_files(text):
                stand_in = UsbId(
                    vendor=rejected.vendor,
                    product=rejected.product,
                    description=rejected.description,
                    evidence="rejected identifier, checked against the sweep",
                )
                check_pair(where, stand_in, text, expect_disabled=True)
            elif (rejected.vendor.lower(), (rejected.product or "").lower()) not in (
                disabled_with_reason
            ):
                # Prose that says "disabled by Debian" and names no file at all.
                # The first draft of this script checked nothing in that case,
                # which is most of `gps-receiver`'s rejected_ids — a check with a
                # hole exactly where the claims are.
                problems.append(
                    f"{where}: says the distribution disabled this rule and names no "
                    f"file; no package in the archive ships a commented-out rule for "
                    f"{rejected} with a stated reason."
                )
    return problems


def main() -> int:
    if not PROBE.is_file():
        print(
            f"no sweep output at {PROBE.relative_to(REPO_ROOT)} — run "
            f"scripts/run-udev-sweep.sh. Citations are unchecked without it, "
            f"which is a gap and not a pass.",
            file=sys.stderr,
        )
        return 2
    problems = check()
    if problems:
        print("udev rule citations that the sweep does not support:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}\n", file=sys.stderr)
        return 1
    counts: dict[str, int] = defaultdict(int)
    classes, devices = load_hardware(HARDWARE)
    for holder in (*classes.values(), *devices.values()):
        for usb in holder.usb_ids:
            for name in cited_files(usb.evidence):
                counts[name] += 1
    print(
        f"rule citations check: ok — {sum(counts.values())} identifiers cite "
        f"{len(counts)} distribution rules files, every one verified against the sweep"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
