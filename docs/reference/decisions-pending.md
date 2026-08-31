<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Q-015 — all fourteen decisions ruled and applied

The batch is closed. Decisions 1–2 were ruled individually on 2026-08-30;
decisions 3 and 4 the same morning; the maintainer then directed "go with all
the recommended steps" for the remainder, and every recommendation was applied
with its own commit. `docs/QUESTIONS.md` carries each ruling in place;
`dispositions.md`, `parity-coverage.md` and `not-carried.md` carry the
consequences. **The dispositions summary now reads zero NEEDS-DECISION in
every column.**

| # | Unit | Ruling | Where it landed |
|---|---|---|---|
| 1 | Mail client | Detect → respect → offer (Thunderbird recommended), never silent | `packet` profile suggestion group |
| 2 | Serial terminal | Same mechanism, PuTTY recommended; Termius/MobaXterm named, not offered | `workstation` profile suggestion group |
| 3 | `libhamlib4` | Dependency, not a unit — SUPERSEDE by apt `depends` | superseded-by-our-own-engine table |
| 4 | `jtdx` | Carry as-is, no deprecation on vibes | full CARRY |
| 5 | `wine` | Out of the 1.0 core; VARA's configured prefix returns post-1.0 as a dependency | RETIRE with reason |
| 6 | FT8-family default | `wsjtx` | recorded in the wsjtx manifest's docs |
| 7 | `rf_exposure_calc` + `solar_data` | Retire the bookmarks; URLs live once as prose | `docs/guides/propagation.md` |
| 8 | `country_files` (cty.dat) | Post-1.0 — the first data-asset-with-cadence deserves a schema shape | CARRY, outstanding with reason |
| 9 | `xwefax` vs fldigi | Carry both; no supersede on a spec comparison | full CARRY (manifest already confirmed) |
| 10 | `FoxTelem` | Post-1.0 pending an AMSAT constellation census | CARRY, outstanding with reason |
| 11 | `M0IAX` | Not carried; post-1.0 candidate on first demand | RETIRE with reason |
| 12 | `PATMENU3` | `pat http` ships the interface the wrapper fronts | RETIRE; packet profile documents the web UI |
| 13 | `REPEAT` | Out of 1.0 scope, not out of favour; post-1.0 on demand | RETIRE with reason |
| 14 | `supersdr` (bookkeeping) | Q-007's Friday resolution reflected in the index | ADD, confirmed 3-for-3 |
