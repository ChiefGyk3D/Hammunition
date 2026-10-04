<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# When something is installed but misbehaves

## <a name="wayland"></a>A GUI comes up blank, or without window decorations

Ham GUI applications and Wayland do not always get along. The classic is
**WSJT-X on a Raspberry Pi**: it comes up with no border and no decorations
under Wayland. Other Qt applications may come up blank.

The reliable fix is to run an **X11** session instead of Wayland. On a
Raspberry Pi:

```
sudo raspi-config
  → 6 Advanced Options → A6 Wayland → W1 Openbox with X11 backend
  → reboot
```

On a desktop, choose an "on Xorg" session at the login screen. For a single
Qt application without switching the whole session, exporting
`QT_QPA_PLATFORM=xcb` before launching it often does the job.

This is accumulated operational knowledge — AHRL learned it over years and it
is captured here rather than rediscovered in the field. It is not a bug in the
software.

## <a name="dialout"></a>Permission denied on a serial device

```
could not open /dev/ttyUSB0: Permission denied
```

Serial devices (programming cables, CAT interfaces, GPS, TNCs) belong to the
`dialout` group. Profiles that touch serial hardware add you to it at install
— but **group membership only applies to a new login session.** Log out and
back in (or reboot), and the device opens.

Confirm you are in the group with `id -nG | tr ' ' '\n' | grep dialout`. If you
are, it is purely the stale-session problem; if you are not, the profile that
needed it was not installed.

## <a name="local-bin"></a>A venv-installed program is "not found"

Programs installed into a per-user virtualenv (not1mm, NanoVNASaver, and the
run-in-place Python units) get a small wrapper in `~/.local/bin`. Debian-family
shells add that directory to `PATH` **when it exists** — but a shell that was
already open before the first such install has the old PATH.

Open a new shell, or `source ~/.profile`. The wrapper is there; the shell just
has not looked since it appeared.

## <a name="config"></a>A program starts and immediately asks for a config file

```
CRITICAL: Config file station.cfg does not exist!
```

Some units (radiosonde-auto-rx is the example) install their whole tree but
need a station-local configuration you write once — location, upload
credentials, the things beyond the callsign/grid the engine already manages.
The program's page under [`docs/packages/`](../packages/index.md) says which
file and where; copy the shipped `*.example`, edit it, done. This is expected
first-run setup, not a broken install.

## <a name="linbpq-capabilities"></a>LinBPQ cannot open a network port

LinBPQ may need `CAP_NET_ADMIN` and `CAP_NET_RAW` for Ethernet/TUN interfaces,
and `CAP_NET_BIND_SERVICE` to bind ports below 1024. Hammunition does not grant
these during a normal install. If the consent gate was declined or unanswered,
LinBPQ is installed without them and the rest of the profile still installs.

Check the installed grant with:

```sh
sudo getcap /usr/local/bin/linbpq
```

No output means no capabilities are set. To opt in during an install, set the
variable to the exact grant shown by the plan:

```sh
HAMMUNITION_ACCEPT_CAPABILITIES_LINBPQ='CAP_NET_ADMIN=ep CAP_NET_RAW=ep CAP_NET_BIND_SERVICE=ep' \
  hammunition install linbpq
```

`--yes` does not answer this gate. A successful grant appears in `getcap`;
`hammunition uninstall linbpq` removes the capability Hammunition recorded.

## <a name="ax25"></a>"Address family not supported by protocol" from a packet program

```
kissattach: Address family not supported by protocol
OSError: [Errno 97] Address family not supported by protocol
modprobe: FATAL: Module ax25 not found in directory /lib/modules/7.1.5-…
```

Your kernel has no AX.25 stack. **Linux 7.1 removed it** — `net/ax25`,
NET/ROM, Rose and every `drivers/net/hamradio` driver, in one merge on
2026-04-24 — so on a 7.1 or newer kernel there is no `ax25` module to load and
nothing for `kissattach` to attach a TNC to. Check with:

```
uname -r
ls /lib/modules/$(uname -r)/kernel/net/ax25/
```

A directory with `ax25.ko` (or `.ko.xz`, `.ko.zst`) in it means the kernel
carries the stack and the module is merely not loaded yet — `sudo modprobe
ax25`, or run `kissattach` as root, which autoloads it. No such directory
means the kernel does not have it, and no package fixes that.

What still works: the **userspace** packet path. Direwolf's KISS and AGW ports
serve pat (`ax25+agwpe://`), LinBPQ, YAAC and Xastir's AGWPE interface with no
kernel AX.25 at all. What does not: `axports`, `kissattach`, `ax25d`,
`listen`, `mheard`, NET/ROM — everything in `ax25-tools` and `ax25-apps`, and
the programs that sit on them (`linpac`, `uronode`, `fbb`, `aprsdigi`).

Hammunition reads the running kernel at plan time and will refuse or defer
those units by name on such a kernel, so the usual way to meet this is
`hammunition install packet` on Kali (7.1.5) or a Pop!_OS machine on its
current kernel — and the plan says which members it withheld and why. The
measurements, and which units are affected, are in
[`docs/reference/kernel-ax25.md`](../reference/kernel-ax25.md). If you need a
kernel port, boot a kernel that still carries the stack: Debian 13's 6.12,
Parrot 7.3's 7.0, Ubuntu 26.04's 7.0. Hammunition does not build kernel
modules.

## <a name="brltty"></a>A CH340 serial device vanishes the moment it is plugged in

```
usb 1-3.2: ch341-uart converter now attached to ttyUSB0
usb 1-3.2: ch341-uart converter now disconnected from ttyUSB0
systemd[1]: Started brltty-udev.service - Braille Device Support.
```

`brltty`, the braille-display daemon, has claimed the device. Ubuntu and
Linux Mint install it by default (it is a Recommends of `ubuntu-desktop`,
`xubuntu-desktop` and the other desktop metapackages), and its udev rules
start it for the USB identifiers braille displays are built on. Once
started, brltty opens the "display" through libusb and detaches the kernel's
serial driver from it: the `/dev/ttyUSB*` node you were about to point
`flrig` or a Meshtastic client at is gone.

**Which machines, measured on the archive's own package** — the whole table
is [`docs/reference/brltty-inventory.md`](../reference/brltty-inventory.md):

- **Debian 13, Parrot, Kali:** brltty ships no udev rules at all. This
  cannot happen there.
- **Ubuntu 24.04 and Linux Mint 22.3** (brltty 6.6): one enabled rule
  names a chip in our catalog — the WCH CH340, `1a86:7523`, **only when it
  sits behind a `1a40:0101` hub** (the Terminus chip inside many cheap
  four-port hubs; it is what the Zoomax braille display is built on). The
  FTDI and CP210x lines that took every cable in 2022 are commented out,
  with the reason and the bug number beside them.
- **Ubuntu 26.04** (brltty 6.7): the CH340 line is commented out too.
- **Pop!_OS 22.04** (brltty 6.4, not a Hammunition target): the CH340 line
  is unqualified — every CH340 is claimed, hub or no hub.

Confirm it is this and not something else:

```
lsusb -t                              # is the CH340 under a 1a40:0101 hub?
journalctl -b -u brltty-udev.service  # did it start when you plugged in?
grep -n '1a86/7523' /usr/lib/udev/rules.d/85-brltty.rules /lib/udev/rules.d/85-brltty.rules 2>/dev/null
```

An uncommented `1a86/7523` line is the rule; a leading `#` means your brltty
does not do this and the cause is elsewhere.

**Fixes, in order of how little they change:**

1. **Plug the device straight into the machine**, or into a different hub.
   The rule needs the `1a40:0101` parent; without it, it does not fire.
2. **If nobody on this machine uses a braille display**, remove the package:
   `sudo apt remove brltty`. That is your call, not Hammunition's — the
   engine never removes accessibility software as a side effect of
   installing a radio program (**D-047**), and it never shadows the rules
   file the way some ham installers do, because that takes braille support
   away from a blind operator to fix a collision that exists for one chip
   behind one hub on two distributions.

Hammunition does not carry a rule against this today, because no target's
*default* brltty claims a catalogued identifier unconditionally. The day one
does again, the generated page above goes stale by name, and the shape of
the fix is a targeted rule for that one identifier, never the whole file.

## <a name="clock"></a>FT8 decodes nothing: check the clock

The waterfall shows traces, the band is busy, and the decode window stays
empty. The same happens to FT4, JS8 and WSPR. There is no error, because
nothing failed: the decoder looks for signals where its clock says each
time slot is, and **a clock more than about a second off finds nothing**.
Audio is the other cause ([the waterfall is silent](../getting-started/first-contact.md#when-the-waterfall-is-silent));
if you can see traces on the waterfall, check the clock first.

```
timedatectl
```

`System clock synchronized: yes` means a time daemon is keeping it right,
and the clock is not your problem. `no` means nothing is. Ask the daemon
you have what it follows (only one of these is installed):

```
timedatectl timesync-status     # systemd-timesyncd
chronyc -n tracking             # chrony: "System time" is how far off the clock is
ntpq -pn                        # ntpsec: the row starting * is the source in use
```

**With a network**, the daemon corrects the clock by itself within minutes
of the network coming up. If it has not, `sudo systemctl restart` the daemon
(`systemd-timesyncd`, `chrony` or `ntpsec`) and look again.

**With no network** nothing corrects it, and a laptop's clock drifts past a
second in days. A GPS receiver fixes that, by a route that depends on the
daemon ([Time and position](../guides/time-and-gps.md#with-no-network-a-gps-keeps-the-clock)
has the table):

- **systemd-timesyncd or chrony**: the [`chrony` unit](../packages/chrony.md)
  (**D-072**). timesyncd cannot read a GPS, so it is replaced, by you.
- **ntpsec** (Parrot, the field laptop): [GPS time](../guides/gps-time.md)
  through ntpsec (**D-058**).

Either way gpsd must be reading the receiver with nobody connected, which is
its `-n` option; without it the daemon gets no time from the GPS at all
([measured](../reference/time-daemons.md#5-gpsd-polls-the-receiver-only-for-a-client-unless-n)).

This entry is from the protocols' timing and the measurements linked above,
not from a decode failure watched on the bench.

## <a name="gps-after-suspend"></a>GPS dead after the laptop slept

The laptop was suspended with a GPS receiver plugged in. On resume, `cgps`
or `xgps` shows no fix: satellites stop updating, or the fix never comes
back, the map tether shows no position, and GPS time stops. Parking and
waking the receiver brings it back.

**Why.** A USB receiver is not re-enumerated across a suspend (measured
across 19 suspends on the field laptop, issue #177), so gpsd's hot-plug
never fires and gpsd can keep a tty that has gone quiet. It happens only
when something was watching across the suspend: a GPS client left open, or
gpsd running with `-n` for [GPS time](../guides/gps-time.md).

**Check whether the resume step is installed:**

```
hammunition doctor
systemctl status hammunition-gps-resume
```

`doctor`'s `gps-resume` line warns when a receiver is attached and the step
is missing. Install it with:

```
hammunition hardware apply
```

After each resume the step gives gpsd a fresh open of each `/dev/gpsN`
(`gpsdctl remove` and `add`), restarts gpsd if gpsd then reports no device,
and then watches gpsd for up to 20 s for a `SKY` or `TPV` report from the
receiver. Satellites without a fix yet count as alive; silence is the fault.
On silence it power-cycles the receiver once through its USB `authorized`
switch (the one `park` and `wake` use), waits for it to come back, makes sure
gpsd lists it, and watches again. The receiver starts cold after that, so a
fix can take a minute or more. Read what it did with:

```
sudo journalctl -b -u hammunition-gps-resume.service -u gpsd.service --since "-1h"
```

The lines you can see, in order: `data check: data from <tty> within N s` (all
well, nothing more happens); `data check: <tty> silent after 20 s`, then
`<tty>: silent; wrote 0 to .../authorized (USB power cycle, once)`, `wrote 1
to`, `re-enumerated`, `gpsd lists <tty>` (or `gpsdctl add` when it did not),
and `data check after the cycle: data from ...`. If that is silent too, the
unit fails and the last line reads `recovery failed: park and wake the
receiver ...`, which is the steps below. When the receiver's USB directory or
its `authorized` file cannot be found, the line says `no USB power cycle
possible` and gpsd is restarted instead.

**If it is still dead,** recover by hand, from least to most invasive,
stopping at the first that brings a fix back:

```
sudo gpsdctl remove /dev/ttyACM0 && sudo gpsdctl add /dev/ttyACM0
sudo systemctl restart gpsd.socket gpsd
hammunition hardware park gps-receiver
hammunition hardware wake gps-receiver
```

`/dev/ttyACM0` is the field laptop's receiver: `readlink -f /dev/gps0`
names yours. A 3D fix took 74 s from a wake on the bench. The resume step
already tries one power cycle itself when the receiver stays silent; these
steps are for when that failed or the step is not installed. Which of the steps a real suspend actually needs is not
yet measured: the bench steps are on issue #177. The step's files and how
to remove them are under [After suspend](../hardware/power-control.md#after-suspend).

## <a name="run-logs"></a>Where is the log of what just happened?

Every run that changes something, `--dry-run` included, writes a plain-text
log (**D-077**). The last line the run printed was `Log: <path>`; if the
terminal is gone, ask for it:

```
hammunition logs            # the list: when, which command, how it ended
hammunition logs --last     # print the newest in full
tail -f "$(hammunition logs --path)"    # follow a run that is still going
```

The log holds everything the run printed, each command it ran with that
command's output, exit code and duration, and a last `result` line. A run
that was killed has no `result` line and the list says `incomplete`; a run
still going says `running`. They live in `~/.local/state/hammunition/logs/`,
mode 0600, and the newest 30 (200 MB at most) are kept. For a run under
`sudo`, that is the invoking user's directory, not root's. The machine's
record of what was done, which `uninstall` uses, is the separate
`transactions.jsonl`. Details: [Run logs](../reference/run-logs.md).

## <a name="reticulum-no-instance"></a>`rnstatus` says "Could not get RNS status"

```
Could not get RNS status
```

`rnstatus` found a Reticulum instance to attach to and could not read its
status. The cause measured on 2026-10-03 is the one in the next entry: a
second `rnsd` (or any program started with a different configuration
directory) attached as a *client* to an instance whose RPC key it does not
hold, so it can serve programs but cannot be asked how it is doing. Check which
one owns the instance, and whether the one you meant to run is running at all:

```
systemctl --user status hammunition-rnsd
tail -n 20 ~/.reticulum/logfile
ss -xlp | grep rns
```

The last command lists the abstract sockets named `@rns/…` and the process
holding each. If the service is simply not running yet (it starts at your next
login after install), start it with `systemctl --user start hammunition-rnsd`.

## <a name="reticulum-another-instance"></a>Another Reticulum program owns the shared instance

`~/.reticulum/logfile` says:

```
Started rnsd version 1.5.6 connected to another shared local instance, this is probably NOT what you want!
```

A Reticulum instance was already running, so `hammunition-rnsd` did not fail
and did not start a second set of interfaces: it attached to the first. The
usual owners are Sideband, MeshChat or an `rnsd` you started by hand, and
another account on the same machine counts: the shared instance is a Unix
socket in the machine-wide abstract namespace (`@rns/default`), not a file in
anybody's home. Nothing loops and nothing is broken, but the interfaces in your
`~/.reticulum/config` are not the ones in use; the other instance's are.

Stop one of the two. Or give one of them its own name: upstream's example
configuration (`rnsd --exampleconfig`) documents an `instance_name` option under
`[reticulum]` for running several different shared instances on one system
(that route was not tried here). Restart the service afterwards:
`systemctl --user restart hammunition-rnsd`.

## <a name="reticulum-autointerface"></a>Two laptops running Reticulum do not see each other

`rnstatus` on each shows the AutoInterface up and no peers. Go in this order:

1. **Both services running, both on one network?** `systemctl --user status
   hammunition-rnsd` on each, and the same Wi-Fi network or the same switch.
2. **Link-local IPv6 enabled?** AutoInterface uses it to find peers and it is on
   by default in current systems. `ip -6 addr show scope link` should list an
   `fe80::` address on the interface you are using.
3. **A firewall?** Upstream says the interface uses UDP ports 29716 and 42671
   and that a firewall may need to allow them (its manual for 1.5.5). On a
   running instance in a Debian 13 container `ss -lun` showed 29716 on a
   multicast group address and 29717 (the unicast discovery port, the discovery
   port plus one) and 42671 on the interface's link-local address (measured
   2026-10-03).
4. **A network that does not pass traffic between its devices.** Upstream names
   very cheap ISP-supplied routers, and an access point set to isolate its
   clients does the same; some phone hotspots are reported to. Move to a
   switch or a cable between the two machines to rule it out.

If one of them cannot be made to work, a TCP link between the two
(`docs/guides/mesh-and-reticulum.md`, section 5) does not depend on multicast.

## <a name="rnodeconf-port"></a>`rnodeconf` cannot open the RNode's port

```
Permission denied: '/dev/ttyACM0'
```

(or `/dev/ttyUSB0`, whichever the board appeared as: `ls /dev/serial/by-id/`).
It is the same cause as any serial device: you are not in the `dialout` group
yet, or you are but the session predates it. [Permission denied on a serial
device](#dialout) has the fix: log out and back in. Two other things hold a
port: a device you parked with `hammunition hardware park` (`hammunition
hardware state` shows it, `hammunition hardware wake NAME` returns it), and
another program that has the port open, ModemManager among them on some
machines, as it does for other serial boards; [a CH340 serial
device that vanishes](#brltty) is a different cause with a similar look.
