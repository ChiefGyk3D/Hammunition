# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The HydraSDR RFOne and Fobos SDR entries, built without owning either.

Hardware without hardware: every identifier here came out of the vendors' own
published files and is cited by commit, so the claims worth testing are the
ones that stop the entries drifting into something the evidence does not say.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from hammunition.manifest.load import load_catalog, load_hardware
from hammunition.manifest.schema import GitInstall

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(REPO_ROOT / "catalog" / "packages")
_CLASSES, DEVICES = load_hardware(REPO_ROOT / "catalog" / "hardware")

UNITS = (
    "hydrasdr-host",
    "soapysdr-module-hydrasdr",
    "libfobos",
    "libfobos-sdr-agile",
    "soapysdr-module-fobos",
)
COMMIT_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/blob/[0-9a-f]{40}/\S+")


def _git_blocks(name: str) -> list[GitInstall]:
    return [b.install for b in CATALOG[name].install if isinstance(b.install, GitInstall)]


def _citations() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_rule_citations", REPO_ROOT / "scripts" / "check_rule_citations.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_both_devices_are_not_owned_and_say_so() -> None:
    """D-027: nobody here ran either board, and the entry must not imply it."""
    for name in ("hydrasdr-rfone", "fobos-sdr"):
        device = DEVICES[name]
        assert device.maintainer_verified is None, name
        assert device.gap_closure == "unverified_by_maintainer", name
        assert device.identification_gap and "Not owned" in device.identification_gap, name


def test_every_identifier_is_cited_by_commit_from_upstream() -> None:
    """A URL to a 40-hex commit can be re-read; 'upstream's rules file' cannot."""
    for name in ("hydrasdr-rfone", "fobos-sdr"):
        device = DEVICES[name]
        ids = list(device.usb_ids) + [f.dfu_usb_id for f in device.firmware if f.dfu_usb_id]
        assert ids, name
        for usb in ids:
            assert COMMIT_URL.search(usb.evidence), f"{name} {usb}: no commit-pinned upstream URL"


def test_the_cited_commits_are_the_commits_the_manifests_pin() -> None:
    """A citation that names another commit than the one built reads a different file.

    The RFOne's rules and registry are cited at hydrasdr-host's v1.1.1 commit;
    the Fobos files at libfobos's pinned head and libfobos-sdr-agile's tag.
    """
    pinned = {
        "hydrasdr/hydrasdr-host": _git_blocks("hydrasdr-host")[0].commit,
        "rigexpert/libfobos": _git_blocks("libfobos")[0].ref,
        "rigexpert/libfobos-sdr-agile": _git_blocks("libfobos-sdr-agile")[0].commit,
    }
    seen: set[str] = set()
    for name in ("hydrasdr-rfone", "fobos-sdr"):
        device = DEVICES[name]
        ids = list(device.usb_ids) + [f.dfu_usb_id for f in device.firmware if f.dfu_usb_id]
        for usb in ids:
            for repo, commit in re.findall(
                r"https://github\.com/([\w.-]+/[\w.-]+)/blob/([0-9a-f]{40})/", usb.evidence
            ):
                assert pinned[repo] == commit, f"{name} {usb}: cites {repo}@{commit[:7]}"
                seen.add(repo)
    assert seen == set(pinned), f"a pinned repository is cited nowhere: {set(pinned) - seen}"


def test_the_pair_airspy_shares_is_recorded_and_not_turned_into_a_rule() -> None:
    """1d50:60a1 is an RFOne on legacy firmware and an Airspy R2/Mini.

    Carried as a usb_id it would generate a permission rule naming an Airspy an
    RFOne (and it cannot carry an `ambiguity` without a product string nobody
    has read), so it lives in rejected_ids, which cannot generate a rule.
    """
    rfone = DEVICES["hydrasdr-rfone"]
    assert "1d50:60a1" not in {str(i) for i in rfone.usb_ids}
    assert "1d50:60a1" in {str(r) for r in rfone.rejected_ids}
    assert "1d50:60a1" in {str(i) for i in DEVICES["airspy"].usb_ids}
    assert [str(i) for i in rfone.usb_ids] == ["38af:0001"]


def test_the_rfone_dfu_identifier_is_marked_shared_with_the_hackrf() -> None:
    dfu = next(f.dfu_usb_id for f in DEVICES["hydrasdr-rfone"].firmware if f.dfu_usb_id)
    assert str(dfu) == "1fc9:000c"
    assert dfu.ambiguity is not None
    assert "hackrf-one" in dfu.ambiguity.also_used_by
    hackrf = next(f.dfu_usb_id for f in DEVICES["hackrf-one"].firmware if f.dfu_usb_id)
    assert str(hackrf) == "1fc9:000c"


def test_the_fobos_firmware_families_are_told_apart_in_prose_not_by_a_second_id() -> None:
    """Both firmware families present 16d0:132e; only bcdDevice differs."""
    fobos = DEVICES["fobos-sdr"]
    assert [str(i) for i in fobos.usb_ids] == ["16d0:132e"]
    note = " ".join(f.note for f in fobos.firmware)
    assert "bcdDevice" in note and "0x0101" in note and "0x0000" in note


def test_no_unit_writes_a_udev_rule_outside_the_hardware_entry() -> None:
    """libfobos-sdr-agile's CMake writes /etc/udev/rules.d as root; it is patched out.

    The diff has to keep upstream's CRLF line endings or GNU patch 2.8 refuses
    it ("different line endings"), which is how the first version failed.
    """
    (block,) = _git_blocks("libfobos-sdr-agile")
    (patch,) = block.patches
    assert patch.unified_diff is not None
    assert "/etc/udev/rules.d" in patch.unified_diff
    assert '-        DESTINATION "/etc/udev/rules.d"\r\n' in patch.unified_diff
    (fobos,) = _git_blocks("libfobos")
    assert any("CMAKE_INSTALL_UDEVRULESDIR=/" in a for a in fobos.configure_args)
    (host,) = [b for b in _git_blocks("hydrasdr-host")]
    assert not any("UDEV" in a for a in host.configure_args)


@pytest.mark.skipif(shutil.which("patch") is None, reason="patch(1) not installed")
def test_the_agile_diff_applies_to_a_crlf_file(tmp_path: Path) -> None:
    """The exact bytes the engine writes, against a file shaped like upstream's."""
    (block,) = _git_blocks("libfobos-sdr-agile")
    diff = block.patches[0].unified_diff
    assert diff is not None
    lines = [
        "#" * 72,
        "# Install udev rules",
        "#" * 72,
        'if (CMAKE_SYSTEM_NAME STREQUAL "Linux")',
        "    install(",
        "        FILES fobos-sdr.rules",
        '        DESTINATION "/etc/udev/rules.d"',
        '        COMPONENT "udev")',
        "endif()",
        "#" * 72,
        "",
        "#" * 72,
    ]
    before = [*(["x"] * 100), *lines, *(["y"] * 20)]
    target = tmp_path / "CMakeLists.txt"
    target.write_bytes(("\r\n".join(before) + "\r\n").encode())
    (tmp_path / "p.diff").write_bytes(diff.encode())
    result = subprocess.run(
        ["patch", "-p1", "-i", "p.diff"], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"/etc/udev" not in target.read_bytes().replace(b"absolute /etc/udev path", b"")


def test_tagged_pins_carry_their_commit_and_sha_pins_their_review() -> None:
    """D-024: a tag names the commit it must resolve to; a bare SHA is reviewed."""
    for name in UNITS:
        for block in _git_blocks(name):
            if len(block.ref) == 40:
                assert block.pin_review is not None, name
                assert block.pin_review.basis == "own_choice", name
            else:
                assert block.commit is not None and len(block.commit) == 40, name
                assert block.pin_review is None, name


def test_distribution_packaged_revisions_match_the_distributions() -> None:
    """The source build is the revision Debian and Kali package (D-024's main rule)."""
    assert _git_blocks("hydrasdr-host")[0].ref == "v1.1.1"
    assert _git_blocks("soapysdr-module-hydrasdr")[0].ref == "v1.0.1"
    assert CATALOG["hydrasdr-host"].version == "1.1.1"
    kali = [b for b in CATALOG["hydrasdr-host"].install if b.when.distro == ["kali"]]
    assert kali and kali[0].install.method == "apt"


def test_every_source_build_installs_where_the_loader_can_find_it() -> None:
    """Nothing runs ldconfig after a build into /usr/local, so each build embeds the path.

    Without it hydrasdr_info, fobos_devinfo and every Soapy module failed with
    'cannot open shared object file' on debian:13 until it was set.
    """
    for name in UNITS:
        for block in _git_blocks(name):
            assert "-DCMAKE_INSTALL_RPATH=/usr/local/lib" in block.configure_args, name


def test_the_soapy_hydrasdr_module_installs_once_under_the_prefix() -> None:
    """Left alone its CMake also wrote /usr/lib/<multiarch>/SoapySDR (dpkg's directory)."""
    (block,) = _git_blocks("soapysdr-module-hydrasdr")
    assert "-DSOAPY_SDR_MODULE_DIR=/usr/local/lib/SoapySDR/modules0.8" in block.configure_args


def test_the_soapy_fobos_module_needs_both_libraries() -> None:
    manifest = CATALOG["soapysdr-module-fobos"]
    assert set(manifest.depends) == {"libfobos", "libfobos-sdr-agile"}
    assert set(manifest.after) == {"libfobos", "libfobos-sdr-agile"}


def test_the_device_packages_resolve_to_these_units() -> None:
    assert DEVICES["hydrasdr-rfone"].packages == ["hydrasdr-host", "soapysdr-module-hydrasdr"]
    assert DEVICES["fobos-sdr"].packages == ["libfobos", "soapysdr-module-fobos"]


def test_a_rules_file_cited_by_url_is_not_read_as_a_distribution_citation() -> None:
    """check_rule_citations must not demand the sweep ship an upstream's own file.

    Falsifiable both ways: the URL's file name is ignored, and the same name
    cited by path, the way every distribution citation is written, is still read.
    """
    cited = _citations().cited_files
    upstream = (
        "see https://github.com/hydrasdr/hydrasdr-host/blob/" + "d" * 40 + "/x/51-hydrasdr.rules"
    )
    assert cited(upstream) == set()
    assert cited("Debian 13 /lib/udev/rules.d/60-libhackrf0.rules") == {"60-libhackrf0.rules"}
    assert cited(upstream + " and /lib/udev/rules.d/60-libairspy0.rules") == {"60-libairspy0.rules"}
