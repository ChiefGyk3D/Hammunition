#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Snapshot lifecycle for the KVM/QEMU test VMs — the restore-to-fresh loop
# that makes install testing honest. docs/contributing/vm-testing.md is the
# runbook; this is the mechanism.
#
#   vm-snapshot.sh baseline <domain>   take the clean-baseline snapshot
#   vm-snapshot.sh reset    <domain>   revert to clean-baseline and start it
#   vm-snapshot.sh save     <domain> <name>   named checkpoint mid-campaign
#   vm-snapshot.sh restore  <domain> <name>   revert to a named checkpoint
#   vm-snapshot.sh list     <domain>   what exists
#   vm-snapshot.sh delete   <domain> <name>   remove one snapshot
#
# Conventions:
#   - The baseline snapshot is always named "clean-baseline" (the same
#     convention the PiNodeXMR_Dev VM already uses), taken ONCE per VM after
#     the OS is installed, updated, and the install ISO detached — and before
#     the first hammunition run. `baseline` refuses to overwrite it; retaking
#     it deliberately is `delete` then `baseline`.
#   - Fails loudly (CLAUDE.md: never silently degrade): missing domain,
#     missing snapshot, raw-format disks, or an attached install ISO at
#     baseline time each stop the script with the reason and the fix.
#   - Works on the system connection (qemu:///system) because that is where
#     virt-manager creates VMs. Override with VM_CONNECT for session VMs.

set -euo pipefail

CONNECT="${VM_CONNECT:-qemu:///system}"
BASELINE="clean-baseline"

die() { echo "vm-snapshot: ERROR: $*" >&2; exit 1; }
virsh_() { virsh --connect "$CONNECT" "$@"; }

usage() {
    sed -n 's/^#   vm-snapshot.sh /  /p' "$0"
    exit 1
}

need_domain() {
    local domain="$1"
    virsh_ dominfo "$domain" >/dev/null 2>&1 \
        || die "domain '$domain' not found on $CONNECT (virsh list --all to see what exists; VM_CONNECT=qemu:///session for session VMs)"
}

# Internal snapshots need qcow2 on every writable disk. A raw disk fails
# snapshot-create with an error that does not name the disk; name it here.
check_disks_qcow2() {
    local domain="$1" source
    while read -r source; do
        [ -f "$source" ] || continue
        case "$source" in
            *.iso) continue ;;  # readonly media are fine and are checked separately
        esac
        if ! head -c 4 "$source" 2>/dev/null | grep -q 'QFI'; then
            # Unreadable (root-owned image) is not proof of raw; only fail on
            # a readable non-qcow2 header.
            if [ -r "$source" ]; then
                die "disk $source is not qcow2 — internal snapshots need qcow2. Convert with qemu-img convert -O qcow2."
            fi
        fi
    done < <(virsh_ domblklist "$domain" | awk 'NR>2 && $2 != "-" {print $2}')
}

check_no_install_iso() {
    local domain="$1"
    local iso
    iso=$(virsh_ domblklist "$domain" | awk 'NR>2 && $2 ~ /\.iso$/ {print $2}')
    if [ -n "$iso" ]; then
        die "an ISO is still attached ($iso) — a baseline with the installer media attached is not a clean baseline, and the snapshot breaks if the ISO moves. Detach it first: virsh --connect $CONNECT change-media $domain sda --eject --config"
    fi
}

snapshot_exists() {
    local domain="$1" name="$2"
    virsh_ snapshot-list "$domain" --name 2>/dev/null | grep -qx "$name"
}

cmd_baseline() {
    local domain="$1"
    need_domain "$domain"
    snapshot_exists "$domain" "$BASELINE" \
        && die "'$BASELINE' already exists for $domain. Retaking it is deliberate: $0 delete $domain $BASELINE first."
    check_no_install_iso "$domain"
    check_disks_qcow2 "$domain"
    local state
    state=$(virsh_ domstate "$domain")
    echo "vm-snapshot: taking '$BASELINE' of $domain (state: $state)"
    if [ "$state" = "running" ]; then
        echo "vm-snapshot: note: live snapshot includes RAM; reset resumes exactly here."
        echo "vm-snapshot: for a boots-fresh baseline, shut the guest down first."
    fi
    virsh_ snapshot-create-as "$domain" "$BASELINE" \
        "clean OS install, updated, no hammunition run yet ($(date -Iseconds))"
    virsh_ snapshot-list "$domain"
}

cmd_save() {
    local domain="$1" name="$2"
    need_domain "$domain"
    [ "$name" = "$BASELINE" ] && die "use '$0 baseline' for the baseline"
    snapshot_exists "$domain" "$name" && die "snapshot '$name' already exists for $domain"
    check_disks_qcow2 "$domain"
    virsh_ snapshot-create-as "$domain" "$name" "checkpoint ($(date -Iseconds))"
    virsh_ snapshot-list "$domain"
}

cmd_restore() {
    local domain="$1" name="$2"
    need_domain "$domain"
    snapshot_exists "$domain" "$name" \
        || die "no snapshot '$name' for $domain. $0 list $domain shows what exists; if the baseline was never taken, that is the finding."
    echo "vm-snapshot: reverting $domain to '$name' — everything since is discarded"
    virsh_ snapshot-revert "$domain" "$name" --running 2>/dev/null \
        || virsh_ snapshot-revert "$domain" "$name"
    # A revert to an offline snapshot leaves the domain shut off; start it so
    # "reset" always ends with a machine to test against.
    if [ "$(virsh_ domstate "$domain")" != "running" ]; then
        virsh_ start "$domain"
    fi
    echo "vm-snapshot: $domain is at '$name' and running"
}

cmd_list() {
    local domain="$1"
    need_domain "$domain"
    virsh_ snapshot-list "$domain" --tree
    virsh_ snapshot-list "$domain"
}

cmd_delete() {
    local domain="$1" name="$2"
    need_domain "$domain"
    snapshot_exists "$domain" "$name" || die "no snapshot '$name' for $domain"
    virsh_ snapshot-delete "$domain" "$name"
    echo "vm-snapshot: deleted '$name' from $domain"
}

command -v virsh >/dev/null || die "virsh not found — install libvirt-clients"

cmd="${1:-}"; shift || true
case "$cmd" in
    baseline) [ $# -eq 1 ] || usage; cmd_baseline "$1" ;;
    reset)    [ $# -eq 1 ] || usage; cmd_restore "$1" "$BASELINE" ;;
    save)     [ $# -eq 2 ] || usage; cmd_save "$1" "$2" ;;
    restore)  [ $# -eq 2 ] || usage; cmd_restore "$1" "$2" ;;
    list)     [ $# -eq 1 ] || usage; cmd_list "$1" ;;
    delete)   [ $# -eq 2 ] || usage; cmd_delete "$1" "$2" ;;
    *) usage ;;
esac
