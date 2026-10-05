"""A tenant can ask why their repair sits where it does and get a real
answer, and can ask a person to review it. Problem statement: "A tenant should
be able to ask why their repair was deprioritised and get a real answer." """

import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from fairtriage import db, service
from fairtriage.api import app
from fairtriage.explain import BANNED
from fairtriage.schemas import LodgeIn

C = TestClient(app)


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def lodge(text, community, days=1, **kw):
    r = service.lodge(LodgeIn(text=text, community=community, **kw), lodged_at=ago(days))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes only one")
    return r


def why(rid, q=None):
    r = C.post(f"/api/requests/{rid}/why", json={"question": q})
    assert r.status_code == 200, r.text
    return " ".join(r.json()["answer"])


def busy_queue_with(mine_text="no hot water since friday", place="Wadeye"):
    mine = lodge(mine_text, place, days=6, phone="0400 000 000")
    lodge("the only toilet is blocked and will not flush", "Darwin (Karama)", days=7)
    lodge("the power point is sparking", "Katherine", days=1)        # reported later, more dangerous
    lodge("no hot water in the house", "Palmerston", days=8, vulnerability=["medical_equipment"])
    return mine["request_id"]


def test_the_answer_says_who_is_ahead_and_why():
    rid = busy_queue_with()
    a = why(rid, "why am I not first?")
    assert "Urgent group" in a
    assert "ahead of yours" in a and "1 is Immediate" in a
    assert "reported after yours and still goes first" in a
    assert "Nobody goes ahead because they live closer" in a


def test_the_answer_says_location_did_not_change_the_place():
    a = why(busy_queue_with())
    assert "Where you live did not change that" in a and "same repair in Darwin" in a
    assert "Travel to your community is part of that time" in a       # Wadeye is remote


def test_deprioritised_by_staff_gets_the_real_reason():
    rid = busy_queue_with()
    C.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Routine",
                                                   "reason": "tenant has a gas heater in the laundry"})
    a = why(rid, "why was my repair moved down?")
    assert "moved it down from Urgent to Routine" in a
    assert "gas heater in the laundry" in a


def test_trips_that_were_full_are_explained():
    rid = busy_queue_with()
    db.update_request(rid, {}, inc={"prior_deferrals": 2})
    assert "left off 2 planned trips" in why(rid)


def test_the_answer_says_what_can_move_it_up_and_how_to_get_a_person():
    a = why(busy_queue_with())
    assert "What can move it up" in a and "ask for a review" in a


def test_the_answer_never_apologises_or_promises():
    rid = busy_queue_with()
    C.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Routine",
                                                   "reason": "sorry, we promise to look next week"})
    ours = re.sub("“[^”]*”", " ", why(rid)).lower()     # quoted staff words are theirs
    assert not any(b in ours for b in BANNED)


def test_not_in_queue_is_explained_in_plain_words():
    r = service.lodge(LodgeIn(text="thanks, all fixed now", community="Darwin (Parap)"))
    a = why(r["request_id"])
    assert "not in the repair queue because it said things were fine or already fixed" in a
    assert "(" not in a                                              # no internal codes


def test_a_question_still_waiting_for_an_answer_is_named():
    r = service.lodge(LodgeIn(text="toilet is blocked", community="Darwin (Parap)"))
    assert "Is this the only toilet in the house?" in why(r["request_id"])


def test_a_review_request_reaches_the_coordinator_until_someone_acts():
    rid = busy_queue_with()
    r = C.post(f"/api/requests/{rid}/review", json={"message": "The kettle broke too. We have kids."}).json()
    assert r["review_requested"] and "phone you" in r["reply"]
    row = next(c for c in C.get("/api/contacts").json() if c["request_id"] == rid)
    assert row["review"] == "The kettle broke too. We have kids."
    C.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Urgent",
                                                   "reason": "phoned: kettle broken, three young kids"})
    assert all(c["request_id"] != rid for c in C.get("/api/contacts").json())


def test_review_without_a_phone_says_where_to_look():
    r = service.lodge(LodgeIn(text="the kitchen tap is dripping", community="Darwin (Parap)"))
    assert "Check this page" in C.post(f"/api/requests/{r['request_id']}/review", json={}).json()["reply"]


def test_unknown_request():
    assert C.post("/api/requests/NOPE/why", json={}).status_code == 404
    assert C.post("/api/requests/NOPE/review", json={}).status_code == 404


def test_questions_are_kept_on_the_record():
    rid = busy_queue_with()
    why(rid, "why so long?")
    assert db.get_request(rid)["tenant_questions"][-1]["question"] == "why so long?"


# --- staff ask the tenant a question ---------------------------------------

def test_request_info_asks_the_tenant_and_reassesses_on_the_answer():
    """Regression: 'Ask tenant' left the tenant waiting with no question to
    answer. Now the coordinator's text is the question, and the answer is read
    with the report: here it reveals danger and the job moves up at once."""
    r = service.lodge(LodgeIn(text="the kitchen tap is dripping", community="Wadeye"))
    rid = r["request_id"]
    assert C.post(f"/api/requests/{rid}/decision", json={"action": "request_info", "reason": "no"}).status_code == 422
    x = C.post(f"/api/requests/{rid}/decision",
               json={"action": "request_info", "reason": "Is any water reaching the power point?"}).json()
    assert x["status"] == "awaiting_tenant" and x["question"] == "Is any water reaching the power point?"
    a = C.post(f"/api/requests/{rid}/clarify", json={"answer": "yes it drips onto it and it sparks"}).json()
    assert a["tier"] == "Immediate"
    assert "We asked: “Is any water reaching the power point?”" in a["explanation_tenant"]
    o = C.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Immediate",
                                                       "reason": "confirmed on the phone"})
    assert o.status_code == 200


def test_request_info_is_refused_for_a_job_on_a_trip():
    r = service.lodge(LodgeIn(text="the kitchen tap is dripping", community="Wadeye"))
    db.update_request(r["request_id"], {"status": "scheduled"})
    x = C.post(f"/api/requests/{r['request_id']}/decision",
               json={"action": "request_info", "reason": "Which room is it in?"})
    assert x.status_code == 422
