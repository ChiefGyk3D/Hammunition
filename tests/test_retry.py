# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan-time retry policy (#200): what is retried, how long it waits, what
it says, and what it gives up with. No network and no real sleep: every probe
here is a fake and the policy's sleep is recorded."""

from __future__ import annotations

import io
import urllib.error

import pytest

from hammunition.geofabrik import GeofabrikError
from hammunition.progress import say
from hammunition.retry import (
    ATTEMPTS,
    DELAYS,
    Outages,
    PublisherUnavailable,
    RetryingProbe,
    RetryPolicy,
    retrying_head,
    transient_answer,
)

URL = "https://download.geofabrik.de/atlantis/oceania.poly"


class Recorder:
    def __init__(self) -> None:
        self.slept: list[float] = []
        self.said: list[str] = []

    def policy(self, **kw: object) -> RetryPolicy:
        return RetryPolicy(sleep=self.slept.append, notify=self.said.append, **kw)  # type: ignore[arg-type]


class Scripted:
    """A probe answering from a script: a status tuple, or an exception raised."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.calls = 0

    def _next(self) -> object:
        self.calls += 1
        answer = self.answers[min(self.calls, len(self.answers)) - 1]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def head(self, url: str) -> tuple[int, int, str | None]:
        return self._next()  # type: ignore[return-value]

    def text(self, url: str) -> str:
        return self._next()  # type: ignore[return-value]


def _http(code: int, reason: str = "x") -> GeofabrikError:
    err = GeofabrikError(f"{URL} returned HTTP {code} ({reason})")
    err.__cause__ = urllib.error.HTTPError(URL, code, reason, None, None)  # type: ignore[arg-type]
    return err


def _timeout() -> GeofabrikError:
    err = GeofabrikError(f"{URL} could not be fetched: timed out")
    err.__cause__ = urllib.error.URLError(TimeoutError("timed out"))
    return err


def test_the_constants_are_the_ones_the_issue_names() -> None:
    assert ATTEMPTS == 3 and DELAYS == (1.0, 3.0, 9.0)


def test_503_twice_then_200_succeeds_with_two_retry_lines_and_the_backoff() -> None:
    rec = Recorder()
    inner = Scripted((503, 0, None), (503, 0, None), (200, 9, '"e"'))
    got = RetryingProbe(inner, rec.policy()).head(URL)
    assert got == (200, 9, '"e"') and inner.calls == 3
    assert rec.slept == [1.0, 3.0]
    assert len(rec.said) == 2
    assert "download.geofabrik.de" in rec.said[0] and "attempt 2 of 3" in rec.said[0]
    assert "attempt 3 of 3" in rec.said[1] and "HTTP 503" in rec.said[1]


def test_503_forever_is_three_attempts_then_publisher_unavailable_quoting_the_answer() -> None:
    rec = Recorder()
    inner = Scripted((503, 0, None))
    with pytest.raises(PublisherUnavailable) as caught:
        RetryingProbe(inner, rec.policy()).head(URL)
    assert inner.calls == 3 and rec.slept == [1.0, 3.0]
    assert caught.value.answer == "HTTP 503" and caught.value.host == "download.geofabrik.de"
    assert "not answering right now" in str(caught.value)
    assert isinstance(caught.value, OSError), "resolvers already catch OSError"


@pytest.mark.parametrize("status", [404, 403, 410, 301, 200])
def test_other_statuses_are_final_at_once(status: int) -> None:
    rec = Recorder()
    inner = Scripted((status, 0, None))
    assert RetryingProbe(inner, rec.policy()).head(URL)[0] == status
    assert inner.calls == 1 and rec.slept == []


def test_429_is_retried() -> None:
    rec = Recorder()
    inner = Scripted((429, 0, None), (200, 1, None))
    assert RetryingProbe(inner, rec.policy()).head(URL)[0] == 200
    assert rec.slept == [1.0]


def test_text_probe_retries_an_http_502_raised_as_an_error() -> None:
    rec = Recorder()
    inner = Scripted(_http(502, "Bad Gateway"), "outline")
    assert RetryingProbe(inner, rec.policy()).text(URL) == "outline"
    assert "HTTP 502 Bad Gateway" in rec.said[0]


def test_text_probe_a_404_raised_as_an_error_is_final() -> None:
    rec = Recorder()
    inner = Scripted(_http(404, "Not Found"))
    with pytest.raises(GeofabrikError, match="404"):
        RetryingProbe(inner, rec.policy()).text(URL)
    assert inner.calls == 1 and rec.said == []


def test_a_read_timeout_is_retried_then_given_up_on() -> None:
    rec = Recorder()
    inner = Scripted(_timeout())
    with pytest.raises(PublisherUnavailable) as caught:
        RetryingProbe(inner, rec.policy()).text(URL)
    assert inner.calls == 3 and caught.value.answer == "timed out"


def test_a_bare_timeout_from_a_body_read_is_retried() -> None:
    rec = Recorder()
    inner = Scripted(TimeoutError("the read operation timed out"), "ok")
    assert RetryingProbe(inner, rec.policy()).text(URL) == "ok"


def test_a_probe_refusing_a_url_is_not_retried() -> None:
    rec = Recorder()
    inner = Scripted(GeofabrikError("refusing 'x': only the mirror is asked"))
    with pytest.raises(GeofabrikError, match="refusing"):
        RetryingProbe(inner, rec.policy()).text(URL)
    assert inner.calls == 1


def test_a_bare_head_callable_is_wrapped_too() -> None:
    rec = Recorder()
    inner = Scripted(503, 200)
    assert retrying_head(inner.head, rec.policy())(URL) == 200  # an int status, as Kiwix's
    assert rec.slept == [1.0]


def test_a_host_that_keeps_failing_is_asked_once_each_after_the_breaker_trips() -> None:
    rec = Recorder()
    policy = rec.policy()
    probe = RetryingProbe(Scripted(_timeout()), policy)
    for _ in range(3):
        with pytest.raises(PublisherUnavailable):
            probe.text(URL)
    slept = len(rec.slept)
    inner = Scripted(_timeout())
    with pytest.raises(PublisherUnavailable) as caught:
        RetryingProbe(inner, policy).text(URL)
    assert inner.calls == 1 and len(rec.slept) == slept and caught.value.attempts == 1
    policy.reset()
    again = Scripted(_timeout())
    with pytest.raises(PublisherUnavailable):
        RetryingProbe(again, policy).text(URL)
    assert again.calls == 3


def test_a_success_resets_the_hosts_failures() -> None:
    rec = Recorder()
    policy = rec.policy()
    for _ in range(2):
        with pytest.raises(PublisherUnavailable):
            RetryingProbe(Scripted(_timeout()), policy).text(URL)
    assert RetryingProbe(Scripted("ok"), policy).text(URL) == "ok"
    third = Scripted(_timeout())
    with pytest.raises(PublisherUnavailable):
        RetryingProbe(third, policy).text(URL)
    assert third.calls == 3


def test_transient_answer_reads_the_cause_chain() -> None:
    assert transient_answer(_http(503, "Service Unavailable")) == "HTTP 503 Service Unavailable"
    assert transient_answer(_http(404)) is None
    assert transient_answer(GeofabrikError("no cause")) is None
    assert transient_answer(ConnectionResetError("reset")) == "connection failed: reset"


def test_say_is_silent_off_a_terminal_and_speaks_when_forced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAMMUNITION_PROGRESS", raising=False)
    quiet = io.StringIO()
    say("hello", quiet)
    assert quiet.getvalue() == ""
    monkeypatch.setenv("HAMMUNITION_PROGRESS", "1")
    loud = io.StringIO()
    say("hello", loud)
    assert loud.getvalue() == "hello\n"


def test_outages_defer_by_unit_naming_items_and_the_answer() -> None:
    outages = Outages()
    exc = PublisherUnavailable("https://prd-tnm.s3.amazonaws.com/x", "HTTP 503", 3)
    assert outages.reporter("typed-unit", requested=True) is None
    report = outages.reporter("usgs-ustopo", requested=False)
    assert report is not None
    report("ZZ_Alpha_20240101", exc)
    report("ZZ_Beta_20240101", exc)
    (deferral,) = outages.deferrals()
    assert deferral.subject == "usgs-ustopo" and deferral.kind == "package"
    assert "ZZ_Alpha_20240101, ZZ_Beta_20240101" in deferral.what
    assert "prd-tnm.s3.amazonaws.com answered HTTP 503" in deferral.why
    assert "again" in deferral.remedy
    footer = outages.footer()
    assert footer is not None and "run the same command again" in footer
