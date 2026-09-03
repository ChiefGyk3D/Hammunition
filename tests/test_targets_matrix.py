# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The CI matrix and ``containers/targets.yaml`` name the same targets.

Two files declare the target set: ``targets.yaml`` is what every script and
generator reads, and the ``targets`` job in ``.github/workflows/ci.yml`` is
what actually runs. Nothing tied them together. Adding ``ubuntu-24.04`` on
2026-09-03 meant editing both by hand, and a target added to one alone would
either be documented and never run, or run and never measured, with no check
going red either way. This one does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGETS = REPO_ROOT / "containers" / "targets.yaml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# A target container carries no .github tree, so there is nothing to compare
# against there; the comparison is a property of the repository.
pytestmark = pytest.mark.skipif(not WORKFLOW.exists(), reason="no CI workflow in this tree")


def _declared() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(TARGETS.read_text())
    return {t["name"]: t for t in data["targets"]}


def _matrix() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(WORKFLOW.read_text())
    rows = data["jobs"]["targets"]["strategy"]["matrix"]["target"]
    return {row["name"]: row for row in rows}


def test_every_declared_target_is_in_the_ci_matrix_and_vice_versa() -> None:
    declared, matrix = _declared(), _matrix()
    assert set(declared) == set(matrix), (
        f"targets.yaml and ci.yml disagree: "
        f"only declared {sorted(set(declared) - set(matrix))}, "
        f"only in CI {sorted(set(matrix) - set(declared))}"
    )


def test_each_target_runs_the_image_it_declares() -> None:
    declared, matrix = _declared(), _matrix()
    for name, entry in declared.items():
        row = matrix[name]
        assert row["image"] == entry["image"], f"{name}: CI runs {row['image']}"
        platform = entry.get("platform", "linux/amd64")
        assert row["platform"] == platform, f"{name}: CI platform {row['platform']}"
        assert row.get("identity_package") == entry.get("identity_package"), (
            f"{name}: identity_package differs between targets.yaml and ci.yml"
        )
