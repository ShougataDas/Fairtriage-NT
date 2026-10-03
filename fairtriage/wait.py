"""Wait-time estimation. The system's main output.

Computed twice: for this tenant, and for the identical job in Darwin. The
gap between those two numbers is the fairness measurement, and it falls out
of the product rather than being calculated specially for a slide.

Always a range, never a date. A restricted road makes a firm date a promise
the system cannot keep, and a broken promise does more damage than delay.

    central = lead time for the tier      booking: routine work is programmed,
                                          not dispatched on the day
            + queue ahead                 hours of the SAME trade's work ranked
                                          ahead in the region / that trade's
                                          crew hours per day
            + mobilisation                getting a crew moving to a remote
                                          community (charter, barge, packing)
            + travel by the planner's fastest route

and for a remote Routine job, at least the wait for the next trip there. The
trip planner only goes to a community for an urgent job, or when its oldest
job has waited N x its target, so that is when a routine job is reached.
Showing anything shorter would be a promise the planner does not keep.

v8: the queue term used to be (jobs ahead / all crews) x half a day, so with
12 Darwin crews even 20 jobs ahead added under a day, and every estimate was
the tier's lead time give or take. Now rank, trade and job size all count, the
range widens with real uncertainty, and an open job's estimate is recomputed
live (`elapsed_days`) instead of being frozen at the moment it was lodged.
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

    @property
    def low_hours(self) -> int:
        return max(1, math.floor(self.low * 24))


def trade_crews(trade_region: str, trade: str) -> float:
    """Crews in a region who can do `trade`. A region's crews are split across
    trades by `trade_share`; there is always at least `min_trade_crews`, since
    a contractor can be called in."""
    w = policy()["wait"]
    crews = trade_capacity()[trade_region]["crews"]
    share = w["trade_share"].get(trade, w["trade_share_default"])
    return max(crews * share, w["min_trade_crews"])


def queue_days(hours_ahead: float, trade_region: str, trade: str) -> float:
    """Working days until a crew of this trade reaches the job, given the
    hours of same-trade work ranked ahead of it in the region."""
    per_day = trade_crews(trade_region, trade) * policy()["trips"]["capacity_hours_per_day"]
    return hours_ahead / per_day


def _mobilise(community: str, tier: str) -> float:
    c = communities()[community]
    m = policy()["wait"]["mobilise_days"]
    if c.access == "air_or_barge":
        return m["air_or_barge"][tier]
    return m["remote_road"][tier] if c.remote else 0.0


def _spread(community: str, road: str, queue: float) -> float:
    """How wide the range is: wider where the estimate is less certain."""
    s = policy()["wait"]["spread"]
    x = s["base"]
    if communities()[community].remote:
        x += s["remote"]
    x += s.get(road, 0.0)
    if queue >= 1:
        x += s["long_queue"]
    return min(x, s["max"])


def estimate(community: str, tier: str, hours_ahead: float, hours_ahead_darwin: float,
             trade: str = "Handyperson", trip_scheduled: bool = False,
             trip_wait_days: float | None = None, elapsed_days: float = 0.0,
             jobs_ahead: int | None = None) -> WaitEstimate | None:
    """`hours_ahead`: hours of same-trade work ranked ahead in this job's region
    (`hours_ahead_darwin`: the same, in Darwin). `trip_wait_days`: for a remote
    Routine job, days until the planner's next trip there (0 if one is due now).
    `elapsed_days`: how long the job has already waited; the booking lead time
    is used up first, so a live estimate counts down."""
    if tier == "NotInQueue":
        return None
    w = policy()["wait"]
    t = policy()["trips"]
    c = communities()[community]
    region = c.trade_region
    road = road_of(community)["status"]

    lead = max(w["lead_days"][tier] - elapsed_days, 0.0)
    queue = queue_days(hours_ahead, region, trade)
    darwin_queue = queue_days(hours_ahead_darwin, "Darwin", trade)
    if tier == "Immediate":                 # crews drop other work: the queue runs on the clock
        queue *= t["capacity_hours_per_day"] / 24
        darwin_queue *= t["capacity_hours_per_day"] / 24
    mobilise = _mobilise(community, tier)
    # Travel by the planner's own fastest route, so the estimate and the trip
    # plan agree: restricted roads are already slower on it, and a closed road
    # means the charter it would actually use. Immediate work runs on clock
    # hours; everything else on crew working days.
    from .routing import travel_hours
    hours = travel_hours(trade_capacity()[region]["depot"], community)
    if hours is None:                       # unreachable: fall back to the old estimate
        travel, penalty = travel_days(community), w["road_penalty_days"][road]
    else:
        per_day = 24 if tier == "Immediate" else t["workday_hours"]
        travel, penalty = round(hours / per_day, 2), 0
    discount = w["scheduled_trip_discount_days"] if trip_scheduled else 0.0
    central = max(lead + queue + mobilise + travel + penalty - discount, lead,
                  w["floor_days"][tier])
    waits_for_trip = trip_wait_days is not None and travel_days(community) > 0
    trip_bound = False
    if waits_for_trip and trip_wait_days + travel + penalty > central:
        central, trip_bound = trip_wait_days + travel + penalty, True

    darwin_central = max(w["lead_days"][tier] + darwin_queue + travel_days(DEPOT),
                         w["floor_days"][tier])

    spread = _spread(community, road, queue)
    if trip_bound:          # the planner's own rule sets this date: only travel is uncertain
        spread = min(spread, policy()["wait"]["spread"]["trip_max"])
    return WaitEstimate(
        low=round(central * (1 - spread), 2),
        high=round(central * (1 + spread), 2),
        central=round(central, 2),
        darwin_central=round(darwin_central, 1),
        breakdown={
            "lead_days": round(lead, 2), "elapsed_days": round(elapsed_days, 1),
            "queue_days": round(queue, 2), "hours_ahead": round(hours_ahead, 1),
            "jobs_ahead": jobs_ahead, "trade": trade,
            "trade_crews": round(trade_crews(region, trade), 1),
            "crews_in_region": trade_capacity()[region]["crews"], "trade_region": region,
            "mobilise_days": mobilise,
            "travel_days": travel, "road_status": road,
            "road_penalty_days": penalty, "trip_discount_days": discount,
            "trip_wait_days": round(trip_wait_days, 1) if waits_for_trip else None,
            "spread": round(spread, 2),
            "road_km_est": road_km(trade_capacity()[region]["depot"], community),
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
        lo_h, hi_h = est.low_hours, est.high_hours
        if hi_h <= 1:
            return "within about an hour"
        if lo_h >= hi_h - 1:
            return f"within about {hi_h} hours"
        return f"within about {lo_h} to {hi_h} hours"
    lo_i, hi_i = max(int(round(lo)), 1), max(int(round(hi)), 1)
    if lo_i == hi_i:
        return f"in about {plural_days(lo_i)}"
    return f"in about {lo_i} to {hi_i} days"
