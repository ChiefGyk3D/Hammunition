# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The values the engine shares with the GPS tether equal the tether's own.

The tether is hammunition-gps-tether (D-071 note, 2026-10-02). Its source is
read as text, never imported, from a checkout beside this one or from the
installed tree; where neither is present the test skips and says why, so the
check runs wherever the tether is.
"""

from __future__ import annotations

import ast
import contextlib
from pathlib import Path

import pytest

from hammunition import geoclue, reference, tether_contract

REPO = Path(__file__).resolve().parents[1]
PACKAGE = Path("src") / "hammunition_gps_tether"
CANDIDATES = (
    REPO.parent / "hammunition-gps-tether",
    Path("/usr/local/share/hammunition/gps-tether"),
)


def _package() -> Path:
    for root in CANDIDATES:
        if (root / PACKAGE / "tether.py").is_file():
            return root / PACKAGE
    pytest.skip("hammunition-gps-tether source not found beside this checkout or installed")


def _constants(path: Path) -> dict[str, object]:
    found: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                with contextlib.suppress(ValueError):
                    found[target.id] = ast.literal_eval(node.value)
    return found


def test_the_ports_equal_the_tethers() -> None:
    theirs = _constants(_package() / "tether.py")
    assert theirs["PORT"] == tether_contract.NMEA_PORT
    assert theirs["POSITION_PORT"] == tether_contract.POSITION_PORT


def test_the_geoclue_four_equal_the_tethers() -> None:
    theirs = _constants(_package() / "geoclue.py")
    assert theirs["DROPIN"] == tether_contract.GEOCLUE_DROPIN
    assert theirs["HEADER"] == tether_contract.GEOCLUE_HEADER
    assert theirs["SOCKET"] == tether_contract.GEOCLUE_SOCKET
    assert theirs["GROUP"] == tether_contract.GEOCLUE_GROUP


def test_the_engine_uses_the_contract_not_its_own_copies() -> None:
    # PATHS holds the real defaults; a fixture may have repointed the attributes.
    assert geoclue.PATHS["DROPIN"] == tether_contract.GEOCLUE_DROPIN
    assert geoclue.PATHS["SOCKET"] == tether_contract.GEOCLUE_SOCKET
    assert geoclue.HEADER == tether_contract.GEOCLUE_HEADER
    assert geoclue.GROUP == tether_contract.GEOCLUE_GROUP
    assert reference.POSITION_PORT == tether_contract.POSITION_PORT


def test_the_engine_carries_no_tether_module() -> None:
    assert not (REPO / "src" / "hammunition" / "gps_tether.py").exists()
