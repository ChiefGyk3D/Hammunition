# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What ``hammunition maps comaps`` prepares before CoMaps starts.  D-069.

Two per-user things, done at launch by the operator's own process and never
at install, where root would be writing into a home:

- **The licence acceptance.** CoMaps shows a modal dialog with its licence
  and copyright notice (``copyright.html``) until ``EulaAccepted=true`` is in
  ``~/.config/CoMaps/settings.ini`` (``qt/main.cpp`` at the pinned commit).
  The file is ``key=value`` lines with no sections, and a key that appears
  twice fails a ``VERIFY`` in ``string_storage_base.cpp``, so the line is
  added only when the key is absent. An answer already there, either one,
  is the operator's and is left.
- **The maps.** CoMaps looks for country maps in version directories under
  its writable directory (``<writable>/<version>/<id>.mwm``) and reads them
  with ``stat``, which follows a symbolic link
  (``platform_unix_impl.cpp``). Each map ``comaps-maps`` installed is linked
  there. A regular file of the same name -- a map the operator downloaded in
  the app -- is left; a link of ours whose map is gone is removed; nothing
  else is touched.

Measured from source, not run: whether CoMaps loads the linked maps on a
running desktop is the bench's to say.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

EULA_KEY = "EulaAccepted"
EULA_LINE = f"{EULA_KEY}=true"


def settings_path(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    """Qt's GenericConfigLocation plus ``CoMaps``, as ``platform_linux.cpp`` builds it."""
    base = environ.get("XDG_CONFIG_HOME") or str((home or Path.home()) / ".config")
    return Path(base) / "CoMaps" / "settings.ini"


def data_dir(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    """Where the launcher points ``MWM_WRITABLE_DIR``: CoMaps' maps, bookmarks
    and tracks for this operator. Set explicitly so it does not depend on how
    Qt names the application before it is started."""
    base = environ.get("XDG_DATA_HOME") or str((home or Path.home()) / ".local" / "share")
    return Path(base) / "CoMaps"


def ensure_eula(text: str) -> str:
    """*text* with ``EulaAccepted=true`` appended when no line sets the key."""
    for line in text.splitlines():
        key, sep, _value = line.partition("=")
        if sep and key == EULA_KEY:
            return text
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}{EULA_LINE}\n"


def link_maps(installed: Path, writable: Path) -> list[str]:
    """Link each installed ``<version>/<id>.mwm`` into *writable*; say what was done."""
    notes: list[str] = []
    maps = (
        sorted(p for p in installed.glob("*/*.mwm") if p.is_file() and not p.is_symlink())
        if installed.is_dir()
        else []
    )
    made = kept = 0
    for target in maps:
        link = writable / target.parent.name / target.name
        if os.path.lexists(link):
            if link.is_symlink() and Path(os.readlink(link)) == target:
                kept += 1
                continue
            notes.append(
                f"{link} is not Hammunition's link to {target}; left as it is (a map "
                f"downloaded in CoMaps, or one you placed)"
            )
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        made += 1
    removed = 0
    if writable.is_dir():
        for link in sorted(writable.glob("*/*.mwm")):
            if not link.is_symlink():
                continue
            points = Path(os.readlink(link))
            if installed in points.parents and not points.exists():
                link.unlink()
                removed += 1
    if not maps:
        notes.append(
            "no CoMaps maps are installed yet: `hammunition install comaps-maps` fetches "
            "them for your map regions; CoMaps shows only its world overview until then"
        )
    else:
        notes.append(
            f"{len(maps)} map(s) from {installed} in {writable}: {made} new link(s), "
            f"{kept} already linked"
            + (f", {removed} link(s) to maps no longer installed removed" if removed else "")
        )
    return notes
