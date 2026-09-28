# GPS time: the laptop keeps its own clock when the network is gone

**Status:** design written from the maintainer's rules (2026-09-28); awaiting
the maintainer's read of this document. The ntpsec mechanism in §4 is being
measured by a read-only spike; its findings replace any line below marked
*to confirm*.
**Decision record:** D-058, written with the implementation. It extends D-056
(device power control) to the time source that depends on the device.
**Origin:** the maintainer, 2026-09-28: "a configuration to use the GPS for
time vs standard NTP if it's in the laptop, think EMCOMM situation where
internet may not be available", then the rules: "switch it off GPS time
basically if GPS is off, but if on it can be GPS or NTP, default to NTP, but
remember persistence of an optional setting to hold that setting. Default is
if gps = true gps time = yes; if gps = false gps time = no."

## 1. Why it matters

Without the network, nothing corrects the clock. FT8 and the other
weak-signal modes stop decoding beyond about a second of error, logs carry
wrong times, and an EMCOMM station loses the one clock everybody else trusts.
The GPS receiver fitted to the field laptop knows the time to far better than
a second.

## 2. The rules (the maintainer's)

| GPS device | GPS time | Which source the clock follows |
|---|---|---|
| **off** (parked) | **no** | the network only |
| **on** | **yes**, as a source | **network preferred** by default; the GPS keeps the clock right when the network is unreachable |
| **on**, preference set to `gps` | yes | the GPS preferred; the network is a check |
| **on**, preference set to `off` | no | the network only |

- The **preference** is optional, one of `ntp` (the default), `gps`, `off`,
  and **persists** across reboots until changed.
- The **device state wins**: a parked receiver never feeds the clock whatever
  the preference says, and waking it restores whatever the preference says.
- A receiver kept parked across reboots (the kept-off work, #119) therefore
  keeps GPS time off across reboots too, with no second setting.

## 3. What the operator sees

```
hammunition time                  # which source the clock follows now, and the preference
hammunition time prefer ntp|gps|off
```

`hammunition time` reads without privilege: the preference, whether a GPS
receiver is attached and awake, and ntpsec's own view (which source it has
selected, the offset), in plain words. `prefer` discloses the one file it
writes and asks polkit, like park and wake. The tray applet gains a small
"Time: network / GPS" line and the same three-way choice (hammunition-tray,
its own PR).

`doctor` gains a line: the time source in use, and a warning when the clock is
following nothing (offline with GPS time off or the receiver parked).

## 4. Mechanism (Parrot first: ntpsec)

Measured on Parrot 7.3 (2026-09-28):

- The time daemon is **ntpsec**; `systemd-timesyncd` and chrony are not
  running. Nothing is displaced (D-022): Hammunition adds a source to the
  daemon the distribution chose.
- gpsd already publishes time to NTP shared memory (keys `0x4e545030`…, units
  0 and 1 root 0600, 2+ 0666) from the attached u-blox.
- ntpsec supports `includefile`. `/etc/ntpsec/ntp.conf` is a dpkg conffile.
- The shipped config has `tos minclock 4 minsane 3`, with Debian's own comment
  above it saying to remove it when a refclock should be able to discipline the
  clock: with it, a lone GPS (network down) is ignored — the exact case this
  exists for.
- The USB receiver has no PPS line (`/dev/pps*` absent): accuracy is NMEA-over-
  USB, tens of milliseconds, fine for FT8 and logging, not for lab timing. The
  docs say so.

Therefore:

1. **One file of Hammunition's own**, `/etc/ntpsec/hammunition-gps.conf`,
   holding the refclock line and the selection options for the current
   preference, rewritten whole by the root helper when the preference changes.
   Its content is generated from the preference only, never from free text.
2. **One line added to `ntp.conf`**: `includefile /etc/ntpsec/hammunition-gps.conf`,
   and the `tos minclock 4 minsane 3` line commented out with a Hammunition
   marker, both disclosed in `hardware apply`'s plan as a change to a
   conffile (dpkg will ask about the file on an ntpsec upgrade, and the docs say
   what to answer). `hardware unapply` restores both lines exactly.
3. **Preference `ntp`** (default): the refclock present, the network servers
   `prefer`red, the refclock ranked below them — *to confirm by the spike*:
   the exact options (`stratum`, `prefer`, `time1` for NMEA latency) that make
   ntpsec follow the network when reachable and the GPS when it is not.
4. **Preference `gps`**: the refclock `prefer`red.
5. **Preference `off`**: the file holds no refclock.
6. **Device parked**: nothing is rewritten. A parked receiver's SHM segment
   goes stale and ntpd stops using it (*to confirm by the spike*: no restart
   needed). On wake it resumes. The rule "GPS off → GPS time no" holds by
   construction, without ntpd being touched on every park.
7. A preference change restarts ntpsec (`systemctl restart ntpsec`), disclosed,
   unless the spike finds a runtime path.

The preference is stored in `/etc/hammunition/time.yaml` (root-owned 0644,
written only by the helper), because it is machine-wide like the time itself.

**Other targets** (Debian 13, Ubuntu, Kali default to `systemd-timesyncd`,
which cannot read a refclock): not in this piece. `hammunition time` says the
target's daemon cannot use a GPS and names the gap; switching daemons is a
D-022 question for later, not a silent swap.

## 5. Privilege

The helper `hammunition-devctl` gains one verb, `time prefer ntp|gps|off`: a
fixed enum, the file content generated from it, the path a constant admitted
by its own exact-path guard (the kept-off pattern, `_guard_kept`), a fixed
argv for the ntpsec restart. No new polkit action. Reading state needs none.

## 6. Security, said plainly

With the network down and GPS time on, the clock follows one source. A spoofed
or faulty GPS could move it. Online, ntpsec weighs the GPS against the network
servers and outvotes a bad one. The operator can set `prefer off` to never
trust the GPS. `doctor` shows which source the clock is following. The docs
state all of this; nothing claims more accuracy than NMEA over USB gives.

## 7. Failure behaviour

| Case | Result |
|---|---|
| No GPS receiver catalogued as attached | `time` says so; `prefer gps` still records the preference and says it takes effect when a receiver is attached |
| ntpsec not installed (other targets) | refused by name, with the gap |
| `ntp.conf` edited by hand so the anchor lines are missing | refuse to edit it, name the file and the line looked for |
| ntpsec fails to restart | reported with its journal hint; the previous file is restored |

## 8. Proof before claims

On the field laptop, recorded on the bench page: `ntpq -p` with the network up
(network selected, GPS present) and with networking off (GPS selected, clock
still disciplined after a few minutes), the offset between them, the GPS
parked (refclock unreachable, no restart), and each preference.

## 9. Out of scope

PPS hardware, chrony, timesyncd targets, serving time to other machines on the
LAN (a later EMCOMM piece: the laptop as the net's time server).
