# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`station set` rig flags, catalog-checked.  D-073 §4."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.station import load_station

cli = importlib.import_module("hammunition.cli.main")

_BY_ID = "/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0"


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *flags: str) -> int:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    return int(cli.main(["station", "set", *flags]))


def _station(tmp_path: Path) -> object:
    return load_station(path=tmp_path / "hammunition" / "station.yml")


def test_set_a_cat_rig(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-device",
        _BY_ID,
        "--rig-baud",
        "38400",
    )
    assert rc == 0
    st = _station(tmp_path)
    assert st.rig == "yaesu-ft-991a"  # type: ignore[attr-defined]
    assert st.rig_baud == 38400  # type: ignore[attr-defined]


def test_baud_out_of_range_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-device",
        _BY_ID,
        "--rig-baud",
        "2400",
    )
    assert rc != 0


def test_ptt_line_refused_for_a_cat_rig(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-device",
        _BY_ID,
        "--rig-ptt-line",
        "rts",
    )
    assert rc != 0


def test_set_a_ptt_only_rig(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "btech-uv-50pro",
        "--rig-device",
        _BY_ID,
        "--rig-ptt-line",
        "rts",
    )
    assert rc == 0
    st = _station(tmp_path)
    assert st.rig == "btech-uv-50pro"  # type: ignore[attr-defined]
    assert st.rig_ptt_line == "rts"  # type: ignore[attr-defined]


def test_switching_from_cat_to_ptt_only_clears_saved_baud(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-device",
        _BY_ID,
        "--rig-baud",
        "38400",
    )
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "btech-uv-50pro",
        "--rig-ptt-line",
        "rts",
    )
    assert rc == 0
    st = _station(tmp_path)
    assert st.rig == "btech-uv-50pro"  # type: ignore[attr-defined]
    assert st.rig_baud is None  # type: ignore[attr-defined]
    assert st.rig_ptt_line == "rts"  # type: ignore[attr-defined]
    assert st.rig_device == _BY_ID  # type: ignore[attr-defined]


def test_switching_from_ptt_only_to_cat_clears_saved_ptt_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "btech-uv-50pro",
        "--rig-device",
        _BY_ID,
        "--rig-ptt-line",
        "rts",
    )
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-baud",
        "9600",
    )
    assert rc == 0
    st = _station(tmp_path)
    assert st.rig == "yaesu-ft-991a"  # type: ignore[attr-defined]
    assert st.rig_baud == 9600  # type: ignore[attr-defined]
    assert st.rig_ptt_line is None  # type: ignore[attr-defined]
    assert st.rig_device == _BY_ID  # type: ignore[attr-defined]


def test_setting_baud_on_same_rig_keeps_other_saved_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-device",
        _BY_ID,
        "--rig-baud",
        "38400",
        "--rig-owner",
        "flrig",
    )
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-baud",
        "19200",
    )
    assert rc == 0
    st = _station(tmp_path)
    assert st.rig == "yaesu-ft-991a"  # type: ignore[attr-defined]
    assert st.rig_baud == 19200  # type: ignore[attr-defined]
    assert st.rig_device == _BY_ID  # type: ignore[attr-defined]
    assert st.rig_owner == "flrig"  # type: ignore[attr-defined]


def test_ptt_only_requires_a_line(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(monkeypatch, tmp_path, "--rig", "btech-uv-50pro", "--rig-device", _BY_ID)
    assert rc != 0


def test_baud_refused_for_ptt_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "btech-uv-50pro",
        "--rig-device",
        _BY_ID,
        "--rig-ptt-line",
        "rts",
        "--rig-baud",
        "9600",
    )
    assert rc != 0


def test_flrig_refused_for_ptt_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "btech-uv-50pro",
        "--rig-device",
        _BY_ID,
        "--rig-ptt-line",
        "rts",
        "--rig-owner",
        "flrig",
    )
    assert rc != 0


def test_unknown_rig_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rc = _run(monkeypatch, tmp_path, "--rig", "not-a-rig", "--rig-device", _BY_ID)
    assert rc != 0


def test_clear_rig(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _run(
        monkeypatch,
        tmp_path,
        "--rig",
        "yaesu-ft-991a",
        "--rig-device",
        _BY_ID,
        "--rig-baud",
        "38400",
    )
    rc = _run(monkeypatch, tmp_path, "--clear-rig")
    assert rc == 0
    st = _station(tmp_path)
    assert st.rig is None  # type: ignore[attr-defined]
