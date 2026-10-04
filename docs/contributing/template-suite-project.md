<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Template: a suite project page

One page per companion project under `docs/suite/`, with exactly these
headings, in this order. A test checks they are present. The project's own
repository owns its technical detail: summarise, link, and state the version
the catalog pins. See [who owns what](documentation.md#who-owns-what).

```markdown
# Project name

## At a glance

| | |
|---|---|
| **Repository** | <https://github.com/ChiefGyk3D/NAME> (verified, not guessed) |
| **Purpose** | one line |
| **Status** | implemented / experimental / planned, version pinned by the catalog, what is not yet run |
| **Platforms** | what it runs on |
| **Independent?** | works alone, or needs which components |
| **Report problems** | issues link, and what to try first |

## What it is for

Practical use cases.

## Dependencies

Software, hardware, network and services.

## Install and first run

Only commands that exist.

## Basic usage

One practical example with the expected result.

## Offline behaviour

What works with no internet, no LAN, no radio. Say which.

## Troubleshooting

Symptoms first; where to report.

## Where the details live

Links to the project's own README and docs, which own the detail.
```

The `Repository` URL must equal the `upstream_url` of the project's manifest.
