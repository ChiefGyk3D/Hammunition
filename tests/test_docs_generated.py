# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generated documentation is generated, and regenerating it is a no-op.

CLAUDE.md: "Generated docs are generated... Never hand-edit a generated file."
That rule needs a check behind it or it is a comment. The failure it prevents
is quiet: a reference page edited by hand reads correctly, passes the link
checker, and is silently reverted the next time anyone runs the generator --
so the correction is lost and nobody learns it was.

The check is the cheap one that actually works: render into memory, compare
against what is on disk. It also catches the commoner case, which is not a
hand edit at all but a manifest changed without regenerating.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog, load_profiles  # noqa: E402

PACKAGES = REPO_ROOT / "docs" / "packages"
GENERATOR = REPO_ROOT / "scripts" / "gen_package_reference.py"


def _generator() -> object:
    spec = importlib.util.spec_from_file_location("gen_package_reference", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rendered() -> dict[str, str]:
    gen = _generator()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    vocabulary = {
        c["name"]: c["summary"]
        for c in yaml.safe_load((REPO_ROOT / "catalog" / "categories.yaml").read_text())[
            "categories"
        ]
    }
    rendered: dict[str, str] = gen.render(catalog, vocabulary)  # type: ignore[attr-defined]
    return rendered


def test_there_is_something_to_compare(rendered: dict[str, str]) -> None:
    """Guards the guard: an empty render would make every check below pass."""
    assert len(rendered) > 100
    assert "index.md" in rendered


def test_every_manifest_has_a_generated_page(rendered: dict[str, str]) -> None:
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    missing = sorted(name for name in catalog if f"{name}.md" not in rendered)
    assert not missing, f"no generated page for: {missing}"


def test_a_kernel_requirement_is_rendered_on_the_page(rendered: dict[str, str]) -> None:
    """`requires_kernel` is why a unit refuses on a 7.1 kernel; a reader must
    see it without opening the manifest."""
    assert "- **Needs from the kernel:** `ax25`" in rendered["ax25-tools.md"]
    assert "Needs from the kernel" not in rendered["direwolf.md"]


def test_a_desktop_restriction_is_rendered_on_the_page(rendered: dict[str, str]) -> None:
    """`desktops` is why the tray is deferred on an Xfce machine (D-060)."""
    assert "- **Desktops:** KDE Plasma only" in rendered["hammunition-tray.md"]
    assert "**Desktops:**" not in rendered["direwolf.md"]


def test_an_installed_tree_is_disclosed_as_a_change_to_the_machine(
    rendered: dict[str, str],
) -> None:
    """Issue #38, D-043: a tree unit's page says the tree is handed to the
    operator and why, under the same heading as every other modification, so
    that a reader on a shared machine learns it before installing. All five
    tree units get the bullet from the manifest, never by hand."""
    for name in ("yaac", "mshv", "js8spotter", "radiosonde-auto-rx", "supersdr"):
        page = rendered[f"{name}.md"]
        assert "## What it changes on your machine" in page, name
        assert f"`/usr/local/share/hammunition/{name}`" in page, name
        assert "D-043" in page, name
        assert f"undo: `hammunition uninstall {name}`" in page, name
    assert "What it changes on your machine" not in rendered["direwolf.md"]


def test_regenerating_is_a_no_op(rendered: dict[str, str]) -> None:
    on_disk = {p.name: p.read_text() for p in PACKAGES.glob("*.md")}
    stale = sorted(set(on_disk) - set(rendered))
    absent = sorted(set(rendered) - set(on_disk))
    changed = sorted(n for n in set(rendered) & set(on_disk) if rendered[n] != on_disk[n])
    assert not (stale or absent or changed), (
        "docs/packages/ is out of date — run scripts/gen_package_reference.py.\n"
        f"  pages for packages that no longer exist: {stale[:6]}\n"
        f"  packages with no page: {absent[:6]}\n"
        f"  pages whose manifest changed: {changed[:6]}"
    )


def test_generated_pages_say_they_are_generated() -> None:
    """So that someone opening one to fix a typo is told where to fix it."""
    unmarked = [
        p.name
        for p in PACKAGES.glob("*.md")
        if "gen_package_reference.py" not in p.read_text().split("\n")[0]
    ]
    assert not unmarked, f"generated pages with no generated-by line: {unmarked[:6]}"


# ---------------------------------------------------------------------------
# The capability matrix
#
# Its generator reads a measured apt sweep from the gitignored reference/probes
# tree, so a full regeneration check cannot run in CI. Two checks instead: the
# part that needs no probe runs everywhere, and the full no-op runs where the
# sweep exists. This is the same shape the programmer-class generator already
# uses, for the same reason.
# ---------------------------------------------------------------------------

MATRIX = REPO_ROOT / "docs" / "reference" / "capability-matrix.md"
PROBES = REPO_ROOT / "reference" / "probes"


def test_the_matrix_lists_every_manifest() -> None:
    """Runs everywhere, needs no probe, and catches the common staleness:
    a manifest added and the matrix not regenerated."""
    text = MATRIX.read_text()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    missing = sorted(name for name in catalog if f"| `{name}` |" not in text)
    assert not missing, (
        f"{len(missing)} manifest(s) absent from the capability matrix — "
        f"run scripts/gen_capability_matrix.py: {missing[:8]}"
    )


def test_the_matrix_lists_no_package_that_left_the_catalog() -> None:

    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    # Only the full table at the end. The legend above it uses the same row
    # shape to explain what `apt` means, and matching that reported `apt` as a
    # package the catalog had lost -- a check failing on its own documentation.
    _, _, table = MATRIX.read_text().partition("## Every manifest")
    listed = set(re.findall(r"^\| `([a-z0-9][a-z0-9.+-]*)` \|", table, re.M))
    assert listed, "found no package rows; the section heading must have changed"
    stale = sorted(listed - set(catalog))
    assert not stale, f"matrix names packages the catalog no longer has: {stale}"


@pytest.mark.skipif(
    not list(PROBES.glob("policy-cat-*.tsv")),
    reason="needs the apt sweep in reference/probes/ — see the generator's docstring",
)
def test_regenerating_the_matrix_is_a_no_op() -> None:
    import subprocess

    before = MATRIX.read_text()
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_capability_matrix.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    after = MATRIX.read_text()
    if before != after:
        MATRIX.write_text(before)
    assert result.returncode == 0, result.stderr

    def without_date(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("**Generated:**")]

    assert without_date(before) == without_date(after), (
        "docs/reference/capability-matrix.md is stale — regenerate it. If the "
        "sweep has moved, that is the point: the matrix is a measurement."
    )


@pytest.mark.skipif(
    not list(PROBES.glob("policy-cat-*.tsv")),
    reason="needs the apt sweep in reference/probes/ — see the generator's docstring",
)
def test_every_swept_target_measured_every_apt_name_the_catalog_references() -> None:
    """A name the sweep never asked about is not absent, and until 2026-09-03
    the matrix said it was: the list was kept by hand, ten manifests outran it,
    and every archive was reported as lacking all ten (D-031). The generator
    now derives the list; this asserts each sweep on disk was run from it."""
    spec = importlib.util.spec_from_file_location(
        "gen_capability_matrix", REPO_ROOT / "scripts" / "gen_capability_matrix.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wanted = set(module.apt_names(load_catalog(REPO_ROOT / "catalog" / "packages")))
    behind: dict[str, list[str]] = {}
    for swept in sorted(PROBES.glob("policy-cat-*.tsv")):
        asked = {ln.split("\t", 1)[0] for ln in swept.read_text().splitlines() if "\t" in ln}
        if wanted - asked:
            behind[swept.name] = sorted(wanted - asked)
    assert not behind, (
        "sweep predates the catalog — regenerate the list with "
        "`scripts/gen_capability_matrix.py --package-list` and re-sweep: "
        f"{behind}"
    )


# ---------------------------------------------------------------------------
# The parity coverage report
#
# Unlike the capability matrix this reads nothing but the catalog and
# dispositions.md, so every check here runs everywhere with no probe to skip on.
# ---------------------------------------------------------------------------

PARITY = REPO_ROOT / "docs" / "reference" / "parity-coverage.md"


def _parity_generator() -> object:
    spec = importlib.util.spec_from_file_location(
        "gen_parity_coverage", REPO_ROOT / "scripts" / "gen_parity_coverage.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_parity_alias_names_a_real_manifest() -> None:
    """A wrong alias hides a gap: the unit reports as covered by a manifest
    that does not exist, and the coverage number goes up for nothing. This is
    the failure the report itself warns about, asserted rather than warned."""
    gen = _parity_generator()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    broken = sorted(
        f"{unit} -> {target}"
        for unit, target in gen.ALIASES.items()  # type: ignore[attr-defined]
        if target not in catalog
    )
    assert not broken, f"parity aliases naming no manifest: {broken}"


def test_no_dispositioned_unit_is_unexplained() -> None:
    """Every CARRY/SUPERSEDE/REVIVE/ADD unit either has a manifest or a
    recorded reason it does not. A unit in neither list is work nobody has
    decided about, and it should be visible rather than absorbed into a
    percentage."""
    assert "## Outstanding and unexplained" not in PARITY.read_text(), (
        "parity-coverage.md lists units that owe a manifest, have none, and "
        "carry no recorded reason. Either write the manifest or add the reason "
        "to EXPLAINED in scripts/gen_parity_coverage.py."
    )


def test_regenerating_the_parity_report_is_a_no_op() -> None:
    import subprocess

    before = PARITY.read_text()
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_parity_coverage.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    after = PARITY.read_text()
    if before != after:
        PARITY.write_text(before)
    assert result.returncode == 0, result.stderr

    def without_date(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("**Generated:**")]

    assert without_date(before) == without_date(after), (
        "docs/reference/parity-coverage.md is stale — run "
        "scripts/gen_parity_coverage.py. A manifest was probably added without "
        "regenerating it."
    )


# ---------------------------------------------------------------------------
# The not-carried page
#
# Same shape as the parity report: reads nothing but the catalog and
# dispositions.md, so every check runs everywhere. Its generator validates its
# own curated tables against the dispositions index and exits non-zero when
# they disagree, so the no-op check below also fails when a disposition
# changes without this page's reasons following it.
# ---------------------------------------------------------------------------

NOT_CARRIED = REPO_ROOT / "docs" / "reference" / "not-carried.md"


def test_regenerating_the_not_carried_page_is_a_no_op() -> None:
    import subprocess

    before = NOT_CARRIED.read_text()
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_not_carried.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    after = NOT_CARRIED.read_text()
    if before != after:
        NOT_CARRIED.write_text(before)
    assert result.returncode == 0, result.stderr

    def without_date(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("**Generated:**")]

    assert without_date(before) == without_date(after), (
        "docs/reference/not-carried.md is stale — run scripts/gen_not_carried.py. "
        "Either a disposition changed or a reason table was edited without "
        "regenerating."
    )


def test_every_retired_unit_has_a_row() -> None:
    """The page's purpose asserted directly: every X unit in the dispositions
    index appears in the rendered page, so a retirement cannot be invisible."""
    spec = importlib.util.spec_from_file_location(
        "gen_not_carried", REPO_ROOT / "scripts" / "gen_not_carried.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = NOT_CARRIED.read_text()
    missing = sorted(
        unit for unit, code in module.parse_index() if code == "X" and f"| `{unit}` |" not in text
    )
    assert not missing, f"retired units with no row in not-carried.md: {missing}"


# ---------------------------------------------------------------------------
# The profile reference (docs/profiles/), same generated-is-generated contract
# as the package reference above.
# ---------------------------------------------------------------------------

PROFILE_DOCS = REPO_ROOT / "docs" / "profiles"


def _profile_generator() -> object:
    spec = importlib.util.spec_from_file_location(
        "gen_profile_reference", REPO_ROOT / "scripts" / "gen_profile_reference.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_profile_has_a_generated_page() -> None:
    gen = _profile_generator()
    rendered: dict[str, str] = gen.render()  # type: ignore[attr-defined]
    from hammunition.manifest.load import load_catalog, load_profiles

    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    profiles = load_profiles(REPO_ROOT / "catalog" / "profiles", catalog)
    missing = sorted(name for name in profiles if f"{name}.md" not in rendered)
    assert not missing, f"no generated page for profile(s): {missing}"
    assert "index.md" in rendered


def test_regenerating_the_profile_reference_is_a_no_op() -> None:
    gen = _profile_generator()
    rendered: dict[str, str] = gen.render()  # type: ignore[attr-defined]
    on_disk = {p.name: p.read_text() for p in PROFILE_DOCS.glob("*.md")}
    stale = sorted(set(on_disk) - set(rendered))
    absent = sorted(set(rendered) - set(on_disk))
    changed = sorted(n for n in set(rendered) & set(on_disk) if rendered[n] != on_disk[n])
    assert not (stale or absent or changed), (
        "docs/profiles/ is out of date — run scripts/gen_profile_reference.py.\n"
        f"  stale: {stale[:6]}\n  absent: {absent[:6]}\n  changed: {changed[:6]}"
    )


# ---------------------------------------------------------------------------
# Hardware reference — one page per device, generated from the device catalog.
# Same no-op contract as the package and profile references.
# ---------------------------------------------------------------------------

HARDWARE_DOCS = REPO_ROOT / "docs" / "hardware"


def _hardware_generator() -> object:
    spec = importlib.util.spec_from_file_location(
        "gen_hardware_reference", REPO_ROOT / "scripts" / "gen_hardware_reference.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_device_has_a_generated_page() -> None:
    gen = _hardware_generator()
    rendered: dict[str, str] = gen.render()  # type: ignore[attr-defined]
    from hammunition.manifest.load import load_hardware

    _classes, devices = load_hardware(REPO_ROOT / "catalog" / "hardware")
    missing = sorted(name for name in devices if f"{name}.md" not in rendered)
    assert not missing, f"no generated page for device(s): {missing}"
    assert "index.md" in rendered


def test_regenerating_the_hardware_reference_is_a_no_op() -> None:
    gen = _hardware_generator()
    rendered: dict[str, str] = gen.render()  # type: ignore[attr-defined]
    # A hand-written page (docs/hardware/power-control.md, D-056) is prose
    # the generator does not own and must never flag as stale. It identifies
    # itself by NOT carrying the generator's own HEADER stamp as its first
    # line -- see gen_hardware_reference.py's `_is_generated()` docstring for
    # why a filename allowlist was rejected in favour of this.
    is_generated = gen._is_generated  # type: ignore[attr-defined]
    on_disk = {p.name: p.read_text() for p in HARDWARE_DOCS.glob("*.md") if is_generated(p)}
    stale = sorted(set(on_disk) - set(rendered))
    absent = sorted(set(rendered) - set(on_disk))
    changed = sorted(n for n in set(rendered) & set(on_disk) if rendered[n] != on_disk[n])
    assert not (stale or absent or changed), (
        "docs/hardware/ is out of date — run scripts/gen_hardware_reference.py.\n"
        f"  stale: {stale[:6]}\n  absent: {absent[:6]}\n  changed: {changed[:6]}"
    )


# ---------------------------------------------------------------------------
# Schema reference — rendered from the pydantic models, cannot drift.
# ---------------------------------------------------------------------------

SCHEMA_DOC = REPO_ROOT / "docs" / "reference" / "schema.md"


def _schema_generator() -> object:
    spec = importlib.util.spec_from_file_location(
        "gen_schema_reference", REPO_ROOT / "scripts" / "gen_schema_reference.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_schema_model_is_documented() -> None:
    gen = _schema_generator()
    rendered: str = gen.render()  # type: ignore[attr-defined]
    models = gen._model_classes()  # type: ignore[attr-defined]
    missing = sorted(name for name in models if f"### `{name}`" not in rendered)
    assert not missing, f"schema model(s) absent from the reference: {missing}"


def test_regenerating_the_schema_reference_is_a_no_op() -> None:
    import difflib

    gen = _schema_generator()
    rendered: str = gen.render()  # type: ignore[attr-defined]
    on_disk = SCHEMA_DOC.read_text()
    if on_disk != rendered:
        diff = "\n".join(
            difflib.unified_diff(
                on_disk.splitlines(),
                rendered.splitlines(),
                fromfile="committed",
                tofile="regenerated",
                lineterm="",
            )
        )
        raise AssertionError(
            "docs/reference/schema.md is out of date — run "
            f"scripts/gen_schema_reference.py.\nDiff (committed vs regenerated):\n{diff}"
        )


def test_every_explained_unit_really_has_no_manifest() -> None:
    """An EXPLAINED reason is a claim that a unit has no manifest and why.
    Once the manifest exists the reason is never rendered, so it can go stale
    unseen — `ARDOPGUI` said "waits on the binary backend" for three days
    after the binary backend shipped, and would have said it forever. A
    reason for a covered unit is either wrong or dead; both come out."""
    gen = _parity_generator()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    table = gen.lookup_table(catalog)  # type: ignore[attr-defined]
    stale = sorted(
        f"{unit} -> {table[gen.normalise(unit)]}"  # type: ignore[attr-defined]
        for unit in gen.EXPLAINED  # type: ignore[attr-defined]
        if gen.normalise(unit) in table  # type: ignore[attr-defined]
    )
    assert not stale, (
        f"EXPLAINED reasons for units that have a manifest: {stale}. "
        "Delete the entry from scripts/gen_parity_coverage.py."
    )


def test_a_label_file_probe_shows_the_reader_where_the_label_lives(
    rendered: dict[str, str],
) -> None:
    # A probe that names a file is only useful to a reader who can find the
    # file; `probe: label file` alone says nothing (issue #31, yaac).
    page = rendered["yaac.md"]
    assert "- probe: label file (<https://www.ka2ddo.org/ka2ddo/YAACBuildLabel.txt>)" in page


# ---------------------------------------------------------------------------
# The README's catalog numbers are catalog data, so they are checked like it
# ---------------------------------------------------------------------------


def test_the_readme_manifest_count_matches_the_catalog() -> None:
    """The front page said **225** manifests for a week while the catalog
    held 244. The hardware counts on the same page have had this test since
    they drifted (tests/test_hardware.py); the manifest count is the number
    beside them and had nothing. Same shape, same fix."""
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    readme = (REPO_ROOT / "README.md").read_text()
    claim = f"| Package manifests | 🟡 **{len(catalog)}**"
    assert claim in readme, f"README no longer says {claim!r}"


def test_the_readme_profile_counts_match_the_catalog() -> None:
    """The front page said "plus 5 post-1.0" after a sixth post-1.0 profile
    (`reference`, D-066) landed beside it: the manifest count one row up had
    a test and this number had none (final review, 2026-09-29)."""
    profiles = load_profiles(REPO_ROOT / "catalog" / "profiles")
    one = sum(1 for p in profiles.values() if p.stage == "1.0")
    post = sum(1 for p in profiles.values() if p.stage == "post-1.0")
    readme = (REPO_ROOT / "README.md").read_text()
    claim = f"| Profiles | ✅ **all {one} of the 1.0 set**, plus {post} post-1.0"
    assert claim in readme, f"README no longer says {claim!r}"


def test_the_readme_parity_coverage_matches_the_generated_page() -> None:
    """The parity headline is generated into docs/reference/parity-coverage.md
    and repeated by hand on the front page, which read "88 of the 108" after
    the page said 102 of 116. The page is the authority; the README must
    quote it."""
    page = (REPO_ROOT / "docs" / "reference" / "parity-coverage.md").read_text()
    match = re.search(r"Coverage of what is owed: \*\*(\d+)/(\d+)\*\*", page)
    assert match, "parity-coverage.md no longer carries its headline line"
    covered, owed = match.groups()
    readme = (REPO_ROOT / "README.md").read_text()
    claim = f"**{covered} of the {owed} units that owe a manifest**"
    assert claim in readme, f"README no longer says {claim!r}"


# ---------------------------------------------------------------------------
# The udev identifier inventory
#
# Found stale on 2026-09-07: eleven identifiers had gone into the hardware
# catalog since the page was last written and nothing said so, because the
# generator had no --check and every other no-op test here skips it. Its
# header also read "Swept: <today>" on every regeneration — the date the page
# was written, labelled as the date the archive was measured (D-031).
# ---------------------------------------------------------------------------

UDEV_INVENTORY = REPO_ROOT / "docs" / "reference" / "udev-inventory.md"


def _gen_udev_inventory() -> object:
    spec = importlib.util.spec_from_file_location(
        "gen_udev_inventory", REPO_ROOT / "scripts" / "gen_udev_inventory.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_udev_inventory_swept_date_is_the_sweep_files_not_todays() -> None:
    import datetime

    gen = _gen_udev_inventory()
    # One enabled librtlsdr0 row in the sweep's own column order.
    values = (
        *("librtlsdr0", "libs", "60-librtlsdr0.rules", "0bda", "2838", "", ""),
        *("Realtek", "RTL2838 DVB-T", "1", "", "usb"),
    )
    fields: tuple[str, ...] = gen.FIELDS  # type: ignore[attr-defined]
    row = dict(zip(fields, values, strict=True))
    page = gen.render(  # type: ignore[attr-defined]
        "debian-13", [row], set(), swept=datetime.date(2026, 8, 27)
    )
    assert "**Swept:** 2026-08-27, `debian-13`" in page
    # The date line, specifically: the page's prose may legitimately name the
    # day a finding was made (D-047's syntax note does), and a sweep run today
    # is legitimately dated today. What must never happen is the line saying
    # "today" when the file says otherwise.
    assert f"**Swept:** {datetime.date.today().isoformat()}" not in page


@pytest.mark.skipif(
    not list(PROBES.glob("udev-*.tsv")),
    reason="needs the udev sweep in reference/probes/ — see the generator's docstring",
)
def test_regenerating_the_udev_inventory_is_a_no_op() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_udev_inventory.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"{result.stdout}{result.stderr}\n"
        "docs/reference/udev-inventory.md is stale — run scripts/gen_udev_inventory.py. "
        "Either the hardware catalog gained identifiers the sweep also carries, "
        "or the sweep was re-run."
    )


# ---------------------------------------------------------------------------
# Every other page generator (issues #45 and #48)
#
# Nine generators had neither --check nor a test that ran them, which is how
# the udev inventory above sat stale for ten days. Each now takes --check,
# renders in memory and compares without the generated-date line. The test
# also asserts --check WROTE NOTHING: six of the nine ignored their argv and
# rewrote the page unconditionally, so a test that only read the exit status
# would have been green on every one of them before the flag existed.
#
# Generators that read a gitignored measurement skip where it is absent, the
# way the capability matrix does. Two read nothing but the catalog and run
# everywhere.
# ---------------------------------------------------------------------------

REFERENCE = REPO_ROOT / "reference"

# (script, outputs it writes, inputs it needs before it can render at all)
CHECKED_GENERATORS: list[tuple[str, list[str], list[Path]]] = [
    (
        "gen_blend_inventory.py",
        ["docs/reference/blend-inventory.md"],
        [REFERENCE / "blend-tasks"],
    ),
    (
        "gen_dragonos_tier1.py",
        ["docs/reference/dragonos-tier1-inventory.md"],
        [REFERENCE / "dragonos" / "README.txt", PROBES / "dragonos-debian-13.tsv"],
    ),
    (
        "gen_skywave_inventory.py",
        ["docs/reference/skywave-inventory.md"],
        [REFERENCE / "skywave" / "skywavelinux-index.html", PROBES / "skywave-debian-13.tsv"],
    ),
    (
        "gen_install_verification.py",
        ["docs/reference/install-verification.md"],
        [REFERENCE / "install-tests" / "tier1-debian-13.tsv"],
    ),
    (
        "gen_lora_inventory.py",
        ["docs/reference/lora-inventory.md"],
        [PROBES / "lora-identifiers.tsv"],
    ),
    (
        "gen_usb_ambiguity.py",
        ["catalog/hardware/ambiguous-ids.yaml", "docs/reference/usb-ambiguity.md"],
        [PROBES / "modules-alias-debian-13.tsv", PROBES / "udev-debian-13.tsv"],
    ),
    (
        "gen_profile_sizing.py",
        ["docs/reference/profile-sizing.md"],
        [PROBES / "blend-debian-13.tsv"],
    ),
    (
        "gen_brltty_inventory.py",
        ["docs/reference/brltty-inventory.md"],
        [
            PROBES / f"brltty-{t}.txt"
            for t in (
                "debian-13",
                "debian-13-arm64",
                "parrot",
                "kali-rolling",
                "ubuntu-24.04",
                "ubuntu-26.04",
                "linuxmint-22.3",
            )
        ],
    ),
    ("gen_device_naming.py", ["docs/reference/device-naming.md"], []),
    ("gen_hardware_gaps.py", ["docs/reference/hardware-gaps.md"], []),
    ("gen_json_reference.py", ["docs/reference/json-interface.md"], []),
    ("gen_station_settings.py", ["docs/guides/station-settings.md"], []),
    ("gen_projects_page.py", ["docs/projects.md"], []),
    ("gen_application_directory.py", ["docs/applications.md"], []),
    (
        "gen_activity_hubs.py",
        [
            f"docs/activities/{p}.md"
            for p in ("gps-time", "aprs", "meshtastic", "reticulum", "meshcore")
        ],
        [],
    ),
    (
        "gen_geofabrik_countries.py",
        ["catalog/data/geofabrik-countries.yaml"],
        [REFERENCE / "geofabrik" / "index-v1-nogeom.json"],
    ),
]


@pytest.mark.parametrize(
    ("script", "outputs", "needs"),
    CHECKED_GENERATORS,
    ids=[g[0] for g in CHECKED_GENERATORS],
)
def test_check_reports_the_page_current_and_writes_nothing(
    script: str, outputs: list[str], needs: list[Path]
) -> None:
    import subprocess

    missing = [p for p in needs if not p.exists()]
    if missing:
        pytest.skip(f"needs the gitignored measurement {missing[0].relative_to(REPO_ROOT)}")
    paths = [REPO_ROOT / o for o in outputs]
    before = {p: p.stat().st_mtime_ns for p in paths}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"{result.stdout}{result.stderr}\n{', '.join(outputs)} is stale — run scripts/{script}"
    )
    assert "up to date" in result.stdout, result.stdout
    rewritten = [
        o for p, o in zip(paths, outputs, strict=True) if p.stat().st_mtime_ns != before[p]
    ]
    assert not rewritten, f"scripts/{script} --check wrote {rewritten}; a check must not write"


def test_the_open_repeater_pin_is_well_formed_and_its_check_writes_nothing() -> None:
    """D-074. The pin lives in catalog/packages/open-repeater.yaml, written by
    its generator; asking the publisher needs the network, which the weekly
    pin review does, so the suite runs the offline half: the manifest's
    shape, through the same script, and nothing written."""
    import subprocess

    manifest = REPO_ROOT / "catalog" / "packages" / "open-repeater.yaml"
    before = manifest.stat().st_mtime_ns
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "gen_open-repeater-pin.py"),
            "--check",
            "--offline",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"{result.stdout}{result.stderr}\nrun scripts/gen_open-repeater-pin.py"
    )
    assert "well formed" in result.stdout, result.stdout
    assert manifest.stat().st_mtime_ns == before, "--check wrote the manifest"


def _load_script(name: str) -> object:
    spec = importlib.util.spec_from_file_location(
        name.removesuffix(".py"), REPO_ROOT / "scripts" / name
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_station_table_covers_every_config_file_and_its_deferral(tmp_path: Path) -> None:
    from hammunition.plan import _plan_config
    from hammunition.station import Station

    gen = _load_script("gen_station_settings.py")
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    table = gen.render_table(catalog)  # type: ignore[attr-defined]
    rows = table.splitlines()[2:]
    configs = [(name, config) for name, m in catalog.items() for config in m.config_files]
    assert configs
    assert len(rows) == len(configs)
    for name, config in configs:
        row = next(r for r in rows if f"| `{config.path}` |" in r)
        assert f"[{name}](../packages/{name}.md)" in row
        for variable in config.station_variables:
            assert f"`{variable}`" in row
        manifest = catalog[name].model_copy(update={"config_files": [config]})
        writable, deferred = _plan_config(manifest, Station(), tmp_path)
        if config.station_variables:
            assert not writable and len(deferred) == 1
            assert (
                f"will not write {tmp_path / config.path[2:] if config.in_home else config.path}"
                == deferred[0].what
            )
            for missing in Station().missing(config.station_variables):
                assert f"`{missing}`" in row
            assert "Defer this file only" in row
        else:
            assert writable and not deferred
            assert "No station value required" in row


def test_station_table_discovers_new_units_and_derived_sources() -> None:
    from hammunition.manifest.schema import ConfigFile

    gen = _load_script("gen_station_settings.py")
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    new = catalog["linbpq"].model_copy(
        update={
            "name": "new-config",
            "config_files": [
                ConfigFile(path="/etc/new.conf", template="{station.longitude}\n"),
                ConfigFile(path="/etc/fixed.conf", template="fixed\n"),
            ],
        }
    )
    table = gen.render_table({"new-config": new})  # type: ignore[attr-defined]
    assert "[new-config](../packages/new-config.md)" in table
    assert "`/etc/new.conf` | `longitude` (from `grid_square`)" in table
    assert "Defer this file only if any of `grid_square` is unset" in table
    assert "`/etc/fixed.conf` | None | No station value required" in table


def test_station_table_check_detects_drift_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gen = _load_script("gen_station_settings.py")
    page = (REPO_ROOT / "docs" / "guides" / "station-settings.md").read_text()
    stale = page.replace("`/etc/bpq32.cfg`", "`/etc/stale.cfg`")
    assert stale != page
    out = tmp_path / "station-settings.md"
    out.write_text(stale)
    before = out.stat().st_mtime_ns
    monkeypatch.setattr(gen, "OUT", out)
    monkeypatch.setattr(sys, "argv", ["gen_station_settings.py", "--check"])
    assert gen.main() == 1  # type: ignore[attr-defined]
    assert "run scripts/gen_station_settings.py" in capsys.readouterr().out
    assert out.read_text() == stale
    assert out.stat().st_mtime_ns == before
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    assert gen.render(stale, catalog) == page  # type: ignore[attr-defined]


@pytest.mark.parametrize("markers", ["", "start", "end", "duplicate", "reversed"])
def test_station_table_refuses_missing_or_ambiguous_markers(markers: str) -> None:
    gen = _load_script("gen_station_settings.py")
    start, end = gen.START, gen.END  # type: ignore[attr-defined]
    page = {
        "": "",
        "start": start,
        "end": end,
        "duplicate": start + start + end,
        "reversed": end + start,
    }[markers]
    with pytest.raises(ValueError, match="generation markers"):
        gen.render(page, {})  # type: ignore[attr-defined]


# Issue #45: a missing probe rendered as an empty measurement. profile-sizing
# reported every profile as "0 installable" from a checkout without the
# probes, exit 0, "wrote docs/reference/profile-sizing.md". dragonos and
# skywave read their probes the same way.
@pytest.mark.parametrize(
    ("script", "constant", "call"),
    [
        ("gen_profile_sizing.py", "PROBES", lambda m, d: m.probe("blend-debian-13.tsv")),
        ("gen_dragonos_tier1.py", "PROBES", lambda m, d: m.parse_probe("debian-13")),
        (
            "gen_skywave_inventory.py",
            "PROBES",
            lambda m, d: m.parse_apt(d / "skywave-debian-13.tsv"),
        ),
    ],
    ids=["profile_sizing", "dragonos", "skywave"],
)
def test_a_missing_probe_is_an_error_that_names_the_file_and_the_sweep(
    tmp_path: Path, script: str, constant: str, call: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script(script)
    monkeypatch.setattr(module, constant, tmp_path)
    with pytest.raises(SystemExit) as raised:
        call(module, tmp_path)  # type: ignore[operator]
    message = str(raised.value)
    assert str(tmp_path) in message, message
    assert "apt-policy-sweep.sh" in message, message


# Four of them also stamped today's date where the page says "measured" or
# "fetched" -- the date the page was written, labelled as the date the
# archive was asked (D-031; the udev inventory had the same defect until
# PR #47). The date is the input file's now, so a regeneration cannot move it.
@pytest.mark.parametrize(
    ("script", "inputs", "label"),
    [
        ("gen_blend_inventory.py", [REFERENCE / "blend-tasks"], "**Fetched:**"),
        ("gen_dragonos_tier1.py", [PROBES / "dragonos-debian-13.tsv"], "— measured"),
        ("gen_skywave_inventory.py", [PROBES / "skywave-debian-13.tsv"], "container,"),
        (
            "gen_install_verification.py",
            [
                REFERENCE / "install-tests" / f"{n}.tsv"
                for n in ("tier1-debian-13", "debs-debian-13", "debs-ubuntu-26.04")
            ],
            "**Measured:**",
        ),
    ],
    ids=["blend", "dragonos", "skywave", "install_verification"],
)
def test_the_measured_date_is_the_inputs_not_todays(
    script: str, inputs: list[Path], label: str
) -> None:
    import datetime

    if not all(p.exists() for p in inputs):
        pytest.skip(f"needs the gitignored measurement {inputs[0].relative_to(REPO_ROOT)}")
    files = [f for p in inputs for f in (p.iterdir() if p.is_dir() else [p])]
    measured = datetime.date.fromtimestamp(max(f.stat().st_mtime for f in files))
    today = datetime.date.today()
    if measured == today:
        pytest.skip("the measurement was taken today, so the two dates agree")
    module = _load_script(script)
    if script == "gen_blend_inventory.py":
        tasks = [module.parse(module.TASK_DIR / n) for n in module.TASKS]  # type: ignore[attr-defined]
        text: str = module.render(tasks)  # type: ignore[attr-defined]
    else:
        text = module.render()  # type: ignore[attr-defined]
    line = next(ln for ln in text.splitlines() if label in ln)
    assert measured.isoformat() in line, line
    assert today.isoformat() not in line, line


def test_the_cli_reference_documents_the_power_verbs() -> None:
    text = (REPO_ROOT / "docs" / "reference" / "cli.md").read_text()
    for verb in ("hardware park", "hardware wake", "hardware state", "hardware unapply"):
        assert verb in text, f"{verb} is undocumented"


def test_the_power_control_page_covers_the_four_required_things() -> None:
    """CLAUDE.md: every system modification says what changes, why, how to
    inspect it afterwards, and how to reverse it."""
    text = (REPO_ROOT / "docs" / "hardware" / "power-control.md").read_text()
    for needle in (
        "/usr/local/libexec/hammunition-devctl",
        "/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy",
        "pkaction",
        "hardware unapply",
        "hammunition-tray",
    ):
        assert needle in text, f"power-control.md does not mention {needle}"


def test_d056_is_recorded() -> None:
    assert "D-056" in (REPO_ROOT / "docs" / "DECISIONS.md").read_text()


# ---------------------------------------------------------------------------
# The Geofabrik pin list (catalog/data/geofabrik-pins.yaml)
#
# Its --check re-probes each pinned URL's HEAD size, which is the network, and
# this suite blocks every non-loopback socket (tests/conftest.py). An empty pin
# list needs no probe and is checked everywhere; a populated one is checked by
# the weekly CI job, and here skips with the reason rather than failing.
# ---------------------------------------------------------------------------

GEOFABRIK_PINS = REPO_ROOT / "catalog" / "data" / "geofabrik-pins.yaml"


def _network_reaches(host: str) -> bool:
    import socket

    try:
        with socket.create_connection((host, 443), timeout=5):
            return True
    except Exception:  # conftest's NetworkBlocked, DNS failure, timeout
        return False


def test_the_geofabrik_pin_check_reports_current_and_writes_nothing() -> None:
    import subprocess

    pins = (yaml.safe_load(GEOFABRIK_PINS.read_text()) or {}).get("pins") or []
    if pins and not _network_reaches("download.geofabrik.de"):
        pytest.skip(
            "the pin list is populated and its --check HEADs every pinned URL on "
            "download.geofabrik.de; the network is unavailable here (this suite "
            "blocks non-loopback sockets). The weekly pin-reviews CI job runs it."
        )
    before = GEOFABRIK_PINS.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_geofabrik_pins.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "up to date" in result.stdout, result.stdout
    assert GEOFABRIK_PINS.stat().st_mtime_ns == before, "--check wrote the pin file"


# ---------------------------------------------------------------------------
# The Copernicus tile list and pins (catalog/data/copernicus-glo30-*), D-061
#
# `--check --offline` reads both files' shape and needs no network, so it runs
# everywhere. The full `--check` fetches the bucket's list and HEADs every pin:
# the weekly pin-reviews job runs it, and here it skips with the reason, since
# this suite blocks every non-loopback socket.
# ---------------------------------------------------------------------------

COPERNICUS = [
    REPO_ROOT / "catalog" / "data" / "copernicus-glo30-tiles.txt",
    REPO_ROOT / "catalog" / "data" / "copernicus-glo30-pins.yaml",
]


def _copernicus_check(*extra: str) -> subprocess.CompletedProcess[str]:
    before = [path.stat().st_mtime_ns for path in COPERNICUS]
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_copernicus_pins.py"), "--check", *extra],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert [path.stat().st_mtime_ns for path in COPERNICUS] == before, "--check wrote a file"
    return result


def test_the_copernicus_files_are_well_formed_offline() -> None:
    result = _copernicus_check("--offline")
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "well formed" in result.stdout


def test_the_copernicus_check_reports_current_and_writes_nothing() -> None:
    if not _network_reaches("copernicus-dem-30m.s3.amazonaws.com"):
        pytest.skip(
            "the check fetches the bucket's tile list and HEADs every pinned tile on "
            "copernicus-dem-30m.s3.amazonaws.com; the network is unavailable here (this "
            "suite blocks non-loopback sockets). The weekly pin-reviews CI job runs it."
        )
    result = _copernicus_check()
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "up to date" in result.stdout


def test_d058_is_recorded() -> None:
    assert "## D-058" in (REPO_ROOT / "docs" / "DECISIONS.md").read_text()


def test_the_gps_time_guide_recommends_an_rtc_first() -> None:
    """The maintainer, 2026-09-28: the RTC recommendation comes first."""
    text = (REPO_ROOT / "docs" / "guides" / "gps-time.md").read_text()
    assert "RTC" in text
    assert text.index("RTC") < text.index("time mode")


def test_the_gps_time_guide_covers_every_system_modification() -> None:
    """CLAUDE.md: what changes, why, how to inspect it, how to reverse it."""
    text = (REPO_ROOT / "docs" / "guides" / "gps-time.md").read_text()
    for needle in (
        "/etc/hammunition/time.yaml",
        "/etc/ntpsec/ntp.d/hammunition-gps.conf",
        "/etc/ntpsec/ntp.conf",
        "/etc/systemd/system/ntpsec.service.d/hammunition-gps.conf",
        "/etc/apparmor.d/local/usr.sbin.ntpd",
        "/etc/systemd/system/gpsd.service.d/hammunition-gps.conf",
        "systemctl cat gpsd",
        "CAP_IPC_OWNER",
        "hardware unapply",
        "dpkg --verify ntpsec",
        "ntpq -pn",
        "fake-hwclock",
    ):
        assert needle in text, f"gps-time.md does not mention {needle}"


def _gps_time_prose() -> dict[str, str]:
    decisions = (REPO_ROOT / "docs" / "DECISIONS.md").read_text()
    d058 = decisions[decisions.index("## D-058") : decisions.index("## D-059")]
    return {
        "D-058": d058,
        "gps-time.md": (REPO_ROOT / "docs" / "guides" / "gps-time.md").read_text(),
        "cli.md": (REPO_ROOT / "docs" / "reference" / "cli.md").read_text(),
        "CHANGELOG.md": (REPO_ROOT / "CHANGELOG.md").read_text(),
        "CLAUDE.md": (REPO_ROOT / "CLAUDE.md").read_text(),
    }


@pytest.mark.parametrize(
    "claim", ["dpkg --verify ntpsec", "never feeds the clock", "never feed the clock"]
)
def test_gps_time_prose_hedges_what_the_bench_has_not_measured(claim: str) -> None:
    """Final review: the plan's Global Constraint, no doc claims an unmeasured
    behaviour. `unapply` leaving `dpkg --verify` clean and a parked receiver
    dropping out of selection are both bench items."""
    hedges = ("not yet", "bench", "inferred", "unmeasured")
    for name, text in _gps_time_prose().items():
        for paragraph in re.split(r"\n\s*\n|\n(?=\|)", text):
            if claim in paragraph:
                assert any(h in paragraph for h in hedges), f"{name}: {paragraph[:200]}"


def test_gps_time_docs_name_the_opt_out_and_the_minsane_cost() -> None:
    """Final review I2."""
    prose = _gps_time_prose()
    for name in ("gps-time.md", "cli.md"):
        assert "--no-gps-time" in prose[name], name
    for name in ("gps-time.md", "D-058"):
        assert "single falseticker" in " ".join(prose[name].split()), name


# ---------------------------------------------------------------------------
# The Kiwix book pins (catalog/data/kiwix-pins.yaml), D-066
#
# `--check --offline` compares the pin file with the hand-written book list
# (one pin per listed book, in its order) and needs no network, so it runs
# everywhere. The full `--check` asks Kiwix for each pinned file's .meta4:
# Kiwix keeps two dated files per book, so a pin dies on its calendar, and
# the weekly pin-reviews job goes red naming it. Here it skips with the
# reason, since this suite blocks every non-loopback socket.
# ---------------------------------------------------------------------------

KIWIX_PINS = REPO_ROOT / "catalog" / "data" / "kiwix-pins.yaml"


def _kiwix_check(*extra: str) -> subprocess.CompletedProcess[str]:
    before = KIWIX_PINS.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_kiwix_pins.py"), "--check", *extra],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert KIWIX_PINS.stat().st_mtime_ns == before, "--check wrote the pin file"
    return result


def test_the_kiwix_pins_match_the_book_list_offline() -> None:
    result = _kiwix_check("--offline")
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "well formed" in result.stdout


def test_the_kiwix_check_reports_current_and_writes_nothing() -> None:
    if not _network_reaches("download.kiwix.org"):
        pytest.skip(
            "the check asks download.kiwix.org for every pinned file's .meta4; the "
            "network is unavailable here (this suite blocks non-loopback sockets). "
            "The weekly pin-reviews CI job runs it."
        )
    result = _kiwix_check()
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "up to date" in result.stdout


# ---------------------------------------------------------------------------
# The US Topo quad index (D-068). `--check --offline` checks its shape and its
# header's counts against its rows everywhere, and writes nothing. The full
# `--check` lists the bucket and fails only on a carried quad that is gone or
# changed: the weekly pin-reviews job runs it, and here it skips, since this
# suite blocks every non-loopback socket.
# ---------------------------------------------------------------------------

USTOPO = REPO_ROOT / "catalog" / "data" / "ustopo-quads.txt"


def _ustopo_check(*extra: str) -> subprocess.CompletedProcess[str]:
    before = USTOPO.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_ustopo_index.py"), "--check", *extra],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert USTOPO.stat().st_mtime_ns == before, "--check wrote a file"
    return result


def test_the_ustopo_index_is_well_formed_offline() -> None:
    result = _ustopo_check("--offline")
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "well formed" in result.stdout


FSTOPO = REPO_ROOT / "catalog" / "data" / "fstopo-quads.txt"


def test_the_fstopo_index_and_pins_are_well_formed_offline() -> None:
    before = FSTOPO.stat().st_mtime_ns
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "gen_fstopo_index.py"),
            "--check",
            "--offline",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert FSTOPO.stat().st_mtime_ns == before, "--check wrote a file"
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "well formed" in result.stdout


THREEDEP = REPO_ROOT / "catalog" / "data" / "usgs-3dep-tiles.txt"


def _threedep_check(*extra: str) -> subprocess.CompletedProcess[str]:
    before = THREEDEP.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_3dep_tiles.py"), "--check", *extra],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert THREEDEP.stat().st_mtime_ns == before, "--check wrote a file"
    return result


def test_the_3dep_tile_list_is_well_formed_offline() -> None:
    result = _threedep_check("--offline")
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "well formed" in result.stdout


def test_the_3dep_check_lists_the_bucket_and_writes_nothing() -> None:
    if not _network_reaches("prd-tnm.s3.amazonaws.com"):
        pytest.skip(
            "the check lists the prd-tnm bucket's 3DEP 1/3-arc-second prefix (six "
            "pages); the network is unavailable here (this suite blocks non-loopback "
            "sockets). The weekly pin-reviews CI job runs it."
        )
    result = _threedep_check()
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "every carried tile" in result.stdout


def test_the_ustopo_check_lists_the_bucket_and_writes_nothing() -> None:
    if not _network_reaches("prd-tnm.s3.amazonaws.com"):
        pytest.skip(
            "the check lists the prd-tnm bucket's GeoTIFF prefix (about 273 pages); the "
            "network is unavailable here (this suite blocks non-loopback sockets). The "
            "weekly pin-reviews CI job runs it."
        )
    result = _ustopo_check()
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "every carried quad" in result.stdout
