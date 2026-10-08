"""Sign-in and roles.

Three roles:
    tenant   signs in with their mobile number and a password. Sees their own
             repairs ("My repairs"). Signing in is optional: reporting and
             tracking by reference never need an account, so nobody facing an
             emergency is stopped by a login.
    staff    signs in with a username. Sees only the staff area.
    admin    staff who can also add, deactivate and reactivate staff accounts.

There is no public staff sign-up. The first admin comes from the settings
FAIRTRIAGE_ADMIN_USERNAME and FAIRTRIAGE_ADMIN_PASSWORD: the first time that
username signs in with that password, the account is created. Every staff
data endpoint checks the session on the server, so hiding links is never the
only protection.

A repair is linked to a tenant account only when it is reported while signed
in, or added with its reference number and the account's own mobile. Accounts
are not verified by text, so a matching mobile alone is never enough: anyone
could register someone else's number.

Passwords: PBKDF2-SHA256, 200,000 rounds, random salt (Python's standard
library). Sessions: a signed token (HMAC-SHA256 with FAIRTRIAGE_AUTH_SECRET) in
an http-only cookie, valid 7 days; checked against the account on every
request, so a deactivated account loses access at once.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response

from . import db
from .config import settings
from .db import REQUESTS, now

USERS = "users"
ATTEMPTS = "login_attempts"
COOKIE = "ft_session"
SESSION_DAYS = 7
DEV_SECRET = "dev-only-secret-change-me"
MAX_FAILURES = 5                    # wrong passwords in 15 minutes before a pause
LOCK_MINUTES = 15


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Passwords and tokens
# ---------------------------------------------------------------------------

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"pbkdf2$200000${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, rounds, salt, h = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(test, base64.b64decode(h))
    except Exception:
        return False


def _secret() -> bytes:
    return (settings().auth_secret or DEV_SECRET).encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user: dict) -> str:
    body = _b64(json.dumps({"uid": user["_id"], "role": user["role"],
                            "exp": int(time.time()) + SESSION_DAYS * 86400}).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(_unb64(body))
    except Exception:
        return None
    return data if data.get("exp", 0) > time.time() else None


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def public(user: dict) -> dict:
    return {"id": user["_id"], "role": user["role"], "name": user.get("name") or "",
            "username": user.get("username"), "phone": user.get("phone"),
            "active": user.get("active", True), "created_at": user.get("created_at")}


def _check_new_password(pw: str) -> None:
    if len(pw or "") < 8:
        raise AuthError(422, "Use a password of at least 8 characters.")


def register_tenant(phone: str, password: str, name: str | None) -> dict:
    from .sms import mobile_problem, normalise_mobile
    mobile = normalise_mobile(phone)
    if not mobile:
        raise AuthError(422, mobile_problem(phone))
    _check_new_password(password)
    if db.col(USERS).find_one({"role": "tenant", "phone": mobile}):
        raise AuthError(409, "There is already an account for this mobile number. Sign in instead.")
    user = {"_id": f"u-{uuid.uuid4().hex[:12]}", "role": "tenant", "phone": mobile,
            "name": (name or "").strip()[:80], "password": hash_password(password),
            "active": True, "created_at": now()}
    db.col(USERS).insert_one(user)
    return user


def _locked(key: str) -> bool:
    since = (datetime.now(timezone.utc) - timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
    return db.col(ATTEMPTS).count_documents({"key": key, "at": {"$gte": since}}) >= MAX_FAILURES


def _failed(key: str) -> None:
    db.col(ATTEMPTS).insert_one({"key": key, "at": now()})


def _bootstrap_admin(username: str, password: str) -> dict | None:
    """The first admin, from settings, created on its first sign-in."""
    st = settings()
    if not st.admin_password or username != st.admin_username.strip().lower():
        return None
    if not hmac.compare_digest(password, st.admin_password):
        return None
    if db.col(USERS).find_one({"role": {"$in": ["staff", "admin"]}, "username": username}):
        return None
    user = {"_id": f"u-{uuid.uuid4().hex[:12]}", "role": "admin", "username": username,
            "name": "Administrator", "password": hash_password(password),
            "active": True, "created_at": now()}
    db.col(USERS).insert_one(user)
    return user


def sign_in(kind: str, identifier: str, password: str) -> dict:
    """kind: 'tenant' (mobile number) or 'staff' (username)."""
    if kind == "tenant":
        from .sms import normalise_mobile
        ident = normalise_mobile(identifier) or (identifier or "").strip()
        query = {"role": "tenant", "phone": ident}
    elif kind == "staff":
        ident = (identifier or "").strip().lower()
        query = {"role": {"$in": ["staff", "admin"]}, "username": ident}
    else:
        raise AuthError(422, "Choose tenant or staff sign-in.")
    key = f"{kind}:{ident}"
    if _locked(key):
        raise AuthError(429, f"Too many wrong passwords. Try again in {LOCK_MINUTES} minutes.")
    user = db.col(USERS).find_one(query)
    if user is None and kind == "staff":
        user = _bootstrap_admin(ident, password)
    if user is None or not check_password(password, user["password"]):
        _failed(key)
        raise AuthError(401, "That mobile number and password do not match." if kind == "tenant"
                        else "That username and password do not match.")
    if not user.get("active", True):
        raise AuthError(403, "This account has been switched off. Ask an administrator.")
    return user


def set_session(response: Response, request: Request, user: dict) -> None:
    secure = (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"
    response.set_cookie(COOKIE, make_token(user), max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=secure, path="/")


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


# ---------------------------------------------------------------------------
# Who is asking (FastAPI dependencies)
# ---------------------------------------------------------------------------

def optional_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    hdr = request.headers.get("authorization", "")
    if not token and hdr.lower().startswith("bearer "):
        token = hdr[7:].strip()
    data = read_token(token)
    if not data:
        return None
    user = db.col(USERS).find_one({"_id": data["uid"]})
    if not user or not user.get("active", True):
        return None
    return user


def require_staff(user: dict | None = Depends(optional_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in as staff to see this.")
    if user["role"] not in ("staff", "admin"):
        raise HTTPException(403, "This is for maintenance staff only.")
    return user


def require_admin(user: dict = Depends(require_staff)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Only an administrator can manage staff accounts.")
    return user


def require_tenant(user: dict | None = Depends(optional_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in to see your repairs.")
    if user["role"] != "tenant":
        raise HTTPException(403, "This page is for tenants.")
    return user


def actor_of(user: dict) -> str:
    return user.get("username") or user["_id"]


# ---------------------------------------------------------------------------
# A tenant's repairs
# ---------------------------------------------------------------------------

def my_requests(user: dict) -> list[dict]:
    rows = db.col(REQUESTS).find({"owner_id": user["_id"]}).sort("lodged_at", -1)
    out = []
    for r in rows:
        a = r.get("assessment") or {}
        out.append({"request_id": r["_id"], "status": r["status"], "lodged_at": r["lodged_at"],
                    "community": r["dwelling"]["community"], "address": r["dwelling"].get("address"),
                    "text": r["text_original"], "tier": a.get("tier")})
    return out


def claim(user: dict, reference: str) -> dict:
    """Add an earlier repair to the account: the reference must exist and must
    have been reported with this account's own mobile number."""
    from .sms import normalise_mobile
    ref = (reference or "").strip()
    m = re.fullmatch(r"(?i)(NTF3-\d{5}-)([0-9a-f]{4})", ref)
    ref = (m.group(1).upper() + m.group(2).lower()) if m else ref
    req = db.get_request(ref)
    if not req or normalise_mobile(req["dwelling"].get("phone")) != user.get("phone"):
        raise AuthError(404, "We could not find a repair with that reference reported with your mobile number.")
    if req.get("owner_id") and req["owner_id"] != user["_id"]:
        raise AuthError(409, "That repair is already on another account.")
    db.update_request(ref, {"owner_id": user["_id"]})
    return {"request_id": ref, "linked": True}


# ---------------------------------------------------------------------------
# Staff accounts (admin)
# ---------------------------------------------------------------------------

def list_staff() -> list[dict]:
    return [public(u) for u in db.col(USERS).find({"role": {"$in": ["staff", "admin"]}}).sort("created_at", 1)]


def add_staff(username: str, name: str, password: str, role: str) -> dict:
    u = (username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,32}", u):
        raise AuthError(422, "Username: 3 to 32 letters, numbers, dots, dashes or underscores.")
    if role not in ("staff", "admin"):
        raise AuthError(422, "Role must be staff or admin.")
    _check_new_password(password)
    if db.col(USERS).find_one({"role": {"$in": ["staff", "admin"]}, "username": u}):
        raise AuthError(409, "That username is taken.")
    user = {"_id": f"u-{uuid.uuid4().hex[:12]}", "role": role, "username": u,
            "name": (name or "").strip()[:80], "password": hash_password(password),
            "active": True, "created_at": now()}
    db.col(USERS).insert_one(user)
    return public(user)


def set_active(admin: dict, user_id: str, active: bool) -> dict:
    user = db.col(USERS).find_one({"_id": user_id, "role": {"$in": ["staff", "admin"]}})
    if not user:
        raise AuthError(404, "No such staff account.")
    if user["_id"] == admin["_id"] and not active:
        raise AuthError(409, "You cannot switch off your own account.")
    db.col(USERS).update_one({"_id": user_id}, {"$set": {"active": active}})
    user["active"] = active
    return public(user)


def reset_password(user_id: str, password: str) -> dict:
    _check_new_password(password)
    user = db.col(USERS).find_one({"_id": user_id, "role": {"$in": ["staff", "admin"]}})
    if not user:
        raise AuthError(404, "No such staff account.")
    db.col(USERS).update_one({"_id": user_id}, {"$set": {"password": hash_password(password)}})
    return public(user)


def status() -> dict:
    st = settings()
    return {"secret_set": bool(st.auth_secret), "admin_from_settings": bool(st.admin_password)}
