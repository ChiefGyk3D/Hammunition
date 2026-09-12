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
**Method:** the read-only ladder only. `sudo` was not exercised this
session, so nothing below installed, removed, or wrote outside the user's
home; every dry run was `--dry-run --no-refresh`. The station values were
set on this machine after the session, in `~/.config/hammunition/`, and are
not recorded here or anywhere else: the maintainer's callsign and grid
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

## Not yet run (this rung's remaining ladder)

In order, and every one needs the operator at the keyboard for `sudo`:

1. `hammunition hardware apply` for real, then re-run `hardware list` and
   confirm the rules file re-reads clean. Then plug in the HackRF Pro, a
   Proxmark3, a Meshtastic node and the C5 Wardriver one at a time and
   confirm each is recognised, permitted, and symlinked as
   `docs/reference/device-naming.md` says it should be. This is the "not
   yet exercised against real hardware on the bench" line in the README.
2. `hammunition station set`, then `install station --yes` — the same
   sequence the Parrot VM ran first, on the real target. Check the
   `hammunition-hill` `.deb` fetch and install here, since this machine has
   a browser to open it in.
3. `install sdr --yes` and `install rf-security --yes`, then the GUI smoke
   lane by hand: gqrx and SDR++ opening against the RTL-SDR and the HackRF
   Pro on this machine's USB topology (two Realtek hubs in the path).
4. `install packet --yes` — three source builds (ardopcf, linbpq,
   qtsoundmodem) on the i7, timed, on battery and on AC.
5. `uninstall` of each of the above, with the attribution check that
   Parrot's preinstalls stay.
6. The GPS and WWAN questions, once the modules exist: the catalog's
   `gps-receiver` class is USB-serial (`/dev/serial/by-id/`); an internal
   GNSS on a WWAN card usually surfaces through ModemManager's location API
   or `/dev/wwan*`, not a tty, and `gpsd` will need a different source line.
   Nothing is written for that yet, and nothing should be until the
   hardware is on the bench to measure.
