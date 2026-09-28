# More desktops: Xfce and LXQt welcomed, Plasma first, a unit for one desktop deferred on the others

**Status:** direction approved by the maintainer 2026-09-28 ("work through
1-3"; the VM runs come later). **Decision record:** D-060, written with the
implementation. **Extends:** D-036 and D-050 (menus per desktop), D-039
(deferral by name), D-056 (the tray is a client of one helper).

**Origin:** the maintainer, 2026-09-28: "Do we have Xfce and lxde support
built in? Maybe we should add those in so we have lower powered systems be
able to use this project. We can test against Xubuntu and Lubuntu … for
simplicity while we test against those we are Parrot OS and KDE first … but
we want to welcome more environments."

## 1. What was measured before this was written

- **Lubuntu is LXQt, not LXDE**, and has been since 18.10. Testing Lubuntu
  tests LXQt. Plain LXDE is still in Debian (`openbox-lxde-session`), and no
  current Ubuntu flavour ships it.
- **The engine is desktop-independent** except for three things: the menu
  (per-mechanism, D-036/D-050), the tray (a Plasma applet only), and
  `station`, which includes `hammunition-tray` unconditionally. On Xubuntu or
  Lubuntu, `station` therefore pulls `plasma-workspace`, the whole Plasma
  shell, which is the opposite of what a low-powered machine wants. That is
  a defect, and this work fixes it.
- **Which desktops a machine has** is readable from the session files every
  display manager lists, `/usr/share/xsessions/*.desktop` and
  `/usr/share/wayland-sessions/*.desktop`. They survive `sudo`, unlike
  `XDG_CURRENT_DESKTOP`. Read from the Debian 13 packages (`apt-get download`
  plus `dpkg-deb -x`, 2026-09-28) and from the field laptop:

  | Session file | Package | `DesktopNames=` |
  |---|---|---|
  | `plasma.desktop`, `plasmax11.desktop` | plasma-workspace | `KDE` (field laptop) |
  | `xfce.desktop`, `xfce-wayland.desktop` | xfce4-session | `XFCE` |
  | `lxqt.desktop` | lxqt-session | `LXQt` |
  | `mate.desktop` | mate-session-manager | `MATE` |
  | `gnome.desktop`, `gnome-wayland.desktop` | gnome-session(-xsession) | `GNOME` |
  | `LXDE.desktop` | openbox-lxde-session | **none** (Exec `/usr/bin/startlxde`) |
  | `cinnamon.desktop`, `cinnamon2d.desktop`, `cinnamon-wayland.desktop` | cinnamon-common | **none** |

  So `DesktopNames` is read first, and a file without one falls back to a
  table keyed by its filename stem, holding exactly the two measured gaps:
  `LXDE` → lxde, `cinnamon`, `cinnamon2d`, `cinnamon-wayland` → cinnamon.
  Anything else without the key (`lightdm-xsession`, `openbox`) is not a
  desktop we name and is ignored.

## 2. Desktop detection (engine)

A new module `src/hammunition/desktop.py`:

- `Desktop`: a `StrEnum` of `kde`, `gnome`, `xfce`, `lxqt`, `lxde`, `mate`,
  `cinnamon`. `DesktopNames` values map case-insensitively: `KDE` → kde,
  `GNOME` → gnome, `XFCE` → xfce, `LXQt` → lxqt, `LXDE` → lxde, `MATE` →
  mate, `X-Cinnamon`/`Cinnamon` → cinnamon. The key is `;`-separated, as in
  the desktop-entry spec (`GNOME;GNOME-Classic`): any recognised element
  counts, and an unrecognised one is ignored.
- `installed_desktops(root: Path = Path("/")) -> frozenset[Desktop]` reads
  both session directories under `root`. A directory that is absent is not
  an error: a container or a server has none, and returns an empty set.
- `current_desktop(environ) -> Desktop | None` from `XDG_CURRENT_DESKTOP`,
  used only where the session matters (menus, doctor), never by the planner.

## 3. A unit for one desktop (schema and plan)

- Manifest field **`desktops: list[Desktop] | None`**, default `None`
  (meaning any, which is every existing unit). Documented in the schema like
  every other field, with a validator that the list is non-empty and has no
  duplicates.
- **Plan, as a profile member:** a unit whose `desktops` shares nothing with
  `installed_desktops()` is **deferred by name** through the D-039 path, with
  the reason `for <Plasma>; this machine has no <Plasma> session (it has:
  Xfce)` (or `(it has none)`), and the rest of the profile installs. The
  deferral is logged and shown by `status` like every other deferral.
- **Plan, typed by name:** the same condition **refuses** with that reason
  and a remedy, consistent with D-039's rule that a name the operator typed
  still refuses. The remedy names the unit that serves the machine's desktop
  when the catalog has one: a manifest may name it in `desktop_alternative:
  <unit>` (optional, validated to exist, and to have `desktops` disjoint from
  this unit's).
- `--dry-run` shows the deferral and the desktops that were read, so the
  decision is visible before anything runs.
- A machine with a desktop installed later: re-running `install station`
  picks the unit up, and that is the whole story (idempotent).

## 4. The tray for other desktops (hammunition-tray repository)

Separable, per the family's rule: it lives in the **same repository** as the
Plasma applet, because it is the same switch for a different panel, and it
ships as a **second binary package, `hammunition-tray-qt`**, from the same
release and version. The Plasma applet is unchanged.

- **Python 3 + PyQt6 `QSystemTrayIcon`.** `python3-pyqt6` is in Debian 13
  (6.9.0) and Ubuntu 24.04+. Qt's tray icon uses StatusNotifierItem over
  D-Bus when the panel offers it (Xfce's systray plugin, LXQt's panel), and
  falls back to XEmbed otherwise (LXDE's lxpanel). One toolkit and one code
  path for all of them; on Lubuntu, Qt is already there.
- **Behaviour mirrors the applet exactly**, because it is a second client of
  the same helper and nothing about consent or privilege may differ:
  - Poll `/usr/local/libexec/hammunition-devctl state` directly (no
    privilege) every 5 s. That path is a constant, never discovered.
  - Exit 127 from the direct poll means the helper is missing. Show that as
    a sentence with the fix (`hammunition hardware apply`), never a dead
    switch.
  - The menu shows one checkable action per attached parkable device:
    *<summary> — awake/parked*, *kept off* when kept. An unplugged kept
    device shows *Forget*, which runs `wake`.
  - Actions run `pkexec <helper> park|wake NAME@ADDRESS`, always qualified.
    Exit 126 or 127 from pkexec (dismissed or refused) is not an error.
    Anything else non-zero shows stderr.
  - After an action, re-poll. The icon shows the parked variant when any
    attached device is parked, and the tooltip carries the same text as the
    applet.
  - One *Kept off: <names>* notification on the first successful poll after
    start (login), never again in that run.
- **Starts at login on the desktops it serves**:
  `/etc/xdg/autostart/hammunition-tray-qt.desktop` with `NotShowIn=KDE;` so
  a machine with both Plasma and Xfce never shows two trays in Plasma, plus
  an application-menu entry to start it by hand. If
  `QSystemTrayIcon.isSystemTrayAvailable()` is false (GNOME without the
  AppIndicator extension), it prints one line to stderr and exits 0, never a
  crash loop.
- **Package:** `hammunition-tray-qt_<version>_all.deb`, built by the same
  `build.sh` from tracked files only, umask 022. It depends on
  `python3 (>= 3.11), python3-pyqt6, pkexec | policykit-1` (pkexec first: `policykit-1` has no candidate on Debian 13, measured with `apt-cache policy`). The release
  workflow builds both, lists both in `SHA256SUMS`, and installs and removes
  both in the Parrot container before publishing.
- **Tests without a display:** state parsing, `target()`, which icon and
  tooltip for a given state, the exit-code handling, and the once-per-run
  notice are pure functions, tested directly. A smoke test constructs the
  tray under `QT_QPA_PLATFORM=offscreen` when PyQt6 is importable, and
  skips with the reason otherwise.

## 5. Catalog

- `hammunition-tray`: `desktops: [kde]`, `desktop_alternative:
  hammunition-tray-qt`.
- `hammunition-tray-qt`: a new unit pinned to the release's `.deb` digest,
  `desktops: [xfce, lxqt, lxde, mate, cinnamon]`, in `station` beside the
  applet. It is added **after** the tray release exists, measured from the
  downloaded artifact like every pin. GNOME is not listed, because the panel
  there has no tray without an extension, and saying so beats shipping an
  icon that never appears.

## 6. Menus, and the desktops page

No menu code changes here. The menu-spec path already serves every
menu-spec desktop by `$XDG_MENU_PREFIX` (D-036). What changes is the record:

- `docs/desktops.md`, a new user-facing page: which desktops Hammunition
  supports, the order (**Parrot and KDE Plasma first**), and for each of
  KDE, Xfce, LXQt, LXDE, GNOME, MATE, Cinnamon and COSMIC what is measured
  and what is not: menu mechanism and state, tray, and lightweight notes
  (what `station` costs on each). Unmeasured says unmeasured.
- `docs/reference/vm-campaign-desktops.md`: the checklist the Xubuntu 26.04
  and Lubuntu 26.04 VM runs will follow, **not yet run**, so nothing on it
  is a claim. It covers: install `station`, confirm the Plasma applet is
  deferred and the Qt tray is installed, `menus apply` then open the menu,
  park and wake the GPS from the tray, log out and in for the kept-off
  notice, and measure RAM at idle before and after.
- `doctor` reports the desktops read from session files, and the current
  session's desktop.
- D-036's table gains rows for LXQt, LXDE, MATE and Cinnamon, marked
  unmeasured; the README and `docs/SCOPE.md` point to `docs/desktops.md`.

## 7. Out of scope

Running the VMs (later, on the maintainer's word), any per-desktop menu code
before those runs show it is needed, a GTK tray, GNOME Shell extensions, and
COSMIC.
