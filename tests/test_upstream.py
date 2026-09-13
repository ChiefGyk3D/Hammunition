# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""`update --upstream`: the catalog's pin against what upstream publishes.
D-053, second half. Every network call is injected, so these run offline;
a probe that cannot be answered is a row, never a crash."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.cli.main import build_parser  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import ManifestError, PackageManifest  # noqa: E402
from hammunition.upstream import (  # noqa: E402
    CURRENT,
    DIFFERS,
    NEWER_UPSTREAM,
    NOT_UPSTREAM,
    UNANSWERED,
    compare,
    git_url_of,
    github_repo_of,
    highest_tag,
    parse_ls_remote,
    probe_upstream,
    render,
)

DOCS = {
    "what_it_does": "Stands in for a unit whose upstream is asked.",
    "why_you_want_it": "To measure the comparison without a network.",
    "upstream_url": "https://example.invalid/",
}


def _manifest(
    version: str, probe: dict[str, Any], install: dict[str, Any] | None = None
) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "thing",
            "version": version,
            "summary": "Fixture",
            "categories": ["sdr"],
            "install": [
                {
                    "install": install
                    or {
                        "method": "git",
                        "repo": "https://github.com/someone/thing",
                        "ref": "v1.0",
                        "build_system": "cmake",
                    }
                }
            ],
            "binaries": [{"produced": "thing", "install_as": "thing"}],
            "update": {"probe": probe, "strategy": "rebuild"},
            "documentation": DOCS,
        }
    )


def _no_network(url: str) -> str:
    raise AssertionError(f"unexpected network call: {url}")


def _no_git(url: str) -> list[str]:
    raise AssertionError(f"unexpected ls-remote: {url}")


# --- comparison ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("catalog", "upstream", "expected"),
    [
        ("4.6", "v4.6", CURRENT),
        ("4.6", "4.6", CURRENT),
        ("4.6", "v4.7", NEWER_UPSTREAM),
        ("4.6", "v4.5", DIFFERS),  # older upstream: differs, never called newer
        ("1.0-beta230(03-Sep-2026)", "1.0-beta230(03-Sep-2026)", CURRENT),
        ("0+git20181219", "nightly", DIFFERS),
    ],
)
def test_compare_orders_numbers_and_refuses_to_guess_otherwise(
    catalog: str, upstream: str, expected: str
) -> None:
    assert compare(catalog, upstream) == expected


def test_highest_tag_ignores_tags_without_numbers() -> None:
    assert highest_tag(["v4.6", "v4.10", "latest", "v4.9"]) == "v4.10"
    assert highest_tag(["latest", "nightly"]) is None


def test_parse_ls_remote_strips_refs_and_peeled_markers() -> None:
    out = "abc\trefs/tags/v1.0\nabd\trefs/tags/v1.0^{}\nabe\trefs/heads/main\n"
    assert parse_ls_remote(out) == ["v1.0", "v1.0"]


# --- deriving the repository -----------------------------------------------------


def test_repo_comes_from_the_probe_else_the_git_block_else_the_source_url() -> None:
    assert github_repo_of(_manifest("1", {"method": "github_tags", "repo": "a/b"})) == "a/b"
    assert github_repo_of(_manifest("1", {"method": "github_tags"})) == "someone/thing"
    src = {
        "method": "source",
        "source": {"url": "https://github.com/o/n/archive/refs/tags/v1.tar.gz", "sha256": "a" * 64},
        "build_system": "make",
    }
    assert github_repo_of(_manifest("1", {"method": "github_tags"}, install=src)) == "o/n"
    assert (
        git_url_of(_manifest("1", {"method": "github_tags"}, install=src))
        == "https://github.com/o/n"
    )


# --- probes --------------------------------------------------------------------


def test_github_release_reads_tag_name_and_compares() -> None:
    def http(url: str) -> str:
        assert url == "https://api.github.com/repos/jvde-github/AIS-catcher/releases/latest"
        return json.dumps({"tag_name": "v0.71"})

    row = probe_upstream(
        _manifest("0.70", {"method": "github_release", "repo": "jvde-github/AIS-catcher"}),
        http=http,
        ls_remote=_no_git,
    )
    assert (row.upstream, row.state) == ("v0.71", NEWER_UPSTREAM)


def test_github_tags_uses_ls_remote_on_the_git_block_repo_and_takes_the_highest() -> None:
    def ls_remote(url: str) -> list[str]:
        assert url == "https://github.com/someone/thing"
        return ["v0.9", "v1.0", "junk"]

    row = probe_upstream(
        _manifest("1.0", {"method": "github_tags"}), http=_no_network, ls_remote=ls_remote
    )
    assert (row.upstream, row.state) == ("v1.0", CURRENT)
    assert "3 tag(s)" in row.detail


def test_pypi_uses_the_unit_name_unless_the_probe_names_a_project() -> None:
    asked: list[str] = []

    def http(url: str) -> str:
        asked.append(url)
        return json.dumps({"info": {"version": "26.9.1"}})

    row = probe_upstream(_manifest("26.8.28", {"method": "pypi"}), http=http, ls_remote=_no_git)
    assert asked == ["https://pypi.org/pypi/thing/json"]
    assert row.state == NEWER_UPSTREAM
    probe_upstream(
        _manifest("26.8.28", {"method": "pypi", "package": "other-name"}),
        http=http,
        ls_remote=_no_git,
    )
    assert asked[-1] == "https://pypi.org/pypi/other-name/json"


def test_label_file_is_compared_verbatim_and_fetched_once() -> None:
    calls = 0

    def http(url: str) -> str:
        nonlocal calls
        calls += 1
        return "1.0-beta231(10-Sep-2026)\n"

    row = probe_upstream(
        _manifest(
            "1.0-beta230(03-Sep-2026)", {"method": "label_file", "url": "https://x.invalid/l.txt"}
        ),
        http=http,
        ls_remote=_no_git,
    )
    assert calls == 1
    assert row.state == DIFFERS  # a label is not a number line; verbatim only
    assert row.upstream == "1.0-beta231(10-Sep-2026)"


def test_a_failing_fetch_is_an_unanswered_row_not_a_crash() -> None:
    def http(url: str) -> str:
        raise TimeoutError("timed out")

    row = probe_upstream(
        _manifest("0.70", {"method": "github_release", "repo": "a/b"}), http=http, ls_remote=_no_git
    )
    assert row.state == UNANSWERED
    assert "TimeoutError" in row.detail


def test_apt_and_binary_version_probes_are_not_upstream_questions() -> None:
    row = probe_upstream(
        _manifest("1", {"method": "apt_policy"}), http=_no_network, ls_remote=_no_git
    )
    assert row.state == NOT_UPSTREAM
    row = probe_upstream(
        _manifest(
            "1", {"method": "binary_version", "command": "thing --version", "pattern": "([0-9.]+)"}
        ),
        http=_no_network,
        ls_remote=_no_git,
    )
    assert row.state == NOT_UPSTREAM


def test_render_counts_and_tells_the_maintainer_what_a_newer_upstream_means() -> None:
    rows = [
        probe_upstream(
            _manifest("0.70", {"method": "github_release", "repo": "a/b"}),
            http=lambda _u: json.dumps({"tag_name": "v0.71"}),
            ls_remote=_no_git,
        )
    ]
    text = render(rows)
    assert "1 with a newer upstream" in text
    assert "re-pin the manifest" in text
    assert "nothing was downloaded or written" in text


# --- schema and CLI ---------------------------------------------------------------


def test_package_is_only_for_pypi_probes() -> None:
    from pydantic import ValidationError

    with pytest.raises((ValidationError, ManifestError), match="package"):
        _manifest("1", {"method": "github_tags", "package": "x"})


def test_update_upstream_is_a_flag_and_every_catalog_probe_has_a_source() -> None:
    args = build_parser().parse_args(["update", "--upstream"])
    assert args.upstream is True
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    for manifest in catalog.values():
        method = manifest.update.probe.method
        if method == "github_release":
            assert github_repo_of(manifest), f"{manifest.name}: github_release with no repo"
        elif method == "github_tags":
            assert git_url_of(manifest), f"{manifest.name}: github_tags with no repository"
