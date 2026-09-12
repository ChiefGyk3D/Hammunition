# Scope — The Six-Source Union

Hammunition's target coverage is the union of what these six projects serve
(five when **D-017** was recorded; EmComm Tools OS Community was added by
**D-042** on 2026-09-06):

| Source | Domain | Approx. size | Cost to absorb |
|---|---|---|---|
| Debian Hamradio Blend | Ham, packaged | ~152 packages | **Lowest** — apt metapackages, machine-readable task lists |
| Andy's Ham Radio Linux | Ham, curated | 95 units | **Medium** — 57 non-apt, but inventoried |
| 73Linux | Winlink / packet / EMCOMM | 47 apps, **28 delta, 13 surviving** (measured) | **Low-medium** — mostly apt or .deb |
| Skywave Linux | Remote SDR, listening | 60 apps, **9 delta** (measured) | **Low** — heavy overlap, few unique |
| DragonOS | SDR / SIGINT | 200+ | **Highest** — mostly source-built GNU Radio OOT modules |
| EmComm Tools OS Community | EMCOMM, rig plug-and-play, offline data | 62 units, **11 delta** (measured) | **Low** for the software; the rig model and offline data are design work, not packages |

**Union of coverage, not union of packages.** Where several sources ship
different tools for the same job, we pick a recommended default, carry viable
alternatives, and document the trade-off. Merging six inventories without
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
`docs/reference/dragonos-tier1-inventory.md`, release Resolute R1, probed in the
four x86 target containers then in CI (Mint was restored as a fifth on
2026-08-28 and is not re-probed here — being Ubuntu-noble-based, it tracks the
Ubuntu result). Of 99 README units, **24 are Tier 1**: Wireshark,
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
`git.osmocom.org/gr-gsm`, and it is present in Debian 13, Kali, Parrot and
Mint 22.3 — though **not** Ubuntu 26.04, where it was dropped from a newer
universe (Mint 22.3 rides Ubuntu's older noble universe, which still carries
it). Upstream development did move off GitHub; the packaging did not stop. It
installs today from apt on four of the five x86 targets (measured 2026-08-28),
which is a different situation from the one this paragraph originally described.

**Tier 3 policy:** carry only modules with a maintained upstream or a maintained
fork, mark the whole tier `experimental`, and record the GNU Radio version each
was built against as catalog data. Where nothing maintained exists, document the
gap and do not carry a fork we can't sustain. Being honest that a module is dead
is worth more than shipping one that breaks on the next GR release.

**Do not attempt Tier 3 before the source backend and pin database are solid.**

### EmComm Tools OS Community — the rig model and the offline layer
**Measured** — `docs/reference/etc-inventory.md`, release 2026.04.01.R6, added
as the sixth source by **D-042**. Of 62 units, **11 are delta**, 21 overlap a
manifest the catalog already carries, 9 are ETC's own integration layer, 4 are
offline data, and 17 are the Ubuntu 22.10 image it builds — a release that
reached end of life on 2023-07-20 and is installed from
`old-releases.ubuntu.com`.

The software delta is small and cheap: the **offline cyberdeck** — Navit and
`maptool`, kiwix and the zim tools, `dict`/`dictd`, QGIS, mbtileserver — plus
two packet clients (Paracon, Chattervox), Artemis, and the AmRRON signed-traffic
pair (GPA, Paranoia Text Encryption). Most of it is apt. Each unit is
dispositioned on its own in `dispositions.md`; none is carried as a set.

What ETC contributes that no other source does is not software. It is the
**rig model** — the operator selects a radio, and udev rules, per-radio JSON
and forty wrappers configure every application for it — and the **offline-data
layer** of maps, Wikipedia and reference documents. Both are studied and
reimplemented as catalog data, and none of ETC's code is taken, for the reason
D-042 gives: the code is the intertwined shell architecture this project
replaces, and its `/dev/et-cat` role symlinks are the D-028 trap with an
operator-selection escape that works for one radio at a time. Five sub-projects,
one pull request each, are listed under D-042. **The software delta is stage 6
of 1.0**, after the five above; the rig model and the offline layer are approved
work in D-042's order and are not 1.0 gates unless the maintainer stages them.

**Two things ETC does that the security requirements refuse.** Thirty-four of
its units download from the network and none verifies a checksum, although its
own helper accepts one; and seven fetch at `latest`, `master` or `nightly`.
Everything that arrives from this source arrives pinned and verified, as from
any other.

---

## Consequences

### Profiles become the product
At 400–600 packages nobody installs everything, and DragonOS-scale installs are
exactly what users complain about. Profile design *is* the user experience, and
it needs its own attention — not a byproduct of the catalog.

**Sized and named** in `docs/reference/profile-sizing.md`, now that the five
sources of D-017 are measured (ETC's delta, added by D-042, is not yet sized
into a profile). No profile exceeds the 80-package threshold. Two names are
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
directory listings; DragonOS builds from `/usr/src` with no pinning. **One
exception, found 2026-08-26:** EFF's Rayhunter publishes a `.sha256` beside
every release asset, verified to match. It is the first upstream in this project
whose hash we can inherit rather than pin ourselves. Sourcing and
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
6. **EmComm Tools OS delta** — the software delta only, mostly apt (**D-042**)
7. **DragonOS Tier 2** — post-1.0
8. **DragonOS Tier 3** — post-1.0, experimental, only where upstream is alive
9. **Trunked and digital-voice listening** — post-1.0, receive-only; see below
10. **Repeater and hotspot** — post-1.0, transmit infrastructure; waits on
    station config; see below

**1.0 = stages 1 through 6.** That is already more coverage than any single
existing project, and it is achievable. Stages 7 through 10 are where "one stop
shop" becomes literally true, and they should not hold up a release.

---

## Post-1.0 tracks — trunking, digital voice, repeaters

Two tracks the six sources touch only at the edges, written down on
2026-09-07 so that "does Hammunition do DMR, trunking, repeaters?" has an
answer in the record rather than in a chat log. Neither is 1.0. Their ordering
and the calls in each were **Q-020**, decided as **D-046** (2026-09-12):
Track A first, then B, with SvxLink's config block taken the day station
config exists.

**What the catalog already has**, so the tracks are measured against it and
not against a blank page: DMR *radio programming* is covered by `qdmr` and
`dmrconfig` (category `dmr`); DMR, D-STAR, P25 and NXDN *decoding* by `dsdcc`
in the `listening` profile; the Blend's `digitalvoice` task is carried whole —
`svxlink-server`, `svxreflector`, `remotetrx`, `svxlink-gpio`,
`svxlink-calibration-tools` and the `qtel` EchoLink client — and the
`digital-modes` profile deliberately includes only `qtel`, because a repeater
controller "is operating infrastructure other people depend on, not a mode you
work, and it wants a considered install." That considered install is track B.
M17 is **D-007**, ours to build, and crosses both tracks.

**Measured 2026-09-07**, `scripts/apt-policy-sweep.sh --all` over the seven
targets of `containers/targets.yaml` (the arm64 row by
`HAMMUNITION_FOREIGN_ARCH=arm64`, which asks the archive index rather than
emulating), seventeen names: OP25, Trunk Recorder, SDRTrunk, DSD, DSD-FME,
`dsdcc`, the seven G4KLX hotspot daemons (`mmdvmhost`, `dmrgateway`,
`ysfgateway`, `p25gateway`, `nxdngateway`, `ircddbgateway`, `dstarrepeater`),
`svxlink-server`, `asl3-asterisk`, `allstarlink` and `asterisk`. **Two of the
seventeen exist in any archive, and both are already in the catalog:**

| Target | `dsdcc` | `svxlink-server` | `asterisk` | The other fourteen |
|---|---|---|---|---|
| Debian 13, Parrot, Debian 13 arm64 | 1.9.3 | 24.02 | — | — |
| Kali rolling | 1.9.6 | 26.05.1 | 22.10.1 | — |
| Ubuntu 26.04 | 1.9.6 | 25.05.1 | 22.5.2 | — |
| Ubuntu 24.04, Linux Mint 22.3 | 1.9.3 | 19.09.2 | 20.6.0 | — |

The archive's `asterisk` is listed for completeness and is not a route:
AllStarLink is Asterisk *with app_rpt*, distributed as its own packages from
its own repository (`docs/reference/prior-art.md`), and it is absent from the
two Debian-13-based targets anyway. Everything else in both tracks is a
source build, a pinned upstream binary, or a third-party archive — the
backends 1.0 already has, under the rules 1.0 already made.

### Track A — trunked and digital-voice listening (stage 9)

Receive-only: P25 and DMR trunked systems, NXDN, D-STAR, YSF, M17, as heard on
an SDR. This is the "does it do trunking" answer and it is the cheaper track,
because nothing in it transmits and nothing in it needs station config.

- **OP25**, the boatbod fork — the live P25 decoder; the Osmocom original is
  dead (`prior-art.md`, head commit 2026-08-23). A CMake build against GNU
  Radio, so it carries the **Tier 3 caveat**: pinned to the GNU Radio the
  targets ship (`3.10.12.0` on all four x86 targets, measured above) and
  re-verified when that moves.
- **Trunk Recorder** (2026-09-01) — records every talkgroup on a trunked
  system; the same CMake-against-GNU-Radio shape and the same caveat.
- **SDRTrunk** — the mature Java decoder. Repo alive (2026-08-01), last release
  v0.6.1 from 2024-12-03; no Debian packaging, so it is a **binary backend**
  unit: a pinned release archive with a hash we record, and whatever runtime
  it needs comes from the archive's own JDK packages, never bundled.
- **DSD-FME** (release 20260715, ISC) — the maintained line of the DSD
  decoder family; a CMake build. `dsdcc` stays. The two overlap, and
  `docs/reference/overlaps.md` has no row for that collision yet — the
  manifest that adds DSD-FME writes one.

Profiles: `listening` for the decoders (SDRTrunk, DSD-FME beside `dsdcc`),
`rf-security` for OP25 and Trunk Recorder — decided, **D-046**; the
SDRTrunk/Trunk Recorder overlap is one `overlaps.md` row, written by the
first manifest of the pair. **No consent gate.**
D-034 drew the line at *transmit, not topic*, and every unit here receives.
What the profile prose owes the operator is the D-021 half: disclose plainly
that these decode public-safety and commercial traffic and that what may be
listened to, recorded, or disclosed is the operator's law to know — never
adjudicated by the engine, never gated by a question.

### Track B — repeater and hotspot (stage 10)

Transmit infrastructure: a repeater controller, an EchoLink or AllStar node, a
DMR/D-STAR/YSF/P25/NXDN/M17 hotspot. Three sub-stacks, each on a different
rule the record already has:

- **SvxLink** — apt on every target (versions above) and in the catalog
  already. What it lacks is not a package but a **station config**: callsign,
  EchoLink credentials, audio and PTT device, in `svxlink.conf`. That is the
  D-004 / **D-035** mechanism `linbpq.yaml` already exercises with
  `config_files`, and it is why this track waits — a missing value defers the
  file, never the transaction, and nothing is invented.
- **AllStarLink ASL3** — Debian 13 based, AGPL-3.0 / GPL-3.0, very active
  (`prior-art.md`), and only from its own apt repository. That is the
  **D-040** gate exactly as `code` and `codium` exercise it: the manifest pins
  the signing-key fingerprint, the archive is added only on the operator
  typing that fingerprint, never on `--yes`, and both files come out on
  uninstall — confirmed as the D-040 case by **D-046**, with no gate beyond
  the fingerprint. It also means ASL3 resolves only where its Debian 13 packages
  install — Debian 13 and Parrot first; the Ubuntu targets are a measurement,
  not an assumption.
- **The G4KLX hotspot suite** — MMDVMHost and the per-mode gateways. In no
  archive, and the upstreams are untagged, which makes them a **D-024**
  question: pin the commit a distribution already packages. The candidate
  distribution is Pi-Star (GPL-2.0, V4.3.7 2026-05-01), which is an image
  rather than an archive; WPSD is image-only and fork-hostile, so it is not a
  pin source. A Pi image's binary set **does** count as "a distribution
  packages it" for D-024 (**D-046**): the manifests pin the commits the
  current Pi-Star release ships, read out of the image by a script that
  records how. The modem side — ZUMspot,
  MMDVM_HS hats, USB MMDVM boards — is a hardware class under **D-026**
  (install the means of talking to the device) and **D-028** (a generic
  CP2102 or CH340 identifier does not get a `/dev/mmdvm` symlink).

**Not carried, with the reason:** OpenRepeater has no LICENSE file
(all-rights-reserved, `prior-art.md`); HamVoIP is dead and its users are
migrating to ASL3; Pi-Star and WPSD are *images*, and an image is the thing
this project augments, not a thing it installs — an operator who wants a
turnkey hotspot on a Pi should run one, and this track does not compete with
them. RepeaterSTART is a post-1.0 candidate by **Q-015**, not part of this
track.

**Consent.** A hotspot on the amateur bands is ordinary licensed operation,
the same thing `flrig` keying a transceiver is, and gets no gate. What the
profile prose owes — again the D-021 half, disclosed and never adjudicated —
is that a repeater is infrastructure others depend on, that frequency
coordination is a matter between the operator and their coordinating body,
and that the licence conditions for an unattended station are the operator's
to know. The profile is opt-in by construction: nothing in it belongs to
`station` or `digital-modes`.

**Ordering.** Track A first, on the numbers: four units, three backends 1.0
already ships, profiles that already exist, and no dependency on station
config. Track B's SvxLink sub-stack is one `config_files` block away once
D-004's station config lands; ASL3 is a D-040 manifest; the G4KLX suite is
last, because it needs the pin decision and hardware nobody here owns yet.
