# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The campaign harness's evidence: what a report must carry to be rerun and
believed.

The overnight passes of 2026-09-04 filed 1,375 unit results and every one
said `installed+confirmed` or named a refusal -- and still could not answer
four questions without a shell on the VM: *what* confirmed each unit, which
snapshot and apt lists it ran against, whether a refusal was caused by the
pass's own earlier installs, and whether the tree that was synced was the
commit the header named. Each test here is one of those questions.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def campaign() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vm_campaign_evidence", REPO_ROOT / "scripts" / "vm_campaign.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vm_campaign_evidence"] = mod
    spec.loader.exec_module(mod)
    return mod


def _begin(*packages: str, apt: tuple[str, ...] = ()) -> str:
    return json.dumps(
        {
            "event": "transaction_begin",
            "version": 2,
            "timestamp": "2026-09-04T06:02:00+00:00",
            "target": {"id": "parrot"},
            "packages": list(packages),
            "apt_packages": list(apt),
            "deferred": [],
        }
    )


def _end(*checks: dict[str, object], verified: bool = True) -> str:
    return json.dumps(
        {
            "event": "transaction_end",
            "version": 2,
            "timestamp": "2026-09-04T06:02:19+00:00",
            "completed": 9,
            "verified": verified,
            "checks": list(checks),
        }
    )


def _pkg(name: str, version: str) -> dict[str, object]:
    return {
        "kind": "package",
        "subject": name,
        "confirmed": True,
        "detail": f"installed {version}",
    }


def _provenance(campaign: ModuleType, **overrides: object) -> object:
    fields: dict[str, object] = {
        "engine_commit": "b447ec6",
        "dirty_files": 0,
        "domain": "ParrotOS_Dev",
        "snapshot": "clean-baseline",
        "snapshot_created": "2026-08-26T05:37:34+00:00",
        "apt_lists": (
            ("deb.parrot.sh_parrot_dists_echo_InRelease", "Thu, 03 Sep 2026 14:23:55 UTC"),
        ),
        "prepared_at": "2026-09-04T05:58:00+00:00",
    }
    fields.update(overrides)
    return campaign.Provenance(**fields)


def test_classify_keeps_the_transaction_entries_the_unit_appended(campaign: ModuleType) -> None:
    """The remote session prints the engine's tail, then `__EXIT=`, then a
    `__LOG` marker followed by the transaction-log lines this unit added.
    Those lines are the evidence: `yaac` on Parrot was `installed+confirmed`
    on the strength of one check, `libjssc-java 2.8.0-4` -- a dependency,
    not YAAC -- and nothing in the report said so."""
    raw = "\n".join(
        [
            "Done. 9 command(s) completed and confirmed.",
            "__EXIT=0",
            "__LOG",
            _begin("yaac", apt=("libjssc-java",)),
            _end(_pkg("libjssc-java", "2.8.0-4")),
        ]
    )
    result = campaign.classify("yaac", raw, seconds=15.0, timeout=1800)
    assert result.exit_code == 0
    assert "__LOG" not in result.tail and "transaction_begin" not in result.tail
    assert [e["event"] for e in result.entries] == ["transaction_begin", "transaction_end"]
    assert result.evidence == "1 check: package libjssc-java installed 2.8.0-4"

    bare = campaign.classify(
        "x", "Done.\n__EXIT=0\n__LOG\n" + _begin("x") + "\n" + _end(), seconds=1, timeout=9
    )
    assert bare.evidence == "no effect checks"


def test_report_names_what_confirmed_each_unit_and_counts_the_unchecked(
    campaign: ModuleType,
) -> None:
    """`installed+confirmed` is the engine's exit 0, and exit 0 is granted
    to a run whose re-probe asked nothing (`checks: []`). The report must say
    per unit what was probed, and count the units confirmed by no check at
    all, because those are the blind spot -- not a failure, but not the
    evidence the word suggests either."""
    probed = campaign.classify(
        "yaac",
        "Done.\n__EXIT=0\n__LOG\n" + _begin("yaac") + "\n" + _end(_pkg("libjssc-java", "2.8.0-4")),
        seconds=15,
        timeout=9,
    )
    unchecked = campaign.classify(
        "sdr-notes",
        "Done.\n__EXIT=0\n__LOG\n" + _begin("sdr-notes") + "\n" + _end(),
        seconds=1,
        timeout=9,
    )
    report = campaign.render_report(
        target_line="T", provenance=_provenance(campaign), results=[probed, unchecked]
    )
    assert "| Name | Outcome | Confirmed by | Seconds |" in report
    assert (
        "| `yaac` | installed+confirmed | 1 check: package libjssc-java installed 2.8.0-4 | 15 |"
        in report
    )
    assert "| `sdr-notes` | installed+confirmed | no effect checks | 1 |" in report
    assert "## Confirmed by no effect check (1)" in report
    assert "`sdr-notes`" in report.split("## Confirmed by no effect check")[1]


def test_report_carries_what_a_rerun_needs_and_never_the_ssh_address(campaign: ModuleType) -> None:
    """Engine commit alone did not reproduce a pass: the tree synced to the
    guest is the working tree, not the commit; the snapshot the guest was
    reset to has a creation time the archive has moved past; and the apt
    lists it resolved against are the ones `prepare` fetched, dated by their
    InRelease. All three go in the header. The guest's `user@ip` goes
    nowhere -- a report is published, an address is not."""
    report = campaign.render_report(
        target_line="Parrot 7.3",
        provenance=_provenance(campaign, dirty_files=2),
        results=[],
    )
    assert "**Engine:** commit `b447ec6` (working tree dirty: 2 files not in that commit)" in report
    assert "**VM:** `ParrotOS_Dev` reset to snapshot `clean-baseline`" in report
    assert "2026-08-26T05:37:34+00:00" in report
    assert "deb.parrot.sh_parrot_dists_echo_InRelease" in report
    assert "Thu, 03 Sep 2026 14:23:55 UTC" in report
    assert "**Prepared:** 2026-09-04T05:58:00+00:00" in report

    unreset = campaign.render_report(
        target_line=campaign.TARGET_UNKNOWN,
        provenance=_provenance(
            campaign, domain=None, snapshot=None, snapshot_created=None, prepared_at=None
        ),
        results=[],
    )
    assert "**VM:** not reset by this campaign" in unreset
    assert "192.168" not in unreset and "@" not in unreset
    # Nothing was prepared, so the lists are whatever the guest held.
    assert "**Apt lists (InRelease dates after prepare):**" in report
    assert "**Apt lists (InRelease dates, as found on the guest):**" in unreset


def test_the_target_line_is_the_guests_os_release_without_the_cli_label(
    campaign: ModuleType,
) -> None:
    """`hammunition status` prints `Target: <describe()>`; every report to
    date carried that label twice (`**Target:** Target: Kali ...`). The
    probe's first line is stripped of the CLI's own prefix, and an empty
    probe still names the unknown rather than the address."""
    status = "Target: Kali GNU/Linux Rolling (ID=kali, version=2026.3, arch=x86_64)\n\nnothing\n"
    assert campaign.target_from_status(status) == (
        "Kali GNU/Linux Rolling (ID=kali, version=2026.3, arch=x86_64)"
    )
    assert campaign.target_from_status("") == campaign.TARGET_UNKNOWN
    assert campaign.target_from_status("\n") == campaign.TARGET_UNKNOWN


def test_a_refusal_naming_a_package_this_pass_installed_is_labelled_cumulative(
    campaign: ModuleType,
) -> None:
    """`wsjtx-improved` was refused on all six targets because `wsjtx`, run
    earlier in the same pass, had installed `wsjtx-data`. Filed as a plain
    plan-time refusal it read as the D-022 rule working; it was, and it also
    hid that the unit fails outright on Kali (#24). The harness knows what
    the pass installed before each unit, so a refusal naming one of those
    packages is labelled with the package and the unit that brought it."""
    # `wsjtx-data` is not in jtdx's transaction at all -- apt pulled it as
    # a dependency -- so the guest's dpkg delta (`__NEW_PACKAGES`) is the
    # only place the harness can learn the pass now holds it.
    jtdx = campaign.classify(
        "jtdx",
        "Done.\n__EXIT=0\n__LOG\n"
        + _begin("jtdx", apt=("jtdx",))
        + "\n"
        + _end(_pkg("jtdx", "2.2.159"))
        + "\n__NEW_PACKAGES\njtdx\nwsjtx-data\n",
        seconds=6,
        timeout=9,
    )
    assert jtdx.new_packages == ("jtdx", "wsjtx-data")
    improved = campaign.UnitResult(
        "wsjtx-improved",
        2,
        3.0,
        "  wsjtx-improved: its vendor .deb collides with installed distribution "
        "package(s): wsjtx-data\n    → remove them first",
    )
    absent = campaign.UnitResult("z8530-utils2", 2, 1.0, "z8530-utils2: not in the archive")
    results = [jtdx, improved, absent]
    assert campaign.cumulative_refusals(results) == {"wsjtx-improved": {"wsjtx-data": "jtdx"}}
    report = campaign.render_report(
        target_line="T", provenance=_provenance(campaign), results=results
    )
    assert (
        "| `wsjtx-improved` | refused (plan) — cumulative: names `wsjtx-data`, installed by `jtdx` "
        "earlier this pass |" in report
    )
    assert "| `z8530-utils2` | refused (plan) |" in report
    assert "1 of them cumulative" in report

    # `--reset-each` restores the guest before every unit: nothing
    # accumulates, so nothing may be labelled as if it had.
    isolated_pass = campaign.render_report(
        target_line="T", provenance=_provenance(campaign), results=results, accumulating=False
    )
    assert "| `wsjtx-improved` | refused (plan) |" in isolated_pass
    assert "cumulative" not in isolated_pass.split("| Name |")[1]


def test_an_isolated_rerun_is_reported_beside_the_cumulative_refusal(campaign: ModuleType) -> None:
    """A cumulative refusal is a fact about the pass, not the unit. When the
    campaign knows a snapshot it re-runs the unit alone on it, and the
    report shows both verdicts side by side -- the one an operator building
    up a machine would see and the one a clean machine gives."""
    wsjtx = campaign.classify(
        "wsjtx",
        "Done.\n__EXIT=0\n__LOG\n" + _begin("wsjtx", apt=("wsjtx-data",)) + "\n" + _end(),
        seconds=400,
        timeout=9,
    )
    improved = campaign.UnitResult("wsjtx-improved", 2, 3.0, "collides with ... wsjtx-data")
    alone = campaign.UnitResult(
        "wsjtx-improved",
        1,
        40.0,
        "E: Unable to correct problems: libboost-log1.83.0 but it is not installable",
    )
    report = campaign.render_report(
        target_line="T",
        provenance=_provenance(campaign),
        results=[wsjtx, improved],
        isolated={"wsjtx-improved": alone},
    )
    assert "alone on `clean-baseline`: FAILED (40 s)" in report
    assert "## Re-run alone on `clean-baseline`" in report
    assert "libboost-log1.83.0" in report.split("## Re-run alone")[1]
    assert "## Failures" not in report


def test_evidence_sidecar_is_the_complete_machine_readable_record(
    campaign: ModuleType, tmp_path: Path
) -> None:
    """The markdown is the summary; the sidecar is the record -- provenance,
    then one line per unit with its exit, tail and every transaction entry,
    then the isolated re-runs. It is rewritten with the report so a campaign
    that dies keeps what it measured, and it must round-trip."""
    yaac = campaign.classify(
        "yaac",
        "Done.\n__EXIT=0\n__LOG\n" + _begin("yaac") + "\n" + _end(_pkg("libjssc-java", "1")),
        seconds=2,
        timeout=9,
    )
    refused = campaign.UnitResult("gap", 2, 1.0, "no block")
    out = tmp_path / "campaign.md"
    campaign.write_evidence(
        campaign.evidence_path(out),
        provenance=_provenance(campaign),
        results=[yaac, refused],
        isolated={"gap": campaign.UnitResult("gap", 2, 1.0, "no block")},
    )
    lines = [
        json.loads(ln) for ln in (tmp_path / "campaign.evidence.jsonl").read_text().splitlines()
    ]
    assert lines[0]["record"] == "provenance" and lines[0]["snapshot"] == "clean-baseline"
    assert lines[1]["record"] == "unit" and lines[1]["unit"] == "yaac"
    assert [e["event"] for e in lines[1]["entries"]] == ["transaction_begin", "transaction_end"]
    assert lines[2]["unit"] == "gap" and lines[2]["exit_code"] == 2
    assert lines[3]["record"] == "isolated" and lines[3]["unit"] == "gap"


def test_remote_command_captures_only_the_lines_this_unit_appended(
    tmp_path: Path, campaign: ModuleType
) -> None:
    """The delta is what attributes log entries to a unit, and it has to be
    measured against the lines present *before* the engine ran: an
    off-by-one here files unit 12's checks under unit 13 and every evidence
    column is wrong by one row. Exercised against a fake engine that appends
    to a real file, through the same `bash -c` the guest runs."""
    home = tmp_path
    engine = home / "hammunition" / ".venv" / "bin" / "hammunition"
    engine.parent.mkdir(parents=True)
    log = home / ".local" / "state" / "hammunition" / "transactions.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text('{"event": "transaction_end", "stale": true}\n')
    # A stand-in dpkg-query reads the fake machine's package list; the fake
    # engine adds two packages to it, one of which was already there. That
    # delta is how the harness learns a unit brought `wsjtx-data` when the
    # unit's own transaction never named it (apt pulled it for jtdx).
    fakebin = home / "fakebin"
    fakebin.mkdir()
    pkgs = home / "installed-packages"
    pkgs.write_text("libc6\njtdx\n")
    dpkg_query = fakebin / "dpkg-query"
    dpkg_query.write_text(f"#!/bin/sh\ncat {pkgs}\n")
    dpkg_query.chmod(dpkg_query.stat().st_mode | stat.S_IXUSR)
    engine.write_text(
        "#!/bin/sh\n"
        f'echo \'{{"event": "transaction_begin", "packages": ["\'$2\'"]}}\' >> {log}\n'
        f'echo \'{{"event": "transaction_end", "checks": []}}\' >> {log}\n'
        f"printf 'jtdx\\nwsjtx-data\\n' >> {pkgs}\n"
        "echo Done.\n"
    )
    engine.chmod(engine.stat().st_mode | stat.S_IXUSR)
    proc = subprocess.run(
        ["bash", "-c", campaign.remote_command("yaac", 60)],
        cwd=home,
        env={**os.environ, "HOME": str(home), "PATH": f"{fakebin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    result = campaign.classify("yaac", proc.stdout, seconds=1, timeout=60)
    assert result.exit_code == 0, proc.stdout + proc.stderr
    assert [e["event"] for e in result.entries] == ["transaction_begin", "transaction_end"]
    assert result.entries[0]["packages"] == ["yaac"]
    assert not any(e.get("stale") for e in result.entries)
    assert result.new_packages == ("wsjtx-data",)
    assert "__NEW_PACKAGES" not in result.tail and "wsjtx-data" not in result.tail
