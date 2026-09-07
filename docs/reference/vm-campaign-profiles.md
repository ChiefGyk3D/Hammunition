# VM campaign — every profile whole on Parrot 7.3 and Debian 13, and all twelve on one machine

Run overnight 2026-09-05 → 06 with `scripts/vm_campaign.py` at engine
`c5fd0b4` and `78947f2` (both on `main`; the one commit between them is
documentation). Three campaigns:

- **Parrot 7.3, each profile from the clean snapshot** (`--whole-profiles
  --reset-each`): sixteen profiles, the VM reverted before every one.
- **Debian 13, the same shape**: sixteen profiles.
- **Parrot 7.3, twelve profiles cumulatively on one machine**
  (`--reset-first`): the snapshot reverted once, then `antenna`,
  `digital-modes`, `electronics`, `listening`, `logging`, `morse`, `packet`,
  `propagation`, `satellite`, `sdr`, `station` and `rfid` installed in that
  order onto the same system. This is what an operator who wants everything
  actually does, and it is the first time the harness has done it.

The `vm-campaign-ubuntu.md` page recorded the 2026-09-03 Parrot passes that
found D-038 (five profiles dead at the first apt command) and the Debian 13
pass that found nothing. This page is the re-verification at the current
engine, after D-038, D-039, D-040 and the tree/launcher/group re-probes
(commit `c5fd0b4`) landed, plus the cumulative shape.

## Standing

| Target | Campaign | Result |
|---|---|---|
| Parrot 7.3 | 16 profiles whole, each from clean | **14 installed+confirmed, 0 failed**, 2 stopped at a consent gate |
| Debian 13 | 16 profiles whole, each from clean | **14 installed+confirmed, 0 failed**, 2 stopped at a consent gate |
| Parrot 7.3 | 12 profiles cumulatively on one machine | **12 installed+confirmed, 0 failed**; 31.5 minutes wall-clock |

"Confirmed" is the engine's own bar: every command completed *and* the
re-probe found the software (D-031) — a binary executable at its path, a
package at a version, a launcher on the operator's PATH, a tree marker where
a tree install claims to have put one, a group membership in the group
database. The count of checks per profile is in the table below, and the
reports carry every one by name.

The two consent gates are the campaign working as designed, not gaps
(D-021): `editors` stops at the D-040 fingerprint prompt for the
`microsoft-vscode` repository, `rf-research` at the authorization
affirmation. The campaign affirms neither, on a non-interactive stdin, and
records the prompt text it was shown.

**Zero failures across 40 whole-profile installs** is the headline. The
last Parrot whole-profile sweep before these (2026-09-03, engine
`4616dde`) failed six of fifteen, every one at its first fetch with a
404: the clean snapshot was four days old and its apt lists still named a
`glib2.0` revision the pool had moved past. That was the snapshot's age,
not the catalog's, and the harness now refreshes the lists once per
prepare before anything is measured (commit `7cc03a9`); the reports here
record the InRelease dates it measured against. None of the six recurred.

## Every profile, three ways

Seconds are the harness's wall clock for the profile, from plan to the
re-probe's last answer. Checks are what the re-probe asked and found.

| Profile | Parrot, from clean | Parrot, cumulative | Debian 13, from clean |
|---|---|---|---|
| `antenna` | 11 checks, 56 s | 11 checks, 53 s | 12 checks, 53 s |
| `digital-modes` | 55 checks, 603 s | 52 checks, 590 s | 57 checks, 533 s |
| `editors` | consent gate (D-040), 1 s | — | consent gate (D-040), 1 s |
| `electronics` | 16 checks, 93 s | 9 checks, 47 s | 19 checks, 111 s |
| `listening` | 46 checks, 177 s | 33 checks, 140 s | 51 checks, 155 s |
| `logging` | 25 checks, 414 s | 14 checks, 381 s | 29 checks, 460 s |
| `morse` | 20 checks, 45 s | 15 checks, 27 s | 23 checks, 40 s |
| `packet` | 36 checks, 51 s | 25 checks, 37 s | 40 checks, 52 s |
| `propagation` | 25 checks, 546 s † | 15 checks, 483 s | 30 checks, 503 s |
| `rf-research` | consent gate (D-021), 2 s | — | consent gate (D-021), 2 s |
| `rf-security` | 3 checks, 12 s | — | 11 checks, 23 s |
| `rfid` | 12 checks, 110 s † | 7 checks, 102 s | 19 checks, 81 s |
| `satellite` | 5 checks, 79 s | 2 checks, 13 s | 5 checks, 88 s |
| `sdr` | 12 checks, 96 s | 8 checks, 10 s | 29 checks, 162 s |
| `station` | 10 checks, 13 s | 5 checks, 9 s | 10 checks, 42 s |
| `workstation` | 2 checks, 6 s | — | 5 checks, 5 s |
| **Total, confirmed profiles** | **2301 s** | **1892 s** | **2308 s** |

† Re-run alone on a quiet VM; see "One row that was not evidence" below.

**The cumulative pass is cheaper than the sum of its parts**, and the
checks column says why: `sdr` needed 12 checks and 96 seconds from a clean
snapshot but 8 and 10 seconds after `listening` had already installed
`gnuradio`, `gqrx-sdr`, `gr-osmosdr` and `soapysdr-tools`; `satellite` fell
from 79 to 13 seconds once `gnuradio`, `satdump` and `libhamlib-utils` were
already there. A profile's plan only claims what it installed, so its re-probe
only asks about that — which is idempotency being measured rather than
asserted. Twelve profiles onto one Parrot machine in 31.5 minutes is the
number an operator can be told.

**Debian 13 asks more of itself than Parrot does** — `sdr` 29 checks
against 12, `rf-security` 11 against 3 — because Parrot's baseline already
carries much of the SDR and security tooling as part of the distribution.
That is the D-022 coexistence rule from the other side: what the target
already has, the engine leaves alone and does not claim.

## What the re-probes found, by kind

The commit `c5fd0b4` re-probes were measured on Debian 13 and falsified on
the guest (`YAAC.jar` removed by hand made the tree check red, naming the
path; restored, green) before this campaign ran. All three kinds ran here
on both targets:

| Check | Where | What it confirmed |
|---|---|---|
| tree marker | `mshv` | `bin/MSHV_x86_64` present under `/usr/local/share/hammunition/mshv` |
| launcher | `mshv`, `ais-catcher`, `hamclock-next`, `openhamclock` | an executable wrapper in the operator's `~/.local/bin`, and for `mshv` the working directory it runs in |
| group | `packet` (`dialout`), `rf-security` (`wireshark`) | the operator's membership in the group database — present after the run, effective at next login |
| binary | 22 built units | the executable at its installed path — `fldigi`, `wsjtx`, `js8call`, `glfer`, `xwefax`, `flaa`, `coil64`, `gsmc`, `AIS-catcher`, `acarsserv`, `fllog`, `flnet`, `cwwav`, `flwkey`, `ibp`, `ardopcf`, `linbpq`, `qtsoundmodem`, `qttermtcp`, `flcluster`, `qgrid`, `hamclock-next` |

`digital-modes` is where the time goes on every target — fldigi, WSJT-X
and MSHV are built from source in one run, nine to ten minutes — followed by
`propagation` (HamClock's two clients, `openhamclock` through the node
backend) and `logging` (the fllog/flnet builds and the Qt 6 WebEngine
development set `qlog`'s build pulls in). Nothing else is over three
minutes.

## One row that was not evidence

The Parrot from-clean sweep's `propagation` row first read `exit 255` after
154 seconds, with no output and no packages recorded. It was not the
engine: a second campaign had been chained on that sweep's report *file*,
which the harness rewrites after every unit and which therefore already
existed, so the chained run started an hour early and reverted the Parrot
snapshot under the running sweep. `rfid`, the next row, could not be placed
on either side of that revert because rows carried no clock. Both were
re-run alone on a quiet VM (`--reset-each`, engine `78947f2`) and confirmed,
and the contaminated cumulative report was deleted rather than kept.

Two things came out of it. `vm_campaign.py` now writes a `started_at` UTC
timestamp on every row, so an overlap is decidable from the record; and
`docs/contributing/vm-testing.md` names the rule: wait on the harness
**process**, never on its report, and one VM runs one campaign at a time.

## The GUI smoke lane over the cumulative machine

With all twelve profiles on the one Parrot system, `scripts/vm_gui_smoke.py`
launched every desktop entry the catalog's units own under Xvfb: **52
entries across 50 units — 45 alive at the timeout, 2 exited clean, 0
suspect, 5 failed.** Host evidence
`gui-smoke-parrot-cumulative-2026-09-05.txt`.

The five failures are for a human eye, not the engine's. None is an
install defect; each is a question of whether the entry belongs in a menu:

| Entry | What it printed | Reading |
|---|---|---|
| `ais-catcher` web launcher | `cannot open display :99` | the launcher opens a browser; nothing under Xvfb answers |
| `nec2c` | its usage text, exit 255 | a command-line tool that ships a desktop entry |
| `pcsc-tools` (`gscriptor`) | `Chipcard::PCSC … Service not available` | needs `pcscd` running; the VM has no reader and no daemon |
| `psk31lx`, `qrq` | `Error opening terminal: unknown` | curses programs; `Terminal=true` entries have no terminal under Xvfb |

The two that exited clean before the timeout: `direwolf` with no
configuration file, and `twpsk` with no audio device (`pa_simple_read`
failed) — both correct behaviour for a headless VM and both worth knowing
when reading a smoke verdict.

That lane hung twice on this run, for a day, on `gpredict` and `satdump`:
`timeout(1)` had ended the child and the child's orphan still held the
lane's stderr pipe. The fix (the lane owns the session and kills it at the
deadline) re-ran the same 52 entries unattended in 9.5 minutes to the same
verdicts; it is PR #43 with its own evidence file.

## Left with the maintainer

- The five smoke failures above are a menu-curation question (D-036), not
  an install one. `nec2c`'s entry and the two curses entries are
  Debian's own packaging; `gscriptor` wants `pcscd` declared or enabled
  when a reader is present; the AIS web launcher is ours and could say so
  when no browser can open.
- `rf-security` on Parrot confirmed three checks in twelve seconds because
  the distribution already ships nearly all of it. The profile page should
  say that a Parrot operator gets `wireshark` group membership and little
  else from it, which is the honest claim.

Raw reports (`.md`, `.log`, `.evidence.jsonl` with per-row timestamps)
stay on the host under `~/.local/state/hammunition-campaigns/`, named
`profiles-parrot-2026-09-05`, `profiles-parrot-rerun-2026-09-05`,
`profiles-parrot-cumulative-2026-09-05` and `profiles-debian13-2026-09-05`.
