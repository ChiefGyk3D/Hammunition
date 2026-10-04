# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A user service may run a file inside its own unit's virtualenv.  D-073, D-080.

Reticulum's shared instance is ``{venv}/bin/rnsd``: the program lives in a
per-user venv under the operator's data directory, which no manifest can name
as an absolute path. ``{venv}`` is filled where ``{python}`` already is.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends import AptBackend, RecordingRunner
from hammunition.backends.apt import AptPackageState
from hammunition.distro import Target
from hammunition.manifest.schema import ManifestError, PackageManifest
from hammunition.plan import resolve
from hammunition.station import Station
from hammunition.userservice import PlanUserServiceError, plan_user_services, service_venv_dir

# Any non-zero digest: the planner refuses the all-zero placeholder as unpinned.
HASHED = (
    "example==1.0 --hash=sha256:1111111111111111111111111111111111111111111111111111111111111111"
)
VENV = Path("/home/op/.local/share/hammunition/venvs/svc")

_SERVICE: dict[str, Any] = {
    "name": "hammunition-svc",
    "description": "A service that lives in its own venv",
    "exec": ["{venv}/bin/svcd", "--service"],
}


def _manifest(
    services: list[dict[str, Any]] | None = None, *, method: str = "venv"
) -> PackageManifest:
    install: dict[str, Any] = (
        {"method": "venv", "requirements": [HASHED]}
        if method == "venv"
        else {"method": "apt", "packages": ["svc"]}
    )
    return PackageManifest.model_validate(
        {
            "name": "svc",
            "version": "1.0",
            "summary": "Fixture for the venv service suite",
            "categories": ["mesh"],
            "install": [{"install": install}],
            "update": {"probe": {"method": "pypi"}, "strategy": "reinstall"},
            "documentation": {
                "what_it_does": "Exists so a user service has a venv to run from.",
                "why_you_want_it": "You do not; the suite does.",
                "upstream_url": "https://example.invalid/",
            },
            "user_services": services if services is not None else [_SERVICE],
        }
    )


def test_a_service_may_run_a_file_under_its_own_venv() -> None:
    (svc,) = _manifest().user_services
    assert svc.exec[0] == "{venv}/bin/svcd"
    assert svc.is_plain  # no station value, no device: always planned


def test_a_venv_service_on_a_manifest_with_no_venv_is_refused_at_load() -> None:
    """The path would name nothing; the service would loop on a missing file."""
    with pytest.raises((ManifestError, ValidationError), match=r"\{venv\}.*no.*venv"):
        _manifest(method="apt")


def test_a_bare_relative_exec_is_still_refused() -> None:
    bad = {**_SERVICE, "exec": ["bin/svcd", "--service"]}
    with pytest.raises((ManifestError, ValidationError), match="absolute path"):
        _manifest([bad])


def test_the_venv_fills_the_exec_line_of_the_unit_file() -> None:
    planned, deferrals, notes = plan_user_services(_manifest(), Station(), None, venv_dir=VENV)
    assert not deferrals and not notes
    (svc,) = planned
    assert svc.exec_argv == (f"{VENV}/bin/svcd", "--service")
    assert f"ExecStart={VENV}/bin/svcd --service\n" in svc.unit_body
    assert "{venv}" not in svc.unit_body


@pytest.mark.parametrize("home", ["/home/an op", "/home/op%h", "/home/op;x", "/home/o'p"])
def test_a_home_the_unit_file_cannot_carry_defers_by_name(home: str) -> None:
    """An ExecStart= is split on whitespace and expands `%`; the service is
    deferred with the reason, never written with a path systemd would read as two."""
    planned, deferrals, _notes = plan_user_services(
        _manifest(), Station(), None, venv_dir=Path(home) / "venvs" / "svc"
    )
    assert planned == []
    (deferral,) = deferrals
    assert deferral.subject == "svc"
    assert deferral.what == "will not run hammunition-svc"
    assert "carries a shell character or whitespace" in deferral.why


def test_a_missing_venv_directory_is_a_bug_not_a_deferral() -> None:
    with pytest.raises(PlanUserServiceError, match="no venv"):
        plan_user_services(_manifest(), Station(), None, venv_dir=None)


def test_the_venv_dir_is_the_backends_own_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert service_venv_dir(_manifest()) == tmp_path / "data" / "hammunition" / "venvs" / "svc"
    assert service_venv_dir(_manifest(method="apt", services=[])) is None


def test_under_sudo_the_venv_is_the_operators_not_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hammunition.paths.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "hammunition.paths.pwd.getpwnam",
        lambda name: SimpleNamespace(pw_uid=1000, pw_dir="/home/op"),
    )
    assert service_venv_dir(_manifest(), "op") == VENV


def test_the_planner_hands_the_operators_venv_to_the_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The wiring: `resolve` fills {venv} from the operator it plans for."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    lists = tmp_path / "lists"
    lists.mkdir()
    (lists / "example.invalid_dists_trixie_main_binary-amd64_Packages").touch()

    class Apt(AptBackend):
        def probe(self, packages: Any) -> Any:
            return {n: AptPackageState(name=n, installed=None, candidate="1.0") for n in packages}

    plan = resolve(
        ["svc"],
        catalog={"svc": _manifest()},
        profiles={},
        target=Target(distro="debian", version="13", arch="x86_64"),
        apt=Apt(RecordingRunner(), lists_dir=lists),
        user="",
    )
    (svc,) = plan.user_services
    expected = tmp_path / "data" / "hammunition" / "venvs" / "svc" / "bin" / "svcd"
    assert svc.exec_argv[0] == str(expected)
