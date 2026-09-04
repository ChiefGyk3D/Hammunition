# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A unit that needs a kernel subsystem says so, and the plan checks the
running kernel for it.

Linux 7.1 removed `net/ax25`, `net/netrom`, `net/rose` and every driver in
`drivers/net/hamradio` (merge 64edfa65, 2026-04-24). Measured 2026-09-04:
Kali rolling (7.1.5) and Pop!_OS 24.04 (7.1.5) have no `CONFIG_AX25` and no
`ax25.ko`; `socket(AF_AX25)` fails with "Address family not supported by
protocol". Debian 13 (6.12), Parrot 7.3 (7.0.13), Ubuntu 24.04 (6.8) and
26.04 (7.0.0) carry it as a module. The overnight campaign had filed
`packet` as installing whole on Pop!_OS -- every package arrived, and
`kissattach` could never have worked. The kernel is a fact about the
*machine*, not the distribution (the same Pop!_OS VM has `ax25.ko.zst`
under its 7.0.11 kernel), so it is read at plan time, never from the
capability matrix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.kernel import KernelProbe
from hammunition.plan import PlanError
from test_plan import _apt, _manifest, _profile, _resolve


def _modules(tmp_path: Path, release: str, *, module: bool, builtin: bool) -> Path:
    root = tmp_path / "lib" / "modules"
    tree = root / release
    tree.mkdir(parents=True)
    if module:
        ko = tree / "kernel" / "net" / "ax25" / "ax25.ko.xz"
        ko.parent.mkdir(parents=True)
        ko.write_bytes(b"")
    (tree / "modules.builtin").write_text("kernel/net/ax25/ax25.ko\n" if builtin else "")
    return root


# ---------------------------------------------------------------------------
# The probe reads /lib/modules/<release>, never the loaded-module list
# ---------------------------------------------------------------------------


def test_the_probe_finds_ax25_as_a_module(tmp_path: Path) -> None:
    root = _modules(tmp_path, "6.12.107+deb13-amd64", module=True, builtin=False)
    probe = KernelProbe(release="6.12.107+deb13-amd64", modules_root=root)
    assert probe.available("ax25") is True


def test_the_probe_finds_ax25_built_in(tmp_path: Path) -> None:
    """A kernel with CONFIG_AX25=y ships no .ko; modules.builtin names it."""
    root = _modules(tmp_path, "6.8.0-custom", module=False, builtin=True)
    assert KernelProbe(release="6.8.0-custom", modules_root=root).available("ax25") is True


def test_a_7_1_kernel_has_no_ax25_and_the_probe_says_so(tmp_path: Path) -> None:
    root = _modules(tmp_path, "7.1.5+kali-amd64", module=False, builtin=False)
    assert KernelProbe(release="7.1.5+kali-amd64", modules_root=root).available("ax25") is False


def test_no_modules_tree_for_the_running_kernel_is_unknown_not_absent(tmp_path: Path) -> None:
    """A container runs on the host's kernel with no /lib/modules for it. That
    is not evidence either way, and the CI targets must not refuse packet
    units over it."""
    root = tmp_path / "lib" / "modules"
    root.mkdir(parents=True)
    assert KernelProbe(release="6.1.0-host", modules_root=root).available("ax25") is None


def test_the_probe_only_knows_measured_features(tmp_path: Path) -> None:
    root = _modules(tmp_path, "r", module=True, builtin=False)
    with pytest.raises(KeyError, match="netrom"):
        KernelProbe(release="r", modules_root=root).available("netrom")


# ---------------------------------------------------------------------------
# The manifest field
# ---------------------------------------------------------------------------


def test_the_schema_vocabulary_is_exactly_what_the_probe_can_see() -> None:
    """A name the schema accepts that the probe has no module path for would
    raise KeyError at plan time, on the operator's machine."""
    from typing import get_args

    from hammunition.kernel import DESCRIBE, FEATURES
    from hammunition.manifest.schema import KernelFeature

    assert set(get_args(KernelFeature)) == set(FEATURES) == set(DESCRIBE)


def test_requires_kernel_takes_only_measured_feature_names() -> None:
    assert _manifest(requires_kernel=["ax25"]).requires_kernel == ["ax25"]
    with pytest.raises(ValidationError, match="ax25"):
        _manifest(requires_kernel=["scc"])


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def _probe(answer: bool | None) -> KernelProbe:
    class Fixed(KernelProbe):
        def available(self, feature: str) -> bool | None:
            assert feature == "ax25"
            return answer

    return Fixed(release="7.1.5+kali-amd64", modules_root=Path("/nonexistent"))


def _catalog(*units: Any) -> dict[str, Any]:
    return {u.name: u for u in units}


def _unit(name: str, **overrides: Any) -> Any:
    return _manifest(
        name=name, install=[{"install": {"method": "apt", "packages": [name]}}], **overrides
    )


def test_a_unit_needing_ax25_is_refused_by_name_on_a_kernel_without_it(tmp_path: Path) -> None:
    catalog = _catalog(_unit("ax25-tools", requires_kernel=["ax25"]))
    with pytest.raises(PlanError) as excinfo:
        _resolve(
            tmp_path,
            ["ax25-tools"],
            catalog=catalog,
            known={"ax25-tools": None},
            kernel=_probe(False),
        )
    text = str(excinfo.value)
    assert "ax25-tools" in text
    assert "7.1.5+kali-amd64" in text
    assert "AX.25" in text and "64edfa65" in text
    # The remedies name what actually works, not a module we would build.
    assert "userspace" in text.lower() or "user-space" in text.lower()
    assert "dkms" not in text.lower() or "no distribution packages" in text.lower()


def test_a_profile_member_needing_ax25_is_deferred_and_the_rest_installs(tmp_path: Path) -> None:
    """The D-039 shape: the kernel is true of the machine, so a member defers."""
    catalog = _catalog(_unit("direwolf"), _unit("ax25-tools", requires_kernel=["ax25"]))
    profile = _profile(name="packet", packages=["direwolf", "ax25-tools"])
    plan = _resolve(
        tmp_path,
        ["packet"],
        catalog=catalog,
        profiles={"packet": profile},
        known={"direwolf": None, "ax25-tools": None},
        kernel=_probe(False),
    )
    assert plan.apt_to_install == ("direwolf",)
    (deferral,) = [d for d in plan.deferrals if d.kind == "package"]
    assert deferral.subject == "ax25-tools"
    assert "7.1.5+kali-amd64" in deferral.why


def test_a_member_already_deferred_by_the_archive_keeps_that_reason(tmp_path: Path) -> None:
    """Kali 2026.3, live: `ax25-tools` is absent from the archive AND the
    kernel lacks ax25. The first `packet` dry-run on the VM showed only the
    kernel reason -- the kernel block had replaced the archive deferral --
    and its remedy text ("a release that carries it needs no change here")
    was then false of Kali's archive. A reason already recorded stands; the
    typed-name refusal shows both."""
    catalog = _catalog(_unit("direwolf"), _unit("ax25-tools", requires_kernel=["ax25"]))
    profile = _profile(name="packet", packages=["direwolf", "ax25-tools"])
    plan = _resolve(
        tmp_path,
        ["packet"],
        catalog=catalog,
        profiles={"packet": profile},
        known={"direwolf": None},  # no candidate for ax25-tools
        kernel=_probe(False),
    )
    (deferral,) = [d for d in plan.deferrals if d.kind == "package"]
    assert deferral.subject == "ax25-tools"
    assert "no candidate" in deferral.why
    assert "7.1.5+kali-amd64" not in deferral.why


def test_a_kernel_that_carries_ax25_plans_the_unit_without_comment(tmp_path: Path) -> None:
    catalog = _catalog(_unit("ax25-tools", requires_kernel=["ax25"]))
    plan = _resolve(
        tmp_path,
        ["ax25-tools"],
        catalog=catalog,
        known={"ax25-tools": None},
        kernel=_probe(True),
    )
    assert plan.apt_to_install == ("ax25-tools",)
    assert not any("ax25" in n.lower() for n in plan.notes)


def test_an_unreadable_kernel_is_disclosed_as_unchecked_not_refused(tmp_path: Path) -> None:
    catalog = _catalog(_unit("ax25-tools", requires_kernel=["ax25"]))
    plan = _resolve(
        tmp_path,
        ["ax25-tools"],
        catalog=catalog,
        known={"ax25-tools": None},
        kernel=_probe(None),
    )
    assert plan.apt_to_install == ("ax25-tools",)
    (note,) = [n for n in plan.notes if "ax25-tools" in n]
    assert "cannot be checked" in note


def test_a_unit_without_the_field_never_consults_the_kernel(tmp_path: Path) -> None:
    class Untouchable(KernelProbe):
        def available(self, feature: str) -> bool | None:
            raise AssertionError("consulted for a unit that declares nothing")

    plan = _resolve(
        tmp_path,
        ["example"],
        apt=_apt(tmp_path, {"example": None}),
        kernel=Untouchable(release="x", modules_root=Path("/nonexistent")),
    )
    assert plan.apt_to_install == ("example",)
