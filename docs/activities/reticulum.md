<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Reticulum

Reticulum is a networking stack for places with no infrastructure. Addresses
are cryptographic identities, every packet is encrypted, and one network can
run over a LoRa radio, a packet modem, a cable, a TCP link or an ordinary
local network with no router. On top of it, LXMF carries messages and
NomadNet is a terminal messenger and page browser.

## Programs the catalog carries

<!-- BEGIN generated: programs -->

- [lxmf](../packages/lxmf.md): LXMF, Reticulum's message layer, and lxmd, its store-and-forward propagation daemon (in [`mesh`](../profiles/mesh.md))
- [nomadnet](../packages/nomadnet.md): Nomad Network, an encrypted messenger and page browser for the terminal, over Reticulum (in [`mesh`](../profiles/mesh.md))
- [rns](../packages/rns.md): Reticulum, encrypted networking over any medium, with its shared instance and the RNode flasher (in [`mesh`](../profiles/mesh.md))

<!-- END generated: programs -->

Each is a hash-pinned per-user virtualenv, because no archive carries them
(about 70 MB for the three). `rns` brings the tools (`rnstatus`, `rnpath`,
`rnprobe`, `rncp`, `rnx`, `rnsh`, `rnid`), the RNode flasher `rnodeconf`, and
`hammunition-rnsd`, a systemd user service that keeps one shared instance per
machine; the first account's service runs it and another account's attaches
as a client. `lxmd`, the store-and-forward propagation daemon, is installed with
`lxmf` and run only on purpose. Sideband and MeshChat are not carried (each is
its own decision; see the [mesh inventory](../reference/mesh-inventory.md)).

## Hardware the catalog carries

<!-- BEGIN generated: hardware -->

- [rnode](../hardware/rnode.md): RNode, Reticulum's LoRa transceiver firmware, on the LilyGO, Heltec and RAK boards it supports (status untested; not maintainer-verified)

<!-- END generated: hardware -->

An RNode is firmware on a common LoRa board, not a product; upstream lists
fifteen supported boards. The catalog claims no USB identifier for it, because
a board presents its base module's, and records the entry as `untested`.
Reticulum also runs with no radio at all, over a local network or the internet.

## Install

```sh
hammunition install mesh --dry-run
hammunition install mesh
systemctl --user start hammunition-rnsd
rnstatus
```

The service is enabled at install and starts at your next login, so start it
by hand the first time. The engine writes no Reticulum configuration:
`~/.reticulum/config` is created by `rnsd` and is yours, and uninstall leaves
`~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd` and `~/.rnsh` in place.

## The licence position

Reticulum and LXMF are under the Reticulum License: the MIT text plus two
added conditions (no use in a system whose functions include purposefully
doing harm to human beings, and no use in training an AI or machine-learning
model). That is not an OSI-approved licence. The plan prints it on each venv's
line and does not gate on it; the decision is yours (**D-080**). NomadNet is
`GPL-3.0-only` by its shipped text. The [guide](../guides/mesh-and-reticulum.md#2-install)
quotes upstream's wording.

## First useful task: two machines, no internet

On two machines on one network, run `nomadnet` on each and write down the
address it shows, then message the other. With nothing configured, the
AutoInterface finds the other machine by itself. The [guide's section
3](../guides/mesh-and-reticulum.md#3-first-run-the-shared-instance-and-two-laptops)
walks through it; section 4 covers NomadNet.

## Radio: RNode, packet and the legal note

To go beyond one network, flash an RNode (`rnodeconf --autoinstall`) and add an
`RNodeInterface` with a frequency you are allowed to use, or put Reticulum over
a Direwolf modem (section 7). The guide states, without ruling on it, that
Reticulum encrypts every packet and that Part 97 in the United States forbids
messages encoded to obscure their meaning on amateur frequencies: whether a
given link is lawful is for you to establish. Read section 6 before you
transmit. Add yourself to `dialout` first.

## Offline, LAN and radio

| Part | With no internet? |
|---|---|
| Two machines on one local network, NomadNet, `rncp`, `rnsh` | Yes. |
| An RNode or packet link | Yes: it is radio. |
| Linking to a distant hub or the wider Reticulum | No: it needs a TCP link. |
| Installing, and `rnodeconf`'s firmware fetch | No: needs the network (`rnodeconf` can be pointed at a file; see its help). |

## Where the detail lives

[Mesh and Reticulum](../guides/mesh-and-reticulum.md) (all 13 sections),
the [`mesh` profile](../profiles/mesh.md), the [RNode device page](../hardware/rnode.md),
[mesh inventory](../reference/mesh-inventory.md), and upstream's manual at
<https://reticulum.network/manual/>.

## What was measured, and what was not

Measured on 2026-10-03, on a Parrot 7.4 machine and in Debian 13 containers
with rootless Podman: the pins install with every hash matching (`rns` 1.5.6,
`lxmf` 1.2.0, `nomadnet` 1.4.4); the shared instance is an abstract Unix
socket and no TCP port; two containers on one bridge found each other, a probe
returned over one hop, an LXMF message was delivered, and an `rnsh` listener
accepted a connection; the install and uninstall through the engine; and
another account attaching to the first account's instance.

Not measured:

- **Any LoRa link.** No RNode and no Meshtastic node has been run; the maintainer's
  boards were lost in a flood, and the `rnode` entry is `untested`.
- **NomadNet's text interface**: it was started in daemon mode only.
- **Any internet link**: the TCP examples are upstream's.
- **`rnodeconf`'s download**: where it fetches from and whether it verifies it.
- **The service under a real systemd user manager**, and propagation between
  two nodes.
- **What another account could send through your instance** once attached.
- **arm64 and Python 3.14.**
