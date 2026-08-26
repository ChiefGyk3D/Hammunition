#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Capture the USB identity of one device, for closing an identification_gap.
#
# The catalog refuses to guess a VID:PID because a wrong one produces a udev
# rule that silently never matches, which an operator cannot tell apart from a
# bad cable. `docs/reference/hardware-gaps.md` lists what is still unknown. This
# is how a gap gets closed.
#
# Read-only. It snapshots the USB bus, waits for you to attach the device,
# snapshots again, and reports what appeared. It writes nothing outside the
# temporary directory it makes, needs no root, and does not touch the device.
#
#   scripts/identify-device.sh catsniffer-v3
#
# Output is a YAML block ready to paste into catalog/hardware/devices/<name>.yaml
# under `usb_ids:`, plus the raw evidence it was derived from.

set -euo pipefail

NAME="${1:-unknown-device}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

need() { command -v "$1" >/dev/null || { echo "missing: $1 (apt install $2)" >&2; exit 1; }; }
need lsusb usbutils

snapshot() { lsusb | sort > "$1"; }

echo "Identifying: $NAME"
echo
echo "1. UNPLUG the device if it is attached, then press Enter."
read -r _
snapshot "$WORK/before"

echo "2. PLUG IN the device, wait for it to settle, then press Enter."
read -r _
sleep 1
snapshot "$WORK/after"

mapfile -t NEW < <(comm -13 "$WORK/before" "$WORK/after")

if [ "${#NEW[@]}" -eq 0 ]; then
    cat >&2 <<'MSG'

Nothing new appeared on the USB bus.

That is itself a finding worth reporting, not a failed run. It means either the
device does not enumerate at all (power, cable, or it needs a button held during
plug-in), or it enumerates as something already present. Try `dmesg | tail -20`
for what the kernel saw.
MSG
    exit 1
fi

echo
echo "=========================================================================="
echo "Found ${#NEW[@]} new device(s)"
echo "=========================================================================="

for line in "${NEW[@]}"; do
    id="$(sed -E 's/.*ID ([0-9a-f]{4}:[0-9a-f]{4}).*/\1/' <<<"$line")"
    vendor="${id%%:*}"
    product="${id##*:}"
    desc="$(sed -E 's/.*ID [0-9a-f]{4}:[0-9a-f]{4} ?//' <<<"$line")"

    # Find the sysfs node so we can read the serial and any tty it created.
    # First match wins. If two devices sharing a VID:PID are attached, this
    # reports one of them -- which is fine here, because the whole procedure is
    # "attach exactly one device", and the pair is identical anyway. The serial
    # is the only per-unit field, and it is what serial_suffix exists for.
    syspath=""
    for candidate in /sys/bus/usb/devices/*; do
        [ -r "$candidate/idVendor" ] || continue
        [ "$(cat "$candidate/idVendor")" = "$vendor" ] || continue
        [ "$(cat "$candidate/idProduct")" = "$product" ] || continue
        syspath="$candidate"
        break
    done

    read_attr() { [ -r "$syspath/$1" ] && cat "$syspath/$1" || echo "(none)"; }

    serial="$(read_attr serial)"
    manufacturer="$(read_attr manufacturer)"
    prodname="$(read_attr product)"

    # Any character devices this created.
    nodes=""
    if [ -n "$syspath" ]; then
        for tty in "$syspath"/*/tty/* "$syspath"/*/*/tty/*; do
            [ -e "$tty" ] && nodes="$nodes /dev/$(basename "$tty")"
        done
    fi
    [ -n "$nodes" ] || nodes=" (none - not a serial device, or no driver bound)"

    echo
    echo "--- raw evidence ---"
    echo "lsusb:        $line"
    echo "sysfs:        ${syspath:-not found}"
    echo "manufacturer: $manufacturer"
    echo "product:      $prodname"
    echo "serial:       $serial"
    echo "dev nodes:   $nodes"
    echo
    echo "--- paste into catalog/hardware/devices/$NAME.yaml under usb_ids: ---"
    cat <<YAML
  - vendor: "$vendor"
    product: "$product"
    description: ${desc:-$prodname}
    evidence: >-
      lsusb against real hardware, $(date +%F), on $(. /etc/os-release 2>/dev/null && echo "$ID $VERSION_ID" || echo "unknown host").
      Reported as "$desc". manufacturer=$manufacturer product=$prodname
      serial=$serial
    confirmed: true
YAML
done

echo
echo "=========================================================================="
echo "Then set  gap_closure  and  identification_gap  appropriately:"
echo "  - if this fully closes the gap, delete both fields and set"
echo "    status: supported"
echo "  - if it closes only part of it (one board of several, one firmware"
echo "    revision), keep the gap and narrow its wording to what is still"
echo "    unknown. A partly-closed gap that reads as closed is worse than an"
echo "    open one."
echo "=========================================================================="
