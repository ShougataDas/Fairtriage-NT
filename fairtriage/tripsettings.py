"""The trip threshold: the equity lever a coordinator owns.

A remote community gets a planned trip for routine work when its oldest open
job has waited `community_threshold_multiple` times its service target. At
3.0 and a 25-day target that is up to 75 days; at 1.5 about 38, with more
trips and more cost. That is a values decision, not a technical one, so it is
made on screen by a person, with a reason, and recorded. The policy file
holds the starting value; a decision made on the Fairness page replaces it
until it is changed again.
"""

from __future__ import annotations

from . import db
from .config import policy
from .db import now

SETTINGS = "settings"
CHANGES = "policy_changes"
KEY = "community_threshold_multiple"
LIMITS = (1.0, 4.0)


class Invalid(Exception):
    pass


def file_value() -> float:
    return float(policy()["trips"][KEY])


def current() -> dict:
    doc = db.col(SETTINGS).find_one({"_id": KEY})
    if doc:
        return {"value": float(doc["value"]), "source": "coordinator", "actor": doc.get("actor"),
                "reason": doc.get("reason"), "at": doc.get("at"), "file_value": file_value()}
    return {"value": file_value(), "source": "policy file", "actor": None, "reason": None,
            "at": None, "file_value": file_value()}


def threshold() -> float:
    """The value the planner and the wait estimate use now."""
    doc = db.col(SETTINGS).find_one({"_id": KEY}, {"value": 1})
    return float(doc["value"]) if doc else file_value()


def set_threshold(value: float, reason: str | None, actor: str = "coordinator-demo") -> dict:
    lo, hi = LIMITS
    if not (lo <= value <= hi):
        raise Invalid(f"the threshold must be between {lo:g} and {hi:g} times the target")
    if not reason or len(reason.strip()) < 10:
        raise Invalid("say why: this changes how long remote tenants wait")
    before = threshold()
    value = round(value, 2)
    db.col(SETTINGS).update_one({"_id": KEY}, {"$set": {
        "value": value, "actor": actor, "reason": reason.strip(), "at": now()}}, upsert=True)
    db.append(CHANGES, {"request_id": None, "setting": KEY, "from": before, "to": value,
                        "actor": actor, "reason": reason.strip()})
    return current()


def history(limit: int = 20) -> list[dict]:
    rows = db.col(CHANGES).find({"setting": KEY}).sort("created_at", -1).limit(limit)
    return [{"from": r["from"], "to": r["to"], "actor": r["actor"], "reason": r["reason"],
             "at": r["created_at"]} for r in rows]
