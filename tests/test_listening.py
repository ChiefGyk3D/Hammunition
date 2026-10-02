# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest

from hammunition.listening import LOOPBACK, bound_to_loopback_only, listening_addresses

HEADER = " sl local_address rem_address   st"


def _row(address: str, port: int, state: str = "0A") -> str:
    return f"  0: {address}:{port:04X} 00000000:0000 {state}"


def _table(path: Path, *rows: str) -> str:
    path.write_text("\n".join((HEADER, *rows)) + "\n")
    return str(path)


def test_reads_a_loopback_listener(tmp_path: Path) -> None:
    table = _table(tmp_path / "tcp", _row("0100007F", 4532))

    assert listening_addresses(4532, tables=(table,)) == {"0100007F"}
    assert bound_to_loopback_only(4532, tables=(table,))


def test_a_listener_on_any_address_is_not_loopback_only(tmp_path: Path) -> None:
    table = _table(tmp_path / "tcp", _row("00000000", 4532))

    assert bound_to_loopback_only(4532, tables=(table,)) is False


def test_ignores_non_listeners_other_ports_and_malformed_rows(tmp_path: Path) -> None:
    table = _table(
        tmp_path / "tcp",
        _row("00000000", 4532, "01"),
        _row("00000000", 4533),
        "malformed",
    )

    assert listening_addresses(4532, tables=(table,)) == set()
    assert bound_to_loopback_only(4532, tables=(table,))


def test_missing_tables_are_skipped_and_existing_tables_are_merged(tmp_path: Path) -> None:
    tcp = _table(tmp_path / "tcp", _row("0100007F", 4532))
    tcp6 = _table(tmp_path / "tcp6", _row("00000000000000000000000001000000", 4532))

    assert listening_addresses(4532, tables=(str(tmp_path / "missing"), tcp, tcp6)) == {
        "0100007F",
        "00000000000000000000000001000000",
    }
    assert listening_addresses(4532, tables=(str(tmp_path / "missing"),)) == set()
    assert LOOPBACK >= {"0100007F", "00000000000000000000000001000000"}


def test_an_unreadable_existing_table_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _table(tmp_path / "tcp", _row("0100007F", 4532))
    original_read_text = Path.read_text

    def read_text(
        path: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        if str(path) == table:
            raise PermissionError("not readable")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", read_text)

    assert listening_addresses(4532, tables=(table,)) is None
    assert bound_to_loopback_only(4532, tables=(table,)) is None
