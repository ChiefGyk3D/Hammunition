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

The maintainer added (2026-09-28): options to **force NTP always or GPS
always** for someone who needs it one way, and **the system must keep time
when neither works**. So the preference is a four-way mode:

| Mode | GPS awake: the clock follows | GPS parked |
|---|---|---|
| `auto` **(default)** | the network when reachable; the GPS when it is not | the network only |
| `prefer-gps` | the GPS first; the network is a check and the fallback | the network only |
| `ntp-only` | the network only; the GPS is never used for time | the network only |
| `gps-only` | the GPS only; network time servers are never used | **no source**: holdover (§4a), and `doctor` warns |

- The **mode** is optional (`auto` when unset) and **persists** across
  reboots until changed.
- The **device state wins**: a parked receiver never feeds the clock whatever
  the preference says, and waking it restores whatever the preference says.
- A receiver kept parked across reboots (the kept-off work, #119) therefore
  keeps GPS time off across reboots too, with no second setting.

## 3. What the operator sees

```
hammunition time                  # which source the clock follows now, and the preference
hammunition time mode auto|prefer-gps|ntp-only|gps-only
```

`hammunition time` reads without privilege: the mode, whether a GPS
receiver is attached and awake, and ntpsec's own view (which source it has
selected, the offset), in plain words. `mode` discloses the one file it
writes and asks polkit, like park and wake. The tray applet gains a small
"Time: network / GPS / holdover" line and the same four-way choice
(hammunition-tray, its own PR).

`doctor` gains a line: the time source in use, and a warning when the clock is
following nothing — offline in `ntp-only`, or `gps-only` with the receiver
parked — saying how long it has been in holdover.

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
3. **`auto`** (default): the refclock present, the network servers
   `prefer`red, the refclock ranked below them — *to confirm by the spike*:
   the exact options (`stratum`, `prefer`, `time1` for NMEA latency) that make
   ntpsec follow the network when reachable and the GPS when it is not.
4. **`prefer-gps`**: the refclock `prefer`red, the network servers kept.
5. **`ntp-only`**: the file holds no refclock.
6. **`gps-only`**: the refclock, and the `pool` lines in `ntp.conf` disabled
   while the mode holds (commented with the Hammunition marker, restored
   exactly when the mode changes or on `unapply`) — *to confirm by the spike*
   whether a `noselect` or `tos` route avoids touching the pool lines.
7. **Device parked**: nothing is rewritten. A parked receiver's SHM segment
   goes stale and ntpd stops using it (*to confirm by the spike*: no restart
   needed). On wake it resumes. The rule "GPS off → GPS time no" holds by
   construction, without ntpd being touched on every park.
8. A mode change restarts ntpsec (`systemctl restart ntpsec`), disclosed,
   unless the spike finds a runtime path.

The mode is stored in `/etc/hammunition/time.yaml` (root-owned 0644,
written only by the helper), because it is machine-wide like the time itself.

### 4a. Holdover: keeping time when neither works

Measured on the field laptop (2026-09-28):

- A battery-backed hardware clock, `rtc0` (`rtc_cmos`), kept in UTC
  (`LocalRTC=no`): it survives power-off and reboots.
- The kernel writes the synced system time back to it every 11 minutes
  (`CONFIG_RTC_SYSTOHC=y`, device `rtc0`), so the stored time is the last good
  one, not the factory's.
- ntpsec keeps a frequency file, `/var/lib/ntpsec/ntp.drift`, so with no
  source at all the clock keeps correcting for this machine's own rate error.
- ntpd runs with `-g`, so a large error at boot is corrected in one step once
  a source appears.

So on a machine with a hardware clock, holdover works today and this piece
only has to show it: `hammunition time` and `doctor` report "holdover since
<time>, last synchronised from <source>", from ntpsec's own state, and warn
after a day without a source (the error grows with the drift file's figure;
the docs say how much, measured on the bench).

**A machine with no hardware clock** (a Raspberry Pi, one of the targets)
boots with a wrong date and nothing to correct it offline. `fake-hwclock`
(in the archive) saves the time at shutdown and hourly and restores it at
boot. `hardware apply` offers it, disclosed, on a machine where
`/sys/class/rtc` is empty; it is never installed where a real clock exists.

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
servers and outvotes a bad one. The operator can set `ntp-only` to never
trust the GPS, or `gps-only` to never trust the network. `doctor` shows which source the clock is following. The docs
state all of this; nothing claims more accuracy than NMEA over USB gives.

## 7. Failure behaviour

| Case | Result |
|---|---|
| No GPS receiver catalogued as attached | `time` says so; a GPS mode is still recorded and `time` says it takes effect when a receiver is attached |
| Neither network nor GPS | holdover from the hardware clock and the drift file; `time` and `doctor` say so and for how long |
| ntpsec not installed (other targets) | refused by name, with the gap |
| `ntp.conf` edited by hand so the anchor lines are missing | refuse to edit it, name the file and the line looked for |
| ntpsec fails to restart | reported with its journal hint; the previous file is restored |

## 8. Proof before claims

On the field laptop, recorded on the bench page: `ntpq -p` with the network up
(network selected, GPS present) and with networking off (GPS selected, clock
still disciplined after a few minutes), the offset between them, the GPS
parked (refclock unreachable, no restart), each of the four modes, and a
holdover run with both sources gone for an hour (offset at the end).

## 9. Out of scope

PPS hardware, chrony, timesyncd targets, serving time to other machines on the
LAN (a later EMCOMM piece: the laptop as the net's time server).
