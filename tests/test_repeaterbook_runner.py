# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The runner the ``repeaterbook-client`` unit's python executes (D-081).

It is tested against a **fake** ``repeaterbook`` client, ``pycountry`` and
``anyio`` written into a temporary directory and put first on ``sys.path``:
the real client (and RepeaterBook) are never touched. What the fake mirrors is
the surface of the 0.13.0 client the runner calls, read from its source on
2026-10-04; whether the real client behaves so is what the first live run
settles.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from hammunition import repeaterbook_runner as runner_module

TOKEN = "rbuapp_synthetic_runner_token"

FAKES = {
    "anyio.py": "from pathlib import Path\n",
    "pycountry/__init__.py": (
        "class _Country:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "    def __hash__(self):\n"
        "        return hash(self.name)\n"
        "    def __eq__(self, other):\n"
        "        return self.name == other.name\n"
        "class _Countries:\n"
        "    def lookup(self, name):\n"
        "        if name == 'Nowhere':\n"
        "            raise LookupError(name)\n"
        "        return _Country(name)\n"
        "countries = _Countries()\n"
    ),
    "repeaterbook/__init__.py": "",
    "repeaterbook/exceptions.py": (
        "class RepeaterBookError(Exception):\n"
        "    pass\n"
        "class RepeaterBookAPIError(RepeaterBookError):\n"
        "    def __init__(self, message, *, status_code=None, error_code=None, url=None, body=None):\n"
        "        self.message = message\n"
        "        self.status_code = status_code\n"
        "        self.error_code = error_code\n"
        "        super().__init__(message)\n"
        "class RepeaterBookUnauthorizedError(RepeaterBookAPIError):\n"
        "    pass\n"
        "class RepeaterBookForbiddenError(RepeaterBookAPIError):\n"
        "    pass\n"
        "class RepeaterBookRateLimitError(RepeaterBookAPIError):\n"
        "    def __init__(self, message, *, retry_after=None, **kw):\n"
        "        super().__init__(message, **kw)\n"
        "        self.retry_after = retry_after\n"
    ),
    "repeaterbook/models.py": (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class ExportQuery:\n"
        "    countries: frozenset = frozenset()\n"
        "    state_ids: frozenset = frozenset()\n"
    ),
    "repeaterbook/services.py": (
        "import json, os\n"
        "from repeaterbook import exceptions as ex\n"
        "class RepeaterBookAPI:\n"
        "    def __init__(self, *, app_token, working_dir, max_cache_age):\n"
        "        self.app_token = app_token\n"
        "        self.working_dir = working_dir\n"
        "        self.max_cache_age = max_cache_age\n"
        "    def urls_export(self, query):\n"
        "        self.query = query\n"
        "        return {'https://www.repeaterbook.com/api/export.php?x=1'}\n"
        "    async def export_multi_json(self, urls):\n"
        "        cache = self.working_dir / 'cache-entry.json'\n"
        "        cache.write_text('rows would be cached here')\n"
        "        mode = os.environ.get('FAKE_RB_MODE', 'ok')\n"
        "        with open(os.environ['FAKE_RB_RECORD'], 'w') as f:\n"
        "            json.dump({'token': self.app_token, 'dir': str(self.working_dir),\n"
        "                       'age': self.max_cache_age.total_seconds(),\n"
        "                       'countries': sorted(c.name for c in self.query.countries),\n"
        "                       'states': sorted(self.query.state_ids)}, f)\n"
        "        if mode == 'rate':\n"
        "            raise ex.RepeaterBookRateLimitError('slow down', retry_after=12.5,\n"
        "                                                status_code=429, error_code='rate_limited')\n"
        "        if mode == 'unauthorized':\n"
        "            raise ex.RepeaterBookUnauthorizedError('no', status_code=401, error_code='auth_invalid')\n"
        "        if mode == 'forbidden':\n"
        "            raise ex.RepeaterBookForbiddenError('ua', status_code=403, error_code='ua_mismatch')\n"
        "        if mode == 'api':\n"
        "            raise ex.RepeaterBookAPIError('broken', status_code=200)\n"
        "        if mode == 'client':\n"
        "            raise ex.RepeaterBookError('cache trouble')\n"
        "        return [{'count': 1, 'results': [{'Callsign': 'N0CALL'}]},\n"
        "                {'count': 1, 'results': [{'Callsign': 'N0TST'}]}]\n"
    ),
}


@pytest.fixture
def fake_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for relative, text in FAKES.items():
        path = tmp_path / "fake" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    for name in [
        m for m in sys.modules if m.split(".")[0] in ("anyio", "pycountry", "repeaterbook")
    ]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(tmp_path / "fake"))
    record = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_RB_RECORD", str(record))
    monkeypatch.delenv("FAKE_RB_MODE", raising=False)
    return record


def test_the_runner_asks_for_one_state_and_merges_the_exports(
    fake_client: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(runner_module.TOKEN_VARIABLE, TOKEN)
    code = runner_module.main(["--country", "United States", "--state-id", "10"])
    out = capsys.readouterr().out
    assert code == 0
    document = json.loads(out)
    assert document == {
        "ok": True,
        "count": 2,
        "results": [{"Callsign": "N0CALL"}, {"Callsign": "N0TST"}],
    }
    assert TOKEN not in out
    seen = json.loads(fake_client.read_text())
    assert seen["token"] == TOKEN and seen["age"] == 0.0
    assert seen["countries"] == ["United States"] and seen["states"] == ["10"]
    assert not Path(seen["dir"]).exists(), "the client's cache directory is removed"


@pytest.mark.parametrize(
    ("mode", "kind", "status", "code"),
    [
        ("rate", "rate_limited", 429, "rate_limited"),
        ("unauthorized", "unauthorized", 401, "auth_invalid"),
        ("forbidden", "forbidden", 403, "ua_mismatch"),
        ("api", "api_error", 200, None),
        ("client", "client_error", None, None),
    ],
)
def test_every_client_failure_is_one_named_document_and_exit_1(
    mode: str,
    kind: str,
    status: int | None,
    code: str | None,
    fake_client: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(runner_module.TOKEN_VARIABLE, TOKEN)
    monkeypatch.setenv("FAKE_RB_MODE", mode)
    exit_code = runner_module.main(["--country", "United States", "--state-id", "10"])
    out = capsys.readouterr().out
    assert exit_code == 1
    document = json.loads(out)
    assert document["ok"] is False and document["kind"] == kind
    assert document["status"] == status and document["error_code"] == code
    assert document["retry_after"] == (12.5 if mode == "rate" else None)
    assert TOKEN not in out
    assert not Path(json.loads(fake_client.read_text())["dir"]).exists()


def test_an_unknown_country_and_a_missing_token_are_named(
    fake_client: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(runner_module.TOKEN_VARIABLE, TOKEN)
    assert runner_module.main(["--country", "Nowhere", "--state-id", "10"]) == 1
    assert json.loads(capsys.readouterr().out)["kind"] == "country"
    monkeypatch.delenv(runner_module.TOKEN_VARIABLE)
    assert runner_module.main(["--country", "United States", "--state-id", "10"]) == 1
    assert json.loads(capsys.readouterr().out)["kind"] == "no_token"
    assert not fake_client.exists(), "the client was never called without a token"


def test_a_missing_client_is_an_environment_failure_not_a_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in [
        m for m in sys.modules if m.split(".")[0] in ("anyio", "pycountry", "repeaterbook")
    ]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "repeaterbook", None)  # an import raises ImportError
    monkeypatch.setenv(runner_module.TOKEN_VARIABLE, TOKEN)
    assert runner_module.main(["--country", "United States", "--state-id", "10"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["kind"] == "environment" and TOKEN not in json.dumps(document)


def test_the_runner_file_imports_only_the_standard_library_at_the_top() -> None:
    """It runs under `python -I` in a venv that has the client and not the
    engine's dependencies (no yaml, no hammunition)."""
    tree = ast.parse(Path(runner_module.__file__).read_text())
    top: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module.split(".")[0])
    assert top <= set(sys.stdlib_module_names), top - set(sys.stdlib_module_names)
