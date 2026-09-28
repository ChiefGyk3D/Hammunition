# GPS time: the laptop keeps its own clock when the network is gone

**Status:** design written from the maintainer's rules (2026-09-28), updated
with a read-only measurement of ntpsec 1.2.3 and gpsd on the field laptop
(§4b); awaiting the maintainer's read. Two behaviours remain for the bench
(§8), named where they are used.
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

### 4b. Measured 2026-09-28 (ntpsec 1.2.3, read-only)

- **ntpd reads `/etc/ntpsec/ntp.d/*.conf` automatically, after `ntp.conf`**,
  if the directory exists (`ntpd(8)` FILES and parsing rules). It is not
  shipped by the package. So Hammunition's settings go in
  `/etc/ntpsec/ntp.d/hammunition-gps.conf` with no `includefile` edit.
- **gpsd writes the first device's time to SHM units 0 and 1, root 0600**
  (`gpsd(8)`, and `ipcs -m`). ntpd drops to `ntpsec:ntpsec` with only
  `cap_net_bind_service,cap_sys_nice,cap_sys_time` (measured from
  `/proc/<pid>/status`), so it **cannot attach unit 0**. ntpsec's own
  `README.Debian` documents the AppArmor half of the fix
  (`capability ipc_owner,` in `/etc/apparmor.d/local/usr.sbin.ntpd`). The
  process also needs the capability itself: a systemd drop-in
  `AmbientCapabilities=CAP_IPC_OWNER` for `ntpsec.service`. **That widens a
  network-facing daemon's privilege**: `CAP_IPC_OWNER` bypasses permission
  checks on all System V IPC. It is disclosed in the plan as such, and reversed
  by `unapply`. This build has no gpsd socket driver (drivers compiled in:
  NMEA, LOCAL, GENERIC and SHM), and the NMEA driver would contend with gpsd
  for the serial port, so SHM with this grant is the route.
- **No refclock line means gpsd's SHM is ignored** (measured: `ntpq -p` has no
  SHM peer today). `ntp-only` is today's unmodified state.
- **`tos minclock 4 minsane 3` stops a lone GPS disciplining the clock**
  (documented, with Debian's comment above the line). *Bench*: whether a later
  `tos minsane 1` in `ntp.d/` overrides it, which would avoid editing the
  conffile. If it does not, the line is commented out with a Hammunition
  marker and restored exactly by `unapply`. The documented cost of minsane 1
  is quoted in §6.
- **"Network preferred" is not guaranteed by the docs.** `prefer` is a tie
  breaker ("all other things being equal"), and a stratum-0 refclock may win
  over stratum-2 servers. *Bench*: measure the selection with the refclock
  `stratum` raised (e.g. to 10) and the pools `prefer`red, network up and down.
  If the documented options cannot make the network win while it is
  reachable, `auto` becomes "GPS and network together, the daemon choosing",
  and the docs say so rather than claiming a preference that is not there.
- **`gps-only` must disable the `pool` lines themselves.** `restrict nopeer`
  no longer blocks pool associations (documented: "they now poke a hole in any
  restrictions"), and nothing in an include file can mark an existing pool
  `noselect`. `gps-only` comments them out with the marker; any other mode
  restores them exactly.
- **A config change needs `systemctl restart ntpsec`.** SIGHUP does not reread
  the configuration (documented). The runtime `ntpq :config` path is marked
  experimental with a silent-failure mode, so it is not used.
- **Readable unprivileged:** `ntpq -p` (peers, `reach`, `when`) and
  `ntpq -c rv` (`reftime`, `clock`, the `sync_*`/`sys_peer` status). Time
  since the last sync is `clock − reftime`. That is what `time` and `doctor`
  report.

Therefore:

1. **One file of Hammunition's own**,
   `/etc/ntpsec/ntp.d/hammunition-gps.conf` (the directory created if absent),
   holding the refclock line and the selection options for the current mode,
   rewritten whole by the root helper when the mode changes. Its content is
   generated from the mode only, never from free text.
2. **Two small grants, installed by `hardware apply` and reversed by
   `unapply`**, both disclosed: the systemd drop-in
   `/etc/systemd/system/ntpsec.service.d/hammunition-gps.conf`
   (`AmbientCapabilities=CAP_IPC_OWNER`) and the AppArmor local rule
   `capability ipc_owner,` in `/etc/apparmor.d/local/usr.sbin.ntpd` (the file
   Debian reserves for local additions; reloaded with `apparmor_parser -r`).
   The `ntp.conf` conffile is edited only where §4b's bench result requires it,
   each edit marked and reversed exactly.
3. **`auto`** (default): the refclock present with its `stratum` raised and
   a `time1` for NMEA latency, the network servers `prefer`red. Whether that
   makes ntpsec follow the network while reachable is a *bench* measurement
   (§4b); the docs claim only what it shows.
4. **`prefer-gps`**: the refclock `prefer`red, the network servers kept.
5. **`ntp-only`**: the file holds no refclock.
6. **`gps-only`**: the refclock, and the `pool` lines in `ntp.conf` disabled
   while the mode holds (commented with the Hammunition marker, restored
   exactly when the mode changes or on `unapply`). Measured: no include-file
   route exists (§4b).
7. **Device parked**: nothing is rewritten. A parked receiver's SHM segment
   stops updating; ntpd's reach register for it decays and it drops out of
   selection with no restart (inferred from the documented reachability model;
   *bench*: confirmed with the receiver parked). On wake it resumes. The rule "GPS off → GPS time no" holds by
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

**The docs recommend a battery-backed hardware clock (RTC), strongly and
up front** (the maintainer, 2026-09-28): it is what carries the time across a
power-off with neither the network nor the GPS, and nothing in software
replaces it. The operator guide says so first, and `doctor` flags a machine
with no RTC as a timekeeping weakness, naming the fix: fit an RTC module
(Raspberry Pi: a supported RTC HAT or the Pi 5's own battery connector with a
battery fitted). `fake-hwclock` is a fallback, not a substitute: it restores
the last saved time, which is wrong by however long the machine was off.

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

The helper `hammunition-devctl` gains one verb,
`time mode auto|prefer-gps|ntp-only|gps-only`: a fixed enum; the ntp.d file's
content generated from it; the `pool`-line edit for `gps-only` done by an
anchored, marker-tagged rewrite of `/etc/ntpsec/ntp.conf` that refuses if the
anchors are not found; each path a constant admitted by its own exact-path
guard (the kept-off pattern, `_guard_kept`); a fixed argv for the ntpsec
restart. No new polkit action. The capability drop-in and AppArmor rule are
installed by `hardware apply` (sudo, disclosed), not by the helper, so the
helper never widens a daemon's privileges. Reading state needs none.

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
