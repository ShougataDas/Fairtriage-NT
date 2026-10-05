"""The trip threshold is the equity lever. The coordinator sees what each value
means for remote waits, trips and cost, and sets it with a recorded reason;
the planner and every live wait follow at once."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from fairtriage import scheduler, service, tripsettings, whatif
from fairtriage.api import app
from fairtriage.schemas import LodgeIn

C = TestClient(app)


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=1):
    r = service.lodge(LodgeIn(text=text, community=community), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes")
    return r


def remote_routine_work():
    lodge("the kitchen tap is dripping", "Wadeye", days=10)
    lodge("the kitchen cupboard door came off the hinge", "Maningrida", days=5)
    lodge("the fly screen on the back door has a big rip", "Gunbalanya", days=20)
    lodge("the kitchen tap is dripping", "Darwin (Parap)", days=2)


def test_lower_threshold_means_shorter_waits_more_trips_more_cost():
    remote_routine_work()
    rows = whatif.scenarios()["scenarios"]
    assert [r["multiple"] for r in rows] == sorted(r["multiple"] for r in rows)
    for a, b in zip(rows, rows[1:]):
        assert a["wait_max_days"] < b["wait_max_days"]
        assert a["trips_per_month"] >= b["trips_per_month"]
        assert a["cost_month_high"] >= b["cost_month_high"]
    assert sum(r["current"] for r in rows) == 1


def test_the_comparison_is_against_darwin():
    remote_routine_work()
    d = whatif.scenarios()
    assert d["darwin_routine_days"] > 0
    assert all(r["ratio_vs_darwin"] > 1 for r in d["scenarios"])


def test_no_remote_work_means_nothing_to_compare():
    lodge("the kitchen tap is dripping", "Darwin (Parap)")
    assert all(r["wait_max_days"] is None for r in whatif.scenarios()["scenarios"])


def test_setting_needs_a_reason_and_a_sane_value():
    for body in ({"multiple": 1.5, "reason": "short"}, {"multiple": 0.2, "reason": "budget approved for more trips"},
                 {"multiple": 9, "reason": "budget approved for more trips"}):
        assert C.post("/api/policy/trip-threshold", json=body).status_code == 422


def test_a_change_is_recorded_with_who_and_why():
    r = C.post("/api/policy/trip-threshold", json={"multiple": 1.5, "reason": "budget approved for more trips this quarter"})
    assert r.status_code == 200
    d = r.json()
    assert d["setting"]["value"] == 1.5 and d["setting"]["source"] == "coordinator"
    assert d["history"][0]["from"] == 3.0 and d["history"][0]["to"] == 1.5
    assert "budget approved" in d["history"][0]["reason"]


def test_a_new_remote_report_is_told_the_shorter_wait():
    before = lodge("the kitchen cupboard door came off the hinge", "Wadeye")["wait"]["central"]
    tripsettings.set_threshold(1.5, "budget approved for more trips this quarter")
    after = lodge("the kitchen cupboard door came off the hinge", "Maningrida")["wait"]["central"]
    assert after < before - 20


def test_jobs_already_waiting_follow_the_change():
    r = lodge("the kitchen cupboard door came off the hinge", "Wadeye")
    told = service.request_view(r["request_id"])["wait_now"]["central"]
    tripsettings.set_threshold(1.5, "budget approved for more trips this quarter")
    now = service.request_view(r["request_id"])["wait_now"]["central"]
    assert told - now > 30                     # 1.5 x 25-day target sooner


def test_the_planner_starts_trips_at_the_new_threshold():
    lodge("the fly screen on the back door has a big rip", "Gunbalanya", days=50)      # 2x the 25-day target
    assert not any(p.trigger == "community_threshold" for p in scheduler.plan(commit=False))
    tripsettings.set_threshold(1.5, "budget approved for more trips this quarter")
    assert any(p.trigger == "community_threshold" and p.community == "Gunbalanya"
               for p in scheduler.plan(commit=False))


def test_trip_rules_show_the_setting_in_force():
    tripsettings.set_threshold(2.0, "trialling more frequent trips to Arnhem")
    assert C.get("/api/trips/preview").json()["rules"]["community_threshold_multiple"] == 2.0
