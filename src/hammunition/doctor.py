# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition doctor`` — is this machine ready, and what is not yet set up.

A read-only health check. It changes nothing and it is the first thing to run
on a fresh machine or when something misbehaves: it turns the failures the
engine would otherwise hit mid-transaction into a report you read up front,
each with the one command that fixes it.

The checks are a **pure function** of explicit inputs so they can be tested
without a real machine; the CLI gathers the inputs (detects the target, probes
for tools, reads the catalog and station) and renders the result. Nothing here
runs a subprocess or touches the filesystem.

Severity has four levels, and the distinction is the point:

- ``fail`` — the engine cannot work until this is fixed (no catalog, not a
  Debian-family system).
- ``warn`` — a whole class of installs will fail or a feature is unavailable
  until this is fixed (no venv support, no compiler, callsign unset), but the
  engine runs and other installs work.
- ``info`` — a true fact worth stating that is not a problem (no ham hardware
  attached right now; udev rules not yet applied on a machine with no radios).
- ``ok`` — checked and healthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["Check", "Status", "run_checks", "summarize"]

Status = Literal["ok", "warn", "fail", "info"]


@dataclass(frozen=True)
class Check:
    """One thing looked at, its verdict, and how to fix it if it is not ok."""

    name: str
    status: Status
    detail: str
    fix: str | None = None


def run_checks(
    *,
    target_describe: str | None,
    is_debian_family: bool,
    catalog_counts: tuple[int, int] | None,
    has_venv_module: bool,
    path_has_local_bin: bool,
    tools: dict[str, bool],
    groups_now: frozenset[str],
    needed_groups: list[str],
    station_set: bool,
    rules_applied: bool,
    attached_recognised: int,
    log_dir_writable: bool,
) -> list[Check]:
    """Every check, in the order a person should read them. Pure; see module docstring."""
    checks: list[Check] = []

    if target_describe is None:
        checks.append(
            Check(
                "system",
                "fail",
                "could not read /etc/os-release — cannot tell what this machine is",
                "run on a Debian-family system (Parrot, Debian, Ubuntu, Kali, Raspberry Pi OS)",
            )
        )
    elif not is_debian_family:
        checks.append(
            Check(
                "system",
                "fail",
                f"{target_describe} is not Debian-family; nothing here applies",
                "Hammunition augments a Debian-family install; use one of the supported targets",
            )
        )
    else:
        checks.append(Check("system", "ok", target_describe))

    if catalog_counts is None:
        checks.append(
            Check(
                "catalog",
                "fail",
                "the catalog could not be found or loaded",
                "run from the git checkout, or pass --catalog / set HAMMUNITION_CATALOG",
            )
        )
    else:
        packages, profiles = catalog_counts
        checks.append(Check("catalog", "ok", f"{packages} packages, {profiles} profiles loaded"))

    if has_venv_module:
        checks.append(Check("python venv", "ok", "python3 -m venv is available"))
    else:
        checks.append(
            Check(
                "python venv",
                "warn",
                "python3 -m venv is missing — venv and hybrid installs will fail",
                "sudo apt install python3-venv",
            )
        )

    if path_has_local_bin:
        checks.append(Check("PATH", "ok", "~/.local/bin is on PATH"))
    else:
        checks.append(
            Check(
                "PATH",
                "warn",
                "~/.local/bin is not on PATH — venv-installed programs will look missing",
                "log out and back in, or add ~/.local/bin to PATH; it is added when the dir first appears",
            )
        )

    if tools.get("cc", False):
        checks.append(Check("compiler", "ok", "a C toolchain is present for source builds"))
    else:
        checks.append(
            Check(
                "compiler",
                "warn",
                "no C compiler found — the ~57 source-built units cannot build",
                "sudo apt install build-essential (the engine also pulls per-build deps at plan time)",
            )
        )

    if tools.get("git", False):
        checks.append(Check("git", "ok", "git is present for git-source builds"))
    else:
        checks.append(
            Check(
                "git",
                "warn",
                "git is missing — git-source units cannot be fetched",
                "sudo apt install git (the planner also injects it as a build dep)",
            )
        )

    if station_set:
        checks.append(Check("station", "ok", "callsign and grid are set"))
    else:
        checks.append(
            Check(
                "station",
                "warn",
                "no callsign/grid set — packet and logging configs are deferred until you set them",
                "hammunition station set --callsign YOURCALL --grid-square AB12cd",
            )
        )

    missing_groups = [g for g in needed_groups if g not in groups_now]
    if not needed_groups:
        pass
    elif not missing_groups:
        checks.append(Check("device groups", "ok", "in every device-access group"))
    else:
        checks.append(
            Check(
                "device groups",
                "warn",
                f"not in: {', '.join(missing_groups)} — devices needing them will be permission-denied",
                "hammunition hardware apply (then log out and back in)",
            )
        )

    if rules_applied:
        checks.append(Check("udev rules", "ok", "the catalog's udev rules are installed"))
    else:
        checks.append(
            Check(
                "udev rules",
                "info",
                "udev rules not yet applied (fine until you connect a supported device)",
                "hammunition hardware apply",
            )
        )

    if attached_recognised > 0:
        checks.append(
            Check(
                "hardware",
                "ok",
                f"{attached_recognised} catalogued device(s) attached — see `hardware list`",
            )
        )
    else:
        checks.append(Check("hardware", "info", "no catalogued devices attached right now"))

    if log_dir_writable:
        checks.append(Check("state dir", "ok", "the transaction log directory is writable"))
    else:
        checks.append(
            Check(
                "state dir",
                "warn",
                "the transaction-log directory is not writable — history and uninstall will not record",
                "check ownership of ~/.local/state/hammunition (do not run install as root)",
            )
        )

    return checks


def summarize(checks: list[Check]) -> tuple[int, int, int]:
    """(fails, warns, oks+infos) — for the closing line and the exit code."""
    fails = sum(1 for c in checks if c.status == "fail")
    warns = sum(1 for c in checks if c.status == "warn")
    healthy = sum(1 for c in checks if c.status in ("ok", "info"))
    return fails, warns, healthy
