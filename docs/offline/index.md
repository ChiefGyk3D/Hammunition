<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Offline documentation

This documentation can be taken with you as a folder of plain web pages that
opens from a disk with **no internet and no web server**. It is the same
text as this site, built from the same source, with search that works
locally.

## Three different downloads

Do not confuse them. Each is its own step, with its own failure modes.

| You want | How | Needs internet |
|---|---|---|
| **These documents**, to read offline | This page: build or download the bundle | Once, to get it |
| **The software** (programs, drivers) | `hammunition install ...` | Yes, or your distribution's mirror |
| **Operational data** (maps, books, forms, layers) | Data units and `hammunition maps ...`: [Offline data](../emcomm/offline-data.md) | Yes, or a [LAN mirror](../guides/lan-mirror.md) |

The bundle contains **only documentation**. It does not install anything,
and a page describing a map download does not give you the map.

## What is in the bundle

- Every page of the site: the [suite](../suite/index.md), the [application
  reference](../packages/index.md), [EMCOMM guides](../emcomm/index.md), the
  guides, [profiles](../profiles/index.md), hardware pages, troubleshooting and
  the command reference. Project records such as the decision log are **not**
  included; links to them go to GitHub and need the internet.
- The theme's own scripts, styles and icons, copied in. **No web fonts, images
  or scripts are loaded from anywhere else.**
- A search box that searches the bundle only.
- `BUILD-INFO.txt`: the build date, the commit and the version of the engine
  and each companion project the catalog pins. The same line is in every
  page's footer.
- `THIRD-PARTY-NOTICES.txt`, `LICENSE` and `SHA256SUMS`.

**External links** (to GitHub, upstream projects, publishers) are marked
**↗ (online)**: they cannot open without the internet and their content is
*not* in the bundle. Only documentation written for this project is included;
no third-party manuals, books, maps or datasets are copied into it.

## Get it

**Build it yourself** from a checkout (needs the documentation dependencies
once; `pip install -e ".[docs]"` in a virtualenv):

```sh
python scripts/build_offline_bundle.py
```

That writes `dist/hammunition-docs-<version>.zip` and the folder it came from,
and then **verifies** the folder: every link and asset resolves inside it, and
nothing references an outside host. It exits non-zero if the check fails.

**Download it:** the `Docs bundle` workflow builds the same file and attaches
it to the run as an artifact (manually, and on a version tag). It is not yet
published as a release asset: that publication is pending.

## Open it

1. Unzip it anywhere.
2. Open `index.html` in a browser.
3. Use the search box, or the navigation tabs: Suite, EMCOMM, Applications.

There is nothing to install and no server to run. Opening it needs a browser
only. To check an extracted copy yourself:

```sh
python scripts/build_offline_bundle.py --verify /path/to/hammunition-docs
```

## Check the date

The footer of every page and `BUILD-INFO.txt` say when it was built and from
which commit. Documentation changes with the software: if the date is old,
rebuild it before a deployment, and check the versions against what you
installed (`hammunition status`).

## Update it

Pull the checkout (`git pull`), build again, replace the old folder. The bundle
is a snapshot; it does not update itself.

## Move it to another machine

Copy the zip with a USB drive or `scp`, then check it:

```sh
sha256sum -c SHA256SUMS      # inside the unzipped folder
```

## Verified how

The build script's verifier is part of the test suite. It checks the built
folder statically (no external scripts, styles, fonts or images; every
internal link and asset exists; the search index is present; the build line is
in the pages) and a test breaks a bundle on purpose to confirm it fails.
The extracted bundle has also been opened in a browser from `file://` with
every request recorded, to confirm none leaves the folder. That is a manual
check: repeat it on your own machine before relying on it.

## Not included

Everything that needs the network, installed software, and operational data.
The software itself is installed with [the engine](../getting-started/installation.md).
