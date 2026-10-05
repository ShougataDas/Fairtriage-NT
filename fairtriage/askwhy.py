"""A tenant asks "why is my repair here?" and gets a real answer.

Built only from the record and today's queue, never generated free text, so
every number in it is a fact the system holds:

    - its group and the reason for it
    - who is ahead and WHY each of them is ahead: more dangerous, more need
      in the same group, or the same need but reported earlier
    - that where they live did not change their place (the same job in Darwin
      would be in the same place), and what travel adds to WHEN
    - what changed since they reported: a staff decision and its reason, trips
      that were full, repairs reported later that are more dangerous
    - what would move it up, and how to ask a person

A tenant who is not satisfied can ask for a review. That puts the request
on the coordinator's phone list with their message until someone acts on it.
"""

from __future__ import annotations

import re
from datetime import datetime

from . import db
from .db import DECISIONS, REQUESTS, now
from .explain import BANNED
from .policy import TIER_ORDER, sort_key
from .queue import open_jobs

# why a report is not in the queue, in plain words (the stored reason names a code)
NOT_IN_QUEUE_WHY = {
    "no_issue": "it said things were fine or already fixed",
    "question": "it was a question rather than a repair to book",
    "follow_up": "it asked about an earlier report rather than a new repair",
    "withdrawal": "it asked to cancel the repair; a staff member will confirm with you",
    "out_of_scope": "it is about something the housing maintenance team does not repair",
    "unclear": "we could not tell what needs fixing; a staff member will phone you",
}

WHAT_TIER_MEANS = {
    "Immediate": "someone could be hurt today, so these are made safe first",
    "Urgent": "an essential service such as water, power, a toilet or cooking is out",
    "Routine": "it needs fixing but is not dangerous and nothing essential is out",
}


class NotFound(Exception):
    pass


def _n(k: int, one: str, many: str) -> str:
    return f"{k} {one if k == 1 else many}"


def _day(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')}"


def answer(request_id: str, question: str | None = None) -> dict:
    from .service import _trip_info, live_wait
    req = db.get_request(request_id)
    if req is None:
        raise NotFound(request_id)
    q = (question or "").strip()[:500]
    db.col(REQUESTS).update_one({"_id": request_id},
                                {"$push": {"tenant_questions": {"question": q or None, "at": now()}}})
    a = req.get("assessment")
    paras: list[str] = []

    if req["status"] == "awaiting_tenant":
        paras.append(f"Your repair is not ranked yet: we asked you a question and are waiting for "
                     f"your answer. The question was: “{req.get('clarification_q') or ''}”")
        return _done(request_id, q, paras)
    if not a:
        paras.append("Your report is still being read. Check again in a minute.")
        return _done(request_id, q, paras)

    tier, facts = a["tier"], a.get("facts") or {}
    if req["status"] == "completed":
        paras.append("This repair has been marked as done. If it is not fixed, ask for a review "
                     "below and a person will follow it up.")
        return _done(request_id, q, paras)
    if tier == "NotInQueue":
        why = NOT_IN_QUEUE_WHY.get(facts.get("actionability") or "", "it did not describe a fault")
        paras.append(f"Your report is not in the repair queue because {why}.")
        paras.append("If something does need fixing, tell us what is wrong and where in the house, "
                     "or ask for a review below and a person will look at it.")
        return _done(request_id, q, paras)

    # 1. its group, and what that means
    paras.append(f"Your repair is in the {tier} group because {facts.get('tier_reason') or WHAT_TIER_MEANS[tier]}. "
                 f"{tier} means {WHAT_TIER_MEANS[tier]}.")

    trip = _trip_info(req, req["dwelling"]["community"])
    if trip:
        paras.append(f"It is booked on a maintenance trip: stop {trip['stop']} of {trip['stops']}. "
                     + (trip.get("tenant_update") or ""))

    # 2. who is ahead, and why each is ahead
    me = sort_key(tier, a["need_score"], req["lodged_at"])
    jobs = open_jobs(exclude=request_id)
    ahead = [j for j in jobs if j.key < me]
    if not ahead:
        paras.append("No repair is ahead of yours in the queue.")
    else:
        mine_order = TIER_ORDER[tier]
        higher = [j for j in ahead if TIER_ORDER[j.tier] < mine_order]
        same = [j for j in ahead if TIER_ORDER[j.tier] == mine_order]
        more_need = [j for j in same if j.need > a["need_score"] + 1e-9]
        earlier = [j for j in same if j not in more_need]
        parts = []
        for t in ("Immediate", "Urgent"):
            k = sum(1 for j in higher if j.tier == t)
            if k:
                parts.append(f"{_n(k, 'is', 'are')} {t}, where {WHAT_TIER_MEANS[t].split(', so')[0]}")
        if more_need:
            parts.append(f"{_n(len(more_need), 'is', 'are')} {tier} like yours but {'has' if len(more_need) == 1 else 'have'} "
                         f"more need: more of the house affected, the problem getting worse, or a "
                         f"vulnerable person living there")
        if earlier:
            parts.append(f"{_n(len(earlier), 'is', 'are')} the same as yours but {'was' if len(earlier) == 1 else 'were'} reported earlier")
        paras.append(f"There {'is' if len(ahead) == 1 else 'are'} {_n(len(ahead), 'repair', 'repairs')} ahead of yours. "
                     f"Of those, " + "; ".join(parts) + ".")
        later = [j for j in ahead if j.lodged_at > req["lodged_at"]]
        if later:
            paras.append(f"{_n(len(later), 'repair was', 'repairs were')} reported after yours and still "
                         f"{'goes' if len(later) == 1 else 'go'} first, because {'it is' if len(later) == 1 else 'they are'} "
                         f"more dangerous or {'has' if len(later) == 1 else 'have'} more need. Nobody goes ahead "
                         f"because they live closer.")

    # 3. location: not in the order, only in the travel
    # today's place, recomputed: rank never uses location, so the same repair
    # in Darwin is in the same place by construction
    rank = 1 + sum(1 for j in jobs if j.tier == tier and j.key < me)
    reach = a.get("reachability") or {}
    loc = (f"You are number {rank} in the {tier} group today. Where you live did not change "
           f"that: the same repair in Darwin would be number {rank} too.")
    w = live_wait(req)
    if w and not w.get("on_trip"):
        loc += f" Expect a tradesperson {w['range_text']}."
        if reach.get("remote"):
            loc += (" Travel to your community is part of that time: it changes when a crew can "
                    "arrive, never who is first.")
    paras.append(loc)

    # 4. what changed since they reported
    changed = []
    for d in db.history(DECISIONS, request_id):
        if d["action"] == "override" and d.get("reason"):
            direction = ("moved it down" if TIER_ORDER.get(d["to_tier"], 0) > TIER_ORDER.get(d["from_tier"], 0)
                         else "moved it up" if TIER_ORDER.get(d["to_tier"], 0) < TIER_ORDER.get(d["from_tier"], 0)
                         else "kept it")
            changed.append(f"On {_day(d['created_at'])} a staff member {direction} from {d['from_tier']} to "
                           f"{d['to_tier']}. Their reason: “{d['reason']}”")
    if req.get("prior_deferrals"):
        k = req["prior_deferrals"]
        changed.append(f"Your repair was left off {_n(k, 'planned trip', 'planned trips')} because "
                       f"{'it was' if k == 1 else 'they were'} already full of more urgent work. It kept its place "
                       f"in the queue, and staff are alerted when a repair is left off more than once.")
    told = (facts.get("wait") or {}).get("range_text")
    if told and w and not w.get("on_trip") and told != w["range_text"]:
        changed.append(f"When you reported, we said to expect a tradesperson {told}. "
                       f"Today it is {w['range_text']}, worked out again from the current queue.")
    if changed:
        paras.append("What has changed: " + " ".join(changed))

    # 5. what would move it up
    paras.append("What can move it up: tell us if it gets worse (sparks, a burning smell, water near "
                 "power, sewage inside, rain coming in), or if someone in the house is elderly, has a "
                 "disability, has young children or relies on medical equipment and we have not been told. "
                 "If you think we have got it wrong, ask for a review and a person will look at it.")
    return _done(request_id, q, paras)


def _done(rid: str, q: str, paras: list[str]) -> dict:
    # the same rule as every tenant text: no apologies, no promises
    # quoted words (the tenant's, a staff member's reason) are theirs, not ours
    text = re.sub("“[^”]*”", " ", " ".join(paras)).lower()
    paras = [p for p in paras if p] if not any(b in text for b in BANNED) else [
        "We could not build an answer for this request. Ask for a review and a person will explain."]
    return {"request_id": rid, "question": q or None, "answer": paras, "asked_at": now()}


def request_review(request_id: str, message: str | None) -> dict:
    req = db.get_request(request_id)
    if req is None:
        raise NotFound(request_id)
    msg = (message or "").strip()[:500] or None
    db.col(REQUESTS).update_one({"_id": request_id}, {
        "$set": {"review_requested": True, "review_requested_at": now()},
        "$push": {"review_requests": {"message": msg, "at": now()}}})
    has_phone = bool(req["dwelling"].get("phone"))
    return {"request_id": request_id, "review_requested": True, "message": msg,
            "reply": ("Your request for a review has been sent to the maintenance team. A staff member "
                      "will look at your repair" + (" and phone you." if has_phone else
                                                     ". Check this page for the outcome, or add a phone "
                                                     "number next time so we can call you."))}

