# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""No file in the package but guard.py may mention the assume-yes flag or a
scripted-consent variable, and guard.py only on lines tagged `# consent-guard`.
This is a grep, so it is falsified on purpose (see the plan)."""

from .helpers import PACKAGE_DIR

PACKAGE = PACKAGE_DIR
TOKENS = ("--yes", '"-y"', "'-y'", "HAMMUNITION_ACCEPT", "_CONSENT")
TAG = "# consent-guard"


def offenders() -> list[str]:
    found: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if any(token in line for token in TOKENS) and not (
                path.name == "guard.py" and TAG in line
            ):
                found.append(f"{path.relative_to(PACKAGE.parents[1])}:{number}: {line.strip()}")
    return found


def test_the_package_never_names_the_assume_yes_flag_or_a_consent_variable() -> None:
    assert offenders() == [], (
        "only hammunition.console/guard.py may name these tokens, on lines tagged "
        f"'{TAG}'; the console must never pass the flag or set the variable (D-021)"
    )


def test_the_scan_itself_sees_the_guard_file() -> None:
    assert any(p.name == "guard.py" for p in PACKAGE.rglob("*.py"))
    guard_lines = [
        ln for ln in (PACKAGE / "guard.py").read_text().splitlines() if "HAMMUNITION_ACCEPT" in ln
    ]
    assert guard_lines and all(TAG in ln for ln in guard_lines)
