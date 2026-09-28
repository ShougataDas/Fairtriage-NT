"""Trip planning: batching may only ever move work forward."""

from datetime import datetime, timedelta, timezone

from fairtriage import scheduler, service
from fairtriage.schemas import LodgeIn


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=1):
    r = service.lodge(LodgeIn(text=text, community=community), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes")
    return r["request_id"]


def test_urgent_job_anchors_a_trip_and_batches_same_community():
    anchor = lodge("power point is sparking in the kitchen", "Wadeye")
    rider = lodge("ceiling fan in the bedroom is not working", "Wadeye")
    plans = scheduler.plan(commit=True)
    trip = next(p for p in plans if p.community == "Wadeye")
    assert trip.trigger == "urgent_anchor" and trip.anchor.request_id == anchor
    assert rider in [j.request_id for j, _, _ in trip.batched]
    assert service.request_view(rider)["advanced_by"] == anchor


def test_community_with_no_emergency_still_gets_a_trip():
    """Without this trigger, quiet communities never get a truck."""
    lodge("the fan does not turn", "Numbulwar", days=120)
    plans = scheduler.plan(commit=True)
    trip = next(p for p in plans if p.community == "Numbulwar")
    assert trip.trigger == "community_threshold"
    assert "x target" in trip.trigger_detail


def test_fill_is_by_need_not_quickest():
    lodge("power point is sparking in the kitchen", "Wadeye")
    hi = service.lodge(LodgeIn(text="lights not working in the kitchen", community="Wadeye",
                               vulnerability=["medical_equipment"]), lodged_at=ago(1))["request_id"]
    lo = lodge("lights not working in the bedroom", "Wadeye")
    trip = next(p for p in scheduler.plan(commit=False) if p.community == "Wadeye")
    order = [j.request_id for j, _, _ in trip.batched]
    assert order.index(hi) < order.index(lo)


def test_urgent_overflow_gets_another_trip_not_a_deferral():
    """More Immediate jobs than one trip holds: every one still gets a crew.
    Before this, the overflow was only counted as deferred and nobody went."""
    ids = [lodge(f"power point sparking in room {i}", "Wadeye") for i in range(12)]
    before = {i: service.request_view(i)["assessment"]["tier"] for i in ids}
    plans = scheduler.plan(commit=True)
    booked = {s.job.request_id for p in plans for s in p.stops}
    assert set(ids) <= booked
    assert sum(p.community == "Wadeye" for p in plans) >= 2
    for i in ids:
        v = service.request_view(i)
        assert v["status"] == "scheduled" and v["prior_deferrals"] == 0
        assert v["assessment"]["tier"] == before[i]


def test_routine_overflow_increments_deferral_and_never_lowers_tier():
    lodge("power point is sparking in the kitchen", "Wadeye")
    ids = [lodge(f"light not working in room {i}", "Wadeye") for i in range(14)]
    before = {i: service.request_view(i)["assessment"]["tier"] for i in ids}
    scheduler.plan(commit=True)
    deferred = [i for i in ids if service.request_view(i)["prior_deferrals"] > 0]
    assert deferred, "a full trip must record who was passed over"
    for i in ids:
        assert service.request_view(i)["assessment"]["tier"] == before[i]


def test_trade_mismatch_is_explained_not_deferred():
    lodge("power point is sparking in the kitchen", "Wadeye")
    plumb = lodge("the tap in the kitchen is dripping", "Wadeye")
    trip = next(p for p in scheduler.plan(commit=True) if p.community == "Wadeye"
                and p.trade == "Electrician")
    reasons = {j.request_id: r for j, r in trip.left_behind}
    assert "not on this trip" in reasons.get(plumb, "")
    assert service.request_view(plumb)["prior_deferrals"] == 0
