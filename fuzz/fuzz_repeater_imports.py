# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atheris target: every reader behind ``hammunition maps repeaters import``.

The first byte picks a reader: the operator's own export read by content
(RepeaterBook GPX and CSV, hearham JSON, the hand CSV), a saved ``.rows.json``
layer, and the on-request lists (Open Repeater, ETCC, Brandmeister, OpenStreetMap
XML, a Direwolf log). Input goes to a temp file where the reader takes a path.
``RepeaterInputError`` is the documented refusal; ``read_layer_rows`` documents
``ValueError``. Anything else is a bug.
"""

import sys
import tempfile
from pathlib import Path

import atheris
from _seeded import seed_text, text_from

with atheris.instrument_imports():
    from hammunition import repeater_sources, repeaters
    from hammunition.repeaters import RepeaterInputError

_FIXTURES = ("tests", "fixtures", "repeaters")


def _seed(name: str) -> str:
    return seed_text(*_FIXTURES, name)


# (reader, seed file, suffix the temp file gets)
_READERS = (
    ("input", "export.gpx", ".gpx"),
    ("input", "rb.csv", ".csv"),
    ("input", "hearham.json", ".json"),
    ("input", "hand.csv", ".csv"),
    ("layer", "", ".json"),
    ("open_repeater", "open-repeater.json", ".json"),
    ("etcc", "etcc.csv", ".csv"),
    ("brandmeister", "brandmeister.json", ".json"),
    ("osm", "osm-repeaters.osm", ".osm"),
    ("direwolf", "direwolf-2026-10-01.csv", ".csv"),
)
_SEEDS = tuple(_seed(name) if name else "" for _, name, _ in _READERS)
_TMP = Path(tempfile.mkdtemp(prefix="fuzz-repeaters-"))


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    index = fdp.ConsumeIntInRange(0, len(_READERS) - 1)
    reader, _, suffix = _READERS[index]
    body = (
        fdp.ConsumeBytes(4096)
        if fdp.ConsumeBool()
        else text_from(fdp, _SEEDS[index]).encode("utf-8")
    )
    path = _TMP / f"in{suffix}"
    path.write_bytes(body)
    try:
        if reader == "input":
            repeaters.read_input(path)
        elif reader == "layer":
            repeaters.read_layer_rows(path)
        elif reader == "open_repeater":
            repeater_sources.read_open_repeater(path)
        elif reader == "etcc":
            repeater_sources.parse_etcc(body, "https://example.invalid/etcc")
        elif reader == "brandmeister":
            repeater_sources.parse_brandmeister(body, "https://example.invalid/bm")
        elif reader == "osm":
            repeater_sources.read_osm_xml(body.decode("utf-8", errors="replace"), path)
        else:
            repeater_sources.read_direwolf_logs([path])
    except RepeaterInputError:
        pass
    except ValueError:
        if reader != "layer":
            raise


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
