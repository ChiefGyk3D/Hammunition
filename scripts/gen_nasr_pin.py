#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the FAA NASR airport pin.  D-075.

The FAA publishes NASR every 28 days, on the AIRAC cycle, at a URL dated by
the cycle's effective day:
``https://nfdc.faa.gov/webContent/28DaySub/extra/01_Oct_2026_APT_CSV.zip``
(8,030,968 bytes for 2026-10-01, byte-identical over two fetches). The cycle
is computed from the AIRAC epoch, every 28 days from 2026-01-22; the file is
fetched, checked to be the APT CSV of that cycle (``APT_BASE.csv``'s
``EFF_DATE``), and its URL, sha256, size, the cycle as ``version`` and the
licence line ``FAA NASR <cycle>, public domain`` (what the plan prints) are
written into ``catalog/packages/faa-nasr-airports.yaml``.

``--check`` goes red when a newer cycle has taken effect, or when the pinned
URL no longer serves the pinned bytes (it fetches them: the FAA's server
answered a HEAD with 503 while serving the file by GET); the weekly pin
review runs it, so it goes red about once in four weeks. ``--check --offline``
checks the manifest's shape only and runs in the test suite.

    scripts/gen_nasr_pin.py                    # regenerate (8 MB)
    scripts/gen_nasr_pin.py --check            # the cycle, and the file again (8 MB)
    scripts/gen_nasr_pin.py --check --offline  # the manifest's shape only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sys
import zipfile
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_pin  # noqa: E402
from hammunition.manifest.load import load_manifest  # noqa: E402
from hammunition.manifest.schema import DataInstall  # noqa: E402

MANIFEST = REPO_ROOT / "catalog" / "packages" / "faa-nasr-airports.yaml"
HOST = "https://nfdc.faa.gov/"
INSTALL_AS = "APT_CSV.zip"
LIMIT = 64 * 1024 * 1024
#: AIRAC 2601's effective day; every cycle is a multiple of 28 days from it.
EPOCH = date(2026, 1, 22)
CYCLE = timedelta(days=28)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
REGENERATE = "regenerate with scripts/gen_nasr_pin.py"
OWNED = ("version", "url", "sha256", "size", "licence")

Ask = Callable[..., data_pin.Answer]


def cycle_for(day: date) -> date:
    """The AIRAC cycle in effect on *day*."""
    return EPOCH + CYCLE * ((day - EPOCH).days // 28)


def url_for(cycle: date) -> str:
    return (
        f"{HOST}webContent/28DaySub/extra/"
        f"{cycle.day:02d}_{_MONTHS[cycle.month - 1]}_{cycle.year}_APT_CSV.zip"
    )


def licence_for(cycle: date) -> str:
    return f"FAA NASR {cycle.isoformat()}, public domain"


def checked_body(body: bytes, cycle: date) -> tuple[str, int, int]:
    """sha256, size and site count, or SystemExit when *body* is not the APT
    CSV of *cycle*."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        text = archive.read("APT_BASE.csv").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise SystemExit(f"the NASR file is not the APT CSV zip ({exc}). Nothing was written.")
    rows = list(csv.DictReader(io.StringIO(text)))
    cycles = {row.get("EFF_DATE", "").strip() for row in rows}
    want = cycle.strftime("%Y/%m/%d")
    if cycles != {want}:
        raise SystemExit(
            f"the NASR file's EFF_DATE is {sorted(cycles)[:3]}, not {want}. Nothing was written."
        )
    return hashlib.sha256(body).hexdigest(), len(body), len(rows)


def _block(path: Path) -> DataInstall:
    block = load_manifest(path).install[0].install
    if not isinstance(block, DataInstall):
        raise SystemExit(f"{path}: its first install block is not a data block")
    return block


def shape_problems(path: Path) -> list[str]:
    """What is wrong with the manifest, offline."""
    try:
        manifest = load_manifest(path)
        block = _block(path)
    except Exception as exc:  # a schema or YAML error, named
        return [f"{path.name} does not load: {exc}"]
    problems: list[str] = []
    if len(block.artifacts) != 1:
        return [f"{path.name} must carry exactly one artifact"]
    artifact = block.artifacts[0]
    try:
        cycle = date.fromisoformat(manifest.version)
    except ValueError:
        return [f"version {manifest.version!r} must be the cycle's day, YYYY-MM-DD"]
    if (cycle - EPOCH).days % 28:
        problems.append(f"version {manifest.version} is not an AIRAC cycle day")
    if artifact.url != url_for(cycle):
        problems.append(f"the URL is {artifact.url!r}, not the cycle's {url_for(cycle)!r}")
    if block.licence != licence_for(cycle):
        problems.append(f"the licence line must be {licence_for(cycle)!r}")
    if artifact.install_as != INSTALL_AS:
        problems.append(f"the artifact must install as {INSTALL_AS}")
    if set(artifact.sha256) == {"0"} or artifact.size <= 1:
        problems.append(f"the pin is a placeholder; {REGENERATE}")
    problems += data_pin.owned_problems(path.read_text(), OWNED, path.name)
    return problems


def main(
    argv: Sequence[str] | None = None,
    *,
    ask: Ask | None = None,
    today: date | None = None,
    manifest_path: Path = MANIFEST,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="check the pin; write nothing")
    parser.add_argument(
        "--offline", action="store_true", help="with --check: the manifest's shape only"
    )
    args = parser.parse_args(argv)
    get = ask or data_pin.ask
    now = today or date.today()
    current = cycle_for(now)

    if args.check:
        problems = shape_problems(manifest_path)
        if not problems and not args.offline:
            pinned = date.fromisoformat(load_manifest(manifest_path).version)
            artifact = _block(manifest_path).artifacts[0]
            if current > pinned:
                problems.append(
                    f"a newer NASR cycle took effect on {current}; the pin is {pinned}. "
                    f"The pinned file still installs while the FAA serves it; {REGENERATE}"
                )
            # A GET, not a HEAD: nfdc.faa.gov answered HEAD with 503 while
            # serving the same URL by GET (2026-10-01).
            answer = get(artifact.url, HOST, limit=LIMIT)
            digest = hashlib.sha256(answer.body).hexdigest()
            if answer.status != 200 or (digest, len(answer.body)) != (
                artifact.sha256,
                artifact.size,
            ):
                problems.append(
                    f"{artifact.url} answered {answer.status} with {len(answer.body)} bytes, "
                    f"sha256 {digest[:12]}…, not the pinned {artifact.size} bytes, "
                    f"{artifact.sha256[:12]}…; {REGENERATE}"
                )
        if problems:
            print(f"{len(problems)} problem(s):")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print(f"{manifest_path.name} is " + ("well formed" if args.offline else "up to date"))
        return 0

    url = url_for(current)
    answer = get(url, HOST, limit=LIMIT)
    if answer.status != 200:
        raise SystemExit(f"{url} answered {answer.status}. Nothing was written.")
    sha256, size, count = checked_body(answer.body, current)
    text = data_pin.rewrite(
        manifest_path.read_text(),
        {
            "version": current.isoformat(),
            "url": url,
            "sha256": sha256,
            "size": str(size),
            "licence": licence_for(current),
        },
    )
    data_pin.write(manifest_path, text)
    # Verify the effect, not the exit status (D-031): read back what was written.
    block = _block(manifest_path)
    artifact = block.artifacts[0]
    if (artifact.url, artifact.sha256, artifact.size, block.licence) != (
        url,
        sha256,
        size,
        licence_for(current),
    ) or load_manifest(manifest_path).version != current.isoformat():
        raise SystemExit(f"{manifest_path} did not take the new pin; check it by hand")
    print(
        f"wrote {manifest_path.name}: cycle {current}, {size:,} bytes, {count} sites, "
        f"sha256 {sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
