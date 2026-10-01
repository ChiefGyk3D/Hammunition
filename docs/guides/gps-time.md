<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# GPS time: keeping the clock right when the network is gone

With the internet up, ntpsec keeps the laptop's clock right from network
time servers. At a field site or on a served agency's deployment with no
internet, nothing corrects it, and it drifts. This guide sets the clock to
follow your GPS receiver when the network is not there, shows how to read
what the clock is following, and how to take all of it back out. The
decision record behind it is **D-058** in `docs/DECISIONS.md`.

> **Status.** Built and tested in containers and fakes; **not yet run on
> the field laptop**. Where a behaviour below depends on that bench run, it
> says so. `docs/reference/bench-verification-5430.md` is where the results
> will be recorded.

## 1. First: fit a battery-backed hardware clock (RTC)

Before any of the rest: a **battery-backed hardware clock (RTC)** is what
carries the time across a power-off when there is neither network nor GPS,
and nothing in software replaces it. Most laptops have one. Check:

```bash
ls /sys/class/rtc
```

`rtc0` (or any entry) means you have one; the kernel writes the
synchronised time back to it every eleven minutes, so what it holds is the
last good time. **An empty directory means you do not**, which is the usual
case on a Raspberry Pi. `hammunition doctor` warns about it. The fix is
hardware: a supported RTC HAT, or on a Raspberry Pi 5 a battery fitted to
its own RTC connector.

On a machine with no RTC, `hammunition hardware apply` offers
`fake-hwclock` from the archive. It saves the time at shutdown and hourly
and restores it at boot. It is a stopgap, not a substitute: the time it
restores is wrong by however long the machine was off. It is never offered
where a real clock exists. `sudo apt remove fake-hwclock` removes it.

## 2. Why it matters

- **Weak-signal modes.** FT8 and its relatives stop decoding once the clock
  is off by more than about a second.
- **Logs.** Every QSO, message and net log carries a time; a wrong clock
  makes them wrong.
- **EMCOMM.** The station clock is the one everybody else trusts.

## 3. Setting it up

GPS time works only where the time daemon is **ntpsec** (Parrot's default).
It needs a GPS receiver the catalog knows (`docs/hardware/gps-receiver-class.md`)
and gpsd, which the `navigation` profile installs.

```bash
hammunition hardware apply --dry-run   # read every change first
hammunition hardware apply
```

Besides udev rules and the power-control helper, `hardware apply` changes
these, and prints each one before it runs:

| What | Why | Inspect | Reverse |
|---|---|---|---|
| `/etc/systemd/system/ntpsec.service.d/hammunition-gps.conf` — `AmbientCapabilities=CAP_IPC_OWNER` | gpsd writes the time into shared memory only root can read; ntpd runs as the `ntpsec` user | `systemctl cat ntpsec` | `hammunition hardware unapply` |
| `/etc/systemd/system/gpsd.service.d/hammunition-gps.conf` — `Environment=OPTIONS=-n` | gpsd reads the receiver, and publishes its time, only while some program is connected to it; `-n` makes it poll the receiver continuously, so ntpd always has time to read. The same file and text as the `chrony` unit writes. gpsd takes it at the next boot | `systemctl cat gpsd`, then after a reboot `ps -o args= -C gpsd` shows `-n` | `hammunition hardware unapply`, unless the `chrony` unit still uses it |
| `capability ipc_owner,` added to `/etc/apparmor.d/local/usr.sbin.ntpd` (the file Debian keeps for local additions), and ntpd's profile reloaded | AppArmor must allow the same capability | `cat /etc/apparmor.d/local/usr.sbin.ntpd` | `hammunition hardware unapply` removes only that block |
| `/etc/ntpsec/ntp.d/` created | ntpd reads `*.conf` here after `ntp.conf` | `ls /etc/ntpsec/ntp.d` | left in place, empty |
| The first time mode, `auto`, set through the helper (the files in section 4) and ntpsec restarted | | `hammunition time` | `hammunition hardware unapply` |
| The GPS receiver's resume step: `/usr/local/libexec/hammunition-gps-resume` and `/etc/systemd/system/hammunition-gps-resume.service`, enabled for the four sleep targets | With `-n`, gpsd holds the receiver open all the time, so every suspend can leave it holding a tty that has gone quiet (issue #177). After each resume the step gives gpsd a fresh open of the receiver. See [After suspend](../hardware/power-control.md#after-suspend) | `systemctl cat hammunition-gps-resume`, `journalctl -u hammunition-gps-resume` | `hammunition hardware unapply` |

**Read this before you agree:** CAP_IPC_OWNER bypasses permission checks on
all System V IPC, not only gpsd's segment, and ntpd is a daemon that talks
to the network. That is the price of letting it read gpsd's time. If you
will not pay it, run `hammunition hardware apply --no-gps-time`: device
rules, groups and the power-control helper are set up, and ntpsec, its
grants and `fake-hwclock` are left alone. Without gpsd installed,
`hardware apply` leaves ntpsec alone by itself, since there is no GPS time to
read, and says so.

**A second cost, in every GPS mode:** the GPS modes turn off the
`tos minclock 4 minsane 3` line so a lone GPS can set the clock. ntpd's
`minsane` then falls to its default of 1, and one source can set the clock
alone. ntpsec's own manual (`ntp.conf(5)`) says minsane "should be at least
4 in order to detect and discard a single falseticker". Online, with four
pool servers and the GPS, that protection is weaker than Debian's default;
`ntp-only` keeps it. Both are printed in the plan before anything runs.

**Reboot after `hardware apply`.** gpsd reads its `-n` setting only when it
starts, and restarting a running gpsd in place left two gpsd processes in
testing. The receiver has to be polled continuously: without `-n`, gpsd
writes no time into the shared memory ntpd reads while nothing else is
asking it for a position (measured: no samples in 8 s without `-n`, nine
with it).

**On a laptop that sleeps, the resume step comes with the grants.** The
resume step is installed with them by the same `hardware apply`, wherever
gpsd is installed, and it is what keeps `-n` workable across a suspend:
measured on the field laptop (issue #177), the receiver is not re-enumerated
when the machine resumes, and a gpsd holding it open can stay silent until
something gives it a fresh open. `--no-gps-time` does not remove the resume
step, which also serves `cgps`, `xgps` and the map tether. To leave it out,
use `--no-gps-resume`. If the GPS is still silent after a resume, park and
wake the receiver by hand (`hammunition hardware park gps-receiver`, then
`wake`).

*Bench:* that ntpd keeps this capability after it drops to the `ntpsec`
user, so it can actually read the receiver, is the first thing to be
checked on the field laptop.

## 4. The four modes

| Mode | GPS awake: the clock follows | GPS parked |
|---|---|---|
| `auto` (default) | the network and the GPS together; the network is marked preferred | the network only |
| `prefer-gps` | the GPS first; the network is a check and the fallback | the network only |
| `ntp-only` | the network only; the GPS is never used | the network only |
| `gps-only` | the GPS only; network time servers are never used | nothing (holdover, below), and `doctor` warns |

Whether `auto` really follows the network while it is reachable is not yet
measured: ntpsec treats `prefer` as a tie-breaker, and a GPS can win over
network servers. Until the bench says otherwise, read `auto` as "ntpsec
chooses between the network and the GPS".

A **parked** receiver (`hammunition hardware park gps-receiver`) never feeds
the clock whatever the mode says; waking it brings GPS time back. A receiver
kept parked across reboots keeps GPS time off across reboots too. Nothing is
rewritten on a park: ntpd stops hearing the receiver and drops it by its own
rules (inferred from ntpsec's documentation, not yet watched on the bench).

Change the mode with:

```bash
hammunition time mode gps-only --dry-run   # every write, then stop
hammunition time mode gps-only
```

It asks for your password once through polkit, like park and wake. The mode
is remembered across reboots. What a mode change writes, all as root through
`/usr/local/libexec/hammunition-devctl`:

- `/etc/hammunition/time.yaml`: the mode, one line.
- `/etc/ntpsec/ntp.d/hammunition-gps.conf`: rewritten whole; the GPS line
  `refclock shm unit 0 refid GPS …`, absent in `ntp-only`.
- `/etc/ntpsec/ntp.conf`, marked lines only. A line Hammunition turns off
  starts `#hammunition-gps:off# `; a line it keeps while adding a preferred
  copy below starts `#hammunition-gps:was# `. In the GPS modes the
  `tos minclock 4 minsane 3` line is turned off (Debian's own comment above
  it says to, so a lone GPS can set the clock); in `gps-only` the `pool`
  lines are turned off too. Another mode or `hardware unapply` puts them
  back exactly.
- then `systemctl restart ntpsec`. If ntpsec will not start on the new
  files, the old ones are put back and ntpsec is started on them;
  `journalctl -u ntpsec -n 20` says why.

If you have edited those marked lines by hand, the mode change and
`hardware unapply` refuse, name the file and line, and change nothing.

## 5. Reading what the clock follows

```bash
hammunition time      # the mode, the receiver, what the clock follows
hammunition doctor    # includes the time and hardware clock checks
ntpq -pn              # ntpd's own view
```

None of these needs a password. In `ntpq -pn`, the row starting `*` is the
source the clock follows; `SHM(0)` with refid `.GPS.` is your receiver, and
its `reach` column counts up from 0 to 377 as ntpd hears it. Always use
`-n`: without it ntpq looks up every address in DNS, and with the network
down that hangs.

The `hammunition-tray` applet shows the same in its Time section and lets
you pick the mode, from its 0.4.0 (corrected 2026-10-01; the section shipped
one release later than first written here).

## 6. Holdover: when nothing sets the clock

With no network and no GPS (or `gps-only` with the receiver parked), the
clock keeps running on the hardware clock and on ntpsec's record of this
machine's own rate error (`/var/lib/ntpsec/ntp.drift`). `hammunition time`
says "Holdover since HH:MM UTC" and how long; `doctor` says it as
information for the first day and warns after that. When a source comes
back, ntpd corrects the clock. How far the laptop drifts in an hour of
holdover is *not yet measured*.

## 7. Accuracy

The receiver sends its time over USB as NMEA sentences, with no PPS line.
That is good to tens of milliseconds: plenty for FT8 and logging, not for
lab timing.

## 8. Security

With the network down and a GPS mode set, the clock follows one source. A
spoofed or faulty GPS could move it. Online, ntpsec weighs the GPS against
the network servers and outvotes a bad one. `ntp-only` never trusts the GPS;
`gps-only` never trusts the network. `hammunition doctor` always shows which
source the clock is following.

## 9. Undoing it

```bash
hammunition hardware unapply --dry-run
hammunition hardware unapply
dpkg --verify ntpsec        # expected: no line for /etc/ntpsec/ntp.conf (not yet measured on the bench)
```

`unapply` puts `ntp.conf`'s marked lines back exactly as they were before
Hammunition edited them (so, if you never edited it yourself, as the package
shipped it, which `dpkg --verify ntpsec` should confirm; not yet measured on
the bench), removes `/etc/ntpsec/ntp.d/hammunition-gps.conf`,
`/etc/hammunition/time.yaml` and the ntpsec drop-in (each only if it
carries the header Hammunition writes), removes gpsd's `-n` drop-in only if
it holds exactly Hammunition's text and the `chrony` unit's
`/etc/chrony/conf.d/hammunition-gps.conf` is absent (the two share it), takes only Hammunition's block out
of `/etc/apparmor.d/local/usr.sbin.ntpd`, reloads systemd and AppArmor, and
restarts ntpsec on the package's own configuration. It also disables and
removes the GPS resume step's unit and script, each only if it carries
Hammunition's header. `hardware apply` puts GPS time back.

## 10. Other targets

Debian 13, Ubuntu and Kali use `systemd-timesyncd` by default, which cannot
read a GPS. There, `hammunition time` and `doctor` say so and `time mode`
refuses by name. Hammunition does not switch your time daemon for you.
