"""Wait-time estimation. The system's main output.

Computed twice: for this tenant, and for the identical job in Darwin. The
gap between those two numbers is the fairness measurement, and it falls out
of the product rather than being calculated specially for a slide.

Always a range, never a date. A restricted road makes a firm date a promise
the system cannot keep, and a broken promise does more damage than delay.

    central = lead time for the tier      booking: routine work is programmed,
                                          not dispatched on the day
            + queue ahead in the region   jobs ahead / crews x days per job
            + travel + road penalty

and for a remote Routine job, at least the wait for the next trip there. The
trip planner only goes to a community for an urgent job, or when its oldest
job has waited N x its target, so that is when a routine job is reached.
Showing anything shorter would be a promise the planner does not keep.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import policy
from .reference import DEPOT, communities, road_km, road_of, trade_capacity, travel_days


@dataclass
class WaitEstimate:
    low: float
    high: float
    central: float
    darwin_central: float
    breakdown: dict

    @property
    def gap_days(self) -> float:
        return round(self.central - self.darwin_central, 1)

    @property
    def ratio(self) -> float:
        return round(self.central / self.darwin_central, 1) if self.darwin_central else 0.0

    @property
    def high_hours(self) -> int:
        """Upper end in hours, for waits under a day."""
        return max(1, math.ceil(self.high * 24))


def _queue_days(jobs_ahead: int, crews: int) -> float:
    return (jobs_ahead / max(crews, 1)) * policy()["wait"]["mean_job_days"]


def estimate(community: str, tier: str, jobs_ahead_region: int,
             jobs_ahead_darwin: int, trip_scheduled: bool = False,
             trip_wait_days: float | None = None) -> WaitEstimate | None:
    """`trip_wait_days`: for a remote Routine job, days until the planner's next
    trip to the community (0 if one is due now). None if not applicable."""
    if tier == "NotInQueue":
        return None
    w = policy()["wait"]
    c = communities()[community]
    crews = trade_capacity()[c.trade_region]["crews"]
    road = road_of(community)["status"]

    lead = w["lead_days"][tier]
    queue = _queue_days(jobs_ahead_region, crews)
    # Travel by the planner's own fastest route, so the estimate and the trip
    # plan agree: restricted roads are already slower on it, and a closed road
    # means the charter it would actually use. Immediate work runs on clock
    # hours; everything else on crew working days.
    from .routing import travel_hours
    hours = travel_hours(trade_capacity()[c.trade_region]["depot"], community)
    if hours is None:                       # unreachable: fall back to the old estimate
        travel, penalty = travel_days(community), w["road_penalty_days"][road]
    else:
        per_day = 24 if tier == "Immediate" else policy()["trips"]["workday_hours"]
        travel, penalty = round(hours / per_day, 2), 0
    discount = w["scheduled_trip_discount_days"] if trip_scheduled else 0.0
    central = max(lead + queue + travel + penalty - discount, lead)
    waits_for_trip = trip_wait_days is not None and travel_days(community) > 0
    if waits_for_trip:
        central = max(central, trip_wait_days + travel + penalty)

    darwin_crews = trade_capacity()["Darwin"]["crews"]
    darwin_central = lead + _queue_days(jobs_ahead_darwin, darwin_crews) + travel_days(DEPOT)

    spread = w["range_spread"]
    return WaitEstimate(
        low=round(central * (1 - spread), 1),
        high=round(central * (1 + spread), 1),
        central=round(central, 1),
        darwin_central=round(darwin_central, 1),
        breakdown={
            "lead_days": lead,
            "queue_days": round(queue, 2), "jobs_ahead": jobs_ahead_region,
            "crews_in_region": crews, "trade_region": c.trade_region,
            "travel_days": travel, "road_status": road,
            "road_penalty_days": penalty, "trip_discount_days": discount,
            "trip_wait_days": round(trip_wait_days, 1) if waits_for_trip else None,
            "road_km_est": road_km(trade_capacity()[c.trade_region]["depot"], community),
        },
    )


def reachability(community: str, trip_scheduled: bool) -> dict:
    """The SECOND axis. Displayed beside need, never folded into it."""
    c = communities()[community]
    road = road_of(community)
    depot = trade_capacity()[c.trade_region]["depot"]
    km = road_km(depot, community)
    if road["status"] == "closed":
        access = "air only"
    elif km <= 40:
        access = "same day"
    elif road["status"] == "restricted":
        access = "uncertain"
    elif km <= 150:
        access = "1-2 days"
    else:
        access = "trip required"
    return {
        "community": community, "remote": c.remote, "access": access,
        "road_km_est": km, "road_status": road["status"],
        "road_snapshot_at": road["snapshot_at"], "access_mode": c.access,
        "trip_scheduled": trip_scheduled,
        "affects_need": False,        # stated in data, rendered on screen
    }


def plural_days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def fmt_range(est: WaitEstimate) -> str:
    """Phrased to follow 'Expect a tradesperson ...'."""
    lo, hi = est.low, est.high
    if hi < 1:
        return f"within about {est.high_hours} hours" if est.high_hours > 1 else "within about an hour"
    lo_i, hi_i = max(int(round(lo)), 1), max(int(round(hi)), 1)
    if lo_i == hi_i:
        return f"in about {plural_days(lo_i)}"
    return f"in about {lo_i} to {hi_i} days"
