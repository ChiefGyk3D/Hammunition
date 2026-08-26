# Session log — overnight round 3, 2026-08-25

Queue complete: items 1–6. Eight commits, one per completed item plus a
formatting fix and this log. Everything green, including the check that could not
run last round.

Previous round's log is in git history at `33495fe`.

---

## Headline

**`mypy --strict` passes clean.** Q-002 is closed. Twelve source files, checked
on Debian 13's own Python 3.13 inside a container, not on whatever the host has.

**All five inventory sources are now measured.** Skywave and DragonOS Tier 1 were
the last two. Every inventory is generated from upstream data and regenerable;
none is hand-typed.

**Two new red-flag findings** that change decisions already made — the Debian
Blend is 94% installable on stable rather than 100%, and DragonOS ships 20 units
of cellular/EW tooling that cannot be folded into a `sigint` package count.

---

## What completed

### Item 1 — Podman migration, and mypy --strict passes — `7d2f8ea`

Per Q-001: **rootless Podman, no `docker` group.** `containers/targets.yaml`,
`scripts/run-targets.sh`, the `Makefile` and the CI workflow all migrated.
Docker is now used nowhere.

Linux Mint 22.3 added as a target (Q-004) because `js8call.yaml` branches on it
specifically — without the target, that selector was decoration and the manifest
untestable. `raspios-arm64` renamed to `debian-13-arm64` with
`claims: aarch64-only`, because an arm64 Debian container is not Raspberry Pi OS
and D-018 forbids claiming what we have not tested (Q-003).

**mypy went 24 → 26 → 3 → 2 → 0.** The one error worth keeping is
`strict_equality` flagging `gtk2.upstream_port_status != qt5.upstream_port_status`
as a **non-overlapping comparison** — mypy narrowed both operands to distinct
literals, so the assertion was statically always-true and tested nothing.
Replaced with a set-cardinality assertion that can actually fail. Q-002 predicted
`strict_equality` would matter; its other three predictions never fired.

Local runs needed two workarounds because this account has no `/etc/subuid`
ranges. Item 6 wired them into an explicit, loud `HAMMUNITION_DEGRADED_PODMAN=1`
opt-in rather than leaving them as command-line folklore. CI needs neither.

### Item 2 — `linbpq` manifest — `fed2b85`

Pinned to tag `25.39`, closing Q-005 and the last packet-core blocker. Build
dependencies came from upstream's makefile `LIBS` line and were then **verified
in a Debian 13 container** — worth recording that `sources.debian.org` searches
*source* packages, so an earlier API check wrongly reported all seven library
`-dev` packages missing. The container is authoritative and now gets used that
way.

First manifest to carry `config_files`, which makes `DESIGN.md` §15.5
station-local configuration concrete rather than deferred.

### Item 3 — Skywave Linux inventory — `71a6663`

`docs/reference/skywave-inventory.md`, generated. Sources: the versioned Featured
Applications list on `skywavelinux.com` (5.10.0, Debian Sid base) for *what*,
`AB9IL/SDR-Scripts` for *how*, and apt probes in `debian:13` and `debian:sid`.

**60 applications — 9 delta, 29 overlap, 22 base system.** Both prior estimates
hold. Three corrections to `SCOPE.md`:

- **Most of the "remote SDR clients" are not client software.** KiwiSDR, WebSDR,
  Web-888, PhantomSDR and OpenWebRX are receivers you connect *to*. Skywave ships
  exactly one dedicated client. The real asset for a hardware-less user is the
  **receiver directory** — data, not a package.
- **AIS is not in 5.10.0** and is already ours.
- The OpenWebRX and PhantomSDR entries traced to `sourcecode.html`, which
  documents the v4 era (Ubuntu focal, WSJT-X 1.6.0) and has not been updated.

**Provenance, all tested rather than taken from GitHub metadata:**

- **SuperSDR has no licence.** No `LICENSE`, no header, default copyright — and
  the other two KiwiSDR clients are no better. Raised as **Q-007**.
- **Thierry Leconte archived his whole decoder suite.** `acarsdec` continues at
  `f00b4r0/acarsdec` (where Skywave's 4.4.1 comes from); `vdlm2dec` supersedes to
  `szpajder/dumpvdl2`; `acarsserv` has no successor.
- GitHub's licence API said `NONE` for `TLeconte/acarsdec`, which states LGPL-2
  in its README. The same lesson `linbpq` taught, in the other direction.

**A control probe of the Blend's own 152 packages** found **8 that do not install
on Debian 13** — including `qlog`, which `overlaps.md` picks as the recommended
logging default. Seven are sid-only release lag. Became **D-019**.

### Item 4 — DragonOS Tier 1 inventory — `0d9bda7`

`docs/reference/dragonos-tier1-inventory.md`, generated from DragonOS's published
README (Resolute R1, Ubuntu 26.04) and probed in **all four** x86 targets.

**99 README units — 24 Tier 1**, 26 Tier 2, 1 Tier 3, 20 hardware, 20
cellular/EW, 8 DragonOS-specific. The generator refuses to emit a Tier 1 row that
is in no target's apt and has no named upstream `.deb`, so the table cannot
silently overclaim.

`SCOPE.md`'s Tier 1 list needed correcting on four of five names. **Kismet is not
in the Resolute R1 README at all** — it is in the older FocalX one. `dumphfdl`
and `DumpVDL2` are Tier 2. `AIS-Catcher` is Tier 1 by `.deb`, not apt. Only
`readsb` survived as written.

**The Tier 3 gate is now measurable, and the news is good:** all four targets ship
`gnuradio 3.10.12.0` — the same upstream version DragonOS built its OOT modules
against. We are not chasing four APIs. The gate itself does not move.

**Universal Radio Hacker is archived** — read-only, final release v2.10.0, the
version DragonOS ships, 12,500 stars, in no target's apt and apparently never
packaged for Debian. Per `PARITY-POLICY.md` "finished" is a legitimate state and
a verdict may not be inherited, so its disposition waits on our own install test.

**Raised Q-008 🔴, the first red question.** DragonOS devotes 20 units to
cellular/EW and `SCOPE.md` folds that into "the SIGINT delta" without
distinguishing a passive decoder from a rogue base station. The line is
**transmit, not topic**.

### Item 5 — Profile sizing regenerated, names argued — `cfe9c26`

`profile-sizing.md` becomes generated. Every number derives from a measured
inventory; the profile set and its **names** are the curated part.

**Naming treated as the deliverable.** Four rules, and two names that are
deliberately not the obvious ones:

- **`station`, not `ham-core`.** "core" is a packaging word, not an operator
  word. `hammunition install station` reads as a sentence, and it survives the
  four-way split — `station` (26), `logging` (14), `morse` (15),
  `propagation` (18).
- **`rf-security`, not `sigint`.** CLAUDE.md already uses that phrase for the
  docs section and the security requirement; a different word in the CLI would
  be a defect. SIGINT is also a term of art for a state intelligence function,
  and most of this profile is Wi-Fi auditing and protocol analysis.

`cellular` is named but deliberately undefined pending Q-008.

**Three errors were caught by making the numbers derived rather than typed:**

- The sizing **summed** Blend tasks instead of unioning them. `morse` absorbs
  `morse` and `training`, which share five packages, so it read 20 when it is 13
  — inflating exactly the profile the split exists to right-size.
- The dispositions parser tested only the AHRL column for a digit, so the `ADD`
  row — whose AHRL cell is an em dash — was silently dropped and the 73Linux
  delta came out as 2 instead of 13.
- The old hand-written doc said 13 `soapysdr-module-*` packages while listing 12.

### Item 6 — Doc reconciliation — this commit

**Two new decisions**, both from measurements this round:

- **D-019 — Blend task membership is a category, not an install default.** 155 of
  160 entries are `Recommends` and none is `Depends`; importing membership as an
  install list would make every profile maximal. Includes the 94%-on-stable
  finding.
- **D-020 — Detected hardware drives profile resolution.** 12 of the Blend's 39
  `sdr` packages are per-device SoapySDR backends. The Blend, Skywave and
  DragonOS all ship the full set because a live ISO cannot know what is plugged
  in. We can. Removes 11 of 12 from the common case, and needs a hardware
  selector in the schema.

**Corrections to documents that were wrong:**

- `overlaps.md` claimed `qlog` "costs no backend work" because it is in Debian.
  It does not install on Debian 13. Recommendation unchanged; the capability
  matrix has to say so. `dump1090-mutability` is likewise sid-only, which
  strengthens the `readsb` call.
- `SCOPE.md` said gr-gsm's upstream "has stalled entirely for GR 3.10". Debian
  ships `gr-gsm 1.0.0~20220727-1+b18`, maintained by the Debian Hamradio
  Maintainers against `git.osmocom.org/gr-gsm`, and it installs from apt on
  Debian 13, Kali and Parrot — not Ubuntu 26.04. Upstream moved off GitHub; the
  packaging did not stop. Same correction applied to `PARITY-POLICY.md`.
- **`catalog/packages/hamclock-next.yaml` still carried the retracted claim** in
  three places — the shape comment, the endpoint note, and `known_problems` —
  that HamClock stopped working in June 2026. Last round retracted that in
  `dispositions.md` and produced D-018; the manifest was missed. Now corrected,
  with hamclock.com flagged as live, third-party and patron-funded.

**Two tooling defects fixed**, both found by doing the work rather than by
looking for them:

- **`scripts/check_doc_links.py` matched its skip list against every path
  component**, so `reference` also matched `docs/reference/` and the checker
  silently skipped all seven inventory documents while reporting success. This is
  the `.gitignore` anchoring bug, repeated inside the tool meant to catch
  problems. Skip list is now root-anchored. The first version of the regression
  test reimplemented the filter and **passed happily with the bug reintroduced**;
  the checker now exposes `scanned_docs()` and the test asserts on the real one.
- **The podman degraded-mode workarounds were never wired in** — item 1 used them
  from the command line and left the harness broken for this account.
  `HAMMUNITION_DEGRADED_PODMAN=1` now applies them explicitly, prints a warning
  that isolation is weakened, and prints the one root command that fixes it
  properly.

---

## Open questions

| | Status |
|---|---|
| Q-001 – Q-005 | ✅ resolved last round |
| **Q-006** 🟡 | Which HamClock. Recommendation stands; the manifest's factual notes are now correct. |
| **Q-007** 🟡 | SuperSDR has no licence. Recommend CARRY pinned with the licence state recorded, and ask upstream. |
| **Q-008** 🔴 | Does the RF-security profile include cellular interception tooling? Blocks item 5's profile contents. |

---

## What I could not do

**Nothing was skipped, but two things are worth naming.**

**The local container harness runs degraded.** Full fidelity needs one root
command this session was not authorised to run:

```
sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 chiefgyk3d
podman system migrate
```

CI is unaffected — its runners have subordinate ID ranges.

**No `.deb` was installed and no source build was attempted.** Every availability
claim in the new inventories is `apt-cache policy` inside a container, which
proves the archive offers the package, not that it installs and runs. The four
upstream `.deb` units in DragonOS Tier 1 target older releases than our primary
targets — SatDump's newest is Ubuntu 24.04, SDR++'s is Debian bookworm — and each
needs an install test before its manifest claims support. Flagged in the document
rather than assumed away.

---

## Verification

| Check | Result |
|---|---|
| `pytest` | 65 passed |
| `mypy --strict` | clean, 12 source files, in a `debian:13` container |
| `ruff check` / `ruff format --check` | clean |
| `scripts/check_doc_links.py` | clean — and now actually scanning `docs/reference/` |
| Generated docs regenerate identically | yes |
| `.gitignore` anchoring | `docs/reference/` tracked (8 files); every `reference/` subdir ignored; 0 files tracked under `reference/` |
