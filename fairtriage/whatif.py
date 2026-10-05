"""What if the trip threshold were different? The equity trade-off, priced.

For each setting of `community_threshold_multiple`, from the remote routine
work waiting today:

    longest wait      threshold x target + travel: a routine job reported
                      just after a trip waits for the next one
    average wait      about half the interval between trips, plus travel
    trips per month   each community with routine work gets a trip every
                      threshold x target days (more if the work outgrows one
                      trip's on-site hours)
    cost per month    those trips, costed by cost.py on the planner's routes

beside the Darwin routine wait today. The figures are planning estimates from
the current queue: demand per community is read from the jobs open now
(Little's law: jobs waiting / the average wait under the current setting),
so the same repair work is costed under every setting. They show the shape of the
trade-off, so the coordinator decides it knowingly; they are not a forecast.
"""

from __future__ import annotations

import math
from statistics import median

from .config import policy
from .cost import JobWork, estimate as trip_cost
from .reference import communities, trade_capacity
from .routing import candidate_routes, needs_trip, travel_hours

STEPS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def _best_depot(community: str) -> str | None:
    best = None
    for c in trade_capacity().values():
        h = travel_hours(c["depot"], community)
        if h is not None and (best is None or h < best[0]):
            best = (h, c["depot"])
    return best[1] if best else None


def scenarios() -> dict:
    from . import tripsettings
    from .scheduler import _load_jobs
    from .service import queue_view

    pol = policy()
    target = pol["service_targets_days"]["Routine"]["remote"]
    wd = pol["trips"]["workday_hours"]
    capacity = pol["trips"]["capacity_hours_per_day"] * pol["trips"]["trip_days"]
    now_value = tripsettings.threshold()

    jobs = [j for j in _load_jobs() if j.tier == "Routine" and needs_trip(j.community)]
    groups: dict[tuple[str, str], list] = {}
    for j in jobs:
        groups.setdefault((j.community, j.trade), []).append(j)

    # per group: demand, travel and a costed trip shape, computed once
    info = []
    for (comm, trade), js in groups.items():
        depot = _best_depot(comm)
        if depot is None:
            continue
        out = candidate_routes(depot, comm)
        back = candidate_routes(comm, depot)
        if not out:
            continue
        # demand from the setting in force: under threshold m a routine job
        # waits about m x target / 2 on average, so jobs waiting now / that =
        # jobs arriving a day (Little's law). The repair work is the same
        # whatever the setting; what changes is how often a crew travels.
        rate = len(js) / max(now_value * target / 2, 1.0)
        hours = sum(j.hours for j in js) / len(js)
        info.append({"community": comm, "trade": trade, "n": len(js), "rate": rate, "hours": hours,
                     "travel_days": out[0].hours / wd, "out": out[0].legs,
                     "back": back[0].legs if back else list(reversed(out[0].legs))})
    for g in info:                    # jobs on one trip under the current setting
        g["k_now"] = max(1, round(g["rate"] * now_value * target))

    # what a Darwin-area routine tenant is told when they report (not the
    # countdown of jobs already waiting, which reaches a day for overdue ones)
    darwin = [((r["told_low"] or 0) + (r["told_high"] or 0)) / 2 for r in queue_view(tier="Routine")
              if not needs_trip(r["community"]) and r["told_low"] is not None]
    darwin_days = round(median(darwin), 1) if darwin else float(pol["wait"]["lead_days"]["Routine"])

    cache: dict[tuple, dict] = {}

    def cost_of(g: dict, k: int) -> dict:
        key = (g["community"], g["trade"], k)
        if key not in cache:
            cache[key] = trip_cost(g["out"], g["back"], [JobWork(g["trade"], g["hours"])] * k,
                                   g["trade"], False, [g["community"]])
        return cache[key]

    values = sorted(set(STEPS) | {round(now_value, 2)})
    out_rows = []
    for m in values:
        interval = m * target
        if not info:
            out_rows.append({"multiple": m, "interval_days": round(interval, 1), "wait_max_days": None,
                             "wait_avg_days": None, "ratio_vs_darwin": None, "trips_per_month": 0,
                             "cost_month_low": 0, "cost_month_high": 0, "current": m == round(now_value, 2)})
            continue
        trips = lo = hi = 0.0
        w_max, w_avg, weight = [], 0.0, 0
        for g in info:
            per_interval = max(1.0, g["rate"] * interval)              # jobs gathered between trips
            visits = max(1, math.ceil(per_interval * g["hours"] / capacity))
            per_month = 30.0 / interval * visits
            # every setting is priced with the trip as it is today, so the
            # cost follows the number of trips: the travel a setting buys
            c = cost_of(g, g["k_now"])
            trips += per_month
            lo += per_month * c["low"]
            hi += per_month * c["high"]
            w_max.append(interval + g["travel_days"])
            w_avg += (interval / 2 + g["travel_days"]) * g["n"]
            weight += g["n"]
        avg = w_avg / weight
        out_rows.append({
            "multiple": m, "interval_days": round(interval, 1),
            "wait_max_days": round(median(w_max)), "wait_avg_days": round(avg),
            "ratio_vs_darwin": round(avg / darwin_days, 1) if darwin_days else None,
            "trips_per_month": round(trips, 1),
            "cost_month_low": int(round(lo, -2)), "cost_month_high": int(round(hi, -2)),
            "current": m == round(now_value, 2),
        })

    return {
        "setting": tripsettings.current(), "history": tripsettings.history(),
        "limits": list(tripsettings.LIMITS), "target_days": target,
        "darwin_routine_days": darwin_days,
        "remote_routine_open": len(jobs), "communities": len({g["community"] for g in info}),
        "scenarios": out_rows,
        "assumptions": [
            f"Remote Routine target {target:g} days; a community gets a trip when its oldest routine "
            f"job has waited the threshold times that.",
            "Demand per community is read from the routine jobs waiting there now.",
            f"A trip carries up to {capacity:g} hours of on-site work; more work means more visits.",
            "Each setting is priced with trips the size they are today, so the cost shows the "
            "travel a setting adds or saves. Costs use the trip cost model and its placeholder rates.",
            "Urgent and Immediate jobs get their own trips whatever this setting is.",
        ],
    }
