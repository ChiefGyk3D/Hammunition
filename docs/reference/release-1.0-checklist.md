<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# The 1.0 checklist

**Written:** 2026-09-13, from measurements, after the maintainer asked how
close 1.0 is. SCOPE.md defines 1.0 as stages 1 through 6, and every one of
them is in the catalog; M5's exit criterion is met on six VMs. What is left is
verification and one decision. Each item names its owner, because most of
them need either the maintainer's hardware or the maintainer's key.

## Done, and where the evidence is

| Gate | Evidence |
|---|---|
| Stages 1–6 in the catalog | 249 manifests; Blend 152 of 152; parity 106 of the 124 units that owe a manifest, every gap with a recorded reason (`parity-coverage.md`) |
| Every backend 1.0 needs, with `uninstall` for each | apt, source, git, binary, venv, node, apt_repo, data — `m5-parity-verified.md`, `vm-campaign-*.md` |
| M5: install-success at least AHRL's 90.5% | zero hard failures on six targets (`m5-parity-verified.md`) |
| The whole catalog on the field target | 164 units installed and verified, 33 effect checks (`bench-verification-5430.md`, session 6) |
| Idempotent re-runs for builds | D-051, measured: 143 of 165 plan nothing on a re-run |
| `update` and `update --upstream` | D-053, measured: 171 units in 0.7 s; 25 probes in 7.5 s; three pins re-pinned (#97) |
| The menu, on KDE Plasma | D-050/D-054/D-055, measured on the field laptop: 8 groups, 54 submenus, 108 entries placed, largest submenu 11 |
| GNOME app-folders | written by `menus apply --gnome` and read back from gsettings on the field laptop, 2026-09-13: 8 folders, each carrying its group's categories and app list |
| Open questions | none (`QUESTIONS.md`) |

## Open, with owners

| # | Item | Owner | How it closes |
|---|---|---|---|
| 1 | **The attached-hardware ladder** on the field target: HackRF Pro, Proxmark3, a Meshtastic node, the C5 Wardriver, one at a time; `hardware list` recognises each, permits it, symlinks it as `device-naming.md` says | maintainer, on the bench | session 10 in `bench-verification-5430.md`; the README's "not yet exercised against an attached device" line comes out |
| 2 | **The rebuilt menu seen on GNOME and Xfce.** Verified as data on 2026-09-13: GNOME's eight folders written and read back from gsettings on the field laptop; the Xfce-form menu file resolved by the freedesktop reference parser (python-xdg) against this machine's application directories into the same tree KDE shows — 8 groups, 51 populated submenus, 204 entries, GNU Radio nested, Hammunition Hill under *Operate the Station*, nothing loose once wsjtx claims its aggregator. What has not happened is a person opening either launcher on a VM; the VM host session has the request | the VM host session, or the maintainer on the Debian GNOME VM and the Kali Xfce VM | one screenshot each, recorded on the VM page |
| 3 | **COSMIC menus.** No mechanism has been measured (D-036). **Recommended and written into SCOPE.md as post-1.0** (stage 11, beside mesh): the Pop!_OS 24.04 VM exists, nobody has opened COSMIC's app library on it, and holding 1.0 on a desktop with no measurement would be the D-036 mistake in reverse. If the maintainer prefers to measure now, one VM session decides it | maintainer's word on the recommendation | SCOPE.md line stands, or a measured mechanism replaces it |
| 4 | **Pop!_OS as a declared target.** Its VM campaign passed clean (`vm-campaign-pop.md`). **Recommended: stay VM-verified and undeclared for 1.0.** A declared target is one CI builds a container for (`containers/targets.yaml`, `.github/workflows/ci.yml`), and no honest Pop!_OS container exists — Pop's identity packages live in its own PPA, so the Mint trick (the distribution's own base-files on Ubuntu's image) has no counterpart. Declaring it would claim a CI check that cannot run. The campaign page records that nothing refused for being Pop rather than Ubuntu 24.04, which is what a Pop operator needs to know | maintainer's word on the recommendation | the campaign page's "left with the maintainer" closes either way |
| 5 | **A signing key.** `releasing.md` documents SSH-signed tags and `.github/allowed_signers`; no key exists | maintainer generates it (nobody else may) | the first signed tag is 1.0 |
| 6 | **The second full-profile run on the field target**, which attributes the 19 builds D-051 cannot yet decide, then `hammunition update` reads them all up to date | maintainer (sudo) | ladder item 6 on the bench page |
| 7 | **Real uninstalls on the field target**: `station`, `rf-security`, `packet`, against their dry runs | maintainer (sudo) | ladder item 5 on the bench page |
| 8 | **Version and tag.** 0.9.0 (beta) is the version on `main` from 2026-09-13, with its changelog entry; the 1.0 bump and the first signed tag come last | this repository, last | bump to 1.0.0, changelog entry, annotated and signed tag |

Issues open and not blocking: #96 (a declared capability step for linbpq;
route 1 shipped in #97), #76 (the wiki, post-1.0), #105 (the mesh and
Reticulum track, SCOPE.md stage 11, post-1.0).

## The bench ladder for the hardware session

Every step is `sudo`-free until it says otherwise, and every one is recorded
in `bench-verification-5430.md` afterwards.

```
hammunition doctor                       # 11 ok expected, as in session 8
hammunition hardware list                # before anything is plugged in: the baseline
# plug in one device, wait two seconds
hammunition hardware list                # the device recognised, its class named, its permission state
ls -l /dev/serial/by-id/ /dev/hammunition* 2>/dev/null   # the symlink device-naming.md promises, if any
hammunition hardware apply --dry-run     # nothing to change is the expected answer; anything else is a finding
# unplug, next device
```

Then, with the RTL-SDR or the HackRF attached: open *Hammunition → SDR &
Listening → SDR Receivers & Transceivers → Gqrx* from the menu, select the
device, confirm audio. That one click is the first GUI-against-radio
measurement on this machine, and it closes ladder item 3.
