# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atheris target: the station config reader (``station.load_station``).

``load_station`` takes a path, so the fuzzed YAML goes to a temp file inside
the target; the real config path is never consulted. ``StationError`` is the
documented rejection.
"""

import sys
import tempfile
from pathlib import Path

import atheris
from _seeded import text_from

with atheris.instrument_imports():
    from hammunition.station import StationError, load_station

_SEED = (
    "callsign: N0CALL\ngrid_square: FN31pr\nnode_alias: TEST\nmap_regions: [delaware]\n"
    "mirror: http://192.0.2.1:8080\nrig: ft-991a\nrig_baud: 38400\ntopo_radius_km: 100\n"
    "topo_all: false\ndem_source: 3dep\n"
)
_TMP = Path(tempfile.mkdtemp(prefix="fuzz-station-"))


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    path = _TMP / "station.yml"
    path.write_text(text_from(fdp, _SEED), encoding="utf-8")
    try:
        station = load_station(path)
    except StationError:
        return
    station.as_dict()


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
