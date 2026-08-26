# Overlap resolution — recommended defaults

`SCOPE.md`: *"Merging five inventories without curation produces four ADS-B
decoders and no opinion about any of them — the opposite of what this project is
for."* This is the opinion.

**Recommendations only. Every one of these is the maintainer's to accept or
reject.** Nothing here is written into a manifest.

Per `PARITY-POLICY.md`, a recommended default **never removes working software**.
Alternatives stay in the catalog with the trade-off documented; the default is
what an operator gets when they install a profile and express no preference.

**Availability was checked** against `sources.debian.org` and the Blend task
files, so the cost of each recommendation is known rather than assumed.

---

## 1. ADS-B and aircraft tracking

| Candidate | Source | Availability |
|---|---|---|
| `dump1090` (FlightAware) | AHRL — source build from a `master` zip | **not in Debian** |
| `dump1090-mutability` | Debian Blend (`nonamateur`) | in Debian |
| `readsb` | — | **in Debian** |
| Virtual Radar Server | AHRL — Mono + `.exe` | not in Debian |
| `tar1090` (web UI) | — | **not in Debian** |

### Recommended: `readsb`

> Actively maintained, in Debian, and it supersedes both dump1090 forks at once — AHRL's unpinned `master` snapshot and the Blend's `dump1090-mutability`, which AHRL itself dropped in v27.

**Also carry:** `dump1090-mutability` — it is the Blend's own choice and removing
it would break parity with a team-governed source for no user benefit.

**Recommend RETIRE:** Virtual Radar Server. Mono was handed off by Microsoft in
2024, the AHRL install needs a second tarball purely to patch a runtime error,
and its launcher starts a decoder and `killall -9`s it on exit.

**Flagged cost:** `tar1090`, the modern web UI, is **not packaged**. A complete
ADS-B story needs a binary or source backend for it, so the *web* half of this
recommendation is post-1.0 unless the backend lands earlier. The decoder half is
apt-only and available today.

---

## 2. Logging

| Candidate | Source | Availability |
|---|---|---|
| `qlog`, `cqrlog`, `xlog`, `klog`, `tlf`, `tucnak`, `pyqso`, `not1mm`, `trustedqsl` | Blend `logging` | **all in Debian** |
| `fllog`, `flnet` | AHRL — source | not in Debian |
| HAMRS | 73Linux — AppImage | not in Debian |

### Recommended: `qlog` for general logging

> Modern, actively developed, already the agreed default in `PARITY-POLICY.md`, and in Debian — so the default costs no backend work.

**These are not all the same job**, and treating them as one overlap would be a
mistake:

| Job | Recommended | Why |
|---|---|---|
| General station log | `qlog` | Active, modern, packaged |
| Contest logging (GUI) | `not1mm` | Actively developed; already carried by AHRL |
| Contest logging (terminal) | `tlf` | The serious contest CLI; no GUI competitor |
| Net control | `flnet` | Different workflow entirely — running a net, not logging QSOs |
| Networked shared log | `fllog` | Serves a log across machines; not a personal logger |
| LoTW upload | `trustedqsl` | Not a logger at all; every operator needs it |

**Also carry:** `cqrlog`, `xlog`, `klog`, `tucnak`, `pyqso`. All work, all
packaged, all have users.

**Post-1.0:** HAMRS — proprietary freemium, AppImage, and its upstream is
discovered by scraping a webpage.

---

## 3. SDR receivers

| Candidate | Source | Availability |
|---|---|---|
| `gqrx-sdr` | Blend `sdr`; AHRL builds from source | **in Debian** |
| `sdrpp` (SDR++) | Blend `sdr`; AHRL builds a `master` snapshot | **in Debian** |
| `sdrangel` | Blend `sdr` | **in Debian** |
| `cubicsdr` | Blend `sdr` | in Debian |
| `quisk` | Blend `sdr`; AHRL source | in Debian |
| `welle.io` | Blend `nonamateur` | in Debian (DAB, not general) |

### Recommended: `gqrx-sdr` as the general-purpose default

> The most documented, most widely used, and simplest receiver to get working with a first SDR — which is the situation most users are in when they open one.

**Tiered alternatives**, because "SDR receiver" hides three different needs:

| Need | Recommended | Why |
|---|---|---|
| First SDR, general listening | `gqrx-sdr` | Simple, documented, forgiving |
| Modern UI, plugin ecosystem | `sdrpp` | Actively developed, better performance |
| Multi-channel, transmit-capable, advanced | `sdrangel` | Far more capable and far more complex |
| Transceiver operation, not scanning | `quisk` | A *transceiver* app; different job |

**This resolves an unpinned snapshot for free.** AHRL builds SDR++ from an
unversioned `SDRPlusPlus-master.zip`. Debian packages it. Preferring apt removes
one of the six snapshot problems in `D-006` at no cost — see the same pattern in
`blend-inventory.md`'s M3 cross-reference.

**Note the naming trap:** the Debian package is **`gqrx-sdr`**, not `gqrx`. A
manifest that guesses will silently resolve to nothing.

---

## 4. APRS

| Candidate | Source | Availability |
|---|---|---|
| `xastir` | Blend `packetmodes`; AHRL apt | **in Debian** |
| YAAC | AHRL — Java zip | **not in Debian** |
| Pi-APRS | 73Linux | not packaged; **unlicensed (D-001)** |
| `aprsdigi` | Blend `packetmodes` | in Debian |
| `direwolf` | Blend; AHRL source | in Debian |

### Recommended: `xastir`

> Mature, packaged, in the Blend, and already installed by AHRL — the only candidate that is simultaneously maintained, free of licence questions, and apt-installable.

**Also carry:** YAAC. It has a genuinely better map UI and an active author, and
some operators strongly prefer it — but it needs a JRE and a binary backend, so
it should not be the default.

**Cannot carry:** Pi-APRS. KM4ACK's own work in an unlicensed repository
(**D-001**); we have no right to redistribute it regardless of merit. If the
licence question is resolved this reopens.

**Not competing, do not conflate:** `direwolf` is the *TNC* — the modem layer
underneath any of these. `aprsdigi` is a digipeater. Both belong in the packet
profile alongside a client, not instead of one.

---

## 5. Satellite imaging

| Candidate | Source | Availability |
|---|---|---|
| `satdump` | Blend `satellite`; AHRL source snapshot | **in Debian** |
| `noaa-apt` | AHRL — **RETIRED** | not in Debian |
| `xwxapt` | AHRL — **RETIRED** | not in Debian |
| `wxtoimg` | — | not packaged, abandoned |
| `gpredict` | Blend `satellite`; AHRL source | in Debian |

### Recommended: `satdump`

> The only live option — it handles the LRPT and HRPT services that still transmit, and it is already the agreed supersede target for both retired APT decoders.

**There is no real overlap here to resolve.** Both alternatives are retired
because the NOAA APT satellites were decommissioned on 2025-11-09. This section
exists so the reasoning is written down where someone looking for an APT decoder
will find it.

**Second free snapshot fix:** AHRL builds SatDump from `SatDump-master.zip` while
shipping an unused pinned `SatDump-1.2.2.zip`. Debian packages it. Prefer apt.

**Not competing:** `gpredict` is *tracking* — where a satellite is and when it
passes. SatDump is *decoding* what it transmits. An operator needs both.

---

## Also overlapping, already raised

Not in this queue item, but they are the same class of problem and each already
has an open question:

| Overlap | Where |
|---|---|
| FT8 family — `wsjtx` / `wsjtx-improved` / `jtdx` / `mshv` | `dispositions.md`, NEEDS-DECISION |
| Rig control — `flrig` / `grig` / `wfview` / `libhamlib-utils` | `dispositions.md`, SUPERSEDE #5 |
| HamClock clients — four options | **Q-006** |
| RigExpert analysers — `flaa` / `antscope2` / `aa-analyzer` | `dispositions.md`, SUPERSEDE #3 |

---

## The pattern worth noticing

Four of the five recommendations above land on **a package Debian already
carries**, and three of them (`sdrpp`, `satdump`, and the `readsb` supersession)
**eliminate an unpinned `master` snapshot** from AHRL's inventory as a side
effect.

That is not a coincidence. Preferring the packaged option where one exists is
usually also the option with a maintainer, a version, and a signature — which is
why `SCOPE.md` puts the Blend first in the staging order. The exceptions worth
building a backend for are the ones where Debian genuinely has nothing:
`tar1090`, YAAC, HAMRS.
