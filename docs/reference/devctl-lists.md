# The helper's lists

The privileged helper that parks and wakes devices, sets the clock's time
source and starts and stops services lives in
[hammunition-tray](https://github.com/ChiefGyk3D/hammunition-tray)
(**D-056**, amended 2026-10-02). The device and service catalogs stay in this
engine, so `hammunition hardware apply` writes two data files the helper reads
instead of importing the engine. A third, per user, is written by the install of
a unit that runs as a user service.

**An allow-list is data, never an argument.** The helper takes a name, looks it
up in these files, and refuses by name one they do not carry. Nothing an
unprivileged caller supplies is ever a path, a unit or a command, and neither
file ever carries a station value (a callsign, a grid square). A root-run helper
reads only a regular file owned by root and not writable by group or other, in a
directory that is the same, never following a symlink.

| File | Written by | Scope |
|---|---|---|
| `/etc/hammunition/devctl-devices.yaml` | `hammunition hardware apply` | the devices the helper may park and wake |
| `/etc/hammunition/devctl-services.yaml` | `hammunition hardware apply` | the system services the helper may start, stop, enable and disable |
| `~/.config/hammunition/devctl-services.yaml` | installing a catalog unit with a `user_services` block | the operator's own services (not written by `hardware apply`: it is written by the install of a unit that runs as one, today `gps-tether` and `rig-service`, and removed by that unit's uninstall) |

Both system files are root-owned, mode `0644`, and open with the header line
```
# Written by `hammunition hardware apply` (D-056, amended 2026-10-02).
```
followed by what the file is for. **Do not edit them.** `hardware apply`
rewrites them whole when the catalog or the machine's time daemon changes, and
`hardware unapply` removes each only when it starts with that header. A file at
either path without the header, or one this account cannot read, refuses the
apply (exit `2`) and is never overwritten. The check is made when the plan is
built and `install -D` replaces whatever is at the path when it runs, so a file
created between the two would be replaced: `/etc/hammunition` is root's, so only
root could do that.

## `devctl-devices.yaml`

Every catalogued class or device whose manifest carries a `power_control`
block, sorted by name. Today that is five entries: the classes `bluetooth-controller`, `camera`, `gps-receiver` and `wwan-modem` (all `usb_deauthorize`), and the field laptop's `dell-dw5930e` (`pci_runtime`, schema-valid and refused). The excerpt below shows `gps-receiver`. The shape is
hammunition-tray's contract 1 (the contract page in that repository's docs directory); the tray's
helper reader loaded a file this exporter wrote with no complaint (run once,
by hand, against its branch).

```yaml
version: 1
devices:
  - name: "gps-receiver"
    summary: "USB GNSS receivers — position for APRS and grid squares, and time for FT8"
    method: "usb_deauthorize"
    quiet: []
    usb_ids:
      - vendor: "1546"
        product: "01a5"
      - vendor: "1546"
        product: "01a6"
      # ... one entry per confirmed identifier
```

The excerpt is a real one, cut after the second identifier. Every string is
double-quoted, always: an identifier like `0003` or `1e10` is a string and never a
number, whatever the reader's YAML version.

| Key | Meaning |
|---|---|
| `version` | the file's shape version, `1`. A reader refuses one it does not know, by name |
| `name` | the catalog name; what `park NAME` and `state` use |
| `summary` | the catalog entry's one line |
| `method` | `usb_deauthorize` (applies) or `pci_runtime` (schema-valid and refused, **D-056**) |
| `quiet` | the consumers to hush before a park and restore on a wake, in order: `networkmanager_autoconnect` is the one verb that exists |
| `usb_ids` | the confirmed identifiers only (an unconfirmed one names nothing, and the engine's own matcher skips it too) |
| `usb_ids[].vendor` | four lowercase hex digits |
| `usb_ids[].product` | four lowercase hex digits; **absent** when the entry matches a whole vendor |
| `usb_ids[].product_string` | present only for an identifier the catalog marks ambiguous (**D-028**) and has read a product string for |

**What the helper does with it.** An identifier matches a bus device on vendor
and, where there is one, product. Where `product_string` is present and the bus
reports a string too, they must be equal; when the bus reports none, the
identifier alone matches. This is the engine's own rule
(`hammunition.hardware.detect.match_catalog`), which compares a product string
only for an ambiguous identifier, carried in the file so the helper needs
nothing else. Whether a match is *certain* (the engine's `ambiguous` flag on a
match, and whether a string is distinctive across the catalog) changes nothing
about whether a device may be parked (**D-056**), so neither is exported. A device
matched this way is parkable only through `usb_deauthorize`; the sysfs guard
that limits a write to `authorized` and `power/control` under a USB or PCI node
is the helper's and does not depend on the file.

## `devctl-services.yaml`

```yaml
version: 1
services:
- name: gpsd
  unit: gpsd.socket
  scope: system
  description: the GPS daemon (socket-activated)
- name: time
  unit: ntpsec.service
  scope: system
  description: 'the clock: the daemon GPS time feeds'
- name: gps-resume
  unit: hammunition-gps-resume.service
  scope: system
  description: re-adds the receiver to gpsd after sleep
```

| Key | Meaning |
|---|---|
| `name` | what `hammunition services` (`start`, `stop`, `enable` or `disable` `NAME`) and the tray pass to the helper |
| `unit` | the systemd unit the helper acts on; fixed argv, never taken from input |
| `scope` | `system` here; `user` in the per-user file |
| `description` | one line, shown beside the switch |

**The `time` row follows the machine.** `ntpsec.service` where ntpsec's daemon
and configuration are installed (the daemon GPS time disciplines, **D-058**);
`chrony.service` where only chrony is (**D-072**); and `ntpsec.service` when
neither is found, which the plan says in so many words and the helper reports as
not installed. `systemd-timesyncd` is never named: it cannot take time from a
GPS. A machine that gains a time daemon later needs `hammunition hardware
apply` again.

A unit that is not installed is still listed by the helper, with `enabled:
not-found`, so a front end can say "not installed" rather than hide the switch.
`hammunition services` is how to read the result.

## Inspect and reverse

```
cat /etc/hammunition/devctl-devices.yaml /etc/hammunition/devctl-services.yaml
hammunition services
hammunition hardware state
hammunition hardware unapply
```

`unapply` removes both files by content and leaves `/etc/hammunition`, which
also holds `time.yaml`. Each write is recorded in the transaction log as a
`devctl_export` event ([transaction-log.md](transaction-log.md)), without the
files' contents.

## What is measured and what is not

Tested against a temporary root: the shapes above, the byte-for-byte read-back,
the refusal of a foreign file, the removal by header. Run once by hand, not part
of the suite (the tray is not a dependency here): the tray's own reader
(`hammunition_devctl.devices.load_devices` and `services.load_services`, from its
`devctl-helper` branch) loaded a devices file written by this exporter from the
real catalog and a services file, with no note: eleven identifiers on
`gps-receiver`, three services. **Not measured:** the tray's helper reading the
files as installed under `/etc/hammunition` (hammunition-tray 0.5.0 is released and the tray units install its helper, but that has not been run as root on a real machine), `hardware apply`
on a real machine with the lists, and the check the helper makes on a root-read
file (a regular file, root-owned, not group- or other-writable, in a directory
that is the same) against what `install -D -m 0644` leaves: the mode is right by
construction, `/etc/hammunition` being root's has not been looked at on a
machine.
