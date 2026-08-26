# Hammunition

> Pick your RF arsenal.

Hammunition turns an existing Debian-family install into an amateur radio, SDR,
and RF experimentation workstation. Primary target: **Parrot OS**. Also
targeting Debian, Ubuntu, Kali, Linux Mint and Raspberry Pi OS.

---

## ⚠️ Work in progress — this does not install anything yet

**Status: pre-alpha. Design and inventory phase. There is no working installer.**

Being honest about this up front matters more than looking finished, so here is
exactly where things stand:

| | Status |
|---|---|
| Catalog schema (Pydantic, `mypy --strict`) | ✅ working |
| Package manifests | 🟡 58 of a planned ~230 |
| Hardware catalog | 🟡 20 devices, 2 classes, 58 confirmed USB identifiers |
| Profiles | 🟡 4 written, the rest sized and named on paper |
| Inventories of all five upstream sources | ✅ complete and measured |
| Consent gates for RF-research tooling | ✅ working |
| `install` / `list` / `status` / `--dry-run` CLI | ❌ **not written** |
| apt backend | ❌ **not written** |
| Source, git, binary, venv, pipx backends | ❌ **not written** |
| udev rule generation | ❌ **not written** |

**Do not install this. There is nothing to install.** If you want a working ham
radio Linux setup today, use one of the projects in [Credit](#credit) below —
they work now, and this project exists because of them, not instead of them.

What *is* usable today is the research. `docs/reference/` contains complete,
generated inventories of five upstream projects, with per-package availability
measured inside real containers rather than assumed — and, increasingly, with
packages actually installed rather than merely reported as available, because
those two turned out to disagree.

**There is one thing you can help with right now**, and it needs no code:
[contributing hardware identifiers](docs/contributing/hardware.md). A dozen
devices in the catalog are waiting on `lsusb` output from somebody who owns
one. It takes thirty seconds and there is a script for it.

---

## What this is

Two separable halves, and keeping them separate is the point:

1. **The catalog** (`catalog/`) — YAML manifests describing software: what it is,
   what it's for, how to install it per distro, which profiles include it. Pure
   data, no executable logic. Usable by an engine that isn't ours.
2. **The engine** (`src/hammunition/`) — a Python CLI that reads manifests and
   performs installation, configuration and hardware setup.

The catalog is the durable asset. The engine is replaceable.

## What this is not

Considered and rejected, so nobody has to ask:

- A Linux distribution, custom ISO, or derivative
- A custom kernel
- A mirror of upstream Debian packages
- Forks of upstream ham/SDR software
- Anything that replaces or reconfigures your OS wholesale

We **augment** an existing system and use upstream packages wherever they exist.

---

## Credit

Hammunition is built on other people's curation. These are inventory sources and
prior art, not things we are replacing — several of them work today and this one
does not.

### Andy's Ham Radio Linux — Andy Stewart, KB1OIQ

The direct inspiration, and the closest existing thing to what we are building.
AHRL has served the amateur radio community for well over a decade, and **its
package curation is the single most valuable artifact in this space** — which
software is worth installing, which actually works, which is abandonware. That
judgement took years to accumulate and would be foolish to discard.

AHRL also arrived at the layered-onto-an-existing-OS model after years as a
distribution. That migration is strong evidence the approach is right, and it is
why building a distro is on our rejected list.

<https://sourceforge.net/projects/kb1oiq-andysham/>

### 73Linux — Jason Oleham, KM4ACK

Covers Winlink, packet and EMCOMM — PAT, BPQ, AX.25, ARDOP, Direwolf with real
configuration — a domain AHRL does not touch at all. Its community side-loading
model also shaped our three-tier catalog.

<https://github.com/km4ack/73Linux>

### Skywave Linux — Philip Collier, AB9IL

Shortwave and utility listening, remote SDR receivers, and the aeronautical
decoder cluster (ACARS, HFDL, VDL2) that is absent from Debian entirely.

<https://skywavelinux.com/>

### DragonOS — cemaxecuter

The SDR and SIGINT reference. Far larger than anything else in this space.

<https://cemaxecuter.com/>

### The Debian Hamradio Blend

Team-governed, signed and machine-readable — the best provenance in the
landscape and the cheapest coverage in this project.

<https://blends.debian.org/hamradio/>

---

## Why it exists

Not because the projects above are wrong. Because they share a governance shape
that worries us more than any technical problem: install logic and package lists
tangled together in shell, a single maintainer, and contribution by email.

| Prior art | Hammunition |
|---|---|
| Tarballs and ISOs | Git, tagged releases, signed |
| Single maintainer | Multiple maintainers, documented governance |
| Contribute by email | Pull requests, issues, public review |
| Install logic and package list intertwined | Declarative catalog, separate engine |
| Bash | Python — idempotent, dry-run, transaction log |
| No cross-distro testing | CI containers per target distro |
| Ham radio | Ham radio **plus** SDR, RF security and mesh |

The full argument, with evidence, is in [`docs/why-hammunition.md`](docs/why-hammunition.md).

---

## Security posture

This is designed to run on machines that also hold security tooling. These are
requirements, not aspirations:

- **Never pipe remote content into a shell.** There is no `method: script` in
  the schema — it is unrepresentable, not merely discouraged.
- **Checksums are mandatory** for any non-apt download. The schema requires
  `sha256`; an unverified download cannot be expressed.
- **Third-party apt repos** are declared in the manifest with the signing key
  fingerprint pinned, and shown to you before being added.
- **Every system modification is printed before it happens.** `--dry-run` is
  complete, not approximate.
- **RF tooling whose lawful use depends on your authorization** sits behind a
  profile with an affirmative consent gate that `--yes` cannot satisfy. It
  discloses what the software can do and asks you to affirm your authorization.
  It does not tell you what is legal where you are — we cannot know that, and we
  are not lawyers.
- **Tests run in rootless Podman**, never Docker. Docker group membership is
  root-equivalent host access, which is not a trade this project will make.

---

## Documentation

Everything below is written before the code it describes, deliberately.

| | |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Authoritative decision record. Where anything disagrees with it, it wins. |
| [`docs/SCOPE.md`](docs/SCOPE.md) | The five-source union and what 1.0 covers |
| [`docs/PARITY-POLICY.md`](docs/PARITY-POLICY.md) | What we carry, replace, revive, retire and add |
| [`docs/QUESTIONS.md`](docs/QUESTIONS.md) | Open questions, with recommendations |
| [`docs/reference/`](docs/reference/) | The measured inventories everything rests on |
| [`docs/reference/hardware-gaps.md`](docs/reference/hardware-gaps.md) | Every USB identifier we don't have, who can close it, and what it blocks |
| [`docs/contributing/hardware.md`](docs/contributing/hardware.md) | How to send one, and what we do and don't store |

The user-facing documentation site is *Hacker's Ham Shack*. Its standard: a
licensed ham with moderate Linux experience should get from a fresh install to a
working digital-modes station without asking anyone a question or reading a forum
thread. A step that needs knowledge not in our docs is a documentation bug.

---

## Contributing

Too early for code contributions — the engine does not exist yet. What is useful
now, roughly in order:

- **`lsusb` output for a device we don't own.** The most useful thing anyone can
  send, and it needs no code. A device whose USB identifier is guessed produces a
  udev rule that *silently never matches* — indistinguishable from a bad cable —
  so this catalog refuses to guess, and a dozen entries are waiting on one fact
  that takes thirty seconds to produce. There is a read-only script for it:
  [`docs/contributing/hardware.md`](docs/contributing/hardware.md).
- **Corrections to the inventories.** If `docs/reference/` says something wrong
  about a package you maintain or use, that is the most valuable issue you can
  file. Several of our own claims have already turned out to be wrong; each
  correction is recorded in the document that made the claim rather than quietly
  edited out.
- **Answers to [`docs/QUESTIONS.md`](docs/QUESTIONS.md).**
- **Telling us what AHRL or 73Linux got right that we have not noticed.**

An entry for hardware nobody here owns is welcome too. `identification_gap`
exists precisely so that *"this device exists and here is what Linux needs for
it"* is a shippable state rather than a blocker.

## Licence

**Two licences, split on the architectural boundary** (see
[D-023](docs/DECISIONS.md)):

| Tree | Licence | Why |
|---|---|---|
| `src/`, `scripts/`, `tests/`, `docs/` | **GPL-3.0-or-later** | Copyleft is the governance argument this project was founded on: a fork cannot close the source. It is also what the ham ecosystem already runs. |
| `catalog/` | **CC0-1.0** | The catalog must stay usable by an engine that isn't ours. Manifests record facts — that `fldigi` is packaged as `fldigi` and needs `hamlib` configured first — and CC0 removes an ambiguity rather than making a grant. |

SPDX headers throughout, per the [REUSE](https://reuse.software/)
specification; verbatim texts in [`LICENSES/`](LICENSES/).

This relicenses nothing the catalog *describes*. Every program in the inventory
keeps its own licence, recorded in
[`docs/reference/licence-verification.md`](docs/reference/licence-verification.md).
