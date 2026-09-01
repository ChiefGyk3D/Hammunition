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
# The only privileged thing it may do is `sudo apt-get install` the venv
# package for the chosen Python, and only when it is missing (a Debian netinst
# ships without it); it tells you before it does, and does nothing else as root.
#
# It requires Python >= 3.11 and finds one even when the system `python3` is
# 3.10 (Ubuntu/Pop 22.04): the engine, and every unit venv built from it, must
# be on a supported interpreter.

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

command -v git >/dev/null 2>&1 || warn "git not found — git-source builds will be unavailable until 'sudo apt-get install git'."

# The engine requires Python >= 3.11 (it uses StrEnum and other 3.11 features),
# but Ubuntu/Pop 22.04 ships 3.10 as `python3`. Find the best interpreter that
# clears the bar — a newer python3.N if the default is too old — so the engine
# venv (and every unit venv built from it) is on a supported Python. This is
# the bootstrap half of the fix found deploying to a Pop 22.04 laptop.
pick_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON="$(pick_python)" || die "no Python >= 3.11 found. The engine needs it (your 'python3' may be 3.10 on Ubuntu/Pop 22.04). Install one, e.g. 'sudo apt-get install python3.12 python3.12-venv'."
say "Using $("$PYTHON" --version) at $PYTHON"

if ! { [ -f pyproject.toml ] && grep -q 'name = "hammunition"' pyproject.toml; }; then
  die "this does not look like the Hammunition checkout (no matching pyproject.toml). Run from the repo root."
fi

# --- 2. Ensure the chosen Python has venv support ---------------------------

if ! "$PYTHON" -c 'import ensurepip, venv' >/dev/null 2>&1; then
  warn "python3-venv is missing (a Debian netinst ships without it)."
  say  "Installing it now: sudo apt-get install -y python3-venv"
  sudo apt-get update -qq
  # Install the venv package matching the interpreter (python3.12-venv etc.),
  # falling back to python3-venv for the system default.
  venv_pkg="$(basename "$PYTHON")-venv"
  sudo apt-get install -y "$venv_pkg" 2>/dev/null || sudo apt-get install -y python3-venv
  "$PYTHON" -c 'import ensurepip, venv' >/dev/null 2>&1 \
    || die "venv still does not work after installing it. Stopping."
fi

# --- 3. Create the venv and install the engine ------------------------------

if [ -x .venv/bin/python ] \
   && .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  say "Reusing the existing .venv ($(.venv/bin/python --version))"
elif [ -x .venv/bin/python ]; then
  warn "existing .venv is on $(.venv/bin/python --version) (< 3.11) — rebuilding it"
  rm -rf .venv
  "$PYTHON" -m venv .venv
else
  say "Creating the virtualenv at .venv"
  "$PYTHON" -m venv .venv
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
