# Operating at a conference

**Status: first draft, written to be corrected.** This is assembled from
documented practice, the tooling in this catalog, and published organiser
policies. It is **not** a report of personal experience at any conference, and
the maintainer's corrections take precedence over everything here. Sections
marked 🟡 are the ones most likely to be wrong.

**On legal questions, this document does what our consent gates do** (**D-021**):
it describes what tools can do and where rules come from. It does not tell you
what is legal where you are. We cannot know your jurisdiction, your
authorizations, or the terms you agreed to at registration, and we are not
lawyers.

---

## 1. Three different rulebooks, and people confuse them

Most conference trouble comes from treating these as one thing. They are not,
they can disagree, and the consequences differ.

| Rulebook | Who sets it | What happens if you break it |
|---|---|---|
| **The law** | Wherever you physically are | Not our subject. Consult someone qualified. |
| **The venue's terms** | The hotel or convention centre | Removal, a bill, a ban |
| **The conference code of conduct** | The organisers | Badge pulled, banned from future events |

**The conference rules are usually the strictest of the three**, and they are the
ones you actually agreed to. A thing can be entirely lawful and still get your
badge taken — running a rogue access point in a hotel lobby is the classic
example. Read the code of conduct before you arrive, not from your phone in the
queue.

**Where organiser policy and law diverge, the organiser's policy is not advice
about the law.** "Don't do that here" is a house rule, not a legal opinion, and
"nobody stopped me" is not authorization.

### The one thing worth internalising

**Receiving is broadly different from transmitting, and both are different from
touching someone else's systems.** That distinction runs through this whole
project — it is why `rf-security` is ungated and `rf-research` is not
(**D-021**), and why **Q-008** separates a passive decoder from a rogue base
station. It maps onto conference rules well:

- Watching spectrum on an SDR: normal, expected, often the point.
- Transmitting anything: needs your own licence or authorization, and the
  organisers may prohibit it regardless.
- Attacking networks or devices that are not yours: needs the owner's
  authorization. A conference network is not yours.
- Attacking the **designated** targets in a CTF or a village range: what the
  authorization you were granted at registration actually covers.

---

## 2. Preparing a machine for a hostile network 🟡

The working assumption at a security conference is that the network is hostile,
that everything unencrypted is read, and that anything listening is probed. That
assumption costs you very little even when it is wrong.

### Before you travel

**Take a machine you can afford to reinstall.** Not the one with your client
work, your key material and your only copy of anything.

**Full-disk encryption, powered off in transit.** Suspend leaves keys in RAM;
"powered off" and "lid closed" are different states.

**Reduce the listening surface.** The honest version of this is `ss -tulpn` and
turning off what you do not recognise. `cups`, `avahi-daemon` and `smbd` are the
usual suspects on a desktop install.

```
ss -tulpn | grep LISTEN            # what is actually listening
systemctl list-units --type=service --state=running
```

**Turn off automatic joining.** A laptop that reconnects to any remembered SSID
will join something's idea of `conference-wifi` without asking.

**Randomise your MAC per network.** NetworkManager does this per connection:

```
nmcli connection modify <name> wifi.cloned-mac-address random
```

🟡 *Whether per-connection randomisation or a global default is better practice
here is a judgement call and I have not tested how it interacts with captive
portals, which is exactly where it tends to break.*

**Assume DNS and captive portals are adversarial.** A captive portal is a
man-in-the-middle by design, which is why one that asks you to install a
certificate is a hard no rather than an inconvenience.

### What this catalog contributes

Nothing conference-specific yet. `rf-security` gives you `wireshark`, `tcpdump`
and the wireless auditing tools; the hardening above is generic and belongs in
`docs/guides/` rather than in a profile. **A `conference` profile is not
proposed** — the work is configuration, not packages, and pretending otherwise
would be the kind of package-list-as-a-product thinking this project exists to
avoid.

---

## 3. Badge hardware and SAOs

This is the part where the catalog does real work, and the part most likely to
go wrong in a hotel room at midnight.

Everything here is the **`badgelife` device class** in
`catalog/hardware/classes/badgelife.yaml`. Build it once and every badge works.

### Before you leave home

Install the tooling and **test it on a board you already own**. A conference is
the worst possible place to discover that your user is not in `dialout`.

```
sudo apt install esptool tio screen minicom
sudo usermod -aG dialout,plugdev "$USER"
# log out and back in — group membership does not apply to a running session
```

### The five things that go wrong

**1. Nothing appears in `/dev`.** Almost always the cable. USB cables sold with
phones and battery packs are frequently charge-only, with no data lines at all,
and they look identical. Keep one known-good data cable in the kit and label it.

```
lsusb                      # is the device enumerating at all?
dmesg -w                   # watch while you plug it in
```

**2. `Permission denied` on the serial port.** Group membership, and you did not
log out. `id` tells you what your current session actually has, which is not the
same as what `/etc/group` says.

**3. The port appears and then disappears for twenty seconds.** ModemManager
grabbing the new serial device to ask whether it is a modem. It looks exactly
like a dead badge. The class ships udev rules tagging matching devices so
ModemManager ignores them; without those, `sudo systemctl stop ModemManager` is
the blunt fix.

**4. The port number changes between plugs.** `/dev/ttyUSB0` becomes
`/dev/ttyUSB1` because you plugged something else in first. This is the whole
reason **persistent symlinks by serial** are the highest-value item in the
hardware role — `/dev/badge-<serial>` does not move.

**5. Flashing fails halfway and the badge stops enumerating.** Usually
recoverable: hold BOOT while tapping RESET to force the bootloader, then flash
again. Know your badge's button combination **before** you need it.

### Talking to a badge

```
tio /dev/badge-<serial>            # 115200 8N1 is the usual default
screen /dev/ttyUSB0 115200         # if you prefer screen; ctrl-a k to quit
```

Wrong baud rate produces plausible-looking garbage rather than nothing, so if
the output is *almost* readable, try 9600 and 921600 before assuming the badge
is broken.

### SAOs

The Simple Add-On header is a six-pin standard carrying power, I²C and two GPIO.
The practical consequence for Linux: an SAO is usually not a USB device and does
not appear in `/dev` at all. You talk to it **through** the badge, over I²C, from
whatever firmware the badge runs.

🟡 *This section is thin and the maintainer will have specifics — I2C address
conflicts between stacked SAOs, and which badges expose an I²C scanner, are the
obvious gaps.*

### Clip-Boy specifically

`catalog/hardware/devices/clip-boy.yaml`. An ESP32-S3 badge, GPLv3, firmware as
an Arduino sketch, with hardware files published alongside. Upstream's flashing
route is a web flasher built on ESP Web Tools over WebSerial — which needs a
Chromium-based browser and does not work in Firefox or without a graphical
session. **The Linux toolchain path is `arduino-cli` to build and `esptool` to
flash**, and that gap is exactly the kind this project exists to fill.

---

## 4. Travelling with RF hardware 🟡

**This section is the most likely to be wrong and the most consequential if it
is.** It describes what people report, not what any authority will do, and
practice varies enormously by country and by the individual officer. Nothing
here is legal advice.

### The kit

| | |
|---|---|
| **Carry-on** | Every radio, every SDR, every badge, all lithium batteries. Lithium cells are restricted in checked baggage by most carriers — that is an airline safety rule with a clear published basis, unlike most of this section. |
| **Cables** | More than you need, and one labelled known-good data cable. |
| **Antennas** | Long whips look alarming and snap in bags. Telescopic and stubby ones travel better. |
| **Documentation** | Your amateur licence if you hold one. |
| **Power** | Region-appropriate adapters, and a battery pack within your carrier's watt-hour limit. |

### What reportedly draws attention

A HackRF with a PortaPack looks, to someone who has never seen one, like a
purpose-built device with an antenna and a screen. A Proxmark looks like a card
reader because it is one. Bare boards with visible antennas and loose wiring
photograph badly on an X-ray.

Things people report helping:
- **Original retail packaging**, or a tidy organiser rather than a tangle.
- **A one-line answer you can give calmly.** "It's a radio receiver for an
  amateur radio hobby" is true for most of this and is a sentence, not a lecture.
- **Not volunteering more than the question asked.**

🟡 *I have no first-hand experience of any of this and it is assembled from
widely repeated advice. The maintainer has actually done it. Their version
replaces mine.*

### The genuinely important part

**Devices can be inspected, copied or retained at many borders**, and the rules
about that differ sharply between countries and depend on your citizenship. The
robust response is not a clever argument at the desk — it is **not carrying the
data in the first place**. See post-conference hygiene below; the same logic
applies on the way out.

---

## 5. Air-gapping and post-conference hygiene

### During

**Keep a captures machine separate from your daily machine** if you can. The one
that gets plugged into unknown hardware and joins unknown networks should not be
the one holding your credentials.

**Store captures somewhere you will find them.** A PCAP named `dump1.pcap` in
`/tmp` is a capture you have already lost. Date, location and what was attached.

**Do not put unknown USB devices in a machine you care about.** Badges are USB
devices. Everyone knows this and everyone does it anyway; the mitigation is
which machine, not whether.

### After

A checklist, in the order that matters:

1. **Rotate anything that touched the conference network.** Not because you saw
   something, but because you would not have.
2. **Reinstall the machine that went**, if it is a dedicated one. That is the
   reason for a dedicated one.
3. **Copy captures off before you wipe.** Onto storage that did not go with you.
4. **Review what you actually collected.** Wireless captures pick up traffic from
   people who did not consent to being in your capture, which is a
   `protected_communications` question in **D-021**'s terms and a question about
   what you keep, not just what you collected.
5. **Update firmware on badges after the event, not during.** A half-flashed
   badge is a paperweight until you are somewhere with a working toolchain.
6. **Write down what broke.** This document gets better from that, and a
   documentation bug is an issue we want.

---

## What this document still needs

Honest list, so it is obvious where the draft ends:

- 🟡 **Everything about airports.** Assembled from repeated advice, not experience.
- 🟡 **SAO specifics** — I²C addressing, stacking conflicts, per-badge quirks.
- 🟡 **MAC randomisation and captive portals** — the interaction is untested here.
- **Nothing about village-specific rules.** RF ranges, wireless CTFs and lockpick
  villages each have their own, and they are the rules people actually trip over.
- **No named conferences.** Policies change yearly and a document naming one
  becomes wrong quietly. Read the current code of conduct.
- **No `conference` profile**, and none proposed. The work here is configuration
  and judgement, not a package list.
