# Session log — overnight round 4, 2026-08-26

Queue complete: items 1–7, plus the README you asked for mid-session. Ten
commits. Everything green.

Previous round's log is in git history at `28b370c`.

---

## Headline

**The engine has its first real mechanism.** Consent gates work, `--yes` cannot
satisfy one, and a disclosure that reads as legal advice is a validation error
rather than a review comment.

**Availability claims became install tests, and two were wrong.** Three of the
four upstream `.deb` artifacts in DragonOS Tier 1 do not install on our targets
from the URL upstream advertises.

**The cargo question is answered: no.** Rayhunter was its strongest candidate
and does not need it. D-014 holds on its own terms.

**A `.gitignore` rule swallowed a source package through an entire commit.**
Third instance of the same bug. Fixed generally this time.

---

## What completed

### The README — `a85a0ff` (your mid-session request, pushed)

It was one line. It now opens with an unmissable status block:

> Status: pre-alpha. Design and inventory phase. There is no working installer.

with a per-component table marking the CLI, every backend, the hardware layer
and the profiles as **not written**, and a plain instruction to use AHRL,
73Linux or Skywave instead if you want something that works today. AHRL is
credited first and at length, per D-001 and D-011.

Writing it raised **Q-009 🔴**: there is no `LICENSE` file and no header on any
source file, so default copyright applies and nobody may copy or contribute.
That is the exact objection D-001 raises against 73Linux and Q-007 against
SuperSDR. Criticising two upstreams for it while doing it ourselves is not a
position that survives anyone reading both. This is the only thing pushed to the
remote this round.

### Item 1 — install testing — `69e03ab`

`apt-cache policy` proves an archive *offers* a package. A capability-matrix row
claims it installs. That gap is now closed for Tier 1.

**The apt claims hold.** 31 of 34 Tier 1 packages resolve and install on
Debian 13, and the 3 that do not are exactly the 3 policy already reported
absent. Nothing that policy said was available failed to resolve.

**The `.deb` claims did not.**

| Artifact | Built for | Debian 13 | Ubuntu 26.04 |
|---|---|---|---|
| SatDump | Ubuntu 24.04 | ❌ | ❌ |
| SDR++ `bookworm` | Debian 12 | ❌ | ❌ |
| SDR++ `sid` | Debian unstable | ✅ | ✅ |
| SDRangel | Ubuntu 26.04 | ❌ | ✅ |
| AIS-Catcher | Debian 12 | ✅ | ✅ |

SatDump stays Tier 1 **by apt** instead. SDR++ works only through the artifact
nobody would pick, and **has no pinnable release at all** — its assets hang off a
rolling `nightly` tag, so the URL never changes and the artifact behind it does.
`SCOPE.md`'s Tier 1 definition now reads "apt-installable, or an upstream `.deb`
**that resolves on the target**".

**The harness needed two corrections first, and both are in the document.** The
first probe ran every package in one container: `direwolf`'s postinst failed,
wedged dpkg, and 21 later packages inherited the error as false failures. The
second tried to recognise harness artifacts by pattern-matching error text and
mis-classified two. The test is now structural — if dpkg recorded a version,
resolution succeeded — which needs no guesses about error strings.

### Item 2 — consent gates — `0038ba3`, and **D-021**

The mechanism, with a test behind each property:

- **`--yes` cannot satisfy a gate.** `resolve_consent()` takes `assume_yes` so
  the signature documents the fact, then deletes it unread.
- The scripted path is the profile's **own** variable, so one profile's opt-in
  cannot satisfy another's gate, and it must be exactly `1`.
- **Silence is never consent.** No TTY and no variable raises
  `ConsentUnavailable`, deliberately a different exception from
  `ConsentDeclined` — "nobody was asked" and "somebody said no" are different
  facts and the log should not conflate them.
- The record carries the **exact text shown**, and a test asserts the string
  passed to the prompt is byte-identical to the string recorded.

**The harder half was what the gate may claim.** It must not tell users what is
legal where they are — we cannot know jurisdiction, licence class, employer
authorizations or engagement terms, and we are not lawyers. So the taxonomy
describes capability, never legality, and **the rule is enforced by the type
system**: `ConsentGate` rejects text that asserts legality, names a regulator,
generalises across jurisdictions, or tells the user what they may do. Same
spirit as having no `method: script`.

**Gating is selective, and asserted as such.** `rf-security` ships ungated —
Wireshark and aircrack-ng are in Debian and Kali without ceremony, and a prompt
that appears for routine software is one people learn to dismiss.

### The `.gitignore` bug — `5d9be0f`

`src/hammunition/state/` — the transaction log written for item 2 — was matched
by the unanchored `state/` rule. `git add` refused it, the commit went through
without it, and **mypy, pytest and ruff all stayed green because they read the
working tree, not the index.** The module was written, tested, type-checked and
not committed.

Third instance: `reference/` did this to `docs/reference/`, and now `state/` to a
source package. Fixed generally — every project-root output directory is
anchored, and a test asserts the property rather than the instances: no `.py`
under `src/` or `tests/` may be ignored, and every one must be tracked.

### Item 3 — device catalog — `75afa2c`

`catalog/hardware/`: a schema, a loader, 17 entries, 24 tests.

**Every USB identifier carries evidence, and guessing is unrepresentable.** A
wrong VID:PID produces a udev rule that silently never matches, and an operator
cannot tell that from a bad cable. So a device with no confirmed identifier, no
class to inherit one from, and no `identification_gap` is a validation error, and
`status: supported` without a confirmed identifier is rejected outright.

Every confirmed ID was read out of a distribution's udev rules **in a container**,
not from memory. My own first guess at bladeRF was `2cf0` only and would have
missed `1d50:6066` entirely.

**Badges are a class, not entries**, as you asked. `badgelife` carries the
CP210x, CH34x and ESP32 rules, the flasher, the serial console and the groups.
Clip-Boy is the first worked example; Meshtastic nodes inherit it too. Espressif's
`303a:1001` is marked **unconfirmed** — esptool in Debian confirms the PID, but
vendor `303a` is not in Debian's `usb.ids` and I would have been asserting it
from memory.

Six devices ship with an honest `identification_gap` and no ID at all.

### Item 4 — Rayhunter — `422d4c6`, and a **D-014 amendment**

**cargo is not justified.** Rayhunter is the strongest candidate in scope — 2.6 MB
of Rust, `Cargo.toml` at the root — and upstream ships prebuilt Linux binaries for
x64, aarch64 and armv7. Nothing compiles on the user's machine. The binary
backend already required for 1.0 covers it. **cargo stays at zero.**

**The better finding is a checksum.** `SCOPE.md` says of the pin/hash database
that *"not one of them publishes checksums we can inherit"*. Rayhunter publishes
a `.sha256` beside every asset — verified, published and computed digests match.
**First inheritable hash in the catalog.** `SCOPE.md` now records the exception.

Also: the installer statically links EFF's fork of `adb_client`, so **no `adb`
package is needed**. The obvious dependency is not one.

Placement: Rayhunter is **defensive**. It belongs in `rf-security` ungated, and
the guide says so explicitly because the adjacency with DragonOS's cellular/EW
cluster will confuse people — both say "IMSI catcher" and they are opposites.

### Item 5 — **D-022** and the VS Code case — `970bb0b`

The general rule first, as instructed. Coexist rather than replace; never remove
silently; a third-party repo's disclosure must say the vendor gains the ability
to ship updates **for any package name, forever**; state the distribution's
reasoning as a reason rather than an obstacle; never a default.

Verified in the Parrot container: it packages `codium` 1.126.04524 and
`code-oss` 1.75.1-0parrot1, and **does not package `code`**. The Microsoft key
fingerprint `BC528686B50D79E339D3721CEB3E94ADBE1229CF` was read from the
published key with gpg, not recalled — a pinned fingerprint nobody checked is
worse than none, because it looks verified.

The trade-off is stated both ways and neither is editorialised.

### Item 6 — conference guide — `1d30e2c`

`docs/guides/conference-operating.md`, drafted to be corrected and saying so.
Sections most likely to be wrong are flagged rather than written confidently.

It applies D-021's discipline to prose: describes what tools can do and where
rules come from, never what is legal. The organising idea is **three rulebooks
people treat as one** — law, venue terms, and the code of conduct you actually
agreed to — with the note that conference rules are usually strictest and
"nobody stopped me" is not authorization.

The badge section is written as **five failure modes** rather than instructions,
because that is what actually happens at midnight in a hotel room: charge-only
cable, group membership without logging out, ModemManager holding the port,
`/dev/ttyUSB0` moving between plugs, and a half-flashed badge.

**No `conference` profile is proposed.** The work is configuration and judgement,
not a package list.

### Item 7 — reconciliation — this commit

`DESIGN.md`'s Tier 1 wording, `SCOPE.md`'s pin/hash claim, `PARITY-POLICY.md`'s
ADD list, `CLAUDE.md`'s repo layout (now marking what is **not written**),
decisions table and questions index, and `profile-sizing.md` regenerated with the
three profiles proposed this round.

**Retraction grep, per your standing rule.** Searched the repository for every
claim this round changed: stale "upstream `.deb`" Tier 1 wording (2 hits, both
fixed), `cargo` claims (D-014 amended, DESIGN.md updated), and the
"no checksums we can inherit" claim (SCOPE.md now records the Rayhunter
exception). No stale claim left standing.

---

## Your two profile recommendations — both need a decision

You asked me to note whether they are accepted or need decisions. **Both need
decisions**, and both are written up with a recommendation:

| | |
|---|---|
| **Q-010** 🟡 `rfid` | Your argument holds, and the packaging evidence strengthens it: every `rf-security` unit installs from apt somewhere, and **nothing Proxmark-related is packaged on any target**. So it is not only a different domain, it has a different cost — burying that inside `rf-security` would hide it. Recommend accepting, post-1.0. |
| **Q-011** 🟡 `workstation` | Recommended, with contents fixed now so it cannot grow quietly, and an explicit exclusion list — shells, prompts, dotfiles, window managers. If it is a matter of taste it is out of scope. `usbutils` earns its place twice: six hardware entries cannot be completed until someone runs `lsusb`. |

---

## Open questions

| | |
|---|---|
| Q-001 – Q-005 | ✅ resolved |
| **Q-006** 🟡 | Which HamClock |
| **Q-007** 🟡 | SuperSDR has no licence |
| **Q-008** 🔴 | Cellular interception tooling in the RF profile? Blocks `rf-research`'s contents |
| **Q-009** 🔴 | **What licence does Hammunition ship under?** Now public and all-rights-reserved |
| **Q-010** 🟡 | Accept `rfid`? |
| **Q-011** 🟡 | Accept `workstation`, with what contents? |

---

## What I could not do

**No hardware was attached to anything.** Six device entries carry an
`identification_gap` that only `lsusb` against real hardware can close:
CatSniffer v3, Minino, Free-WiLi 2, Proxmark3, LimeSDR, PlutoSDR — plus the
`303a` Espressif vendor ID in the badgelife class. That is the single highest-
value thing you can do in ten minutes with the kit on your desk.

**No Rayhunter device.** The guide reproduces upstream's workflow accurately and
says plainly it is not a report of having run it. The open question — whether the
installer needs udev rules for raw USB, since it uses `nusb` rather than `adb` —
is the thing most likely to bite a first-time Linux user.

**Configuration is still untested for anything touching dbus or systemd.** Six
packages and two `.deb` artifacts resolved and unpacked but could not configure,
because this account has no subuid ranges. One root command fixes it:

```
sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 chiefgyk3d
podman system migrate
```

**The `workstation` profile was not built**, as instructed — recommended only.

---

## Verification

| Check | Result |
|---|---|
| `pytest` | 139 passed |
| `mypy --strict` | clean, 21 source files, `debian:13` container |
| `ruff check` / `format --check` | clean |
| `check_doc_links.py` | clean, 87 references |
| Generated docs regenerate identically | yes |
| Catalog | 11 packages, 2 profiles, 1 device class, 16 devices — all validate |
