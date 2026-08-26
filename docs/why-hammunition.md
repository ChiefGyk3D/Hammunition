# Why Hammunition Exists

*Linux radio tools for people who can't leave well enough alone.*

> **State of the project, August 2026: there is nothing to install yet.**
> Hammunition is in design. What exists today is documentation — a decision
> record, a parity policy, and a complete measured inventory of what Andy's Ham
> Radio Linux v27 installs (95 units, 57 of which apt cannot provide). No
> catalog, no engine, no CLI, no releases. Everything below describes what
> Hammunition is being built to do, not what it does. When that changes, this
> banner changes with it.
>
> If you need a working ham Linux setup *today*, the "You might prefer something
> else" section near the bottom is the honest answer, and it is not a formality.

If you're deciding whether this is worth following, that decision should be
informed. This page explains what Hammunition is for, what it deliberately
isn't, who built the ground it stands on, and when you'd be better off with
something else.

---

## Credit first

Hammunition would not exist without two projects.

**Andy's Ham Radio Linux**, by Andy Stewart (KB1OIQ), has been getting hams onto
Linux for well over a decade. Its real value isn't the installer — it's the
*curation*. Knowing which of the hundreds of ham applications on Linux actually
work, which are worth your disk space, which have quietly died, and which
compiler flag a 2003-era package needs to build on a modern system is knowledge
that takes years to accumulate and cannot be reconstructed from a package search.
Our catalog is seeded from that inventory. Where a package needs an odd build
flag or a patch, we very often learned it from AHRL.

AHRL also made a decision we followed: it used to be a full distribution and
moved to being an installer layered onto an existing OS. Arriving independently
at the same conclusion is a strong signal it's the right one.

**73Linux**, by Jason Oleham (KM4ACK), grew out of Build-a-Pi and does something
AHRL doesn't: Winlink, packet, and EMCOMM. PAT, BPQ, ARDOP, VARA, AX.25. If
you're running emergency communications on Linux, Jason's work is probably why
it's working. It also pioneered community side-loading — drop a file in a
directory and it appears in the menu — which is the single best idea in this
space and one we've adopted in our own form.

Neither project owes us anything. We took package names, versions, and upstream
URLs — facts, freely usable — and wrote our own implementation. No code was
ported from either.

---

## What Hammunition is

A tool that turns an existing Debian-family Linux install into an amateur radio,
SDR, and RF experimentation workstation.

It is **not a Linux distribution**. There's no ISO. You install Parrot OS, Debian,
Ubuntu, Kali, or Raspberry Pi OS the normal way, then run Hammunition on top. Your
OS stays yours.

It works from a **declarative catalog**: YAML files describing what each piece of
software is, how to install it on each distribution and architecture, and what it
needs configured. A Python engine reads those files and does the work. The catalog
is plain data — you can read it, diff it, validate it, or write your own tool that
consumes it without asking us.

---

## What makes it different

### One machine for ham radio, SDR, and RF security

This is the gap we set out to fill. The landscape splits cleanly in two:

- **Ham-focused projects** (AHRL, 73Linux, HamPi, Debian's Hamradio Blend) cover
  rig control, digital modes, logging, contesting, antenna modeling, propagation,
  CW, and satellites — and include essentially no signals-intelligence or RF
  security tooling.
- **SDR and security projects** (DragonOS, Kali, Parrot) cover signal analysis,
  trunked voice decoding, cellular tooling, direction finding, and wireless
  attack tooling — and largely skip the ham operating workflow. No logging, no
  contesting, no antenna modeling.

If you want both, you currently carry two laptops. Hammunition is for the
operator who wants one.

### Verified sources

Every non-apt download is pinned to a specific version and verified against a
checksum or signature before anything is installed. If verification isn't
possible, we don't install it — we tell you why and point you at the upstream
project.

This is harder than it sounds, and it's ongoing work: the upstream ecosystem
largely doesn't publish checksums, so we maintain our own. It also means we will
sometimes lag a new upstream release by a few days while we pin it. We think
that's the right trade on a machine that may also hold security tooling.

### A transaction log

Hammunition records everything it does: packages installed, repositories enabled,
groups created, udev rules written, configuration files touched. `--dry-run`
shows you all of it before anything happens, and it's complete rather than
approximate.

**On undo, we want to be precise about what we promise.** True rollback across
apt, pipx, cargo, and AppImage is not achievable — apt alone can't cleanly
reverse a transaction that pulled dependency changes. What we offer is
`hammunition uninstall`, which removes what Hammunition added and tells you
honestly about anything it can't safely reverse. A smaller promise we can
actually keep.

### Honest status on every package

Some ham software is dead. Some builds only with specific compiler flags on
modern systems. Some was killed by a library removal in Debian 13. Some decodes
satellites that no longer exist.

Every catalog entry carries a status and a reason. If you go looking for a NOAA
weather satellite decoder, Hammunition will tell you that all NOAA APT satellites
went out of service in November 2025 rather than installing a decoder for signals
that aren't there.

We hold ourselves to that standard about our own claims too. While preparing this
catalog we recorded — on three consistent sources — that HamClock had stopped
working. We then tested it, and it hadn't: the original author's server is gone,
but the project was picked up by others and is on a newer release than the ham
distributions ship. We were wrong in the direction that flattered our argument.
The correction is in `docs/reference/dispositions.md`, and the rule we wrote
afterwards is that external claims get tested before they get published.

### The configuration layer

Installing packages is the easy part. The hard part — and the part almost nobody
handles — is everything after:

- udev rules and device permissions so your SDR works without root
- persistent device naming so `/dev/ttyUSB0` roulette stops mattering
- audio routing for digital modes, which is where most Linux ham setups die
- CAT and rig control setup
- gpsd integration
- on the ClockworkPi uConsole, GPIO-gated power rails for the SDR, GPS, and LoRa

Hammunition treats configuration as first-class, declarative, and logged. This is
where we intend to be visibly better than the alternatives.

---

## Design decisions, and why

### Why not build a distribution?

Because it's a maintenance trap. A distribution means an ISO to build, a kernel to
track, security updates to ship, and users stuck on your release cadence. AHRL
started as a distribution and moved away from it. DragonOS ships a multi-gigabyte
ISO that's stale the week after release.

Augmenting an existing install means you get your distribution's security updates
from your distribution, and we stay in our lane.

### Why a declarative catalog instead of a shell script?

Shell scripts are how most of this space works, and they scale badly. The failure
mode isn't hypothetical: an imperative installer can define an install function,
give it a menu entry, ship the tarball, list it in the changelog — and never call
it. Users get a menu entry that does nothing, and no test catches it because
there's nothing to test against.

Declarative data doesn't have that failure mode. If a catalog entry exists, the
engine finds it. If it's malformed, validation rejects it. The call list is
generated, so it can't drift from the catalog.

Data is also inspectable in ways code isn't. You can ask "what does this profile
install?" without running anything as root. You can diff two releases. You can
write your own consumer.

### Why Parrot OS as the primary target?

Because the ham-plus-security operator is the person we're building for, and
Parrot is a reasonable base for that work. Debian, Ubuntu, Kali, Mint, and
Raspberry Pi OS are all supported — we test on all of them — but Parrot is where
we start.

### Why Python?

Because contribution is the point. This project exists partly because we wanted a
ham software catalog that anyone could contribute to, and Python is the language
the ham and security communities actually read and write. Go would give us a
static binary with no runtime dependency, which is genuinely attractive; we chose
the larger contributor pool. We ship as a `.deb` with a vendored virtualenv so
you never touch pip and your system Python is untouched.

### Why not just fork an existing project?

For 73Linux, the answer is simple and impersonal: there's no license file in the
repository, which under default copyright means we have no right to redistribute
a derivative. That's a fact about a missing file, not a criticism of anyone. If
that changes, the calculus changes.

For AHRL, the installer is GPL-3.0-or-later, so a fork would be legally possible.
We didn't, because forking would inherit the architecture we specifically wanted
to change. Rewriting from the package inventory gets us a declarative catalog and
keeps the provenance unambiguous.

### What we ship under, since we asked it of others

If a missing licence file is enough for us to decline forking 73Linux, and
enough to hold up SuperSDR pending a decision, then the same question pointed
back at us deserves an answer in the same document rather than a link to one.

We ship under **two** licences, split on the boundary the architecture already
draws:

- **`src/`, `scripts/`, `tests/`, `docs/` — GPL-3.0-or-later.** Copyleft is not
  decoration here. The argument for this project is a governance argument: that
  the failure mode in this space is a single maintainer and a closed door, not
  bad software. A permissive licence would let a fork close the source and
  recreate exactly that. It is also the licence most of the ham ecosystem
  already runs on, including AHRL's own installer.
- **`catalog/` — CC0-1.0.** The catalog is required to stay usable by an engine
  that isn't ours; that requirement is written into our own architecture rules.
  Copylefting it would contradict that outright. And the honest description of a
  manifest is that it records facts — `fldigi` is packaged as `fldigi`, it wants
  `hamlib` configured first, it is not in Raspberry Pi OS. Whatever thin
  copyright interest attaches to arranging facts is not worth the friction it
  would put on the one artifact we most want other people to take. CC0 removes
  an ambiguity; it does not make a grant.

Two licences cost one paragraph of explanation. One licence would have cost
either the governance guarantee or the invariant, and neither was available to
spend. The reasoning is recorded as D-023.

Nothing in this relicenses the software the catalog *describes*. Every program
in the inventory keeps its own terms, verified and recorded in
`docs/reference/licence-verification.md` — which is where that criticism of
other projects started, and is the same standard applied to us.

### Why governance from day one?

Nearly every project in this space depends on one person. That's not a criticism
— it's how volunteer software gets made, and the ham community is enormously in
debt to those individuals. But it's fragile, and we'd rather build something that
survives its founder. Multiple maintainers with merge rights, a documented
decision process, signed releases, and a real pull-request path from the start.

---

## You might prefer something else

We'd rather you use the right tool than ours.

**Use AHRL if** you want a mature, proven ham-radio-only setup from someone with
a decade of track record, you're on Ubuntu/Mint/Debian/Raspberry Pi OS, and you
don't need SDR or security tooling. It's a known quantity and it works.

**Use 73Linux if** Winlink, packet, and EMCOMM are your primary use case,
especially on a Raspberry Pi. Its coverage there is better than ours will be for
a while, and its menu-driven interface is friendly.

**Use DragonOS if** you're doing pure SDR and SIGINT work, want the widest
possible signal-analysis toolset preinstalled, and don't mind a large ISO and a
dedicated machine. Nothing else comes close on breadth of RF tooling.

**Use the Debian Hamradio Blend if** you want maximum stability and provenance,
you're comfortable configuring things yourself, and `apt install hamradio-all` is
all the automation you need. It's team-maintained and it's the gold standard for
packaging discipline.

**Use Skywave Linux if** you mainly listen — especially via remote SDRs like
KiwiSDR and WebSDR.

**Use Hammunition if** you want ham radio and SDR and RF security on one machine,
you care about knowing exactly what's being done to your system, or you want to
contribute to the catalog.

---

## What we're adding that the ecosystem is missing

Beyond parity with existing catalogs, these are gaps we intend to fill. Not
promises with dates — priorities.

### Digital voice and M17

M17 is an open, patent-free digital voice standard, and Linux support for it is
in poor shape — AHRL currently ships none at all after `mvoice` broke on Debian
13. This is a gap worth filling properly rather than porting something broken.

- **M17 tooling** — m17-tools, mvoice or a maintained successor, M17 gateway
  software
- **Digital voice generally** — DSD-FME, dsdcc, and the FreeDV ecosystem, which
  is well-maintained and underrepresented in ham catalogs

### Mesh networking and LoRa

Almost entirely absent from ham catalogs despite enormous operator interest, and
directly relevant to emergency communications.

- **Meshtastic** — CLI, Python API, and desktop clients
- **Reticulum / NomadNet / MeshChat** — encrypted mesh networking that runs over
  packet radio, LoRa, or IP
- **LoRa tooling** — gr-lora_sdr and related GNU Radio blocks
- **AREDN / mesh node tooling** where Linux-side tooling exists

### RF security and SIGINT

The half of our thesis that no ham catalog covers. Presented in a separate
profile requiring explicit opt-in, with legal framing (see below).

- **Signal analysis** — Universal Radio Hacker, inspectrum, SigDigger,
  QSpectrumAnalyzer
- **Wireless** — Kismet, Aircrack-ng suite, Bluetooth tooling (Ubertooth,
  Sparrow-WiFi)
- **Sub-GHz and IoT** — rtl_433, Flipper Zero tooling (qFlipper), CatSniffer
  tooling, nRF-based 802.15.4/BLE tools
- **HackRF ecosystem** — PortaPack/Mayhem firmware management, hackrf-tools
- **Trunked and digital voice decode** — SDRTrunk, OP25, DSD-FME
- **Cellular** — noting that gr-gsm's upstream has stalled for modern GNU Radio;
  we'll carry a maintained fork and mark it experimental rather than pretend
  otherwise

### Direction finding

A genuine ham interest (foxhunting, ARDF) and a genuine security interest, served
by neither side's catalogs.

- **KrakenSDR DoA** and the KrakenSDR toolchain
- **DF-Aggregator** for networked multi-station direction finding
- **Foxhunt and ARDF tooling** where it exists

### Modern SDR applications

Several excellent, actively maintained applications aren't in Debian and
therefore aren't in the ham blends.

- **SDR++** and maintained forks
- **SatDump** — properly version-pinned, unlike the unversioned snapshots common
  elsewhere
- **SDRangel** — very actively developed, Qt6
- **SDR4space**, **Sparrow**, and similar newer tools

### Winlink, packet, and EMCOMM

Filling the gap AHRL leaves, learning from 73Linux's coverage.

- **PAT** (Winlink client), **BPQ** node software, **ARDOP**, **VARA** via Wine,
  **AX.25** stack configuration, **GARIM/VARIM**
- **Direwolf** with actual configuration, not just installation
- **KISS bridging** for Bluetooth-connected radios — a systemd unit that presents
  a stable KISS endpoint so packet software doesn't need re-pairing in the field

### Weather, propagation, and imaging

- **XyGrib** (GRIB weather), **SatDump** for modern weather satellites
- Propagation: VOACAP, splat, and modern alternatives
- Noting honestly that NOAA APT decoding is retired — the satellites are gone

### Antenna and test equipment

- **NanoVNA tooling** — nanovna-saver and successors
- **TinySA** spectrum analyzer tooling
- **xnec2c**, antenna modeling, and Smith chart tools
- **AntScope2**, version-pinned

### Logging and operating

- Modern logging: **QLog**, **CQRLog**, **HAMRS**, **Cloudlog** client tooling
- **POTA/SOTA** spotting and activation tools
- **GridTracker2**, per-architecture
- **WSJT-X**, **WSJT-X improved**, **JTDX**, **MSHV**, **JS8Call** — the full
  weak-signal family, with the ordering constraints between them handled
  correctly

### Hardware support

Hardware Hammunition should configure, not merely install drivers for:

- SDRs: RTL-SDR, HackRF/HackRF Pro, Airspy, SDRplay, LimeSDR, PlutoSDR, BladeRF,
  KrakenSDR
- Transceivers via CAT: the Yaesu, Icom, Kenwood, and Elecraft families through
  hamlib
- Interfaces: Digirig, SignaLink, and the CP210x/CH34x bridges most LoRa and
  Meshtastic hardware uses
- GPS/GNSS receivers via gpsd
- ClockworkPi uConsole with the Hacker Gadgets AIO board — including the GPIO
  power rails, which mean your peripherals are invisible until enabled

---

## On the RF security tooling

This is a separate profile you have to opt into deliberately, and it ships with
documentation about legal boundaries rather than a wink.

Amateur radio operation in the United States is governed by Part 97, which
prohibits transmissions intended to obscure meaning and restricts what a licensed
amateur may transmit. Separately, computer-crime statutes govern accessing
systems you don't own. The intersection is not obvious, and "I have a license"
does not authorize testing networks that aren't yours.

We include these tools for authorized testing, lab work, research, and education.
The documentation says so plainly, explains the relevant boundaries, and doesn't
pretend the tools are only ever used well. If that framing seems excessive to
you, it isn't aimed at you — it's aimed at the person who installs this without
having thought about it.

---

## Contributing

The reason the catalog is data rather than code is so you can add to it without
learning our internals. Adding a package means writing a YAML file. Adding a
distribution means describing how packages resolve on it.

Three tiers: **core** (reviewed, tested in CI, signed), **community**
(contributed, reviewed, marked as such), and **local** (yours, never leaves your
machine). You choose which tiers you trust.

If you've been maintaining a personal script that installs your station, that
script is a catalog contribution waiting to happen.

---

*Hammunition is independent of and unaffiliated with Andy's Ham Radio Linux,
73Linux, DragonOS, Parrot OS, or Debian. Any errors in how we've characterized
those projects are ours; corrections are welcome as issues.*
