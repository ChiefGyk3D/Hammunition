# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 3DEP tile-list generator (D-068, amended 2026-10-01), on a synthetic
listing; no network."""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "gen_3dep_tiles.py"
PREFIX = "StagedProducts/Elevation/13/TIFF/current/"
MD5 = "0123456789abcdef0123456789abcdef"
MD6 = "fedcba9876543210fedcba9876543210"

LISTING = [
    (f"{PREFIX}n39w079/USGS_13_n39w079.tif", 488, f'"{MD5}-94"', "2025-03-01T00:00:00.000Z"),
    (f"{PREFIX}n39w079/USGS_13_n39w079.xml", 9, f'"{MD6}"', "2025-03-01T00:00:00.000Z"),
    (f"{PREFIX}n39w079/USGS_13_n39w079.jpg", 5, f'"{MD6}"', "2025-03-01T00:00:00.000Z"),
    (f"{PREFIX}n39w078/USGS_13_n39w078_20220101.tif", 7, f'"{MD6}"', "2022-01-01T00:00:00.000Z"),
    (f"{PREFIX}n45w073/USGS_13_n45w073.tif", 400, f'"{MD6}"', "2024-06-01T00:00:00.000Z"),
    (f"{PREFIX}n45w072/USGS_13_n46w072.tif", 3, f'"{MD6}"', "2024-06-01T00:00:00.000Z"),
]


@functools.cache
def _gen() -> Any:
    spec = importlib.util.spec_from_file_location("gen_3dep_tiles", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_only_each_folder_s_own_current_tile_is_kept() -> None:
    built = _gen().build(LISTING)
    assert [(r.name, r.size, r.etag) for r in built.rows] == [
        ("USGS_13_n39w079", 488, f"{MD5}-94"),
        ("USGS_13_n45w073", 400, MD6),
    ]
    assert built.newest == "2025-03-01"


def test_rendering_is_deterministic_and_reads_back(tmp_path: Path) -> None:
    gen = _gen()
    text = gen.render(gen.build(LISTING))
    assert text == gen.render(gen.build(list(reversed(LISTING))))
    assert gen.GENERATED_MARK in text
    assert [r.name for r in gen.check_shape(text).rows] == ["USGS_13_n39w079", "USGS_13_n45w073"]


def test_a_hand_edit_fails_the_offline_check() -> None:
    gen = _gen()
    text = gen.render(gen.build(LISTING))
    with pytest.raises(gen.GeneratorError):
        gen.check_shape(text.replace(f"USGS_13_n45w073 400 {MD6}\n", ""))
    with pytest.raises(gen.GeneratorError):
        gen.check_shape(text.replace(gen.GENERATED_MARK, "hand made"))


def test_the_online_check_names_a_gone_or_changed_tile() -> None:
    gen = _gen()
    carried = gen.build(LISTING).rows
    live = gen.build(
        [
            (f"{PREFIX}n39w079/USGS_13_n39w079.tif", 488, f'"{MD6}-94"', "2026-01-01T00:00:00Z"),
        ]
    ).rows
    problems = gen.check_online(carried, live)
    assert len(problems) == 2
    assert any("USGS_13_n45w073" in p and "no longer" in p for p in problems)
    assert any("USGS_13_n39w079" in p and MD6 in p for p in problems)
    assert gen.check_online(carried, carried) == []


def test_the_carried_list_is_well_formed() -> None:
    gen = _gen()
    built = gen.check_shape(gen.LIST.read_text())
    assert len(built.rows) > 1000
