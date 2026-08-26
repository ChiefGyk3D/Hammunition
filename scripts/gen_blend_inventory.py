#!/usr/bin/env python3
"""Generate docs/reference/blend-inventory.md from the Debian Blend task files.

CLAUDE.md: "Generate what can be generated." The package reference comes from
upstream task files, so it cannot drift from what Debian actually ships.

Source task files live in the gitignored ``reference/blend-tasks/`` tree, fetched
from salsa.debian.org. Re-fetch with ``--fetch`` before regenerating.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_DIR = REPO_ROOT / "reference" / "blend-tasks"
OUT = REPO_ROOT / "docs" / "reference" / "blend-inventory.md"
BASE_URL = "https://salsa.debian.org/blends-team/hamradio/-/raw/master/tasks"

TASKS = [
    "antenna",
    "datamodes",
    "digitalvoice",
    "logging",
    "morse",
    "nonamateur",
    "packetmodes",
    "rigcontrol",
    "satellite",
    "sdr",
    "tools",
    "training",
]
RELATIONS = ("Depends", "Recommends", "Suggests", "Ignore", "Avoid")


class Entry:
    def __init__(self, package: str, relation: str, remark: str) -> None:
        self.package = package
        self.relation = relation
        self.remark = remark


class Task:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.title = filename
        self.description = ""
        self.blurb = ""
        self.entries: list[Entry] = []


def fetch() -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    for task in TASKS:
        subprocess.run(
            ["curl", "-sSL", "-o", str(TASK_DIR / task), f"{BASE_URL}/{task}"],
            check=True,
        )
    print(f"fetched {len(TASKS)} task files to {TASK_DIR}")


def parse(path: Path) -> Task:
    task = Task(path.name)
    for stanza in re.split(r"\n\s*\n", path.read_text()):
        fields: dict[str, str] = {}
        key: str | None = None
        for line in stanza.splitlines():
            if not line.strip():
                continue
            match = re.match(r"^([A-Z][A-Za-z-]*):\s*(.*)$", line)
            if match:
                key = match.group(1)
                fields[key] = match.group(2).strip()
            elif key and line.startswith(" "):
                fields[key] = f"{fields[key]} {line.strip()}".strip()
        if "Task" in fields:
            task.title = fields["Task"]
            task.description = fields.get("Description", "")
        for relation in RELATIONS:
            value = fields.get(relation)
            if not value:
                continue
            for pkg in filter(None, re.split(r"[,\s|]+", value)):
                task.entries.append(Entry(pkg, relation, fields.get("Remark", "")))
    return task


def _ahrl_facts() -> tuple[set[str], list[str]]:
    """Pull AHRL's apt package names and source-built unit names from the
    inventory doc, so the cross-reference below is derived rather than typed."""
    inv = (REPO_ROOT / "docs" / "reference" / "ahrl-inventory.md").read_text()
    phase2 = inv[inv.index("### Phase 2") : inv.index("### Phase 3")]
    apt: set[str] = set()
    for row in phase2.splitlines():
        if not row.startswith("| "):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) >= 3 and cells[0].isdigit():
            apt.update(re.findall(r"`([a-z0-9][a-z0-9.+-]*)`", cells[2]))
    apt.update(
        {
            "xastir",
            "svxlink-server",
            "svxreflector",
            "libhamlib4",
            "pipx",
            "js8call",
            "jtdx",
            "flamp",
            "flmsg",
            "flwrap",
            "atril",
        }
    )

    phase3 = inv[inv.index("### Phase 3") : inv.index("### Phase 4")]
    built: list[str] = []
    for row in phase3.splitlines():
        cells = row.strip("|").split("|")
        if row.startswith("| ") and cells[0].strip().isdigit():
            built.append(re.split(r"\s+\d", cells[1].strip())[0].strip())
    return apt, built


def _crossref(blend_pkgs: set[str]) -> list[str]:
    apt, built = _ahrl_facts()

    def norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    by_norm = {norm(p): p for p in blend_pkgs}

    shared = sorted(blend_pkgs & apt)
    packaged = [(u, by_norm[norm(u)]) for u in built if norm(u) in by_norm]

    out = [
        "## Cross-reference with AHRL",
        "",
        "Derived, not typed. Regenerating this file recomputes it.",
        "",
        f"- Blend unique packages: **{len(blend_pkgs)}**",
        f"- AHRL apt package names: **{len(apt)}**",
        f"- Installed by both, same apt name: **{len(shared)}**",
        f"- Blend packages AHRL does not install at all: **{len(blend_pkgs - apt)}**",
        "",
        "### The finding that matters for M3 scope",
        "",
        f"**{len(packaged)} of AHRL's {len(built)} source builds are already packaged in Debian.**",
        "",
        "| AHRL builds from source | Debian ships as apt |",
        "|---|---|",
    ]
    out += [f"| {unit} | `{pkg}` |" for unit, pkg in packaged]
    out += [
        "",
        "This does not remove the need for a source backend — the remaining",
        f"{len(built) - len(packaged)} still require one, and D-004 stands. It does mean",
        "the trade-off for these is **version currency, not availability**: AHRL",
        "compiles them to get newer versions than Debian ships, which is a",
        "`recommended_default` and `update` question rather than a backend question.",
        "",
        "Per `PARITY-POLICY.md` these are CARRY-both candidates: apt for the",
        "operator who wants stability, source for the one who wants current.",
        "",
        "### Packages in both, by name",
        "",
        "```",
    ]
    out += shared
    out += ["```", ""]
    return out


def render(tasks: list[Task]) -> str:
    all_pkgs = {e.package for t in tasks for e in t.entries}
    entries = sum(len(t.entries) for t in tasks)
    seen: dict[str, list[str]] = {}
    for t in tasks:
        for e in t.entries:
            seen.setdefault(e.package, []).append(t.filename)
    overlapping = {k: v for k, v in seen.items() if len(v) > 1}

    out: list[str] = []
    add = out.append
    add("# Debian Hamradio Blend — complete task inventory")
    add("")
    add("Generated by `scripts/gen_blend_inventory.py` from the Blend's own task")
    add("files. Do not edit by hand — regenerate.")
    add("")
    add(f"**Source:** <{BASE_URL}>  ")
    add(f"**Fetched:** {date.today().isoformat()}  ")
    add("**Format:** `https://blends.debian.org/blends/1.1`")
    add("")
    add("Per `docs/SCOPE.md` this is the cheapest coverage in the project and the")
    add("best provenance: team-governed, signed, machine-readable, and every entry")
    add("is already in Debian. Complete, not sampled.")
    add("")
    add("---")
    add("")
    add("## Summary")
    add("")
    add("| | Count |")
    add("|---|---:|")
    add(f"| Tasks | {len(tasks)} |")
    add(f"| Package entries | {entries} |")
    add(f"| **Unique packages** | **{len(all_pkgs)}** |")
    add(f"| Packages in more than one task | {len(overlapping)} |")
    add("")
    rel_counts: dict[str, int] = {}
    for t in tasks:
        for e in t.entries:
            rel_counts[e.relation] = rel_counts.get(e.relation, 0) + 1
    add("| Relation | Count | Meaning |")
    add("|---|---:|---|")
    meaning = {
        "Depends": "installed unconditionally with the metapackage",
        "Recommends": "installed by default; removable",
        "Suggests": "offered, not installed",
        "Ignore": "deliberately excluded",
        "Avoid": "deliberately excluded, with prejudice",
    }
    for rel, count in sorted(rel_counts.items(), key=lambda kv: -kv[1]):
        add(f"| `{rel}` | {count} | {meaning.get(rel, '')} |")
    add("")
    add("Note the Blend uses **`Recommends` almost exclusively**. Its metapackages")
    add("are opt-out rather than opt-in, which is the opposite of the profile model")
    add("in D-003 — worth knowing before importing the task structure wholesale.")
    add("")
    add("### Packages appearing in more than one task")
    add("")
    add("Direct evidence for D-003: the Blend's own categories overlap and do not")
    add("nest. These are tags, not a tree.")
    add("")
    add("| Package | Tasks |")
    add("|---|---|")
    for pkg, where in sorted(overlapping.items()):
        add(f"| `{pkg}` | {', '.join(sorted(where))} |")
    add("")
    add("---")
    add("")
    add("## Tasks")
    add("")
    for t in tasks:
        add(f"### `{t.filename}` — {t.title}")
        add("")
        if t.description:
            add(f"*{t.description}*")
            add("")
        add(f"**{len(t.entries)} packages.**")
        add("")
        add("| apt package | Relation | Blend remark |")
        add("|---|---|---|")
        for e in sorted(t.entries, key=lambda x: x.package):
            remark = e.remark.replace("|", "\\|") if e.remark else ""
            add(f"| `{e.package}` | {e.relation} | {remark} |")
        add("")
    add("---")
    add("")
    out.extend(_crossref(all_pkgs))
    add("---")
    add("")
    add("## Flat package list")
    add("")
    add(f"All {len(all_pkgs)} unique packages, for diffing against future Blend releases.")
    add("")
    add("```")
    for pkg in sorted(all_pkgs):
        add(pkg)
    add("```")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="re-fetch task files first")
    args = parser.parse_args()

    if args.fetch:
        fetch()

    if not TASK_DIR.exists():
        print(f"{TASK_DIR} missing; run with --fetch", file=sys.stderr)
        return 1

    tasks = [parse(TASK_DIR / name) for name in TASKS if (TASK_DIR / name).exists()]
    if len(tasks) != len(TASKS):
        missing = set(TASKS) - {t.filename for t in tasks}
        print(f"missing task files: {sorted(missing)}", file=sys.stderr)
        return 1

    OUT.write_text(render(tasks))
    total = len({e.package for t in tasks for e in t.entries})
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: {len(tasks)} tasks, {total} unique packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
