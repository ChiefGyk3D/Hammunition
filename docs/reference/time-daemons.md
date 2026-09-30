<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Time daemons per target, and GPS time through chrony

**Measured:** 2026-09-29 (the archive sweep, the coexistence simulation) and
2026-09-30 (the metapackage simulation, the reference-clock runs), in
rootless Podman containers of the seven targets in `containers/targets.yaml`,
plus one read-only `dpkg` query on the field laptop. Hand-written, because
nothing here is regenerated from a probe file; every table says the command
that produced it.

**Why it was measured.** The gap analysis (`docs/reference/catalog-gaps-2026-09.md`,
§A4) asked for a `chrony` unit in `station` reading `gpsd`, displacing
`systemd-timesyncd` by disclosure, and Q-022 #3 ruled yes with *measure which
targets already ship chrony first*. Pull request #124 (D-058) had meanwhile
built GPS time through **ntpsec**, the daemon the field laptop runs. Two time
daemons on one machine fight, so which daemon each target actually has
decides what this catalog may carry. **D-071** in `docs/DECISIONS.md` is the
ruling taken from these tables.

## 1. What each archive offers

`scripts/apt-policy-sweep.sh` over `chrony ntpsec ntp systemd-timesyncd gpsd
python3-tk python3-venv`, one container per target, `apt-cache policy`
candidate. The `--all` run stopped at Kali because this machine's Podman has
no short-name alias for `kalilinux/kali-rolling`; Kali, Parrot and Mint were
then swept one at a time with `docker.io/`-qualified image names, and the
arm64 row with `HAMMUNITION_FOREIGN_ARCH=arm64` on `debian:13`.

| Target | chrony | ntpsec | ntp | systemd-timesyncd | gpsd |
|---|---|---|---|---|---|
| debian-13 | 4.6.1-3+deb13u2 | 1.2.3+dfsg1-8 | — | 257.13-1~deb13u1 | 3.25-5+deb13u2 |
| debian-13-arm64 | 4.6.1-3+deb13u2 | 1.2.3+dfsg1-8 | — | 257.13-1~deb13u1 | 3.25-5+deb13u2 |
| ubuntu-24.04 | 4.5-1ubuntu4.2 | 1.2.2+dfsg1-4build2 | 1:4.2.8p15+dfsg-2~1.2.2+dfsg1-4build2 | 255.4-1ubuntu8.17 | 3.25-3ubuntu3.2 |
| ubuntu-26.04 | 4.8-2ubuntu1 | 1.2.3+dfsg1-8ubuntu2 | — | 259.5-0ubuntu3.4 | 3.27.5-0.1 |
| linuxmint-22.3 | 4.5-1ubuntu4.2 | 1.2.2+dfsg1-4build2 | 1:4.2.8p15+dfsg-2~1.2.2+dfsg1-4build2 | 255.4-1ubuntu8.17 | 3.25-3ubuntu3.2 |
| kali-rolling | 4.9-1 | 1.2.5+dfsg-1 | — | 261.2-1 | 3.27.5-3 |
| parrot | 4.6.1-3+deb13u2 | 1.2.3+dfsg1-8 | 1:4.2.8p15+dfsg-2~1.2.3+dfsg1-3 | 257.13-1~deb13u1 | 3.25-5+deb13u2 |

Every target offers all three daemons. Where `ntp` exists it is a
transitional package that `Depends: ntpsec` (its version carries the ntpsec
version after the `~`). `python3-tk` and `python3-venv` have a candidate on
all seven, which is what the PyGPSClient unit needs.

## 2. Which daemon a machine ends up with

**The container images do not answer this.** A fresh image of every target
except Mint carries none of the three (`dpkg -l`); Mint's image carries
`systemd-timesyncd` 255.4-1ubuntu8.17. An installed system gets its daemon
from package priorities and from whichever metapackage is installed first, so
the question was asked of the archive: `apt-cache show` for the priority, and
`apt-get install --simulate <metapackage>` in the fresh image for which
daemon apt would pull in.

| Target | Priority in the archive | Metapackage simulated → daemon apt installs |
|---|---|---|
| debian-13 | timesyncd `standard`; chrony, ntpsec `optional` | `systemd` → timesyncd (its `Recommends: systemd-timesyncd \| time-daemon`); `task-desktop` → timesyncd |
| ubuntu-24.04 | timesyncd `important`; chrony `extra`; ntpsec `optional` | `ubuntu-minimal` → timesyncd; `ubuntu-desktop-minimal` → timesyncd |
| ubuntu-26.04 | **chrony `important`**; timesyncd, ntpsec `optional` | **`ubuntu-minimal` → chrony** (`Depends: chrony \| time-daemon`); `ubuntu-desktop-minimal` alone → timesyncd |
| linuxmint-22.3 | as ubuntu-24.04 | the image itself has timesyncd installed |
| kali-rolling | timesyncd `standard`; chrony, ntpsec `optional` | `kali-linux-core` → timesyncd; `kali-desktop-xfce` → timesyncd; `kali-linux-default` alone → ntpsec |
| parrot | timesyncd `standard`; chrony, ntpsec `optional` | `parrot-core` → none; `parrot-desktop-kde` → none; **`parrot-tools-full` → ntpsec** |
| field laptop, Parrot 7.3 | — | **ntpsec 1.2.3+dfsg1-8 installed, automatically**; `apt-cache rdepends --installed --recurse ntpsec` reaches it through `netsniff-ng` → `parrot-tools-sniff` → `parrot-tools-full`; `systemd-timesyncd` and `chrony` not installed |

Read with care: a simulation in an empty image says which daemon apt picks
when *nothing* satisfies `time-daemon` yet. On a real install the first
package to need one wins, so where two metapackages disagree (Kali's
`kali-linux-core` and `kali-linux-default`, Ubuntu 26.04's `ubuntu-minimal`
and `ubuntu-desktop-minimal`) what an installed machine has depends on the
installer's order, which was **not measured**. The field laptop is the only
installed system read, and it runs ntpsec.

In short: **ntpsec** on Parrot's security edition (and on a Kali whose
`kali-linux-default` came first, unmeasured); **chrony** on Ubuntu 26.04
through `ubuntu-minimal`; **systemd-timesyncd** on Debian 13, Ubuntu 24.04,
Mint 22.3 and a Kali installed core-first.

## 3. The three cannot coexist

Every one of the three `Provides: time-daemon` and `Conflicts: time-daemon`
in all six target images (`apt-cache show`, 2026-09-29; the arm64 row
shares Debian 13's archive and was not asked separately). On `debian:13` with
`systemd-timesyncd` installed first:

```
$ apt-get install --simulate ntpsec        $ apt-get install --simulate chrony
Remv systemd-timesyncd [257.13-1~deb13u1]  Remv systemd-timesyncd [257.13-1~deb13u1]
Inst ntpsec (1.2.3+dfsg1-8 ...)            Inst chrony (4.6.1-3+deb13u2 ...)
```

With `--no-remove` both end `E: Packages need to be removed but remove is
disabled.` With ntpsec installed, `apt-get install --simulate chrony` prints
`Remv ntpsec [1.2.3+dfsg1-8]`. So apt itself never lets two of these daemons
share a machine: installing one *is* removing the other. This engine refuses
any transaction whose simulation removes a package (D-022, amended
2026-09-07) and runs apt with `--no-remove`, so a unit that installs a time
daemon is refused, by name, on every machine that already has a different
one.

## 4. chrony reading gpsd: what was run

All on `debian:13`, chrony 4.6.1-3+deb13u2 and gpsd 3.25-5+deb13u2 from the
archive, `chronyd -x` (it never touches the clock) with `-u _chrony` (the
package's own privilege drop). No receiver: a small script served
`$GPRMC`/`$GPGGA`/`$GPGSA` with the container's current UTC time once a
second on `tcp://127.0.0.1:2000`, and gpsd read that. This proves the
plumbing between gpsd and chrony; **it says nothing about a real receiver's
accuracy**, because the "receiver" is the container's own clock.

| What | Result |
|---|---|
| `refclock SHM 0 refid GPS poll 2 delay 0.2`, chronyd started first | `#* GPS` selected, reach 377, within 40 s |
| the same, gpsd started first | `#* GPS` selected, reach 377 |
| segment ownership (`ipcs -m`) | `0x4e545030` (unit 0) and `0x4e545031` owned by root, mode 600; chronyd attaches before it drops to `_chrony`, so no grant was needed |
| the chrony package's own `chrony.conf` with that line in `/etc/chrony/conf.d/hammunition-gps.conf` | `#* GPS` selected, reach 377 (network `pool` lines commented out for the run) |
| `confdir /etc/chrony/conf.d` present in the shipped `chrony.conf` | yes in all six target images, chrony installed in each; `chrony.service` carries `Alias=chronyd.service` in all six (arm64 not run) |
| `refclock SOCK /run/chrony.clk.<device>.sock` | **not measured.** chronyd created the socket, but gpsd could not open a pseudo-terminal under rootless Podman (`Permission denied` even at mode 0666 and with `--privileged`), and for a network source gpsd opens no chrony socket at all |

**SHM or SOCK.** chrony's manual (`chrony.conf(5)`, from the Debian 13
package) says the SHM driver "is deprecated in favor of SOCK", because a
shared-memory segment "needs to be created before untrusted applications or
users can execute code to prevent an attacker from feeding chronyd with false
measurements". It also says SOCK's path names the serial device
(`chrony.clk.ttyUSB0.sock`, per `gpsd(8)`) and that "gpsd needs to be started
after chronyd". A USB receiver is `ttyACM0` on one machine and `ttyUSB1` on
the next, so a SOCK line has to guess the device, and the SOCK route was
not made to work here. SHM unit 0 is whatever receiver gpsd opened first,
needs no device name and no start order, and is the route that ran. The unit
uses SHM and says why; the attack the manual describes needs code running on
the machine before chronyd starts at boot.

## 5. gpsd polls the receiver only for a client, unless `-n`

`gpsd(8)`: `-n` "Don't wait for a client to connect before polling whatever
GPS is associated with it … You should use this option if you plan to use
gpsd to provide reference clock information to ntpd or chronyd." Measured,
`ntpshmmon` counting unit-0 samples with no gpsd client connected:

| gpsd started as | device given | samples |
|---|---|---|
| `gpsd` | on the command line | 0 in 8 s |
| `gpsd -n` | on the command line | 9 in 8 s |
| `gpsd` | added over the control socket with `gpsdctl add`, as `gpsdctl@.service` does on hotplug | 0 in 8 s |
| `gpsd -n` | added with `gpsdctl add` | 9 in 8 s |

Debian's `/etc/default/gpsd` ships `GPSD_OPTIONS=""`, and so does the field
laptop's (read, not changed). `gpsd.service` runs
`/usr/sbin/gpsd $GPSD_OPTIONS $OPTIONS $DEVICES` with
`EnvironmentFile=-/etc/default/gpsd`, and that file sets no `OPTIONS`, so a
drop-in at `/etc/systemd/system/gpsd.service.d/hammunition-gps.conf` holding
`Environment=OPTIONS=-n` adds the flag without touching gpsd's conffile.
Measured in a `debian:13` container booted with systemd: with the drop-in in
place before gpsd first starts, the socket-activated gpsd ran as
`/usr/sbin/gpsd -n` and published 7 samples in 6 s, with no client. Writing
the drop-in while gpsd was already running and then `systemctl restart
gpsd.service` left two gpsd processes and no samples, so a restart in place
is **not** the documented route; a reboot, which starts gpsd with the
drop-in already there, is.

This matters to D-058 as much as to chrony: ntpsec's `refclock shm unit 0`
reads the same segment, and on a machine where nothing holds a gpsd client
open it will read nothing. Whether the field laptop's gpsd has a client
connected is not measured here.

## 6. Not measured

- The installer order on Kali and Ubuntu 26.04 (section 2), and so which
  daemon an installed Kali or Ubuntu 26.04 really has.
- The SOCK refclock (section 4).
- Anything with a real receiver: chrony's offset from UTC through NMEA over
  USB, how `delay 0.2` weighs the GPS against network servers when both are
  reachable, and chrony's AppArmor profile on a host (a container enforces
  none). The last one is the first thing to check on a machine with
  chrony: `journalctl -u chrony` for an `apparmor="DENIED"` on the segment.
- `chrony.service` itself: it carries `ConditionCapability=CAP_SYS_TIME`,
  which a rootless container does not have, so every run above started
  `chronyd -x` by hand.
