<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Reticulum core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Reticulum, LXMF and NomadNet as hash-pinned per-user virtualenvs with one shared instance per operator, a `mesh` profile, an `rnode` hardware entry and a guide, with every claim the guide makes read from a program, a socket or a log.

**Architecture:** Three `method: venv` catalog units (`rns`, `lxmf`, `nomadnet`) from PyPI, because no archive on any target carries them. `rns` carries one plain systemd *user* service, `hammunition-rnsd`, so that one shared instance owns the interfaces for every Reticulum program an operator runs. Two small engine changes are needed first and are done test-first: a user service's `exec` may start `{venv}/...`, and a venv block may state its licence on the plan line. The engine writes no Reticulum configuration, and uninstall leaves the operator's identities.

**Tech Stack:** Python 3.11+ (pydantic manifests, pytest, `mypy --strict`, ruff), YAML catalog, MkDocs 1.6.1 with Material (`--strict`), rootless Podman for the Debian 13 container measurement.

**Spec:** `docs/superpowers/specs/2026-10-03-reticulum-core-design.md` (binding), with the maintainer's rulings after it (binding): `hammunition-rnsd` is **enabled at install**; the `mesh` profile **includes** `python3-meshtastic` and `gtk-meshtastic-client`; `rnsh` is exposed from the `rns` unit; `nomadnet` is `GPL-3.0-only` by its shipped text. Evidence: `docs/reference/mesh-inventory.md` and `docs/reference/mesh-venv-closures.txt` (PR #283). Tracking issue #105.

## Global Constraints

Every task's requirements include this section. Values are copied from the spec and the inventory.

- **Units.** `rns` 1.5.6, `lxmf` 1.2.0, `nomadnet` 1.4.4: each `method: venv`, `python: ">=3.11"`, requirements one `name==version  --hash=...` line per package copied from `docs/reference/mesh-venv-closures.txt` (uv 0.12.23, 2026-10-03, `--python-platform x86_64-unknown-linux-gnu --python-version 3.11 --generate-hashes`; hashes cover every file PyPI lists, so one pin set verifies on arm64): `rns` 5 packages / 165 hashes, `lxmf` 6 / 167, `nomadnet` 11 / 196. All three pin the same `rns` and are bumped as a set.
- **Exposed commands.** `rns`: `rnsd`, `rnstatus`, `rnpath`, `rnprobe`, `rnid`, `rncp`, `rnx`, `rnsh`, `rnodeconf`. `lxmf`: `lxmd`. `nomadnet`: `nomadnet`. **No separate `rnsh` unit** (the PyPI `rnsh` would collide on the name).
- **The service.** Name `hammunition-rnsd`; `exec` `["{venv}/bin/rnsd", "--service"]`; `restart: on-failure`; no `when_station` (Reticulum needs no station value, so D-035 defers nothing); **enabled at install** (the engine does that for every plain service, and it starts at the next login). `lxmd` is not a service.
- **Licence.** `rns` and `lxmf` carry the Reticulum License (MIT plus two use restrictions, not OSI) under D-033's shape (as LinBPQ is): fetched from PyPI, never mirrored or vendored, the terms printed on the plan line and quoted on the page, never judged (D-021). **No consent gate**: nothing transmits until the operator attaches and configures a radio. `nomadnet` is `GPL-3.0-only` by its shipped text, and its page notes the wheel's MIT classifier disagrees.
- **The engine writes no Reticulum configuration.** `~/.reticulum/config` is created by `rnsd` under the operator's account. Uninstall removes the service, the venvs and the wrappers and leaves `~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd` and `~/.rnsh`, and says so.
- **Profile.** `mesh`: `stage: post-1.0`, members `rns`, `lxmf`, `nomadnet`, `python3-meshtastic`, `gtk-meshtastic-client`, the four required `ProfileDocumentation` fields and the six newcomer fields (`who_for`, `hardware_assumed`, `footprint_short`, `excludes_short`, `goals`, `first_ten_minutes`), in no default.
- **Hardware.** `rnode`: class `badgelife`, no udev symlink (D-028), `maintainer_verified` unset (D-027), and no identifier it cannot source.
- **The guide.** `docs/guides/mesh-and-reticulum.md`, all thirteen sections, every command copy-pasteable, placeholders `N0CALL` and `FN31pr` only, the Part 97 note worded as disclosure and never as a ruling, ending in *What is measured, and what is not*.
- **Decision number.** D-080 (D-079 is held by the unmerged branch `copilot/fix-issue-96`); confirm against `origin/main` in Task 9.
- **Out, by name.** Sideband, Reticulum MeshChat, `meshtasticd`, MeshCore, any TAK software, any Reticulum configuration writer, any claim that a LoRa link was made.
- **Never** put a callsign, grid square, hostname, serial or employer name in any file, commit, log excerpt or output pasted into the repository. Do not paste tool output that prints a real station. The container logs contain only throwaway accounts and hashes.
- **Process.** Everything under `nice -n 19`. Never launch a GUI. Work in the worktree `/home/chiefgyk3d/src/Hammunition-reticulum` on branch `reticulum-core`; never touch `/home/chiefgyk3d/src/Hammunition`'s checkout. Test first, and see each test fail for the stated reason before writing the code. Every task ends green and committed; do not `git add` a path the commit message does not claim (`scripts/check_commit_claims.py` runs as the commit-msg hook), and use `git add -A` only when `git status --short` lists nothing but this task's files (otherwise add by name). End every commit message with a blank line and `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` (or the attribution line the executing session is given). A pull request is merged by the maintainer, not by the branch's author.
- **Gates** (from the worktree root; mypy and the CLI need `PYTHONPATH=src`, pytest gets it from `pyproject.toml`): `nice -n 19 .venv/bin/ruff check .`, `nice -n 19 .venv/bin/ruff format --check .` (it also formats Python fences in Markdown outside `docs/superpowers`), `PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict`, `python3 scripts/check_doc_links.py`, and the suite. Capture a gate to a log and test its exit status; never `gate | grep && push`. A run of the suite as root in an unshared namespace must clear `USER`, `SUDO_USER` and `LOGNAME` and use a throwaway `HOME` (Task 12 gives the command): the engine's per-user directories follow `$USER` when running as root, and six tests would otherwise write into the real `~/.config/hammunition/`.

## Review Focus

The five input classes or failure modes the spec implies but no ready-made test exercises, most likely first. Each is pinned to the task that owns the code.

1. **Two laptops on one network see no peers.** The AutoInterface needs link-local IPv6 and a network that passes multicast between its devices; a firewall, an access point that isolates its clients or a very cheap ISP router stops it silently. Expected: an entry that lists the checks in order and names the TCP fallback, a guide that links to it, and `Peers : 1 reachable` shown on both machines when it works. Pinned: Task 7 (`test_each_symptom_has_an_entry_an_index_line_and_a_link_from_the_guide[reticulum-autointerface]`) and Task 11 (`check_pair.sh`).
2. **Another Reticulum program already owns the shared instance** (Sideband, MeshChat, a hand-started `rnsd`, or another account on the machine: the instance is a machine-wide abstract socket). Expected: the service neither fails nor loops, and the log line it prints is quoted verbatim where the operator will search for it. Pinned: Task 3 (`test_the_unit_file_runs_the_operators_venv_and_cannot_loop_forever`, `test_the_shared_instance_is_one_plain_user_service`), Task 7 (`test_the_second_instance_symptom_is_quoted_the_same_everywhere`) and Task 11 (the second-`rnsd` and other-account checks).
3. **`rnodeconf` cannot open the board's port** (not in `dialout`, a session that predates the group, a parked device, another program holding it). Expected: the entry names each cause and the command that fixes it, and the `rnode` entry inherits `dialout` instead of overriding it. Pinned: Task 6 (`test_an_rnode_inherits_dialout_so_rnodeconf_can_open_the_port`) and Task 7 (the `rnodeconf-port` entry).
4. **The three venvs drift to different `rns` versions** (a bump of one unit alone): a client and the shared instance would speak different protocol versions. Expected: the suite fails, naming the unit and both versions. Pinned: Task 4 and Task 5 (`test_every_reticulum_venv_pins_the_same_rns`, falsified in Task 4).
5. **Uninstall removes the operator's identity or configuration.** `~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd` and `~/.rnsh` hold keys; deleting one gives the operator a new address. Expected: only the service, the venvs, the wrappers and the menu entry go, and the guide says what stays and how to back it up. Pinned: Task 3 (`test_uninstall_takes_the_service_and_never_the_operators_identity`), Tasks 4 and 5 (`config_files` and `system_modifications` empty, the pages' wording) and Task 11 (`check_single.sh`: four identity directories left).

A sixth case the engine owns is pinned in Task 1: an operator's home path with a character a unit file cannot carry (whitespace, `%`, `;`, a quote) defers the service by name.

## What this plan changes from the spec, each because it was measured or read

The spec is binding where it is silent about the engine; where reading the engine or measuring a program showed it assumed something false, the plan follows the evidence and says so, here and in D-080:

| The spec said | What is true | Where handled |
|---|---|---|
| `{venv}` is substituted in `user_services` exec as in launchers | It is not; `exec[0]` must be absolute or `{python}` | Task 1 |
| The licence is named on the plan line (a `license:` field) | No manifest field exists for it on a venv block, and `note` is read by no plan line | Task 2 |
| `listens: tcp 127.0.0.1:37428` | `rnsd` binds the abstract Unix sockets `@rns/<name>` and `@rns/<name>/rpc` and **no TCP port** (measured on Parrot and in Debian 13 containers) | Task 3; no `listens` |
| `restart_prevent_exit_status` unless the inventory finds an exit code to refuse | A second `rnsd` does not exit; it attaches to the first | Task 3, settled in Task 11 |
| "opens no listening socket on a routable address" | UDP 29716 on a multicast address and 29717 and 42671 on the link-local address (upstream says 29716 and 42671) | Tasks 7 and 11 |
| `rnode`: `status: supported`, identifiers from the sweep | Neither Reticulum's manual nor `RNode_Firmware`'s `Boards.h` names a USB id, and the catalog's own test refuses `supported` without one | Task 6; `untested`, none |
| The manual lists public community entry points | It recommends against a pasted list and points to `directory.rns.recipes` and `rmap.world` | Task 7; the manual's own example only |
| `menu_title` on the NomadNet launcher | `menu_title` is the manifest-level field for a *generated* entry; a launcher uses `title` | Task 5 |
| The per-PR `check_pin_reviews.py --only` covers the three manifests | It resolves git pins only; these units have none | Task 12; `update --upstream` is the check that applies |
| Uninstall "leaves `~/.reticulum` in place, saying so" | The uninstall output lists only what it removed; no manifest field prints a "left in place" note | The page, the guide and D-080 say so; a printed note is a new manifest field, for the maintainer to decide |
| "enabled at install" | A plain service is enabled and `try-restart`ed; it starts at the next login | Tasks 3 and 7 say so, and give `systemctl --user start` |

## File Structure

| File | Responsibility |
|---|---|
| `src/hammunition/manifest/schema.py` | `UserService` accepts `{venv}`; `PackageManifest` refuses `{venv}` with no venv block; `VenvInstall` gains `licence` and `licence_url` |
| `src/hammunition/userservice.py` | `service_venv_dir`; `{venv}` filled where `{python}` is |
| `src/hammunition/plan.py`, `src/hammunition/backends/venv.py` | pass the operator's venv to the service planner; print the licence on the venv's plan line |
| `catalog/packages/{rns,lxmf,nomadnet}.yaml` | the three units |
| `catalog/hardware/devices/rnode.yaml`, `scripts/gen_hardware_gaps.py` | the hardware entry and its gap-report line |
| `catalog/profiles/mesh.yaml` | the profile |
| `docs/guides/mesh-and-reticulum.md`, `docs/troubleshooting/{running,index}.md`, `docs/guides/index.md`, `docs/reference/cli.md`, `mkdocs.yml` | the guide, four entries, the nav and the CLI line |
| `docs/DECISIONS.md`, `CLAUDE.md`, `docs/SCOPE.md`, `docs/reference/licence-verification.md` | D-080, its table row, the Track C status, the licence evidence |
| `tests/test_user_services_venv.py`, `tests/test_venv_licence.py`, `tests/test_reticulum_catalog.py`, `tests/test_rnode_catalog.py`, `tests/test_mesh_profile.py`, `tests/test_reticulum_docs.py` | one test file per responsibility |
| generated | `docs/packages/*`, `docs/projects.md`, `docs/hardware/*`, `docs/profiles/*`, `docs/reference/{capability-matrix,parity-coverage,hardware-gaps,device-naming,schema}.md`: regenerated by their generators, never edited |

## Task order

Engine first (Tasks 1 and 2: both are needed to *load* the `rns` manifest), then the three units (3 to 5), the hardware entry (6), the guide (7: it links to the unit and hardware pages and the inventory), the profile (8: its first-ten-minutes steps link to the guide), the records (9), a whole-tree regeneration check (10), the container measurement and what it changes in the prose (11), and the changelog, the gates and the push (12). Every task leaves the suite green.

---

## Tasks

### Task 0: Branch prerequisites: main and the inventory PR

**Files:**
- No files: git operations on branch `reticulum-core`.

**Interfaces:**
- Consumes: PR #283's `docs/reference/mesh-inventory.md` and `docs/reference/mesh-venv-closures.txt` (the evidence the units' pins and the guide's links rest on).
- Produces: a branch that contains `origin/main` and the inventory, so every later link check and the pins can be read.

- [ ] **Step 1: Update the branch and read its state**

Never touch `/home/chiefgyk3d/src/Hammunition`'s checkout: this plan lives and runs in the worktree. `.venv` is a symlink to that checkout's virtualenv and is gitignored; the interpreter imports the *worktree's* `src` only because `pyproject.toml` sets `pythonpath = ["src"]` for pytest, so mypy and the CLI need `PYTHONPATH=src` in front (every gate below has it).

Run:

```bash
cd /home/chiefgyk3d/src/Hammunition-reticulum
git pull -q --ff-only origin reticulum-core
git fetch -q origin main mesh-inventory
ln -sfn /home/chiefgyk3d/src/Hammunition/.venv .venv
git status --short
git log --oneline -3
```

Expected: `git status --short` prints nothing; the log's newest commit is the spec (`Spec: fold rnsh into rns, NomadNet is GPL v3 by its shipped text`) or a later commit of this branch.

- [ ] **Step 2: Is the inventory already on main?**

Run:

```bash
git merge-base --is-ancestor origin/mesh-inventory origin/main && echo merged || echo not-merged
```

Expected: `not-merged` while PR #283 is open (as of this plan), `merged` after it lands.

- [ ] **Step 3: Merge main, then the inventory if it is not on main**

Run:

```bash
git merge --no-edit origin/main
git merge-base --is-ancestor origin/mesh-inventory HEAD || git merge --no-edit origin/mesh-inventory
test -f docs/reference/mesh-inventory.md && test -f docs/reference/mesh-venv-closures.txt && echo inventory-present
```

Expected: no conflict (the three-way merge was checked with `git merge-tree` when this plan was written: the two PRs touch `mkdocs.yml` one nav line apart from this plan's lines); the last line is `inventory-present`. A conflict in `mkdocs.yml` is resolved by keeping both nav lines.

- [ ] **Step 4: Record the baseline**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_user_services_generic.py tests/test_venv_backend.py tests/test_docs_generated.py tests/test_site.py -p no:cacheprovider
```

Expected: all pass (a final summary line ending `passed`, with no `failed`): the suite is green before the first change, so any later red is this plan's.

### Task 1: A user service may run a file inside its own unit's virtualenv (`{venv}`)

**Files:**
- Modify: `src/hammunition/manifest/schema.py` (`UserService._check`, a new `PackageManifest` validator)
- Modify: `src/hammunition/userservice.py` (`service_venv_dir`, `_substitute`, `plan_user_services`, `_plan_rig`)
- Modify: `src/hammunition/plan.py` (the one `plan_user_services` call in `resolve`)
- Test: `tests/test_user_services_venv.py` (new)

**Interfaces:**
- Consumes: `hammunition.paths.venv_root(owner) -> Path` (`<XDG data>/hammunition/venvs`, owner-aware under `sudo`) and `VenvInstall` from the schema.
- Produces: `service_venv_dir(manifest: PackageManifest, owner: str | None = None) -> Path | None` and `plan_user_services(manifest, station, devices, *, model_lister=None, interpreter=None, venv_dir: Path | None = None)`; a `UserService.exec` whose first word is `{venv}/...` loads, and a manifest using `{venv}` with no venv install block is refused at load. Tasks 3 to 5 consume it.

- [ ] **Step 1: Why this task exists**

The spec assumed `{venv}` is substituted in a user service's `exec` as it is in launchers. It is not: `UserService._check` demands `exec[0]` be an absolute path or `{python}`, and `plan_user_services` fills only `{station.*}` and `{python}`. A venv's path lives in each operator's data directory, so no manifest can write it as an absolute path, and `rns`'s service cannot be declared without this. A sixth case, beyond the five in Review Focus (the operator's home directory has a character a unit file cannot carry: whitespace, `%`, `;`, a quote), is pinned here: the service is deferred by name, never written with a path systemd would split in two.

- [ ] **Step 2: Write the failing test**

Create `tests/test_user_services_venv.py` with exactly this content:

```python
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
```

- [ ] **Step 3: Run it to see it fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_user_services_venv.py -p no:cacheprovider
```

Expected: collection fails with `ImportError: cannot import name 'service_venv_dir' from 'hammunition.userservice'`.

- [ ] **Step 4: Implement it**

Apply this patch from the worktree root:

```bash
git apply <<'PATCH'
--- a/src/hammunition/manifest/schema.py
+++ b/src/hammunition/manifest/schema.py
@@ -2126,21 +2126,26 @@
             raise ManifestError(
                 f"user service name {self.name!r} must be a lowercase unit-file base name"
             )
-        # exec[0] is an absolute path, or the engine placeholder {python} (the
+        # exec[0] is an absolute path, the engine placeholder {python} (the
         # interpreter that rendered the unit, as a launcher embeds the engine
-        # path, #145). Nothing else: a bare name resolves against systemd's own
-        # PATH, not ours.
-        if self.exec[0] != "{python}" and not self.exec[0].startswith("/"):
+        # path, #145), or a file inside the unit's own virtualenv
+        # ({venv}/bin/rnsd). Nothing else: a bare name resolves against
+        # systemd's own PATH, not ours.
+        if (
+            self.exec[0] != "{python}"
+            and not self.exec[0].startswith("/")
+            and not self.exec[0].startswith("{venv}/")
+        ):
             raise ManifestError(
-                f"user service {self.name!r}: exec[0] {self.exec[0]!r} must be an absolute path "
-                f"or {{python}}"
+                f"user service {self.name!r}: exec[0] {self.exec[0]!r} must be an absolute path, "
+                f"{{python}} or a file under {{venv}}/"
             )
         for word in self.exec:
             # A {station.*} reference stands in for a value re-checked after
             # substitution (D-073 §4, §6a); strip it before the word check so a
             # legitimate reference is not mistaken for a metacharacter. {python}
-            # is likewise an engine placeholder, not a shell token.
-            bare = STATION_REF.sub("X", word).replace("{python}", "X")
+            # and {venv} are likewise engine placeholders, not shell tokens.
+            bare = STATION_REF.sub("X", word).replace("{python}", "X").replace("{venv}", "X")
             if any(c in bare for c in _EXEC_FORBIDDEN):
                 raise ManifestError(
                     f"user service {self.name!r}: exec element {word!r} is not one argv word; "
@@ -2532,6 +2537,19 @@
         return self
 
     @model_validator(mode="after")
+    def _user_service_venv_needs_a_venv(self) -> PackageManifest:
+        """``{venv}`` in a service's exec is the unit's own virtualenv; a manifest
+        with no venv block has none to name, and the service would start a path
+        that does not exist."""
+        uses = [svc.name for svc in self.user_services if any("{venv}" in w for w in svc.exec)]
+        if uses and not any(isinstance(b.install, VenvInstall) for b in self.install):
+            raise ManifestError(
+                f"{self.name}: user service {uses[0]!r} runs a file under {{venv}}/ but no "
+                f"install block of this manifest is a venv, so there is no virtualenv to name"
+            )
+        return self
+
+    @model_validator(mode="after")
     def _desktops_are_a_real_list(self) -> PackageManifest:
         """D-060. An empty list would be a unit for no desktop -- never
         installable, and silently so -- and a duplicate is a typo."""
--- a/src/hammunition/userservice.py
+++ b/src/hammunition/userservice.py
@@ -22,9 +22,11 @@
 import re
 from collections.abc import Callable, Mapping, Sequence
 from dataclasses import dataclass
+from pathlib import Path
 from typing import TYPE_CHECKING
 
-from hammunition.manifest.schema import STATION_REF, UserService
+from hammunition.manifest.schema import STATION_REF, UserService, VenvInstall
+from hammunition.paths import venv_root
 from hammunition.rig import RigError, resolve_rig
 from hammunition.station import Station
 
@@ -43,6 +45,7 @@
     "is_ours",
     "plan_user_services",
     "render_unit_file",
+    "service_venv_dir",
 ]
 
 #: The first words of every unit file the engine writes; the catalog unit that
@@ -187,10 +190,22 @@
     return all(facts.get(key) == value for key, value in conditions.items())
 
 
-def _substitute(word: str, values: Mapping[str, str], interpreter: str) -> str:
-    """Replace every ``{station.*}`` and ``{python}`` in *word*, re-checking the
-    result is one safe argv word. A reference with no value is a bug (the caller
-    decides what is needed before calling); an unsafe result raises."""
+def service_venv_dir(manifest: PackageManifest, owner: str | None = None) -> Path | None:
+    """The virtualenv ``{venv}`` names for *manifest*'s services: where the venv
+    backend puts this unit's environment for *owner* (the operator, never root's
+    home under ``sudo``), or None when the manifest has no venv block."""
+    if not any(isinstance(block.install, VenvInstall) for block in manifest.install):
+        return None
+    return venv_root(owner or None) / manifest.name
+
+
+def _substitute(
+    word: str, values: Mapping[str, str], interpreter: str, venv_dir: Path | None = None
+) -> str:
+    """Replace every ``{station.*}``, ``{python}`` and ``{venv}`` in *word*,
+    re-checking the result is one safe argv word. A reference with no value is a
+    bug (the caller decides what is needed before calling); an unsafe result
+    raises."""
 
     def repl(match: re.Match[str]) -> str:
         key = match.group(1)
@@ -199,6 +214,10 @@
         return values[key]
 
     result = STATION_REF.sub(repl, word).replace("{python}", interpreter)
+    if "{venv}" in result:
+        if venv_dir is None:
+            raise PlanUserServiceError("{venv} is used but this manifest has no venv block")
+        result = result.replace("{venv}", str(venv_dir))
     # A quote or backslash is as much a shell token to systemd as the others;
     # RIG_DEVICE already excludes them, this is defence in depth (review minor).
     if any(c in result for c in " \t\n\r;|&$`%<>\"'\\"):
@@ -223,6 +242,7 @@
     *,
     model_lister: Callable[[], Mapping[int, tuple[int, int]]] | None = None,
     interpreter: str | None = None,
+    venv_dir: Path | None = None,
 ) -> tuple[list[PlannedUserService], list[Deferral], list[str]]:
     """Plan *manifest*'s user services against *station*.
 
@@ -237,6 +257,8 @@
 
     ``interpreter`` fills ``{python}`` in an exec (the loopback filter runs
     under the engine's own interpreter); it defaults to :data:`sys.executable`.
+    ``venv_dir`` fills ``{venv}``, the unit's own virtualenv
+    (:func:`service_venv_dir`).
     """
     import sys
 
@@ -250,8 +272,15 @@
     deferred: list[Deferral] = []
     for svc in manifest.user_services:
         if svc.is_plain:
+            if venv_dir is None and any("{venv}" in word for word in svc.exec):
+                # The loader refuses a manifest with no venv block, so this is a
+                # caller that did not pass service_venv_dir(): a bug, not an
+                # operator's problem, and not something to defer quietly.
+                raise PlanUserServiceError(
+                    f"{svc.name}: {{venv}} is used but no venv directory was given"
+                )
             try:
-                exec_argv = tuple(_substitute(word, {}, python) for word in svc.exec)
+                exec_argv = tuple(_substitute(word, {}, python, venv_dir) for word in svc.exec)
             except PlanUserServiceError as exc:
                 # A home the unit file cannot carry (a space, a `%`): named, not a traceback.
                 deferred.append(
@@ -269,7 +298,7 @@
     if not rig_entries:
         return planned, deferred, []
     rig_planned, deferrals, notes = _plan_rig(
-        manifest, rig_entries, station, devices, model_lister, python
+        manifest, rig_entries, station, devices, model_lister, python, venv_dir
     )
     return planned + rig_planned, deferred + deferrals, notes
 
@@ -313,6 +342,7 @@
     devices: Mapping[str, DeviceManifest | DeviceClass] | None,
     model_lister: Callable[[], Mapping[int, tuple[int, int]]] | None,
     python: str,
+    venv_dir: Path | None = None,
 ) -> tuple[list[PlannedUserService], list[Deferral], list[str]]:
     """The station-driven entries: resolve the rig, defer or skip, render."""
     from hammunition.plan import Deferral
@@ -422,7 +452,7 @@
         return planned, deferrals, notes
 
     for svc in selected:
-        exec_argv = tuple(_substitute(word, values, python) for word in svc.exec)
+        exec_argv = tuple(_substitute(word, values, python, venv_dir) for word in svc.exec)
         filled = _station_sources(svc, res)
         device_path = station.rig_device if svc.binds_to_device else None
         planned.append(_planned(manifest, svc, exec_argv, device_path, filled))
--- a/src/hammunition/plan.py
+++ b/src/hammunition/plan.py
@@ -87,7 +87,7 @@
 from hammunition.state.log import TransactionLog
 from hammunition.state.uninstall import deb_attributed
 from hammunition.station import Station
-from hammunition.userservice import PlannedUserService, plan_user_services
+from hammunition.userservice import PlannedUserService, plan_user_services, service_venv_dir
 
 __all__ = [
     "Blocker",
@@ -1463,7 +1463,9 @@
             # Plain services need nothing; the rig's need the hardware
             # catalog and defer by name without it (D-035) -- decided in
             # plan_user_services, which knows which is which.
-            svc_planned, svc_deferrals, svc_notes = plan_user_services(manifest, station, devices)
+            svc_planned, svc_deferrals, svc_notes = plan_user_services(
+                manifest, station, devices, venv_dir=service_venv_dir(manifest, user or None)
+            )
             user_services.extend(svc_planned)
             deferrals.extend(svc_deferrals)
             notes_early.extend(svc_notes)
PATCH
```

The patch does four things: lets `exec[0]` start `{venv}/` and treats `{venv}` as an engine placeholder in the shell-metacharacter check; refuses, at load, a manifest whose service uses `{venv}` but which has no venv install block; adds `service_venv_dir` (the backend's own path for the operator, never root's home under `sudo`); and fills `{venv}` in `_substitute`, where a path the unit file cannot carry (whitespace, `%`, `;`, a quote) raises the same `PlanUserServiceError` that the plain-service branch already turns into a deferral by name.

- [ ] **Step 5: Run the test to see it pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_user_services_venv.py -p no:cacheprovider
```

Expected: `12 passed`.

- [ ] **Step 6: Run the services suites that must not change**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_user_services_generic.py tests/test_user_services_plan.py tests/test_user_services_schema.py tests/test_user_services_execute.py tests/test_gps_tether_catalog.py tests/test_rig_service_manifest.py -p no:cacheprovider
```

Expected: all pass; the rig service and the GPS tether render byte for byte as before.

- [ ] **Step 7: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict src tests/test_user_services_venv.py
```

Expected: ruff reports `All checks passed!`, `ruff format --check` reports the files already formatted, and mypy reports `Success: no issues found`.

- [ ] **Step 8: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Let a user service run a file inside its own venv

plan_user_services fills {venv} from the operator's venv path, a manifest that
uses {venv} without a venv install block is refused at load, and a home the
unit file cannot carry defers the service by name. Track C, issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 2: A venv block may state its licence on the plan line

**Files:**
- Modify: `src/hammunition/manifest/schema.py` (`VenvInstall`: `licence`, `licence_url`, one validator)
- Modify: `src/hammunition/backends/venv.py` (`_licence_clause`, the pip step's description)
- Modify (generated): `docs/reference/schema.md`
- Test: `tests/test_venv_licence.py` (new)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `VenvInstall.licence: str | None` and `VenvInstall.licence_url: str | None` (both set or neither; https), and a pip step whose description ends `; licence: <licence> (<url>)` when set. Tasks 3 to 5 set them.

- [ ] **Step 1: Why this task exists**

The spec says the licence is named "in the plan line that prints before the confirmation". Only data blocks carry a `licence` the plan prints; a venv block has `note`, which no plan line reads (grep `\.note` in `src/hammunition/plan.py` and `src/hammunition/interface/plan.py`: nothing). The Reticulum License is the one thing an operator must see before confirming, so the venv block gains the same two fields the data blocks have, and the one plan line that installs the venv carries them.

- [ ] **Step 2: Write the failing test**

Create `tests/test_venv_licence.py` with exactly this content:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A venv unit may state its licence on the plan line.  D-033, D-080.

Reticulum is under a licence the operator would not assume. The data blocks
already print theirs beside the size; a venv block had nowhere to say it, and
the `note` field no plan line reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends import Command, VenvBackend
from hammunition.manifest.schema import ManifestError, PackageManifest, VenvInstall

HASHED = (
    "example==1.0 --hash=sha256:1111111111111111111111111111111111111111111111111111111111111111"
)
URL = "https://github.com/markqvist/Reticulum/blob/master/LICENSE"


def _manifest(**block: Any) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "venvunit",
            "version": "1.0",
            "summary": "Fixture for the venv licence suite",
            "categories": ["mesh"],
            "install": [{"install": {"method": "venv", "requirements": [HASHED], **block}}],
            "update": {"probe": {"method": "pypi"}, "strategy": "reinstall"},
            "documentation": {
                "what_it_does": "Exists so the venv backend has a unit to plan.",
                "why_you_want_it": "You do not; the suite does.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _pip_step(m: PackageManifest, tmp_path: Path) -> Command:
    install = m.install[0].install
    assert isinstance(install, VenvInstall)
    backend = VenvBackend(venv_root=tmp_path / "venvs", bin_dir=tmp_path / "bin")
    (step,) = [
        s
        for s in backend.steps(m, install)
        if isinstance(s, Command) and "--require-hashes" in s.argv
    ]
    return step


def test_the_licence_is_on_the_plan_line_that_installs_the_venv(tmp_path: Path) -> None:
    step = _pip_step(_manifest(licence="Reticulum License", licence_url=URL), tmp_path)
    assert step.description.endswith(f"; licence: Reticulum License ({URL})")
    assert "verified against the manifest's sha256 pins" in step.description


def test_a_block_with_no_licence_prints_the_line_it_always_did(tmp_path: Path) -> None:
    step = _pip_step(_manifest(), tmp_path)
    assert step.description == (
        "Install venvunit into its venv — every wheel verified against the manifest's sha256 pins"
    )


def test_a_licence_without_its_url_is_refused() -> None:
    with pytest.raises((ManifestError, ValidationError), match="set together"):
        _manifest(licence="Reticulum License")


def test_a_url_without_its_licence_is_refused() -> None:
    with pytest.raises((ManifestError, ValidationError), match="set together"):
        _manifest(licence_url=URL)


def test_the_licence_url_must_be_https() -> None:
    with pytest.raises((ManifestError, ValidationError), match="licence_url must be https"):
        _manifest(licence="Reticulum License", licence_url="http://example.invalid/LICENSE")
```

- [ ] **Step 3: Run it to see it fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_venv_licence.py -p no:cacheprovider
```

Expected: `4 failed, 1 passed`: the four that pass `licence` fail (`Extra inputs are not permitted`), and the test that a block with no licence prints today's line passes already.

- [ ] **Step 4: Implement it**

Apply this patch from the worktree root:

```bash
git apply <<'PATCH'
--- a/src/hammunition/manifest/schema.py
+++ b/src/hammunition/manifest/schema.py
@@ -998,6 +998,31 @@
             "nothing while reporting success."
         ),
     )
+    licence: str | None = Field(
+        default=None,
+        min_length=2,
+        description=(
+            "The terms the installed software is under, when they are not a "
+            "licence the operator would assume (SPDX where one exists, else the "
+            "publisher's own words). Printed on the plan line that installs the "
+            "venv, before the confirmation, and stated, never adjudicated (D-021, "
+            "D-033). Requires licence_url."
+        ),
+    )
+    licence_url: str | None = Field(
+        default=None,
+        description="Where those terms are stated, on the publisher's site. Requires licence.",
+    )
+
+    @model_validator(mode="after")
+    def _licence_has_its_url(self) -> VenvInstall:
+        if (self.licence is None) != (self.licence_url is None):
+            raise ManifestError(
+                "a venv block's licence and licence_url are set together or not at all"
+            )
+        if self.licence_url is not None and not self.licence_url.startswith("https://"):
+            raise ManifestError(f"licence_url must be https, got {self.licence_url!r}")
+        return self
 
     @model_validator(mode="after")
     def _payload_script_needs_payload(self) -> VenvInstall:
--- a/src/hammunition/backends/venv.py
+++ b/src/hammunition/backends/venv.py
@@ -76,6 +76,14 @@
     return f"wrote {path} -> {target}"
 
 
+def _licence_clause(block: VenvInstall) -> str:
+    """The licence, stated on the plan line that installs the venv (D-033), or
+    nothing for a block that declares none."""
+    if block.licence is None:
+        return ""
+    return f"; licence: {block.licence} ({block.licence_url})"
+
+
 class VenvBackend:
     """Plans venv installs. Steps only — the runner executes them.
 
@@ -145,7 +153,7 @@
                 ),
                 description=(
                     f"Install {manifest.name} into its venv — every wheel verified "
-                    f"against the manifest's sha256 pins"
+                    f"against the manifest's sha256 pins{_licence_clause(block)}"
                 ),
                 requires_root=False,
                 env=dict(block.env),
PATCH
```

- [ ] **Step 5: Run the new and the existing venv tests**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_venv_licence.py tests/test_venv_backend.py -p no:cacheprovider
```

Expected: `17 passed`.

- [ ] **Step 6: Regenerate the schema reference**

Run:

```bash
.venv/bin/python scripts/gen_schema_reference.py
.venv/bin/python scripts/gen_schema_reference.py --check && git diff --stat docs/reference/schema.md
```

Expected: `wrote docs/reference/schema.md`, then the check is silent; the diff is two added table rows (`licence`, `licence_url`) under `VenvInstall`.

- [ ] **Step 7: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict src tests/test_venv_licence.py
```

Expected: ruff and format clean, mypy `Success: no issues found`.

- [ ] **Step 8: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Let a venv block state its licence on the plan line

VenvInstall gains licence and licence_url, set together and https, and the
plan line that installs the venv prints them. Track C, issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 3: The `rns` unit: the stack, the shared instance, the tools

**Files:**
- Create: `catalog/packages/rns.yaml`
- Create: `tests/test_reticulum_catalog.py` (the `rns` cases; Tasks 4 and 5 append to it)
- Modify (generated): `docs/packages/index.md`, `docs/packages/rns.md`, `docs/projects.md`, `docs/reference/capability-matrix.md`, `docs/reference/parity-coverage.md`
- Modify: `README.md` (manifest count)

**Interfaces:**
- Consumes: Task 1's `{venv}` in a service `exec`; Task 2's `licence` and `licence_url` on a venv block.
- Produces: unit `rns` 1.5.6 (nine exposed commands, user service `hammunition-rnsd`) and the test helpers `_unit(name)`, `_venv(name)`, `pinned(unit, project)`, `pinned_projects(unit)`, `hash_count(unit)` that Tasks 4 and 5 use.

- [ ] **Step 1: What this unit is, and what the measurements corrected in the spec**

`rns` is a hash-pinned venv from PyPI (no archive on any of the seven targets carries it: mesh-inventory.md, 2026-10-03). The requirement lines below are the `rns==1.5.6` closure from `docs/reference/mesh-venv-closures.txt`, written one line per package (`name==version  --hash=... --hash=...`) as `artemis.yaml` does, with every hash kept. They were also installed with `pip install --require-hashes` into a fresh virtualenv on Python 3.13.5 on 2026-10-03: five packages, 165 hashes, every one matched.

Three things differ from the spec, each because it was measured: **the service declares no `listens`** (the spec had `tcp 127.0.0.1:37428`; on Linux `rnsd` binds the abstract Unix sockets `@rns/default` and `@rns/default/rpc` and no TCP port, so the declaration would make the plan print a loopback listener that does not exist); **no `restart_prevent_exit_status`** (a second `rnsd` does not exit, it attaches to the first: the spec's conditional is measured, and it is "not set"); and the service **starts at the next login**, not at install, because that is what the engine does for every plain service (enabled plus `try-restart`), which is the maintainer's "enabled at install".

- [ ] **Step 2: Write the failing test**

Create `tests/test_reticulum_catalog.py` with exactly this content:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Reticulum units: `rns`, `lxmf` and `nomadnet`.  Track C, D-080.

Three hash-pinned venvs from PyPI, because no archive on any target carries
any of it (docs/reference/mesh-inventory.md, 2026-10-03). What these tests
hold is what an operator meets: the pins are real and complete, the licence is
said on the plan line, the shared instance is one service the engine renders,
and uninstall never touches the identity and configuration that are the
operator's.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hammunition.backends import Command, VenvBackend
from hammunition.execute import _user_unit_path, user_service_removal_steps
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import PackageManifest, VenvInstall
from hammunition.station import Station
from hammunition.userservice import header_for, plan_user_services

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "packages"
VENV = Path("/home/op/.local/share/hammunition/venvs/rns")


def _unit(name: str) -> PackageManifest:
    return load_catalog(CATALOG)[name]


def _venv(name: str) -> VenvInstall:
    (block,) = _unit(name).install
    assert isinstance(block.install, VenvInstall)
    return block.install


def pinned(unit: str, project: str) -> str:
    """The version `unit` pins `project` to, read from its requirement lines."""
    for line in _venv(unit).requirements:
        match = re.match(rf"{re.escape(project)}==(\S+)", line)
        if match:
            return match.group(1)
    raise AssertionError(f"{unit} does not pin {project}")


def pinned_projects(unit: str) -> set[str]:
    """Every project `unit`'s venv pins: the whole closure, nothing left to float."""
    names: set[str] = set()
    for line in _venv(unit).requirements:
        match = re.match(r"([A-Za-z0-9_.-]+)==", line)
        assert match, f"not a pinned requirement: {line[:40]}"
        names.add(match.group(1))
    return names


def hash_count(unit: str) -> int:
    return sum(line.count("--hash=sha256:") for line in _venv(unit).requirements)


# -- rns ---------------------------------------------------------------------


def test_rns_is_one_complete_hash_pinned_venv() -> None:
    block = _venv("rns")
    assert block.python == ">=3.11"
    assert pinned_projects("rns") == {"cffi", "cryptography", "pycparser", "pyserial", "rns"}
    assert pinned("rns", "rns") == "1.5.6" and _unit("rns").version == "1.5.6"
    for line in block.requirements:
        assert line.count("--hash=sha256:") >= 1, f"unhashed: {line[:40]}"
    # The inventory counted 165 hashes for this closure; fewer means a pin lost
    # files PyPI lists, and an arm64 or Python 3.14 target stops verifying.
    assert hash_count("rns") == 165


def test_rns_exposes_every_tool_an_operator_types_including_the_shell_and_the_flasher() -> None:
    assert _venv("rns").expose == [
        "rnsd",
        "rnstatus",
        "rnpath",
        "rnprobe",
        "rnid",
        "rncp",
        "rnx",
        "rnsh",
        "rnodeconf",
    ]


def test_there_is_no_separate_rnsh_unit() -> None:
    """`rns` 1.5.x installs its own `rnsh`; PyPI's `rnsh` 0.1.7 would be a second
    owner of the same command name (inventory, 2026-10-03)."""
    assert "rnsh" not in load_catalog(CATALOG)


def test_the_licence_is_on_the_plan_line_before_the_confirmation(tmp_path: Path) -> None:
    block = _venv("rns")
    assert block.licence is not None and block.licence.startswith("Reticulum License")
    assert block.licence_url == "https://github.com/markqvist/Reticulum/blob/master/LICENSE"
    backend = VenvBackend(venv_root=tmp_path / "venvs", bin_dir=tmp_path / "bin")
    pip = [
        s
        for s in backend.steps(_unit("rns"), block)
        if isinstance(s, Command) and "--require-hashes" in s.argv
    ]
    assert len(pip) == 1 and "licence: Reticulum License" in pip[0].description


def test_the_shared_instance_is_one_plain_user_service() -> None:
    (svc,) = _unit("rns").user_services
    assert svc.name == "hammunition-rnsd"
    assert svc.exec == ["{venv}/bin/rnsd", "--service"]
    assert svc.restart == "on-failure"
    assert svc.is_plain  # no station value: Reticulum needs none, so nothing defers (D-035)
    # Not a TCP port: measured 2026-10-03, rnsd binds abstract Unix sockets
    # (@rns/default and @rns/default/rpc) and no TCP port. A `listens` entry would
    # print a loopback listener the plan does not have.
    assert svc.listens == []
    # A second rnsd does not exit, it attaches to the first (measured), so there
    # is no exit status to refuse a restart on.
    assert svc.restart_prevent_exit_status == []


def test_the_unit_file_runs_the_operators_venv_and_cannot_loop_forever() -> None:
    planned, deferrals, notes = plan_user_services(_unit("rns"), Station(), None, venv_dir=VENV)
    assert not deferrals and not notes
    (svc,) = planned
    assert svc.unit == "rns"
    assert svc.unit_body.startswith(header_for("rns"))
    assert f"ExecStart={VENV}/bin/rnsd --service\n" in svc.unit_body
    assert "Restart=on-failure" in svc.unit_body
    # A start limit bounds a crash loop: five tries in thirty seconds, then stop.
    assert "StartLimitIntervalSec=30" in svc.unit_body and "StartLimitBurst=5" in svc.unit_body
    assert "RestartPreventExitStatus" not in svc.unit_body


def test_uninstall_takes_the_service_and_never_the_operators_identity(tmp_path: Path) -> None:
    """~/.reticulum holds the operator's identity, interfaces and known destinations.
    The engine did not write them and does not remove them (D-080)."""
    unit = _unit("rns")
    assert unit.config_files == [] and unit.system_modifications == []
    path = _user_unit_path(tmp_path, "hammunition-rnsd")
    path.parent.mkdir(parents=True)
    path.write_text(header_for("rns") + "\n[Service]\nExecStart=/x\n")
    steps = user_service_removal_steps(["hammunition-rnsd"], home=tmp_path, units=["rns"])
    assert steps, "an installed service must be stopped and removed"
    text = " ".join(
        " ".join(
            [
                getattr(s, "description", ""),
                getattr(s, "detail", ""),
                " ".join(getattr(s, "argv", ())),
            ]
        )
        for s in steps
    ).lower()
    assert "hammunition-rnsd" in text
    assert ".reticulum" not in text and ".nomadnetwork" not in text


def test_the_page_says_what_an_operator_will_hit() -> None:
    docs = _unit("rns").documentation
    assert docs.known_problems is not None
    for phrase in (
        "not an OSI licence",
        "~/.reticulum/logfile",
        "starts at your next login",
        "connected to another shared local instance",
        "leaves `~/.reticulum` in place",
    ):
        assert phrase in docs.known_problems, phrase


@pytest.mark.parametrize("unit", ["rns"])
def test_the_unit_is_a_mesh_unit_and_updates_from_pypi(unit: str) -> None:
    manifest = _unit(unit)
    assert manifest.categories == ["mesh"]
    assert manifest.update.probe.method == "pypi"
    assert manifest.depends == ["python3-venv"]
```

Review Focus 4 is pinned across Tasks 4 and 5 (`test_every_reticulum_venv_pins_the_same_rns`), Review Focus 5 here (`test_uninstall_takes_the_service_and_never_the_operators_identity`) and Review Focus 2 here and in Task 7 (`test_the_unit_file_runs_the_operators_venv_and_cannot_loop_forever`, which holds the start limit that bounds a crash loop, and `test_the_page_says_what_an_operator_will_hit`, which holds the symptom's wording on the unit's page).

- [ ] **Step 3: Run it to see it fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: `8 failed, 1 passed`: eight fail with `KeyError: 'rns'` (the unit does not exist); `test_there_is_no_separate_rnsh_unit` passes already, because nothing named `rnsh` exists yet.

- [ ] **Step 4: Write the manifest**

Create `catalog/packages/rns.yaml` with exactly this content:

```yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

name: rns
version: "1.5.6"
summary: Reticulum, encrypted networking over any medium, with its shared instance and the RNode flasher
categories: [mesh]

# ADD, Track C (issue #105; docs/superpowers/specs/2026-10-03-reticulum-core-design.md;
# D-080). Evidence: docs/reference/mesh-inventory.md, measured 2026-10-03.
#
# * Nothing Reticulum is in any apt archive: `rns`, `python3-rns`, `reticulum`
#   and `python3-reticulum` have no candidate on any of the seven targets. So
#   this is a hash-pinned venv, as `artemis` and `pygpsclient` are.
# * The pins are `uv pip compile --python-platform x86_64-unknown-linux-gnu
#   --python-version 3.11 --generate-hashes` from `rns==1.5.6` (uv 0.12.23,
#   2026-10-03). A hash set covers every file PyPI lists for each pinned
#   release, wheels and sdist, so the one set verifies on arm64 as well.
#   Installed with `pip install --require-hashes` into a fresh venv on Python
#   3.13.5 on 2026-10-03: all five packages and all 165 hashes matched, and
#   `ls bin/` shows every script exposed below.
# * `rnsh` is part of `rns` since 1.5.x (`RNS.Utilities.rnsh`). The separate
#   PyPI project `rnsh` 0.1.7 installs a script of the same name from a
#   different package, so there is deliberately no `rnsh` unit: two owners for
#   one command.
# * `rnodeconf` is the RNode flasher. It is installed under D-026, as the means
#   of talking to a device, and it downloads firmware itself; what it checks
#   was not measured, and known_problems says so.
# * Licence: the Reticulum License, which is MIT plus two use restrictions and
#   is not OSI-approved. Carried under D-033's shape, as LinBPQ is: fetched
#   from PyPI at the operator's direction, never mirrored, the terms stated on
#   the plan line and below. docs/reference/licence-verification.md has the
#   file read and the date.
# * The three Reticulum units (`rns`, `lxmf`, `nomadnet`) each own a venv with
#   its own copy of `rns`, and `lxmf` and `nomadnet` each demand `rns>=1.5.5`.
#   They move as a set; tests/test_reticulum_catalog.py fails if they do not.
install:
  - install:
      method: venv
      python: ">=3.11"
      licence: "Reticulum License (MIT plus two use restrictions; not OSI-approved)"
      licence_url: https://github.com/markqvist/Reticulum/blob/master/LICENSE
      requirements:
        - cffi==2.1.1  --hash=sha256:046bfc24911b37851ee1b51aab8bffe713d89c68c6a057b09484ce9fd5f69b4e  --hash=sha256:06c72bb76605a4b0cd0aad6930b69d4baf7dd5d806cfc409b824191099700e66  --hash=sha256:0beceaabe56af686895136a2de78db54ecd8e4046b236b8fd6d6cb61389e9bf2  --hash=sha256:154852545011f779917b11c78db2358d095da62a9a172b78ad0a583ee5adc0d0  --hash=sha256:194cffa889098ced9976c3fc6340305e43f6303657d298da55366907c05c22d6  --hash=sha256:19ee6127ee34de7d83ce3d371ebc5ed91addbdcc39f9ab15ce4eb35a4e534971  --hash=sha256:1a18a57b58cfb21fc28d72e876acf10eaed67a1ed96226f92af4df681d571c4c  --hash=sha256:1aa5645c30469b09530c4ebca77ebf8f17618293c58f8549cb1a543a50236e7d  --hash=sha256:1dea0e4d7d4f11f619fe8c1d76caf49e24405b4b5743c0e3be16a500ecd930c9  --hash=sha256:208f941bb9d18e768138677f0a6d2ce01f590df56043dda1df1535ac57c88517  --hash=sha256:210019b6c7cf07f081b4c54635c8cf744377001350e29cc0f81c4377b4797735  --hash=sha256:246fa40ce8645a614ff682e0b70f37134e460eaf93a775e0cbe3cca585a67a80  --hash=sha256:25792eac27877609e7bb06d42ff88278a6624fff2ba9bbb523c09616b117e80f  --hash=sha256:27350daa11d4f10c540e6e89dada4c54feb7256ad03e9a4dc075ebad7ba360d1  --hash=sha256:28907ab9bfb6aa13184cfc17c6b8e1023c5ab6fd7076d8c20a35e59fe04f8f29  --hash=sha256:2ae64be792b8966f2c69538199728b290e34726562896df1e5dc8ffd8d8188e8  --hash=sha256:31348097ff5bbe827ccc41795d4dd099d9f0625e7def00ee653c137a490c2a6c  --hash=sha256:3143d81e29e1e20a9ce10901ec369012947876596f75a222235965f2b7ae832e  --hash=sha256:3222ba5d678f80a030e6afbcc33dc1ae5cb45facabb61cee2c7016b8432fde48  --hash=sha256:3311ed60d36f83378794e1009ac6258bafbf81f7888b4caa7b35a521e3f95813  --hash=sha256:334644fbac4eff73d985a17a91226df55d0f394160c4cfb880e084c8f7161cac  --hash=sha256:34e261f78cb6ceaaa36f42f2613f4380d94d9c759a9c73c769ee6e0247364632  --hash=sha256:363e05fa78e15116c3c32c210ee36884fd6b9afa6d440e47112c3bd511d64cb6  --hash=sha256:398aff33cee2767e3e781d2554c54bd0dff386bb437581e0d8011fde1a942ec1  --hash=sha256:3d22a20b1fb1632cc72c22f95f7b0d2961c3e1c235f245ba4c606c4771035659  --hash=sha256:42a494cee34437f05546455144f2b5d9ac09b1face62bcfce597d2e521066688  --hash=sha256:42e2f76b9455f5a9a844f770bf3e200ed3da0e15f5df3db9c31fe80b04b3d004  --hash=sha256:42f6930c31dc7f50732c9ae793c2786c7b6b044195967bbdde40bb9be81c4cc0  --hash=sha256:456a61fa52d579ebf9df2e9552ead5129855dbaff6c1e5a9b1bc408809bdc062  --hash=sha256:471cee653ae88de62096552e6d24ccb4a5adb8c8c9f10b5054d0122c15bf2779  --hash=sha256:49cbc70e6542d4ccccb936558d1064a8012541e78f821f955cff24e357776c94  --hash=sha256:4a7c934f7360e8cd64fe9efadcbd10c7c6364f531e432b9a4bf5ccbc9e0e8b50  --hash=sha256:4be96343e422f2dfcd12ab5c9f5aebe03f82f737c6bffeca6830b3875cb44aab  --hash=sha256:4f42141fc14250de6dde5ee7ea4432be017252d91f19c5ad043c084cea629cac  --hash=sha256:507a24c282e0f42f8ed737cf048572cbf580468da5555764a8331735e9c736b6  --hash=sha256:51b31d1c98274844cfd7838ce00bfc27c7423a4dc00fc0772fc3331c2cc90676  --hash=sha256:58acb8ab8e295e6c5ea12f888cbb13cf21511ef2a3303a23f4325c29d17fe5c1  --hash=sha256:5a59cc1c4442bc3d5c703bf720b51138d0bfc173618807c9ee2490a7541dd3d9  --hash=sha256:5bb4e7ea95dcd6a014a6fef62e62467d67d8e582326443f3d68e71d6320a9fcf  --hash=sha256:5c58fe613dc5e5336357eff555824a314d8e43282600435c8d1cb6a7a2fedd13  --hash=sha256:5e7cecbaadb83884793e05828cee59b210b24583b9c7425d0ba6a754fe22eb4e  --hash=sha256:616f097f2fe415bc92a247f02e11f634e1f9e9a83d327e3c915c15089c87869e  --hash=sha256:63bbfd5ded17c4840ac07cd8f1c21ba9d9708141f840b324f422f41b207e3973  --hash=sha256:64faea20f4e2613363a1a9b9c7dd73058f3ecd00133a511e72ad7c511658f527  --hash=sha256:661c298b4821edebead0c91edd2b00374d67ad7c5a1f7a91d4442633b79d6a72  --hash=sha256:68e62fe11f30d5ca8289242866f0a5291402d8529ca2178ab8afc5c9694ae890  --hash=sha256:6a8dddef476fab96d066d578fc88526767b836ab5ab21754e1d5bf3879c31c7c  --hash=sha256:6e192623c49c94421616a5778fba35cf0d5a8d000650c1967ef4448ee5cdd990  --hash=sha256:7225e4514edb64eb6740324353e0da0711954fd8d7da4576755b1c6e09b697cd  --hash=sha256:75f80557d1389eddbd0de2681f6a390a0c5338c31ddaa821381c203fc3fd50d9  --hash=sha256:770de9db11e84213beec501cfcaa013b019820ca881e03344dea5844f7876d94  --hash=sha256:7750c6449dff7864bb9bb27ddfb0267756189201a3afc911d82b3caacd70dfc3  --hash=sha256:7bde5e4cc5c10140859842b9d383af292b22639a4dffb725314baf45968cef80  --hash=sha256:7ce713ace7c0e4520535b42b77eaa742c16dab813978064913e5a3cf82973b41  --hash=sha256:7da0c5eff80f0197f3b3d1232ec5a682a9325f4ae9016a78f5f5ca35f9ced1f5  --hash=sha256:7dbb61fe3a7699468030f71bbe5f8a0e326a151daa91beb11a6fc1f980c55e1c  --hash=sha256:811bd1e21d32de12efca32393a0ab3f5133b54fce9bd44b8bd77ab07da14bf6a  --hash=sha256:8ef53b2de9bcb9197d31854256575d59dbac0cba72ac627bb291ef5eceb74be4  --hash=sha256:937c0052c05a31ca1daf18de3158eed4dbfcb9cc107adbea227728d647be701e  --hash=sha256:9d2055050ea716bd38b7f7f1579c275386646b4894c155a3e2f3cd62ed41b7c6  --hash=sha256:9f8d177621de5cb38ee3e731eda45d421db093ec0739f46a5594babda7987a98  --hash=sha256:a2d7755bef5a12ed488f4ef1f1b69ee9191d7396083b755a5d2295f6edb4768b  --hash=sha256:a48d62ab9d6f4f98c983223a547af44be6ca3691074c31cecced6facd3ba2dc1  --hash=sha256:a4f00aa42f75d6e4595e8866e748cc1705adc0cddfeb2ca86d0d03993d63ba03  --hash=sha256:a6e721d4b0e45d5b65e87534470e67b18dcd092c83f68fba09f152b9cbc061af  --hash=sha256:a730a083190634c65cca36ba5f489531576ebd79bcd5c8e172130f6453127231  --hash=sha256:a931079504ecc49efed7744c476a5c343a92fabf66dec2db95edb1b2fdc770e2  --hash=sha256:aa9511c62d14da7aacc9b4bf51f3f697a621e83b2d6919008243c3aad168eea3  --hash=sha256:ab36d55f9ed2d067327667c2fea18dda018eb628dd6347aa01dda6cf1f5d3836  --hash=sha256:ad2c86c495b899d862ea0f4b42891b8713a3bd45dd4105c7fd51c2a72f39f3a5  --hash=sha256:aeae0e330c9f6acd681f647d46cefd30c29f93e3392882e792e82080c9691399  --hash=sha256:b0431303acaea1089ad4b3e9ce4e6518193def1118d4073ca848635ee4ea2e96  --hash=sha256:b5bdfd1c873d4e093aabc0ca84c4ca6dbc4f752afb5c86f146d9742580c9da2e  --hash=sha256:baed1e86cc735622097354b9d1281406caf42ff42a886d29faa8e8d1630333be  --hash=sha256:c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf  --hash=sha256:c26608d2222fb1e94487e4a387d85f13eb55d5ed725cb25a0c589ac4ee60e7bc  --hash=sha256:c7659f22557c5a0bc4855cd635f55edec690cc008a40768527762cb9fb263455  --hash=sha256:c8c69575568085ba0b1b10c0249d779a214aea6f6522e949a0fc9fb0fcb449d0  --hash=sha256:c8d2c9fd1f2d16f780d15127abb050d13d1a76c03a4bd87d7e4980e45e511e12  --hash=sha256:ca82be1a1d406ecfe1d25dc16cb33488e5a16bf4438c9fb590484ea29d92478b  --hash=sha256:cc572dace3f60ef98d7b12ff411d20f5362feb31a0439eab0085bbfd349982d7  --hash=sha256:d18e5ac0f2f03f4f518d3e23db0f0cad7faa1da8620e9c09461d443bbf6e6692  --hash=sha256:d28630f5854ab07ab1fd4aba756de52326c82e6be15d414b12793f1975048b54  --hash=sha256:d9c275eaacd24aa73f94ffd6de08fc3f932424d8b6c376f4bed7cde376fe7bc3  --hash=sha256:da0e573f9f97159390c89d9f1a9e41908b66d408cc5b58d08cf3847d844c531b  --hash=sha256:dd31f52ea1086513bb9df30f8fcee9b8918323ae067a3d5b78bc826a000712be  --hash=sha256:dddad92b554513a31f272570678ba307fb9f618f05e3d4a5eacafff9eae03e1d  --hash=sha256:df423d40ee8654634421812bc3b196da3f9bd7d32929da813f8394c4348a5358  --hash=sha256:df913725b79db7bcf03448f36b7bf8815363417d5b58deecf9305e3e30f0f21a  --hash=sha256:e0bcb7e0f677f543555d2adff3bf19c05f66cdb4796e5ff602442ab2fe3c4ef7  --hash=sha256:e2d65b31f36619cda3999b78b2aa9632e76b78448e7a56fc4240824200e7c4fc  --hash=sha256:e6e8cff14d6fb0be70a09c0bdc58096f501952d04624ebf867e0e56da2df8960  --hash=sha256:f16c709686a78c727bbbf059f92b0bf41c6fc60deec706d2dc19f529175a6125  --hash=sha256:f24fb43132a4c6b4cb4eb029492919b2db645be6808d738f244fd146c03c32cb  --hash=sha256:f53e442b08449d42821fa4a4fba000095af9f62742a500f978a9f557ec44339a  --hash=sha256:f5cfbc5fe74540d335175b656c725d74d90e3730c626d92575eea35029d9afaa  --hash=sha256:f81b3b8f3d4e343550fa4baa0e479bba9f2d29ce9c2e9b51d1ce1718d7442fcf  --hash=sha256:f8ec5e643a9a937f64e1999eb9f75d072263751912dc5cd06d3c85f8f44be7c3  --hash=sha256:fb92203a88b3d3053034db775110081c49d28be6551923805e039924093761e4  --hash=sha256:fcd22650c908d7b7da162bbfaab594a1227a15d1643a98c68b122ac642fa2264
        - cryptography==50.0.2  --hash=sha256:0ddc924c04591c2811ca024d62ecad4f7f6f08af8939c211438f48a16bd23602  --hash=sha256:0ec5f09541743261e66e291b4a0cbf0fb2997aeaab6d9e9c740b9dba1b58d1c2  --hash=sha256:0ecbc5652bdb6fc9eaf89a7d196e20941adfe812f43bc4ca05d9150496821047  --hash=sha256:1981f1db4630889b9ef7803fadef12b056f428cb6b85c27ba57b774793b6093c  --hash=sha256:1ba34f04897fcdaa73f74145c25f3ec146fbd56593853e88adc2e811303c5f42  --hash=sha256:241449bf940a5d27309bd317e6f9a2af6932113818bb2b8f5c59ddc7ef16da18  --hash=sha256:25784ce8b9621c90c643efb9e1e2162ab3b0224cae446ad5e70e7fcb1ce18b51  --hash=sha256:3dc4fd8058cea1644971207d530e1a03a184a805ffc8ebdddf0599d78a331b81  --hash=sha256:4061c0079120205fb760c58acab6443e217307dcf05e3702cf970e0689972856  --hash=sha256:4a20ce1e5cb4284a86692fdcba7cb8754185c6b2e5c56fcef3751cf451d3cdc2  --hash=sha256:4e81d95e5bafc2d6e34e4bed780e53e4d5b9a2f928573428aa4d35fbec1eb0de  --hash=sha256:58a0c478eeca76fe5e07993c5a0703def34a6dc6a0cda4f5564639b33112ffe7  --hash=sha256:58ddb5a8e3179d12f19e4ea34d2d32e9d63a4baa142c875c1eb59f41b7243acd  --hash=sha256:630ebfea3bf689d075f82316324ff7433dc447fe6bc1bfc76524b74b4a9567d2  --hash=sha256:6f8700550aa1474a91e5dc07049c46f98b423b5b1ddd0483e0b51362eeeaf5be  --hash=sha256:78198641e5be9521beea5aa782bb551a58068d10e6eb04c9c680c1b69f2e7d45  --hash=sha256:79def8d059362e7831389ed3be0ecdf58a89386e1271e35dd9f5af84e81bffd0  --hash=sha256:7a8701d6b584d76e909e3d305b7d126b41439876a5aaf76cddc67fc230eafa2e  --hash=sha256:7afa5a6602a9f29af1f3a2965f831bae7c9d5d597b7cbb716d41ab3b7d89879c  --hash=sha256:7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5  --hash=sha256:7b75de3c8b3be1cdb1052747c929440c3eea46c1bc2cb8a6e3a48388e9b7b452  --hash=sha256:7c6d0330c472d96f6a6afe24d80dfdf15176c33096f0a4397ae4c60f3dd3be48  --hash=sha256:828d49b0ff5a0e3975865571c5d91dbbdd0d38d8289b249a163e9425413a5e05  --hash=sha256:84f964e537f916e2cc85199e5a88742e964939b575ac8598b3f9d6cc416cdaf1  --hash=sha256:85d0d9a31b9098e98534226d5686b47264b95e62ce459dc2e62fdfc809f9fe93  --hash=sha256:87e9ce85beb6b328ba370cc6e6aea483c92617b4c95b1d33a49297eb662bfb04  --hash=sha256:8c71ba2cd31fc93748c38e1b613200ff1c2665cbfd5341fe3a61cfde35a1430e  --hash=sha256:92e665960f25fcdc73725b9cec7a3824f279ba97a98653afe9ffac2e43668f67  --hash=sha256:94e5e9f108ee10471288214d3d233fbfbb492840a8457eb85178d643ddeb32c7  --hash=sha256:9c8402a82ea0dc4ceeab793db05f0fafa8ca139ca34fcde5df0f596103c74107  --hash=sha256:9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079  --hash=sha256:a582ab2ae1d34f67112cadc86702774c9ea4374df6bca6afe672817203c99134  --hash=sha256:a6557e5f38e065ca9fbdaf7cfc7435ecb1d113aa81a022d1b51921ee7432e227  --hash=sha256:a9f7355e6fab51f6c369b86fb7571cffa05edee2c2121e0380a37fb9ac1cd5c1  --hash=sha256:ab50ee449bf968271e820086f10a33d101dd060370abc10bcd22279be2656539  --hash=sha256:ac9ed99d81760c62fe89d5f0815cdfa1ba9a35141cf30f1c2d044f04b4803d2e  --hash=sha256:b13478603dcd0a2479ff8e87e2c19a7d525734686fe3c49542472293a204212d  --hash=sha256:c423ab384a46c4dff7217b2ea5ba2e11cffdeab6441acd04cf65a369caf0366c  --hash=sha256:c5e67125c7dca78d199ec4e116aa93dbb83494808ecbb8211a2cb09b1bf41dbd  --hash=sha256:c71be1cbfa5cd9a41ee452acf1eccd82b2c05950358b106ec8ceb83411d1a020  --hash=sha256:cbc8738fd8526d80f35cb3a40d41f41a2e7030bb3b18b09a6778ef63d291c2fd  --hash=sha256:ce47f66801c20ec6c6632453bb5960fe38939e9306970b48b3a5a26de7745d94  --hash=sha256:d370b8d1dfcdf7130178137f6fbee6140774a1acc6cacefc4b42643ec11d0a3a  --hash=sha256:d38cdff612d06fa6a32840d5e1b1f7a27cee4a349aa9085d94a67789d6bfd408  --hash=sha256:d8947001be83df1394050758ce0e745dd74fb134eef0a4b5124208dfc3a68c37  --hash=sha256:deb9fde5c60e437ee4821bc9bc39ff31b42135c27e1dc61ef0a629389c1de62e  --hash=sha256:dfe9763530994147d9af1def057a5b9658b00e8f8fe8743d144d1e0911c2e454  --hash=sha256:e105ab60406787da31fccc883fc0f733af1efd78f0136a4599692c4083a73d0c  --hash=sha256:e275096ea1e60cc595cda2836fd4a6c725d1125108b868be17f53684d164e2cc  --hash=sha256:edc3342adf8f697fc5f59c887a304356f147b397809440ed64e2fa6af2f50f37  --hash=sha256:ee247f5c245c9a2fe7c8e2214e295918838e44e00a45a6718451e4004219e767  --hash=sha256:eef4c2f3423810b3070ab391f85436d2f8bbfcb286ac15cbc73190b3563b1f1a  --hash=sha256:f21e8a22c8605750c7af886bab299a363721264061b4ac0a30efb73cfd58efc5  --hash=sha256:f265528741e048bce55c3463ed721fb0aa45a5888d8add8cfeccb3035451bbdc  --hash=sha256:f2f9bd7f90c64fe89253f0a2c05e3c4856072660429ce8831b4235bf29403a67  --hash=sha256:f785f6161f202ab04d8ca194158968798e480ca058943907972da5f12e2881e8  --hash=sha256:f9f6143a8c75945eb960d9eb98905a441394abfa24afaae239d514ffb2586480  --hash=sha256:fa8f5efb344d6908a1ce62f4a24e2e5780f825d6f53f5f50ec5ffacac72936cb  --hash=sha256:fdd28f912fccfec1846a94e2e1e8f9b0012f557f0c46fe4f3eb0d7a87afcf90b
        - pycparser==3.0  --hash=sha256:600f49d217304a5902ac3c37e1281c9fe94e4d0489de643a9504c5cdfdfc6b29  --hash=sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992
        - pyserial==3.5  --hash=sha256:3c77e014170dfffbd816e6ffc205e9842efb10be9f58ec16d3e8675b4925cddb  --hash=sha256:c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0
        - rns==1.5.6  --hash=sha256:57a2498a6581e994b088ad815f096b7c23ed321e3909b44fe1589f8b08506898  --hash=sha256:975a646836749560f4553e4cc82d7dc9774c6c79c8beef08357264e1d8443626
      expose:
        - rnsd
        - rnstatus
        - rnpath
        - rnprobe
        - rnid
        - rncp
        - rnx
        - rnsh
        - rnodeconf
    note: >-
      Pins resolved on 2026-10-03 from `rns==1.5.6` (see the comment above).
      Bumping means resolving the set again for `rns`, `lxmf` and `nomadnet`
      together and changing all three units in one commit.

depends: [python3-venv]

# The shared instance. By default the first Reticulum program to start owns the
# interfaces and every other one attaches to it, so when it is NomadNet and
# NomadNet exits, everything else loses the network. A service that is always
# the first makes that the same one every time. `--service` makes rnsd log to
# ~/.reticulum/logfile rather than the journal. The unit is enabled at install
# and starts at the operator's next login (or `systemctl --user start
# hammunition-rnsd` now). The engine writes no Reticulum configuration:
# ~/.reticulum/config is created by rnsd itself, under the operator's account.
#
# No `listens`: the shared instance is not a TCP port. Measured 2026-10-03
# (Parrot 7.4, rns 1.5.6, `ss -xl`): rnsd binds the abstract Unix sockets
# `@rns/<instance_name>` and `@rns/<instance_name>/rpc`, and no TCP port.
# Upstream's example config names 37428 only for platforms without domain
# sockets or `shared_instance_type = tcp`. A `listens:` entry would print a
# loopback TCP listener the plan does not have.
user_services:
  - name: hammunition-rnsd
    description: Reticulum shared instance for this operator's Reticulum programs
    exec:
      - "{venv}/bin/rnsd"
      - --service
    restart: on-failure

update:
  probe:
    method: pypi
  strategy: reinstall
  cadence_hint: >-
    144 releases since 2020-04-27 and three in the 21 days to 2026-10-02 (1.5.4,
    1.5.5, 1.5.6); GitHub's latest *release* lagged PyPI by one at that date.
    `lxmf` and `nomadnet` each demand `rns>=1.5.5`, so the three units are
    bumped together: resolve the closures again for all three, change the
    version, the pins and the three notes in one commit.

documentation:
  what_it_does: >-
    Reticulum is a networking stack that does not assume the internet. An
    address is a hash of a public key, every packet is encrypted, and one
    network can run over any medium that can carry a few hundred bytes: a LoRa
    radio, a KISS packet modem, serial, Ethernet or Wi-Fi with no router at all,
    or the internet when there is one. This unit installs the stack and its
    command-line tools: `rnsd` (the daemon), `rnstatus` (what it is doing),
    `rnpath` and `rnprobe` (can I reach that destination), `rnid` (identities),
    `rncp` (file transfer), `rnx` (remote commands), `rnsh` (a remote shell) and
    `rnodeconf` (configures and flashes an RNode, Reticulum's LoRa radio). It
    also installs a systemd user service, `hammunition-rnsd`, so that one
    shared instance owns the interfaces for every Reticulum program you run.
  why_you_want_it: >-
    For messaging and file transfer that keep working when the infrastructure
    does not: two laptops on one Wi-Fi or Ethernet segment find each other with
    no configuration, and the same software reaches further over an RNode on
    LoRa or a packet TNC. It is a separate network from Meshtastic (the two do
    not talk to each other) and from Winlink and APRS, and it sits beside them:
    any KISS modem can carry it, including Direwolf, which `packet` installs. The nearest
    alternative in this catalog is Meshtastic, which is a ready-made text mesh
    with a phone app; Reticulum is a general stack with more to learn and no
    central design.
  prerequisites: >-
    Python 3.11 or newer from the distribution, and `python3-venv`. Nothing
    else for the local-network case: AutoInterface needs link-local IPv6 and a
    network that passes multicast between its devices. For LoRa an RNode and
    membership of `dialout` (log out and back in after being added). Nothing
    here transmits until you attach a radio or a network and configure it.
  known_problems: >-
    **The licence is not an OSI licence.** The Reticulum License is the MIT
    text plus two added conditions, quoted from upstream's LICENSE (read
    2026-10-03): "The Software shall not be used in any kind of system which
    includes amongst its functions the ability to purposefully do harm to human
    beings." and "The Software shall not be used, directly or indirectly, in the
    creation of an artificial intelligence, machine learning or language model
    training dataset, including but not limited to any use that contributes to
    the training or development of such a model or algorithm." Hammunition
    installs it from PyPI at your direction and never mirrors or vendors it,
    states the terms and does not judge your use of it (D-033, D-021).

    **First start writes a configuration, and the engine writes none.** `rnsd`
    creates `~/.reticulum/config` with its defaults, which enable the
    AutoInterface: link-local IPv6 multicast on every interface, so two
    machines on one network find each other. Upstream's manual (1.5.5) says it
    uses UDP ports 29716 and 42671 and that a firewall may need to allow them;
    the guide says what was measured. The file and the identity beside it are
    yours: Hammunition never edits them and `hammunition uninstall rns` leaves
    `~/.reticulum` in place.

    **The shared instance is a local socket, not a TCP port, and it is not
    private to your account.** On Linux it is the abstract Unix socket
    `@rns/default` (measured 2026-10-03), which has no file permissions, so
    another account on the same machine can attach to it as a client. Which of
    your interfaces that lets it use was not measured on a multi-user machine
    for this unit; treat the machine as a single-operator one.

    **The service is enabled at install and starts at your next login**, as the
    engine's other user services do. To start it now: `systemctl --user start
    hammunition-rnsd`. Until it runs, the first Reticulum program you start
    becomes the shared instance, and stops serving the others when it exits.
    A second `rnsd` that finds an instance already running does not fail: it
    attaches to it, logs "connected to another shared local instance, this is
    probably NOT what you want!" and `rnstatus` against its own configuration
    says "Could not get RNS status" (measured 2026-10-03).

    **`rnsd --service` logs to `~/.reticulum/logfile`**, not to the journal, so
    `journalctl --user -u hammunition-rnsd` shows little.

    **`rnodeconf` downloads firmware itself** from upstream unless told
    otherwise (`--fw-url`, `--nocheck`, `--extract`/`--use-extracted` exist).
    Where it fetches from and whether it verifies what it fetches were not
    measured; read the run before you let it flash, and see D-026 for why the
    flasher is installed and the firmware is not ours. `rnsh -l` lets the
    identities you name run commands as you; `-n` allows anyone and is the
    wrong switch to try.

    Three venvs each carry their own `rns` (about 20 MB, 20 MB and 27 MB for
    `rns`, `lxmf` and `nomadnet` measured on 2026-10-03). No LoRa link, RNode
    or TCP hub has been run through this unit.
  upstream_url: https://github.com/markqvist/Reticulum
  upstream_support: >-
    GitHub issues and discussions on markqvist/Reticulum, and the manual that
    ships with it (`rnsd --exampleconfig` prints the annotated configuration).
```

- [ ] **Step 5: Run the test to see it pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: `9 passed`.

- [ ] **Step 6: Track the new files and regenerate the generated pages**

`tests/test_repo_hygiene.py` fails on an untracked source file, so everything is `git add`ed before the tests run. The package reference, the projects page, the parity report and the capability matrix are generated from the manifests and a test asserts regenerating is a no-op (CLAUDE.md: a generated page is never hand-edited).

Run:

```bash
git add -A
.venv/bin/python scripts/gen_package_reference.py
.venv/bin/python scripts/gen_projects_page.py
.venv/bin/python scripts/gen_parity_coverage.py
.venv/bin/python scripts/gen_capability_matrix.py
git add -A
git status --short
```

Expected: four `wrote ...` lines; `git status --short` lists the new manifest, its generated page `docs/packages/rns.md`, and the modified `docs/packages/index.md`, `docs/projects.md`, `docs/reference/capability-matrix.md` and `docs/reference/parity-coverage.md`.

- [ ] **Step 7: Bring the README's manifest count to the catalog's**

The README quotes the manifest count and `tests/test_docs_generated.py` holds it to the catalog; this reads the catalog and edits the one row, so it is right whatever number `main` carries.

```bash
python3 - <<'PY'
import pathlib, re, sys
sys.path.insert(0, "src")
from hammunition.manifest.load import load_catalog

n = len(load_catalog(pathlib.Path("catalog/packages")))
p = pathlib.Path("README.md")
s = p.read_text()
new, hits = re.subn(r"(\| Package manifests \| 🟡 \*\*)\d+(\*\*)", rf"\g<1>{n}\g<2>", s, count=1)
assert hits == 1, "the README's manifest-count row moved: find it and edit it by hand"
p.write_text(new)
print("README says", n, "manifests")
PY
```

- [ ] **Step 8: Run the tests that read the catalog and the generated pages**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_docs_generated.py tests/test_categories.py tests/test_site.py tests/test_json_catalog.py tests/test_repo_hygiene.py tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 9: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict src tests/test_reticulum_catalog.py
```

Expected: clean, `Success: no issues found`.

- [ ] **Step 10: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Add the rns unit: Reticulum, its tools and one shared instance

A hash-pinned per-user venv, nine exposed commands including rnsh and the
RNode flasher, and a user service that keeps one shared instance. The
Reticulum License is printed on the plan line. Track C, issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 4: The `lxmf` unit: the message layer and `lxmd`

**Files:**
- Create: `catalog/packages/lxmf.yaml`
- Modify: `tests/test_reticulum_catalog.py` (append the `lxmf` cases)
- Modify (generated): `docs/packages/index.md`, `docs/packages/lxmf.md`, `docs/projects.md`, `docs/reference/capability-matrix.md`, `docs/reference/parity-coverage.md`
- Modify: `README.md` (manifest count)

**Interfaces:**
- Consumes: Task 3's test helpers and the `rns` unit's pinned `rns` version.
- Produces: unit `lxmf` 1.2.0 exposing `lxmd`, no service, pinned to the same `rns` as the `rns` unit; the parametrized `test_every_reticulum_venv_pins_the_same_rns` that Task 5 widens.

- [ ] **Step 1: What this unit is**

`lxmd` is not a user service in this PR: a propagation node stores other people's messages, and running one is a decision the guide puts to the operator. The closure is `lxmf==1.2.0` from the inventory: six packages, 167 hashes, installed with `--require-hashes` on 2026-10-03. This venv carries its own `rns`, pinned to the version the `rns` unit pins; the test below is Review Focus 4, the version-skew case: a client and a shared instance on different `rns` versions is a failure nobody should have to diagnose.

- [ ] **Step 2: Write the failing tests**

Append this to the end of `tests/test_reticulum_catalog.py`, after 2 blank lines:

```python
# -- lxmf --------------------------------------------------------------------


def test_lxmf_is_a_complete_hash_pinned_venv_exposing_lxmd() -> None:
    block = _venv("lxmf")
    assert block.python == ">=3.11" and block.expose == ["lxmd"]
    assert pinned_projects("lxmf") == {
        "cffi",
        "cryptography",
        "lxmf",
        "pycparser",
        "pyserial",
        "rns",
    }
    assert pinned("lxmf", "lxmf") == "1.2.0" and _unit("lxmf").version == "1.2.0"
    assert hash_count("lxmf") == 167
    assert block.licence is not None and block.licence.startswith("Reticulum License")
    assert block.licence_url == "https://github.com/markqvist/LXMF/blob/master/LICENSE"


def test_lxmd_is_not_a_service() -> None:
    """A propagation node stores other people's messages; running one is the
    operator's decision, made in the guide, never an install default."""
    unit = _unit("lxmf")
    assert unit.user_services == [] and unit.launchers == []
    assert unit.config_files == [] and unit.system_modifications == []


def test_the_lxmf_page_says_where_the_identity_lives_and_that_uninstall_keeps_it() -> None:
    docs = _unit("lxmf").documentation
    assert docs.known_problems is not None
    assert "~/.lxmd" in docs.known_problems and "leaves in place" in docs.known_problems
    assert "propagation node" in docs.known_problems


@pytest.mark.parametrize("unit", ["rns", "lxmf"])
def test_every_reticulum_venv_pins_the_same_rns(unit: str) -> None:
    """Each unit is its own venv with its own copy of `rns`, and the one that runs
    the shared instance must be the version every client was built against.
    Bump all three units in one commit (`rns`'s cadence_hint says how)."""
    assert pinned(unit, "rns") == pinned("rns", "rns"), (
        f"{unit} pins rns {pinned(unit, 'rns')} but the rns unit pins "
        f"{pinned('rns', 'rns')}: resolve the three closures again together"
    )
```

- [ ] **Step 3: Run them to see them fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: `4 failed, 10 passed`: the four `lxmf` cases fail with `KeyError: 'lxmf'`; the nine `rns` tests and the `rns` parametrization of the skew test pass.

- [ ] **Step 4: Write the manifest**

Create `catalog/packages/lxmf.yaml` with exactly this content:

```yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

name: lxmf
version: "1.2.0"
summary: LXMF, Reticulum's message layer, and lxmd, its store-and-forward propagation daemon
categories: [mesh]

# ADD, Track C (issue #105; D-080). Evidence: docs/reference/mesh-inventory.md,
# measured 2026-10-03; not in any apt archive on any target, so a hash-pinned
# venv like `rns`. The pins are `uv pip compile --python-platform
# x86_64-unknown-linux-gnu --python-version 3.11 --generate-hashes` from
# `lxmf==1.2.0` (uv 0.12.23, 2026-10-03), six packages and 167 hashes; installed
# with `pip install --require-hashes` into a fresh venv on Python 3.13.5 on
# 2026-10-03, every hash matched and `lxmd` is in `bin/`.
#
# Licence: the Reticulum License, the same text as `rns` (upstream's LXMF
# LICENSE differs from Reticulum's only in the copyright years, read
# 2026-10-03). D-033 shape; docs/reference/licence-verification.md.
#
# This venv carries its own `rns`, pinned to the version the `rns` unit pins:
# a client and a shared instance at different RNS versions is a failure nobody
# should have to diagnose, and tests/test_reticulum_catalog.py holds the three
# Reticulum units to one `rns`. `lxmf>=1.2.0` itself demands `rns>=1.5.5`.
#
# `lxmd` is not a user service. A propagation node stores other people's
# messages, and running one is a decision the guide puts to the operator.
install:
  - install:
      method: venv
      python: ">=3.11"
      licence: "Reticulum License (MIT plus two use restrictions; not OSI-approved)"
      licence_url: https://github.com/markqvist/LXMF/blob/master/LICENSE
      requirements:
        - cffi==2.1.1  --hash=sha256:046bfc24911b37851ee1b51aab8bffe713d89c68c6a057b09484ce9fd5f69b4e  --hash=sha256:06c72bb76605a4b0cd0aad6930b69d4baf7dd5d806cfc409b824191099700e66  --hash=sha256:0beceaabe56af686895136a2de78db54ecd8e4046b236b8fd6d6cb61389e9bf2  --hash=sha256:154852545011f779917b11c78db2358d095da62a9a172b78ad0a583ee5adc0d0  --hash=sha256:194cffa889098ced9976c3fc6340305e43f6303657d298da55366907c05c22d6  --hash=sha256:19ee6127ee34de7d83ce3d371ebc5ed91addbdcc39f9ab15ce4eb35a4e534971  --hash=sha256:1a18a57b58cfb21fc28d72e876acf10eaed67a1ed96226f92af4df681d571c4c  --hash=sha256:1aa5645c30469b09530c4ebca77ebf8f17618293c58f8549cb1a543a50236e7d  --hash=sha256:1dea0e4d7d4f11f619fe8c1d76caf49e24405b4b5743c0e3be16a500ecd930c9  --hash=sha256:208f941bb9d18e768138677f0a6d2ce01f590df56043dda1df1535ac57c88517  --hash=sha256:210019b6c7cf07f081b4c54635c8cf744377001350e29cc0f81c4377b4797735  --hash=sha256:246fa40ce8645a614ff682e0b70f37134e460eaf93a775e0cbe3cca585a67a80  --hash=sha256:25792eac27877609e7bb06d42ff88278a6624fff2ba9bbb523c09616b117e80f  --hash=sha256:27350daa11d4f10c540e6e89dada4c54feb7256ad03e9a4dc075ebad7ba360d1  --hash=sha256:28907ab9bfb6aa13184cfc17c6b8e1023c5ab6fd7076d8c20a35e59fe04f8f29  --hash=sha256:2ae64be792b8966f2c69538199728b290e34726562896df1e5dc8ffd8d8188e8  --hash=sha256:31348097ff5bbe827ccc41795d4dd099d9f0625e7def00ee653c137a490c2a6c  --hash=sha256:3143d81e29e1e20a9ce10901ec369012947876596f75a222235965f2b7ae832e  --hash=sha256:3222ba5d678f80a030e6afbcc33dc1ae5cb45facabb61cee2c7016b8432fde48  --hash=sha256:3311ed60d36f83378794e1009ac6258bafbf81f7888b4caa7b35a521e3f95813  --hash=sha256:334644fbac4eff73d985a17a91226df55d0f394160c4cfb880e084c8f7161cac  --hash=sha256:34e261f78cb6ceaaa36f42f2613f4380d94d9c759a9c73c769ee6e0247364632  --hash=sha256:363e05fa78e15116c3c32c210ee36884fd6b9afa6d440e47112c3bd511d64cb6  --hash=sha256:398aff33cee2767e3e781d2554c54bd0dff386bb437581e0d8011fde1a942ec1  --hash=sha256:3d22a20b1fb1632cc72c22f95f7b0d2961c3e1c235f245ba4c606c4771035659  --hash=sha256:42a494cee34437f05546455144f2b5d9ac09b1face62bcfce597d2e521066688  --hash=sha256:42e2f76b9455f5a9a844f770bf3e200ed3da0e15f5df3db9c31fe80b04b3d004  --hash=sha256:42f6930c31dc7f50732c9ae793c2786c7b6b044195967bbdde40bb9be81c4cc0  --hash=sha256:456a61fa52d579ebf9df2e9552ead5129855dbaff6c1e5a9b1bc408809bdc062  --hash=sha256:471cee653ae88de62096552e6d24ccb4a5adb8c8c9f10b5054d0122c15bf2779  --hash=sha256:49cbc70e6542d4ccccb936558d1064a8012541e78f821f955cff24e357776c94  --hash=sha256:4a7c934f7360e8cd64fe9efadcbd10c7c6364f531e432b9a4bf5ccbc9e0e8b50  --hash=sha256:4be96343e422f2dfcd12ab5c9f5aebe03f82f737c6bffeca6830b3875cb44aab  --hash=sha256:4f42141fc14250de6dde5ee7ea4432be017252d91f19c5ad043c084cea629cac  --hash=sha256:507a24c282e0f42f8ed737cf048572cbf580468da5555764a8331735e9c736b6  --hash=sha256:51b31d1c98274844cfd7838ce00bfc27c7423a4dc00fc0772fc3331c2cc90676  --hash=sha256:58acb8ab8e295e6c5ea12f888cbb13cf21511ef2a3303a23f4325c29d17fe5c1  --hash=sha256:5a59cc1c4442bc3d5c703bf720b51138d0bfc173618807c9ee2490a7541dd3d9  --hash=sha256:5bb4e7ea95dcd6a014a6fef62e62467d67d8e582326443f3d68e71d6320a9fcf  --hash=sha256:5c58fe613dc5e5336357eff555824a314d8e43282600435c8d1cb6a7a2fedd13  --hash=sha256:5e7cecbaadb83884793e05828cee59b210b24583b9c7425d0ba6a754fe22eb4e  --hash=sha256:616f097f2fe415bc92a247f02e11f634e1f9e9a83d327e3c915c15089c87869e  --hash=sha256:63bbfd5ded17c4840ac07cd8f1c21ba9d9708141f840b324f422f41b207e3973  --hash=sha256:64faea20f4e2613363a1a9b9c7dd73058f3ecd00133a511e72ad7c511658f527  --hash=sha256:661c298b4821edebead0c91edd2b00374d67ad7c5a1f7a91d4442633b79d6a72  --hash=sha256:68e62fe11f30d5ca8289242866f0a5291402d8529ca2178ab8afc5c9694ae890  --hash=sha256:6a8dddef476fab96d066d578fc88526767b836ab5ab21754e1d5bf3879c31c7c  --hash=sha256:6e192623c49c94421616a5778fba35cf0d5a8d000650c1967ef4448ee5cdd990  --hash=sha256:7225e4514edb64eb6740324353e0da0711954fd8d7da4576755b1c6e09b697cd  --hash=sha256:75f80557d1389eddbd0de2681f6a390a0c5338c31ddaa821381c203fc3fd50d9  --hash=sha256:770de9db11e84213beec501cfcaa013b019820ca881e03344dea5844f7876d94  --hash=sha256:7750c6449dff7864bb9bb27ddfb0267756189201a3afc911d82b3caacd70dfc3  --hash=sha256:7bde5e4cc5c10140859842b9d383af292b22639a4dffb725314baf45968cef80  --hash=sha256:7ce713ace7c0e4520535b42b77eaa742c16dab813978064913e5a3cf82973b41  --hash=sha256:7da0c5eff80f0197f3b3d1232ec5a682a9325f4ae9016a78f5f5ca35f9ced1f5  --hash=sha256:7dbb61fe3a7699468030f71bbe5f8a0e326a151daa91beb11a6fc1f980c55e1c  --hash=sha256:811bd1e21d32de12efca32393a0ab3f5133b54fce9bd44b8bd77ab07da14bf6a  --hash=sha256:8ef53b2de9bcb9197d31854256575d59dbac0cba72ac627bb291ef5eceb74be4  --hash=sha256:937c0052c05a31ca1daf18de3158eed4dbfcb9cc107adbea227728d647be701e  --hash=sha256:9d2055050ea716bd38b7f7f1579c275386646b4894c155a3e2f3cd62ed41b7c6  --hash=sha256:9f8d177621de5cb38ee3e731eda45d421db093ec0739f46a5594babda7987a98  --hash=sha256:a2d7755bef5a12ed488f4ef1f1b69ee9191d7396083b755a5d2295f6edb4768b  --hash=sha256:a48d62ab9d6f4f98c983223a547af44be6ca3691074c31cecced6facd3ba2dc1  --hash=sha256:a4f00aa42f75d6e4595e8866e748cc1705adc0cddfeb2ca86d0d03993d63ba03  --hash=sha256:a6e721d4b0e45d5b65e87534470e67b18dcd092c83f68fba09f152b9cbc061af  --hash=sha256:a730a083190634c65cca36ba5f489531576ebd79bcd5c8e172130f6453127231  --hash=sha256:a931079504ecc49efed7744c476a5c343a92fabf66dec2db95edb1b2fdc770e2  --hash=sha256:aa9511c62d14da7aacc9b4bf51f3f697a621e83b2d6919008243c3aad168eea3  --hash=sha256:ab36d55f9ed2d067327667c2fea18dda018eb628dd6347aa01dda6cf1f5d3836  --hash=sha256:ad2c86c495b899d862ea0f4b42891b8713a3bd45dd4105c7fd51c2a72f39f3a5  --hash=sha256:aeae0e330c9f6acd681f647d46cefd30c29f93e3392882e792e82080c9691399  --hash=sha256:b0431303acaea1089ad4b3e9ce4e6518193def1118d4073ca848635ee4ea2e96  --hash=sha256:b5bdfd1c873d4e093aabc0ca84c4ca6dbc4f752afb5c86f146d9742580c9da2e  --hash=sha256:baed1e86cc735622097354b9d1281406caf42ff42a886d29faa8e8d1630333be  --hash=sha256:c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf  --hash=sha256:c26608d2222fb1e94487e4a387d85f13eb55d5ed725cb25a0c589ac4ee60e7bc  --hash=sha256:c7659f22557c5a0bc4855cd635f55edec690cc008a40768527762cb9fb263455  --hash=sha256:c8c69575568085ba0b1b10c0249d779a214aea6f6522e949a0fc9fb0fcb449d0  --hash=sha256:c8d2c9fd1f2d16f780d15127abb050d13d1a76c03a4bd87d7e4980e45e511e12  --hash=sha256:ca82be1a1d406ecfe1d25dc16cb33488e5a16bf4438c9fb590484ea29d92478b  --hash=sha256:cc572dace3f60ef98d7b12ff411d20f5362feb31a0439eab0085bbfd349982d7  --hash=sha256:d18e5ac0f2f03f4f518d3e23db0f0cad7faa1da8620e9c09461d443bbf6e6692  --hash=sha256:d28630f5854ab07ab1fd4aba756de52326c82e6be15d414b12793f1975048b54  --hash=sha256:d9c275eaacd24aa73f94ffd6de08fc3f932424d8b6c376f4bed7cde376fe7bc3  --hash=sha256:da0e573f9f97159390c89d9f1a9e41908b66d408cc5b58d08cf3847d844c531b  --hash=sha256:dd31f52ea1086513bb9df30f8fcee9b8918323ae067a3d5b78bc826a000712be  --hash=sha256:dddad92b554513a31f272570678ba307fb9f618f05e3d4a5eacafff9eae03e1d  --hash=sha256:df423d40ee8654634421812bc3b196da3f9bd7d32929da813f8394c4348a5358  --hash=sha256:df913725b79db7bcf03448f36b7bf8815363417d5b58deecf9305e3e30f0f21a  --hash=sha256:e0bcb7e0f677f543555d2adff3bf19c05f66cdb4796e5ff602442ab2fe3c4ef7  --hash=sha256:e2d65b31f36619cda3999b78b2aa9632e76b78448e7a56fc4240824200e7c4fc  --hash=sha256:e6e8cff14d6fb0be70a09c0bdc58096f501952d04624ebf867e0e56da2df8960  --hash=sha256:f16c709686a78c727bbbf059f92b0bf41c6fc60deec706d2dc19f529175a6125  --hash=sha256:f24fb43132a4c6b4cb4eb029492919b2db645be6808d738f244fd146c03c32cb  --hash=sha256:f53e442b08449d42821fa4a4fba000095af9f62742a500f978a9f557ec44339a  --hash=sha256:f5cfbc5fe74540d335175b656c725d74d90e3730c626d92575eea35029d9afaa  --hash=sha256:f81b3b8f3d4e343550fa4baa0e479bba9f2d29ce9c2e9b51d1ce1718d7442fcf  --hash=sha256:f8ec5e643a9a937f64e1999eb9f75d072263751912dc5cd06d3c85f8f44be7c3  --hash=sha256:fb92203a88b3d3053034db775110081c49d28be6551923805e039924093761e4  --hash=sha256:fcd22650c908d7b7da162bbfaab594a1227a15d1643a98c68b122ac642fa2264
        - cryptography==50.0.2  --hash=sha256:0ddc924c04591c2811ca024d62ecad4f7f6f08af8939c211438f48a16bd23602  --hash=sha256:0ec5f09541743261e66e291b4a0cbf0fb2997aeaab6d9e9c740b9dba1b58d1c2  --hash=sha256:0ecbc5652bdb6fc9eaf89a7d196e20941adfe812f43bc4ca05d9150496821047  --hash=sha256:1981f1db4630889b9ef7803fadef12b056f428cb6b85c27ba57b774793b6093c  --hash=sha256:1ba34f04897fcdaa73f74145c25f3ec146fbd56593853e88adc2e811303c5f42  --hash=sha256:241449bf940a5d27309bd317e6f9a2af6932113818bb2b8f5c59ddc7ef16da18  --hash=sha256:25784ce8b9621c90c643efb9e1e2162ab3b0224cae446ad5e70e7fcb1ce18b51  --hash=sha256:3dc4fd8058cea1644971207d530e1a03a184a805ffc8ebdddf0599d78a331b81  --hash=sha256:4061c0079120205fb760c58acab6443e217307dcf05e3702cf970e0689972856  --hash=sha256:4a20ce1e5cb4284a86692fdcba7cb8754185c6b2e5c56fcef3751cf451d3cdc2  --hash=sha256:4e81d95e5bafc2d6e34e4bed780e53e4d5b9a2f928573428aa4d35fbec1eb0de  --hash=sha256:58a0c478eeca76fe5e07993c5a0703def34a6dc6a0cda4f5564639b33112ffe7  --hash=sha256:58ddb5a8e3179d12f19e4ea34d2d32e9d63a4baa142c875c1eb59f41b7243acd  --hash=sha256:630ebfea3bf689d075f82316324ff7433dc447fe6bc1bfc76524b74b4a9567d2  --hash=sha256:6f8700550aa1474a91e5dc07049c46f98b423b5b1ddd0483e0b51362eeeaf5be  --hash=sha256:78198641e5be9521beea5aa782bb551a58068d10e6eb04c9c680c1b69f2e7d45  --hash=sha256:79def8d059362e7831389ed3be0ecdf58a89386e1271e35dd9f5af84e81bffd0  --hash=sha256:7a8701d6b584d76e909e3d305b7d126b41439876a5aaf76cddc67fc230eafa2e  --hash=sha256:7afa5a6602a9f29af1f3a2965f831bae7c9d5d597b7cbb716d41ab3b7d89879c  --hash=sha256:7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5  --hash=sha256:7b75de3c8b3be1cdb1052747c929440c3eea46c1bc2cb8a6e3a48388e9b7b452  --hash=sha256:7c6d0330c472d96f6a6afe24d80dfdf15176c33096f0a4397ae4c60f3dd3be48  --hash=sha256:828d49b0ff5a0e3975865571c5d91dbbdd0d38d8289b249a163e9425413a5e05  --hash=sha256:84f964e537f916e2cc85199e5a88742e964939b575ac8598b3f9d6cc416cdaf1  --hash=sha256:85d0d9a31b9098e98534226d5686b47264b95e62ce459dc2e62fdfc809f9fe93  --hash=sha256:87e9ce85beb6b328ba370cc6e6aea483c92617b4c95b1d33a49297eb662bfb04  --hash=sha256:8c71ba2cd31fc93748c38e1b613200ff1c2665cbfd5341fe3a61cfde35a1430e  --hash=sha256:92e665960f25fcdc73725b9cec7a3824f279ba97a98653afe9ffac2e43668f67  --hash=sha256:94e5e9f108ee10471288214d3d233fbfbb492840a8457eb85178d643ddeb32c7  --hash=sha256:9c8402a82ea0dc4ceeab793db05f0fafa8ca139ca34fcde5df0f596103c74107  --hash=sha256:9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079  --hash=sha256:a582ab2ae1d34f67112cadc86702774c9ea4374df6bca6afe672817203c99134  --hash=sha256:a6557e5f38e065ca9fbdaf7cfc7435ecb1d113aa81a022d1b51921ee7432e227  --hash=sha256:a9f7355e6fab51f6c369b86fb7571cffa05edee2c2121e0380a37fb9ac1cd5c1  --hash=sha256:ab50ee449bf968271e820086f10a33d101dd060370abc10bcd22279be2656539  --hash=sha256:ac9ed99d81760c62fe89d5f0815cdfa1ba9a35141cf30f1c2d044f04b4803d2e  --hash=sha256:b13478603dcd0a2479ff8e87e2c19a7d525734686fe3c49542472293a204212d  --hash=sha256:c423ab384a46c4dff7217b2ea5ba2e11cffdeab6441acd04cf65a369caf0366c  --hash=sha256:c5e67125c7dca78d199ec4e116aa93dbb83494808ecbb8211a2cb09b1bf41dbd  --hash=sha256:c71be1cbfa5cd9a41ee452acf1eccd82b2c05950358b106ec8ceb83411d1a020  --hash=sha256:cbc8738fd8526d80f35cb3a40d41f41a2e7030bb3b18b09a6778ef63d291c2fd  --hash=sha256:ce47f66801c20ec6c6632453bb5960fe38939e9306970b48b3a5a26de7745d94  --hash=sha256:d370b8d1dfcdf7130178137f6fbee6140774a1acc6cacefc4b42643ec11d0a3a  --hash=sha256:d38cdff612d06fa6a32840d5e1b1f7a27cee4a349aa9085d94a67789d6bfd408  --hash=sha256:d8947001be83df1394050758ce0e745dd74fb134eef0a4b5124208dfc3a68c37  --hash=sha256:deb9fde5c60e437ee4821bc9bc39ff31b42135c27e1dc61ef0a629389c1de62e  --hash=sha256:dfe9763530994147d9af1def057a5b9658b00e8f8fe8743d144d1e0911c2e454  --hash=sha256:e105ab60406787da31fccc883fc0f733af1efd78f0136a4599692c4083a73d0c  --hash=sha256:e275096ea1e60cc595cda2836fd4a6c725d1125108b868be17f53684d164e2cc  --hash=sha256:edc3342adf8f697fc5f59c887a304356f147b397809440ed64e2fa6af2f50f37  --hash=sha256:ee247f5c245c9a2fe7c8e2214e295918838e44e00a45a6718451e4004219e767  --hash=sha256:eef4c2f3423810b3070ab391f85436d2f8bbfcb286ac15cbc73190b3563b1f1a  --hash=sha256:f21e8a22c8605750c7af886bab299a363721264061b4ac0a30efb73cfd58efc5  --hash=sha256:f265528741e048bce55c3463ed721fb0aa45a5888d8add8cfeccb3035451bbdc  --hash=sha256:f2f9bd7f90c64fe89253f0a2c05e3c4856072660429ce8831b4235bf29403a67  --hash=sha256:f785f6161f202ab04d8ca194158968798e480ca058943907972da5f12e2881e8  --hash=sha256:f9f6143a8c75945eb960d9eb98905a441394abfa24afaae239d514ffb2586480  --hash=sha256:fa8f5efb344d6908a1ce62f4a24e2e5780f825d6f53f5f50ec5ffacac72936cb  --hash=sha256:fdd28f912fccfec1846a94e2e1e8f9b0012f557f0c46fe4f3eb0d7a87afcf90b
        - lxmf==1.2.0  --hash=sha256:805f053e61082f585efc6d09beffd039fd921174c5e1547a2e690bc479d75b85  --hash=sha256:f14243283b90ad06356071d90394357640924201f9c992dcdfecbc23614fb309
        - pycparser==3.0  --hash=sha256:600f49d217304a5902ac3c37e1281c9fe94e4d0489de643a9504c5cdfdfc6b29  --hash=sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992
        - pyserial==3.5  --hash=sha256:3c77e014170dfffbd816e6ffc205e9842efb10be9f58ec16d3e8675b4925cddb  --hash=sha256:c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0
        - rns==1.5.6  --hash=sha256:57a2498a6581e994b088ad815f096b7c23ed321e3909b44fe1589f8b08506898  --hash=sha256:975a646836749560f4553e4cc82d7dc9774c6c79c8beef08357264e1d8443626
      expose:
        - lxmd
    note: >-
      Pins resolved on 2026-10-03 from `lxmf==1.2.0`. Bumping means resolving
      `rns`, `lxmf` and `nomadnet` together and changing all three units in one
      commit.

depends: [python3-venv]

update:
  probe:
    method: pypi
  strategy: reinstall
  cadence_hint: >-
    75 releases; 1.2.0 on 2026-09-30. It moves with `rns` (it demands
    `rns>=1.5.5`), so the three Reticulum units are bumped together: see `rns`.

documentation:
  what_it_does: >-
    LXMF is the message format and delivery layer on top of Reticulum, the one
    NomadNet and Sideband speak: addressed, encrypted, store-and-forward
    messages. This unit installs the library and `lxmd`,
    a daemon that can run an LXMF *propagation node* (a machine other
    people's messages wait on until their recipient is reachable) and can run a
    program of yours when a message arrives.
  why_you_want_it: >-
    NomadNet has its own LXMF inside it; you install this only to run a
    propagation node, to script LXMF messaging in Python, or to run `lxmd`
    as a message-arrival hook. A mesh that must carry messages between laptops
    that are not on at the same time needs at least one propagation node
    somewhere, and an always-on laptop or a Bunker on the LAN is a reasonable
    place for it.
  prerequisites: >-
    Reticulum running, which this venv carries its own copy of: with the `rns`
    unit's service up, `lxmd` attaches to the shared instance; without it, the
    first program to start becomes the shared instance and stops serving the
    others when it exits. A propagation node wants an always-on machine.
  known_problems: >-
    **Nothing is started by this unit.** `lxmd -p` makes your machine a
    propagation node: it stores encrypted messages addressed to other people
    on your disk, for as long as its limits allow, and relays them to peers. Run
    one on purpose; the guide says what that means. `lxmd` keeps its identity,
    configuration and message store in `~/.lxmd` (created on first run;
    measured 2026-10-03), which `hammunition uninstall lxmf` leaves in place:
    the identity is yours and is not rebuilt.

    **The licence is the Reticulum License**, MIT plus two use restrictions, the
    same text as `rns` (see its page); Hammunition states it and does not judge
    your use of it (D-033, D-021).

    About 20 MB in its own venv. `lxmd` was run only against an interfaceless
    shared instance on 2026-10-03 (it attached and kept running; no message
    was sent); propagation between two nodes was not measured.
  upstream_url: https://github.com/markqvist/LXMF
  upstream_support: >-
    GitHub issues on markqvist/LXMF; `lxmd --exampleconfig` prints the annotated
    configuration.
```

- [ ] **Step 5: Run the tests to see them pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: `14 passed`.

- [ ] **Step 6: Track the new files and regenerate the generated pages**

`tests/test_repo_hygiene.py` fails on an untracked source file, so everything is `git add`ed before the tests run. The package reference, the projects page, the parity report and the capability matrix are generated from the manifests and a test asserts regenerating is a no-op (CLAUDE.md: a generated page is never hand-edited).

Run:

```bash
git add -A
.venv/bin/python scripts/gen_package_reference.py
.venv/bin/python scripts/gen_projects_page.py
.venv/bin/python scripts/gen_parity_coverage.py
.venv/bin/python scripts/gen_capability_matrix.py
git add -A
git status --short
```

Expected: four `wrote ...` lines; `git status --short` lists the new manifest, its generated page `docs/packages/lxmf.md`, and the modified `docs/packages/index.md`, `docs/projects.md`, `docs/reference/capability-matrix.md` and `docs/reference/parity-coverage.md`.

- [ ] **Step 7: Bring the README's manifest count to the catalog's**

The README quotes the manifest count and `tests/test_docs_generated.py` holds it to the catalog; this reads the catalog and edits the one row, so it is right whatever number `main` carries.

```bash
python3 - <<'PY'
import pathlib, re, sys
sys.path.insert(0, "src")
from hammunition.manifest.load import load_catalog

n = len(load_catalog(pathlib.Path("catalog/packages")))
p = pathlib.Path("README.md")
s = p.read_text()
new, hits = re.subn(r"(\| Package manifests \| 🟡 \*\*)\d+(\*\*)", rf"\g<1>{n}\g<2>", s, count=1)
assert hits == 1, "the README's manifest-count row moved: find it and edit it by hand"
p.write_text(new)
print("README says", n, "manifests")
PY
```

- [ ] **Step 8: Run the tests that read the catalog and the generated pages**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_docs_generated.py tests/test_categories.py tests/test_site.py tests/test_json_catalog.py tests/test_repo_hygiene.py tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 9: Falsify the skew test**

Run:

```bash
cp catalog/packages/lxmf.yaml /tmp/lxmf.yaml.bak
sed -i 's/^        - rns==1.5.6 /        - rns==1.5.5 /' catalog/packages/lxmf.yaml
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_catalog.py -p no:cacheprovider 2>&1 | grep -E 'AssertionError|failed'
cp /tmp/lxmf.yaml.bak catalog/packages/lxmf.yaml
git diff --stat catalog/packages/lxmf.yaml
```

Expected: the run names `lxmf pins rns 1.5.5 but the rns unit pins 1.5.6: resolve the three closures again together`; after the restore, `git diff --stat` prints nothing. (A check is trusted only after it has been seen to go red: CLAUDE.md.)

- [ ] **Step 10: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict tests/test_reticulum_catalog.py
```

Expected: clean.

- [ ] **Step 11: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Add the lxmf unit: LXMF and lxmd

A hash-pinned venv exposing lxmd, pinned to the same rns as the rns unit.
Nothing is started: a propagation node stores other people's messages.
Track C, issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 5: The `nomadnet` unit: the terminal messenger, with its menu entry

**Files:**
- Create: `catalog/packages/nomadnet.yaml`
- Modify: `tests/test_reticulum_catalog.py` (append the `nomadnet` cases; widen the skew test)
- Modify: `tests/test_verify_tree_launchers.py` (the pinned launcher-name table)
- Modify (generated): `docs/packages/index.md`, `docs/packages/nomadnet.md`, `docs/projects.md`, `docs/reference/capability-matrix.md`, `docs/reference/parity-coverage.md`
- Modify: `README.md` (manifest count; launcher count)

**Interfaces:**
- Consumes: Task 3's helpers; Task 4's `lxmf` pin (`nomadnet`'s venv carries `lxmf` and must pin the same one).
- Produces: unit `nomadnet` 1.4.4 (`GPL-3.0-only`, one exposed command `nomadnet`, one terminal launcher `nomadnet-terminal`), and the skew test over all three units.

- [ ] **Step 1: What this unit is**

Eleven packages, 196 hashes (`nomadnet==1.4.4`, installed with `--require-hashes` on 2026-10-03). The wheel's classifier says MIT and the licence text it ships (identical, by sha256, to the repository's `LICENSE`) is the GNU GPL v3; the shipped text governs (the maintainer's ruling), so the unit says `GPL-3.0-only` and its page says the two disagree. The launcher is named `nomadnet-terminal`, not `nomadnet`: both the launcher wrapper and the exposed command are written to `~/.local/bin`, so one name would have one overwrite the other. (The schema's launcher-shadowing check does not compare a launcher with `expose`; this test does.) The spec's `menu_title` is a manifest-level field for the entry the engine *generates*; a unit with a launcher uses the launcher's `title`, which is what this sets. `tests/test_verify_tree_launchers.py` pins every launcher name in the catalog by name (issue #174), so adding one is a table edit.

- [ ] **Step 2: Write the failing tests**

Append this to the end of `tests/test_reticulum_catalog.py`, after 2 blank lines:

```python
# -- nomadnet ----------------------------------------------------------------


def test_nomadnet_is_a_complete_hash_pinned_venv_exposing_nomadnet() -> None:
    block = _venv("nomadnet")
    assert block.python == ">=3.11" and block.expose == ["nomadnet"]
    assert pinned_projects("nomadnet") == {
        "cffi",
        "cryptography",
        "lxmf",
        "nomadnet",
        "pycparser",
        "pyserial",
        "qrcode",
        "rns",
        "typing-extensions",
        "urwid",
        "wcwidth",
    }
    assert pinned("nomadnet", "nomadnet") == "1.4.4" and _unit("nomadnet").version == "1.4.4"
    assert hash_count("nomadnet") == 196
    assert pinned("nomadnet", "lxmf") == pinned("lxmf", "lxmf")


def test_nomadnet_is_gpl_by_its_shipped_text_and_the_page_says_the_classifier_disagrees() -> None:
    """The wheel's classifier says MIT and the licence text it ships is the GPL v3;
    the shipped text governs (maintainer's ruling, 2026-10-03)."""
    block = _venv("nomadnet")
    assert block.licence is not None and block.licence.startswith("GPL-3.0-only")
    assert block.licence_url == "https://github.com/markqvist/NomadNet/blob/master/LICENSE"
    problems = _unit("nomadnet").documentation.known_problems
    assert problems is not None
    assert "The licence statements disagree" in problems and "MIT" in problems
    assert "Reticulum License" not in (block.licence or "")


def test_the_menu_entry_is_a_terminal_launcher_that_does_not_shadow_the_wrapper() -> None:
    unit = _unit("nomadnet")
    (launcher,) = unit.launchers
    assert launcher.terminal and launcher.exec == "{venv}/bin/nomadnet"
    assert launcher.title == "NomadNet (Reticulum messaging and pages)"
    # Both land in ~/.local/bin; one name would have one overwrite the other.
    assert launcher.name == "nomadnet-terminal" and launcher.name not in _venv("nomadnet").expose
    assert unit.user_services == []


def test_nomadnet_leaves_the_operators_identity_and_messages() -> None:
    unit = _unit("nomadnet")
    assert unit.config_files == [] and unit.system_modifications == []
    problems = unit.documentation.known_problems
    assert problems is not None
    assert "~/.nomadnetwork" in problems and "leaves in place" in problems
```

- [ ] **Step 3: Widen the skew test to all three units**

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("tests/test_reticulum_catalog.py")
s = p.read_text()
old = '@pytest.mark.parametrize("unit", ["rns", "lxmf"])\ndef test_every_reticulum_venv_pins_the_same_rns'
new = '@pytest.mark.parametrize("unit", ["rns", "lxmf", "nomadnet"])\ndef test_every_reticulum_venv_pins_the_same_rns'
assert old in s
p.write_text(s.replace(old, new, 1))
PY
```

- [ ] **Step 4: Run them to see them fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: `5 failed, 14 passed`: the four new `nomadnet` cases and the `nomadnet` parametrization of the skew test fail with `KeyError: 'nomadnet'`.

- [ ] **Step 5: Write the manifest**

Create `catalog/packages/nomadnet.yaml` with exactly this content:

```yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

name: nomadnet
version: "1.4.4"
summary: Nomad Network, an encrypted messenger and page browser for the terminal, over Reticulum
categories: [mesh]

# ADD, Track C (issue #105; D-080). Evidence: docs/reference/mesh-inventory.md,
# measured 2026-10-03. Not in any apt archive on any target, so a hash-pinned
# venv like `rns`. The pins are `uv pip compile --python-platform
# x86_64-unknown-linux-gnu --python-version 3.11 --generate-hashes` from
# `nomadnet==1.4.4` (uv 0.12.23, 2026-10-03), eleven packages and 196 hashes;
# installed with `pip install --require-hashes` into a fresh venv on Python
# 3.13.5 on 2026-10-03, every hash matched.
#
# Licence: the wheel's classifier says MIT and the licence text it ships (and
# the repository's LICENSE, 35,149 bytes) is the GNU GPL v3; GitHub reports
# GPL-3.0. The two statements disagree and the shipped text governs
# (maintainer's ruling, 2026-10-03), so this says GPL-3.0-only and the page
# notes the disagreement. Nothing here is the Reticulum License.
#
# This venv carries its own `rns` and `lxmf`, pinned to the versions the `rns`
# and `lxmf` units pin; tests/test_reticulum_catalog.py holds the three
# Reticulum units to one `rns`.
#
# The launcher is named `nomadnet-terminal` and the exposed wrapper `nomadnet`:
# both are written to ~/.local/bin, and one name would have one overwrite the
# other.
install:
  - install:
      method: venv
      python: ">=3.11"
      licence: "GPL-3.0-only (by the licence text the wheel ships; the wheel's classifier says MIT)"
      licence_url: https://github.com/markqvist/NomadNet/blob/master/LICENSE
      requirements:
        - cffi==2.1.1  --hash=sha256:046bfc24911b37851ee1b51aab8bffe713d89c68c6a057b09484ce9fd5f69b4e  --hash=sha256:06c72bb76605a4b0cd0aad6930b69d4baf7dd5d806cfc409b824191099700e66  --hash=sha256:0beceaabe56af686895136a2de78db54ecd8e4046b236b8fd6d6cb61389e9bf2  --hash=sha256:154852545011f779917b11c78db2358d095da62a9a172b78ad0a583ee5adc0d0  --hash=sha256:194cffa889098ced9976c3fc6340305e43f6303657d298da55366907c05c22d6  --hash=sha256:19ee6127ee34de7d83ce3d371ebc5ed91addbdcc39f9ab15ce4eb35a4e534971  --hash=sha256:1a18a57b58cfb21fc28d72e876acf10eaed67a1ed96226f92af4df681d571c4c  --hash=sha256:1aa5645c30469b09530c4ebca77ebf8f17618293c58f8549cb1a543a50236e7d  --hash=sha256:1dea0e4d7d4f11f619fe8c1d76caf49e24405b4b5743c0e3be16a500ecd930c9  --hash=sha256:208f941bb9d18e768138677f0a6d2ce01f590df56043dda1df1535ac57c88517  --hash=sha256:210019b6c7cf07f081b4c54635c8cf744377001350e29cc0f81c4377b4797735  --hash=sha256:246fa40ce8645a614ff682e0b70f37134e460eaf93a775e0cbe3cca585a67a80  --hash=sha256:25792eac27877609e7bb06d42ff88278a6624fff2ba9bbb523c09616b117e80f  --hash=sha256:27350daa11d4f10c540e6e89dada4c54feb7256ad03e9a4dc075ebad7ba360d1  --hash=sha256:28907ab9bfb6aa13184cfc17c6b8e1023c5ab6fd7076d8c20a35e59fe04f8f29  --hash=sha256:2ae64be792b8966f2c69538199728b290e34726562896df1e5dc8ffd8d8188e8  --hash=sha256:31348097ff5bbe827ccc41795d4dd099d9f0625e7def00ee653c137a490c2a6c  --hash=sha256:3143d81e29e1e20a9ce10901ec369012947876596f75a222235965f2b7ae832e  --hash=sha256:3222ba5d678f80a030e6afbcc33dc1ae5cb45facabb61cee2c7016b8432fde48  --hash=sha256:3311ed60d36f83378794e1009ac6258bafbf81f7888b4caa7b35a521e3f95813  --hash=sha256:334644fbac4eff73d985a17a91226df55d0f394160c4cfb880e084c8f7161cac  --hash=sha256:34e261f78cb6ceaaa36f42f2613f4380d94d9c759a9c73c769ee6e0247364632  --hash=sha256:363e05fa78e15116c3c32c210ee36884fd6b9afa6d440e47112c3bd511d64cb6  --hash=sha256:398aff33cee2767e3e781d2554c54bd0dff386bb437581e0d8011fde1a942ec1  --hash=sha256:3d22a20b1fb1632cc72c22f95f7b0d2961c3e1c235f245ba4c606c4771035659  --hash=sha256:42a494cee34437f05546455144f2b5d9ac09b1face62bcfce597d2e521066688  --hash=sha256:42e2f76b9455f5a9a844f770bf3e200ed3da0e15f5df3db9c31fe80b04b3d004  --hash=sha256:42f6930c31dc7f50732c9ae793c2786c7b6b044195967bbdde40bb9be81c4cc0  --hash=sha256:456a61fa52d579ebf9df2e9552ead5129855dbaff6c1e5a9b1bc408809bdc062  --hash=sha256:471cee653ae88de62096552e6d24ccb4a5adb8c8c9f10b5054d0122c15bf2779  --hash=sha256:49cbc70e6542d4ccccb936558d1064a8012541e78f821f955cff24e357776c94  --hash=sha256:4a7c934f7360e8cd64fe9efadcbd10c7c6364f531e432b9a4bf5ccbc9e0e8b50  --hash=sha256:4be96343e422f2dfcd12ab5c9f5aebe03f82f737c6bffeca6830b3875cb44aab  --hash=sha256:4f42141fc14250de6dde5ee7ea4432be017252d91f19c5ad043c084cea629cac  --hash=sha256:507a24c282e0f42f8ed737cf048572cbf580468da5555764a8331735e9c736b6  --hash=sha256:51b31d1c98274844cfd7838ce00bfc27c7423a4dc00fc0772fc3331c2cc90676  --hash=sha256:58acb8ab8e295e6c5ea12f888cbb13cf21511ef2a3303a23f4325c29d17fe5c1  --hash=sha256:5a59cc1c4442bc3d5c703bf720b51138d0bfc173618807c9ee2490a7541dd3d9  --hash=sha256:5bb4e7ea95dcd6a014a6fef62e62467d67d8e582326443f3d68e71d6320a9fcf  --hash=sha256:5c58fe613dc5e5336357eff555824a314d8e43282600435c8d1cb6a7a2fedd13  --hash=sha256:5e7cecbaadb83884793e05828cee59b210b24583b9c7425d0ba6a754fe22eb4e  --hash=sha256:616f097f2fe415bc92a247f02e11f634e1f9e9a83d327e3c915c15089c87869e  --hash=sha256:63bbfd5ded17c4840ac07cd8f1c21ba9d9708141f840b324f422f41b207e3973  --hash=sha256:64faea20f4e2613363a1a9b9c7dd73058f3ecd00133a511e72ad7c511658f527  --hash=sha256:661c298b4821edebead0c91edd2b00374d67ad7c5a1f7a91d4442633b79d6a72  --hash=sha256:68e62fe11f30d5ca8289242866f0a5291402d8529ca2178ab8afc5c9694ae890  --hash=sha256:6a8dddef476fab96d066d578fc88526767b836ab5ab21754e1d5bf3879c31c7c  --hash=sha256:6e192623c49c94421616a5778fba35cf0d5a8d000650c1967ef4448ee5cdd990  --hash=sha256:7225e4514edb64eb6740324353e0da0711954fd8d7da4576755b1c6e09b697cd  --hash=sha256:75f80557d1389eddbd0de2681f6a390a0c5338c31ddaa821381c203fc3fd50d9  --hash=sha256:770de9db11e84213beec501cfcaa013b019820ca881e03344dea5844f7876d94  --hash=sha256:7750c6449dff7864bb9bb27ddfb0267756189201a3afc911d82b3caacd70dfc3  --hash=sha256:7bde5e4cc5c10140859842b9d383af292b22639a4dffb725314baf45968cef80  --hash=sha256:7ce713ace7c0e4520535b42b77eaa742c16dab813978064913e5a3cf82973b41  --hash=sha256:7da0c5eff80f0197f3b3d1232ec5a682a9325f4ae9016a78f5f5ca35f9ced1f5  --hash=sha256:7dbb61fe3a7699468030f71bbe5f8a0e326a151daa91beb11a6fc1f980c55e1c  --hash=sha256:811bd1e21d32de12efca32393a0ab3f5133b54fce9bd44b8bd77ab07da14bf6a  --hash=sha256:8ef53b2de9bcb9197d31854256575d59dbac0cba72ac627bb291ef5eceb74be4  --hash=sha256:937c0052c05a31ca1daf18de3158eed4dbfcb9cc107adbea227728d647be701e  --hash=sha256:9d2055050ea716bd38b7f7f1579c275386646b4894c155a3e2f3cd62ed41b7c6  --hash=sha256:9f8d177621de5cb38ee3e731eda45d421db093ec0739f46a5594babda7987a98  --hash=sha256:a2d7755bef5a12ed488f4ef1f1b69ee9191d7396083b755a5d2295f6edb4768b  --hash=sha256:a48d62ab9d6f4f98c983223a547af44be6ca3691074c31cecced6facd3ba2dc1  --hash=sha256:a4f00aa42f75d6e4595e8866e748cc1705adc0cddfeb2ca86d0d03993d63ba03  --hash=sha256:a6e721d4b0e45d5b65e87534470e67b18dcd092c83f68fba09f152b9cbc061af  --hash=sha256:a730a083190634c65cca36ba5f489531576ebd79bcd5c8e172130f6453127231  --hash=sha256:a931079504ecc49efed7744c476a5c343a92fabf66dec2db95edb1b2fdc770e2  --hash=sha256:aa9511c62d14da7aacc9b4bf51f3f697a621e83b2d6919008243c3aad168eea3  --hash=sha256:ab36d55f9ed2d067327667c2fea18dda018eb628dd6347aa01dda6cf1f5d3836  --hash=sha256:ad2c86c495b899d862ea0f4b42891b8713a3bd45dd4105c7fd51c2a72f39f3a5  --hash=sha256:aeae0e330c9f6acd681f647d46cefd30c29f93e3392882e792e82080c9691399  --hash=sha256:b0431303acaea1089ad4b3e9ce4e6518193def1118d4073ca848635ee4ea2e96  --hash=sha256:b5bdfd1c873d4e093aabc0ca84c4ca6dbc4f752afb5c86f146d9742580c9da2e  --hash=sha256:baed1e86cc735622097354b9d1281406caf42ff42a886d29faa8e8d1630333be  --hash=sha256:c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf  --hash=sha256:c26608d2222fb1e94487e4a387d85f13eb55d5ed725cb25a0c589ac4ee60e7bc  --hash=sha256:c7659f22557c5a0bc4855cd635f55edec690cc008a40768527762cb9fb263455  --hash=sha256:c8c69575568085ba0b1b10c0249d779a214aea6f6522e949a0fc9fb0fcb449d0  --hash=sha256:c8d2c9fd1f2d16f780d15127abb050d13d1a76c03a4bd87d7e4980e45e511e12  --hash=sha256:ca82be1a1d406ecfe1d25dc16cb33488e5a16bf4438c9fb590484ea29d92478b  --hash=sha256:cc572dace3f60ef98d7b12ff411d20f5362feb31a0439eab0085bbfd349982d7  --hash=sha256:d18e5ac0f2f03f4f518d3e23db0f0cad7faa1da8620e9c09461d443bbf6e6692  --hash=sha256:d28630f5854ab07ab1fd4aba756de52326c82e6be15d414b12793f1975048b54  --hash=sha256:d9c275eaacd24aa73f94ffd6de08fc3f932424d8b6c376f4bed7cde376fe7bc3  --hash=sha256:da0e573f9f97159390c89d9f1a9e41908b66d408cc5b58d08cf3847d844c531b  --hash=sha256:dd31f52ea1086513bb9df30f8fcee9b8918323ae067a3d5b78bc826a000712be  --hash=sha256:dddad92b554513a31f272570678ba307fb9f618f05e3d4a5eacafff9eae03e1d  --hash=sha256:df423d40ee8654634421812bc3b196da3f9bd7d32929da813f8394c4348a5358  --hash=sha256:df913725b79db7bcf03448f36b7bf8815363417d5b58deecf9305e3e30f0f21a  --hash=sha256:e0bcb7e0f677f543555d2adff3bf19c05f66cdb4796e5ff602442ab2fe3c4ef7  --hash=sha256:e2d65b31f36619cda3999b78b2aa9632e76b78448e7a56fc4240824200e7c4fc  --hash=sha256:e6e8cff14d6fb0be70a09c0bdc58096f501952d04624ebf867e0e56da2df8960  --hash=sha256:f16c709686a78c727bbbf059f92b0bf41c6fc60deec706d2dc19f529175a6125  --hash=sha256:f24fb43132a4c6b4cb4eb029492919b2db645be6808d738f244fd146c03c32cb  --hash=sha256:f53e442b08449d42821fa4a4fba000095af9f62742a500f978a9f557ec44339a  --hash=sha256:f5cfbc5fe74540d335175b656c725d74d90e3730c626d92575eea35029d9afaa  --hash=sha256:f81b3b8f3d4e343550fa4baa0e479bba9f2d29ce9c2e9b51d1ce1718d7442fcf  --hash=sha256:f8ec5e643a9a937f64e1999eb9f75d072263751912dc5cd06d3c85f8f44be7c3  --hash=sha256:fb92203a88b3d3053034db775110081c49d28be6551923805e039924093761e4  --hash=sha256:fcd22650c908d7b7da162bbfaab594a1227a15d1643a98c68b122ac642fa2264
        - cryptography==50.0.2  --hash=sha256:0ddc924c04591c2811ca024d62ecad4f7f6f08af8939c211438f48a16bd23602  --hash=sha256:0ec5f09541743261e66e291b4a0cbf0fb2997aeaab6d9e9c740b9dba1b58d1c2  --hash=sha256:0ecbc5652bdb6fc9eaf89a7d196e20941adfe812f43bc4ca05d9150496821047  --hash=sha256:1981f1db4630889b9ef7803fadef12b056f428cb6b85c27ba57b774793b6093c  --hash=sha256:1ba34f04897fcdaa73f74145c25f3ec146fbd56593853e88adc2e811303c5f42  --hash=sha256:241449bf940a5d27309bd317e6f9a2af6932113818bb2b8f5c59ddc7ef16da18  --hash=sha256:25784ce8b9621c90c643efb9e1e2162ab3b0224cae446ad5e70e7fcb1ce18b51  --hash=sha256:3dc4fd8058cea1644971207d530e1a03a184a805ffc8ebdddf0599d78a331b81  --hash=sha256:4061c0079120205fb760c58acab6443e217307dcf05e3702cf970e0689972856  --hash=sha256:4a20ce1e5cb4284a86692fdcba7cb8754185c6b2e5c56fcef3751cf451d3cdc2  --hash=sha256:4e81d95e5bafc2d6e34e4bed780e53e4d5b9a2f928573428aa4d35fbec1eb0de  --hash=sha256:58a0c478eeca76fe5e07993c5a0703def34a6dc6a0cda4f5564639b33112ffe7  --hash=sha256:58ddb5a8e3179d12f19e4ea34d2d32e9d63a4baa142c875c1eb59f41b7243acd  --hash=sha256:630ebfea3bf689d075f82316324ff7433dc447fe6bc1bfc76524b74b4a9567d2  --hash=sha256:6f8700550aa1474a91e5dc07049c46f98b423b5b1ddd0483e0b51362eeeaf5be  --hash=sha256:78198641e5be9521beea5aa782bb551a58068d10e6eb04c9c680c1b69f2e7d45  --hash=sha256:79def8d059362e7831389ed3be0ecdf58a89386e1271e35dd9f5af84e81bffd0  --hash=sha256:7a8701d6b584d76e909e3d305b7d126b41439876a5aaf76cddc67fc230eafa2e  --hash=sha256:7afa5a6602a9f29af1f3a2965f831bae7c9d5d597b7cbb716d41ab3b7d89879c  --hash=sha256:7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5  --hash=sha256:7b75de3c8b3be1cdb1052747c929440c3eea46c1bc2cb8a6e3a48388e9b7b452  --hash=sha256:7c6d0330c472d96f6a6afe24d80dfdf15176c33096f0a4397ae4c60f3dd3be48  --hash=sha256:828d49b0ff5a0e3975865571c5d91dbbdd0d38d8289b249a163e9425413a5e05  --hash=sha256:84f964e537f916e2cc85199e5a88742e964939b575ac8598b3f9d6cc416cdaf1  --hash=sha256:85d0d9a31b9098e98534226d5686b47264b95e62ce459dc2e62fdfc809f9fe93  --hash=sha256:87e9ce85beb6b328ba370cc6e6aea483c92617b4c95b1d33a49297eb662bfb04  --hash=sha256:8c71ba2cd31fc93748c38e1b613200ff1c2665cbfd5341fe3a61cfde35a1430e  --hash=sha256:92e665960f25fcdc73725b9cec7a3824f279ba97a98653afe9ffac2e43668f67  --hash=sha256:94e5e9f108ee10471288214d3d233fbfbb492840a8457eb85178d643ddeb32c7  --hash=sha256:9c8402a82ea0dc4ceeab793db05f0fafa8ca139ca34fcde5df0f596103c74107  --hash=sha256:9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079  --hash=sha256:a582ab2ae1d34f67112cadc86702774c9ea4374df6bca6afe672817203c99134  --hash=sha256:a6557e5f38e065ca9fbdaf7cfc7435ecb1d113aa81a022d1b51921ee7432e227  --hash=sha256:a9f7355e6fab51f6c369b86fb7571cffa05edee2c2121e0380a37fb9ac1cd5c1  --hash=sha256:ab50ee449bf968271e820086f10a33d101dd060370abc10bcd22279be2656539  --hash=sha256:ac9ed99d81760c62fe89d5f0815cdfa1ba9a35141cf30f1c2d044f04b4803d2e  --hash=sha256:b13478603dcd0a2479ff8e87e2c19a7d525734686fe3c49542472293a204212d  --hash=sha256:c423ab384a46c4dff7217b2ea5ba2e11cffdeab6441acd04cf65a369caf0366c  --hash=sha256:c5e67125c7dca78d199ec4e116aa93dbb83494808ecbb8211a2cb09b1bf41dbd  --hash=sha256:c71be1cbfa5cd9a41ee452acf1eccd82b2c05950358b106ec8ceb83411d1a020  --hash=sha256:cbc8738fd8526d80f35cb3a40d41f41a2e7030bb3b18b09a6778ef63d291c2fd  --hash=sha256:ce47f66801c20ec6c6632453bb5960fe38939e9306970b48b3a5a26de7745d94  --hash=sha256:d370b8d1dfcdf7130178137f6fbee6140774a1acc6cacefc4b42643ec11d0a3a  --hash=sha256:d38cdff612d06fa6a32840d5e1b1f7a27cee4a349aa9085d94a67789d6bfd408  --hash=sha256:d8947001be83df1394050758ce0e745dd74fb134eef0a4b5124208dfc3a68c37  --hash=sha256:deb9fde5c60e437ee4821bc9bc39ff31b42135c27e1dc61ef0a629389c1de62e  --hash=sha256:dfe9763530994147d9af1def057a5b9658b00e8f8fe8743d144d1e0911c2e454  --hash=sha256:e105ab60406787da31fccc883fc0f733af1efd78f0136a4599692c4083a73d0c  --hash=sha256:e275096ea1e60cc595cda2836fd4a6c725d1125108b868be17f53684d164e2cc  --hash=sha256:edc3342adf8f697fc5f59c887a304356f147b397809440ed64e2fa6af2f50f37  --hash=sha256:ee247f5c245c9a2fe7c8e2214e295918838e44e00a45a6718451e4004219e767  --hash=sha256:eef4c2f3423810b3070ab391f85436d2f8bbfcb286ac15cbc73190b3563b1f1a  --hash=sha256:f21e8a22c8605750c7af886bab299a363721264061b4ac0a30efb73cfd58efc5  --hash=sha256:f265528741e048bce55c3463ed721fb0aa45a5888d8add8cfeccb3035451bbdc  --hash=sha256:f2f9bd7f90c64fe89253f0a2c05e3c4856072660429ce8831b4235bf29403a67  --hash=sha256:f785f6161f202ab04d8ca194158968798e480ca058943907972da5f12e2881e8  --hash=sha256:f9f6143a8c75945eb960d9eb98905a441394abfa24afaae239d514ffb2586480  --hash=sha256:fa8f5efb344d6908a1ce62f4a24e2e5780f825d6f53f5f50ec5ffacac72936cb  --hash=sha256:fdd28f912fccfec1846a94e2e1e8f9b0012f557f0c46fe4f3eb0d7a87afcf90b
        - lxmf==1.2.0  --hash=sha256:805f053e61082f585efc6d09beffd039fd921174c5e1547a2e690bc479d75b85  --hash=sha256:f14243283b90ad06356071d90394357640924201f9c992dcdfecbc23614fb309
        - nomadnet==1.4.4  --hash=sha256:7d8577e6c1b53e72ac9664382366d5e9163c96a6ccc273d765cae50c50d32e09  --hash=sha256:7fd433b890755b3187bc440d502f6fd50ec9b59bbf655283dff44d4274cf1b35
        - pycparser==3.0  --hash=sha256:600f49d217304a5902ac3c37e1281c9fe94e4d0489de643a9504c5cdfdfc6b29  --hash=sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992
        - pyserial==3.5  --hash=sha256:3c77e014170dfffbd816e6ffc205e9842efb10be9f58ec16d3e8675b4925cddb  --hash=sha256:c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0
        - qrcode==8.2  --hash=sha256:16e64e0716c14960108e85d853062c9e8bba5ca8252c0b4d0231b9df4060ff4f  --hash=sha256:35c3f2a4172b33136ab9f6b3ef1c00260dd2f66f858f24d88418a015f446506c
        - rns==1.5.6  --hash=sha256:57a2498a6581e994b088ad815f096b7c23ed321e3909b44fe1589f8b08506898  --hash=sha256:975a646836749560f4553e4cc82d7dc9774c6c79c8beef08357264e1d8443626
        - typing-extensions==4.16.0  --hash=sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8  --hash=sha256:dc983d19a509c94dba722ee6abd33940f7c05a89e243c47e907eb4db6f1a43e5
        - urwid==4.2.4  --hash=sha256:2a46f1b6564c060494c993b9dc61a9665d7fca20bcaf5d197865b8d65ad92600  --hash=sha256:a4bff322e8b8e407d7809e942e63177790509f5a2a740d27199ce8368f36f113
        - wcwidth==0.9.1  --hash=sha256:03cfca3dcbffa86564290fe3c9978a6191ba003e8ced7f7dbda315fcb3fbe725  --hash=sha256:0665ee822ea04e25801e6e82e5407528be0863e88a17b0e7ca038843a4a3ac0c  --hash=sha256:0d68a30d504c68cfdff2a5f804675c1e7ab4c0bbe878024c8b680ec5579cde67  --hash=sha256:10b00ba23482e352f874d2e8135e7ace9da838646c7dd800566246bbd46125ff  --hash=sha256:356376852357b8fca71fe5415808ec421679e04b4a98eb7c9cb6a7984b911a05  --hash=sha256:40d936d72c9bdc10df43f93a8be502bc5024b487259139f66a328722c07f34a9  --hash=sha256:5823209b0d43af322ce698c689380d7c15ca31fa8e6e3be8459f27031bef0af5  --hash=sha256:61bd7aef9cafb6cb77a37a169998d7928ce82a51522146d11f60db9e7d1cb43a  --hash=sha256:69bb970cf5652b88cfdb9d3fdd1764fc15e5f8ad531643e7bb3e894cd969740e  --hash=sha256:6e1272b7986cefe79783737e38bdb9eaae0682b333c7bd132024441193dd5ce7  --hash=sha256:708158c082364af442f9983de7b6ec9ac0d2e1b825ada25f0911b1f138d55405  --hash=sha256:747fb724223f417a17541a95a17c1dac3a8ef9a0cf41684950f0eab191a35f65  --hash=sha256:991d1c8834f548e9c1f16432075ee84638e122312556bbf1ed595ea8fffc4673  --hash=sha256:9f1636c5075ffd5c2e835b4561874f6e5dd2bbeba3c6c2c99f067d0d16883af8  --hash=sha256:b5da43d6967668982e44a52fb551967d293f86d26cd86036ac95bbdd34394ed9  --hash=sha256:bcb9ed4a367cc025bf1092ac679a156759605182d60b7ed3c28f7221a42ddf55  --hash=sha256:c4cead196551112cb8f43cdd1f80c235ef2456e34b1a9955c424537ec99961b2  --hash=sha256:dc10e262c3ac0abbfd0a2a51e45a848b1b7f500b21ff512630277973ba25674d  --hash=sha256:e0c3a1c45c5b9550c6919a4449e95f5b177f6e165786376981db8f1addae9b21  --hash=sha256:eab587e18e7cadf1a750b0098fc8bebfb62c125eb9306f2268f0443a282a3d78  --hash=sha256:fe021c4d8de9d36c31a0cb41d0d2546dadd3b0708a301f1a0c66ce200851831f
      expose:
        - nomadnet
    note: >-
      Pins resolved on 2026-10-03 from `nomadnet==1.4.4`. Bumping means
      resolving `rns`, `lxmf` and `nomadnet` together and changing all three
      units in one commit.

depends: [python3-venv]

# A terminal program: the menu entry opens a terminal window and the wrapper
# holds it open at exit, as the engine's other terminal launchers do.
launchers:
  - name: nomadnet-terminal
    exec: "{venv}/bin/nomadnet"
    title: NomadNet (Reticulum messaging and pages)
    terminal: true

update:
  probe:
    method: pypi
  strategy: reinstall
  cadence_hint: >-
    97 releases; 1.4.4 on 2026-09-30. It demands `rns>=1.5.5` and `lxmf>=1.2.0`,
    so the three Reticulum units are bumped together: see `rns`.

documentation:
  what_it_does: >-
    A text-mode messenger and page browser for Reticulum. It sends and
    receives encrypted LXMF messages, shows "nodes" (pages and files other
    people's machines publish), and can host pages and files of your own. You
    start it in a terminal as `nomadnet`, or from the menu. Everything runs over
    whatever Reticulum is attached to: the local network, a TCP link, an RNode
    on LoRa.
  why_you_want_it: >-
    It is the quickest way to see Reticulum doing something useful: two laptops
    on one network can message each other with no server and no accounts, and
    the same conversation continues over a radio link when the network goes
    away. It is the Reticulum equivalent of a BBS client and a mail client in
    one, which is why the `mesh` profile carries it.
  prerequisites: >-
    The `rns` unit's service running (`systemctl --user start hammunition-rnsd`,
    or log in again after install) so NomadNet attaches to the shared instance;
    without it NomadNet starts its own and everything else loses the network
    when you quit. For anything beyond the local network, an interface in
    `~/.reticulum/config`; the guide shows them.
  known_problems: >-
    **The licence statements disagree.** The wheel's classifier says MIT and
    the licence text it ships, and the repository's LICENSE, is the GNU GPL v3;
    GitHub reports GPL-3.0. The shipped text governs here: this manifest says
    GPL-3.0-only (the maintainer's ruling, 2026-10-03).

    **It keeps your identity and messages in `~/.nomadnetwork`** (created on
    first run; measured 2026-10-03), which `hammunition uninstall nomadnet`
    leaves in place: the identity is yours, and so is every conversation in it.
    The configuration there is NomadNet's, not Reticulum's; Reticulum's is
    `~/.reticulum/config`.

    **Run it in daemon mode (`nomadnet -d`) only on purpose:** it then serves
    your pages and accepts messages with nobody at the keyboard. About 27 MB in
    its own venv. Only `nomadnet -d` against an interfaceless shared instance
    was run on 2026-10-03 (it attached and kept running); the text interface
    and a message between two machines were not measured.
  upstream_url: https://github.com/markqvist/NomadNet
  upstream_support: >-
    GitHub issues on markqvist/NomadNet.
```

- [ ] **Step 6: Run the tests to see them pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_catalog.py -p no:cacheprovider
```

Expected: `19 passed`.

- [ ] **Step 7: See the launcher table go red, then fix it**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_verify_tree_launchers.py -p no:cacheprovider 2>&1 | grep -E "nomadnet|failed"
```

Expected: `1 failed, 18 passed`: `test_every_catalog_launcher_working_directory_is_under_the_shared_prefix` fails and the diff names `{'nomadnet': ('nomadnet-terminal',)}`: the table pins every launcher name.

- [ ] **Step 8: Add the launcher to the table**

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("tests/test_verify_tree_launchers.py")
s = p.read_text()
old = '        "navit": ("navit-offline",),\n'
assert old in s
p.write_text(s.replace(old, old + '        "nomadnet": ("nomadnet-terminal",),\n', 1))
PY
```

- [ ] **Step 9: Track the new files and regenerate the generated pages**

`tests/test_repo_hygiene.py` fails on an untracked source file, so everything is `git add`ed before the tests run. The package reference, the projects page, the parity report and the capability matrix are generated from the manifests and a test asserts regenerating is a no-op (CLAUDE.md: a generated page is never hand-edited).

Run:

```bash
git add -A
.venv/bin/python scripts/gen_package_reference.py
.venv/bin/python scripts/gen_projects_page.py
.venv/bin/python scripts/gen_parity_coverage.py
.venv/bin/python scripts/gen_capability_matrix.py
git add -A
git status --short
```

Expected: four `wrote ...` lines; `git status --short` lists the new manifest, its generated page `docs/packages/nomadnet.md`, and the modified `docs/packages/index.md`, `docs/projects.md`, `docs/reference/capability-matrix.md` and `docs/reference/parity-coverage.md`.

- [ ] **Step 10: Bring the README's manifest count to the catalog's**

The README quotes the manifest count and `tests/test_docs_generated.py` holds it to the catalog; this reads the catalog and edits the one row, so it is right whatever number `main` carries.

```bash
python3 - <<'PY'
import pathlib, re, sys
sys.path.insert(0, "src")
from hammunition.manifest.load import load_catalog

n = len(load_catalog(pathlib.Path("catalog/packages")))
p = pathlib.Path("README.md")
s = p.read_text()
new, hits = re.subn(r"(\| Package manifests \| 🟡 \*\*)\d+(\*\*)", rf"\g<1>{n}\g<2>", s, count=1)
assert hits == 1, "the README's manifest-count row moved: find it and edit it by hand"
p.write_text(new)
print("README says", n, "manifests")
PY
```

- [ ] **Step 11: Bring the README's launcher count to the catalog's**

```bash
python3 - <<'PY'
import pathlib, re, sys
sys.path.insert(0, "src")
from hammunition.manifest.load import load_catalog

n = sum(1 for m in load_catalog(pathlib.Path("catalog/packages")).values() if m.launchers)
p = pathlib.Path("README.md")
s = p.read_text()
new, hits = re.subn(r"(working — )\d+( units carry launchers;)", rf"\g<1>{n}\g<2>", s, count=1)
assert hits == 1, "the README's launcher row moved"
p.write_text(new)
print("README says", n, "units carry launchers")
PY
```

- [ ] **Step 12: Run the tests that read the catalog, the generated pages and the launchers**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_docs_generated.py tests/test_categories.py tests/test_site.py tests/test_json_catalog.py tests/test_repo_hygiene.py tests/test_reticulum_catalog.py -p no:cacheprovider tests/test_verify_tree_launchers.py tests/test_launchers.py tests/test_launcher_shadowing.py -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 13: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict tests/test_reticulum_catalog.py tests/test_verify_tree_launchers.py
```

Expected: clean.

- [ ] **Step 14: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Add the nomadnet unit: the terminal messenger and its menu entry

A hash-pinned venv, GPL-3.0-only by the licence text it ships, one exposed
command and a terminal launcher named so it cannot overwrite it.
Track C, issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 6: The `rnode` hardware entry and its generated page

**Files:**
- Create: `catalog/hardware/devices/rnode.yaml`
- Create: `tests/test_rnode_catalog.py`
- Modify: `scripts/gen_hardware_gaps.py` (one table entry), `mkdocs.yml` (one nav line)
- Modify (generated): `docs/hardware/rnode.md`, `docs/hardware/index.md`, `docs/hardware/badgelife-class.md`, `docs/reference/hardware-gaps.md`, `docs/reference/device-naming.md`
- Modify: `README.md` (device counts)

**Interfaces:**
- Consumes: Task 3's `rns` unit (the entry names it as the package that installs `rnodeconf`).
- Produces: device `rnode` (class `badgelife`, `untested`, no identifier, no symlink); the page `docs/hardware/rnode.md` is generated from its `documentation` block, not written by hand.

- [ ] **Step 1: What the entry is, and why it is `untested`**

RNode is firmware on a family of boards, so there is no identifier to carry. Read on 2026-10-03: Reticulum's manual (1.5.5, "Communications Hardware") lists fifteen boards the auto-installer supports, and `markqvist/RNode_Firmware`'s `Boards.h` (GPL-3.0, last pushed 2026-09-27) defines 21 board identifiers and model codes for 433 MHz, 868 MHz and 850-950 MHz variants. **Neither names a USB vendor or product id**, because a flasher addresses a serial port. So the entry claims no identifier (the spec's "the identifiers the LoRa sweep attributes to the boards RNode supports" has no source: RNode publishes no board-to-id list), inherits the `badgelife` class (`dialout`, `esptool`, serial tools), emits no symlink (D-028), and says why in `identification_gap`. **Its status is `untested`, not the spec's `supported`:** `tests/test_hardware.py::test_devices_without_confirmed_ids_are_not_marked_supported` and D-018/D-027 refuse `supported` for an entry with no identifier of its own. Review Focus 3 (`rnodeconf` cannot open the port) is pinned by the second test below: the entry must inherit `dialout`, not override it with a list that lacks it.

- [ ] **Step 2: Write the failing test**

Create `tests/test_rnode_catalog.py` with exactly this content:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `rnode` hardware entry: firmware, not a board.  Track C, D-080.

Closed from upstream's board lists, which name boards and no USB identifier, so
the entry claims no identifier, no symlink and no maintainer verification, and
inherits the serial-board class's permission story (D-027, D-028, D-029).
"""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.hardware import DeviceManifest
from hammunition.manifest.load import load_catalog, load_hardware
from hammunition.manifest.schema import VenvInstall

ROOT = Path(__file__).resolve().parent.parent


def _rnode() -> DeviceManifest:
    _, devices = load_hardware(ROOT / "catalog" / "hardware")
    return devices["rnode"]


def test_the_entry_claims_no_identifier_no_symlink_and_no_verification() -> None:
    rnode = _rnode()
    # `supported` is earned by an identifier of its own (D-018, D-027); there is none to confirm.
    assert rnode.status == "untested"
    assert rnode.maintainer_verified is None  # nobody here has run an RNode
    assert rnode.usb_ids == [] and rnode.udev is None  # D-028: a bridge chip names no /dev node
    assert rnode.gap_closure == "unverified_by_maintainer"
    assert rnode.identification_gap and "no USB identifier of its own" in rnode.identification_gap


def test_an_rnode_inherits_dialout_so_rnodeconf_can_open_the_port() -> None:
    """The first thing that fails for a new operator: `rnodeconf` cannot open
    /dev/ttyACM0 or /dev/ttyUSB0. The class gives the group; the entry must not
    override it with a list that lacks it."""
    classes, devices = load_hardware(ROOT / "catalog" / "hardware")
    rnode = devices["rnode"]
    assert rnode.device_class == "badgelife"
    assert rnode.groups == []  # inherits; an explicit list here would replace the class's
    assert "dialout" in classes["badgelife"].groups
    assert "dialout" in (rnode.documentation.setup_steps or "")


def test_the_flasher_it_names_is_installed_by_the_rns_unit() -> None:
    rnode = _rnode()
    assert rnode.packages == ["rns"]
    (firmware,) = rnode.firmware
    assert firmware.kind == "vendor_tool" and firmware.packages == ["rns"]
    (block,) = load_catalog(ROOT / "catalog" / "packages")["rns"].install
    assert isinstance(block.install, VenvInstall) and "rnodeconf" in block.install.expose


def test_the_legal_note_is_a_disclosure_not_a_ruling() -> None:
    """Part 97 and encryption: said, never adjudicated (D-021's rule for gates,
    applied to prose)."""
    problems = _rnode().documentation.known_problems
    assert problems is not None
    assert "Part 97" in problems and "stated as disclosure and not as a ruling" in problems
    assert "not for this catalog to say" in problems
    for forbidden in ("is legal", "is lawful on", "you may transmit", "is permitted"):
        assert forbidden not in problems
```

- [ ] **Step 3: Run it to see it fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_rnode_catalog.py -p no:cacheprovider
```

Expected: `4 failed` with `KeyError: 'rnode'`.

- [ ] **Step 4: Write the entry**

Create `catalog/hardware/devices/rnode.yaml` with exactly this content:

```yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

kind: device
name: rnode
summary: RNode, Reticulum's LoRa transceiver firmware, on the LilyGO, Heltec and RAK boards it supports
vendor: various (LilyGO, Heltec Automation, RAK Wireless, unsigned.io, Liberated Embedded Systems)
device_class: badgelife
status: untested

# Recorded from upstream data, not from hardware, as `meshtastic` is, and for the
# same reason: RNode is not one board, it is firmware (and an open design) that
# runs on a family of them. `untested`, not `supported`: `supported` is earned by
# a confirmed identifier of the entry's own (D-018, D-027; the catalog's own test
# refuses it otherwise), and there is none to confirm. No RNode has been run here.
#
# What was read, 2026-10-03, and what it does NOT contain:
#   * Reticulum's manual (1.5.5), "Communications Hardware", lists the boards
#     the auto-installer supports: fifteen, from the LilyGO T-Beam, T-Beam
#     Supreme, T3S3, LoRa32 v1.0/2.0/2.1, T-Deck and T-Echo, through the RAK4631
#     boards, Heltec LoRa32 v2/v3/v4 and T114, to the OpenCom XL and unsigned.io's
#     RNode v2.x.
#   * markqvist/RNode_Firmware (GPL-3.0, last pushed 2026-09-27) `Boards.h`
#     defines 21 board identifiers and the model codes for their 433 MHz, 868 MHz
#     and (Heltec v4) 850-950 MHz variants. It names no USB vendor or product id:
#     a flasher addresses a serial port, so the file has no reason to.
# So there is no identifier to carry, and none is invented. A board enumerates as
# its base board does (ESP32-S3 native USB, CP210x or CH34x bridge, nRF52840), the
# same silicon the `badgelife` class and `meshtastic` already carry, each already
# marked ambiguous by measurement. No udev symlink (D-028): the chips are the ones
# the rig cable uses.
identification_gap: >-
  RNode is firmware, so it has no USB identifier of its own, and upstream's board
  list (Boards.h in RNode_Firmware, and Reticulum's manual) names boards but no
  VID:PID, so no identifier can be taken from it without a capture. A board
  presents the identifiers of its base module, which the badgelife class and the
  meshtastic entry already carry as ambiguous. What no source records is what a
  *provisioned RNode* reports in its manufacturer and product strings, which is
  the only thing that could make a per-board rule safe.
gap_closure: unverified_by_maintainer

packages: [rns]
firmware:
  - kind: vendor_tool
    packages: [rns]
    note: >-
      `rnodeconf` (installed by the `rns` unit) identifies, flashes, provisions and
      configures an RNode; `rnodeconf --autoinstall` walks through it. It fetches
      firmware from upstream itself unless told otherwise. Where it fetches from
      and whether it verifies the download were not measured. Firmware that runs
      on the board is upstream's, not something this project installs (D-026).

documentation:
  what_it_is: >-
    A LoRa radio modem for Reticulum: an open design and firmware (upstream's
    RNode_Firmware, GPL-3.0) that turns a common LoRa development board into a
    serial or Bluetooth device Reticulum can use as a network interface. It is not
    one product from one vendor. Reticulum's manual lists fifteen supported boards
    (LilyGO T-Beam, T-Beam Supreme, T3S3, LoRa32, T-Deck and T-Echo, the RAK4631
    boards, Heltec LoRa32 and T114, the OpenCom XL, unsigned.io's RNode v2) and says
    RNode uses raw LoRa modulation and has nothing to do with LoRaWAN.
  what_you_can_do_with_it: >-
    Carry Reticulum over kilometres of radio with no infrastructure: attach the
    board, add an `RNodeInterface` to `~/.reticulum/config` with a frequency,
    bandwidth, spreading factor and transmit power, and every Reticulum program
    (NomadNet, `rnsh`, `rncp`) reaches whoever else is on that channel. An RNode
    is a different network from Meshtastic's and the two do not talk.
  setup_steps: >-
    Install the `mesh` profile (`hammunition install mesh`), which brings `rnodeconf`
    with `rns`; add yourself to `dialout` and log out and back in. Attach the
    board and run `rnodeconf --autoinstall` as Reticulum's manual describes, then
    add the interface; docs/guides/mesh-and-reticulum.md section 6 has the stanza and
    the options. Nothing here has been run against a board.
  known_problems: >-
    **Frequency and power are yours to get right.** Radio spectrum is regulated and
    varies by country; upstream's manual says so beside every radio interface. Two
    things to know before you transmit on an amateur band, stated as disclosure and
    not as a ruling: Reticulum encrypts every packet, and in the United States
    Part 97 forbids messages encoded to obscure their meaning on amateur
    frequencies, so whether a given link is lawful is for you to establish, not for
    this catalog to say; and upstream's manual says RNodes most commonly use LoRa in
    the common ISM bands, which have their own power and duty-cycle rules (upstream's
    RNodeInterface has `airtime_limit_long` and `airtime_limit_short`, and
    `id_callsign` and `id_interval` for identification). A serial port that is
    parked or that you cannot open is the same `dialout` and parked-device story as
    any other board. The board lists above are upstream's as read on 2026-10-03,
    not a claim about which boards work.
  upstream_url: https://github.com/markqvist/RNode_Firmware
```

- [ ] **Step 5: Run the test to see it pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_rnode_catalog.py -p no:cacheprovider
```

Expected: `4 passed`.

- [ ] **Step 6: Give the gap report a real line for the new entry**

`scripts/gen_hardware_gaps.py` keeps a per-device table of what a gap blocks; without an entry the report says `Not assessed.`

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("scripts/gen_hardware_gaps.py")
s = p.read_text()
old = '    "limesdr": ("post-1.0", "No SDR in the 1.0 profiles depends on it."),\n'
new = '''    "rnode": (
        "nothing",
        "Closed from upstream's board lists (Reticulum's manual and RNode_Firmware's "
        "Boards.h, read 2026-10-03), which name boards and no USB identifier. A board "
        "enumerates as its base module, which the badgelife class already covers. What "
        "is left is what a provisioned RNode reports in its strings: a contribution "
        "ask for anyone owning one.",
    ),
''' + old
assert old in s, "gen_hardware_gaps.py's table moved"
p.write_text(s.replace(old, new, 1))
PY
```

- [ ] **Step 7: Put the page in the nav**

`tests/test_site.py` fails any page that is in no nav.

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("mkdocs.yml")
s = p.read_text()
old = "          - Meshtastic nodes: hardware/meshtastic.md\n"
assert old in s, "the hardware nav moved"
p.write_text(s.replace(old, old + "          - RNode, Reticulum's LoRa radio: hardware/rnode.md\n", 1))
PY
```

- [ ] **Step 8: Regenerate the hardware pages**

Run:

```bash
git add -A
.venv/bin/python scripts/gen_hardware_reference.py
.venv/bin/python scripts/gen_hardware_gaps.py
.venv/bin/python scripts/gen_device_naming.py
git add -A
git status --short
```

Expected: three `wrote ...` lines (`wrote 44 files to docs/hardware`, the gaps report, `wrote docs/reference/device-naming.md: 34 devices, 29 where by-id is insufficient, 7 symlinks, 0 overlapping`); `docs/hardware/rnode.md` appears as a new file.

- [ ] **Step 9: Bring the README's device counts to the catalog's**

Five hand-typed numbers on the front page derive from the hardware catalog (`tests/test_hardware.py::test_the_readme_hardware_counts_match_the_catalog` holds two of them; the rest are prose that would rot). The supported/run-here pair is unchanged because `rnode` is `untested`.

```bash
python3 - <<'PY'
import pathlib, re, sys
sys.path.insert(0, "src")
from hammunition.manifest.load import load_hardware

classes, devices = load_hardware(pathlib.Path("catalog/hardware"))
n = len(devices)
p = pathlib.Path("README.md")
s = p.read_text()
subs = [
    (r"(\| Hardware catalog \| 🟡 )\d+( devices,)", rf"\g<1>{n}\g<2>"),
    (r"(the 29 of )\d+( devices where it does not)", rf"\g<1>{n}\g<2>"),
    (r"(\*\*Non-serial devices\*\* \| 15 of )\d+( present nothing serial)", rf"\g<1>{n}\g<2>"),
    (r"(Of )\d+( catalogued devices, \*\*29 are ones)", rf"\g<1>{n}\g<2>"),
]
for pattern, repl in subs:
    s, hits = re.subn(pattern, repl, s, count=1)
    assert hits == 1, f"README row moved: {pattern}"
old = """Eighteen of
the 33 catalogued devices still have something unknown about them, and ten of
those are waiting"""
new = f"""Nineteen of
the {n} catalogued devices still have something unknown about them, and eleven of
those are waiting"""
assert old in s, "the README's hardware-gap sentence moved"
p.write_text(s.replace(old, new, 1))
print("README says", n, "devices")
PY
```

- [ ] **Step 10: Run the hardware, generated-page and site tests**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_rnode_catalog.py tests/test_hardware.py tests/test_docs_generated.py tests/test_site.py tests/test_repo_hygiene.py -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 11: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict tests/test_rnode_catalog.py scripts/gen_hardware_gaps.py
```

Expected: clean.

- [ ] **Step 12: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Add the rnode hardware entry

RNode is firmware on a family of boards and upstream names no USB id, so the
entry carries none, inherits the serial-board class and is untested. The page
is generated. Track C, issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 7: The guide, four troubleshooting entries, the nav and the CLI reference line

**Files:**
- Create: `docs/guides/mesh-and-reticulum.md`
- Create: `tests/test_reticulum_docs.py`
- Modify: `docs/troubleshooting/running.md` (four entries), `docs/troubleshooting/index.md` (four lines), `docs/guides/index.md`, `docs/reference/cli.md` (one line), `mkdocs.yml` (one nav line)

**Interfaces:**
- Consumes: Tasks 3 to 6 (the guide quotes the units' pins, the service, the exposed tools and the `rnode` page) and Task 0's `docs/reference/mesh-inventory.md`.
- Produces: guide sections 1 to 13 (section 13 is rewritten in Task 11 from the container run), the anchors `reticulum-no-instance`, `reticulum-another-instance`, `reticulum-autointerface` and `rnodeconf-port` in `docs/troubleshooting/running.md`.

- [ ] **Step 1: What was read to write it**

Every option and command in the guide was read from the installed programs on 2026-10-03 (`--help` of `rnsd`, `rnstatus`, `rnprobe`, `rnsh`, `rnid`, `rncp`, `rnx`, `lxmd`, `nomadnet`, `rnodeconf`, `rnpath` and `meshtastic` 2.7.11 from hash-pinned scratch virtualenvs), and every interface stanza from Reticulum's manual (1.5.5) read the same day. **The spec expected the manual to list public community entry points; it does not.** It calls a pasted list of hard-coded entrypoints a common mistake, recommends interface discovery (`discover_interfaces`, `bootstrap_only`, `rnstatus -d` and `-D`), and points at `directory.rns.recipes` and `rmap.world`. The guide says that, carries the manual's own example host (`amsterdam.connect.reticulum.network`) as an example of the shape, and carries no list; a test holds that. **The spec's "packet TNC: the KISS port which `packet` already configures" is right**: the `direwolf` unit writes `/etc/direwolf.conf` with `KISSPORT 8001` from the station values (D-035).

The guide is project documentation in the voice of `docs/guides/offline-navigation.md` (numbered sections, every command copy-pasteable, a closing measured-and-not section), not the social voice the `chiefgyk3d-voice` skill covers. Placeholders only: `N0CALL`, `FN31pr`, and a made-up hash where a destination hash goes.

- [ ] **Step 2: Write the failing test**

Create `tests/test_reticulum_docs.py` with exactly this content:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Reticulum guide and the troubleshooting entries an operator lands on.  D-080.

Docs are a deliverable here, and what an operator hits first is the symptom, so
the symptoms the unit pages and the guide name must have entries that say what
they name. The station is never a real one: placeholders only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hammunition.manifest.load import load_catalog

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "guides" / "mesh-and-reticulum.md"
RUNNING = ROOT / "docs" / "troubleshooting" / "running.md"
TROUBLE_INDEX = ROOT / "docs" / "troubleshooting" / "index.md"

# The exact line rnsd logs when it finds an instance already running (measured
# 2026-10-03, rns 1.5.6). The rns page, the guide and the entry must agree on it.
ANOTHER_INSTANCE = "connected to another shared local instance, this is probably NOT what you want!"

# Anything shaped like a callsign or a grid square that is not a placeholder is a
# station, and a station is never public (N0CALL and FN31pr are the placeholders;
# I2P is the anonymity network, not a callsign).
CALLSIGN = re.compile(r"(?<![A-Za-z0-9_-])[A-Z]{1,2}\d[A-Z]{1,3}(?:-\d{1,2})?(?![A-Za-z0-9_])")
GRID = re.compile(r"(?<![A-Za-z0-9])[A-R]{2}\d\d(?:[a-x]{2})?(?![A-Za-z0-9])")


def _text(path: Path) -> str:
    return path.read_text()


def _flat(text: str) -> str:
    """The text with every run of whitespace, line breaks included, as one space:
    prose is wrapped, and a phrase is not two phrases because it was."""
    return " ".join(text.split())


def test_the_guide_has_its_thirteen_sections_in_order_and_ends_on_what_is_measured() -> None:
    sections = re.findall(r"^## (\d+)\. (.+)$", _text(GUIDE), re.MULTILINE)
    assert [int(number) for number, _ in sections] == list(range(1, 14))
    assert sections[-1][1] == "What is measured, and what is not"


def test_the_guide_and_the_new_pages_name_no_real_station() -> None:
    pages = [GUIDE, RUNNING, ROOT / "docs" / "hardware" / "rnode.md"]
    for page in pages:
        text = _text(page)
        callsigns = set(CALLSIGN.findall(text)) - {"I2P"}
        grids = set(GRID.findall(text)) - {"FN31pr"}
        assert not callsigns, f"{page.name}: callsign-shaped text that is not a placeholder"
        assert not grids, f"{page.name}: grid-square-shaped text that is not a placeholder"
    assert "N0CALL" in _text(GUIDE) and "FN31pr" not in _text(RUNNING)


def test_the_part_97_note_is_a_disclosure_and_never_a_ruling() -> None:
    text = _flat(_text(GUIDE))
    assert "Part 97 forbids messages encoded to obscure their meaning" in text
    assert "not something this guide can tell you is lawful" in text
    assert "as disclosure and not as a ruling" in text
    for ruling in ("is legal", "is lawful on", "you may transmit", "is permitted on"):
        assert ruling not in text


@pytest.mark.parametrize(
    "anchor",
    [
        "reticulum-no-instance",
        "reticulum-another-instance",
        "reticulum-autointerface",
        "rnodeconf-port",
    ],
)
def test_each_symptom_has_an_entry_an_index_line_and_a_link_from_the_guide(anchor: str) -> None:
    assert f'<a name="{anchor}"></a>' in _text(RUNNING), anchor
    assert f"running.md#{anchor}" in _text(TROUBLE_INDEX), anchor
    assert f"troubleshooting/running.md#{anchor}" in _text(GUIDE), f"the guide never links {anchor}"


def test_the_second_instance_symptom_is_quoted_the_same_everywhere() -> None:
    """The log line is what an operator pastes into a search; it is measured, so
    the page, the guide and the entry carry it verbatim."""
    rns = load_catalog(ROOT / "catalog" / "packages")["rns"].documentation.known_problems
    assert rns is not None
    for text in (rns, _text(GUIDE), _text(RUNNING)):
        assert ANOTHER_INSTANCE in _flat(text)


def test_the_guide_says_the_shared_instance_is_a_socket_and_not_a_port() -> None:
    text = _flat(_text(GUIDE))
    assert "It is a local socket, not a TCP port" in text
    assert "@rns/default" in text and "not private to your account" in text


def test_the_guide_does_not_carry_a_list_of_public_entry_points() -> None:
    """Upstream's own manual calls a pasted list of hard-coded entrypoints a
    common mistake, and an address that was up when this was written is not
    evidence that it is now. The one hostname is the manual's own example."""
    hosts = set(re.findall(r"[a-z0-9.-]+\.connect\.reticulum\.network", _text(GUIDE)))
    assert hosts == {"amsterdam.connect.reticulum.network"}


def test_the_guide_lists_what_uninstall_leaves_and_how_to_back_it_up() -> None:
    text = _text(GUIDE)
    for kept in ("~/.reticulum", "~/.nomadnetwork", "~/.lxmd", "~/.rnsh"):
        assert kept in text, kept
    assert "mesh-identities-" in text


def test_the_cli_reference_names_the_user_service_row() -> None:
    cli = _text(ROOT / "docs" / "reference" / "cli.md")
    assert "(`gps-tether`, `rig`, `rns`)" in cli
```

Review Focus 1 (two laptops see no peers) is pinned by `test_each_symptom_has_an_entry_an_index_line_and_a_link_from_the_guide[reticulum-autointerface]`, which holds the entry, its index line and the guide's link to it, and Review Focus 2 (a second Reticulum program owns the shared instance) by `test_each_symptom_has_an_entry_an_index_line_and_a_link_from_the_guide[reticulum-another-instance]` and `test_the_second_instance_symptom_is_quoted_the_same_everywhere` (the page, the guide and the entry must carry the measured log line verbatim). The Part 97 test holds the disclosure-not-ruling wording; the station test holds that no callsign or grid shaped text other than the placeholders reaches a page.

- [ ] **Step 3: Run it to see it fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_docs.py -p no:cacheprovider
```

Expected: every test fails with `FileNotFoundError` for `docs/guides/mesh-and-reticulum.md` (`test_the_cli_reference_names_the_user_service_row` fails on its assertion).

- [ ] **Step 4: Write the guide**

Create `docs/guides/mesh-and-reticulum.md` with exactly this content:

````markdown
<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Mesh and Reticulum: messaging with no infrastructure

Most of what an operator runs for emergency communications leans on
something that is somebody else's: a repeater, a gateway, an internet
service. Reticulum is a networking stack that assumes none of them. The
`mesh` profile puts it on the laptop, with NomadNet (an encrypted messenger
and page browser for the terminal), LXMF (the message layer under it), the
RNode flasher for LoRa radios, and the two Meshtastic clients the catalog
already carried. Two laptops on one network find each other with no setup;
the same programs then reach further over a LoRa radio, a packet modem or
the internet. The decision record behind it is **D-080** in
`docs/DECISIONS.md`, and the inventory it rests on is
`docs/reference/mesh-inventory.md`.

It is the laptop-in-a-passenger-seat case: no tower, no gateway, a radio or
two and the notes to run them. Daily use and EMCOMM are the same setup. The
way to be ready is to have used it on ordinary days, so the identity you will
need and the habits to go with it already exist.

**Where things are in this page.** Sections: 1 what Reticulum is; 2 install;
3 first run, and two laptops on one network; 4 NomadNet; 5 the internet; 6 LoRa
with an RNode; 7 a packet TNC; 8 a shell on another laptop; 9 a propagation
node; 10 EMCOMM notes; 11 Meshtastic beside it; 12 removing it. The page ends
with what has and has not been measured.

The examples use `N0CALL` for a callsign and `FN31pr` for a grid square, and
a made-up hash where a destination hash goes. Put your own in their place.

---

## What you need first

- **An ordinary account, not root.** Everything here runs as you and keeps
  its files in your home directory.
- **A network connection at install time**, and only then, for the local
  network case. The Reticulum programs come from PyPI against pinned hashes.
- **A second machine on the same network**, for the two-laptop test in
  section 3. One machine can run every command here, but nothing is
  worth messaging until there is somebody on the other end.
- **For radio**, an RNode (section 6) or a packet modem (section 7), and
  membership of the `dialout` group: `docs/hardware/rnode.md` and the
  [serial permission entry](../troubleshooting/running.md#dialout) say how.
- **About 70 MB of disk** for the three Reticulum environments, plus the two
  Meshtastic packages.

The profile is marked post-1.0: it is built and its pieces are tested, and no
LoRa link has been run through it. [What is measured, and what is
not](#13-what-is-measured-and-what-is-not) lists exactly what that means.

---

## 1. What Reticulum is

Reticulum is not a service you subscribe to and not one global network you
join. Upstream's manual puts it as "a networking stack; a toolkit for building
communications systems that align with your specific values, requirements, and
operational environment" (the manual for 1.5.5, read on 2026-10-03). Three
things make it different from the networks an operator already knows:

- **Addresses are keys.** A destination is the hash of a public key, 32
  hexadecimal characters such as `c89b4da064bf66d280f0e4d8abfd9806` (the
  example hash from upstream's manual). There is no registry, no callsign
  lookup and nobody to ask for one.
- **Every packet is encrypted**, between the two ends, whatever carries it.
  Section 6 says why that matters on an amateur band.
- **Any medium that can carry a few hundred bytes will do.** The interface
  types in the installed version (listed from `RNS/Interfaces/`, 2026-10-03)
  include `AutoInterface` (a local network with no configuration),
  `TCPClientInterface` and `TCPServerInterface` and `BackboneInterface` (the
  internet or a private network), `RNodeInterface` (LoRa), `KISSInterface` and
  `AX25KISSInterface` (a packet modem), `SerialInterface`, `UDPInterface`,
  `I2PInterface`, `PipeInterface`, `WeaveInterface` and `LocalInterface`.
  One instance can run several at once and route between them.

**What it is not.** It is not Meshtastic: a Meshtastic node and a Reticulum
node do not exchange messages, and a LoRa board runs one firmware or the
other. It is not Winlink or APRS: those are station-to-station on amateur
bands under callsigns, and a Reticulum address is a key. They coexist on one
laptop, and a KISS modem such as Direwolf, which the `packet` profile
installs, can carry Reticulum as well (section 7).

---

## 2. Install

Look before you install:

```
hammunition install mesh --dry-run
```

Among the rest of the plan, the Reticulum programs print their licence on the
line that installs them. For `rns` it reads, in part:

```
Install rns into its venv — every wheel verified against the manifest's sha256 pins; licence: Reticulum License (MIT plus two use restrictions; not OSI-approved) (https://github.com/markqvist/Reticulum/blob/master/LICENSE)
```

and the service the profile will write is listed under *User services*, run
as you and not as root, with the command it will run, the `systemctl --user`
commands that enable it, and a line saying it is not started now but at your
next login. It lists no listening port, because it has none (section 3).

Then install for real:

```
hammunition install mesh
```

Run it as yourself. Nothing needs root unless a Meshtastic package has to
come from the archive, and then the plan shows the `sudo` step first.

**What the licence means for you.** Reticulum and LXMF are under the
Reticulum License: the MIT text plus two added conditions, which upstream's
LICENSE states (read 2026-10-03):

> The Software shall not be used in any kind of system which includes amongst
> its functions the ability to purposefully do harm to human beings.
>
> The Software shall not be used, directly or indirectly, in the creation of
> an artificial intelligence, machine learning or language model training
> dataset, including but not limited to any use that contributes to the
> training or development of such a model or algorithm.

It is not on the OSI list. Hammunition installs it from PyPI at your
direction, never mirrors or vendors it, prints the terms and does not judge
your use of them (**D-033**, **D-021**). NomadNet is a different matter: its
wheel's metadata says MIT while the licence text it ships, and the one in its
repository, is the GNU GPL v3; the shipped text governs here, so the manifest
says GPL-3.0-only.

**Where the programs went.** Each of `rns`, `lxmf` and `nomadnet` is a
per-user virtualenv under `~/.local/share/hammunition/venvs/`, with a small
wrapper for every command in `~/.local/bin`. If a new shell says `rnstatus:
command not found`, `~/.local/bin` is not on your `PATH` yet: see [A
venv-installed program is "not found"](../troubleshooting/running.md#local-bin).

On Ubuntu 24.04 and Pop!_OS 24.04 the archive has no `python3-meshtastic`
(measured 2026-10-03), so the plan defers that member by name and installs the
rest (**D-039**).

---

## 3. First run: the shared instance and two laptops

By default the first Reticulum program to start owns the interfaces and every
other one attaches to it as a client. That is a trap if the first one is
NomadNet, because when you quit it the others lose the network. The profile
installs a systemd user service, `hammunition-rnsd`, so the owner is always
the same quiet daemon. It is enabled at install and starts at your next
login. To start it now:

```
systemctl --user start hammunition-rnsd
systemctl --user status hammunition-rnsd
```

To turn it off, and stop it starting at login, run `systemctl --user disable
--now hammunition-rnsd`; `hammunition uninstall mesh` does the same and removes
the unit file. (`hammunition services` lists it as `rns` when hammunition-tray's
helper is installed.)

Then ask it what it is doing:

```
rnstatus
```

You should see one block for the shared instance and one for each interface
that is up. If it prints "Could not get RNS status" instead, see [`rnstatus`
says "Could not get RNS status"](../troubleshooting/running.md#reticulum-no-instance).

On first start `rnsd` writes `~/.reticulum/config` with its defaults, which turn
on the **AutoInterface**: link-local IPv6 and UDP, with multicast to find
peers, so two machines on one Wi-Fi network or one Ethernet segment see each
other with no routers, no DHCP and no configuration. Upstream says the
interface uses UDP ports 29716 and 42671 and that a firewall may need to allow
them (the manual for 1.5.5). The engine writes none of this file and never
edits it: it is created by `rnsd`, under your account, and it is yours.
`rnsd --exampleconfig` prints the whole annotated reference.

Three facts about the shared instance, each read from the installed program:

- **It is a local socket, not a TCP port.** On Linux `rnsd` binds the abstract
  Unix sockets `@rns/default` and `@rns/default/rpc`, and no TCP port
  (`ss -xl`, measured 2026-10-03; upstream's example configuration names port
  37428 only for platforms without domain sockets). `rnstatus` names it
  `Shared Instance[rns/default]` on a default configuration.
- **It is not private to your account.** An abstract socket has no file
  permissions, so another account on the same machine can attach to it as a
  client. Treat the machine as a single-operator one.
- **`rnsd --service` logs to `~/.reticulum/logfile`**, not to the journal, so
  `journalctl --user -u hammunition-rnsd` shows very little. Read the file.

**Two laptops.** Install the profile on both, start the service on both, join
both to one network, and run `rnstatus` on either. The AutoInterface block
shows its peers: upstream's manual shows `Peers : 1 reachable`. If it stays at
none, see [Two laptops do not see each other](../troubleshooting/running.md#reticulum-autointerface):
a firewall, or a network that does not pass multicast between its devices
(upstream names very cheap ISP-supplied routers as the usual cause). Sections 4
and 8 then give you something to do with the link.

**If you already run a Reticulum program of your own** (Sideband, MeshChat or a
`rnsd` you started by hand), it already owns the instance. The service will
start, find the instance taken and attach to it as a client rather than fail:
its log says "Started rnsd version 1.5.6 connected to another shared local
instance, this is probably NOT what you want!" and `rnstatus` run against its
configuration says "Could not get RNS status" (both measured 2026-10-03).
Stop one of the two: [Another Reticulum program owns the shared
instance](../troubleshooting/running.md#reticulum-another-instance).

---

## 4. Messaging with NomadNet

```
nomadnet
```

(or *NomadNet* under *LoRa Mesh* in the desktop menu, which opens a terminal).
On first run it creates `~/.nomadnetwork/`: its configuration, a `storage`
directory holding your **identity**, your conversations, the pages and files
you publish, and an `examples` directory. Your NomadNet address, the LXMF
destination other people write to, is derived from that identity, and the
program displays it (the text interface was not run for this page: section
13). Give it to the person at the other laptop; they give you theirs; each of
you can then send the other a message, and the conversation stays on your
disk.

`nomadnet --daemon` runs it with no screen, serving your pages and accepting
messages with nobody at the keyboard. Do that on purpose, not by habit.

**Keep the identity.** If `~/.nomadnetwork` is lost, you have a new address
and everyone who knew the old one has to be told. Take a copy now, and again
whenever you change anything you care about:

```
( cd ~ && tar -czf mesh-identities-$(date +%F).tar.gz $(ls -d .reticulum .nomadnetwork .lxmd .rnsh 2>/dev/null) )
chmod 600 ~/mesh-identities-$(date +%F).tar.gz
```

That archive holds private keys: keep it on media you control, not in a shared
folder. It takes whichever of the four directories exist: `~/.lxmd` appears if
you run a propagation node (section 9) and `~/.rnsh` once you use `rnsh`
(section 8).

A single laptop is enough to see NomadNet start and write its files; messaging
needs a second. Which keys do what inside the program is its own help's job,
and this page does not describe the text interface, which was not run for it
(section 13).

---

## 5. Over the internet

Reticulum's own manual is plain about how to start. It says there is no "right"
way to build a network, and calls the reliance on "a few centralized,
hard-coded entrypoints" a common mistake: a long list of public addresses
pasted from a website makes the network brittle. What it recommends
instead is to use a temporary bootstrap connection to *discover* nearby
infrastructure, with the `discover_interfaces` and
`autoconnect_discovered_interfaces` options and an interface marked
`bootstrap_only`, and it points to two directory sites for interface
definitions, `directory.rns.recipes` and `rmap.world` (the manual for 1.5.5,
read 2026-10-03). `rnstatus -d` lists the interfaces your instance has
discovered and `rnstatus -D` prints a configuration entry for each.

This guide does not carry a list of public entry points, for the manual's
reason and for ours: an address that was up when this was written is not
evidence that it is now, and the connection to a public hub is not run from
this project's CI by policy. The manual's own example of connecting to a
remote listener is:

```
[[Backbone Remote]]
  type = BackboneInterface
  enabled = yes
  remote = amsterdam.connect.reticulum.network
  target_port = 4251
```

Read that as an example of the shape, not a promise about the host. For a
listener that is not a Reticulum Backbone, upstream's TCP client stanza is:

```
[[TCP Client Interface]]
  type = TCPClientInterface
  enabled = yes
  target_host = 127.0.0.1
  target_port = 4242
```

Add a stanza under `[interfaces]` in `~/.reticulum/config`, then restart the
service so the shared instance reads it:

```
systemctl --user restart hammunition-rnsd
rnstatus
```

**Your own hub.** The way to make your laptops reachable from afar is a
machine of your own that stays up: a small server with a public address, or an
always-on machine on your LAN, such as the one that holds your [LAN
mirror](lan-mirror.md). Upstream's server stanza is:

```
[[TCP Server Interface]]
  type = TCPServerInterface
  enabled = yes
  listen_ip = 0.0.0.0
  listen_port = 4242
```

That listens on **every address the machine has**. Say so to yourself before
you enable it, put it behind the firewall rules you intend, and read what the
manual says about TCP: TCP connections "reveal the IP address of both your
instance and the server to anyone who can inspect the connection", and someone
could use that to determine your location or identity. For something private,
upstream's gateway examples take a `network_name` and a `passphrase`. The I2P
interface hides the addresses at a cost in speed and needs an I2P daemon of your
own; the manual has the details.

---

## 6. Over LoRa with an RNode

An **RNode** is not one device. It is an open design and firmware that turns a
LoRa development board into a modem Reticulum can use. Upstream's manual lists
fifteen boards the auto-installer supports: LilyGO's T-Beam, T-Beam Supreme,
T3S3, LoRa32 v1.0, v2.0 and v2.1, T-Deck and T-Echo; RAK4631-based boards;
Heltec's T114 and LoRa32 v2.0, v3.0 and v4.0; the OpenCom XL; and unsigned.io's
RNode v2.x. It says RNodes use raw LoRa modulation and have nothing to do with
LoRaWAN. That list is upstream's as read on 2026-10-03, not a claim about which
boards work here. `docs/hardware/rnode.md` has the hardware entry.

**The legal note, before you transmit.** Radio spectrum is a regulated
resource and the rules differ by country; upstream's manual says so beside
every radio interface. Two things deserve stating plainly here, as
disclosure and not as a ruling:

- Reticulum encrypts every packet. In the United States, Part 97 forbids
  messages encoded to obscure their meaning on amateur frequencies. So an
  RNode on an amateur band is not something this guide can tell you is
  lawful: that is for you to establish, for your licence class, your band and
  your country.
- Upstream's manual says RNodes most commonly use LoRa in the common ISM bands
  (868 MHz in ITU Region 1 and 915 MHz in Region 2 are the usual
  allocations). Those have their own power and duty-cycle limits, which are
  yours to look up. The `RNodeInterface` has `airtime_limit_long` and
  `airtime_limit_short` for the duty cycle, and `id_callsign` and
  `id_interval` to send identification on the channel; whether any of that
  satisfies a rule is not for this guide to say either.

**Flash the board.** `rnodeconf` is installed with `rns`. Find the board's
port, look at it, and run the installer, which asks a series of questions
about your hardware and installs and provisions the firmware (the manual's
route):

```
ls /dev/serial/by-id/
rnodeconf --info /dev/ttyACM0
rnodeconf --autoinstall
```

If `rnodeconf` cannot open the port, you are not in `dialout` yet or the
session predates it: [rnodeconf cannot open the
port](../troubleshooting/running.md#rnodeconf-port). `rnodeconf` downloads
firmware itself from upstream unless you give it `--fw-url`, or a file you
extracted yourself with `--extract` and `--use-extracted`. What it checks
about the download, and from where it fetches, were not measured; read what it
prints before you let it flash, and note that the firmware is upstream's and
not something Hammunition installs (**D-026**).

**Add the interface.** Upstream's stanza, with the manual's example values
(867.2 MHz, a 125 kHz channel) that you must replace with ones you are
allowed to use:

```
[[RNode LoRa Interface]]
  type = RNodeInterface
  enabled = yes
  port = /dev/ttyACM0
  frequency = 867200000
  bandwidth = 125000
  txpower = 7
  spreadingfactor = 8
  codingrate = 5
  # id_callsign = N0CALL
  # id_interval = 600
```

Frequency is in hertz, bandwidth in hertz, `txpower` in dBm, the spreading
factor runs 7 to 12 (7 fastest, 12 longest range) and the coding rate 5 to 8
(upstream's comments). Two RNodes talk to each other only when frequency,
bandwidth, spreading factor and coding rate all match. Restart the service
(`systemctl --user restart hammunition-rnsd`) and read `rnstatus`. An RNode
that is plugged in but not configured does nothing, and one that is configured
transmits when Reticulum has something to send.

---

## 7. Over a packet TNC

Any packet modem that speaks KISS over USB, serial or TCP can carry
Reticulum; upstream's manual names Dire Wolf among them. The `packet` profile
installs Direwolf and, from your station values, writes the
`/etc/direwolf.conf` whose `KISSPORT 8001` is the port
[Packet and Winlink](packet-winlink.md) uses. A software modem on that port is
reached with the TCP client interface in KISS mode (upstream's stanza):

```
[[Direwolf KISS]]
  type = TCPClientInterface
  enabled = yes
  kiss_framing = True
  target_host = 127.0.0.1
  target_port = 8001
  fixed_mtu = 500
```

Upstream's warning goes with it: use `kiss_framing` only to reach a modem or
similar, never between two Reticulum instances. For a hardware TNC on a serial
port the plain `KISSInterface` takes `port`, `speed`, `preamble`, `txtail`,
`persistence` and `slottime`, and can send an identifying beacon with
`id_callsign` and `id_interval`. If you want Reticulum's frames wrapped in
AX.25 and your callsign on every transmission, there is an `AX25KISSInterface`
with `callsign` and `ssid` set (`callsign = N0CALL` in the examples), though
upstream says to use it only if you need to: it adds overhead to every packet
and the plain interface with beaconing is more efficient.

The legal note in section 6 applies word for word: this is the same encrypted
traffic on the same kind of channel. One packet station is also one radio:
Direwolf and your digital-mode programs share it, so plan which one is up.

---

## 8. A shell on the other laptop: rnsh

`rnsh` gives you a shell on another machine over Reticulum, with no SSH and no
IP address between you. It is part of `rns` (the separate PyPI project of the
same name is deliberately not installed: two packages would own one command).
It works by identity: the machine you want to reach runs a listener that
answers only to identities you name.

On **your own machine**, print its identity hash. The first `rnsh` run also
creates your `rnsh` identity in `~/.rnsh/identity`, and, if there is none yet,
starts Reticulum and writes `~/.reticulum/config`:

```
rnsh -p
```

It prints a line of the form `Identity     : <c89b4da064bf66d280f0e4d8abfd9806>`
(the hash shown is the manual's example, nobody's identity; yours differs).

On **the remote machine**, name that identity and listen, announcing at
startup. Substitute the hash `rnsh -p` printed for the made-up one below:

```
rnsh -l -a c89b4da064bf66d280f0e4d8abfd9806 -b 0
```

Allowed identities can also be listed one hash per line in
`~/.config/rnsh/allowed_identities` (or `~/.rnsh/allowed_identities`).
`rnsh -l -p` on the remote machine prints its identity and a line `Listening
on : <hash>`, the **destination** hash: the address you connect to. From your
machine:

```
rnsh a1b2c3d4e5f60718293a4b5c6d7e8f90
```

(again a made-up hash: use the one the listener printed). Be exact about what
you have done: **a listener runs commands as the account that started it, for
every identity you allowed.** `-n` allows anyone and is the wrong switch to try.
`-C` stops the listener running command lines sent by the other side, leaving
only the shell or the program you named after `--`. Treat an `rnsh` listener
like an SSH daemon.

`rncp` copies files the same way (`rncp --help`) and `rnx` runs a command on a
listener (`rnx --help`), under the same identity rules.

---

## 9. A propagation node: lxmd

Reticulum delivers messages while both ends are reachable. **LXMF** adds
store-and-forward: a *propagation node* holds a message for someone who is
off, and hands it over when they are next on the mesh. A mesh that has to move
messages between laptops that are not on at the same time wants at least one,
somewhere always on.

**What running one means.** `lxmd -p` makes your machine store encrypted
messages addressed to other people, on your disk, for as long as its limits
allow, and relay them to its peers. You do not read them, and you are carrying
them. Decide that on purpose, on a machine that is meant to stay on, and not
on the laptop that goes in the bag.

`lxmd` is installed by `lxmf` and **never started by Hammunition**. It keeps
its configuration, identity and message store in `~/.lxmd`, created on first
run (measured 2026-10-03). To read the annotated configuration and to see it
run in a terminal first:

```
lxmd --exampleconfig
lxmd -p -v
```

`lxmd --status` shows the node and `lxmd --peers` its peers. To keep one
running unattended, a user service of your own does it; this one is a sketch
and was not run:

```
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/lxmd.service <<'UNIT'
[Unit]
Description=LXMF propagation node

[Service]
ExecStart=%h/.local/share/hammunition/venvs/lxmf/bin/lxmd -p -s
Restart=on-failure

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now lxmd.service
```

The path assumes the default `XDG_DATA_HOME`. `hammunition uninstall lxmf`
does not know about a unit you wrote: disable it first with
`systemctl --user disable --now lxmd.service`.

---

## 10. EMCOMM notes

What works with nothing but two laptops and their batteries: the
AutoInterface between them, NomadNet messages and pages, `rncp` file transfer
and `rnsh`. There is no tower, no internet and no server to depend on, and
the first test of all of it is that two laptops do exactly that in a room.
Anything past the length of one Wi-Fi network needs a radio, a TNC or the
internet:

- **Distance without infrastructure** needs an RNode or a packet modem at each
  end (sections 6 and 7), and a decision about the legal note in section 6.
- **Reaching somebody elsewhere** needs the internet, or a chain of
  radio-linked machines to something that has it (section 5).
- **Messages between machines that are not on together** need a propagation
  node somewhere (section 9).

Habits worth having before the bad day:

- **Back up the identities** (section 4) and keep a copy off the laptop.
- **Keep it running with nobody logged in**, if the laptop is meant to answer
  unattended: `hammunition station set --unattended` has the power-control
  helper enable linger for your account, so your user services, this one among
  them, keep running; the plan lists what it keeps alive before the prompt, and
  `--no-unattended` turns it off (**D-073**). Not measured for this unit.
- **Write the address down.** Your NomadNet address, and those of the people
  you will need, belong on paper as well as in a program.
- **Practise with the same setup.** Once a month, two laptops, one
  `rnstatus` and one message each way; it takes five minutes and finds the
  problem while there is time.
- **Have these notes with you.** An offline, served copy of the Hammunition
  documentation is a separate unit that does not exist yet; until it does,
  print this page or save it from the site.

---

## 11. Meshtastic beside it

The profile also installs the two Meshtastic clients the catalog already
carried: `python3-meshtastic`, the command-line client and Python library, and
`gtk-meshtastic-client`, a desktop GUI. They talk to a Meshtastic node over
USB, which is a different network from Reticulum's and does not interoperate
with it. A Meshtastic node on your USB bus is `/dev/ttyACM0` or `/dev/ttyUSB0`
and needs the same `dialout` membership as an RNode.

The command-line client's `--help` (read from version 2.7.11; the version your
distribution packages may differ, and Debian 13 and Parrot carry 2.6.0) shows
`--info` to read the node's configuration, `--nodes` for the nodes it has
heard, `--sendtext` to send a message, and `--set FIELD VALUE` to change a
setting:

```
meshtastic --info
meshtastic --nodes
```

A node transmits only once its region is set: `meshtastic --set lora.region
US` is the form, with your region's code in place of `US` (the field name and
region codes are Meshtastic's, and its documentation is the authority; this
guide did not run it). The same `--help` lists `--set-ham`, "Set licensed Ham
ID and turn off encryption", which is Meshtastic's own switch for the
amateur-radio question section 6 raises.

The Linux Meshtastic node daemon, `meshtasticd`, is not here: no distribution
carries it, it comes from a third-party repository and it is the next unit of
this track. So are MeshCore's clients.

---

## 12. Removing it

```
hammunition uninstall mesh --dry-run
hammunition uninstall mesh
```

removes what the profile installed: the `hammunition-rnsd` service and its
unit file, the three virtualenvs and their wrappers, and the two Meshtastic
packages if Hammunition installed them. It **leaves your identities and
configuration where they are**, and this page says so (the uninstall output
does not list what it did not touch):

- `~/.reticulum`: your Reticulum configuration, identity and known
  destinations.
- `~/.nomadnetwork`: your NomadNet identity, conversations and pages.
- `~/.lxmd`: your propagation node's identity and message store, if you ran
  one.
- `~/.rnsh`: the identity `rnsh` made for you, if you used it.

Those were created by the programs, under your account, and are not
Hammunition's to remove: delete one and you have a new address. If you really
mean to start over, after taking the backup in section 4:

```
rm -rf ~/.reticulum ~/.nomadnetwork ~/.lxmd ~/.rnsh
```

A unit you wrote yourself in section 9 stays too; disable it first.

---

## 13. What is measured, and what is not

Measured on 2026-10-03 on a Parrot 7.4 machine, in a scratch virtualenv and with
a Reticulum configuration that had no interfaces, so nothing reached a
network:

- **The pins install.** `rns` 1.5.6, `lxmf` 1.2.0 and `nomadnet` 1.4.4, each
  with its hash-pinned closure, installed with `pip install --require-hashes`
  on Python 3.13.5, every hash matching, and every command this page names is
  in `bin/`.
- **The shared instance is a local socket.** `rnsd` bound the abstract Unix
  sockets `@rns/<name>` and `@rns/<name>/rpc` and no TCP port, and
  `rnstatus` read it as `Shared Instance[rns/<name>]`. `rnsd --service` wrote
  `~/.reticulum/logfile`.
- **A second `rnsd` does not fail.** It attached to the first, logged "connected
  to another shared local instance, this is probably NOT what you want!" and
  kept running; `rnstatus` against its own configuration said "Could not get
  RNS status".
- **`lxmd` and `nomadnet --daemon`** both attached to that instance and kept
  running (`rnstatus` then read `Serving : 2 programs`), and created `~/.lxmd`
  and `~/.nomadnetwork` with the contents sections 4 and 9 name.
- **`rnsh -p` and `rnsh -l -p`** printed an `Identity` line and, in listen
  mode, a `Listening on` line, and created `~/.rnsh/identity`; no connection
  was made.
- **The options this page quotes** are those of the installed programs'
  `--help`, and the interface stanzas are upstream's manual for 1.5.5, both
  read that day.

Not measured, and this page says so where it matters:

- **No LoRa link.** No RNode, and no Meshtastic node, has been run for this
  page. The maintainer's LoRa boards were lost in a flood; the `rnode` entry
  is recorded from upstream's board lists, as `meshtastic` was, and says
  `untested`.
- **The AutoInterface between two machines**, `rnstatus` showing a peer, and
  NomadNet, `rnsh` and `rncp` over it: not yet. Upstream's UDP ports 29716 and
  42671 are quoted from its manual, not read from a socket here.
- **The text interface of NomadNet.** It was started in daemon mode only; what
  it looks like and where its keys are is its own help's business.
- **Any internet link.** The TCP and Backbone examples are upstream's, and a
  connection to a public hub is not run from this project's CI by policy.
- **Another account attaching to your shared instance.** It follows from an
  abstract socket having no file permissions; it was not tried with a second
  user.
- **`rnodeconf`'s download.** Where it fetches firmware from and whether it
  verifies what it fetches.
- **The service under a real systemd user manager**, `lxmd` as a service, and
  propagation between two nodes.
- **arm64 and Python 3.14.** The hash sets cover every file PyPI lists, and the
  wheels exist on both architectures (the inventory's resolver run); neither
  was installed.
````

Section 13 is the pre-container version: it lists what was measured on 2026-10-03 on a Parrot machine in a scratch virtualenv and says everything else is not measured. Task 11 replaces it with what the Debian 13 container run measured.

- [ ] **Step 5: Add the four troubleshooting entries**

Each entry is symptom-first, as the file's other entries are, with the anchor the guide and the index link to.

Append this to the end of `docs/troubleshooting/running.md`, after one blank line:

````markdown
## <a name="reticulum-no-instance"></a>`rnstatus` says "Could not get RNS status"

```
Could not get RNS status
```

`rnstatus` found a Reticulum instance to attach to and could not read its
status. The cause measured on 2026-10-03 is the one in the next entry: a
second `rnsd` (or any program started with a different configuration
directory) attached as a *client* to an instance whose RPC key it does not
hold, so it can serve programs but cannot be asked how it is doing. Check which
one owns the instance, and whether the one you meant to run is running at all:

```
systemctl --user status hammunition-rnsd
tail -n 20 ~/.reticulum/logfile
ss -xlp | grep rns
```

The last command lists the abstract sockets named `@rns/…` and the process
holding each. If the service is simply not running yet (it starts at your next
login after install), start it with `systemctl --user start hammunition-rnsd`.

## <a name="reticulum-another-instance"></a>Another Reticulum program owns the shared instance

`~/.reticulum/logfile` says:

```
Started rnsd version 1.5.6 connected to another shared local instance, this is probably NOT what you want!
```

A Reticulum instance was already running, so `hammunition-rnsd` did not fail
and did not start a second set of interfaces: it attached to the first. The
usual owners are Sideband, MeshChat or an `rnsd` you started by hand, and
another account on the same machine counts: the shared instance is a Unix
socket in the machine-wide abstract namespace (`@rns/default`), not a file in
anybody's home. Nothing loops and nothing is broken, but the interfaces in your
`~/.reticulum/config` are not the ones in use; the other instance's are.

Stop one of the two. Or give one of them its own name: upstream's example
configuration (`rnsd --exampleconfig`) documents an `instance_name` option under
`[reticulum]` for running several different shared instances on one system
(that route was not tried here). Restart the service afterwards:
`systemctl --user restart hammunition-rnsd`.

## <a name="reticulum-autointerface"></a>Two laptops running Reticulum do not see each other

`rnstatus` on each shows the AutoInterface up and no peers. Go in this order:

1. **Both services running, both on one network?** `systemctl --user status
   hammunition-rnsd` on each, and the same Wi-Fi network or the same switch.
2. **Link-local IPv6 enabled?** AutoInterface uses it to find peers and it is on
   by default in current systems. `ip -6 addr show scope link` should list an
   `fe80::` address on the interface you are using.
3. **A firewall?** Upstream says the interface uses UDP ports 29716 and 42671
   and that a firewall may need to allow them (its manual for 1.5.5; not
   measured here).
4. **A network that does not pass traffic between its devices.** Upstream names
   very cheap ISP-supplied routers, and an access point set to isolate its
   clients does the same; some phone hotspots are reported to. Move to a
   switch or a cable between the two machines to rule it out.

If one of them cannot be made to work, a TCP link between the two
(`docs/guides/mesh-and-reticulum.md`, section 5) does not depend on multicast.

## <a name="rnodeconf-port"></a>`rnodeconf` cannot open the RNode's port

```
Permission denied: '/dev/ttyACM0'
```

(or `/dev/ttyUSB0`, whichever the board appeared as: `ls /dev/serial/by-id/`).
It is the same cause as any serial device: you are not in the `dialout` group
yet, or you are but the session predates it. [Permission denied on a serial
device](#dialout) has the fix: log out and back in. Two other things hold a
port: a device you parked with `hammunition hardware park` (`hammunition
hardware state` shows it, `hammunition hardware wake NAME` returns it), and
another program that has the port open, ModemManager among them on some
machines, as it does for other serial boards; [a CH340 serial
device that vanishes](#brltty) is a different cause with a similar look.
````

- [ ] **Step 6: List them in the troubleshooting index**

```bash
python3 - <<'PY'
import pathlib

new_lines = '''- **[`rnstatus` says "Could not get RNS status"](running.md#reticulum-no-instance)** —
  it could not read the shared instance it attached to; look at who owns the
  `@rns/` socket and at `~/.reticulum/logfile`.
- **[Another Reticulum program owns the shared instance](running.md#reticulum-another-instance)** —
  `hammunition-rnsd` attached to it instead of starting its own; stop one of
  the two.
- **[Two laptops running Reticulum do not see each other](running.md#reticulum-autointerface)** —
  no peers on the AutoInterface: the service, link-local IPv6, UDP 29716 and
  42671, or a network that isolates its devices.
- **[`rnodeconf` cannot open the RNode's port](running.md#rnodeconf-port)** —
  `dialout`, a parked device, or another program holding it.
'''
p = pathlib.Path("docs/troubleshooting/index.md")
s = p.read_text()
old = '- **["Address family not supported by protocol" from a packet program](running.md#ax25)** —'
assert old in s, "the troubleshooting index moved"
p.write_text(s.replace(old, new_lines + old, 1))
PY
```

- [ ] **Step 7: Put the guide in the nav and the guides index, and the service in the CLI reference**

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("mkdocs.yml")
s = p.read_text()
old = "          - APRS: guides/aprs.md\n"
assert old in s, "the guides nav moved"
p.write_text(s.replace(old, old + "          - Mesh and Reticulum: guides/mesh-and-reticulum.md\n", 1))

p = pathlib.Path("docs/guides/index.md")
s = p.read_text()
old = """- **[APRS](aprs.md)** — Direwolf as the TNC, Xastir or YAAC on the map, and
  the decisions about digipeating and gating that affect other people.
"""
new = old + """- **[Mesh and Reticulum](mesh-and-reticulum.md)** — encrypted messaging with no
  infrastructure: two laptops on one network, then a LoRa RNode, a packet
  modem or the internet, with NomadNet, `rnsh` and the Meshtastic clients beside
  it.
"""
assert old in s, "the guides index moved"
p.write_text(s.replace(old, new, 1))

p = pathlib.Path("docs/reference/cli.md")
s = p.read_text()
old = "any user service a catalog unit installed\n(`gps-tether`, `rig`)."
assert old in s, "the services section of cli.md moved"
p.write_text(s.replace(old, "any user service a catalog unit installed\n(`gps-tether`, `rig`, `rns`).", 1))
PY
```

- [ ] **Step 8: Run the tests to see them pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_docs.py -p no:cacheprovider
```

Expected: `12 passed`.

- [ ] **Step 9: Check the links and the site**

`git add -A` first: `tests/test_repo_hygiene.py` fails on an untracked source file.

Run:

```bash
git add -A && python3 scripts/check_doc_links.py && nice -n 19 .venv/bin/python -m pytest tests/test_site.py tests/test_docs_generated.py tests/test_repo_hygiene.py -p no:cacheprovider
```

Expected: `no broken internal references` (this is where a missing Task 0 shows: `docs/reference/mesh-inventory.md` would be reported), then all pass. The site test builds MkDocs with `--strict`.

- [ ] **Step 10: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict tests/test_reticulum_docs.py
```

Expected: clean.

- [ ] **Step 11: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Add the Mesh and Reticulum guide and four troubleshooting entries

Thirteen sections from what Reticulum is to what is measured and what is not,
with the Part 97 note as disclosure. Symptom-first entries for a missing
shared instance, a second instance, an AutoInterface with no peers and an
RNode port that will not open. Track C, issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 8: The `mesh` profile

**Files:**
- Create: `catalog/profiles/mesh.yaml`
- Create: `tests/test_mesh_profile.py`
- Modify: `mkdocs.yml` (one nav line), `README.md` (profile count)
- Modify (generated): `docs/profiles/mesh.md`, `docs/profiles/index.md`

**Interfaces:**
- Consumes: Tasks 3 to 5 (`rns`, `lxmf`, `nomadnet`) and the two Meshtastic units the catalog already carries (`python3-meshtastic`, `gtk-meshtastic-client`).
- Produces: profile `mesh`, `stage: post-1.0`, five members, no consent gate, the four required documentation fields plus the six newcomer fields #276 added (`who_for`, `hardware_assumed`, `footprint_short`, `excludes_short`, `goals`, `first_ten_minutes`).

- [ ] **Step 1: What the profile is**

Post-1.0 and in no default: the 1.0 set is the one accepted on 2026-08-29 and adding to it is a decision. It carries the two Meshtastic units by the maintainer's ruling; where an archive lacks one the plan defers it by name and the rest installs (D-039). Measured 2026-10-03: `python3-meshtastic` has no candidate on Ubuntu 24.04 and Pop!_OS 24.04, and Debian's testing/unstable 2.7.11-1 carries an autoremoval notice dated 2026-11-03 (trixie's 2.6.0-1, which Parrot and Debian 13 carry, is not on the list). The footprint is the inventory's measured venv sizes (20, 20 and 27 MB) and says the two apt packages were not measured. `docs/SCOPE.md` says a `mesh` profile ships when its units have run against a node on the bench; that is not yet true, so the profile says it is post-1.0 and that no LoRa link has been run through it.

- [ ] **Step 2: Write the failing test**

Create `tests/test_mesh_profile.py` with exactly this content:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `mesh` profile: Reticulum and the Meshtastic clients together.  D-080.

Post-1.0 and in no default; the maintainer's ruling of 2026-10-03 puts the two
Meshtastic units in it, and D-039 is what keeps that from refusing a target whose
archive lacks one (`python3-meshtastic` is absent on Ubuntu 24.04, measured
2026-10-03).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hammunition.manifest.load import load_catalog, load_profiles
from hammunition.manifest.schema import ProfileManifest

from test_plan import TARGET, _apt, _resolve  # isort: skip

ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(ROOT / "catalog" / "packages")
PROFILES = load_profiles(ROOT / "catalog" / "profiles", CATALOG)
MESH: ProfileManifest = PROFILES["mesh"]


def test_the_profile_is_post_1_0_ungated_and_carries_exactly_these_five() -> None:
    assert MESH.stage == "post-1.0"
    assert MESH.consent is None  # nothing transmits until the operator attaches a radio
    assert MESH.packages == [
        "rns",
        "lxmf",
        "nomadnet",
        "python3-meshtastic",
        "gtk-meshtastic-client",
    ]


def test_no_other_profile_pulls_it_in_and_no_default_does() -> None:
    for name, profile in PROFILES.items():
        if name != "mesh":
            assert not {"rns", "lxmf", "nomadnet"} & set(profile.packages), name


def test_the_profile_says_what_it_leaves_out_and_what_the_operator_does_next() -> None:
    doc = MESH.documentation
    for left_out in ("Sideband", "MeshChat", "meshtasticd", "MeshCore", "TAK"):
        assert left_out in doc.deliberately_excludes, left_out
    assert "Part 97" in doc.manual_configuration
    assert "systemctl --user start hammunition-rnsd" in doc.manual_configuration
    assert "20, 20 and 27 MB" in (doc.disk_footprint_hint or "")
    assert any("mesh-and-reticulum.md" in step for step in doc.first_ten_minutes)


def test_a_target_without_python3_meshtastic_defers_it_by_name_and_installs_the_rest(
    tmp_path: Path,
) -> None:
    """Ubuntu 24.04: no `python3-meshtastic` candidate. The profile still installs
    the Reticulum units; the plan names what it left out (D-039)."""
    known: dict[str, Any] = {"python3-venv": None, "gtk-meshtastic-client": None}
    plan = _resolve(
        tmp_path,
        ["mesh"],
        catalog=CATALOG,
        profiles={"mesh": MESH},
        known=known,
        target=TARGET,
        apt=_apt(tmp_path, known),
    )
    installed = {p.name for p in plan.packages}
    assert {"rns", "lxmf", "nomadnet"} <= installed
    deferred = {d.subject for d in plan.deferrals if d.kind == "package"}
    assert "python3-meshtastic" in deferred
    assert "python3-meshtastic" not in installed
    # The shared instance is still planned: it needs nothing from the missing member.
    assert [s.name for s in plan.user_services] == ["hammunition-rnsd"]
```

The last test is the maintainer's ruling made executable: with no `python3-meshtastic` candidate, `resolve(['mesh'], ...)` defers that member by name and still plans `rns`, `lxmf`, `nomadnet` and the `hammunition-rnsd` service.

- [ ] **Step 3: Run it to see it fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_mesh_profile.py -p no:cacheprovider
```

Expected: a collection error, `KeyError: 'mesh'` (the module reads the profile at import).

- [ ] **Step 4: Write the profile**

Create `catalog/profiles/mesh.yaml` with exactly this content:

```yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

name: mesh
summary: "Off-grid mesh messaging: Reticulum with NomadNet and LXMF, and the Meshtastic clients"
# post-1.0: the 1.0 profile set is the one accepted on 2026-08-29 and asserted by
# tests/test_schema.py, and adding to it is a decision, not a side effect of a
# new profile. Track C (issue #105, D-080). SCOPE.md says a `mesh` profile ships
# when its units have run against a node on the bench; this one is built and its
# pieces are tested, and no LoRa link has been run through it.
stage: post-1.0

# The two Meshtastic members are the maintainer's ruling of 2026-10-03. Where the
# archive lacks one the plan defers it by name and the rest installs (D-039):
# `python3-meshtastic` is absent on Ubuntu 24.04 and Pop!_OS 24.04 (measured
# 2026-10-03), and Debian's 2.7.11-1 carries an autoremoval notice dated
# 2026-11-03 for testing and unstable, not for trixie's 2.6.0-1.
packages:
  - rns
  - lxmf
  - nomadnet
  - python3-meshtastic
  - gtk-meshtastic-client

documentation:
  what_it_installs: >-
    Two mesh networks that do not talk to each other, and the programs for each.

    **Reticulum** is a general networking stack: addresses are keys, every packet
    is encrypted, and one network can run over a LoRa radio, a packet modem, a
    cable or an ordinary network with no router. `rns` is the stack, its command
    tools (`rnstatus`, `rnpath`, `rnprobe`, `rncp`, `rnx`, `rnsh`, `rnid`), the
    RNode flasher `rnodeconf`, and a systemd user service that keeps one shared
    instance running for your account. `lxmf` is the message layer and `lxmd`, a
    store-and-forward daemon you run only on purpose. `nomadnet` is the
    terminal messenger and page browser.

    **Meshtastic** is a ready-made text mesh on LoRa with phone apps: the
    command-line client (`python3-meshtastic`) and a GTK desktop client
    (`gtk-meshtastic-client`) from the distribution's archive.

    All of the Reticulum programs come from PyPI, hash-pinned, each in its own
    per-user virtualenv: no archive carries them. Reticulum's licence is its
    own (MIT plus two use restrictions) and is printed in the plan before you
    confirm.
  why_together: >-
    They are the two off-grid messaging networks a person with a LoRa board is
    most likely to meet, and they use the same boards, the same `dialout`
    group and the same serial tools, so one profile gets a laptop ready for
    either. They are a choice, not a bridge: a Meshtastic node and a Reticulum
    node do not exchange messages. Reticulum is the one with no central design
    and a wider reach (a laptop on one Wi-Fi, a TCP link, a LoRa RNode, a
    Direwolf modem, all one network); Meshtastic is the one with the ready
    hardware and the phone app.
  deliberately_excludes: >-
    **Sideband**, Reticulum's phone-style client: a 293 MB Kivy environment under
    a non-commercial Creative Commons licence, with a compiler build on arm64
    (mesh-inventory.md); its own decision. **Reticulum MeshChat**, which ships
    only as an AppImage (a post-1.0 backend). **`meshtasticd`**, the Linux
    Meshtastic node daemon, which no distribution archive carries and which
    comes from a third-party repository (the next unit of this track), and
    **MeshCore** and its clients. Any TAK server or client. **Any Reticulum
    configuration**: the engine writes none, and the file is yours.
  manual_configuration: >-
    **Reticulum.** Nothing is required for two machines on one local network:
    `rnsd` writes `~/.reticulum/config` on first start with the AutoInterface on.
    Start the service now with `systemctl --user start hammunition-rnsd` (it is
    enabled and begins at your next login). For the internet add a
    `TCPClientInterface`; for LoRa flash an RNode with `rnodeconf --autoinstall`
    and add an `RNodeInterface` with a frequency you are allowed to use. The
    guide has the stanzas. Reticulum encrypts every packet, which matters on
    amateur frequencies (Part 97 in the United States): the guide states it as a
    disclosure and does not rule on it. NomadNet creates your identity in
    `~/.nomadnetwork` on first run; keep it.

    **Meshtastic.** Set the radio region on the node before it will transmit, and
    expect the client and the node's firmware to want matching versions. Add
    yourself to `dialout` for either family and log out and back in.
  disk_footprint_hint: >-
    About 70 MB for the three Reticulum virtualenvs (20, 20 and 27 MB, measured
    2026-10-03 on Python 3.13.5; each carries its own copy of `rns`), plus the two
    Meshtastic packages and their dependencies from the archive, which were not
    measured here.
  who_for: "An operator who wants encrypted off-grid messaging for EMCOMM or experiment, over a local network now and over LoRa when a board arrives."
  hardware_assumed: "None for Reticulum on a local network. A LoRa board (an RNode for Reticulum, a Meshtastic node) for radio links. No LoRa link has been run through this profile."
  footprint_short: "about 70 MB of venvs, plus two apt packages"
  excludes_short: "Sideband, MeshChat, meshtasticd, MeshCore, TAK, any Reticulum configuration"
  goals:
    - "Message another laptop with no internet and no server"
    - "Run Reticulum over LoRa"
    - "Use Meshtastic from the desktop"
  first_ten_minutes:
    - "Read the plan first: `hammunition install mesh --dry-run`. It names the Reticulum licence beside the venv step, the user service it will write, and any Meshtastic package your archive lacks, which it defers rather than refuses."
    - "Install: `hammunition install mesh`. The Reticulum programs are fetched from PyPI against pinned hashes, so it needs the network and takes a minute or two."
    - "Start the shared instance now: `systemctl --user start hammunition-rnsd`, then `rnstatus`. It should show a shared instance and the AutoInterface."
    - "Put `~/.local/bin` on your PATH if the shell says `rnstatus: command not found` (a new shell usually does it), then run `nomadnet` and write down the address it shows."
    - "On a second machine on the same network, install the profile too and message the first one. [Mesh and Reticulum](../guides/mesh-and-reticulum.md) walks through it, then the internet and LoRa."
    - "For radio, read the legal note in the guide's section 6 before you transmit, add yourself to `dialout`, and flash an RNode with `rnodeconf --autoinstall`."
```

- [ ] **Step 5: Run the test to see it pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_mesh_profile.py -p no:cacheprovider
```

Expected: `4 passed`.

- [ ] **Step 6: Put the profile page in the nav**

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("mkdocs.yml")
s = p.read_text()
old = "      - navigation: profiles/navigation.md\n"
assert old in s, "the profiles nav moved"
p.write_text(s.replace(old, "      - mesh: profiles/mesh.md\n" + old, 1))
PY
```

- [ ] **Step 7: Bring the README's profile counts to the catalog's**

```bash
python3 - <<'PY'
import pathlib, re, sys
sys.path.insert(0, "src")
from hammunition.manifest.load import load_catalog, load_profiles

profiles = load_profiles(pathlib.Path("catalog/profiles"), load_catalog(pathlib.Path("catalog/packages")))
one = sum(1 for p in profiles.values() if p.stage == "1.0")
post = sum(1 for p in profiles.values() if p.stage == "post-1.0")
p = pathlib.Path("README.md")
s = p.read_text()
new, hits = re.subn(
    r"(\| Profiles \| ✅ \*\*all )\d+( of the 1.0 set\*\*, plus )\d+( post-1.0)",
    rf"\g<1>{one}\g<2>{post}\g<3>",
    s,
    count=1,
)
assert hits == 1, "the README's profile row moved"
p.write_text(new)
print("README says", one, "1.0 profiles and", post, "post-1.0")
PY
```

- [ ] **Step 8: Regenerate the profile pages**

Run:

```bash
git add -A
.venv/bin/python scripts/gen_profile_reference.py
git add -A
git status --short
```

Expected: `wrote 21 files to docs/profiles` (or the catalog's count); `docs/profiles/mesh.md` is new and `docs/profiles/index.md` changes.

- [ ] **Step 9: Run the profile, generated-page and site tests**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_mesh_profile.py tests/test_profile_docs.py tests/test_profile_deferral.py tests/test_docs_generated.py tests/test_site.py tests/test_schema.py tests/test_repo_hygiene.py -p no:cacheprovider && python3 scripts/check_doc_links.py
```

Expected: all pass, then `no broken internal references`. (`tests/test_profile_docs.py` is the one that fails, naming the profile and the field, if a newcomer field is missing.)

- [ ] **Step 10: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict tests/test_mesh_profile.py
```

Expected: clean.

- [ ] **Step 11: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Add the mesh profile: Reticulum and the Meshtastic clients

Post-1.0, ungated, five members. A member the target's archive lacks is
deferred by name, so the Reticulum units install everywhere. Track C, issue
#105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 9: The records: D-080, the project-instructions row, the scope status line, the licence evidence

**Files:**
- Modify: `docs/DECISIONS.md` (append D-080)
- Modify: `CLAUDE.md` (one decision-table row)
- Modify: `docs/SCOPE.md` (one status paragraph under Track C)
- Modify: `docs/reference/licence-verification.md` (one section, one introductory sentence)
- Modify: `tests/test_reticulum_docs.py` (one test)

**Interfaces:**
- Consumes: everything built so far; the decision text names the files and tests of Tasks 1 to 8.
- Produces: the decision D-080, the table row, the Track C status line and the licence record that `docs/reference/licence-verification.md` keeps for each carried licence.

- [ ] **Step 1: Confirm the decision number is free**

Run:

```bash
git grep -n '^## D-079\|^## D-080\|^## D-081' origin/main -- docs/DECISIONS.md; git grep -n '^## D-079' origin/copilot/fix-issue-96 -- docs/DECISIONS.md | cut -c1-120
```

Expected: nothing from `origin/main` (the last decision on `main` is D-078 as of this plan); D-079 appears only on `origin/copilot/fix-issue-96`, an open branch, which is why the spec says D-080. **If `origin/main` already has D-080, renumber this task's text to the next free number** (D-080 appears in the manifests, the guide, the tests and the changelog fragment too: `git grep -n 'D-080'`).

- [ ] **Step 2: Write the failing test**

Append this to the end of `tests/test_reticulum_docs.py`, after 2 blank lines:

```python
def test_the_records_carry_the_decision_the_row_and_the_status_line() -> None:
    """D-080 is one decision, in the record, the table the project instructions
    carry and the scope page's Track C, with the licence evidence beside the others."""
    decisions = _text(ROOT / "docs" / "DECISIONS.md")
    assert decisions.count("## D-080 ") == 1
    assert "## D-080 — Reticulum is carried as per-user venvs with one shared instance" in decisions
    assert "(**D-080**)" in _text(ROOT / "CLAUDE.md")
    assert "| Reticulum |" in _text(ROOT / "CLAUDE.md")
    assert "**Status, 2026-10-03 (D-080):**" in _text(ROOT / "docs" / "SCOPE.md")
    licences = _text(ROOT / "docs" / "reference" / "licence-verification.md")
    assert "## Reticulum, LXMF and NomadNet — the Reticulum License" in licences
    for unit in ("`rns` 1.5.6", "`lxmf` 1.2.0", "`nomadnet` 1.4.4"):
        assert unit in licences, unit
```

- [ ] **Step 3: Run it to see it fail**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_docs.py -p no:cacheprovider
```

Expected: `1 failed, 12 passed`: the new test fails on `decisions.count("## D-080 ") == 1`.

- [ ] **Step 4: Record the decision**

Appended after D-078 (D-079 is held by an unmerged branch, so D-080 is the next number on `main`). The shape is D-078's: date and status, what it depends on, the rule, what the engine and the measurements corrected, what was rejected, what is not measured, the consequences.

Append this to the end of `docs/DECISIONS.md`, after 2 blank lines:

```markdown
## D-080 — Reticulum is carried as per-user venvs with one shared instance per operator; the Reticulum License is stated, not gated; the engine writes no Reticulum configuration

**Date:** 2026-10-03. **Status:** accepted (the maintainer's rulings of
2026-10-03 on the design and on its four open points, recorded in
`docs/superpowers/specs/2026-10-03-reticulum-core-design.md`); the
implementation is proposed until merged (branch `reticulum-core`, Track C PR 2,
issue #105). **Depends on:** D-033 (a licence judged on what we do with it),
D-021 (disclose, never adjudicate), D-026 (the means of talking to a device),
D-039 (a member the target lacks is deferred by name), D-073 (user services),
D-078 (the operator's own data stays theirs), D-010 (one update block per
upstream), D-027 and D-018 (a hardware claim is earned).

**The shape.** Three catalog units, `rns`, `lxmf` and `nomadnet`, each a
hash-pinned `venv` from PyPI, because no archive on any of the seven targets
carries any of it (`docs/reference/mesh-inventory.md`, 2026-10-03). `rns`
exposes `rnsd`, `rnstatus`, `rnpath`, `rnprobe`, `rnid`, `rncp`, `rnx`, `rnsh`
and `rnodeconf`; there is **no `rnsh` unit**, because `rns` 1.5.x installs its
own and PyPI's separate `rnsh` would be a second owner of one command name.
`lxmf` exposes `lxmd` and starts nothing: a propagation node stores other
people's messages, and running one is the operator's decision. `nomadnet`
exposes `nomadnet` and ships a terminal launcher named `nomadnet-terminal`
(one name for both would have one overwrite the other in `~/.local/bin`). The
three venvs each carry their own `rns`, so they are pinned to one version and
bumped as a set; `tests/test_reticulum_catalog.py` fails if they are not.

**One shared instance per operator.** `rns` carries a `user_services` block,
`hammunition-rnsd` (`{venv}/bin/rnsd --service`), a plain service in D-073's
sense: no station value, nothing to defer. It is **enabled at install** and,
as every plain service does, starts at the operator's next login (the guide
prints `systemctl --user start hammunition-rnsd` for now). Its purpose is that
the first Reticulum program to start owns the interfaces and the rest attach, so
a service that is always first means NomadNet quitting does not take the
network with it. **It is not a TCP port.** Measured 2026-10-03 (Parrot 7.4, rns
1.5.6, `ss -xl`): `rnsd` binds the abstract Unix sockets `@rns/<instance>` and
`@rns/<instance>/rpc` and no TCP port; upstream's example configuration names
37428 only for platforms without domain sockets. So the unit declares no
`listens`: a declaration would print a loopback TCP listener the plan does not
have. An abstract socket has no file permissions and is machine-wide, so it is
not private to one account; the page and the guide say so, and which of an
operator's interfaces another account could use through it was not measured. A
second `rnsd` that finds the instance taken does not exit: it attaches, logs
"connected to another shared local instance, this is probably NOT what you
want!" and keeps running (measured), so there is no exit status to refuse a
restart on and none is set.

**The licence is stated on the plan line and not gated.** `rns` and `lxmf` are
under the Reticulum License, MIT plus two use restrictions (harm to human
beings; AI and machine-learning training data), not OSI-approved. Carried under
D-033's shape, as LinBPQ is: fetched from PyPI at the operator's direction,
never mirrored or vendored, the terms printed before the confirmation and quoted
on the package page, no judgement of the operator's use. A venv block gains
`licence` and `licence_url` (set together, https) and the plan line that
installs the venv carries them. There is **no consent gate**: nothing here
transmits until the operator attaches and configures a radio, and `rnodeconf`,
the RNode flasher, is the means of talking to a device (D-026); the firmware it
fetches is upstream's, what `rnodeconf` verifies was not measured, and the page
says so. `nomadnet`'s wheel classifier says MIT while the licence text it ships
(identical to its repository's, 35,149 bytes) is the GNU GPL v3; **the shipped
text governs** (the maintainer's ruling), so the unit says `GPL-3.0-only` and
its page notes the disagreement. `docs/reference/licence-verification.md` has
the file read and the date for each.

**The engine writes no Reticulum configuration, and uninstall removes none.**
`~/.reticulum/config` is created by `rnsd` on first start with its defaults
(the AutoInterface, which finds peers on a local network by IPv6 multicast and
UDP) under the operator's account. Hammunition never edits it. `hammunition
uninstall` removes the service, the venvs and the wrappers and **leaves
`~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd` and `~/.rnsh`**, which hold the
operator's identities and conversations; the guide says so and shows a backup.

**The `mesh` profile** is post-1.0 and carries `rns`, `lxmf`, `nomadnet`,
`python3-meshtastic` and `gtk-meshtastic-client` (the maintainer's ruling: the
Meshtastic units belong here, and D-039 defers by name where the archive lacks
one, as it does for `python3-meshtastic` on Ubuntu 24.04 and Pop!_OS 24.04).
`docs/SCOPE.md` says a `mesh` profile ships when its units have run against a
node on the bench; that is not yet true, and the profile says it is post-1.0 and
that no LoRa link has been run through it.

**The `rnode` hardware entry** records upstream's board lists, not an
identifier: Reticulum's manual lists fifteen supported boards and
`RNode_Firmware`'s `Boards.h` defines 21 board identifiers, and neither names a
USB vendor or product id. It inherits the `badgelife` class (`dialout`), carries
no identifier and no symlink (D-028), and is `untested`, not `supported`:
`supported` is earned by an identifier of the entry's own (D-018, D-027), and
there is none to confirm.

**Where the design's assumptions met the engine and the measurement.** The
design assumed `{venv}` was substituted in a user service's exec (it was not;
`UserService` accepts `{venv}/...` now and `plan_user_services` fills it from
the operator's own venv, under `sudo` as well); that a venv unit could name its
licence (it could not; the plan printed nothing, and `note` is read by no
plan line); that the shared instance listens on TCP 127.0.0.1:37428 (it does
not); that the `rnode` entry could be `supported` (the catalog's own test and
D-018 refuse it); and that Reticulum's manual lists public entry points (it
recommends against a pasted list and points to `directory.rns.recipes` and
`rmap.world`, so the guide carries the manual's own example and no list).

**Rejected.** A consent gate (nothing transmits at install). A Reticulum
configuration written from station values: the file is the operator's, and the
engine cannot know their interfaces. One unit holding all three programs: each
upstream has its own update block (D-010). A separate `rnsh` unit. A `listens:`
entry for a port that is not bound. Starting the service during install: D-073
starts a plain service at login, and changing that is its own decision. Sideband
(a 293 MB Kivy environment under a non-commercial Creative Commons licence, an
arm64 build from source) and Reticulum MeshChat (an AppImage) are their own
decisions.

**Not measured.** Any LoRa link: no RNode has been run, and the maintainer's
LoRa boards were lost in a flood. A public hub (not run from CI by policy). The
service under a real systemd user manager. What is measured and what is not is
the last section of `docs/guides/mesh-and-reticulum.md`.

**Consequences.** `catalog/packages/{rns,lxmf,nomadnet}.yaml`,
`catalog/hardware/devices/rnode.yaml`, `catalog/profiles/mesh.yaml`;
`UserService`'s `{venv}` and `VenvInstall.licence` in
`src/hammunition/manifest/schema.py`, `service_venv_dir` and the `venv_dir`
argument in `src/hammunition/userservice.py`, the call in
`src/hammunition/plan.py`, the licence clause in
`src/hammunition/backends/venv.py`; `docs/guides/mesh-and-reticulum.md`,
`docs/hardware/rnode.md` (generated), four entries in
`docs/troubleshooting/running.md`. Tests: `tests/test_reticulum_catalog.py`,
`tests/test_user_services_venv.py`, `tests/test_venv_licence.py`,
`tests/test_rnode_catalog.py`, `tests/test_mesh_profile.py`,
`tests/test_reticulum_docs.py`.
```

- [ ] **Step 5: Add the project-instructions row**

`CLAUDE.md`'s decision table is where an agent looking at this repository reads that a thing was decided; the row is placed after the last decision's.

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("CLAUDE.md")
s = p.read_text()
i = s.index("| Bring-your-own data |")
j = s.index("\n", i)
row = """| Reticulum | Three hash-pinned per-user venvs, `rns`, `lxmf` and `nomadnet` (no archive carries any of it), bumped as a set; `rns` exposes the tools including `rnsh` and the RNode flasher `rnodeconf`, and carries one plain user service, `hammunition-rnsd`, enabled at install and started at next login, that keeps one shared instance per operator; the shared instance is an abstract Unix socket, not a TCP port, so the unit declares no `listens`; the Reticulum License (MIT plus two use restrictions, not OSI) is printed on the venv's plan line and never gated, NomadNet is `GPL-3.0-only` by its shipped text; the engine writes no Reticulum configuration and uninstall leaves `~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd` and `~/.rnsh`; a post-1.0 `mesh` profile carries the three and the two Meshtastic clients; the `rnode` entry records upstream's board lists, claims no identifier and is `untested` | `{venv}` was not substituted in a user service and a venv could not state its licence; the design's TCP 127.0.0.1:37428 was measured not to exist; no LoRa link has been run (**D-080**) |"""
p.write_text(s[:j] + "\n" + row + s[j:])
PY
```

- [ ] **Step 6: Add the Track C status line**

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("docs/SCOPE.md")
s = p.read_text()
old = """or through a pinned repository, which is why the track can be cheap; what it
must not do is arrive as a list of names. A `mesh` profile ships when its
units have run against a node on the bench, and the tracking issue is #105."""
assert old in s, "SCOPE.md's Track C paragraph moved"
new = old + """

**Status, 2026-10-03 (D-080):** the Reticulum core is built: `rns`, `lxmf` and
`nomadnet` as hash-pinned venvs, the `rnode` hardware entry, a post-1.0 `mesh`
profile that also carries the two Meshtastic clients, and
`docs/guides/mesh-and-reticulum.md`. The condition above is not yet met: no
RNode or Meshtastic node has been run, so the profile says it is post-1.0 and
the guide says what is measured. Still to come: `meshtasticd`, MeshCore's
clients, Sideband and MeshChat (each its own decision)."""
p.write_text(s.replace(old, new, 1))
PY
```

- [ ] **Step 7: Add the licence evidence**

One row per unit with the file read and the date, as the LinBPQ section does: what the wheel's metadata says, what each repository's `LICENSE` says (sizes, and for NomadNet the sha256 prefix of both copies), what was carried, and what this does not establish.

Append this to the end of `docs/reference/licence-verification.md`, after one blank line:

```markdown
---

## Reticulum, LXMF and NomadNet — the Reticulum License, and GPL-3.0 by shipped text, verified 2026-10-03

**Evidence for D-080 and D-033's shape.** `rns`, `lxmf` and `nomadnet` are
installed from PyPI into per-user virtualenvs and never mirrored or vendored.
This is what the packages and their repositories say, read on 2026-10-03; it
records the text and rules on nothing. **Re-verify before any public release.**

| Unit | What was read | What it says | Carried as |
|---|---|---|---|
| `rns` 1.5.6 | The wheel's `METADATA` (`License: Reticulum License`; no licence file in `.dist-info`); `markqvist/Reticulum`'s `LICENSE` (`gh api repos/markqvist/Reticulum/contents/LICENSE`, 1,510 bytes, default branch `master`; GitHub's licence API reports `NOASSERTION`) | MIT plus two added conditions, quoted below | `licence: Reticulum License (MIT plus two use restrictions; not OSI-approved)`, printed on the plan line |
| `lxmf` 1.2.0 | The wheel's `METADATA` (`License: Reticulum License`; no licence file); `markqvist/LXMF`'s `LICENSE` (1,510 bytes; `NOASSERTION`) | The same text as Reticulum's; the two files differ only in the copyright years | the same |
| `nomadnet` 1.4.4 | The wheel's `METADATA` (classifier `License :: OSI Approved :: MIT License`, `License-File: LICENSE`); the wheel's `licenses/LICENSE` (35,149 bytes, "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007"); `markqvist/NomadNet`'s `LICENSE` (the same 35,149 bytes, and the same first 16 hex digits of its sha256, `3972dc9744f6499f`; GitHub reports `GPL-3.0`) | The two statements disagree: the classifier says MIT, the shipped text is the GNU GPL v3 | `licence: GPL-3.0-only (by the licence text the wheel ships; the wheel's classifier says MIT)` (the maintainer's ruling, 2026-10-03: the shipped text governs) |

The two added conditions, from `markqvist/Reticulum`'s `LICENSE`:

> The Software shall not be used in any kind of system which includes amongst
> its functions the ability to purposefully do harm to human beings.
>
> The Software shall not be used, directly or indirectly, in the creation of an
> artificial intelligence, machine learning or language model training dataset,
> including but not limited to any use that contributes to the training or
> development of such a model or algorithm.

**What this establishes, and what it does not.** The Reticulum License is not an
OSI-approved licence and not an SPDX identifier, and it limits fields of use
rather than granting nothing, which is D-033's situation with a different
shape: the catalog is data, the bytes reach the operator's machine from PyPI by
the act the operator would perform by hand, and Hammunition names the terms
where the operator will read them (the plan line before the confirmation, the
package page, the guide) and does not judge anyone's use of them (D-021). It
does not establish that those clauses are enforceable, how they apply to any
particular use, or that Sideband (CC BY-NC-SA 4.0) and LXST (CC BY-NC-ND 4.0),
which are not carried, are acceptable to carry later: those licences are
recorded in `docs/reference/mesh-inventory.md` and are their own decision. No
upstream was asked.
```

- [ ] **Step 8: Say in the record's introduction that it now serves D-080**

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("docs/reference/licence-verification.md")
s = p.read_text()
old = """makes a public claim about 73Linux's licence; this is what that claim rests on."""
assert old in s, "the licence record's introduction moved"
new = old + """
The last section is the evidence for **D-080**: the licences of Reticulum,
LXMF and NomadNet."""
p.write_text(s.replace(old, new, 1))
PY
```

- [ ] **Step 9: Run the test to see it pass**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_docs.py -p no:cacheprovider
```

Expected: `13 passed`.

- [ ] **Step 10: Check the links and the documents**

Run:

```bash
python3 scripts/check_doc_links.py && nice -n 19 .venv/bin/python -m pytest tests/test_docs_generated.py tests/test_site.py tests/test_repo_hygiene.py tests/test_docs_json_interface.py -p no:cacheprovider
```

Expected: `no broken internal references` (the decision names `tests/test_mesh_profile.py`, `tests/test_reticulum_docs.py` and the others as backticked paths, and each exists), then all pass.

- [ ] **Step 11: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict tests/test_reticulum_docs.py
```

Expected: clean.

- [ ] **Step 12: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Record the Reticulum decision, its licence evidence and the Track C status

D-080 in the decision record, its row in CLAUDE.md, the status line under
Track C in SCOPE.md and the three licences read for the units, with the files
and dates. Issue #105.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 10: Regenerate everything and prove regenerating is a no-op

**Files:**
- Modify (only if a generator changes something): generated pages under `docs/`

**Interfaces:**
- Consumes: Tasks 2 to 9.
- Produces: a tree where every generator's `--check` passes and a re-run changes nothing.

- [ ] **Step 1: Why a separate task**

Each earlier task regenerated what its own change touched. This one asks the whole question once, from the top: does any generated page differ from what its generator writes now? CLAUDE.md: a generated page is never hand-edited, and `tests/test_docs_generated.py` is the guard. It also catches a page that two tasks touched in an order that left an older rendering.

- [ ] **Step 2: Run every generator's check**

Run:

```bash
for g in gen_package_reference gen_projects_page gen_profile_reference gen_hardware_reference gen_hardware_gaps gen_device_naming gen_parity_coverage gen_capability_matrix gen_schema_reference gen_json_reference gen_not_carried; do
  if .venv/bin/python scripts/$g.py --check >/dev/null 2>&1; then echo "current  $g"; else echo "STALE    $g"; fi
done
```

Expected: eleven `current` lines and no `STALE`. A `STALE` line names the generator to run (without `--check`) and the Task whose change it reflects.

- [ ] **Step 3: Run the generated-docs tests and the link checker**

Run:

```bash
nice -n 19 .venv/bin/python -m pytest tests/test_docs_generated.py -p no:cacheprovider && python3 scripts/check_doc_links.py
```

Expected: all pass, then `no broken internal references`.

- [ ] **Step 4: Check nothing is left to commit**

The capability matrix and the hardware-gaps page carry a `Generated:` date line, which the tests ignore.

Run:

```bash
git status --short
```

Expected: nothing. If a generator wrote something (a changed `Generated:` date is the usual reason), run `git add -A` and commit it as `Regenerate the generated pages`; the commit message may not claim a path it does not stage.

### Task 11: Measure it in a Debian 13 container, then write down what was measured

**Files:**
- Create (outside the repository, under `~/.cache/hm-reticulum-measure/`): `measure_single.sh`, `node_setup.sh`, `pair.sh`, `check_single.sh`, `check_pair.sh`
- Modify: `docs/guides/mesh-and-reticulum.md` (section 13 rewritten; sections 3's ports, peers and sample), `catalog/packages/rns.yaml` and `catalog/packages/nomadnet.yaml` (`known_problems`), `docs/troubleshooting/running.md` (one item), `docs/DECISIONS.md` (D-080's last paragraph), `tests/test_reticulum_docs.py` (one test)
- Modify (generated): `docs/packages/rns.md`, `docs/packages/nomadnet.md`

**Interfaces:**
- Consumes: Tasks 1 to 10 as committed; the repository's own `containers/Dockerfile.target` (the engine installed into `/opt/hammunition-venv`, the whole checkout copied in).
- Produces: two measurement logs and, from them, the guide's last section and the unit pages' known problems stated as measured fact. Nothing in this task changes engine behaviour.

- [ ] **Step 1: What is measured and how**

The spec requires a Debian 13 container run before the guide states anything as fact. The harness is the repository's own target image, built with rootless Podman: an ordinary account `op` runs `hammunition install rns lxmf nomadnet --yes` **unprivileged** (nothing in the plan needs root: `python3-venv` is already in the image, so there is no apt work), then runs what the unit would run. **A container has no systemd user manager**, so `systemctl` is replaced by a stub that records its arguments: the run shows what the engine *asks* systemd to do, and the unit's `ExecStart` line is run by hand. That is the honest limit, and the guide's last section says it. Two further limits: the rootless harness has no terminal, so an `rnsh` client's own screen is not observed (the listener's log is); and the first run's network is Podman's pass-through of the host's interfaces, so its AutoInterface really does multicast on the host's network for about a minute, while the second run's two containers share a private bridge.

The author of this plan ran exactly these scripts on 2026-10-03 against the state Tasks 1 to 10 produce, and every check below passed. **This task repeats the run; it does not take that on trust.** The decision the spec made conditional is settled by it: a second `rnsd` finds the instance taken and *attaches* (it exits only when killed, `exit=124` under `timeout`), so there is no exit status that should not restart, and `restart_prevent_exit_status` stays unset (`test_the_shared_instance_is_one_plain_user_service` pins that).

- [ ] **Step 2: Build the Debian 13 target image from this worktree**

Run:

```bash
nice -n 19 podman build -f containers/Dockerfile.target --build-arg BASE=debian:13 --build-arg IDENTITY_PACKAGE= -t hammunition-debian-13:reticulum .
```

Expected: ends with `Successfully tagged localhost/hammunition-debian-13:reticulum`. On an account with no `/etc/subuid` ranges, add the two flags `scripts/run-targets.sh` adds under `HAMMUNITION_DEGRADED_PODMAN=1` (`--build-arg APT_SANDBOX_USER=root --storage-opt ignore_chown_errors=true` to the build, `--storage-opt ignore_chown_errors=true` to each `podman run`), and say so in the section 13 text: it weakens isolation. Never join the `docker` group instead (Q-001).

- [ ] **Step 3: Write the single-container measurement**

Runs inside one container as root: makes `op` and `op2`, stubs `systemctl`, installs unprivileged, runs the unit's `ExecStart`, then probes another account, a second `rnsd`, the daemons, `rnsh`, and uninstall.

Run:

```bash
mkdir -p "$HOME/.cache/hm-reticulum-measure"
cat > "$HOME/.cache/hm-reticulum-measure/measure_single.sh" <<'EOS'
#!/bin/bash
# Runs INSIDE a debian:13 target container as root. Measurement only: nothing
# here is part of the engine. `systemctl` is a stub that records its argv, since
# a container has no systemd user manager.
set -u
H=/opt/hammunition-venv/bin/hammunition

useradd -m -s /bin/bash op
useradd -m -s /bin/bash op2
chmod 755 /home/op
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq --no-install-recommends iproute2 procps >/dev/null 2>&1
printf '#!/bin/sh\necho "systemctl $*" >> /tmp/systemctl.log\nexit 0\n' > /usr/local/bin/systemctl
chmod 0755 /usr/local/bin/systemctl
: > /tmp/systemctl.log; chmod 666 /tmp/systemctl.log

as_op() { runuser -u op -- env HOME=/home/op PATH="/home/op/.local/bin:$PATH" PYTHONUNBUFFERED=1 "$@"; }
as_op2() { runuser -u op2 -- env HOME=/home/op2 PATH="/home/op/.local/bin:$PATH" PYTHONUNBUFFERED=1 "$@"; }

echo "=== 1. dry run (the plan lines)"
as_op $H install rns lxmf nomadnet --dry-run > /tmp/plan.txt 2>&1; echo "dry-run exit=$?"
grep -n "licence:" /tmp/plan.txt | cut -c1-260
grep -n -A8 "User services" /tmp/plan.txt | cut -c1-200

echo "=== 2. install, unprivileged"
as_op $H install rns lxmf nomadnet --yes > /tmp/install.txt 2>&1; echo "install exit=$?"; tail -5 /tmp/install.txt
echo "--- wrappers"; ls /home/op/.local/bin
echo "--- venvs"; ls /home/op/.local/share/hammunition/venvs
echo "--- unit file"; cat /home/op/.config/systemd/user/hammunition-rnsd.service
echo "--- systemctl stub log"; cat /tmp/systemctl.log
echo "--- ~/.reticulum after install (the engine writes none)"; ls -d /home/op/.reticulum 2>&1

echo "=== 3. run what the unit runs"
EXEC=$(sed -n 's/^ExecStart=//p' /home/op/.config/systemd/user/hammunition-rnsd.service)
echo "ExecStart: $EXEC"
as_op bash -c "nohup $EXEC > /tmp/rnsd.out 2>&1 &"
sleep 8
echo "--- rnstatus"; as_op rnstatus 2>&1 | head -30
echo "--- unix sockets"; ss -xlp 2>/dev/null | grep -i "@rns" | cut -c1-140
echo "--- tcp listeners"; ss -ltnp 2>/dev/null | tail -n +2 | cut -c1-140
echo "--- udp listeners"; ss -lunp 2>/dev/null | tail -n +2 | cut -c1-140
echo "--- ~/.reticulum"; ls -a /home/op/.reticulum
echo "--- logfile"; tail -8 /home/op/.reticulum/logfile
echo "--- default config interfaces"; sed -n '/^\[interfaces\]/,$p' /home/op/.reticulum/config | grep -v "^ *#" | grep -v "^$" | head -12

echo "=== 4. another account"
as_op2 /home/op/.local/bin/rnstatus 2>&1 | head -6; echo "op2 rnstatus exit=${PIPESTATUS[0]}"
ls -d /home/op2/.reticulum 2>&1
as_op2 timeout 12 /home/op/.local/bin/rnsd --service; echo "op2 rnsd exit=$?"
grep -c "connected to another shared local instance" /home/op2/.reticulum/logfile

echo "=== 5. a second rnsd for the same account"
(as_op timeout 12 /home/op/.local/bin/rnsd --service --config /home/op/second-config >/dev/null 2>&1; echo "second rnsd exit=$?") 
cat /home/op/second-config/logfile 2>/dev/null | head -3

echo "=== 6. the daemons attach"
as_op bash -c "nohup lxmd > /tmp/lxmd.out 2>&1 &"
as_op bash -c "nohup nomadnet --daemon --console > /tmp/nomadnet.out 2>&1 &"
sleep 8
as_op rnstatus 2>&1 | sed -n 1,5p
ls -a /home/op | grep -E "^\.(lxmd|nomadnetwork|reticulum)$"

echo "=== 7. rnsh identities"
as_op rnsh -p 2>&1 | tail -2
as_op rnsh -l -p 2>&1 | tail -3

echo "=== 8. uninstall"
pkill -x rnsd; pkill -x lxmd; pkill -x python3.13 >/dev/null 2>&1; sleep 1
: > /tmp/systemctl.log
as_op $H uninstall rns lxmf nomadnet --yes > /tmp/uninstall.txt 2>&1; echo "uninstall exit=$?"; tail -4 /tmp/uninstall.txt
echo "--- systemctl stub log"; cat /tmp/systemctl.log
echo "--- venvs, wrappers, unit file"; ls /home/op/.local/share/hammunition/venvs 2>&1; ls /home/op/.local/bin 2>&1; ls /home/op/.config/systemd/user 2>&1
echo "--- identities left in place"; ls -d /home/op/.reticulum /home/op/.lxmd /home/op/.nomadnetwork /home/op/.rnsh 2>&1
EOS
chmod 0755 "$HOME/.cache/hm-reticulum-measure/measure_single.sh"
```

Expected: nothing printed; `$HOME/.cache/hm-reticulum-measure/measure_single.sh` exists.

- [ ] **Step 4: Write the node setup shared by the two-container run**

Makes an operator account with the three units installed through the engine, and drops two ten-line LXMF scripts (a receiver and a sender, the layer NomadNet uses) in `/home/op`.

Run:

```bash
mkdir -p "$HOME/.cache/hm-reticulum-measure"
cat > "$HOME/.cache/hm-reticulum-measure/node_setup.sh" <<'EOS'
#!/bin/bash
# Inside a debian:13 target container, as root: an operator account with the three
# Reticulum units installed through the engine, unprivileged. Measurement only.
set -eu
H=/opt/hammunition-venv/bin/hammunition
useradd -m -s /bin/bash op
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq --no-install-recommends iproute2 procps >/dev/null 2>&1
printf '#!/bin/sh\necho "systemctl $*" >> /tmp/systemctl.log\nexit 0\n' > /usr/local/bin/systemctl
chmod 0755 /usr/local/bin/systemctl
runuser -u op -- env HOME=/home/op $H install rns lxmf nomadnet --yes > /tmp/install.txt 2>&1
tail -3 /tmp/install.txt
cat > /home/op/lxmf_receive.py <<'PY'
import sys, time
import RNS, LXMF

config, storage, seconds = sys.argv[1], sys.argv[2], int(sys.argv[3])
RNS.Reticulum(configdir=config)
router = LXMF.LXMRouter(storagepath=storage)
destination = router.register_delivery_identity(RNS.Identity(), display_name="receiver")


def on_message(message):
    print("RECEIVED:", message.content_as_string(), flush=True)


router.register_delivery_callback(on_message)
destination.announce()
print("ADDRESS:", RNS.hexrep(destination.hash, delimit=False), flush=True)
time.sleep(seconds)
PY
cat > /home/op/lxmf_send.py <<'PY'
import sys, time
import RNS, LXMF

config, storage, address, text = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
RNS.Reticulum(configdir=config)
router = LXMF.LXMRouter(storagepath=storage)
source = router.register_delivery_identity(RNS.Identity(), display_name="sender")
recipient = bytes.fromhex(address)
deadline = time.time() + 30
while not RNS.Transport.has_path(recipient) and time.time() < deadline:
    RNS.Transport.request_path(recipient)
    time.sleep(1)
identity = RNS.Identity.recall(recipient)
if identity is None:
    print("NO PATH", flush=True)
    sys.exit(2)
destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
message = LXMF.LXMessage(destination, source, text, desired_method=LXMF.LXMessage.DIRECT)
state = {"done": False}


def delivered(m):
    state["done"] = True
    print("DELIVERED", flush=True)


message.register_delivery_callback(delivered)
router.handle_outbound(message)
deadline = time.time() + 30
while not state["done"] and time.time() < deadline:
    time.sleep(0.5)
sys.exit(0 if state["done"] else 3)
PY
chown op:op /home/op/lxmf_*.py
EOS
chmod 0755 "$HOME/.cache/hm-reticulum-measure/node_setup.sh"
```

Expected: nothing printed; `$HOME/.cache/hm-reticulum-measure/node_setup.sh` exists.

- [ ] **Step 5: Write the two-container measurement**

Two containers on one bridge network; `a` is a transport that answers probes, `b` is plain; measures peers, `rnprobe`, an LXMF message and an `rnsh` command over the AutoInterface, then removes both containers and the network.

Run:

```bash
mkdir -p "$HOME/.cache/hm-reticulum-measure"
cat > "$HOME/.cache/hm-reticulum-measure/pair.sh" <<'EOS'
#!/bin/bash
# Host side: two containers on one bridge, Reticulum on each, measured over the
# AutoInterface. Measurement only; nothing here is part of the engine.
set -u
IMG=hammunition-debian-13:reticulum
podman rm -f hm-ret-a hm-ret-b >/dev/null 2>&1
podman network rm -f hm-ret >/dev/null 2>&1
podman network create hm-ret >/dev/null || exit 1
for n in a b; do podman run -d --name hm-ret-$n --network hm-ret $IMG sleep infinity >/dev/null; done
for n in a b; do echo "--- setup $n"; podman exec -i hm-ret-$n bash -s < node_setup.sh; done
X() { n=$1; shift; podman exec -u op -e HOME=/home/op -e PYTHONUNBUFFERED=1 -e PATH="/home/op/.local/bin:/usr/local/bin:/usr/bin:/bin" hm-ret-$n "$@"; }
echo "=== link-local IPv6 in each"
for n in a b; do podman exec hm-ret-$n ip -6 addr show scope link | grep inet6; done
echo "=== a is a transport that answers probes; b is plain"
X a bash -c 'mkdir -p ~/.reticulum && rnsd --exampleconfig > ~/.reticulum/config && sed -i "s/^enable_transport = no/enable_transport = yes/; s/^# respond_to_probes = no/respond_to_probes = yes/" ~/.reticulum/config && grep -n "^enable_transport\|^respond_to_probes" ~/.reticulum/config'
X a bash -c 'nohup rnsd --service > /tmp/rnsd.out 2>&1 &'
X b bash -c 'nohup rnsd --service > /tmp/rnsd.out 2>&1 &'
sleep 20
echo "=== rnstatus on each"
X a rnstatus | sed -n 1,20p
X b rnstatus | sed -n 1,20p
PH=$(X a bash -c "sed -n 's/.*probe requests on <rnstransport\.probe\.[0-9a-f]*:\([0-9a-f]*\)>.*/\1/p' ~/.reticulum/logfile | tail -1")
echo "=== rnprobe from b to a's probe destination $PH"
X b rnprobe -t 20 rnstransport.probe "$PH"; echo "rnprobe exit=$?"
echo "=== LXMF message, b to a"
X a bash -c 'nohup /home/op/.local/share/hammunition/venvs/lxmf/bin/python /home/op/lxmf_receive.py /home/op/.reticulum /home/op/lxa 60 > /tmp/rx.out 2>&1 &'
sleep 8
ADDR=$(X a bash -c "sed -n 's/^ADDRESS: //p' /tmp/rx.out")
echo "address $ADDR"
X b /home/op/.local/share/hammunition/venvs/lxmf/bin/python /home/op/lxmf_send.py /home/op/.reticulum /home/op/lxb "$ADDR" "hello over the AutoInterface"; echo "send exit=$?"
sleep 3; X a cat /tmp/rx.out
echo "=== rnsh, b to a"
BID=$(X b rnsh -p 2>&1 | sed -n 's/^Identity *: <\([0-9a-f]*\)>.*/\1/p' | tail -1)
ADEST=$(X a rnsh -l -p 2>&1 | sed -n 's/^Listening on : <\([0-9a-f]*\)>.*/\1/p' | tail -1)
echo "b identity $BID; a destination $ADEST"
X a bash -c "nohup rnsh -l -vv -a $BID -b 0 > /tmp/rnsh.out 2>&1 &"
sleep 8
X b bash -c "(sleep 6) | timeout 25 rnsh $ADEST -- echo hello-from-a" ; echo "rnsh client exit=$?"
X a bash -c "grep -h 'Initiator identified\|executing' /home/op/.rnsh/logfile /tmp/rnsh.out 2>/dev/null | sort -u | cut -c1-160"
echo "=== peers after all that"
X a rnstatus | grep -i "peers"
X b rnstatus | grep -i "peers"
echo "=== cleanup"
for n in a b; do podman rm -f hm-ret-$n >/dev/null; done
podman network rm hm-ret >/dev/null
EOS
chmod 0755 "$HOME/.cache/hm-reticulum-measure/pair.sh"
```

Expected: nothing printed; `$HOME/.cache/hm-reticulum-measure/pair.sh` exists.

- [ ] **Step 6: Write the two checks**

Asserts, line by line, what the single-container log must contain: each assertion is one claim the guide will make.

Run:

```bash
mkdir -p "$HOME/.cache/hm-reticulum-measure"
cat > "$HOME/.cache/hm-reticulum-measure/check_single.sh" <<'EOS'
#!/bin/bash
# Asserts what the single-container run must have printed. Reads single.out.
F="${1:-$HOME/.cache/hm-reticulum-measure/single.out}"
bad=0
has() { grep -qE -- "$2" "$F" && echo "ok    $1" || { echo "FAIL  $1"; bad=1; }; }
between() { awk -v a="$1" -v b="$2" '$0 ~ a {f=1; next} $0 ~ b {f=0} f' "$F"; }
has "dry run exits 0"                          '^dry-run exit=0'
has "the rns venv line states the licence"     'Install rns into its venv.*licence: Reticulum License \(MIT plus two use restrictions'
has "the lxmf venv line states the licence"    'Install lxmf into its venv.*licence: Reticulum License'
has "the nomadnet venv line states its licence" 'Install nomadnet into its venv.*licence: GPL-3.0-only'
has "the service block names the venv's rnsd"  'runs     /home/op/\.local/share/hammunition/venvs/rns/bin/rnsd --service'
has "the service is not started at install"    'hammunition-rnsd is not started now: it starts at your next login'
has "install exits 0 unprivileged"             '^install exit=0'
has "the stubbed systemctl enabled the unit"   'systemctl --user enable hammunition-rnsd\.service'
has "the stubbed systemctl try-restarted it"   'systemctl --user try-restart hammunition-rnsd\.service'
has "the engine wrote no ~/.reticulum"         "cannot access '/home/op/\.reticulum'"
has "rnstatus names the shared instance"       'Shared Instance\[rns/default\]'
has "the AutoInterface is up"                  'AutoInterface\[Default Interface\]'
has "UDP 29716 is bound"                       ':29716 '
has "UDP 29717 is bound"                       ':29717 '
has "UDP 42671 is bound"                       ':42671 '
has "the abstract socket is bound"             '@rns/default '
has "another account's rnstatus cannot read"   'op2 rnstatus exit=2'
has "another account's rnsd attached"          '^op2 rnsd exit=124'
has "a second rnsd warns and attaches"         'connected to another shared local instance, this is probably NOT what you want!'
has "lxmd and nomadnet attach"                 'Serving   : 2 programs'
has "rnsh prints a listening destination"      'Listening on : <[0-9a-f]{32}>'
has "uninstall exits 0"                        '^uninstall exit=0'
has "uninstall disabled the unit"              'systemctl --user disable --now hammunition-rnsd\.service'
n=$(between '^--- wrappers' '^--- venvs' | grep -c .)
[ "$n" = 12 ] && echo "ok    twelve wrappers" || { echo "FAIL  wrappers: $n"; bad=1; }
t=$(between '^--- tcp listeners' '^--- udp listeners' | grep -c .)
[ "$t" = 0 ] && echo "ok    no TCP listener" || { echo "FAIL  TCP listeners: $t"; bad=1; }
k=$(between '^--- identities left in place' '^NOSUCHMARKER' | grep -c '^/home/op/\.\(reticulum\|lxmd\|nomadnetwork\|rnsh\)$')
[ "$k" = 4 ] && echo "ok    four identity directories left" || { echo "FAIL  identity directories left: $k"; bad=1; }
d=$(grep -cE 'Done\. [0-9]+ command\(s\) completed and confirmed\.' "$F")
[ "$d" = 2 ] && echo "ok    install and uninstall both completed and confirmed" || { echo "FAIL  Done lines: $d"; bad=1; }
exit $bad
EOS
chmod 0755 "$HOME/.cache/hm-reticulum-measure/check_single.sh"
```

Expected: nothing printed; `$HOME/.cache/hm-reticulum-measure/check_single.sh` exists.

- [ ] **Step 7: Write the second check**

Run:

```bash
mkdir -p "$HOME/.cache/hm-reticulum-measure"
cat > "$HOME/.cache/hm-reticulum-measure/check_pair.sh" <<'EOS'
#!/bin/bash
# Asserts what the two-container run must have printed. Reads pair.out.
F="${1:-$HOME/.cache/hm-reticulum-measure/pair.out}"
bad=0
has() { grep -qE -- "$2" "$F" && echo "ok    $1" || { echo "FAIL  $1"; bad=1; }; }
has "both machines see a peer"           'Peers     : 1 reachable'
has "the transport answers probes"       'Probe responder at <[0-9a-f]{32}> active'
has "rnprobe gets a valid reply"         'Valid reply from <[0-9a-f]{32}>'
has "rnprobe reports one hop"            'Round-trip time is [0-9.]+ milliseconds over 1 hop'
has "the LXMF message is delivered"      '^DELIVERED'
has "the LXMF message is received"       'RECEIVED: hello over the AutoInterface'
has "rnsh listener authenticated"        'Initiator identified <[0-9a-f]{32}>'
has "rnsh listener ran the command"      "executing: \['echo', 'hello-from-a'\]"
n=$(grep -c 'Peers     : 1 reachable' "$F")
[ "$n" -ge 2 ] && echo "ok    peers on both machines" || { echo "FAIL  peers lines: $n"; bad=1; }
exit $bad
EOS
chmod 0755 "$HOME/.cache/hm-reticulum-measure/check_pair.sh"
```

Expected: nothing printed; `$HOME/.cache/hm-reticulum-measure/check_pair.sh` exists.

- [ ] **Step 8: Run the single-container measurement**

Run:

```bash
cd "$HOME/.cache/hm-reticulum-measure" && nice -n 19 podman run --rm -i hammunition-debian-13:reticulum bash -s < measure_single.sh > single.out 2>&1; echo "podman exit=$?"
```

Expected: `podman exit=0` after about two minutes (the engine install and uninstall, the daemons' sleeps).

- [ ] **Step 9: Check it**

Run:

```bash
"$HOME/.cache/hm-reticulum-measure/check_single.sh" "$HOME/.cache/hm-reticulum-measure/single.out"
```

Expected: twenty-seven `ok` lines and no `FAIL`. A `FAIL` is a finding: stop, say which claim did not hold, and fix the page that makes it (the units' `known_problems`, the guide, the troubleshooting entry) before going on; do not edit a check to match.

- [ ] **Step 10: Run the two-container measurement**

Run:

```bash
cd "$HOME/.cache/hm-reticulum-measure" && nice -n 19 ./pair.sh > pair.out 2>&1; echo "pair exit=$?"; podman ps -a --format "{{.Names}}"; podman network ls --format "{{.Name}}"
```

Expected: `pair exit=0`; the final warnings `StopSignal SIGTERM failed to stop container ... resorting to SIGKILL` and, on some Podman versions, `rootless netns: kill network process: permission denied` are the harness's cleanup and do not matter; the two lists must show no `hm-ret-a`, `hm-ret-b` or `hm-ret` left (remove them with `podman rm -f` and `podman network rm` if they are).

- [ ] **Step 11: Check it**

Run:

```bash
"$HOME/.cache/hm-reticulum-measure/check_pair.sh" "$HOME/.cache/hm-reticulum-measure/pair.out"
```

Expected: nine `ok` lines and no `FAIL`.

- [ ] **Step 12: See the checks go red**

Run:

```bash
sed "/op2 rnstatus exit=2/d" "$HOME/.cache/hm-reticulum-measure/single.out" > "$HOME/.cache/hm-reticulum-measure/doctored.out"; "$HOME/.cache/hm-reticulum-measure/check_single.sh" "$HOME/.cache/hm-reticulum-measure/doctored.out" | grep FAIL; echo "exit=${PIPESTATUS[0]}"
```

Expected: `FAIL  another account's rnstatus cannot read` and a non-zero exit: the checks are seen to go red on a missing claim, not only green on a present one.

- [ ] **Step 13: Write what was measured into the guide, the unit pages, the entry and the decision**

One script, so the numbers in the prose are the run's: the counts of commands the engine reported for the install and the uninstall, and the `rnprobe` round trip are read from the logs; every other replacement asserts the text it replaces is there exactly once. Section 13 becomes the container run's account (what the engine did, what the unit runs, another account, two machines, uninstall) followed by what is still not measured. Sections 3, the `rns` and `nomadnet` pages, the AutoInterface troubleshooting item and D-080's last paragraph change from "upstream says" / "not measured" to what was read from a socket.

````bash
python3 - <<'PY'
import pathlib, re

work = pathlib.Path.home() / ".cache" / "hm-reticulum-measure"
single = (work / "single.out").read_text()
pair = (work / "pair.out").read_text()
done = re.findall(r"Done\. (\d+) command\(s\) completed and confirmed", single)
assert len(done) == 2, "the single-container run should end two transactions"
install_n, uninstall_n = done
rtt = re.search(r"Round-trip time is ([0-9.]+) milliseconds over 1 hop", pair).group(1)


def edit(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text()
    for old, new in pairs:
        assert s.count(old) == 1, f"{path}: the text to replace moved: {old[:50]!r}"
        s = s.replace(old, new, 1)
    p.write_text(s)


SECTION = """## 13. What is measured, and what is not

Measured on 2026-10-03, in two ways. First on a Parrot 7.4 machine, in a scratch
virtualenv and with a Reticulum configuration that had no interfaces, so nothing
reached a network:

- **The pins install.** `rns` 1.5.6, `lxmf` 1.2.0 and `nomadnet` 1.4.4, each
  with its hash-pinned closure, installed with `pip install --require-hashes`
  on Python 3.13.5, every hash matching, and every command this page names is
  in `bin/`.
- **The shared instance is a local socket.** `rnsd` bound the abstract Unix
  sockets `@rns/<name>` and `@rns/<name>/rpc` and no TCP port, and
  `rnstatus` read it as `Shared Instance[rns/<name>]`. `rnsd --service` wrote
  `~/.reticulum/logfile`.
- **A second `rnsd` does not fail.** It attached to the first, logged "connected
  to another shared local instance, this is probably NOT what you want!" and
  kept running; `rnstatus` against its own configuration said "Could not get
  RNS status".
- **`lxmd` and `nomadnet --daemon`** both attached to that instance and kept
  running (`rnstatus` then read `Serving : 2 programs`), and created `~/.lxmd`
  and `~/.nomadnetwork` with the contents sections 4 and 9 name.
- **`rnsh -p` and `rnsh -l -p`** printed an `Identity` line and, in listen
  mode, a `Listening on` line, and created `~/.rnsh/identity`.
- **The options this page quotes** are those of the installed programs'
  `--help`, and the interface stanzas are upstream's manual for 1.5.5, both
  read that day.

Then in Debian 13 containers built from the repository's own target image
(`containers/Dockerfile.target`), as an ordinary account, with `hammunition
install rns lxmf nomadnet` through the engine, and `systemctl` replaced by a
stub that records what it is asked, because a container has no systemd user
manager:

- **The engine.** The dry run printed the licence on each venv's line and the
  *User services* block (`runs …/venvs/rns/bin/rnsd --service`, "is not started
  now: it starts at your next login"). The install exited 0 with @INSTALL_N@ commands
  confirmed, unprivileged, and left the twelve wrappers `lxmd`, `nomadnet`,
  `nomadnet-terminal`, `rncp`, `rnid`, `rnodeconf`, `rnpath`, `rnprobe`,
  `rnsd`, `rnsh`, `rnstatus` and `rnx`, the three virtualenvs and the unit file.
  The stub was asked to `daemon-reload`, `enable hammunition-rnsd.service` and
  `try-restart` it, and `~/.reticulum` **did not exist** after the install: the
  engine writes none.
- **What the unit runs.** Started from the `ExecStart` line the engine wrote,
  `rnsd` created `~/.reticulum` (`config`, `interfaces`, `logfile`, `storage`)
  whose default configuration enables only the AutoInterface, and `rnstatus`
  read `Shared Instance[rns/default]` and `AutoInterface[Default Interface]`.
  `ss` showed no TCP listener, the abstract sockets `@rns/default` and
  `@rns/default/rpc`, and UDP 29716 on a multicast address with 29717 and 42671
  on the interface's link-local address.
- **Another account.** A second account on the same machine ran `rnstatus`
  against the first account's instance and got "Could not get RNS status"
  (exit 2), and its own `rnsd --service` attached to the first account's
  instance with the same warning in its log. What an attached client can then
  send through your interfaces was not measured.
- **Two machines.** Two containers on one bridge network, each running the
  instance: `rnstatus` on both read `Peers : 1 reachable`. With
  `enable_transport = yes` and `respond_to_probes = yes` on one, `rnstatus`
  there read `Probe responder at <hash> active`, and `rnprobe rnstransport.probe
  <hash>` from the other printed `Valid reply` with a round trip of @RTT@ ms over
  one hop. An LXMF message sent from one to the other, with a ten-line Python
  script against the installed `lxmf`, was delivered and received. An `rnsh`
  listener on one logged `Initiator identified` and `Remote … executing:
  ['echo', 'hello-from-a']` for the other's connection; the connecting
  client's own screen was not observed (the harness has no terminal).
- **Uninstall.** `hammunition uninstall rns lxmf nomadnet` exited 0 with @UNINSTALL_N@
  commands, asked the stub to `disable --now hammunition-rnsd.service`, and
  removed the unit file, the virtualenvs, the wrappers and the menu entry. It
  left `~/.reticulum`, `~/.lxmd`, `~/.nomadnetwork` and `~/.rnsh` in place.

Not measured, and this page says so where it matters:

- **No LoRa link.** No RNode, and no Meshtastic node, has been run for this
  page. The maintainer's LoRa boards were lost in a flood; the `rnode` entry
  is recorded from upstream's board lists, as `meshtastic` was, and says
  `untested`.
- **NomadNet's text interface**, and a message sent through NomadNet's own
  screen rather than at the LXMF layer. It was started in daemon mode only;
  what it looks like and where its keys are is its own help's business.
- **Any internet link.** The TCP and Backbone examples are upstream's, and a
  connection to a public hub is not run from this project's CI by policy.
- **What another account could do through your instance**, beyond attaching to
  it, and the `rncp` file transfer, which was not run.
- **`rnodeconf`'s download.** Where it fetches firmware from and whether it
  verifies what it fetches.
- **The service under a real systemd user manager**, `lxmd` as a service, and
  propagation between two nodes.
- **arm64 and Python 3.14.** The hash sets cover every file PyPI lists, and the
  wheels exist on both architectures (the inventory's resolver run); neither
  was installed.
"""
section = (
    SECTION.replace("@INSTALL_N@", install_n).replace("@UNINSTALL_N@", uninstall_n).replace("@RTT@", rtt)
)
guide = pathlib.Path("docs/guides/mesh-and-reticulum.md")
s = guide.read_text()
i = s.index("## 13. What is measured, and what is not")
guide.write_text(s[:i] + section)

edit(
    "docs/guides/mesh-and-reticulum.md",
    [
        ("""other with no routers, no DHCP and no configuration. Upstream says the
interface uses UDP ports 29716 and 42671 and that a firewall may need to allow
them (the manual for 1.5.5). The engine writes none of this file and never
edits it: it is created by `rnsd`, under your account, and it is yours.""", """other with no routers, no DHCP and no configuration. Upstream says the
interface uses UDP ports 29716 and 42671 and that a firewall may need to allow
them (the manual for 1.5.5); on a running instance `ss -lun` showed 29716 on a
multicast group address and 29717 and 42671 on the interface's link-local
address (measured 2026-10-03). The engine writes none of this file and never
edits it: it is created by `rnsd`, under your account, and it is yours."""),
        ("""shows its peers: upstream's manual shows `Peers : 1 reachable`. If it stays at
none,""", """shows its peers: `Peers : 1 reachable` on each (measured with two containers
on one bridge network, 2026-10-03). If it stays at none,"""),
        ("""says "Could not get RNS status"](../troubleshooting/running.md#reticulum-no-instance).

On first start `rnsd` writes""", """says "Could not get RNS status"](../troubleshooting/running.md#reticulum-no-instance).
On a single machine it reads, in part (measured 2026-10-03 in a Debian 13
container):

```
 Shared Instance[rns/default]
    Status    : Up
    Serving   : 0 programs

 AutoInterface[Default Interface]
    Status    : Up
    Mode      : Full
    Peers     : 0 reachable
```

On first start `rnsd` writes"""),
    ],
)
edit("catalog/packages/rns.yaml", [("""    uses UDP ports 29716 and 42671 and that a firewall may need to allow them;
    the guide says what was measured. The file and the identity beside it are""", """    uses UDP ports 29716 and 42671 and that a firewall may need to allow them;
    in a Debian 13 container `rnsd` held UDP 29716 (on a multicast address),
    29717 and 42671 (on the link-local address) and no TCP port (measured
    2026-10-03). The file and the identity beside it are"""), ("""    another account on the same machine can attach to it as a client. Which of
    your interfaces that lets it use was not measured on a multi-user machine
    for this unit; treat the machine as a single-operator one.""", """    another account on the same machine can attach to it as a client: a second
    account's `rnsd` did, with the same warning as below (measured 2026-10-03,
    Debian 13 container). What an attached client can then send through your
    interfaces was not measured; treat the machine as a single-operator one.""")])
edit("catalog/packages/nomadnet.yaml", [("""its own venv. Only `nomadnet -d` against an interfaceless shared instance
    was run on 2026-10-03 (it attached and kept running); the text interface
    and a message between two machines were not measured.""", """its own venv. `nomadnet -d` attached to a shared instance and kept running
    (2026-10-03), and an LXMF message between two machines was delivered at the
    library level; NomadNet's text interface, and a message through its own
    screen, were not measured.""")])
edit("docs/troubleshooting/running.md", [("""3. **A firewall?** Upstream says the interface uses UDP ports 29716 and 42671
   and that a firewall may need to allow them (its manual for 1.5.5; not
   measured here).""", """3. **A firewall?** Upstream says the interface uses UDP ports 29716 and 42671
   and that a firewall may need to allow them (its manual for 1.5.5). On a
   running instance `ss -lun` showed 29716 on a multicast group address and
   29717 and 42671 on the interface's link-local address (measured 2026-10-03).""")])
edit("docs/DECISIONS.md", [("""**Not measured.** Any LoRa link: no RNode has been run, and the maintainer's
LoRa boards were lost in a flood. A public hub (not run from CI by policy). The
service under a real systemd user manager. What is measured and what is not is
the last section of `docs/guides/mesh-and-reticulum.md`.""", """**Measured, and not.** The engine installed the three units unprivileged in a
Debian 13 container, the unit's `ExecStart` ran, and two containers on one bridge
saw each other over the AutoInterface, answered `rnprobe`, exchanged an LXMF
message and ran an `rnsh` command (2026-10-03). Not measured: any LoRa link (no
RNode has been run, and the maintainer's LoRa boards were lost in a flood), a
public hub (not run from CI by policy), the service under a real systemd user
manager, NomadNet's text interface, and what an attached client of another
account can do. The last section of `docs/guides/mesh-and-reticulum.md` has the
detail.""")])
print("installed in", install_n, "commands, removed in", uninstall_n, "; rnprobe", rtt, "ms")
PY
````

- [ ] **Step 14: Add the test that holds section 13 to the run**

Append this to the end of `tests/test_reticulum_docs.py`, after 2 blank lines:

```python
def test_the_last_section_records_the_container_run_and_what_it_did_not_cover() -> None:
    """Section 13 is the page's honesty: what the Debian 13 container run measured,
    and what that run could not reach (a radio, an internet hub, a terminal)."""
    text = _flat(_text(GUIDE))
    section = text[text.index("## 13. What is measured, and what is not") :]
    for measured in (
        "Debian 13 containers",
        "Peers : 1 reachable",
        "Probe responder at",
        "Valid reply",
        "was delivered and received",
        "Initiator identified",
        "Could not get RNS status",
        "did not exist",
        "29717",
    ):
        assert measured in section, measured
    for not_measured in ("No LoRa link", "NomadNet's text interface", "Any internet link"):
        assert not_measured in section, not_measured
    assert "not yet" not in section  # the pre-container wording is gone
```

- [ ] **Step 15: Regenerate the unit pages and run the documentation tests**

Run:

```bash
.venv/bin/python scripts/gen_package_reference.py && git add -A && nice -n 19 .venv/bin/python -m pytest tests/test_reticulum_docs.py tests/test_reticulum_catalog.py tests/test_docs_generated.py tests/test_site.py -p no:cacheprovider && python3 scripts/check_doc_links.py
```

Expected: a `NN passed` summary with no `failed` (`tests/test_reticulum_docs.py` alone is now `14 passed`), then `no broken internal references`.

- [ ] **Step 16: Gates**

Run:

```bash
nice -n 19 .venv/bin/ruff check . && nice -n 19 .venv/bin/ruff format --check . && PYTHONPATH=src nice -n 19 .venv/bin/mypy --strict tests/test_reticulum_docs.py
```

Expected: clean.

- [ ] **Step 17: Commit**

Run:

```bash
git add -A
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com commit -F - <<'MSG'
Record what the Debian 13 container run measured

The guide's last section, the rns and nomadnet pages, the AutoInterface
troubleshooting item and the decision's last paragraph now say what was read
from a socket, a log or an exit status, and what no container could reach.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

Expected: the commit-msg hook prints `commit claims check: ok` and git reports the new commit.

### Task 12: The changelog fragment, the whole gate, the pin check and the push

**Files:**
- Create: `changelog.d/reticulum-core.added.md`

**Interfaces:**
- Consumes: everything.
- Produces: a branch `reticulum-core` that a maintainer can review and merge: green under `make check` and under an unshared root namespace, with one changelog fragment.

- [ ] **Step 1: Write the fragment**

CLAUDE.md: never edit `CHANGELOG.md` in a pull request; add one fragment `changelog.d/<pr-or-branch>.<kind>.md`, the entry as one bullet naming the PR and the decision. `tests/test_changelog.py` fails a pull request that changes `src/`, `catalog/` or `docs/guides/` without one.

Create `changelog.d/reticulum-core.added.md` with exactly this content:

```markdown
- **Reticulum, NomadNet and LXMF** (Track C, PR 2, issue #105, **D-080**). Three
  hash-pinned per-user venvs, `rns`, `lxmf` and `nomadnet`, because no archive
  carries any of them: `rns` exposes `rnsd`, `rnstatus`, `rnpath`, `rnprobe`,
  `rnid`, `rncp`, `rnx`, `rnsh` and the RNode flasher `rnodeconf` and installs a
  user service, `hammunition-rnsd`, that keeps one shared instance per operator
  (enabled at install, started at next login; a local socket, not a TCP port);
  `lxmf` gives `lxmd` and starts nothing; `nomadnet` gives the terminal
  messenger and a menu entry. The Reticulum License (MIT plus two use
  restrictions, not OSI-approved) is printed on the plan line that installs the
  venv and never gated; NomadNet is `GPL-3.0-only` by its shipped text. The
  engine writes no Reticulum configuration and uninstall leaves `~/.reticulum`,
  `~/.nomadnetwork`, `~/.lxmd` and `~/.rnsh`. New post-1.0 `mesh` profile
  (the three plus `python3-meshtastic` and `gtk-meshtastic-client`), a `rnode`
  hardware entry (`untested`: no identifier of its own), and
  `docs/guides/mesh-and-reticulum.md` with four troubleshooting entries. Engine:
  a user service's `exec` may start `{venv}/...`, and a venv block may state its
  `licence` and `licence_url` on its plan line. No LoRa link has been run.
```

- [ ] **Step 2: Check the fragment is well formed**

Run:

```bash
git add -A && nice -n 19 .venv/bin/python -m pytest tests/test_changelog.py tests/test_repo_hygiene.py -p no:cacheprovider
```

Expected: all pass (the pull-request test skips outside a PR run).

- [ ] **Step 3: Run the whole gate to a log and test its exit status**

Run:

```bash
LOG="$(mktemp)"; PYTHONPATH=src nice -n 19 make check > "$LOG" 2>&1; rc=$?; tail -5 "$LOG"; echo "make check rc=$rc"; test $rc -eq 0
```

Expected: `make check rc=0`: ruff, ruff format, `mypy --strict`, the test suite and the doc-link check, all green. Never `gate | grep && push`: capture to a log and test `$?` (it is the exit status that gates the push, not a line of output).

- [ ] **Step 4: Run the suite as root in a fresh user namespace, without your account's name**

Run:

```bash
T="$(mktemp -d)"; PYTHONPATH=src nice -n 19 unshare -r env -u USER -u SUDO_USER -u LOGNAME HOME="$T" XDG_CONFIG_HOME= XDG_STATE_HOME= XDG_DATA_HOME= XDG_CACHE_HOME= .venv/bin/python -m pytest -p no:cacheprovider > "$(mktemp)" 2>&1; echo "unshare pytest rc=$?"
```

Expected: `unshare pytest rc=0`. The CI containers run as root, and a test that passes as an ordinary user and fails as root is exactly the matrix-not-your-machine bug CLAUDE.md warns of. **Clear `USER`, `SUDO_USER` and `LOGNAME` and give the run a throwaway `HOME`, exactly as above.** The engine's per-user directories are owner-aware: as root with `$USER` set they resolve to that user's real home whatever `XDG_*_HOME` says, so a bare `unshare -r pytest` makes six tests (`tests/test_station_set_json.py`, `tests/test_json_interface.py::test_station_set_json_writes_a_station_set_document`, two in `tests/test_cli.py`) write into, and read from, the real `~/.config/hammunition/` and `~/.local/state/hammunition/` instead of the test's temporary ones. With the variables cleared the same six pass and touch nothing outside the temporary directory.

- [ ] **Step 5: Pin check for the three manifests**

Run:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_pin_reviews.py --verify-refs --only rns lxmf nomadnet
XDG_STATE_HOME="$(mktemp -d)" PYTHONPATH=src .venv/bin/hammunition update rns lxmf nomadnet --upstream 2>&1 | sed -n '/^Upstream/,/^Answers/p'
```

Expected: the first prints `0 git ref(s) checked in 3 changed manifest(s)`: **that script resolves git pins only**, and these three units have none, so it is a no-op for them (the spec's per-PR check does not apply to a venv). The check that does apply is the second: `update --upstream` asks PyPI whether each pin is current, and prints `rns current catalog 1.5.6 upstream 1.5.6`, the same for `lxmf` (1.2.0) and `nomadnet` (1.4.4). If upstream has moved by the time this runs, a row says `newer upstream`: that is not a failure of this branch, it is the cadence the units' `cadence_hint` describes; bump the three units together, in one commit, by resolving the three closures again.

- [ ] **Step 6: Look at what is going to be reviewed**

Run:

```bash
git status --short
git log --oneline origin/main..HEAD
```

Expected: a clean tree and the commits of Tasks 0 to 11 (two merge commits from Task 0 if they were needed).

- [ ] **Step 7: Push the branch**

Run:

```bash
git push origin reticulum-core
```

Expected: the branch updates on the remote. Do not merge it: a pull request is merged by the maintainer, never by the author of the branch (CLAUDE.md). Check the PR is still open before pushing again later: a push to a merged PR's branch strands the commit.


## Self-review

Run against the spec after the plan was written; every gap found was fixed in the task named.

**Spec coverage.**

| Spec | Task |
|---|---|
| Units table: `rns`, `lxmf`, `nomadnet`, exposes, categories, notes; no separate `rnsh` | 3, 4, 5 |
| Depends: `python3-venv`; no `build_depends`; arm64 and Python 3.14 named as not installed | 3 to 5, 11 (section 13) |
| Licence fields, `licence-verification.md` rows, NomadNet `GPL-3.0-only` | 2, 3 to 5, 9 |
| `hammunition-rnsd`: `{venv}`, plain service, enabled at install, first-start behaviour disclosed, no configuration written, uninstall leaves `~/.reticulum`, `restart_prevent_exit_status` conditional | 1, 3, 7, 11 |
| `rnode` entry and `docs/hardware/rnode.md` | 6 |
| `mesh` profile with the ten documentation fields | 8 |
| Guide, all thirteen sections, Part 97 as disclosure, closing measured-and-not section | 7, 11 |
| Troubleshooting: no shared instance, no peers, `rnodeconf` port | 7 |
| Package pages, `projects.md`, parity report, CLI line, JSON reference unchanged | 3 to 5, 7, 10 |
| D-080, CLAUDE.md row, SCOPE status | 9 |
| Tests: catalog-wide, pin check, Debian 13 container run, uninstall leaves `~/.reticulum`, site and link checks | 3 to 12 |
| Open questions (a) enabled at install, (b) `mesh` carries the Meshtastic units | Global Constraints; Tasks 3 and 8 |

**Two spec points are not delivered as written, and why.** (1) The spec says the plan discloses the service's first-start behaviour. The plan view prints the service's name, unit, command and the `systemctl` steps, never its `description`, so the first-start behaviour (it writes `~/.reticulum/config`, enables the AutoInterface, opens no routable socket) is disclosed on the unit's page, in the guide and in D-080. Printing the description would add a field to the `install --dry-run --json` plan document (D-059) and is a separate change for the maintainer to decide. (2) The spec says uninstall leaves `~/.reticulum` in place "saying so". The uninstall output lists only what it removed and no manifest field prints a "left in place" note, so the page, the guide and D-080 say it; a printed note is a new manifest field, also for the maintainer to decide.

**Placeholder scan.** No step says "TBD", "TODO", "implement later", "add appropriate error handling", "similar to Task N" or "write tests for the above": every test, manifest, patch and document is given whole, or as a patch or an asserting edit script that fails loudly when its anchor text has moved. The two numbers the container run decides (the engine's command counts and the `rnprobe` round trip) are read from the logs by Task 11's edit script, which asserts it found them.

**Type and name consistency.** `service_venv_dir(manifest, owner=None) -> Path | None` and the `venv_dir` keyword of `plan_user_services` (Task 1) are the names Tasks 3 and the tests use; `licence` and `licence_url` (Task 2) are the keys the three manifests set; the test helpers `_unit`, `_venv`, `pinned`, `pinned_projects` and `hash_count` (Task 3) are the ones Tasks 4 and 5 append against; the anchors `reticulum-no-instance`, `reticulum-another-instance`, `reticulum-autointerface` and `rnodeconf-port` are spelled the same in the entries, the index, the guide and the test. Test counts in the `Expected:` lines were taken from a replay of this plan on a scratch worktree.

**Review Focus.** Each of the five has a test, a doc check or a container check in the task named beside it, and the first two and the fifth are also measured in Task 11. The two that could not be given a pure unit test (the AutoInterface and a foreign instance) are pinned through the documentation test plus the measured logs, and the plan says so.
