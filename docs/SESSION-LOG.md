# Session log — overnight round 5, 2026-08-26

Queue complete. Seven commits, none pushed. Everything green.

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

**Q-013 🟡 — SDR++.** Neither branch of your instruction fits. Upstream *does*
tag, and the newest tag is from **2021-10-18**, 541+ commits behind a master that
moved in July 2026. Recommendation: apt where packaged, SHA-pinned source build
elsewhere. Explicitly not the nightly `.deb`.

**Q-012 🟢 — copyright holder string.** A default is in place.

**Four gaps on your bench.** `scripts/identify-device.sh <name>` — read-only, no
root, emits a paste-ready block with the evidence field filled in:

```
scripts/identify-device.sh catsniffer-v3
scripts/identify-device.sh minino
scripts/identify-device.sh free-wili-2
scripts/identify-device.sh clip-boy
```

The last one closes the Espressif `303a` vendor ID for the whole `badgelife`
class, so it is worth more than the one device.

**Which CallMeKoko boards you have.** They are ESP32, so the badgelife class
almost certainly already covers them, but I will not write device entries for
products I cannot name.

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
