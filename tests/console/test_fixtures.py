# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
from typing import Any

import pytest

from .fixture_scan import findings
from .schema_check import validate

FIX = Path(__file__).parent / "fixtures"
FILES = sorted(p for p in FIX.glob("*.json") if p.name != "manifest.json")


def schema_for(path: Path, kind: str) -> dict[str, Any]:
    suffixed = FIX / "schemas" / f"{kind}-without.json"
    plain = FIX / "schemas" / f"{kind}.json"
    chosen = suffixed if path.stem.endswith("-without") and suffixed.exists() else plain
    assert chosen.exists(), (
        f"no schema for {path.name}: run tests/console/capture_fixtures.py --docs <json-interface.md> (in a container)"
    )
    return json.loads(chosen.read_text())  # type: ignore[no-any-return]


def test_there_are_fixtures() -> None:
    assert len(FILES) >= 15, "run tests/console/capture_fixtures.py (in a container)"


# Hand-authored from the engine's topo-bound branch (PR #260); the published schema predates its fields.
AHEAD_OF_SCHEMA = {"plan-station-size-consent.json"}


@pytest.mark.parametrize(
    "path", [p for p in FILES if p.name not in AHEAD_OF_SCHEMA], ids=lambda p: p.name
)
def test_fixture_validates_against_the_engines_schema(path: Path) -> None:
    doc = json.loads(path.read_text())
    assert doc["schema"] == "hammunition/1"
    problems = validate(doc, schema_for(path, doc["kind"]))
    assert problems == [], f"{path.name} disagrees with the published schema: {problems[:3]}"


@pytest.mark.parametrize(
    "path",
    [*FILES, *FIX.glob("*.exit"), FIX / "manifest.json", FIX / "README.md"],
    ids=lambda p: p.name,
)
def test_fixture_carries_no_identifier(path: Path) -> None:
    assert findings(path.read_text()) == [], f"{path.name}: review and scrub by hand"


def test_e1_fields_are_present_with_and_absent_without() -> None:
    with_e1 = json.loads((FIX / "list-all.json").read_text())["profiles"][0]
    without = json.loads((FIX / "list-all-without.json").read_text())["profiles"][0]
    assert {"members", "installed", "installed_size_bytes"} <= set(with_e1)
    assert not {"members", "installed", "installed_size_bytes"} & set(without)


def test_the_station_fixtures_use_only_placeholders() -> None:
    # N0TST, not N0CALL: the engine's callsign check rejects N0CALL (four-letter suffix).
    doc = json.loads((FIX / "station-set.json").read_text())
    assert (doc["callsign"], doc["grid_square"]) == ("N0TST", "FN31pr")
    assert json.loads((FIX / "station-none.json").read_text())["callsign"] is None
