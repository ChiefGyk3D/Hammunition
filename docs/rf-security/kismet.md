<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Kismet

Kismet listens to Wi-Fi, Bluetooth and a range of sniffer dongles and SDRs,
and builds a live list of every network and device it hears, logged to a
database you can convert to pcapng or KML afterwards. It is in the
`rf-security` profile; its package page, generated from the manifest, is
[`docs/packages/kismet.md`](../packages/kismet.md), and the manifest is
`catalog/packages/kismet.yaml`.

Everything on this page was measured on 2026-09-30 in containers of the
seven targets, from the packages' own control scripts and configuration
files, and from Kismet's repository index and source. **Nothing here has yet
been run on the field laptop or against a real radio**; where a step below
depends on behaviour a package only describes, it says so.

## What you are installing, and what it can do

Read this before you run it, because Kismet's capability is broader than
"a Wi-Fi scanner":

- **It captures what it hears.** With a Wi-Fi card in monitor mode it records
  frames from every network on the channels it visits, not only yours, and
  by default logs packets, including data frames, to the `.kismet` file
  (`kis_log_packets=true`, `kis_log_data_packets=true` in the shipped
  `kismet_logging.conf`).
- **It collects device identifiers.** MAC addresses, device and network names,
  Bluetooth addresses, manufacturers, and — with `gpsd` running — where each
  was heard. That is the `identifier_collection` capability in D-021's
  taxonomy.
- **Its Bluetooth source transmits discovery requests.** The Linux Bluetooth
  helper starts the adapter's ordinary discovery (read from the 2025-09-R1
  source), which sends inquiry and scan requests the way any Bluetooth device
  looking for others does. The Wi-Fi helper makes no inject or send call.
  Nothing in Kismet deauthenticates, jams, or impersonates.

**Why it is not consent-gated.** D-021 attaches gates to profiles whose
capability is the hazard, and keeps `rf-security` ungated on purpose, so the
gate on `rf-research` stays rare enough to be read. Kismet's capability is the
one Wireshark, aircrack-ng and hcxdumptool already bring into that profile. The
only question `--yes` cannot answer when you install it is the repository
question below, and only on the targets that need the repository.

## Using it lawfully is your call, not ours

This project discloses capability and does not tell you what is lawful where
you are; [the section index](index.md) sets out why, and what bodies of law
commonly apply. For Kismet specifically, the posture the project takes is:

- Survey **your own** networks and devices, or ones you hold written
  authorisation to assess.
- What you capture from other people's networks and devices may be yours to
  see and not yours to keep. Kismet logs data frames by default; if you do
  not need them, set `kis_log_data_packets=false` in
  `/etc/kismet/kismet_site.conf`, and delete logs you are not entitled to
  hold.
- Identifiers and locations of other people's devices are personal data in
  many places. Treat a wardriving log accordingly.

## How it installs on each target

| Target | Where Kismet comes from | Version (2026-09-30) |
|---|---|---|
| Parrot 7.3 | Parrot's own archive | 2025.09.R1-0parrot1 |
| Kali rolling | Kali's own archive | 2025.09.R1-0kali3 |
| Debian 13 (amd64, arm64) | Kismet's repository, `release/trixie` | 2025-09-R1 |
| Ubuntu 24.04 | Kismet's repository, `release/noble` | 2025-09-R1 |
| Linux Mint 22.3 | Kismet's repository, `release/noble` | 2025-09-R1 |
| Ubuntu 26.04 | nothing yet — deferred by name | — |

The archive column is `scripts/apt-policy-sweep.sh` over every Kismet package
name on all seven targets: Kali and Parrot offer all of them, the other five
offer none. On Debian 13, Ubuntu 24.04 and Mint 22.3 the plan adds Kismet's
own repository under **D-040**: you are shown the repository, its suite, the
two files it writes (`/etc/apt/sources.list.d/kismet-<suite>.sources` and
`/etc/apt/keyrings/kismet-<suite>.gpg`), and the key fingerprint, and the
repository is added only when you type that fingerprint:

```
ADA09A0E9B80ACCCE8FE6BB65345B8BF43403B93
```

That is Kismet's packaging key, "Kismet Wireless (Packaging Signature)", RSA
4096, created 2018-09-12, no expiry, read from the published key with this
engine's own OpenPGP reader. For a scripted install, the answer is an
environment variable holding the same fingerprint:
`HAMMUNITION_ACCEPT_APT_REPO_KISMET_TRIXIE` on Debian 13,
`HAMMUNITION_ACCEPT_APT_REPO_KISMET_NOBLE` on Ubuntu 24.04 and Mint. Declining
stops the transaction and nothing is changed; the rest of `rf-security` can
still be installed by name. `hammunition uninstall kismet` removes both
repository files with the package (see *Reversing it*).

**Ubuntu 26.04** has no Kismet release repository: `release/` in Kismet's index
has no `resolute` tree (its `Release` file is a 404), although Kismet's own
packages page prints a line for one. Only the nightly `git/` channel has
`resolute`, and a nightly is not something this catalog pins. Kismet is
deferred there by name and the rest of the profile installs.

## What it changes on your machine

- **The `kismet` group.** Every packaging measured creates a `kismet` system
  group and makes each capture helper (`/usr/bin/kismet_cap_*`) runnable by
  that group only — setuid root on Kali and Parrot, file capabilities
  (`cap_net_raw`, `cap_net_admin`) on Kismet's own packages. The install adds
  you to the group. Membership is the ability to switch radios into capture
  modes and capture what they hear. Undo: `sudo gpasswd -d $USER kismet`.
- **`kismet.service`, on Kali and Parrot.** The kismet-core package in both
  archives ships a systemd unit that runs Kismet **as root**, restarts it if it
  stops, and its install script enables it and starts it when systemd is
  running. This is read from the package's `postinst`, not observed on a
  running system. Kismet's own packages ship the same unit without enabling
  it. If you want Kismet only when you start it:
  `sudo systemctl disable --now kismet.service`. Inspect with
  `systemctl status kismet.service`.
- **A repository and a key**, on Debian 13, Ubuntu 24.04 and Mint only — above.

## First run

1. Log out and back in, so the `kismet` group applies. `id -nG` should list
   `kismet`.
2. If you are on a network you do not control, keep the web interface to this
   machine first (next section).
3. Start it in a terminal: `kismet`. Leave that terminal open.
4. Open <http://localhost:2501>. The first browser to connect is asked to
   create the login; the login is stored in `~/.kismet/kismet_httpd.conf` for
   the user Kismet runs as.
5. Add a source under **Data Sources**, or name one when you start it:
   `kismet -c wlan1`. Kismet puts a Wi-Fi card into monitor mode itself when
   it opens it; you do not need to.

## Keep the web interface on this machine

The shipped `/etc/kismet/kismet_httpd.conf` sets `httpd_port=2501` and leaves
`httpd_bind_address` commented out, with the comment *"By default kismet
listens on all interfaces"*. So while Kismet runs, port 2501 is reachable from
any network you are on, and the first browser to reach a fresh install sets its
login. To confine it, put this in `/etc/kismet/kismet_site.conf` (create it;
Kismet reads it last and no package upgrade overwrites it):

```
httpd_bind_address=127.0.0.1
```

Restart Kismet (or `sudo systemctl restart kismet.service`) for it to apply.
Your own settings belong in `kismet_site.conf`, never in `kismet.conf`, which
the package replaces on upgrade.

## Hardware you may already have

| Device | Kismet source | Status here |
|---|---|---|
| The laptop's own Wi-Fi card | `linux-wifi` | Works if its driver supports monitor mode; many built-in cards do not. Unmeasured on the field laptop. |
| The laptop's own Bluetooth | `linux-bluetooth` | Through BlueZ. Unmeasured on the field laptop. |
| Ubertooth One | `ubertooth-one` | Packaged on every route. Firmware must match the host tools; see [`docs/packages/ubertooth.md`](../packages/ubertooth.md). |
| nRF52840 running Nordic's sniffer firmware | `nrf-52840` | Packaged on every route. The firmware is Nordic's, flashed separately; unmeasured here. |
| CatSniffer V3 | none packaged | See below. |

**CatSniffer V3 is not a Kismet source yet.** Kismet's development branch has
a CatSniffer Zigbee helper (`capture_catsniffer_zigbee`, added 2024-09-18) and
a Sniffle BLE helper (`capture_sniffle_ble`, 2026-07-22), and neither is in any
release: not in the `kismet-2025-09-R1` tag, not in Kali's or Parrot's
packages, and not in Kismet's release *or* nightly repositories, whose
`Contents` files list no such binary. When a Kismet release carries them this
page and [the device page](../hardware/catsniffer-v3.md) change; until then
the CatSniffer is used through its own tooling and Wireshark.

## When Kismet shows no data source, or a source will not open

Symptom first; each cause names its check. These come from the packages and
Kismet's configuration, not yet from a session on real hardware.

**You added a Wi-Fi card and it errors or never reports packets.**
The card cannot do monitor mode. Check what the driver offers:

```
iw list | grep -A 10 'Supported interface modes'
```

If `monitor` is not in that list, Kismet cannot use the card for Wi-Fi capture
and no setting will change it; a USB adapter whose driver does is the usual
answer. If it *is* listed and the source still drops, NetworkManager may be
taking the interface back; the aircrack-ng page's known problems cover the
same fight.

**The source type you expect is not offered at all.**
The capture helper for that hardware is not installed. Kismet can only open
sources whose helper exists:

```
ls /usr/bin/kismet_cap_*
```

The `kismet` package installs every helper its packaging has; a device with no
helper there (the CatSniffer, today) has no Kismet support in that release.

**Kismet runs, but opening any source is refused for permissions.**
You are not in the `kismet` group *in this session*. The install added you,
but a group applies only to a login that starts after it:

```
id -nG | tr ' ' '\n' | grep -x kismet      # this session
getent group kismet                         # the group database
```

If `getent` lists you and `id` does not, log out and back in. If neither does,
the install did not add you; `hammunition status` shows what the log recorded.

**`kismet` says port 2501 is already in use.**
On Kali and Parrot, `kismet.service` is probably already running (above).
Use that instance at <http://localhost:2501>, or stop it first with
`sudo systemctl stop kismet.service`.

## Reversing it

```
hammunition uninstall kismet
```

removes the `kismet` package it installed and, where it added them, both
repository files, then refreshes apt. `kismet` is a metapackage: kismet-core
and the capture helpers came in as its dependencies, and — like every shared
dependency this engine's uninstall leaves — they stay until
`sudo apt autoremove` takes them. **Until then, on Kali and Parrot,
`kismet.service` is still installed and enabled.** Stop it first if you are
removing Kismet:

```
sudo systemctl disable --now kismet.service
hammunition uninstall kismet
sudo apt autoremove
```

The `kismet` group and your membership in it are left as the packages leave
them: `sudo gpasswd -d $USER kismet` undoes the membership, and purging
`kismet-capture-common` on Kali or Parrot removes the group.
