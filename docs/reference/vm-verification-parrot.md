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

## Uninstall (added same day — the verb did not exist that morning)

`hammunition uninstall` was written because this campaign needed to test
removal and found nothing to test. All results below are from the Parrot
guest, engine at the commit introducing the verb:

| Test | Result |
|---|---|
| `uninstall twclock --dry-run` | One unit, one `apt-get remove` command, nothing executed. |
| `uninstall aircrack-ng --dry-run` | **The promise holds:** Parrot preinstalls aircrack-ng, Hammunition did not — reported under *Left in place — installed, but not installed by Hammunition* and refused. Nothing to do. |
| `uninstall twclock --yes` | Completed and confirmed; dpkg shows `rc` — removed, config kept, which is `remove`-not-`purge` doing what the plan said. |
| `uninstall station --yes` | Planned 9 (twclock correctly in *already absent*), one command, completed and confirmed; all 10 station packages verified gone via `dpkg-query` afterwards. |
| `uninstall station --dry-run` again | *Nothing to do* — attribution replay saw its own removal. |
| `install station --yes` after the uninstall | Reinstalls cleanly. The full install → uninstall → reinstall cycle holds. |

## Configuration: linbpq end to end (D-008, D-035)

The first run of a `config_files` manifest outside a container, and the first
real run of the git backend on the primary target. Three defects fell out of
one command, each now fixed with a regression test:

| Test | Result |
|---|---|
| `install linbpq --callsign N0CALL …` | The validator rightly rejected the placeholder — but as a **raw traceback**. `StationError` from operator input now prints the validator's message and exits 2. |
| `install linbpq --yes --callsign N0TST --grid-square FN31pr --node-alias TEST` (first attempt) | Clone pinned to tag `25.39` (`be1400c7`), pin verified, compile clean — then **`make install` failed: upstream's makefile has no install target** (`all:` only; the word "install" does not appear in it). The manifest had claimed `provides_install_target` by default; measured, not assumed, it is `false`, and the declared `binaries` path now installs it — the same mechanism that already served coil64/cwwav/ardopcf. |
| Same command after the manifest fix | Failed on the config write: **an unprivileged engine cannot write `/etc/bpq32.cfg` in-process**, and the `PermissionError` escaped as a traceback. Root-owned config targets now plan as *stage the finished file unprivileged → `cp -a` backup when one is due → `sudo install -m MODE`* — every step printed by `--dry-run` exactly as run, no shell, contents never in argv. |
| Same command, final engine | **10 commands completed and confirmed.** Verified independently: `/etc/bpq32.cfg` root-owned mode 0644 carrying `NODECALL=N0TST` / `NODEALIAS=TEST` / `LOCATOR=FN31pr`; `/usr/local/bin/linbpq` runs and announces G8BPQ 6.0.25.36; `dialout` membership present. |

## Harness finding: the guest suspends itself

Both apparent "wedges" this campaign (domain `running`, CPU time frozen,
network gone, `dompmwakeup` refusing) were the **desktop guest's own idle
suspend**, not the snapshot tooling first suspected: the console showed
"Display output is not active" and a single `virsh send-key` woke it.
`systemctl mask sleep.target suspend.target hibernate.target
hybrid-sleep.target` is now baseline prep item 4 in the runbook, baked into
`clean-baseline` v3 along with sshd and the NOPASSWD drop-in.

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
3. **The interactive station prompt works, in the right order, exactly once.**
   Tested over a forced TTY with no saved values: the three questions come
   *before* the plan is resolved, answers save to `station.yml` (mode 0600),
   the plan then shows the resolved config write, and declining at the
   confirmation changes nothing. A second run asks no questions. `--yes` and
   non-interactive runs skip the prompt by design and defer the file (D-035);
   `hammunition station set` is the deliberate up-front path.
4. **A git-built package is not yet idempotent on re-run.** `linbpq` shows
   `already installed` in the plan header, yet the command list still carries
   the full clone-and-rebuild plus the config rewrite. The outcome is
   idempotent; the work is not — the second-run-changes-nothing property that
   apt packages already have needs the git/source backends to learn what
   "already installed at this pin" means. Engine work, queued.
5. **The two manifests that do not resolve on Parrot are deliberate.**
   `status` says 223/225; the two are `arduino-cli` and
   `soapysdr-module-plutosdr`, both of which carry a single
   `when: distro: [kali]` block. That is the capability matrix behaving as
   designed — an honest gap, reported rather than shimmed — not a defect.

## Not yet run (this campaign's remaining ladder)

GUI launch checks (needs the console, not SSH), hardware/udev with USB
passthrough, uninstall against a `save` checkpoint, and the M5
re-verification list (`ardopcf` CM108 caveat first). Then the same ladder on
Debian 13, Ubuntu 26.04, Pop!_OS 24.04 (see the runbook's caveat), and Kali.
