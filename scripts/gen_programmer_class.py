#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate catalog/hardware/classes/programmer.yaml from the archive sweep.

The first *device* file in this catalog that is generated rather than written,
and the reason is arithmetic: five Debian packages — `openocd`, `avrdude`,
`flashrom`, `stlink-tools`, `openfpgaloader` — ship rules naming **180 distinct
identifiers**. Hand-transcribing 180 evidence strings is not careful work, it is
a long opportunity to make the mistakes this project keeps writing checks for,
and every fact needed is already in a measurement.

`catalog/hardware/ambiguous-ids.yaml` set the precedent inside `catalog/`. The
architectural invariant is that the catalog is *data with no executable logic*,
which a generated file satisfies exactly as well as a typed one.

Two things are derived rather than assumed:

``node_kind``
    From the rule's own ``SUBSYSTEM``. ``tty`` is a serial port; ``usb`` is the
    bus device a libusb program opens. This is the same reasoning the DMR class
    used by hand, applied 180 times by the thing that can do it consistently.
    A rule that names no subsystem yields no ``node_kind``, because the honest
    answer is that nobody has recorded it.
``ambiguity``
    From the generated ambiguity dataset, so the class agrees with it by
    construction. The loader cross-checks the two, and a class this size would
    otherwise be a standing source of that failure.

    **Run this after** ``scripts/gen_usb_ambiguity.py``. It reads that script's
    output, so running them the other way round produces a class that disagrees
    with the list — which the loader refuses, loudly, rather than shipping.

**No symlink, and not a close call.** These identifiers are the most heavily
shared in the archive. Two of them are claimed by `libhamlib4t64` — the ham
radio CAT control library — and those are the *only two* identifiers hamlib
claims: `0403:6001` and `16c0:05dc`. A programmer rule and a rig-control cable
are the same USB device as far as the kernel is concerned. That is D-029's
argument arriving in this project's own domain: what this layer is doing here is
granting access, and access is precisely the thing that cannot be given to one
device without giving it to the other.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402


class Hex(str):
    """A USB identifier, always emitted quoted.

    `yaml.safe_dump` writes the string "204f" bare and "2103" quoted, which is
    correct in both cases and fragile in a third: a pair like `1e50` is
    scientific notation in YAML 1.1 and would come back as a float. Quoting
    every one costs nothing and removes the class of bug entirely.
    """


yaml.add_representer(
    Hex,
    lambda dumper, data: dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'"),
    Dumper=yaml.SafeDumper,
)

PROBE = REPO_ROOT / "reference" / "probes" / "udev-debian-13.tsv"
AMBIGUITY = REPO_ROOT / "catalog" / "hardware" / "ambiguous-ids.yaml"
OUT = REPO_ROOT / "catalog" / "hardware" / "classes" / "programmer.yaml"

PACKAGES = ("avrdude", "flashrom", "openfpgaloader", "openocd", "stlink-tools")

# Debian package -> the catalog package manifest that installs it.
CATALOG_PACKAGES = ["avrdude", "flashrom", "openfpgaloader", "openocd", "stlink-tools"]

SUBSYSTEM_TO_NODE = {"tty": "serial", "usb": "libusb", "hidraw": "hid", "block": "storage"}

BASIS_PROSE = {
    "distribution_disabled": (
        "A distribution ships a rule for this pair and commented it out, saying "
        "why. The strongest evidence in the dataset."
    ),
    "kernel_generic_driver": (
        "Debian 13's modules.alias binds this pair to a general-purpose "
        "USB-serial bridge driver, which is the kernel maintainers stating that "
        "it names silicon rather than a product."
    ),
    "shared_across_products": (
        "Two or more packages in the Debian archive name this pair as different "
        "devices, or two or more upstream board definitions claim it."
    ),
    "vendor_chip_default": (
        "A documented chip-level constant, shared by every board using that silicon."
    ),
    "generic_function_name": ("usb.ids names a function rather than a product for this pair."),
}


def load_sweep() -> list[list[str]]:
    rows = []
    for line in PROBE.read_text(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 12 and parts[9] == "1":
            rows.append(parts)
    return rows


def clean(text: str) -> str:
    return " ".join(text.split()).strip()


def main() -> int:
    if not PROBE.is_file():
        print("no udev sweep output; run scripts/run-udev-sweep.sh", file=sys.stderr)
        return 1
    rows = load_sweep()
    if not rows:
        print(f"{PROBE} has no parseable rows — re-run the sweep", file=sys.stderr)
        return 1

    flagged = {
        entry["id"]: entry["basis"]
        for entry in (yaml.safe_load(AMBIGUITY.read_text()) or {}).get("identifiers", [])
    }

    packages_of: dict[tuple[str, str], set[str]] = defaultdict(set)
    files_of: dict[tuple[str, str], set[str]] = defaultdict(set)
    names_of: dict[tuple[str, str], set[str]] = defaultdict(set)
    usbids_of: dict[tuple[str, str], str] = {}
    subsystems: dict[tuple[str, str], set[str]] = defaultdict(set)
    # Everything OUTSIDE the five, so the entry can say who else claims a pair.
    elsewhere: dict[tuple[str, str], set[str]] = defaultdict(set)

    for package, _section, rules, vendor, product, _link, comment, _vn, pn, _e, _r, sub in rows:
        key = (vendor.lower(), product.lower())
        if package in PACKAGES:
            packages_of[key].add(package)
            files_of[key].add(rules)
            if comment and not comment.startswith("http"):
                names_of[key].add(clean(comment))
            if pn:
                usbids_of[key] = pn
            if sub:
                subsystems[key].add(sub)
        else:
            elsewhere[key].add(package)

    entries: list[dict[str, object]] = []
    for key in sorted(packages_of):
        vendor, product = key
        pair = f"{vendor}:{product}"
        owners = sorted(packages_of[key])
        name = sorted(names_of[key])[0] if names_of[key] else usbids_of.get(key, "")
        description = name or f"Programmer or debug probe claimed by {', '.join(owners)}"

        evidence = [f"Debian 13 {', '.join(sorted(files_of[key]))}, from {' and '.join(owners)}."]
        if names_of[key]:
            evidence.append("Rule comment: " + "; ".join(sorted(names_of[key])) + ".")
        if usbids_of.get(key):
            evidence.append(f'usb.ids names the pair "{usbids_of[key]}".')
        others = sorted(elsewhere.get(key, ()))
        if others:
            evidence.append(f"Also claimed outside this class by {', '.join(others)}.")

        entry: dict[str, object] = {
            "vendor": Hex(vendor),
            "product": Hex(product),
            "description": description[:200],
            "evidence": " ".join(evidence),
            "confirmed": True,
        }
        kinds = {SUBSYSTEM_TO_NODE[s] for s in subsystems[key] if s in SUBSYSTEM_TO_NODE}
        if len(kinds) == 1:
            entry["node_kind"] = kinds.pop()

        basis = flagged.get(pair)
        if basis:
            also = [f"claimed by {p}" for p in owners]
            also += [f"claimed by {p}" for p in others]
            entry["ambiguity"] = {
                "basis": basis,
                "evidence": (
                    f"{BASIS_PROSE[basis]} Carried here on the generated list's "
                    f"verdict rather than a separate judgement, so this class and "
                    f"catalog/hardware/ambiguous-ids.yaml cannot disagree."
                ),
                "also_used_by": also,
            }
        entries.append(entry)

    shared_out = sum(1 for k in packages_of if elsewhere.get(k))
    hamlib = sorted(
        f"{v}:{p}"
        for (v, p) in packages_of
        if any(pkg.startswith("libhamlib") for pkg in elsewhere.get((v, p), ()))
    )

    doc = {
        "kind": "class",
        "name": "programmer",
        "summary": ("In-circuit programmers and debug probes — JTAG, SWD, SPI flash, AVR and FPGA"),
        "usb_ids": entries,
        "groups": ["plugdev", "dialout"],
        "packages": CATALOG_PACKAGES,
        "documentation": {
            "what_it_is": (
                "The adapters that talk to a chip rather than to a computer: JTAG "
                "and SWD debug probes, SPI flash clips, AVR programmers and FPGA "
                "loaders. One class because their Linux-side need is identical — "
                "unprivileged access to a USB device — and because the five Debian "
                "packages that drive them name overlapping sets of the same "
                "hardware."
            ),
            "what_you_can_do_with_it": (
                "Read and write the firmware of a microcontroller, dump or reflash "
                "an SPI ROM, load a bitstream into an FPGA, and single-step code on "
                "a target board. In this catalog's terms that is device tooling and "
                "not a capability claim (D-026): what a programmer may lawfully be "
                "pointed at is a matter for the operator, and installing one is not "
                "an argument about it."
            ),
            "setup_steps": (
                "Install the tools you need, join `plugdev` and `dialout`, then log "
                "out and back in — group membership does not apply to a session "
                "already open. There is no symlink to look for and that is "
                "deliberate; see the known problems."
            ),
            "known_problems": (
                f"These are the most heavily shared identifiers in the archive. "
                f"{shared_out} of the {len(entries)} are claimed by at least one "
                f"package outside this class, and the two that matter most to this "
                f"project are claimed by `libhamlib4t64`: {', '.join(hamlib)}. Those "
                f"are the ONLY two identifiers hamlib claims. A rig-control cable "
                f"and a JTAG adapter built on the same FTDI chip are the same USB "
                f"device to the kernel, so the access this class grants cannot be "
                f"given to one without giving it to the other.\n\n"
                f"That is why there is no symlink here at all — naming any of these "
                f"would claim hardware it does not identify (D-028) — and why the "
                f"class asks for group membership rather than anything cleverer. "
                f"An operator who wants a stable name for one specific programmer "
                f"wants a station-local rule matching its serial, not a "
                f"catalog-wide one matching its chip.\n\n"
                f"avrdude and openocd also drive parallel-port and network "
                f"programmers that have no USB identifier at all and are therefore "
                f"invisible to this class."
            ),
            "upstream_url": "https://openocd.org/",
        },
    }

    header = (
        "# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC\n"
        "# SPDX-License-Identifier: CC0-1.0\n"
        "#\n"
        "# GENERATED by scripts/gen_programmer_class.py from the archive-wide udev\n"
        "# sweep. Do not hand-edit — regenerate. Five packages name 180 distinct\n"
        "# identifiers between them, which is past the point where transcribing\n"
        "# evidence by hand is careful work.\n"
        f"#\n# Generated: {date.today().isoformat()}\n"
        f"# Sources: {', '.join(PACKAGES)}\n"
        f"# Identifiers: {len(entries)}, of which {sum(1 for e in entries if 'ambiguity' in e)}\n"
        "#   are on the generated ambiguity list and carry its verdict verbatim.\n\n"
    )
    OUT.write_text(header + yaml.safe_dump(doc, sort_keys=False, width=88, allow_unicode=True))
    print(
        f"wrote {OUT.relative_to(REPO_ROOT)}: {len(entries)} identifiers, "
        f"{sum(1 for e in entries if 'ambiguity' in e)} ambiguous, "
        f"{shared_out} also claimed outside this class"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
