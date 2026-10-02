# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A synthetic ACMA register, in the shape of the 2026-10-01 file.

The column names and their order are the real file's (``DOC/cr_tables_oracle.sql``
and the CSV headers, measured 2026-10-01); every row is invented. Callsigns
are VK7RZZ-style placeholders, sites are public Tasmanian and Victorian
hilltops, and ``client.csv`` holds one invented natural person whose name
and street must never reach any output.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

LICENCE_HEADER = (
    "LICENCE_NO,CLIENT_NO,SV_ID,SS_ID,LICENCE_TYPE_NAME,LICENCE_CATEGORY_NAME,DATE_ISSUED,"
    "DATE_OF_EFFECT,DATE_OF_EXPIRY,STATUS,STATUS_TEXT,AP_ID,AP_PRJ_IDENT,SHIP_NAME,BSL_NO,AWL_TYPE"
)
DEVICE_HEADER = (
    "SDD_ID,LICENCE_NO,DEVICE_REGISTRATION_IDENTIFIER,FORMER_DEVICE_IDENTIFIER,"
    "AUTHORISATION_DATE,CERTIFICATION_METHOD,GROUP_FLAG,SITE_RADIUS,FREQUENCY,BANDWIDTH,"
    "CARRIER_FREQ,EMISSION,DEVICE_TYPE,TRANSMITTER_POWER,TRANSMITTER_POWER_UNIT,SITE_ID,"
    "ANTENNA_ID,POLARISATION,AZIMUTH,HEIGHT,TILT,FEEDER_LOSS,LEVEL_OF_PROTECTION,EIRP,EIRP_UNIT,"
    "SV_ID,SS_ID,EFL_ID,EFL_FREQ_IDENT,EFL_SYSTEM,LEQD_MODE,RECEIVER_THRESHOLD,AREA_AREA_ID,"
    "CALL_SIGN,AREA_DESCRIPTION,AP_ID,CLASS_OF_STATION_CODE,SUPPLIMENTAL_FLAG,EQ_FREQ_RANGE_MIN,"
    "EQ_FREQ_RANGE_MAX,NATURE_OF_SERVICE_ID,HOURS_OF_OPERATION,SA_ID,RELATED_EFL_ID,EQP_ID,"
    "ANTENNA_MULTI_MODE,POWER_IND,LPON_CENTER_LONGITUDE,LPON_CENTER_LATITUDE,TCS_ID,"
    "TECH_SPEC_ID,DROPTHROUGH_ID,STATION_TYPE,STATION_NAME"
)
SITE_HEADER = (
    "SITE_ID,LATITUDE,LONGITUDE,NAME,STATE,LICENSING_AREA_ID,POSTCODE,SITE_PRECISION,"
    "ELEVATION,HCIS_L2"
)
CLIENT_HEADER = (
    "CLIENT_NO,LICENCEE,TRADING_NAME,ACN,ABN,POSTAL_STREET,POSTAL_SUBURB,POSTAL_STATE,"
    "POSTAL_POSTCODE,CAT_ID,CLIENT_TYPE_ID,FEE_STATUS_ID"
)
#: The invented licensee, who must appear in no output.
CLIENT_NAME = "Jane Examplesmith"
CLIENT_STREET = "1 Imaginary Lane"
#: A Tasmanian region's box (left, right, top, bottom), roughly Geofabrik's.
TASMANIA = (143.5, 148.6, -39.2, -43.9)
#: The Mount Wellington site, inside TASMANIA.
HOBART_LAT, HOBART_LON = "-42.896000", "147.237000"
LICENCE_TEXT = (
    "LICENCE TO USE THE REGISTER OF RADIOCOMMUNICATIONS LICENCES\n"
    '9. ... "Based on Australian Communications and Media Authority information".\n'
)


def _licence(no: str, ss: str, status: str, text: str) -> str:
    return f"{no},9001,6,{ss},Amateur,Amateur Repeater,2020-01-01,2020-01-01,2030-01-01,{status},{text},1,,,,"


def _device(
    sdd: int, licence: str, hz: int, emission: str, kind: str, site: str, efl: str, call: str
) -> str:
    cells = [""] * DEVICE_HEADER.count(",")
    cells.append("")
    names = DEVICE_HEADER.split(",")
    for name, value in (
        ("SDD_ID", str(sdd)),
        ("LICENCE_NO", licence),
        ("FREQUENCY", str(hz)),
        ("EMISSION", emission),
        ("DEVICE_TYPE", kind),
        ("SITE_ID", site),
        ("SS_ID", "602"),
        ("EFL_SYSTEM", efl),
        ("CALL_SIGN", call),
    ):
        cells[names.index(name)] = value
    return ",".join(cells)


def register_members() -> dict[str, str]:
    """Every member's text, keyed by name."""
    licences = [
        LICENCE_HEADER,
        _licence("900001/1", "602", "1", "Granted"),
        _licence("900002/1", "602", "1", "Granted"),
        _licence("900003/1", "602", "10", "Expired"),
        _licence("900004/1", "305", "1", "Granted"),
    ]
    devices = [
        DEVICE_HEADER,
        # A 2 m pair on Mount Wellington: output 146.700, input 146.100.
        _device(1, "900001/1", 146_700_000, "16K0F3E  ", "T", "5001", "70", "VK7RZZ"),
        _device(2, "900001/1", 146_100_000, "16K0F3E  ", "R", "5001", "70", "VK7RZZ"),
        # A 70 cm pair at the same site, composite emission.
        _device(3, "900001/1", 438_525_000, "16K0F9W", "T", "5001", "71", "VK7RZZ"),
        _device(4, "900001/1", 433_525_000, "16K0F9W", "R", "5001", "71", "VK7RZZ"),
        # The same transmitter listed twice: D-064's merge keeps one.
        _device(5, "900001/1", 146_700_000, "16K0F3E", "T", "5001", "72", "VK7RZZ"),
        # A transmitter with no site.
        _device(6, "900001/1", 147_000_000, "16K0F3E", "T", "", "73", "VK7RZZ"),
        # 24 GHz: outside 1 to 10,000 MHz.
        _device(7, "900001/1", 24_048_000_000, "10M0F3F", "T", "5001", "74", "VK7RZZ"),
        # Victoria: outside the Tasmanian box.
        _device(8, "900002/1", 147_250_000, "16K0F3E", "T", "5002", "80", "VK3RZZ"),
        # An expired licence at the Tasmanian site.
        _device(9, "900003/1", 146_950_000, "16K0F3E", "T", "5001", "90", "VK7RZY"),
        # Land mobile, not amateur: never read.
        _device(10, "900004/1", 160_000_000, "16K0F3E", "T", "5001", "95", "VK7XXX"),
    ]
    sites = [
        SITE_HEADER,
        f"5001,{HOBART_LAT},{HOBART_LON},Mount Wellington summit HOBART,TAS,7,7000,"
        f"Within 10 metres,,AB1C",
        "5002,-37.833000,145.350000,Mount Dandenong KALORAMA,VIC,3,3767,Unknown,,AB2C",
        "5003,-12.471947,130.845073,Not a repeater site DARWIN,NT,4,0800,Unknown,,AB3C",
    ]
    clients = [
        CLIENT_HEADER,
        f'9001,{CLIENT_NAME},,,,"{CLIENT_STREET}",HOBART,TAS,7000,1,7,1',
    ]
    return {
        "licence.csv": "\n".join(licences) + "\n",
        "device_details.csv": "\n".join(devices) + "\n",
        "site.csv": "\n".join(sites) + "\n",
        "client.csv": "\n".join(clients) + "\n",
        "licence_subservice.csv": "SS_ID,SV_SV_ID,SS_NAME\n602,6,Amateur Repeater\n",
        "LICENCE.TXT": LICENCE_TEXT,
        "README.TXT": "LICENCE FOR USE\n",
    }


def write_register(
    path: Path,
    *,
    members: dict[str, str] | None = None,
    when: tuple[int, int, int, int, int, int] = (2026, 10, 2, 7, 31, 0),
) -> Path:
    """The synthetic register, zipped, every member dated *when*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in (members if members is not None else register_members()).items():
            archive.writestr(zipfile.ZipInfo(name, date_time=when), text)
    return path


def register_bytes(tmp_path: Path, **kwargs: object) -> bytes:
    return write_register(tmp_path / "built" / "spectra_rrl.zip", **kwargs).read_bytes()  # type: ignore[arg-type]
