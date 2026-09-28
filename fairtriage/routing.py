"""Road network and alternative routes. No I/O beyond the reference CSVs.

The planner asks one question here: "what are the sensible ways to get from
where the crew is to this community, and what does each pass through?"

Travel time per leg = km / speed (+ fixed handling for a flight). The current
road snapshot is applied at load time: a CLOSED road is removed from the
graph (a closed-road community is then reachable by air only, if at all), a
RESTRICTED road is driven at a reduced speed.

Alternatives are the k fastest simple paths (Yen's algorithm), kept only if
they pass a different set of places and are within a multiple of the
fastest time. A route that is much slower is not an alternative, it is a
detour, and nobody would drive it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import islice
from pathlib import Path

import networkx as nx

from .config import policy, settings
from .reference import communities, road_of

URBAN_REGION = "Greater Darwin"


@dataclass(frozen=True)
class Leg:
    a: str
    b: str
    km: float
    hours: float
    mode: str
    road: str


@dataclass
class Route:
    nodes: list[str]
    legs: list[Leg] = field(default_factory=list)

    @property
    def hours(self) -> float:
        return round(sum(l.hours for l in self.legs), 2)

    @property
    def km(self) -> float:
        return round(sum(l.km for l in self.legs), 1)

    @property
    def by_air(self) -> bool:
        return any(l.mode == "air" for l in self.legs)

    @property
    def waypoints(self) -> list[str]:
        """Places passed on the way that are not suburbs of Darwin."""
        return [n for n in self.nodes[1:-1] if communities()[n].nt_region != URBAN_REGION]

    @property
    def name(self) -> str:
        via = f"via {', '.join(self.waypoints)}" if self.waypoints else "direct"
        return f"{'by air, ' if self.by_air else ''}{via}"

    @property
    def roads(self) -> list[str]:
        out = []
        for l in self.legs:
            if l.road not in out and l.road != "local roads":
                out.append(l.road)
        return out

    def arrival_hours(self) -> dict[str, float]:
        """Driving hours from the start to each node on the route."""
        t, out = 0.0, {self.nodes[0]: 0.0}
        for l in self.legs:
            t += l.hours
            out[l.b] = round(t, 3)
        return out


def _leg_hours(km: float, speed: float, extra: float) -> float:
    return km / max(speed, 1) + extra


@lru_cache
def load_network() -> nx.Graph:
    path = Path(settings().reference_dir) / "road_network.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing. Run: python scripts/build_road_network.py")
    factor = policy()["trips"]["routing"]["restricted_speed_factor"]
    known = communities()
    G = nx.Graph()
    G.add_nodes_from(known)
    with open(path) as fh:
        for r in csv.DictReader(fh):
            a, b = r["a"], r["b"]
            if a not in known or b not in known:
                continue
            speed, mode = float(r["speed_kmh"]), r["mode"]
            status = {road_of(a)["status"], road_of(b)["status"]} if mode == "road" else {"open"}
            if "closed" in status:
                continue
            if "restricted" in status:
                speed *= factor
            km = float(r["km"])
            G.add_edge(a, b, km=km, mode=mode, road=r["road"],
                       hours=_leg_hours(km, speed, float(r["extra_hours"])),
                       restricted="restricted" in status)
    return G


def _route(G: nx.Graph, nodes: list[str]) -> Route:
    legs = []
    for a, b in zip(nodes, nodes[1:]):
        e = G.edges[a, b]
        legs.append(Leg(a, b, e["km"], round(e["hours"], 3), e["mode"],
                        e["road"] + (" - restricted" if e["restricted"] else "")))
    return Route(nodes, legs)


def candidate_routes(src: str, dst: str, G: nx.Graph | None = None) -> list[Route]:
    """Fastest route first, then genuine alternatives. Empty if unreachable."""
    G = G if G is not None else load_network()
    cfg = policy()["trips"]["routing"]
    if src == dst:
        return [Route([src])]
    try:
        paths = nx.shortest_simple_paths(G, src, dst, weight="hours")
        out: list[Route] = []
        seen: set[tuple] = set()
        # Road routes are compared with the fastest ROAD route, flights with the
        # fastest route of any kind. Otherwise a 2-hour charter would rule out
        # every road, and with it every chance of serving jobs on the way; and
        # a silly flight (fly past the job, drive back) would count as an option.
        fastest_any: float | None = None
        fastest_road: float | None = None
        for nodes in islice(paths, cfg["paths_examined"]):
            r = _route(G, nodes)
            fastest_any = r.hours if fastest_any is None else fastest_any
            if not r.by_air and fastest_road is None:
                fastest_road = r.hours
            base = fastest_any if r.by_air else fastest_road
            if r.hours > base * cfg["max_route_ratio"]:
                continue
            sig = (tuple(r.waypoints), r.by_air)
            if sig in seen:
                continue
            seen.add(sig)
            out.append(r)
            if len(out) >= cfg["max_alternatives"]:
                break
        return sorted(out, key=lambda r: r.hours)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def travel_hours(src: str, dst: str, G: nx.Graph | None = None) -> float | None:
    f = fastest(src, dst) if G is None else None
    if G is None:
        return f[0] if f else None
    routes = candidate_routes(src, dst, G)
    return routes[0].hours if routes else None


@lru_cache(maxsize=4096)
def fastest(src: str, dst: str) -> tuple[float, float, bool] | None:
    """(hours, km, by air) of the fastest route, or None if unreachable."""
    routes = candidate_routes(src, dst)
    return (routes[0].hours, routes[0].km, routes[0].by_air) if routes else None


def reset() -> None:
    load_network.cache_clear()
    fastest.cache_clear()
