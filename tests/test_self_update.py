# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`hammunition self-update` (#303) and the version it reports (#311).

Every test builds a scratch git repository with a fake `bootstrap.sh`; none runs
the real one or touches this machine's checkout, `~/.local/bin` or its venv.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hammunition import runlog, selfupdate
from hammunition.cli.main import EXIT_CONSENT, EXIT_FAILED, EXIT_OK, EXIT_UNPLANNABLE, main
from hammunition.doctor import run_checks
from hammunition.interface import envelope
from test_doctor import HEALTHY

GIT_ENV = {
    "GIT_AUTHOR_NAME": "T",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "T",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

FAKE_BOOTSTRAP = """#!/usr/bin/env bash
set -e
echo "fake bootstrap ran in $(basename "$(pwd)")"
echo ran >> "$BOOTSTRAP_MARK"
[ -z "${BOOTSTRAP_FAIL:-}" ] || { echo "boom" >&2; exit 7; }
"""


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    return out.stdout.strip()


def commit(cwd: Path, name: str, message: str, version: str | None = None) -> None:
    (cwd / name).write_text(message)
    if version:
        (cwd / "pyproject.toml").write_text(
            f'[project]\nname = "hammunition"\nversion = "{version}"\n'
        )
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", message)


class Repo:
    def __init__(self, base: Path) -> None:
        self.origin = base / "origin.git"
        self.work = base / "work"
        self.other = base / "other"
        git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(base, "clone", "-q", str(self.origin), str(self.work))
        git(self.work, "checkout", "-q", "-b", "main")
        (self.work / "bootstrap.sh").write_text(FAKE_BOOTSTRAP)
        (self.work / "bootstrap.sh").chmod(0o755)
        (self.work / "src" / "hammunition").mkdir(parents=True)
        commit(self.work, "a.txt", "first", version="1.0.0")
        git(self.work, "push", "-q", "-u", "origin", "main")
        git(base, "clone", "-q", str(self.origin), str(self.other))

    def upstream(self, name: str, message: str, version: str | None = None) -> None:
        commit(self.other, name, message, version)
        git(self.other, "push", "-q", "origin", "main")

    def tag(self, tag: str) -> None:
        git(self.other, "tag", tag)
        git(self.other, "push", "-q", "origin", tag)

    def head(self) -> str:
        return git(self.work, "rev-parse", "HEAD")


def test_without_a_git_binary_it_refuses_with_a_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_git(*_a: object, **_k: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(subprocess, "run", no_git)
    with pytest.raises(selfupdate.Refused, match="git is not installed"):
        selfupdate.preflight(tmp_path, release=False)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    # The scratch repositories need a git binary; the distro containers run the suite
    # without one, so these tests skip there (the no-git refusal test above still runs).
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    # The distro containers run the suite as root, and the verb refuses root before
    # anything under test here runs; these tests are about the checkout, not the uid.
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("BOOTSTRAP_MARK", str(tmp_path / "bootstrap.ran"))
    r = Repo(tmp_path)
    monkeypatch.setattr(selfupdate, "PACKAGE_FILE", r.work / "src" / "hammunition" / "x.py")
    monkeypatch.setattr(selfupdate, "installed_version", lambda: "1.0.0")
    # what a real bootstrap's editable install does: the venv now reports the tree's version
    monkeypatch.setattr(
        selfupdate, "installed_version_in", lambda root: selfupdate.checkout_version(root)
    )
    return r


def bootstrap_runs(tmp_path: Path) -> int:
    mark = tmp_path / "bootstrap.ran"
    return len(mark.read_text().split()) if mark.exists() else 0


def test_outside_a_checkout_it_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(selfupdate, "PACKAGE_FILE", tmp_path / "a" / "b" / "c" / "x.py")
    assert main(["self-update", "--dry-run"]) == EXIT_UNPLANNABLE
    assert "not running from a git checkout" in capsys.readouterr().err


def test_a_dirty_tree_is_refused_before_anything_is_fetched(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.upstream("b.txt", "second")
    (repo.work / "a.txt").write_text("edited")
    before = repo.head()
    assert main(["self-update", "--yes"]) == EXIT_UNPLANNABLE
    assert "uncommitted changes" in capsys.readouterr().err
    assert repo.head() == before and bootstrap_runs(tmp_path) == 0
    assert "origin/main" in git(repo.work, "branch", "-r")
    assert git(repo.work, "rev-parse", "origin/main") == before  # not even fetched


def test_a_branch_other_than_main_is_refused_unless_release(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo.work, "checkout", "-q", "-b", "topic")
    assert main(["self-update", "--dry-run"]) == EXIT_UNPLANNABLE
    assert "branch 'topic', not main" in capsys.readouterr().err
    repo.upstream("b.txt", "second")
    repo.tag("v1.1.0")
    assert main(["self-update", "--dry-run", "--release"]) == EXIT_OK


def test_a_detached_head_is_refused(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    git(repo.work, "checkout", "-q", "--detach")
    assert main(["self-update", "--dry-run"]) == EXIT_UNPLANNABLE
    assert "detached HEAD" in capsys.readouterr().err


def test_a_non_fast_forward_is_refused_and_nothing_moves(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    commit(repo.work, "local.txt", "local only")
    repo.upstream("b.txt", "second")
    before = repo.head()
    assert main(["self-update", "--yes"]) == EXIT_UNPLANNABLE
    assert "not a fast-forward" in capsys.readouterr().err
    assert repo.head() == before and bootstrap_runs(tmp_path) == 0


def test_the_dry_run_prints_the_plan_and_the_arriving_commits_and_changes_nothing(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.upstream("b.txt", "the newest thing", version="1.1.0")
    before = repo.head()
    assert main(["self-update", "--dry-run"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "fetch origin" in out and "merge --ff-only origin/main" in out and "bootstrap.sh" in out
    assert "1 commit(s) would arrive from origin/main" in out and "the newest thing" in out
    assert "Never touched: apt" in out
    assert repo.head() == before and bootstrap_runs(tmp_path) == 0


def test_a_real_run_fetches_fast_forwards_and_runs_bootstrap(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.upstream("b.txt", "second", version="1.1.0")
    assert main(["self-update", "--yes"]) == EXIT_OK
    out = capsys.readouterr()
    assert repo.head() == git(repo.origin, "rev-parse", "main")
    assert bootstrap_runs(tmp_path) == 1 and "fake bootstrap ran in work" in out.out
    assert "Version before: 1.0.0 (checkout), 1.0.0 (installed)" in out.out
    assert "Version after:  1.1.0 (checkout), 1.1.0 (installed)" in out.out


def test_a_venv_that_still_lags_after_bootstrap_is_a_failure(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.upstream("b.txt", "second", version="1.1.0")
    monkeypatch.setattr(selfupdate, "installed_version_in", lambda root: "1.0.0")
    assert main(["self-update", "--yes"]) == EXIT_FAILED
    assert "installed version still differs" in capsys.readouterr().err


def test_the_run_is_teed_to_the_run_log(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.upstream("b.txt", "second")
    assert main(["self-update", "--yes"]) == EXIT_OK
    logs = runlog.list_runs(runlog.logs_dir(None))
    assert logs and logs[0].command == "self-update" and logs[0].result == "ok"
    text = logs[0].path.read_text()
    assert "merge --ff-only origin/main" in text and "fake bootstrap ran" in text
    assert "exit=0" in text


def test_an_up_to_date_checkout_still_runs_bootstrap_but_does_not_merge(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["self-update", "--yes"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "already has origin/main; only bootstrap would run" in out
    assert not [ln for ln in out.splitlines() if ln.startswith("$ ") and "merge" in ln]
    assert bootstrap_runs(tmp_path) == 1


def test_declining_the_confirmation_changes_nothing(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.upstream("b.txt", "second")
    before = repo.head()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "no")
    assert main(["self-update"]) == EXIT_CONSENT
    assert repo.head() == before and bootstrap_runs(tmp_path) == 0


def test_a_failing_bootstrap_is_reported_and_exits_1(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BOOTSTRAP_FAIL", "1")
    assert main(["self-update", "--yes"]) == EXIT_FAILED
    err = capsys.readouterr().err
    assert "exited 7" in err


def test_release_goes_to_the_newest_tag_not_past_it(repo: Repo, tmp_path: Path) -> None:
    repo.upstream("b.txt", "one")
    repo.tag("v1.1.0")
    repo.upstream("c.txt", "two")
    repo.tag("v1.2.0")
    repo.upstream("d.txt", "three, untagged")
    tagged = git(repo.origin, "rev-parse", "v1.2.0^{commit}")
    assert main(["self-update", "--yes", "--release"]) == EXIT_OK
    assert repo.head() == tagged
    assert repo.head() != git(repo.origin, "rev-parse", "main")


def test_release_with_no_tag_refuses(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["self-update", "--dry-run", "--release"]) == EXIT_UNPLANNABLE
    assert "no v* release tag" in capsys.readouterr().err


def test_the_dry_run_json_is_one_document(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.upstream("b.txt", "second")
    assert main(["self-update", "--dry-run", "--json"]) == EXIT_OK
    doc = json.loads(capsys.readouterr().out)
    assert doc["kind"] == "self-update" and doc["dry_run"] is True
    assert doc["target"] == "origin/main" and len(doc["arriving"]) == 1
    assert doc["steps"][1]["argv"][-3:] == ["merge", "--ff-only", "origin/main"]


def test_a_real_run_is_never_driven_through_json(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["self-update", "--json"]) == EXIT_UNPLANNABLE
    assert json.loads(capsys.readouterr().out)["kind"] == "error"


# -- #311: what --version and the documents say ------------------------------


def test_version_line_when_the_venv_lags(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    repo.upstream("b.txt", "x", version="0.20.0")
    git(repo.work, "pull", "-q")
    monkeypatch.setattr(selfupdate, "installed_version", lambda: "0.19.0")
    assert (
        selfupdate.version_line()
        == "0.20.0 (checkout), 0.19.0 (installed); run `hammunition self-update`"
    )
    assert envelope.engine_version() == "0.20.0"


def test_version_line_is_one_version_when_they_agree(repo: Repo) -> None:
    assert selfupdate.version_line() == "1.0.0"


def test_version_line_outside_a_checkout_is_the_installed_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(selfupdate, "PACKAGE_FILE", tmp_path / "a" / "b" / "c" / "x.py")
    monkeypatch.setattr(selfupdate, "installed_version", lambda: "0.19.0")
    assert selfupdate.version_line() == "0.19.0"
    assert envelope.engine_version() == "0.19.0"


def test_the_cli_version_flag_prints_both(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(selfupdate, "installed_version", lambda: "0.9.0")
    with pytest.raises(SystemExit):
        main(["--version"])
    assert (
        capsys.readouterr().out.strip()
        == "hammunition 1.0.0 (checkout), 0.9.0 (installed); run `hammunition self-update`"
    )


def test_doctor_names_the_lag_with_the_fix_as_argv() -> None:
    checks = run_checks(**HEALTHY, engine_versions=("0.20.0", "0.19.0"))  # type: ignore[arg-type]
    check = next(c for c in checks if c.name == "engine version")
    assert check.status == "warn" and check.fix_argv == ["hammunition", "self-update"]
    assert "0.20.0 (checkout), 0.19.0 (installed)" in check.detail


def test_doctor_is_quiet_when_they_agree_or_there_is_no_checkout() -> None:
    agree = run_checks(**HEALTHY, engine_versions=("0.20.0", "0.20.0"))  # type: ignore[arg-type]
    assert next(c for c in agree if c.name == "engine version").status == "ok"
    none = run_checks(**HEALTHY, engine_versions=(None, "0.20.0"))  # type: ignore[arg-type]
    assert not [c for c in none if c.name == "engine version"]


def test_root_is_refused_before_anything_is_fetched(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert main(["self-update", "--yes"]) == EXIT_UNPLANNABLE
    assert "never as root" in capsys.readouterr().err
    assert bootstrap_runs(tmp_path) == 0
