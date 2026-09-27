# Device power control: park and wake a catalogued device from the CLI, the menu, and the Plasma tray

**Status:** design approved in conversation 2026-09-22; awaiting the maintainer's read of this document.
**Decision record:** D-056 (to be written with the implementation).
**Origin:** the field laptop carries a u-blox GPS receiver and a WWAN modem in
M.2 slots. Both draw power whether or not the operator is using them, and both
have to be quietened by hand today: a USB `authorized` write for the receiver, that
plus a NetworkManager `autoconnect` change and an rfkill block for the modem. The
maintainer asked for a switch he can reach from the tray, the app menu, or the
shell, and that comes back on at boot.

## 1. What this is

A device that the hardware catalog marks as parkable can be put into a low-power,
detached state (**park**) and brought back (**wake**) without a reboot, from three
surfaces that all run the same privileged helper:

| Surface | What it does |
|---|---|
| `hammunition hardware park NAME` / `wake NAME` / `state` | prints the exact writes, runs the helper, exits by the CLI's existing codes |
| two generated menu entries per parkable attached device | `Park GPS receiver (hammunition hardware park gps-receiver)`, `Wake …`; under the device's first category |
| a Plasma 6 applet, `com.chiefgyk3d.hammunition.devices`, in its own repository `ChiefGyk3D/hammunition-tray` | one switch per parkable attached device; polls `state`; flips run the helper |

Parked state is **not** persisted. A reboot resets sysfs, every device wakes, and
`state` reports the truth from sysfs. There is nothing to reconcile.

## 2. What it is not

- Not a persistent power policy. Nothing survives a reboot by design.
- Not a rig-cable or SDR kill switch. Only a device whose class or device
  manifest carries `power_control` is parkable; nothing else appears anywhere.
- Not a D-Bus service. Three callers, one helper, one polkit action (approach
  A of three considered; C, a D-Bus service with live state, is the shape to
  grow into if Hammunition ever carries a dozen device controls).
- Not a change to what `hardware apply` already does for udev rules and groups.
  It adds two installed artefacts beside them (helper and polkit action). The
  applet is a separate repository with its own installer.

## 3. Catalog: the `power_control` block

An optional block on a `DeviceClass` or `DeviceManifest`, validated against
fixed enums so the catalog stays pure data and can never carry a command:

```yaml
power_control:
  method: usb_deauthorize        # usb_deauthorize | pci_runtime
  quiet: []                      # zero or more of: networkmanager_autoconnect
  note: >-
    gpsd handles hot-unplug itself (USBAUTO="true" in /etc/default/gpsd), so
    nothing else needs quieting; the receiver reappears at /dev/gpsN on wake.
```

- `method` names how the engine parks the device, not a shell line:
  - `usb_deauthorize`: write `0` to `/sys/bus/usb/devices/<addr>/authorized`
    and `auto` to `…/power/control`; wake writes `1` to `authorized`. The
    kernel drops the interfaces, the port runtime-suspends, and every consumer
    sees a normal unplug.
  - `pci_runtime`: reserved for MHI/PCIe cards (D3cold via `d3cold_allowed`
    and `power/control`). Schema-valid now so a `wwan-modem` class can carry
    it; the helper refuses it with "not implemented" until the branch that
    adds the WWAN class implements and tests it against a card. Nothing is
    shipped that has not been run.
- `quiet` names consumers to hush before parking and restore on wake, each a
  known verb the engine implements: `networkmanager_autoconnect` sets
  `connection.autoconnect no` on every NetworkManager profile bound to the
  device's interface, and `yes` on wake. A verb that cannot run (NetworkManager
  absent) is reported and the park proceeds: the verb is a courtesy to the
  consumer, not a precondition of the hardware step.
- `note` (min 10 chars) is prose for the generated device page: what the
  operator will observe, and why nothing else is needed.

This branch adds the block to `catalog/hardware/classes/gps-receiver.yaml`
only. The `wwan-modem` class comes with the card that proves it.

## 4. Engine: planning and the helper

**Detection is what `hardware list` already does.** `match_catalog()` yields
`Match(name, attached, ambiguous)`; `AttachedDevice` gains one field,
`sysfs_path: str | None` (the `/sys/bus/usb/devices/<addr>` node it was read
from; `None` when a caller supplied the record). Parkable = matched, entry
carries `power_control`, `sysfs_path` set. An ambiguous match (D-028) is still
parkable: the operator is naming a device that is attached and that the
catalog recognises, and parking a mis-identified USB device is a reversible
unplug, not a udev claim.

**`hammunition.hardware.power` (new module)** owns:
- `parkable(matches, entries) -> list[Parkable]`: name, summary, method,
  quiet verbs, sysfs path, and `parked: bool` read from sysfs (`authorized ==
  "0"` for USB).
- `plan_park(p) / plan_wake(p) -> list[Write]`: the ordered `(path, value)`
  writes and quiet verbs, for printing before doing and for tests over a
  synthetic sysfs tree.
- `execute(plan)`: performs the writes, re-reads each path afterwards, and
  fails on mismatch. D-031: the exit status of a `write()` is not evidence.

**`hammunition-devctl` (new `[project.scripts]` entry point)** is the only
thing that runs as root. Interface: `park NAME`, `wake NAME`, `state`
(JSON list of parkables with `parked`). It re-reads sysfs itself, refuses a
name that is not a parkable attached device, refuses any path outside
`/sys/bus/usb/devices/` and `/sys/bus/pci/devices/`, and runs the quiet verbs
as the invoking user where they are per-user (NetworkManager profiles) by
honouring `PKEXEC_UID`. It never reads the operator's station config.

**Installed by `hardware apply`, beside the udev rules** (each printed in the
plan, logged in the transaction, removed by `uninstall`). These two are the
privileged surface and belong with the engine:
1. `/usr/local/libexec/hammunition-devctl`: a wrapper that execs the package
   entry point from the interpreter that owns the package (the venv the
   engine was installed into), so a `pkexec` path is stable across upgrades.
2. `/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy`:
   one action, `allow_active=auth_self_keep` (prompt once, then quiet for the
   session), `allow_inactive=auth_admin`, `allow_any=auth_admin`, annotated
   with the wrapper path. The battery applet's exact shape.
The applet is **not** installed by Hammunition; see section 5.

The optional polkit **rule** that removes the prompt entirely for the active
user is documented on the hardware page and never installed.

## 5. Callers

**CLI.** `hardware park NAME [--dry-run]`, `hardware wake NAME [--dry-run]`,
`hardware state`. `park`/`wake` print the `pkexec` line and every write it
will cause, then run it; `--dry-run` stops after printing. Exit codes follow
`docs/reference/cli.md`: 0 confirmed, 1 a write's effect could not be
confirmed, 2 not plannable (unknown name, not attached, helper or policy not
installed: the message names the missing artefact and that `hardware apply`
installs it), 3 the polkit prompt was dismissed (pkexec 126/127), nothing
changed.

**Menu.** `menus apply` gains, per parkable device attached at apply time,
two generated entries through the existing `cli_entries`/`render_cli_entry`
path with the D-054 title shape, `Exec=` the CLI verb, placed under the
entry's first category (`gps-gnss` for the receiver, beside `cgps`). No
vocabulary change. GNOME gets the same two entries in the group folder.

**Plasma applet.** Its own repository, `ChiefGyk3D/hammunition-tray`
(GPL-3.0-or-later, same author), mirroring `dell-battery-balance`'s layout:
`plasmoid/package/`, `install.sh`/`uninstall.sh` that run `kpackagetool6
--type Plasma/Applet` as the invoking user (never root), a package test, a
README that says it requires Hammunition's `hardware apply` to have installed
the helper and policy. Hammunition's hardware page links to it; nothing in
the engine depends on it. Inside the package: a
`Plasma5Support.DataSource` executable engine runs `hammunition-devctl state`
on a 5 s timer and renders one `Switch` per parkable device, labelled with the
catalog summary; toggling runs `pkexec /usr/local/libexec/hammunition-devctl
park|wake NAME`; a dismissed prompt (126/127) reverts the switch. Compact
representation is one icon that changes when any device is parked. "Not
installed" is shown, not a dead switch, when the helper is absent. The applet
never touches sysfs and never runs as root.

## 6. Failure behaviour

| Situation | Behaviour |
|---|---|
| Prompt dismissed | exit 3 / switch reverts; no write attempted |
| Device unplugged between `state` and `park` | helper re-reads sysfs, refuses "not attached"; tray drops the row next poll |
| A write's readback mismatches | exit 1, reported by path; earlier writes are not rolled back (each is independently reversible by `wake`) |
| Quiet verb fails | reported; park proceeds |
| Helper or policy missing | exit 2 naming the artefact; applet shows "not installed" |
| Reboot while parked | everything wakes; `state` says so |
| `pci_runtime` requested | refused "not implemented" until a card proves it |

## 7. Tests (all in the suite, all falsifiable)

- Schema: `power_control` round-trips; an unknown `method` or `quiet` verb
  fails validation with a message naming the field.
- Planner: over a synthetic sysfs tree, `plan_park`/`plan_wake` for
  `usb_deauthorize` produce exactly the expected writes; `parked` is read
  correctly; a device without the block is not parkable; `pci_runtime` is
  refused.
- Executor: readback mismatch fails; success requires the re-read to match.
- Helper: argv parsing; a name not in the parkable set is refused; a path
  outside the allowed roots is refused before any write.
- Apply: the plan lists the three artefacts; `--dry-run` writes nothing;
  uninstall removes exactly what the log records.
- Menus: two entries per parkable attached device, correct category, D-054
  title shape.
- Applet (in `hammunition-tray`): a package test like `dell-battery-balance`'s
  (metadata, required QML files present, no hardcoded device names); its own
  CI, per the standing rule that every repository gets one.
- Docs: the generated CLI reference and device page pass `--check`.

## 8. Documentation (the feature is not done without it)

- `docs/hardware/power-control.md`: what changes on the machine (two files,
  which sysfs writes), why, how to inspect (`hardware state`, `lsusb`,
  `pkaction`), how to reverse (`wake`, `uninstall`), the optional polkit rule,
  and a pointer to `hammunition-tray` for the tray switch.
- `docs/reference/cli.md`: the three verbs and their exit codes.
- `docs/hardware/gps-receiver-class.md`: regenerated from the manifest.
- `docs/DECISIONS.md`: **D-056**, the polkit boundary (why a helper and not
  `sudo hammunition`, why not a D-Bus service yet, why parked state is not
  persisted, why `pci_runtime` ships refused, why the applet is a separate
  repository: it is a client of the engine, not part of it, and a
  non-Hammunition user can be pointed at it).
- `docs/reference/bench-verification-5430.md`: one line, only after this has
  been run on the field laptop.

## 9. Delivery: two repositories, two plans

1. **Hammunition** (this branch): schema, `hardware.power`, the helper, apply
   and uninstall changes, CLI verbs, menu entries, tests, docs, D-056.
2. **hammunition-tray** (`ChiefGyk3D/hammunition-tray`, created empty
   2026-09-22): the applet, installer, package test, CI, README. Depends on
   1 being installed on the machine; developed against it, second.

## 10. Out of scope (named so they are not lost)

- The `wwan-modem` class and `pci_runtime` implementation: the branch that
  brings up the Quectel EM160R-GL.
- An rfkill quiet verb: the Dell EC does not cut slot power on this chassis
  (measured 2026-09-22), so it buys nothing on the one machine tested.
- Persisted park state and a boot-time unit: explicitly not wanted.
