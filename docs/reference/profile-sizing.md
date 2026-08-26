# Profile sizing across the five-source union

`SCOPE.md`: *"At 400–600 packages nobody installs everything… Profile design **is**
the user experience."* This sizes the proposed profiles before they are built, to
find the ones that will be unusable.

**Threshold:** anything over **~80 packages** is flagged as needing a split.

**Estimates, not counts.** Three of the five sources are not yet inventoried
(Skywave, DragonOS, and the Blend↔AHRL de-duplication is name-based). Every
figure below states its basis, and unmeasured inputs are marked. Profiles are
**flat tags with overlap** per **D-003**, so the same package appears in several
profiles and the totals deliberately exceed the union size.

---

## Measured inputs

| Source | Basis | Units |
|---|---|---|
| Debian Blend | **measured** — `blend-inventory.md`, 12 tasks | **152** unique packages |
| AHRL | **measured** — `dispositions.md`, CARRY + SUPERSEDE + REVIVE | **79** of 105 survive |
| 73Linux delta | **measured** — `dispositions.md`, CARRY + ADD | **13** of 28 survive |
| Skywave delta | *estimated* — `SCOPE.md` says ~30 apps, "small delta" | **~10–15** unique |
| DragonOS Tier 1 | *estimated* — the named list in `SCOPE.md` | **~12–15** |

**Union upper bound: ~265 units** before de-duplication; realistically **~200–230**
once the Blend/AHRL overlap is resolved (20 exact-name matches plus 11 packaged
source builds already identified in `blend-inventory.md`).

That is comfortably below `SCOPE.md`'s 400–600 estimate, because that figure
included DragonOS Tiers 2 and 3, which are post-1.0.

---

## Sizing per proposed profile

Blend task mappings are exact. AHRL and delta contributions are attributed by
menu category and disposition.

| Profile | Blend tasks (measured) | + AHRL | + delta | **Estimate** | Verdict |
|---|---|---:|---:|---:|---|
| `ham-core` | logging 10, rigcontrol 12, morse 11, tools 8, training 7 | ~22 | 0 | **~62** | ⚠️ near threshold |
| `digital-modes` | datamodes 15, digitalvoice 7 | ~20 | 2 | **~40** | ✅ |
| `packet` | packetmodes 19 | ~4 | 8 | **~30** | ✅ |
| `sdr` | sdr 39 | ~6 | 0 | **~45** | ✅ |
| `satellite` | satellite 3 | ~3 | 0 | **~8** | ✅ small |
| `antenna` | antenna 7 | ~8 | 0 | **~15** | ✅ |
| `listening` | nonamateur 22 | ~2 | 0 | **~35** | ✅ |
| `electronics` | — | 4 | 0 | **~6** | ✅ opt-in |
| `sigint` | — | 0 | 0 | **~13** | ✅ Tier 1 only |
| `mesh` | — | 0 | 0 | **~8** | ✅ post-1.0 |
| `uconsole` | — | 0 | 0 | **~5** | ✅ hardware |

**No profile exceeds 80.** One warrants attention.

---

## ⚠️ `ham-core` at ~62 — the one to watch

It is the only profile near the threshold, and it is the **worst** one to get
wrong: it is what a new user installs first, and first impressions of this
project will be formed by how long it takes and how much of it they wanted.

It is large because it absorbs five Blend tasks at once — `logging`,
`rigcontrol`, `morse`, `tools`, `training` — plus AHRL's HF_Propagation and
Documentation clusters.

**Recommendation: split it, before it crosses the threshold rather than after.**

| Proposed | Contents | Est. | Rationale |
|---|---|---:|---|
| `ham-core` | rigcontrol, tools, cty.dat, hamlib, one logger, one clock | **~25** | What *every* station needs regardless of mode |
| `logging` | The full 9-package Blend logging task plus AHRL's loggers | ~14 | Most operators want one logger, not nine |
| `morse` | morse + training tasks (they overlap by 4 already) | ~15 | Self-contained interest; nobody needs it to make a digital contact |
| `propagation` | HF_Propagation cluster — clocks, cluster, grid tools | ~12 | Genuinely optional and heavy on web-service dependencies |

`ham-core` at ~25 installs fast, contains no surprises, and every one of the
four splits is a coherent thing an operator can name. That is the test a profile
should pass.

**This is a recommendation, not a decision.** Profile names are user-facing and
hard to change later.

---

## Notes that affect sizing

**The Blend's `sdr` task is 39 packages, of which 13 are `soapysdr-module-*`.**
Those are per-hardware backends — airspy, bladerf, hackrf, lms7, mirisdr,
osmosdr, redpitaya, remote, rfspace, rtlsdr, uhd, audio — and installing all
thirteen for a user with one dongle is exactly the DragonOS complaint
`SCOPE.md` names. **Recommend** installing `soapysdr-tools` plus the modules
matching detected hardware, and treating the rest as available-not-installed.
That single decision removes ~11 packages from the common case and is the
clearest argument in the whole exercise for hardware detection driving profile
resolution.

**The Blend uses `Recommends` for 155 of 160 entries.** Its metapackages are
opt-out; our profiles are opt-in. Importing task membership directly would make
every profile maximal. Task membership should be read as *"belongs to this
category"*, not *"install this by default"*.

**`nonamateur` (22) does not map cleanly.** It mixes ADS-B, DAB, GNSS and
utility decoding — closer to our `listening` profile than to anything amateur.
It also contains `dump1090-mutability`, which the ADS-B recommendation in
`overlaps.md` supersedes.

**Overlap is expected and correct.** `splat` is in both `antenna` and `tools`;
`cw`, `cwcp`, `xcwcp`, `aldo` and `morse` are in both `morse` and `training`.
Per D-003 that is a tag appearing twice, not a modelling error.

---

## What would change these numbers

1. **Skywave inventory** — not yet extracted. `SCOPE.md` estimates a small unique
   delta (remote SDR clients, utility decoders, Reticulum). Would mostly land in
   `listening`, which has room.
2. **DragonOS Tier 1 inventory** — not yet extracted; `sigint` is sized from
   `SCOPE.md`'s named list alone. Tiers 2 and 3 are post-1.0 and would push
   `sigint` well past 80, so **`sigint` should be assumed to need splitting later**
   even though Tier 1 alone does not.
3. **Blend/AHRL de-duplication** — currently name-based. `gqrx` vs `gqrx-sdr`
   already shows names differ between sources, so the real overlap is larger than
   measured and these estimates are **upper bounds**.
