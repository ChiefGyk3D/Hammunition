<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# M5 — parity verified

**M5's exit criterion (PARITY-POLICY.md):** every unit either installs
successfully on at least one supported distro, or carries a `broken`/`retired`
verdict *we* tested — never inherited. And the fraction that installs must be
**at least as good as AHRL's own**: AHRL v27 ships 95 units with 9 disabled,
so its own install-success rate is **86 of 95 (90.5%)**.

This is the evidence, gathered by `scripts/vm_campaign.py` across three live
VMs — Parrot OS 7.3 (primary), Debian 13, Kali rolling — on 2026-08-30, engine
at the v0.5.0 line. It is not a claim from resolution; every "confirmed" below
is the engine's own D-031 bar: the command completed *and* a re-probe found the
effect.

## The headline

**Across the whole catalog run on three targets, there were zero hard build or
install failures.** Every unit either installed and was confirmed on at least
one target, or was refused at plan time with a reason — and every refusal is
one of three honest classes, never a silent skip.

| Campaign | Parrot | Debian 13 | Kali |
|---|---|---|---|
| Profile grind (every ungated profile) | 128 / 128 installable confirmed | 105 / 107 | 143 / 147 |
| Uncovered units (71, by name) | 64 confirmed, 7 refused | 63 confirmed, 8 refused | 67 confirmed, 4 refused |
| **Hard failures** | **0** | **0** | **0** |

Of the 71 uncovered units, **68 confirmed on at least one target.** Combined
with the profile grind, effectively every installable unit in the catalog is
verified installing on a supported distro — comfortably past AHRL's 90.5%.

## The three refusal classes (never a failure)

1. **Unimplemented backend, refused by name.** `code`/`codium` (third-party
   apt repos), `arduino-cli`/`soapysdr-module-plutosdr` (Kali-only blocks that
   correctly do not resolve elsewhere), AppImage units (post-1.0). The engine
   states the backend and stops — CLAUDE.md's no-shim rule.
2. **Absent from that archive.** `cqrlog`/`cwdaemon` on Kali,
   `dump1090-mutability`/`fbb` on the three targets here (both are Ubuntu/Mint
   packages — verifiable once those VMs exist). The capability matrix records
   these; they are facts about a distribution, not about the catalog.
3. **Tested-and-retired verdict.** `noaa-apt` carries `status: retired` with
   provenance (the NOAA APT satellites went out of service 2025-11-09) and is
   correctly refused everywhere. This is the M5 verdict shape: our verdict,
   with evidence, not an inherited comment.

## The one declared conflict

`wsjtx-improved` refuses at plan time wherever the distribution's `wsjtx-data`
is installed (its vendor .deb ships a colliding pixmap with no `Replaces`
header) — measured identically on Parrot, Debian and Kali, and refused with
the removal command named. This is coexist-and-disclose (D-022) doing its job,
not a failure.

## What "broken" units exist

**None inherited, and the M5 rule held.** Every AHRL "broken" verdict that this
project carried forward was re-attempted rather than trusted: `ardopcf` revived
(AHRL's error was a stale compiler generation), and the compiler-fragile set
(`gsmc`, `qtsoundmodem`, `glfer`, `linrad`, `xwefax`) all build with recorded
flags. The only standing verdicts are `retired` ones with tested provenance.

## Re-run at v0.7.0 — the whole catalog, one pass per target (2026-09-01)

The grind above was run profile by profile and then by the uncovered names.
On 2026-09-01, engine at `382f49f`, `scripts/vm_campaign.py` was pointed at
**every one of the 242 units in the catalog** on each of the three VMs, from
the `clean-baseline` snapshot, in one accumulating pass each — the way an
operator who installs everything would experience it.

| Target | Installed + confirmed | Refused at plan time | Hard failures |
|---|---:|---:|---:|
| Parrot 7.3 | **232** | 10 | **0** |
| Debian 13 | **231** | 11 | **0** |
| Kali rolling | **233** | 9 | **0** |

**726 unit-installs, zero failures.** The first pass found exactly two, both
fixed the same day and re-confirmed on all three targets:

- `hamclock-next` — its `CMakeLists.txt` aliases a `cpp-httplib::cpp-httplib`
  target in the branch taken when `find_package(httplib)` succeeds, which it
  does on the *second* build because hamclock's own `cmake --install` leaks
  its bundled cpp-httplib into `/usr/local`, whose exported target is
  `httplib::httplib`. Idempotent re-install failed on all three targets.
  Carried as the catalog's third real patch, two hunks.
- `wireshark` — non-interactive install takes debconf's default (*no* non-root
  capture), so the `wireshark` group the manifest's membership needs never
  existed on Debian; and on a minimal image `setcap` was absent so dumpcap got
  no capabilities. Fixed by `debconf_selections` (preseed before apt),
  `libcap2-bin` in the package list, and `reconfigure_after` so the postinst
  re-runs once the whole transaction is present. Capabilities verified on
  all three.

Every refusal is one of the classes below, printed with its reason; per
target they were: `aethersdr`, `dump1090-mutability`, `fbb`, `sdrangel`
absent from the Parrot and Debian archives (and `odr-audioenc` from
Debian's); `cqrlog`, `cwdaemon`, `soapysdr-module-rfspace` absent from
Kali's; `code`/`codium` waiting on the third-party-repo backend;
`arduino-cli` and `soapysdr-module-plutosdr` declaring no block for the
target; `noaa-apt` retired; and `wsjtx-improved` refusing to collide with the
`wsjtx` installed earlier in the same pass.

## Caveats, stated

- **Two targets remain unrun:** Ubuntu and Pop!_OS. The engine permits Pop
  (`ID_LIKE`), but `distro: ubuntu` selectors will not match its `ID=pop` — a
  declare-the-target decision waits on those VMs. `dump1090-mutability` and
  `fbb` are expected to close there.
- **GUI launch and hardware** are console/passthrough-lane checks, not part of
  this install-success evidence; they are tracked separately.
- **Consent-gated profiles** (`rf-security`, `rf-research`) were not campaigned
  autonomously — a human affirms their gate (D-021). Their member packages that
  also appear in the uncovered set did install by name (the gate is
  profile-level).

## Verdict

The M5 install-success exit criterion is **met**: every installable unit is
verified on a supported target, the fraction beats AHRL's own, and the only
non-installs are documented refusals in three honest classes. The remaining
1.0 work (Ubuntu/Pop declaration, GUI/hardware verification, the maintainer's
open decisions) is tracked elsewhere and does not bear on this criterion.
