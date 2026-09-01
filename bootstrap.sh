#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# One-command setup from a fresh checkout. Run it from the repository root:
#
#     ./bootstrap.sh
#
# It creates the virtualenv the engine runs from, installs the package into it,
# and finishes by running `hammunition doctor` so you see exactly what is ready
# and what still needs setting up. It is idempotent — safe to re-run — and it
# fails loudly rather than degrading silently (CLAUDE.md).
#
# The only privileged thing it may do is `sudo apt-get install python3-venv`,
# and only when that package is missing (a Debian netinst ships without it);
# it tells you before it does, and does nothing else as root.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!  \033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mx  \033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. Sanity: a Debian-family system with the tools we assume --------------

[ -r /etc/os-release ] || die "no /etc/os-release — Hammunition targets Debian-family systems only."
# shellcheck disable=SC1091
. /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
  *" debian "*|*" ubuntu "*) : ;;
  *) warn "${PRETTY_NAME:-this system} is not obviously Debian-family. Continuing, but the catalog assumes apt." ;;
esac

command -v python3 >/dev/null 2>&1 || die "python3 is not installed. 'sudo apt-get install python3' first."
command -v git     >/dev/null 2>&1 || warn "git not found — git-source builds will be unavailable until 'sudo apt-get install git'."

if ! { [ -f pyproject.toml ] && grep -q 'name = "hammunition"' pyproject.toml; }; then
  die "this does not look like the Hammunition checkout (no matching pyproject.toml). Run from the repo root."
fi

# --- 2. Ensure python3 -m venv actually works -------------------------------

if ! python3 -c 'import ensurepip, venv' >/dev/null 2>&1; then
  warn "python3-venv is missing (a Debian netinst ships without it)."
  say  "Installing it now: sudo apt-get install -y python3-venv"
  sudo apt-get update -qq
  sudo apt-get install -y python3-venv
  python3 -c 'import ensurepip, venv' >/dev/null 2>&1 \
    || die "python3 -m venv still does not work after installing python3-venv. Stopping."
fi

# --- 3. Create the venv and install the engine ------------------------------

if [ ! -x .venv/bin/python ]; then
  say "Creating the virtualenv at .venv"
  python3 -m venv .venv
else
  say "Reusing the existing .venv"
fi

say "Installing the engine into .venv"
if .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e .
elif command -v uv >/dev/null 2>&1; then
  VIRTUAL_ENV="$here/.venv" uv pip install --quiet -e .
else
  die "neither pip nor uv is available in the venv. 'sudo apt-get install python3-pip' and re-run."
fi

command -v .venv/bin/hammunition >/dev/null 2>&1 || [ -x .venv/bin/hammunition ] \
  || die "the 'hammunition' entry point did not install. Check the pip output above."

# --- 4. Show the operator where they stand ----------------------------------

say "Installed. Health check:"
echo
.venv/bin/hammunition doctor || true   # doctor's non-zero exit is a report, not a bootstrap failure

cat <<'NEXT'

Next:
  .venv/bin/hammunition station set --callsign YOURCALL --grid-square AB12cd
  .venv/bin/hammunition list profiles
  .venv/bin/hammunition install station --dry-run

Put .venv/bin on your PATH (or activate it) to type `hammunition` directly:
  source .venv/bin/activate
NEXT
