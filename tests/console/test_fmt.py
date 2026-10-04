# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from hammunition.console.fmt import clean, first_line, human_size, mask


@pytest.mark.parametrize(
    "raw", ["\x1b[2J\x1b[31mred", "a\x1b]0;title\x07b", "x\x00y", "a\x7fb", "c\x9b31md", "bell\x07"]
)
def test_clean_removes_every_control_character(raw: str) -> None:
    out = clean(raw)
    assert not any((ord(c) < 32 and c != "\n") or 0x7F <= ord(c) <= 0x9F for c in out)


def test_clean_removes_whole_escape_sequences_not_just_the_escape() -> None:
    assert clean("\x1b[2J\x1b[31mred\x1b[0m") == "red"
    assert clean("a\x1b]0;title\x07b") == "ab"
    assert clean("a\x1b]0;title\x1b\\b") == "ab"
    assert clean("c\x9b31md") == "cd"
    assert clean("a\x1bPdcs\x1b\\b") == "ab"
    assert clean("a\x1bcb") == "ab"


def test_clean_is_falsifiable_a_raw_escape_would_survive_without_it() -> None:
    raw = "\x1b[2Jboom"
    assert "\x1b" in raw and "\x1b" not in clean(raw)


def test_clean_keeps_text_newlines_and_expands_tabs() -> None:
    assert clean("a\tb\nc") == "a    b\nc"
    assert clean("plain text 123") == "plain text 123"


def test_clean_accepts_non_strings_and_none() -> None:
    assert clean(None) == "None" and clean(7) == "7"


def test_human_size() -> None:
    assert [human_size(n) for n in (0, 512, 2048, 5 * 1024**2, 3 * 1024**3)] == [
        "0 B",
        "512 B",
        "2.0 KiB",
        "5.0 MiB",
        "3.0 GiB",
    ]


def test_mask_never_reveals_and_says_not_set() -> None:
    assert (
        mask(None) == "not set" and mask("N0CALL") == "********" and "N0CALL" not in mask("N0CALL")
    )


def test_first_line() -> None:
    assert (
        first_line("one\ntwo") == "one"
        and first_line("") == ""
        and len(first_line("x" * 500)) <= 120
    )
