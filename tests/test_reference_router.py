# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Routes on the browser map: ``reference serve`` starts GraphHopper and
answers ``/map/route`` itself.  D-076.

A loopback stand-in answers GraphHopper's ``/route`` (port 0, never a real
GraphHopper); the child is a fake. The route request is rebuilt by the
reference server, so the stand-in records exactly what reached it.
"""

from __future__ import annotations

import http.client
import http.server
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import Any, ClassVar

import pytest

from hammunition import graphhopper as gh
from hammunition.map_page import ROUTE, find_map, map_page
from hammunition.reference import RouterState, Shelf, die_with_parent, make_server, run
from test_graphhopper import JAR, _installed
from test_map_serve import _data

ROUTE_ANSWER = {
    "paths": [
        {
            "distance": 4148.0,
            "time": 2980000,
            "points": {"type": "LineString", "coordinates": [[-72.547, 44.255], [-72.547, 44.29]]},
            "instructions": [{"text": "Continue onto Trail 19", "distance": 4148.0}],
        }
    ]
}


class _FakeGraphHopper(http.server.BaseHTTPRequestHandler):
    asked: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        type(self).asked.append(self.path)
        body = json.dumps(ROUTE_ANSWER).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet."""


@pytest.fixture
def graphhopper() -> Iterator[tuple[int, list[str]]]:
    _FakeGraphHopper.asked = []
    fake = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeGraphHopper)
    Thread(target=fake.serve_forever, daemon=True).start()
    try:
        yield fake.server_address[1], _FakeGraphHopper.asked
    finally:
        fake.shutdown()
        fake.server_close()


def _router(tmp_path: Path, port: int) -> RouterState:
    return RouterState(port=port, profiles=gh.PROFILES, log=tmp_path / "graphhopper.log")


def _serve(tmp_path: Path, router: RouterState | None) -> tuple[Any, int]:
    shelf = find_map(_data(tmp_path))
    server = make_server(0, "<html></html>", [], map_shelf=shelf, position_port=1, router=router)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _get(port: int, path: str, host: str | None = None) -> tuple[int, dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.putrequest("GET", path, skip_host=True)
        conn.putheader("Host", host or f"127.0.0.1:{port}")
        conn.endheaders()
        response = conn.getresponse()
        body = response.read()
        return response.status, json.loads(body) if body.startswith(b"{") else {"raw": body}
    finally:
        conn.close()


GOOD = f"{ROUTE}?point=44.255,-72.547&point=44.29,-72.547&profile=hike"


def test_a_route_is_asked_of_graphhopper_as_rebuilt_and_its_answer_relayed(
    tmp_path: Path, graphhopper: tuple[int, list[str]]
) -> None:
    port, asked = graphhopper
    server, served = _serve(tmp_path, _router(tmp_path, port))
    try:
        status, body = _get(served, GOOD)
    finally:
        server.shutdown()
        server.server_close()
    assert status == 200 and body == ROUTE_ANSWER
    assert asked == [
        gh.route_query("point=44.255,-72.547&point=44.29,-72.547&profile=hike", gh.PROFILES)
    ]


def test_a_request_graphhopper_should_not_see_is_refused_here(
    tmp_path: Path, graphhopper: tuple[int, list[str]]
) -> None:
    port, asked = graphhopper
    server, served = _serve(tmp_path, _router(tmp_path, port))
    try:
        status, body = _get(served, GOOD + "&custom_model=x")
        refused, _ = _get(served, GOOD, host="evil.example:80")
    finally:
        server.shutdown()
        server.server_close()
    assert status == 400 and "custom_model" in body["message"]
    assert refused == 403
    assert asked == [], "nothing reached GraphHopper"


def test_a_graphhopper_not_listening_yet_is_a_503_that_says_so(tmp_path: Path) -> None:
    server, served = _serve(tmp_path, _router(tmp_path, gh.free_port()))
    try:
        status, body = _get(served, GOOD)
    finally:
        server.shutdown()
        server.server_close()
    assert status == 503 and "starting" in body["message"]


def test_a_graphhopper_that_exited_is_a_503_naming_the_exit_and_the_log(tmp_path: Path) -> None:
    router = _router(tmp_path, gh.free_port())
    router.exited = 1
    server, served = _serve(tmp_path, router)
    try:
        status, body = _get(served, GOOD)
    finally:
        server.shutdown()
        server.server_close()
    assert status == 503
    assert "exit 1" in body["message"] and str(tmp_path / "graphhopper.log") in body["message"]


def test_without_a_router_there_is_no_route(tmp_path: Path) -> None:
    server, served = _serve(tmp_path, None)
    try:
        status, _ = _get(served, GOOD)
    finally:
        server.shutdown()
        server.server_close()
    assert status == 404


# -- run: the router child -----------------------------------------------------


class FakeChild:
    def __init__(self, exits_after: int | None = None) -> None:
        self.polls = 0
        self.exits_after = exits_after
        self.terminated = False

    def poll(self) -> int | None:
        self.polls += 1
        if self.terminated:
            return -15
        if self.exits_after is not None and self.polls > self.exits_after:
            return 3
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return -15

    def kill(self) -> None:  # pragma: no cover - terminate always works here
        self.terminated = True


def _run(
    tmp_path: Path, child: FakeChild, *, interrupt_after: int
) -> tuple[int, list[gh.RouterSpec], list[str]]:
    started: list[gh.RouterSpec] = []
    lines: list[str] = []
    ticks = {"n": 0}
    spec = gh.RouterSpec(
        argv=["java", "-jar", JAR, "server", "config.yml"],
        port=gh.free_port(),
        profiles=gh.PROFILES,
        log=tmp_path / "graphhopper.log",
        config=tmp_path / "config.yml",
    )

    def start_router(router: gh.RouterSpec) -> FakeChild:
        started.append(router)
        return child

    def tick() -> None:
        ticks["n"] += 1
        if ticks["n"] >= interrupt_after:
            raise KeyboardInterrupt

    rc = run(
        0,
        shelf=Shelf(books=(), forms=(), dict_client=False, goldendict=False),
        library=tmp_path / "library.xml",
        spawn=lambda argv: pytest.fail("no books, no kiwix-serve"),
        manage=lambda library, zims: None,
        tick=tick,
        log=lines.append,
        map_shelf=find_map(_data(tmp_path)),
        router=spec,
        start_router=start_router,
    )
    return rc, started, lines


def test_the_router_is_started_logged_and_stopped_with_the_page(tmp_path: Path) -> None:
    child = FakeChild()
    rc, started, lines = _run(tmp_path, child, interrupt_after=3)
    assert rc == 0 and child.terminated and len(started) == 1
    assert any("routes:" in line and "GraphHopper" in line for line in lines)


def test_a_router_that_exits_is_reported_once_and_the_page_keeps_serving(tmp_path: Path) -> None:
    child = FakeChild(exits_after=1)
    rc, _started, lines = _run(tmp_path, child, interrupt_after=6)
    assert rc == 0, "the books and the map keep serving"
    said = [line for line in lines if "GraphHopper exited" in line]
    assert len(said) == 1 and "(3)" in said[0] and "graphhopper.log" in said[0]


# -- deciding whether there is a router ---------------------------------------------


def test_a_ready_graph_with_java_and_a_map_makes_a_router(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    spec, note = gh.plan_router(
        data=data, tree=tree, home=tmp_path / "home", map_ready=True, java="/usr/bin/java"
    )
    assert note is None and spec is not None
    assert spec.argv[-2:] == ["server", str(tmp_path / "home" / "config.yml")]


def test_no_router_without_the_map_without_java_or_with_a_stale_graph(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    home = tmp_path / "home"
    assert gh.plan_router(data=data, tree=tree, home=home, map_ready=False, java="java") == (
        None,
        None,
    )
    spec, note = gh.plan_router(data=data, tree=tree, home=home, map_ready=True, java=None)
    assert spec is None and note is not None and "java" in note
    (tree / JAR).rename(tree / "graphhopper-web-12.0.jar")
    spec, note = gh.plan_router(data=data, tree=tree, home=home, map_ready=True, java="java")
    assert spec is None and note is not None and "graphhopper-web-12.0.jar" in note
    assert gh.plan_router(
        data=tmp_path / "none", tree=tree, home=home, map_ready=True, java="java"
    ) == (None, None), "nothing installed, nothing to say: the landing page says how"


# -- the child dies with reference serve -------------------------------------------------


def test_the_router_child_is_asked_to_die_with_its_parent(tmp_path: Path) -> None:
    """GraphHopper has no ``-a PID`` as kiwix-serve does, so the child is given
    PR_SET_PDEATHSIG: a parent killed without the chance to stop it does not
    leave GraphHopper running."""
    pid_file = tmp_path / "child.pid"
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess, sys, time\n"
            "from hammunition.reference import die_with_parent\n"
            "child = subprocess.Popen(['sleep', '60'], preexec_fn=die_with_parent)\n"
            f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
            "time.sleep(60)\n",
        ],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")},
    )
    try:
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text():
                break
            time.sleep(0.05)
        child = int(pid_file.read_text())
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        for _ in range(100):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            os.kill(child, signal.SIGKILL)
            pytest.fail("the child outlived its parent")
    finally:
        if parent.poll() is None:
            parent.kill()
    assert callable(die_with_parent)


# -- the page ---------------------------------------------------------------------


def test_with_a_router_the_page_has_the_route_control_and_names_only_this_server() -> None:
    page = map_page(position_port=10111, router=gh.PROFILES)
    for needle in ('id="profile"', 'id="route"', 'id="clear"', ROUTE, "#route="):
        assert needle in page, needle
    for profile in gh.PROFILES:
        assert f">{profile}<" in page or f'"{profile}"' in page
    assert "graphhopper.com" not in page and "8989" not in page


def test_without_a_router_the_page_has_no_route_control() -> None:
    page = map_page(position_port=10111)
    assert 'id="route"' not in page and ROUTE not in page
