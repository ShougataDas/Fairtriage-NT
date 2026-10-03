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
