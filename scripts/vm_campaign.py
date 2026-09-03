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

The exception is ``--whole-profiles``: each name is a profile installed as
one transaction, and ``--reset-each DOMAIN`` restores the VM to
`clean-baseline` and re-prepares it before every one. Per-unit success does
not prove profile success -- `digital-modes` had twenty of twenty-one
members confirmed by name on two targets and could not install whole on any
(the twenty-first's vendor .deb collided with a package another member
pulled in; found on a clean Kali VM, 2026-09-02, only because the profile
was installed as an operator would install it). Twenty minutes of resets a night is the price of
that test, and the profile is what an operator actually types.

The engine's own honesty does the heavy lifting: exit 0 means completed
*and confirmed* (D-031), exit 2 means the plan refused with every blocker
printed, exit 1 means a command failed with the log holding what completed.
This script only files the outcomes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
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
    124: "STOPPED (budget)",
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


def reset_and_prepare(domain: str, host: str, identity: str | None) -> None:
    """Back to `clean-baseline`, then the runbook's prepare steps.

    The VM's own address is what ``--host`` says; the snapshot restore goes
    through libvirt on this side. A guest that never answers ssh after the
    restore is an error here, not a unit result -- nothing was measured.
    """
    subprocess.run(
        [str(REPO_ROOT / "scripts" / "vm-snapshot.sh"), "restore", domain, "clean-baseline"],
        check=True,
    )
    ssh = [*SSH_BASE, *(["-i", identity] if identity else [])]
    for _ in range(60):
        if subprocess.run([*ssh, host, "true"], capture_output=True, check=False).returncode == 0:
            break
        time.sleep(5)
    else:
        sys.exit(f"{domain} did not answer ssh at {host} within 5 minutes of the restore")
    # tar over ssh rather than rsync: the Debian 13 guest's clean-baseline
    # has no rsync, and a prepare step that depends on a package the
    # snapshot may lack fails before anything is measured. tar is essential.
    excludes = ("./.git", "./.venv", "./reference", "./vendor", "*.tar.gz")
    tar = subprocess.Popen(
        ["tar", "-C", str(REPO_ROOT), *(f"--exclude={e}" for e in excludes), "-cf", "-", "."],
        stdout=subprocess.PIPE,
    )
    subprocess.run(
        [*ssh, host, "rm -rf hammunition && mkdir hammunition && tar -C hammunition -xf -"],
        stdin=tar.stdout,
        check=True,
    )
    if tar.wait() != 0:
        sys.exit("tar of the repository failed")
    subprocess.run(
        [
            *ssh,
            host,
            "cd hammunition && python3 -m venv .venv && .venv/bin/pip install -q -e . "
            "&& .venv/bin/hammunition --version",
        ],
        check=True,
        capture_output=True,
    )


def run_unit(host: str, identity: str | None, unit: str, timeout: int) -> UnitResult:
    """One engine install over SSH; the tail is the evidence.

    The budget is enforced on the VM, not here. A local ``subprocess`` timeout
    only kills the ssh client; the remote ``hammunition install`` keeps going
    with nobody watching, and the next unit starts on top of it. That is how
    the Ubuntu 26.04 campaign filed ``qlog`` as failed at 900 s while its
    single-job compile ran on to a verified transaction at 1032 s
    (2026-09-02). ``timeout`` on the VM signals the whole process group, so
    the compile stops with the engine, and exit 124 says so.
    """
    remote = (
        f"cd hammunition && timeout -k 30 {timeout}s "
        f".venv/bin/hammunition install {unit} --yes 2>&1 | tail -60; "
        f'echo "__EXIT=${{PIPESTATUS[0]}}"'
    )
    argv = list(SSH_BASE)
    if identity:
        argv += ["-i", identity]
    argv += [host, f"bash -c '{remote}'"]
    started = datetime.now(UTC)
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout + 120, check=False
        )
        raw = proc.stdout
    except subprocess.TimeoutExpired:
        return UnitResult(unit, -1, timeout, f"ssh did not return {timeout + 120}s after start")
    seconds = (datetime.now(UTC) - started).total_seconds()
    return classify(unit, raw, seconds=seconds, timeout=timeout)


def classify(unit: str, raw: str, *, seconds: float, timeout: int) -> UnitResult:
    """Turn the remote session's merged output into a filed result."""
    exit_code = 255
    tail_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("__EXIT="):
            exit_code = int(line.split("=", 1)[1])
        else:
            tail_lines.append(line)
    if exit_code == 124:
        return UnitResult(
            unit, 124, seconds, f"stopped by the {timeout}s budget; the build was still running"
        )
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
    noun: str = "Units",
) -> str:
    ok = [r for r in results if r.exit_code == 0]
    refused = [r for r in results if r.exit_code == 2]
    stopped = [r for r in results if r.exit_code == 124]
    failed = [r for r in results if r.exit_code not in (0, 2, 124)]
    budget = f", {len(stopped)} stopped by the budget" if stopped else ""
    lines = [
        "# VM campaign report",
        "",
        f"**Date:** {datetime.now(UTC).date().isoformat()}",
        f"**Engine:** commit `{engine_commit}`",
        f"**Target:** {target_line}",
        f"**{noun}:** {len(results)} — "
        f"{len(ok)} installed+confirmed, {len(refused)} refused at plan time, "
        f"{len(failed)} failed{budget}",
        "",
        "Exit 0 is the engine's own bar: completed *and confirmed* by re-probe",
        "(D-031). A plan-time refusal is honest coverage reporting, not a",
        "failure — its text names what is missing.",
        "",
        "| Name | Outcome | Seconds |",
        "|---|---|---:|",
    ]
    for r in results:
        lines.append(f"| `{r.unit}` | {r.outcome} | {r.seconds:.0f} |")
    buckets = (
        ("Failures", failed),
        ("Stopped by the budget (not a verdict; rerun with a larger --timeout)", stopped),
        ("Plan-time refusals", refused),
    )
    for title, bucket in buckets:
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
    parser.add_argument(
        "--whole-profiles",
        action="store_true",
        help="each name in --units is a profile, installed as one transaction",
    )
    parser.add_argument(
        "--reset-each",
        metavar="DOMAIN",
        default=None,
        help="libvirt domain to restore to clean-baseline and re-prepare before every unit",
    )
    args = parser.parse_args()

    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    profiles = load_profiles(REPO_ROOT / "catalog" / "profiles", catalog)

    units: list[str] = list(args.units)
    for name in args.profile:
        if name not in profiles:
            sys.exit(f"no profile named {name!r}")
        units += [p for p in profiles[name].packages if p not in units]
    known = profiles if args.whole_profiles else catalog
    unknown = [u for u in units if u not in known]
    if unknown:
        what = "profiles" if args.whole_profiles else "the catalog"
        sys.exit(f"not in {what}: {', '.join(unknown)}")
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
        if args.reset_each:
            reset_and_prepare(args.reset_each, args.host, args.identity)
        result = run_unit(args.host, args.identity, unit, args.timeout)
        print(f"    {result.outcome} ({result.seconds:.0f}s)", flush=True)
        results.append(result)

    report = render_report(
        target_line=target_probe,
        engine_commit=commit,
        results=results,
        noun="Profiles (whole, from clean-baseline)" if args.whole_profiles else "Units",
    )
    if args.out:
        args.out.write_text(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
