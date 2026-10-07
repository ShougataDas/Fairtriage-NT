import re

from fastapi.testclient import TestClient

from fairtriage.api import app

c = TestClient(app)


def test_health():
    assert c.get("/api/health").json()["ok"]


def test_every_page_renders():
    for p in ["/tenant", "/coordinator", "/coordinator?order=cost",
              "/coordinator/trips", "/coordinator/equity"]:
        assert c.get(p).status_code == 200, p


def test_tenant_html_flow_question_then_docket():
    r = c.post("/tenant/lodge", data={"text": "toilet is blocked.", "community": "Wadeye", "phone": "0412 345 678"})
    assert "only toilet" in r.text
    rid = re.search(r"/tenant/(NTF3-[\w-]+)/clarify", r.text).group(1)
    r = c.post(f"/tenant/{rid}/clarify", data={"answer": "yes only one"})
    assert "Customer copy" in r.text and "stamp Urgent" in r.text


def test_json_api_round_trip():
    r = c.post("/api/requests", json={"text": "power point sparking", "community": "Belyuen", "phone": "0412 345 678"})
    assert r.status_code == 200 and r.json()["tier"] == "Immediate"
    rid = r.json()["request_id"]
    assert c.get(f"/api/requests/{rid}").json()["assessment"]["tier"] == "Immediate"


def test_unknown_community_is_rejected():
    r = c.post("/api/requests", json={"text": "x", "community": "Atlantis", "phone": "0412 345 678"})
    assert r.status_code == 422


def test_override_without_reason_rejected_over_http():
    rid = c.post("/api/requests", json={"text": "the only toilet is blocked",
                                        "community": "Belyuen", "phone": "0412 345 678"}).json()["request_id"]
    r = c.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Routine"})
    assert r.status_code == 422


def test_emergency_instruction_is_first_and_boxed():
    r = c.post("/tenant/lodge", data={"text": "the kitchen caught fire", "community": "Wadeye", "phone": "0412 345 678"})
    html = r.text
    assert 'class="emergency" role="alert"' in html
    assert html.index("call 000 now") < html.index('class="stamp')


def test_000_line_is_not_an_alarm_box_in_an_ordinary_unclear_docket():
    r = c.post("/tenant/lodge", data={"text": "something is off", "community": "Wadeye", "phone": "0412 345 678"})
    rid = re.search(r"/tenant/(NTF3-[\w-]+)/clarify", r.text).group(1)
    html = c.post(f"/tenant/{rid}/clarify", data={"answer": "dunno"}).text
    assert 'class="emergency"' not in html and "call 000 now" in html


def test_json_endpoints_for_the_web_app():
    c.post("/api/requests", json={"text": "power point sparking", "community": "Wadeye", "phone": "0412 345 678"})
    groups = c.get("/api/communities").json()
    assert any(x["name"] == "Wadeye" and x["remote"] for g in groups for x in g["communities"])
    assert c.get("/api/contacts").status_code == 200
    assert c.get("/api/trips").json() == []
    rows = c.get("/api/queue?order=cost").json()
    assert rows and all("shift" in r and "display_pos" in r for r in rows)
    assert "rules" in c.get("/api/trips/preview").json()
