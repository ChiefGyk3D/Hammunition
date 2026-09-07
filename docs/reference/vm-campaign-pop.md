# VM campaign — the whole catalog and every profile on Pop!_OS 24.04

Run 2026-09-04 with `scripts/vm_campaign.py` against a Pop!_OS 24.04 LTS VM
(`ID=pop`, `ID_LIKE="ubuntu debian"`, x86_64). Pop is **not a declared
target** and has no CI container; `docs/contributing/vm-testing.md` says
how to read its results — as evidence for a decision about declaring `pop`,
not as pass/fail against current claims. This page is that evidence. It was
the last of the six VMs to be run, and the README had said "queued on a VM
that does not exist yet" until it did.

The engine under test was a local integration branch of the day's work; the
branches it merged landed on `main` as PRs #21 (`cmake` joins the apt set
of every cmake build), #22 (`wsjtx` declares `libhamlib-dev`) and #23
(`yaac` re-pinned). The first two were *found* by this campaign.

## Standing

| Campaign | Result |
|---|---|
| Every unit, 243, from the clean snapshot | **224 installed+confirmed, 17 refused at plan time, 1 stopped at a consent gate, 1 failed** — the failure re-pinned and confirmed the same day |
| Every profile whole, from the clean snapshot | **14 of 16 installed+confirmed**; `digital-modes` failed twice, was fixed, and confirmed alone; `editors` and `rf-research` were not run (consent gates, D-021) |

"Confirmed" is the engine's own bar (D-031): every command completed *and*
the re-probe found the software. Raw reports on the host under
`~/.local/state/hammunition-campaigns/`: `units-pop2404-2026-09-04`,
`units-pop2404-yaac-2026-09-04`, `profiles-pop2404-2026-09-04`,
`profiles-pop2404-rerun-2026-09-04`, `profiles-pop2404-digital-modes-2026-09-04`
(`.md` and `.log`).

## The seventeen refusals

All at plan time, nothing changed on the machine, each naming its reason.
Pop's archive is Ubuntu 24.04's plus Pop's own suites, so this is mostly
the 24.04 rung's list seen again (`docs/reference/vm-campaign-ubuntu.md`).

| Unit | Reason |
|---|---|
| `aethersdr`, `gtk-meshtastic-client`, `m2kcli`, `mlat-client-adsbfi`, `odr-audioenc`, `python3-meshtastic`, `readsb`, `rtl-ais`, `satdump`, `sdrangel`, `voacapl` | apt has no candidate on this release |
| `pythonprop` | no candidate, and depends on `voacapl` |
| `arduino-cli`, `soapysdr-module-plutosdr` | their only install block is `distro: [kali]`; no block declares this target |
| `openhamclock` | the archive's `nodejs` is 18.19; the manifest's floor is 20.19 and Node is never fetched (D-037) |
| `wsjtx-improved` | its vendor `.deb` collides with the installed `wsjtx-data` — refused before dpkg could half-do it |
| `noaa-apt` | retired: the satellites it decodes were taken out of service 2025-11-09 |

That is Ubuntu 24.04's list less two. `code` and `codium` were refused
there for an engine gap that D-040 has since closed; here `codium` stopped
at the D-040 fingerprint prompt, which the campaign never affirms, and
**`code` installed from the archive in 16 seconds** — Pop!_OS carries
Microsoft's build in its own `pop-os-apps` suite, so no third-party
repository was offered or needed. That is the one result on this page that
is Pop's own, and it is D-040's first rule ("added only when the archive
offers nothing") holding on a target nobody designed it for.

## The two failures, and what each taught

**`yaac`** — the fetch of `YAAC.zip` did not match the manifest's sha256; the
download was discarded and nothing ran. Upstream had re-cut the beta under
the same URL. Re-pinned to build #230 (PR #23) and confirmed alone the same
day. This is the fetcher doing its one job. The author's own account of how
YAAC is versioned and distributed arrived later as issue #31.

**`digital-modes`** — failed twice, at 386 s and 656 s, in the same place:
`wsjtx`'s cmake configure could not find Hamlib's development headers. The
`wsjtx` manifest had never declared `libhamlib-dev`; on every other target it
had been building in `js8call`'s wake, which declares it and sorts earlier.
Pop was the first machine where the order fell the other way. Declared (PR
#22), then the profile ran alone from clean and confirmed in 513 s.
The related finding, from the same day's `wsjtx` build: a cmake build had
been relying on `cmake` already being present, so PR #21 made the engine
put it in the apt set of every cmake block rather than hope.

## Every profile

Seconds are the harness's wall clock from plan to the re-probe's last answer.

| Profile | Result | Seconds |
|---|---|---:|
| `antenna` | confirmed | 50 |
| `digital-modes` | confirmed on the third run, after PR #22 | 386 ✗, 656 ✗, 513 |
| `editors` | not run — consent gate (D-040) | — |
| `electronics` | confirmed | 113 |
| `listening` | confirmed | 150 |
| `logging` | confirmed | 589 |
| `morse` | confirmed | 27 |
| `packet` | confirmed — **see below** | 54 |
| `propagation` | confirmed | 527 |
| `rf-research` | not run — consent gate (D-021) | — |
| `rf-security` | confirmed | 18 |
| `rfid` | confirmed | 114 |
| `satellite` | confirmed | 55 |
| `sdr` | confirmed | 170 |
| `station` | confirmed | 26 |
| `workstation` | confirmed | 4 |

## The row that was true of packages and false of capability

`packet` installed whole and confirmed every check. It could not have
worked: the VM's kernel, 7.1.5, carries no `ax25` module — Linux 7.1
removed AX.25 — so `kissattach` had nothing to attach to. The engine had
no way to know, because the capability matrix is per target and this is a
fact about the running kernel. That finding is D-041 and
`docs/reference/kernel-ax25.md`: the plan now reads
`/lib/modules/$(uname -r)` and refuses or defers by name. Confirming an
install by its packages is necessary and not sufficient.

## Left with the maintainer

- **Declare `pop` a target, or not.** Nothing on this page refused for
  being Pop rather than Ubuntu 24.04: every refusal is the archive's or the
  manifest's, and the `ID`-only selector caveat in `vm-testing.md` did not
  bite: the one manifest that gates on `distro: [ubuntu]` (`sdrangel`) also
  gates on `26.04`, so a Pop 24.04 machine refuses it for the release, not
  the `ID`. The decision is still open; this is the evidence it did not
  need to be urgent.
- **COSMIC menus.** Pop!_OS 24.04 is the release that ships COSMIC, so the
  machine D-036's third mechanism was waiting on now exists. Which desktop
  this VM booted has not been checked, and nothing about COSMIC has been
  measured.
