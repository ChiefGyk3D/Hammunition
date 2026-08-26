# Session log — overnight round 5, 2026-08-26

Queue complete, twice — a second batch arrived mid-round. Twenty commits,
**pushed**; the first push also published round 4, which had been committed but
held back. Everything green.

Previous round's log is in git history at `175869a`.

---

## Headline

**Three of your decisions landed; one of my claims was wrong.** Q-009, Q-010 and
Q-011 are resolved and implemented. Q-010's *decisive argument* was false —
Kali packages a Proxmark client — and the retraction is in the question itself
rather than quietly edited out.

**The project has a licence.** GPL-3.0-or-later engine, CC0-1.0 catalog, split
on the architectural boundary, enforced by tests rather than by convention.

**The `.gitignore` bug class is closed, not patched again.** Every pattern is
now anchored or justified by name, and the audit is verified against both
historical bugs.

**The catalog was internally inconsistent and nothing noticed.** Two profiles
named nine packages with no manifests.

---

## What completed

### 1. Hardware gap dispositions — `1a6165a`

Every `identification_gap` in the device catalog ended in some variant of "run
lsusb and record it". For LimeSDR and PlutoSDR that told the reader to attach
hardware that does not exist here. `gap_closure` is now required alongside every
gap: `maintainer_hardware`, `unverified_by_maintainer` (your term, chosen over
"pending" because it names *why* the gap is open), or `not_applicable`.

Proxmark3 is scoped to the original design — not RDV4 or RDV5 — because that is
the board available to test against. Gap left open, nothing guessed.

New generated `docs/reference/hardware-gaps.md` answers what the per-file prose
could not: **when does any of this block anything.** Today, none of it. The udev
generator that would consume an identifier is M4 and is not written.

### 2. The `.gitignore` audit — `c4c6552`

You asked for one pass over every pattern rather than a fourth point patch.
`scripts/audit_gitignore.py` does two checks, because the failures have two
shapes: nothing in the source tree may be ignored (catches a collision when the
directory appears), and every pattern is anchored or listed by name with why it
must match at any depth (catches it *before* the directory exists — the only
check that would have prevented all three rather than detected them).

Verified by reintroducing both historical bugs. Eleven findings on the first
run; `MANIFEST` was the live hazard and `catalog.cache` was the next instance
waiting to happen.

### 3. Licensing — `b201edf`

Q-009 resolved as you specified. Texts copied from Debian `base-files` rather
than transcribed, checksums recorded. `why-hammunition.md` answers it in the
same document that raises the criticism against 73Linux and SuperSDR.

### 4. `workstation` — `23cc52b`

Nine packages, contents fixed at acceptance, exclusion list written into
`deliberately_excludes` — a required schema field — so it travels with the
profile rather than living in a review comment.

### 5. Catalog consistency — `b9bc183`

Nine manifests written for packages the profiles already referenced.

### 6. `rfid` — `e1cd469`

Six packages. Ungated, which is the closest call in the catalog and is argued
rather than assumed.

### 7. SatDump and SDR++ — `da0e418`; the capture helper — `d284a31`

### 8. D-024, reviewed commit pins — `ae688e9`

Q-013 answered as general policy rather than one manifest. A tag carries an
upstream signal that a revision was worth naming; a SHA carries none, so pinning
one moves a judgement upstream stopped making onto us. `pin_review` records it;
the schema rejects a SHA without one and a tag with one.

Staleness is checked weekly on a schedule, never on push — failing an unrelated
pull request because a date rolled over is how a check teaches people to ignore
it.

**The implementation beat the recommendation.** The pin is not master HEAD: Kali
and Parrot both package SDR++ at commit `36ea9a1`, so pinning theirs means a
source build and an apt install are the same revision. Someone else's packaging
is the review signal upstream stopped providing.

### 9. D-025, re-verify when a claim becomes decisive — `ae688e9`

Your rule, and the fourth instance is what earned it. Gathering standards and
decision standards are different bars.

### 10. D-026, tooling is not capability — `4860c84`

Plus the ESP32 Marauder in the `badgelife` class, with no version recorded
because the revision is unconfirmed and the revision determines the bridge chip.

### 11–14. Hardware inventory, community catalogue, 21 manifests, README

`517f4f8`, `be893fc`, `bc40212`, `f35feb5`.

### 15. Copyright holder, and no CLA — `85b003f`

Q-012 closed as `Copyright (C) 2026 Renegade Penguin LLC` across 115 files.
**My option list had missed the answer**: I framed it as handle-versus-
abstraction and treated an entity as hypothetical. An LLC is a legal person and
can enforce a licence; a handle cannot.

Deliberately *not* applied to `LICENSE` or `catalog/LICENSE` — verbatim texts
whose checksums are asserted, and a copyright line inserted into a licence
corrupts it. A test now says that in those words.

`CONTRIBUTING.md` exists mainly to state what the company name does **not**
mean: no CLA, no assignment, contributors keep copyright. A company name in
every header invites the opposite assumption, and that inference would cost
exactly the drive-by contributions the project most wants.

### 16. D-027 — two axes for hardware claims — `acff5bb`

`status: supported` and `maintainer_verified` are separate fields.
**6 of 21 devices claim supported; 0 have been run here**, and that number is
printed at the top of the gap report rather than smoothed away.

### 17. D-024 — pin what a distribution packages — `a102cf8`

Made structural: `basis` is `distribution_pin` (must name them) or `own_choice`
(must name none, and needs a fuller rationale saying what was checked). "Looked
recent" can no longer be expressed as a basis at all.

### 18. The udev sweep — `0a6574f`

The round's largest result. Every package in Debian 13 that ships a udev rule —
280 of them, no shortlist — downloaded, unpacked and read. **1,947 distinct USB
identifiers; we carried 77.**

Two gaps closed without owning hardware: **LimeSDR** (Debian's `limesuite-udev`
names the board) and **Flipper Zero** (Debian packages `qflipper`).

And the hazard, which is the same failure pointed the other way: `0483:df11`
appears in *both* `qflipper`'s rule and `dmrconfig`'s, where it is a TYT
MD-UV380. Generic bridge identifiers over-match as silently as omission
under-matches. A sweep produces candidates, not answers.

---

## What I got wrong

**Q-010's decisive argument.** It said "No target packages a Proxmark client at
all." Kali ships `proxmark3 4.21611-0kali1`. The claim came from a narrower probe
and was never re-checked before it became load-bearing. Repo-wide sweep found
two hits; the generated one was fixed in its generator, never by hand. The answer
survives — the client is absent on three of four targets including the primary
one — but the argument as stated was false.

**The `codium` manifest failed D-022 on the first run.** The tests caught it, not
my reading of them. It adds a third-party repository on three of four targets
while being the distribution's own choice on the fourth, and
`recommended_default` is per-manifest while the behaviour is per-target. That
tension is now recorded in the manifest; it will recur.

---

## What needs you

**Q-012 🟢 — copyright holder string.** A default is in place: `The Hammunition
contributors`. One sed if you want otherwise.

**The ESP32 Marauder revision**, from the silkscreen, before anything records
one. Also which bridge chip it carries — `identify-device.sh c5-wardriver`
answers both.

**Four gaps on your bench.** `scripts/identify-device.sh <name>` — read-only, no
root, emits a paste-ready block with the evidence field filled in:

```
scripts/identify-device.sh catsniffer-v3
scripts/identify-device.sh minino
scripts/identify-device.sh free-wili-2
scripts/identify-device.sh clip-boy
scripts/identify-device.sh c5-wardriver
```

The last one closes the Espressif `303a` vendor ID for the whole `badgelife`
class, so it is worth more than the one device.

**A note on what changed in the catalog's shape.** The most productive hour of
this round was not writing manifests — it was reading Debian's own udev rules.
`rtl-sdr` went from 3 identifiers to 42, the `nfc-reader` class was built from
`93-pn53x.rules`, and the `usrp` entry from `60-uhd-host.rules`. None of that
needed hardware. A distribution's rules are a primary source about devices
nobody here owns, and we had barely been reading them.

---

## What I could not do

**No hardware was attached to anything.** Still true, and now the limiting
factor on six device entries rather than a general caveat.

**Configuration is still untested for anything pulling dbus or systemd.** The
local harness runs degraded — no `/etc/subuid` ranges. One root command fixes it:

```
sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 chiefgyk3d
podman system migrate
```

**Nothing was installed outside a container, and nothing was pushed.**

**Ubuntu 26.04, Mint and Raspberry Pi OS were not probed this round.** The new
availability measurements cover Debian 13, Kali rolling and Parrot. Manifests
claim only what was measured.
