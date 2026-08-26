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
contribution either way. There are issue forms that tell you exactly what to
paste, so nothing is left to guess:

| Form | For |
|---|---|
| [`hardware-identifier.yml`](../../.github/ISSUE_TEMPLATE/hardware-identifier.yml) | Any device in `hardware-gaps.md`, or one we do not list at all |
| [`lora-product-string.yml`](../../.github/ISSUE_TEMPLATE/lora-product-string.yml) | Meshtastic, MeshCore and RNode boards — see below, the ask is narrower than it looks |

### The LoRa ask is specific, and deliberately not a blanket one

107 upstream board definitions were mined into
[`docs/reference/lora-inventory.md`](../reference/lora-inventory.md), which settled
what every Meshtastic and MeshCore board *presents* — 26 identifiers, the top
one covering 49 boards — without anyone owning one. What it cannot settle is
which board is which, because **a board definition records what the flasher
matches, not what the board reports**, and the descriptor's product string is
the only thing that separates two boards sharing a module.

That makes the ask worth targeting rather than broadcasting. **nRF52840 boards
(`239a:*`, `2886:*`) are worth a capture; ESP32-S3 boards using native USB are
not.** The ESP32-S3's `303a:1001` was captured three times here on unrelated
products — a Clip-Boy, a Minino, and the ESP32-S3 inside a Free-WiLi 2 — and
reported the identical product string every time, because it belongs to the ROM
rather than to any board. Asking 49 boards' worth of owners to confirm that
would waste their thirty seconds, which is a reason to do the arithmetic before
posting an ask rather than after.

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
