<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Credits

Hammunition is built on other people's work, twice over. The software it
installs is written by its authors, and every one is linked from [The
projects we install](projects.md). The *choice* of software, which programs
are worth installing, which work, which are dead, comes from six projects
that did that curation long before this one existed. They are inventory
sources and prior art, not things this project replaces.

## The projects whose curation seeded the catalog

### Andy's Ham Radio Linux — Andy Stewart, KB1OIQ

The direct inspiration and the closest thing to what Hammunition does. AHRL
has served the amateur radio community for well over a decade, and its
package curation is the most valuable artifact in this space. It also moved
from being a distribution to being an installer on an existing system, which
is the model this project follows.

<https://sourceforge.net/projects/kb1oiq-andysham/>

### 73Linux — Jason Oleham, KM4ACK

Winlink, packet and EMCOMM: Pat, BPQ, AX.25, ARDOP and Direwolf, a domain
AHRL does not cover. Its community side-loading model shaped the catalog's
three tiers.

<https://github.com/km4ack/73Linux>

### EmComm Tools OS Community — Gaston Gonzalez, KT7RUN

The EMCOMM station as a system: choose the radio once and every program is
configured for it, with offline maps and reference data for when the network
is gone. Those two ideas are being rebuilt here as catalog data.

<https://github.com/thetechprepper/emcomm-tools-os-community>

### Skywave Linux — Philip Collier, AB9IL

Shortwave and utility listening, remote receivers, and the aeronautical
decoders (ACARS, HFDL, VDL2) that no distribution packages.

<https://skywavelinux.com/>

### DragonOS — cemaxecuter

The reference for SDR and signals work on Linux, far larger than anything
else in this space.

<https://cemaxecuter.com/>

### The Debian Hamradio Blend

The Debian Hamradio Maintainers' task lists: team-governed, signed and
machine-readable. Most of what this catalog installs, it installs because
they package it.

<https://blends.debian.org/hamradio/>

## The data

The offline units install data, not software, and each set has its own
terms. The install plan prints each one's licence before you confirm.

| Data | From | Terms |
|---|---|---|
| Map regions | [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, cut into regions by [Geofabrik](https://download.geofabrik.de/) | ODbL 1.0: credit "© OpenStreetMap contributors" when you share a map made from it |
| Elevation | [Copernicus DEM GLO-30](https://registry.opendata.aws/copernicus-dem/), from the European Union's Copernicus programme | [Copernicus DEM licence](https://copernicus-dem-30m.s3.amazonaws.com/readme.html): free, with attribution |
| Country boundaries | [Natural Earth](https://www.naturalearthdata.com/) | [Public domain](https://www.naturalearthdata.com/about/terms-of-use/) |
| DXCC country files | Jim Reisert, AD1C, [country-files.com](https://www.country-files.com/) | Free to use and redistribute |

## The tools this site is built with

[MkDocs](https://www.mkdocs.org/) and [Material for
MkDocs](https://squidfunk.github.io/mkdocs-material/), published by GitHub
Pages.
