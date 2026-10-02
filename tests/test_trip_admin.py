"""Changing an approved trip: cancel it, take a job off it, or close it as done."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from fairtriage import scheduler, service
from fairtriage.api import app
from fairtriage.schemas import LodgeIn

c = TestClient(app)


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=1):
    r = service.lodge(LodgeIn(text=text, community=community), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes")
    return r["request_id"]


def approved_trip():
    a = lodge("no hot water in the house", "Gunbalanya")
    b = lodge("the tap in the kitchen is dripping", "Batchelor", days=6)
    d = lodge("the tap in the laundry is dripping", "Pine Creek", days=6)
    scheduler.plan(commit=True, only=a)
    t = next(t for t in scheduler.trips_view() if t["anchor"] == a)
    return t, (a, b, d)


def test_approved_trip_is_listed_as_active():
    t, ids = approved_trip()
    assert t["status"] == "approved" and t["active_jobs"] == 3
    assert t["history"][0]["action"] == "approved"


def test_cancel_returns_every_job_to_the_queue():
    t, ids = approved_trip()
    r = c.post(f"/api/trips/{t['id']}/cancel", json={"reason": "crew vehicle broke down"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    for rid in ids:
        v = service.request_view(rid)
        assert v["status"] == "ranked" and v["trip"] is None and v["advanced_by"] is None
        assert any(d["action"] == "trip_cancelled" for d in v["decisions"])     # audited
    queue = {q["request_id"] for q in service.queue_view()}
    assert set(ids) <= queue
    # and they are recommended again
    again = {s["request_id"] for p in c.get("/api/trips/preview").json()["trips"] for s in p["stops"]}
    assert set(ids) <= again


def test_cancel_needs_a_reason_and_only_once():
    t, _ = approved_trip()
    assert c.post(f"/api/trips/{t['id']}/cancel", json={}).status_code == 409
    assert c.post(f"/api/trips/{t['id']}/cancel", json={"reason": "duplicate"}).status_code == 200
    assert c.post(f"/api/trips/{t['id']}/cancel", json={"reason": "again"}).status_code == 409
    assert c.post("/api/trips/TRIP-nope/cancel", json={"reason": "x y z"}).status_code == 404


def test_cancel_undoes_the_deferrals_it_caused():
    lodge("power point is sparking in the kitchen", "Wadeye")
    ids = [lodge(f"light not working in room {i}", "Wadeye") for i in range(14)]
    scheduler.plan(commit=True)
    deferred = {i for i in ids if service.request_view(i)["prior_deferrals"] > 0}
    assert deferred
    for t in scheduler.trips_view():
        if t["status"] == "approved":
            scheduler.cancel_trip(t["id"], "replanning")
    assert all(service.request_view(i)["prior_deferrals"] == 0 for i in deferred)


def test_remove_one_job_keeps_the_rest_booked():
    t, (a, b, d) = approved_trip()
    r = c.post(f"/api/trips/{t['id']}/remove", json={"request_id": b, "reason": "tenant away this week"})
    assert r.status_code == 200
    assert r.json()["active_jobs"] == 2 and r.json()["status"] == "approved"
    assert service.request_view(b)["status"] == "ranked"
    assert service.request_view(a)["status"] == "scheduled"
    assert c.post(f"/api/trips/{t['id']}/remove", json={"request_id": b, "reason": "again"}).status_code == 409


def test_removing_every_job_cancels_the_trip():
    t, ids = approved_trip()
    for rid in ids:
        out = scheduler.remove_from_trip(t["id"], rid, "not needed")
    assert out["status"] == "cancelled"


def test_complete_closes_the_jobs():
    t, ids = approved_trip()
    r = c.post(f"/api/trips/{t['id']}/complete", json={})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    for rid in ids:
        assert service.request_view(rid)["status"] == "completed"
    assert not set(ids) & {q["request_id"] for q in service.queue_view()}
    assert c.post(f"/api/trips/{t['id']}/cancel", json={"reason": "too late"}).status_code == 409
