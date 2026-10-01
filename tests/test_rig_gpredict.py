# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""gpredict's radio file points at the shared rigctld.  D-073 §7."""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.load import load_catalog
from hammunition.plan import _plan_config
from hammunition.station import Station

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "packages"
_BY_ID = "/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0"


def _gpredict() -> object:
    return load_catalog(CATALOG)["gpredict"]


def test_the_radio_file_is_written_when_the_rig_device_is_set(tmp_path: Path) -> None:
    station = Station(grid_square="FN31pr", rig="yaesu-ft-991a", rig_device=_BY_ID, rig_baud=38400)
    writable, deferred = _plan_config(_gpredict(), station, tmp_path)
    bodies = {Path(cfg.path).name: body for _unit, cfg, body in writable}
    assert "hammunition.rig" in bodies
    radio = bodies["hammunition.rig"]
    assert "Host=localhost" in radio
    assert "Port=4532" in radio


def test_the_radio_file_defers_when_no_rig_is_set(tmp_path: Path) -> None:
    station = Station(grid_square="FN31pr")  # QTH known, rig not
    writable, deferred = _plan_config(_gpredict(), station, tmp_path)
    names = {Path(cfg.path).name for _unit, cfg, _body in writable}
    assert "hammunition.rig" not in names
    assert any("rig_device" in d.why for d in deferred)
