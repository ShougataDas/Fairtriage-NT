"""Orchestration used by both the API and the web UI.

lodge()   persist verbatim -> run graph -> either pause for a question or
          finalise into a ranked recommendation
clarify() resume the paused graph with the tenant's answer
decide()  append a human decision; an override needs a reason and is shown
          to the tenant

Nothing here dispatches anything. The system recommends and stops.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog
from langgraph.types import Command

from . import graph as G
from .config import policy
from . import db
from .db import ASSESSMENTS, DECISIONS, EXTRACTIONS, REQUESTS, now
from .explain import fact_sheet, render_coordinator, render_tenant, verify
from .queue import job_trade, open_jobs, position
from .reference import area_of, communities
from .schemas import DecisionIn, Extraction, LodgeIn
from .wait import estimate, fmt_range, plural_days, reachability

log = structlog.get_logger()


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def _new_id() -> str:
    return f"NTF3-{db.next_seq('request'):05d}-{uuid.uuid4().hex[:4]}"


# ---------------------------------------------------------------------------

def lodge(inp: LodgeIn, lodged_at: str | None = None) -> dict:
    if inp.community not in communities():
        raise Invalid(f"unknown community: {inp.community}")
    rid = _new_id()
    db.col(REQUESTS).insert_one({
        "_id": rid, "lodged_at": lodged_at or now(), "text_original": inp.text,
        "text_normalised": None, "status": "lodged",
        "dwelling": {"community": inp.community,
                     "address": (inp.address or "").strip() or None,
                     "phone": (inp.phone or "").strip() or None,
                     "vulnerability": list(inp.vulnerability),
                     "alternative_toilet": inp.alternative_toilet},
        "clarification_q": None, "clarification_a": None,
        "prior_deferrals": 0, "advanced_by": None,
        "trip_id": None, "trip_stop": None, "trip_stops": None, "eta_at": None,
        "assessment": None, "extraction": None,
    })

    initial = {"request_id": rid, "text_original": inp.text, "rounds": 0,
               "vulnerability": inp.vulnerability, "flags": []}
    # A known second toilet settles the only-toilet question without asking.
    # It travels as a separate note used for reading only; the tenant's own
    # words are stored and quoted exactly as written.
    if inp.alternative_toilet is not None and "toilet" in inp.text.lower():
        initial["household_note"] = ("There is another toilet in the house."
                                     if inp.alternative_toilet else "This is the only toilet.")
    out = G.app().invoke(initial, G.config_for(rid))
    return _after_run(rid, out)


def clarify(request_id: str, answer: str) -> dict:
    req = db.get_request(request_id)
    if req is None:
        raise NotFound(request_id)
    if req["status"] != "awaiting_tenant":
        raise Invalid(f"{request_id} is not waiting for an answer (status {req['status']})")
    db.update_request(request_id, {"clarification_a": answer})
    out = G.app().invoke(Command(resume=answer), G.config_for(request_id))
    return _after_run(request_id, out)


def _after_run(rid: str, out: dict) -> dict:
    if "__interrupt__" in out:
        q = out["__interrupt__"][0].value["question"]
        db.update_request(rid, {"status": "awaiting_tenant", "clarification_q": q,
                                "text_normalised": out.get("text_normalised")})
        _persist_extractions(rid, out)
        return {"request_id": rid, "status": "awaiting_tenant", "question": q}
    return finalise(rid, out)


def _persist_extractions(rid: str, st: dict) -> None:
    from .config import settings
    last = None
    for m in st.get("extraction_meta", []):
        db.append(EXTRACTIONS, {"request_id": rid, "source_text": m["source"],
                                "payload": m["payload"], "extractor": m["extractor"],
                                "model": m["model"], "prompt_version": settings().prompt_version,
                                "cache_hit": m["cache_hit"], "fallback": m["fallback"]})
        last = m["payload"]
    if last is not None:
        db.update_request(rid, {"extraction": last})


def finalise(rid: str, st: dict, override: dict | None = None) -> dict:
    _persist_extractions(rid, st)
    req = db.get_request(rid)
    lodged_at, community = req["lodged_at"], req["dwelling"]["community"]
    deferrals, text_original = req.get("prior_deferrals", 0), req["text_original"]

    ex = Extraction.model_validate(st["extraction"])
    tier = override["to_tier"] if override else st["tier"]
    need = st["need"]
    flags = list(st.get("flags", []))
    if deferrals >= policy()["alerts"]["repeat_deferral_at"]:
        flags.append({"code": "repeat_deferral", "detail": f"deferred {deferrals} times",
                      "action": "equity alert", "audience": "coordinator"})

    trade = ex.trade or "Handyperson"
    pos = position(rid, tier, need, lodged_at, community, trade=trade)
    reach = reachability(community, trip_scheduled=False) if tier != "NotInQueue" else None
    trip_wait = None
    if pos and tier == "Routine":
        from .scheduler import next_trip_days
        c = communities()[community]
        target = policy()["service_targets_days"][tier]["remote" if c.remote else "urban"]
        trip_wait = next_trip_days(community, trade, tier, target, exclude=rid)
    wait = (estimate(community, tier, pos.hours_ahead, pos.hours_ahead_darwin, trade=trade,
                     trip_wait_days=trip_wait, jobs_ahead=pos.jobs_ahead_trade) if pos else None)

    from .policy import Component
    comps = [Component(**c) for c in st.get("components", [])]
    clar = tuple(st["clarification"]) if st.get("clarification") else None

    facts = fact_sheet(
        request_id=rid, text_original=text_original,
        evidence=st.get("evidence_original") or ex.evidence_phrase,
        tier=tier, tier_reason=(f"a staff member set it: {override['reason']}"
                                if override else st["tier_reason"]),
        need=need, components=comps,
        rank=pos.rank if pos else None, tier_size=pos.tier_size if pos else None,
        darwin_rank=pos.darwin_rank if pos else None, wait=wait, reach=reach,
        flags=flags, clarification=clar, override=override,
        actionability=ex.actionability.value, weights_version=st["weights_version"],
        hazard_domain=ex.hazard_domain.value, tenant_isolated=ex.tenant_isolated,
        emergency=ex.emergency_000, person_hurt=ex.person_hurt)

    tenant = render_tenant(facts)
    problems = verify(tenant, facts)
    if problems:            # the template itself must pass its own checks
        log.error("template_failed_verification", problems=problems, request=rid)
        flags.append({"code": "explanation_check_failed", "detail": problems,
                      "action": "review wording", "audience": "coordinator"})
    coordinator = render_coordinator(facts)

    # An unclear report never just disappears: after one question it goes to a
    # person to phone the tenant.
    status = ("needs_phone_call" if ex.actionability.value == "unclear"
              or (ex.emergency_000 and tier == "NotInQueue")
              else "awaiting_confirmation" if ex.actionability.value == "withdrawal"
              else "not_in_queue" if tier == "NotInQueue"
              else "approved" if override else "ranked")

    assessment = {
        "tier": tier, "need_score": need, "need_components": facts["components"],
        "wait_days_low": wait.low if wait else None,
        "wait_days_high": wait.high if wait else None,
        "wait_days_darwin": wait.darwin_central if wait else None,
        "reachability": reach, "flags": flags,
        "facts": json.loads(json.dumps(facts, default=str)),
        "explanation_coordinator": coordinator, "explanation_tenant": tenant,
        "weights_version": st["weights_version"], "created_at": now(),
    }
    db.append(ASSESSMENTS, {"request_id": rid, **assessment})
    db.update_request(rid, {"status": status, "text_normalised": st.get("text_normalised"),
                            "assessment": assessment})

    return {"request_id": rid, "status": status, "tier": tier,
            "rank": pos.rank if pos else None,
            "tier_size": pos.tier_size if pos else None,
            "wait": facts["wait"], "explanation_tenant": tenant,
            "explanation_coordinator": coordinator, "flags": flags}


# ---------------------------------------------------------------------------

def decide(request_id: str, d: DecisionIn) -> dict:
    req = db.get_request(request_id)
    if req is None:
        raise NotFound(request_id)
    if not req.get("assessment"):
        raise Invalid("no assessment to decide on")
    from_tier = req["assessment"]["tier"]

    if d.action == "override":
        if not d.reason or len(d.reason.strip()) < 5:
            raise Invalid("an override needs a reason the tenant will be shown")
        if d.to_tier not in ("Immediate", "Urgent", "Routine"):
            raise Invalid("to_tier must be Immediate, Urgent or Routine")
        if from_tier == "Immediate" and d.to_tier != "Immediate" and "second reviewer" \
                not in d.reason.lower():
            raise Invalid("downgrading an Immediate job needs a second reviewer; "
                          "name them in the reason")

    db.append(DECISIONS, {"request_id": request_id, "actor": d.actor, "action": d.action,
                          "from_tier": from_tier, "to_tier": d.to_tier or from_tier,
                          "reason": d.reason})
    if d.action == "approve":
        db.update_request(request_id, {"status": "approved"})
    elif d.action == "request_info":
        db.update_request(request_id, {"status": "awaiting_tenant"})

    if d.action == "override":
        st = G.app().get_state(G.config_for(request_id)).values
        return finalise(request_id, st, override={"to_tier": d.to_tier,
                                                  "reason": d.reason.strip(),
                                                  "actor": d.actor})
    return request_view(request_id)


# ---------------------------------------------------------------------------

def _days_since(iso: str) -> float:
    t = datetime.fromisoformat(iso)
    return round((datetime.now(timezone.utc) - t).total_seconds() / 86400, 1)


def live_wait(req: dict, jobs=None) -> dict | None:
    """The wait from NOW for an open request, recomputed from today's queue.

    The estimate stored with the assessment is what the tenant was told on the
    day; this one counts down as the job waits, and moves when jobs ahead are
    finished or a more urgent one arrives. A job on a confirmed trip uses the
    trip's arrival instead."""
    a = req.get("assessment")
    if not a or req.get("status") not in ("ranked", "approved") or a["tier"] == "NotInQueue":
        return None
    community = req["dwelling"]["community"]
    days_open = _days_since(req["lodged_at"])
    if req.get("trip_id") and req.get("eta_at"):
        left = max((datetime.fromisoformat(req["eta_at"]) - datetime.now(timezone.utc))
                   .total_seconds() / 86400, 0.0)
        return {"low": round(left, 1), "high": round(left, 1), "central": round(left, 1),
                "range_text": ("within a day" if left < 1 else
                               f"in about {plural_days(max(int(round(left)), 1))}"),
                "on_trip": True, "days_open": days_open, "breakdown": None}
    trade, _ = job_trade(req)
    pos = position(req["_id"], a["tier"], a["need_score"], req["lodged_at"], community,
                   trade=trade, jobs=jobs)
    if pos is None:
        return None
    told = ((a.get("facts") or {}).get("wait") or {}).get("breakdown") or {}
    trip_wait = told.get("trip_wait_days")
    if trip_wait is not None:
        trip_wait = max(trip_wait - days_open, 0.0)
    w = estimate(community, a["tier"], pos.hours_ahead, pos.hours_ahead_darwin, trade=trade,
                 trip_wait_days=trip_wait, elapsed_days=days_open,
                 jobs_ahead=pos.jobs_ahead_trade)
    return {"low": round(w.low, 1), "high": round(w.high, 1), "central": round(w.central, 1),
            "range_text": fmt_range(w), "on_trip": False, "days_open": days_open,
            "breakdown": w.breakdown}


def request_view(request_id: str) -> dict:
    req = db.get_request(request_id)
    if req is None:
        raise NotFound(request_id)
    dw, a = req["dwelling"], req.get("assessment")
    return {
        "wait_now": live_wait(req),
        "request_id": req["_id"], "status": req["status"], "lodged_at": req["lodged_at"],
        "text_original": req["text_original"], "text_normalised": req.get("text_normalised"),
        "community": dw["community"], "address": dw.get("address"), "phone": dw.get("phone"),
        "question": req.get("clarification_q"),
        "answer": req.get("clarification_a"), "prior_deferrals": req.get("prior_deferrals", 0),
        "advanced_by": req.get("advanced_by"),
        "trip": _trip_info(req, dw["community"]),
        "assessment": None if not a else {
            "tier": a["tier"], "need": a["need_score"], "facts": a.get("facts") or {},
            "flags": a.get("flags") or [], "reachability": a.get("reachability"),
            "explanation_tenant": a["explanation_tenant"],
            "explanation_coordinator": a["explanation_coordinator"],
            "weights_version": a["weights_version"], "created_at": a["created_at"]},
        "decisions": [{"actor": d["actor"], "action": d["action"], "from": d["from_tier"],
                       "to": d["to_tier"], "reason": d.get("reason"), "at": d["created_at"]}
                      for d in db.history(DECISIONS, request_id)],
        "extractions": [{"source": e["source_text"], "extractor": e["extractor"],
                         "cache_hit": e["cache_hit"], "fallback": e["fallback"],
                         "payload": e["payload"]} for e in db.history(EXTRACTIONS, request_id)],
    }


def _trip_info(req: dict, community: str) -> dict | None:
    """The confirmed trip this job is on, with its arrival counted down from now."""
    if not req.get("trip_id") or not req.get("eta_at"):
        return None
    from .explain import render_trip_update
    left = max((datetime.fromisoformat(req["eta_at"]) - datetime.now(timezone.utc))
               .total_seconds() / 86400, 0.0)
    facts = {"request_id": req["_id"], "community": community, "stop": req["trip_stop"],
             "stops": req["trip_stops"], "eta_days": round(left, 1)}
    return {"trip_id": req["trip_id"], "stop": req["trip_stop"], "stops": req["trip_stops"],
            "eta_at": req["eta_at"], "eta_days": round(left, 1),
            "tenant_update": render_trip_update(facts)}


def queue_view(tier: str | None = None, community: str | None = None) -> list[dict]:
    from .policy import sort_key
    targets = policy()["service_targets_days"]
    out = []
    jobs = open_jobs()                      # loaded once: every row's live wait uses it
    for req in db.open_requests():
        a, dw = req["assessment"], req["dwelling"]
        if tier and a["tier"] != tier:
            continue
        if community and dw["community"] != community:
            continue
        c = communities()[dw["community"]]
        days_open = _days_since(req["lodged_at"])
        target = targets[a["tier"]]["remote" if c.remote else "urban"]
        urban_target = targets[a["tier"]]["urban"]
        facts = a.get("facts") or {}
        now_w = live_wait(req, jobs)
        out.append({
            "request_id": req["_id"], "tier": a["tier"], "need": a["need_score"],
            "community": dw["community"], "area": area_of(dw["community"]),
            "address": dw.get("address"), "phone": dw.get("phone"), "remote": c.remote,
            "text": req["text_original"], "status": req["status"],
            "lodged_at": req["lodged_at"],
            "evidence": facts.get("evidence", ""),
            "trade": Extraction.model_validate(req["extraction"]).trade if req.get("extraction") else "",
            "reachability": a.get("reachability") or {},
            # live: from today's queue, counting down (what the tenant was told
            # on the day stays in told_low/told_high)
            "wait_low": now_w["low"] if now_w else a.get("wait_days_low"),
            "wait_high": now_w["high"] if now_w else a.get("wait_days_high"),
            "wait_text": now_w["range_text"] if now_w else None,
            "wait_on_trip": bool(now_w and now_w["on_trip"]),
            "told_low": a.get("wait_days_low"), "told_high": a.get("wait_days_high"),
            "wait_darwin": a.get("wait_days_darwin"), "days_open": days_open,
            "target_days": target, "pct_of_target": round(100 * days_open / target) if target else 0,
            "pct_of_urban_target": round(100 * days_open / urban_target) if urban_target else 0,
            "past_target": days_open > target,
            "target_label": (f"{round(target * 24)} h" if target < 1
                             else f"{target:g} business days"),
            "deferrals": req.get("prior_deferrals", 0), "advanced_by": req.get("advanced_by"),
            "flags": a.get("flags") or [],
            "_key": sort_key(a["tier"], a["need_score"], req["lodged_at"]),
        })
    out.sort(key=lambda r: r["_key"])
    for i, r in enumerate(out, 1):
        r["position"] = i
        r.pop("_key")
    return out


def contact_list() -> list[dict]:
    """Reports a person must follow up by phone: still unclear after asking,
    or a withdrawal that may mean the tenant gave up. Shown above the queue."""
    rows = db.col(REQUESTS).find(
        {"status": {"$in": ["needs_phone_call", "awaiting_confirmation"]}}).sort("lodged_at", 1)
    out = [{"request_id": r["_id"], "community": r["dwelling"]["community"],
            "address": r["dwelling"].get("address"), "phone": r["dwelling"].get("phone"),
            "status": r["status"], "text": r["text_original"],
            "answer": r.get("clarification_a"), "lodged_at": r["lodged_at"],
            "danger": any(fl.get("code") == "emergency_000"
                          for fl in ((r.get("assessment") or {}).get("flags") or []))}
           for r in rows]
    # someone in danger is phoned first
    return sorted(out, key=lambda c: not c["danger"])


def all_requests_view() -> list[dict]:
    """Every request, whatever its status: for the spreadsheet export."""
    out = []
    for r in db.col(REQUESTS).find().sort("lodged_at", 1):
        a, dw = r.get("assessment") or {}, r["dwelling"]
        out.append({
            "request_id": r["_id"], "status": r["status"], "lodged_at": r["lodged_at"],
            "tier": a.get("tier", ""), "need": a.get("need_score"),
            "community": dw["community"], "area": area_of(dw["community"]),
            "address": dw.get("address"), "phone": dw.get("phone"),
            "remote": communities()[dw["community"]].remote, "text": r["text_original"],
            "evidence": (a.get("facts") or {}).get("evidence", ""),
            "trade": Extraction.model_validate(r["extraction"]).trade if r.get("extraction") else "",
            "wait_low": a.get("wait_days_low"), "wait_high": a.get("wait_days_high"),
            "days_open": _days_since(r["lodged_at"]), "deferrals": r.get("prior_deferrals", 0),
            "flags": a.get("flags") or [], "trip_id": r.get("trip_id"), "eta_at": r.get("eta_at"),
        })
    return out
