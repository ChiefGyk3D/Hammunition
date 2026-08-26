# Contributing hardware identifiers

**The single most useful thing you can send this project is `lsusb` output for a
device we don't own.**

Not code, not a bug report. Twelve entries in
[`docs/reference/hardware-gaps.md`](../reference/hardware-gaps.md) are waiting on
exactly one fact that anyone holding the hardware can produce in thirty seconds,
and that nobody without it can produce at all.

## Why this is worth asking for

A device whose USB identifier is guessed produces a udev rule that **silently
never matches**. The operator gets a device that enumerates, works when run as
root, and has no `/dev` symlink — which is indistinguishable from a bad cable.
There is no error message anywhere in that chain.

So the catalog refuses to guess. Where an identifier is unknown, the entry says
so and says who could close it, rather than shipping a plausible pair. That is
an honest position and it is also a standing request for help.

## How

```
scripts/identify-device.sh <device-name>
```

Read-only. No root. It snapshots the USB bus, waits for you to attach the
device, snapshots again, and prints a YAML block ready to paste — with the
evidence field already filled in, because an identifier without provenance is
the thing this catalog exists to refuse.

Use the name from the gap report if your device is listed. If it isn't, use any
short lowercase name and say what the hardware is.

Send the output as an issue or a pull request. Both are fine; the output is the
contribution either way.

**"Nothing appeared" is a real result.** It means the device does not enumerate,
or enumerates as something already present. Send that too — it is information we
do not have.

## What we do with it

The identifier goes into `catalog/hardware/devices/<name>.yaml` with your capture
cited in the `evidence` field. If it fully closes the gap, `identification_gap`
and `gap_closure` are removed and the entry can claim `status: supported`.

If it closes only part of the gap — one board revision of several, one firmware
version — **the gap stays open and its wording narrows to what is still
unknown.** A partly-closed gap that reads as closed is worse than an open one.

## What we will not do with it

Serial numbers are per-unit. `identify-device.sh` prints yours because it is
useful to *you* for building a persistent symlink, but **the catalog stores
vendor and product identifiers only** — never a serial, and never anything that
identifies your particular device or machine. If you paste raw output, we
transcribe the identifiers and nothing else.

## The other kind of contribution

If you own a device the catalog does not list at all, an entry for it is welcome
even without the identifier. `identification_gap` exists precisely so that
"this hardware exists and here is what Linux needs for it" is a shippable state.

Reading a distribution's own udev rules is also an under-used primary source and
needs no hardware whatsoever. The `nfc-reader` class and the `usrp` entry were
both built that way, and expanding `rtl-sdr` from 3 identifiers to Debian's full
42 took one `grep` — those 39 missing pairs were rebadged DVB-T sticks that
people actually own.
