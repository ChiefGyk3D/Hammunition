<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# The tray's Controls panel, and `hammunition services`

A field station spends most of its day with something running that nobody is
using: a GPS receiver drawing power, a cellular modem looking for a tower, a
Bluetooth controller, the service that serves your position to the map. This
guide is the one place that says how to switch those on and off, from the
tray or from a terminal, and what each switch asks of you.

Everything here is a front end for one small root helper,
`/usr/local/libexec/hammunition-devctl`, which belongs to
[hammunition-tray](https://github.com/ChiefGyk3D/hammunition-tray). The tray,
`hammunition hardware park`, `hammunition services` and the generated menu
entries all call that same helper through the same polkit action, so they
cannot disagree. Why that is safe, and what it writes, is
[Device power control](../hardware/power-control.md); this page is the
how-to.

## What you need first

1. **The engine's hardware step**, once:

    ```sh
    hammunition hardware apply --dry-run     # read it
    hammunition hardware apply
    ```

    It writes the two lists the helper reads, the devices it may park and the
    system services it may start and stop
    ([the helper's lists](../reference/devctl-lists.md)). Without them the
    tray shows no device switches and no system services.
2. **A tray, for your desktop.** The [`station`](../profiles/station.md)
   profile carries both; each defers itself by name on a desktop it does not
   serve ([Desktops](../desktops.md)).

    | Desktop | Install | Where the switches are |
    |---|---|---|
    | KDE Plasma | `hammunition install hammunition-tray` | the *Hammunition Devices* applet, added to the panel or the system tray by hand: nothing places it for you |
    | Xfce, LXQt, LXDE, MATE, Cinnamon | `hammunition install hammunition-tray-qt` | a tray icon with a menu |
    | GNOME, COSMIC | none yet | use the terminal commands below |

    Either unit also installs the helper and the polkit action, printed in
    the plan; the install asks one `yes` that `--yes` cannot answer when the
    engine's virtualenv belongs to a single account, and refuses when any
    account can write it.
3. **A polkit authentication agent running in your session**, which every
   desktop above provides. Without one the password prompt never appears; see
   [the pkexec note](../hardware/power-control.md#troubleshooting).

After installing, Plasma keeps the old applet loaded until
`systemctl --user restart plasma-plasmashell` or your next login.

## The Controls panel

One panel, three groups, worded the same on Plasma and in the Qt tray.

| Group | One row per | What a switch does |
|---|---|---|
| **Devices** | catalogued device that is attached and parkable: the GPS receiver, a cellular modem, a Bluetooth controller, a camera | *Park* detaches it so the kernel drops its interfaces and its port can suspend; *wake* brings it back. A device kept off across reboots reads "kept off"; one unplugged while kept offers *Forget* |
| **Services** | service the helper controls | a switch for *running* and a **Start at login** checkbox |
| **Radios** | mobile broadband (WWAN), Wi-Fi, Bluetooth | switches your session's own radio, the way `nmcli radio` and `bluetoothctl power` do |

The Time section below the groups is the GPS clock's mode, covered in
[GPS time on ntpsec](gps-time.md#4-the-four-modes).

**Which services appear.** The helper's allow-list: `gpsd` (the GPS daemon's
socket), `time` (ntpsec or chrony, whichever your machine has),
`gps-resume` (re-adds the receiver to gpsd after a suspend), and any user
service a catalog unit registered: `gps-tether` once you have
[installed the tether](offline-navigation.md#run-it-as-a-service), and `rig`
once you have installed `rig-service` ([Rig control](rig-control.md)). A
service whose unit is not installed is still listed, says *not installed* and
cannot be switched, so you can tell "off" from "never installed".

### Which switch asks for a password

Reading is never privileged: the panel polls the helper every few seconds
with no prompt. Changing something:

| You switch | Password prompt |
|---|---|
| a device (park, wake, forget) | one polkit prompt |
| the clock's mode | one polkit prompt |
| a **system** service, running or at login (`gpsd`, `time`, `gps-resume`) | one polkit prompt |
| a **user** service, running or at login (`gps-tether`, `rig`) | none: it is `systemctl --user` as you |
| a radio | none: polkit already lets your active session switch its own radios |

The prompt is `pkexec` showing the one action
`com.chiefgyk3d.hammunition.devctl`. Once you have authenticated, an active
session is not asked again for a short while (polkit's `auth_self_keep`), so
parking a device and waking it straight after asks once; the bench run below
saw exactly that. A dismissed or
refused prompt leaves the switch where it was: nothing was written.

A switch moves at once to what you asked for, and the next poll replaces that
with what the helper really reports. If the helper could not do it, the
switch goes back and its one line of reason is shown. While a command runs,
every switch is disabled.

### Update hammunition-tray

If a group says *update hammunition-tray*, the installed helper is older than
the panel (it answers contract 1's `services` and `radio` verbs only from
hammunition-tray 0.5.0). Re-run `hammunition install hammunition-tray` (or
`-qt`). If the whole panel says *Device control is not installed*, the helper
is missing: the same install puts it back.

## The same switches in a terminal

Every switch has a command, which is also what to use on GNOME, COSMIC or a
headless station.

| In the panel | In a terminal |
|---|---|
| a device | `hammunition hardware state`, `hardware park NAME`, `hardware wake NAME` ([power control](../hardware/power-control.md#the-verbs-and-their-exit-codes)) |
| the clock's mode | `hammunition time`, `hammunition time mode MODE` |
| a service | `hammunition services`, `services start\|stop\|enable\|disable NAME` |
| a radio | `nmcli radio wwan on\|off`, `nmcli radio wifi on\|off`, `bluetoothctl power on\|off` (the helper wraps exactly these; the engine has no verb for them) |

`hammunition services` lists each service and what it is doing:

```sh
hammunition services                      # the list; no password
hammunition services start gps-tether     # a user service: no password
hammunition services stop gpsd --dry-run  # print the helper call, then stop
hammunition services enable time          # a system service: one polkit prompt
```

- The engine asks the installed helper and **never runs `systemctl`
  itself**. It passes a *name* from the list, never a unit; the helper looks
  the unit up in `/etc/hammunition/devctl-services.yaml` (system) or
  `~/.config/hammunition/devctl-services.yaml` (your own).
- It reads the result back from the helper afterwards. A start that ends
  `failed`, a stop that leaves the service running, or an enable that does not
  read `enabled` is reported as unverified and exits `1`. A name the helper
  does not list, or a unit that is not installed, exits `2` before any prompt.
  A dismissed prompt exits `3`.
- `--json` is available on the list only, as a `services` document
  ([JSON interface](../reference/json-interface.md)); the four verbs change
  the machine and have no JSON form.

The full flag list is in the [command line reference](../reference/cli.md#hammunition-services-startstopenabledisable-name-dry-run-json).

## When it does not work

- **The switch does nothing and no prompt appears.** No polkit agent is
  running in your session, or you are on a bare SSH session. Run
  `hammunition hardware park NAME` from a desktop terminal instead; the
  [power-control page](../hardware/power-control.md#troubleshooting) explains
  exit 126 and 127.
- **`hammunition services` says the helper "has no `services` verb (it
  predates contract 1)".** An older helper is installed (for example the one
  `hardware apply` wrote in an earlier release). Run
  `hammunition install hammunition-tray` to bring in the current one, then
  check `/usr/local/libexec/hammunition-devctl --version`, which should print
  `hammunition-devctl contract 1`.
- **The Devices group is empty.** Nothing parkable is attached, or
  `hammunition hardware apply` has not written the devices list. Compare with
  `hammunition hardware state`, which reads the same.
- **A service shows *not installed*.** Its unit is not on this machine:
  `hammunition install gps-tether` or `rig-service`, or, for `time` on a
  machine whose daemon is `systemd-timesyncd`, see [Time and
  position](time-and-gps.md).
- **The clock modes are greyed.** The machine's clock daemon is not ntpsec
  (Debian 13, Ubuntu 24.04 and Mint ship `systemd-timesyncd`, which cannot
  read a GPS; Ubuntu 26.04 ships chrony, which the `chrony` unit configures,
  [Time and position](time-and-gps.md)); the panel says why.

## What was measured, and what was not

**Measured** (field laptop, 2026-09-27, bench session 10): parking and waking
a USB GPS receiver from the Plasma applet: one KDE password prompt for the
park, none for the wake inside the `auth_self_keep` window, gpsd releasing
the device and taking it back within a second, a 3D fix again 74 seconds after
the wake ([bench record](../reference/bench-verification-5430.md)). That run
used the engine's own copy of the helper and the applet before the Controls
panel and hammunition-tray 0.5.0's helper existed.

**Not measured.** The Controls panel itself, and everything under it: the
tray's helper with the `services` and `radio` verbs has been exercised
against fakes only, never against a real `systemctl`, NetworkManager or BlueZ
(and whether a modem ModemManager has disabled is still listed by `nmcli` is
open). The engine's install of the tray's helper as root on a real machine,
that Plasma lists an applet placed without a `.deb`, the polkit prompt for a
system service, the Xfce, LXQt, LXDE, MATE and Cinnamon trays, and every
park of a modem, a Bluetooth controller or a camera are all unrun. A device
kept off across a reboot, which the panel shows as "kept off", is built and
has not been rebooted on hardware. Treat each as an expectation from the
design until the bench page says otherwise.
