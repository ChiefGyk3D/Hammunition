#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render docs/reference/brltty-inventory.md from reference/probes/brltty-*.txt.

The question (D-042, sub-project 2; answered by D-047): does any target's
``brltty`` ship a udev rule that claims a USB identifier our hardware catalog
also names? AHRL purges brltty unconditionally and EmComm Tools shadows its
rules file with an empty one, because the rules once claimed every FTDI,
CP210x and CH340 bridge as a braille display. Whether they still do, on the
distributions this project targets, is a measurement -- this page -- and not
a memory.

The probe files come from ``scripts/run-brltty-probe.sh``. Each holds what
the archive's package ships, never what an installed machine has. The catalog
side is read live from ``catalog/hardware/``, so a catalog that gains an
identifier brltty names makes ``--check`` report this page stale, which is the
point.

``--check`` renders in memory and compares, ignoring the probed-date line; a
missing probe is an error naming the runner (issue #45's shape), never an
empty table.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBES = REPO_ROOT / "reference" / "probes"
OUT = REPO_ROOT / "docs" / "reference" / "brltty-inventory.md"
TARGETS = [
    "debian-13",
    "debian-13-arm64",
    "parrot",
    "kali-rolling",
    "ubuntu-24.04",
    "ubuntu-26.04",
    "linuxmint-22.3",
]

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from udev_rule_pairs import find_pair  # noqa: E402


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANUFACTURER = re.compile(r'ATTRS?\{manufacturer\}\s*==\s*"([^"]+)"')
PARENT = re.compile(
    r'ATTRS\{idVendor\}\s*==\s*"([0-9a-fA-F]{4})",\s*ATTRS\{idProduct\}\s*==\s*"([0-9a-fA-F]{4})"'
)
DRIVER = re.compile(r'ENV\{BRLTTY_BRAILLE_DRIVER\}\s*=\s*"([^"]+)"')


@dataclass
class Rule:
    vendor: str
    product: str
    enabled: bool
    line: str
    description: str

    @property
    def pair(self) -> str:
        return f"{self.vendor}:{self.product}"

    @property
    def qualifier(self) -> str:
        """What else the rule requires, read from the line itself."""
        m = MANUFACTURER.search(self.line)
        if m:
            return f"only when the USB manufacturer string is `{m.group(1)}`"
        p = PARENT.search(self.line)
        if p and (p.group(1).lower(), p.group(2).lower()) != (self.vendor, self.product):
            return (
                f"only behind a parent device `{p.group(1).lower()}:{p.group(2).lower()}` (a hub)"
            )
        return "every device with this identifier"


@dataclass
class Probe:
    target: str
    pretty: str = ""
    candidate: str = ""
    pulled_in_by: list[tuple[str, str]] = field(default_factory=list)
    version: str = ""
    shipped: list[str] = field(default_factory=list)
    files: list[tuple[str, str, list[Rule]]] = field(default_factory=list)  # path, sha, rules
    no_deb: bool = False


def parse_probe(target: str, text: str) -> Probe:
    probe = Probe(target=target)
    section = ""
    current_file: tuple[str, str, list[Rule]] | None = None
    description = ""
    for line in text.splitlines():
        if line.startswith("### FILE "):
            _, _, rest = line.partition("### FILE ")
            path, _, sha = rest.partition(" sha256=")
            current_file = (path, sha, [])
            probe.files.append(current_file)
            description = ""
            section = "file"
            continue
        if line.startswith("### END FILE"):
            current_file = None
            section = ""
            continue
        if line.startswith("### "):
            section = line[4:].strip()
            continue
        if line == "NO DEB":
            probe.no_deb = True
            continue
        if section == "target":
            m = re.match(r'PRETTY_NAME="([^"]+)"', line)
            if m:
                probe.pretty = m.group(1)
        elif section == "candidate":
            probe.candidate = line.strip() or probe.candidate
        elif section == "pulled-in-by":
            parts = line.split()
            if len(parts) == 2:
                probe.pulled_in_by.append((parts[0], parts[1]))
        elif section == "version":
            probe.version = line.strip() or probe.version
        elif section == "udev-rules-shipped":
            if line.strip() and line.strip() != "none":
                probe.shipped.append(line.strip().lstrip("."))
        elif section == "file" and current_file is not None:
            stripped = line.strip()
            if stripped.startswith("#"):
                text_ = stripped.lstrip("#").strip()
                pair = find_pair(text_)
                if pair:
                    current_file[2].append(Rule(pair[0], pair[1], False, text_, description))
                elif text_.startswith(("Device:", "BEGIN", "END", "Vendor:", "Product:")):
                    pass
                elif text_:
                    description = text_
                continue
            pair = find_pair(stripped)
            if pair:
                current_file[2].append(Rule(pair[0], pair[1], True, stripped, description))
    return probe


def render(probes: list[Probe], catalog: set[tuple[str, str]], probed: date) -> str:
    out = [
        "<!-- Generated by scripts/gen_brltty_inventory.py. Do not edit by hand -->",
        "",
        "# brltty against the hardware catalog",
        "",
        "Generated by `scripts/gen_brltty_inventory.py` from `scripts/run-brltty-probe.sh`.",
        "Do not edit by hand — regenerate.",
        "",
        f"**Probed:** {probed.isoformat()}, seven targets, the archive's package downloaded and read,",
        "never installed. The catalog side is `catalog/hardware/` as it is now.",
        "",
        "## What this is",
        "",
        "`brltty` gives a blind operator a braille display. Its udev rules start it",
        "when a display is plugged in, and for years they named the generic USB",
        "serial bridges — FTDI FT232, Silicon Labs CP210x, WCH CH340 — because",
        "several displays are built on them. A rig-control cable, a GPS puck or a",
        "Meshtastic node on the same chip was then claimed as a braille display the",
        "moment it appeared, and its serial port vanished with no error anywhere.",
        "AHRL purges `brltty` unconditionally at the start of every run; EmComm Tools",
        "shadows `85-brltty.rules` with an empty file and masks `brltty-udev.service`",
        "(**D-042**). Both are the accessibility software removed from every machine",
        "to fix a collision that may not exist on it.",
        "",
        "This page measures the collision per target instead: which `brltty` the",
        "archive offers, what pulls it onto a machine, whether the package ships a",
        "rules file at all, and which of its rules name an identifier this catalog",
        "also names — with the rule's own qualifiers, because a rule that fires only",
        "for one manufacturer string or only behind one hub is not the rule that",
        "took every FTDI cable in 2022. **D-047** records what follows from it.",
        "",
        "## Per target",
        "",
        "| Target | `brltty` | Arrives by | Rules file | Rules (on / off) | Names a catalogued identifier |",
        "|---|---|---|---|---:|---|",
    ]
    for p in probes:
        arrives = (
            ", ".join(
                f"`{pkg}` ({rel})" for pkg, rel in p.pulled_in_by if not pkg.startswith("brltty-")
            )
            or "nothing in the archive"
        )
        if p.no_deb:
            rules_file, counts, names = "not downloadable", "—", "—"
        elif not p.files:
            rules_file, counts, names = "**none shipped**", "—", "—"
        else:
            rules_file = ", ".join(f"`{path}`" for path, _, _ in p.files)
            rules = [r for _, _, rs in p.files for r in rs]
            on = sum(1 for r in rules if r.enabled)
            counts = f"{on} / {len(rules) - on}"
            hits = [r for r in rules if (r.vendor, r.product) in catalog]
            on_hits = [r for r in hits if r.enabled]
            names = f"**{len(on_hits)} enabled** of {len(hits)} rules" if hits else "none"
        out.append(
            f"| {p.target} — {p.pretty} | {p.version or p.candidate or '—'} | {arrives} | "
            f"{rules_file} | {counts} | {names} |"
        )
    out += [
        "",
        "*Arrives by* lists every archive package whose Depends, Recommends or",
        "Suggests names `brltty` (its own driver sub-packages excluded). Recommends",
        "installs by default; Suggests does not.",
        "",
        "## The rules that name a catalogued identifier",
        "",
        "Every rule below is quoted from the shipped file. *Fires for* is read from",
        "the rule's own qualifiers: a manufacturer-string match fires only for a",
        "device whose USB descriptor carries that exact string, and a parent match",
        "fires only for a device plugged in behind that hub.",
        "",
    ]
    any_rows = False
    for p in probes:
        for path, sha, rules in p.files:
            hits = [r for r in rules if (r.vendor, r.product) in catalog]
            if not hits:
                continue
            any_rows = True
            out += [
                f"### {p.target} — `brltty` {p.version}, `{path}` (sha256 `{sha[:16]}…`)",
                "",
                "| Identifier | State | Braille device | Fires for | Rule |",
                "|---|---|---|---|---|",
            ]
            for r in hits:
                state = "**enabled**" if r.enabled else "disabled"
                out.append(
                    f"| `{r.pair}` | {state} | {r.description or '—'} | {r.qualifier} | `{r.line}` |"
                )
            out.append("")
    if not any_rows:
        out += ["No target's `brltty` names an identifier this catalog carries.", ""]
    out += [
        "## What the rule does when it fires",
        "",
        "Every matching rule jumps to `brltty_usb_run`, which adds a",
        "`/dev/brltty/USB-…` symlink, sets `BRLTTY_BRAILLE_DEVICE` to the device's",
        "USB address, tags the device for systemd and wants `brltty-udev.service`.",
        "That service runs `brltty -n`, which opens the display it was told about",
        "through libusb — detaching the kernel's serial driver from it. The `/dev/ttyUSB*`",
        "node the operator's software was about to open is gone from that moment.",
        "",
        "## Reproducing the measurement",
        "",
        "```",
        "scripts/run-brltty-probe.sh            # all seven targets, rootless podman",
        "scripts/gen_brltty_inventory.py        # this page",
        "```",
        "",
        "Set `HAMMUNITION_DEGRADED_PODMAN=1` on an account without subuid ranges,",
        "and `PODMAN_AUTHFILE` to an empty `{}` file if a stale Docker Hub login in",
        "`~/.docker/config.json` makes anonymous pulls fail — the runner says so.",
        "",
    ]
    return "\n".join(out)


def _comparable(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.startswith("**Probed:**")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()

    missing = [t for t in TARGETS if not (PROBES / f"brltty-{t}.txt").exists()]
    if missing:
        sys.exit(
            f"missing probe(s) for {', '.join(missing)}: run scripts/run-brltty-probe.sh "
            f"{' '.join(missing)} — a page rendered without them would say nothing about them"
        )
    probes = [parse_probe(t, (PROBES / f"brltty-{t}.txt").read_text()) for t in TARGETS]
    empty = [p.target for p in probes if not p.candidate and not p.no_deb]
    if empty:
        sys.exit(f"probe file(s) carry no answer: {', '.join(empty)} — rerun the probe")
    inventory = _load("gen_udev_inventory")
    catalog = inventory.catalog_identifiers()  # type: ignore[attr-defined]
    probed = date.fromtimestamp(max((PROBES / f"brltty-{t}.txt").stat().st_mtime for t in TARGETS))
    body = render(probes, catalog, probed)
    if args.check:
        if not OUT.exists() or _comparable(OUT.read_text()) != _comparable(body):
            print(
                f"{OUT.relative_to(REPO_ROOT)} is out of date; run scripts/gen_brltty_inventory.py"
            )
            return 1
        print(f"{OUT.relative_to(REPO_ROOT)} is up to date")
        return 0
    OUT.write_text(body)
    print(f"wrote {OUT.relative_to(REPO_ROOT)} from {len(probes)} probe(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
