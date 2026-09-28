# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A unit for one desktop: the manifest says which, the plan decides from the
session files it was handed.  D-060.

The case it exists for: `station` includes `hammunition-tray`, a Plasma
applet whose .deb depends on `plasma-workspace`. On Xubuntu or Lubuntu that
pulled the whole Plasma shell onto a machine chosen for being light. A
profile member for a desktop the machine has no session for is deferred by
name (the D-039 path); the same unit typed by name is refused, with the
remedy naming the unit that serves the machine's desktop when the catalog
has one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.desktop import Desktop
from hammunition.manifest.load import CatalogError, load_catalog
from hammunition.plan import PlanError
from test_plan import _manifest, _profile, _resolve

PLASMA = frozenset({Desktop.kde})
XFCE = frozenset({Desktop.xfce})
NONE: frozenset[Desktop] = frozenset()


def _unit(name: str, **overrides: Any) -> Any:
    return _manifest(
        name=name, install=[{"install": {"method": "apt", "packages": [name]}}], **overrides
    )


def _catalog(*units: Any) -> dict[str, Any]:
    return {u.name: u for u in units}


def _deferred(plan: Any) -> dict[str, Any]:
    return {d.subject: d for d in plan.deferrals if d.kind == "package"}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_desktops_defaults_to_any() -> None:
    assert _unit("plain").desktops is None


def test_desktops_takes_the_enum() -> None:
    assert _unit("tray", desktops=["kde"]).desktops == [Desktop.kde]


def test_desktops_refuses_an_unknown_name() -> None:
    with pytest.raises(ValidationError):
        _unit("tray", desktops=["plasma"])


def test_desktops_refuses_an_empty_list() -> None:
    """An empty list would mean "for no desktop": never installable, silently."""
    with pytest.raises(ValidationError, match="desktops"):
        _unit("tray", desktops=[])


def test_desktops_refuses_duplicates() -> None:
    with pytest.raises(ValidationError, match="kde"):
        _unit("tray", desktops=["kde", "kde"])


def test_desktop_alternative_needs_desktops() -> None:
    with pytest.raises(ValidationError, match="desktop_alternative"):
        _unit("tray", desktop_alternative="tray-qt")


def test_desktop_alternative_may_not_name_itself() -> None:
    with pytest.raises(ValidationError, match="itself"):
        _unit("tray", desktops=["kde"], desktop_alternative="tray")


def _write(directory: Path, name: str, extra: str = "") -> None:
    (directory / f"{name}.yaml").write_text(
        f"""name: {name}
version: "1.0"
summary: An example package
categories: [digital-modes]
install:
  - install:
      method: apt
      packages: [{name}]
update:
  probe:
    method: apt_policy
documentation:
  what_it_does: Does an example thing for the purposes of testing.
  why_you_want_it: Because the test suite requires a valid manifest.
  upstream_url: https://example.invalid/
{extra}"""
    )


def test_the_catalog_refuses_an_alternative_that_does_not_exist(tmp_path: Path) -> None:
    _write(tmp_path, "tray", "desktops: [kde]\ndesktop_alternative: tray-qt\n")
    with pytest.raises(CatalogError, match="tray-qt"):
        load_catalog(tmp_path)


def test_the_catalog_refuses_an_alternative_for_the_same_desktop(tmp_path: Path) -> None:
    _write(tmp_path, "tray", "desktops: [kde]\ndesktop_alternative: tray-qt\n")
    _write(tmp_path, "tray-qt", "desktops: [xfce, kde]\n")
    with pytest.raises(CatalogError, match="KDE Plasma"):
        load_catalog(tmp_path)


def test_the_catalog_refuses_an_alternative_for_any_desktop(tmp_path: Path) -> None:
    """No `desktops` means every desktop, which overlaps everything."""
    _write(tmp_path, "tray", "desktops: [kde]\ndesktop_alternative: tray-qt\n")
    _write(tmp_path, "tray-qt")
    with pytest.raises(CatalogError, match="tray-qt"):
        load_catalog(tmp_path)


def test_the_catalog_accepts_a_disjoint_alternative(tmp_path: Path) -> None:
    _write(tmp_path, "tray", "desktops: [kde]\ndesktop_alternative: tray-qt\n")
    _write(tmp_path, "tray-qt", "desktops: [xfce, lxqt]\n")
    assert set(load_catalog(tmp_path)) == {"tray", "tray-qt"}


def test_the_shipped_tray_is_for_plasma() -> None:
    catalog = load_catalog(Path(__file__).resolve().parent.parent / "catalog" / "packages")
    assert catalog["hammunition-tray"].desktops == [Desktop.kde]


# ---------------------------------------------------------------------------
# Plan: a profile member defers, a typed name refuses
# ---------------------------------------------------------------------------


def _station(**tray: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = _catalog(_unit("gpsd"), _unit("tray", desktops=["kde"], **tray))
    return catalog, {"station": _profile(name="station", packages=["gpsd", "tray"])}


def test_a_plasma_unit_installs_where_plasma_is(tmp_path: Path) -> None:
    catalog, profiles = _station()
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None, "tray": None},
        desktops=PLASMA,
    )
    assert plan.apt_to_install == ("gpsd", "tray")
    assert not _deferred(plan)


def test_a_plasma_unit_in_a_profile_is_deferred_on_xfce(tmp_path: Path) -> None:
    catalog, profiles = _station()
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None, "tray": None},
        desktops=XFCE,
    )
    assert plan.apt_to_install == ("gpsd",)
    deferral = _deferred(plan)["tray"]
    assert deferral.why == "for KDE Plasma; this machine has no KDE Plasma session (it has: Xfce)"
    assert "station" in deferral.what


def test_with_no_session_files_the_reason_says_it_has_none(tmp_path: Path) -> None:
    """A container or a server: no session directories at all."""
    catalog, profiles = _station()
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None, "tray": None},
        desktops=NONE,
    )
    assert _deferred(plan)["tray"].why.endswith("(it has none)")


def test_the_deferral_remedy_says_how_it_is_picked_up_later(tmp_path: Path) -> None:
    catalog, profiles = _station()
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None},
        desktops=XFCE,
    )
    remedy = _deferred(plan)["tray"].remedy
    assert "install station" in remedy


def test_the_deferral_remedy_names_the_alternative_that_serves_this_desktop(
    tmp_path: Path,
) -> None:
    catalog, profiles = _station(desktop_alternative="tray-qt")
    catalog["tray-qt"] = _unit("tray-qt", desktops=["xfce", "lxqt"])
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None},
        desktops=XFCE,
    )
    assert "tray-qt" in _deferred(plan)["tray"].remedy


def test_a_plasma_unit_typed_by_name_is_refused_with_a_remedy(tmp_path: Path) -> None:
    catalog = _catalog(_unit("tray", desktops=["kde"], desktop_alternative="tray-qt"))
    catalog["tray-qt"] = _unit("tray-qt", desktops=["xfce", "lxqt"])
    with pytest.raises(PlanError) as excinfo:
        _resolve(tmp_path, ["tray"], catalog=catalog, known={"tray": None}, desktops=XFCE)
    (blocker,) = excinfo.value.blockers
    assert blocker.subject == "tray"
    assert "no KDE Plasma session (it has: Xfce)" in blocker.reason
    assert blocker.remedy is not None and "hammunition install tray-qt" in blocker.remedy


def test_the_refusal_without_an_alternative_still_says_what_to_do(tmp_path: Path) -> None:
    catalog = _catalog(_unit("tray", desktops=["kde"]))
    with pytest.raises(PlanError) as excinfo:
        _resolve(tmp_path, ["tray"], catalog=catalog, known={"tray": None}, desktops=NONE)
    (blocker,) = excinfo.value.blockers
    assert blocker.remedy is not None and "KDE Plasma" in blocker.remedy


def test_an_alternative_that_does_not_serve_this_desktop_is_not_offered(tmp_path: Path) -> None:
    """On a GNOME machine the Qt tray is no answer either; say what is."""
    catalog = _catalog(_unit("tray", desktops=["kde"], desktop_alternative="tray-qt"))
    catalog["tray-qt"] = _unit("tray-qt", desktops=["xfce", "lxqt"])
    with pytest.raises(PlanError) as excinfo:
        _resolve(
            tmp_path,
            ["tray"],
            catalog=catalog,
            known={"tray": None},
            desktops=frozenset({Desktop.gnome}),
        )
    (blocker,) = excinfo.value.blockers
    assert blocker.remedy is not None
    assert "hammunition install tray-qt" not in blocker.remedy


def test_one_desktop_of_several_is_enough(tmp_path: Path) -> None:
    catalog = _catalog(_unit("tray", desktops=["kde"]))
    plan = _resolve(
        tmp_path,
        ["tray"],
        catalog=catalog,
        known={"tray": None},
        desktops=frozenset({Desktop.xfce, Desktop.kde}),
    )
    assert plan.apt_to_install == ("tray",)


def test_a_dependent_of_a_desktop_deferred_unit_defers_with_it(tmp_path: Path) -> None:
    catalog = _catalog(
        _unit("gpsd"), _unit("tray", desktops=["kde"]), _unit("widget", depends=["tray"])
    )
    profiles = {"station": _profile(name="station", packages=["gpsd", "tray", "widget"])}
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None, "tray": None, "widget": None},
        desktops=XFCE,
    )
    assert set(_deferred(plan)) == {"tray", "widget"}


def test_desktops_not_read_are_disclosed_and_the_unit_is_planned(tmp_path: Path) -> None:
    """`None` is "not read", the way an unreadable kernel is: disclosed, not guessed."""
    catalog = _catalog(_unit("tray", desktops=["kde"]))
    plan = _resolve(tmp_path, ["tray"], catalog=catalog, known={"tray": None}, desktops=None)
    assert plan.apt_to_install == ("tray",)
    (note,) = [n for n in plan.notes if "tray" in n]
    assert "not read" in note


def test_a_unit_for_any_desktop_never_consults_them(tmp_path: Path) -> None:
    plan = _resolve(
        tmp_path, ["gpsd"], catalog=_catalog(_unit("gpsd")), known={"gpsd": None}, desktops=NONE
    )
    assert plan.apt_to_install == ("gpsd",)
    assert plan.desktops_read is None


def test_the_plan_carries_the_desktops_it_decided_against(tmp_path: Path) -> None:
    catalog, profiles = _station()
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None},
        desktops=XFCE,
    )
    assert plan.desktops_read == XFCE


# ---------------------------------------------------------------------------
# The dry run shows it
# ---------------------------------------------------------------------------


def test_the_dry_run_shows_the_deferral_and_the_desktops_read(tmp_path: Path) -> None:
    from hammunition.cli.main import render_plan

    catalog, profiles = _station()
    plan = _resolve(
        tmp_path,
        ["station"],
        catalog=catalog,
        profiles=profiles,
        known={"gpsd": None},
        desktops=frozenset({Desktop.xfce, Desktop.lxqt}),
    )
    text = "\n".join(render_plan(plan, [], euid=1000))
    assert "Will NOT happen" in text
    assert "no KDE Plasma session (it has: Xfce, LXQt)" in text
    assert "Desktops read from session files" in text
    assert "/usr/share/xsessions" in text


def test_the_dry_run_says_nothing_of_desktops_when_no_unit_asked(tmp_path: Path) -> None:
    from hammunition.cli.main import render_plan

    plan = _resolve(
        tmp_path, ["gpsd"], catalog=_catalog(_unit("gpsd")), known={"gpsd": None}, desktops=XFCE
    )
    assert "Desktops read" not in "\n".join(render_plan(plan, [], euid=1000))
