# VM verification — Parrot OS (campaign 1)

Hand-written campaign record, per `docs/contributing/vm-testing.md`. Raw logs
stay out of git; what is here is conclusions, versions, and actual failure
text.

**Date:** 2026-08-29
**Engine:** commit `6aeb3c6` (venv-installed with `pip install -e .` in the guest)
**Guest:** Parrot Security 7.3 "echo" (`ID=parrot`, `VERSION_ID=7.3`), x86_64,
Python 3.13.5, fully updated at baseline
**Host:** KVM/QEMU via libvirt, domain `ParrotOS_Dev`, qcow2, NAT
**Method:** every sequence starts from the `clean-baseline` snapshot
(`scripts/vm-snapshot.sh reset`), driven over SSH from the host

## The harness itself

| Claim | Result |
|---|---|
| Cold baseline → `reset` → fresh boot → SSH reachable | **Works.** SSH answered 8 s after revert-and-start. |
| Baseline guard refuses with install ISO attached | **Works** — refused the real mid-install VM before the tooling was even committed. |
| Baseline guard refuses to overwrite `clean-baseline` | **Works** (exercised during the re-baseline below). |

Two facts about Parrot that baseline prep must include, now baked into
`clean-baseline`:

- **`openssh-server` is installed but disabled by default** (security-distro
  posture). `systemctl enable --now ssh` before baselining, or every reset
  comes up unreachable. Learned by baselining without it and re-baselining.
- **Driving the engine over SSH needs a terminal for sudo.** A ticket
  pre-validated with `sudo -S -v` in a no-TTY session is keyed to the parent
  process, so the engine's own `sudo` (a child of Python) does not inherit
  it: `apt-get update` came back `returncode: 1` in 28 ms. The engine did
  exactly the right thing — logged `command_begin`/`command_end`/
  `transaction_failed`, executed nothing further. **This is a harness fact,
  not an engine defect**; `ssh -tt` (allocate a TTY) resolves it, and the
  ticket then covers the whole transaction.

## Engine results

| Test | Result |
|---|---|
| `hammunition status` | Detects `Parrot Security 7.3 (echo) (ID=parrot, version=7.3, arch=x86_64)`, Debian family yes. 225 packages loaded, **223 resolve on this target**. |
| `hammunition install station --dry-run` | Resolves 10 packages, all apt on Parrot, prints exactly one `apt-get install` command plus the transaction-log record. Aborting at the confirmation prompt (empty stdin) changed nothing — the refusal path is the correct default. |
| `hammunition install station --yes --refresh` | **Both commands completed and confirmed.** All 10 packages verified independently at `ii` via `dpkg-query` after the run — `chirp`, `flrig`, `gpsbabel`, `gpsd`, `gpsd-clients`, `gpsd-tools`, `libhamlib-utils`, `pipx`, `twclock`, `tzwatch`. |
| Idempotency — same command again | **Zero commands.** All 10 report `already installed`, output ends `Nothing to do.`, exit 0, no sudo touched. |
| The container-blocked six | **All six configure cleanly on a real init system.** `gpsd` in the station run; `direwolf`, `gpredict`, `cubicsdr`, `gnuradio`, `gr-gsm` in one engine transaction (`--yes`), one apt command, completed and confirmed, all five verified `ii` afterwards. `install-verification.md`'s rootless-harness caveat is now closed for the whole set: those were harness facts, not package problems. |

## Findings for the catalog and engine

1. **chirp's executables are `chirpw` (GUI) and `chirpc` (CLI) — there is no
   `chirp` binary.** The manifest already records Parrot's patched
   `1:20250530-1parrot1`; it should also say what the launch command is,
   because anyone following AHRL habits (`run_chirp` wrapper) or typing
   `chirp` gets nothing. Manifest documentation updated with this finding.
2. **The CLI has no `--version` flag** (`hammunition --version` errors).
   Found while writing `not-carried.md`, which had claimed it as the
   `ahrl_version` replacement; the page now names `hammunition status`
   instead. An engine `--version` remains worth having for bug reports.
3. **The two manifests that do not resolve on Parrot are deliberate.**
   `status` says 223/225; the two are `arduino-cli` and
   `soapysdr-module-plutosdr`, both of which carry a single
   `when: distro: [kali]` block. That is the capability matrix behaving as
   designed — an honest gap, reported rather than shimmed — not a defect.

## Not yet run (this campaign's remaining ladder)

GUI launch checks (needs the console, not SSH), hardware/udev with USB
passthrough, uninstall against a `save` checkpoint, and the M5
re-verification list (`ardopcf` CM108 caveat first). Then the same ladder on
Debian 13, Ubuntu 26.04, Pop!_OS 24.04 (see the runbook's caveat), and Kali.
