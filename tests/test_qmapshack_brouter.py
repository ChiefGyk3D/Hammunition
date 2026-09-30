# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""QMapShack's local BRouter, pointed at Hammunition's.  D-063.

The keys are ``Route/brouter/*`` from QMapShack 1.17.1's
``CRouterBRouterSetup.cpp``; the file shapes are what its ``save()`` writes.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import NoReturn

import pytest

from hammunition.qmapshack_config import BRouterSetup, register_brouter

cli = importlib.import_module("hammunition.cli.main")

TREE = Path("/usr/local/share/hammunition/brouter")
SEGMENTS = Path("/usr/local/share/hammunition/data/brouter-segments")
SETUP = BRouterSetup(
    tree=TREE, jar="brouter-1.7.10-all.jar", segments=SEGMENTS, java="/usr/bin/java"
)
OURS = (
    "brouter\\installMode=local\n"
    f"brouter\\localDir={TREE}\n"
    "brouter\\localBRouterJar=brouter-1.7.10-all.jar\n"
    f"brouter\\localSegmentsDir={SEGMENTS}\n"
    "brouter\\localHost=127.0.0.1\n"
    "brouter\\localBindLocalonly=true\n"
)

#: What QMapShack 1.17.1 saves on exit when BRouter was never set up (its
#: defaults), with java not yet installed: localJava is saved empty.
SAVED_DEFAULTS = (
    "[Route]\n"
    "current=0\n"
    "brouter\\expertMode=false\n"
    "brouter\\installMode=online\n"
    "brouter\\localDir=.\n"
    "brouter\\localBRouterJar=brouter.jar\n"
    "brouter\\localJava=\n"
    "brouter\\localProfileDir=profiles2\n"
    "brouter\\localSegmentsDir=segments4\n"
    "brouter\\localHost=127.0.0.1\n"
    "brouter\\localPort=17777\n"
    "brouter\\localBindLocalonly=true\n"
    "brouter\\localJavaOpts=-Xmx128M -Xms128M -Xmn8M\n"
    "routino\\database=0\n"
)


def test_a_file_with_no_route_section_gets_every_key() -> None:
    text, notes = register_brouter("[Units]\ntype=metric\n", SETUP)
    assert text == (
        "[Units]\ntype=metric\n\n[Route]\n" + OURS + "brouter\\localJava=/usr/bin/java\n"
    )
    assert "pick BRouter in the Routing dock" in notes[0]


def test_qmapshack_s_saved_defaults_are_replaced_in_place_and_the_rest_kept() -> None:
    text, notes = register_brouter(SAVED_DEFAULTS, SETUP)
    assert text.splitlines() == [
        "[Route]",
        "current=0",
        "brouter\\expertMode=false",
        "brouter\\installMode=local",
        f"brouter\\localDir={TREE}",
        "brouter\\localBRouterJar=brouter-1.7.10-all.jar",
        "brouter\\localJava=/usr/bin/java",
        "brouter\\localProfileDir=profiles2",
        f"brouter\\localSegmentsDir={SEGMENTS}",
        "brouter\\localHost=127.0.0.1",
        "brouter\\localPort=17777",
        "brouter\\localBindLocalonly=true",
        "brouter\\localJavaOpts=-Xmx128M -Xms128M -Xmn8M",
        "routino\\database=0",
    ]
    assert "switched from online to local" in "\n".join(notes)


def test_registering_twice_changes_nothing() -> None:
    once, _ = register_brouter(SAVED_DEFAULTS, SETUP)
    twice, notes = register_brouter(once, SETUP)
    assert twice == once and notes == []


def test_the_operator_s_own_brouter_is_left_alone() -> None:
    theirs = SAVED_DEFAULTS.replace("brouter\\localDir=.", "brouter\\localDir=/home/op/brouter")
    text, notes = register_brouter(theirs, SETUP)
    assert text == theirs
    assert "/home/op/brouter" in notes[0] and "left as it is" in notes[0]


def test_an_empty_directory_is_read_as_never_set() -> None:
    empty = SAVED_DEFAULTS.replace("brouter\\localDir=.", "brouter\\localDir=")
    text, notes = register_brouter(empty, SETUP)
    assert f"brouter\\localDir={TREE}\n" in text
    assert "pick BRouter in the Routing dock" in notes[0]


def test_our_tree_is_always_bound_to_loopback() -> None:
    open_to_all = SAVED_DEFAULTS.replace(
        "brouter\\localBindLocalonly=true", "brouter\\localBindLocalonly=false"
    ).replace("brouter\\localHost=127.0.0.1", "brouter\\localHost=0.0.0.0")
    text, notes = register_brouter(open_to_all, SETUP)
    assert "brouter\\localBindLocalonly=true\n" in text
    assert "brouter\\localHost=127.0.0.1\n" in text and "0.0.0.0" not in text
    assert "bound to 127.0.0.1 only" in "\n".join(notes)


def test_a_java_already_named_is_kept_and_none_found_is_said() -> None:
    named = SAVED_DEFAULTS.replace("brouter\\localJava=", "brouter\\localJava=/opt/jdk/bin/java")
    text, _ = register_brouter(named, SETUP)
    assert "brouter\\localJava=/opt/jdk/bin/java\n" in text
    no_java = BRouterSetup(tree=TREE, jar=SETUP.jar, segments=SEGMENTS, java=None)
    text, notes = register_brouter(SAVED_DEFAULTS, no_java)
    assert "brouter\\localJava=\n" in text
    assert "java was not found" in "\n".join(notes)


def test_a_value_it_cannot_read_leaves_brouter_alone_without_refusing() -> None:
    odd = SAVED_DEFAULTS.replace("brouter\\localDir=.", 'brouter\\localDir="/a, b"')
    text, notes = register_brouter(odd, SETUP)
    assert text == odd and "does not edit" in notes[0]


def test_which_router_the_dock_shows_is_the_operator_s() -> None:
    text, _ = register_brouter(SAVED_DEFAULTS, SETUP)
    assert "current=0\n" in text


# ---------------------------------------------------------------------------
# Through the launcher
# ---------------------------------------------------------------------------


class Exec(Exception):
    pass


def _launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, installed: bool) -> Path:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    prefix = tmp_path / "prefix"
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", prefix)
    if installed:
        tree = prefix / "share" / "hammunition" / "brouter"
        tree.mkdir(parents=True)
        (tree / "brouter-1.7.10-all.jar").write_bytes(b"jar")
        segments = prefix / "share" / "hammunition" / "data" / "brouter-segments"
        segments.mkdir(parents=True)
        (segments / "W80_N35.rd5").write_bytes(b"rd5")

    def execvp(file: str, argv: list[str]) -> NoReturn:
        raise Exec

    monkeypatch.setattr(os, "execvp", execvp)
    return tmp_path / "config" / "QLandkarte" / "QMapShack.conf"


def test_the_launcher_registers_brouter_when_it_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conf = _launch(tmp_path, monkeypatch, installed=True)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    text = conf.read_text()
    tree = tmp_path / "prefix" / "share" / "hammunition" / "brouter"
    assert f"brouter\\localDir={tree}\n" in text
    assert "brouter\\installMode=local\n" in text
    assert "registering Hammunition's BRouter" in capsys.readouterr().err


def test_the_launcher_leaves_brouter_alone_when_it_is_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = _launch(tmp_path, monkeypatch, installed=False)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    assert "brouter\\" not in conf.read_text()
