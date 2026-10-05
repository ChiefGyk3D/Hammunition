# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The console's documentation pages say what the code does (docs/console/, docs/getting-started/console.md)."""

from hammunition.console.config import SCREENS
from hammunition.console.helptext import KEYS, NEVER
from hammunition.console.verbs import JSON_VERBS

from .fixture_scan import findings
from .helpers import REPO

DOCS = REPO / "docs"
INDEX = (DOCS / "console" / "index.md").read_text()
CONTRACT = (DOCS / "console" / "contract.md").read_text()
GUIDE = (DOCS / "getting-started" / "console.md").read_text()
CLI = (DOCS / "reference" / "cli.md").read_text()


def test_the_reference_has_every_required_section() -> None:
    for heading in (
        "What it is",
        "Requirements",
        "How it works",
        "What it never does",
        "Keys",
        "Screens",
        "Status",
        "Development",
    ):
        assert f"\n## {heading}\n" in INDEX, heading


def test_the_keys_table_lists_every_key_in_the_help() -> None:
    for keys, meaning in KEYS:
        assert f"| `{keys}` | {meaning} |" in INDEX, (
            f"the keys table is out of step with helptext.KEYS: {keys}"
        )


def test_the_reference_names_every_screen_and_counts_them_right() -> None:
    assert len(SCREENS) == 8
    for screen in SCREENS:
        assert f"**{screen.capitalize()}**" in INDEX, screen


def test_the_never_section_carries_the_help_text_verbatim() -> None:
    never = INDEX.split("\n## What it never does\n")[1].split("\n## ")[0]
    for line in NEVER:
        assert f"- {line}" in never, f"the reference is out of step with helptext.NEVER: {line}"


def test_there_is_one_version_and_no_floor_anywhere_in_the_docs() -> None:
    for name, text in (("reference", INDEX), ("contract", CONTRACT), ("guide", GUIDE)):
        assert "ENGINE_FLOOR" not in text and "or later on `PATH`" not in text, name
    assert "no version floor" in CONTRACT


def test_the_status_section_says_what_has_not_run_on_real_hardware() -> None:
    status = INDEX.split("\n## Status\n")[1].split("\n## ")[0]
    assert (
        "has not been run" in status
        or "have not been run" in status
        or "What has not been run" in status
    )
    assert "field laptop" in status and "urwid.Terminal" in status


def test_the_pages_carry_no_identifier() -> None:
    for name, text in (("reference", INDEX), ("contract", CONTRACT), ("guide", GUIDE)):
        assert findings(text) == [], name


def test_the_contract_lists_every_verb_the_console_reads() -> None:
    for verb in JSON_VERBS:
        assert f"`hammunition {' '.join(verb)}" in CONTRACT, verb
    assert "E1" in CONTRACT and "E2" in CONTRACT and "unknown" in CONTRACT


def test_the_reference_says_how_the_three_channels_differ() -> None:
    assert "worker thread" in INDEX and "terminal pane" in INDEX and "config.toml" in INDEX
    assert "python -m hammunition" in INDEX


def test_nothing_claims_the_console_never_fetches_without_naming_the_u_key() -> None:
    for name, text in (("reference", INDEX), ("guide", GUIDE)):
        flat = " ".join(text.split())
        assert "never fetches anything from the network;" not in flat, name
        assert "u" in flat
    assert "only when you press u" in " ".join(INDEX.split()) and "PyPI" in INDEX


def test_the_prompt_says_only_esc_cancels_and_the_docs_agree() -> None:
    from hammunition.console.screens.base import PromptScreen

    from .helpers import FakeContext

    prompt = PromptScreen(FakeContext(), "t", "l: ", lambda v: None)
    shown = " ".join(
        str(w.original_widget.text) for w in prompt._walker if hasattr(w, "original_widget")
    )
    assert "Esc cancels" in shown and "Esc or b" not in shown
    assert "only Esc" in INDEX


def test_unmeasured_claims_stay_unmeasured_and_docs_use_the_placeholder() -> None:
    for text in (INDEX, GUIDE):
        assert "works over SSH and on a Pi" not in text
    assert "has not been measured" in " ".join(INDEX.split())
    assert "Not measured:" in GUIDE
    assert "N0CALL" not in INDEX and "hardware apply" in INDEX


def test_the_cli_reference_names_the_verb_and_what_it_refuses() -> None:
    section = CLI.split("### `hammunition console", 1)[1].split("\n### ", 1)[0]
    assert "python3-urwid" in section and "hammunition[console]" in section
    assert "no `--json` form" in section and "exit 2" in section
