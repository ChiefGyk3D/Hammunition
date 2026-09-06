# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The coverage matrix is computed, and the judgement in it is checked.

`scripts/gen_coverage_matrix.py` reconciles AHRL's 95 executing units against
the Debian Hamradio Blend metapackages as Parrot ships them. The facts — which
metapackage recommends what, which version Parrot's index offers, which
version AHRL bundles — are parsed, never typed. The judgement — DEAD versus
DELTA_SOURCE, the free substitute for something proprietary — is a curated
table in the generator, and these tests hold it to the rule the matrix was
asked for: every unit classified exactly once, every non-COVERED
classification citing a URL, every name in the table real.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

GENERATOR = REPO_ROOT / "scripts" / "gen_coverage_matrix.py"
PROBE = REPO_ROOT / "reference" / "probes" / "blend-metapackages-parrot-echo.tsv"
OUT = REPO_ROOT / "docs" / "reference" / "coverage-matrix.md"


def _gen() -> object:
    spec = importlib.util.spec_from_file_location("gen_coverage_matrix", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve string annotations through sys.modules; a module
    # executed from a spec without being registered has no entry there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


INVENTORY = """## Full inventory

### Phase 1 — prerequisites

| # | Software | Method | apt package(s) | Non-apt source / build | Menu category | Conditional |
|---:|---|---|---|---|---|---|
| 1 | Firefox (browser) | apt (+PPA) | `firefox` \\| `firefox-esr` \\| `software-properties-common` | mozillateam PPA | — | — |
| 2 | libhamlib4 | apt | `libhamlib4` | — | — | — |

### Phase 3 — source builds from bundled tarballs

| # | Software | Bundled archive | Build | apt build deps | Menu category | Notes |
|---:|---|---|---|---|---|---|
| 43 | Dire Wolf 1.8.1 | `direwolf-1.8.1.tar.gz` | `cmake` | `libhamlib-dev` | Digital_Modes | |
| 60 | Linrad 05-02 | `lir05-02.zip` | `./configure` | `nasm` | SDR | |
| 76 | GridTracker2 2.260421.1 | vendor `.deb` | `GridTracker2-…-amd64.deb` | Digital_Modes | 112 MB |

### Disabled in v27 (`INSTALL_*=0`)

| Toggle | Software |
|---|---|
| `INSTALL_DREAM` | Dream 2.1.1 |
"""


def test_units_are_read_from_the_numbered_inventory_tables() -> None:
    units = _gen().parse_ahrl_units(INVENTORY)  # type: ignore[attr-defined]
    assert [(u.number, u.name, u.version) for u in units] == [
        (1, "Firefox (browser)", None),
        (2, "libhamlib4", None),
        (43, "Dire Wolf", "1.8.1"),
        (60, "Linrad", "05-02"),
        (76, "GridTracker2", "2.260421.1"),
    ]
    assert units[0].apt_packages == ["firefox", "firefox-esr", "software-properties-common"]
    assert units[2].apt_packages == []


PACKAGES = """Package: hamradio-sdr
Version: 0.10
Depends: hamradio-tasks (= 0.10)
Recommends: airspy, gqrx-sdr, quisk, rtl-sdr (>= 0.6), soapysdr-tools | soapysdr-module-rtlsdr

Package: hamradio-tasks
Version: 0.10
Depends: tasksel

Package: gqrx-sdr
Version: 2.17.5-1+b2
Source: gqrx-sdr

Package: chirp
Version: 1:20250530-1parrot1
"""


def test_metapackage_membership_is_parsed_with_constraints_stripped() -> None:
    members = _gen().parse_metapackages(PACKAGES)  # type: ignore[attr-defined]
    assert members == {
        "hamradio-sdr": {
            "Recommends": ["airspy", "gqrx-sdr", "quisk", "rtl-sdr", "soapysdr-tools"],
        },
    }


def test_index_versions_are_parsed() -> None:
    versions = _gen().parse_index(PACKAGES)  # type: ignore[attr-defined]
    assert versions["gqrx-sdr"] == "2.17.5-1+b2"
    assert versions["chirp"] == "1:20250530-1parrot1"


@pytest.mark.parametrize(
    ("debian", "upstream"),
    [
        ("1:20250530-1parrot1", "20250530"),
        ("2.17.5-1+b2", "2.17.5"),
        ("2.7.0+repack-2", "2.7.0"),
        ("4.2.06+dfsg-1", "4.2.06"),
        ("1.2.2+git20260527-1", "1.2.2+git20260527"),
        ("0.0.10-rc5+git20230513+d3e6d4f-3", "0.0.10-rc5+git20230513+d3e6d4f"),
    ],
)
def test_debian_versions_reduce_to_upstream(debian: str, upstream: str) -> None:
    assert _gen().upstream_version(debian) == upstream  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("ahrl", "debian", "behind"),
    [
        ("4.2.11", "4.2.06", False),  # patch level: not material
        ("2.17.7", "2.17.5", False),
        ("3.0.0", "2.7.0", True),  # major
        ("2.5.2", "2.3.1", True),  # minor
        ("1.8.1", "1.7", True),
        ("20260501", "20250530", True),  # date-versioned: a year behind
        ("2.0.25", "2.0.24", False),
        ("4.2.11", "4.2.11", False),
        ("2.7.0", "3.0.0", False),  # Debian ahead of AHRL is not stale
    ],
)
def test_materially_behind_means_major_or_minor(ahrl: str, debian: str, behind: bool) -> None:
    assert _gen().materially_behind(ahrl, debian) is behind  # type: ignore[attr-defined]


def test_classification_follows_the_evidence() -> None:
    gen = _gen()
    classify = gen.classify  # type: ignore[attr-defined]
    F = gen.Facts  # type: ignore[attr-defined]
    assert (
        classify(
            F(metapackages=["hamradio-datamodes"], ahrl_version="4.2.11", parrot_version="4.2.06-1")
        )
        == "COVERED"
    )
    assert (
        classify(
            F(
                metapackages=["hamradio-datamodes"],
                ahrl_version="3.0.0",
                parrot_version="2.7.0+repack-2",
            )
        )
        == "COVERED_STALE"
    )
    assert classify(F(metapackages=[], parrot_version="4.6.1-6")) == "DELTA_APT"
    assert (
        classify(F(metapackages=[], parrot_version=None, method="binary:deb")) == "DELTA_UPSTREAM"
    )
    assert classify(F(metapackages=[], parrot_version=None, method="source")) == "DELTA_SOURCE"
    assert classify(F(metapackages=[], parrot_version=None, method="venv")) == "DELTA_SOURCE"
    assert (
        classify(F(metapackages=[], parrot_version="1.0-1", override="DELTA_NONFREE"))
        == "DELTA_NONFREE"
    )
    assert classify(F(metapackages=[], parrot_version=None, status="retired")) == "DEAD"
    # A unit the blend covers but the catalog retired is still dead: the
    # override wins, the evidence column shows the blend membership.
    assert (
        classify(F(metapackages=["hamradio-sdr"], parrot_version="1-1", status="retired")) == "DEAD"
    )


def test_every_executing_unit_is_curated_exactly_once() -> None:
    gen = _gen()
    units = gen.parse_ahrl_units(gen.INVENTORY.read_text())  # type: ignore[attr-defined]
    assert len(units) == 95
    numbers = [u.number for u in units]
    assert numbers == list(range(1, 96))
    curated = set(gen.CURATION)  # type: ignore[attr-defined]
    assert curated == set(numbers), (
        f"uncurated: {sorted(set(numbers) - curated)}; curated but not a unit: {sorted(curated - set(numbers))}"
    )


def test_curation_names_only_real_manifests_and_toggles() -> None:
    gen = _gen()
    manifests = {p.stem for p in (REPO_ROOT / "catalog" / "packages").glob("*.yaml")}
    toggles = {unit for unit, _ in gen.parse_dispositions_index()}  # type: ignore[attr-defined]
    bad = []
    for number, entry in gen.CURATION.items():  # type: ignore[attr-defined]
        if entry.manifest is not None and entry.manifest not in manifests:
            bad.append(f"#{number}: manifest {entry.manifest!r} does not exist")
        if entry.toggle not in toggles:
            bad.append(f"#{number}: toggle {entry.toggle!r} is not in dispositions.md")
    assert not bad, "\n".join(bad)


def test_every_override_and_dead_unit_cites_a_source() -> None:
    """The matrix was asked for one URL per non-COVERED classification. The
    computed classes (DELTA_APT, DELTA_SOURCE, DELTA_UPSTREAM) cite the
    manifest's upstream_url or the archive; the curated ones must bring
    their own."""
    gen = _gen()
    missing = [
        f"#{number} {entry.toggle}"
        for number, entry in gen.CURATION.items()  # type: ignore[attr-defined]
        if entry.override is not None and not entry.cite.startswith("https://")
    ]
    assert not missing, "curated classifications without a citation:\n  " + "\n  ".join(missing)


needs_probe = pytest.mark.skipif(
    not PROBE.exists(),
    reason="needs the Parrot index probe under reference/probes/ — run the generator with --fetch",
)


@needs_probe
def test_regenerating_the_matrix_is_a_no_op() -> None:
    gen = _gen()
    before = OUT.read_text()
    after = gen.render()  # type: ignore[attr-defined]

    def without_date(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("**Generated:**")]

    assert without_date(before) == without_date(after), (
        "docs/reference/coverage-matrix.md is stale — regenerate it"
    )


@needs_probe
def test_every_row_in_the_rendered_matrix_has_exactly_one_class_and_a_citation() -> None:
    gen = _gen()
    rows = gen.classified_rows()  # type: ignore[attr-defined]
    assert len(rows) == 95
    classes = {
        "COVERED",
        "COVERED_STALE",
        "DELTA_APT",
        "DELTA_UPSTREAM",
        "DELTA_SOURCE",
        "DELTA_NONFREE",
        "DEAD",
    }
    for row in rows:
        assert row.cls in classes, row
        if row.cls != "COVERED":
            assert row.cite.startswith("https://"), (
                f"#{row.unit.number} {row.unit.name} ({row.cls}) has no citation"
            )
