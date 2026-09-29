# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""QMapShack's per-user config: ours added, theirs kept, nothing else touched.  D-061."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hammunition.qmapshack_config import (
    QmsConfigError,
    Wanted,
    config_path,
    ensure_paths,
    superseded,
    wanted,
)

DATA = Path("/usr/local/share/hammunition/data")
GARMIN = f"{DATA}/osm-garmin"
CONTOURS = f"{DATA}/dem-qmapshack/contours"
DEM = f"{DATA}/dem-qmapshack/dem"
ROUTINO = f"{DATA}/osm-routino"


def test_the_keys_are_the_ones_qmapshack_keeps() -> None:
    """Measured on the bench, 2026-09-29: QMapShack 1.17.1 wrote ``mapPath``
    and ``demPaths`` back under ``[Canvas]`` and ignored them under
    ``[General]``; ``routino\\paths`` under ``[Route]`` it kept (D-061)."""
    assert wanted(DATA) == (
        Wanted("Canvas", "mapPath", (GARMIN, CONTOURS)),
        Wanted("Canvas", "demPaths", (DEM,)),
        Wanted("Route", "routino\\paths", (ROUTINO,)),
    )
    assert superseded(DATA) == (
        Wanted("General", "mapPath", (GARMIN, CONTOURS)),
        Wanted("General", "demPaths", (DEM,)),
    )


def test_an_empty_config_gains_every_key() -> None:
    assert ensure_paths("", wanted(DATA)) == (
        "[Canvas]\n"
        f"mapPath={GARMIN}, {CONTOURS}\n"
        f"demPaths={DEM}\n"
        "\n"
        "[Route]\n"
        f"routino\\paths={ROUTINO}\n"
    )


def test_existing_values_are_kept_in_place_and_ours_appended() -> None:
    text = (
        "[Canvas]\n"
        "mapPath=/home/op/maps\n"
        "demPaths=\n"
        "\n"
        "[Units]\n"
        "type=metric\n"
        "\n"
        "[Route]\n"
        "routino\\paths=/home/op/routino, /srv/routino\n"
        "routino\\profile=3\n"
    )
    assert ensure_paths(text, wanted(DATA)) == (
        "[Canvas]\n"
        f"mapPath=/home/op/maps, {GARMIN}, {CONTOURS}\n"
        f"demPaths={DEM}\n"
        "\n"
        "[Units]\n"
        "type=metric\n"
        "\n"
        "[Route]\n"
        f"routino\\paths=/home/op/routino, /srv/routino, {ROUTINO}\n"
        "routino\\profile=3\n"
    )


def test_a_config_already_naming_our_paths_is_returned_byte_for_byte() -> None:
    text = (
        "; kept\r\n"
        "[Canvas]\r\n"
        f"mapPath={CONTOURS}, /x, {GARMIN}\r\n"
        f"demPaths={DEM}\r\n"
        "[Route]\r\n"
        f"routino\\paths={ROUTINO}"
    )
    assert ensure_paths(text, wanted(DATA)) == text


def test_a_missing_key_goes_at_the_end_of_its_existing_section() -> None:
    text = "[General]\nmapPath=/m\n\n[Units]\ntype=metric\n"
    got = ensure_paths(text, [Wanted("General", "demPaths", (DEM,))])
    assert got == f"[General]\nmapPath=/m\ndemPaths={DEM}\n\n[Units]\ntype=metric\n"


def test_a_file_without_a_final_newline_gains_one_only_when_something_is_added() -> None:
    assert ensure_paths("[Units]\ntype=metric", [Wanted("Units", "type", ())]) == (
        "[Units]\ntype=metric"
    )
    assert ensure_paths("[Units]\ntype=metric", [Wanted("General", "demPaths", (DEM,))]) == (
        f"[Units]\ntype=metric\n\n[General]\ndemPaths={DEM}\n"
    )


@pytest.mark.parametrize(
    "text",
    [
        "[General]\nthis is not a setting\n",
        '[Canvas]\nmapPath="/a, b"\n',
        "[Canvas]\ndemPaths=@Variant(\\0\\0\\0\\x7f)\n",
        "[Canvas]\nmapPath=@ByteArray(/a)\n",
        "[Canvas]\nmapPath=@Invalid\n",
    ],
)
def test_a_config_it_cannot_read_is_refused_by_name(text: str) -> None:
    with pytest.raises(QmsConfigError):
        ensure_paths(text, wanted(DATA))


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("[Canvas]\ndemPaths=@Variant(\\0\\0\\0\\x7f)\n", "demPaths"),
        (
            "[Route]\nroutino\\paths=@ByteArray(/a)\n",
            "routino\\paths",
        ),
    ],
)
def test_a_typed_value_is_refused_naming_its_key(text: str, key: str) -> None:
    with pytest.raises(QmsConfigError, match=re.escape(key)):
        ensure_paths(text, wanted(DATA))


#: What Qt itself writes for three empty QStringLists and one int: PyQt6's
#: QSettings(IniFormat), setValue(..., []), measured 2026-09-28. Qt's
#: iniEscapedStringList writes an empty list as @Invalid() on purpose.
QT_WROTE_EMPTY_LISTS = (
    "[Canvas]\n"
    "demPaths=@Invalid()\n"
    "mapPath=@Invalid()\n"
    "\n"
    "[Route]\n"
    "routino\\paths=@Invalid()\n"
    "\n"
    "[Units]\n"
    "type=1\n"
)


def test_qts_empty_list_is_an_empty_list_and_gains_our_paths() -> None:
    """A QMapShack run once with no maps has exactly this file (D-061)."""
    assert ensure_paths(QT_WROTE_EMPTY_LISTS, wanted(DATA)) == (
        "[Canvas]\n"
        f"demPaths={DEM}\n"
        f"mapPath={GARMIN}, {CONTOURS}\n"
        "\n"
        "[Route]\n"
        f"routino\\paths={ROUTINO}\n"
        "\n"
        "[Units]\n"
        "type=1\n"
    )


def test_an_invalid_marker_with_nothing_of_ours_to_add_is_left_as_qt_wrote_it() -> None:
    text = "[Canvas]\nmapPath=@Invalid()\n"
    assert ensure_paths(text, [Wanted("Canvas", "mapPath", ())]) == text


def test_a_path_that_cannot_be_a_list_entry_is_refused() -> None:
    with pytest.raises(QmsConfigError):
        ensure_paths("", [Wanted("General", "mapPath", ("/a,b",))])


def test_the_config_follows_xdg_config_home(tmp_path: Path) -> None:
    assert config_path({"XDG_CONFIG_HOME": str(tmp_path)}) == (
        tmp_path / "QLandkarte" / "QMapShack.conf"
    )
    assert config_path({}, home=tmp_path) == tmp_path / ".config" / "QLandkarte" / "QMapShack.conf"


#: What an earlier launcher left, and QMapShack 1.17.1 then wrote around it
#: on exit (bench, 2026-09-29): ours ignored under [General], its own empty
#: lists under [Canvas].
EARLIER_RUN = (
    "[General]\n"
    f"mapPath={GARMIN}, {CONTOURS}\n"
    f"demPaths={DEM}\n"
    "\n"
    "[Canvas]\n"
    "mapPath=@Invalid()\n"
    "demPaths=@Invalid()\n"
    "\n"
    "[Route]\n"
    f"routino\\paths={ROUTINO}\n"
)


def test_an_earlier_runs_general_keys_move_to_canvas() -> None:
    assert ensure_paths(EARLIER_RUN, wanted(DATA), remove=superseded(DATA)) == (
        "[General]\n"
        "\n"
        "[Canvas]\n"
        f"mapPath={GARMIN}, {CONTOURS}\n"
        f"demPaths={DEM}\n"
        "\n"
        "[Route]\n"
        f"routino\\paths={ROUTINO}\n"
    )


def test_only_our_values_leave_general_and_every_other_key_stays() -> None:
    text = (
        "[General]\n"
        "firstRun=false\n"
        f"mapPath=/home/op/maps, {GARMIN}, {CONTOURS}\n"
        f"demPaths={DEM}\r\n"
        "language=en\n"
    )
    assert ensure_paths(text, (), remove=superseded(DATA)) == (
        "[General]\nfirstRun=false\nmapPath=/home/op/maps\nlanguage=en\n"
    )


@pytest.mark.parametrize(
    "text",
    [
        "[General]\nmapPath=/home/op/maps\ndemPaths=@Invalid()\n",
        "[General]\nmapPath=@Variant(\\0)\n",
        f"[Units]\nmapPath={GARMIN}\n",
    ],
)
def test_a_general_key_holding_nothing_of_ours_is_left_as_it_is(text: str) -> None:
    """Not ours, or not a shape we wrote: never refused, never rewritten."""
    assert ensure_paths(text, (), remove=superseded(DATA)) == text
