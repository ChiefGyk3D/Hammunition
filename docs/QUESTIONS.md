# Open questions for the maintainer

Decisions that are the maintainer's to make, and blockers this session could not
clear. Each carries options and a recommendation. Nothing here was decided
unilaterally.

**Urgency key:** 🔴 blocks work · 🟡 blocks a milestone · 🟢 decide when convenient

---

## Q-001 ✅ RESOLVED 2026-08-25 — rootless Podman installed and working. Two degraded-mode workarounds needed locally (see SESSION-LOG); CI needs neither.

## Q-001 (original) — Container tests cannot run on this machine

**Blocks:** item 1's verification half, and every future capability-matrix claim
made locally.

The Docker daemon is running (`systemctl is-active docker` → `active`) but this
account is **not in the `docker` group**, so `/var/run/docker.sock`
(`srw-rw---- root:docker`) is unreadable. Containers were unavailable for the
whole session.

I did not fix this, deliberately. **Adding a user to the `docker` group grants
root-equivalent access to the host** — any container can mount `/` as root. On a
machine that also holds offensive security tooling, per `CLAUDE.md`, that is a
real security decision and not mine to make while you are asleep.

| Option | Trade-off |
|---|---|
| **Add the account to `docker`** | Simplest. Root-equivalent access to the host for anything that can talk to the socket. |
| **Rootless Docker** (recommended) | `dockerd-rootless-setuptool.sh install`. Containers run as your user; no root-equivalent group. Slightly slower, some networking limits. Fits this project's threat model best. |
| **Podman rootless** | Same benefit, daemonless, drop-in `docker` CLI alias. Not currently installed. |
| **CI only** | Zero local risk, but no container feedback before pushing — slow loop for backend work. |

**Recommendation: rootless Docker or Podman.** You get container tests without
handing the socket root. Whatever you pick, `scripts/run-targets.sh` already
fails loudly with these instructions rather than skipping silently.

---

## Q-002 ✅ RESOLVED 2026-08-25 — **`mypy --strict` passes clean** on Python 3.13.5 in-container. 24 errors found and fixed; `strict_equality` caught a tautological assertion, as predicted.

## Q-002 (original) — `mypy --strict` is authored but UNVERIFIED

**Depends on Q-001.**

`CLAUDE.md` requires `mypy --strict` clean. **I could not run it, and I am not
claiming it passes.**

- `mypy` is not installed on this machine.
- Installing it would violate the standing rule against installing outside a
  container.
- Containers were unavailable (Q-001).
- The host is **Python 3.10**; the project targets **3.11+**, so even a local run
  would not have tested the supported interpreter.

**What *is* verified**, with the tooling already present:

| Check | Result |
|---|---|
| `ruff check` (E, F, W, I, UP, B, SIM, **ANN**, RUF) | ✅ clean |
| `ruff format --check` | ✅ clean, 8 files |
| `pyflakes` | ✅ clean |
| `pytest` (55 tests) | ✅ pass |
| `scripts/check_doc_links.py` | ✅ clean, self-tested against a known-broken link |
| `mypy --strict` | ❌ **NOT RUN** |

The `ANN` rules cover `disallow_untyped_defs` and `disallow_incomplete_defs` —
a real slice of `--strict`, but only the annotation-presence slice.

**Not covered, and where I would look first when it does run:**

1. `disallow_any_generics` — bare `dict`/`list` in annotations.
2. `warn_return_any` — `capability_matrix.py` reads YAML, which is `Any`;
   returns are annotated but the plugin may still object.
3. The **pydantic mypy plugin** with `init_typed = true` — `model_validator(mode="after")`
   methods return the class name rather than `typing.Self`. Valid under
   `from __future__ import annotations`, but `Self` is available on 3.11+ and
   may be what the plugin wants.
4. `strict_equality` — the enum-vs-`Literal` comparisons in the tests. One of
   these already bit us: `toolkit_risk.framework` is a `Literal`, not an enum, so
   `.value` raised `AttributeError` at runtime. mypy would have caught it
   statically.

**Recommendation:** resolve Q-001, then `make venv && make types`. Expect a
handful of findings — point 4 above is evidence the code is not yet proven, and
I would rather say so than let it pass on silence.

---

## Q-003 ✅ RESOLVED 2026-08-25 — target renamed `debian-13-arm64`, `claims: aarch64-only`. Pi stays untested until verified on uConsole hardware.

## Q-003 (original) — Raspberry Pi OS has no container image

`containers/targets.yaml` uses `debian:13` on `linux/arm64` as the closest
honest proxy. It exercises the `aarch64` selectors, which is most of the value,
but it is **not** Raspberry Pi OS: different kernel, different firmware,
different default packages, and none of the Pi-specific hardware paths.

| Option | Trade-off |
|---|---|
| **Keep the proxy, label it honestly** (recommended) | Free arch coverage now; the capability matrix must say "arm64 proxy, not Pi-verified". |
| Build our own Pi OS image from the official rootfs tarball | Accurate; ongoing maintenance and a large image. |
| Self-hosted runner on real Pi hardware | Most accurate; needs hardware you own and expose to CI. |

**Recommendation:** keep the proxy and never let the capability matrix claim Pi
coverage from it. The uConsole and Pi are named target devices, so this becomes
a real gap at M4 when hardware support lands.

---

## Q-004 ✅ RESOLVED 2026-08-25 — `linuxmint-22.3` added, pinned to `linuxmintd/mint22.3-amd64`.

## Q-004 (original) — Ubuntu 26.04 is in CI but not in `CLAUDE.md`'s target list

`CLAUDE.md` names Parrot, Debian, Ubuntu, Kali and Raspberry Pi OS. AHRL's own
tested set includes Ubuntu/Xubuntu/Kubuntu 26.04 and Linux Mint 22.3, and one
manifest (`js8call`) already branches on **Linux Mint 22.3** specifically.

So the catalog has a Mint-specific selector while Mint is in no target list and
no CI job.

**Recommendation:** add Linux Mint 22.3 as a declared target. It is cheap
(`linuxmintd/mint22-amd64` or equivalent) and we are already writing manifests
against it — an untested selector is worse than no selector.

---

## Q-005 ✅ RESOLVED 2026-08-25 — BPQ: pinned tag. `catalog/packages/linbpq.yaml` written.

## Q-005 (original) — BPQ: the licence assumption was wrong, and there is a third option

**Blocks:** the 1.0 packet core (D-008). **Resolves:** `DESIGN.md` §15.6.

You asked me to check the condition before deciding, and the condition came back
the opposite way. **linbpq is GPL-3.0-or-later** — explicit grant in the source
headers, Copyright 2001-2018 John Wiseman G8BPQ, verified against seven sampled
files. Full evidence in `docs/reference/licence-verification.md`.

More usefully: **upstream publishes version tags** (`25.39`, `25.36`, `25.35`,
…). The unversioned `/Downloads/Beta/` URLs are how *73Linux* installs it, not
how upstream publishes it. We were about to inherit someone else's packaging
problem.

| Option | Assessment |
|---|---|
| Mirror binaries with our own hashes | Your conditional pointed here, and it is now permitted. But it means hosting, bandwidth, a GPL source-offer obligation for the binaries we redistribute, and staying in step with a project that committed **today**. |
| `status: unverifiable`, opt-in | No longer warranted. It would tell users this package is uniquely untrustworthy when it is a normal GPL project with tagged releases. |
| **Build from a pinned git tag** ⭐ | Structurally identical to AIS-catcher (shape 6). `ref: "25.39"`, declared `build_depends`, no unverified download, no hosting, no GPL redistribution question. |

**Recommendation: build from a pinned tag.** It is the option that makes BPQ
ordinary instead of special, and "this package is not actually a special case"
is the best available outcome.

Two things to decide when you pick:

1. **Which tag.** `25.39` is newest; upstream tags frequently and does not cut
   releases, so tag selection is a judgement call about stability.
2. **What we lose.** 73Linux also fetches a prebuilt `pibpqConfigGen`, HTML
   pages, and a sample `bpq32.cfg`. Some are KM4ACK's own work and unlicensed
   (D-001), so they cannot come with us regardless. BPQ needs real configuration
   to be useful, which lands it in the same bucket as Direwolf: *installed with
   configuration, not merely installed*.

**I did not write a BPQ manifest.** The finding is recorded; building the packet
core is not in this queue.

---

## Q-006 ✅ — Which HamClock? — **RESOLVED 2026-08-29**

**Adopted as recommended.** Carry both clients; `openhamclock` is the default;
the backend endpoint defaults to `ohb.works`, which
`catalog/packages/hamclock-next.yaml` now records as settled.

**But `openhamclock` cannot be installed yet, and that was not known when the
recommendation was written.** It is not the C++ program the original HamClock
was: at tag v26.6.0 it is a Node and Vite web application — `package.json`,
`vite.config.mjs`, `server.js`, an `electron/` directory, a `Dockerfile` — and
its releases publish no binary assets. It needs an `npm` backend this project
does not have. See `docs/reference/source-build-gaps.md` #7. The decision
stands as a preference; `hamclock-next` is what ships until the backend exists.

The untested caveat below also still stands and is now a task rather than a
question: nobody has run a HamClock client end to end against either backend.

## Q-006 (original) — Which HamClock, now that there are four options?

**Blocks:** nothing immediately. **Changes:** the SUPERSEDE #1 rationale, and any
public copy about HamClock.

Tested 2026-08-25 rather than reported. The forecast was wrong: HamClock did not
stop. `hamclock.com/ham/HamClock/version.pl` serves **4.27** with a feature
changelog. Elwood's own server (`clearskyinstitute.com`) *is* gone — it refuses
TCP — but the hostname AHRL points at is live and maintained.

| Option | State | Licence | Consideration |
|---|---|---|---|
| **`accius/openhamclock`** ⭐ | 455 stars, pushed 2026-08-22 | MIT | Most active by a wide margin. ARRL EMA covered it. Continuation of the original codebase. |
| **`k4drw/hamclock-next`** | 34 stars, pushed 2026-06-23 | MIT | Full SDL2 rewrite. Carries Elwood's copyright forward explicitly. Smaller, newer, less proven. **This is the unit AHRL defines and never calls (D-013).** |
| **hamclock.com** backend | Live, 4.27 | service | Third-party, patron-funded — "$4.99/month is what keeps the backend on the air" — plus an Amazon Appstore listing. Works today; commercial direction unknown. |
| **`ohb.works`** | HTTPS 200 | service | Open HamClock Backend. Recommended by Amateur Radio Daily. A backend only; you still need a client. |

**Recommendation: CARRY both clients; default to `openhamclock`; default the
backend endpoint to `ohb.works`.**

Reasoning:

- **openhamclock as client default** — 13× the community of hamclock-next and
  pushed three days ago. It is the continuation people actually use.
- **hamclock-next carried, not dropped** — it is a genuine rewrite, it honours
  the original author, and it is the D-013 worked example. Dropping the unit that
  proves our central design argument would be a poor trade.
- **`ohb.works` as the endpoint default** — a community backend is a better
  default than a commercial one for software we install on someone's behalf.
  hamclock.com stays available; `service_endpoints` is user-configurable by
  design, which is the whole point of shape 7.

**One thing I could not test:** no HamClock client was run end to end. Two of six
guessed endpoint paths responded; the four 404s are as likely to be my wrong path
names as missing functionality. Before defaulting anyone to `ohb.works`, someone
should run a real client against both and confirm.

---

## Q-007 ✅ — SuperSDR has no licence. Do we carry it? — **RESOLVED 2026-08-29**

**Yes, carry it** — and the reasoning generalises, so it is recorded as
**D-033** rather than left as one unit's exception. A missing licence is
weighed against how widely the community already relies on the software and
against what this project actually does with it, which is fetch it from the
author's own server at install time rather than redistribute it. Most authors
of small ham utilities are not lawyers; a missing LICENSE is usually an
oversight, not a reservation of rights.

The manifest must still state the position plainly: no LICENSE, no header, null
GitHub licence field, and a last commit of 2022-12-31 — all measured, none of it
implied to be permission.

**It cannot be written yet, for a reason unrelated to the licence.** At tag
v3.14 SuperSDR is `supersdr.py` beside a frequency database, two fonts, two
images and two vendored Python packages, with no `setup.py` and no install
rule. It runs from the directory it was unpacked into. That needs installing a
tree and generating a launcher, neither of which exists — see
`docs/reference/source-build-gaps.md` #8, which `js8spotter` and `mshv` share.

## Q-007 (original) — SuperSDR has no licence. Do we carry it?

**Raised by:** item 3, the Skywave inventory. **Blocks:** the `listening` profile's
remote-SDR story. **Changes:** whether Hammunition ships a KiwiSDR client at all.

`mcogoni/supersdr` — Skywave's KiwiSDR client, shipped as v3.14 in Skywave 5.10 —
carries **no `LICENSE`, no `COPYING`, and no per-file header.** Verified by reading
the repository tree and `supersdr.py` itself, not inferred from GitHub's metadata,
which was wrong in the other direction for `acarsdec` in the same pass. Default
copyright therefore applies: all rights reserved.

**Correction, 2026-08-28 — this question was posed with a wrong fact in it.** It
said upstream was "active (2026-02-18)". That date is GitHub's `updated_at`, which
moves when somebody *stars* a repository. The newest commit on SuperSDR's default
branch is **2022-12-31**. It is not active; it has been untouched for three and a
half years. The whole table below was measured the same wrong way and is corrected
with default-branch commit dates.

This is the **D-001** situation again, and it lands on the single most visible piece
of the listening delta. Worse, the alternatives are no cleaner:

| Client | Licence | Last commit (default branch) |
|---|---|---|
| `mcogoni/supersdr` | **none** | **2022-12-31** — dormant; the one Skywave ships |
| `jks-prv/kiwiclient` | **none** — nothing in README or sources | **2026-08-03** — the only maintained one, and a CLI |
| `llinkz/directKiwi` | WTFPL-style grant in README prose; no licence file | **2023-03-03** — dormant |

There is no cleanly-licensed KiwiSDR client in this ecosystem, and the only one
still being worked on is the CLI.

**What is and is not at stake.** We do not redistribute source, so installing from
upstream at a pinned ref is not the problem `.bapp` was. The problems are that we
could not vendor a patch, could not carry a fork if upstream went quiet, and would
be pointing users at software whose author has granted them nothing in writing.

| Option | Consequence |
|---|---|
| Option | Consequence |
|---|---|
| **A. CARRY `supersdr`, pinned, with the licence state recorded in the manifest** ⭐ | Users get the client that works. `status`/`licence` fields make the risk visible rather than hidden. No forking, no patching — if upstream disappears, so does the unit. **Weaker than it looked:** the software is also three and a half years stale, so "if upstream disappears" is closer to "upstream already has". |
| B. Ask upstream to add a licence first | Right thing to do regardless, and free to attempt. Cannot be a blocker: we do not control the answer or its timing. **Less likely to land** on a repository whose author has not committed since 2022. |
| C. RETIRE the whole client cluster; document browser access only | Honest and clean. Also removes the on-ramp for the user who owns no hardware, which `SCOPE.md` calls the point of the listening delta. |
| D. Carry `kiwiclient` instead | Same licence status, and a CLI rather than a GUI — but it is the **only one of the three still maintained** (2026-08-03). On the corrected dates this is no longer plainly worse than A. |

**Recommendation, revised 2026-08-28: still A, but with less confidence, and D is
now a real contender.** The licence position is unchanged and is the same class of
decision as D-001. What changed is that A's software is dormant, so carrying it
buys a client that will not gain fixes, while D buys a maintained one at the cost
of a CLI instead of a GUI. Carry pinned either way, record
`licence: unlicensed-default-copyright` in the manifest so the catalog states the
fact rather than eliding it, and open a polite upstream issue asking for a licence.

The dormancy is a fact about the software, not a verdict: **PARITY-POLICY.md** is
explicit that "finished" is a legitimate state for a tool to be in, and a KiwiSDR
client that works against a stable protocol may simply be done. It is recorded
because it changes the trade-off, not because it settles it.

**This is your call, not mine** — it is the same class of decision as D-001, which
you made deliberately.

---

## Q-008 ✅ — Does the RF-security profile include cellular interception tooling?
— **RESOLVED 2026-08-29**

**Option A now, D later — and D is a commitment, not a maybe.** Recorded as
**D-034**. The cellular cluster is carried in full and *staged*: receive-and-
decode tooling ships in the consent-gated `rf-research` profile for 1.0, and the
transmit-capable network stacks land post-1.0 in a separate consent-gated
`cellular` profile with its own `env_var`.

The dividing line is **transmit, not topic**. The excluded units are scheduled
rather than refused, and each gets an entry saying so — "not yet" and "not ever"
are different claims.

## Q-008 (original) — Does the RF-security profile include cellular interception tooling?

**Raised by:** item 4, the DragonOS Tier 1 inventory. **Blocks:** the shape of the
`sigint` / RF-security profile, and therefore item 5's naming work. **Changes:**
what Hammunition is willing to install on someone's behalf.

DragonOS Resolute R1 devotes 20 of its 99 README units to **Cellular / EW**:
`srsRAN_4G`, `Osmocom core` (bsc/bts/msc/hlr/mgw/pcu/sgsn/ggsn/stp/cbc),
`osmo-trx`, `OsmocomBB`, `LTESniffer`, `FALCON`, `intrusive-lte-mme`, `sni5gect`,
`IMSI-catcher`, `QCSuper`, `gr-gsm`, `cmas-pws-4g` and others. `SCOPE.md`
describes DragonOS as "the SIGINT delta" without distinguishing this cluster from
`rtl_433` and `inspectrum`. They are not the same kind of thing.

**The line that matters is transmit, not topic.**

| Class | Examples | Character |
|---|---|---|
| Passive receive | `gr-gsm`, `IMSI-catcher`, `QCSuper`, `FALCON`, `LTESniffer`, `cmas-pws-4g` | Receives and decodes signals already in the air. Legality varies by jurisdiction — interception statutes, not spectrum rules. |
| **Active transmit** | `srsRAN_4G`, `Osmocom core`, `osmo-trx`, `intrusive-lte-mme`, `sni5gect`, `ella-core`, `ocudu` | Operates a cellular network. In the US this engages FCC licensing *and* federal interception law; an ordinary user has no authorisation for either. |

DragonOS states the constraint itself — its README qualifies `intrusive-lte-mme`
as *"authorized RX/active use"*. Its audience has authorisations ours generally
will not: red teams under contract, labs with shielded benches, vendors, academics.

**This is not a question about whether the software is legitimate.** It is. The
question is whether a one-command installer aimed at licensed hams is the right
delivery mechanism, given that the distance between "installed" and "transmitting"
is one command and the user may hold no authorisation at all.

| Option | Consequence |
|---|---|
| **A. Receive-only subset in the opt-in RF-security profile; transmit-capable cellular out of 1.0** ⭐ | Keeps `gr-gsm` (already apt on Debian 13, Kali and Parrot), `QCSuper`, the LTE decoders. Requires the legal/ethical framing CLAUDE.md already mandates for `docs/rf-security/`. Nothing is hidden — the excluded units get an entry saying why, per `PARITY-POLICY.md`'s RETIRE rules. |
| B. Include everything behind an explicit opt-in and a strong warning | Matches DragonOS's own posture and treats the user as an adult. Puts a rogue-base-station stack one `hammunition install` from a machine that also holds offensive tooling. |
| C. Exclude the whole cellular cluster, receive and transmit alike | Simplest to defend. Also drops `gr-gsm`, which `PARITY-POLICY.md` already lists as an ADD and which every one of our targets packages. |
| D. Separate `cellular` profile, documented as requiring authorisation, post-1.0 | Defers the decision without pretending it does not exist. Compatible with A. |

**Recommendation: A now, D later.** Ship the receive-only subset in the opt-in
RF-security profile for 1.0 with the legal framing the docs already require, and
keep a `cellular` profile as an explicit post-1.0 question once there is a real
policy and real documentation behind it. Record the excluded units with a reason
rather than dropping them silently.

**Why this is 🔴 rather than 🟡:** it is the only open question that changes what
the tool is willing to do to a user's machine, and item 5's profile naming cannot
be finished without it — `sigint` means different things under A, B and C.

---

## Q-009 ✅ — What licence does Hammunition ship under? — **RESOLVED 2026-08-26**

**Raised by:** publishing the README. **Blocks:** any outside contribution, and
arguably the repository being public at all. **Changes:** who can use, fork,
package or contribute to this.

There is **no `LICENSE` file in the repository** and no licence header on any
source file. Default copyright therefore applies: all rights reserved, nobody
may copy, modify or redistribute.

**This is exactly the objection this project raises about other people's work.**
D-001 declines to build on 73Linux because it has no licence file. Q-007 flags
SuperSDR for the same reason. Shipping a public repository in that state while
criticising it in two decision records is not a position that survives contact
with anyone who reads both.

**The catalog and the engine may want different answers**, which is the real
question here rather than a detail:

| | Consideration |
|---|---|
| **The catalog** (`catalog/`, `docs/reference/`) | The durable asset, and deliberately designed to be usable by an engine that is not ours. A permissive or data-oriented licence maximises that. It is closer to a database than to a program. |
| **The engine** (`src/hammunition/`) | Ordinary software. Copyleft is defensible and matches most of the ham ecosystem. |

| Option | Consequence |
|---|---|
| **A. GPL-3.0-or-later throughout** ⭐ | Matches AHRL, 73Linux's tooling, Skywave's scripts, and most ham software. Familiar to this audience. Strongest guarantee that a fork stays open — which is the governance argument the project is founded on. Copylefts the catalog too, which slightly undercuts "usable by an engine that isn't ours". |
| B. GPL-3.0-or-later engine, CC0 or MIT catalog | Matches the architecture invariant exactly: the catalog is data anyone may use, the engine is copyleft software. Two licences to explain, and contributors must understand which tree they are in. |
| C. Apache-2.0 throughout | Permissive, explicit patent grant, good for contribution from companies. Loses the copyleft guarantee that a commercial fork stays open. |
| D. AGPL-3.0 | Overkill — nothing here is a network service. |

**Recommendation: B**, and A if you want one licence and no explaining. B is
what the architecture actually describes: `docs/reference/` is measurement,
`catalog/` is data, and both are more valuable the more freely they travel.
The engine is where the copyleft argument has force.

**Also needs deciding with it:** whether contributions require a DCO sign-off
(`git commit -s`) or a CLA. Recommendation: **DCO, not a CLA** — a CLA is a
barrier to exactly the drive-by manifest contributions this project wants, and
the multi-maintainer governance argument does not need one.

**Resolved: option B.** `LICENSE` is GPL-3.0-or-later over `src/`, `scripts/`,
`tests/` and `docs/`; `catalog/LICENSE` is CC0-1.0. The split follows the
architectural boundary — copyleft where the governance argument has force,
CC0 where the invariant requires the data travel freely. SPDX headers per REUSE.
Recorded as **D-023**, and answered in `why-hammunition.md` in the same document
that raises the criticism of other projects for lacking one.

DCO-versus-CLA is still open and carried into D-023's "still open" section; the
recommendation of **DCO, not a CLA** stands unopposed.

---

## Q-010 ✅ — Accept a separate `rfid` profile? — **RESOLVED 2026-08-26**

**Raised by:** item 3, the device catalog. **Blocks:** where Proxmark3 lands.
**Changes:** the profile set, which is user-facing and hard to rename later.

Your instruction was to recommend a separate `rfid` profile rather than folding
RFID into `rf-security`, on the grounds that it is a different domain and mixing
them muddies both. Recorded here as a recommendation because the profile set is
yours to approve — `profile-sizing.md` treats naming as a deliverable for the
same reason.

**The argument holds on the evidence, and gets stronger the closer you look.**

| | `rf-security` | `rfid` |
|---|---|---|
| Range | metres to kilometres | centimetres |
| Hardware | SDRs, Wi-Fi and Bluetooth adapters | purpose-built readers |
| Software | apt-installable across four targets | **packaged on one target of four** |
| Skills | spectrum, modulation, DSP | card protocols, cryptography, key recovery |
| Overlap | — | essentially none |

The packaging point is the decisive one. Every unit in `rf-security` installs
from apt on at least one target.

> **Correction, 2026-08-26.** This section previously said *"No target packages
> a Proxmark client at all"*. **That is wrong.** Kali rolling ships
> `proxmark3 4.21611-0kali1`, which corresponds to upstream's `v4.21611` tag.
> Debian 13 and Parrot do not package it, and no target ships a Proxmark udev
> rule — both measured in containers today. The claim was inherited from a
> narrower probe and not re-checked before it was used as the decisive argument.
> It should have been, which is what D-018 exists to say.

The corrected picture does not change the answer and barely weakens it: the
client is absent on **three of four targets including the primary one**, so
`rfid` still cannot ship without the source backend, and folding it into
`rf-security` would still make an otherwise apt-only profile depend on that
backend. `libnfc-bin` is in Debian 13 and covers PN53x readers, but that is a
different device family from a Proxmark and reaches only 13.56 MHz. So `rfid`
is not just a different domain; it has a different *cost*, and burying that
inside `rf-security` would hide it.

| Option | Consequence |
|---|---|
| **A. Separate `rfid` profile, post-1.0** ⭐ | Honest about the cost — it needs the source backend before it can ship anything. Keeps `rf-security` fully apt-installable, which is its main virtue. |
| B. Fold into `rf-security` | One fewer name. Makes an apt-only profile depend on the source backend, so `rf-security` stops being cheap. |
| C. No RFID at all | Loses a domain the maintainer actively works in and hardware they own. |

**Recommendation: A.** Not gated by **D-021**: reading a card you hold is not the
kind of capability the consent taxonomy is about, and `third_party_systems`
already covers testing systems you do not own if that ever becomes relevant.

`catalog/hardware/devices/proxmark3.yaml` is written and its identifier is
flagged unconfirmed — Proxmark hardware spans several generations with different
identifiers and none is in a distribution rule to read from.

**Resolved: A.** `catalog/profiles/rfid.yaml` ships post-1.0 with six packages:
`libnfc-bin`, `libfreefare-bin`, `mfoc`, `mfcuk`, `pcsc-tools` and `proxmark3`.
Five are apt on all three probed targets; `proxmark3` is apt on Kali and a
pinned source build everywhere else, using the same `v4.21611` tag Kali packages
so a user does not end up on a different client version depending on their
distribution.

Ungated, and this is the closest call in the catalog. Reading a card you are
holding involves no third party, no protected communication and no spectrum;
`third_party_systems` is a property of what an operator chooses to do rather
than of what the profile installs. Gating routine software is what teaches
people to dismiss gates.

---

## Q-011 ✅ — Accept a `workstation` profile, and what goes in it? — **RESOLVED 2026-08-26**

**Raised by:** item 5, the VS Code manifest. **Blocks:** where `code` lands — it
currently declares `categories: [workstation]` against a profile that does not
exist. **Changes:** the profile set, and arguably the scope of the project.

The VS Code manifest has nowhere to go. It is not radio software, and every
existing profile is. `profile-sizing.md`'s set is entirely RF: `station`,
`logging`, `morse`, `propagation`, `digital-modes`, `packet`, `satellite`,
`antenna`, `sdr`, `listening`, `electronics`, `rf-security`.

**The case for it.** A lab machine needs an editor, a terminal, git tooling and
a shell setup, and a person building a station is usually also building the
machine it runs on. Every one of those is apt-installable on all four targets,
so it is the cheapest profile in the catalog. It also gives displacement cases
like `code` a home instead of an orphaned category.

**The case against, and it is not weak.** This is scope creep in its most
plausible costume. There are a thousand dotfile projects and this is not one of
them; every hour spent choosing between `tmux` and `zellij` is an hour not spent
on the source backend. It also invites bikeshedding from people who care
enormously about editors, on a project whose actual difficulty is packaging.

| Option | Consequence |
|---|---|
| **A. Minimal `workstation`, tightly scoped and opt-in** ⭐ | Editor, terminal, git tooling, serial console. Roughly 8-12 packages, all apt. Gives `code` a home. Scope defended by keeping it deliberately boring. |
| B. No profile; drop the `code` manifest | Smallest scope. Also discards a worked example of **D-022** that took real research — the Microsoft key fingerprint is verified and the trade-off is documented. |
| C. No profile; keep `code` uncategorised | Leaves a manifest referencing a category nothing defines, which the profile cross-check in `load_profiles` is designed to catch. Worst of both. |
| D. Broad `workstation` with shell, prompt, dotfiles | This is the scope creep. Not recommended. |

**Recommendation: A, with the contents fixed now so it cannot grow quietly.**

| Package | Why |
|---|---|
| `git` | Every workflow here assumes it |
| `tio` | Serial console — already a `badgelife` class dependency, so it is not new scope |
| `minicom`, `screen` | The serial consoles people already know |
| `tmux` | Sessions that survive a dropped SSH connection to a field machine |
| `codium` | The editor the primary target already ships |
| `code` | Opt-in, per **D-022**, never a default |
| `usbutils`, `pciutils` | `lsusb` is step one of every hardware problem in this catalog |

**Deliberately excluded:** shells, prompts, dotfiles, window managers, fonts,
terminal emulators beyond what serial work needs. If it is a matter of taste, it
is not in scope. Recommend writing that exclusion into the profile's
`deliberately_excludes` so it is enforced by documentation rather than by
argument.

`usbutils` is the one that earns its place twice: half the hardware entries in
`catalog/hardware/` say "run lsusb and record what you see", and six of them
cannot be completed without someone doing exactly that.

**Resolved: A, with the contents above.** `catalog/profiles/workstation.yaml`
ships with all nine, and the exclusion list is written into the profile's
`deliberately_excludes` — a required schema field — so it travels with the
profile rather than living in a review comment.

Two things the implementation measured that the recommendation assumed:

- **`codium` is not in Debian 13 or Kali.** Only Parrot ships it (1.126.04524,
  measured 2026-08-26). Everywhere else it needs VSCodium's own apt repository,
  which gets the same D-022 treatment as Microsoft's: declared, fingerprint
  pinned (`1302DE60…F433B132`, read from the published key), shown before it is
  added. Being the freer option is not a reason to skip a disclosure.
- **A package can be a distribution default on one target and a third-party repo
  on another**, and `recommended_default` is per-manifest while the behaviour is
  per-target. `codium` takes the conservative reading — false everywhere —
  because the alternative silently adds a repository on Debian. This will recur;
  it is recorded in the manifest rather than rediscovered.

---

## Q-012 ✅ — What copyright holder string do the SPDX headers name? — **RESOLVED 2026-08-26**

**Raised by:** implementing D-023. **Blocks:** nothing — a default is in place
and is trivially changed by one sed. **Changes:** who is named on 58 files.

Every file now carries `SPDX-FileCopyrightText: 2026 The Hammunition
contributors`.

| Option | Consequence |
|---|---|
| **A. `The Hammunition contributors`** ⭐ | Current default. Matches the project's founding argument — multiple maintainers from day one — and needs no update when the second one arrives. Standard for community projects. Slightly abstract if anyone ever needs to identify a rights holder. |
| B. A named individual | Unambiguous rights holder. Contradicts the governance pitch on the first line of every file, and needs revisiting the moment someone else contributes. |
| C. An entity or foundation | Cleanest if one ever exists. None does. |

**Resolved: none of the above.** `Copyright (C) 2026 Renegade Penguin LLC`.

The option list missed the answer, and the reason is worth keeping: I framed it
as handle-versus-abstraction and treated an entity as hypothetical ("cleanest if
one ever exists"). The maintainer had one. An LLC is a **legal person**, which
resolves the enforceability problem a handle-only line has — a handle cannot
enforce a licence — and it keeps the maintainer's legal name out of a public
repository, which the other options did not.

Applied to 115 files, `REUSE.toml`, `CONTRIBUTING.md` and the README footer.

**Not applied to `LICENSE` or `catalog/LICENSE`.** Those are the verbatim GPL-3.0
and CC0-1.0 texts from Debian `base-files`, and their checksums are asserted in
`tests/test_licensing.py`; a project copyright line inserted into either would
corrupt the licence. The GPL's own template at its line 635 is part of that text,
not a field to fill in, and CC0 is a waiver — a copyright notice printed inside
it would contradict the instrument.

`CONTRIBUTING.md` states what the company name does **not** mean, because people
reasonably assume otherwise when one appears in copyright headers: **no CLA, no
copyright assignment.** Contributors keep copyright on their own work under
GPL-3.0-or-later; contributions from the LLC are the LLC's. Handles remain fine
for attribution everywhere it appears. That also settles the DCO-versus-CLA
question D-023 left open, in the direction it recommended.

---

## Q-013 ✅ — How does SDR++ get into the catalog, if at all? — **RESOLVED 2026-08-26**

**Raised by:** `install-verification.md`, which found SDR++'s release assets hang
off a rolling `nightly` tag — a URL that never changes with an artifact behind it
that does. **Blocks:** whether SDR++ ships at all. **Changes:** nothing else; it
is one manifest.

You asked me to check whether upstream tags releases in git even where the
binaries do not, and said: if so, build from source at a tag; if not, mark it
`unverifiable` behind explicit opt-in.

**Upstream does tag. The tags are abandoned.** Measured 2026-08-26:

| | |
|---|---|
| Newest release tag | `1.0.4`, commit `f539cfa`, **2021-10-18** |
| `nightly` tag | commit `0521679`, 2024-01-17 |
| `master` HEAD | commit `8c9f5ee`, **2026-07-04** |
| Commits `1.0.4` → `nightly` | **541**, and more since |
| Version DragonOS reports | 1.3.0 — **corresponds to no git tag at all** |

So neither branch of your instruction quite fits. Building at `1.0.4` gives a
program five years old that nobody runs and that no bug report will match.
Marking it unverifiable would be wrong for a reason worth stating plainly:
**every commit on master is an immutable, content-addressed SHA, which is a
stronger pin than a tag.** The schema already knows this — `GitInstall.ref`
accepts a SHA or a tag and rejects branch names by name. Nothing about this
software is unpinnable; only its *binaries* are.

| Option | Consequence |
|---|---|
| **A. Source build pinned to a commit SHA** ⭐ | `ref: 8c9f5ee8fe405775bfcd62c8c8f8c0fc928a64af` (2026-07-04). Fully pinned and reproducible. Costs us a curation judgement upstream does not make — which commit, and when to move — and that judgement has to be recorded and re-tested each time it moves. Needs the source-from-git backend, which is not written. |
| B. The `nightly` `.deb`, `sid` variant | The only artifact that installs on both probed targets. Unpinnable by construction: rolling tag, no version, no published checksum. This is the shape the schema exists to forbid, and admitting it would make `RemoteArtifact`'s mandatory `sha256` a suggestion. |
| C. Apt where available | `sdrpp` is packaged on Kali and Parrot but absent from Debian 13 and Ubuntu 26.04. Cheapest, and covers two targets honestly, but leaves the primary-target-adjacent Debian case empty. |
| D. Do not carry it | Loses one of the more popular SDR front-ends. |

**Recommendation: A and C together** — apt where the distribution packages it,
a SHA-pinned source build elsewhere, which is exactly the shape `proxmark3.yaml`
already uses. Not B under any circumstance: the reason to have a mandatory
checksum field is that it is not negotiable when it is inconvenient.

**The honest cost of A**, so it is not discovered later: pinning a SHA with no
upstream release signal means *we* decide when to move it, and every move is a
re-test. That is real maintenance we would be taking on because upstream stopped
tagging. It may be a reason to prefer C alone and document the Debian gap.

**Resolved: A and C, generalised into D-024 rather than settled as one
manifest.** Projects that have stopped tagging get pinned to a *reviewed*
commit: `GitInstall.pin_review` records when, by whom, why that commit, and the
cadence after which it must be looked at again. The schema rejects a SHA without
one and a tag with one; `scripts/check_pin_reviews.py` reports staleness on a
weekly CI schedule rather than on every push, so a rolled-over date never fails
an unrelated pull request.

**The implementation improved on the recommendation.** The pin is not master
HEAD. Kali and Parrot both package SDR++ as a git snapshot at `36ea9a1` — the
distributions hit the same problem and answered it the same way — so pinning
their commit means a source build and an apt install are the same revision.
Two commits older than master, and worth it: someone else's packaging is the
review signal upstream stopped providing, and it is a better one than our own
preference for recency.

---

## Q-014 ✅ — The Mint container was never Mint. — **RESOLVED 2026-08-28**

Resolved by the maintainer: Mint should be genuinely container-tested, not
declared-untested. And it can be, honestly. The `linuxmintd/mint22.3-amd64`
image is built from Ubuntu and ships Ubuntu's `base-files` (hence
`ID=ubuntu`), but it carries `packages.linuxmint.com` (the `zena` suite =
Mint 22.3) and Mint's own apt preferences pinning it. Mint's `base-files` is
a version *downgrade* from Ubuntu's security update, so the image never
installed it. The target build now installs `base-files/zena` — Mint's own
signed package from Mint's own repo — which sets `ID=linuxmint`,
`VERSION_ID=22.3`, the identity a real Mint ISO ships and its priority-700
pin keeps. Not a forged file (the shim the capability-matrix rules forbid):
the distribution's own package completing an incompletely-built image. The
`linuxmint-22.3` target is restored to `containers/targets.yaml` with
`identity_package: base-files/zena`, and js8call's Mint-specific selector is
now exercised against a real Mint os-release. Verified: the built image
reports `linuxmint 22.3`, the drift check passes, and the full suite is green
inside it. Option 1 (declared-but-untested) is therefore moot — option 2
(real coverage) turned out to cost one build arg, not a VM.

**Raised by:** the engine's `--check` drift guard, first run 2026-08-28.
**Blocks:** honest capability-matrix claims for Linux Mint 22.3, one of
CLAUDE.md's named secondary targets. **Changes:** whether `js8call`'s
Mint-specific selector — the only distro-version branch in the catalog — is
ever exercised against a real Mint.

**What was found.** The `linuxmint-22.3` CI target (Q-004) ran
`linuxmintd/mint22.3-amd64:latest`, the closest thing to an official Mint
container image. The first code to ever read that image's own identity found
`/etc/os-release` inside is **Ubuntu 24.04's, verbatim**: `ID=ubuntu`,
`VERSION_ID="24.04"`. The engine keys distro detection on `/etc/os-release`
by decision, so inside that container Hammunition correctly reports Ubuntu
24.04 — a release we do not otherwise target — and the `linuxmint` selector
the target existed to exercise can never match. Every green run it produced
was false coverage. The target is removed; the finding is recorded in
`containers/targets.yaml` where the entry used to be.

**What was NOT done.** Writing Mint's os-release into the image from the
Dockerfile would make the selector match. That is a forged identity — the
"shim to make an unsupported combination appear to work" that CLAUDE.md's
capability-matrix section forbids — and it would test our ability to write a
file, not Mint.

**Options.**

1. **Leave Mint as declared-but-container-untested**, exactly like Raspberry
   Pi OS: the selector is verified by unit tests against a captured Mint
   os-release, the capability matrix says `untested`, and the docs say why.
   Zero cost, fully honest, and the js8call Qt-version claim (Mint 22.3 ships
   Qt 6.4.2) remains a claim taken from packaging data rather than a test.
2. **A periodic VM-based job** (Vagrant/qemu with the real Mint ISO), run on
   a schedule rather than per push. Real coverage, meaningful cost: a new CI
   mechanism for one selector on one package.
3. **Drop the Mint-specific branch from js8call** and let Mint users get the
   source build path. Removes the only consumer of the selector, which would
   also remove the reason Mint is more than an `ID_LIKE=ubuntu` footnote.

**Recommendation:** option 1 now, option 2 only if Mint-specific divergence
grows past a single package. The Raspberry Pi OS precedent (Q-003) is exactly
this shape and has held up: an honest `untested` beats a green lie, and D-018
already commits the project to not claiming what it has not run. Option 3
throws away a measured, real difference (the Qt 6.4.2 gap is a fact about
Mint 22.3) to simplify bookkeeping, which is backwards.

## Q-015 — The NEEDS-DECISION batch: fourteen units, one sitting

**Raised 2026-08-30.** Every unit below is dispositioned NEEDS-DECISION in
`docs/reference/dispositions.md`, each with its question already stated there.
They are the last judgment calls between the catalog and full coverage of the
five-source union, and none is design work — each is a yes/no/stage call.
Recommendations follow the precedents already set (browser/notepadqq/xosview
for scope, Q-006/Q-007 for defaults, D-034 for staging).

| Unit | The question | Recommendation |
|---|---|---|
| `claws-mail` | Does the EMCOMM stack carry a mail client? | **RESOLVED 2026-08-30 — a third way, the maintainer's:** detect an existing client and respect the system default; if none, offer an open-source selection (Thunderbird, Claws Mail, Evolution, Geary) interactively; never install silently. Implemented as the profile `suggests_one_of` mechanism. |
| `putty` | Serial-terminal tool or out of scope? | **RESOLVED 2026-08-30 — carry, as a suggestion group.** Workstation profile detects an existing serial terminal and respects it; offers PuTTY (recommended), CuteCom, picocom, tio, minicom when none is found. Termius and MobaXterm named in docs, not offered (proprietary / Windows-only). |
| `rf_exposure_calc` | Do we ship browser bookmarks? | **Retire, with the other bookmarks.** A bookmark to a dead site is worse than none, liveness checks for URLs are real maintenance, and a catalog entry that opens a web page installs nothing. Put the URLs (hintlink power density, DXLook, HamTab, PSKReporter, VOACAP, OpenHamClock) in the propagation guide prose, once. |
| `solar_data` | Same, plus a deprecated ImageMagick dependency | **Retire**, same reasoning; the N0NBH banners belong in guide prose. |
| `xwefax` vs fldigi | Superseded by fldigi's WEFAX mode? | **Carry both, no supersede.** The question needs a radiofax operator, not a spec comparison; until one weighs in, dropping a dedicated tool on an assumption is the inherited-verdict mistake. |
| `jtdx` | Deprecate in favour of the others? | **Carry as-is, no deprecation mark.** Devoted user base, packaged, measured. |
| FT8-family default | wsjtx / wsjtx-improved / jtdx / mshv / js8call — which is recommended? | **`wsjtx`.** Reference implementation, packaged on every target, the documentation everyone else's assumes. The others stay carried; js8call is a different mode, not an alternative. |
| `FoxTelem` | Enough of the Fox constellation alive to justify it? | **Stage post-1.0 pending an AMSAT status check.** Partial world-changed case; blocking 1.0 on a satellite census serves nobody, quietly carrying a decoder for re-entered satellites serves nobody either. |
| `libhamlib4` | A catalog unit, or purely a dependency? | ✅ **RESOLVED 2026-08-30 — dependency, not a unit.** SUPERSEDE by apt `depends` resolution; no manifest owed. `libhamlib-utils` is the operator-facing hamlib manifest. |
| `country_files` (cty.dat) | A package, or the first "data asset with a cadence"? | **Post-1.0, as the data-asset design question.** The consuming apps bundle their own copies; a monthly-cadence fan-out asset deserves a schema shape, not a shoehorn. Document manual updates in the logging guide meanwhile. |
| `wine` | If Morse Runner goes conditional, does Wine leave 1.0? | **Already effectively resolved:** the Morse Runner resolution took Wine out of the 1.0 core; VARA brings a Wine *prefix* back post-1.0. Mark it so. |
| `M0IAX` (JS8 utilities) | Does the JS8 profile want them? | **Post-1.0 candidate.** Third-party and fine, but no measured demand; revisit when a JS8 profile user asks. |
| `PATMENU3` | Clone KM4ACK's menu, or is PAT's UI enough? | **PAT's own web UI suffices.** Do not write a licence-clean clone of a wrapper whose function PAT ships natively; document the web UI in the packet profile docs. |
| `REPEAT` (RepeaterSTART) | In scope? | **Post-1.0 candidate.** Repeater directory app, open, harmless — and nothing in the five-source union's 1.0 rationale needs it. |

**What resolving this buys:** every unit in the five-source union has a final
disposition; the parity-coverage "owed" denominator stops moving; and the
retire/no-manifest calls land in `not-carried.md` automatically once the
dispositions index is updated (the generator refuses to run until the reasons
follow — that is the drift guard doing its job).
