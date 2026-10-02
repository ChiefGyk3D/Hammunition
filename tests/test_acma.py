# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ACMA register: the file check and the repeater reader.  D-074,
amended 2026-10-01.

Every register here is synthetic (:mod:`acma_support`), in the real file's
shape. No network.
"""

from __future__ import annotations

import re
import zipfile
from datetime import date
from pathlib import Path

import pytest

from acma_support import (
    CLIENT_NAME,
    CLIENT_STREET,
    TASMANIA,
    register_members,
    write_register,
)
from hammunition import acma
from hammunition import repeater_sources as rs
from hammunition.repeaters import ACMA, Repeater, RepeaterInputError, merge, read_input


def _reg(tmp_path: Path, **kwargs: object) -> Path:
    return write_register(tmp_path / "spectra_rrl.zip", **kwargs)  # type: ignore[arg-type]


# --- the file check ---------------------------------------------------------------------


def test_a_whole_register_passes_and_is_dated_by_its_licence_table(tmp_path: Path) -> None:
    got = acma.check_register(_reg(tmp_path))
    assert got.day == date(2026, 10, 2)
    assert got.members == len(register_members())


def test_a_web_page_is_not_a_register(tmp_path: Path) -> None:
    page = tmp_path / "spectra_rrl.zip"
    page.write_text("<html>Service unavailable</html>")
    with pytest.raises(acma.AcmaError, match="not a zip archive"):
        acma.check_register(page)


def test_a_zip_without_the_tables_is_refused_by_name(tmp_path: Path) -> None:
    members = register_members()
    del members["site.csv"]
    with pytest.raises(acma.AcmaError, match=re.escape("lacks site.csv")):
        acma.check_register(_reg(tmp_path, members=members))


def test_a_changed_layout_is_refused_by_column(tmp_path: Path) -> None:
    members = register_members()
    members["site.csv"] = members["site.csv"].replace("LATITUDE", "LAT", 1)
    with pytest.raises(acma.AcmaError, match=re.escape("site.csv has no column LATITUDE")):
        acma.check_register(_reg(tmp_path, members=members))


def test_a_damaged_member_fails_its_crc(tmp_path: Path) -> None:
    """Falsified: one byte of a stored member flipped after the zip was
    written; the CRC-32 check names the member."""
    path = tmp_path / "spectra_rrl.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, text in register_members().items():
            archive.writestr(name, text)
    raw = bytearray(path.read_bytes())
    # README.TXT: a member nothing else reads, so only the CRC pass sees it.
    at = raw.find(b"LICENCE FOR USE")
    raw[at] ^= 0x20
    path.write_bytes(bytes(raw))
    with pytest.raises(acma.AcmaError, match=r"CRC-32.*README\.TXT|README\.TXT.*CRC-32"):
        acma.check_register(path)
    # Without the CRC pass the same file is accepted: the pass is what caught it.
    assert acma.check_register(path, crc=False).members == len(register_members())


def test_a_truncated_download_is_refused(tmp_path: Path) -> None:
    path = _reg(tmp_path)
    path.write_bytes(path.read_bytes()[:-200])
    with pytest.raises(acma.AcmaError):
        acma.check_register(path)


def test_an_archive_that_would_inflate_past_the_limit_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(acma, "INFLATE_LIMIT", 100)
    with pytest.raises(acma.AcmaError, match="past the 100-byte limit"):
        acma.check_register(_reg(tmp_path))


def test_the_probe_asks_only_the_register_url() -> None:
    with pytest.raises(acma.AcmaError, match=re.escape("only https://cdn.acma.gov.au")):
        acma.AcmaProbe().size("https://example.invalid/spectra_rrl.zip")


# --- the reader --------------------------------------------------------------------------


def test_read_keeps_granted_transmitters_in_the_box_with_their_input(tmp_path: Path) -> None:
    parsed = rs.read_acma(_reg(tmp_path), [TASMANIA])
    assert parsed.format == ACMA
    # Seven transmitters on amateur repeater licences; land mobile is not read.
    assert parsed.read == 7
    calls = {(r.callsign, r.output_hz) for r in parsed.rows}
    assert calls == {("VK7RZZ", 146_700_000), ("VK7RZZ", 438_525_000)}
    two_m = next(r for r in parsed.rows if r.output_hz == 146_700_000)
    assert two_m.offset_hz == -600_000
    assert two_m.mode == "FM (16K0F3E)"
    assert two_m.place == "Mount Wellington summit HOBART, TAS"
    assert two_m.notes == "ACMA licence 900001/1; site position within 10 metres"
    assert (two_m.lat, two_m.lon) == (-42.896, 147.237)
    seventy = next(r for r in parsed.rows if r.output_hz == 438_525_000)
    assert seventy.mode == "FM and digital (16K0F9W)"
    assert seventy.offset_hz == -5_000_000


def test_every_left_out_row_is_counted_with_its_reason(tmp_path: Path) -> None:
    parsed = rs.read_acma(_reg(tmp_path), [TASMANIA])
    skipped = {s.reason: (s.count, s.first) for s in parsed.skipped}
    assert skipped["no site in the register"] == (1, (7,))
    assert skipped["no usable output frequency"] == (1, (8,))
    assert skipped["the licence is not granted (expired, cancelled or refused)"] == (1, (10,))
    # Outside the regions: counted, never numbered (which rows are outside
    # says where the regions are).
    assert skipped[rs.ACMA_OUTSIDE] == (1, ())
    assert parsed.read == len(parsed.rows) + sum(s.count for s in parsed.skipped)
    # The duplicate transmitter is merged by D-064's key, as every layer is.
    rows, merged = merge(parsed.rows)
    assert (len(rows), merged) == (2, 1)


def test_no_box_or_a_box_elsewhere_keeps_nothing(tmp_path: Path) -> None:
    path = _reg(tmp_path)
    assert rs.read_acma(path, []).rows == ()
    vermont = (-73.5, -71.4, 45.1, 42.7)
    parsed = rs.read_acma(path, [vermont])
    assert parsed.rows == ()
    assert {s.reason: s.count for s in parsed.skipped}[rs.ACMA_OUTSIDE] == 4


def test_a_box_across_the_antimeridian_is_read_the_way_round_it_wraps(tmp_path: Path) -> None:
    across = (170.0, -170.0, -10.0, -50.0)  # 170 E to 170 W: Tasmania is not in it
    assert rs.read_acma(_reg(tmp_path), [across]).rows == ()
    wide = (140.0, -170.0, -10.0, -50.0)  # 140 E eastwards to 170 W: it is
    assert len(rs.read_acma(_reg(tmp_path), [wide]).rows) == 4


def test_the_licensee_table_is_never_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    real = zipfile.ZipFile.open

    def spy(self: zipfile.ZipFile, name: object, *args: object, **kwargs: object) -> object:
        opened.append(name if isinstance(name, str) else getattr(name, "filename", ""))
        return real(self, name, *args, **kwargs)  # type: ignore[arg-type]

    path = _reg(tmp_path)
    monkeypatch.setattr(zipfile.ZipFile, "open", spy)
    parsed = rs.read_acma(path, [TASMANIA])
    assert "device_details.csv" in opened  # the spy sees the reads
    assert "client.csv" not in opened
    text = repr(parsed)
    assert CLIENT_NAME not in text and CLIENT_STREET not in text


def test_a_file_that_is_not_the_register_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as archive:
        archive.writestr("readme.txt", "hello")
    with pytest.raises(RepeaterInputError, match=re.escape("lacks licence.csv")):
        rs.read_acma(other, [TASMANIA])


def test_the_layer_is_named_and_attributed_as_the_licence_requires(tmp_path: Path) -> None:
    day = rs.acma_date(_reg(tmp_path))
    assert rs.acma_layer_name(day) == "Repeaters (ACMA, 2026-10-02)"
    text = rs.acma_licence(day)
    assert text.startswith("Based on Australian Communications and Media Authority information.")
    assert "unverified" in text


def test_the_regulator_comes_second_in_the_all_sources_order() -> None:
    assert rs.PRECEDENCE.index(ACMA) == 3  # after the export's three formats
    assert rs.PRECEDENCE[:3] == ("repeaterbook-gpx", "repeaterbook-csv", "hand-csv")
    assert rs.PRECEDENCE.index(ACMA) < rs.PRECEDENCE.index("etcc-csv")


def test_the_regulator_row_wins_a_join_with_open_repeater() -> None:
    acma_row = Repeater("VK7RZZ", 146_700_000, -42.896, 147.237, ACMA, mode="FM (16K0F3E)")
    community = Repeater(
        "VK7RZZ",
        146_700_000,
        -42.90,
        147.24,
        "open-repeater-json",
        offset_hz=-600_000,
        tone="123.0",
    )
    rows, joined = rs.cross_merge([[community], [acma_row]])
    assert joined == 1
    (kept,) = rows
    assert kept.source == ACMA and kept.lat == -42.896
    assert kept.tone == "123.0" and kept.offset_hz == -600_000


def test_import_file_refuses_the_register_and_names_the_route(tmp_path: Path) -> None:
    with pytest.raises(RepeaterInputError, match="--from-acma"):
        read_input(_reg(tmp_path))
    other = tmp_path / "export.zip"
    with zipfile.ZipFile(other, "w") as archive:
        archive.writestr("export.gpx", "<gpx/>")
    with pytest.raises(RepeaterInputError, match="unpack it"):
        read_input(other)


def test_a_member_in_a_compression_nothing_reads_is_a_named_refusal(tmp_path: Path) -> None:
    """Final review: a table whose central-directory entry names a compression
    method zipfile cannot read raised NotImplementedError past the check and
    the import, a traceback instead of a named error."""
    path = tmp_path / "spectra_rrl.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, text in register_members().items():
            archive.writestr(name, text)
    raw = bytearray(path.read_bytes())
    entry = raw.find(b"PK\x01\x02", raw.find(b"PK\x01\x02"))
    while entry != -1:
        name_length = int.from_bytes(raw[entry + 28 : entry + 30], "little")
        if raw[entry + 46 : entry + 46 + name_length] == b"site.csv":
            raw[entry + 10 : entry + 12] = (99).to_bytes(2, "little")
            break
        entry = raw.find(b"PK\x01\x02", entry + 4)
    assert entry != -1
    path.write_bytes(bytes(raw))
    with pytest.raises(acma.AcmaError, match="damaged"):
        acma.check_register(path, crc=False)
    with pytest.raises(RepeaterInputError, match="damaged"):
        rs.read_acma(path, [TASMANIA])
