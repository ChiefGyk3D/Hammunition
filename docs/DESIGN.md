# Hammunition — Design Document

> Pick your RF arsenal.

Status: draft, pre-implementation. This document holds the reasoning behind the
decisions summarised in `CLAUDE.md`.

**Authority order:** `DECISIONS.md` > `PARITY-POLICY.md` > `CLAUDE.md` > this
document. Where any of them disagrees with this file, they win and this file is a
bug. `docs/reference/ahrl-inventory.md` is the measurement everything rests on.

---

## 1. Problem statement

A licensed amateur who wants a Linux station has three bad options:

1. **Install everything by hand.** Dozens of packages, several not in Debian,
   plus audio routing, rig control, udev permissions, and group membership. A
   weekend of work, repeated from scratch on every new machine.
2. **Use a purpose-built distribution.** Solves the software problem, replaces
   your OS, and leaves you on someone else's release cadence.
3. **Use an install script layered onto an existing OS.** This is what Andy's Ham
   Radio Linux does today, and it is the correct shape. Its limitations are
   organisational rather than technical.

Nobody serves the operator who wants amateur radio *and* SDR *and* RF security
tooling on one machine. The ham distributions do not ship security tools; the
security distributions do not ship ham software. That operator currently carries
two laptops.

Hammunition targets that person.

## 2. Baseline: Andy's Ham Radio Linux

AHRL (Andy Stewart, KB1OIQ) is the direct baseline. Hammunition is AHRL's model
executed with modern engineering practice, extended into RF security.

**What AHRL is, as of v27 (May 2026):** an installation script layered onto
Debian Live, Raspberry Pi OS, or a supported Ubuntu flavour. Tested targets are
Ubuntu/Xubuntu/Kubuntu 26.04, Linux Mint 22.3, Debian Live 13.4, LMDE 7, and
Raspberry Pi OS 6.2. Distributed as versioned tarballs via SourceForge.

Notably, AHRL *used* to be a distribution and moved away from that model. That
migration is strong independent evidence for the augmentation approach, and is
why building a distro appears on our rejected list rather than our roadmap.

**What we inherit:** the package curation. Andy's judgment about what ham
software is worth installing, what works, and what is abandonware represents
years of accumulated knowledge. Rebuilding it from scratch would be wasteful and
worse. We use the AHRL inventory as the seed for our catalog.

**What we change, and why the project exists:**

| AHRL | Hammunition |
|---|---|
| Tarballs on SourceForge | Git, tagged releases, signed |
| Single maintainer | Multiple maintainers, documented governance |
| Contribute by emailing the maintainer | Pull requests, issues, public review |
| Package list embedded in shell logic | Declarative catalog, separate engine |
| Bash install script | Python engine: idempotent, dry-run, transaction log |
| Manual cross-distro testing | CI containers per target |
| Ham radio | Ham radio + SDR + SIGINT + RF security |

**Positioning.** We are not a replacement for AHRL and must not present ourselves
as one. We solve a governance problem and cover a domain AHRL does not. AHRL is
credited prominently in the README. Approach Andy before launch as a courtesy.

**Provenance — verified, not assumed.** Package names, versions, upstream URLs,
install mechanisms, build flags, `-Wno-*` workarounds and patch sets are facts
and freely usable.

Verified 2026-08-25: `bin/install_ahrl` and `bin/test_menus_debian13.py` carry
GPL-3.0-or-later headers, Copyright 2024/2025 Andy Stewart (KB1OIQ). **No
`LICENSE` or `COPYING` ships at the top level**, and the rest of AHRL's authored
material — seven helper scripts, 105 `.desktop` files, 18 `.directory` files, and
all documentation prose — carries no license notice at all.

**Therefore:** do not reuse `.desktop` files, `.directory` files, menu structure,
or documentation prose; their status is genuinely unclear. Do not port installer
logic; GPL-3.0-or-later would be viral. Writing from the inventory keeps
provenance unambiguous. See **D-011**.

**73Linux:** no license file at all, so nothing from its code. Inventory only.
See **D-001**.

## 3. Scope

### In scope

Turning an existing Debian-family installation into a working amateur radio,
SDR, and RF experimentation workstation: package installation, hardware
configuration, and the documentation to operate it.

### Explicitly rejected

Considered and decided against. Do not revisit without new information:

- A Linux distribution, derivative, or custom ISO
- A custom kernel
- A mirror or fork of upstream Debian packages
- Forks of upstream ham or SDR software
- Anything that replaces or wholesale-reconfigures the user's OS

We augment. Upstream packages are used wherever they exist.

### Deliberately deferred

- Graphical installer (CLI and TUI first)
- Our own APT repository (only if `.deb` distribution proves insufficient)
- Non-Debian families (Fedora, Arch) — the abstraction should not preclude them,
  but no effort goes there before 1.0

## 4. Architecture

Two separable halves. Keeping them separate is the single most important
structural decision in the project.

### 4.1 The catalog (`catalog/`)

YAML manifests describing software: what it is, what it does, how to install it
on each supported distribution, which profiles include it, and the documentation
fields the docs generator consumes.

**Pure data.** No executable logic, no shell fragments, no conditionals beyond
declarative per-distro variants. The catalog must remain consumable by an engine
that is not ours — someone should be able to write an Ansible or Nix consumer
without our permission or our code.

The catalog is the durable asset. Engines are replaceable; curated knowledge
about what to install and how is not.

### 4.2 The engine (`src/hammunition/`)

A Python CLI that reads manifests and performs installation, configuration, and
hardware setup. Knows *how* to install things; knows nothing about *what* to
install. No package names in engine code, ever.

### 4.3 The boundary

Any change that puts install logic into the catalog, or hardcodes package names
into the engine, is a defect regardless of how convenient it seems.

## 5. Implementation language

**Decision: Python 3.11+.**

| Option | For | Against |
|---|---|---|
| **Python** | Present on every target; the language ham and security contributors read and write; rapid iteration; trivial YAML handling | Runtime dependency; system-Python conflicts on machines with heavy tooling |
| **Go** | Single static binary, no runtime deps, easy distribution, fast | Smaller contributor pool in this community; more ceremony for what is mostly orchestration |
| **Rust** | Correctness, excellent tooling | Highest contribution barrier; overkill for subprocess orchestration |
| **Bash** | Zero deps, what AHRL uses | Untestable at scale, no types, no structured error handling — exactly the fragility we are replacing |

The deciding factor is that *contribution is the point of this project*. AHRL's
limitation is a bus factor of one; choosing a language fewer people can
contribute in would reproduce that failure in a nicer repository.

Go's static-binary advantage is real, particularly on a machine whose system
Python is contested by security tooling. Mitigation: ship as a `.deb` with a
vendored virtualenv, so users never touch pip and system Python is untouched.
Revisit if that mitigation proves inadequate in practice.

Bash is permitted only for small helper scripts, never for core logic.

## 6. Package installation

**Primary backend: `apt` via subprocess.** Simpler than `python3-apt`, behaves
identically across all Debian-family targets, and produces output we can show
the user verbatim.

**Additional backends, justified by measurement rather than convention**
(**D-014**). The coverage report is done: **57 of 95 AHRL units are not
apt-installable**. An apt-only tool covers 40% of the parity target.

Required for 1.0: source-from-tarball (35 units), binary/`.deb`/archive (9),
Python venv (3), pipx (1), source-from-git (1), **CPAN** (1 — `aa-analyzer`
needs `Device::SerialPort`), and launcher generation (14 units need a generated
wrapper).

Measured zeros, recorded so they are not re-added from habit: `cargo` 0,
`flatpak` 0, `appimage` 0 across all 3,911 lines of AHRL. AppImage and a
configured Wine prefix are post-1.0 (HAMRS, VARA). `snap` appears 11 times, all
removals — it is an anti-dependency belonging in `system_modifications`.

This is the core engineering problem, not an edge case. The non-apt packages are
precisely the ones users cannot easily install themselves — the reason to exist
(**D-004**).

**Third-party APT repositories** must be declared in the manifest with a pinned
signing key, shown to the user before being added, and documented. Never added
silently.

## 7. Undo semantics

**We do not promise rollback.** True rollback across apt plus source builds plus
`make install` plus per-user venvs plus CPAN is not achievable — apt alone cannot
cleanly reverse a transaction that pulled dependency changes, and a source build
that ran `make install` scatters files with no manifest.

**We promise a transaction log.** Every package installed, every source enabled,
every file written, every group modified, recorded with timestamps. `hammunition
uninstall` removes what Hammunition itself added, and reports honestly on
anything it cannot safely reverse.

This is a smaller promise that we can actually keep. Overpromising rollback is
how the project earns its first justified angry issue.

## 8. Distribution support

Detection via `/etc/os-release`. No heuristics, no version sniffing beyond what
that file provides.

Support is declared per package in manifests and resolved into a capability
matrix. Where a package is unavailable on a target, we say so. We never add a
shim to make an unsupported combination appear to work.

Priority order: Parrot OS, then Debian, Ubuntu, Kali, Raspberry Pi OS.

Raspberry Pi OS implies ARM64. **Settled (D-002): ARM is a day-one target and
`arch` is a structural selector in the schema from M1.** Nine AHRL units are
arch-conditional; 73Linux ships arch-partitioned trees. The retrofit cost is
visible in AHRL's `install_gspiceui`, which hardcodes an `aarch64-linux-gnu` path
on every architecture and leaves a dangling symlink on x86_64. The ClockworkPi
uConsole is a target device.

## 9. Hardware

Configuration for SDRs (HackRF, RTL-SDR, Airspy, SDRplay, LimeSDR, PlutoSDR,
BladeRF), serial-connected transceivers and CAT interfaces, Digirig, GPS
receivers, LoRa and Meshtastic hardware.

**The highest-value single feature in the project:** persistent udev symlinks by
device serial. `/dev/rig-991a`, `/dev/rig-ftx1`, `/dev/catsniffer`,
`/dev/meshtastic0`. Plug order stops mattering; every downstream config
references a stable name. This is roughly 150 lines of rules and saves an hour
per field deployment.

Everything the hardware layer does to a system is printed before it happens and
recorded in the transaction log.

## 10. Security

This runs on machines that also hold offensive-security tooling. Security
requirements are non-negotiable:

- Never pipe remote content into a shell, and never instruct users to
- Verify checksums or signatures for any non-apt source; refuse to install if
  verification is impossible
- Pin signing keys for third-party repositories
- `--dry-run` must be complete and accurate, not approximate
- Minimise root: sudo only for apt and udev operations
- RF-security tooling lives in a separate profile requiring explicit opt-in
- No credentials, keys, or tokens in the repository or in generated config

## 11. Documentation

Documentation is a deliverable, not an afterthought. A feature is not done until
it is documented.

**Standard:** a licensed ham with moderate Linux experience should get from a
fresh Parrot install to a working digital-modes station without asking anyone a
question or reading a forum thread. A step requiring knowledge absent from our
docs is a documentation bug.

**Generated where possible.** Package reference pages and the capability matrix
are built from manifests, so they cannot drift. Manifests carry required
documentation fields; a manifest missing them fails CI. Hand-written prose covers
what a schema cannot express.

**Sections** under `docs/` — collectively "Hacker's Ham Shack":
getting-started, profiles, packages, hardware, guides, troubleshooting,
rf-security, contributing, reference.

The RF-security section requires legal and ethical framing written carefully by
hand: Part 97 constraints and computer-crime statutes both apply, and their
intersection is not obvious. That section will be quoted back at us.

## 12. Testing

- Container-based, one per target distribution. Never test against a developer
  machine.
- Every manifest validated against the schema in CI.
- Capability-matrix claims backed by a passing container install.
- `mypy --strict` clean; type hints throughout.
- Docs CI: broken internal links, missing manifest doc fields, and CLI examples
  that no longer match real output all fail the build.

## 13. Repository and release

**One repository initially.** Splitting catalog from engine into separate repos
is tempting for purity but adds coordination cost before there is a community to
coordinate. The directory boundary enforces the architecture adequately. Split
later if the catalog gains independent consumers.

**Distribution:** `.deb` with a vendored virtualenv. Our own APT repository only
if that proves insufficient.

**Versioning:** semantic versioning. The catalog and engine version together
until they are split.

**Governance from day one:** more than one person with merge rights, a documented
decision process, signed releases. A single-maintainer GitHub repository is not
more open than a single-maintainer SourceForge project — it is the same problem
with better tooling. Avoiding that is the entire point.

## 14. Roadmap

**1.0 = AHRL parity + the packet core** (**D-008**). Parity is not "reproduce
AHRL" — per `PARITY-POLICY.md` it is that a user who uninstalls AHRL and installs
Hammunition is **strictly better off**. Every unit gets one disposition: CARRY,
SUPERSEDE, REVIVE, RETIRE, ADD. Reproducing AHRL faithfully, broken entries
included, would be a worse product than AHRL.

In 1.0: PAT, AX.25, BPQ, ARDOP, Direwolf-with-configuration. Post-1.0: VARA
(Wine prefix) and HAMRS (AppImage). Novel capability layers on top, never
substitutes.

- **M1 — walking skeleton.** Manifest schema and validator, apt backend,
  os-release detection for Parrot and Debian, ~20 packages, one `ham-core`
  profile, `install`/`list`/`status`/`--dry-run`, container test harness.
- **M2 — inventory and coverage.** *AHRL done* — see
  `reference/ahrl-inventory.md`: 95 units, 57 non-apt. Remaining: the 73Linux
  delta and per-unit dispositions.
- **M3 — backend completeness.** Implement the measured backend set (§6). Every
  backend names the unit requiring it (**D-014**).
- **M4 — profiles and hardware.** Full profile set, udev rules, groups, firmware,
  persistent device symlinks.
- **M5 — parity verified.** Every unit either installs on at least one supported
  distro, or carries a `broken`/`retired` status **verified by us**, never
  inherited from an AHRL comment. **Exit criterion: our install-success fraction
  must be at least as good as AHRL's own** — 95 units, 9 disabled. Shipping 95
  manifests with 40 broken is not parity. Inherited verdicts count against us.
- **Post-1.0.** SIGINT and RF-security profiles, Meshtastic/LoRa, Parrot-specific
  integration. Where Hammunition stops being "AHRL done properly" and becomes its
  own thing.

## 15. Questions

### Closed

1. **Profile dependencies** — closed by **D-003**. Flat tags with overlap, no
   nesting. AHRL's categories overlap heavily (14 programs in two or three) but
   never nest; the one nested case is a doc menu, not a software grouping.
   73Linux uses a flat checklist. `categories` is a list.
2. **ARM as a day-one target** — closed by **D-002**. Yes. `arch` is a structural
   selector from M1.
3. **Can we build on 73Linux?** — closed by **D-001**. No: unlicensed, and
   `.bapp` is bash with a metadata header. Inventory source only.
4. **Does the Winlink delta land in 1.0?** — closed by **D-008**. Split. Packet
   core in 1.0; VARA and HAMRS post-1.0.

### Open

5. **Station-local configuration — now blocking.** Callsign, grid square, rig
   device paths. Where does operator-specific config live, and how does it stay
   out of git?

   No longer deferrable: the 1.0 packet core forces it. AX.25's install writes
   `wl2k ${MYCALL} 1200 255 7 Winlink` into `/etc/ax25/axports`, and Direwolf is
   admitted to 1.0 explicitly *with configuration, not merely installation*. This
   also exceeds `system_modifications` as scoped in **D-012**, which covers udev
   rules, groups and blacklists but not templated config files. The schema needs
   a `config` concept with templating from station-local variables, and those
   variables need a home that is gitignored by construction.

6. **Unverifiable upstreams.** *Substantially resolved 2026-08-25 — see below.*

   The original concern: BPQ (linbpq) appeared to be published as loose files in
   a personal website's `/Downloads/Beta/` directory — unversioned URLs, no
   release structure, no checksums — making it the first 1.0 unit that could not
   satisfy **D-004**'s pin-and-verify requirement.

   **That was 73Linux's install method, not upstream's publishing model.**
   Verified: linbpq is GPL-3.0-or-later with tagged source on GitHub (`25.39`,
   `25.36`, …). It becomes an ordinary pinned source build. See
   `reference/licence-verification.md` and **Q-005**.

   **The general question survives BPQ's removal from it.** HAMRS discovers its
   AppImage by scraping `hamrs.app`, and several AHRL units ship as unversioned
   `master` snapshots. The lesson is a method, not a policy: **check how upstream
   publishes before accepting how an existing installer fetches.** One of the
   two is usually better, and it is rarely the installer.

7. **Catalog versioning.** If a user is on Hammunition 1.2, which catalog version
   do they get, and can they pin it? Interacts with the three-tier model
   (**D-009**) — core, community, and local tiers may not version together.
