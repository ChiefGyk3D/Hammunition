# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Curated desktop menus, generated from the catalog's own categories. D-036.

Two of the three measured mechanisms (the D-036 addendum has the
measurements; COSMIC waits for a Pop!_OS machine to exist):

- **The freedesktop menu spec** — Xfce and every menu-spec DE. A merged
  ``.menu`` file in the user's ``menus`` config builds a "Ham Radio" tree
  with one submenu per catalog category, each including by the
  ``X-Hammunition-<category>`` marker the launcher generator writes into
  every desktop entry — and, by ``<Filename>``, the desktop entries the
  installed catalog packages ship themselves, placed under the submenu of
  their manifest's categories. Measured on the Kali VM (2026-09-01): 43 of
  the distribution's own ``HamRadio`` entries sat scattered under Internet,
  Multimedia, Education and Other while the curated tree held the 7
  generated launchers, and 42 of the 43 mapped back to a manifest through
  ``dpkg -L`` of its apt package. Anything ``HamRadio``-tagged that no
  manifest claims is gathered at the tree's top level, so a source build's
  ``make install`` entry under ``/usr/local`` still lands in Ham Radio.
  One taxonomy: the tree is rendered from ``catalog/categories.yaml``, the
  same vocabulary the manifests use, and the desktop-file ids come from
  the machine at apply time, never from a maintained list.
- **GNOME app-folders** — GNOME Shell renders no nested menus; its folders
  live in gsettings. One "Ham Radio" folder declaring
  ``categories=['HamRadio']`` populates itself from the same entries with
  no app list to maintain. Applied as commands, because dconf needs the
  operator's session bus: run ``hammunition menus apply`` in a desktop
  session, and over SSH it fails loudly instead of pretending.

Everything here is per-user and unprivileged — the property both measured
mechanisms share and the launcher artifacts already have.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from xml.sax.saxutils import escape

from hammunition.backends.base import Action, Command
from hammunition.manifest.schema import AptInstall, BinaryInstall, PackageManifest

__all__ = [
    "Category",
    "DesktopIdLister",
    "MenuPaths",
    "MenuPrefixError",
    "Placement",
    "gnome_commands",
    "menu_steps",
    "place_installed_entries",
    "render_directory",
    "render_menu",
    "resolve_menu_prefix",
    "root_menu_prefixes",
]

MENU_NAME = "Ham Radio"
GNOME_FOLDER = "HamRadio"


class MenuPrefixError(Exception):
    """The merged file's name could not be decided, so nothing was written."""


def root_menu_prefixes(config_dirs: Iterable[Path]) -> list[str]:
    """Every ``<prefix>`` for which a ``<prefix>applications.menu`` root exists.

    The root menus a machine carries are the measurement of which DEs can
    read a merged file: each is a ``menus/<prefix>applications.menu`` under
    ``$XDG_CONFIG_DIRS`` and merges ``<prefix>applications-merged/`` and
    nothing else. Measured 2026-09-02: no machine in the VM set nor the
    maintainer's laptop has a bare ``applications.menu``; Parrot has four
    prefixed roots (``kf5-``, ``mate-``, ``plasma-``, ``xfce-``), Debian and
    the laptop ``gnome-``, Kali ``xfce-``, a server image none.
    """
    found: dict[str, None] = {}
    for config_dir in config_dirs:
        for root in sorted((config_dir / "menus").glob("*applications.menu")):
            found[root.name[: -len("applications.menu")]] = None
    return list(found)


def resolve_menu_prefix(
    explicit: str | None,
    environment: str | None,
    config_dirs: Iterable[Path],
) -> str:
    """Decide which root menu the merged file is for -- or refuse.

    An explicit ``--menu-prefix`` wins, then the session's
    ``$XDG_MENU_PREFIX``. With neither -- ``sudo``, a shell older than the
    login, plain SSH -- the empty prefix used to be written and merged into
    nothing on every measured machine, silently. Now the installed root
    menus decide: exactly one prefixed root means that one; a bare root and
    no prefixed ones means the empty prefix; several means a refusal that
    names them, because guessing which desktop the operator logs into is
    how a menu gets written for the one they do not.
    """
    if explicit is not None:
        return explicit
    if environment:
        return environment
    prefixes = root_menu_prefixes(config_dirs)
    if len(prefixes) == 1:
        return prefixes[0]
    if not prefixes:
        raise MenuPrefixError(
            "no root menu found (no <prefix>applications.menu under "
            + ", ".join(str(d / "menus") for d in config_dirs)
            + ") -- there is no menu to merge into on this machine"
        )
    listed = ", ".join(f"--menu-prefix {p!r}" for p in prefixes)
    raise MenuPrefixError(
        "$XDG_MENU_PREFIX is not set and this machine has "
        f"{len(prefixes)} root menus -- run this inside your desktop session, "
        f"or say which one: {listed}"
    )


@dataclass(frozen=True)
class Category:
    """One entry of the catalog vocabulary, as the menu needs it."""

    name: str
    summary: str
    title: str = ""
    """How the tag reads on a menu — ``SDR``, not ``Sdr``. Falls back to a
    title-cased name, which is wrong for every acronym; the vocabulary carries
    the real one."""

    @property
    def label(self) -> str:
        return self.title or self.name.replace("-", " ").title()


@dataclass(frozen=True)
class Placement:
    """Where the installed catalog packages' own desktop entries go.

    ``by_category`` maps a category tag to the desktop-file ids (``wsjtx.desktop``)
    of entries shipped by installed packages whose manifest carries that tag.
    ``claimed`` is every id placed anywhere plus every generated launcher's id —
    the set the top-level ``HamRadio`` catch-all must exclude, or each of them
    shows twice.
    """

    by_category: dict[str, tuple[str, ...]]
    claimed: tuple[str, ...]

    @classmethod
    def empty(cls) -> Placement:
        return cls(by_category={}, claimed=())


DesktopIdLister = Callable[[str], list[str]]
"""Given an installed package name, the desktop-file ids it ships (empty if
the package is not installed). Injected so the placement is testable without
dpkg; :func:`dpkg_desktop_ids` is the real one."""


def dpkg_desktop_ids(package: str) -> list[str]:
    """The desktop entries an installed package put under the XDG data dir.

    ``dpkg-query -L`` is unprivileged and exits 1 for a package that is not
    installed, which is the ordinary case for most of the catalog and not an
    error here.
    """
    result = subprocess.run(
        ["dpkg-query", "-L", package], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
    return sorted(
        Path(line).name
        for line in result.stdout.splitlines()
        if line.startswith("/usr/share/applications/") and line.endswith(".desktop")
    )


def place_installed_entries(
    manifests: Iterable[PackageManifest], lister: DesktopIdLister = dpkg_desktop_ids
) -> Placement:
    """Map each installed catalog package's own desktop entries to its
    manifest's categories.

    The whole catalog is consulted, not only what the transaction log says
    Hammunition installed: being in the catalog *is* the curation, and an
    operator who installed ``fldigi`` with apt last year is served by the
    same submenu. A package that is not installed lists nothing, so the
    result describes this machine.
    """
    by_category: dict[str, set[str]] = {}
    claimed: set[str] = set()
    for manifest in manifests:
        for launcher in manifest.launchers:
            claimed.add(f"hammunition-{launcher.name}.desktop")
        packages: set[str] = set()
        for block in manifest.install:
            method = block.install
            if isinstance(method, AptInstall):
                packages.update(p for p in method.packages if not p.startswith("-"))
            elif isinstance(method, BinaryInstall) and method.deb_package:
                packages.add(method.deb_package)
        ids = {desktop_id for package in sorted(packages) for desktop_id in lister(package)}
        if not ids:
            continue
        claimed.update(ids)
        for category in manifest.categories:
            by_category.setdefault(category, set()).update(ids)
    return Placement(
        by_category={k: tuple(sorted(v)) for k, v in sorted(by_category.items())},
        claimed=tuple(sorted(claimed)),
    )


@dataclass(frozen=True)
class MenuPaths:
    """Where the per-user artifacts land."""

    menus_dir: Path
    """``~/.config/menus/<prefix>applications-merged`` — the merge point."""

    directories_dir: Path
    """``~/.local/share/desktop-directories`` — the .directory entries."""


def render_menu(categories: list[Category], placement: Placement | None = None) -> str:
    """The merged ``.menu`` XML: one tree, one submenu per category.

    Each submenu includes by the ``X-Hammunition-<category>`` marker (the
    generated launchers) and by ``<Filename>`` (the entries installed
    packages ship, from ``placement``). The tree's own level includes every
    ``HamRadio``-tagged entry the submenus did not claim, so nothing radio
    is left scattered through the DE's flat categories — D-036's "alongside
    the DE's own organization", with the DE's own copies untouched.
    """
    placement = placement or Placement.empty()

    def filenames(ids: tuple[str, ...], indent: str) -> str:
        return "".join(f"\n{indent}<Filename>{escape(i)}</Filename>" for i in ids)

    submenus = "\n".join(
        f"""    <Menu>
      <Name>hammunition-{escape(c.name)}</Name>
      <Directory>hammunition-{escape(c.name)}.directory</Directory>
      <Include>
        <Category>X-Hammunition-{escape(c.name)}</Category>{filenames(placement.by_category.get(c.name, ()), "        ")}
      </Include>
    </Menu>"""
        for c in categories
    )
    catch_all = "    <Include><Category>HamRadio</Category></Include>"
    if placement.claimed:
        catch_all += f"\n    <Exclude>{filenames(placement.claimed, '      ')}\n    </Exclude>"
    return f"""<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
 "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<!-- generated by hammunition (D-036); regenerate with `hammunition menus apply` -->
<Menu>
  <Name>Applications</Name>
  <Menu>
    <Name>{MENU_NAME}</Name>
    <Directory>hammunition-hamradio.directory</Directory>
{catch_all}
{submenus}
  </Menu>
</Menu>
"""


def render_directory(name: str, comment: str) -> str:
    return f"[Desktop Entry]\nType=Directory\nName={name}\nComment={comment}\nIcon=folder\n"


def _write(path: Path, body: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    os.chmod(path, 0o644)
    return f"wrote {path}"


def menu_steps(
    categories: list[Category],
    paths: MenuPaths,
    *,
    menu_prefix: str,
    placement: Placement | None = None,
) -> list[Action]:
    """The file half — inert data any menu-spec DE picks up on next login.

    ``menu_prefix`` is the DE's ``$XDG_MENU_PREFIX`` (``xfce-`` on Xfce,
    empty on most others); the merged file must match the root menu's name
    or nothing merges, which is a silent nothing — hence it is a parameter,
    not a guess.
    """
    placed = sum(len(v) for v in (placement or Placement.empty()).by_category.values())
    steps = [
        Action(
            kind="menu",
            description=(
                f"Write the {MENU_NAME} menu tree ({len(categories)} categories, "
                f"{placed} installed-package entries placed)"
            ),
            detail=str(paths.menus_dir / f"{menu_prefix}applications-merged" / "hammunition.menu"),
            perform=partial(
                _write,
                paths.menus_dir / f"{menu_prefix}applications-merged" / "hammunition.menu",
                render_menu(categories, placement),
            ),
        ),
        Action(
            kind="menu",
            description=f"Name the top-level {MENU_NAME} directory entry",
            detail=str(paths.directories_dir / "hammunition-hamradio.directory"),
            perform=partial(
                _write,
                paths.directories_dir / "hammunition-hamradio.directory",
                render_directory(MENU_NAME, "Amateur radio, SDR and RF tools from Hammunition"),
            ),
        ),
    ]
    for category in categories:
        target = paths.directories_dir / f"hammunition-{category.name}.directory"
        steps.append(
            Action(
                kind="menu",
                description=f"Name the {category.name} submenu",
                detail=str(target),
                perform=partial(
                    _write,
                    target,
                    render_directory(category.label, category.summary),
                ),
            )
        )
    return steps


def gnome_commands(placement: Placement | None = None) -> list[Command]:
    """The GNOME half — an app-folder populated by category, via gsettings.

    ``categories=['HamRadio']`` already gathers every entry tagged HamRadio,
    including the ones distributions ship. The entries a catalog package
    ships *without* that tag (Kali's ``gqrx`` and ``chirp`` carry Kali's own
    ``kali-radio-frequency`` instead; ``welle.io`` says ``AudioVideo``) are
    appended to the folder's ``apps`` list from ``placement`` — a union, so
    re-running adds nothing twice and removes nothing the operator added.

    Needs the operator's session bus (dconf), so these are Commands the
    runner executes as the user: they succeed in a desktop session and fail
    loudly over bare SSH, which is the honest behaviour. Existing folders in
    ``folder-children`` are preserved by the read-modify-write script being
    avoided entirely: dconf list mutation without a shell means gsettings'
    own idempotent behaviour — setting the same folder twice is harmless,
    and the folder list append is done by the small python -c below, the
    one place argv cannot express "append to a list setting".
    """
    folder_path = f"/org/gnome/desktop/app-folders/folders/{GNOME_FOLDER}/"
    return [
        Command(
            argv=(
                "python3",
                "-c",
                (
                    "import subprocess, ast\n"
                    "current = subprocess.run(['gsettings','get',"
                    "'org.gnome.desktop.app-folders','folder-children'],"
                    "capture_output=True,text=True,check=True).stdout.strip()\n"
                    "value = ast.literal_eval(current.removeprefix('@as '))\n"
                    f"name = {GNOME_FOLDER!r}\n"
                    "if name not in value:\n"
                    "    value.append(name)\n"
                    "    subprocess.run(['gsettings','set',"
                    "'org.gnome.desktop.app-folders','folder-children',str(value)],check=True)\n"
                    "print('folder-children:', value)\n"
                ),
            ),
            description=f"Register the {GNOME_FOLDER} app-folder with GNOME (append, never replace)",
        ),
        Command(
            argv=(
                "gsettings",
                "set",
                f"org.gnome.desktop.app-folders.folder:{folder_path}",
                "name",
                MENU_NAME,
            ),
            description="Name the folder",
        ),
        Command(
            argv=(
                "gsettings",
                "set",
                f"org.gnome.desktop.app-folders.folder:{folder_path}",
                "categories",
                "['HamRadio']",
            ),
            description="Populate it by category — no app list to maintain",
        ),
    ] + (
        [
            Command(
                argv=(
                    "python3",
                    "-c",
                    (
                        "import subprocess, ast\n"
                        f"schema = 'org.gnome.desktop.app-folders.folder:{folder_path}'\n"
                        "current = subprocess.run(['gsettings','get',schema,'apps'],"
                        "capture_output=True,text=True,check=True).stdout.strip()\n"
                        "value = ast.literal_eval(current.removeprefix('@as '))\n"
                        f"wanted = {list(placement.claimed)!r}\n"
                        "merged = value + [a for a in wanted if a not in value]\n"
                        "if merged != value:\n"
                        "    subprocess.run(['gsettings','set',schema,'apps',str(merged)],check=True)\n"
                        "print('apps:', len(merged))\n"
                    ),
                ),
                description=(
                    f"Add the {len(placement.claimed)} installed-package entries by name "
                    "(union, never replace) — the ones not tagged HamRadio need it"
                ),
            )
        ]
        if placement and placement.claimed
        else []
    )
