"""The scheduling loop: which trips to run, by which route, stopping where.

Separate from the request loop because the clocks differ: a tenant needs an
answer in seconds; trip planning is a decision over everything open, redone
whenever the queue, a priority or a crew's location changes. Merging them
would make ranking depend on scheduling state, which is how efficiency leaks
back into priority. Nothing here changes a tier, a need score or a rank.

TWO TRIGGERS (unchanged)
  urgent_anchor        an Immediate/Urgent job forces a trip
  community_threshold  a community's oldest job has waited N x its target.
                       Without it, a community with no emergencies never
                       gets a truck.

ROUTE AND STOPS, for each trip
  1. Candidate routes from where the crew is to the destination job: the
     fastest, plus slower routes that pass different places (routing.py).
  2. On each route, jobs located ON the route are offered as stops, in need
     order. Never quickest-first: that is efficiency returning through the
     ordering. A stop is accepted only if
       - the trip still has on-site hours for it,
       - the destination job still arrives inside its limit: 75% of its
         remaining time to target (or, if already past target, no more than
         a fixed delay beyond its fastest arrival),
       - no job already on the trip is pushed past its own limit.
  3. Immediate jobs take the fastest route and nothing is added before them.
  4. The route chosen maximises: value of the extra jobs served, minus extra
     travel hours, minus the cost of a charter. Value grows with tier and
     with how long a job has waited.

ACROSS TRIPS
  Trips are given to the region's crews in priority order. If a long trip
  makes a later urgent trip (waiting for the same crew) miss its target, the
  earlier trip is shortened to its fastest route and the reason is recorded.

WAIT TIMES
  Every stop gets an expected arrival: crew start + travel + the on-site
  work at earlier stops. Recomputed on every view; stored when confirmed.

RECORD (on confirm)
  batched jobs: status scheduled, advanced_by = anchor, expected arrival.
  jobs eligible and passed over for capacity: prior_deferrals += 1.
  Nothing on a trip plan ever moves a job down.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import policy
from . import db
from .db import REQUESTS, TEAMS, TRIPS, now
from .policy import sort_key
from .reference import communities, trade_capacity, travel_days
from .routing import Route, candidate_routes, fastest, load_network, needs_trip
from .schemas import Extraction


@dataclass
class Job:
    request_id: str
    tier: str
    need: float
    lodged_at: str
    community: str
    trade: str
    hours: float
    days_open: float
    target_days: float
    evidence: str
    key: tuple = field(default=())
    trade_region: str = ""
    prev_wait_days: float | None = None
    address: str | None = None
    status: str = "ranked"          # before booking: ranked or approved


def _days_since(iso: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 86400


def _load_jobs() -> list[Job]:
    targets = policy()["service_targets_days"]
    jobs = []
    for req in db.open_requests():
        a, dw = req["assessment"], req["dwelling"]
        if not req.get("extraction"):
            continue
        ex = Extraction.model_validate(req["extraction"])
        c = communities()[dw["community"]]
        prev = ((a["wait_days_low"] + a["wait_days_high"]) / 2
                if a.get("wait_days_low") is not None else None)
        jobs.append(Job(
            request_id=req["_id"], tier=a["tier"], need=a["need_score"], lodged_at=req["lodged_at"],
            community=dw["community"], trade=ex.trade or "Handyperson",
            hours=ex.job_hours or 1.0, days_open=_days_since(req["lodged_at"]),
            target_days=targets[a["tier"]]["remote" if c.remote else "urban"],
            evidence=(a.get("facts") or {}).get("evidence", ""),
            key=sort_key(a["tier"], a["need_score"], req["lodged_at"]),
            trade_region=c.trade_region, prev_wait_days=prev, address=dw.get("address"),
            status=req["status"]))
    return jobs


# ---------------------------------------------------------------------------
# Time, limits and value
# ---------------------------------------------------------------------------

def _cfg() -> dict:
    return policy()["trips"]


def slack_hours(j: Job) -> float:
    """Crew hours left before the job passes its service target. Immediate
    targets are clock hours (4 h); the others are days of crew time."""
    if j.tier == "Immediate":
        return (j.target_days - j.days_open) * 24
    return (j.target_days - j.days_open) * _cfg()["workday_hours"]


def job_value(j: Job) -> float:
    r = _cfg()["routing"]
    waited = min(j.days_open / max(j.target_days, 0.01), r["wait_bonus_cap"])
    return r["stop_value"][j.tier] * (1 + waited)


def fmt_hours(h: float) -> str:
    wd = _cfg()["workday_hours"]
    if h < wd:
        return f"{h:.1f} h"
    return f"{h:.1f} h (about {h / wd:.1f} crew days)"


# ---------------------------------------------------------------------------
# Plan structures
# ---------------------------------------------------------------------------

@dataclass
class Stop:
    job: Job
    eta_h: float                 # crew hours from now until work starts
    reason: str

    @property
    def eta_days(self) -> float:
        return round(self.eta_h / _cfg()["workday_hours"], 2)


@dataclass
class RouteOption:
    route: Route
    stops: list[Stop]
    rejected: list[tuple[Job, str]]
    score: float
    feasible: bool
    note: str = ""               # why it could not be chosen, if it could not
    passes: list[Job] = field(default_factory=list)   # eligible jobs on the way, served or not


@dataclass
class TripPlan:
    id: str
    community: str
    trigger: str
    trigger_detail: str
    anchor: Job
    trade: str
    capacity_hours: float
    start: str = ""
    start_offset_h: float = 0.0
    crew: int = 0
    route: Route | None = None
    stops: list[Stop] = field(default_factory=list)      # visit order, anchor included
    left_behind: list = field(default_factory=list)      # (Job, reason)
    options: list[RouteOption] = field(default_factory=list)
    headline: str = ""
    explanation: str = ""
    target_missed: bool = False
    shortened_for: str = ""
    finish_h: float = 0.0
    crew_region: str = ""        # whose crew goes: the soonest to arrive, not always the home region
    crew_note: str = ""          # why, when it is not the home region's crew

    @property
    def batched(self) -> list[tuple[Job, str, float]]:
        """(job, reason, detour) in visit order. Kept for callers of v5."""
        return [(s.job, "anchor" if s.job is self.anchor else s.reason, 0.0) for s in self.stops]

    @property
    def reachable(self) -> bool:
        return self.route is not None


# ---------------------------------------------------------------------------
# One trip
# ---------------------------------------------------------------------------

def _eligible(j: Job, anchor: Job, trade: str) -> str | None:
    """None if the job may ride on this trip, else the reason it may not."""
    cfg = _cfg()
    if cfg["match_trade"] and j.trade != trade:
        return f"{j.trade} not on this trip"
    if (not cfg["stops_include_urban"] and j.community != anchor.community
            and travel_days(j.community) == 0):
        return "served by the daily Darwin crews"
    return None


def _timeline(route: Route, anchor: Job, before: list[Job], after: list[Job],
              offset: float) -> tuple[dict[str, float], float]:
    """Expected arrival for every job, and the time the last job finishes.

    Crew leaves at `offset`, drives the route, and at each place does the
    selected jobs there in need order. At the destination the anchor is done
    first, then the other jobs in that community."""
    drive = route.arrival_hours()
    by_node: dict[str, list[Job]] = {}
    for j in before:
        by_node.setdefault(j.community, []).append(j)
    eta, onsite = {}, 0.0
    for node in route.nodes:
        here = sorted(by_node.get(node, []), key=lambda j: j.key)
        if node == route.nodes[-1]:
            here = [anchor] + sorted(after, key=lambda j: j.key)
        for j in here:
            eta[j.request_id] = offset + drive[node] + onsite
            onsite += j.hours
    return eta, offset + drive[route.nodes[-1]] + onsite


def _limit(j: Job, base_eta: float, is_anchor: bool) -> float:
    """Latest acceptable arrival. Before target: keep a reserve of the time
    left. Already past target: at most a fixed delay beyond `base_eta`."""
    r = _cfg()["routing"]
    slack = slack_hours(j)
    if slack <= 0:
        return base_eta + r["overdue_delay_cap_hours"]
    budget = slack * (1 - r["anchor_slack_reserve"]) if is_anchor else slack
    return max(budget, base_eta)          # never demand faster than possible


def _evaluate(route: Route, fastest: Route, anchor: Job, pool: list[Job], trade: str,
              offset: float, allow_before: bool, capacity: float) -> RouteOption:
    cfg = _cfg()["routing"]
    on_route = set(route.nodes[:-1])
    cands, rejected = [], []
    for j in pool:
        if j.community == anchor.community or (allow_before and j.community in on_route):
            why = _eligible(j, anchor, trade)
            if why:
                if j.community == anchor.community:
                    rejected.append((j, why))
            else:
                cands.append(j)

    passes = [j for j in cands if j.community != anchor.community]
    # the anchor's limit is measured against the fastest possible arrival
    anchor_limit = _limit(anchor, offset + fastest.hours, is_anchor=True)
    before: list[Job] = []
    after: list[Job] = []
    etas, _ = _timeline(route, anchor, before, after, offset)
    feasible = etas[anchor.request_id] <= anchor_limit + 1e-9 or route is fastest
    note = "" if feasible else (f"arrives {etas[anchor.request_id] - offset:.1f} h after "
                                f"leaving, too late for {anchor.request_id}'s limit")
    base = dict(etas)

    for j in sorted(cands, key=lambda j: j.key):        # BY NEED, never quickest-first
        if not feasible:
            break
        onsite = anchor.hours + sum(x.hours for x in before + after) + j.hours
        if onsite > capacity:
            rejected.append((j, "trip at capacity — deferred"))
            continue
        trial_b = before + [j] if j.community != anchor.community else before
        trial_a = after + [j] if j.community == anchor.community else after
        new, _ = _timeline(route, anchor, trial_b, trial_a, offset)
        if new[anchor.request_id] > anchor_limit + 1e-9:
            rejected.append((j, f"stopping here would make {anchor.request_id} arrive "
                                f"after its limit"))
            continue
        pushed = [x for x in before + after
                  if new[x.request_id] > _limit(x, base.get(x.request_id, new[x.request_id]),
                                                False) + 1e-9]
        if pushed:
            rejected.append((j, f"would push {pushed[0].request_id} past its target"))
            continue
        before, after = trial_b, trial_a
        base.update({k: v for k, v in new.items() if k not in base})

    etas, finish = _timeline(route, anchor, before, after, offset)
    stops = []
    order = sorted(before + after + [anchor], key=lambda j: etas[j.request_id])
    for j in order:
        if j is anchor:
            reason = "destination"
        elif j.community == anchor.community:
            reason = "same community"
        elif j.community == route.nodes[0]:
            reason = "where the crew is now"
        else:
            reason = f"on the way ({route.name})"
        stops.append(Stop(j, round(etas[j.request_id], 2), reason))

    extra_h = route.hours - fastest.hours
    value = sum(job_value(j) for j in before)
    score = value - cfg["extra_hour_cost"] * extra_h - (cfg["charter_cost"] if route.by_air else 0)
    return RouteOption(route, stops, rejected, round(score, 2), feasible, note, passes)


def _route_text(start: str, stops: list[Stop], route: Route) -> str:
    places = [start]
    for s in stops:
        if s.job.community != places[-1]:
            places.append(s.job.community)
    return " → ".join(places) + (" (by air)" if route.by_air else "")


def plan_trip(anchor: Job, pool: list[Job], start: str, offset: float = 0.0,
              trigger: str = "urgent_anchor", trigger_detail: str = "",
              force_fastest: str = "", G=None) -> TripPlan:
    """Choose the route and stops for one trip. Pure apart from reading the
    policy and the road network: every input is passed in."""
    t = _cfg()
    capacity = t["capacity_hours_per_day"] * t["trip_days"]
    tp = TripPlan(id=f"TRIP-{uuid.uuid4().hex[:6]}", community=anchor.community,
                  trigger=trigger, trigger_detail=trigger_detail, anchor=anchor,
                  trade=anchor.trade, capacity_hours=capacity, start=start,
                  start_offset_h=round(offset, 2), shortened_for=force_fastest)
    routes = candidate_routes(start, anchor.community, G if G is not None else load_network())
    if not routes:
        tp.headline = f"No route from {start} to {anchor.community}"
        tp.explanation = ("No road is open and there is no flight to this community from "
                          "where the crew is. Arrange access by hand.")
        tp.target_missed = True
        return tp

    fastest = routes[0]
    direct_tier = anchor.tier in t["routing"]["direct_tiers"]
    direct = direct_tier or bool(force_fastest)
    options = []
    for r in routes:
        opt = _evaluate(r, fastest, anchor, pool, anchor.trade, offset,
                        allow_before=True, capacity=capacity)
        if direct and r is not fastest:
            opt.feasible = False
            opt.note = (f"{anchor.request_id} is {anchor.tier}: fastest route only"
                        if direct_tier else f"kept short for {force_fastest}")
        options.append(opt)
    if direct:
        # stops before the destination are not allowed; re-evaluate the fastest
        options[0] = _evaluate(fastest, fastest, anchor, pool, anchor.trade, offset,
                               allow_before=False, capacity=capacity)
    chosen = max((o for o in options if o.feasible), key=lambda o: (o.score, -o.route.hours))

    tp.options, tp.route, tp.stops = options, chosen.route, chosen.stops
    etas = {s.job.request_id: s.eta_h for s in chosen.stops}
    tp.finish_h = round(max(etas.values()) + max(s.job.hours for s in chosen.stops), 2) \
        if chosen.stops else offset
    tp.target_missed = etas[anchor.request_id] > max(slack_hours(anchor), 0) + 1e-9
    tp.headline = "Recommended trip: " + _route_text(start, chosen.stops, chosen.route)

    taken = {s.job.request_id for s in chosen.stops}
    left = [(j, why) for j, why in chosen.rejected if j.request_id not in taken]
    for o in options:
        if o is chosen:
            continue
        for j in o.passes:
            if j.request_id not in taken and all(j.request_id != x.request_id for x, _ in left):
                left.append((j, f"on the route {o.route.name}, which was not chosen"))
    tp.left_behind = left
    tp.explanation = _explain(tp, chosen, options, fastest, direct_tier)
    return tp


def _explain(tp: TripPlan, chosen: RouteOption, options: list[RouteOption],
             fastest: Route, direct_tier: bool) -> str:
    a = tp.anchor
    extra = [s for s in chosen.stops if s.job.community != a.community]
    eta_a = next(s.eta_h for s in chosen.stops if s.job is a)
    slack = slack_hours(a)
    time_left = (f"{fmt_hours(slack)} left before its target" if slack > 0
                 else f"already {fmt_hours(-slack)} past its target")
    best_alt = max((o for o in options if o is not chosen), key=lambda o: len(o.passes),
                   default=None)
    alt_n = len(best_alt.passes) if best_alt else 0
    L = []
    if direct_tier:
        L.append(f"{a.request_id} in {a.community} is {a.tier}, so the fastest route is used "
                 f"({fmt_hours(fastest.hours)} travel) and nothing is added before it.")
        if best_alt and alt_n:
            L.append(f"The route {best_alt.route.name} could have served {alt_n} more "
                     f"job{'s' if alt_n > 1 else ''}, but takes "
                     f"{best_alt.route.hours - fastest.hours:.1f} h longer.")
    elif tp.shortened_for:
        L.append(f"Kept to the fastest route with no stops on the way, so that "
                 f"{tp.shortened_for}, waiting for the same crew, is not pushed past its target.")
    elif extra:
        where = sorted({s.job.community for s in extra}, key=lambda c: next(
            s.eta_h for s in extra if s.job.community == c))
        joined = " and ".join(where) if len(where) <= 2 else ", ".join(where[:-1]) + " and " + where[-1]
        on = "the fastest route" if chosen.route is fastest else f"the route {chosen.route.name}"
        n = len(extra)
        jobs = f"{n} job{'s' if n > 1 else ''}"
        reached = f"it is reached {fmt_hours(eta_a - tp.start_offset_h)} after the crew leaves"
        if slack > 0:
            why = (f"{a.request_id} is {a.tier} with {time_left}, so {jobs} can be done on "
                   f"the way and {reached}.")
        else:
            cap = _cfg()["routing"]["overdue_delay_cap_hours"]
            why = (f"{a.request_id} is {a.tier} and {time_left}, so stops may delay it by at "
                   f"most {cap:g} h; {jobs} fit within that and {reached}.")
        L.append(f"{joined} {'is' if len(where) == 1 else 'are'} on {on} to {a.community}. {why}")
        if chosen.route is not fastest:
            L.append(f"This adds {chosen.route.hours - fastest.hours:.1f} h of travel compared "
                     f"with the fastest route ({fastest.name}).")
    elif chosen.passes:
        why = next((w for j, w in chosen.rejected if j in chosen.passes), "")
        n = len(chosen.passes)
        L.append(f"{n} open job{'s lie' if n > 1 else ' lies'} on the way to {a.community}, "
                 f"but {'none was' if n > 1 else 'it was not'} added"
                 + (f": {why}" if why else "") + f". The fastest route is used "
                 f"({fmt_hours(fastest.hours)}).")
    else:
        L.append(f"No open job that this crew can do lies on a route to {a.community}, so the "
                 f"fastest route is used ({fmt_hours(fastest.hours)}).")
        if best_alt and alt_n:
            L.append(f"The route {best_alt.route.name} passes {alt_n} open "
                     f"job{'s' if alt_n > 1 else ''} but was not worth "
                     f"{best_alt.route.hours - fastest.hours:.1f} h more travel"
                     + (f" ({best_alt.note})" if best_alt.note else "") + ".")
    if chosen.route.by_air:
        L.append("It is a charter flight.")
    if tp.target_missed and slack <= 0 and extra and not direct_tier and not tp.shortened_for:
        pass                                # already said above
    elif tp.target_missed and slack <= 0:
        L.append(f"{a.request_id} is already {fmt_hours(-slack)} past its target; this is the "
                 f"quickest way to reach it now.")
    elif tp.target_missed:
        L.append(f"Even this way {a.request_id} is reached after its target. Escalate: a "
                 f"local contractor, or an earlier start.")
    return " ".join(L)


def next_trip_days(community: str, trade: str, tier: str, target_days: float,
                   exclude: str | None = None) -> float | None:
    """Days until the planner would next send a `trade` crew to `community`.

    Urgent and Immediate jobs trigger their own trip, so None. A routine job
    rides on a trip that is due now (an urgent job of the same trade is open
    there), or waits until the community's oldest job reaches the threshold
    multiple of its target: the same rule `plan()` uses to start a trip."""
    if tier in ("Immediate", "Urgent") or not needs_trip(community):
        return None
    same = [j for j in _load_jobs() if j.community == community and j.trade == trade
            and j.request_id != exclude]
    if any(j.tier in ("Immediate", "Urgent") for j in same):
        return 0.0
    from .tripsettings import threshold
    mult = threshold()            # the coordinator's setting, or the policy file's
    until = [mult * j.target_days - j.days_open for j in same] + [mult * target_days]
    return max(min(until), 0.0)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def team_locations() -> dict[str, str]:
    """Where each region's crews are now. Defaults to the region's depot."""
    locs = {r: c["depot"] for r, c in trade_capacity().items()}
    for t in db.col(TEAMS).find():
        if t["_id"] in locs and t.get("location") in communities():
            locs[t["_id"]] = t["location"]
    return locs


def set_team_location(trade_region: str, location: str) -> None:
    if trade_region not in trade_capacity():
        raise ValueError(f"unknown trade region: {trade_region}")
    if location not in communities():
        raise ValueError(f"unknown community: {location}")
    db.col(TEAMS).update_one({"_id": trade_region},
                             {"$set": {"location": location, "updated_at": now()}}, upsert=True)


# ---------------------------------------------------------------------------
# All trips
# ---------------------------------------------------------------------------

def _triggers(jobs: list[Job]) -> list[tuple[Job, str, str]]:
    remote_jobs = [j for j in jobs if needs_trip(j.community)]
    by_comm: dict[str, list[Job]] = {}
    for j in remote_jobs:
        by_comm.setdefault(j.community, []).append(j)

    anchors, anchored = [], set()
    for comm, js in by_comm.items():
        for j in sorted([j for j in js if j.tier in ("Immediate", "Urgent")], key=lambda j: j.key):
            if (comm, j.trade) not in anchored:
                anchors.append((j, "urgent_anchor", f"{j.tier} job forces a trip"))
                anchored.add((comm, j.trade))

    from .tripsettings import threshold
    mult = threshold()            # the coordinator's setting, or the policy file's
    for comm, js in by_comm.items():
        oldest = max(js, key=lambda j: j.days_open / max(j.target_days, 0.1))
        ratio = oldest.days_open / max(oldest.target_days, 0.1)
        if ratio >= mult and (comm, oldest.trade) not in anchored:
            anchors.append((oldest, "community_threshold",
                            f"trip triggered: oldest job at {ratio:.1f}x target "
                            f"(threshold {mult:.1f}x)"))
            anchored.add((comm, oldest.trade))
    return sorted(anchors, key=lambda a: a[0].key)


def _build(jobs: list[Job], anchors, locations: dict[str, str],
           shorten: dict[str, str]) -> list[TripPlan]:
    G = load_network()
    free: dict[str, list[float]] = {r: [0.0] * max(c["crews"], 1)
                                    for r, c in trade_capacity().items()}
    taken: set[str] = set()
    plans = []
    queue = list(anchors)
    while queue:
        anchor, trigger, detail = queue.pop(0)
        if anchor.request_id in taken:
            continue
        region, crew, why = _pick_crew(anchor, free, locations)
        crews = free[region]
        start = locations[region]
        pool = [j for j in jobs if j.request_id not in taken and j is not anchor]
        tp = plan_trip(anchor, pool, start, crews[crew], trigger, detail,
                       force_fastest=shorten.get(anchor.request_id, ""), G=G)
        tp.crew, tp.crew_region, tp.crew_note = crew, region, why
        if why:
            tp.explanation = f"{why} {tp.explanation}"
        if tp.reachable:
            back = candidate_routes(anchor.community, start, G)
            crews[crew] = tp.finish_h + (back[0].hours if back else 0.0)
            taken.update(s.job.request_id for s in tp.stops)
        plans.append(tp)
        if not queue:
            # An urgent job left off a full trip still needs someone: it gets a
            # trip of its own (another crew, or the same crew once it is free).
            # Without this, overflow from a busy community was only "deferred".
            waiting = sorted((j for j in jobs if j.request_id not in taken
                              and j.tier in ("Immediate", "Urgent") and needs_trip(j.community)
                              and not any(p.anchor is j for p in plans)), key=lambda j: j.key)
            queue = [(j, "urgent_anchor", f"{j.tier} job left off a full trip gets its own")
                     for j in waiting]
    return plans


def _pick_crew(anchor: Job, free: dict[str, list[float]],
               locations: dict[str, str]) -> tuple[str, int, str]:
    """The crew that reaches the destination soonest: when it is free plus the
    fastest route from where it is. The home region's crew keeps the job unless
    another is more than `home_crew_preference_hours` sooner. Arrival time
    only, never cost: Wadeye is in the Katherine region, but with its road out
    the Katherine crew would drive three hours to Darwin to catch the charter
    a Darwin crew can take straight away."""
    home = anchor.trade_region
    bias = _cfg().get("home_crew_preference_hours", 0.5)
    arrive: dict[str, tuple[float, int]] = {}
    for region, crews in free.items():
        f = fastest(locations[region], anchor.community)
        if not f:
            continue
        i = min(range(len(crews)), key=lambda k: crews[k])
        arrive[region] = (crews[i] + f[0], i)
    if not arrive:
        r = home if home in free else next(iter(free))
        return r, min(range(len(free[r])), key=lambda k: free[r][k]), ""
    best = min(arrive, key=lambda r: arrive[r][0] - (bias if r == home else 0.0))
    if best == home or home not in arrive:
        return best, arrive[best][1], ""
    gain = arrive[home][0] - arrive[best][0]
    return best, arrive[best][1], (f"A {best} crew is sent: it reaches {anchor.community} "
                                   f"{fmt_hours(gain)} sooner than the {home} crew.")


# ---------------------------------------------------------------------------
# Daily runs: Darwin, Palmerston and the towns within daily reach
# ---------------------------------------------------------------------------

def _hours(a: str, b: str) -> float:
    if a == b:
        return 0.0
    f = fastest(a, b)
    return f[0] if f else float("inf")


def _visit_order(depot: str, stops: list[Job]) -> list[Job]:
    """Nearest place first, from the depot; jobs in one place stay together
    in queue order. Only the order of driving: never who is on the run."""
    left = list(stops)
    out, here = [], depot
    while left:
        nxt = min(left, key=lambda j: (_hours(here, j.community), j.key))
        same = sorted([j for j in left if j.community == nxt.community], key=lambda j: j.key)
        out += same
        left = [j for j in left if j.community != nxt.community]
        here = nxt.community
    return out


def _driving(depot: str, ordered: list[Job]) -> float:
    """Out through the stops and back to the depot."""
    places = [depot] + [j.community for j in ordered] + [depot]
    return sum(_hours(a, b) for a, b in zip(places, places[1:]))


def _run_route(depot: str, ordered: list[Job]) -> Route:
    nodes, legs = [depot], []
    for j in ordered:
        if j.community == nodes[-1]:
            continue
        rs = candidate_routes(nodes[-1], j.community)
        if not rs:
            continue
        nodes += rs[0].nodes[1:]
        legs += rs[0].legs
    return Route(nodes, legs)


def _daily_runs(jobs: list[Job], plans: list[TripPlan], locations: dict[str, str]) -> list[TripPlan]:
    cfg = _cfg()
    dr = cfg.get("daily_runs") or {}
    if not dr.get("enabled", True):
        return []
    from .wait import trade_crews
    taken = {s.job.request_id for p in plans for s in p.stops}
    cap = cfg["capacity_hours_per_day"]
    day = cfg["workday_hours"]
    max_added = dr.get("max_added_minutes", 30) / 60
    max_stops = dr.get("max_stops", 8)

    pool = [j for j in jobs if j.request_id not in taken and not needs_trip(j.community)]
    runs = []

    capacity = trade_capacity()
    pool = [j for j in pool if j.trade_region in capacity]      # a region with no crews plans nothing

    # Immediate: an on-call make-safe call-out each, straight there, never bundled
    for j in sorted([j for j in pool if j.tier == "Immediate"], key=lambda j: j.key):
        depot = locations.get(j.trade_region) or capacity[j.trade_region]["depot"]
        rs = candidate_routes(depot, j.community)
        route = rs[0] if rs else Route([depot])
        st = Stop(j, round(route.hours, 2), "anchor")
        tp = TripPlan(id=f"SAFE-{uuid.uuid4().hex[:6]}", community=j.community, trigger="make_safe",
                      trigger_detail="on-call make-safe call-out", anchor=j, trade=j.trade,
                      capacity_hours=cap, start=depot, crew=0, crew_region=j.trade_region,
                      route=route, stops=[st])
        tp.options = [RouteOption(route, [st], [], 0.0, True)]
        tp.finish_h = round(route.hours + j.hours, 2)
        tp.target_missed = st.eta_h > max(slack_hours(j), 0) + 1e-9
        tp.headline = f"Make-safe call-out: {depot} → {j.community}"
        tp.explanation = (f"{j.request_id} is Immediate: an on-call {j.trade.lower()} goes straight there to "
                          f"make it safe. Immediate work is never bundled into a day's run.")
        runs.append(tp)

    groups: dict[tuple[str, str], list[Job]] = {}
    for j in pool:
        if j.tier != "Immediate":
            groups.setdefault((j.trade_region, j.trade), []).append(j)

    days_ahead = max(int(dr.get("days_ahead", 1)), 1)
    for (region, trade), js in sorted(groups.items()):
        depot = locations.get(region) or capacity[region]["depot"]
        per_day = max(int(trade_crews(region, trade)), 1)
        # crews leaving today on a remote trip are not free for today's runs
        away_today = sum(1 for p in plans if p.reachable and p.crew_region == region
                         and p.trade == trade and p.start_offset_h == 0)
        waiting = sorted(js, key=lambda j: j.key)
        slots = [(d, k) for d in range(days_ahead)
                 for k in range(max(per_day - away_today, 1) if d == 0 else per_day)]
        for day_no, crew in slots:
            if not waiting:
                break
            offset = day_no * day
            anchor = waiting[0]
            chosen = [anchor]
            for cand in waiting[1:]:
                if len(chosen) >= max_stops:
                    break
                if sum(j.hours for j in chosen) + cand.hours > cap:
                    continue
                before = _driving(depot, _visit_order(depot, chosen))
                trial = _visit_order(depot, chosen + [cand])
                after = _driving(depot, trial)
                if after - before > max_added + 1e-9:
                    continue
                if after + sum(j.hours for j in chosen) + cand.hours > day:
                    continue
                chosen.append(cand)
            ordered = _visit_order(depot, chosen)
            waiting = [j for j in waiting if j not in chosen]

            # expected arrival: driving so far plus the work at earlier stops
            stops, here, clock = [], depot, float(offset)
            for j in ordered:
                clock += _hours(here, j.community)
                stops.append(Stop(j, round(clock, 2), "daily run" if j is not anchor else "anchor"))
                clock += j.hours
                here = j.community
            route = _run_route(depot, ordered)
            tp = TripPlan(id=f"RUN-{uuid.uuid4().hex[:6]}", community=anchor.community,
                          trigger="daily_run",
                          trigger_detail=f"daily run for the {region} {trade} crew",
                          anchor=anchor, trade=trade, capacity_hours=cap, start=depot,
                          crew=crew, crew_region=region, route=route, stops=stops,
                          start_offset_h=float(offset))
            tp.options = [RouteOption(route, stops, [], 0.0, True)]
            tp.finish_h = round(clock, 2)
            tp.target_missed = stops[[s.job for s in stops].index(anchor)].eta_h > max(slack_hours(anchor), 0) + 1e-9
            places = []
            for s in stops:
                if s.job.community not in places:
                    places.append(s.job.community)
            tp.headline = ("Daily run" + (" tomorrow" if day_no == 1 else f" in {day_no} days" if day_no > 1 else "")
                           + ": " + " → ".join([depot] + places))
            extra = len(stops) - 1
            tp.explanation = (
                f"A day's work for a {region} {trade.lower()} crew. It starts with {anchor.request_id}, "
                f"the highest-ranked {trade.lower()} job still waiting ({anchor.tier}, {anchor.community})"
                + (f", and adds {extra} more {trade.lower()} job{'s' if extra != 1 else ''} in need order, "
                   f"each adding no more than {int(max_added * 60)} minutes of driving, while the day has room"
                   if extra else "")
                + ". The visiting order is by road to save driving; it never changes who is served.")
            runs.append(tp)
    return runs


def plan(commit: bool = True, only: str | None = None) -> list[TripPlan]:
    """Recommend trips. `commit` books them; `only` (an anchor request id)
    books just that one trip and leaves the rest as recommendations."""
    jobs = _load_jobs()
    anchors = _triggers(jobs)
    locations = team_locations()
    shorten: dict[str, str] = {}
    plans = _build(jobs, anchors, locations, shorten)

    # A crew away on a long trip is not free for the next urgent one. If a
    # later trip misses its target because it waited for that crew, try the
    # earlier trip on its fastest route with no stops on the way. Keep the
    # change only if it rescues the later job: giving up stops for nothing
    # helps nobody. Bounded: each earlier trip is tried once.
    tried: set[str] = set()
    for _ in range(len(plans)):
        fix = None
        for later in plans:
            if not (later.reachable and later.target_missed and later.start_offset_h > 0):
                continue
            earlier = [p for p in plans if p is not later and p.crew == later.crew
                       and p.anchor.trade_region == later.anchor.trade_region
                       and p.anchor.key < later.anchor.key
                       and p.anchor.request_id not in tried
                       and p.anchor.tier not in _cfg()["routing"]["direct_tiers"]
                       and any(s.job.community != p.community for s in p.stops)]
            if earlier:
                fix = (earlier[-1], later)
                break
        if not fix:
            break
        early, later = fix
        tried.add(early.anchor.request_id)
        trial_shorten = {**shorten,
                         early.anchor.request_id: f"{later.anchor.request_id} in {later.community}"}
        trial = _build(jobs, anchors, locations, trial_shorten)
        rescued = next((p for p in trial if p.anchor.request_id == later.anchor.request_id), None)
        if rescued is not None and not rescued.target_missed:
            shorten, plans = trial_shorten, trial

    plans = plans + _daily_runs(jobs, plans, locations)
    if commit:
        _commit([p for p in plans if p.reachable and (only is None or p.anchor.request_id == only)])
    return plans


# ---------------------------------------------------------------------------
# Persist and display
# ---------------------------------------------------------------------------

def benefit(tp: TripPlan) -> dict | None:
    """What approving this trip buys, against sending each job on its own trip.

    Every figure is recomputed from the plan: travel by the same fastest routes
    the planner uses, arrival times from the plan's own timeline, and the
    earlier estimate each tenant was given."""
    if not tp.reachable:
        return None
    wd = _cfg()["workday_hours"]
    back = fastest(tp.community, tp.start)
    trip_h = tp.route.hours + (back[0] if back else 0.0)
    trip_km = tp.route.km + (back[1] if back else 0.0)
    sep_h = sep_km = 0.0
    for st in tp.stops:
        f = fastest(tp.start, st.job.community) or (0.0, 0.0, False)
        sep_h += 2 * f[0]
        sep_km += 2 * f[1]
    sooner = []
    for st in tp.stops:
        if st.job.prev_wait_days is not None:
            gain = st.job.prev_wait_days - st.eta_h / wd
            if gain >= 0.5:
                sooner.append(round(gain, 1))
    a_eta = next(st.eta_h for st in tp.stops if st.job is tp.anchor)
    direct = tp.start_offset_h + tp.options[0].route.hours if tp.options else a_eta
    slack = slack_hours(tp.anchor)
    n = len(tp.stops)
    b = {
        "jobs": n, "communities": len({st.job.community for st in tp.stops}),
        "trip_hours": round(trip_h, 1), "trip_km": round(trip_km),
        "separate_trips": n, "separate_hours": round(sep_h, 1), "separate_km": round(sep_km),
        "hours_saved": round(max(sep_h - trip_h, 0.0), 1),
        "km_saved": round(max(sep_km - trip_km, 0.0)),
        "sooner_jobs": len(sooner), "sooner_days": round(sum(sooner), 1),
        "destination_delay_h": round(max(a_eta - direct, 0.0), 1),
        "destination_on_time": a_eta <= max(slack, 0.0) + 1e-9,
        "destination_slack_left_h": round(slack - a_eta, 1),
        "on_time_jobs": sum(1 for st in tp.stops if st.eta_h <= max(slack_hours(st.job), 0.0) + 1e-9),
    }
    b["why"] = _why_approve(tp, b)
    return b


def _why_approve(tp: TripPlan, b: dict) -> list[str]:
    a = tp.anchor
    out = []
    if b["jobs"] > 1:
        out.append(f"Fixes {b['jobs']} repairs in one visit instead of {b['separate_trips']} "
                   f"separate trips" + (f", saving about {b['hours_saved']:g} hours of travel "
                                        f"({b['km_saved']:,} km)" if b["hours_saved"] >= 0.5 else "") + ".")
    else:
        out.append(f"Sends a crew for {a.request_id}, the {a.tier} job in {a.community}.")
    if b["sooner_jobs"]:
        out.append(f"{b['sooner_jobs']} tenant{'s are' if b['sooner_jobs'] > 1 else ' is'} reached "
                   f"sooner than they were told, by {b['sooner_days']:g} days in total.")
    if b["destination_delay_h"] >= 0.1:
        tail = (f"still {fmt_hours(b['destination_slack_left_h'])} inside its target"
                if b["destination_on_time"] else "it was already past its target")
        out.append(f"The stops add {b['destination_delay_h']:g} h before reaching {a.community}; "
                   f"{tail}.")
    elif a.tier in _cfg()["routing"]["direct_tiers"]:
        out.append(f"Goes straight to the {a.tier} job by the fastest route.")
    overdue = sum(1 for st in tp.stops if slack_hours(st.job) <= 0)
    made_late = sum(1 for st in tp.stops
                    if 0 < slack_hours(st.job) < st.eta_h - 1e-9)
    if overdue:
        out.append(f"{overdue} job{'s were' if overdue > 1 else ' was'} already past target; "
                   f"this trip reaches {'them' if overdue > 1 else 'it'} as soon as this crew can.")
    if made_late:
        out.append(f"{made_late} job{'s' if made_late > 1 else ''} would still be reached after "
                   f"target: consider an earlier start or another crew.")
    return out


def _cost(tp: TripPlan) -> dict | None:
    """Shown beside the plan, never used to make it: see cost.py."""
    from .cost import trip_cost
    return trip_cost(tp)


def to_dict(tp: TripPlan) -> dict:
    wd = _cfg()["workday_hours"]
    cs = communities()
    names = set(tp.route.nodes if tp.route else []) | {s.job.community for s in tp.stops} | {tp.start}
    for o in tp.options:
        names |= set(o.route.nodes)
    return {
        "id": tp.id, "community": tp.community, "trigger": tp.trigger,
        "trigger_detail": tp.trigger_detail, "trade": tp.trade, "anchor": tp.anchor.request_id,
        "start": tp.start, "crew": tp.crew + 1, "crew_region": tp.crew_region or tp.anchor.trade_region,
        "crew_note": tp.crew_note, "start_offset_h": tp.start_offset_h,
        "headline": tp.headline, "explanation": tp.explanation,
        "target_missed": tp.target_missed, "capacity_hours": tp.capacity_hours,
        "route": None if not tp.route else {
            "name": tp.route.name, "roads": tp.route.roads, "nodes": tp.route.nodes, "hours": tp.route.hours,
            "km": tp.route.km, "by_air": tp.route.by_air,
            "legs": [l.__dict__ for l in tp.route.legs]},
        "coords": {n: [cs[n].lat, cs[n].lon] for n in names if n in cs},
        "benefit": benefit(tp),
        "cost": _cost(tp),
        "stops": [{"order": i, "request_id": s.job.request_id, "community": s.job.community,
                   "address": s.job.address, "trade": s.job.trade, "evidence": s.job.evidence,
                   "tier": s.job.tier, "need": s.job.need, "reason": s.reason,
                   "eta_hours": s.eta_h, "eta_days": s.eta_days,
                   "prev_wait_days": s.job.prev_wait_days,
                   "slack_hours": round(slack_hours(s.job), 1),
                   "on_time": s.eta_h <= max(slack_hours(s.job), 0) + 1e-9}
                  for i, s in enumerate(tp.stops, 1)],
        "options": [{"name": o.route.name, "hours": o.route.hours, "km": o.route.km,
                     "nodes": o.route.nodes, "modes": [l.mode for l in o.route.legs],
                     "extra_hours": round(o.route.hours - tp.options[0].route.hours, 2),
                     "by_air": o.route.by_air, "score": o.score,
                     "serves": len([s for s in o.stops if s.job.community != tp.community]),
                     "passes": len(o.passes),
                     "chosen": o.route is tp.route, "feasible": o.feasible, "note": o.note}
                    for o in tp.options],
        "left_behind": [{"request_id": j.request_id, "community": j.community,
                         "tier": j.tier, "reason": r} for j, r in tp.left_behind],
        "workday_hours": wd,
    }


def _commit(plans: list[TripPlan], actor: str = "coordinator-demo") -> None:
    now_dt = datetime.now(timezone.utc)
    wd = _cfg()["workday_hours"]
    booked = {st.job.request_id for tp in plans for st in tp.stops}
    for tp in plans:
        d = to_dict(tp)
        db.col(TRIPS).insert_one({
            "_id": tp.id, "community": tp.community, "anchor_request_id": tp.anchor.request_id,
            "trigger": tp.trigger, "trade": tp.trade, "capacity_hours": tp.capacity_hours,
            "jobs": [{"request_id": j.request_id, "community": j.community,
                      "tier": j.tier, "reason": r, "detour_km": 0.0,
                      "eta_hours": st["eta_hours"], "eta_days": st["eta_days"],
                      "address": j.address, "prev_status": j.status, "removed": False}
                     for (j, r, _), st in zip(tp.batched, d["stops"])],
            "left_behind": d["left_behind"], "start": tp.start, "headline": tp.headline,
            "explanation": tp.explanation, "route": d["route"], "options": d["options"],
            "benefit": d["benefit"], "cost": d["cost"], "created_at": now(),
            "status": "approved",
            # jobs this approval passed over for lack of room: undone on cancel
            "deferred": [j.request_id for j, reason in tp.left_behind
                         if "capacity" in reason and j.request_id not in booked],
            "history": [{"action": "approved", "at": now(), "actor": actor, "reason": None}]})
        n = len(tp.stops)
        for i, st in enumerate(tp.stops, 1):
            fields = {"status": "scheduled", "trip_id": tp.id, "trip_stop": i, "trip_stops": n,
                      "eta_at": (now_dt + timedelta(days=st.eta_h / wd)).isoformat(timespec="seconds")}
            if st.job is not tp.anchor:
                fields["advanced_by"] = tp.anchor.request_id
            db.update_request(st.job.request_id, fields)
        for j, reason in tp.left_behind:
            if "capacity" in reason and j.request_id not in booked:   # passed over
                db.update_request(j.request_id, {}, inc={"prior_deferrals": 1})


def trips_view() -> list[dict]:
    return [{"id": t["_id"], "community": t["community"], "anchor": t["anchor_request_id"],
             "trigger": t["trigger"], "trade": t["trade"], "capacity_hours": t["capacity_hours"],
             "jobs": t.get("jobs", []), "left_behind": t.get("left_behind", []),
             "start": t.get("start"), "headline": t.get("headline"),
             "explanation": t.get("explanation"), "route": t.get("route"),
             "benefit": t.get("benefit"), "cost": t.get("cost"), "created_at": t["created_at"],
             "status": t.get("status", "approved"), "history": t.get("history", []),
             "active_jobs": sum(1 for j in t.get("jobs", []) if not j.get("removed"))}
            for t in db.col(TRIPS).find().sort("created_at", -1)]


# ---------------------------------------------------------------------------
# Changing an approval. Nothing is deleted: the trip keeps every job it ever
# had, marked, and a dated history of who changed what and why.
# ---------------------------------------------------------------------------

class TripError(Exception):
    pass


def _trip(trip_id: str) -> dict:
    t = db.col(TRIPS).find_one({"_id": trip_id})
    if t is None:
        raise KeyError(trip_id)
    if t.get("status", "approved") != "approved":
        raise TripError(f"this trip is already {t['status']}")
    return t


def _release(t: dict, job: dict, why: str, actor: str) -> bool:
    """Put one job back in the queue, as it was before the trip booked it.
    Only touches the request if it is still booked on THIS trip."""
    from .db import DECISIONS
    req = db.get_request(job["request_id"])
    if not req or req.get("trip_id") != t["_id"] or req["status"] != "scheduled":
        return False
    fields = {"status": job.get("prev_status") or "ranked", "trip_id": None,
              "trip_stop": None, "trip_stops": None, "eta_at": None}
    if req.get("advanced_by") == t["anchor_request_id"]:
        fields["advanced_by"] = None
    db.update_request(job["request_id"], fields)
    db.append(DECISIONS, {"request_id": job["request_id"], "actor": actor, "action": why,
                          "from_tier": job.get("tier"), "to_tier": job.get("tier"),
                          "reason": f"trip {t['_id']}"})
    return True


def _need_reason(reason: str | None) -> str:
    if not reason or len(reason.strip()) < 3:
        raise TripError("give a reason: it is kept with the trip's history")
    return reason.strip()


def cancel_trip(trip_id: str, reason: str | None, actor: str = "coordinator-demo") -> dict:
    """Withdraw an approval. Its jobs go back to the queue, tenants stop seeing
    the trip, and the jobs it passed over are no longer counted as deferred."""
    reason = _need_reason(reason)
    t = _trip(trip_id)
    released = sum(_release(t, j, "trip_cancelled", actor) for j in t["jobs"] if not j.get("removed"))
    for rid in t.get("deferred", []):
        db.col(REQUESTS).update_one({"_id": rid, "prior_deferrals": {"$gt": 0}},
                                    {"$inc": {"prior_deferrals": -1}})
    db.col(TRIPS).update_one({"_id": trip_id}, {
        "$set": {"status": "cancelled"},
        "$push": {"history": {"action": "cancelled", "at": now(), "actor": actor,
                              "reason": reason, "jobs_returned": released}}})
    return next(v for v in trips_view() if v["id"] == trip_id)


def remove_from_trip(trip_id: str, request_id: str, reason: str | None,
                     actor: str = "coordinator-demo") -> dict:
    """Take one job off an approved trip; it goes back to the queue. A trip left
    with no jobs is cancelled."""
    reason = _need_reason(reason)
    t = _trip(trip_id)
    job = next((j for j in t["jobs"] if j["request_id"] == request_id and not j.get("removed")), None)
    if job is None:
        raise TripError(f"{request_id} is not on this trip")
    _release(t, job, "removed_from_trip", actor)
    db.col(TRIPS).update_one({"_id": trip_id, "jobs.request_id": request_id},
                             {"$set": {"jobs.$.removed": True},
                              "$push": {"history": {"action": "job_removed", "at": now(),
                                                    "actor": actor, "reason": reason,
                                                    "request_id": request_id}}})
    left = [j for j in db.col(TRIPS).find_one({"_id": trip_id})["jobs"] if not j.get("removed")]
    if not left:
        db.col(TRIPS).update_one({"_id": trip_id}, {
            "$set": {"status": "cancelled"},
            "$push": {"history": {"action": "cancelled", "at": now(), "actor": actor,
                                  "reason": "every job was removed"}}})
    return next(v for v in trips_view() if v["id"] == trip_id)


def complete_trip(trip_id: str, actor: str = "coordinator-demo") -> dict:
    """The crew has done the work: the trip's jobs are closed as completed."""
    t = _trip(trip_id)
    done = 0
    for j in t["jobs"]:
        if j.get("removed"):
            continue
        req = db.get_request(j["request_id"])
        if req and req.get("trip_id") == trip_id and req["status"] == "scheduled":
            db.update_request(j["request_id"], {"status": "completed", "completed_at": now()})
            done += 1
    db.col(TRIPS).update_one({"_id": trip_id}, {
        "$set": {"status": "completed", "completed_at": now()},
        "$push": {"history": {"action": "completed", "at": now(), "actor": actor,
                              "reason": None, "jobs_completed": done}}})
    return next(v for v in trips_view() if v["id"] == trip_id)
