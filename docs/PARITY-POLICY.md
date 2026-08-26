# Parity Policy — What We Carry, Replace, Revive, Retire, and Add

The goal is not to reproduce AHRL. The goal is that a user who uninstalls AHRL
and installs Hammunition is **strictly better off**: everything that worked still
works, some things work that didn't, some things are better than what they
replace, and the dead weight is gone with an explanation.

Reproducing AHRL faithfully — including its broken entries and its obsolete ones
— would be a worse product than AHRL, because it would have all the same problems
plus being newer and less proven.

Every unit in the AHRL inventory (and the 73Linux delta) gets exactly one
disposition. No unit is left unclassified.

---

## The five dispositions

### CARRY
The software works, is maintained, and there's no better option. Bring it across
as-is.

**Bar:** builds or installs cleanly on at least one supported distro; upstream
shows activity in the last ~2 years, or it's stable-and-finished rather than
abandoned (some ham software is genuinely done).

**Most of the catalog is this.** Don't get creative where creativity isn't needed.

---

### SUPERSEDE
Something better exists. Ship the better thing; optionally keep the original as
an alternative.

**Bar — all four must hold:**
1. The replacement covers the original's core function
2. The replacement is more actively maintained
3. The replacement is packaged or installable at least as cleanly
4. We can state the trade-off in one sentence

**Rule:** never silently substitute. If someone's muscle memory says `dump1090`,
the catalog must explain why they're getting `readsb`. A `supersedes:` field on
the replacement and a `superseded_by:` on the original, with a reason.

**Where the original still has unique capability, CARRY both** and mark the
recommended default. Superseding is not an excuse to remove working software.

---

### REVIVE
AHRL disabled it, but the problem was AHRL's, not the software's. We fix it.

**This is where we earn the project.** AHRL disables things for compile errors,
packaging difficulty, and library churn. Some of those are genuinely dead. Others
are a stale version pin, a missing `-Wno-*` flag, an upstream that fixed the bug
two years ago, or a packaging job that a bash script couldn't do and a venv
backend can.

**Rule: never inherit a `broken` verdict without testing it yourself.** If AHRL
says it doesn't compile, we attempt the build, on current sources, on our
supported distros. Record the attempt and the result in the status reason —
including the date and the version tried, so the next person knows what was
actually tested.

---

### RETIRE
The software is genuinely unnecessary now. Not broken — *unnecessary*.

**Three legitimate reasons, and only these:**
1. **The world changed.** The signal, service, satellite, or protocol it worked
   with no longer exists.
2. **It never worked.** Empty stubs, permanently broken, no upstream.
3. **It's out of scope.** Fine software, but not what this project is for.

**Not legitimate:** "it's old," "it looks unmaintained," "I don't use it," "the
UI is dated." Ham software is full of programs that were finished in 2005 and
still do their job correctly.

**Every RETIRE entry stays in the catalog** with `status: retired`, a reason, and
a date. Users who go looking must find an explanation, not silence. If a
replacement exists, name it.

---

### ADD
Software AHRL never had. Either it fills a real gap, or it's newer and better
than anything in the original inventory.

**Bar:** a named use case a licensed operator actually has, and maintained
upstream. Not "this exists, therefore include it."

---

## Known dispositions from the inventory

These are settled by evidence already gathered. Everything else needs
classification.

### RETIRE — the world changed
| Unit | Reason |
|---|---|
| `noaa-apt` | All NOAA APT satellites out of service 2025-11-09. Point users to SatDump for the satellites that still transmit. |
| `xwxapt` | Same. Same pointer. |

### RETIRE — never worked
| Unit | Reason |
|---|---|
| `mfc_gpl` | Empty stub function; AHRL's own docs call it obsolete |
| `tt3_gpl` | Same |

### REVIVE — attempt before accepting the verdict
| Unit | AHRL's reason | Why we retry |
|---|---|---|
| `ardop` | v27 compile error on Xubuntu 26.04 | Upstream `pflarue/ardop` is active. Also in our 1.0 packet core. |
| `radiosonde_auto_rx` | AHRL gave up packaging | Upstream healthy. A venv backend handles what a bash script couldn't. |
| `ibp` | "many, many compiler errors" | Upstream 0.21 predates modern C — likely genuine, but IBP beacons still transmit, so if the build can't be revived this becomes SUPERSEDE, not RETIRE. Find what shows beacon status now. |

### REVIVE-or-SUPERSEDE — decide after investigation
| Unit | Situation |
|---|---|
| `dream` | Killed by Debian 13 dropping `libqt5webkit5-dev`. May be the only DRM decoder — check before retiring. If nothing replaces it, that's a documented gap, not a quiet removal. |
| `mvoice` | Killed by `libopendht-dev` removal. Was AHRL's only M17 path. M17 is on our ADD list regardless — find the maintained successor. |

### CARRY, with attention
| Units | Note |
|---|---|
| `glfer`, `gsmc`, `owx`, `linrad`, `qgrid` | Build only with `-Wno-*` flags. They work. Record the flags in `compiler_flags` and add a CI job so we learn when a GCC release breaks them. |

### SUPERSEDE candidates — verify each
| Original | Candidate replacement | Check |
|---|---|---|
| `dump1090` | `readsb` or `dump1090-fa` | Original upstream stagnant; PiSDR dropped it over security concerns |
| `cqrlog` / `xlog` | `QLog` as recommended default | QLog is modern and active; both originals still work — CARRY all three, mark the default |
| AHRL's unversioned snapshots (SatDump, SDR++, gsmc, cwwav, AntScope2) | Same software, pinned | Not a replacement — a packaging fix. A pinned `SatDump-1.2.2.zip` sits unused in AHRL's own tarball. |

### RETIRE-as-out-of-scope candidates — my call needed
| Units | Question |
|---|---|
| `kicad`, `pcb`, `gerbv`, `gspiceui`, `gwave`, Arduino IDE, Fritzing | General electronics/EDA, not radio. Proposal: move to a separate `electronics` profile rather than removing — hams do build things, but this shouldn't land in a ham-core install. Note `install_gspiceui` hardcodes an `aarch64` path and leaves a dangling symlink on x86_64, so it needs fixing either way. |
| `Morse Runner` (via Wine) | Wine dependency for a CW trainer. Check whether Morse Runner CE or a native alternative exists before carrying a Wine prefix into core. |

---

## What needs classifying

Every remaining AHRL unit, plus the 73Linux delta. For each, the disposition and
the evidence for it. Where the disposition is SUPERSEDE or RETIRE, name what
replaces it or state plainly that nothing does.

---

## ADD — gaps to fill

Ordered by how badly the ecosystem needs them.

**M17 / digital voice.** AHRL has zero M17 support in v27. Find the maintained
tooling and build it properly.

**Packet / Winlink / EMCOMM.** AHRL has no Winlink client at all. 1.0 core: PAT,
AX.25 stack, BPQ, ARDOP, Direwolf *with configuration, not just installation*.
Post-1.0: VARA (needs Wine prefix, closed-source freeware), HAMRS (needs
AppImage, and its upstream discovers downloads by scraping a webpage).

**Mesh and LoRa.** Absent from every ham catalog despite huge operator interest.
Meshtastic (CLI, Python API, desktop clients), Reticulum/NomadNet/MeshChat,
gr-lora_sdr.

**RF security and SIGINT.** Separate opt-in profile. Universal Radio Hacker,
inspectrum, SigDigger, Kismet, rtl_433, Aircrack-ng suite, Ubertooth, SDRTrunk,
OP25, DSD-FME, HackRF/PortaPack firmware management, qFlipper, CatSniffer and
nRF52840 tooling.

**Two units in this list now have measured status** (`docs/reference/dragonos-tier1-inventory.md`):

- **gr-gsm** — the "upstream has stalled for modern GNU Radio" note is out of
  date as a practical matter. Debian ships `gr-gsm 1.0.0~20220727-1+b18`,
  maintained by the Debian Hamradio Maintainers against `git.osmocom.org/gr-gsm`,
  and it installs from apt on Debian 13, Kali and Parrot — not Ubuntu 26.04.
  Upstream development moved off GitHub; the packaging did not stop. **CARRY via
  apt**, with the Ubuntu gap recorded in the capability matrix. It is also in
  the receive-only cellular group that **Q-008** governs.
- **Universal Radio Hacker** — `jopohl/urh` is **archived**: read-only, last
  pushed 2025-12-19, final release v2.10.0, 12,500 stars. It is in none of the
  four targets' apt and appears never to have been packaged for Debian at all
  (`tracker.debian.org/pkg/urh` 404s). It installs from PyPI. Per this document
  "finished" is a legitimate state and a `broken` verdict may not be inherited,
  so **the disposition waits on our own install test on a supported distro** —
  most likely CARRY via a venv or pipx backend with `status: frozen` and the
  archival recorded. Do not write it down as dead without testing it.

**Direction finding.** Ham interest (ARDF, foxhunting) and security interest,
served by neither side. KrakenSDR DoA, DF-Aggregator.

**Defensive cellular.** EFF's **Rayhunter** detects IMSI catchers rather than
being one. It transmits nothing and collects no identifiers but its own device's,
so it belongs in `rf-security` **ungated** — none of D-021's risk categories
fits it. Investigated 2026-08-26: the host tooling is a prebuilt binary with a
**published, verified `.sha256`**, the first inheritable hash in this catalog.
See `docs/guides/rayhunter.md`. The topic adjacency with DragonOS's cellular/EW
cluster will confuse people and the docs say so explicitly.

**Modern SDR applications.** SDR++, SDRangel, SatDump — all actively developed,
none in Debian, therefore absent from the ham blends.

**Test equipment.** nanovna-saver (restored in AHRL v27), TinySA tooling,
AntScope2 pinned.

**Configuration that nobody ships.** Persistent udev symlinks by device serial.
Audio routing for digital modes. A KISS bridge systemd unit for Bluetooth-
connected radios. This is the differentiator and it isn't a package list.

---

## Reporting

The M5 parity report must show, per unit: disposition, evidence, and — for
`broken` — whether the verdict was tested by us or inherited.

**Exit criteria:** the fraction of AHRL units that install successfully must
be **at least as good as AHRL's own**. AHRL ships 95 units with 9 disabled.
If we ship 95 manifests with 40 marked broken, we have not reached parity no
matter how complete the coverage looks.

Inherited verdicts count against us. Tested-and-confirmed-dead does not.
