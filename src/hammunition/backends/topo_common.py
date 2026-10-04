# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the US Topo backend and the FSTopo backend share, in a module neither
imports the other for: the file suffixes, a sheet's ledger key and the
replace-an-older-edition step. ``topo`` hands its FSTopo half to ``fstopo``,
so ``fstopo`` must not import ``topo`` back."""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from pathlib import Path

from .base import Action, Command
from .regions import SOURCE
from .verified import PrefixWriter

TIF = ".tif"
QUADS = ".quads"


def stem_of(name: str) -> str:
    """A sheet's name without its edition date: ``VT_Name_20240101`` -> ``VT_Name``."""
    return name.rsplit("_", 1)[0]


def replaced_steps(
    directory: Path, wanted: Sequence[str], writer: PrefixWriter, what: str
) -> tuple[set[str], list[Action | Command]]:
    """(the installed names an edition in *wanted* replaces, a step removing
    each only once its replacement is on disk).

    Review I1: an older edition removed before its newer one installed left
    a hole in the map until the next online run. The removal is judged by the
    effect -- the new file there -- never by a ledger read ahead of time, and
    runs after every install; a replacement that did not arrive keeps the old
    one, and says so."""
    if not directory.is_dir():
        return set(), []
    by_stem = {stem_of(name): name for name in wanted}
    old: set[str] = set()
    steps: list[Action | Command] = []
    for path in sorted(directory.glob(f"*{TIF}")):
        name = path.name[: -len(TIF)]
        new = by_stem.get(stem_of(name))
        if new is None or new == name or not path.is_file():
            continue
        old.add(name)
        steps.append(
            Action(
                kind="remove-data",
                description=(
                    f"Remove {what} {name} once its newer edition {new} is installed; "
                    f"kept if it is not"
                ),
                detail=str(path),
                perform=partial(_replace, writer, path, directory / f"{new}{TIF}"),
                requires_root=writer.privileged,
            )
        )
    return old, steps


def _replace(writer: PrefixWriter, old: Path, new: Path) -> str:
    if not new.is_file():
        return f"kept {old}: its newer edition {new.name} is not installed"
    writer.remove([old, old.with_name(old.name + SOURCE)])
    return f"removed {old}; replaced by {new.name}"


def quad_key(name: str) -> str:
    """The ledger key of a sheet: its name, which no slug or tile can be."""
    return f"quad {name}"
