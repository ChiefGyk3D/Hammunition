# Reticulum core — design (Track C, PR 2)

**Status:** draft for the maintainer's review, 2026-10-03.
**Track:** `docs/SCOPE.md` Track C, stage 11; tracking issue #105.
**Precedes:** PR 1, `docs/reference/mesh-inventory.md` (the measured pins
and licences this design installs; nothing here names a version that page
does not). **Follows:** PR 3 (`meshtasticd` and the web client), PR 4
(MeshCore CLI), then Sideband and MeshChat once the inventory says what they
cost, and the `hammunition-docs` offline-site unit as its own spec.

## Why

The maintainer asked on 2026-10-03 for "base functionality for Reticulum,
NomadNet, RNS, LoRa and the internet-capable stuff, with a ton of
documentation", for EMCOMM use: a laptop in a passenger seat with no
infrastructure, and the notes to run it offline. Today the catalog carries
two Meshtastic units and nothing of Reticulum. Nothing Reticulum is in any
Debian-family archive (measured 2026-10-03 on Parrot 7.4 and in
`mesh-inventory.md`), so every unit comes from PyPI through the venv
backend, hash-pinned end to end, exactly as `artemis` and `pygpsclient` do.

## Rulings already taken (2026-10-03)

1. **Licence.** Reticulum, LXMF, NomadNet and Sideband ship under the
   "Reticulum License", which is not OSI-approved and carries use
   restrictions. Carried under the **D-033** shape, as LinBPQ is: installed
   from PyPI at the operator's direction, never mirrored, never vendored,
   the terms quoted on each package page and the licence named in the plan
   line that prints before the confirmation. No consent gate: nothing here
   transmits until the operator attaches and configures a radio.
2. **Order.** Reticulum core first, then Meshtastic's daemon, then MeshCore.
3. **Offline docs** are a separate unit and spec (`hammunition-docs`,
   served by `hammunition reference serve` on 127.0.0.1).

## Scope

**In:** four package units, one profile, one hardware entry, one guide, the
package pages the generator writes, troubleshooting entries, CLI reference
lines for the new user service, a changelog fragment, and the decision
record entry (**D-080**, number to be confirmed against `DECISIONS.md` at
plan time).

**Out, by name:** Sideband (`sbapp`: a Kivy desktop build whose system
packages and size the inventory measures first), Reticulum MeshChat (an
AppImage, post-1.0 backend), `meshtasticd`, MeshCore, any TAK software, any
Reticulum configuration writer beyond what rnsd writes itself, any
transport the catalog does not already carry, and any claim that a LoRa
link has been made (no RNode has been run here).

## Units

Each is one manifest in `catalog/packages/`, `method: venv`, requirements
hash-pinned from the inventory's `uv pip compile --generate-hashes` run,
`python: ">=3.11"` unless the inventory measured a higher floor, and
`expose:` for the console scripts an operator types. One unit per upstream
project is the catalog's grain (**D-010**: each has its own update block);
the venvs overlap in their dependencies, which costs disk the inventory
states and the package pages repeat.

| Unit | Upstream (PyPI) | Exposes | Categories | Notes |
|---|---|---|---|---|
| `rns` | `rns` | `rnsd`, `rnstatus`, `rnpath`, `rnprobe`, `rnid`, `rncp`, `rnx`, `rnodeconf` | `mesh` | Carries the `hammunition-rnsd` user service (below). `rnodeconf` is the RNode flasher: installed under **D-026** (the means of talking to a device); it downloads firmware itself, from upstream's GitHub releases, and the package page says what it checks and what it does not, as measured. |
| `lxmf` | `lxmf` | `lxmd` | `mesh` | The message layer and its propagation-node daemon. `lxmd` is **not** a user service in this PR: a propagation node stores other people's messages, and running one is a decision the operator takes in the guide, not a default. |
| `nomadnet` | `nomadnet` | `nomadnet` | `mesh` | Terminal client; `launchers:` entry with `terminal: true`, `menu_title` "NomadNet (Reticulum messaging and pages)" under *Mesh*. Depends on `rns` running as the shared instance or starts its own. |
| `rnsh` | `rnsh` | `rnsh` | `mesh` | Shell over Reticulum. MIT. Listed because it is the first thing an EMCOMM operator asks for after messaging works: a terminal on the other laptop. |

**Depends.** `python3-venv` and the system libraries `cryptography`'s
wheel needs on each target, as the venv backend's existing units already
list; `pyserial` is inside the venv. No `build_depends` unless the inventory
finds a target without a wheel for the pinned `cryptography`, in which case
that target is **deferred by name** (**D-039**), never built.

**Licence fields.** `license:` as the schema spells it set to the
inventory's SPDX-style identifier for the Reticulum License on `rns`,
`lxmf`, `nomadnet`; `MIT` on `rnsh`. `docs/reference/licence-verification.md`
gains one row per unit with the file read and its date.

## The shared instance: `hammunition-rnsd`

A `user_services:` block on the `rns` manifest, the **D-073** shape:

```yaml
user_services:
  - name: hammunition-rnsd
    description: Reticulum shared instance for this operator's Reticulum programs
    exec: ["{venv}/bin/rnsd", "--service"]
    listens:
      - {protocol: tcp, address: 127.0.0.1, port: 37428}
    restart: on-failure
```

- No `when_station`: Reticulum needs no station value. **D-035** is not
  involved; nothing is deferred.
- `{venv}` is the unit's own venv path, which the `launchers` block already
  substitutes; the plan writer confirms `user_services` resolves it the same
  way or adds that (one line in the renderer and a test).
- Enabled at install, as the rig service is, because the shared instance is
  what makes every client (`nomadnet`, `lxmd`, `rnsh`, `rnstatus`) find one
  running stack instead of each starting its own. The plan discloses the
  listener and the first-start behaviour below; `hammunition services`
  shows it; `systemctl --user disable --now hammunition-rnsd` turns it off,
  and the guide prints that command.
- `--unattended` linger is the existing opt-in; nothing new.
- **What rnsd does on first start, disclosed in the plan text and the
  package page:** writes `~/.reticulum/config` with its defaults, which
  enable the *AutoInterface* (link-local IPv6 multicast on every interface,
  so two Hammunition laptops on one Wi-Fi or Ethernet segment see each
  other with no configuration) and the shared-instance socket on
  127.0.0.1:37428. It opens no listening socket on a routable address and
  makes no outbound connection. The engine writes **no** Reticulum
  configuration: the file is the operator's (**D-078**'s spirit: their
  identity, their interfaces), created and owned by rnsd under their
  account, and the guide shows the stanzas to add. Uninstall stops and
  removes the service and leaves `~/.reticulum` in place, saying so.
- `restart_prevent_exit_status` is not set unless the inventory's
  measurement of rnsd's exit codes finds a configuration-error code that
  should not loop.

## Hardware: `rnode`

`catalog/hardware/devices/rnode.yaml`, class `badgelife` like `meshtastic`,
`status: supported`, `maintainer_verified: false` (**D-027**). RNode is
firmware, not a board: it runs on the same LilyGO, Heltec and RAK boards
the LoRa sweep already read (`docs/reference/lora-inventory.md`), so the
entry carries the identifiers that sweep attributes to the boards RNode
supports, each marked ambiguous by measurement exactly as `meshtastic.yaml`
does, and claims nothing about which board. `scripts/lora-sweep.sh` gains
RNode's board list as a third source only if upstream publishes one in a
readable form; otherwise the entry cites the Meshtastic/MeshCore sweep and
RNode's own supported-boards page, dated. No udev symlink (**D-028**): the
chips are CP2102, CH340 and ESP32-S3 native USB, the same ones the rig cable
uses. The dialout group rule the class already applies is the whole
permission story.

The hardware page `docs/hardware/rnode.md` is generated from the entry plus
prose: what RNode is, which boards, the flasher, and the one legal note
below.

## Profile: `mesh`

`catalog/profiles/mesh.yaml`, `stage: post-1.0`, members: `rns`, `lxmf`,
`nomadnet`, `rnsh`, `python3-meshtastic`, `gtk-meshtastic-client`. The six
`ProfileDocumentation` fields the profile pages generate from (added in
#276) are filled: what installs and why together; footprint from the
inventory's measured venv sizes; what it excludes (Sideband, MeshChat,
`meshtasticd`, MeshCore, TAK) and why; what the operator configures by hand
afterward (an RNode or TCP interface; an LXMF identity; Meshtastic's
region). `tests/test_profiles.py`'s membership assertions cover it like the
others; the profile is in no `install` default and nothing else references
it.

## Guide: `docs/guides/mesh-and-reticulum.md`

In the voice and shape of `offline-navigation.md`: numbered sections, every
command copy-pasteable, placeholders only, and a closing *What is measured,
and what is not*. Sections:

1. **What Reticulum is**, in two paragraphs for an operator who has run
   Winlink and APRS: addresses are keys, every link is encrypted, any
   medium carries it, no infrastructure is assumed. What it is **not**:
   Meshtastic (a different network; the two do not talk).
2. **Install**: `hammunition install mesh`, what the plan shows, the
   licence line, the service line.
3. **First run**: `rnstatus` against the shared instance; what the
   AutoInterface already gives you; two laptops on one Wi-Fi.
4. **Messaging with NomadNet**: identity, the LXMF address, a conversation,
   the node pages, where the data lives (`~/.nomadnetwork`).
5. **Over the internet**: the `TCPClientInterface` stanza; the public
   community entry points Reticulum's own manual lists, quoted with the
   date read; your own hub on a VPS or the Bunker as a `TCPServerInterface`.
6. **Over LoRa with an RNode**: the board, `rnodeconf` to flash and to set
   frequency, bandwidth, spreading factor and power; the
   `RNodeInterface` stanza; **the legal note**: Reticulum encrypts every
   packet, and in the United States Part 97 forbids messages encoded to
   obscure their meaning on amateur frequencies, so an RNode on an amateur
   band is not something this guide can tell you is lawful; the unlicensed
   ISM allocations (915 MHz in Region 2, 868 MHz in Region 1) under their
   own power and duty-cycle rules are where RNode links are normally run.
   Stated as a disclosure, never adjudicated (**D-021**'s rule for
   consent gates applies to prose too).
7. **Over a packet TNC**: the `KISSInterface` stanza against Direwolf's
   KISS port, which `packet` already configures; the same legal note.
8. **A shell on the other laptop: rnsh**.
9. **A propagation node: lxmd**, when and why, and that it holds others'
   traffic.
10. **EMCOMM notes**: what works with nothing but two laptops and
    batteries; what needs an RNode; what needs the internet; keeping the
    identity file; printing this guide. Points at the offline docs unit
    once it exists.
11. **Meshtastic beside it**: the two existing units, what they do today,
    and that `meshtasticd` is PR 3.
12. **Removing it**: `hammunition uninstall mesh`, what stays
    (`~/.reticulum`, `~/.nomadnetwork`, the identity) and why.
13. **What is measured, and what is not** (below).

`docs/troubleshooting/` gains entries: *rnstatus says no shared instance*
(service not running; `systemctl --user status hammunition-rnsd`), *two
laptops do not see each other* (AutoInterface needs IPv6 link-local and a
multicast-passing network; many phone hotspots block it), *rnodeconf cannot
open the port* (dialout, the parked-device case from **D-056**).

The wiki mirror picks the guide up on merge (`scripts/gen_wiki.py` reads
`docs/`); nothing wiki-specific is written.

## Documentation the generators write

Package pages from the four manifests' documentation blocks (what it does,
why, prerequisites, known problems, upstream support), each quoting the
licence position. `docs/projects.md` and `docs/reference/parity-coverage.md`
regenerate. `docs/reference/cli.md` gains `hammunition-rnsd` in the
`services` section's list of user services. `docs/reference/json-interface.md`
changes only if a document changes, which this design does not expect.

## Decision record

**D-080 — Reticulum is carried as per-user venvs with one shared instance
per operator; the Reticulum License is stated, not gated; the engine writes
no Reticulum configuration.** Evidence: the inventory's archive sweep (no
target packages any of it), the licence text, rnsd's first-start behaviour
as measured in a container, and the shared-instance port. `CLAUDE.md`'s
decision table gains the row.

## Tests

- Manifest validation and the existing catalog-wide tests (categories,
  pins, documentation fields, profile membership, SPDX headers).
- `scripts/check_pin_reviews.py --only` on the four manifests, per the PR
  rule for changed pins.
- A container run on Debian 13 (`scripts/run-targets.sh`, the unit pass):
  `hammunition install rns` as an unprivileged account, then `rnstatus`
  shows the shared instance and the AutoInterface, and `rnprobe` against
  the instance's own destination answers. This is the measurement the
  guide's section 3 rests on; without it the section is not written as
  fact.
- A second container test that `hammunition uninstall rns` removes the
  service unit and the venv and leaves `~/.reticulum`.
- `tests/test_site.py` for the new pages in the nav, `check_doc_links.py`,
  the generated-docs no-op check.

## What is measured, and what is not (as this spec stands)

Measured: the archive sweep and PyPI state (inventory, 2026-10-03). Not
measured, and to be measured by the plan before the guide claims them: rnsd
first start in a container; two instances discovering each other over
AutoInterface (two containers on one bridge); NomadNet exchanging a message
over that; `rnsh` over it. Not measurable here and said so in the guide:
any LoRa link (the maintainer's LoRa boards were lost in a flood; the RNode
entry is closed from upstream data as `meshtastic.yaml` was), and the
TCP interface to a public hub (not run from CI by policy; the guide quotes
the manual, dated).

## Open questions for the maintainer

None blocking. Two to confirm at plan review: (a) that
`hammunition-rnsd` enabled at install is what you want, rather than
installed and left for `hammunition services enable` (the D-073 precedent
enables; AutoInterface traffic is link-local only); (b) whether the `mesh`
profile should include `rnsh`, which is more tool than ecosystem.
