"""A life in danger reported through the repair form: the tenant is told to
call 000, nothing enters the repair queue, and staff can record that they
passed it on to the right authority.

Found in a demo: "My son is drowning in the sea" was asked "what is wrong and
where in the house?" instead of being told to call 000.
"""

import pytest
from fastapi.testclient import TestClient

from fairtriage import safety, service
from fairtriage.api import app
from fairtriage.extract import KeywordExtractor
from fairtriage.schemas import LodgeIn

C = TestClient(app)


def lodge(text, community="Katherine"):
    return service.lodge(LodgeIn(text=text, community=community, phone="0412345678"))


@pytest.mark.parametrize("text", [
    "My son is drowning in the sea",
    "my daughter is not breathing",
    "the kid fell in the river and cant swim",
    "car crash outside my house, people hurt",
    "my baby is choking",
    "snake bit my son",
    "my nan collapsed in the kitchen",
    "he took a lot of pills, an overdose",
    "we cant find our daughter, she is missing",
])
def test_a_life_in_danger_is_told_to_call_000_and_not_queued(text):
    r = lodge(text)
    assert r["status"] == "needs_phone_call", (text, r.get("question"))
    assert r["tier"] == "NotInQueue"
    assert "000" in r["explanation_tenant"]
    assert "emergency_000" in [f["code"] for f in r["flags"]]


@pytest.mark.parametrize("text", [
    "the ceiling collapsed in the bedroom",
    "we are drowning in bills, also the tap drips",
    "the kids went in the pool, the pool pump is broken",
    "no one is drowning, the backyard is flooded",
    "the light fitting is loose",
])
def test_repair_words_that_sound_alarming_are_not_a_life_in_danger(text):
    e = KeywordExtractor().extract(text)
    assert not e.emergency_000 and not e.person_hurt, text


def test_a_life_in_danger_beside_a_repair_keeps_both():
    e = KeywordExtractor().extract("the gas is leaking and my dad passed out")
    assert e.actionability.value == "repair" and e.endangers_person and e.person_hurt


def test_staff_see_the_case_with_the_authorities_to_call():
    rid = lodge("My son is drowning in the sea")["request_id"]
    lodge("the kitchen tap drips")
    body = C.get("/api/safety").json()
    assert [c["request_id"] for c in body["cases"]] == [rid]
    case = body["cases"][0]
    assert case["open"] and case["kind"] == "life_at_risk" and case["phone"] == "0412345678"
    phones = {a["id"]: a["phone"] for a in body["agencies"]}
    assert phones["000"] == "000" and phones["child"] == "1800 700 250" and phones["police"] == "131 444"


def test_recording_a_report_closes_the_case_under_the_signed_in_name():
    rid = lodge("my neighbour is beating his wife")["request_id"]
    r = C.post(f"/api/safety/{rid}", json={"outcome": "reported", "agency": "police",
                                             "reference": "P-12345", "note": "Police on the way"})
    assert r.status_code == 200, r.text
    assert r.json()["actor"] == "test-staff"          # from the session, not the browser
    case = C.get("/api/safety").json()["cases"][0]
    assert not case["open"] and case["referrals"][0]["reference"] == "P-12345"


def test_a_report_must_say_who_it_went_to_and_no_report_must_say_why():
    rid = lodge("My son is drowning in the sea")["request_id"]
    assert C.post(f"/api/safety/{rid}", json={"outcome": "reported"}).status_code == 422
    assert C.post(f"/api/safety/{rid}", json={"outcome": "no_report_needed", "note": "fine"}).status_code == 422
    ok = C.post(f"/api/safety/{rid}", json={"outcome": "no_report_needed",
                                              "note": "Tenant says it was a test message, called back"})
    assert ok.status_code == 200


def test_the_record_is_append_only():
    rid = lodge("My son is drowning in the sea")["request_id"]
    C.post(f"/api/safety/{rid}", json={"outcome": "already_reported", "note": "Tenant called 000"})
    C.post(f"/api/safety/{rid}", json={"outcome": "reported", "agency": "child", "reference": "CP-77"})
    entries = C.get("/api/safety").json()["cases"][0]["referrals"]
    assert [e["outcome"] for e in entries] == ["already_reported", "reported"]


def test_only_safety_reports_can_be_recorded():
    rid = lodge("the kitchen tap drips")["request_id"]
    r = C.post(f"/api/safety/{rid}", json={"outcome": "reported", "agency": "police"})
    assert r.status_code == 422
    assert C.post("/api/safety/NTF3-99999-0000", json={"outcome": "reported", "agency": "police"}).status_code == 404


def test_open_count():
    lodge("My son is drowning in the sea")
    lodge("my daughter is not breathing")
    assert safety.open_count() == 2
