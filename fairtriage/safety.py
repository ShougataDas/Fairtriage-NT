"""Safety reports: a life in danger that reached us through the repair form.

"My son is drowning in the sea" is not a repair, so it never enters the queue.
But it must not stop there either: the tenant is told to call 000, and the
staff member who reads it may have a duty to pass it on. In the Northern
Territory any person who believes a child is being harmed must report it
(Care and Protection of Children Act), and s124A of the Domestic and Family
Violence Act sets a reporting duty for serious family violence.

This module lists those reports, the authorities to contact, and records
every follow-up in an append-only collection: who reported it, to whom,
when, with what reference. A case stays open until someone records one.
"""

from __future__ import annotations

from . import db
from .db import REQUESTS, now

REFERRALS = "safety_referrals"

SAFETY_FLAGS = ("emergency_000", "person_hurt")

# Numbers checked against nt.gov.au (October 2026).
AGENCIES = [
    {"id": "000", "name": "Emergency: police, ambulance, fire", "phone": "000",
     "when": "A life is in danger right now. From a mobile with no signal, try 112."},
    {"id": "police", "name": "NT Police assistance line", "phone": "131 444",
     "when": "Police are needed but no one is in immediate danger, or to follow up a 000 call."},
    {"id": "child", "name": "NT Child Protection Hotline", "phone": "1800 700 250",
     "when": "A child is being harmed or is at risk, including seeing family violence. Any adult in the NT must report this. 24 hours."},
    {"id": "dv", "name": "1800RESPECT (family and domestic violence)", "phone": "1800 737 732",
     "when": "Advice and support for family violence. Serious violence must also go to police."},
    {"id": "mental_health", "name": "NT Mental Health Line", "phone": "1800 682 288",
     "when": "Someone may hurt themselves and is not in immediate danger. 24 hours."},
    {"id": "lifeline", "name": "Lifeline", "phone": "13 11 14",
     "when": "Crisis support for the person, any time."},
    {"id": "poisons", "name": "Poisons Information Centre", "phone": "13 11 26",
     "when": "Someone swallowed something harmful and is awake and breathing."},
]
AGENCY_IDS = {a["id"] for a in AGENCIES}

OUTCOMES = {
    "reported": "Reported to an authority",
    "already_reported": "Already reported by someone else (e.g. the tenant called 000)",
    "no_report_needed": "No report needed",
}


class Invalid(Exception):
    pass


class NotFound(Exception):
    pass


def _flags(req: dict) -> list[dict]:
    return [f for f in ((req.get("assessment") or {}).get("flags") or []) if f.get("code") in SAFETY_FLAGS]


def is_safety_case(req: dict) -> bool:
    return bool(_flags(req))


def cases() -> list[dict]:
    """Every safety report, open ones first, newest first within each."""
    rows = db.col(REQUESTS).find({"assessment.flags.code": {"$in": list(SAFETY_FLAGS)}})
    out = []
    for r in rows:
        flags = _flags(r)
        if not flags:
            continue
        history = db.history(REFERRALS, r["_id"])
        a = r.get("assessment") or {}
        out.append({
            "request_id": r["_id"], "lodged_at": r["lodged_at"], "text": r["text_original"],
            "community": r["dwelling"]["community"], "address": r["dwelling"].get("address"),
            "phone": r["dwelling"].get("phone"), "status": r["status"], "tier": a.get("tier"),
            "kind": "life_at_risk" if any(f["code"] == "emergency_000" for f in flags) else "person_hurt",
            "repair_too": a.get("tier") not in (None, "NotInQueue"),
            "referrals": history, "open": not history,
        })
    out.sort(key=lambda c: c["lodged_at"], reverse=True)
    out.sort(key=lambda c: not c["open"])
    return out


def open_count() -> int:
    return sum(1 for c in cases() if c["open"])


def record(request_id: str, *, actor: str, outcome: str, agency: str | None = None,
           reference: str | None = None, note: str | None = None) -> dict:
    """Append one follow-up. Never edited: a mistake is corrected by recording
    another entry, so the record shows what was done and when."""
    req = db.get_request(request_id)
    if req is None:
        raise NotFound(request_id)
    if not is_safety_case(req):
        raise Invalid(f"{request_id} is not a safety report")
    if outcome not in OUTCOMES:
        raise Invalid("choose what was done")
    note = (note or "").strip()
    reference = (reference or "").strip() or None
    if outcome == "reported" and agency not in AGENCY_IDS:
        raise Invalid("choose who it was reported to")
    if outcome == "no_report_needed" and len(note) < 10:
        raise Invalid("say why no report is needed (at least 10 characters)")
    entry = db.append(REFERRALS, {
        "request_id": request_id, "outcome": outcome,
        "agency": agency if outcome == "reported" else None,
        "reference": reference, "note": note or None, "actor": actor, "at": now()})
    entry.pop("_id", None)
    return entry
