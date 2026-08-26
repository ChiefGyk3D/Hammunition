#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/profile-sizing.md.

`SCOPE.md`: *"Profile design **is** the user experience."* This sizes every
proposed profile before it is built, so the unusable ones are found on paper
rather than by a user waiting on an install.

All five sources are now measured, so nothing here is an estimate of an
estimate:

* Blend task membership and per-task counts — parsed from `blend-inventory.md`
* Blend installability on stable — parsed from the container probe
* AHRL and 73Linux survivors — parsed from `dispositions.md`
* Skywave delta — parsed from `skywave-inventory.md`
* DragonOS Tier 1 — parsed from `dragonos-tier1-inventory.md`

The **profile proposals and their names** are the curated part and live in
`PROFILES` below. Names are user-facing and hard to change later, so they are
argued in the generated document rather than asserted.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REF = REPO_ROOT / "docs" / "reference"
PROBES = REPO_ROOT / "reference" / "probes"
OUT = REF / "profile-sizing.md"

THRESHOLD = 80


class Profile:
    """One proposed profile. `blend` names Blend tasks it absorbs in full."""

    def __init__(
        self,
        name: str,
        headline: str,
        blend: tuple[str, ...],
        blend_partial: int,
        other: int,
        rationale: str,
        stage: str = "1.0",
    ) -> None:
        self.name = name
        self.headline = headline
        self.blend = blend
        self.blend_partial = blend_partial
        self.other = other
        self.rationale = rationale
        self.stage = stage


# Proposed profile set. `blend_partial` is packages drawn from Blend tasks that
# the profile does NOT absorb whole; `other` is AHRL + 73Linux + Skywave +
# DragonOS Tier 1 contributions, attributed by disposition and menu category.
PROFILES = [
    Profile(
        "station",
        "Station essentials",
        ("rigcontrol", "tools"),
        0,
        6,
        "What every station needs before it can do anything else: rig control, "
        "hamlib, propagation-free basics, the tools that other profiles assume.",
    ),
    Profile(
        "logging",
        "Contest and DX logging",
        ("logging",),
        0,
        4,
        "Most operators want one logger, not nine. Splitting it out means the "
        "choice is visible and the default is stated.",
    ),
    Profile(
        "morse",
        "CW and Morse training",
        ("morse", "training"),
        0,
        2,
        "Self-contained, and its two Blend tasks already overlap heavily. "
        "Nobody needs it to make a digital contact.",
    ),
    Profile(
        "propagation",
        "Propagation and spotting",
        (),
        6,
        12,
        "Clocks, cluster clients, grid tools, beacon monitors. Genuinely "
        "optional and heavy on web-service dependencies, so it is the first "
        "thing a low-bandwidth or offline station wants to skip.",
    ),
    Profile(
        "digital-modes",
        "FT8, JS8 and the digital modes",
        ("datamodes", "digitalvoice"),
        0,
        22,
        "The reason most people install something like this. Wide but coherent.",
    ),
    Profile(
        "packet",
        "Packet, Winlink and EMCOMM",
        ("packetmodes",),
        0,
        12,
        "The 73Linux delta lands here whole. AHRL has none of it.",
    ),
    Profile(
        "satellite",
        "Satellites and weather imaging",
        ("satellite",),
        0,
        5,
        "Small. SatDump carries most of the weight now that the APT decoders are retired.",
    ),
    Profile(
        "antenna",
        "Antennas and modelling",
        ("antenna",),
        0,
        8,
        "NEC modelling, coverage prediction, analyser tooling.",
    ),
    Profile(
        "sdr",
        "SDR receivers and device support",
        ("sdr",),
        0,
        6,
        "Large, and a third of the Blend's `sdr` task is per-hardware Soapy "
        "modules a one-dongle user does not need. See the hardware-detection note.",
    ),
    Profile(
        "listening",
        "Shortwave and utility listening",
        ("nonamateur",),
        0,
        11,
        "The Skywave delta lands here. Works with no transmitter and no "
        "licence, which makes it the best on-ramp we have.",
    ),
    Profile(
        "electronics",
        "Bench and electronics",
        (),
        0,
        6,
        "KiCad, gerbv, spice. Fine software; not radio. Opt-in, per the "
        "PARITY-POLICY question reserved to the maintainer.",
    ),
    Profile(
        "rf-security",
        "RF security and spectrum analysis",
        (),
        0,
        14,
        "DragonOS Tier 1, opt-in, with the legal framing CLAUDE.md requires. "
        "Its final shape depends on Q-008.",
    ),
    Profile(
        "rf-research",
        "Transmit-capable and interception-capable RF tooling",
        (),
        0,
        1,
        "Consent-gated (**D-021**). Contents provisional pending **Q-008** — the "
        "receive-only subset only, with transmit-capable cellular stacks excluded.",
        "post-1.0",
    ),
    Profile(
        "rfid",
        "RFID and NFC",
        (),
        0,
        3,
        "Proposed in **Q-010**. Different domain, different range, different skills — "
        "and nothing is packaged on any target, so it needs the source backend first.",
        "post-1.0",
    ),
    Profile(
        "workstation",
        "Editor, terminal and bench tooling",
        (),
        0,
        9,
        "Proposed in **Q-011**. Not radio software; a lab machine needs it and the "
        "VS Code manifest has nowhere else to live. Deliberately boring, to stay small.",
        "post-1.0",
    ),
    Profile("mesh", "Mesh and LoRa", (), 0, 8, "Meshtastic, Reticulum. Post-1.0.", "post-1.0"),
    Profile(
        "uconsole",
        "ClockworkPi uConsole",
        (),
        0,
        5,
        "Hardware-specific: display, audio routing, power. Post-1.0.",
        "post-1.0",
    ),
]


def _read(name: str) -> str:
    path = REF / name
    if not path.exists():
        sys.exit(f"missing {path}; generate it first")
    return path.read_text()


def blend_tasks() -> dict[str, list[str]]:
    body = _read("blend-inventory.md")
    tasks_section = body[body.index("## Tasks") :]
    tasks: dict[str, list[str]] = {}
    current = ""
    for line in tasks_section.splitlines():
        head = re.match(r"^### `([a-z]+)`", line)
        if head:
            current = head.group(1)
            tasks[current] = []
            continue
        row = re.match(r"^\| `([a-z0-9][a-z0-9.+-]*)` \| (?:Recommends|Suggests|Depends)", line)
        if row and current:
            tasks[current].append(row.group(1))
    return tasks


def probe(name: str) -> dict[str, str]:
    path = PROBES / name
    if not path.exists():
        return {}
    return {
        k.strip(): v.strip()
        for k, _, v in (line.partition("\t") for line in path.read_text().splitlines())
        if v
    }


def dispositions() -> dict[str, tuple[int, int]]:
    body = _read("dispositions.md")
    out: dict[str, tuple[int, int]] = {}

    def count(cell: str) -> int:
        return int(cell) if cell.isdigit() else 0

    for line in body[body.index("## Summary") :].splitlines():
        cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        # A disposition row is 4 cells and has a number in at least one of the
        # two source columns. An em dash means "not applicable to this source",
        # which is why testing only the first column silently dropped ADD.
        if len(cells) == 4 and (cells[1].isdigit() or cells[2].isdigit()):
            out[cells[0]] = (count(cells[1]), count(cells[2]))
        if line.startswith("| **Total**"):
            break
    for required in ("CARRY", "SUPERSEDE", "REVIVE", "ADD"):
        if required not in out:
            sys.exit(f"dispositions.md summary is missing the {required} row")
    return out


def measured_count(doc: str, pattern: str) -> int:
    match = re.search(pattern, _read(doc))
    if not match:
        sys.exit(f"could not read the measured count out of {doc} using {pattern!r}")
    return int(match.group(1))


def render() -> str:
    tasks = blend_tasks()
    stable = probe("blend-debian-13.tsv")
    unstable = probe("blend-debian-sid.tsv")
    disp = dispositions()
    skywave_delta = measured_count(
        "skywave-inventory.md", r"\*\*Delta — new coverage for us\*\* \| \*\*(\d+)\*\*"
    )
    dragon_t1 = measured_count(
        "dragonos-tier1-inventory.md", r"apt or upstream `\.deb` \| (\d+) \|"
    )

    unique = {p for pkgs in tasks.values() for p in pkgs}
    absent_stable = sorted(p for p in unique if stable.get(p, "-") == "-")

    ahrl_alive = sum(disp.get(k, (0, 0))[0] for k in ("CARRY", "SUPERSEDE", "REVIVE"))
    delta_alive = sum(disp.get(k, (0, 0))[1] for k in ("CARRY", "ADD"))

    def task_size(task: str, on_stable: bool = False) -> int:
        pkgs = tasks.get(task, [])
        if on_stable:
            return sum(1 for p in pkgs if stable.get(p, "-") != "-")
        return len(pkgs)

    def profile_pkgs(names: tuple[str, ...]) -> set[str]:
        """Union, not sum. Two Blend tasks in one profile can share packages —
        `morse` and `training` share five — and counting those twice would
        inflate exactly the profile the split is meant to right-size."""
        return {p for t in names for p in tasks.get(t, [])}

    rows = []
    for p in PROFILES:
        pkgs = profile_pkgs(p.blend)
        blend_n = len(pkgs) + p.blend_partial
        blend_stable = sum(1 for q in pkgs if stable.get(q, "-") != "-") + p.blend_partial
        total = blend_n + p.other
        rows.append((p, blend_n, blend_stable, total))

    over = [r for r in rows if r[3] > THRESHOLD]

    out: list[str] = []
    add = out.append
    add("# Profile sizing across the five-source union")
    add("")
    add("Generated by `scripts/gen_profile_sizing.py`. Do not edit by hand —")
    add("regenerate. Every number below is derived from a measured inventory; the")
    add("profile set and its **names** are the curated part and are argued rather")
    add("than asserted.")
    add("")
    add(f"**Generated:** {date.today().isoformat()}  ")
    add(f"**Split threshold:** anything over **{THRESHOLD}** packages is flagged")
    add("")
    add("---")
    add("")
    add("## Measured inputs — all five sources, no estimates left")
    add("")
    add("| Source | Basis | Units |")
    add("|---|---|---:|")
    add(f"| Debian Blend | `blend-inventory.md`, {len(tasks)} tasks | **{len(unique)}** unique |")
    add(
        f"| Blend, installable on Debian 13 | container probe | **{len(unique) - len(absent_stable)}** |"
    )
    add(f"| AHRL survivors | `dispositions.md` — CARRY + SUPERSEDE + REVIVE | **{ahrl_alive}** |")
    add(f"| 73Linux delta survivors | `dispositions.md` — CARRY + ADD | **{delta_alive}** |")
    add(f"| Skywave delta | `skywave-inventory.md` | **{skywave_delta}** |")
    add(f"| DragonOS Tier 1 | `dragonos-tier1-inventory.md` | **{dragon_t1}** |")
    add("")
    add(
        INPUTS_NOTE.format(
            upper=len(unique) + ahrl_alive + delta_alive + skywave_delta + dragon_t1,
            absent=len(absent_stable),
            absent_list=", ".join(f"`{p}`" for p in absent_stable),
            sid_absent=", ".join(f"`{p}`" for p in absent_stable if unstable.get(p, "-") == "-")
            or "none",
        )
    )
    add("")
    add("---")
    add("")
    add("## Sizing")
    add("")
    add("`Blend` counts task membership; `on stable` is how many of those actually")
    add("install on Debian 13. `Other` is AHRL, 73Linux, Skywave and DragonOS Tier 1")
    add("attributed by disposition and menu category — the one estimated column, and")
    add("estimated from measured survivor lists rather than from guesses.")
    add("")
    add("| Profile | Blend tasks | Blend | on stable | Other | **Total** | Verdict |")
    add("|---|---|---:|---:|---:|---:|---|")
    for p, blend_n, blend_stable, total in rows:
        tasks_cell = ", ".join(f"`{t}`" for t in p.blend) or "—"
        if p.blend_partial:
            tasks_cell += f" + {p.blend_partial} partial"
        verdict = "⚠️ **split**" if total > THRESHOLD else ("post-1.0" if p.stage != "1.0" else "✅")
        gap = f"{blend_stable}" + (" ⚠️" if blend_stable < blend_n else "")
        add(
            f"| `{p.name}` | {tasks_cell} | {blend_n} | {gap} | {p.other} | "
            f"**{total}** | {verdict} |"
        )
    add("")
    if over:
        add("**Over threshold:** " + ", ".join(f"`{r[0].name}`" for r in over))
    else:
        add(
            f"**No profile exceeds {THRESHOLD}.** That is the point of the split "
            "proposed below, not an accident."
        )
    add("")
    add("---")
    add("")
    add("## Naming — the actual deliverable")
    add("")
    add(NAMING)
    add("")
    add("### The proposed set")
    add("")
    add("| `name` | What the operator reads | Why this name |")
    add("|---|---|---|")
    for p in PROFILES:
        stage = "" if p.stage == "1.0" else f" *({p.stage})*"
        add(f"| `{p.name}`{stage} | **{p.headline}** | {p.rationale} |")
    add("")
    add("---")
    add("")
    add("## The `ham-core` split")
    add("")
    add(HAM_CORE_SPLIT)
    add("")
    add("---")
    add("")
    add("## The `sigint` split")
    add("")
    add(SIGINT_SPLIT)
    add("")
    add("---")
    add("")
    add("## Notes that affect sizing")
    add("")
    add(
        NOTES.format(
            sdr_total=task_size("sdr"),
            soapy=(
                soapy := sum(1 for p in tasks.get("sdr", []) if p.startswith("soapysdr-module-"))
            ),
            soapy_minus_one=soapy - 1,
            logging_total=task_size("logging"),
            logging_stable=task_size("logging", True),
            logging_missing=f"{task_size('logging') - task_size('logging', True)} packages",
        )
    )
    add("")
    return "\n".join(out) + "\n"


INPUTS_NOTE = """\
**Union upper bound: ~{upper} units** before de-duplication. Profiles are **flat
tags with overlap** (**D-003**), so the same package appears in several profiles
and the per-profile totals deliberately sum to more than the union.

**{absent} Blend packages do not install on Debian 13:** {absent_list}. All but
{sid_absent} are in unstable, so most is release lag — but a user installing
today on a stable base does not get them. Per **D-005**, coverage counts only
where it installs, so the `on stable` column below is the honest one."""

NAMING = """\
Profile names are the first thing an operator reads and effectively permanent
once published — they appear in `hammunition install <name>`, in documentation,
in forum posts, and in other people's shell history. Renaming one later breaks
all of that. So the names are argued here.

**Four rules, applied consistently.**

1. **Name the activity, not the package set.** An operator knows they want to
   work satellites; they do not know they want `gpredict` plus `satdump`. Every
   name below is something a person would say out loud about their own station.
2. **No adjectives, no size words.** `ham-core`, `ham-extra`, `ham-full` describe
   *our* packaging decisions, not the operator's intent, and they force a reader
   to learn our taxonomy before they can choose. `core` in particular is a claim
   about importance that ages badly the moment someone disagrees with it.
3. **One word where one word works.** `packet`, `satellite`, `antenna`,
   `logging`, `morse`, `sdr`, `listening`, `mesh`. Hyphenate only when a single
   word would be ambiguous — `digital-modes`, `rf-security`.
4. **Say what it is, not what it is not.** `nonamateur` is the Blend's name for
   the task we map to `listening`; it defines a category by exclusion, which
   tells a newcomer nothing.

**Two names are deliberately not what you might expect.**

**`station`, not `ham-core`.** `core` is the packaging word this project was
built to avoid — it invites "what's not core?" and makes everything else feel
optional-in-a-bad-way. `station` is what an operator calls the thing they are
building. `hammunition install station` reads as a sentence. It also survives the
split cleanly: `station` is what every station needs, and `logging`, `morse` and
`propagation` are things *some* stations want, which is exactly true.

**`rf-security`, not `sigint`.** Three reasons, in order of weight.

- **It is what CLAUDE.md already calls it.** The docs section is
  `docs/rf-security/`, the security requirement says *"RF-security tooling lives
  in its own profile requiring explicit opt-in"*. Using a different word in the
  CLI than in the documentation is a defect.
- **SIGINT is a term of art with a specific meaning** — signals intelligence, as
  practised by states. Most of what this profile contains is Wi-Fi auditing,
  Bluetooth sniffing, ISM decoding and protocol analysis. Calling that SIGINT
  overclaims what the tools do and mis-sets expectations in both directions.
- **It reads better on a shared machine.** This runs alongside offensive tooling
  on people's work laptops. `rf-security` describes a discipline; `sigint`
  describes an intelligence function, and the difference matters to whoever reads
  the operator's screen over their shoulder.

**One name is held back.** `cellular` is proposed but not defined, pending
**Q-008**. Naming a profile before deciding what goes in it is how you end up
renaming it."""

HAM_CORE_SPLIT = """\
The previous sizing put `ham-core` at ~62 — under the threshold, but the worst
profile to get wrong, because it is what a new user installs first and it forms
their impression of the whole project.

It was large because it absorbed five Blend tasks at once. Split four ways:

| Profile | Absorbs | Why it is a coherent thing to name |
|---|---|---|
| `station` | `rigcontrol`, `tools` | The floor. Rig control, hamlib, the utilities everything else assumes. Installs fast, contains no surprises. |
| `logging` | `logging` | An operator wants *a* logger. Nine is a menu, not a feature. Splitting makes the default an explicit, documented choice. |
| `morse` | `morse`, `training` | Already self-contained — the two Blend tasks overlap by five packages and by nothing else. |
| `propagation` | AHRL's HF_Propagation cluster | Clocks, cluster clients, grid and beacon tools. Optional, and the heaviest user of external web services in the catalog. |

Each of the four passes the test a profile should pass: an operator can name it
without being told what is in it, and can explain why they do or do not want it.

**`station` is the one to keep small.** Everything that gets added to it is
something a first-time user did not ask for and has to wait through."""

SIGINT_SPLIT = """\
`rf-security` measures well under the threshold, so this is not a size problem.
It is a **kind** problem, and **Q-008** is the open question.

The DragonOS Tier 1 inventory found that the units divide by *transmit*, not by
topic:

| Group | Contents | Character |
|---|---|---|
| Analysis and audit | `wireshark`, `aircrack-ng`, `hcxdumptool`/`hcxtools`, `ubertooth`, `inspectrum`, `rtl-433`, `kismet` | Receive, capture, decode. The bulk of the profile. |
| Cellular, receive-only | `gr-gsm` (apt on three of four targets), `QCSuper`, the LTE decoders | Legality varies by jurisdiction — interception statutes rather than spectrum rules. |
| Cellular, transmit | `srsRAN_4G`, `Osmocom core`, `osmo-trx`, `intrusive-lte-mme` | Operates a network. Requires authorisation an ordinary user will not have. |

**Recommendation: one `rf-security` profile for 1.0** containing the analysis and
audit group plus the receive-only cellular subset, with the legal framing
`docs/rf-security/` already requires — and **`cellular` deferred as a named,
undefined post-1.0 profile** rather than folded in quietly.

That keeps the 1.0 profile honest about what it is, keeps `gr-gsm` — apt on
Debian 13, Kali and Parrot, though **not** on Ubuntu 26.04, which is a capability-
matrix row rather than a reason to drop it — and does not put a rogue base
station one command away from a machine that also holds offensive tooling.

**This is a recommendation. Q-008 is the maintainer's to answer**, and the answer
changes the profile's contents, not its name."""

NOTES = """\
**The Blend's `sdr` task is {sdr_total} packages, of which {soapy} are
`soapysdr-module-*`.** Those are per-hardware backends, and a user with one
dongle needs one of them. Skywave ships the full set for the same reason the
Blend lists it — a live ISO cannot know what will be plugged in. **We can.**

Recommend installing `soapysdr-tools` plus the modules matching detected
hardware, treating the rest as available-not-installed. That single decision
removes {soapy_minus_one} of the {soapy} from the common case, and it is now supported by two
independent sources rather than one. **This is a design requirement on M4**, not
a catalog nicety: profile resolution has to be able to consult detected hardware.

**`logging` loses {logging_missing} on stable.** The Blend task is
{logging_total} packages and only {logging_stable} install on Debian 13 — the
missing ones are `qlog`, which `overlaps.md` picks as the *recommended default*,
and `not1mm`. A profile whose recommended default does not install on the stable
Debian base most of our targets derive from is a capability-matrix row, not a
footnote — and `overlaps.md` needs to say so.

**The Blend uses `Recommends` for almost every entry.** Its metapackages are
opt-out; our profiles are opt-in. Task membership means *"belongs to this
category"*, never *"install this by default"*. Importing it directly would make
every profile maximal.

**Overlap is expected and correct.** `splat` is in `antenna` and `tools`; `cw`,
`cwcp`, `xcwcp`, `aldo` and `morse` are in `morse` and `training`. Per **D-003**
that is one tag appearing twice, not a modelling error.

**`nonamateur` maps to `listening`, not to anything amateur.** It mixes ADS-B,
DAB, GNSS and utility decoding. It also contains `dump1090-mutability`, which
`overlaps.md` supersedes with `readsb` and which does not install on Debian 13
anyway."""


def main() -> int:
    OUT.write_text(render())
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
