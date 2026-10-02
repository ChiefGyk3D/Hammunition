# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The federal and worldwide files behind the infrastructure layers.  D-075.

Every file here is built by the test in the publisher's measured layout
(the spike's copies of 2026-10-01: NASR ``APT_CSV.zip``, EIA-860M's
workbook, WRI's CSV, FCC ``r_tower.zip``, NWS ``ccl-data.js``), with
synthetic rows. Nothing is fetched.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from hammunition import infra_sources as src
from hammunition.infra import InfraInputError

#: Delaware's box, as its extract's header carries it (west, south, east, north).
DELAWARE = (-75.79, 38.45, -74.96, 40.03)
BOXES = [DELAWARE]
WHEN = datetime(2026, 10, 1, 18, 30, tzinfo=UTC)

# --- NASR -----------------------------------------------------------------------------

NASR_HEAD = (
    "EFF_DATE,SITE_NO,SITE_TYPE_CODE,STATE_CODE,ARPT_ID,CITY,COUNTRY_CODE,ARPT_NAME,"
    "FACILITY_USE_CODE,LAT_DECIMAL,LONG_DECIMAL,ELEV,ARPT_STATUS,ICAO_ID"
)


def _nasr(tmp_path: Path, rows: list[str], head: str = NASR_HEAD) -> Path:
    path = tmp_path / "APT_CSV.zip"
    body = head + "\n" + "\n".join(rows) + "\n"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("APT_BASE.csv", body)
        z.writestr("APT_RWY.csv", "not read\n")
    return path


NASR_ROWS = [
    '"2026/10/01","1.","A","DE","0T0","TESTVILLE","US","TESTVILLE MUNI","PU",38.7,-75.5,52.1,"O","KTST"',
    '"2026/10/01","2.","H","DE","0T1","TESTVILLE","US","TESTVILLE GENERAL","PR",38.71,-75.51,40,"O",""',
    '"2026/10/01","3.","C","DE","0T2","TESTVILLE","US","TESTVILLE HARBOR","PU",38.72,-75.52,0,"CI",""',
    '"2026/10/01","4.","A","VT","1V0","ELSEWHERE","US","ELSEWHERE FIELD","PU",44.0,-72.5,900,"O",""',
    '"2026/10/01","5.","A","DE","0T3","TESTVILLE","US","NO POSITION","PU",,,10,"O",""',
]


def test_nasr_keeps_every_site_type_in_the_boxes_with_its_status(tmp_path: Path) -> None:
    got = src.read_nasr(_nasr(tmp_path, NASR_ROWS), BOXES)
    assert [p.name for p in got.points] == [
        "Testville Muni (0T0)",
        "Testville General (0T1)",
        "Testville Harbor (0T2)",
    ]
    assert [p.kind for p in got.points] == ["airport", "heliport", "seaplane base"]
    assert "closed indefinitely" in got.points[2].details
    assert "public use" in got.points[0].details and "ICAO KTST" in got.points[0].details
    assert "private use" in got.points[1].details
    assert got.read == 5 and got.outside == 1
    assert got.skipped == {src.NO_POSITION: [6]}


def test_nasr_is_dated_and_licensed_by_its_cycle(tmp_path: Path) -> None:
    got = src.read_nasr(_nasr(tmp_path, NASR_ROWS), BOXES)
    assert got.day == date(2026, 10, 1)
    assert got.licence == "FAA NASR 2026-10-01, public domain"
    assert got.name == "Airports and heliports (FAA NASR 2026-10-01)"
    assert got.layer_id == "faa-airports"


def test_a_zip_without_apt_base_is_refused_by_name(tmp_path: Path) -> None:
    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("other.csv", "a\n")
    with pytest.raises(InfraInputError, match=r"APT_BASE\.csv"):
        src.read_nasr(path, BOXES)


def test_a_csv_without_the_columns_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InfraInputError, match="LAT_DECIMAL"):
        src.read_nasr(_nasr(tmp_path, ["1,2"], head="EFF_DATE,ARPT_ID"), BOXES)


def test_a_member_over_the_cap_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(src, "MEMBER_LIMIT", 100)
    with pytest.raises(InfraInputError, match="larger than"):
        src.read_nasr(_nasr(tmp_path, NASR_ROWS), BOXES)


def test_not_a_zip_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "APT_CSV.zip"
    path.write_text("not a zip")
    with pytest.raises(InfraInputError, match="not a zip"):
        src.read_nasr(path, BOXES)


# --- EIA-860M ---------------------------------------------------------------------------

EIA_HEAD = [
    "Entity ID", "Entity Name", "Plant ID", "Plant Name", "Google Map", "Bing Map",
    "Plant State", "County", "Balancing Authority Code", "Sector", "Generator ID",
    "Unit Code", "Nameplate Capacity (MW)", "Net Summer Capacity (MW)",
    "Net Winter Capacity (MW)", "Technology", "Energy Source Code", "Prime Mover Code",
    "Operating Month", "Operating Year", "Planned Retirement Month",
    "Planned Retirement Year", "Status", "Latitude", "Longitude",
]  # fmt: skip


def _col(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _xlsx(tmp_path: Path, rows: list[list[str]], *, doctype: bool = False) -> Path:
    """A minimal workbook in EIA's layout: an Operating sheet first, shared
    strings for text, numbers as values, a title row and a blank row."""
    strings: list[str] = []

    def cell(ref: str, value: str) -> str:
        try:
            float(value)
        except ValueError:
            if value not in strings:
                strings.append(value)
            return f'<c r="{ref}" t="s"><v>{strings.index(value)}</v></c>'
        return f'<c r="{ref}"><v>{value}</v></c>'

    body = []
    for number, row in enumerate(rows, start=1):
        cells = "".join(cell(f"{_col(i)}{number}", v) for i, v in enumerate(row) if v != "")
        body.append(f'<row r="{number}">{cells}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    head = '<!DOCTYPE x [<!ENTITY a "b">]>' if doctype else ""
    sheet = f"{head}<worksheet {ns}><sheetData>{''.join(body)}</sheetData></worksheet>"
    shared = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
    path = tmp_path / "eia860m.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook {ns} xmlns:r="{rel}"><sheets>'
            '<sheet name="Operating" sheetId="1" r:id="rId1"/>'
            '<sheet name="Planned" sheetId="2" r:id="rId2"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="x"/></Relationships>',
        )
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>{shared}</sst>")
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/worksheets/sheet2.xml", f"<worksheet {ns}><sheetData/></worksheet>")
    return path


def _gen(plant: str, name: str, gen: str, mw: str, tech: str, lat: str, lon: str) -> list[str]:
    row = dict.fromkeys(EIA_HEAD, " ")
    row.update(
        {
            "Entity ID": "9",
            "Entity Name": "Testville Power Co",
            "Plant ID": plant,
            "Plant Name": name,
            "Plant State": "DE",
            "Generator ID": gen,
            "Nameplate Capacity (MW)": mw,
            "Technology": tech,
            "Status": "(OP) Operating",
            "Latitude": lat,
            "Longitude": lon,
        }
    )
    return [row[h] for h in EIA_HEAD]


EIA_ROWS = [
    ["Inventory of Operating Generators as of August 2026"],
    [],
    EIA_HEAD,
    _gen("101", "Testville Station", "1", "100.5", "Natural Gas Fired Combined Cycle", "38.8", "-75.4"),
    _gen("101", "Testville Station", "2", "20", "Solar Photovoltaic", "38.8", "-75.4"),
    _gen("102", "Elsewhere Hydro", "1", "5", "Conventional Hydroelectric", "44.1", "-72.6"),
    _gen("103", "Nowhere Plant", "1", "5", "Solar Photovoltaic", " ", " "),
]  # fmt: skip


def test_eia_writes_one_point_a_plant_with_its_capacity_summed(tmp_path: Path) -> None:
    got = src.read_eia(_xlsx(tmp_path, EIA_ROWS), BOXES)
    (plant,) = got.points
    assert plant.name == "Testville Station"
    assert "120.5 MW nameplate" in plant.details and "2 generators" in plant.details
    assert (
        "Natural Gas Fired Combined Cycle, Solar Photovoltaic" in plant.details
        and "operator Testville Power Co" in plant.details
        and "EIA plant 101" in plant.details
    )
    assert got.read == 4 and got.outside == 1
    assert got.skipped == {src.NO_POSITION: [7]}


def test_eia_licence_line_is_exactly_what_eia_asks(tmp_path: Path) -> None:
    got = src.read_eia(_xlsx(tmp_path, EIA_ROWS), BOXES)
    assert got.licence == "Source: U.S. Energy Information Administration (Aug 2026), public domain"
    assert got.day == date(2026, 8, 1)
    assert got.name == "Power plants (EIA-860M Aug 2026)"


def test_a_workbook_without_the_operating_header_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InfraInputError, match="Plant ID"):
        src.read_eia(_xlsx(tmp_path, [["Inventory of Operating Generators as of May 2026"]]), BOXES)


def test_a_workbook_with_a_doctype_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InfraInputError, match="DOCTYPE"):
        src.read_eia(_xlsx(tmp_path, EIA_ROWS, doctype=True), BOXES)


# --- WRI ---------------------------------------------------------------------------------

WRI_HEAD = (
    "country,country_long,name,gppd_idnr,capacity_mw,latitude,longitude,primary_fuel,"
    "other_fuel1,other_fuel2,other_fuel3,commissioning_year,owner,source"
)


def _wri(tmp_path: Path, rows: list[str]) -> Path:
    path = tmp_path / "global_power_plant_database.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("global_power_plant_database.csv", WRI_HEAD + "\n" + "\n".join(rows) + "\n")
        z.writestr("README.txt", "License: Creative Commons Attribution 4.0 International\n")
    return path


def test_wri_keeps_plants_outside_the_us_and_says_eia_covers_it(tmp_path: Path) -> None:
    boxes = [(-74.0, 44.5, -72.0, 46.0)]  # across the Vermont-Quebec border
    path = _wri(
        tmp_path,
        [
            "CAN,Canada,Testville Barrage,WRI1,20.0,45.2,-73.0,Hydro,,,,1960,Hydro Test,src",
            "USA,United States of America,Testville Dam,USA1,5.0,44.9,-73.0,Hydro,,,,1950,X,src",
            "CAN,Canada,Far Away,WRI2,5.0,50.0,-80.0,Wind,,,,2010,,src",
        ],
    )
    got = src.read_wri(path, boxes)
    assert [p.name for p in got.points] == ["Testville Barrage"]
    assert "20 MW" in got.points[0].details and "Hydro" in got.points[0].details
    assert got.outside == 1
    assert got.notes == (
        "1 plant in the US left out: EIA-860M covers the US (`--from-eia`), with this "
        "month's data where WRI's US rows are EIA's of 2019",
    )
    assert got.licence == "WRI Global Power Plant Database v1.3.0 (2021), CC BY 4.0"


# --- FCC ASR -----------------------------------------------------------------------------

CANARY = "CANARY-OWNER-CONTACT"


def _ra(reg: str, usi: str, status: str, dismantled: str = "", kind: str = "TOWER") -> str:
    fields = [""] * 49
    fields[:15] = [
        "RA",
        "REG",
        "A1",
        reg,
        usi,
        "NE",
        "",
        "I",
        status,
        "",
        "",
        "",
        "01/01/2000",
        dismantled,
        "",
    ]
    fields[17], fields[19], fields[21] = f"{CANARY}-FIRST", f"{CANARY}-LAST", "Specialist"
    fields[23], fields[24], fields[25] = f"1 {CANARY} ROAD", "TESTVILLE", "DE"
    fields[28:33] = ["60.0", "10.0", "61.5", "71.5", kind]
    return "|".join(fields)


def _co(usi: str, lat: tuple[int, int, float], lon: tuple[int, int, float], kind: str = "T") -> str:
    return "|".join(
        ["CO", "REG", "A1", "0", usi, kind, str(lat[0]), str(lat[1]), str(lat[2]), "N", "0",
         str(lon[0]), str(lon[1]), str(lon[2]), "W", "0", "", ""]
    )  # fmt: skip


def _asr(*, ra: list[str], co: list[str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("counts", "File Creation Date: Sun Sep 27 06:26:39 EDT 2026\n")
        z.writestr("RA.dat", "\r\n".join(ra) + "\r\n")
        z.writestr("CO.dat", "\r\n".join(co) + "\r\n")
        z.writestr("EN.dat", f"EN|REG|A1|1|1||{CANARY}|{CANARY}@example.com|555-0100\r\n")
    return out.getvalue()


ASR = _asr(
    ra=[
        _ra("1000001", "1", "C"),
        _ra("1000002", "2", "G", kind="MAST"),
        _ra("1000003", "3", "C", dismantled="01/01/2020"),
        _ra("1000004", "4", "T"),
        _ra("1000005", "5", "C"),
        _ra("1000006", "6", "C"),
    ],
    co=[
        _co("1", (38, 42, 0.0), (75, 30, 0.0)),
        _co("2", (38, 43, 0.0), (75, 31, 0.0)),
        _co("3", (38, 44, 0.0), (75, 32, 0.0)),
        _co("4", (38, 45, 0.0), (75, 33, 0.0)),
        _co("5", (44, 0, 0.0), (72, 30, 0.0)),
        _co("6", (38, 46, 0.0), (75, 34, 0.0), kind="A"),
    ],
)


def test_fcc_keeps_constructed_and_granted_structures_with_coordinates() -> None:
    got = src.parse_fcc_asr(ASR, "https://x/r_tower.zip", BOXES, fetched=WHEN, sha256="ab" * 32)
    assert [p.name for p in got.points] == ["ASR 1000001", "ASR 1000002"]
    first = got.points[0]
    assert (first.lat, first.lon) == pytest.approx((38.7, -75.5))
    assert "61.5 m above ground" in first.details and "71.5 m above sea level" in first.details
    assert "constructed" in first.details and got.points[1].kind == "mast"
    assert got.read == 6 and got.outside == 1
    assert got.skipped == {
        "dismantled": [3],
        "not constructed or granted": [4],
        "no structure coordinates": [6],
    }


def test_fcc_never_carries_owner_contacts() -> None:
    got = src.parse_fcc_asr(ASR, "https://x/r_tower.zip", BOXES, fetched=WHEN, sha256="ab" * 32)
    every = json.dumps([p.__dict__ for p in got.points]) + repr(got)
    assert CANARY not in every


def test_fcc_never_opens_en_dat(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    real = zipfile.ZipFile.open

    def spy(self: zipfile.ZipFile, name: str | zipfile.ZipInfo, *a: object, **k: object) -> object:
        opened.append(name if isinstance(name, str) else name.filename)
        return real(self, name, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(zipfile.ZipFile, "open", spy)
    src.parse_fcc_asr(ASR, "https://x/r_tower.zip", BOXES, fetched=WHEN, sha256="ab" * 32)
    assert "EN.dat" not in opened and set(opened) <= {"counts", "RA.dat", "CO.dat"}


def test_fcc_is_dated_by_its_own_file_and_licensed_exactly() -> None:
    got = src.parse_fcc_asr(ASR, "https://x/r_tower.zip", BOXES, fetched=WHEN, sha256="ab" * 32)
    assert got.day == date(2026, 9, 27)
    assert got.name == "FCC towers (unverified, 2026-09-27)"
    assert got.licence == "FCC Antenna Structure Registration, US Government work, public domain"
    assert any("sha256 " + "ab" * 32 in n and "not verifiable" in n for n in got.notes)


def test_fcc_that_is_not_the_archive_is_refused() -> None:
    with pytest.raises(InfraInputError, match=r"RA\.dat"):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("x", "y")
        src.parse_fcc_asr(out.getvalue(), "u", BOXES, fetched=WHEN, sha256="")
    with pytest.raises(InfraInputError, match="not a zip"):
        src.parse_fcc_asr(b"<html>", "u", BOXES, fetched=WHEN, sha256="")


# --- NOAA Weather Radio -------------------------------------------------------------------


def _station(call: str, lat: str, lon: str, status: str = "NORMAL") -> dict[str, object]:
    return {
        "siteloc": "Testville",
        "lat": lat,
        "callsign": call,
        "status": status,
        "counties": [
            {"state": "Delaware", "same": "010001", "st": "DE", "remarks": "", "county": "Kent"},
            {"state": "Delaware", "same": "010005", "st": "DE", "remarks": "", "county": "Sussex"},
        ],
        "sitestate": "DE",
        "sitename": "Testville",
        "freq": "162.475",
        "wfo": "Mount Holly|NJ",
        "power": "1000",
        "lon": lon,
    }


def _ccl(stations: list[dict[str, object]]) -> bytes:
    return ("var cclData = " + json.dumps(stations) + ";\n").encode()


NWR = _ccl(
    [
        _station("WXJ00", "38.7", "-75.5", status="OUT OF SERVICE"),
        _station("WXJ01", "40.9", "-75.5", status="DEGRADED"),  # 0.87 degree north of the box
        _station("WXJ02", "42.0", "-75.5"),
        _station("WXJ03", "", "-75.5"),
    ]
)


def test_nwr_keeps_frequency_power_and_same_codes_and_drops_status() -> None:
    got = src.parse_nwr(NWR, "https://x/ccl-data.js", BOXES, fetched=WHEN, sha256="cd" * 32)
    assert [p.name for p in got.points] == ["WXJ00 162.475", "WXJ01 162.475"]
    details = got.points[0].details
    assert "162.475 MHz" in details and "1000 W" in details
    assert "SAME 010001 Kent DE, 010005 Sussex DE" in details
    every = json.dumps([p.__dict__ for p in got.points]) + repr(got)
    for status in ("OUT OF SERVICE", "DEGRADED", "NORMAL"):
        assert status not in every
    assert got.outside == 1 and got.skipped == {src.NO_POSITION: [4]}


def test_nwr_ignores_brackets_after_the_ccl_data_array() -> None:
    clean = src.parse_nwr(NWR, "u", BOXES, fetched=WHEN, sha256="")
    trailing = src.parse_nwr(NWR + b"var x = [1, 2];", "u", BOXES, fetched=WHEN, sha256="")
    assert trailing.points == clean.points


def test_nwr_truncated_json_is_refused() -> None:
    with pytest.raises(InfraInputError, match="cclData array"):
        src.parse_nwr(b"var cclData = [{", "u", BOXES, fetched=WHEN, sha256="")


def test_nwr_is_dated_by_the_fetch_and_licensed_exactly() -> None:
    got = src.parse_nwr(NWR, "https://x/ccl-data.js", BOXES, fetched=WHEN, sha256="cd" * 32)
    assert got.name == "NOAA Weather Radio (unverified, fetched 2026-10-01)"
    assert got.licence == "NOAA/NWS, public domain, not an official NWS product"
    assert any("live status" in n for n in got.notes)


def test_nwr_that_is_not_the_list_is_refused() -> None:
    with pytest.raises(InfraInputError, match="cclData"):
        src.parse_nwr(b"<html>nope</html>", "u", BOXES, fetched=WHEN, sha256="")
