# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Inputs the Atheris targets under ``fuzz/`` crashed on, kept as ordinary tests.

Each one escaped as an exception nothing documents (a ``csv.Error`` or a
``TypeError``) where the module's own error is the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition import repeater_sources, repeaters
from hammunition.repeaters import RepeaterInputError
from hammunition.station import StationError, load_station

HAND = "callsign,output_mhz,offset_mhz,tone,mode,lat,lon,name,notes\n"
RB = "callsign,frequency,lat,long\n"
ETCC = "call,band,chan,txmhz,rxmhz,lat,lon\n"


def _csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "in.csv"
    path.write_bytes(body.encode())
    return path


@pytest.mark.parametrize("header", [HAND, RB])
def test_a_bare_carriage_return_in_a_csv_row_is_a_refusal(tmp_path: Path, header: str) -> None:
    with pytest.raises(RepeaterInputError, match="not valid CSV"):
        repeaters.read_input(_csv(tmp_path, header + "N0CALL,146.94\rx,39.8,-89.6\n"))


def test_a_bare_carriage_return_in_an_etcc_row_is_a_refusal() -> None:
    with pytest.raises(RepeaterInputError, match="not valid CSV"):
        repeater_sources.parse_etcc(
            (ETCC + "GB3XX,2m,R0,145.6\r00,145.0,51,-1\n").encode(), "https://x.invalid"
        )


def test_a_bare_carriage_return_in_a_direwolf_row_is_a_refusal(tmp_path: Path) -> None:
    head = ",".join(repeaters.DIREWOLF_HEAD) + ",dti,frequency\n"
    path = _csv(tmp_path, head + "a,b,c,;,146\r9\n")
    with pytest.raises(RepeaterInputError, match="not valid CSV"):
        repeater_sources.read_direwolf_logs([path])


def test_a_station_key_that_is_not_text_is_a_station_error(tmp_path: Path) -> None:
    path = tmp_path / "station.yml"
    path.write_text("? \n: x\n")  # a mapping whose one key is null
    with pytest.raises(StationError, match="nothing can use"):
        load_station(path)
