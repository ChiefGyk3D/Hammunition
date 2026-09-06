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

``--reset-first DOMAIN`` does that restore, and the prepare (repository
synced, apt lists refreshed, venv built), once before the first unit.

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

Files them with their evidence, since 2026-09-04. Six passes of 243 units
each said `installed+confirmed` 1,375 times and could not answer, without a
shell on the guest, what confirmed any one of them: `yaac` on Parrot was
confirmed by one check, `libjssc-java 2.8.0-4`, a dependency. So every unit
now brings back the transaction-log lines it appended, the report has a
"Confirmed by" column and counts the units confirmed by no check at all,
the header carries what a rerun needs (snapshot and its creation time, the
InRelease dates of the apt lists, whether the synced tree was the named
commit), a refusal naming a package the pass itself installed earlier is
labelled *cumulative* and re-run alone on the snapshot, and a
`.evidence.jsonl` sidecar holds the whole record. The guest's address is in
none of it: a report is published, an address is not.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


#: What the report prints for the target when the guest's `status` probe
#: gave nothing. Never the ssh address: the report is what gets published.
TARGET_UNKNOWN = "(status probe returned nothing; the guest's os-release was not read)"


def target_from_status(status_output: str) -> str:
    """The guest's os-release line from `hammunition status`, minus the CLI's
    own `Target: ` label -- the report adds its own, and every report to
    2026-09-04 read `**Target:** Target: ...`."""
    first = status_output.strip().splitlines()[0].strip() if status_output.strip() else ""
    return first.removeprefix("Target:").strip() or TARGET_UNKNOWN


@dataclass(frozen=True)
class UnitResult:
    unit: str
    exit_code: int
    seconds: float
    tail: str
    entries: tuple[dict[str, Any], ...] = ()
    """The transaction-log lines this unit appended on the guest, parsed.
    Empty for a plan-time refusal (nothing is logged before execution) and
    for results filed before 2026-09-04."""
    new_packages: tuple[str, ...] = ()
    """What dpkg holds after this unit that it did not hold before --
    dependencies included, which the transaction log never names. `jtdx`
    brings `wsjtx-data`; only this delta knows."""

    @property
    def outcome(self) -> str:
        return OUTCOMES.get(self.exit_code, f"exit {self.exit_code}")

    @property
    def checks(self) -> tuple[dict[str, Any], ...]:
        """The D-031 re-probe's findings, from `transaction_end`."""
        return tuple(
            check
            for entry in self.entries
            if entry.get("event") == "transaction_end"
            for check in entry.get("checks", ())
        )

    @property
    def evidence(self) -> str:
        """What "confirmed" rested on, for the table. `no effect checks` is
        the honest reading of an exit 0 whose re-probe asked nothing."""
        if self.exit_code != 0:
            return ""
        if not self.checks:
            return "no effect checks"
        found = "; ".join(f"{c['kind']} {c['subject']} {c['detail']}" for c in self.checks)
        n = len(self.checks)
        return f"{n} check{'s' if n != 1 else ''}: {found}"

    @property
    def installed_packages(self) -> frozenset[str]:
        """Every package the guest gained from this unit: what its transaction
        asked apt for, what the re-probe confirmed, and what dpkg's before /
        after delta shows apt pulled in besides. What a later refusal may
        name."""
        names: set[str] = set()
        for entry in self.entries:
            if entry.get("event") == "transaction_begin":
                names.update(entry.get("apt_packages", ()))
        names.update(c["subject"] for c in self.checks if c.get("kind") == "package")
        names.update(self.new_packages)
        return frozenset(names)


@dataclass(frozen=True)
class Provenance:
    """What a reader needs to run the same campaign again.

    The commit alone was not it: the tree tar'd to the guest is the working
    tree, so a dirty checkout ships changes the commit does not name; the
    snapshot's creation time bounds what the guest's own packages were; and
    the apt lists resolution ran against are the ones `prepare` fetched,
    each dated by its InRelease.
    """

    engine_commit: str
    dirty_files: int
    domain: str | None
    snapshot: str | None
    snapshot_created: str | None
    apt_lists: tuple[tuple[str, str], ...]
    prepared_at: str | None

    def header_lines(self) -> list[str]:
        dirty = (
            f" (working tree dirty: {self.dirty_files} files not in that commit)"
            if self.dirty_files
            else ""
        )
        lines = [f"**Engine:** commit `{self.engine_commit}`{dirty}"]
        if self.domain and self.snapshot:
            created = f" (taken {self.snapshot_created})" if self.snapshot_created else ""
            lines.append(f"**VM:** `{self.domain}` reset to snapshot `{self.snapshot}`{created}")
        else:
            lines.append(
                "**VM:** not reset by this campaign — the guest held whatever state it "
                "had when the first unit ran"
            )
        if self.prepared_at:
            lines.append(f"**Prepared:** {self.prepared_at}")
        if self.apt_lists:
            when = " after prepare" if self.prepared_at else ", as found on the guest"
            lines.append(f"**Apt lists (InRelease dates{when}):**")
            lines += [f"- `{name}` — {date}" for name, date in self.apt_lists]
        return lines

    def to_record(self) -> dict[str, Any]:
        return {
            "record": "provenance",
            "engine_commit": self.engine_commit,
            "dirty_files": self.dirty_files,
            "domain": self.domain,
            "snapshot": self.snapshot,
            "snapshot_created": self.snapshot_created,
            "apt_lists": [list(pair) for pair in self.apt_lists],
            "prepared_at": self.prepared_at,
        }


# The runbook's "prepared" includes updated (vm-testing.md, baseline prep
# step 1), and a snapshot freezes the apt lists at the day it was taken. The
# archive does not wait: Parrot's clean-baseline was four days old when its
# lists still named glib2.0 2.84.4-3~deb13u3 and the pool had moved on, and
# six of fifteen profiles failed at the first fetch with a 404 (2026-09-03).
# So the lists are refreshed here, once per prepare, before anything is
# measured -- the engine's own ``--refresh`` would do it per unit, and the
# campaign is measuring the catalog, not the age of a snapshot. The retry
# loop is for a guest that runs its own apt at boot: Pop!_OS 24.04's did,
# and a prepare that started 30 s after the restore lost the lists lock to
# it (2026-09-04). ``DPkg::Lock::Timeout`` was the obvious fix and does not
# apply to the lists lock -- measured at 0 s against a held lock, apt 3.0.3
# -- so the wait is this loop, bounded at five minutes.
PREPARE_REMOTE = (
    "cd hammunition || exit 1; n=0; until sudo -n apt-get update -q; do "
    "n=$((n+1)); [ $n -ge 30 ] && exit 100; sleep 10; done; "
    "python3 -m venv .venv && .venv/bin/pip install -q -e . "
    "&& .venv/bin/hammunition --version"
)


def prepare(ssh: list[str], host: str, *, attempts: int = 2) -> None:
    """The venv and the engine on the guest, with the failure text kept.

    ``check=True`` with ``capture_output=True`` and nothing printed is how the
    Kali campaign died at profile 5 of 15 with a bare ``CalledProcessError``
    and no way to tell a PyPI hiccup from a broken guest (2026-09-03). The
    output is printed on every failure, and one retry covers the transient
    kind -- the same command succeeded by hand a minute later.
    """
    for attempt in range(1, attempts + 1):
        proc = subprocess.run(
            [*ssh, host, PREPARE_REMOTE], capture_output=True, text=True, check=False
        )
        if proc.returncode == 0:
            return
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
        print(
            f"prepare attempt {attempt}/{attempts} failed (exit {proc.returncode}):\n{tail}",
            flush=True,
        )
    sys.exit(f"{host} could not be prepared after {attempts} attempts; nothing was measured")


def snapshot_created(domain: str, snapshot: str) -> str | None:
    """When the snapshot was taken, from libvirt's own XML (`creationTime`,
    epoch seconds) -- `snapshot-info` does not print it. ``None`` when
    virsh cannot say, which the report shows rather than hides."""
    proc = subprocess.run(
        ["virsh", "--connect", "qemu:///system", "snapshot-dumpxml", domain, snapshot],
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"<creationTime>(\d+)</creationTime>", proc.stdout)
    if proc.returncode != 0 or not match:
        return None
    return datetime.fromtimestamp(int(match.group(1)), tz=UTC).isoformat()


#: One line per InRelease the guest holds: file name, then its `Date:`.
APT_LISTS_REMOTE = (
    'for f in /var/lib/apt/lists/*_InRelease; do [ -f "$f" ] || continue; '
    'printf "%s\\t%s\\n" "$(basename "$f")" "$(grep -m1 "^Date:" "$f" | cut -c7-)"; done'
)


def apt_lists(ssh: list[str], host: str) -> tuple[tuple[str, str], ...]:
    """The apt lists the guest resolves against, dated by their InRelease.
    Read after prepare, so they are the ones the units actually saw."""
    proc = subprocess.run(
        [*ssh, host, APT_LISTS_REMOTE], capture_output=True, text=True, check=False
    )
    pairs: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        name, _, date = line.partition("\t")
        if name:
            pairs.append((name, date.strip() or "(no Date field)"))
    return tuple(pairs)


def working_tree_dirty_files() -> int:
    """How many paths the tar'd tree carries that HEAD does not: modified,
    staged, or untracked-and-not-ignored. The commit in the header is only
    the truth when this is zero."""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    return len([ln for ln in proc.stdout.splitlines() if ln.strip()])


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
    prepare(ssh, host)


#: The engine's transaction log on the guest, as the operator the campaign
#: runs as (`hammunition.state.log.log_path`, XDG default). Not root's:
#: apt goes through `sudo -n` per command and the log follows the operator.
GUEST_LOG = "$HOME/.local/state/hammunition/transactions.jsonl"


def remote_command(unit: str, timeout: int) -> str:
    """The guest-side session for one unit, for ``bash -c``.

    Counts the transaction log's lines *before* the engine runs and prints
    everything after that count once it exits, behind a ``__LOG`` marker.
    That delta is what attributes log entries to this unit -- a plan-time
    refusal appends nothing and gets nothing. The same before/after is taken
    of dpkg's package list and the new names printed behind
    ``__NEW_PACKAGES``: the log names what the plan asked for, not what apt
    pulled in beside it. Single quotes are not usable here: the whole string
    is wrapped in them for ssh.
    """
    dpkg = 'dpkg-query -W -f "\\${Package}\\n" | sort -u'
    return (
        f"cd hammunition && L={GUEST_LOG}; "
        'before=0; [ -f "$L" ] && before=$(wc -l < "$L"); '
        f'P=$(mktemp); {dpkg} > "$P"; '
        f"timeout -k 30 {timeout}s "
        f".venv/bin/hammunition install {unit} --yes 2>&1 | tail -60; "
        f'echo "__EXIT=${{PIPESTATUS[0]}}"; echo __LOG; '
        '[ -f "$L" ] && tail -n +$((before+1)) "$L"; '
        f'echo __NEW_PACKAGES; {dpkg} | comm -13 "$P" -; rm -f "$P"; true'
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
    argv = list(SSH_BASE)
    if identity:
        argv += ["-i", identity]
    argv += [host, f"bash -c '{remote_command(unit, timeout)}'"]
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
    entries: list[dict[str, Any]] = []
    new_packages: list[str] = []
    section = "tail"
    for line in raw.splitlines():
        if line == "__LOG":
            section = "log"
        elif line == "__NEW_PACKAGES":
            section = "packages"
        elif section == "packages":
            if line.strip():
                new_packages.append(line.strip())
        elif section == "log":
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                # Filed, not dropped: a log line that is not JSON is itself
                # a finding about the engine's log.
                parsed = {"event": "unparsed", "line": line}
            entries.append(parsed)
        elif line.startswith("__EXIT="):
            exit_code = int(line.split("=", 1)[1])
        else:
            tail_lines.append(line)
    kept = tuple(entries)
    gained = tuple(new_packages)
    if exit_code == 124:
        return UnitResult(
            unit,
            124,
            seconds,
            f"stopped by the {timeout}s budget; the build was still running",
            kept,
            gained,
        )
    # Keep what a reader needs. Stderr outruns block-buffered stdout through
    # a pipe, so a failure's text can land ANYWHERE in the merged stream —
    # the first report buried every real error above the tail window. Prefer
    # the lines from the first failure marker; fall back to the last few.
    nonempty = [ln for ln in tail_lines if ln.strip()]
    markers = ("Failed:", "problem block", "error:", "E: ")
    start = next((i for i, ln in enumerate(nonempty) if any(m in ln for m in markers)), None)
    keep = nonempty[start : start + 10] if start is not None else nonempty[-6:]
    return UnitResult(unit, exit_code, seconds, "\n".join(keep), kept, gained)


def cumulative_refusals(results: list[UnitResult]) -> dict[str, dict[str, str]]:
    """Refusals that name a package an earlier unit of this pass installed.

    ``{refused unit: {package named: unit that installed it}}``. A pass
    accumulates state by design (one machine, like an operator's), and a
    refusal caused by that state is a fact about the pass, not about the
    unit: `wsjtx-improved` was refused on every target for colliding with
    the `wsjtx-data` that `wsjtx` had installed hours earlier, and that
    honest refusal hid the unit's own failure on a clean Kali (#24). The
    match is on whole package-name tokens in the refusal text.
    """
    installed_by: dict[str, str] = {}
    labelled: dict[str, dict[str, str]] = {}
    for result in results:
        if result.exit_code == 2:
            tokens = set(re.findall(r"[a-z0-9][a-z0-9+.-]*", result.tail.lower()))
            named = {pkg: unit for pkg, unit in installed_by.items() if pkg in tokens}
            if named:
                labelled[result.unit] = dict(sorted(named.items()))
        for pkg in result.installed_packages:
            installed_by.setdefault(pkg, result.unit)
    return labelled


def render_report(
    *,
    target_line: str,
    provenance: Provenance,
    results: list[UnitResult],
    noun: str = "Units",
    isolated: Mapping[str, UnitResult] | None = None,
    accumulating: bool = True,
) -> str:
    """The markdown summary. ``isolated`` holds the re-runs of cumulative
    refusals alone on the snapshot, keyed by unit. ``accumulating`` is
    false for a ``--reset-each`` pass, where no unit sees another's state
    and nothing may be labelled as if it had."""
    isolated = isolated or {}
    ok = [r for r in results if r.exit_code == 0]
    unchecked = [r for r in ok if not r.checks]
    refused = [r for r in results if r.exit_code == 2]
    cumulative = cumulative_refusals(results) if accumulating else {}
    # A consent gate declining on a non-interactive stdin is the gate working
    # (D-021): the campaign never affirms one. It is neither a failure nor
    # coverage the engine lacks, so it gets its own count and no failure tail.
    declined = [r for r in results if r.exit_code == 3]
    stopped = [r for r in results if r.exit_code == 124]
    failed = [r for r in results if r.exit_code not in (0, 2, 3, 124)]
    budget = f", {len(stopped)} stopped by the budget" if stopped else ""
    gated = f", {len(declined)} stopped at a consent gate" if declined else ""
    caused = f" ({len(cumulative)} of them cumulative)" if cumulative else ""
    blind = f" ({len(unchecked)} by no effect check)" if unchecked else ""
    lines = [
        "# VM campaign report",
        "",
        f"**Date:** {datetime.now(UTC).date().isoformat()}",
        *provenance.header_lines(),
        f"**Target:** {target_line}",
        f"**{noun}:** {len(results)} — "
        f"{len(ok)} installed+confirmed{blind}, {len(refused)} refused at plan time{caused}, "
        f"{len(failed)} failed{gated}{budget}",
        "",
        "Exit 0 is the engine's own bar: completed *and confirmed* by re-probe",
        "(D-031); *Confirmed by* is what that re-probe found, and `no effect",
        "checks` means it asked nothing. A plan-time refusal is honest coverage",
        "reporting, not a failure — its text names what is missing. A refusal",
        "marked *cumulative* names a package an earlier unit of this same pass",
        "installed; it is a fact about the pass, and the unit is re-run alone.",
        "",
        "| Name | Outcome | Confirmed by | Seconds |",
        "|---|---|---|---:|",
    ]

    def outcome_cell(r: UnitResult) -> str:
        cell = r.outcome
        if r.unit in cumulative:
            named = ", ".join(
                f"`{pkg}`, installed by `{unit}`" for pkg, unit in cumulative[r.unit].items()
            )
            cell += f" — cumulative: names {named} earlier this pass"
        alone = isolated.get(r.unit)
        if alone is not None and provenance.snapshot:
            cell += f"; alone on `{provenance.snapshot}`: {alone.outcome} ({alone.seconds:.0f} s)"
        return cell

    for r in results:
        lines.append(f"| `{r.unit}` | {outcome_cell(r)} | {r.evidence} | {r.seconds:.0f} |")
    buckets = (
        ("Failures", failed),
        ("Stopped by the budget (not a verdict; rerun with a larger --timeout)", stopped),
        ("Plan-time refusals", refused),
        ("Consent gates presented (the campaign affirms none, D-021)", declined),
    )
    for title, bucket in buckets:
        if not bucket:
            continue
        lines += ["", f"## {title}", ""]
        for r in bucket:
            lines += [f"### `{r.unit}`", "", "```", r.tail, "```", ""]
    if isolated and provenance.snapshot:
        lines += [
            "",
            f"## Re-run alone on `{provenance.snapshot}`",
            "",
            "Each cumulative refusal above, installed by itself on the freshly",
            "restored snapshot. This is the verdict a clean machine gives.",
            "",
        ]
        for unit, alone in isolated.items():
            lines += [
                f"### `{unit}` — {alone.outcome} ({alone.seconds:.0f} s)",
                "",
                *([f"Confirmed by: {alone.evidence}", ""] if alone.evidence else []),
                "```",
                alone.tail,
                "```",
                "",
            ]
    if unchecked:
        lines += [
            "",
            f"## Confirmed by no effect check ({len(unchecked)})",
            "",
            "The engine exited 0 and its re-probe had nothing to ask: no archive",
            "package, no built binary, no group membership in the plan. These are",
            "not failures; they are the units whose `confirmed` rests on exit",
            "codes alone, which D-031 says is not evidence. An engine that probes",
            "their effects (launchers, installed trees) would move them out of here.",
            "",
            *[f"- `{r.unit}`" for r in unchecked],
        ]
    return "\n".join(lines) + "\n"


def evidence_path(out: Path) -> Path:
    """`campaign.md` → `campaign.evidence.jsonl`, beside it."""
    return out.with_name(out.stem + ".evidence.jsonl")


def write_evidence(
    path: Path,
    *,
    provenance: Provenance,
    results: list[UnitResult],
    isolated: Mapping[str, UnitResult] | None = None,
) -> None:
    """The complete record: provenance, one line per unit with every
    transaction entry it appended, then the isolated re-runs. Rewritten
    whole with the report after every unit."""

    def unit_record(kind: str, r: UnitResult) -> dict[str, Any]:
        return {
            "record": kind,
            "unit": r.unit,
            "exit_code": r.exit_code,
            "outcome": r.outcome,
            "seconds": r.seconds,
            "tail": r.tail,
            "entries": list(r.entries),
            "new_packages": list(r.new_packages),
        }

    records = [provenance.to_record()]
    records += [unit_record("unit", r) for r in results]
    records += [unit_record("isolated", r) for r in (isolated or {}).values()]
    path.write_text("".join(json.dumps(rec, sort_keys=True) + "\n" for rec in records))


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
    parser.add_argument(
        "--reset-first",
        metavar="DOMAIN",
        default=None,
        help="libvirt domain to restore to clean-baseline and prepare once, before the campaign",
    )
    args = parser.parse_args()
    if args.reset_each and args.reset_first:
        parser.error("--reset-each already resets before the first unit; drop --reset-first")

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

    ssh = [*SSH_BASE, *(["-i", args.identity] if args.identity else [])]
    domain = args.reset_first or args.reset_each
    prepared_at: str | None = None
    if args.reset_first:
        reset_and_prepare(args.reset_first, args.host, args.identity)
        prepared_at = datetime.now(UTC).isoformat(timespec="seconds")

    # The guest's own os-release line, from the engine that ran there. The
    # ssh address is deliberately not the fallback: the report is published.
    target_probe = target_from_status(
        subprocess.run(
            [
                *ssh,
                args.host,
                "cd hammunition && .venv/bin/hammunition status 2>/dev/null | head -1",
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    )
    provenance = Provenance(
        engine_commit=commit,
        dirty_files=working_tree_dirty_files(),
        domain=domain,
        snapshot="clean-baseline" if domain else None,
        snapshot_created=snapshot_created(domain, "clean-baseline") if domain else None,
        apt_lists=apt_lists(ssh, args.host),
        prepared_at=prepared_at,
    )
    noun = "Profiles (whole, from clean-baseline)" if args.whole_profiles else "Units"

    results: list[UnitResult] = []
    isolated: dict[str, UnitResult] = {}

    def report_so_far() -> str:
        return render_report(
            target_line=target_probe,
            provenance=provenance,
            results=results,
            noun=noun,
            isolated=isolated,
            accumulating=not args.reset_each,
        )

    def file_so_far() -> None:
        # The report is rewritten after every unit, so a campaign that dies
        # at unit 5 of 15 leaves the four results it had, and a failure's
        # tail is readable while the next unit builds instead of hours later.
        if args.out:
            args.out.write_text(report_so_far())
            write_evidence(
                evidence_path(args.out), provenance=provenance, results=results, isolated=isolated
            )

    for unit in units:
        print(f"[{len(results) + 1}/{len(units)}] {unit} ...", flush=True)
        if args.reset_each:
            reset_and_prepare(args.reset_each, args.host, args.identity)
        result = run_unit(args.host, args.identity, unit, args.timeout)
        print(f"    {result.outcome} ({result.seconds:.0f}s)", flush=True)
        results.append(result)
        file_so_far()

    # A refusal the pass itself caused says nothing about the unit. With a
    # snapshot to hand, ask the clean machine -- one restore per such unit,
    # after the pass, so the pass's own accumulation is not disturbed.
    cumulative = cumulative_refusals(results) if not args.reset_each else {}
    if cumulative and args.reset_first:
        for unit in cumulative:
            print(f"[alone on clean-baseline] {unit} ...", flush=True)
            reset_and_prepare(args.reset_first, args.host, args.identity)
            isolated[unit] = run_unit(args.host, args.identity, unit, args.timeout)
            print(f"    {isolated[unit].outcome} ({isolated[unit].seconds:.0f}s)", flush=True)
            file_so_far()
    elif cumulative:
        print(
            f"{len(cumulative)} cumulative refusal(s) not re-run alone: no snapshot "
            f"(pass --reset-first DOMAIN): {', '.join(cumulative)}",
            flush=True,
        )

    if args.out:
        print(f"wrote {args.out} and {evidence_path(args.out)}")
    else:
        print(report_so_far())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
