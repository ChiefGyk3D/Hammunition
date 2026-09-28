# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which desktops a machine has, read from the session files a display
manager lists. D-060.

The fixtures reproduce the shape of the files as measured on 2026-09-28 from
the Debian 13 packages and from the field laptop: most carry ``DesktopNames``,
LXDE's and Cinnamon's carry none, and some files in the same directories
(``lightdm-xsession``, ``openbox``) are not a desktop at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.desktop import Desktop, current_desktop, describe, installed_desktops

X = "usr/share/xsessions"
WAYLAND = "usr/share/wayland-sessions"


def _session(root: Path, directory: str, filename: str, body: str) -> None:
    path = root / directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _entry(name: str, exec_: str, desktop_names: str | None = None) -> str:
    lines = ["[Desktop Entry]", "Type=XSession", f"Name={name}", f"Exec={exec_}"]
    if desktop_names is not None:
        lines.append(f"DesktopNames={desktop_names}")
    return "\n".join(lines) + "\n"


def test_no_session_directories_is_an_empty_set_not_an_error(tmp_path: Path) -> None:
    """A container or a server has neither directory."""
    assert installed_desktops(tmp_path) == frozenset()


def test_one_directory_present_and_the_other_absent(tmp_path: Path) -> None:
    _session(tmp_path, X, "xfce.desktop", _entry("Xfce Session", "startxfce4", "XFCE"))
    assert installed_desktops(tmp_path) == {Desktop.xfce}


def test_plasma_from_the_field_laptop_shape(tmp_path: Path) -> None:
    _session(
        tmp_path,
        WAYLAND,
        "plasma.desktop",
        _entry("Plasma (Wayland)", "startplasma-wayland", "KDE"),
    )
    _session(tmp_path, X, "plasmax11.desktop", _entry("Plasma (X11)", "startplasma-x11", "KDE"))
    assert installed_desktops(tmp_path) == {Desktop.kde}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("KDE", Desktop.kde),
        ("GNOME", Desktop.gnome),
        ("XFCE", Desktop.xfce),
        ("LXQt", Desktop.lxqt),
        ("LXDE", Desktop.lxde),
        ("MATE", Desktop.mate),
        ("X-Cinnamon", Desktop.cinnamon),
        ("Cinnamon", Desktop.cinnamon),
        ("xfce", Desktop.xfce),
    ],
)
def test_desktop_names_map_case_insensitively(
    tmp_path: Path, value: str, expected: Desktop
) -> None:
    _session(tmp_path, X, "some.desktop", _entry("Some", "start", value))
    assert installed_desktops(tmp_path) == {expected}


def test_desktop_names_is_semicolon_separated(tmp_path: Path) -> None:
    """``GNOME;GNOME-Classic``: any recognised element counts, the rest is ignored."""
    _session(
        tmp_path,
        X,
        "gnome-classic.desktop",
        _entry("Classic", "gnome-session", "GNOME;GNOME-Classic;"),
    )
    assert installed_desktops(tmp_path) == {Desktop.gnome}


def test_a_file_without_desktop_names_falls_back_to_its_measured_stem(tmp_path: Path) -> None:
    """The two measured gaps: openbox-lxde-session and cinnamon-common."""
    _session(tmp_path, X, "LXDE.desktop", _entry("LXDE", "/usr/bin/startlxde"))
    _session(tmp_path, X, "cinnamon.desktop", _entry("Cinnamon", "cinnamon-session-cinnamon"))
    assert installed_desktops(tmp_path) == {Desktop.lxde, Desktop.cinnamon}


@pytest.mark.parametrize("stem", ["cinnamon2d", "cinnamon-wayland"])
def test_every_measured_cinnamon_stem(tmp_path: Path, stem: str) -> None:
    directory = WAYLAND if "wayland" in stem else X
    _session(tmp_path, directory, f"{stem}.desktop", _entry("Cinnamon", "cinnamon-session"))
    assert installed_desktops(tmp_path) == {Desktop.cinnamon}


@pytest.mark.parametrize("stem", ["lightdm-xsession", "openbox", "lxde", "LXQt"])
def test_an_unrelated_file_without_desktop_names_is_ignored(tmp_path: Path, stem: str) -> None:
    """The fallback holds exactly the measured stems. ``lxde`` in lower case is
    not what openbox-lxde-session ships, and guessing wider is how a machine
    gets told it has a desktop it does not."""
    _session(tmp_path, X, f"{stem}.desktop", _entry("Something", "something"))
    assert installed_desktops(tmp_path) == frozenset()


def test_an_unrecognised_desktop_name_is_ignored(tmp_path: Path) -> None:
    _session(
        tmp_path, X, "enlightenment.desktop", _entry("E", "enlightenment_start", "Enlightenment")
    )
    assert installed_desktops(tmp_path) == frozenset()


def test_desktop_names_in_another_group_does_not_count(tmp_path: Path) -> None:
    body = "[Desktop Entry]\nName=Odd\nExec=odd\n\n[Desktop Action other]\nDesktopNames=KDE\n"
    _session(tmp_path, X, "odd.desktop", body)
    assert installed_desktops(tmp_path) == frozenset()


def test_desktop_names_wins_over_the_stem(tmp_path: Path) -> None:
    _session(tmp_path, X, "cinnamon.desktop", _entry("Not really", "x", "XFCE"))
    assert installed_desktops(tmp_path) == {Desktop.xfce}


def test_only_desktop_files_are_read(tmp_path: Path) -> None:
    _session(tmp_path, X, "xfce.desktop.dpkg-old", _entry("Xfce", "startxfce4", "XFCE"))
    assert installed_desktops(tmp_path) == frozenset()


def test_several_desktops_on_one_machine(tmp_path: Path) -> None:
    _session(tmp_path, WAYLAND, "plasma.desktop", _entry("Plasma", "startplasma-wayland", "KDE"))
    _session(tmp_path, X, "xfce.desktop", _entry("Xfce", "startxfce4", "XFCE"))
    _session(tmp_path, X, "lxqt.desktop", _entry("LXQt", "startlxqt", "LXQt"))
    assert installed_desktops(tmp_path) == {Desktop.kde, Desktop.xfce, Desktop.lxqt}


# ---------------------------------------------------------------------------
# The session the caller is in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("KDE", Desktop.kde),
        ("ubuntu:GNOME", Desktop.gnome),
        ("XFCE", Desktop.xfce),
        ("LXQt", Desktop.lxqt),
        ("X-Cinnamon", Desktop.cinnamon),
        ("Unity:Unity7:ubuntu", None),
        ("", None),
    ],
)
def test_current_desktop_reads_the_colon_separated_variable(
    value: str, expected: Desktop | None
) -> None:
    assert current_desktop({"XDG_CURRENT_DESKTOP": value}) is expected


def test_current_desktop_unset_is_none() -> None:
    """Under sudo the variable is usually gone, which is why the planner never reads it."""
    assert current_desktop({}) is None


def test_describe_names_each_desktop_the_way_people_do() -> None:
    assert describe(Desktop.kde) == "KDE Plasma"
    assert describe(Desktop.xfce) == "Xfce"
    assert describe(Desktop.lxqt) == "LXQt"
    assert {describe(d) for d in Desktop} == {
        "KDE Plasma",
        "GNOME",
        "Xfce",
        "LXQt",
        "LXDE",
        "MATE",
        "Cinnamon",
    }


# ---------------------------------------------------------------------------
# What was seen but not recognised, and files that are not what they seem
# ---------------------------------------------------------------------------


def test_a_session_the_catalog_does_not_name_is_reported_as_seen(tmp_path: Path) -> None:
    """A graphical machine whose only desktop the catalog does not name is not
    a server. ASSUMPTION, not measured: COSMIC's session file is taken to be
    `cosmic.desktop` with `DesktopNames=COSMIC`; nobody has read Pop!_OS's."""
    from hammunition.desktop import scan_sessions

    _session(tmp_path, WAYLAND, "cosmic.desktop", _entry("COSMIC", "start-cosmic", "COSMIC"))
    scan = scan_sessions(tmp_path)
    assert scan.desktops == frozenset()
    assert scan.unrecognised == ("cosmic.desktop",)
    assert installed_desktops(tmp_path) == frozenset()


def test_recognised_files_are_not_listed_as_unrecognised(tmp_path: Path) -> None:
    from hammunition.desktop import scan_sessions

    _session(tmp_path, X, "xfce.desktop", _entry("Xfce", "startxfce4", "XFCE"))
    _session(tmp_path, WAYLAND, "sway.desktop", _entry("Sway", "sway", "sway"))
    scan = scan_sessions(tmp_path)
    assert scan.desktops == {Desktop.xfce}
    assert scan.unrecognised == ("sway.desktop",)


def test_no_session_files_at_all_is_distinguishable(tmp_path: Path) -> None:
    from hammunition.desktop import scan_sessions

    scan = scan_sessions(tmp_path)
    assert scan.desktops == frozenset() and scan.unrecognised == ()
    assert not scan.any_files


def test_usr_local_session_directories_are_read(tmp_path: Path) -> None:
    """SDDM and LightDM both search /usr/local/share for sessions."""
    _session(tmp_path, "usr/local/share/xsessions", "xfce.desktop", _entry("X", "x", "XFCE"))
    _session(tmp_path, "usr/local/share/wayland-sessions", "lxqt.desktop", _entry("L", "l", "LXQt"))
    assert installed_desktops(tmp_path) == {Desktop.xfce, Desktop.lxqt}


def test_a_leading_byte_order_mark_is_stripped(tmp_path: Path) -> None:
    path = tmp_path / X / "xfce.desktop"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xef\xbb\xbf" + _entry("Xfce", "startxfce4", "XFCE").encode())
    assert installed_desktops(tmp_path) == {Desktop.xfce}


def _within_seconds(seconds: int, root: Path) -> frozenset[Desktop]:
    """Reading a FIFO blocks forever. An alarm turns that hang into a failure."""
    import signal

    def _timeout(signum: int, frame: object) -> None:
        raise AssertionError("installed_desktops blocked: it opened something that is not a file")

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(seconds)
    try:
        return installed_desktops(root)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def test_a_fifo_named_like_a_session_is_not_read(tmp_path: Path) -> None:
    import os

    (tmp_path / X).mkdir(parents=True)
    os.mkfifo(tmp_path / X / "plasma.desktop")
    assert _within_seconds(3, tmp_path) == frozenset()


def test_a_symlink_to_a_fifo_is_not_read(tmp_path: Path) -> None:
    import os

    (tmp_path / X).mkdir(parents=True)
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / X / "plasma.desktop").symlink_to(tmp_path / "pipe")
    assert _within_seconds(3, tmp_path) == frozenset()


def test_a_symlink_to_a_real_session_file_is_read(tmp_path: Path) -> None:
    (tmp_path / X).mkdir(parents=True)
    (tmp_path / "real").write_text(_entry("Xfce", "startxfce4", "XFCE"))
    (tmp_path / X / "xfce.desktop").symlink_to(tmp_path / "real")
    assert installed_desktops(tmp_path) == {Desktop.xfce}


def test_a_directory_named_like_a_session_is_skipped(tmp_path: Path) -> None:
    (tmp_path / X / "plasma.desktop").mkdir(parents=True)
    assert installed_desktops(tmp_path) == frozenset()


def test_an_unreadable_session_file_is_skipped(tmp_path: Path) -> None:
    import os

    if os.geteuid() == 0:
        pytest.skip("root reads a mode-000 file; CI runs as uid 0")
    _session(tmp_path, X, "xfce.desktop", _entry("Xfce", "startxfce4", "XFCE"))
    (tmp_path / X / "xfce.desktop").chmod(0)
    try:
        assert installed_desktops(tmp_path) == frozenset()
    finally:
        (tmp_path / X / "xfce.desktop").chmod(0o644)


def test_non_utf8_content_does_not_raise(tmp_path: Path) -> None:
    path = tmp_path / X / "odd.desktop"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"[Desktop Entry]\nName=\xff\xfe\nDesktopNames=XFCE\n")
    assert installed_desktops(tmp_path) == {Desktop.xfce}


def test_an_empty_desktop_names_value_is_no_desktop_and_skips_the_stem(tmp_path: Path) -> None:
    """`DesktopNames=` present but empty: the file said something, and it was nothing."""
    _session(tmp_path, X, "LXDE.desktop", _entry("LXDE", "/usr/bin/startlxde", ""))
    assert installed_desktops(tmp_path) == frozenset()
