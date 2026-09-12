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

## Not yet run (this rung's remaining ladder)

In order, and every one needs the operator at the keyboard for `sudo`:

1. Plug in the HackRF Pro, a Proxmark3, a Meshtastic node and the C5
   Wardriver one at a time and confirm each is recognised by
   `hardware list`, permitted, and symlinked as
   `docs/reference/device-naming.md` says it should be. The rules are
   installed; this is what exercises them, and the "not yet exercised
   against an attached device" line in the README closes here.
2. Open `http://127.0.0.1:8073/` in this machine's browser and check the
   dashboard against the station values — by eye, not by pasting. And
   open the Plasma launcher and confirm the *Ham Radio* menu is there with
   its three station entries under the right submenus.
3. `install sdr --yes` and `install rf-security --yes`, then the GUI smoke
   lane by hand: gqrx and SDR++ opening against the RTL-SDR and the HackRF
   Pro on this machine's USB topology (two Realtek hubs in the path).
4. `install packet --yes` — three source builds (ardopcf, linbpq,
   qtsoundmodem) on the i7, timed, on battery and on AC.
5. `uninstall` of each of the above, with the attribution check that
   Parrot's preinstalls stay — `station` first, since its dry run already
   plans correctly.
6. The GPS and WWAN questions, once the modules exist: the catalog's
   `gps-receiver` class is USB-serial (`/dev/serial/by-id/`); an internal
   GNSS on a WWAN card usually surfaces through ModemManager's location API
   or `/dev/wwan*`, not a tty, and `gpsd` will need a different source line.
   Nothing is written for that yet, and nothing should be until the
   hardware is on the bench to measure.
