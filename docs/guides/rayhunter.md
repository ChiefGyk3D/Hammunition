# Rayhunter — deploying and reading an IMSI-catcher detector

**Investigated 2026-08-26 against Rayhunter v0.12.0.** Every claim below about
what ships and what it needs was checked against the repository and the release
artifact; the two things not tested are named at the end.

---

## What Rayhunter is, and why it is in `rf-security` and not `rf-research`

Rayhunter is the EFF's detector for **IMSI catchers** — cell-site simulators,
also called stingrays. It runs on a cheap mobile hotspot, watches the cellular
control traffic that device already sees, and flags patterns characteristic of a
simulator rather than a real network.

**It is a defensive tool.** It detects surveillance; it does not conduct it. It
transmits nothing, emulates no network, and collects no identifiers belonging to
anyone but the device it runs on.

That matters for where it lands, and the topic adjacency will confuse people:
DragonOS's cellular/EW cluster and Rayhunter both say "IMSI catcher" and are
opposites. **Rayhunter belongs in `rf-security`, ungated.** The transmit-capable
cellular stacks that **Q-008** governs are a different kind of thing and none of
the **D-021** risk categories fits Rayhunter — it does not transmit, does not
intercept communications not addressed to the device, and does not touch anyone
else's systems.

EFF publishes its own legal note with the project, which is worth reading and is
not reproduced or interpreted here.

---

## What we can and cannot install

**Rayhunter itself is firmware for a hotspot. We cannot install it**, in the
same way we cannot install a radio's firmware by running apt. What Hammunition
can do is provide the host side: the tooling that deploys it, the tooling that
reads what it produced, and documentation for the parts in between.

| Piece | Where it runs | Can we install it? |
|---|---|---|
| `rayhunter-daemon` | on the hotspot | **No** — deployed to the device by the installer |
| `installer` | your machine | **Yes** — prebuilt Linux binary |
| `rayhunter-check` | your machine | **Yes** — same release artifact |
| `tools/*.py` | your machine | Yes — Python, needs a venv |
| PCAP analysis | your machine | Yes — `wireshark`/`tshark`, already Tier 1 |

---

## The cargo question — measured, and the answer is no

**D-014** records `cargo` at **zero occurrences** across the inventoried sources
and says backends are justified by measurement rather than convention. Rayhunter
looked like the first real counter-example: it is a Rust project, 2.6 MB of it,
with `Cargo.toml` and `Cargo.lock` at the repository root.

**It is not a counter-example.** Upstream publishes prebuilt binaries for every
platform it supports:

```
rayhunter-v0.12.0-linux-x64.zip          + .sha256
rayhunter-v0.12.0-linux-aarch64.zip      + .sha256
rayhunter-v0.12.0-linux-armv7.zip        + .sha256
```

The `linux-x64` zip contains the `installer`, the `rayhunter-check` analyser
built for five platforms, the `rayhunter-daemon` that gets deployed to the
device, and the init scripts. Nothing is compiled on the user's machine.

**`cargo` stays at zero. The binary backend, which is already required for 1.0,
covers this completely.** D-014 is satisfied on its own terms: we looked for a
unit that requires cargo, the most promising candidate does not, and the measured
count does not move.

**Rayhunter is also the first upstream in this entire project that publishes
checksums.** `SCOPE.md` says of the pin/hash database that *"not one of them
publishes checksums we can inherit"* — across AHRL's 63 archives, 73Linux,
Skywave and DragonOS. Rayhunter publishes a `.sha256` beside every asset.
Verified here:

```
published: 2472e86bcdc9fb6023996c06555365daee849a9fbbaa59900083ae3544bc54ee
computed:  2472e86bcdc9fb6023996c06555365daee849a9fbbaa59900083ae3544bc54ee
```

That is one manifest we can write with an inherited hash instead of a hash we
pinned ourselves, and it is worth saying which project made that possible.

**No `adb` package is needed either.** The installer statically links EFF's fork
of the `adb_client` Rust crate and speaks USB directly through `nusb`. There is
no dependency on Android platform-tools.

---

## Supported hardware

From upstream's own device list. Availability varies by region and by what the
device's cellular bands support where you are — check that before buying.

| Device | Status | Region |
|---|---|---|
| **Orbic RC400L** (also branded Kajeet RC400L) | Recommended | Americas |
| **TP-Link M7350** | Recommended | Africa, Europe, Middle East — works in the Americas, usually costs more |
| Wingtech CT2MHS01 | Functional | Americas |
| T-Mobile TMOHS1 | Functional | Americas |
| TP-Link M7310 | Functional | Africa, Europe, Middle East |
| PinePhone / PinePhone Pro | Functional | Global |
| FY UZ801 | Functional | Asia, Europe |
| Moxee hotspot | Functional | Americas |

The underlying requirement is a **Qualcomm modem exposing `/dev/diag`**, which
is why the list grows by community contribution rather than by vendor support.

---

## The workflow, end to end

### 1. Get the release, and check it

```
curl -LO https://github.com/EFForg/rayhunter/releases/download/v0.12.0/rayhunter-v0.12.0-linux-x64.zip
curl -LO https://github.com/EFForg/rayhunter/releases/download/v0.12.0/rayhunter-v0.12.0-linux-x64.zip.sha256
sha256sum -c rayhunter-v0.12.0-linux-x64.zip.sha256
unzip rayhunter-v0.12.0-linux-x64.zip
```

Do the `sha256sum -c` step. Upstream went to the trouble of publishing it.

### 2. Deploy to the device

Connect to the hotspot over Wi-Fi or USB tethering and confirm you can reach its
admin page — `http://192.168.1.1` for the Orbic, `http://192.168.0.1` for the
TP-Link. Then:

```
cd rayhunter-v0.12.0-linux-x64
./installer orbic --admin-password 'your-device-admin-password'
```

`./installer tplink` for TP-Link hardware; `./installer --help` lists the rest.
The device reboots itself when the installer finishes.

### 3. Read what it found

Rayhunter serves a web interface from the device. Captures come off as **QMDL**
(Qualcomm diagnostic logs) and **PCAP**.

- `rayhunter-check` — the offline analyser, shipped in the same zip. Run it
  against a downloaded capture to re-run the detection heuristics on your own
  machine rather than on the hotspot's very limited CPU.
- `wireshark` / `tshark` — for the PCAP side. Both are in `rf-security` already.
- `tools/*.py` in the repository — `asn1grep.py`, `nasparse.py`, `pcap_check.py`,
  with a `requirements.txt`. A venv, not a system install.

---

## What this means for the catalog

**A `rayhunter` manifest is straightforward and unusually clean:**

- `method: binary`, per-architecture install blocks selecting the right zip —
  `Selector` already expresses that, and the three Linux artifacts map to
  `x86_64`, `aarch64` and `armv7l`.
- `sha256` **inherited from upstream** rather than pinned by us. First one.
- No `apt_repos`, no `system_modifications`, no `config_files`.
- Belongs to `rf-security`, ungated.
- `update.probe: github_release` against `EFForg/rayhunter`.

**One open point for the manifest.** The installer talks to USB directly through
`nusb` rather than through `adb`, so it may need udev rules or root for raw USB
access to the hotspot in bootloader or diagnostic mode. Upstream's Linux
instructions mention neither, and this has not been tested against hardware — so
the manifest should not assert a udev rule it has not seen work. Note it, test
it, then write it.

---

## What was not tested

- **No device.** Nothing here was deployed to an Orbic, a TP-Link or anything
  else. The workflow is upstream's, reproduced accurately; it is not a report of
  having run it.
- **`rayhunter-check` was not executed.** Its presence in the archive is
  confirmed by listing the zip; its behaviour is not.
- **No capture was analysed**, so nothing is claimed about detection quality,
  false-positive rates, or what its output looks like.
- **The udev question above is open**, and is the one thing most likely to bite
  a first-time user on Linux.

Per **D-018**, these are named rather than smoothed over. The checksum
verification and the archive contents *were* tested, and those are the two
claims this document actually leans on.
