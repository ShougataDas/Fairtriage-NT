"""Probable trip cost: every major cost shown, as a range, line by line, and
never used to decide who is served."""

from datetime import datetime, timedelta, timezone

from fairtriage import config, scheduler, service
from fairtriage.schemas import LodgeIn


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=1):
    r = service.lodge(LodgeIn(text=text, community=community), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes")
    return r["request_id"]


def trip_to(community):
    tp = next(p for p in scheduler.plan(commit=False) if p.community == community)
    return tp, scheduler.to_dict(tp)["cost"]


def lines(cost):
    return {l["label"]: l for g in cost["groups"] for l in g["lines"]}


def road_trip():
    """Darwin -> Batchelor -> Pine Creek -> Gunbalanya by road, three jobs."""
    lodge("no hot water in the house", "Gunbalanya")
    lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    return trip_to("Gunbalanya")


def test_every_cost_group_is_shown_and_adds_up():
    _, c = road_trip()
    assert [g["key"] for g in c["groups"]] == ["transport", "logistics", "labour", "other"]
    for g in c["groups"]:
        assert g["low"] == sum(l["low"] for l in g["lines"]) and g["high"] == sum(l["high"] for l in g["lines"])
        assert all(l["low"] <= l["high"] and l["basis"] for l in g["lines"])
    assert c["low"] == sum(g["low"] for g in c["groups"]) and c["low"] < c["high"]
    assert c["gst"] == "excluded" and c["used_for_priority"] is False


def test_a_road_trip_costs_fuel_and_vehicle_and_no_charter():
    _, c = road_trip()
    ls = lines(c)
    assert ls["Fuel"]["high"] > 0 and ls["Vehicle running costs"]["high"] > 0
    assert "Charter flights" not in ls
    assert "L/100 km" in ls["Fuel"]["basis"] and c["assumptions"]["road_km"] > 300


def test_labour_counts_travel_and_site_hours_for_every_person():
    _, c = road_trip()
    ls = lines(c)
    plumber = ls["Plumber (1)"]
    assert "h travel" in plumber["basis"] and "on site" in plumber["basis"]
    assert "Assistant (1)" in ls                 # remote roads: never alone
    assert c["assumptions"]["people"] == 2 and c["assumptions"]["jobs"] == 3


def test_costs_considered_but_not_charged_are_listed_at_zero():
    _, c = road_trip()
    ls = lines(c)
    assert ls["Tolls and parking"]["high"] == 0
    assert ls["Aboriginal land permit"]["high"] == 0     # Gunbalanya is remote


def test_parts_and_contingency_are_separate_lines():
    _, c = road_trip()
    ls = lines(c)
    assert ls["Parts and materials"]["high"] > 0
    assert ls["Contingency"]["high"] > 0 and "%" in ls["Contingency"]["basis"]


def test_a_flight_costs_a_charter_landings_and_freight():
    lodge("the power point is sparking", "Galiwinku", days=0.1)     # air or barge only
    tp, c = trip_to("Galiwinku")
    assert tp.route.by_air
    ls = lines(c)
    assert ls["Charter flights"]["high"] > 1000 and ls["Landing fees"]["high"] > 0
    assert "Tools and parts freight" in ls and "Vehicle in the community" in ls
    assert "Fuel" not in ls or ls["Fuel"]["high"] < 50


def test_nights_away_add_accommodation():
    _, c = road_trip()
    if c["assumptions"]["nights"][1] > 0:
        assert lines(c)["Accommodation"]["high"] > 0
    lodge("the power point is sparking", "Galiwinku", days=0.1)
    _, day = trip_to("Galiwinku")
    assert day["assumptions"]["nights"] == [0, 0] and "Accommodation" not in lines(day)


def test_one_trip_is_cheaper_than_separate_trips():
    _, c = road_trip()
    assert c["separate"]["trips"] == 3
    assert c["separate"]["low"] > c["low"] and c["saving"]["low"] > 0


def test_cost_never_changes_who_is_served(monkeypatch):
    """Cost is displayed, not used: making every cost absurd changes nothing."""
    road_trip()
    before = [(p.community, [s.job.request_id for s in p.stops]) for p in scheduler.plan(commit=False)]
    pol = config.policy()
    tc = pol["trip_cost"]
    monkeypatch.setitem(tc["charter"], "rate_per_flight_hour", [99999, 99999])
    monkeypatch.setitem(tc["vehicle"], "fuel_price_per_litre", [99.0, 99.0])
    monkeypatch.setitem(tc["labour_rate_per_hour"], "Plumber", [9999, 9999])
    after = [(p.community, [s.job.request_id for s in p.stops]) for p in scheduler.plan(commit=False)]
    assert before == after


def test_an_approved_trip_keeps_its_cost():
    road_trip()
    scheduler.plan(commit=True)
    t = scheduler.trips_view()[0]
    assert t["cost"] and t["cost"]["high"] > t["cost"]["low"] > 0


def test_the_preview_api_returns_cost():
    from fastapi.testclient import TestClient
    from fairtriage.api import app
    road_trip()
    trips = TestClient(app).get("/api/trips/preview").json()["trips"]
    assert any(t["cost"] and t["cost"]["groups"] for t in trips)
