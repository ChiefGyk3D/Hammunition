# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A venv unit may state its licence on the plan line.  D-033, D-080.

Reticulum is under a licence the operator would not assume. The data blocks
already print theirs beside the size; a venv block had nowhere to say it, and
the `note` field no plan line reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends import Command, VenvBackend
from hammunition.manifest.schema import ManifestError, PackageManifest, VenvInstall

HASHED = (
    "example==1.0 --hash=sha256:1111111111111111111111111111111111111111111111111111111111111111"
)
URL = "https://github.com/markqvist/Reticulum/blob/master/LICENSE"


def _manifest(**block: Any) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "venvunit",
            "version": "1.0",
            "summary": "Fixture for the venv licence suite",
            "categories": ["mesh"],
            "install": [{"install": {"method": "venv", "requirements": [HASHED], **block}}],
            "update": {"probe": {"method": "pypi"}, "strategy": "reinstall"},
            "documentation": {
                "what_it_does": "Exists so the venv backend has a unit to plan.",
                "why_you_want_it": "You do not; the suite does.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _pip_step(m: PackageManifest, tmp_path: Path) -> Command:
    install = m.install[0].install
    assert isinstance(install, VenvInstall)
    backend = VenvBackend(venv_root=tmp_path / "venvs", bin_dir=tmp_path / "bin")
    (step,) = [
        s
        for s in backend.steps(m, install)
        if isinstance(s, Command) and "--require-hashes" in s.argv
    ]
    return step


def test_the_licence_is_on_the_plan_line_that_installs_the_venv(tmp_path: Path) -> None:
    step = _pip_step(_manifest(licence="Reticulum License", licence_url=URL), tmp_path)
    assert step.description.endswith(f"; licence: Reticulum License ({URL})")
    assert "verified against the manifest's sha256 pins" in step.description


def test_a_block_with_no_licence_prints_the_line_it_always_did(tmp_path: Path) -> None:
    step = _pip_step(_manifest(), tmp_path)
    assert step.description == (
        "Install venvunit into its venv — every wheel verified against the manifest's sha256 pins"
    )


def test_a_licence_without_its_url_is_refused() -> None:
    with pytest.raises((ManifestError, ValidationError), match="set together"):
        _manifest(licence="Reticulum License")


def test_a_url_without_its_licence_is_refused() -> None:
    with pytest.raises((ManifestError, ValidationError), match="set together"):
        _manifest(licence_url=URL)


def test_the_licence_url_must_be_https() -> None:
    with pytest.raises((ManifestError, ValidationError), match="licence_url must be https"):
        _manifest(licence="Reticulum License", licence_url="http://example.invalid/LICENSE")
