# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The values the engine shares with the GPS tether equal the tether's own.

The tether is hammunition-gps-tether (D-071 note, 2026-10-02). Its source is
read as text, never imported, from a checkout beside this one or from the
installed tree. Where neither is present the test skips and says why on a
developer machine, and fails in CI (``HAMMUNITION_REQUIRE_TETHER=1``,
``HAMMUNITION_CI=1`` or ``GITHUB_ACTIONS=true``), where a skip is the drift
check silently not running (issue #215). The workflow's ``ci`` job (``scripts/ci-test.sh``) checks the
tether out at the tag the catalog pins.
"""

from __future__ import annotations

import ast
import contextlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from hammunition import geoclue, reference, tether_contract

REPO = Path(__file__).resolve().parents[1]
PACKAGE = Path("src") / "hammunition_gps_tether"
CANDIDATES = (
    REPO.parent / "hammunition-gps-tether",
    Path("/usr/local/share/hammunition/gps-tether"),
)


def _required() -> bool:
    env = os.environ
    return (
        env.get("HAMMUNITION_REQUIRE_TETHER") == "1"
        or env.get("HAMMUNITION_CI") == "1"
        or env.get("GITHUB_ACTIONS") == "true"
    )


def _package() -> Path:
    for root in CANDIDATES:
        if (root / PACKAGE / "tether.py").is_file():
            return root / PACKAGE
    looked = ", ".join(str(r / PACKAGE / "tether.py") for r in CANDIDATES)
    message = f"hammunition-gps-tether source not found; looked for {looked}"
    if _required():
        pytest.fail(
            message + " (CI must check it out: see scripts/ci-test.sh, run by the ci job in ci.yml)"
        )
    raise pytest.skip.Exception(message)


def _constants(path: Path) -> dict[str, object]:
    found: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                with contextlib.suppress(ValueError):
                    found[target.id] = ast.literal_eval(node.value)
    return found


def test_the_ports_equal_the_tethers() -> None:
    theirs = _constants(_package() / "tether.py")
    assert theirs["PORT"] == tether_contract.NMEA_PORT
    assert theirs["POSITION_PORT"] == tether_contract.POSITION_PORT


def test_the_geoclue_four_equal_the_tethers() -> None:
    theirs = _constants(_package() / "geoclue.py")
    assert theirs["DROPIN"] == tether_contract.GEOCLUE_DROPIN
    assert theirs["HEADER"] == tether_contract.GEOCLUE_HEADER
    assert theirs["SOCKET"] == tether_contract.GEOCLUE_SOCKET
    assert theirs["GROUP"] == tether_contract.GEOCLUE_GROUP


def test_the_engine_uses_the_contract_not_its_own_copies() -> None:
    # PATHS holds the real defaults; a fixture may have repointed the attributes.
    assert geoclue.PATHS["DROPIN"] == tether_contract.GEOCLUE_DROPIN
    assert geoclue.PATHS["SOCKET"] == tether_contract.GEOCLUE_SOCKET
    assert geoclue.HEADER == tether_contract.GEOCLUE_HEADER
    assert geoclue.GROUP == tether_contract.GEOCLUE_GROUP
    assert reference.POSITION_PORT == tether_contract.POSITION_PORT


def test_the_engine_carries_no_tether_module() -> None:
    assert not (REPO / "src" / "hammunition" / "gps_tether.py").exists()


# --- the check cannot silently stop running (issue #215) -------------------


_ENV = ("HAMMUNITION_REQUIRE_TETHER", "HAMMUNITION_CI", "GITHUB_ACTIONS")


def _empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys.modules[__name__], "CANDIDATES", (tmp_path / "a", tmp_path / "b"))
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "name,value",
    [
        ("HAMMUNITION_REQUIRE_TETHER", "1"),
        ("HAMMUNITION_CI", "1"),
        ("GITHUB_ACTIONS", "true"),
    ],
)
def test_a_missing_tether_fails_in_ci(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, value: str
) -> None:
    _empty(monkeypatch, tmp_path)
    monkeypatch.setenv(name, value)
    with pytest.raises(pytest.fail.Exception, match=r"looked for .*tether\.py"):
        _package()


def test_a_missing_tether_skips_on_a_developer_machine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _empty(monkeypatch, tmp_path)
    with pytest.raises(pytest.skip.Exception, match="not found"):
        _package()


def test_a_present_tether_is_found_in_ci(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _empty(monkeypatch, tmp_path)
    (tmp_path / "a" / PACKAGE).mkdir(parents=True)
    (tmp_path / "a" / PACKAGE / "tether.py").write_text("PORT = 1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert _package() == tmp_path / "a" / PACKAGE


def _manifest_tag() -> str:
    text = (REPO / "catalog" / "packages" / "gps-tether.yaml").read_text(encoding="utf-8")
    found = re.findall(r"hammunition-gps-tether/archive/refs/tags/(v[0-9][^/\s]*?)\.tar\.gz", text)
    assert len(set(found)) == 1, found
    return str(found[0])


CI_SCRIPT = REPO / "scripts" / "ci-test.sh"


def _workflow_tag_command() -> str:
    """The script's tag extraction, so the test runs what CI runs."""
    text = CI_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^tag=\$\((.*?)\)\n", text, re.S | re.M)
    assert match, "scripts/ci-test.sh does not read the tether tag from the manifest"
    return "tag=$(" + match.group(1) + ')\necho "tag=$tag"'


def test_ci_reads_the_tether_tag_from_the_manifest() -> None:
    """Neither the workflow nor its script holds a tag, so a re-pin cannot leave CI behind."""
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "test-command: bash scripts/ci-test.sh" in workflow
    text = CI_SCRIPT.read_text(encoding="utf-8")
    assert "ChiefGyk3D/hammunition-gps-tether" in text
    assert "HAMMUNITION_REQUIRE_TETHER=1" in text
    assert '--branch "$tag"' in text
    assert not re.search(r"--branch\s+v?[0-9]", text), "a hard-coded tether tag in ci-test.sh"
    assert not re.search(r"ref:\s*v[0-9]", workflow), "a hard-coded tether tag in ci.yml"
    command = _workflow_tag_command()
    assert "catalog/packages/gps-tether.yaml" in command
    # Run the script's own extraction, so the grep and the manifest agree.
    out = subprocess.run(
        ["bash", "-c", command],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": os.environ["PATH"]},
    ).stdout
    assert f"tag={_manifest_tag()}" in out
