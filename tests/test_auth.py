"""Sign-in and roles: tenants never reach staff data, staff are created only
by an admin, and every staff endpoint is checked on the server."""

import pytest
from fastapi.testclient import TestClient

from fairtriage import auth, config, db
from fairtriage.api import app

pytestmark = pytest.mark.usefixtures("real_auth")

ADMIN_PW = "correct horse battery"
STAFF_ROUTES = [("get", "/api/queue"), ("get", "/api/export?format=csv"), ("get", "/api/contacts"),
                ("get", "/api/alerts"), ("get", "/api/trips"), ("get", "/api/trips/preview"),
                ("get", "/api/metrics/equity"), ("get", "/api/policy/trip-threshold"),
                ("post", "/api/trips/plan"), ("get", "/coordinator"), ("get", "/coordinator/trips")]


@pytest.fixture
def admin_settings(monkeypatch):
    st = config.settings()
    monkeypatch.setattr(st, "admin_username", "admin")
    monkeypatch.setattr(st, "admin_password", ADMIN_PW)


def client():
    return TestClient(app)


def staff_client(username="admin", password=ADMIN_PW):
    c = client()
    r = c.post("/api/auth/signin", json={"kind": "staff", "identifier": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def tenant_client(phone="0412 345 678", password="tenant-pass-1"):
    c = client()
    r = c.post("/api/auth/register", json={"phone": phone, "password": password, "name": "Test Tenant"})
    assert r.status_code == 200, r.text
    return c


def report(c, text="the kitchen tap is dripping", phone="0412 345 678"):
    return c.post("/api/requests", json={"text": text, "community": "Darwin (Parap)", "phone": phone}).json()


# --- staff data is closed to everyone else ---------------------------------------

@pytest.mark.parametrize("method, path", STAFF_ROUTES)
def test_staff_routes_refuse_signed_out_visitors(method, path):
    assert getattr(client(), method)(path).status_code == 401


@pytest.mark.parametrize("method, path", STAFF_ROUTES)
def test_staff_routes_refuse_tenants(method, path):
    assert getattr(tenant_client(), method)(path).status_code == 403


def test_tenants_cannot_make_staff_decisions():
    c = tenant_client()
    rid = report(c)["request_id"]
    r = c.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Immediate",
                                                       "reason": "please make it urgent"})
    assert r.status_code == 403


# --- staff accounts ---------------------------------------------------------------

def test_the_first_admin_comes_from_settings(admin_settings):
    c = staff_client()
    me = c.get("/api/auth/me").json()["user"]
    assert me["role"] == "admin" and me["username"] == "admin"
    assert c.get("/api/queue").status_code == 200


def test_no_admin_without_settings():
    r = client().post("/api/auth/signin", json={"kind": "staff", "identifier": "admin", "password": "anything"})
    assert r.status_code == 401


def test_wrong_staff_password_is_refused_and_repeated_tries_are_paused(admin_settings):
    c = client()
    for _ in range(5):
        assert c.post("/api/auth/signin", json={"kind": "staff", "identifier": "admin",
                                                "password": "wrong"}).status_code == 401
    r = c.post("/api/auth/signin", json={"kind": "staff", "identifier": "admin", "password": ADMIN_PW})
    assert r.status_code == 429


def test_admin_adds_staff_and_staff_see_only_staff_things(admin_settings):
    a = staff_client()
    r = a.post("/api/staff/users", json={"username": "jsmith", "name": "J Smith", "password": "staff-pass-1",
                                         "role": "staff"})
    assert r.status_code == 200 and r.json()["role"] == "staff"
    s = staff_client("jsmith", "staff-pass-1")
    assert s.get("/api/queue").status_code == 200
    assert s.get("/api/staff/users").status_code == 403          # only an admin manages accounts
    assert s.get("/api/me/requests").status_code == 403          # the tenant area is not for staff


def test_there_is_no_public_staff_sign_up(admin_settings):
    assert client().post("/api/staff/users", json={"username": "me", "password": "12345678",
                                                   "role": "admin"}).status_code == 401
    t = tenant_client()
    assert t.post("/api/staff/users", json={"username": "me", "password": "12345678",
                                            "role": "admin"}).status_code == 403


def test_a_switched_off_account_loses_access_at_once(admin_settings):
    a = staff_client()
    uid = a.post("/api/staff/users", json={"username": "temp", "password": "staff-pass-1"}).json()["id"]
    s = staff_client("temp", "staff-pass-1")
    assert a.post(f"/api/staff/users/{uid}/active?active=false").status_code == 200
    assert s.get("/api/queue").status_code == 401                 # existing session refused
    r = client().post("/api/auth/signin", json={"kind": "staff", "identifier": "temp", "password": "staff-pass-1"})
    assert r.status_code == 403


def test_an_admin_cannot_switch_off_themself(admin_settings):
    a = staff_client()
    me = a.get("/api/auth/me").json()["user"]
    assert a.post(f"/api/staff/users/{me['id']}/active?active=false").status_code == 409


def test_admin_resets_a_password(admin_settings):
    a = staff_client()
    uid = a.post("/api/staff/users", json={"username": "kim", "password": "old-pass-11"}).json()["id"]
    assert a.post(f"/api/staff/users/{uid}/password", json={"password": "new-pass-22"}).status_code == 200
    staff_client("kim", "new-pass-22")


def test_decisions_are_recorded_under_the_staff_members_name(admin_settings):
    rid = report(client())["request_id"]
    a = staff_client()
    a.post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Urgent",
                                                  "reason": "elderly tenant, only sink", "actor": "someone-else"})
    assert a.get(f"/api/requests/{rid}").json()["decisions"][0]["actor"] == "admin"


# --- tenant accounts -----------------------------------------------------------------

def test_tenant_registers_with_a_mobile_and_password():
    c = tenant_client()
    me = c.get("/api/auth/me").json()["user"]
    assert me["role"] == "tenant" and me["phone"] == "+61412345678"


@pytest.mark.parametrize("phone, pw, status", [("08 8999 1234", "long-enough-1", 422),
                                               ("0412 345 678", "short", 422)])
def test_registration_checks(phone, pw, status):
    assert client().post("/api/auth/register", json={"phone": phone, "password": pw}).status_code == status


def test_one_account_per_mobile():
    tenant_client()
    r = client().post("/api/auth/register", json={"phone": "+61412345678", "password": "another-pass"})
    assert r.status_code == 409


def test_tenant_signs_in_again_and_out():
    tenant_client()
    c = client()
    r = c.post("/api/auth/signin", json={"kind": "tenant", "identifier": "0412345678", "password": "tenant-pass-1"})
    assert r.status_code == 200
    assert c.post("/api/auth/signout").status_code == 200
    assert c.get("/api/auth/me").json()["user"] is None


def test_wrong_tenant_password():
    tenant_client()
    r = client().post("/api/auth/signin", json={"kind": "tenant", "identifier": "0412 345 678", "password": "nope"})
    assert r.status_code == 401


def test_repairs_reported_while_signed_in_are_on_my_repairs():
    c = tenant_client()
    rid = report(c)["request_id"]
    mine = c.get("/api/me/requests").json()
    assert [m["request_id"] for m in mine] == [rid]


def test_another_tenant_never_sees_my_repairs():
    a = tenant_client("0412 345 678")
    report(a)
    b = tenant_client("0499 888 777")
    assert b.get("/api/me/requests").json() == []


def test_an_earlier_repair_is_added_with_its_reference_and_my_mobile():
    rid = report(client(), phone="0412 345 678")["request_id"]          # reported signed out
    c = tenant_client("0412 345 678")
    assert c.get("/api/me/requests").json() == []                        # not linked by mobile alone
    assert c.post("/api/me/claim", json={"reference": rid.upper()}).status_code == 200
    assert [m["request_id"] for m in c.get("/api/me/requests").json()] == [rid]


def test_someone_elses_repair_cannot_be_claimed():
    rid = report(client(), phone="0412 345 678")["request_id"]
    other = tenant_client("0499 888 777")
    assert other.post("/api/me/claim", json={"reference": rid}).status_code == 404


def test_my_repairs_needs_a_tenant_sign_in():
    assert client().get("/api/me/requests").status_code == 401


# --- what a reference shows to the public ------------------------------------------

def test_tracking_by_reference_still_works_signed_out_and_hides_staff_details(admin_settings):
    rid = report(client())["request_id"]
    staff_client().post(f"/api/requests/{rid}/decision", json={"action": "override", "to_tier": "Urgent",
                                                                "reason": "elderly tenant, only sink"})
    v = client().get(f"/api/requests/{rid}").json()
    assert v["assessment"]["explanation_tenant"]
    for hidden in ("phone", "sms", "extractions"):
        assert hidden not in v
    assert "explanation_coordinator" not in v["assessment"]
    assert all("actor" not in d for d in v["decisions"])
    full = staff_client().get(f"/api/requests/{rid}").json()
    assert full["phone"] == "+61412345678" and "explanation_coordinator" in full["assessment"]


def test_tenant_features_need_no_account():
    c = client()
    r = report(c)
    assert r["tier"] == "Routine"
    assert c.post(f"/api/requests/{r['request_id']}/why", json={}).status_code == 200
    assert c.post(f"/api/requests/{r['request_id']}/review", json={}).status_code == 200
    assert c.post("/api/sms/resend", json={"phone": "0412 345 678"}).status_code == 200
    assert c.get("/api/communities").status_code == 200


# --- the session itself ---------------------------------------------------------------

def test_a_tampered_session_is_refused():
    c = tenant_client()
    token = c.cookies.get(auth.COOKIE)
    body, sig = token.rsplit(".", 1)
    forged = auth._b64(auth._unb64(body).replace(b'"tenant"', b'"admin"')) + "." + sig
    c.cookies.clear()
    c.cookies.set(auth.COOKIE, forged)
    assert c.get("/api/auth/me").json()["user"] is None
    assert c.get("/api/queue").status_code == 401


def test_passwords_are_never_stored_in_plain_text():
    tenant_client(password="tenant-pass-1")
    u = db.col(auth.USERS).find_one({"role": "tenant"})
    assert "tenant-pass-1" not in u["password"] and u["password"].startswith("pbkdf2$")


def test_health_says_whether_sign_in_is_configured():
    h = client().get("/api/health").json()
    assert set(h["auth"]) == {"secret_set", "admin_from_settings"}
