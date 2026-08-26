# Hammunition — Claude Code Context

> Pick your RF arsenal.

## What this project is

Hammunition turns an existing Debian-family install into an amateur radio, SDR,
and RF experimentation workstation. Primary target: **Parrot OS**. Secondary:
Debian, Ubuntu, Kali, Raspberry Pi OS.

Binary: `hammunition`. Python package: `hammunition`.

## Document authority

`docs/DECISIONS.md` is authoritative. Where this file or `docs/DESIGN.md`
disagrees with it, DECISIONS wins and the disagreeing file is a bug.
`docs/PARITY-POLICY.md` governs per-unit disposition and the M5 exit criteria.
`docs/reference/ahrl-inventory.md` is the measurement everything else rests on.

## What this project is NOT

Do not propose or build any of these. They have been considered and rejected:

- A Linux distribution, custom ISO, or derivative
- A custom kernel
- A mirror of upstream Debian packages
- Forks of upstream ham/SDR software
- Anything that replaces or reconfigures the user's OS wholesale

We **augment** an existing system. Upstream packages are used wherever they exist.

## Inventory sources

Two projects seed the catalog. Both are inventory sources; neither is a base we
build on. See **D-001** and **D-011** for the provenance rules, and credit both
in the README.

### Andy's Ham Radio Linux (AHRL)

AHRL by Andy Stewart (KB1OIQ) is the direct inspiration and the closest existing
thing to what we are building. Study it before designing anything. Treat it with
respect — it has served the ham community for well over a decade and its package
curation represents years of accumulated judgment we would be foolish to discard.

**What AHRL is (as of v27, May 2026):** no longer a distribution. It is an
installation script layered onto Debian Live, Raspberry Pi OS, or a supported
Ubuntu flavor. Supported and tested targets are Ubuntu/Xubuntu/Kubuntu 26.04,
Linux Mint 22.3, Debian Live 13.4, LMDE 7, and Raspberry Pi OS 6.2. Distributed
as versioned tarballs on SourceForge.

**What we take from it:**

- The package curation itself. Andy's selection of ham software — what is worth
  installing, what actually works, what is abandonware — is the single most
  valuable artifact in this space. Use the AHRL package inventory as the
  reference when seeding `catalog/packages/`.
- The layered-onto-existing-OS model. AHRL arrived at this after years as a
  distribution. That migration is strong evidence the augmentation approach is
  correct, and it is why building a distro is on our rejected list.
- Hard-won operational knowledge, e.g. Andy's guidance to prefer X11 over Wayland
  where ham applications misbehave. Capture that kind of thing in manifests and
  docs rather than rediscovering it in the field.

**What we do differently, and why the project exists:**

| AHRL | Hammunition |
|---|---|
| Tarballs on SourceForge | Git, tagged releases, signed |
| Single maintainer, bus factor of one | Multiple maintainers from day one, documented governance |
| Contribution by emailing the maintainer | Pull requests, issues, public review |
| Install logic and package list intertwined in shell | Declarative catalog separated from engine |
| Bash installation script | Python engine, idempotent, dry-run, transaction log |
| No automated cross-distro testing | CI containers per target distro |
| Ham radio only | Ham radio plus SDR, SIGINT, and RF security on a security-tooling base |

### 73Linux (KM4ACK)

73Linux, by Jason Oleham (KM4ACK), grew out of Build-a-Pi. Same shape as AHRL and
as us: an installer layered onto an existing Debian-family OS, not a distribution.
Actively maintained, 47 unique units across `app/stable/pi/` and
`app/stable/x86_64/`.

**What we take:** the inventory delta. 73Linux covers Winlink, packet, and EMCOMM
— PAT, PATMENU3, BPQ, AX.25, ARDOP, ARDOPGUI, VARA, GARIM, VARIM — a domain AHRL
does not touch at all. The packet core lands in 1.0 (**D-008**). Its community
side-loading model also informs our three-tier catalog (**D-009**).

**What we do not take:** any code. There is no LICENSE or COPYING in the
repository and no header on `73.sh`, so default copyright applies. A `.bapp` is
also executable bash with a metadata header — five easy fields declarative, every
hard field trapped inside an imperative `INSTALL()` body. That is the architecture
we exist to replace. See **D-001**.

**Positioning.** We are not competing with AHRL or 73Linux and must not present
ourselves as a replacement for either in README, docs, or commit messages. We cover a domain it does
not — RF security and SIGINT alongside amateur radio — and we solve a governance
problem rather than a software problem. Credit AHRL prominently in the README.

## Architecture invariants

Two separable halves. Do not blur them.

1. **The catalog** (`catalog/`) — YAML manifests describing software: what it is,
   what it's for, how to install it per-distro, which profiles include it.
   Pure data. No executable logic. Must remain usable by an engine that isn't ours.
2. **The engine** (`src/hammunition/`) — Python CLI that reads manifests and
   performs installation, configuration, and hardware setup.

The catalog is the durable asset; the engine is replaceable. Any change that puts
install logic into the catalog, or hardcodes package names into the engine, is wrong.

## Decisions already made

Do not re-litigate these without being asked:

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Contributor accessibility is the point of the project |
| Package ops | `apt` via subprocess | Simpler than python3-apt, uniform across targets |
| Manifests | YAML | Human-editable by non-programmers |
| Distro detection | `/etc/os-release` | Standard, no heuristics |
| Undo semantics | Transaction log + `uninstall` | True rollback is not achievable; do not promise it |
| Config management | Own engine, Ansible as export target | Keep the catalog engine-agnostic |
| Privilege | Drop to user where possible; sudo only for apt/udev | Runs alongside offensive tooling |
| Naming | One name: Hammunition | "Renegade RF" is held in reserve, not used in docs or code |
| Architecture selector | `arch` structural from M1 | 9 AHRL units are arch-conditional; retrofitting is what broke `gspiceui` (**D-002**) |
| Profiles | Flat tags with overlap, no nesting | AHRL categories overlap but never nest; 73Linux is a flat checklist (**D-003**) |
| Catalog tiers | core / community / local | Side-loading is 73Linux's best idea and answers our founding objection to AHRL (**D-009**) |
| Update tracking | `update` block on every manifest | AHRL has no update story — install once, rot forever (**D-010**) |
| Backend selection | Measured, never conventional | We listed cargo/flatpak from habit and missed CPAN from data (**D-014**) |
| 73Linux | Inventory source, never a base | No license file; `.bapp` is bash with a header (**D-001**) |
| 1.0 scope | AHRL parity + packet core | VARA and HAMRS are post-1.0 (**D-008**) |

Full reasoning and evidence in `docs/DECISIONS.md`, which is authoritative.

## Security requirements

Non-negotiable. This runs on machines that also hold security tooling.

- Never pipe remote content into a shell
- Verify checksums/signatures for any non-apt source; refuse to install if absent
- Third-party apt repos must be declared in the manifest and shown to the user
  before being added, with the signing key pinned
- Print every system modification before making it (`--dry-run` must be complete
  and accurate, not approximate)
- RF-security tooling lives in its own profile requiring explicit opt-in
- No credentials, keys, or tokens in the repo or in generated configs

## Documentation is a first-class deliverable

Documentation is not written after the code. A feature is not done until it is
documented. This is a hard rule, not an aspiration.

**The standard:** a licensed ham with moderate Linux experience should be able to
go from a fresh Parrot install to a working digital-modes station without asking
anyone a question or reading a forum thread. If a step requires knowledge that is
not in our docs, that is a documentation bug and gets an issue.

**Required for every package manifest** — the docs generator reads these fields,
so an undocumented package cannot ship:
- What the software does, in plain language, for someone who has not used it
- Why an operator would want it, and what it is an alternative to
- What it depends on being configured first (rig control, audio routing, GPS)
- Known problems and workarounds, including desktop/display-server issues
- Upstream project URL and where to get real support for the software itself

**Required for every profile:** what it installs and why those things belong
together, disk footprint, what it deliberately excludes, and what an operator
still has to configure by hand afterward.

**Required for every system modification:** what changes, why it is necessary,
how to inspect it afterward, and how to reverse it. Groups added, udev rules
written, config files touched, repositories enabled. Nothing happens to a user's
machine that is not written down.

**Top-level docs (not part of the user-facing site):** `DECISIONS.md`
(authoritative decision record), `PARITY-POLICY.md` (per-unit disposition and M5
exit criteria), `DESIGN.md` (reasoning), `why-hammunition.md` (public rationale).

**Structure under `docs/` ("Hacker's Ham Shack"):**
- `getting-started/` — install, first profile, first contact
- `profiles/` — one page per profile, generated from manifests plus prose
- `packages/` — generated reference, one entry per manifest
- `hardware/` — per-device setup: SDRs, rigs, CAT interfaces, GPS, LoRa
- `guides/` — task-oriented: digital modes, APRS, satellite, packet, SDR
- `troubleshooting/` — symptom-first, not component-first
- `rf-security/` — separate section, legal and ethical framing required
- `contributing/` — how to add a manifest, how to add a backend, review process
- `reference/` — CLI, schema, capability matrix, transaction log format

**Generate what can be generated.** The package reference and capability matrix
come from manifests, so they cannot drift from reality. Hand-written prose is for
things a schema cannot express. Any doc that duplicates manifest data by hand is
a defect.

**Docs are tested.** CI fails on broken internal links, manifests missing
required doc fields, CLI examples that no longer match actual output, and
capability-matrix claims not backed by a passing container test.

## Conventions

- Idempotent: every operation safe to re-run
- Fail loudly, never silently degrade
- Structured logging to `~/.local/state/hammunition/`
- Type hints throughout; `mypy --strict` clean
- Tests run in containers per target distro, never against the dev machine
- Small, logically scoped commits
- `/reference/` and `/vendor/` are gitignored, **anchored to the repo root**:
  third-party tarballs and extracted upstream trees are studied locally, never
  committed. Keep provenance clean. The anchoring matters — the unanchored form
  also matches `docs/reference/`, a required documentation section, and silently
  excluded it. A test asserts `docs/reference/` stays tracked.

## Capability matrix

Not every profile works everywhere. Manifests declare per-distro support and the
engine reports honest gaps rather than faking coverage. Never add a shim to make
an unsupported combination appear to work.

## Repo layout

```
catalog/
  packages/        # one YAML per piece of software
  profiles/        # named bundles referencing packages
  hardware/        # udev rules, group membership, firmware
src/hammunition/
  cli/             # argparse/click entry points
  manifest/        # schema, loader, validation
  backends/        # apt, source, git, binary, venv, pipx, cpan (D-014)
  distro/          # /etc/os-release detection and capability resolution
  hardware/        # USB/serial detection, udev generation
  state/           # transaction log, uninstall
docs/              # "Hacker's Ham Shack" — guides and labs (section title, not a brand)
tests/
```

## Closed questions

Both former open questions are settled. Do not reopen without new evidence.

- **Profile nesting** — closed by **D-003**. Profiles are flat tags with overlap;
  they do not nest or depend on each other. AHRL's categories overlap heavily
  (14 programs appear in two or three) but never nest; 73Linux uses a flat
  checklist. These are tags, not a tree. `categories` is a list.
- **ARM as a day-one target** — closed by **D-002**. Yes. `arch` is a structural
  selector in the schema from M1, not a retrofit. Nine AHRL units are
  arch-conditional and 73Linux ships arch-partitioned trees. The cost of
  retrofitting is visible in AHRL's `install_gspiceui`, which hardcodes an
  `aarch64-linux-gnu` path on every architecture.

**Still open and now blocking:** station-local configuration (callsign, grid
square, rig device paths). The 1.0 packet core forces it — AX.25's install writes
`wl2k ${MYCALL} 1200 255 7 Winlink` into `/etc/ax25/axports`. See `DESIGN.md`
§15.3 and the D-004 amendment.

## Roadmap — 1.0 is AHRL parity plus the packet core

Parity is **not** "reproduce AHRL." Per `docs/PARITY-POLICY.md`, the goal is that
a user who uninstalls AHRL and installs Hammunition is **strictly better off**:
everything that worked still works, some things work that didn't, some are better
than what they replace, and the dead weight is gone *with an explanation*.
Reproducing AHRL faithfully — broken and obsolete entries included — would be a
worse product than AHRL.

Every unit gets exactly one disposition: **CARRY, SUPERSEDE, REVIVE, RETIRE, or
ADD**. No unit is left unclassified. Never inherit a `broken` verdict without
testing it ourselves.

**1.0 = AHRL parity + the 1.0 packet core** (PAT, AX.25, BPQ, ARDOP, Direwolf
with configuration) — **D-008**. VARA and HAMRS are post-1.0. Novel capability
(SIGINT, RF security, mesh) layers on top, never substitutes.

**M1 — walking skeleton.** Nothing beyond this scope unless asked.
- Manifest schema + validator
- apt backend only
- `/etc/os-release` detection for Parrot and Debian
- ~20 packages, one `ham-core` profile, seeded from the AHRL inventory
- `install`, `list`, `status`, `--dry-run`
- Container test harness for Parrot and Debian

**M2 — inventory and coverage.** *Done for AHRL* —
`docs/reference/ahrl-inventory.md` records all 95 executing units with method,
package names, build details, category, and conditionals. Headline: 57 of 95 are
not apt-installable. Remaining: the 73Linux delta inventory, and per-unit
dispositions per `PARITY-POLICY.md`.

**M3 — backend completeness.** Backends are justified by measurement, never by
convention (**D-014**). Every backend names the unit requiring it.

Measured from the inventory: **57 of 95 AHRL units cannot be satisfied by apt** —
35 source builds from bundled tarballs, 9 prebuilt binaries and data archives,
4 Python venv/pipx, 2 Python-run-in-place, 3 infrastructure, 2 launcher-only,
1 network git clone, 1 remote script piped into bash. An apt-only tool covers
40% of the parity target, and the missing 60% is precisely what users cannot
install themselves — the reason this project exists (**D-004**).

Required for 1.0: apt, source-from-tarball, source-from-git, binary/`.deb`/
archive, Python venv, pipx, **CPAN** (`aa-analyzer` needs
`Device::SerialPort`), and launcher generation (14 units need a generated
wrapper).

Measured zeros — recorded, not deleted, so they are not re-added by convention:
`cargo` 0, `flatpak` 0, `appimage` 0 in AHRL. AppImage and a configured Wine
prefix are **post-1.0**, required by HAMRS and VARA respectively. `snap` appears
11 times and is an **anti-dependency** — every occurrence is removal — so it
belongs in `system_modifications`, never as a backend.

**M4 — profiles and hardware.** Full profile set. udev rules, group membership,
firmware. Persistent device symlinks.

**M5 — parity verified.** Every unit either **installs successfully on at least
one supported distro**, or carries a `broken`/`retired` status **verified by us**
— never inherited from an AHRL shell comment. Re-attempt `ardop`,
`radiosonde_auto_rx`, and the compiler-flag-fragile set before accepting any
verdict, and record what was tested: date, version, distro, actual failure.

**Exit criterion: our install-success fraction must be at least as good as
AHRL's own.** AHRL ships 95 units with 9 disabled. Shipping 95 manifests with 40
marked broken is not parity, however complete the coverage looks. Inherited
verdicts count against us; tested-and-confirmed-dead does not. The M5 report
shows disposition, evidence, and whether each verdict was tested or inherited.

**Post-1.0 — the extension.** SIGINT and RF-security profiles, Meshtastic/LoRa,
the Parrot-specific integration. This is where Hammunition stops being "AHRL
done properly" and becomes its own thing.

**Definition of "more modern and robust":** declarative over imperative,
git over tarballs, tested over hoped-for, multi-maintainer over solo,
idempotent over run-once, dry-run over surprise, measured coverage over
assumed coverage.

## Hardware context

The maintainer's own gear drives priority for the hardware role: HackRF Pro +
PortaPack, CatSniffer V3, Free-WiLi 2, nRF52840, Meshtastic devices (T-Deck,
T-Echo, RAK/WisMesh), ClockworkPi uConsole, Yaesu FT-991A, BTECH UV-50PRO,
Panasonic Toughbook FZ-55.

Persistent udev symlinks by device serial are the highest-value feature in the
hardware role — `/dev/rig-991a`, `/dev/catsniffer`, etc., so plug order stops
mattering and downstream configs reference stable names.
