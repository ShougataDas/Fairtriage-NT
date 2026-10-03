"""Probable trip cost: a range for the whole of a recommended trip.

Shown beside the recommendation so staff can budget and compare. It is never
used to decide who is served or in what order. A trip to a remote community
costs more, and that must not push its tenants back: the ranking has no cost
term, and this module is only called when a trip is displayed or stored.

    transport   fuel (road km x litres/100 km x price), vehicle running costs,
                charter flights and landing fees
    logistics   accommodation and meals for nights away, freight and a
                community vehicle when flying in; tolls, parking and land
                permits listed at $0 so it is clear they were considered
    labour      every person on the trip, for travel hours and on-site hours,
                with overtime past the ordinary day and an after-hours
                loading when the destination job is Immediate
    other       parts and materials per job, and a stated contingency

Every figure is [low, high] in AUD excluding GST, from `trip_cost` in the
policy. Low uses the low end of every input and high the high end, so the
range is wide on purpose: it is an estimate for planning, not a quote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import policy
from .reference import communities


@dataclass
class JobWork:
    trade: str
    hours: float


def _cfg() -> dict:
    return policy()["trip_cost"]


def _r10(x: float) -> int:
    return int(round(x / 10.0) * 10)


def _rough(leg) -> bool:
    road = (leg.road or "").lower()
    return "unsealed" in road or "restricted" in road


def _line(label: str, lo: float, hi: float, basis: str) -> dict:
    return {"label": label, "low": _r10(lo), "high": _r10(hi), "basis": basis}


def _group(key: str, label: str, lines: list[dict]) -> dict:
    return {"key": key, "label": label, "lines": lines,
            "low": sum(l["low"] for l in lines), "high": sum(l["high"] for l in lines)}


def estimate(out_legs: list, back_legs: list, jobs: list[JobWork], trade: str,
             immediate: bool, places: list[str]) -> dict:
    """Cost of one trip: drive or fly out along `out_legs`, do `jobs`, come
    home along `back_legs`. `places` are the communities visited."""
    c = _cfg()
    v, air, crew, lg = c["vehicle"], c["charter"], c["crew"], c["logistics"]
    wd = policy()["trips"]["workday_hours"]
    legs = list(out_legs) + list(back_legs)
    road = [l for l in legs if l.mode != "air"]
    flights = [l for l in legs if l.mode == "air"]

    road_km = sum(l.km for l in road)
    rough_km = sum(l.km for l in road if _rough(l))
    litres = ((road_km - rough_km) + rough_km * v["unsealed_factor"]) * v["litres_per_100km"] / 100
    travel_h = sum(l.hours for l in legs)
    flight_h = sum(l.km for l in flights) / air["cruise_kmh"]
    onsite = sum(j.hours for j in jobs)
    setup = c["setup_hours_per_stop"] * len(jobs)
    remote = any(communities()[p].remote for p in places if p in communities())

    def scenario(k: int) -> dict:
        """k = 0: every input at its low end; k = 1: at its high end."""
        work_h = onsite * c["job_hours_range"][k] + setup
        total_h = travel_h + work_h
        days = max(1, math.ceil(total_h / wd))
        nights = days - 1
        people = crew["tradespeople"] + (crew["assistant_on_remote_trips"]
                                         if (remote or nights or flights or rough_km) else 0)
        overnight = nights > 0
        repositions = 2 if (flights and overnight and air["reposition_when_overnight"]) else 1
        landings = len(flights) * repositions
        ordinary = days * c["ordinary_hours_per_day"]
        overtime = max(total_h - ordinary, 0.0)
        paid_h = total_h + overtime * c["overtime_loading"]
        loading = c["immediate_callout_loading"][k] if immediate else 0.0
        rate = c["labour_rate_per_hour"].get(trade, c["labour_rate_per_hour"]["Handyperson"])[k]
        mat = sum(c["materials_per_job"].get(j.trade, c["materials_per_job"]["Handyperson"])[k]
                  for j in jobs)
        return {"work_h": work_h, "total_h": total_h, "days": days, "nights": nights,
                "people": people, "landings": landings, "repositions": repositions,
                "overtime": overtime, "paid_h": paid_h, "loading": loading, "rate": rate,
                "assistant_rate": c["labour_rate_per_hour"]["assistant"][k],
                "materials": mat, "overnight": overnight}

    lo, hi = scenario(0), scenario(1)

    transport = []
    if road_km:
        transport.append(_line(
            "Fuel", litres * v["fuel_price_per_litre"][0], litres * v["fuel_price_per_litre"][1],
            f"{road_km:,.0f} km by road, about {litres:,.0f} L at {v['litres_per_100km']:g} L/100 km"
            + (f" ({rough_km:,.0f} km unsealed or restricted, {v['unsealed_factor']:g}x)" if rough_km else "")
            + f", ${v['fuel_price_per_litre'][0]:.2f} to ${v['fuel_price_per_litre'][1]:.2f} a litre"))
        transport.append(_line(
            "Vehicle running costs", road_km * v["running_cost_per_km"][0] * (1 + 0.5 * rough_km / road_km),
            road_km * v["running_cost_per_km"][1] * (1 + 0.5 * rough_km / road_km),
            f"tyres, servicing and wear, ${v['running_cost_per_km'][0]:.2f} to "
            f"${v['running_cost_per_km'][1]:.2f} a km"))
    if flights:
        transport.append(_line(
            "Charter flights", flight_h * lo["repositions"] * air["rate_per_flight_hour"][0],
            flight_h * hi["repositions"] * air["rate_per_flight_hour"][1],
            f"{air['aircraft']}, about {flight_h:.1f} flight hours"
            + (" billed twice: the aircraft goes home and comes back for the crew"
               if hi["repositions"] > 1 else "")
            + f", ${air['rate_per_flight_hour'][0]:,} to ${air['rate_per_flight_hour'][1]:,} an hour"))
        transport.append(_line(
            "Landing fees", lo["landings"] * air["landing_fee"][0], hi["landings"] * air["landing_fee"][1],
            f"{hi['landings']} landing{'s' if hi['landings'] != 1 else ''} at community airstrips"))

    logistics = []
    if hi["nights"]:
        logistics.append(_line(
            "Accommodation",
            lo["nights"] * lo["people"] * lg["accommodation_per_person_night"][0],
            hi["nights"] * hi["people"] * lg["accommodation_per_person_night"][1],
            f"{lo['nights']}" + (f" to {hi['nights']}" if hi["nights"] != lo["nights"] else "")
            + f" night{'s' if hi['nights'] != 1 else ''} away for {hi['people']} "
            f"{'people' if hi['people'] != 1 else 'person'}"))
    meals_lo = lo["days"] * lo["people"] * (lg["meals_per_person_day_overnight"][0] if lo["overnight"]
                                            else lg["meals_per_person_day_day_trip"][0])
    meals_hi = hi["days"] * hi["people"] * (lg["meals_per_person_day_overnight"][1] if hi["overnight"]
                                            else lg["meals_per_person_day_day_trip"][1])
    logistics.append(_line("Meals and travel allowance", meals_lo, meals_hi,
                           f"{hi['days']} day{'s' if hi['days'] != 1 else ''} for {hi['people']} "
                           f"{'people' if hi['people'] != 1 else 'person'}"))
    if flights:
        logistics.append(_line("Tools and parts freight", *lg["freight_air_trip"],
                               "flown in with the crew"))
        logistics.append(_line(
            "Vehicle in the community", lo["days"] * lg["local_vehicle_per_day_air_trip"][0],
            hi["days"] * lg["local_vehicle_per_day_air_trip"][1],
            "hire of a community vehicle after flying in"))
    logistics.append(_line("Tolls and parking", 0, 0,
                           "none: the NT has no toll roads, and no paid parking outside Darwin city"))
    if remote:
        logistics.append(_line("Aboriginal land permit", 0, 0,
                               "no fee, but apply to the land council before travelling"))

    labour = [_line(
        f"{trade} ({crew['tradespeople']})",
        lo["paid_h"] * lo["rate"] * crew["tradespeople"],
        hi["paid_h"] * hi["rate"] * crew["tradespeople"] * (1 + hi["loading"]),
        f"{travel_h:.1f} h travel + {lo['work_h']:.1f} to {hi['work_h']:.1f} h on site"
        + (f", overtime past {c['ordinary_hours_per_day']:g} h a day" if hi["overtime"] > 0 else "")
        + f", ${lo['rate']} to ${hi['rate']} an hour"
        + (f", up to {hi['loading']:.0%} after-hours loading (Immediate)" if immediate and hi["loading"] else ""))]
    if hi["people"] > crew["tradespeople"]:
        n = hi["people"] - crew["tradespeople"]
        labour.append(_line(
            f"Assistant ({n})",
            (lo["paid_h"] * lo["assistant_rate"] * n) if lo["people"] > crew["tradespeople"] else 0,
            hi["paid_h"] * hi["assistant_rate"] * n * (1 + hi["loading"]),
            "a second person on remote roads and nights away: working alone out there is not safe"))

    other = [_line("Parts and materials", lo["materials"], hi["materials"],
                   f"{len(jobs)} job{'s' if len(jobs) != 1 else ''}, allowance by trade")]
    groups = [_group("transport", "Transport", transport), _group("logistics", "Logistics", logistics),
              _group("labour", "Labour", labour)]
    sub_lo = sum(g["low"] for g in groups) + other[0]["low"]
    sub_hi = sum(g["high"] for g in groups) + other[0]["high"]
    other.append(_line("Contingency", sub_lo * c["contingency"][0], sub_hi * c["contingency"][1],
                       f"{c['contingency'][0]:.0%} to {c['contingency'][1]:.0%} for weather, road "
                       f"delays or a return visit"))
    groups.append(_group("other", "Other", other))

    return {
        "low": sum(g["low"] for g in groups), "high": sum(g["high"] for g in groups),
        "currency": "AUD", "gst": "excluded", "groups": groups,
        "assumptions": {
            "vehicle": v["type"] if road_km else None,
            "aircraft": air["aircraft"] if flights else None,
            "road_km": round(road_km), "flight_hours": round(flight_h, 1),
            "travel_hours": round(travel_h, 1),
            "onsite_hours": [round(lo["work_h"], 1), round(hi["work_h"], 1)],
            "days": [lo["days"], hi["days"]], "nights": [lo["nights"], hi["nights"]],
            "people": hi["people"], "jobs": len(jobs),
        },
        "placeholder_rates": True,
        "used_for_priority": False,     # stated in data, rendered on screen
    }


def trip_cost(tp) -> dict | None:
    """The probable cost of a recommended trip, and of serving its jobs one
    trip each instead."""
    if not tp.reachable or not tp.stops:
        return None
    from .routing import candidate_routes
    back = candidate_routes(tp.community, tp.start)
    back_legs = back[0].legs if back else list(reversed(tp.route.legs))
    jobs = [JobWork(s.job.trade or tp.trade, s.job.hours) for s in tp.stops]
    places = [s.job.community for s in tp.stops]
    immediate = tp.anchor.tier == "Immediate"
    out = estimate(tp.route.legs, back_legs, jobs, tp.trade, immediate, places)

    if len(tp.stops) > 1:
        sep_lo = sep_hi = 0
        for s in tp.stops:
            there = candidate_routes(tp.start, s.job.community)
            home = candidate_routes(s.job.community, tp.start)
            if not there:
                continue
            one = estimate(there[0].legs, (home[0].legs if home else []),
                           [JobWork(s.job.trade or tp.trade, s.job.hours)], tp.trade,
                           s.job.tier == "Immediate", [s.job.community])
            sep_lo += one["low"]
            sep_hi += one["high"]
        out["separate"] = {"trips": len(tp.stops), "low": sep_lo, "high": sep_hi}
        out["saving"] = {"low": max(sep_lo - out["low"], 0), "high": max(sep_hi - out["high"], 0)}
    else:
        out["separate"] = out["saving"] = None
    return out
