"""Regression: every Immediate showed "5-10 hours", every Urgent "2-3 days" and
every Routine "5-6 days", whatever the rank, trade or place. The queue term was
(jobs ahead / all crews) x half a day, so it barely moved the tier's lead time,
and the estimate was frozen at lodging. Now rank, trade, job size, remoteness
and time already waited all show in the number."""

from datetime import datetime, timedelta, timezone

from fairtriage import service
from fairtriage.schemas import LodgeIn


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=0.0):
    r = service.lodge(LodgeIn(text=text, community=community), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes only one")
    return r


def busy_plumbing(n=30):
    for i in range(n):
        lodge("the kitchen tap is dripping", "Darwin (Karama)", days=1 + i * 0.2)


def test_more_jobs_ahead_means_a_longer_wait():
    quiet = lodge("the kitchen tap is dripping", "Darwin (Parap)")["wait"]["central"]
    busy_plumbing()
    busy = lodge("the kitchen tap is dripping", "Darwin (Parap)")["wait"]["central"]
    assert busy > quiet + 1


def test_a_job_does_not_wait_behind_another_trade():
    busy_plumbing()
    tap = lodge("the kitchen tap is dripping", "Darwin (Parap)")["wait"]["central"]
    hinge = lodge("the kitchen cupboard door came off the hinge", "Darwin (Parap)")["wait"]["central"]
    assert tap > hinge


def test_remote_and_island_communities_wait_longer_for_urgent_work():
    text = "the toilet is blocked and it is the only toilet"
    darwin = lodge(text, "Darwin (Parap)")["wait"]
    wadeye = lodge(text, "Wadeye")["wait"]
    island = lodge(text, "Galiwinku")["wait"]          # air or barge only
    assert darwin["central"] < wadeye["central"] < island["central"]
    assert darwin["range_text"] != island["range_text"]


def test_the_range_is_wider_where_less_is_certain():
    text = "the toilet is blocked and it is the only toilet"
    d = lodge(text, "Darwin (Parap)")["wait"]
    r = lodge(text, "Wadeye")["wait"]
    assert (r["high"] - r["low"]) / r["central"] > (d["high"] - d["low"]) / d["central"]


def test_the_queue_shows_the_wait_from_now_not_from_lodging():
    lodge("the toilet is blocked and it is the only toilet", "Darwin (Parap)", days=0.8)
    row = next(q for q in service.queue_view() if q["tier"] == "Urgent")
    assert row["wait_high"] < row["told_high"]
    assert row["wait_text"]


def test_the_tenant_page_has_the_live_wait_too():
    r = lodge("the kitchen tap is dripping", "Darwin (Parap)", days=2)
    v = service.request_view(r["request_id"])
    assert v["wait_now"]["central"] < r["wait"]["central"]
    assert v["wait_now"]["range_text"].startswith(("in about", "within"))


def test_short_waits_are_a_range_of_hours():
    for _ in range(4):
        lodge("water is pouring from the ceiling onto the power point and sparking", "Darwin (Karama)")
    r = lodge("water is pouring from the ceiling onto the power point and sparking", "Wadeye")
    assert r["tier"] == "Immediate"
    assert "hours" in r["wait"]["range_text"]
    assert r["explanation_tenant"].count("hours") >= 1
    assert not any(f["code"] == "explanation_check_failed" for f in r.get("flags", []))


def test_an_overdue_routine_job_is_never_promised_within_hours():
    lodge("the kitchen cupboard door came off the hinge", "Darwin (Parap)", days=20)
    row = next(q for q in service.queue_view() if q["tier"] == "Routine")
    assert "hour" not in row["wait_text"]


import pytest  # noqa: E402


@pytest.mark.parametrize("place", ["Humpty Doo", "Batchelor", "Coolalinga", "Palmerston", "Katherine"])
def test_towns_within_daily_reach_do_not_wait_for_a_trip(place):
    """Regression: Humpty Doo (45 km) and Batchelor (100 km) are under an hour's
    drive but were past the 40 km line, so a routine job there waited for a
    remote-style trip: 26 to 35 days, against 3 days in Palmerston."""
    r = lodge("the kitchen cupboard door came off the hinge", place)
    assert r["wait"]["central"] < 6, (place, r["wait"]["range_text"])
    assert "maintenance trip" not in r["explanation_tenant"]


def test_remote_routine_still_waits_for_its_trip():
    r = lodge("the kitchen cupboard door came off the hinge", "Wadeye")
    assert r["wait"]["breakdown"]["trip_wait_days"] is not None
    assert "maintenance trip" in r["explanation_tenant"]


def test_a_longer_drive_reads_as_a_longer_immediate_wait():
    text = "water is pouring from the ceiling onto the power point and sparking"
    near = lodge(text, "Palmerston")["wait"]
    far = lodge(text, "Batchelor")["wait"]
    assert far["central"] > near["central"]
    assert far["range_text"] != near["range_text"]


def test_queue_position_moves_the_wait():
    first = lodge("the kitchen tap is dripping", "Palmerston", days=10)["wait"]["central"]
    for i in range(40):
        lodge("the kitchen tap is dripping", "Palmerston", days=5 - i * 0.1)
    last = lodge("the kitchen tap is dripping", "Palmerston")["wait"]["central"]
    assert last >= first + 2


def test_immediate_is_made_safe_within_the_target_on_a_normal_day():
    """Regression: a sparking power point in Darwin City was told 14 to 18 hours
    behind a stale backlog; Immediate work competed with the day crews only."""
    for _ in range(3):
        lodge("the power point is sparking", "Darwin (Karama)")
    r = lodge("the power point in the kitchen is sparking when I plug the kettle in", "Darwin (City)")
    assert r["tier"] == "Immediate"
    assert r["wait"]["high"] * 24 <= 4, r["wait"]["range_text"]
    assert not any(f["code"] == "immediate_over_target" for f in r["flags"])
    assert service.backlog_alerts() == []


def test_an_immediate_backlog_alerts_the_coordinator_and_tells_the_truth():
    # same report, so the new one queues behind the 40 (ties go to who reported first)
    for i in range(40):
        lodge("the power point is sparking", "Darwin (Karama)", days=0.1 - i * 0.001)
    r = lodge("the power point is sparking", "Darwin (City)")
    assert r["wait"]["high"] * 24 > 4                     # the tenant gets the real time
    flag = next(f for f in r["flags"] if f["code"] == "immediate_over_target")
    assert flag["audience"] == "coordinator" and "Electrician" in flag["detail"]
    alerts = service.backlog_alerts()
    assert alerts and alerts[0]["trade"] == "Electrician" and alerts[0]["trade_region"] == "Darwin"
    assert alerts[0]["over_target"] >= 1


def test_the_alerts_endpoint():
    from fastapi.testclient import TestClient
    from fairtriage.api import app
    for i in range(40):
        lodge("the power point is sparking", "Darwin (Karama)", days=0.1 - i * 0.001)
    got = TestClient(app).get("/api/alerts").json()
    assert got and got[0]["trade"] == "Electrician"


def test_a_remote_flight_alone_does_not_raise_a_crew_alert():
    r = lodge("the power point is sparking", "Galiwinku")      # air or barge only
    assert r["tier"] == "Immediate"
    assert not any(f["code"] == "immediate_over_target" for f in r["flags"])
    assert service.backlog_alerts() == []
