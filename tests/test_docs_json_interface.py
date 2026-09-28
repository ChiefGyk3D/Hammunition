# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The JSON interface, and `hammunition` on the PATH, are documented where
people look.  D-059."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from hammunition.interface import envelope

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_DOC = REPO_ROOT / "docs" / "reference" / "cli.md"
INSTALL_DOC = REPO_ROOT / "docs" / "getting-started" / "install.md"


def test_d059_is_recorded() -> None:
    text = (REPO_ROOT / "docs" / "DECISIONS.md").read_text()
    assert "## D-059" in text
    assert "never driven through JSON" in text


def test_every_json_capable_verb_says_so_in_the_cli_reference() -> None:
    importlib.import_module("hammunition.cli.main")  # registers the decorators
    text = CLI_DOC.read_text()
    # Only the engine's own commands: test_json_interface.py registers a probe.
    capable = [f for f in envelope._CAPABLE if f.__module__ == "hammunition.cli.main"]
    assert capable, "no JSON-capable command found; the check below would pass empty"
    for func in capable:
        verb = func.__name__.removeprefix("cmd_").replace("_", " ")
        assert f"`hammunition {verb}" in text, f"{verb} is undocumented"
    assert text.count("--json") >= len(capable), (
        "each verb with a JSON form names --json in its section"
    )


def _sections(text: str) -> dict[str, str]:
    """cli.md's verb sections, keyed by heading."""
    parts = re.split(r"^### (.+)$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def test_each_json_capable_section_names_its_document_kind() -> None:
    """Counting `--json` over the whole page passes when one section says it
    ten times; each verb's own section must name its kind and the page."""
    importlib.import_module("hammunition.cli.main")
    sections = _sections(CLI_DOC.read_text())
    kinds = envelope.kinds()
    capable = [f for f in envelope._CAPABLE if f.__module__ == "hammunition.cli.main"]
    for func in capable:
        verb = func.__name__.removeprefix("cmd_").replace("_", " ")
        heading = next((h for h in sections if h.startswith(f"`hammunition {verb}")), None)
        assert heading is not None, f"no section for {verb}"
        body = sections[heading]
        assert "--json" in body, f"the {verb} section does not mention --json"
        assert "json-interface.md" in body, f"the {verb} section does not link the page"
        named = [k for k in kinds if f"`{k}` document" in body]
        assert named, f"the {verb} section names no document kind"


def test_the_privacy_rule_is_in_the_prose_docs() -> None:
    """`station` and `plan` carry values meant for a local program only."""
    sections = _sections(CLI_DOC.read_text())
    station = next(b for h, b in sections.items() if h.startswith("`hammunition station show"))
    install = next(b for h, b in sections.items() if h.startswith("`hammunition install"))
    for body in (station, install):
        assert "not for pasting" in body
    decisions = (REPO_ROOT / "docs" / "DECISIONS.md").read_text()
    d059 = decisions[decisions.index("## D-059") :]
    assert "not for pasting" in d059


def test_getting_started_says_bootstrap_puts_hammunition_on_the_path() -> None:
    text = INSTALL_DOC.read_text()
    assert "~/.local/bin/hammunition" in text
    assert "source .venv/bin/activate" not in text
    # A reader whose shell says "command not found" is told what to run instead.
    assert "command not found" in text
    assert "~/src/Hammunition/.venv/bin/hammunition" in text


# Pages that record what was typed at the time. They are history, and stay as
# written: the decision record, the session log, the changelog, the bench and
# campaign pages, and the plans and specs under docs/superpowers/.
HISTORICAL = (
    "docs/DECISIONS.md",
    "docs/SESSION-LOG.md",
    "CHANGELOG.md",
)
HISTORICAL_PREFIXES = (
    "docs/superpowers/",
    "docs/reference/bench-verification-",
    "docs/reference/vm-campaign-",
    "docs/reference/vm-verification-",
)

# The engine run by a path, or as a module: `.venv/bin/hammunition doctor`,
# `~/src/Hammunition/.venv/bin/hammunition status`, `python -m hammunition`.
# Only where the path is the command itself: `ln -s .../bin/hammunition LINK`
# names the file, and is not an example of running it.
BY_PATH = re.compile(
    r"(?:^|[;&|]\s*|\bsudo\s+|^\$\s+)"
    r"(?:\S*/bin/hammunition|python3?\s+-m\s+hammunition)(?=\s|$)"
)


def _current_docs() -> list[Path]:
    out = [REPO_ROOT / "README.md"]
    for md in sorted((REPO_ROOT / "docs").rglob("*.md")):
        rel = md.relative_to(REPO_ROOT).as_posix()
        if rel in HISTORICAL or rel.startswith(HISTORICAL_PREFIXES):
            continue
        out.append(md)
    return out


def test_every_example_runs_the_engine_as_bare_hammunition() -> None:
    """Spec §2: examples say `hammunition ...`, which bootstrap puts on the
    PATH. The full path is shown only under a heading about "command not
    found", which is where a reader who needs it is sent."""
    offenders: list[str] = []
    for md in _current_docs():
        heading, fenced = "", False
        for line in md.read_text().splitlines():
            if line.startswith("```"):
                fenced = not fenced
            elif not fenced and line.startswith("#"):
                heading = line
            elif fenced and "command not found" not in heading and BY_PATH.search(line):
                offenders.append(f"{md.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, "run the engine as bare `hammunition` in examples:\n" + "\n".join(
        offenders
    )


def test_the_bare_command_check_can_fail() -> None:
    """Falsified: the pattern catches the forms it exists to catch."""
    for line in (
        ".venv/bin/hammunition doctor",
        "~/src/Hammunition/.venv/bin/hammunition status",
        "python3 -m hammunition list",
        "sudo /home/op/Hammunition/.venv/bin/hammunition install station",
        "cd x && .venv/bin/hammunition status",
    ):
        assert BY_PATH.search(line), line
    for line in (
        "hammunition doctor",
        'ln -s "$PWD/.venv/bin/hammunition" ~/.local/bin/hammunition',
        "rm ~/.local/bin/hammunition",
        "hammunition install hammunition-tray",
    ):
        assert not BY_PATH.search(line), line
