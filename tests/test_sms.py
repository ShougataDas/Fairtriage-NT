"""Text messages: a tenant who loses their reference can still check on their
repair. A mobile number is required; the message they are shown is texted
with the reference and a tracking link; staff questions and tier changes are
texted too; a lost reference can be texted again. No test sends a real text."""

import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from fairtriage import config, db, sms
from fairtriage.api import app

C = TestClient(app)
MOBILE = "0412 345 678"


def lodge(text="the kitchen tap is dripping", community="Darwin (Parap)", phone=MOBILE):
    return C.post("/api/requests", json={"text": text, "community": community, "phone": phone})


@pytest.mark.parametrize("raw, ok", [
    ("0412 345 678", "+61412345678"), ("+61 412 345 678", "+61412345678"), ("61412345678", "+61412345678"),
    ("(04) 1234 5678", "+61412345678"), ("08 8999 1234", None), ("0412 345 67", None), ("", None),
])
def test_only_australian_mobiles_are_accepted(raw, ok):
    assert sms.normalise_mobile(raw) == ok


def test_a_mobile_number_is_required_to_report():
    assert C.post("/api/requests", json={"text": "the tap drips", "community": "Darwin (Parap)"}).status_code == 422
    r = lodge(phone="08 8999 1234")                          # a landline cannot get a text
    assert r.status_code == 422 and "04" in r.json()["detail"]


def test_the_tenant_is_texted_their_reference_and_message():
    r = lodge().json()
    assert r["sms"]["status"] == "demo" and r["sms"]["to"] == "0412 ••• 678"
    v = C.get(f"/api/requests/{r['request_id']}").json()
    assert v["phone"] == "+61412345678"
    text = v["sms"][0]["body"]
    assert text.startswith(f"FairTriage NT repair {r['request_id']}")
    assert "Expect a tradesperson" in text and f"/track/{r['request_id']}" in text
    assert len(text) <= sms.MAX_CHARS


def test_a_question_is_texted_then_the_answer_brings_the_message():
    r = lodge("the toilet is blocked").json()
    assert r["status"] == "awaiting_tenant" and r["sms"]["status"] == "demo"
    a = C.post(f"/api/requests/{r['request_id']}/clarify", json={"answer": "yes it is the only one"}).json()
    assert a["sms"]["status"] == "demo"
    kinds = [m["kind"] for m in C.get(f"/api/requests/{r['request_id']}").json()["sms"]]
    assert kinds == ["question", "report"]


def test_staff_questions_and_tier_changes_reach_the_tenant():
    rid = lodge().json()["request_id"]
    C.post(f"/api/requests/{rid}/decision", json={"action": "request_info", "reason": "Which room is the tap in?"})
    C.post(f"/api/requests/{rid}/clarify", json={"answer": "the kitchen sink tap"})
    C.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Urgent",
                                                  "reason": "confirmed on the phone with the tenant"})
    log = C.get(f"/api/requests/{rid}").json()["sms"]
    assert [m["kind"] for m in log] == ["report", "question", "report", "update"]
    assert "Which room is the tap in?" in log[1]["body"]
    assert log[-1]["body"].startswith("FairTriage NT update")


def test_the_same_text_is_not_sent_twice():
    r = lodge().json()
    again = sms.after_result({"request_id": r["request_id"], "status": "ranked",
                              "explanation_tenant": C.get(f"/api/requests/{r['request_id']}").json()["assessment"]["explanation_tenant"]})
    assert again.get("repeat") and len(C.get(f"/api/requests/{r['request_id']}").json()["sms"]) == 1


def test_a_long_message_is_trimmed_to_one_text_keeping_reference_and_link():
    long = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(12))
    t = sms.compose_report("NTF3-00001-abcd", long)
    assert len(t) <= sms.MAX_CHARS and t.startswith("FairTriage NT repair NTF3-00001-abcd")
    assert t.endswith("/track/NTF3-00001-abcd")


def test_a_lost_reference_is_texted_again():
    rid = lodge().json()["request_id"]
    r = C.post("/api/sms/resend", json={"phone": "+61412345678"})
    assert r.status_code == 200 and "If that number is on a repair report" in r.json()["message"]
    sent = db.col(sms.SMS).find_one({"kind": "resend", "status": "demo"})
    assert rid in sent["body"] and f"/track/{rid}" in sent["body"]


def test_resend_reveals_nothing_about_unknown_numbers():
    known = C.post("/api/sms/resend", json={"phone": "0499 999 999"}).json()
    lodge()
    other = C.post("/api/sms/resend", json={"phone": MOBILE}).json()
    assert known == other                                    # same reply either way
    assert db.col(sms.SMS).find_one({"to": "+61499999999"})["status"] == "no_match"


def test_resend_is_rate_limited():
    lodge()
    for _ in range(5):
        C.post("/api/sms/resend", json={"phone": MOBILE})
    assert db.col(sms.SMS).count_documents({"kind": "resend", "status": "demo"}) == sms.RESEND_LIMIT_PER_HOUR


def test_resend_needs_a_mobile_number():
    assert C.post("/api/sms/resend", json={"phone": "08 8999 1234"}).status_code == 422


# --- with a text service connected (a stand-in; nothing is really sent) ------

def connect(monkeypatch):
    st = config.settings()
    monkeypatch.setattr(st, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(st, "twilio_auth_token", "secret")
    monkeypatch.setattr(st, "twilio_from_number", "+61400000000")


def test_with_twilio_the_text_is_sent(monkeypatch):
    connect(monkeypatch)
    calls = []

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        calls.append(req)
        return Reply(json.dumps({"sid": "SM123"}).encode())

    monkeypatch.setattr(sms.urllib.request, "urlopen", fake_urlopen)
    r = lodge().json()
    assert r["sms"]["status"] == "sent" and r["sms"]["mode"] == "twilio"
    req = calls[0]
    assert "Accounts/ACtest/Messages.json" in req.full_url
    assert b"To=%2B61412345678" in req.data and req.headers["Authorization"].startswith("Basic ")


def test_a_failed_text_never_stops_the_report(monkeypatch):
    connect(monkeypatch)

    def broken(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"message":"invalid To"}'))

    monkeypatch.setattr(sms.urllib.request, "urlopen", broken)
    r = lodge()
    assert r.status_code == 200 and r.json()["tier"] == "Routine"
    assert r.json()["sms"]["status"] == "failed"
    log = C.get(f"/api/requests/{r.json()['request_id']}").json()["sms"]
    assert "invalid To" in log[0]["error"]


def test_the_original_tenant_form_also_requires_a_mobile():
    r = C.post("/tenant/lodge", data={"text": "the kitchen tap is dripping", "community": "Wadeye"})
    assert "mobile number starting 04" in r.text
    r = C.post("/tenant/lodge", data={"text": "the kitchen tap is dripping", "community": "Wadeye",
                                      "phone": "0412 345 678"})
    assert "Expect a tradesperson" in r.text
    assert db.col(sms.SMS).count_documents({"kind": "report"}) == 1
