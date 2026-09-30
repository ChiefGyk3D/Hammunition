# VM campaign — Xubuntu 26.04 and Lubuntu 26.04 (NOT YET RUN)

> **Status: NOT YET RUN.** This page is the checklist the two runs will
> follow. Nothing on it is a claim about how Hammunition behaves on Xfce or
> LXQt. When a run happens, its results replace the empty cells below with
> what was seen and the date, and whatever it contradicts in
> `docs/desktops.md` is corrected the same day.

**Why these two.** The maintainer asked for Xfce and LXDE so that a
low-powered machine can run the project (2026-09-28). **Lubuntu is LXQt,
not LXDE**, and has been since 18.10, so Lubuntu tests LXQt. Plain LXDE is
still in Debian as `openbox-lxde-session` and no current Ubuntu flavour
ships it. Xubuntu is Xfce. Both 26.04 images share the Ubuntu 26.04 base,
which already has a full-catalog campaign (`vm-campaign-ubuntu.md`), so
anything that differs here is the desktop's doing. The decision record is
**D-060**.

**Harness.** The same one as every other VM campaign: a clean snapshot per
target, the engine synced from the branch under test, `scripts/vm_campaign.py`
for the install steps, and the GUI checks done on the console, because a
menu or a tray icon is only verified by looking at it. Station values are
placeholders (`N0CALL`, `FN31pr`), as on every VM page.

---

## Before anything is installed

| # | Step | Xubuntu 26.04 | Lubuntu 26.04 |
|---|---|---|---|
| 1 | Record the image, kernel and desktop version | | |
| 2 | `ls /usr/share/xsessions /usr/share/wayland-sessions /usr/local/share/xsessions /usr/local/share/wayland-sessions`, and the `DesktopNames=` line of each file | | |
| 3 | `hammunition doctor`: the *desktops* line names Xfce (or LXQt) and the current session | | |
| 4 | Idle memory after login, nothing else started: `free -m` three times a minute apart, and the median | | |

## Install `station`

| # | Step | Xubuntu 26.04 | Lubuntu 26.04 |
|---|---|---|---|
| 5 | `hammunition install station --dry-run`: *Desktops read from session files* shows only this desktop, and `hammunition-tray` is under *Will NOT happen* with the reason `for KDE Plasma; this machine has no KDE Plasma session` | | |
| 6 | The plan does not fetch the applet: `hammunition-tray_*_all.deb` appears nowhere in it (its Depends are never printed, so looking for `plasma-workspace` in the plan proves nothing) | | |
| 7 | `hammunition install station`: every other member installs and confirms | | |
| 7a | The effect, after step 7 (D-031): `apt-cache policy plasma-workspace` shows `Installed: (none)`, `dpkg -l 'plasma*'` lists nothing installed, and no `plasma*.desktop` is in any of the four session directories | | |
| 8 | `hammunition status` shows the deferral | | |
| 9 | `hammunition install hammunition-tray` is refused, and the refusal names the remedy | | |
| 10 | Once `hammunition-tray-qt` is in the catalog: it installs with `station` here, and its autostart entry exists | | |

## Menus

| # | Step | Xubuntu 26.04 | Lubuntu 26.04 |
|---|---|---|---|
| 11 | `hammunition menus apply` from the desktop session (not over SSH): which prefix it chose, and the file it wrote | | |
| 12 | Open the desktop's own menu: *Hammunition* is there, the groups are in D-050's order, and a unit's entry opens | | |
| 13 | Log out and back in, and the tree is still there | | |

## Tray and device power (needs `hammunition-tray-qt` and a GPS receiver)

| # | Step | Xubuntu 26.04 | Lubuntu 26.04 |
|---|---|---|---|
| 14 | `hammunition hardware apply`, then the tray icon appears after login | | |
| 15 | Park the GPS from the tray: one password prompt, the icon turns to its parked variant, `hammunition hardware state` agrees | | |
| 16 | Wake it from the tray, and `cgps` sees fixes again | | |
| 17 | Park it *kept off*, log out and back in: one *Kept off* notice, and only one | | |

## After

| # | Step | Xubuntu 26.04 | Lubuntu 26.04 |
|---|---|---|---|
| 18 | Idle memory after login with `station` installed, measured the same way as step 4 | | |
| 19 | Disk used by the `station` transaction (the plan's figure against `df` before and after) | | |

Steps 10 and 14–17 wait on the Qt tray's first release. The rest can run
as soon as the VMs exist.
