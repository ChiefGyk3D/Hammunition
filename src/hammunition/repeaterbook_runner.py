# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fetch one state through the unofficial ``repeaterbook`` client.  D-081.

**Run by the ``repeaterbook-client`` unit's own venv python, never imported by
the engine**: ``<venv>/bin/python -I /path/to/repeaterbook_runner.py --country
NAME --state-id ID``. ``-I`` keeps this directory off ``sys.path`` (a
``secrets.py`` beside it would shadow the standard library's). It uses only
the standard library and that client (``repeaterbook``, ``pycountry``,
``anyio``, ``loguru``, all in the unit's pinned closure).

The operator's token is read from the environment variable ``REPEATERBOOK``,
the client's own name for it, and handed to the client, which sends it as
``X-RB-App-Token`` with its own User-Agent (App #114's, which the client's
docs say to leave alone). It is never an argument and is printed nowhere.
The client caches API responses on disk; this points it at a fresh private
temporary directory with a zero cache age and removes the directory on exit,
so nothing of RepeaterBook's is left behind.

Prints exactly one JSON document on stdout: ``{"ok": true, "count": N,
"results": [...]}`` (the export's own rows, merged) or ``{"ok": false,
"kind": ..., "status": ..., "error_code": ..., "message": ...,
"retry_after": ...}``; the exit status is 0 and 1. Built against the
client's 0.13.0 source, read 2026-10-04; **not yet run against the live API**.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import timedelta
from typing import Any

TOKEN_VARIABLE = "REPEATERBOOK"


def _failure(kind: str, message: str, **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "ok": False,
        "kind": kind,
        "status": None,
        "error_code": None,
        "message": message[:300],
        "retry_after": None,
    }
    document.update(extra)
    return document


def fetch(country: str, state_id: str, token: str) -> dict[str, Any]:
    """The export for one state as a document, or a failure document."""
    try:
        import anyio
        import pycountry
        from repeaterbook import exceptions
        from repeaterbook.models import ExportQuery
        from repeaterbook.services import RepeaterBookAPI
    except ImportError as exc:
        return _failure("environment", f"the repeaterbook client is not importable here: {exc}")
    try:
        found = pycountry.countries.lookup(country)
    except LookupError:
        return _failure("country", f"RepeaterBook's client does not know the country {country!r}")
    with tempfile.TemporaryDirectory(prefix="hammunition-repeaterbook-") as work:
        api = RepeaterBookAPI(
            app_token=token,
            working_dir=anyio.Path(work),
            max_cache_age=timedelta(0),
        )
        query = ExportQuery(countries=frozenset({found}), state_ids=frozenset({state_id}))
        try:
            exports = asyncio.run(api.export_multi_json(api.urls_export(query)))
        except exceptions.RepeaterBookRateLimitError as exc:
            return _failure(
                "rate_limited",
                exc.message,
                status=exc.status_code or 429,
                error_code=exc.error_code,
                retry_after=exc.retry_after,
            )
        except exceptions.RepeaterBookUnauthorizedError as exc:
            return _failure(
                "unauthorized",
                exc.message,
                status=exc.status_code or 401,
                error_code=exc.error_code,
            )
        except exceptions.RepeaterBookForbiddenError as exc:
            return _failure(
                "forbidden", exc.message, status=exc.status_code or 403, error_code=exc.error_code
            )
        except exceptions.RepeaterBookAPIError as exc:
            return _failure(
                "api_error", exc.message, status=exc.status_code, error_code=exc.error_code
            )
        except exceptions.RepeaterBookError as exc:
            return _failure("client_error", str(exc))
    results: list[Any] = []
    for export in exports:
        results.extend(export["results"])
    return {"ok": True, "count": len(results), "results": results}


def _quiet_client_logging() -> None:
    """The client logs at INFO to stderr through loguru; keep only warnings.
    Without loguru there is nothing to quiet."""
    try:
        from loguru import logger
    except ImportError:
        return
    logger.remove()
    logger.add(sys.stderr, level="WARNING")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--country", required=True)
    parser.add_argument("--state-id", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token:
        document = _failure("no_token", f"{TOKEN_VARIABLE} is not set in this process")
    else:
        _quiet_client_logging()
        document = fetch(args.country, args.state_id, token)
    sys.stdout.write(json.dumps(document) + "\n")
    return 0 if document["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
