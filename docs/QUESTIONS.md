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

## Q-006 🟡 — Which HamClock, now that there are four options?

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
