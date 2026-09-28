"""Fairness measurements. Numbers, not assurances.

  rank_location_invariance  share of jobs whose rank equals their
                            location-free rank. Must be 100%.
  wait_gap                  remote vs urban expected wait, by tier. The gap
                            is travel, and this is where it becomes visible.
  deferrals_by_remoteness   are remote jobs passed over more often?
  passenger_share           of remote jobs scheduled, what share rode on
                            someone else's trip rather than their own?
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from . import db
from .db import REQUESTS, TRIPS
from .reference import communities


def equity() -> dict:
    rows = list(db.col(REQUESTS).find({"assessment": {"$ne": None}}))
    trips = list(db.col(TRIPS).find())

    inv_total = inv_ok = 0
    waits = defaultdict(lambda: {"remote": [], "urban": []})
    darwin_eq = defaultdict(list)
    deferrals = {"remote": [], "urban": []}

    for req in rows:
        a = req["assessment"]
        if a["tier"] == "NotInQueue":
            continue
        remote = communities()[req["dwelling"]["community"]].remote
        band = "remote" if remote else "urban"
        facts = a.get("facts") or {}
        if facts.get("rank") is not None:
            inv_total += 1
            inv_ok += int(facts.get("rank") == facts.get("darwin_rank"))
        if a.get("wait_days_low") is not None:
            central = (a["wait_days_low"] + a["wait_days_high"]) / 2
            waits[a["tier"]][band].append(central)
            darwin_eq[a["tier"]].append(a["wait_days_darwin"])
        deferrals[band].append(req.get("prior_deferrals", 0))

    gap = {}
    for tier, d in waits.items():
        r = round(mean(d["remote"]), 1) if d["remote"] else None
        u = round(mean(d["urban"]), 1) if d["urban"] else None
        gap[tier] = {"remote_days": r, "urban_days": u,
                     "gap_days": round(r - u, 1) if r is not None and u is not None else None,
                     "ratio": round(r / u, 1) if r and u else None,
                     "n_remote": len(d["remote"]), "n_urban": len(d["urban"])}

    passengers = own = 0
    for t in trips:
        for j in t.get("jobs", []):
            if communities()[j["community"]].remote:
                if j["reason"] == "anchor":
                    own += 1
                else:
                    passengers += 1

    return {
        "rank_location_invariance": {
            "checked": inv_total,
            "identical": inv_ok,
            "pct": round(100 * inv_ok / inv_total, 1) if inv_total else None},
        "wait_gap_by_tier": gap,
        "deferrals": {b: {"mean": round(mean(v), 2) if v else 0,
                          "at_or_above_2": sum(1 for x in v if x >= 2), "n": len(v)}
                      for b, v in deferrals.items()},
        "remote_jobs_scheduled": {
            "on_own_trip": own, "as_passengers": passengers,
            "passenger_share_pct": round(100 * passengers / (own + passengers), 1)
            if (own + passengers) else None},
    }
