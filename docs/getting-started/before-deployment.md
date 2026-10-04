<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Before a deployment: what to download

Everything on this page needs the **internet (or a [LAN mirror](../guides/lan-mirror.md))**.
Do it ahead, because nothing here can be fetched in the field. Using what you
download does not need the internet afterwards, but some of it needs a
radio, a GPS or a local service to be useful: *offline* does not mean *without
its hardware*. Field use is in [EMCOMM field use](../guides/emcomm-field.md).

There are four different downloads. Do not confuse them:

| You are downloading | With | Section |
|---|---|---|
| **Software** (programs, drivers) | `hammunition install PROFILE` | 1 |
| **Operational data** (maps, books, forms, repeater and infrastructure layers) | data units and `hammunition maps ...` | 2 to 5 |
| **Account state** (a Winlink registration, the gateway list) | `pat-winlink` | 6 |
| **These documents** | the release tarball | 7 |

Use your own callsign and grid square where examples show the placeholders
`N0CALL` and `FN31pr`.

## 1. Software

```sh
hammunition doctor                                # read-only health check
hammunition station set --callsign N0CALL --grid-square FN31pr
hammunition install station --dry-run             # read the plan
hammunition install station
hammunition hardware apply --dry-run              # udev rules and groups; read first
hammunition hardware apply
```

Add the profiles your mission uses: `hammunition list profiles`, then for
example `hammunition install navigation`, `reference`, `packet`,
`digital-modes`. The [profiles](../profiles/index.md) say what each brings and
[disk space](disk-space.md) how much room to have.

## 2. Map regions

```sh
hammunition maps regions                          # fetches Geofabrik's index, lists region paths
hammunition station set --map-regions REGION1,REGION2    # replaces the earlier list
hammunition install navigation
```

Choose every region you may travel through, including the route. Procedure and
limits: [Offline navigation](../guides/offline-navigation.md).

## 3. Reference books and forms

```sh
hammunition reference books                       # the Kiwix books on offer, with size and licence
hammunition station set --reference-books ID,ID
hammunition install kiwix-library ics-forms
```

[Offline reference](../guides/offline-reference.md) names the book ids and what
the forms are.

## 4. Infrastructure layers

```sh
hammunition maps infra import --from-osm         # medical, responders, supply, shelter candidates, ...
```

Built from the installed map extracts, so do it after section 2, and rebuild
after you update the regions. **A mapped shelter, hospital or repeater is not a
statement that it is open or working.**

## 5. Repeater layers

```sh
hammunition maps repeaters import FILE            # your own RepeaterBook export, hearham JSON or CSV
hammunition maps repeaters import --from-osm      # from the installed extracts, downloads nothing
hammunition maps repeaters fetch-hearham          # on request; recorded as unverified
```

RepeaterBook's export is for your own use: bring your own file. The layer's
name carries its source and date. `hammunition maps repeaters --help` lists the
other sources (`fetch-etcc`, `fetch-brandmeister`, `--from-open-repeater`).

## 6. Winlink

Pat's first connection, which registers your callsign and sets your password,
must be over the internet. Then download the gateway list and write down the
ones you can reach: `pat-winlink rmslist --mode packet --sort-distance`. See
[Packet and Winlink](../guides/packet-winlink.md).

## 7. This documentation

Each release publishes `hammunition-docs-VERSION.tar.gz` on the repository's
[releases page](https://github.com/ChiefGyk3D/Hammunition/releases): the whole
site, built by `mkdocs build --strict`. A `hammunition-docs` catalog unit that
serves it from `hammunition reference serve` is planned and does not exist yet.
To build it yourself instead: `pip install -e ".[docs]"`, then
`mkdocs build --strict`; the site is in `site/`.

Extract it and **serve it from the loopback address**: that needs no network,
only the machine itself.

```sh
mkdir hammunition-docs && tar -xzf hammunition-docs-VERSION.tar.gz -C hammunition-docs
python3 -m http.server 8765 --bind 127.0.0.1 --directory hammunition-docs
```

Then open <http://127.0.0.1:8765/>. To move it to another machine, copy the
tarball (check it against the release's `SHA256SUMS`) and extract it there.
The tarball is a snapshot: fetch the next release to update it.

**Opening `index.html` straight from a disk (`file://`) does not work well.**
The site uses directory URLs, so a link such as `guides/` opens a folder
listing, and the search box loads its index with a request a browser blocks on
`file://`. Page reading works; navigation and search need the loopback server
above.

### Checked with the network off

The site was built, extracted and opened in Chrome, from a loopback server and
from `file://`, with every request recorded:

- **Fonts:** before this check the pages requested Google Fonts, so a machine
  with no network fell back to a system font after a stall. `mkdocs.yml` now
  sets `font: false`; no font request remains. `tests/test_site.py` holds it.
- **Search, navigation and images:** over the loopback server, search returned
  results and navigation worked, with no request leaving the machine. There
  are no images in the pages.
- **One request remains:** the header's repository link asks `api.github.com`
  for the star count and latest release. It is decorative and fails silently
  offline; nothing depends on it.

Not checked: other browsers, and a machine that was actually disconnected (the
check watched requests; it did not unplug a network).

## Check what you have

```sh
hammunition update          # offline: installed against the catalog's pins
hammunition status
hammunition artifacts --map-regions REGION1,REGION2 --json   # what a LAN mirror should keep
```
