# Open questions for the maintainer

Decisions that are the maintainer's to make, and blockers this session could not
clear. Each carries options and a recommendation. Nothing here was decided
unilaterally.

**Urgency key:** 🔴 blocks work · 🟡 blocks a milestone · 🟢 decide when convenient

---

## Q-001 🔴 — Container tests cannot run on this machine

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

## Q-002 🔴 — `mypy --strict` is authored but UNVERIFIED

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

## Q-003 🟡 — Raspberry Pi OS has no container image

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

## Q-004 🟢 — Ubuntu 26.04 is in CI but not in `CLAUDE.md`'s target list

`CLAUDE.md` names Parrot, Debian, Ubuntu, Kali and Raspberry Pi OS. AHRL's own
tested set includes Ubuntu/Xubuntu/Kubuntu 26.04 and Linux Mint 22.3, and one
manifest (`js8call`) already branches on **Linux Mint 22.3** specifically.

So the catalog has a Mint-specific selector while Mint is in no target list and
no CI job.

**Recommendation:** add Linux Mint 22.3 as a declared target. It is cheap
(`linuxmintd/mint22-amd64` or equivalent) and we are already writing manifests
against it — an untested selector is worse than no selector.
