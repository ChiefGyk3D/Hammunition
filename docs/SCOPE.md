# Scope — The Five-Source Union

Hammunition's target coverage is the union of what these five projects serve:

| Source | Domain | Approx. size | Cost to absorb |
|---|---|---|---|
| Debian Hamradio Blend | Ham, packaged | ~152 packages | **Lowest** — apt metapackages, machine-readable task lists |
| Andy's Ham Radio Linux | Ham, curated | 95 units | **Medium** — 57 non-apt, but inventoried |
| 73Linux | Winlink / packet / EMCOMM | 47 apps (~15 delta) | **Low-medium** — mostly apt or .deb |
| Skywave Linux | Remote SDR, listening | ~30 apps (small delta) | **Low** — heavy overlap, few unique |
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
Small and mostly overlapping, but its unique cluster is genuinely unserved
elsewhere: **remote SDR clients** (KiwiSDR, WebSDR, Web-888, PhantomSDR,
OpenWebRX), utility decoders (ACARS, HFDL, VDL2, AIS), and Reticulum/MeshChat.

Cheap to absorb, high user value, and it makes Hammunition useful to someone
who doesn't own an SDR yet — a real on-ramp.

Note Skywave deliberately *dropped* the GNU Radio-heavy stack to stay lean, and
excludes the SDRplay API as closed-source. Both are decisions worth respecting
rather than reversing by default.

### DragonOS — the SIGINT delta, tiered
The largest and most expensive. Absorb in three tiers, and do not treat them as
one job.

**Tier 1 — apt-installable or upstream .deb.** Kismet, Wireshark, Aircrack-ng,
rtl_433, readsb, AIS-Catcher, dumphfdl, DumpVDL2, gpredict, inspectrum, and the
SoapySDR family. Cheap, stable, high value. **This is the 1.0 SIGINT profile.**

**Tier 2 — maintained upstream binaries or straightforward builds.** SDR++,
SDRangel, SatDump, SigDigger, SDRTrunk, DSD-FME, qFlipper, Universal Radio
Hacker, KrakenSDR DoA, DF-Aggregator, Iridium-Toolkit, JAERO. Version-pinned and
verified — several of these AHRL ships as unpinned master snapshots, which we
fix on the way through.

**Tier 3 — GNU Radio out-of-tree modules.** gr-gsm, gr-iridium, gr-lora_sdr,
gr-satellites, gr-air-modes, gr-dect2, gr-nrsc5, gr-tempest, gr-smart_meters,
and the rest. **This is where the maintenance burden lives.** Each is pinned to
a GNU Radio API version, and GNU Radio's release train breaks them routinely —
gr-gsm's upstream has stalled entirely for GR 3.10.

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

Minimum viable profile set: `ham-core`, `digital-modes`, `packet`, `satellite`,
`antenna`, `sdr`, `sigint`, `mesh`, `listening`, `electronics`, `uconsole`.
Flat tags with overlap, per D-003.

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
