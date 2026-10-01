# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The FSTopo index generator (D-068, amended 2026-10-01), on synthetic
features; no network."""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from hammunition.fstopo import load_pins

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "gen_fstopo_index.py"


def _feature(secoord: int | None, name: str, state: str, vintage: int | None, x: float) -> Any:
    ring = [[x, 0.0], [x + 0.125, 0.0], [x + 0.125, 0.125], [x, 0.125], [x, 0.0]]
    return {
        "attributes": {
            "secoord": secoord,
            "cell_name": name,
            "primary_state": state,
            "vintage": vintage,
        },
        "geometry": {"rings": [ring]} if secoord else {"rings": []},
    }


FEATURES = [
    _feature(1230001, "Beta  Knob", "Virginia", 11, 0.125),
    _feature(1230000, "Alpha", "Vermont", None, 0.0),
    _feature(None, "Supply", "Arkansas", None, 1.0),
]


@functools.cache
def _gen() -> Any:
    spec = importlib.util.spec_from_file_location("gen_fstopo_index", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_features_become_sorted_rows_with_postal_codes() -> None:
    built = _gen().build(FEATURES, "2025-08-08")
    assert [(q.secoord, q.state, q.cell, q.vintage) for q in built.quads] == [
        (1230000, "VT", "Alpha", 0),
        (1230001, "VA", "Beta Knob", 11),
    ]
    assert (built.quads[1].west, built.quads[1].east) == (0.125, 0.25)
    assert built.missing == 1


def test_an_unknown_state_is_refused_by_name() -> None:
    gen = _gen()
    with pytest.raises(gen.GeneratorError, match="Atlantis"):
        gen.build([_feature(1, "Lost", "Atlantis", 1, 0.0)], "2025-08-08")


def test_rendering_is_deterministic_and_checks_offline() -> None:
    gen = _gen()
    text = gen.render(gen.build(FEATURES, "2025-08-08"))
    assert text == gen.render(gen.build(list(reversed(FEATURES)), "2025-08-08"))
    assert "last edited 2025-08-08" in text
    assert len(gen.check_shape(text).quads) == 2
    with pytest.raises(gen.GeneratorError):
        gen.check_shape(text.replace("0 0.125 0.125 0.25 1230001 11 VA Beta Knob\n", ""))
    with pytest.raises(gen.GeneratorError):
        gen.check_shape(text.replace(gen.GENERATED_MARK, "made by hand"))


def test_the_online_check_fails_on_a_gone_quad_and_counts_a_new_vintage() -> None:
    gen = _gen()
    carried = gen.build(FEATURES, "x").quads
    live = gen.build([_feature(1230001, "Beta Knob", "Virginia", 12, 0.125)], "x").quads
    problems, changed = gen.check_online(carried, live)
    assert problems == ["1230000 (Alpha): no longer in the index"]
    assert changed == 1


def test_pins_render_and_read_back(tmp_path: Path) -> None:
    gen = _gen()
    path = tmp_path / "fstopo-pins.yaml"
    path.write_text(gen.render_pins({"1230001": (21, "b" * 64), "1230000": (20, "a" * 64)}))
    pins = load_pins(path)
    assert list(pins) == [1230000, 1230001] and pins[1230001].size == 21
    path.write_text(gen.render_pins({}))
    assert load_pins(path) == {}


def test_the_layer_is_paged_until_a_short_page(tmp_path: Path) -> None:
    gen = _gen()
    asked: list[str] = []

    def get(url: str) -> bytes:
        asked.append(url)
        offset = int(url.split("resultOffset=")[1].split("&")[0])
        count = gen.PAGE if offset == 0 else 1
        import json

        return json.dumps({"features": [FEATURES[0]] * count}).encode()

    assert len(list(gen.list_features(get))) == gen.PAGE + 1
    assert len(asked) == 2


def test_the_carried_index_and_pins_are_well_formed() -> None:
    gen = _gen()
    built = gen.check_shape(gen.INDEX.read_text())
    assert len(built.quads) > 18000
    load_pins(gen.PINS)
