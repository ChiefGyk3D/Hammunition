#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate CoMaps' map pins and region table.  D-069.

Writes ``catalog/data/comaps-pins.yaml`` from CoMaps' own map index,
``data/countries.txt`` at the commit ``catalog/packages/comaps.yaml`` pins
(about 360 KB): every map's size and base64 SHA-1, the map version and
series, and a table from Geofabrik's region paths -- the ones Hammunition
carries, ``gen_geofabrik_pins.REGIONS`` and ``geofabrik-countries.yaml`` -- to
the CoMaps maps that cover each. Every map in the world is pinned, so the file
says nothing about whose region matters.

The SHA-1 is the publisher's check, not one Hammunition measured: nothing is
downloaded but the index. The plan says so beside every map.

``--check --offline`` reads the file's shape and needs no network; the test
suite runs it. ``--check`` fetches the index at the pinned commit again and
compares the maps and the table (not the ``measured`` date), and ``HEAD``s the
pinned ``World.mwm``: CoMaps' CDN keeps a map version for months, not forever,
and a mirror answers a missing file with 200 and a web page, so the size is
compared, never the status. The weekly pin-review job runs it.

    scripts/gen_comaps_pins.py                   # fetch the index at the pin
    scripts/gen_comaps_pins.py --from FILE       # a countries.txt on disk
    scripts/gen_comaps_pins.py --check [--offline]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.comaps import (  # noqa: E402
    GENERATED_MARK,
    CdnProbe,
    ComapsError,
    flatten,
    map_url,
    parse_pins,
    published,
    region_table,
    version_date,
)

CATALOG = REPO_ROOT / "catalog"
PINS = CATALOG / "data" / "comaps-pins.yaml"
MANIFEST = CATALOG / "packages" / "comaps.yaml"
REPO = "https://codeberg.org/comaps/comaps"
MAX_INDEX = 8 * 1024 * 1024

Text = Callable[[str], str]
Head = Callable[[str], tuple[int, int]]

HEADER = f"""\
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

# {GENERATED_MARK}. Do not edit by hand.
#
# CoMaps' maps, from its own index (data/countries.txt) at the commit the
# comaps unit builds: every map's size and base64 SHA-1, the publisher's check
# (D-069). Nothing but the index was downloaded to make this. `regions` maps
# Geofabrik region paths (what `station set --map-regions` takes) to the maps
# that cover them, by the rule in hammunition.comaps.region_table; a region
# the rule cannot place is absent, and the plan names it.
#
# Regenerate: scripts/gen_comaps_pins.py (after moving the comaps pin)
# Check:      scripts/gen_comaps_pins.py --check [--offline]
"""


def index_url(commit: str) -> str:
    return f"{REPO}/raw/commit/{commit}/data/countries.txt"


def manifest_commit(path: Path = MANIFEST) -> str:
    """The commit ``comaps.yaml``'s git block pins: the maps must be the
    version the app's own index names."""
    data = yaml.safe_load(path.read_text())
    for block in data.get("install") or ():
        install = block.get("install") or {}
        if install.get("method") == "git" and install.get("commit"):
            return str(install["commit"])
    raise SystemExit(f"{path}: no git block with a commit; nothing to generate from")


def _load_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def carried_regions() -> tuple[str, ...]:
    """Every Geofabrik region path Hammunition carries a list of."""
    pinned: tuple[str, ...] = _load_module("gen_geofabrik_pins").REGIONS
    countries = yaml.safe_load((CATALOG / "data" / "geofabrik-countries.yaml").read_text())
    return tuple(sorted({*pinned, *(countries.get("regions") or {})}))


def render(index: Mapping[str, Any], *, commit: str, measured: date, regions: Sequence[str]) -> str:
    maps = flatten(index)
    version = index.get("v")
    series = index.get("map_series")
    if not isinstance(version, int) or not isinstance(series, str):
        raise ComapsError("the index carries no version or map series")
    version_date(version)
    table = region_table(index, regions)
    body = {
        "commit": commit,
        "source": index_url(commit),
        "measured": measured.isoformat(),
        "version": version,
        "map_series": series,
        "maps": {name: {"size": pin.size, "sha1": pin.sha1} for name, pin in sorted(maps.items())},
        "regions": {region: list(ids) for region, ids in sorted(table.items())},
    }
    return (
        HEADER
        + "\n"
        + yaml.safe_dump(
            body, sort_keys=False, default_flow_style=None, width=1000, allow_unicode=True
        )
    )


def real_text(url: str) -> str:
    if not url.startswith(REPO + "/raw/commit/"):
        raise SystemExit(f"refusing {url!r}: only {REPO}'s pinned index is fetched")
    request = urllib.request.Request(url, headers={"User-Agent": "hammunition"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body: bytes = response.read(MAX_INDEX + 1)
    if len(body) > MAX_INDEX:
        raise SystemExit(f"{url} is larger than {MAX_INDEX} bytes; refusing it")
    return body.decode("utf-8")


def _comparable(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("measured:"))


def main(
    argv: Sequence[str] | None = None,
    *,
    text: Text | None = None,
    head: Head | None = None,
    pins_path: Path = PINS,
    commit: str | None = None,
    regions: Sequence[str] | None = None,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="check the file; write nothing")
    parser.add_argument(
        "--offline", action="store_true", help="with --check: the shape only, no network"
    )
    parser.add_argument(
        "--from", dest="source", metavar="FILE", help="read a countries.txt from disk"
    )
    args = parser.parse_args(argv)
    pinned = commit or manifest_commit()
    known = regions if regions is not None else carried_regions()

    if args.check:
        try:
            current = parse_pins(pins_path.read_text(), known_regions=known)
        except (OSError, ComapsError) as exc:
            print(f"{pins_path}: {exc}")
            return 1
        if current.commit != pinned:
            print(
                f"{pins_path.name} was generated at {current.commit} and comaps.yaml pins "
                f"{pinned}: the maps would not be the version the app reads. Regenerate."
            )
            return 1
        if args.offline:
            print(
                f"{pins_path.name} is well formed: {len(current.maps)} map(s), "
                f"{len(current.regions)} region(s), version {current.version}"
            )
            return 0
        problems: list[str] = []
        index = json.loads((text or real_text)(index_url(pinned)))
        fresh = render(index, commit=pinned, measured=date.today(), regions=known)
        if _comparable(fresh) != _comparable(pins_path.read_text()):
            problems.append(
                f"{pins_path.name} is not what the index at {pinned[:12]} and the rule "
                f"produce now; regenerate it"
            )
        world = current.maps["World"]
        url = map_url(current, "World")
        status, size = (head or CdnProbe().head)(url)
        if not published(status, size, world):
            problems.append(
                f"pin expired: {url} answered {status} with {size} bytes, not "
                f"{world.size}; CoMaps' CDN no longer publishes map version "
                f"{current.version}. Move comaps.yaml to a newer CoMaps tag and regenerate."
            )
        if problems:
            print(f"{len(problems)} problem(s):")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print(
            f"{pins_path.name} is up to date: {len(current.maps)} map(s), version "
            f"{current.version} still published"
        )
        return 0

    if args.source:
        source = Path(args.source)
        index = json.loads(source.read_text())
        measured = date.fromtimestamp(source.stat().st_mtime)
    else:
        index = json.loads((text or real_text)(index_url(pinned)))
        measured = today or date.today()
    rendered = render(index, commit=pinned, measured=measured, regions=known)
    parse_pins(rendered, known_regions=known)
    pins_path.write_text(rendered)
    pins = parse_pins(rendered)
    print(
        f"wrote {pins_path.name}: {len(pins.maps)} map(s), {len(pins.regions)} region(s), "
        f"version {pins.version} ({pins.series})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
