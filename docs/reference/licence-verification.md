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

Lines 1–13 carry the **identical** GPL-3.0-or-later notice, word for word. It
carries **no copyright line** — the notice appears without an attached
`Copyright` statement.

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

### What is *not* established, and must not be overstated

1. **Whether the shutdown actually happened on schedule.** Three sources agree it
   was expected end of June 2026; one hedges ("apparently"). Today is
   2026-08-25, so the date has passed — but **we have not tested a live client**
   and must not claim we have. Correct phrasing: *reported to stop functioning
   end of June 2026*.
2. **The final version number.** Newsline says the final release is **4.22**.
   AHRL v27 ships **`ESPHamClock-V4.23.zip`** and its CHANGES lists "updated
   ESPHamClock 4.23". One of the two is wrong, or 4.23 came from a community
   mirror. Unresolved, and it does not change the conclusion.

### Successors — there are three, not one

| Project | What it is |
|---|---|
| `hamclock-next` (k4drw) | Full SDL2 rewrite. **AHRL v27 already ships the tarball and never calls the install function** (**D-013**). |
| `openhamclock` (accius) | Updated HamClock fork; ARRL EMA reports it "is being updated regularly". |
| Open HamClock Backend (`ohb.works`) | Replacement *server*, keeping existing clients alive. |

AHRL already ships an `open_hamclock.desktop` bookmark pointing at
openhamclock.com — so it has a bookmark to a successor while building four
copies of the discontinued original.

### Why this matters to the schema

All four AHRL HamClock menu entries hardcode `-b hamclock.com:80` as a launcher
argument. A dead upstream service cannot be repointed without editing generated
launchers. **The backend URL must be a manifest field, not a launcher constant** —
this is shape 7 in the schema work.
