"""Build reference/distance_matrix.csv offline. Run once; the app only reads it.

    python scripts/build_distance_matrix.py

Two distances per pair, named honestly:

  straight_line_km   haversine between community coordinates
  road_km_est        straight-line x a winding factor. An ESTIMATE.

For a production build, replace road_km_est with shortest paths over the NT
Government Controlled Roads KMZ using GeoPandas + networkx (or OSRM). The
column name stays the same, so nothing downstream changes. A routing service
is deliberately not run at demo time: it is a container to babysit and the
answer never changes between runs.

Coordinates in communities.csv are approximate. Say so in the datasheet.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "reference"

WINDING = {"road": 1.35, "air_or_barge": 1.0}


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def main() -> None:
    with open(REF / "communities.csv") as fh:
        rows = list(csv.DictReader(fh))

    out = REF / "distance_matrix.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["from", "to", "straight_line_km", "road_km_est", "method"])
        for a in rows:
            for b in rows:
                sl = haversine((float(a["lat"]), float(a["lon"])),
                               (float(b["lat"]), float(b["lon"])))
                mode = "air_or_barge" if "air_or_barge" in (a["access"], b["access"]) else "road"
                w.writerow([a["community"], b["community"], round(sl, 1),
                            round(sl * WINDING[mode], 1),
                            f"haversine x {WINDING[mode]} ({mode}) - ESTIMATE"])
    print(f"wrote {out} ({len(rows) ** 2} pairs)")


if __name__ == "__main__":
    main()
