# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every module importable on its own, first.

Issue #158: ``python -c 'import hammunition.fetch'`` raised a circular
``ImportError`` when ``hammunition.fetch`` was the *first* ``hammunition``
module a process imported. The engine's own CLI never hit it, because
``hammunition.cli.main`` happens to import ``hammunition.backends`` (and
therefore ``hammunition.backends.base``) before anything reaches
``hammunition.fetch``, which primes ``sys.modules`` in an order that hides
the cycle. Hammunition Bunker's ``enginelib.py`` imports ``hammunition.fetch``
directly and hit it for real.

A test that imports modules in the suite's own collection order cannot catch
this: by the time any single test runs, dozens of earlier test modules have
already imported half the package, so ``sys.modules`` is pre-primed exactly
the way ``hammunition.cli.main`` primes it. The only way to see what a cold
caller sees is a fresh interpreter per module, with nothing loaded first.
"""

from __future__ import annotations

import os
import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

sys.path.insert(0, str(SRC))

import hammunition  # noqa: E402


def _discover_modules() -> list[str]:
    """Every dotted module name under the ``hammunition`` package.

    ``__main__`` is skipped: run as a script, not imported, so it is not
    subject to the "first import" property this test checks.
    """
    names = []
    for info in pkgutil.walk_packages(hammunition.__path__, prefix="hammunition."):
        if info.name.rsplit(".", 1)[-1] == "__main__":
            continue
        names.append(info.name)
    return sorted(names)


MODULE_NAMES = _discover_modules()


@pytest.fixture(scope="module")
def _isolated_env() -> dict[str, str]:
    """A subprocess environment where ``src/`` is importable and nothing else
    about the host leaks in beyond what the real CLI also inherits."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    return env


@pytest.mark.parametrize("module_name", MODULE_NAMES)
def test_module_imports_alone(module_name: str, _isolated_env: dict[str, str]) -> None:
    """``import <module_name>`` succeeds as the only hammunition import in the process.

    A module that only imports cleanly *after* some other module has already
    been loaded has a cycle; this is the regression test for #158, where
    ``hammunition.fetch`` was exactly that module.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=REPO_ROOT,
        env=_isolated_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"import {module_name} failed as the first hammunition import in a "
        f"fresh interpreter (exit {result.returncode}):\n{result.stderr}"
    )


def test_discovered_at_least_the_known_modules() -> None:
    """A collection bug that silently found zero modules would pass every
    parametrized case above by having nothing to check (CLAUDE.md: a missing
    probe is an error, never an empty measurement)."""
    assert len(MODULE_NAMES) >= 50, (
        f"only discovered {len(MODULE_NAMES)} hammunition modules; "
        "pkgutil.walk_packages may not be finding the package"
    )
    assert "hammunition.fetch" in MODULE_NAMES
    assert "hammunition.backends.apt_repo" in MODULE_NAMES
