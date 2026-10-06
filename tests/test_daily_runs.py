"""Daily runs in Darwin, Palmerston and towns within daily reach, and make-safe
call-outs for Immediate jobs in town. Who goes on a run is decided by the
queue; the order of visits is by road and never changes who is served."""

from datetime import datetime, timedelta, timezone

from fairtriage import config, scheduler, service
from fairtriage.schemas import LodgeIn


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=1):
    r = service.lodge(LodgeIn(text=text, community=community), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes only one")
    return r["request_id"]


def runs(kind="daily_run"):
    return [p for p in scheduler.plan(commit=False) if p.trigger == kind]


def ids(p):
    return {s.job.request_id for s in p.stops}


def test_jobs_near_each_other_go_on_one_daily_run():
    a = lodge("the kitchen tap is leaking under the sink", "Palmerston (Gray)", days=4)
    b = lodge("the laundry tap drips all the time", "Palmerston (Gunn)", days=3)
    c = lodge("the shower drain is blocked and water stays in the shower", "Palmerston (Woodroffe)", days=2)
    r = runs()
    assert len(r) == 1 and ids(r[0]) == {a, b, c}
    assert r[0].headline.startswith("Daily run:") and r[0].route is not None
    assert all(s.eta_h < 10 for s in r[0].stops)                   # inside one working day


def test_the_run_starts_with_the_highest_ranked_job():
    lodge("the kitchen tap is leaking under the sink", "Palmerston (Gray)", days=9)
    top = lodge("the only toilet is blocked and will not flush", "Darwin (Nightcliff)", days=1)
    r = runs()
    assert any(p.anchor.request_id == top for p in r)
    assert next(p for p in r if p.anchor.request_id == top).anchor.tier == "Urgent"


def test_a_day_holds_only_so_much_work():
    for i, place in enumerate(["Palmerston (Gray)", "Palmerston (Gunn)", "Palmerston (Driver)",
                               "Palmerston (Moulden)", "Palmerston (Woodroffe)"]):
        lodge("the kitchen tap is leaking under the sink", place, days=5 - i * 0.5)
    for p in runs():
        assert sum(s.job.hours for s in p.stops) <= config.policy()["trips"]["capacity_hours_per_day"]


def test_a_far_job_is_not_added_for_a_long_detour():
    near = lodge("the kitchen tap is leaking under the sink", "Darwin (Stuart Park)", days=3)
    far = lodge("the laundry tap drips all the time", "Batchelor", days=2)        # about an hour away
    r = runs()
    run_with_near = next(p for p in r if near in ids(p))
    assert far not in ids(run_with_near)


def test_immediate_in_town_is_a_make_safe_call_out_never_bundled():
    imm = lodge("the power point is sparking", "Darwin (Karama)")
    lodge("the bedroom light switch is broken", "Darwin (Karama)", days=3)
    safe = runs("make_safe")
    assert [p.anchor.request_id for p in safe] == [imm] and len(safe[0].stops) == 1
    assert all(imm not in ids(p) for p in runs())


def test_remote_work_stays_on_remote_trips():
    w = lodge("the only toilet is blocked and will not flush", "Wadeye")
    lodge("the kitchen tap is leaking under the sink", "Palmerston (Gray)", days=3)
    plans = scheduler.plan(commit=False)
    assert all(w not in ids(p) for p in plans if p.trigger == "daily_run")
    assert any(w in ids(p) for p in plans if p.trigger not in ("daily_run", "make_safe"))


def test_approving_a_run_tells_each_tenant_when_to_expect_someone():
    a = lodge("the kitchen tap is leaking under the sink", "Palmerston (Gray)", days=4)
    b = lodge("the laundry tap drips all the time", "Palmerston (Gunn)", days=3)
    run = runs()[0]
    scheduler.plan(commit=True, only=run.anchor.request_id)
    for rid in (a, b):
        v = service.request_view(rid)
        assert v["status"] == "scheduled" and v["trip"]["tenant_update"]


def test_runs_can_be_switched_off(monkeypatch):
    lodge("the kitchen tap is leaking under the sink", "Palmerston (Gray)", days=4)
    monkeypatch.setitem(config.policy()["trips"]["daily_runs"], "enabled", False)
    assert runs() == [] and runs("make_safe") == []
