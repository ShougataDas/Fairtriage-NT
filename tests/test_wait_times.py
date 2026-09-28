"""Wait estimates must be believable: never shorter than the way work is
actually booked, and for remote routine jobs never shorter than the wait for
the trip that will reach them."""

from datetime import datetime, timedelta, timezone

from fairtriage import service
from fairtriage.config import policy
from fairtriage.schemas import LodgeIn


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=0.0):
    r = service.lodge(LodgeIn(text=text, community=community), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes only one")
    return r


def test_routine_never_shown_as_within_a_day():
    r = lodge("the kitchen cupboard door came off the hinge", "Darwin (Parap)")
    lead = policy()["wait"]["lead_days"]["Routine"]
    assert r["wait"]["central"] >= lead
    assert "within" not in r["wait"]["range_text"]


def test_urgent_is_about_a_day_or_more():
    r = lodge("no hot water since friday", "Darwin (Parap)")
    assert r["wait"]["central"] >= policy()["wait"]["lead_days"]["Urgent"]


def test_immediate_is_given_in_hours():
    r = lodge("the power point is sparking", "Darwin (Parap)")
    assert r["wait"]["range_text"].startswith("within about")
    assert "hour" in r["wait"]["range_text"]


def test_remote_routine_waits_for_the_trip_and_says_so():
    r = lodge("the kitchen cupboard door came off the hinge", "Wadeye")
    t = policy()
    trip = t["trips"]["community_threshold_multiple"] * t["service_targets_days"]["Routine"]["remote"]
    assert r["wait"]["central"] >= trip
    assert "maintenance trip" in r["explanation_tenant"]
    assert "The difference is travel, not priority" in r["explanation_tenant"]


def test_remote_routine_rides_on_a_trip_that_is_due():
    lodge("the power point is sparking in the kitchen", "Wadeye")        # electrician trip due now
    r = lodge("one light in the bedroom does not work", "Wadeye")        # electrician, routine
    assert "One is due now" in r["explanation_tenant"]
    trip = policy()["trips"]["community_threshold_multiple"] * 25
    assert r["wait"]["central"] < trip


def test_rank_is_still_location_free():
    far = lodge("the kitchen cupboard door came off the hinge", "Wadeye")
    assert "number" in far["explanation_tenant"]
    assert "Where you live was not used to decide your position" in far["explanation_tenant"]
