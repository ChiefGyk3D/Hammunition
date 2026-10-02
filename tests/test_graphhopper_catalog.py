# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shipped GraphHopper units, and that no profile carries them.  D-076.

The pin is the digest measured on 2026-10-01 by downloading the jar once and
comparing it with Maven Central's own ``.sha256`` (and ``.sha512``); it is
asserted here so a changed manifest is a visible change. Nothing is
downloaded by the suite.
"""

from __future__ import annotations

from pathlib import Path

from hammunition.graphhopper import GRAPH_UNIT, JAR_GLOB, PROGRAM_UNIT
from hammunition.manifest.load import load_catalog, load_profiles
from hammunition.manifest.schema import BinaryInstall, DerivedDataInstall

CATALOG = Path(__file__).resolve().parent.parent / "catalog"
CENTRAL = "https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web/11.1/"
JAR = "graphhopper-web-11.1.jar"


def test_the_jar_is_pinned_from_maven_central_with_its_signature_recorded() -> None:
    m = load_catalog(CATALOG / "packages")[PROGRAM_UNIT]
    block = m.install[0].install
    assert isinstance(block, BinaryInstall)
    assert block.artifact.url == CENTRAL + JAR
    assert block.artifact.sha256 == (
        "8462f758d9ea49edaded557cec5c687a0a24f004ec371cd4daaeb0534824ea33"
    )
    assert block.artifact.signature_url == CENTRAL + JAR + ".asc"
    assert (block.format, block.install_tree, block.tree_marker) == ("executable", True, JAR)
    assert block.tree_marker == block.artifact.url.rsplit("/", 1)[-1]
    assert Path(JAR).match(JAR_GLOB)
    assert m.version == "11.1"
    assert m.depends == ["default-jre-headless"]
    assert m.binaries == [] and m.launchers == []


def test_the_graph_is_derived_from_the_regions_with_the_jar() -> None:
    m = load_catalog(CATALOG / "packages")[GRAPH_UNIT]
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    assert (block.converter, block.source, block.program) == (
        "graphhopper-import",
        "osm-regions",
        PROGRAM_UNIT,
    )
    assert m.depends == ["osm-regions", PROGRAM_UNIT, "osmium-tool"]
    assert block.licence == "ODbL-1.0"


def test_neither_unit_is_in_any_profile() -> None:
    """D-076: installed by name only; the graph's cost does not fit `navigation`."""
    profiles = load_profiles(CATALOG / "profiles")
    holding = sorted(
        name
        for name, profile in profiles.items()
        if {PROGRAM_UNIT, GRAPH_UNIT} & set(profile.packages)
    )
    assert holding == []
