# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The artifact URL sweep lists every pinned URL and crashes on none.  D-067.

A derived block's ``source`` is a unit name, not an artifact; the sweep
read it as one and died on the first map unit (found 2026-09-29).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from hammunition.manifest.load import load_catalog

REPO_ROOT = Path(__file__).resolve().parent.parent


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_artifact_urls", REPO_ROOT / "scripts" / "check_artifact_urls.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_sweep_reads_the_whole_catalog_and_includes_the_poi_writer() -> None:
    urls = _script().artifact_urls(load_catalog(REPO_ROOT / "catalog" / "packages"))
    assert all(url.startswith(("https://", "http://")) for _, url in urls)
    assert ("mapsforge-poi", next(u for n, u in urls if n == "mapsforge-poi")) in urls
    assert any(u.endswith("mapsforge-poi-writer-0.25.0-jar-with-dependencies.jar") for _, u in urls)
    assert not any(n in ("osm-navit", "osm-garmin", "mapsforge-map") for n, _ in urls)
