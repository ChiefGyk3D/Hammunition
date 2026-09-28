#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Put `hammunition` on the PATH: ~/.local/bin/hammunition -> CHECKOUT/.venv/bin/hammunition.
#
#     scripts/path-link.sh CHECKOUT
#
# Called by bootstrap.sh (D-059); safe to run by hand. Idempotent. It never
# replaces anything it did not create: a file, a directory, or a symlink
# pointing anywhere but some checkout's .venv/bin/hammunition, is left alone
# and named. A link to ANOTHER checkout is also left alone -- two worktrees
# must not fight over the PATH -- and the one command that switches it is
# printed. The only link replaced is one of ours whose target is gone.
#
# Every change is printed before it is made. ~/.local/bin is created mode 0755
# only when absent; an existing one keeps its mode. Shell rc files are never
# touched: when ~/.local/bin is not on PATH, the line to add is printed.
#
# Exit 0: the link points at this checkout. Exit 1: it does not; why is on
# stderr. Exit 2: usage.

set -euo pipefail

say()  { printf '==> %s\n' "$*"; }
warn() { printf '!   %s\n' "$*" >&2; }

[ $# -eq 1 ] || { warn "usage: $0 CHECKOUT"; exit 2; }
checkout="$(cd -- "$1" && pwd -P)"
want="$checkout/.venv/bin/hammunition"
bindir="$HOME/.local/bin"
link="$bindir/hammunition"
status=0

path_hint() {
  case ":${PATH:-}:" in
    *":$bindir:"*) ;;
    *)
      warn "$bindir is not on your PATH, so \`hammunition\` will not be found yet."
      warn "Add this line to ~/.profile, then log out and back in:"
      # shellcheck disable=SC2016  # the literal $HOME and $PATH are the point
      printf '    export PATH="$HOME/.local/bin:$PATH"\n' >&2
      ;;
  esac
}

if [ ! -x "$want" ]; then
  warn "$want does not exist or is not executable; run ./bootstrap.sh first."
  exit 1
fi

# -L before -d: a symlink or file at ~/.local/bin is not ours to create over.
if [ -L "$bindir" ] || [ -e "$bindir" ]; then
  if [ ! -d "$bindir" ]; then
    warn "$bindir exists and is not a directory; left as it is."
    exit 1
  fi
else
  say "creating $bindir (mode 0755)"
  mkdir -p -- "$HOME/.local"
  mkdir -m 0755 -- "$bindir"
fi

# Every test of $link below starts with -L, so a symlink is judged by what it
# says (readlink), never by what it points to.
if [ -L "$link" ]; then
  current="$(readlink -- "$link")"
  if [ "$current" = "$want" ]; then
    say "$link already points at this checkout"
  elif [[ "$current" == */.venv/bin/hammunition ]] && [ ! -e "$link" ]; then
    say "replacing $link, whose checkout ($current) is gone, with a link to $want"
    ln -sfn -- "$want" "$link"
  elif [[ "$current" == */.venv/bin/hammunition ]]; then
    warn "$link points at another checkout ($current); left as it is."
    warn "To use this checkout instead: ln -sfn '$want' '$link'"
    status=1
  else
    warn "$link is a symlink to $current, which this script did not create; left as it is."
    status=1
  fi
elif [ -e "$link" ]; then
  warn "$link exists and is not a link this script created; left as it is."
  status=1
else
  say "linking $link -> $want"
  ln -s -- "$want" "$link"
fi

path_hint
exit "$status"
