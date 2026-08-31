<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Decisions pending — the morning list

The twelve Q-015 units still awaiting your call, ordered so the mechanical
ones go first and the ones needing outside knowledge go last. Two are already
resolved (`claws-mail`, `putty`) and not repeated. Each has a recommendation
and its precedent; the intent is that you can answer these one at a time
quickly. **Nothing here was applied autonomously** — every one has at least a
sliver of preference in it, and you asked to take them one at a time.

## Group A — mechanical (bookkeeping, no real trade-off)

| # | Unit | Recommendation | Why it is mechanical |
|---|---|---|---|
| 3 | `libhamlib4` | **Dependency, not a unit** — resolve with no manifest owed. | No menu entry, no operator surface; arrives via `depends`, and `libhamlib-utils` is the operator-facing manifest already carried. |
| 4 | `jtdx` | **Carry as-is**, no deprecation mark. | Already carried, already builds and confirms on every target. The question was only whether to demote it; devoted user base says no. |
| 5 | `wine` | **Confirm out of 1.0 core, post-1.0 for VARA.** | Already effectively resolved — the Morse Runner decision took Wine out of core; VARA reintroduces a Wine prefix post-1.0. Just needs recording. |

## Group B — a preference call (I lean one way, you may differ)

| # | Unit | Recommendation | The other view |
|---|---|---|---|
| 6 | FT8-family default | **`wsjtx`** — mark it the recommended default where wsjtx/wsjtx-improved/jtdx/mshv/js8call overlap. | You might prefer wsjtx-improved for marginal decodes, or decline to pick a default at all. It is metadata on an already-carried unit — purely additive whichever way. |
| 7 | `rf_exposure_calc` + `solar_data` (the browser bookmarks) | **Retire, move URLs to guide prose.** A bookmark to a dead site is worse than none. | Your mail/serial rulings suggest you might prefer an *offer* pattern here too — a "propagation links" suggestion group, or a small launcher set. Your call whether bookmarks are worth any mechanism at all. |
| 8 | `country_files` (cty.dat) | **Post-1.0, as the data-asset design question.** Apps bundle their own; document manual updates meanwhile. | Could be pulled into 1.0 as the first "data asset with an update cadence" if you want that schema shape now rather than later. |

## Group C — needs knowledge I do not have

| # | Unit | Recommendation | What it actually needs |
|---|---|---|---|
| 9 | `xwefax` vs fldigi | **Carry both, no supersede.** | A radiofax operator's judgment on whether fldigi's built-in WEFAX truly replaces the dedicated tool. Dropping it on a spec comparison is the inherited-verdict mistake. |
| 10 | `FoxTelem` | **Stage post-1.0 pending an AMSAT status check.** | Whether enough of the AMSAT Fox constellation is alive to justify carrying its decoder. A census, not a guess. |
| 11 | `M0IAX` (JS8 utilities) | **Post-1.0 candidate.** | Whether the JS8 profile wants them — no measured demand yet. |
| 12 | `PATMENU3` | **PAT's own web UI suffices** — do not clone KM4ACK's licence-blocked wrapper. | Confirmation you are content with PAT's native UI over a clean-room menu reimplementation. |
| 13 | `REPEAT` (RepeaterSTART) | **Post-1.0 candidate.** | Whether a repeater-directory app is in 1.0 scope; nothing in the union's rationale needs it. |

## How to answer

Tell me the number and your call (or "recommendation" to take mine). I apply
it, update `dispositions.md`, `QUESTIONS.md` and the parity ledger, regenerate
the affected docs, and — where it adds a manifest or changes behaviour —
verify on a VM before moving to the next. Group A can go in one breath if you
just say "A: recommendations."
