<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Bench verification — Dell Latitude 5430 Rugged (field target, session 1)

Hand-written record, per `docs/contributing/vm-testing.md`, of the first
engine session on real hardware. The VM pages prove the engine on six
disposable guests; this page is the ladder's last rung: the laptop
Hammunition is being built for and will be shown on. Raw output stays out
of git; what is here is what ran, what it reported, and what it found.

**Date:** 2026-09-12
**Engine:** commit `c8ab2fd` (`main`, v0.7.0 line), installed by
`./bootstrap.sh` into the checkout's `.venv`
**Machine:** Dell Latitude 5430 Rugged — Core i7-1185G7 (8 threads), 32 GB
RAM, 512 GB NVMe with a LUKS root, Iris Xe graphics, Intel AX210 Wi-Fi 6E
with Bluetooth, two batteries. **No WWAN module and no GNSS receiver are
fitted yet**; both are planned once antennas and cabling for the chassis are
sourced. Nothing catalogued was attached during this session.
**OS:** Parrot Security 7.3 "echo" (`ID=parrot`, `VERSION_ID=7.3`), kernel
`7.0.13+parrot7-amd64`, Python 3.13.5, a KDE session, `parrot-backports`
already in use by the machine (cmake and pipewire come from it)
**Method:** session 1 was the read-only ladder only. `sudo` was not
exercised by the engine session, so nothing in it installed, removed, or
wrote outside the user's home; every dry run was `--dry-run --no-refresh`.
Session 2 (below) is the operator's own first real commands, verified
afterwards. The station values were set on this machine in
`~/.config/hammunition/`, and are not recorded here or anywhere else: the maintainer's callsign and grid
square are private (CLAUDE.md, hardware context), and bench pages carry
`N0CALL`-style placeholders only. This laptop is a separate
machine from the development host and its hypervisor — the bench, not the
dev machine CLAUDE.md forbids testing on.

## The ladder

| Step | Result |
|---|---|
| `./bootstrap.sh` | Found Python 3.13.5, created `.venv`, installed the engine, ran `doctor`. Idempotent re-run not exercised. |
| `hammunition doctor` | **10 ok, 1 to look at, 0 blocking.** The one item is no callsign or grid set. Device groups: already in every access group (`dialout`, `plugdev`). udev rules not applied. No catalogued hardware attached. State directory writable. |
| `hammunition status` | `Parrot Security 7.3 (echo) (ID=parrot, version=7.3, arch=x86_64)`, Debian family yes, **244 packages, 242 resolve on this target**, 16 profiles, empty transaction log. |
| `hammunition hardware list` | No catalogued device on the bus. Eight attached and uncatalogued, all of them the machine's own: two Realtek hubs, the integrated webcam, the AX210's Bluetooth function (`8087:0032`, no product string), and four xHCI root hubs. None of these wants a rule. |
| `hammunition hardware apply --dry-run` | 58 rule lines would go to `/etc/udev/rules.d/65-hammunition.rules` via three printed commands (`install -D`, `udevadm control --reload-rules`, `udevadm trigger`). Four devices named as deliberately given no symlink (airspy, bladerf, nfc-reader, ubertooth-one — `serial_suffix` unmeasured), permissions still applied. Both groups reported as already held. |
| `hammunition list profiles` | 16 profiles: the 12 of the 1.0 set and 4 post-1.0. `rf-research` flagged `[consent gate]`. |
| `hammunition install <profile> --dry-run` × 16 | **15 resolve completely; `morse` refuses** — see below. 146 units would install, build, or fetch across the 16 plans. |
| `make check` (lint, `mypy --strict`, tests, doc links) | **1697 passed, 20 skipped**, no broken references. Every skip is a gitignored measurement input or the udev sweep output, none is machine-related. |

### What a Parrot desktop already carries

The engine recognised Parrot's own preinstalls as `already installed` and
planned nothing for them: `aircrack-ng`, `hcxdumptool`, `hcxtools`,
`inspectrum`, `tcpdump`, `ubertooth`, `wireshark` (so `rf-security` plans
only `esptool` and `rtl-433`, plus the `wireshark` group), `rtl-sdr`,
`libfreefare-bin`, `libnfc-bin`, `mfcuk`, `mfoc`, `pcsc-tools` (`rfid` plans
one unit), `git`, `pciutils`, `screen`, `tmux`, `usbutils`, and `code`. The
`workstation` companion offer respected the `screen` already present and
offered nothing. This is the attribution rule doing its job on a machine
that was not a clean baseline: none of these would come out on `uninstall`.

### D-038 on a real machine

Four profiles — `digital-modes`, `electronics`, `listening`, `propagation` —
reported *apt refused the default release because a package this machine
already installs from parrot-backports would have been downgraded*, and
re-planned the apt step with `--target-release parrot-backports`. The
package in every case was `cmake` (once `debhelper`), which this laptop
already runs from backports. The VM campaigns saw D-038 as a Kali fact; this
is the first time a Parrot install has exercised it, and the disclosure read
exactly as designed.

### The kernel still has AX.25

`7.0.13+parrot7-amd64` ships `ax25`, `netrom`, `rose`, `mkiss` and `6pack`
as modules, so `packet` planned all 21 units with no D-041 deferral. Linux
7.1 removed AX.25; the day Parrot's kernel crosses that line, this laptop
becomes the first real machine where D-041 refuses by name. Worth
re-running the `packet` dry run after every kernel update, for that reason.

## Finding: `morse` refuses on a PipeWire desktop

```
1 problem block this transaction:
  aldo, canadian-ham-exam, cw, cwcp, cwdaemon, cwwav, ebook2cw, ebook2cwgui,
  fccexam, flwkey, hamexam, ibp, morse-classic, morse2ascii, qrq, xcwcp,
  xdemorse: apt would remove installed package(s) to install this
  transaction: pipewire-alsa (1.4.9-1~bpo13+2) -- and no manifest in it
  declares that conflict in conflicts_with_repo_package, which is a catalog
  defect worth an issue
```

The engine did the right thing: resolution ran to completion, the removal
was refused under D-022 and the apt step's `--no-remove`, and nothing
changed. Bisected with `apt-get install -s` one unit at a time, the culprit
is a single unit:

- **`morse-classic`** installs Debian's `morse`, which *Recommends*
  `pulseaudio`. apt installs Recommends by default; `pulseaudio` *Conflicts*
  with `pipewire-alsa`; this desktop runs on `pipewire-alsa 1.4.9-1~bpo13+2`.
  So the plan removes the machine's audio routing to install a Morse
  sounder. The other sixteen units are innocent — the engine names the whole
  transaction, as it should, because the transaction is what fails.

None of the six VM campaigns hit this, and none of their pages records
whether the guest had `pipewire-alsa` installed, so whether the VMs were
PulseAudio, PipeWire without the ALSA shim, or something else is not known.
It is a machine-class finding: any Debian 13 / Parrot desktop on PipeWire
with the ALSA compatibility package will refuse the `morse` profile whole.
The fix belongs in the manifest, not the engine — either install `morse`
without Recommends or declare the conflict so the dry run discloses it — and
it is filed as issue #61 rather than fixed here, because it needs a decision
about whether the catalog has, or wants, a per-unit no-Recommends switch.

## Session 2, same day: the first real changes to the field target

The operator ran these at the keyboard; the engine session that followed
verified the effect of each (D-031), never the exit status alone.

| Step | Result |
|---|---|
| `hammunition station set` | Set. `doctor` moved from 10/1/0 to **11 ok, 0 to look at, 0 blocking**. The values are private and not recorded (see above). |
| `hammunition hardware apply` | Applied. `/etc/udev/rules.d/65-hammunition.rules` is root-owned, mode 0644, 58 lines, and **byte-identical** to what `apply --dry-run` stages from the catalog. `apply --dry-run` afterwards: *Nothing to do: the rules file already matches and you are in every access group.* No catalogued device has been plugged in yet, so the rules are installed but not exercised. |
| `hammunition install station` | **Completed and confirmed, 25 s wall clock** for the whole transaction. The log shows the `hammunition-hill` `.deb` fetched and its sha256 verified, `apt-get update`, the combined `--simulate` of the `.deb` plus the ten apt units, the real `apt-get install` of the ten, then the `.deb` through apt — every command `returncode: 0`. Verified independently: all eleven at `ii` via `dpkg-query` — chirp (Parrot's own `1:20250530-1parrot1`), flrig, gpsbabel, gpsd, gpsd-clients, gpsd-tools, libhamlib-utils, pipx, twclock, tzwatch, hammunition-hill 1.0.0. |
| `hammunition-hill` on a real desktop | The `.deb` installs a system unit; `hammunition-hill.service` is **active and running**, listening on `127.0.0.1:8073` only, and answers `200 text/html` on `/`. First time the maintainer's own dashboard has been installed by this engine outside a VM. |
| gpsd after install | `gpsd.socket` enabled and active, `gpsd.service` inactive until a client connects, `USBAUTO="true"` with `DEVICES=""` — Debian's default, which is the right default for a machine whose receiver is not fitted yet. Listening on `2947` on both loopback addresses. |
| `install station --dry-run` again | Plans the same transaction again rather than *Nothing to do*: the ten apt units are already installed, and the `.deb` step is re-planned — fetch (a cache hit) plus a root `apt-get install` that apt itself turns into *already the newest version*. Outcome idempotent, work not: the `deb` instance of the already-installed-at-pin gap `vm-verification-parrot.md` queued for git and source builds. Filed as #63 with a dpkg-plus-attribution fix that needs no design decision. |
| `uninstall station --dry-run` | Attributes all **11** units to Hammunition, including the `.deb`, and plans one `apt-get remove`; states what is not reversed (apt's pulled-in dependencies, groups, config files). Not run. |
| Launchers | `flrig.desktop`, `twclock.desktop` and Parrot's `parrot-chirp.desktop` are in `/usr/share/applications/`, from the packages themselves. No engine-generated launcher was needed for this profile. |

## Session 3, same day: what runs without the radios and without root

The hardware is in the lab downstairs and `sudo` was not exercised by the
engine session, so this pass took the unprivileged, device-free rungs.

| Step | Result |
|---|---|
| Is the applied rules file actually loaded? | **Yes.** `udevadm verify` on `65-hammunition.rules`: 1 checked, 1 success, 0 fail. `udevadm test` on an unrelated existing device (the webcam) lists `/etc/udev/rules.d/65-hammunition.rules` among the 134 rules files it reads. So the rules are parsed and in udev's working set; matching against a real device is still item 1 below. |
| `hammunition menus apply` on **KDE Plasma** | **Works, and Plasma was unmeasured until now** — the README names Xfce and GNOME and calls COSMIC unmeasured. `XDG_MENU_PREFIX=plasma-` was honoured; 27 category submenus, 17 desktop entries from installed catalog packages placed 18 times by their manifests' categories. Wrote `~/.config/menus/plasma-applications-merged/hammunition.menu` (well-formed XML, `xmllint`) and 28 `.directory` files under `~/.local/share/desktop-directories/`. GNOME app-folder correctly skipped. **But two of the placed entries do not exist on this machine** — see the next row. |
| The placements versus what is on disk | An earlier draft of this page said `chirp.desktop` resolves because `dpkg -L chirp` lists it. That was reading the shipped file list as the truth, and it is not: **`parrot-menu` runs from an apt `DPkg::Post-Invoke` hook after every apt run and rewrites the launcher set** — 444 `parrot-*.desktop` entries here — removing the packaged `chirp.desktop` and `org.wireshark.Wireshark.desktop` and writing `parrot-chirp.desktop` (`Categories=Engineering;`, no `HamRadio`) and `parrot-wireshark.desktop` in their place. Measured over every installed catalog package: 7 entries present, 2 listed by dpkg but absent. So **CHIRP is not under Ham Radio at all on the primary target**, and neither is Wireshark; the tree places a filename that is not there and the summary counts it as placed. Filed as #64 with the fix (place only what exists, find the `parrot-` replacement, say so in the summary). |
| Menu refresh on Plasma | The engine's closing line names `xfce4-panel -r` and a GNOME Shell reload; on Plasma the equivalent is `kbuildsycoca6`, which ran clean (exit 0). Not a defect; one line of the closing hint could name it. Whether the *Ham Radio* menu renders correctly in the launcher is a by-eye check, still open. |
| GUI smoke lane (`scripts/vm_gui_smoke.py`) | **Not run.** It wants `xvfb-run`, which this machine does not have, and its own docstring warns it can wedge behind a live display session. Launching the station GUIs on the operator's logged-in desktop from an unattended session was judged the wrong way to do it. Belongs with item 3 below, eyes on. |
| `flrig`, `twclock` desktop entries | Present under `/usr/share/applications/` from their packages and placed by the Plasma tree where their manifests' categories say: flrig under Rig Control and Station; twclock under CW, Station and Timing. CHIRP: see the row above. `hammunition-hill` has **no desktop entry at all** — the `.deb` ships none and the manifest declares no `launchers`, so the dashboard is invisible in the menu; a launcher opening `http://127.0.0.1:8073/` in the browser, the `ais-catcher-web` pattern, would place it under Station, HF Propagation and Satellite. Catalog change, not filed yet — it is a choice for the maintainer. |
| Does the tree make sense? (asked by the maintainer) | Judgement, recorded so it can be disagreed with. **Structure:** *Ham Radio* is one flat, alphabetical list of 27 submenus; empty ones are hidden by the menu spec, so today nine show, but with the whole catalog installed it is 27 siblings — more than Plasma's own top level has — with visible overlap (Station / Timing / Tracking; CW / Training; Contest / Logging; Hardware / Programmer / Electronics). **Placements that read oddly:** a clock (`twclock`) under *CW* because its manifest carries `cw` for its CW-ID feature; GPS viewers (`xgps`, `xgpsspeed`) under *Hardware*, a title that says little next to *Programmer* and *Electronics*; VS Code under *Ham Radio → Workstation* because Parrot preinstalled it and the catalog knows it. **Duplication:** three of the seven placed entries appear in three submenus each. **Sound:** the vocabulary titles (`SDR`, `NBEMS`, `HF Propagation`) read correctly; flrig under Rig Control, wireshark under RF Security, gscriptor under RFID are right. The taxonomy is D-036's one-list rule working as designed; whether it wants a second level of grouping in `catalog/categories.yaml` is a decision, not a bug. |

## Session 4, same day: the three findings fixed and re-measured here

Each fix was written test-first in its own worktree and run from that
worktree's engine against this laptop's real state before its PR was
opened. Nothing privileged ran; every measurement is a dry run or an
unprivileged command.

| Finding | Fix | Re-measured on this machine |
|---|---|---|
| `morse` refuses on a PipeWire desktop (#61) | PR #65, catalog only: `morse-classic` leaves the profile with the reason in the file; the manifest declares `conflicts_with_repo_package: [pipewire-alsa]`. The per-unit no-Recommends switch stays open on #61 as engine work. | `install morse --dry-run`: **16 packages, 19 commands, no removal.** `install morse-classic --dry-run`: refuses with the unit as the subject and the declared conflict named. |
| CHIRP and Wireshark missing from the Ham Radio tree (#64) | PR #66: `menus.on_disk()` places only entries that exist, uses `parrot-<package>.desktop` when the packaged one is gone, and reports what happened under the count. | `menus apply`: *chirp: chirp.desktop is not on disk; placed the distribution's parrot-chirp.desktop instead* — same for wireshark. The written `.menu` carries the two `parrot-*` ids and **zero dead filenames**; `kbuildsycoca6` rebuilt clean. Whether CHIRP now shows under *Rig Control* in the launcher is still the by-eye check. |
| `station` re-plans the .deb on every run (#63) | PR #67: a vendor .deb dpkg still holds **and** the transaction log attributes to this engine is `already installed`; not ours stays with apt. | `install station --dry-run`: hammunition-hill *already installed*, **Commands (0)** — *everything this plan asks for is already in place*. `install wsjtx-improved --dry-run` (never installed here): still plans fetch+install. |

Two harness notes from the session, recorded because they bit: a `make
check` whose output is piped into `grep` and chained with `&&` reports the
grep's exit status, not make's — one failing docs test and one
`ruff format` refusal reached CI that way before the habit changed to
`make check > log; echo $?`. And a shell whose working directory resets
between commands put one worktree's edit into another; absolute paths
from then on.

## Session 5, same day: the menu rebuilt in Parrot's shape (D-050)

The maintainer's verdict on the session-3 tree: fix it, and look at how
Parrot lays out its own tools. Parrot's menu was measured on this machine
(one top menu, 14 numbered groups, numbered subcategories, a `<Layout>`
order, 671 entries of which 670 have a Comment and 572 open a terminal),
the design was approved in chat, and D-050 records the rule. Re-measured
here, from the branch engine, all of it unprivileged:

| Step | Result |
|---|---|
| `menus apply` | **8 groups, 27 categories**, prefix `plasma-`; 20 placed entries (CHIRP and Wireshark by Parrot's own entries, zero dead filenames); **12 entries generated** for installed units that ship none; **12 skipped with the reason named** — eleven with several executables and none named like the unit, and `gpsd`, whose only application-shaped executables are the daemon's tools. `kbuildsycoca6` run by the engine. |
| The written tree | Well-formed (`xmllint`); `<Layout>` lists the eight groups in declared order; each category sits under exactly its group — Station holds station, rig-control, timing, logging, contest; SDR & Listening holds sdr, listening, satellite, tracking, hf-propagation; and so on. 8 group `.directory` files, 27 category ones. |
| A generated entry | `hammunition-cli-tcpdump.desktop`: Name, the manifest summary as Comment, `Keywords=rf-security;workstation;tcpdump;`, `Terminal=true`, `Exec=/usr/bin/tcpdump`, the `X-Hammunition-*` markers. Searchable by name, by category word, and by what it does. |
| Pruning | The first apply of the session generated `hammunition-cli-gpsd.desktop` running `/usr/sbin/gpsd` in a terminal — a daemon, not an application. The sbin rule was written from that, and the next apply **removed** the stale entry, which is the pruning path proving itself on a real mistake. |
| `install hammunition-hill` (re-run, unprivileged) | With #67 merged the `.deb` is *already installed* and the plan is exactly the two launcher steps: the wrapper (`x-www-browser http://127.0.0.1:8073`) and the desktop entry, both written and confirmed. The dashboard is in the tree under Station, HF Propagation and Satellite. |
| By eye, first look | **No Ham Radio menu, and the generated entries in Kickoff's *Lost & Found*.** The maintainer's report from the launcher, and the measurement that followed: `QT_LOGGING_RULES='kf.service.sycoca=true' kbuildsycoca6 --noincremental` lists every menu file it reads — `/etc/xdg/menus/plasma-applications.menu`, then `/etc/xdg/menus/applications-merged/{parrot-applications,privacy,services}.menu` — and never `plasma-applications-merged/`, where the tree had been written. KDE's kservice ignores `XDG_MENU_PREFIX` for `<DefaultMergeDirs/>`; Xfce's garcon, where the prefix rule was first measured, honours it. An entry no menu allocates is what *Lost & Found* holds; that was every `hammunition-cli-*` entry. |
| The fix, re-measured | `merge_dir()` sends the file to `applications-merged/` on a `plasma-`/`kf5-` prefix and removes the copy in the directory nothing read. Re-applied: *wrote ~/.config/menus/applications-merged/hammunition.menu*, *removed ~/.config/menus/plasma-applications-merged/hammunition.menu*, `kbuildsycoca6` run — and the verbose rebuild now reports **Found menu file ~/.config/menus/applications-merged/hammunition.menu**. |
| Second round, from the launcher | The maintainer saw the tree and asked for three things: the name *Hammunition*, no general tools under it (git, VS Code), and a parity plan for GNOME, Xfce and COSMIC. Measured first: Parrot's own menu carries 71 RF entries under *Pentesting → Wireless Attacks*, 15 of them catalog units, and its KDE root has no `HamRadio` category at all. Then: *Workstation* declared `menu: false`; re-applied here — **7 groups shown, 26 categories, 9 generated entries**, the git, screen and tmux entries and the Workstation directory files **removed** by the pruning paths, the top entry now reads `Name=Hammunition`. GNOME's per-group folders are code and tests only until the Debian VM runs them; Xfce needs the Kali VM; COSMIC is unmeasured. |
| By eye, second look | The operator's: open the Plasma launcher, find *Ham Radio → Station → Rig Control → CHIRP*, confirm *Lost & Found* has emptied of `hammunition-cli-*` entries, and type `tcpdump` into search. `rigctl` will find nothing until `libhamlib-utils` gets its `launchers` block, exactly as the summary says. |

## Session 6, same day: the full catalog, installed

The maintainer ran the whole thing himself: fifteen profiles in one
transaction (everything but `editors`), then two resumes. Engine at the
main of the moment for each run. Every number below is from the transaction
log, dpkg, or the files on disk, not from the exit status.

| Step | Result |
|---|---|
| `install <15 profiles>` (16:56) | Plan: **164 units, 267 commands, 32 source builds**, no blocker, morse included, rf-research consent given at the prompt. One apt step of **1027 .debs (965 MB)**, 1013 packages configured by 17:06 with no error, then 21 builds — and **a failure at paracon**: `[install-binary] /usr/local/bin/paracon: Permission denied`. The `executable` binary format copied the file in-process as the operator; every other install form went through sudo. Engine defect, fixed as #72 (the install now goes through a privileged `install -D`). 165 commands completed and recorded; nothing rolled back (D-004). |
| Resume 1 (17:21, from the fix's worktree) | The remaining 11 builds plus the launcher-bearing units re-ran; paracon installed at mode 0755 through the fixed path. **Then a failure at the first virtualenv unit**, `radiosonde-auto-rx`: the engine spawned `<worktree>/.venv/bin/python3 -m venv` and that path no longer existed — the worktree had been removed after its PR merged, mid-transaction, by the assistant. Self-inflicted, and it produced #74: the venv backend now spawns the resolved interpreter (`/usr/bin/python3.13`), which the symlink pointed at all along. 118 commands completed. |
| Resume 2 (18:20, from the main checkout, after a firmware reboot on the same `7.0.13+parrot7` kernel with AX.25 still present) | **Done. 234 commands completed and confirmed**; `transaction_end` `verified: true`, **33 effect checks, none unconfirmed**. On disk afterwards: 3 unit venvs (artemis, radiosonde-auto-rx, supersdr), 59 `hammunition-*` desktop entries, the operator in the `wireshark` group in the group database (applies at next login), and wsjtx, fldigi, js8call, proxmark3, linbpq and direwolf all on PATH. |
| What was deferred | `linbpq`'s `/etc/bpq32.cfg`: the station has a callsign and grid but no node alias, so D-035 deferred that one file and installed the other 20 units of `packet`. `hammunition station set --node-alias …` and a re-run of `install linbpq` writes it. |
| The cost of the two failures | 21 source and git builds ran **three times**. The engine knew "already installed" only for apt and, since #67, vendor .debs; a build had no such notion. That is D-051, written the same evening (#75). |
| D-051 measured against this log | Dry run of the same fifteen profiles from the D-051 engine: **143 already installed, 21 will build**, 186 commands instead of 267. Of the 21: fourteen were built only in the two failed transactions, which never verified them — correct, they rebuild once more and then never again; seven were built and verified in resume 2 but **declare no `binaries` and no tree marker** (proxmark3, libacars, rtlsdr-airband, acarsdec, dumphfdl, dumpvdl2; openhamclock is a node unit and outside the rule by design), so the engine has no effect to check and cannot decide them. That is the same gap issue #27 named for verification, and the fix is catalog data: declare what those builds install. |
| The menu after the install | 60 HamRadio-tagged entries on disk and, until `menus apply` was re-run, 42 of them sitting directly under *Hammunition* — placement happens at apply time and the last apply predated the install. After re-apply: 68 placed. The 20 left over were Parrot's per-tool `parrot-gnuradio-<tool>` entries, which the replacement rule did not cover; with #77, **90 entries placed 142 times, 47 generated, zero left at the top level**. The maintainer's "it's all just under Hammunition" was both of those things, and the second lesson is that an install should end by re-applying the menu (an open item). |
| The read-only ladder after the reboot | doctor 11 ok / 0 / 0; `status` sees 249 packages; same kernel, AX.25 modules present. |

## Session 7, same day: a launcher that called itself

Found by the agent writing launchers for the units the menu could not
guess (#82), before its own nine shipped the same defect: **a launcher
wrapper named like its tool calls itself.** The wrapper lands at
`~/.local/bin/<name>` and its command line names the tool bare;
`~/.local/bin` is first on PATH here (Debian's `.profile`), so the
wrapper resolves to itself and forks until the machine refuses. The six
launchers merged the same afternoon (#71: rtl_test, rigctl, hackrf_info,
ubertooth-util, nfc-list, cgps) all had it, and this page had never
claimed a generated entry was opened by eye.

| Step | Result |
|---|---|
| Exposure on this laptop | One wrapper on disk, `ubertooth-util`, written by the `rf-security` profile in the resume; the other five units were not in that run. `type -a rtl_test` resolved to `/bin/rtl_test`. So one menu entry was a fork bomb, and it had not been clicked. |
| The fix (#82, engine commit) | A wrapper named like its tool takes its own directory out of PATH before the command; every other wrapper is byte-identical. Red on the unfixed engine, green after. |
| Regenerated here | `install ubertooth` from the fixed engine: plan is exactly the two launcher steps, run unprivileged, wrapper rewritten with the PATH strip. |
| Proven, not assumed | Run inside a systemd user scope with `TasksMax=48` (a plain `ulimit -u` cannot bound this: threads count and a desktop session already holds hundreds): the wrapper ran the real `ubertooth-util -v` exactly once — *could not open Ubertooth device*, no unit attached — printed the hold prompt, zero fork errors, no leftover processes once the scope stopped. |
| Rule for the record | A wrapper never shares its tool's name without the PATH strip, and a launcher is not verified until it has been run once under a task ceiling. |

## Session 8, same day, into the night: the log read back, uninstall planned, Rayhunter in hand

No radio was attached and nothing privileged ran except one launcher
re-apply. This session is what the engine can say about this laptop after
the full install, measured from the log and the disk rather than remembered.

| Step | Result |
|---|---|
| The transaction log | **1117 entries**: 9 `transaction_begin`, 7 `transaction_end` every one `verified: true` (checks confirmed per transaction: 2, 33, 1, 9, 1, 1, 1), 2 `transaction_failed` (session 6's paracon and venv failures), 210 actions, 340 commands. `status` reports the most recent transaction as 2 commands, 0 packages intended, 1 check passed: a launcher re-apply for `ax25-apps`, which is what those numbers say. |
| Rayhunter, for real | The `rf-security` resume put `rayhunter-installer` (14.2 MB) and `rayhunter-check` (6.1 MB) in `/usr/local/bin`, root-owned, mode 0755, at 18:29; `rayhunter-check --help` answers. No Orbic hotspot was on the bench, so the daemon side stays where #69 left it: the host-modem route through the DW5930e's DIAG channel, once the card is fitted. From #86 the manifest carries aarch64 and armv7l blocks with their own digests and `binaries`, so the same unit resolves on the uConsole; the dry run here reads *already installed* and, against an empty prefix, each architecture renders its own fetch and two installs. |
| `uninstall rf-security --dry-run` | Attribution by source, every artifact labelled with how the engine knows it is ours: 2 units apt-removed (esptool, rtl-433); 8 artifacts, the `ubertooth` wrapper and entry `[marker]`, `artemis`'s venv, requirements file, wrapper and entry `[namespaced]`/`[marker]`, Rayhunter's two binaries `[log]`; **7 units left in place** as Parrot's own preinstalls (aircrack-ng, hcxdumptool, hcxtools, inspectrum, tcpdump, ubertooth, wireshark); 9 commands. `uninstall packet --dry-run`: 9 artifacts, 10 commands. Neither was run for real; that is the operator's, and item 5 below. |
| `morse` back in the profile | D-052 (#85) gives `morse-classic` its own apt command with `--no-install-recommends`, so the profile refusal from session 1 is gone and the unit is a member again (#87). From main: `install morse --dry-run` plans **20 commands**, one apt-get for `morse` alone carrying the flag, everything else on apt's defaults, no removal, and the plan names the unit that asked. |
| D-051 re-measured from main | The same fifteen profiles: **142 already installed, 21 will build, 2 will install** (morse-classic, newly a member; and artemis, a venv unit, which always re-plans because pip over a satisfied venv is its own cheap check), 203 commands. The 21 are the same 21 as session 6: fourteen never verified, and the seven with no effect to check. Declaring `binaries` on five of those (#79) did not change the count, and it should not have: attribution needs a verified `transaction_end` that confirmed one of *this unit's* checks, and resume 2 could not confirm a check the manifest did not declare. They build once more under the new manifests and are decided from then on. libacars and openhamclock still declare nothing and stay outside the rule. |
| A menu entry called "input" | Read out of the log, not the menu: the launcher agent's `yagiuda` launcher put an entry named **input** under Antenna, with a comment about Yagi-Uda arrays. The name is right for the wrapper, since a shell finds it by that name, and wrong for a menu. Launchers now carry a `title` for the entry (#89); seventeen gained one in the shape *what it does, then the command*. `install yagiuda --yes` from that branch on this laptop: two unprivileged steps, `Name=Yagi-Uda design input (input)` on disk, wrapper unchanged, 99 entries placed. |
| The flaky orphan test, measured (#81) | `test_a_grandchild_holding_the_pipe_does_not_stall_the_lane` read the orphan's `/proc` state the instant the lane returned. The lane returns on pipe EOF, and the kernel closes a dying process's files before it marks the process a zombie. Under twelve busy threads on this i7: at that instant the orphan read Z 10 times, gone 19, X once, and **R 30 times** out of 60, every one a zombie or gone within 6.4 ms; the single read failed **21 of 40** runs, a bounded 2 s poll **0 of 40** (#88). The lane was never at fault. |
| The weekly udev citation job | Found by the #86 agent's dispatched run: the job restated the sweep runner's podman line by hand and mounted only the script, so from the day the pair parser became a module (D-047) it died on import. Only the schedule runs it and the last schedule predated the split; tomorrow's would have been the first red. CI now calls the runner (#88), and the dispatched proof run passed that job on the first attempt. |

## Session 9, into the small hours: the catalog answers back

The engine could say what it installed; it could not say whether any of it
was current. Every manifest has carried an `update` block since D-010 and
nothing read it. This session is the two halves of D-053 written and
measured here, and what the second half found the first time it ran.

| Step | Result |
|---|---|
| `hammunition update` (#91, D-053) | Offline, 0.7 s, against the **171 units the log has ever named**: **145 up to date, 17 behind the catalog's pin, 2 unknown, 4 re-checked on install, 3 manual, 0 with a different apt candidate**; apt lists last refreshed 06:38 that morning, printed rather than refreshed. The 17 + 2 unknown + 2 manual-strategy builds are exactly the 21 units the same evening's fifteen-profile dry run planned to build, which is the consistency the command needs to be trusted. A default set that read only clean transaction endings showed 70 units and hid ninety this machine has, because the first full install failed after its apt step; the default is now every unit ever named, and the comparison looks at apt and the disk. |
| The two unknowns, decided (#92) | `libacars` is a library: its install rule leaves a `.so`, a symlink and a pkg-config file and no executable, so nothing could be checked. `installed_files` names them; `fl-moxgen`'s Makefile installs `fl_moxgen`, declared in `binaries`. Both read off this disk. `update libacars fl-moxgen` then reads *behind the pin* for both, which is right: they were built before the manifests declared anything, and they build once more and are attributed from then on. |
| `update --upstream` (#94) | Opt-in and the only network the report uses. **25 probes answered in 7.5 s, none unanswered**: 11 GitHub latest-release tags, 13 `git ls-remote` tag lists (the highest by numeric parts; LinBPQ has 112 tags), one PyPI JSON, YAAC's one-line label compared verbatim. **22 current, 3 with a newer upstream**: hamclock-next 1.5 → 1.6, linbpq 25.39 → 25.40, openhamclock 26.7.0 → 26.7.3. Issue #95. |
| openhamclock re-pinned and installed (#97) | The loopback-bind patch's hunk moved three lines and applies. Installed through the engine from the branch, **unprivileged** (nodejs and npm already here): 12 commands confirmed in 32 s. Server started from its wrapper: HTTP 200 on `localhost:3001`, `/proc/net/tcp6` shows one listener on `::1` and nothing on `0.0.0.0`. The patch holds at 26.7.3. |
| hamclock-next 1.6 built (#97) | The CMake alias patch applies at the same lines; regenerated exact from the 1.6 tree. `cmake` + `make -j8` on the patched tree: exit 0, 21 MB binary, starts. **Not installed**: `cmake --install` into `/usr/local` is the operator's sudo. |
| linbpq 25.40, and the finding (#96, #97) | The tag compiles clean and then the makefile's `linbpq` target runs **`sudo setcap`** for three capabilities, in 25.39 as well. The engine never printed it, and session 6's build passed only because the apt step had just warmed this operator's sudo timestamp. Outside a warm timestamp: `sudo: a terminal is required`, `make: Error 1`, binary already linked. Git blocks may now carry `patches`; linbpq's deletes the line, `known_problems` names the ports that need the capabilities and the one `setcap` to grant them. With the patch: `make -j8` exits 0, no sudo. The 25.40 binary still prints `6.0.25.39`; upstream's version string lags its tag. |
| The Parrot mirror, four times (#93) | Between 23:30 and 00:40 the target container build for CI's `parrot` job failed four times on `deb.parrot.sh` 404s: the index named `python3.13 3.13.5-2+deb13u4` and the pool no longer had it, from two mirror addresses, each green on a plain re-run. The Dockerfile's apt steps now retry up to three times a minute apart, clearing the lists between attempts; a package that really is missing still fails three times. Driven locally with a fake `apt-get` before it went to CI. |

## Not yet run (this rung's remaining ladder)

In order, and every one needs the operator at the keyboard for `sudo`:

1. Plug in the HackRF Pro, a Proxmark3, a Meshtastic node and the C5
   Wardriver one at a time and confirm each is recognised by
   `hardware list`, permitted, and symlinked as
   `docs/reference/device-naming.md` says it should be. The rules are
   installed; this is what exercises them, and the "not yet exercised
   against an attached device" line in the README closes here.
2. Open `http://127.0.0.1:8073/` in this machine's browser and check the
   dashboard against the station values — by eye, not by pasting. Open the
   Plasma launcher and walk the *Hammunition* menu group by group: every
   entry is placed (session 6), none has been opened by eye except the
   Ubertooth launcher under a task ceiling (session 7), and the seventeen
   retitled entries (session 8) have been read on disk, not on screen.
3. The GUI smoke lane by hand: gqrx and SDR++ opening against the RTL-SDR
   and the HackRF Pro on this machine's USB topology (two Realtek hubs in
   the path). The units are installed (session 6); nothing has been opened
   against a radio.
4. Time the three `packet` source builds (ardopcf, linbpq, qtsoundmodem)
   on the i7, on battery and on AC. They built once in session 6, untimed;
   linbpq rebuilds at 25.40 regardless (session 9), ardopcf and
   qtsoundmodem need `--force` or a cleared prefix to measure. And
   `station set --node-alias …` then `install linbpq` to write the one
   deferred file. `install hamclock-next` at 1.6 is the same shape: built
   here, not installed, one sudo away.
5. `uninstall` for real, `station` first, then `rf-security` and `packet`,
   against the dry runs in session 8: the two apt removals, the eight and
   nine artifacts, and the seven Parrot preinstalls that must still be
   there afterwards.
6. A second full-profile run to attribute the 19 remaining builds under
   D-051 (21 in session 8, less openhamclock re-installed and attributed in
   session 9, less libacars now decidable), then a third that plans none
   of them. The second is the one that proves the rule; `hammunition
   update` afterwards should read them all *up to date* and is the cheaper
   check than a dry run.
7. The GPS and WWAN questions, once the modules exist: the catalog's
   `gps-receiver` class is USB-serial (`/dev/serial/by-id/`); an internal
   GNSS on a WWAN card usually surfaces through ModemManager's location API
   or `/dev/wwan*`, not a tty, and `gpsd` will need a different source line.
   Nothing is written for that yet, and nothing should be until the
   hardware is on the bench to measure. Rayhunter's host-modem route (#69)
   waits on the same service session.
