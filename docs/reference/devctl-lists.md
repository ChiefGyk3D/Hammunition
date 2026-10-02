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
file ever carries a station value (a callsign, a grid square).

| File | Written by | Scope |
|---|---|---|
| `/etc/hammunition/devctl-devices.yaml` | `hammunition hardware apply` | the devices the helper may park and wake |
| `/etc/hammunition/devctl-services.yaml` | `hammunition hardware apply` | the system services the helper may start, stop, enable and disable |
| `~/.config/hammunition/devctl-services.yaml` | installing a catalog unit with a `user_services` block | the operator's own services (not written by `hardware apply`; its writer is not in this change) |

Both system files are root-owned, mode `0644`, and open with the header line
```
# Written by `hammunition hardware apply` (D-056, amended 2026-10-02).
```
followed by what the file is for. **Do not edit them.** `hardware apply`
rewrites them whole when the catalog or the machine's time daemon changes, and
`hardware unapply` removes each only when it starts with that header. A file at
either path without the header refuses the apply (exit `2`) and is never
overwritten.

## `devctl-devices.yaml`

Every catalogued class or device whose manifest carries a `power_control`
block, sorted by name. Today that is `gps-receiver` alone.

```yaml
version: 1
devices:
- name: gps-receiver
  summary: USB GNSS receivers — position for APRS and grid squares, and time for FT8
  method: usb_deauthorize
  quiet: []
  usb_ids:
  - vendor: '1546'
    product: 01a8
    product_string: null
    ambiguous: true
    distinctive: false
  # ... one entry per confirmed identifier
```

`vendor` and `product` are strings in the file: four lowercase hex digits,
quoted where YAML would otherwise read them as a number (`'1546'`, `'0003'`).
The excerpt is a real one, cut after the first identifier.

| Key | Meaning |
|---|---|
| `version` | the file's shape version, `1`. A reader refuses one it does not know, by name |
| `name` | the catalog name; what `park NAME` and `state` use |
| `summary` | the catalog entry's one line |
| `method` | `usb_deauthorize` (applies) or `pci_runtime` (schema-valid and refused, **D-056**) |
| `quiet` | the consumers to hush before a park and restore on a wake, in order: `networkmanager_autoconnect` is the one verb that exists |
| `usb_ids` | the confirmed identifiers only (an unconfirmed one names nothing, and the engine's own matcher skips it too) |
| `usb_ids[].vendor`, `.product` | four hex digits; `product` is `null` when the entry matches a whole vendor |
| `usb_ids[].product_string` | the descriptor's product string the catalog recorded, or `null` |
| `usb_ids[].ambiguous` | the pair names a chip or a function, not a device (**D-028**) |
| `usb_ids[].distinctive` | the product string is recorded by exactly one catalog entry for this identifier, so a match on it is a conclusion rather than a candidate |

**What the helper does with it.** An identifier matches a bus device on vendor
and product. Where `ambiguous` is true and both the file and the bus carry a
product string, they must be equal; and where they are equal and `distinctive`
is true, the match is no longer ambiguous. This is the engine's own rule
(`hammunition.hardware.detect.match_catalog`), carried in the file so the
helper needs nothing else. A device matched this way is parkable
only through `usb_deauthorize`; the sysfs guard that limits a write to
`authorized` and `power/control` under a USB or PCI node is the helper's and
does not depend on the file.

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
the refusal of a foreign file, the removal by header. **Not measured:** the
tray's helper reading these files, which is not yet released; the exact keys it
requires beyond those the design names (`version` is the engine's addition);
and `hardware apply` on a real machine with the lists.
