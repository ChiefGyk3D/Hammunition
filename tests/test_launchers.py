# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Launcher generation: endpoints resolved, workdirs honoured, menus fed."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hammunition.launchers import desktop_entry, launcher_steps, wrapper_body
from hammunition.manifest.schema import PackageManifest


def manifest(**overrides: Any) -> PackageManifest:
    base: dict[str, Any] = {
        "name": "launchable",
        "version": "1.0",
        "summary": "Fixture with a launcher",
        "categories": ["sdr", "tracking"],
        "install": [{"install": {"method": "apt", "packages": ["launchable"]}}],
        "launchers": [{"name": "launchable", "exec": "launchable --serve"}],
        "update": {"probe": {"method": "none"}, "strategy": "manual"},
        "documentation": {
            "what_it_does": "Exists so launcher generation has a unit to plan.",
            "why_you_want_it": "You do not; the suite does.",
            "upstream_url": "https://example.invalid/",
        },
    }
    base.update(overrides)
    return PackageManifest.model_validate(base)


def test_endpoint_references_resolve_to_the_catalog_url() -> None:
    m = manifest(
        launchers=[{"name": "l", "exec": "prog --backend {endpoint:backend}"}],
        service_endpoints=[
            {
                "name": "backend",
                "default_url": "https://ohb.works",
                "description": "The repointable data backend for this fixture.",
            }
        ],
    )
    assert "prog --backend https://ohb.works" in wrapper_body(m, m.launchers[0])


def test_a_working_directory_becomes_a_guarded_cd() -> None:
    m = manifest(launchers=[{"name": "l", "exec": "./RUN", "working_directory": "/opt/x"}])
    body = wrapper_body(m, m.launchers[0])
    assert "cd '/opt/x' || exit 1" in body
    assert body.splitlines()[-1] == "./RUN"


def test_desktop_entry_carries_mapped_categories_and_the_marker(tmp_path: Path) -> None:
    m = manifest()
    entry = desktop_entry(m, m.launchers[0], tmp_path / "bin" / "launchable")
    assert "Categories=" in entry
    for category in ("HamRadio", "AudioVideo", "Geography"):
        assert category in entry, entry
    assert "X-Hammunition-Package=launchable" in entry
    assert "Terminal=false" in entry


def test_steps_write_both_artifacts_and_they_are_real(tmp_path: Path) -> None:
    m = manifest()
    steps = launcher_steps(m, bin_dir=tmp_path / "bin", applications_dir=tmp_path / "apps")
    assert [s.kind for s in steps] == ["wrapper", "desktop-entry"]
    for step in steps:
        step.perform()
    wrapper = tmp_path / "bin" / "launchable"
    assert os.access(wrapper, os.X_OK)
    entry = (tmp_path / "apps" / "hammunition-launchable.desktop").read_text()
    assert f"Exec={wrapper}" in entry


def test_a_manifest_with_no_launchers_plans_nothing() -> None:
    m = manifest(launchers=[])
    assert launcher_steps(m, bin_dir=Path("/x"), applications_dir=Path("/y")) == []
