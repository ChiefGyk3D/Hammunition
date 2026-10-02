# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the converter and ``reference serve`` share about GraphHopper:
its configuration, the graph's record, and the route request.  D-076."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
import yaml

from hammunition import graphhopper as gh

JAR = "graphhopper-web-11.1.jar"


# -- the configuration ---------------------------------------------------------


def test_the_import_config_names_its_input_and_graph_and_the_four_profiles(
    tmp_path: Path,
) -> None:
    pbf = tmp_path / "odd 'name\".osm.pbf"
    text = gh.import_config(pbf, tmp_path / "graph")
    config = yaml.safe_load(text)["graphhopper"]
    assert config["datareader.file"] == str(pbf)
    assert config["graph.location"] == str(tmp_path / "graph")
    assert [p["name"] for p in config["profiles"]] == ["car", "bike", "foot", "hike"]
    assert [p["custom_model_files"] for p in config["profiles"]] == [
        ["car.json"],
        ["bike.json"],
        ["foot.json"],
        ["hike.json"],
    ]
    assert config["profiles_ch"] == [{"profile": "car"}]
    assert config["profiles_lm"] == [{"profile": p} for p in ("bike", "foot", "hike")]
    assert "hike_rating" in config["graph.encoded_values"]
    # Mandatory since GraphHopper 10 (the spike's first config was refused).
    assert config["import.osm.ignored_highways"] == ""
    assert config["graph.dataaccess.default_type"] == "RAM_STORE"


def test_the_serve_config_reads_no_input_and_listens_on_loopback_only(tmp_path: Path) -> None:
    config = yaml.safe_load(gh.serve_config(tmp_path / "graph", 40123))
    assert "datareader.file" not in config["graphhopper"]
    assert config["graphhopper"]["graph.location"] == str(tmp_path / "graph")
    assert config["server"]["application_connectors"] == [
        {"type": "http", "port": 40123, "bind_host": "127.0.0.1"}
    ]
    assert config["server"]["admin_connectors"] == []


def test_import_and_serve_share_the_same_profiles(tmp_path: Path) -> None:
    """GraphHopper refuses to load a graph whose profiles changed."""
    built = yaml.safe_load(gh.import_config(tmp_path / "a.osm.pbf", tmp_path / "g"))
    served = yaml.safe_load(gh.serve_config(tmp_path / "g", 1))
    for key in ("profiles", "profiles_ch", "profiles_lm", "graph.encoded_values"):
        assert built["graphhopper"][key] == served["graphhopper"][key]


def test_the_server_argv_runs_the_jar_with_the_config(tmp_path: Path) -> None:
    argv = gh.server_argv(tmp_path / JAR, tmp_path / "config.yml")
    assert argv == [
        "java",
        gh.HEAP,
        "-jar",
        str(tmp_path / JAR),
        "server",
        str(tmp_path / "config.yml"),
    ]


# -- the record ----------------------------------------------------------------


def test_the_record_round_trips() -> None:
    text = gh.render_record(["delaware 260928"], JAR, ["properties", "edges"])
    assert text.splitlines()[-1] == f"converter: {gh.CONVERTER}"
    record = gh.parse_record(text)
    assert record is not None
    assert record.regions == ("delaware 260928",)
    assert record.program == JAR
    assert record.profiles == gh.PROFILES
    assert record.files == ("edges", "properties")
    assert record.converter == gh.CONVERTER


def _installed(
    tmp_path: Path, *, files: tuple[str, ...] = ("properties", "edges")
) -> tuple[Path, Path]:
    data, tree = tmp_path / "data" / gh.GRAPH_UNIT, tmp_path / "share" / gh.PROGRAM_UNIT
    data.mkdir(parents=True)
    tree.mkdir(parents=True)
    (tree / JAR).write_bytes(b"jar")
    for name in files:
        (data / name).write_bytes(b"graph")
    (data / gh.RECORD).write_text(gh.render_record(["vermont 260928"], JAR, list(files)))
    return data, tree


def test_an_installed_current_graph_is_ready(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    shelf = gh.find_graph(data, tree)
    assert shelf.ready, shelf.why
    assert shelf.jar == tree / JAR
    assert sorted(p.name for p in shelf.files) == ["edges", "properties"]
    assert shelf.profiles == gh.PROFILES
    assert shelf.regions == 1


def test_no_record_is_not_installed(tmp_path: Path) -> None:
    shelf = gh.find_graph(tmp_path / "nothing", tmp_path / "tree")
    assert not shelf.ready and not shelf.installed
    assert "hammunition install graphhopper-graph" in (shelf.why or "")


def test_a_graph_built_by_another_jar_is_not_served(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    (tree / JAR).rename(tree / "graphhopper-web-12.0.jar")
    shelf = gh.find_graph(data, tree)
    assert not shelf.ready and shelf.installed
    assert JAR in (shelf.why or "") and "graphhopper-web-12.0.jar" in (shelf.why or "")


def test_a_graph_missing_a_file_is_not_served(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    (data / "edges").unlink()
    shelf = gh.find_graph(data, tree)
    assert not shelf.ready and "edges" in (shelf.why or "")


def test_a_record_from_another_converter_version_is_not_served(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    record = data / gh.RECORD
    record.write_text(record.read_text().replace(gh.CONVERTER, "graphhopper-import 0"))
    assert not gh.find_graph(data, tree).ready


def test_a_record_naming_a_path_is_not_followed(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    (data / gh.RECORD).write_text(
        f"x 1\nprogram {JAR}\nprofiles car\nfile properties\nfile ../../etc/passwd\n"
        f"converter: {gh.CONVERTER}\n"
    )
    shelf = gh.find_graph(data, tree)
    assert not shelf.ready


# -- the route request -----------------------------------------------------------


def test_a_route_query_is_rebuilt_from_its_checked_parts() -> None:
    path = gh.route_query("point=44.26,-72.58&point=44.29,-72.55&profile=hike", gh.PROFILES)
    assert path == (
        "/route?point=44.26%2C-72.58&point=44.29%2C-72.55&profile=hike"
        "&points_encoded=false&instructions=true&calc_points=true&locale=en&ch.disable=true"
    )


def test_car_keeps_its_contraction_hierarchies() -> None:
    path = gh.route_query("point=44.26,-72.58&point=44.29,-72.55&profile=car", gh.PROFILES)
    assert "ch.disable" not in path


@pytest.mark.parametrize(
    "query",
    [
        "point=44.26,-72.58&profile=car",  # one point
        "point=1,1&point=2,2&point=3,3&profile=car",  # three
        "point=44.26,-72.58&point=44.29,-72.55",  # no profile
        "point=44.26,-72.58&point=44.29,-72.55&profile=truck",  # not built
        "point=44.26,-72.58&point=44.29,-72.55&profile=car&profile=foot",
        "point=91,0&point=0,0&profile=car",
        "point=0,181&point=0,0&profile=car",
        "point=nan,0&point=0,0&profile=car",
        "point=inf,0&point=0,0&profile=car",
        "point=0&point=0,0&profile=car",
        "point=0,0,0&point=0,0&profile=car",
        "point=0,0&point=0,0&profile=car&custom_model=x",  # nothing else is passed
        "point=0,0&point=0,0&profile=car&locale=de",
    ],
)
def test_anything_else_is_refused(query: str) -> None:
    with pytest.raises(gh.RouteRefused):
        gh.route_query(query, gh.PROFILES)


def test_only_the_profiles_the_graph_was_built_with_are_asked_for() -> None:
    with pytest.raises(gh.RouteRefused, match="hike"):
        gh.route_query("point=0,0&point=1,1&profile=hike", ("car", "foot"))


# -- what reference serve prepares ------------------------------------------------


def test_a_free_port_is_on_loopback_and_free() -> None:
    port = gh.free_port()
    with socket.create_server(("127.0.0.1", port)):
        pass


def test_the_router_is_prepared_in_the_operators_cache(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    shelf = gh.find_graph(data, tree)
    home = tmp_path / "cache" / "graphhopper"
    spec = gh.prepare_router(shelf, home, 40000)
    assert spec.port == 40000 and spec.profiles == gh.PROFILES
    assert spec.argv == gh.server_argv(tree / JAR, home / "config.yml")
    assert spec.log == home / "graphhopper.log"
    assert (home / "config.yml").stat().st_mode & 0o777 == 0o600
    assert home.stat().st_mode & 0o777 == 0o700
    config = yaml.safe_load((home / "config.yml").read_text())
    assert config["graphhopper"]["graph.location"] == str(home / "graph")
    links = sorted((home / "graph").iterdir())
    assert [p.name for p in links] == ["edges", "properties"]
    assert all(p.is_symlink() and p.resolve() == data / p.name for p in links)


def test_a_previous_runs_links_and_lock_are_replaced_and_nothing_else_is_touched(
    tmp_path: Path,
) -> None:
    data, tree = _installed(tmp_path)
    home = tmp_path / "cache" / "graphhopper"
    (home / "graph").mkdir(parents=True)
    (home / "graph" / "gone").symlink_to(data / "missing")
    (home / "graph" / "gh.lock").write_text("")
    gh.prepare_router(gh.find_graph(data, tree), home, 1)
    assert sorted(p.name for p in (home / "graph").iterdir()) == ["edges", "properties"]
    (home / "graph" / "mine.txt").write_text("the operator's")
    with pytest.raises(gh.RouterError, match=r"mine\.txt"):
        gh.prepare_router(gh.find_graph(data, tree), home, 1)
    assert (home / "graph" / "mine.txt").read_text() == "the operator's"


def test_a_graph_not_ready_is_not_prepared(tmp_path: Path) -> None:
    with pytest.raises(gh.RouterError, match="install"):
        gh.prepare_router(gh.find_graph(tmp_path / "x", tmp_path / "y"), tmp_path / "home", 1)


def test_the_config_never_follows_a_link_left_in_its_place(tmp_path: Path) -> None:
    data, tree = _installed(tmp_path)
    home = tmp_path / "cache" / "graphhopper"
    home.mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.write_text("keep")
    os.symlink(victim, home / "config.yml")
    gh.prepare_router(gh.find_graph(data, tree), home, 1)
    assert victim.read_text() == "keep"
    assert not (home / "config.yml").is_symlink()


def test_a_record_line_that_would_not_parse_back_is_refused() -> None:
    """The record is plain lines: a region line is a slug and a snapshot, and
    a file is a plain name."""
    with pytest.raises(ValueError):
        gh.render_record(["two words 260928"], JAR, ["properties"])
    with pytest.raises(ValueError):
        gh.render_record(["vermont 260928"], JAR, ["graph/properties"])
