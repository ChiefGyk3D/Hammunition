# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""GraphHopper, the browser map's router: what the converter and
``reference serve`` share.  D-076.

GraphHopper 11.1 (``graphhopper-web-11.1.jar``, Maven Central) imports a
region into a routing graph with ``java -jar <jar> import config.yml`` and
serves it with ``java -jar <jar> server config.yml``. GraphHopper refuses to
load a graph whose profiles changed, so both configurations come from one
place, here, and the catalog never carries one: the four profiles are
GraphHopper's own bundled custom models (``car``, ``bike``, ``foot``,
``hike``), ``hike`` routing on ``sac_scale``.

**The graph is served through links.** GraphHopper takes a lock file,
``gh.lock``, in the graph's own directory whenever writes are allowed, and
11.1 has no configuration key to disallow them (measured 2026-10-01: a
read-only graph refuses to start). The installed graph is root's, so
:func:`prepare_router` makes a directory of links to it in the operator's
cache, where the lock can be taken; the files themselves stay read-only.

**The route request is rebuilt, never passed through.** :func:`route_query`
reads two points and a profile and builds GraphHopper's query itself, so a
page can ask for nothing GraphHopper offers beyond a route.
"""

from __future__ import annotations

import json
import math
import os
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

#: The two catalog units this module reads, by name.
PROGRAM_UNIT = "graphhopper"
GRAPH_UNIT = "graphhopper-graph"
#: The graph's record, in its data directory.
RECORD = "graph.source"
#: What the graph was built by: the record's last line. Bumped whenever the
#: configuration or the argv changes the graph, so every older one is rebuilt.
CONVERTER = "graphhopper-import 1"
#: GraphHopper's jar, as Maven Central names it.
JAR_GLOB = "graphhopper-web-*.jar"
#: The file every graph GraphHopper writes holds (measured).
PROPERTIES = "properties"
#: The profiles built, in the order the page offers them; car under
#: contraction hierarchies, the rest under landmarks (the spike's choice).
PROFILES: tuple[str, ...] = ("car", "bike", "foot", "hike")
CH_PROFILES = frozenset({"car"})
#: The encoded values the four custom models read (the spike's config).
ENCODED_VALUES = (
    "car_access, car_average_speed, road_access, foot_access, foot_priority, "
    "foot_average_speed, foot_road_access, hike_rating, mtb_rating, foot_network, country, "
    "road_class, bike_priority, bike_access, bike_road_access, bike_average_speed, roundabout"
)
#: One heap for the import and the server: BRouter's figure (D-063). The
#: import peaked at 1.18 GB on Delaware under -Xmx2g; nothing larger is
#: measured, and the JVM takes only what it uses.
HEAP = "-Xmx4000m"
HOST = "127.0.0.1"
#: The lock GraphHopper leaves in the graph directory while it serves.
LOCK = "gh.lock"


MEASURED = "measured on one region"
#: The graph against the downloads it was built from: 78 MB from Delaware's
#: 22.1 MB (the routing spike, 2026-09-29), 3.5x, rounded up to 3.7 in case
#: the spike's MB were MiB.
FACTOR = 3.7
#: The import's memory, from the same single measurement.
MEMORY = (
    "about 1.2 GB of memory on Delaware's 22.1 MB, the one region measured; "
    "Java's heap is capped at 4 GB"
)
GRAPH_NOTE = (
    f"the route graph at {FACTOR}x all the downloads together ({MEASURED}), twice over "
    f"while it builds and installs"
)


def estimate(total: int) -> int:
    return round(total * FACTOR)


def _q(value: object) -> str:
    """A YAML scalar: JSON's quoting, which YAML reads as a string."""
    return json.dumps(str(value))


def _graphhopper(graph: Path, source: Path | None) -> list[str]:
    lines = ["graphhopper:"]
    if source is not None:
        lines.append(f"  datareader.file: {_q(source)}")
    lines.append(f"  graph.location: {_q(graph)}")
    lines.append("  profiles:")
    for name in PROFILES:
        lines += [f"    - name: {name}", f"      custom_model_files: [{name}.json]"]
    lines.append("  profiles_ch:")
    lines += [f"    - profile: {name}" for name in PROFILES if name in CH_PROFILES]
    lines.append("  profiles_lm:")
    lines += [f"    - profile: {name}" for name in PROFILES if name not in CH_PROFILES]
    lines += [
        f"  graph.encoded_values: {ENCODED_VALUES}",
        '  import.osm.ignored_highways: ""',
        "  prepare.min_network_size: 200",
        "  prepare.subnetworks.threads: 1",
        "  routing.snap_preventions_default: tunnel, bridge, ferry",
        "  graph.dataaccess.default_type: RAM_STORE",
    ]
    return lines


_LOGGING = ["logging:", "  appenders:", "    - type: console"]


def import_config(source: Path, graph: Path) -> str:
    """``config.yml`` for ``import``: one input, the graph written to *graph*."""
    return "\n".join([*_graphhopper(graph, source), *_LOGGING]) + "\n"


def serve_config(graph: Path, port: int) -> str:
    """``config.yml`` for ``server``: no input, so nothing is imported; one
    connector on 127.0.0.1 and no admin connector (measured: accepted)."""
    server = [
        "server:",
        "  application_connectors:",
        "    - type: http",
        f"      port: {int(port)}",
        f"      bind_host: {HOST}",
        "  admin_connectors: []",
    ]
    return "\n".join([*_graphhopper(graph, None), *server, *_LOGGING]) + "\n"


def import_argv(jar: Path, config: Path) -> list[str]:
    return ["java", HEAP, "-jar", str(jar), "import", str(config)]


def server_argv(jar: Path, config: Path) -> list[str]:
    return ["java", HEAP, "-jar", str(jar), "server", str(config)]


def find_jar(tree: Path) -> Path | None:
    """The one ``graphhopper-web-*.jar`` in GraphHopper's tree, or None."""
    found = sorted(tree.glob(JAR_GLOB))
    return found[0] if len(found) == 1 else None


# -- the record ----------------------------------------------------------------


def _plain(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and "\0" not in name


def render_record(regions: Sequence[str], jar: str | None, files: Sequence[str]) -> str:
    """The record: a ``<slug> <snapshot>`` line per region, the jar, the
    profiles, each graph file, then :data:`CONVERTER`."""
    for line in regions:
        if len(line.split()) != 2 or line != " ".join(line.split()):
            raise ValueError(f"a region line is a slug and a snapshot: {line!r}")
    for name in files:
        if not _plain(name) or " " in name:
            raise ValueError(f"a graph file is a plain name: {name!r}")
    lines = [
        *sorted(regions),
        f"program {jar or '-'}",
        f"profiles {' '.join(PROFILES)}",
        *(f"file {name}" for name in sorted(files)),
        f"converter: {CONVERTER}",
    ]
    return "".join(f"{line}\n" for line in lines)


def without_files(record: str) -> str:
    return "".join(
        line for line in record.splitlines(keepends=True) if not line.startswith("file ")
    )


@dataclass(frozen=True)
class Record:
    regions: tuple[str, ...]
    program: str | None
    profiles: tuple[str, ...]
    files: tuple[str, ...]
    converter: str | None


def parse_record(text: str) -> Record | None:
    """The record's parts, or None when it is not one."""
    regions: list[str] = []
    files: list[str] = []
    program = converter = None
    profiles: tuple[str, ...] = ()
    for line in text.splitlines():
        if line.startswith("converter: "):
            converter = line.removeprefix("converter: ")
        elif line.startswith("program "):
            program = line.removeprefix("program ")
        elif line.startswith("profiles "):
            profiles = tuple(line.removeprefix("profiles ").split())
        elif line.startswith("file "):
            files.append(line.removeprefix("file "))
        elif len(line.split()) == 2:
            regions.append(line)
        else:
            return None
    if converter is None:
        return None
    return Record(tuple(regions), program, profiles, tuple(sorted(files)), converter)


@dataclass(frozen=True)
class GraphShelf:
    """What ``reference serve`` has to route with."""

    installed: bool
    why: str | None
    jar: Path | None = None
    files: tuple[Path, ...] = ()
    profiles: tuple[str, ...] = ()
    regions: int = 0

    @property
    def ready(self) -> bool:
        return self.why is None


REBUILD = "`hammunition install graphhopper-graph` rebuilds it"


def find_graph(data: Path, tree: Path) -> GraphShelf:
    """The installed graph under *data* and GraphHopper's jar in *tree*, and
    whether they can be served together."""
    try:
        text = (data / RECORD).read_text()
    except OSError:
        return GraphShelf(
            False,
            "no route graph is installed: set map regions, then "
            "`hammunition install graphhopper-graph`",
        )
    record = parse_record(text)
    if record is None or record.converter != CONVERTER:
        return GraphShelf(True, f"the route graph was built by another converter; {REBUILD}")
    jar = find_jar(tree)
    if jar is None:
        return GraphShelf(
            True,
            f"GraphHopper's jar is not installed in {tree}: `hammunition install graphhopper`",
        )
    if record.program != jar.name:
        return GraphShelf(
            True,
            f"the route graph was built by {record.program} and {jar.name} is installed; {REBUILD}",
        )
    bad = [n for n in record.files if not _plain(n)]
    missing = [n for n in record.files if _plain(n) and not (data / n).is_file()]
    if bad or missing or PROPERTIES not in record.files:
        named = ", ".join([*bad, *missing]) or PROPERTIES
        return GraphShelf(True, f"the route graph is incomplete ({named}); {REBUILD}")
    profiles = tuple(p for p in record.profiles if p in PROFILES)
    if not profiles:
        return GraphShelf(True, f"the route graph names no profile; {REBUILD}")
    return GraphShelf(
        True,
        None,
        jar=jar,
        files=tuple(data / n for n in record.files),
        profiles=profiles,
        regions=len(record.regions),
    )


# -- the route request -----------------------------------------------------------


class RouteRefused(ValueError):
    """A route request that is not two points and a profile this graph has."""


def _point(text: str) -> str:
    parts = text.split(",")
    if len(parts) != 2:
        raise RouteRefused(f"a point is LAT,LON: {text!r}")
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        raise RouteRefused(f"a point is two numbers: {text!r}") from None
    if not (math.isfinite(lat) and math.isfinite(lon)) or abs(lat) > 90 or abs(lon) > 180:
        raise RouteRefused(f"a point is a latitude and a longitude on the globe: {text!r}")
    return f"{lat!r},{lon!r}"  # the numbers as read, never the text sent


def route_query(query: str, profiles: Sequence[str]) -> str:
    """GraphHopper's ``/route`` path and query for a page's request of
    ``point=LAT,LON&point=LAT,LON&profile=P``, built here; anything else is
    refused (:class:`RouteRefused`)."""
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True, max_num_fields=8)
    except ValueError:
        raise RouteRefused("the request is not point=LAT,LON twice and profile=NAME") from None
    extra = sorted({k for k, _ in pairs} - {"point", "profile"})
    if extra:
        raise RouteRefused(f"only point and profile are taken, not {', '.join(extra)}")
    points = [_point(v) for k, v in pairs if k == "point"]
    asked = [v for k, v in pairs if k == "profile"]
    if len(points) != 2:
        raise RouteRefused(f"a route is two points, not {len(points)}")
    if len(asked) != 1:
        raise RouteRefused(f"a route has one profile, one of {', '.join(profiles)}")
    if asked[0] not in profiles:
        raise RouteRefused(
            f"{asked[0]!r} is not a profile of this graph; it has {', '.join(profiles)}"
        )
    profile = asked[0]
    fields = [("point", p) for p in points] + [
        ("profile", profile),
        ("points_encoded", "false"),
        ("instructions", "true"),
        ("calc_points", "true"),
        ("locale", "en"),
    ]
    if profile not in CH_PROFILES:
        # Measured: GraphHopper refuses a profile it prepared no contraction
        # hierarchies for unless asked to route without them (landmarks).
        fields.append(("ch.disable", "true"))
    return "/route?" + urlencode(fields)


# -- what reference serve prepares ------------------------------------------------


class RouterError(Exception):
    """The router cannot be prepared; the message says why."""


@dataclass(frozen=True)
class RouterSpec:
    """A GraphHopper server ready to start: its argv, port and log."""

    argv: list[str]
    port: int
    profiles: tuple[str, ...]
    log: Path
    config: Path


def free_port() -> int:
    """A port on 127.0.0.1 nothing listens on now, chosen by the system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def _write_private(path: Path, text: str) -> None:
    """*text* into *path*, 0600, replacing whatever was there without
    following it: a link left in its place is removed, not written through."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.replace(temporary, path)


def prepare_router(shelf: GraphShelf, home: Path, port: int) -> RouterSpec:
    """In *home* (the operator's cache): ``config.yml``, 0600, and ``graph/``
    refilled with one link per installed graph file. A previous run's links
    and lock are removed; anything else there refuses, untouched."""
    if not shelf.ready or shelf.jar is None:
        raise RouterError(shelf.why or "no route graph is installed")
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.chmod(0o700)
    links = home / "graph"
    if links.is_symlink():
        links.unlink()
    links.mkdir(exist_ok=True, mode=0o700)
    foreign = sorted(p.name for p in links.iterdir() if not p.is_symlink() and p.name != LOCK)
    if foreign:
        raise RouterError(
            f"{links} holds {', '.join(foreign)}, which this did not make; it is left as it "
            f"is and the router is not started"
        )
    for entry in links.iterdir():
        entry.unlink()
    for path in shelf.files:
        (links / path.name).symlink_to(path)
    config = home / "config.yml"
    _write_private(config, serve_config(links, port))
    return RouterSpec(
        argv=server_argv(shelf.jar, config),
        port=port,
        profiles=shelf.profiles,
        log=home / "graphhopper.log",
        config=config,
    )
