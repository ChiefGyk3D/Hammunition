# Device power control, kept off: a parked device stays parked across reboots

**Status:** design approved in conversation 2026-09-27; awaiting the maintainer's read of this document.
**Decision record:** a D-056 amendment, written with the implementation. It
reverses D-056's "Why parked state is not persisted".
**Origin:** with park and wake proven on the field laptop's GPS receiver
(bench session 10), the maintainer asked for the switch to *stay* where it is
set: "we may not always want GPS but maybe cell, or maybe we want cell off and
GPS to save battery or whatever for an extended period."

## 1. What this is

Turning a device off in the tray, or `hammunition hardware park NAME`, detaches
it now **and keeps it detached** across reboots, suspend and resume, and a
replug into the same port, until it is turned back on. The switch is the memory.
After login, the tray shows one notification naming what came up kept off.

This is piece 1 of 2. Piece 2, the cellular modem class (detach, plus a separate
radio switch through NetworkManager), is its own spec once a working modem is
fitted (§9).

## 2. What it is not

- Not a boot-time service or daemon. Nothing runs to apply the kept state:
  udev does, as the device appears.
- Not a new privileged path. The existing helper, behind the existing polkit
  action, writes the one new file.
- Not per-user. A kept device is kept for the machine, as the `authorized`
  write already is.
- Not model-wide. The same model in a different port is not kept off (§3).

## 3. Mechanism: one udev rules file

`/etc/udev/rules.d/66-hammunition-kept.rules`, owned by the engine and rewritten
whole on each change. One line per kept device:

```
ACTION=="add", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", KERNEL=="3-5.1", ATTR{idVendor}=="1546", ATTR{idProduct}=="01a9", ATTR{authorized}="0"
```

- **Port and model together.** `KERNEL` is the USB port path; `idVendor` and
  `idProduct` are read from the device. A different device in that port is not
  touched, and another receiver of the same model elsewhere is not either.
  Moving the kept device to another port brings it back on, which errs toward
  not losing a device.
- **Why udev, not a state file and a unit.** The rule is applied by udev as
  the device appears, so nothing has to run at boot for gpsd and
  ModemManager to be kept off it. A unit applying a state file after boot
  would let them grab the device and then lose it: the retry churn the
  DW5930e showed on 2026-09-22. Whether the rule wins outright — whether a
  tty node like `/dev/ttyACM0` never appears at all, or appears briefly
  before the rule's `authorized=0` lands — is not established by this
  reasoning: a udev `ACTION=="add"` rule fires once the kernel has already
  enumerated the device's interfaces, not before them, so "before its
  interfaces bind" was this design's assumption, not a measured fact. The
  moment before the rule applies is exactly what the field-laptop reboot
  test in §7 measures.
- **D-056's objection, answered.** Live state is still read from sysfs
  (`authorized`). The rule records only intent. `state` reports both, so a
  disagreement (a kept device someone authorised by hand) is shown, not hidden,
  and the next add re-applies the rule.
- **Numbers `66`.** After Hammunition's own `65-hammunition.rules`, so the
  permission rules have run first.

**The assumption this rests on:** the port path (`3-5.1`) is stable across
boots on fixed hardware. It is measured before any doc claims the feature
works (§7).

## 4. Engine

**`src/hammunition/hardware/power.py`**
- `kept_rule_line(p: Parkable) -> str`: builds the line from `p.address`,
  `p.identifier`. The address must match `^\d+-\d+(\.\d+)*$` and the IDs
  `^[0-9a-f]{4}$`, or it raises. Nothing else reaches the file.
- `read_kept(path) -> list[KeptEntry]`: parses the file back (address, vendor,
  product). Lines it did not write are an error naming the line, not skipped.
- `plan_park(p, keep=True)` adds a `WriteKept` step after the sysfs writes;
  `plan_wake(p)` adds a `WriteKept` that drops the line, if present.
  `keep=False` is `--until-reboot`: today's behaviour, no file write.
- The file write is atomic (temp file in the same directory, `fsync`, rename),
  mode 0644, root-owned, followed by `udevadm control --reload`. No `trigger`:
  the park already happened through sysfs.
- `guard()` gains the one absolute path `KEPT_RULES`. It stays lexical and
  leaf-pinned, as D-056 requires; no other path under `/etc` is writable.

**`src/hammunition/cli/devctl.py` (the root helper)**
- `park NAME` keeps by default; `park --until-reboot NAME` does not.
- `wake NAME` removes the device's line. `wake NAME@ADDRESS` also works for a
  kept device that is not attached, so a stale line can be cleared.
- `state` JSON gains `"kept": bool` per device, plus kept entries whose device
  is absent (`"attached": false`).

**`src/hammunition/cli/main.py`**
- `hammunition hardware park [--until-reboot]`, `wake`, `state` pass through.
- `hardware unapply` removes `66-hammunition-kept.rules` and reloads udev, and
  says so in its plan.
- `doctor` reports kept devices, and flags any kept entry whose device is absent.

## 5. Tray (`hammunition-tray`)

- A kept device's row shows "kept off" under its name; the switch still shows
  the live state.
- **Boot notice.** On the first successful poll after the applet loads, if any
  attached device is parked and kept, one notification: "Kept off: GPS
  receiver" (names joined). Once per applet load, which is once per login.
  Nothing when none is kept.
- No new privilege: the applet already calls `pkexec` for park and wake, and
  the helper now also writes the rule.

## 6. Failure behaviour

| Case | Result |
|---|---|
| Rule write fails after the sysfs park succeeded | Exit non-zero, message says the device **is parked now but will not stay parked**; the tray shows the error line. Not rolled back: the operator asked for off, and it is off. |
| Rule file has a line the engine did not write | Refuse to rewrite it; name the line and the file. |
| `udevadm control --reload` fails | Report it; the rule still applies from the next boot. |
| Kept device authorised by hand | `state`: awake, kept. Next add parks it again. |
| Kept device moved to another port | Comes up awake; the old line is listed as absent until woken or cleared. |

## 7. Tests and proof

Unit, falsifiable, in the suite: the line for a known `Parkable`; refusal of a
malformed address or ID; round-trip `read_kept(write(x)) == x`; a foreign line
refuses; `plan_park` writes the rule only with `keep=True`; `plan_wake` drops
exactly one line; `guard` admits `KEPT_RULES` and nothing beside it; `unapply`
plans the removal; `state` reports `kept` and absent entries. Tray: the notice
text for zero, one and two kept devices, and that it fires once.

On the field laptop, recorded in `bench-verification-5430.md` before the docs
claim it: park the GPS, reboot, confirm `authorized=0`, no `/dev/ttyACM0`, the
notice shown, and the port path unchanged; wake, reboot, confirm it comes up
awake with a fix.

## 8. Documentation

`docs/hardware/power-control.md` (kept off, `--until-reboot`, how to inspect the
file, how to remove it), `docs/reference/cli.md` (the flag, the `state` fields,
`unapply`), the D-056 amendment, and the tray README.

## 9. Piece 2, named so it is not lost

A `wwan-modem` hardware class: detach through this same mechanism, plus a
separate radio switch through NetworkManager (`nmcli radio wwan`). NM keeps
`WWANEnabled` in `/var/lib/NetworkManager/NetworkManager.state`; whether that
survives a reboot is measured, not assumed, and our own record is added only if
it does not. Blocked on a working modem: the DW5821e fitted now is FCC-locked,
and the Quectel EM160R-GL and Sierra EM7455 are on order.
