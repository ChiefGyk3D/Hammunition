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
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402

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
    import re

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
    on_disk = {p.name: p.read_text() for p in HARDWARE_DOCS.glob("*.md")}
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
