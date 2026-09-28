"""Trip planner v6: routes, stops on the way, and expected arrivals.

The geography used throughout, from the road network:
  Darwin depot -> Gunbalanya, three routes:
    direct, Arnhem Hwy                          about 4.1 h
    via Adelaide River, Pine Creek (Kakadu)     about 5.5 h
    via Batchelor, Adelaide River, Pine Creek   about 5.8 h
Batchelor and Pine Creek are on the long routes only.
"""

from datetime import datetime, timedelta, timezone

import pytest

from fairtriage import reference, scheduler, service
from fairtriage.schemas import LodgeIn

HUB = "Darwin (Ludmilla)"


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=1, vul=()):
    r = service.lodge(LodgeIn(text=text, community=community, vulnerability=list(vul)),
                      lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes")
    return r["request_id"]


def trip_to(community, plans=None):
    plans = plans if plans is not None else scheduler.plan(commit=False)
    return next(p for p in plans if p.community == community)


def order(tp):
    return [s.job.request_id for s in tp.stops]


# ---------------------------------------------------------------------------

def test_not_urgent_destination_takes_long_route_and_serves_jobs_on_the_way():
    """Hub -> C -> D -> B: C and D lie on the long route to B, and B has time."""
    b = lodge("no hot water in the house", "Gunbalanya")                  # Urgent, plumber
    c = lodge("the tap in the kitchen is dripping", "Batchelor", days=6)  # Routine, plumber
    d = lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    tp = trip_to("Gunbalanya")
    assert order(tp) == [c, d, b]
    assert tp.route.waypoints[:1] == ["Batchelor"] and "Pine Creek" in tp.route.waypoints
    assert tp.headline == f"Recommended trip: {HUB} → Batchelor → Pine Creek → Gunbalanya"
    assert "on the route" in tp.explanation and "Urgent" in tp.explanation


def test_wait_times_follow_the_sequence():
    """C earliest, then D, then B, and B later than it would be going direct."""
    b = lodge("no hot water in the house", "Gunbalanya")
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    tp = trip_to("Gunbalanya")
    etas = [s.eta_h for s in tp.stops]
    assert etas == sorted(etas) and len(set(etas)) == 3
    direct = tp.options[0].route.hours
    b_eta = next(s.eta_h for s in tp.stops if s.job.request_id == b)
    assert b_eta > direct                   # the stops cost B some time...
    assert b_eta <= scheduler.slack_hours(tp.anchor) * 0.75   # ...within its limit


def test_immediate_destination_goes_direct_and_says_what_it_gave_up():
    """Hub -> B on the short route, even though C and D could have been served."""
    b = lodge("the power point is sparking", "Gunbalanya")               # Immediate, electrician
    lodge("lights not working in the kitchen", "Batchelor", days=6)
    lodge("lights not working in the bedroom", "Pine Creek", days=6)
    tp = trip_to("Gunbalanya")
    assert order(tp) == [b]
    assert tp.route is tp.options[0].route and tp.route.waypoints == []
    assert tp.headline == f"Recommended trip: {HUB} → Gunbalanya"
    assert "Immediate" in tp.explanation and "fastest route" in tp.explanation
    assert "could have served 2 more jobs" in tp.explanation
    assert all("not chosen" in why for _, why in tp.left_behind)


def test_destination_near_its_target_is_not_delayed_by_stops():
    """B has waited most of its target: no time left for stops on the way."""
    b = lodge("no hot water in the house", "Gunbalanya", days=4.6)
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    tp = trip_to("Gunbalanya")
    assert order(tp) == [b]
    assert tp.route.waypoints == []


def test_long_route_not_taken_for_nothing():
    lodge("no hot water in the house", "Gunbalanya")
    tp = trip_to("Gunbalanya")
    assert tp.route.waypoints == []
    assert "fastest route is used" in tp.explanation


def test_stop_needing_another_trade_is_not_added():
    lodge("no hot water in the house", "Gunbalanya")
    e = lodge("lights not working in the kitchen", "Batchelor", days=6)   # electrician
    tp = trip_to("Gunbalanya")
    assert e not in order(tp)


def test_fill_on_the_way_is_by_need_not_quickest():
    """With room for one more stop, the needier job gets it."""
    lodge("no hot water in the house", "Gunbalanya")
    low = lodge("the tap in the kitchen is dripping", "Pine Creek", days=6)
    high = lodge("the tap in the laundry is dripping", "Pine Creek", days=6,
                 vul=["medical_equipment"])
    t = scheduler._cfg()
    saved = t["capacity_hours_per_day"], t["routing"]["extra_hour_cost"]
    t["capacity_hours_per_day"] = (2.5 + 2.0) / t["trip_days"]           # anchor + one stop
    t["routing"]["extra_hour_cost"] = 0.1          # so the long route is worth taking
    try:
        tp = trip_to("Gunbalanya")
    finally:
        t["capacity_hours_per_day"], t["routing"]["extra_hour_cost"] = saved
    assert "Pine Creek" in tp.route.nodes          # the route passes both jobs
    assert high in order(tp) and low not in order(tp)
    assert any(j.request_id == low and "capacity" in why for j, why in tp.left_behind)


def test_changing_the_crew_location_recalculates_route_and_times():
    lodge("no hot water in the house", "Gunbalanya")
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    from_hub = trip_to("Gunbalanya")
    scheduler.set_team_location("Arnhem", "Pine Creek")
    from_pc = trip_to("Gunbalanya")
    assert from_pc.start == "Pine Creek" and from_hub.start == HUB
    assert from_pc.headline.startswith("Recommended trip: Pine Creek")
    assert "Batchelor" not in from_pc.route.nodes          # behind the crew now
    assert from_pc.stops[-1].eta_h != from_hub.stops[-1].eta_h


def test_raising_priority_recalculates():
    """The same job, overridden to Immediate, loses its stops."""
    b = lodge("no hot water in the house", "Gunbalanya")
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    assert len(trip_to("Gunbalanya").stops) == 3
    from fairtriage.schemas import DecisionIn
    service.decide(b, DecisionIn(action="override", to_tier="Immediate",
                                 reason="elderly tenant has no other water"))
    tp = trip_to("Gunbalanya")
    assert order(tp) == [b] and "Immediate" in tp.explanation


def test_confirming_stores_expected_arrival_and_tells_the_tenant():
    b = lodge("no hot water in the house", "Gunbalanya")
    c = lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    scheduler.plan(commit=True)
    vc, vb = service.request_view(c), service.request_view(b)
    assert vc["status"] == vb["status"] == "scheduled"
    assert (vc["trip"]["stop"], vb["trip"]["stop"]) == (1, 3)
    assert vc["trip"]["eta_at"] < vb["trip"]["eta_at"]
    assert "stop 1 of 3" in vc["trip"]["tenant_update"]
    assert vc["advanced_by"] == b


def test_closed_road_means_flying_and_no_stops_on_the_way():
    lodge("the fan does not turn", "Numbulwar", days=120)     # road closed in snapshot
    tp = trip_to("Numbulwar")
    assert tp.route.by_air and "charter" in tp.explanation


def test_long_trip_is_shortened_when_it_would_make_a_later_urgent_job_wait_too_long(monkeypatch):
    """One crew. Trip 1 could take the long route to Gunbalanya, but then the
    crew would be back too late for the Urgent job at Maningrida."""
    orig = reference.trade_capacity()
    one_crew = {k: {**v, "crews": 1} for k, v in orig.items()}
    monkeypatch.setattr(scheduler, "trade_capacity", lambda: one_crew)
    first = lodge("no hot water in the house", "Gunbalanya", vul=["medical_equipment"])
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    later = lodge("no hot water in the house", "Maningrida", days=3.3)
    plans = scheduler.plan(commit=False)
    t1 = next(p for p in plans if p.anchor.request_id == first)
    t2 = next(p for p in plans if p.anchor.request_id == later)
    assert order(t1) == [first] and t1.shortened_for.startswith(later)
    assert "not pushed past its target" in t1.explanation
    assert not t2.target_missed


def test_every_page_shows_the_plan():
    from fastapi.testclient import TestClient
    from fairtriage.api import app
    lodge("no hot water in the house", "Gunbalanya")
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    c = TestClient(app)
    html = c.get("/coordinator/trips").text
    assert "Recommended trip" in html and "Batchelor" in html
    js = c.get("/api/trips/preview").json()
    trip = next(t for t in js["trips"] if t["community"] == "Gunbalanya")
    assert [s["community"] for s in trip["stops"]] == ["Batchelor", "Pine Creek", "Gunbalanya"]
    assert [s["eta_hours"] for s in trip["stops"]] == sorted(s["eta_hours"] for s in trip["stops"])
    r = c.post("/coordinator/team", data={"trade_region": "Arnhem", "location": "Pine Creek"},
               follow_redirects=False)
    assert r.status_code == 303
    assert scheduler.team_locations()["Arnhem"] == "Pine Creek"


def test_benefit_explains_why_to_approve():
    lodge("no hot water in the house", "Gunbalanya")
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    d = scheduler.to_dict(trip_to("Gunbalanya"))
    b = d["benefit"]
    assert b["jobs"] == 3 and b["separate_trips"] == 3
    assert b["separate_hours"] > b["trip_hours"] and b["hours_saved"] > 0
    assert b["destination_on_time"] and b["destination_delay_h"] > 0
    assert any("3 repairs in one visit" in line for line in b["why"])
    # the map has every place the trip and its alternatives pass
    assert all(n in d["coords"] for o in d["options"] for n in o["nodes"])


def test_confirm_one_trip_leaves_the_others():
    a = lodge("no hot water in the house", "Gunbalanya")
    b = lodge("power point is sparking in the kitchen", "Wadeye")
    scheduler.plan(commit=True, only=a)
    assert service.request_view(a)["status"] == "scheduled"
    assert service.request_view(b)["status"] == "ranked"


def test_address_travels_with_the_job():
    r = service.lodge(LodgeIn(text="no hot water in the house", community="Gunbalanya",
                              address="Lot 12, Oenpelli Road", phone="0400 000 000"))
    v = service.request_view(r["request_id"])
    assert v["address"] == "Lot 12, Oenpelli Road" and v["phone"] == "0400 000 000"
    stop = scheduler.to_dict(trip_to("Gunbalanya"))["stops"][0]
    assert stop["address"] == "Lot 12, Oenpelli Road"
    assert "Lot 12" not in r["explanation_tenant"]         # never in the verified text


def test_tenant_message_opens_with_the_wait():
    r = service.lodge(LodgeIn(text="no hot water since friday", community="Darwin (Parap)"))
    assert r["explanation_tenant"].startswith("Expect a tradesperson")
    e = service.lodge(LodgeIn(text="not sure", community="Darwin (Parap)"))
    e = service.clarify(e["request_id"], "the gas is on fire")
    assert e["explanation_tenant"].startswith("If there is a fire")   # safety before the wait
