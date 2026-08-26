"""Manifest schema tests.

Two halves:

* **Shape tests** — each of the seven shapes from the real inventory must be
  expressible, and must resolve to the right thing.
* **Rejection tests** — the schema must make certain mistakes *impossible*, not
  merely discouraged. A schema that accepts an unverified download is not
  enforcing D-004, it is documenting it.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import CatalogError, load_catalog  # noqa: E402
from hammunition.manifest.schema import (  # noqa: E402
    ManifestError,
    PackageManifest,
    Status,
)

CATALOG = REPO_ROOT / "catalog" / "packages"


@pytest.fixture(scope="module")
def catalog() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG)


def _minimal(**overrides: object) -> dict[str, Any]:
    base = {
        "name": "example",
        "version": "1.0",
        "summary": "An example package",
        "categories": ["digital-modes"],
        "install": [{"install": {"method": "apt", "packages": ["example"]}}],
        "update": {"probe": {"method": "apt_policy"}},
        "documentation": {
            "what_it_does": "Does an example thing for the purposes of testing.",
            "why_you_want_it": "Because the test suite requires a valid manifest.",
            "upstream_url": "https://example.invalid/",
        },
    }
    base.update(overrides)
    return base


# ===========================================================================
# The whole catalog loads
# ===========================================================================


def test_catalog_loads(catalog) -> None:
    assert len(catalog) == 9


def test_every_manifest_has_documentation(catalog) -> None:
    """CLAUDE.md: an undocumented package cannot ship."""
    for name, m in catalog.items():
        assert m.documentation.what_it_does, name
        assert m.documentation.why_you_want_it, name
        assert m.documentation.upstream_url, name


def test_every_remote_artifact_is_verified(catalog) -> None:
    """D-004: no unverified downloads anywhere in the catalog."""
    for name, m in catalog.items():
        for block in m.install:
            inst = block.install
            artifact = getattr(inst, "source", None) or getattr(inst, "artifact", None)
            if artifact is not None:
                assert len(artifact.sha256) == 64, f"{name} has an unverified artifact"


# ===========================================================================
# Shape 1 — install METHOD varies by distro, not just its argument
# ===========================================================================


def test_shape1_js8call_method_varies_by_distro(catalog) -> None:
    js8 = catalog["js8call"]

    mint = js8.resolve("linuxmint", "22.3", "x86_64")
    other = js8.resolve("debian", "13", "x86_64")

    assert mint is not None and other is not None
    assert mint.install.method == "apt"
    assert mint.install.packages == ["js8call"]
    assert other.install.method == "source"
    assert other.install.build_system == "cmake"


def test_shape1_selector_precision(catalog) -> None:
    """Mint 22.4 must NOT get the Qt-6.4 workaround."""
    js8 = catalog["js8call"]
    assert js8.resolve("linuxmint", "22.4", "x86_64").install.method == "source"


# ===========================================================================
# Shape 2 — provides + conflicts_with_repo_package
# ===========================================================================


def test_shape2_fldigi_provides_flarq(catalog) -> None:
    fldigi = catalog["fldigi"]
    assert "flarq" in fldigi.provides
    assert {b.install_as for b in fldigi.binaries} == {"fldigi", "flarq"}


def test_shape2_fldigi_declares_repo_conflict(catalog) -> None:
    """The purge is destructive, so it must be declared, not implicit."""
    assert catalog["fldigi"].conflicts_with_repo_package == ["fldigi"]


def test_provides_may_not_list_self() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(_minimal(provides=["example"]))


# ===========================================================================
# Shape 3 — the wsjtx binary collision
# ===========================================================================


def test_shape3_binary_collision_is_declared_away(catalog) -> None:
    """Both builds emit `wsjtx`; install_as gives them distinct final names, so
    AHRL's rename dance is unnecessary rather than merely automated."""
    a, b = catalog["wsjtx"], catalog["wsjtx-improved"]

    assert a.binaries[0].produced == b.binaries[0].produced == "wsjtx"
    assert a.binaries[0].install_as == "wsjtx"
    assert b.binaries[0].install_as == "wsjtx-improved"
    assert a.binaries[0].install_as != b.binaries[0].install_as


def test_shape3_ordering_is_declared(catalog) -> None:
    assert catalog["wsjtx-improved"].after == ["wsjtx"]


def test_shape3_only_one_is_the_default(catalog) -> None:
    assert catalog["wsjtx"].recommended_default is True
    assert catalog["wsjtx-improved"].recommended_default is False


def test_duplicate_install_as_is_rejected() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                binaries=[
                    {"produced": "a", "install_as": "same"},
                    {"produced": "b", "install_as": "same"},
                ]
            )
        )


# ===========================================================================
# Shape 4 — per-architecture project file
# ===========================================================================


def test_shape4_mshv_project_file_per_arch(catalog) -> None:
    mshv = catalog["mshv"]
    arm = mshv.resolve("debian", "13", "aarch64")
    x86 = mshv.resolve("debian", "13", "x86_64")

    assert arm.install.project_file == "MSHV_ARM_PI.pro"
    assert x86.install.project_file == "MSHV_x86_64.pro"
    # Same archive, same hash — only the project file differs.
    assert arm.install.source.sha256 == x86.install.source.sha256


def test_shape4_unsupported_arch_resolves_to_none(catalog) -> None:
    """Honest gaps, not shims. CLAUDE.md capability matrix."""
    assert catalog["mshv"].resolve("debian", "13", "armv7l") is None


# ===========================================================================
# Shape 5 — retired, with a verdict we own
# ===========================================================================


def test_shape5_noaa_apt_is_retired_with_provenance(catalog) -> None:
    n = catalog["noaa-apt"]
    assert n.status is Status.retired
    assert n.retire_reason.value == "world_changed"
    assert n.status_date == date(2025, 11, 9)
    assert n.status_verdict.value == "tested"  # D-005: never inherit a verdict
    assert n.superseded_by == "satdump"


def test_shape5_retired_stays_in_the_catalog(catalog) -> None:
    """PARITY-POLICY: users who go looking must find an explanation, not silence."""
    assert "noaa-apt" in catalog
    assert catalog["noaa-apt"].documentation.why_you_want_it


@pytest.mark.parametrize("missing", ["status_reason", "status_date", "status_verdict"])
def test_non_supported_status_requires_provenance(missing: str) -> None:
    fields = {
        "status": "retired",
        "retire_reason": "world_changed",
        "status_reason": "The signal source no longer exists.",
        "status_date": "2025-11-09",
        "status_verdict": "tested",
    }
    fields.pop(missing)
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(_minimal(**fields))


def test_retired_requires_a_reason_code() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                status="retired",
                status_reason="Because.",
                status_date="2025-11-09",
                status_verdict="tested",
            )
        )


# ===========================================================================
# Shape 6 — the remote script is unrepresentable
# ===========================================================================


def test_shape6_ais_catcher_uses_a_pinned_ref(catalog) -> None:
    block = catalog["ais-catcher"].install[0]
    assert block.install.method == "git"
    assert block.install.ref == "v0.70"
    assert block.build_depends, "dependencies must be declared, not discovered"


def test_shape6_no_script_method_exists() -> None:
    """There is no way to say 'pipe this URL into bash'."""
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                install=[{"install": {"method": "script", "url": "https://example.invalid/i.sh"}}]
            )
        )


def test_moving_git_refs_are_rejected() -> None:
    for ref in ("master", "main", "HEAD", "develop"):
        with pytest.raises((ValidationError, ManifestError)):
            PackageManifest.model_validate(
                _minimal(
                    install=[
                        {
                            "install": {
                                "method": "git",
                                "repo": "https://example.invalid/x",
                                "ref": ref,
                                "build_system": "cmake",
                            }
                        }
                    ]
                )
            )


def test_source_without_sha256_is_rejected() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                install=[
                    {
                        "install": {
                            "method": "source",
                            "source": {"url": "https://example.invalid/x.tar.gz"},
                            "build_system": "cmake",
                        }
                    }
                ]
            )
        )


def test_malformed_sha256_is_rejected() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                install=[
                    {
                        "install": {
                            "method": "source",
                            "source": {
                                "url": "https://example.invalid/x.tar.gz",
                                "sha256": "deadbeef",
                            },
                            "build_system": "cmake",
                        }
                    }
                ]
            )
        )


# ===========================================================================
# Shape 7 — configurable service endpoint
# ===========================================================================


def test_shape7_backend_is_a_field_not_a_launcher_constant(catalog) -> None:
    hc = catalog["hamclock-next"]
    endpoint = next(e for e in hc.service_endpoints if e.name == "backend")

    assert endpoint.user_configurable
    assert endpoint.default_url == "https://ohb.works"
    # The dead host must not appear anywhere in the manifest.
    assert "hamclock.com" not in hc.launchers[0].exec


def test_shape7_launcher_references_endpoint_symbolically(catalog) -> None:
    exec_line = catalog["hamclock-next"].launchers[0].exec
    assert "{endpoint:backend}" in exec_line


def test_launcher_may_not_reference_an_undeclared_endpoint() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(launchers=[{"name": "x", "exec": "x --backend {endpoint:nope}"}])
        )


# ===========================================================================
# Cross-cutting rules
# ===========================================================================


def test_unconditional_block_may_not_shadow_later_blocks() -> None:
    """First-match-wins means a default block placed early silently wins."""
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                install=[
                    {"install": {"method": "apt", "packages": ["a"]}},
                    {
                        "when": {"arch": ["aarch64"]},
                        "install": {"method": "apt", "packages": ["b"]},
                    },
                ]
            )
        )


def test_irreversible_modification_must_explain_itself() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                system_modifications=[
                    {
                        "kind": "file_shadow",
                        "description": "Replaces distro librtlsdr",
                        "detail": "rm -fr /usr/lib/librtlsdr*",
                        "reversible": False,
                    }
                ]
            )
        )


def test_third_party_repo_requires_a_pinned_key() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(
            _minimal(
                apt_repos=[
                    {
                        "name": "example",
                        "uri": "https://ppa.invalid/",
                        "suites": ["stable"],
                        "components": ["main"],
                        "key_url": "https://ppa.invalid/key.asc",
                        "rationale": "Needed for the thing.",
                    }
                ]
            )
        )


def test_categories_are_a_non_empty_list() -> None:
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(_minimal(categories=[]))


def test_unquoted_two_component_version_is_rejected() -> None:
    """YAML parses `version: 1.5` as a float, and `0.70` silently becomes 0.7.
    Fail loudly rather than shipping a wrong version string (D-016)."""
    data = yaml.safe_load("version: 0.70\n")
    assert data["version"] == 0.7, "YAML float coercion (this is the trap)"
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(_minimal(version=0.7))


def test_extra_fields_are_rejected() -> None:
    """Typos in field names must fail, not be silently ignored."""
    with pytest.raises((ValidationError, ManifestError)):
        PackageManifest.model_validate(_minimal(catagories=["typo"]))


# ===========================================================================
# Loader behaviour
# ===========================================================================


def test_loader_reports_all_failures_not_just_the_first(tmp_path: Path) -> None:
    """D-016: resolve everything, then report together."""
    (tmp_path / "a.yaml").write_text("name: 'A'\n")
    (tmp_path / "b.yaml").write_text("name: 'B'\n")
    with pytest.raises(CatalogError) as exc:
        load_catalog(tmp_path)
    assert len(exc.value.failures) == 2


def test_toolkit_risk_register_is_queryable(catalog) -> None:
    """D-015: 'what breaks when Debian drops Qt5?' must be answerable from data."""
    at_risk = {
        name for name, m in catalog.items() if any(t.framework == "qt5" for t in m.toolkit_risk)
    }
    assert {"wsjtx", "wsjtx-improved", "mshv"} <= at_risk
    for name in at_risk:
        for risk in catalog[name].toolkit_risk:
            assert risk.checked, f"{name}: register entry must record when it was checked"


def test_toolkit_register_is_multi_framework(catalog) -> None:
    """D-015 is generic, not Qt5-specific. The register must prove that."""
    frameworks = {t.framework for m in catalog.values() for t in m.toolkit_risk}
    assert len(frameworks) > 1, f"register only covers {frameworks}"
    assert "gtk2" in frameworks


def test_no_path_is_distinct_from_not_yet_ported(catalog) -> None:
    """The distinction that carries the value: glfer's GTK2 has nowhere to go,
    which is a different problem from a port that simply has not happened."""
    glfer = catalog["glfer"]
    gtk2 = next(t for t in glfer.toolkit_risk if t.framework == "gtk2")
    assert gtk2.upstream_port_status == "no_path"

    wsjtx = catalog["wsjtx"]
    qt5 = next(t for t in wsjtx.toolkit_risk if t.framework == "qt5")
    assert qt5.upstream_port_status == "in_progress"
    assert gtk2.upstream_port_status != qt5.upstream_port_status


def test_compiler_flags_are_recorded_not_rediscovered(catalog) -> None:
    """PARITY-POLICY 'CARRY with attention': the flags are catalog data."""
    flags = catalog["glfer"].install[0].install.compiler_flags
    assert "-Wno-incompatible-pointer-types" in flags
    assert len(flags) == 3
