"""Build reference/road_network.csv offline. Run once; the app only reads it.

    python scripts/build_road_network.py

The trip planner needs ROUTES, not just distances: two ways to reach the same
community, one faster and one passing more places with open jobs. So this
writes an edge list, three kinds of edge:

  local     Greater Darwin suburbs, joined by a minimum spanning tree over
            straight-line distance x 1.3, plus the Stuart / Arnhem Highway
            trunk from the depot to Coolalinga. Nearly a tree on purpose:
            route alternatives then come from the regional roads, not from a
            hundred near-identical suburban detours.
  highway   Hand-listed regional corridors (Stuart, Arnhem, Kakadu, Daly
            River / Port Keats, Cox Peninsula, Roper). Kilometres and speeds
            are APPROXIMATE, read off a map; replace them from the NT
            Government Controlled Roads KMZ before relying on them.
  air       Charter legs from the Darwin depot to communities with an
            airstrip. Straight-line km, plus fixed handling time.

Road status (closed, restricted) is NOT baked in here. It changes weekly, so
fairtriage/routing.py applies the current snapshot when it loads the network.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "reference"

URBAN_REGION = "Greater Darwin"
URBAN_WINDING = 1.3
URBAN_SPEED = 50
AIR_SPEED = 250
AIR_HANDLING_H = 1.0

# (a, b, km, speed_kmh, road)
HIGHWAYS = [
    # the trunk through Greater Darwin, so the depot is not reached only by
    # zigzagging through suburban streets
    ("Darwin (Ludmilla)", "Darwin (Winnellie)", 5, 60, "Bagot Rd"),
    ("Darwin (Winnellie)", "Darwin (Berrimah)", 5, 80, "Stuart Hwy"),
    ("Darwin (Berrimah)", "Palmerston", 9, 90, "Stuart Hwy"),
    ("Palmerston", "Coolalinga", 9, 90, "Stuart Hwy"),
    ("Coolalinga", "Berry Springs", 22, 100, "Stuart Hwy"),
    ("Coolalinga", "Humpty Doo", 10, 90, "Arnhem Hwy"),
    ("Berry Springs", "Adelaide River", 62, 110, "Stuart Hwy"),
    ("Berry Springs", "Batchelor", 42, 100, "Stuart Hwy / Batchelor Rd"),
    ("Batchelor", "Adelaide River", 38, 90, "Batchelor Rd / Stuart Hwy"),
    ("Adelaide River", "Pine Creek", 112, 110, "Stuart Hwy"),
    ("Pine Creek", "Katherine", 90, 110, "Stuart Hwy"),
    ("Adelaide River", "Peppimenarti", 230, 65, "Daly River Rd / Port Keats Rd (part unsealed)"),
    ("Batchelor", "Peppimenarti", 245, 60, "Litchfield Park Rd / Daly River Rd (unsealed)"),
    ("Peppimenarti", "Wadeye", 95, 60, "Port Keats Rd (unsealed)"),
    ("Berry Springs", "Belyuen", 80, 80, "Cox Peninsula Rd"),
    ("Humpty Doo", "Gunbalanya", 290, 80, "Arnhem Hwy / Oenpelli Rd"),
    ("Pine Creek", "Gunbalanya", 270, 80, "Kakadu Hwy / Oenpelli Rd"),
    ("Gunbalanya", "Maningrida", 300, 50, "Maningrida Rd (dry-season track)"),
    ("Katherine", "Numbulwar", 590, 70, "Stuart Hwy / Roper Hwy (part unsealed)"),
]

AIR_FROM = "Darwin (Ludmilla)"
AIRSTRIPS = ["Wurrumiyanga", "Galiwinku", "Maningrida", "Numbulwar", "Wadeye"]


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def urban_tree(rows: list[dict]) -> list[tuple[str, str, float]]:
    """Prim's minimum spanning tree over the Greater Darwin places."""
    pts = {r["community"]: (float(r["lat"]), float(r["lon"]))
           for r in rows if r["nt_region"] == URBAN_REGION}
    names = sorted(pts)
    inside, edges = {names[0]}, []
    while len(inside) < len(names):
        a, b = min(((x, y) for x in inside for y in names if y not in inside),
                   key=lambda e: haversine(pts[e[0]], pts[e[1]]))
        edges.append((a, b, haversine(pts[a], pts[b]) * URBAN_WINDING))
        inside.add(b)
    return edges


def main() -> None:
    with open(REF / "communities.csv") as fh:
        rows = list(csv.DictReader(fh))
    known = {r["community"]: (float(r["lat"]), float(r["lon"])) for r in rows}

    out = REF / "road_network.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["a", "b", "km", "speed_kmh", "extra_hours", "mode", "road", "note"])
        for a, b, km in urban_tree(rows):
            w.writerow([a, b, round(km, 1), URBAN_SPEED, 0, "road", "local roads",
                        "suburban link, straight-line x 1.3 - ESTIMATE"])
        for a, b, km, speed, road in HIGHWAYS:
            assert a in known and b in known, (a, b)
            w.writerow([a, b, km, speed, 0, "road", road, "approximate - check against NT roads KMZ"])
        for dest in AIRSTRIPS:
            km = haversine(known[AIR_FROM], known[dest])
            w.writerow([AIR_FROM, dest, round(km, 1), AIR_SPEED, AIR_HANDLING_H, "air",
                        "charter flight", "straight line + 1 h handling - ESTIMATE"])
    n = sum(1 for _ in open(out)) - 1
    print(f"wrote {out} ({n} edges)")


if __name__ == "__main__":
    main()
