# VM campaign — Ubuntu 24.04 and 26.04 by unit, every profile whole on three targets

Run overnight 2026-09-02 → 03 with `scripts/vm_campaign.py`. Two campaigns
per unit on the Ubuntu targets at engine `118b237` (main, after the node
backend merged), and three campaigns that install **every profile whole
from a clean snapshot** — the shape an operator actually uses — on Kali,
Parrot and Debian 13. The whole-profile runs are new to the harness
(`--whole-profiles --reset-each DOMAIN`) and they found what the per-unit
runs could not: two profiles that planned clean and failed partway.

## Standing

| Target | Campaign | Result |
|---|---|---|
| Ubuntu 24.04.4 | 243 units by name | **224 installed+confirmed, 0 failed**, 19 refused at plan time |
| Ubuntu 26.04.1 | 243 units by name | **234 installed+confirmed, 0 failed**, 9 refused at plan time |
| Debian 13 | 15 profiles whole | **13 installed+confirmed**, 1 stopped at its consent gate, 1 refused |
| Parrot 7.3, pass 1 | 15 profiles whole | 8 confirmed, 1 consent gate, 1 refused, **5 failed at the first apt command** |
| Parrot 7.3, pass 2 (D-038) | 15 profiles whole | **13 installed+confirmed**, 1 consent gate, 1 refused |
| Kali rolling | `digital-modes` whole | failed after 44 commands, then **confirmed** after the fix below; 1.28 GB measured |

"Confirmed" is the engine's own bar: every command completed *and* the
re-probe found the software (D-031). The consent gate is `rf-research`
stopping on a non-interactive stdin, which is the gate working — the
campaign never affirms one (D-021). The refusal is `workstation`, whose
`code` and `codium` need the third-party-repository backend that is the
maintainer's decision to make.

**Zero failures on either Ubuntu** is the headline. The engine's 24.04 and
26.04 coverage was untested before this run — the capability matrix has
never carried a 24.04 target, only Linux Mint 22.3 on the same base — and
every unit that did not confirm was refused *before anything ran*, with a
reason that is true of the archive and not of the engine.

## What Ubuntu refuses, and why each is honest

| Reason | 24.04 | 26.04 |
|---|---|---|
| No apt candidate in this release's archive | `aethersdr`, `gtk-meshtastic-client`, `m2kcli`, `mlat-client-adsbfi`, `odr-audioenc`, `python3-meshtastic`, `pythonprop` (and its `voacapl`), `readsb`, `rtl-ais`, `satdump`, `sdrangel`, `voacapl` | `aethersdr`, `gr-gsm`, `soapysdr-module-rfspace` |
| No install block declares this target | `arduino-cli`, `soapysdr-module-plutosdr` | `arduino-cli`, `soapysdr-module-plutosdr` |
| Third-party apt repository (unimplemented, the maintainer's call) | `code`, `codium` | `code`, `codium` |
| Node floor (D-037): the archive's `nodejs` is 18.19, the unit needs 20.19 | `openhamclock` | — |
| Retired on evidence: the NOAA APT satellites went off the air 2025-11-09 | `noaa-apt` | `noaa-apt` |
| Vendor `.deb` collides with the installed `wsjtx-data` (from `jtdx`, installed earlier in the same campaign) | `wsjtx-improved` | `wsjtx-improved` |

The 26.04 gaps are already in `capability-matrix.md`'s measured sweep; the
24.04 list above is that target's first measurement and is the record for
it. Two are worth a second look by whoever next touches them:
`soapysdr-module-rfspace` has left Ubuntu's archive between 24.04 and
26.04 (Kali lacks it too), and `sdrangel` remains the binary-backend unit
on every target that does not package it.

The slowest confirmed units, for the runbook's timeouts: `qlog` 977 s and
1108 s, `hamclock-next` 872 s and 925 s, `wsjtx` 475 s and 459 s,
`js8call` 413 s on 26.04. Nothing reached the 1800 s per-unit budget; the
whole-profile runs used 3600 s and their longest was 585 s.

## Profiles that do not install whole, per target

Every refusal above was checked against the profiles that list it. The
plan resolves the whole transaction or refuses it (D-016), so one refused
member withholds the profile:

| Profile | Ubuntu 24.04 | Ubuntu 26.04 | Debian 13 | Parrot |
|---|---|---|---|---|
| `electronics` (11) | `m2kcli` | — | — | — |
| `listening` (23) | `readsb`, `rtl-ais`, `satdump`, `mlat-client-adsbfi` | — | — | — |
| `propagation` (12) | `openhamclock`, `voacapl`, `pythonprop` | — | — | — |
| `satellite` (4) | `satdump` | — | — | — |
| `rf-research` (2) | — | `gr-gsm` | — | — |
| `workstation` (9) | `code`, `codium` | `code`, `codium` | `code`, `codium` | `code`, `codium` |

Five of fifteen on 24.04, two on 26.04, one on Debian and Parrot. Whether
a member the archive does not carry should withhold the profile (D-016) or
be deferred by name the way a config file is (D-035) is **Q-017**, and it
is the maintainer's; the table is its evidence.

## What the whole-profile runs found, and what was fixed

**`digital-modes` on Kali planned clean and failed after forty-four
commands.** The plan checked every package for a candidate and every
`.deb` for a conflict with what was *installed* — on a clean machine,
nothing. It did not ask what the transaction's own apt step would *pull
in*: `jtdx` brings `wsjtx-data`, and the `wsjtx-improved` vendor `.deb`
ships the same pixmap. fldigi and WSJT-X had built by the time dpkg
refused. Two fixes: the plan now refuses that pairing by name, and the
profile no longer lists `wsjtx-improved` (its page says how to install it
alone). Re-run whole from the clean snapshot: 45 commands, confirmed,
**1.28 GB installed** measured as `df` before minus after with the 0.9 GB
of build trees and the apt cache subtracted.

**Five Parrot profiles planned clean and failed at the first apt command,
in one second each.** Parrot's clean baseline installs 197 of its 3,801
packages from `parrot-backports`; main's `-dev` packages depend on their
runtime at an exact version the machine no longer has, and apt will not
downgrade the runtime to build against it. The same skew was seen on
2026-08-30 (`vm-campaign-digital-modes.md`: glfer and xwefax, the GTK dev
chain) and worked around by hand that night. This time it was measured
across every failed line and put in the engine as **D-038**: the plan asks
`apt-get install --simulate` for every transaction with apt work, reads
the package apt refused to downgrade and the release it was installed
from, retries once with `--target-release` naming that release, and lists
in the plan every package that release alone supplies. Pass 2 on the same
clean snapshot: `digital-modes` 585 s, `electronics` 93 s, `listening`
185 s, `logging` 427 s, `propagation` 515 s, all confirmed.

**Debian 13 had no surprises**: thirteen of fifteen whole, the other two
the gate and the repository refusal, and it is the target that proved the
Parrot failures were Parrot's — the same five profiles installed there
untouched (`digital-modes` 554 s, `propagation` 505 s, `logging` 441 s).

Two harness fixes came out of it: the CLI line-buffers stdout so a
redirected install log fills as it runs (the first campaign's reports
buried every error above the tail window), and the campaign report files
a declined consent gate in its own bucket rather than as a failure.

## An engine gap the campaign named but did not close

Both partway failures had the same shape: the plan is complete about what
apt *knows*, and anything apt only learns by trying still surfaces after
the machine has been touched. D-038's simulate step closes the apt half.
The `.deb` half is still open — `apt-get install ./file.deb` does not
simulate a file that has not been fetched, and the engine fetches during
execution. **Fetching and verifying every artefact, and simulating every
`.deb` against the post-apt state, before the first system modification**
would make "the plan passed" mean what an operator reads it to mean. It is
a reordering of `execute.py`, not a new backend, and it is recorded here so
it is built on evidence and not forgotten.

## Left with the maintainer

- Q-017, above.
- The third-party-repository backend (`code`, `codium` on every target).
- Ubuntu 24.04 as a declared target in `containers/targets.yaml` and the
  capability matrix, now that it is measured — or Linux Mint 22.3 as its
  stand-in, which is the current state.
