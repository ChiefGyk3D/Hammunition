# Scope — The Five-Source Union

Hammunition's target coverage is the union of what these five projects serve:

| Source | Domain | Approx. size | Cost to absorb |
|---|---|---|---|
| Debian Hamradio Blend | Ham, packaged | ~152 packages | **Lowest** — apt metapackages, machine-readable task lists |
| Andy's Ham Radio Linux | Ham, curated | 95 units | **Medium** — 57 non-apt, but inventoried |
| 73Linux | Winlink / packet / EMCOMM | 47 apps (~15 delta) | **Low-medium** — mostly apt or .deb |
| Skywave Linux | Remote SDR, listening | 60 apps, **9 delta** (measured) | **Low** — heavy overlap, few unique |
| DragonOS | SDR / SIGINT | 200+ | **Highest** — mostly source-built GNU Radio OOT modules |

**Union of coverage, not union of packages.** Where several sources ship
different tools for the same job, we pick a recommended default, carry viable
alternatives, and document the trade-off. Merging five inventories without
curation produces four ADS-B decoders and no opinion about any of them — the
opposite of what this project is for.

---

## What we take from each

### Debian Hamradio Blend — take wholesale
Team-governed, signed, machine-readable task lists. The cheapest coverage in the
entire landscape and the best provenance.

**Take:** the full task structure — antenna, datamodes, digitalvoice, logging,
morse, packetmodes, rigcontrol, satellite, sdr, tools, training, nonamateur.

**Note:** the Blend installs packages and nothing else. No configuration layer,
no status honesty, no non-Debian software. Our value over it is everything that
happens after `apt install`.

**Two measured qualifications, both settled by D-019.** The Blend uses
`Recommends` for 155 of 160 entries and `Depends` for none, so task membership
means *"belongs to this category"*, never *"install by default"* — importing it
as an install list would make every profile maximal. And **8 of its 152 packages
do not install on Debian 13**, including `qlog`, which `overlaps.md` picks as the
recommended logging default. Cheapest coverage in the landscape, yes — at 94% on
a stable base, not 100%.

**Do first.** It's the highest coverage-per-effort in the project.

### AHRL — the parity target
Already inventoried and dispositioned. See `PARITY-POLICY.md` and
`docs/reference/dispositions.md`. Its curation — which packages need which
compiler flags, what's quietly dead — is knowledge that can't be derived from a
package search.

### 73Linux — the packet/Winlink delta
PAT, AX.25, BPQ, ARDOP, QtTermTCP, QtSoundModem, the APRS client, Direwolf with
real configuration. AHRL has none of it and a large share of the EMCOMM audience
needs it.

Deferred post-1.0: VARA (Wine prefix, closed-source freeware), HAMRS (AppImage,
scrapes its own download URL).

### Skywave Linux — the listening delta
**Measured** — `docs/reference/skywave-inventory.md`, release 5.10.0. Of 60
featured applications, **9 are delta**, 29 overlap another source, and 22 are
the desktop the live ISO boots into.

The delta is the **utility-decoder cluster** — ACARS, HFDL, VDL2, and the
libraries and calibration tools they need — plus SuperSDR and Reticulum MeshChat.
Every one is absent from Debian, stable *and* unstable, so this is a real gap in
the distribution rather than release lag.

Cheap to absorb, high user value, and it makes Hammunition useful to someone
who doesn't own an SDR yet — a real on-ramp.

**Three corrections to the earlier description of this delta,** all in the
inventory:

- **Most of the "remote SDR clients" are not client software.** KiwiSDR, WebSDR,
  Web-888, PhantomSDR and OpenWebRX are receivers and server stacks you connect
  *to*. Skywave ships exactly one dedicated client, **SuperSDR**; everything else
  is a browser plus AB9IL's site-directory tooling. The real asset for a
  hardware-less user is the **receiver directory**, which is data, not a package.
- **AIS is not in the 5.10.0 release** and is already ours: `rtl-ais` is in
  Debian 13 and `ais-catcher` has a manifest. It belongs on our ADD list.
- **SuperSDR has no licence** — no `LICENSE`, no header, default copyright, and
  the other KiwiSDR clients are no better. See **Q-007**.

Skywave deliberately *dropped* the GNU Radio-heavy stack to stay lean and
*excludes* the SDRplay API as closed-source. Both are confirmed from its own
release notes. Respect the second: the SDRplay artifact sits behind an
interactive download gate, so it cannot be checksummed in advance and cannot
meet our security requirement. The first does not transfer — DragonOS Tier 3
*is* GNU Radio, and our `sdr` profile carries gqrx.

### DragonOS — the SIGINT delta, tiered
The largest and most expensive. Absorb in three tiers, and do not treat them as
one job.

**Tier 1 — apt-installable, or an upstream `.deb` that resolves on the
target.** The qualifier is not pedantry: three of the four `.deb` artifacts
tested do **not** resolve on our targets from the URL upstream advertises
(`docs/reference/install-verification.md`). A tier meant to be cheap and stable
cannot admit artifacts that fail to install. **Measured** —
`docs/reference/dragonos-tier1-inventory.md`, release Resolute R1, probed in all
four x86 target containers. Of 99 README units, **24 are Tier 1**: Wireshark,
aircrack-ng, hcxdumptool/hcxtools, Ubertooth, rtl_433, inspectrum, GNU Radio,
SoapySDR, UHD, gpsd/ffmpeg/sox, the ham decoders we already carry, and four that
arrive as an upstream `.deb` — SDRangel, SDR++, SatDump and AIS-Catcher.
**This is the 1.0 RF-security profile.**

The earlier list above needed correcting on four of five names:

- **Kismet** is not in the Resolute R1 README at all — it is in the older FocalX
  one. It belongs in the profile on its own merits (apt on Kali and Parrot, with
  drone-detection capture drivers on Kali; an official signed apt repo elsewhere)
  and should stop being cited as a DragonOS inheritance.
- **dumphfdl and DumpVDL2** are in no target's apt and in neither Debian stable
  nor unstable. They are Tier 2.
- **AIS-Catcher** is Tier 1 by upstream `.deb`, not by apt.
- **readsb** survives as written, and stays our ADS-B default per `overlaps.md`.

**Cellular / EW is 20 of the 99 units and is not folded into this.** The line is
*transmit*, not topic: a passive decoder and a rogue base station are different
kinds of thing. See **Q-008**, which is open and blocks the profile's contents.

**Tier 2 — maintained upstream binaries or straightforward builds.** SDR++,
SDRangel, SatDump, SigDigger, SDRTrunk, DSD-FME, qFlipper, Universal Radio
Hacker, KrakenSDR DoA, DF-Aggregator, Iridium-Toolkit, JAERO. Version-pinned and
verified — several of these AHRL ships as unpinned master snapshots, which we
fix on the way through.

**Tier 3 — GNU Radio out-of-tree modules.** gr-gsm, gr-iridium, gr-lora_sdr,
gr-satellites, gr-air-modes, gr-dect2, gr-nrsc5, gr-tempest, gr-smart_meters,
and the rest. **This is where the maintenance burden lives.** Each is pinned to
a GNU Radio API version, and GNU Radio's release train breaks them routinely.

**Two measured findings soften this, without moving the gate.** First, all four
of our x86 targets ship the **same** GNU Radio — `3.10.12.0`, differing only in
Debian revision — and it is the same upstream version DragonOS built its modules
against. We are not chasing four APIs. (`libvolk` does differ: 3.2 on the
Debian-13-derived targets, 3.3 on the newer ones.)

Second, the claim that **gr-gsm's upstream has stalled entirely for GR 3.10 no
longer holds as a practical matter.** Debian ships `gr-gsm 1.0.0~20220727-1+b18`,
maintained by the Debian Hamradio Maintainers against
`git.osmocom.org/gr-gsm`, and it is present in Debian 13, Kali and Parrot —
though **not** Ubuntu 26.04. Upstream development did move off GitHub; the
packaging did not stop. It installs today from apt on three of four targets,
which is a different situation from the one this paragraph originally described.

**Tier 3 policy:** carry only modules with a maintained upstream or a maintained
fork, mark the whole tier `experimental`, and record the GNU Radio version each
was built against as catalog data. Where nothing maintained exists, document the
gap and do not carry a fork we can't sustain. Being honest that a module is dead
is worth more than shipping one that breaks on the next GR release.

**Do not attempt Tier 3 before the source backend and pin database are solid.**

---

## Consequences

### Profiles become the product
At 400–600 packages nobody installs everything, and DragonOS-scale installs are
exactly what users complain about. Profile design *is* the user experience, and
it needs its own attention — not a byproduct of the catalog.

**Sized and named** in `docs/reference/profile-sizing.md`, now that all five
sources are measured. No profile exceeds the 80-package threshold. Two names are
**proposed and awaiting the maintainer**, because names are user-facing and
effectively permanent:

- **`station`** rather than `ham-core`, split four ways into `station` (26),
  `logging` (14), `morse` (15) and `propagation` (18). `core` is a packaging
  word, not an operator word.
- **`rf-security`** rather than `sigint`, matching `docs/rf-security/` and the
  security requirement in CLAUDE.md, which already use that phrase.

Proposed set: `station`, `logging`, `morse`, `propagation`, `digital-modes`,
`packet`, `satellite`, `antenna`, `sdr`, `listening`, `electronics`,
`rf-security`, plus `mesh` and `uconsole` post-1.0. A `cellular` profile is named
but deliberately undefined pending **Q-008**. Flat tags with overlap, per
**D-003**.

Profile resolution also consults **detected hardware** (**D-020**): 12 of the
Blend's 39 `sdr` packages are per-device SoapySDR backends, and a one-dongle
operator needs one of them.

### The pin/hash database is a named sub-project
Five sources, hundreds of non-apt artifacts, and not one of them publishes
checksums we can inherit. AHRL ships zero across 63 archives; 73Linux scrapes
directory listings; DragonOS builds from `/usr/src` with no pinning. Sourcing and
verifying every artifact is ongoing work and arguably our most valuable output.

### Overlap resolution needs a policy
Where sources disagree, the catalog needs a recommended default and a documented
reason. Known collisions to resolve: ADS-B (dump1090 / dump1090-fa / readsb /
Virtual Radar Server), logging (cqrlog / xlog / QLog / HAMRS), SDR receivers
(gqrx / SDR++ / SDRangel / CubicSDR / quisk), APRS (Xastir / YAAC / the 73Linux
client), and satellite imaging (SatDump / the retired APT decoders).

---

## Staging

Ordered by coverage-per-effort, not by source.

1. **Debian Blend** — cheapest coverage, best provenance, establishes the schema
   against real data
2. **AHRL parity** — per `PARITY-POLICY.md`, with honest status
3. **73Linux packet core** — closes the Winlink gap
4. **Skywave listening delta** — cheap, and an on-ramp for users without hardware
5. **DragonOS Tier 1** — the 1.0 SIGINT profile
6. **DragonOS Tier 2** — post-1.0
7. **DragonOS Tier 3** — post-1.0, experimental, only where upstream is alive

**1.0 = stages 1 through 5.** That is already more coverage than any single
existing project, and it is achievable. Stages 6 and 7 are where "one stop shop"
becomes literally true, and they should not hold up a release.
