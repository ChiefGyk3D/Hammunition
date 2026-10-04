# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `mesh` profile: Reticulum and the Meshtastic clients together.  D-080.

Post-1.0 and in no default; the maintainer's ruling of 2026-10-03 puts the two
Meshtastic units in it, and D-039 is what keeps that from refusing a target whose
archive lacks one (`python3-meshtastic` is absent on Ubuntu 24.04, measured
2026-10-03).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hammunition.manifest.load import load_catalog, load_profiles
from hammunition.manifest.schema import ProfileManifest

from test_plan import TARGET, _apt, _resolve  # isort: skip

ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(ROOT / "catalog" / "packages")
PROFILES = load_profiles(ROOT / "catalog" / "profiles", CATALOG)
MESH: ProfileManifest = PROFILES["mesh"]


def test_the_profile_is_post_1_0_ungated_and_carries_exactly_these_five() -> None:
    assert MESH.stage == "post-1.0"
    assert MESH.consent is None  # nothing transmits until the operator attaches a radio
    assert MESH.packages == [
        "rns",
        "lxmf",
        "nomadnet",
        "python3-meshtastic",
        "gtk-meshtastic-client",
    ]


def test_no_other_profile_pulls_it_in_and_no_default_does() -> None:
    for name, profile in PROFILES.items():
        if name != "mesh":
            assert not {"rns", "lxmf", "nomadnet"} & set(profile.packages), name


def test_the_profile_says_what_it_leaves_out_and_what_the_operator_does_next() -> None:
    doc = MESH.documentation
    for left_out in ("Sideband", "MeshChat", "meshtasticd", "MeshCore", "TAK"):
        assert left_out in doc.deliberately_excludes, left_out
    assert "Part 97" in doc.manual_configuration
    assert "systemctl --user start hammunition-rnsd" in doc.manual_configuration
    assert "20, 20 and 27 MB" in (doc.disk_footprint_hint or "")
    assert any("mesh-and-reticulum.md" in step for step in doc.first_ten_minutes)


def test_a_target_without_python3_meshtastic_defers_it_by_name_and_installs_the_rest(
    tmp_path: Path,
) -> None:
    """Ubuntu 24.04: no `python3-meshtastic` candidate. The profile still installs
    the Reticulum units; the plan names what it left out (D-039)."""
    known: dict[str, Any] = {"python3-venv": None, "gtk-meshtastic-client": None}
    plan = _resolve(
        tmp_path,
        ["mesh"],
        catalog=CATALOG,
        profiles={"mesh": MESH},
        known=known,
        target=TARGET,
        apt=_apt(tmp_path, known),
    )
    installed = {p.name for p in plan.packages}
    assert {"rns", "lxmf", "nomadnet"} <= installed
    deferred = {d.subject for d in plan.deferrals if d.kind == "package"}
    assert "python3-meshtastic" in deferred
    assert "python3-meshtastic" not in installed
    # The shared instance is still planned: it needs nothing from the missing member.
    assert [s.name for s in plan.user_services] == ["hammunition-rnsd"]
