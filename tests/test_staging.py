# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Converters run as the operator in their staging directory.  D-061."""

from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import BackendError
from hammunition.backends.staging import ROOT_NO_OPERATOR, Staging, staging_refusal
from hammunition.backends.verified import PrefixWriter, digest_of

#: A fixed non-root operator, whoever runs the suite.
OPERATOR = pwd.struct_passwd(("operator", "x", 4242, 4242, "", "/nonexistent", "/bin/sh"))
#: The engine as an ordinary account, whoever runs the suite: CI runs as root,
#: where an unnamed operator outside any home is a refusal (the root tests).
NOT_ROOT = 4242


class Recorder:
    """``subprocess`` under root, faked: records each call and its drop, then
    runs it for real without the drop (a test cannot setgroups)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        real_popen = subprocess.Popen

        def strip(kwargs: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in kwargs.items() if k not in ("user", "group", "extra_groups")}

        def run(argv: list[str], **kwargs: Any) -> Any:
            self.calls.append((list(argv), kwargs))
            # Not the real subprocess.run: it calls Popen, patched below, and
            # would record itself a second time without the drop.
            kept = strip(kwargs)
            text = kept.pop("text", False)
            kept.pop("check", None)
            kept.pop("capture_output", None)
            with real_popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, **kept
            ) as proc:
                out, err = proc.communicate()
            return subprocess.CompletedProcess(argv, proc.returncode, out, err)

        def popen(argv: list[str], **kwargs: Any) -> Any:
            self.calls.append((list(argv), kwargs))
            return real_popen(argv, **strip(kwargs))

        monkeypatch.setattr("hammunition.backends.staging.subprocess.run", run)
        monkeypatch.setattr("hammunition.backends.staging.subprocess.Popen", popen)

    def dropped(self) -> bool:
        return bool(self.calls) and all(
            k.get("user") == OPERATOR.pw_uid
            and k.get("group") == OPERATOR.pw_gid
            and k.get("extra_groups") == []
            for _, k in self.calls
        )


def _as_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home" / "operator"
    home.mkdir(parents=True)
    operator = pwd.struct_passwd((*OPERATOR[:5], str(home), OPERATOR.pw_shell))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: operator)
    monkeypatch.setattr(pwd, "getpwall", lambda: [operator])


def test_not_root_runs_in_place_with_env_c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Recorder(monkeypatch)
    staging = Staging(tmp_path / "staging", euid=NOT_ROOT, environ={"JAVA_OPTS": "-Xmx4000m"})
    assert staging.prepare(tmp_path / "staging" / "sub") is None
    result = staging.run(["sh", "-c", 'printf %s "$JAVA_OPTS" > out'], cwd=tmp_path / "staging")
    assert result.returncode == 0
    assert (tmp_path / "staging" / "out").read_text() == "-Xmx4000m"
    argv, kwargs = fake.calls[-1]
    assert argv[:4] == ["env", "-C", str(tmp_path / "staging"), "JAVA_OPTS=-Xmx4000m"]
    assert "user" not in kwargs and "cwd" not in kwargs


def test_under_root_every_operation_is_dropped_to_the_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    fake = Recorder(monkeypatch)
    directory = tmp_path / "home" / "operator" / "staging"
    staging = Staging(directory, owner="operator", euid=0)
    assert staging.prepare() is None
    staging.run(["sh", "-c", "printf data > out.part"], cwd=directory)
    staged = directory / "out.part"
    digest = staging.digest(staged)
    assert digest == digest_of(staged)
    dest = tmp_path / "prefix" / "out"
    staging.publish(staged, dest, digest=digest, writer=PrefixWriter(privileged=False, euid=0))
    staging.remove_tree(directory)
    assert dest.read_text() == "data"
    assert not directory.exists()
    assert fake.dropped()
    assert all("cwd" not in k for _, k in fake.calls)


def test_under_root_a_symlinked_staging_directory_is_refused_before_anything_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    fake = Recorder(monkeypatch)
    target = tmp_path / "sudoers.d"
    target.mkdir()
    link = tmp_path / "home" / "operator" / "staging"
    link.symlink_to(target)
    refusal = Staging(link, owner="operator", euid=0).prepare()
    assert refusal is not None and "symlink" in refusal
    assert fake.calls == []


def test_an_empty_or_missing_output_has_no_digest(tmp_path: Path) -> None:
    staging = Staging(tmp_path, euid=NOT_ROOT)
    (tmp_path / "empty").write_bytes(b"")
    assert staging.digest(tmp_path / "empty") is None
    assert staging.digest(tmp_path / "missing") is None


def test_a_file_changed_after_hashing_is_not_published(tmp_path: Path) -> None:
    staging = Staging(tmp_path, euid=NOT_ROOT)
    staged = tmp_path / "out.part"
    staged.write_text("before")
    digest = staging.digest(staged)
    assert digest is not None
    staged.write_text("after")
    dest = tmp_path / "prefix" / "out"
    with pytest.raises(Exception, match="does not match"):
        staging.publish(staged, dest, digest=digest, writer=PrefixWriter(privileged=False))
    assert not dest.exists()


def test_a_missing_program_is_a_result_not_an_exception(tmp_path: Path) -> None:
    result = Staging(tmp_path, euid=NOT_ROOT).run(["hammunition-no-such-program"], cwd=tmp_path)
    assert result.returncode != 0


def test_staging_refusal_names_a_regular_file(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("")
    assert "not a directory" in (staging_refusal(tmp_path / "f") or "")
    assert staging_refusal(tmp_path / "absent") is None


# maptool writes fixed-name temporary files into its working directory, so two
# conversions sharing one crash each other: two parallel runs segfaulted on
# 2026-09-28. Every conversion gets its own directory, at a stable path so the
# next run clears a crashed run's leftovers, and a run is refused rather than
# started in a directory another run -- this process or another -- is using.


def test_each_conversion_gets_its_own_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fake_tools import calls, install_fakes

    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"converter": 'printf "%s" "$1" > scratch.tmp'}
    )
    staging = Staging(tmp_path / "staging", euid=NOT_ROOT)
    first, second = staging.workdir("region-a"), staging.workdir("region-b")
    assert first != second
    assert first == staging.directory / "region-a.work"
    assert staging.workdir("region-a") == first
    assert staging.prepare(first, second) is None
    assert staging.run(["converter", "a"], cwd=first).returncode == 0
    assert staging.run(["converter", "b"], cwd=second).returncode == 0
    assert (first / "scratch.tmp").read_text() == "a"
    assert (second / "scratch.tmp").read_text() == "b"
    assert [where for where, _ in calls(log)] == [str(first), str(second)]


def test_a_crashed_runs_leftovers_are_cleared_before_the_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fake_tools import install_fakes

    install_fakes(monkeypatch, tmp_path / "bin", {"converter": "printf new > scratch.tmp"})
    staging = Staging(tmp_path / "staging", euid=NOT_ROOT)
    work = staging.workdir("region")
    work.mkdir(parents=True)
    (work / "scratch.tmp").write_text("stale")
    (work / "split").mkdir()
    (work / "split" / "63240001.osm.pbf").write_text("stale")
    staging.remove_tree(work)
    assert staging.prepare(work) is None
    assert staging.run(["converter"], cwd=work).returncode == 0
    assert sorted(p.name for p in work.iterdir()) == ["scratch.tmp"]
    assert (work / "scratch.tmp").read_text() == "new"


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "../escape", "a\0b"])
def test_a_working_directory_name_is_one_plain_component(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        Staging(tmp_path, euid=NOT_ROOT).workdir(name)


def test_a_run_in_a_directory_another_process_holds_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl

    from fake_tools import calls, install_fakes

    log = install_fakes(monkeypatch, tmp_path / "bin", {"converter": "true"})
    staging = Staging(tmp_path / "staging", euid=NOT_ROOT)
    work = staging.workdir("region")
    assert staging.prepare(work) is None
    lock = work.with_name(work.name + ".lock")
    with lock.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        refused = staging.run(["converter"], cwd=work)
    assert refused.returncode == 125
    assert str(work) in refused.stderr and "another conversion" in refused.stderr
    assert calls(log) == []
    assert staging.run(["converter"], cwd=work).returncode == 0
    assert len(calls(log)) == 1


def test_a_second_run_in_a_busy_working_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    import time

    from fake_tools import calls, install_fakes

    release = tmp_path / "release"
    log = install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {
            "converter": (
                f'n=0; while [ ! -e "{release}" ] && [ $n -lt 1000 ]; '
                "do sleep 0.01; n=$((n+1)); done"
            )
        },
    )
    staging = Staging(tmp_path / "staging", euid=NOT_ROOT)
    work = staging.workdir("region")
    assert staging.prepare(work) is None
    results: list[int] = []
    first = threading.Thread(
        target=lambda: results.append(staging.run(["converter"], cwd=work).returncode)
    )
    first.start()
    try:
        deadline = time.monotonic() + 10
        while not calls(log) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert calls(log), "the first run never started"
        second = staging.run(["converter"], cwd=work)
        assert second.returncode == 125 and str(work) in second.stderr
    finally:
        release.write_text("")
        first.join(timeout=15)
    assert results == [0]
    assert len(calls(log)) == 1
    # Released: the directory can be used again.
    assert staging.run(["converter"], cwd=work).returncode == 0


def test_a_converters_own_stderr_is_kept_and_the_lock_is_quiet(tmp_path: Path) -> None:
    staging = Staging(tmp_path, euid=NOT_ROOT)
    result = staging.run(["sh", "-c", "echo oops >&2; exit 3"], cwd=tmp_path)
    assert result.returncode == 3
    assert result.stderr == "oops\n"


def test_under_root_the_operator_gets_a_minimal_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    monkeypatch.setenv("HAMMUNITION_ROOT_SECRET", "root-only")
    monkeypatch.setenv("HOME", "/root")
    monkeypatch.setenv("LANG", "C.UTF-8")
    fake = Recorder(monkeypatch)
    directory = tmp_path / "home" / "operator" / "staging"
    staging = Staging(directory, owner="operator", euid=0, environ={"JAVA_OPTS": "-Xmx4000m"})
    assert staging.prepare() is None
    staging.run(["sh", "-c", "env > seen"], cwd=directory)
    seen = dict(
        line.split("=", 1) for line in (directory / "seen").read_text().splitlines() if "=" in line
    )
    assert "HAMMUNITION_ROOT_SECRET" not in seen
    assert seen["HOME"] == str(tmp_path / "home" / "operator")
    assert seen["USER"] == seen["LOGNAME"] == "operator"
    assert seen["LANG"] == "C.UTF-8"
    assert seen["JAVA_OPTS"] == "-Xmx4000m"
    assert seen["PATH"] == os.environ["PATH"]
    assert all(k["env"]["HOME"] == seen["HOME"] for _, k in fake.calls)
    assert fake.dropped()


def test_under_root_with_no_owner_the_operator_is_found_from_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    fake = Recorder(monkeypatch)
    directory = tmp_path / "home" / "operator" / "staging"
    staging = Staging(directory, euid=0)
    assert staging.drop() == (OPERATOR.pw_uid, OPERATOR.pw_gid)
    assert staging.prepare() is None
    assert staging.run(["true"], cwd=directory).returncode == 0
    assert fake.dropped()


def _owned_by(monkeypatch: pytest.MonkeyPatch, uid: int) -> None:
    """Every path reads as owned by *uid*: a test cannot chown to root, and
    under ``unshare -r`` everything the suite made already reads as root's."""
    monkeypatch.setattr("hammunition.backends.staging._owner_uid", lambda path: uid)


def test_under_root_with_no_operator_a_root_owned_directory_is_worked_as_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    _owned_by(monkeypatch, 0)
    fake = Recorder(monkeypatch)
    directory = tmp_path / "root" / ".cache" / "staging"
    staging = Staging(directory, euid=0, environ={"JAVA_OPTS": "-Xmx4000m"})
    assert staging.drop() is None
    assert staging.who() == ROOT_NO_OPERATOR == "as root: no operator"
    assert staging.prepare() is None
    work = staging.workdir("region")
    assert staging.prepare(work) is None
    assert staging.run(["sh", "-c", "printf data > out.part"], cwd=work).returncode == 0
    staged = work / "out.part"
    digest = staging.digest(staged)
    assert digest == digest_of(staged)
    dest = tmp_path / "prefix" / "out"
    staging.publish(staged, dest, digest=digest, writer=PrefixWriter(privileged=False, euid=0))
    assert dest.read_text() == "data"
    staging.remove_tree(work)
    assert not work.exists()
    assert fake.calls and all("user" not in k and "env" not in k for _, k in fake.calls)


def test_under_root_with_no_operator_a_cwd_outside_the_staging_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    _owned_by(monkeypatch, 0)
    fake = Recorder(monkeypatch)
    staging = Staging(tmp_path / "root" / ".cache" / "staging", euid=0)
    result = staging.run(["true"], cwd=tmp_path / "home" / "operator")
    assert result.returncode == 125 and "outside" in result.stderr
    assert fake.calls == []


def test_under_root_with_no_operator_a_symlink_on_the_way_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    _owned_by(monkeypatch, 0)
    fake = Recorder(monkeypatch)
    (tmp_path / "real").mkdir()
    (tmp_path / "cache").symlink_to(tmp_path / "real")
    refusal = Staging(tmp_path / "cache" / "staging", euid=0).prepare()
    assert refusal is not None and "symlink" in refusal
    assert fake.calls == []


def test_under_root_with_nobody_to_drop_to_nothing_runs_as_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)
    _owned_by(monkeypatch, 4242)
    fake = Recorder(monkeypatch)
    directory = tmp_path / "elsewhere" / "staging"
    staging = Staging(directory, euid=0)
    assert staging.drop() is None
    refusal = staging.prepare()
    assert refusal is not None and "as root" in refusal and str(directory) in refusal
    result = staging.run(["true"], cwd=directory)
    assert result.returncode == 125 and "as root" in result.stderr
    (tmp_path / "elsewhere").mkdir()
    staged = tmp_path / "elsewhere" / "out"
    staged.write_text("data")
    assert staging.digest(staged) is None
    with pytest.raises(BackendError, match="as root"):
        staging.publish(
            staged,
            tmp_path / "prefix" / "out",
            digest="0" * 64,
            writer=PrefixWriter(privileged=False, euid=0),
        )
    staging.remove_tree(staged)
    assert staged.exists()
    assert fake.calls == []


def test_under_root_an_owner_with_no_account_is_a_refusal_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_root(monkeypatch, tmp_path)

    def missing(name: str) -> pwd.struct_passwd:
        raise KeyError(name)

    monkeypatch.setattr(pwd, "getpwnam", missing)
    fake = Recorder(monkeypatch)
    refusal = Staging(tmp_path / "home" / "operator" / "s", owner="ghost", euid=0).prepare()
    assert refusal is not None and "ghost" in refusal
    assert fake.calls == []
