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
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from hammunition.backends.base import Action, Command
from hammunition.manifest.schema import AptInstall, BinaryInstall, PackageManifest

__all__ = [
    "Category",
    "CliEntries",
    "CliEntry",
    "DesktopIdLister",
    "Group",
    "MenuPaths",
    "MenuPrefixError",
    "Placement",
    "Vocabulary",
    "cli_entries",
    "cli_entry_steps",
    "gnome_commands",
    "load_vocabulary",
    "menu_steps",
    "merge_dir",
    "place_installed_entries",
    "refresh_command",
    "render_cli_entry",
    "render_directory",
    "render_menu",
    "resolve_menu_prefix",
    "root_menu_prefixes",
]

MENU_NAME = "Hammunition"
GNOME_FOLDER = "HamRadio"


class MenuPrefixError(Exception):
    """The merged file's name could not be decided, so nothing was written."""


def root_menu_prefixes(config_dirs: Iterable[Path]) -> list[str]:
    """Every ``<prefix>`` for which a ``<prefix>applications.menu`` root exists.

    The root menus a machine carries are the measurement of which DEs can
    read a merged file: each is a ``menus/<prefix>applications.menu`` under
    ``$XDG_CONFIG_DIRS`` and merges one directory -- which one is
    :func:`merge_dir`'s measurement. Measured 2026-09-02: no machine in the VM set nor the
    maintainer's laptop has a bare ``applications.menu``; Parrot has four
    prefixed roots (``kf5-``, ``mate-``, ``plasma-``, ``xfce-``), Debian and
    the laptop ``gnome-``, Kali ``xfce-``, a server image none.
    """
    found: dict[str, None] = {}
    for config_dir in config_dirs:
        for root in sorted((config_dir / "menus").glob("*applications.menu")):
            found[root.name[: -len("applications.menu")]] = None
    return list(found)


def merge_dir(menu_prefix: str) -> str:
    """The directory the root menu's ``<DefaultMergeDirs/>`` actually reads.

    The spec says ``<prefix>applications-merged``, and Xfce's garcon does
    that (Kali, 2026-09-02). **KDE's kservice ignores the prefix**: on the
    field laptop (Plasma 6, ``XDG_MENU_PREFIX=plasma-``, 2026-09-12)
    ``kbuildsycoca6`` reported *Found menu file
    /etc/xdg/menus/applications-merged/parrot-applications.menu* and never
    opened ``plasma-applications-merged/``, where this tree had been written
    and where nothing read it -- no Ham Radio menu, every generated entry
    in Lost & Found. Parrot's own menu ships in ``applications-merged`` for
    the same reason.
    """
    if menu_prefix in ("plasma-", "kf5-"):
        return "applications-merged"
    return f"{menu_prefix}applications-merged"


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
class Group:
    """One of the tree's second-level headings (D-050): Parrot's own tool
    menu is one top menu, numbered groups, then subcategories, and the flat
    27-sibling tree was the thing the maintainer could not find anything in.
    ``order`` is the menu's order — a ``<Layout>``, not the alphabet."""

    order: int
    name: str
    title: str
    summary: str
    categories: tuple[str, ...]
    menu: bool = True
    """``menu: false`` hides the group and its categories from every desktop
    integration: no submenu, no folder, no generated entry, and the packaged
    entries of a unit tagged only there are left where the desktop already
    puts them. Workstation is the case -- git, tmux and VS Code are catalog
    units, not radio software (maintainer, 2026-09-12)."""


@dataclass(frozen=True)
class Vocabulary:
    categories: list[Category]
    groups: list[Group]
    """In ``order``. Empty when the file declares none, and the tree is flat."""

    @property
    def hidden_categories(self) -> frozenset[str]:
        return frozenset(c for g in self.groups if not g.menu for c in g.categories)


def load_vocabulary(path: Path) -> Vocabulary:
    """``catalog/categories.yaml`` as the menu needs it: the categories in
    file order, the groups sorted by their declared order."""
    data = yaml.safe_load(path.read_text())
    categories = [
        Category(name=c["name"], summary=c["summary"], title=c.get("title", ""))
        for c in data["categories"]
    ]
    groups = sorted(
        (
            Group(
                order=int(g["order"]),
                name=g["name"],
                title=g["title"],
                summary=g["summary"],
                categories=tuple(g["categories"]),
                menu=bool(g.get("menu", True)),
            )
            for g in data.get("groups", [])
        ),
        key=lambda g: g.order,
    )
    return Vocabulary(categories=categories, groups=groups)


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

    replaced: tuple[tuple[str, str, str], ...] = ()
    """``(package, shipped id, id placed instead)`` — a packaged entry that is
    gone from disk and was placed by the distribution's own copy (#64)."""

    missing: tuple[tuple[str, str], ...] = ()
    """``(package, shipped id)`` — gone from disk with nothing to place; the
    summary names it rather than counting it as placed."""

    units: tuple[str, ...] = ()
    """Catalog units that received at least one placed entry — the ones
    :func:`cli_entries` must not generate a second entry for."""

    @classmethod
    def empty(cls) -> Placement:
        return cls(by_category={}, claimed=())


DesktopIdLister = Callable[[str], list[str]]
"""Given an installed package name, the desktop-file ids it ships (empty if
the package is not installed). Injected so the placement is testable without
dpkg; :func:`dpkg_desktop_ids` is the real one."""

APPLICATIONS_DIR = Path("/usr/share/applications")


@dataclass(frozen=True)
class OnDisk:
    """What a package's shipped desktop entries look like on *this* disk."""

    ids: tuple[str, ...]
    replaced: tuple[tuple[str, str], ...]
    missing: tuple[str, ...]


def on_disk(package: str, shipped: Iterable[str], applications_dir: Path) -> OnDisk:
    """Reconcile ``dpkg -L``'s list with the files that exist.

    ``dpkg -L`` is what the package *shipped*; it is not what is on disk after
    a distribution has had its say. Parrot's ``parrot-menu`` runs from an apt
    ``DPkg::Post-Invoke`` hook after every apt run and rewrites the launcher
    set — removing the packaged ``chirp.desktop`` and writing
    ``parrot-chirp.desktop`` in its place (field laptop, 2026-09-12, #64).
    A ``<Filename>`` for a file that is not there places nothing and the
    summary counted it anyway. So: an entry that exists is placed as shipped;
    one that is gone is placed by ``parrot-<package>.desktop`` when that
    exists; otherwise it is reported as missing, never counted.
    """
    ids: list[str] = []
    replaced: list[tuple[str, str]] = []
    missing: list[str] = []
    replacement = f"parrot-{package}.desktop"
    for desktop_id in shipped:
        if (applications_dir / desktop_id).exists():
            ids.append(desktop_id)
        elif (applications_dir / replacement).exists():
            if replacement not in ids:
                ids.append(replacement)
            replaced.append((desktop_id, replacement))
        else:
            missing.append(desktop_id)
    return OnDisk(ids=tuple(ids), replaced=tuple(replaced), missing=tuple(missing))


def placement_summary(placement: Placement) -> list[str]:
    """The lines after the count, so the count cannot stand alone as a lie."""
    lines = [
        f"  {package}: {shipped} is not on disk; placed the distribution's {instead} instead"
        for package, shipped, instead in placement.replaced
    ]
    lines.extend(
        f"  {package}: {shipped} is not on disk and nothing replaces it -- not placed"
        for package, shipped in placement.missing
    )
    return lines


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
    manifests: Iterable[PackageManifest],
    lister: DesktopIdLister = dpkg_desktop_ids,
    *,
    applications_dir: Path | None = None,
    hidden: frozenset[str] = frozenset(),
) -> Placement:
    """Map each installed catalog package's own desktop entries to its
    manifest's categories.

    The whole catalog is consulted, not only what the transaction log says
    Hammunition installed: being in the catalog *is* the curation, and an
    operator who installed ``fldigi`` with apt last year is served by the
    same submenu. A package that is not installed lists nothing, so the
    result describes this machine.

    ``applications_dir`` is where the entries must actually exist; ``None``
    trusts the lister (the fixtures' case). The CLI passes the real directory,
    because ``dpkg -L`` alone was wrong on Parrot (#64, :func:`on_disk`).
    """
    by_category: dict[str, set[str]] = {}
    claimed: set[str] = set()
    replaced: list[tuple[str, str, str]] = []
    missing: list[tuple[str, str]] = []
    units: list[str] = []
    for manifest in manifests:
        visible = [c for c in manifest.categories if c not in hidden]
        if not visible:
            continue
        for launcher in manifest.launchers:
            claimed.add(f"hammunition-{launcher.name}.desktop")
        packages = _packages_of(manifest)
        ids: set[str] = set()
        for package in sorted(packages):
            shipped = lister(package)
            if applications_dir is None:
                ids.update(shipped)
                continue
            found = on_disk(package, shipped, applications_dir)
            ids.update(found.ids)
            replaced.extend((package, was, now) for was, now in found.replaced)
            missing.extend((package, was) for was in found.missing)
        if not ids:
            continue
        units.append(manifest.name)
        claimed.update(ids)
        for category in visible:
            by_category.setdefault(category, set()).update(ids)
    return Placement(
        by_category={k: tuple(sorted(v)) for k, v in sorted(by_category.items())},
        claimed=tuple(sorted(claimed)),
        replaced=tuple(replaced),
        missing=tuple(missing),
        units=tuple(units),
    )


def _packages_of(manifest: PackageManifest) -> set[str]:
    """The distribution packages a manifest's install blocks name."""
    packages: set[str] = set()
    for block in manifest.install:
        method = block.install
        if isinstance(method, AptInstall):
            packages.update(method.packages)
        elif isinstance(method, BinaryInstall) and method.deb_package:
            packages.add(method.deb_package)
    return packages


# ---------------------------------------------------------------------------
# D-050: an entry for every installed unit, so the launcher's search finds it.
# ---------------------------------------------------------------------------

ExecutableLister = Callable[[str], list[str]]
"""Given an installed package name, the executables it put on the system
path (empty if not installed). Injected like :data:`DesktopIdLister`."""

_BIN_DIRS = ("/usr/bin/", "/usr/sbin/", "/usr/local/bin/")


def dpkg_executables(package: str) -> list[str]:
    result = subprocess.run(
        ["dpkg-query", "-L", package], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
    return sorted(
        line
        for line in result.stdout.splitlines()
        if line.startswith(_BIN_DIRS) and os.path.isfile(line) and os.access(line, os.X_OK)
    )


@dataclass(frozen=True)
class CliEntry:
    unit: str
    exec: str
    comment: str
    categories: tuple[str, ...]

    @property
    def desktop_id(self) -> str:
        return f"hammunition-cli-{self.unit}.desktop"


@dataclass(frozen=True)
class CliEntries:
    entries: tuple[CliEntry, ...]
    skipped: tuple[tuple[str, str], ...]
    """``(unit, why)`` — installed, no entry, and no executable this can name
    without guessing. A ``launchers`` block in the manifest is the fix."""


def cli_entries(
    manifests: Iterable[PackageManifest],
    placement: Placement,
    executables: ExecutableLister = dpkg_executables,
    hidden: frozenset[str] = frozenset(),
) -> CliEntries:
    """One generated entry per installed catalog unit that has none.

    Parrot's own menu does this for 572 of its 671 entries: a terminal
    launcher with a Comment, so the launcher's search finds ``gpsd`` by
    name or by what it does. The executable is the one named like the unit,
    else the package's only one; several and none named like the unit is a
    guess this refuses to make (``rtl-sdr``: six tools), and the summary
    names the unit so a ``launchers`` block gets written instead.
    """
    entries: list[CliEntry] = []
    skipped: list[tuple[str, str]] = []
    for manifest in manifests:
        if manifest.launchers or manifest.name in placement.units:
            continue
        visible = tuple(c for c in manifest.categories if c not in hidden)
        if not visible:
            continue
        on_path = [e for package in sorted(_packages_of(manifest)) for e in executables(package)]
        if not on_path:
            continue
        # sbin is the system's: a daemon systemd owns (gpsd) or an admin
        # tool, not an application to open from a menu.
        found = [e for e in on_path if not e.startswith("/usr/sbin/")]
        if not found:
            skipped.append(
                (
                    manifest.name,
                    f"only /usr/sbin executables ({', '.join(Path(e).name for e in on_path[:4])}): "
                    f"a service, not an application",
                )
            )
            continue
        named = [e for e in found if Path(e).name == manifest.name]
        if len(named) == 1:
            chosen = named[0]
        elif len(found) == 1:
            chosen = found[0]
        else:
            names = ", ".join(Path(e).name for e in found[:6]) + (", …" if len(found) > 6 else "")
            skipped.append(
                (manifest.name, f"{len(found)} executables, none named {manifest.name}: {names}")
            )
            continue
        entries.append(
            CliEntry(
                unit=manifest.name,
                exec=chosen,
                comment=manifest.summary,
                categories=visible,
            )
        )
    return CliEntries(entries=tuple(entries), skipped=tuple(skipped))


def render_cli_entry(entry: CliEntry) -> str:
    markers = ";".join(f"X-Hammunition-{c}" for c in entry.categories)
    keywords = ";".join((*entry.categories, entry.unit))
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={entry.unit}\n"
        f"Comment={entry.comment}\n"
        f"Exec={entry.exec}\n"
        "Terminal=true\n"
        f"Categories={markers};\n"
        f"Keywords={keywords};\n"
        f"X-Hammunition-Package={entry.unit}\n"
        "X-Hammunition-Generated=cli\n"
    )


def _remove(path: Path) -> str:
    path.unlink()
    return f"removed {path}"


def cli_entry_steps(result: CliEntries, applications_dir: Path) -> list[Action]:
    """Write this run's entries; remove ours from earlier runs that this run
    did not produce (the unit was uninstalled, or now ships an entry).
    Only ``hammunition-cli-*.desktop`` is ours to prune — a launcher's
    ``hammunition-<name>.desktop`` belongs to the install that wrote it."""
    wanted = {entry.desktop_id for entry in result.entries}
    steps = [
        Action(
            kind="menu",
            description=f"Write a menu entry for {entry.unit} ({entry.exec})",
            detail=str(applications_dir / entry.desktop_id),
            perform=partial(_write, applications_dir / entry.desktop_id, render_cli_entry(entry)),
        )
        for entry in result.entries
    ]
    for stale in sorted(applications_dir.glob("hammunition-cli-*.desktop")):
        if stale.name not in wanted:
            steps.append(
                Action(
                    kind="menu",
                    description=f"Remove the entry of a unit no longer installed: {stale.name}",
                    detail=str(stale),
                    perform=partial(_remove, stale),
                )
            )
    return steps


def refresh_command(
    menu_prefix: str, which: Callable[[str], str | None] = shutil.which
) -> Command | None:
    """KDE reads its application cache, not the files: without a rebuild the
    new tree appears at next login. Measured on the field laptop (Plasma,
    2026-09-12); other desktops re-read on their own or are told to."""
    if menu_prefix not in ("plasma-", "kf5-"):
        return None
    for tool in ("kbuildsycoca6", "kbuildsycoca5"):
        path = which(tool)
        if path:
            return Command(
                argv=(path,),
                description="Rebuild KDE's application cache so the menu shows now",
                requires_root=False,
            )
    return None


@dataclass(frozen=True)
class MenuPaths:
    """Where the per-user artifacts land."""

    menus_dir: Path
    """``~/.config/menus/<prefix>applications-merged`` — the merge point."""

    directories_dir: Path
    """``~/.local/share/desktop-directories`` — the .directory entries."""


def render_menu(
    categories: list[Category],
    placement: Placement | None = None,
    groups: list[Group] | None = None,
) -> str:
    """The merged ``.menu`` XML: one tree, one submenu per category.

    Each submenu includes by the ``X-Hammunition-<category>`` marker (the
    generated launchers) and by ``<Filename>`` (the entries installed
    packages ship, from ``placement``). The tree's own level includes every
    ``HamRadio``-tagged entry the submenus did not claim, so nothing radio
    is left scattered through the DE's flat categories — D-036's "alongside
    the DE's own organization", with the DE's own copies untouched.
    """
    placement = placement or Placement.empty()
    groups = groups or []

    def filenames(ids: tuple[str, ...], indent: str) -> str:
        return "".join(f"\n{indent}<Filename>{escape(i)}</Filename>" for i in ids)

    def submenu(c: Category, indent: str) -> str:
        i = indent
        return (
            f"{i}<Menu>\n"
            f"{i}  <Name>hammunition-{escape(c.name)}</Name>\n"
            f"{i}  <Directory>hammunition-{escape(c.name)}.directory</Directory>\n"
            f"{i}  <Include>\n"
            f"{i}    <Category>X-Hammunition-{escape(c.name)}</Category>"
            f"{filenames(placement.by_category.get(c.name, ()), i + '    ')}\n"
            f"{i}  </Include>\n"
            f"{i}</Menu>"
        )

    by_name = {c.name: c for c in categories}
    grouped: set[str] = set()
    blocks: list[str] = []
    for group in groups:
        members = [by_name[n] for n in group.categories if n in by_name]
        grouped.update(c.name for c in members)
        if not group.menu:
            continue
        inner = "\n".join(submenu(c, "      ") for c in members)
        blocks.append(
            f"    <Menu>\n"
            f"      <Name>hammunition-group-{escape(group.name)}</Name>\n"
            f"      <Directory>hammunition-group-{escape(group.name)}.directory</Directory>\n"
            f"{inner}\n"
            f"    </Menu>"
        )
    # A category no group claims is still rendered, beside the groups: the
    # vocabulary test forbids it in the shipped file, and the renderer must
    # not be the second place that silently drops something.
    blocks.extend(submenu(c, "    ") for c in categories if c.name not in grouped)
    submenus = "\n".join(blocks)
    layout = ""
    if groups:
        names = "".join(
            f"\n      <Menuname>hammunition-group-{escape(g.name)}</Menuname>"
            for g in groups
            if g.menu
        )
        layout = (
            f"    <Layout>{names}\n"
            f'      <Merge type="menus"/>\n'
            f"      <Separator/>\n"
            f'      <Merge type="files"/>\n'
            f"    </Layout>\n"
        )
    catch_all = "    <Include><Category>HamRadio</Category></Include>"
    if placement.claimed:
        catch_all += f"\n    <Exclude>{filenames(placement.claimed, '      ')}\n    </Exclude>"
    return f"""<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
 "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<!-- generated by hammunition (D-036, D-050); regenerate with `hammunition menus apply` -->
<Menu>
  <Name>Applications</Name>
  <Menu>
    <Name>{MENU_NAME}</Name>
    <Directory>hammunition-hamradio.directory</Directory>
{layout}{catch_all}
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
    groups: list[Group] | None = None,
) -> list[Action]:
    """The file half — inert data any menu-spec DE picks up on next login.

    ``menu_prefix`` is the DE's ``$XDG_MENU_PREFIX`` (``xfce-`` on Xfce,
    empty on most others); the merged file must match the root menu's name
    or nothing merges, which is a silent nothing — hence it is a parameter,
    not a guess.
    """
    placed = sum(len(v) for v in (placement or Placement.empty()).by_category.values())
    target = paths.menus_dir / merge_dir(menu_prefix) / "hammunition.menu"
    steps = [
        Action(
            kind="menu",
            description=(
                f"Write the {MENU_NAME} menu tree ({len(categories)} categories, "
                f"{placed} installed-package entries placed)"
            ),
            detail=str(target),
            perform=partial(_write, target, render_menu(categories, placement, groups)),
        ),
    ]
    # A copy left where an earlier engine wrote it and nothing read it (the
    # prefixed directory on KDE) is removed, or it lingers as a second file
    # some future desktop might merge twice.
    for stale in sorted(paths.menus_dir.glob("*applications-merged/hammunition.menu")):
        if stale != target:
            steps.append(
                Action(
                    kind="menu",
                    description="Remove the tree from a directory this desktop does not read",
                    detail=str(stale),
                    perform=partial(_remove, stale),
                )
            )
    steps += [
        Action(
            kind="menu",
            description=f"Name the top-level {MENU_NAME} directory entry",
            detail=str(paths.directories_dir / "hammunition-hamradio.directory"),
            perform=partial(
                _write,
                paths.directories_dir / "hammunition-hamradio.directory",
                render_directory(MENU_NAME, "Amateur radio, SDR and RF tools"),
            ),
        ),
    ]
    hidden = {c for g in groups or [] if not g.menu for c in g.categories}
    for group in groups or []:
        if not group.menu:
            continue
        target = paths.directories_dir / f"hammunition-group-{group.name}.directory"
        steps.append(
            Action(
                kind="menu",
                description=f"Name the {group.title} group",
                detail=str(target),
                perform=partial(_write, target, render_directory(group.title, group.summary)),
            )
        )
    for category in categories:
        if category.name in hidden:
            continue
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
    written = {Path(step.detail).name for step in steps if step.detail.endswith(".directory")}
    for stale in sorted(paths.directories_dir.glob("hammunition-*.directory")):
        if stale.name not in written:
            steps.append(
                Action(
                    kind="menu",
                    description=f"Remove a directory entry the tree no longer has: {stale.name}",
                    detail=str(stale),
                    perform=partial(_remove, stale),
                )
            )
    return steps


def gnome_commands(
    placement: Placement | None = None, groups: list[Group] | None = None
) -> list[Command]:
    """The GNOME half — app-folders populated by category, via gsettings.

    With ``groups`` (D-050): GNOME cannot nest, so each visible group is one
    folder, *Hammunition · <title>*, populated by the ``X-Hammunition-<cat>``
    markers of its categories -- no app list to maintain -- plus the placed
    entries under those categories by name. Without ``groups`` the original
    single ``HamRadio`` folder is written, as first measured.

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
    if groups is not None:
        commands: list[Command] = []
        placement = placement or Placement.empty()
        for group in groups:
            if not group.menu:
                continue
            apps = sorted({i for c in group.categories for i in placement.by_category.get(c, ())})
            commands.extend(
                _gnome_folder(
                    f"hammunition-{group.name}",
                    f"{MENU_NAME} · {group.title}",
                    [f"X-Hammunition-{c}" for c in group.categories],
                    apps,
                )
            )
        return commands
    return _gnome_folder(
        GNOME_FOLDER, MENU_NAME, ["HamRadio"], list(placement.claimed) if placement else []
    )


def _gnome_folder(folder: str, name: str, categories: list[str], apps: list[str]) -> list[Command]:
    folder_path = f"/org/gnome/desktop/app-folders/folders/{folder}/"
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
                    f"name = {folder!r}\n"
                    "if name not in value:\n"
                    "    value.append(name)\n"
                    "    subprocess.run(['gsettings','set',"
                    "'org.gnome.desktop.app-folders','folder-children',str(value)],check=True)\n"
                    "print('folder-children:', value)\n"
                ),
            ),
            description=f"Register the {folder} app-folder with GNOME (append, never replace)",
        ),
        Command(
            argv=(
                "gsettings",
                "set",
                f"org.gnome.desktop.app-folders.folder:{folder_path}",
                "name",
                name,
            ),
            description=f"Name the folder {name}",
        ),
        Command(
            argv=(
                "gsettings",
                "set",
                f"org.gnome.desktop.app-folders.folder:{folder_path}",
                "categories",
                str(categories),
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
                        f"wanted = {apps!r}\n"
                        "merged = value + [a for a in wanted if a not in value]\n"
                        "if merged != value:\n"
                        "    subprocess.run(['gsettings','set',schema,'apps',str(merged)],check=True)\n"
                        "print('apps:', len(merged))\n"
                    ),
                ),
                description=(
                    f"Add the {len(apps)} installed-package entries by name "
                    "(union, never replace) — the ones not tagged by category need it"
                ),
            )
        ]
        if apps
        else []
    )
