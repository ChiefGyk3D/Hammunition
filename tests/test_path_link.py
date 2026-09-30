# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``scripts/path-link.sh``: `hammunition` on the PATH, and nothing clobbered.  D-059.

Run against a fake checkout and a scratch $HOME, never the real one.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "path-link.sh"


def _checkout(root: Path) -> Path:
    entry = root / ".venv" / "bin" / "hammunition"
    entry.parent.mkdir(parents=True)
    entry.write_text("#!/bin/sh\n")
    entry.chmod(0o755)
    return root


def _run(
    checkout: Path, home: Path, *, on_path: bool = True, umask: str = "022"
) -> subprocess.CompletedProcess[str]:
    path = f"{home / '.local' / 'bin'}:/usr/bin:/bin" if on_path else "/usr/bin:/bin"
    return subprocess.run(
        ["bash", "-c", f'umask {umask}; exec bash "$0" "$1"', str(SCRIPT), str(checkout)],
        env={"HOME": str(home), "PATH": path},
        capture_output=True,
        text=True,
        check=False,
    )


def test_it_creates_the_link_and_the_directory(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    result = _run(checkout, home)
    link = home / ".local" / "bin" / "hammunition"
    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    assert os.readlink(link) == str(checkout.resolve() / ".venv" / "bin" / "hammunition")


def test_it_is_idempotent(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    _run(checkout, home)
    again = _run(checkout, home)
    assert again.returncode == 0 and "already points at this checkout" in again.stdout


def test_it_refuses_to_replace_a_file_it_did_not_create(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    foreign = home / ".local" / "bin" / "hammunition"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("#!/bin/sh\necho someone else's\n")
    result = _run(checkout, home)
    assert result.returncode == 1
    assert "not a link this script created" in result.stderr
    assert foreign.read_text() == "#!/bin/sh\necho someone else's\n"


def test_it_refuses_to_replace_a_directory(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    occupied = home / ".local" / "bin" / "hammunition"
    occupied.mkdir(parents=True)
    result = _run(checkout, home)
    assert result.returncode == 1
    assert occupied.is_dir() and not occupied.is_symlink()
    assert list(occupied.iterdir()) == []


def test_it_refuses_to_repoint_a_foreign_symlink(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    link = home / ".local" / "bin" / "hammunition"
    link.parent.mkdir(parents=True)
    link.symlink_to("/usr/bin/true")
    result = _run(checkout, home)
    assert result.returncode == 1 and os.readlink(link) == "/usr/bin/true"


def test_a_dangling_foreign_symlink_is_left_alone(tmp_path: Path) -> None:
    """Dangling is not enough to be ours: only a dead *checkout* link is replaced."""
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    link = home / ".local" / "bin" / "hammunition"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "gone" / "hammunition")
    result = _run(checkout, home)
    assert result.returncode == 1
    assert os.readlink(link) == str(tmp_path / "gone" / "hammunition")


def test_another_checkouts_link_is_left_and_the_switch_is_printed(tmp_path: Path) -> None:
    first = _checkout(tmp_path / "Hammunition")
    second = _checkout(tmp_path / "Hammunition-json")
    home = tmp_path / "home"
    _run(first, home)
    result = _run(second, home)
    link = home / ".local" / "bin" / "hammunition"
    assert result.returncode == 1
    assert os.readlink(link) == str(first.resolve() / ".venv" / "bin" / "hammunition")
    assert "ln -sfn" in result.stderr


def test_the_printed_switch_runs_as_printed_from_a_path_with_a_quote(tmp_path: Path) -> None:
    """Final review Minor 6: the switch was single-quoted by hand, so a
    checkout path holding `'` broke the pasted command. Paste it and look."""
    first = _checkout(tmp_path / "Hammunition")
    second = _checkout(tmp_path / "it's Hammunition")
    home = tmp_path / "home"
    _run(first, home)
    result = _run(second, home)
    (line,) = [ln for ln in result.stderr.splitlines() if "ln -sfn" in ln]
    command = line.split("instead: ", 1)[1]
    ran = subprocess.run(["bash", "-c", command], capture_output=True, text=True, check=False)
    assert ran.returncode == 0, ran.stderr
    link = home / ".local" / "bin" / "hammunition"
    assert os.readlink(link) == str(second.resolve() / ".venv" / "bin" / "hammunition")


def test_a_dangling_link_of_ours_is_replaced(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    link = home / ".local" / "bin" / "hammunition"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "deleted-checkout" / ".venv" / "bin" / "hammunition")
    result = _run(checkout, home)
    assert result.returncode == 0, result.stderr
    assert os.readlink(link) == str(checkout.resolve() / ".venv" / "bin" / "hammunition")


def test_a_path_without_local_bin_gets_the_line_to_add(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    result = _run(checkout, tmp_path / "home", on_path=False)
    assert result.returncode == 0
    assert 'export PATH="$HOME/.local/bin:$PATH"' in result.stderr


def test_it_never_touches_shell_rc_files(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text("# mine\n")
    _run(checkout, home, on_path=False)
    assert (home / ".profile").read_text() == "# mine\n"
    created = sorted(p.relative_to(home).as_posix() for p in home.rglob("*"))
    assert created == [".local", ".local/bin", ".local/bin/hammunition", ".profile"]


def test_a_new_local_bin_is_0755_whatever_the_umask(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    _run(checkout, home, umask="077")
    assert stat.S_IMODE((home / ".local" / "bin").stat().st_mode) == 0o755


def test_an_existing_local_bin_keeps_its_mode(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    bindir = home / ".local" / "bin"
    bindir.mkdir(parents=True)
    bindir.chmod(0o700)
    result = _run(checkout, home)
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(bindir.stat().st_mode) == 0o700
    assert "creating" not in result.stdout


def test_every_change_is_announced(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    result = _run(checkout, home)
    bindir = home / ".local" / "bin"
    assert f"creating {bindir}" in result.stdout
    assert f"linking {bindir / 'hammunition'} -> " in result.stdout


def test_a_checkout_without_the_entry_point_changes_nothing(tmp_path: Path) -> None:
    empty = tmp_path / "Hammunition"
    empty.mkdir()
    home = tmp_path / "home"
    result = _run(empty, home)
    assert result.returncode == 1 and "bootstrap.sh" in result.stderr
    assert not (home / ".local").exists()


def test_a_file_at_dot_local_is_refused_before_anything_is_announced(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    home.mkdir()
    (home / ".local").write_text("not a directory\n")
    result = _run(checkout, home)
    assert result.returncode == 1
    assert "creating" not in result.stdout
    assert f"{home / '.local'} exists and is not a directory" in result.stderr
    assert (home / ".local").read_text() == "not a directory\n"


def test_an_exported_cdpath_does_not_redirect_a_relative_checkout(tmp_path: Path) -> None:
    here = _checkout(tmp_path / "work" / "Hammunition")
    decoy = tmp_path / "decoy" / "Hammunition"
    decoy.mkdir(parents=True)
    home = tmp_path / "home"
    result = subprocess.run(
        ["bash", str(SCRIPT), "Hammunition"],
        cwd=here.parent,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin", "CDPATH": str(decoy.parent)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    link = home / ".local" / "bin" / "hammunition"
    assert os.readlink(link) == str(here.resolve() / ".venv" / "bin" / "hammunition")


def test_usage_is_exit_2(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "usage" in result.stderr


def test_the_scripts_parse() -> None:
    for script in (SCRIPT, REPO_ROOT / "bootstrap.sh"):
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr


def test_bootstrap_calls_it() -> None:
    assert 'scripts/path-link.sh" "$here"' in (REPO_ROOT / "bootstrap.sh").read_text()


def _next_steps(checkout: Path, home: Path, *, on_path: bool) -> str:
    """Run bootstrap's closing section alone: the lines it tells you to type."""
    text = (REPO_ROOT / "bootstrap.sh").read_text()
    tail = text[text.index("# --- 6.") :]
    path = f"{home / '.local' / 'bin'}:/usr/bin:/bin" if on_path else "/usr/bin:/bin"
    prelude = 'warn() { printf \'%s\\n\' "$*" >&2; }\nhere="$1"\n'
    result = subprocess.run(
        ["bash", "-c", prelude + tail, "bootstrap-tail", str(checkout)],
        env={"HOME": str(home), "PATH": path},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_bootstrap_prints_bare_hammunition_only_when_the_shell_finds_it(
    tmp_path: Path,
) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    assert _run(checkout, home).returncode == 0
    found = _next_steps(checkout, home, on_path=True)
    assert "\n  hammunition install station --dry-run\n" in found
    # ~/.local/bin not on PATH yet: "hammunition" would be "command not found".
    missing = _next_steps(checkout, home, on_path=False)
    full = str(checkout.resolve() / ".venv" / "bin" / "hammunition")
    assert f"\n  {full} install station --dry-run\n" in missing
    assert "\n  hammunition " not in missing


def test_bootstrap_prints_the_full_path_when_the_link_was_refused(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    bindir = home / ".local" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "hammunition").write_text("#!/bin/sh\n")
    (bindir / "hammunition").chmod(0o755)
    assert _run(checkout, home).returncode == 1
    out = _next_steps(checkout, home, on_path=True)
    assert "\n  hammunition " not in out
    assert str(checkout.resolve() / ".venv" / "bin" / "hammunition") in out
