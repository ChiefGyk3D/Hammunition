<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Desktops: what works where

Hammunition installs radio software. Almost all of it does not care which
desktop you run: a decoder, a rig control daemon or a logger is the same
program under KDE Plasma, Xfce or no desktop at all. Three things do care,
and this page says what is known about each of them on each desktop:

- **the menu** that `hammunition menus apply` builds (*Hammunition* →
  eight groups → one submenu per category, D-050);
- **the tray**, the switch that parks and wakes a GPS or a modem (D-056);
- **what `station` costs**, which matters on a low-powered machine.

**The order is Parrot OS with KDE Plasma first.** That is the field laptop,
and it is where things are measured before anywhere else. Other desktops are
welcome, and Xfce and LXQt are next, because they are what a low-powered
machine usually runs. Where a row below says *unmeasured*, it means nobody
has run it yet. It is not a promise and it is not a known failure. The
checklist those runs will follow is `docs/reference/vm-campaign-desktops.md`.

The decision record behind this page is **D-060** in `docs/DECISIONS.md`.

---

## How Hammunition tells which desktops you have

It reads the session files your login screen lists, in
`/usr/share/xsessions/` and `/usr/share/wayland-sessions/`. Each one names
its desktop in a `DesktopNames=` line (`KDE`, `XFCE`, `LXQt` and so on).
LXDE's and Cinnamon's session files carry no such line, so those two are
recognised by file name instead: `LXDE.desktop`, and `cinnamon.desktop`,
`cinnamon2d.desktop` or `cinnamon-wayland.desktop`.

Session files are on disk, so the answer is the same under `sudo` as
outside it. The desktop you are *logged into* (`$XDG_CURRENT_DESKTOP`) is a
different question, and `sudo` usually drops that variable. The installer
never uses it. `hammunition doctor` shows both:

```console
$ hammunition doctor
...
  [·] desktops       session files offer KDE Plasma, Xfce; this session is KDE Plasma
...
```

A container or a server has no session files at all, and that is reported
as none.

### A unit for one desktop

A few catalog units only make sense on one desktop, and their manifest says
which (the `desktops` field). Today there is one: `hammunition-tray`, the
Plasma applet. Its package depends on `plasma-workspace`, which is the
whole Plasma shell, so installing it on an Xfce machine would drag Plasma
in behind it.

So when a machine has no session for any desktop the unit is for:

- **In a profile** (`hammunition install station`), the unit is **deferred
  by name** and the rest of the profile installs. The plan prints it under
  *Will NOT happen*, with the desktops it read:

  ```text
  Desktops read from session files (/usr/share/xsessions, /usr/share/wayland-sessions):
    Xfce

  Will NOT happen (the rest of the transaction still will):
    hammunition-tray: will not be installed (profile station)
        why: for KDE Plasma; this machine has no KDE Plasma session (it has: Xfce)
        → the rest installs without it; on a machine that gains a KDE Plasma session,
        `hammunition install station` again picks it up
  ```

  `hammunition status` keeps showing the deferral until the next install.
- **By name** (`hammunition install hammunition-tray`), it is **refused**
  with the same reason and what to do instead. Asking for a thing by name
  is asking to see why it cannot install.

If you install Plasma later, run the same `hammunition install station`
again. It picks the applet up and leaves everything else as it is.

---

## The desktops

### KDE Plasma (Parrot OS): first, and measured

| | |
|---|---|
| **Menu** | Measured on the field laptop, 2026-09-12. `menus apply` writes the tree to `applications-merged/` (KDE ignores the menu prefix) and runs `kbuildsycoca6` so it shows immediately (D-050). |
| **Tray** | `hammunition-tray`, a Plasma applet. Measured on the field laptop. It installs with `station` on a machine that has a Plasma session. |
| **Lightweight notes** | Plasma is the heaviest desktop on this page, and the one everything is tested on first. |

### Xfce (Xubuntu, Kali, Parrot's alternative)

| | |
|---|---|
| **Menu** | The menu-spec path, into `xfce-applications-merged/`. Measured on the Kali VM for the earlier one-level tree (2026-09-02). The grouped tree is the same mechanism and **has not been re-run there**. |
| **Tray** | **None yet.** The Plasma applet is deferred. A Qt tray for this panel is planned (`hammunition-tray-qt`), and nothing is claimed about it until it exists and has run. |
| **Lightweight notes** | `station` no longer pulls in Plasma here (D-060). Idle memory before and after `station` is **unmeasured**, and is on the Xubuntu 26.04 checklist. |

### LXQt (Lubuntu)

**Lubuntu has been LXQt, not LXDE, since 18.10**, so testing Lubuntu tests
LXQt.

| | |
|---|---|
| **Menu** | **Unmeasured.** Debian 13's `lxqt-menu-data` ships `/etc/xdg/menus/lxqt-applications.menu` with `<DefaultMergeDirs/>`, so the file `menus apply` writes to `lxqt-applications-merged/` is one the spec says it reads. Whether LXQt's panel menu shows it is what the Lubuntu 26.04 run will find out. |
| **Tray** | **None yet.** The Plasma applet is deferred. The planned Qt tray is meant for this panel. |
| **Lightweight notes** | Qt is already installed, so a Qt tray adds little. Idle memory is **unmeasured**, and is on the Lubuntu 26.04 checklist. |

### LXDE

Plain LXDE is still in Debian (`openbox-lxde-session`). No current Ubuntu
flavour ships it.

| | |
|---|---|
| **Menu** | **Unmeasured.** `lxmenu-data` ships `/etc/xdg/menus/lxde-applications.menu` with `<DefaultMergeDirs/>`. |
| **Tray** | **None yet.** lxpanel's tray is the older XEmbed kind, which the planned Qt tray is meant to fall back to. Nothing has run. |
| **Lightweight notes** | The lightest desktop on this page. **Unmeasured** here. |

### GNOME (Debian 13, Ubuntu)

| | |
|---|---|
| **Menu** | GNOME cannot nest menus. The equivalent is one app folder per visible group. The code and tests exist, and the Debian 13 VM run **has not happened yet** (D-050). |
| **Tray** | **None.** GNOME's panel has no system tray without an extension. The planned Qt tray does not list GNOME, because an icon that never appears is worse than saying so. |
| **Lightweight notes** | Not a lightweight desktop. |

### MATE

| | |
|---|---|
| **Menu** | **Unmeasured.** `mate-menus` ships `/etc/xdg/menus/mate-applications.menu` with `<DefaultMergeDirs/>`, and Parrot's `/etc/xdg/menus` carries a `mate-` root. |
| **Tray** | **None yet.** The planned Qt tray lists MATE. |
| **Lightweight notes** | **Unmeasured.** |

### Cinnamon (Linux Mint)

| | |
|---|---|
| **Menu** | **Unmeasured.** `cinnamon-common` ships `/etc/xdg/menus/cinnamon-applications.menu` with `<DefaultMergeDirs/>`. |
| **Tray** | **None yet.** The planned Qt tray lists Cinnamon. |
| **Lightweight notes** | **Unmeasured.** |

### COSMIC (Pop!_OS)

| | |
|---|---|
| **Menu** | **Unmeasured.** COSMIC's app library does not use the menu spec, and nobody has read how it groups apps (D-036, D-050). |
| **Tray** | **None.** |
| **Lightweight notes** | **Unmeasured.** |

The menu roots quoted above for LXQt, LXDE, MATE and Cinnamon were read
from the Debian 13 packages (`apt-get download`, then `dpkg-deb -c` and
`-x`) on 2026-09-28. That tells you which file the spec says a desktop
reads, and nothing about what its panel draws.

---

## Choosing a desktop for a low-powered machine

Pick whichever one you are comfortable with. Nothing in the radio software
depends on the choice. If the machine is short of memory, LXQt and Xfce are
the two this project will measure first. Until those runs happen, this page
cannot give you numbers, and it will not guess.
