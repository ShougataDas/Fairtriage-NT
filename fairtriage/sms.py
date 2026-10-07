"""Text messages to tenants.

A tenant who loses their reference cannot see their repair's progress. So the
message they were shown is also texted to the mobile number they gave, with
the reference at the top and a link to track it; a staff question is texted
too, and a tenant who has lost everything can ask for their references to be
texted again from the Track page.

Sending uses Twilio's REST API when TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and
TWILIO_FROM_NUMBER are set. Without them the system runs in DEMO MODE: each
text is composed and recorded exactly as it would be sent, staff can read it,
and the tenant is told plainly that no text was sent. Every text, sent or not,
is logged with its status; a failure never stops a report being lodged.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import db
from .config import settings
from .db import REQUESTS

SMS = "sms"
MAX_CHARS = 1600                  # Twilio's limit for one (multi-part) message
RESEND_LIMIT_PER_HOUR = 3


class Invalid(Exception):
    pass


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def normalise_mobile(raw: str | None) -> str | None:
    """An Australian mobile in +614XXXXXXXX form, or None if it is not one.
    Texts only reach mobiles, so a landline (08 …) is not accepted."""
    if not raw:
        return None
    d = re.sub(r"[\s().-]", "", raw.strip())
    if re.fullmatch(r"04\d{8}", d):
        return "+61" + d[1:]
    if re.fullmatch(r"\+614\d{8}", d):
        return d
    if re.fullmatch(r"614\d{8}", d):
        return "+" + d
    if re.fullmatch(r"4\d{8}", d):
        return "+61" + d
    return None


def mobile_problem(raw: str | None) -> str:
    """Why a number is not an Australian mobile, in plain words."""
    s = (raw or "").strip()
    if not s:
        return "Enter a mobile number so we can text you your reference number and this message."
    if re.search(r"[^\d\s()+.-]", s):
        return "Use numbers only, like 0412 345 678."
    d = re.sub(r"[\s().-]", "", s)
    if d.startswith("+61"):
        d = "0" + d[3:]
    elif d.startswith("61") and len(d) >= 11:
        d = "0" + d[2:]
    elif d.startswith("4") and len(d) == 9:
        d = "0" + d
    if d.startswith("04"):
        return f"An Australian mobile has 10 digits, like 0412 345 678. This one has {len(d)}."
    if d.startswith("0"):
        return "That looks like a landline. Texts can only go to a mobile, starting 04."
    return "Enter a mobile number starting 04, like 0412 345 678."


def mask(e164: str | None) -> str | None:
    """+61412345678 -> 0412 ••• 678: enough for a tenant to recognise it."""
    if not e164 or not e164.startswith("+61"):
        return None
    local = "0" + e164[3:]
    return f"{local[:4]} ••• {local[-3:]}"


def provider_ready() -> bool:
    st = settings()
    return bool(st.twilio_account_sid and st.twilio_auth_token and st.twilio_from_number)


def mode() -> str:
    return "twilio" if provider_ready() else "demo"


# ---------------------------------------------------------------------------
# What is sent
# ---------------------------------------------------------------------------

def _link(rid: str) -> str:
    return f"{settings().public_web_url.rstrip('/')}/track/{rid}"


def compose_report(rid: str, explanation: str, update: bool = False) -> str:
    """The verified message the tenant was shown, reference first, link last.
    Trimmed only to fit one text, paragraph by paragraph from the end."""
    head = f"FairTriage NT {'update' if update else 'repair'} {rid}"
    tail = f"Track it: {_link(rid)}"
    paras = [p.strip() for p in explanation.split("\n\n") if p.strip()]
    body = paras[:]
    while body:
        text = "\n\n".join([head] + body + [tail])
        if len(text) <= MAX_CHARS:
            return text
        body = body[:-1]
    return f"{head}\n\n{tail}"


def compose_question(rid: str, question: str) -> str:
    return (f"FairTriage NT repair {rid}\n\nWe need one answer before we can rank your repair: "
            f"{question}\n\nAnswer here: {_link(rid)}")


# ---------------------------------------------------------------------------
# Sending and the log
# ---------------------------------------------------------------------------

def _twilio(to: str, body: str) -> tuple[str, str | None, str | None]:
    """(status, provider message id, error)."""
    st = settings()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{st.twilio_account_sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to, "From": st.twilio_from_number, "Body": body}).encode()
    token = base64.b64encode(f"{st.twilio_account_sid}:{st.twilio_auth_token}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            out = json.loads(r.read().decode() or "{}")
            return "sent", out.get("sid"), None
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("message")
        except Exception:
            msg = None
        return "failed", None, f"HTTP {e.code}: {msg or e.reason}"[:300]
    except Exception as e:                         # network, timeout
        return "failed", None, str(e)[:300]


def send(request_id: str | None, to: str | None, body: str, kind: str) -> dict:
    """Send (or, in demo mode, record) one text. Never raises."""
    if not to:
        return {"status": "no_number", "to": None, "mode": mode()}
    if request_id:
        dup = db.col(SMS).find_one({"request_id": request_id, "kind": kind, "body": body,
                                    "status": {"$in": ["sent", "demo"]}})
        if dup:
            return {"status": dup["status"], "to": mask(to), "mode": dup["mode"], "repeat": True}
    if provider_ready():
        status, sid, err = _twilio(to, body)
    else:
        status, sid, err = "demo", None, None
    db.append(SMS, {"request_id": request_id, "to": to, "kind": kind, "body": body,
                    "status": status, "mode": mode(), "provider_id": sid, "error": err})
    return {"status": status, "to": mask(to), "mode": mode()}


def log(request_id: str) -> list[dict]:
    return [{"kind": r["kind"], "status": r["status"], "mode": r.get("mode"), "to": mask(r["to"]),
             "body": r["body"], "error": r.get("error"), "at": r["created_at"]}
            for r in db.history(SMS, request_id)]


def phone_of(request_id: str) -> str | None:
    req = db.get_request(request_id)
    return normalise_mobile((req or {}).get("dwelling", {}).get("phone"))


def after_result(result: dict, update: bool = False) -> dict | None:
    """Text what the tenant has just been shown: the question, or the message."""
    rid = result.get("request_id")
    if not rid:
        return None
    to = phone_of(rid)
    if result.get("status") == "awaiting_tenant" and result.get("question"):
        return send(rid, to, compose_question(rid, result["question"]), "question")
    text = result.get("explanation_tenant")
    if text:
        return send(rid, to, compose_report(rid, text, update=update), "update" if update else "report")
    return None


# ---------------------------------------------------------------------------
# "I lost my reference"
# ---------------------------------------------------------------------------

STATUS_WORDS = {"awaiting_tenant": "waiting for your answer", "ranked": "in the queue",
                "approved": "checked by staff", "scheduled": "trip booked", "completed": "done",
                "not_in_queue": "not a repair job", "needs_phone_call": "staff will phone you",
                "awaiting_confirmation": "staff will check with you"}


def resend(raw_phone: str) -> dict:
    """Text every recent reference on this number to this number. The reply is
    the same whether or not the number is on a report, so the page cannot be
    used to find out who has reported a repair."""
    to = normalise_mobile(raw_phone)
    if not to:
        raise Invalid(mobile_problem(raw_phone))
    reply = {"ok": True, "message": "If that number is on a repair report, we have texted it the "
                                    "reference numbers. It can take a few minutes to arrive."}
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    recent = db.col(SMS).count_documents({"to": to, "kind": "resend", "created_at": {"$gte": since}})
    if recent >= RESEND_LIMIT_PER_HOUR:
        return reply
    reqs = [r for r in db.col(REQUESTS).find().sort("lodged_at", -1)
            if normalise_mobile(r.get("dwelling", {}).get("phone")) == to][:5]
    if not reqs:
        db.append(SMS, {"request_id": None, "to": to, "kind": "resend", "body": None,
                        "status": "no_match", "mode": mode(), "provider_id": None, "error": None})
        return reply
    lines = [f"{r['_id']}: {STATUS_WORDS.get(r['status'], r['status'].replace('_', ' '))}, "
             f"{r['dwelling']['community']}. {_link(r['_id'])}" for r in reqs]
    body = "FairTriage NT: your repair reference numbers\n\n" + "\n\n".join(lines)
    send(None, to, body[:MAX_CHARS], "resend")
    return reply

