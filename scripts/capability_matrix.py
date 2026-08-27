#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resolve every manifest against every declared target.

CLAUDE.md requires capability-matrix claims to be backed by a passing container
test. This is the check: for each target's real ``(distro, version, arch)``,
does each manifest resolve to an install block?

Run with ``--check`` inside a target container to verify that container's own
row, using its actual ``/etc/os-release`` rather than a declared one — a target
whose image drifts should fail loudly (D-016), not silently test the wrong row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.distro import DetectionError, Target  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
TARGETS = REPO_ROOT / "containers" / "targets.yaml"


def detect_target() -> Target:
    """Identify this container using the engine's own detection.

    Deliberately not a second parser. This script's ``--check`` mode exists to
    catch a target image drifting away from what ``containers/targets.yaml``
    declares; if it read ``/etc/os-release`` with its own copy of the logic, it
    would be verifying a parser the engine does not use, and the two could
    disagree about a machine while both reported success.
    """
    try:
        return Target.detect()
    except DetectionError as exc:
        raise SystemExit(str(exc)) from exc


def load_targets() -> list[dict[str, Any]]:
    data = yaml.safe_load(TARGETS.read_text())
    targets: list[dict[str, Any]] = data["targets"]
    return targets


def resolve_row(
    manifests: dict[str, PackageManifest], distro: str, version: str, arch: str
) -> dict[str, str | None]:
    row: dict[str, str | None] = {}
    for name, manifest in sorted(manifests.items()):
        block = manifest.resolve(distro, version, arch)
        row[name] = None if block is None else block.install.method
    return row


def full_matrix(manifests: dict[str, PackageManifest]) -> dict[str, dict[str, str | None]]:
    return {
        t["name"]: resolve_row(
            manifests, t["os_release_id"], str(t["os_release_version"]), t["arch"]
        )
        for t in load_targets()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify this container's own row using its real /etc/os-release",
    )
    parser.add_argument("--json", action="store_true", help="emit the full matrix as JSON")
    args = parser.parse_args()

    manifests = load_catalog(CATALOG)

    if args.json:
        print(json.dumps(full_matrix(manifests), indent=2, sort_keys=True))
        return 0

    if args.check:
        target = detect_target()
        distro, version, arch = target.distro, target.version, target.arch
        print(f"detected: {target.describe()}")

        declared = [
            t
            for t in load_targets()
            if t["os_release_id"] == distro and str(t["os_release_version"]) == version
        ]
        if not declared:
            print(
                f"FAIL: running on {distro} {version}, which no target in "
                f"containers/targets.yaml declares. Either the image drifted or "
                f"targets.yaml is stale.",
                file=sys.stderr,
            )
            return 1

        row = resolve_row(manifests, distro, version, arch)
        unsupported = [n for n, m in row.items() if m is None]
        for name, method in sorted(row.items()):
            print(f"  {name:<18} {method or 'UNSUPPORTED on this target'}")
        print(
            f"\n{len(row) - len(unsupported)}/{len(row)} manifests resolve on "
            f"{distro} {version} {arch}"
        )
        if unsupported:
            print(f"honest gaps (not failures): {', '.join(unsupported)}")
        return 0

    matrix = full_matrix(manifests)
    names = sorted(next(iter(matrix.values())))
    width = max(len(n) for n in names) + 2
    print(f"{'package':<{width}}" + "".join(f"{t:<16}" for t in matrix))
    for name in names:
        cells = "".join(f"{(matrix[t][name] or '—'):<16}" for t in matrix)
        print(f"{name:<{width}}{cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
