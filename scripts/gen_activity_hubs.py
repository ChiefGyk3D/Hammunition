#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fill the generated blocks of the activity hub pages under docs/activities/.

Each hub is hand-written prose: what the activity is, the first useful task,
what works offline, what was measured. Prose cannot say which programs and
which hardware the catalog carries without duplicating manifest data by hand,
and a hand copy drifts. So each hub holds two marked blocks,

    <!-- BEGIN generated: programs -->  ...  <!-- END generated: programs -->
    <!-- BEGIN generated: hardware -->  ...  <!-- END generated: hardware -->

and this script rewrites what lies between them from the manifests, the
profiles and the hardware catalog. Everything outside the markers is the
author's and is never touched. A hub whose block is missing, or whose
catalog selection is empty where the page says it is not, fails loudly.

Which units belong to a hub is the table HUBS below: a vocabulary tag
(`catalog/categories.yaml`) plus, where a tag is wider than the activity, the
names listed. MeshCore has none yet; the block says so, and lists the unit the
day one is added, so the stub cannot go quietly stale.

Usage:
    scripts/gen_activity_hubs.py            # rewrite the blocks
    scripts/gen_activity_hubs.py --check    # fail if any page is out of date
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.hardware import DeviceClass, DeviceManifest  # noqa: E402
from hammunition.manifest.load import load_catalog, load_hardware, load_profiles  # noqa: E402
from hammunition.manifest.schema import PackageManifest, Status  # noqa: E402

DOCS = REPO_ROOT / "docs"


@dataclass(frozen=True)
class Hub:
    page: str
    tags: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    # Name prefixes that would make a unit this hub's (MeshCore has none yet).
    prefixes: tuple[str, ...] = ()
    devices: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
    none_yet: str = ""
    # Extra manifests, by name, that belong to the hub but sit under tags the hub
    # does not otherwise want (a tag like navigation-maps is far wider).
    also: tuple[str, ...] = field(default=())


HUBS = (
    Hub(
        "gps-time.md",
        tags=("gps-gnss",),
        also=("chrony", "comaps", "osm-pmtiles", "qmapshack", "navit"),
        classes=("gps-receiver",),
    ),
    Hub("aprs.md", tags=("aprs",)),
    Hub(
        "meshtastic.md",
        names=("python3-meshtastic", "gtk-meshtastic-client"),
        devices=("meshtastic",),
    ),
    Hub("reticulum.md", names=("rns", "lxmf", "nomadnet"), devices=("rnode",)),
    Hub(
        "meshcore.md",
        prefixes=("meshcore", "python3-meshcore"),
        none_yet="The catalog carries no MeshCore unit and no MeshCore device entry.",
    ),
)

BLOCK = re.compile(
    r"(<!-- BEGIN generated: (?P<kind>programs|hardware) -->\n)(?P<body>.*?)(<!-- END generated: (?P=kind) -->)",
    re.DOTALL,
)


def _members(hub: Hub, manifests: dict[str, PackageManifest]) -> list[str]:
    chosen: set[str] = set()
    for name, m in manifests.items():
        if any(t in hub.tags for t in m.categories):
            chosen.add(name)
        if name in hub.names or name in hub.also:
            chosen.add(name)
        if any(name.startswith(p) for p in hub.prefixes):
            chosen.add(name)
    missing = [n for n in (*hub.names, *hub.also) if n not in manifests]
    if missing:
        raise SystemExit(f"{hub.page}: no such unit: {', '.join(missing)}")
    return sorted(chosen)


def programs_block(
    hub: Hub, manifests: dict[str, PackageManifest], profiles: dict[str, list[str]]
) -> str:
    members = _members(hub, manifests)
    if not members:
        return (hub.none_yet or "The catalog carries no unit for this.") + "\n"
    in_profiles: dict[str, list[str]] = {}
    for pname, pkgs in profiles.items():
        for pkg in pkgs:
            in_profiles.setdefault(pkg, []).append(pname)
    lines = []
    for name in members:
        m = manifests[name]
        retired = " *(retired)*" if m.status is Status.retired else ""
        where = in_profiles.get(name)
        how = (
            "in " + ", ".join(f"[`{p}`](../profiles/{p}.md)" for p in sorted(where))
            if where
            else "by name only"
        )
        lines.append(f"- [{name}](../packages/{name}.md){retired}: {m.summary} ({how})")
    return "\n".join(lines) + "\n"


def hardware_block(
    hub: Hub, classes: dict[str, DeviceClass], devices: dict[str, DeviceManifest]
) -> str:
    lines = []
    for name in hub.devices:
        if name not in devices:
            raise SystemExit(f"{hub.page}: no such device: {name}")
        d = devices[name]
        lines.append(
            f"- [{name}](../hardware/{name}.md): {d.summary} "
            f"(status {d.status}; "
            f"{'maintainer-verified' if d.maintainer_verified else 'not maintainer-verified'})"
        )
    for name in hub.classes:
        if name not in classes:
            raise SystemExit(f"{hub.page}: no such device class: {name}")
        lines.append(f"- [{name}](../hardware/{name}-class.md) (class): {classes[name].summary}")
    if not lines:
        return (hub.none_yet or "The catalog carries no hardware entry for this.") + "\n"
    return "\n".join(lines) + "\n"


def render(
    text: str,
    hub: Hub,
    manifests: dict[str, PackageManifest],
    profiles: dict[str, list[str]],
    classes: dict[str, DeviceClass],
    devices: dict[str, DeviceManifest],
) -> str:
    seen: set[str] = set()

    def sub(match: re.Match[str]) -> str:
        kind = match.group("kind")
        seen.add(kind)
        body = (
            programs_block(hub, manifests, profiles)
            if kind == "programs"
            else hardware_block(hub, classes, devices)
        )
        return f"{match.group(1)}\n{body}\n{match.group(4)}"

    out = BLOCK.sub(sub, text)
    # A hub with no catalogued hardware (APRS) writes its hardware prose by hand.
    needed = {"programs"} | ({"hardware"} if hub.devices or hub.classes or hub.none_yet else set())
    if seen != needed:
        raise SystemExit(
            f"docs/activities/{hub.page}: needs the generated blocks {sorted(needed)} "
            f"(found: {sorted(seen)})"
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()

    manifests = load_catalog(REPO_ROOT / "catalog" / "packages")
    loaded = load_profiles(REPO_ROOT / "catalog" / "profiles", manifests)
    profiles = {n: list(p.packages) for n, p in loaded.items()}
    classes, devices = load_hardware(REPO_ROOT / "catalog" / "hardware")

    stale = 0
    for hub in HUBS:
        path = DOCS / "activities" / hub.page
        if not path.exists():
            print(f"{path.relative_to(REPO_ROOT)} is missing")
            return 1
        old = path.read_text()
        new = render(old, hub, manifests, profiles, classes, devices)
        rel = path.relative_to(REPO_ROOT)
        if args.check:
            if old != new:
                print(f"{rel} is out of date; run scripts/gen_activity_hubs.py")
                stale += 1
        elif old != new:
            path.write_text(new)
            print(f"wrote {rel}")
    if args.check:
        if stale:
            return 1
        print("activity hubs are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
