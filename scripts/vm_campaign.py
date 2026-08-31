#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Drive an install campaign against a VM and emit the evidence table.

M5's exit criterion is per-unit: every unit installs successfully on at
least one supported distro, or carries a verdict *we* tested. Gathering that
evidence by hand is one SSH session per unit per target; this script is that
session, looped, with the record written the way `vm-verification-*.md`
already records things — date, engine commit, target, and the actual failure
text, because an unrecorded result rots into an inherited verdict.

What it does per unit, over SSH against a prepared VM
(`docs/contributing/vm-testing.md` explains prepared): run
``hammunition install <unit> --yes``, keep the exit code and the last lines,
classify. What it deliberately does not do: reset between units — a campaign
is one machine-state accumulating installs, which is exactly how a real
operator's machine behaves, and per-unit resets would turn a night into a
week. Reset to `clean-baseline` before a campaign when you want isolation
(`scripts/vm-snapshot.sh reset DOMAIN`).

The engine's own honesty does the heavy lifting: exit 0 means completed
*and confirmed* (D-031), exit 2 means the plan refused with every blocker
printed, exit 1 means a command failed with the log holding what completed.
This script only files the outcomes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog, load_profiles  # noqa: E402

SSH_BASE = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
]

OUTCOMES = {
    0: "installed+confirmed",
    1: "FAILED",
    2: "refused (plan)",
    3: "consent declined",
}


@dataclass(frozen=True)
class UnitResult:
    unit: str
    exit_code: int
    seconds: float
    tail: str

    @property
    def outcome(self) -> str:
        return OUTCOMES.get(self.exit_code, f"exit {self.exit_code}")


def run_unit(host: str, identity: str | None, unit: str, timeout: int) -> UnitResult:
    """One engine install over SSH; the tail is the evidence."""
    remote = (
        f"cd hammunition && .venv/bin/hammunition install {unit} --yes 2>&1 | tail -60; "
        f'echo "__EXIT=${{PIPESTATUS[0]}}"'
    )
    argv = list(SSH_BASE)
    if identity:
        argv += ["-i", identity]
    argv += [host, f"bash -c '{remote}'"]
    started = datetime.now(UTC)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        raw = proc.stdout
    except subprocess.TimeoutExpired:
        return UnitResult(unit, -1, timeout, f"timed out after {timeout}s (build still running?)")
    seconds = (datetime.now(UTC) - started).total_seconds()
    exit_code = 255
    tail_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("__EXIT="):
            exit_code = int(line.split("=", 1)[1])
        else:
            tail_lines.append(line)
    # Keep what a reader needs. Stderr outruns block-buffered stdout through
    # a pipe, so a failure's text can land ANYWHERE in the merged stream —
    # the first report buried every real error above the tail window. Prefer
    # the lines from the first failure marker; fall back to the last few.
    nonempty = [ln for ln in tail_lines if ln.strip()]
    markers = ("Failed:", "problem block", "error:", "E: ")
    start = next((i for i, ln in enumerate(nonempty) if any(m in ln for m in markers)), None)
    keep = nonempty[start : start + 10] if start is not None else nonempty[-6:]
    return UnitResult(unit, exit_code, seconds, "\n".join(keep))


def render_report(
    *,
    target_line: str,
    engine_commit: str,
    results: list[UnitResult],
) -> str:
    ok = [r for r in results if r.exit_code == 0]
    refused = [r for r in results if r.exit_code == 2]
    failed = [r for r in results if r.exit_code not in (0, 2)]
    lines = [
        "# VM campaign report",
        "",
        f"**Date:** {datetime.now(UTC).date().isoformat()}",
        f"**Engine:** commit `{engine_commit}`",
        f"**Target:** {target_line}",
        f"**Units:** {len(results)} — "
        f"{len(ok)} installed+confirmed, {len(refused)} refused at plan time, "
        f"{len(failed)} failed",
        "",
        "Exit 0 is the engine's own bar: completed *and confirmed* by re-probe",
        "(D-031). A plan-time refusal is honest coverage reporting, not a",
        "failure — its text names what is missing.",
        "",
        "| Unit | Outcome | Seconds |",
        "|---|---|---:|",
    ]
    for r in results:
        lines.append(f"| `{r.unit}` | {r.outcome} | {r.seconds:.0f} |")
    for title, bucket in (("Failures", failed), ("Plan-time refusals", refused)):
        if not bucket:
            continue
        lines += ["", f"## {title}", ""]
        for r in bucket:
            lines += [f"### `{r.unit}`", "", "```", r.tail, "```", ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="user@ip of a prepared VM")
    parser.add_argument("--identity", default=None, help="ssh key path")
    parser.add_argument("--units", nargs="*", default=[], help="explicit unit names")
    parser.add_argument("--profile", action="append", default=[], help="expand a profile")
    parser.add_argument("--timeout", type=int, default=1800, help="per-unit seconds")
    parser.add_argument("--out", type=Path, default=None, help="write the report here")
    args = parser.parse_args()

    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    profiles = load_profiles(REPO_ROOT / "catalog" / "profiles", catalog)

    units: list[str] = list(args.units)
    for name in args.profile:
        if name not in profiles:
            sys.exit(f"no profile named {name!r}")
        units += [p for p in profiles[name].packages if p not in units]
    unknown = [u for u in units if u not in catalog]
    if unknown:
        sys.exit(f"not in the catalog: {', '.join(unknown)}")
    if not units:
        sys.exit("nothing to run: pass --units or --profile")

    commit = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    target_probe = (
        subprocess.run(
            [
                *SSH_BASE,
                *(["-i", args.identity] if args.identity else []),
                args.host,
                "cd hammunition && .venv/bin/hammunition status 2>/dev/null | head -1",
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or args.host
    )

    results: list[UnitResult] = []
    for unit in units:
        print(f"[{len(results) + 1}/{len(units)}] {unit} ...", flush=True)
        result = run_unit(args.host, args.identity, unit, args.timeout)
        print(f"    {result.outcome} ({result.seconds:.0f}s)", flush=True)
        results.append(result)

    report = render_report(target_line=target_probe, engine_commit=commit, results=results)
    if args.out:
        args.out.write_text(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
