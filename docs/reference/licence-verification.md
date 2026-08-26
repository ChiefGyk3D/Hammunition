# Licence verification record

Evidence for **D-001** (73Linux is an inventory source, not a base) and
**D-011** (provenance: facts only, from both sources). `why-hammunition.md`
makes a public claim about 73Linux's licence; this is what that claim rests on.

**Verified:** 2026-08-25. **Re-verify before any public release.** A licence
file can appear at any time, and if one does, D-001 reopens.

---

## 73Linux — no licence, verified three ways

**Repository:** `km4ack/73Linux`, default branch `master`, last push
2026-06-20T13:13:54Z.

### 1. GitHub licence API — null

```
GET /repos/km4ack/73Linux         →  "license": null
GET /repos/km4ack/73Linux/license →  HTTP 404  {"message": "Not Found"}
```

### 2. Full recursive tree — zero matches

`GET /repos/km4ack/73Linux/git/trees/master?recursive=1` returned **158 paths,
not truncated**. Case-insensitive search for `licen|copying|gpl|mit|legal|
copyright` across every path: **NONE**.

This is the strongest form of the negative available remotely — not "no file at
the root," but no file anywhere in the tree.

### 3. No notice in any script header

`73.sh` opens (verbatim, first 7 lines):

```bash
#! /bin/bash

# Localization can do weird things.
# See https://github.com/km4ack/73Linux/issues/144 and https://github.com/km4ack/73Linux/issues/71.
# 73Linux is not translated in any other languages and does change behaviour based on locale settings.
# Forcing to use the default locale prevents any of those localization issues.
export LC_ALL=C
```

Grep for `copyright|licence|license|GPL|MIT|BSD|Apache` across `73.sh`,
`changelog`, and all nine scripts in `bin/`: **0 hits in every file.**

### Conclusion

No licence grant of any kind. Under the Berne Convention default, all rights are
reserved to the author. GitHub's Terms of Service grant the right to view and
fork *on GitHub*, and nothing further — no redistribution, no derivative works.

**Consequence:** we may use facts (package names, versions, upstream URLs,
install methods). We may not copy, port, or redistribute any 73Linux code —
including the roughly half of the delta that is KM4ACK's own software rather
than third-party packages he wraps.

**The cheap fix remains open:** one email to Jason asking him to add a licence
file. It either unblocks the delta or closes the question cleanly.

---

## AHRL — GPL-3.0-or-later on exactly two files

**Source:** `andy_v27.tar.gz`, extracted tree. Top-level entries are exactly
`bin`, `share`, `tarballs` — **no top-level `LICENSE`, `LICENCE`, or `COPYING`
(0 matches).**

### `bin/install_ahrl`

`sha256: 74e249fec4fc2eb0dd1ba82143ff989c252811148e5b4e18c6234efaaba04981`

Lines 3–15, verbatim:

```
################################################################################
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.
################################################################################
```

Lines 18–21, verbatim:

```
################################################################################
# Script for installing "Andy's Ham Radio Linux" (AHRL).
# Copyright 2024, Andy Stewart (KB1OIQ)
# Copyright 2025, Andy Stewart (KB1OIQ)
```

### `bin/test_menus_debian13.py`

`sha256: e100b56609ad4850cd1ba89fdfee18bacb05fd944ed40801c67be813e075e56b`

Lines 1–13 carry the **identical** GPL-3.0-or-later notice, word for word.

**Discrepancy, recorded 2026-08-25:** unlike `install_ahrl`, this file carries
**no copyright line at all** — the licence notice appears without any attached
`Copyright` statement naming an author or year.

`DECISIONS.md` D-011 says the two files are "GPL-3.0-or-later (Copyright
2024/2025, Andy Stewart KB1OIQ)", which is precise for `install_ahrl` and
imprecise for this one. Recorded for accuracy; **no further action**. It changes
nothing operationally: we do not reuse either file, and a GPL notice without a
copyright line is still a GPL notice.

### Everything else — no notice

Every AHRL-authored file was examined: `bin/*` (11), `share/applications/*.desktop`
(105), `share/desktop-directories/*.directory` (18) plus `install_it`, and
`share/doc/Andy_Ham_Radio_Linux/*` (24).

| | Count |
|---|---:|
| AHRL-authored files examined | **159** |
| Carrying a licence notice | **2** |

The `LICENSE` and `COPYING` files present under `share/doc/` — nanovnasaver,
xastir, owx, hamlib, JTDX, wsjtx, direwolf — are **third-party documentation
AHRL bundles**, not licence grants covering AHRL's own work. Do not mistake them
for one.

### Conclusion

Matches what **D-011** records:

- The installer and the test harness are **GPL-3.0-or-later**. Porting their
  logic would make our engine a derivative work and force GPL-3.0 on it.
- The other **157** authored files — every `.desktop`, every `.directory`, the
  menu structure, all documentation prose, and seven of the nine helper scripts
  — carry **no notice at all**. Their status is genuinely unclear, which is a
  reason to avoid them, not a reason to assume permission.
- Writing our engine from the inventory keeps provenance unambiguous.

---

## Related verification: the HamClock sunset

Not a licence question, but it gates a public claim in `dispositions.md`
(SUPERSEDE #1) and is held to the same evidentiary standard.

### What is firmly established

**Amateur Radio Newsline**, reported by Kevin Trotman, 2026-01-30:

> "Elwood had become a Silent Key on Thursday, the 29th of January"

> "the final release of HamClock is version 4.22. All HamClocks are to stop
> functioning in June of this year."

**Eastern Massachusetts ARRL**, W1IZZ, 2026-02-03:

> "Due to Elwood's recent death, HamClock will apparently stop working at the
> end of June."

> "Some enterprising folks have put together an updated version of HamClock,
> known as OpenHamClock."

**Amateur Radio Daily / Ham Weekly**, January 2026: the project "will no longer
receive updates"; devices continue initially but "it's expected data will no
longer be pushed to the application" by June 2026. Recommends the **Open HamClock
Backend** (`ohb.works`) to keep existing clients running past the sunset.

### TESTED 2026-08-25 — the forecast was wrong, and I nearly published it

Last session recorded the June 2026 sunset as *reported*. Instructed to test it
rather than report it, I did. **The conclusion changes.**

#### What the probes found

| Probe | Result |
|---|---|
| DNS `hamclock.com` | 52.15.88.208 |
| TCP `hamclock.com:80` | **CONNECTED** |
| `GET http://hamclock.com/` | **HTTP 200**, 22,860 bytes, `Last-Modified: Fri, 07 Aug 2026` |
| `GET /ham/HamClock/version.pl` | **HTTP 200** |
| `GET /ham/HamClock/esats.pl` | **HTTP 200**, 4,545 bytes |
| DNS `clearskyinstitute.com` | 72.167.43.150 |
| TCP `clearskyinstitute.com:80` | **NO CONNECTION** |
| `GET clearskyinstitute.com/ham/HamClock/version.pl` | **no response, terminated** |

`version.pl` returns, verbatim:

```
4.27

Changes since 4.25:
  * New panes: Active Nets, Rocket Launches
  * Satellite transponder frequency display
  * HamQSL band conditions
  * Upstream maintenance and bug fixes
```

#### What that means

1. **HamClock did not stop. It was continued.** Newsline reported 4.22 as final
   in January; AHRL shipped 4.23 in May; the live backend serves **4.27** with a
   changelog of new features. Development continued past the author's death.
   **This resolves the 4.22-vs-4.23 discrepancy** — both were true snapshots of
   a moving target, and neither was final.

2. **Elwood's original server *is* gone.** `clearskyinstitute.com` refuses TCP
   entirely. The sunset was real — it just landed on the original host, not on
   the name AHRL happens to point at. hamclock.com's own page says so: *"your
   clock keeps ticking now that the original Clear Sky Institute server is
   offline."*

3. **hamclock.com is now a different operation.** Patron-funded, commercial
   adjacent: *"Become a patron sponsor by subscribing: $4.99/month is what keeps
   the backend on the air for everyone,"* plus an Amazon Appstore listing and a
   Fire TV build. It is a third-party continuation, not the author's service.

#### The correction I owe

Last session's `dispositions.md` SUPERSEDE #1 said AHRL v27 leaves users with
*"four menu entries pointing at a discontinued backend."* **That is wrong.**
AHRL's launchers pass `-b hamclock.com:80`, and hamclock.com is up, maintained,
and serving a newer version than AHRL ships. Corrected in place.

Had this gone into public copy unverified, we would have told users a live
service was dead — in a document whose entire argument is that we report status
honestly. The instruction to test rather than report is what caught it.

#### Limits of what was tested

- Endpoint paths were **guessed** from the original API shape. Two of six
  responded; the four 404s are as likely to be wrong path names as missing
  functionality. **No claim is made that the backend is partial.**
- No HamClock client was run against it. "Serves `version.pl` and `esats.pl`" is
  not "a client works end to end."
- Whether hamclock.com stays free is a commercial question, not a technical one.

#### Four paths forward, not three

| Option | Status 2026-08-25 | Licence |
|---|---|---|
| **hamclock.com** backend | Live, serving 4.27, patron-funded, third-party | service, not software |
| **`accius/openhamclock`** | Pushed **2026-08-22**, 455 stars | **MIT** (dual copyright, so GitHub reports NOASSERTION) |
| **`k4drw/hamclock-next`** | Pushed 2026-06-23, 34 stars | **MIT** — *"Copyright (c) 2020-2025 Elwood Charles Downey (WB0OEW) / Copyright (c) 2026-present HamClock Community Maintainers"* |
| **`ohb.works`** | HTTPS 200, WordPress site | service, not software |

Both candidate clients are MIT and clean under **D-011**. See **Q-006**.

### Why this matters to the schema

All four AHRL HamClock menu entries hardcode `-b hamclock.com:80` as a launcher
argument.

**The testing strengthened this argument rather than weakening it.** In seven
months the backend landscape moved twice: the author's server went offline, and
a third-party patron-funded service took over the name AHRL points at. A
hardcoded launcher constant cannot follow that. A manifest field can, in one
line, for every install. **This is shape 7**, and it is now justified by observed
churn rather than by a forecast.

---

## linbpq / BPQ32 — GPL-3.0-or-later, verified 2026-08-25

**This corrects a maintainer assumption, and it unblocks the 1.0 packet core.**

The working assumption was that linbpq is "free to use, but not open source," so
mirroring might not be permitted. **It is open source.** John Wiseman's software
carries an explicit GPL-3.0-or-later grant.

### Evidence

`https://github.com/g8bpq/LinBPQ` — 276 paths, tree not truncated, last push
2026-08-25 (the project is actively developed).

Like AHRL, there is **no `LICENSE` or `COPYING` file** in the tree and GitHub's
licence API returns `null`. The grant is in the source headers. `LinBPQ.c`,
lines 1–18, verbatim:

```c
/*
Copyright 2001-2018 John Wiseman G8BPQ

This file is part of LinBPQ/BPQ32.
 
LinBPQ/BPQ32 is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

LinBPQ/BPQ32 is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with LinBPQ/BPQ32.  If not, see http://www.gnu.org/licenses
*/
```

Note the wording: *"This file is part of LinBPQ/BPQ32. **LinBPQ/BPQ32** is free
software"* — a statement about the whole project, not that one file.

Sampled 12 of 216 `.c`/`.h` files: **7 carry the header verbatim.** The five
without it are generated data and allocator helpers (`APRSIconData.c`,
`APRSStdPages.c`, `AISCommon.c`, `Alloc.c`, `Alloc.h`) — the pattern of a
project that headers its real source and not its tables.

### The finding that actually matters: **there are version tags**

```
tags: 25.39, 25.36, 25.35, 25.32, 25.30, 25.28, 25.15, 25.13, 25.12, 25.11
releases: NONE
```

This dissolves the problem rather than solving it. The pin-and-verify difficulty
recorded in `DESIGN.md` §15.6 came from 73Linux's *install method* — `wget` of
loose, unversioned binaries from `cantab.net/.../Downloads/Beta/` — not from
anything upstream does. Upstream publishes tagged source.

**We do not have to mirror binaries, and we do not need `status: unverifiable`.**
BPQ becomes an ordinary pinned source build, structurally identical to
AIS-catcher (schema shape 6): a `git` install block with `ref: "25.39"`, a
declared build-dependency list, and no unverified download anywhere.

See **Q-005**. `DESIGN.md` §15.6 is amended accordingly.

### Caveat recorded honestly

The GPL applies to the **source on GitHub**. The prebuilt binaries at
`cantab.net/.../Beta/` are a separate distribution channel with no stated terms
on the page. Under GPL-3.0 the author is free to distribute his own binaries
however he likes, and downstream redistribution of *those specific binaries*
would carry an obligation to offer corresponding source. Building from the
tagged source sidesteps that question entirely, which is a second reason to
prefer it.
