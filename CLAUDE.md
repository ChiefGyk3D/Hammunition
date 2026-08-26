# Hammunition — Claude Code Context

> Pick your RF arsenal.

## What this project is

Hammunition turns an existing Debian-family install into an amateur radio, SDR,
and RF experimentation workstation. Primary target: **Parrot OS**. Secondary:
Debian, Ubuntu, Kali, Raspberry Pi OS.

Binary: `hammunition`. Python package: `hammunition`.

## What this project is NOT

Do not propose or build any of these. They have been considered and rejected:

- A Linux distribution, custom ISO, or derivative
- A custom kernel
- A mirror of upstream Debian packages
- Forks of upstream ham/SDR software
- Anything that replaces or reconfigures the user's OS wholesale

We **augment** an existing system. Upstream packages are used wherever they exist.

## Prior art: Andy's Ham Radio Linux (AHRL)

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

**Positioning.** We are not competing with AHRL and must not present ourselves as
its replacement in README, docs, or commit messages. We cover a domain it does
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
- `reference/` and `vendor/` are gitignored: third-party tarballs and extracted
  upstream trees are studied locally, never committed. Keep provenance clean.

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
  backends/        # apt, pipx, cargo, flatpak, appimage, source
  distro/          # /etc/os-release detection and capability resolution
  hardware/        # USB/serial detection, udev generation
  state/           # transaction log, uninstall
docs/              # "Hacker's Ham Shack" — guides and labs (section title, not a brand)
tests/
```

## Open question to resolve before the schema is final

Can a profile depend on another profile — does `sdr` pull in `ham-core`? Flat
profiles are simpler; nested ones are more useful and harder to get right. Ask
the maintainer rather than deciding unilaterally.

## Roadmap — AHRL parity is the definition of 1.0

AHRL is the baseline, not merely an influence. Hammunition 1.0 means: everything
AHRL installs, Hammunition installs, on more distros, with better mechanics.
Novel capability (SIGINT, RF security) is layered on top of parity, never
substituted for it.

**M1 — walking skeleton.** Nothing beyond this scope unless asked.
- Manifest schema + validator
- apt backend only
- `/etc/os-release` detection for Parrot and Debian
- ~20 packages, one `ham-core` profile, seeded from the AHRL inventory
- `install`, `list`, `status`, `--dry-run`
- Container test harness for Parrot and Debian

**M2 — inventory and coverage.** Extract the complete AHRL v27 package list into
manifests. Produce a coverage report: which AHRL packages are apt-installable on
each target, and which need another backend. That report drives M3 scope — do not
guess at which backends are needed, measure it.

**M3 — backend completeness.** Implement whichever backends the M2 report proves
necessary (pipx, cargo, flatpak, AppImage, source build). Parity is unreachable
with apt alone; AHRL builds some things from source, and those are exactly the
packages users cannot easily install themselves — the highest-value cases.

**M4 — profiles and hardware.** Full profile set. udev rules, group membership,
firmware. Persistent device symlinks.

**M5 — parity verified.** Automated check that every package in the AHRL
inventory resolves to an installable manifest on at least one supported distro.
Gaps are documented in the capability matrix, never hidden.

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
