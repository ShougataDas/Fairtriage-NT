"""Reference data: communities, distances, trade capacity, road status.

Loaded from CSVs at startup, not stored in tables. It changes only when
someone edits a file, and a CSV is reviewable in a pull request.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import settings

DEPOT = "Darwin (Ludmilla)"


@dataclass(frozen=True)
class Community:
    name: str
    nt_region: str
    remote: bool
    lat: float
    lon: float
    access: str
    wet_season_isolation: str
    trade_region: str


def _ref() -> Path:
    return Path(settings().reference_dir)


@lru_cache
def communities() -> dict[str, Community]:
    with open(_ref() / "communities.csv") as fh:
        return {
            r["community"]: Community(
                name=r["community"], nt_region=r["nt_region"],
                remote=r["remote"].strip().lower() == "true",
                lat=float(r["lat"]), lon=float(r["lon"]), access=r["access"],
                wet_season_isolation=r["wet_season_isolation"],
                trade_region=r["trade_region"])
            for r in csv.DictReader(fh)
        }


@lru_cache
def _distances() -> dict[tuple[str, str], tuple[float, float]]:
    path = _ref() / "distance_matrix.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing. Run: python scripts/build_distance_matrix.py")
    with open(path) as fh:
        return {(r["from"], r["to"]): (float(r["straight_line_km"]), float(r["road_km_est"]))
                for r in csv.DictReader(fh)}


def road_km(a: str, b: str) -> float:
    return _distances()[(a, b)][1]


def straight_line_km(a: str, b: str) -> float:
    return _distances()[(a, b)][0]


@lru_cache
def trade_capacity() -> dict[str, dict]:
    with open(_ref() / "trade_capacity.csv") as fh:
        return {r["trade_region"]: {"depot": r["depot_community"],
                                    "crews": int(r["crews"]), "note": r["note"]}
                for r in csv.DictReader(fh)}


@lru_cache
def road_status() -> dict[str, dict]:
    path = _ref() / "road_status_snapshot.csv"
    if not path.exists():
        return {}
    with open(path) as fh:
        return {r["community"]: {"status": r["road_status"],
                                 "snapshot_at": r["snapshot_at"],
                                 "source": r["source"]}
                for r in csv.DictReader(fh)}


def road_of(community: str) -> dict:
    return road_status().get(community, {"status": "open", "snapshot_at": None,
                                         "source": "no snapshot - assumed open"})


def travel_days(community: str) -> float:
    """Days of travel to reach a community from its region's depot."""
    c = communities()[community]
    depot = trade_capacity()[c.trade_region]["depot"]
    km = road_km(depot, community)
    if c.access == "air_or_barge":
        return 1.0 if km > 50 else 0.5
    if km <= 40:
        return 0.0
    if km <= 150:
        return 0.5
    if km <= 350:
        return 1.0
    return 2.0


def reset() -> None:
    for f in (communities, _distances, trade_capacity, road_status):
        f.cache_clear()
    from . import routing           # the road graph is built from these files
    routing.reset()
