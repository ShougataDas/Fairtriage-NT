"""HTTP layer. JSON under /api, HTML for tenant and coordinator.

The tenant docket shows the VERIFIED explanation text verbatim. What the
tenant reads is exactly what passed verify(), never a second rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

from fastapi import FastAPI, Form, HTTPException, Request as HttpRequest
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import metrics, scheduler, service
from .config import policy, reader_status
from .reference import communities, road_km, trade_capacity
from .schemas import ClarifyIn, DecisionIn, LodgeIn, ResendIn, ReviewIn, ThresholdIn, TripChangeIn, WhyIn

WEB = Path(__file__).parent / "web"
app = FastAPI(title="FairTriage NT", version="3.0")
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
T = Jinja2Templates(directory=WEB / "templates")
T.env.globals["reader_status"] = reader_status


def _error(request, message: str):
    r = T.TemplateResponse(request, "_error.html", {"message": message})
    r.headers["HX-Retarget"] = "#outcome"
    r.headers["HX-Reswap"] = "innerHTML"
    return r


def _paragraphs(text: str) -> list[list[str]]:
    return [[ln for ln in block.split("\n") if ln.strip()]
            for block in text.split("\n\n") if block.strip()]


def _community_groups() -> list[tuple[str, list[str]]]:
    from .reference import AREA_ORDER, area_of
    groups: dict[str, list[str]] = {g: [] for g in AREA_ORDER}
    for name in communities():
        groups.setdefault(area_of(name), []).append(name)
    return [(g, sorted(v)) for g, v in groups.items() if v]


def _docket_ctx(rid: str, result: dict) -> dict:
    return {"request_id": rid, "tier": result["tier"],
            "paragraphs": _paragraphs(result["explanation_tenant"])}


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.post("/api/requests")
def api_lodge(inp: LodgeIn):
    """Lodge a report. A mobile number is required: the tenant is texted their
    reference and the message they are shown, so a lost reference never means
    a lost repair."""
    from . import sms
    mobile = sms.normalise_mobile(inp.phone)
    if not mobile:
        raise HTTPException(422, sms.mobile_problem(inp.phone))
    try:
        out = service.lodge(inp.model_copy(update={"phone": mobile}))
    except service.Invalid as e:
        raise HTTPException(422, str(e))
    out["sms"] = sms.after_result(out)
    return out


@app.get("/api/requests/{rid}")
def api_get(rid: str):
    try:
        return service.request_view(rid)
    except service.NotFound:
        raise HTTPException(404, "no such request")


@app.post("/api/requests/{rid}/clarify")
def api_clarify(rid: str, inp: ClarifyIn):
    from . import sms
    try:
        out = service.clarify(rid, inp.answer)
        out["sms"] = sms.after_result(out)
        return out
    except service.NotFound:
        raise HTTPException(404, "no such request")
    except service.Invalid as e:
        raise HTTPException(409, str(e))


@app.post("/api/sms/resend")
def api_sms_resend(inp: ResendIn):
    """A tenant lost their reference: text the references on this number to it."""
    from . import sms
    try:
        return sms.resend(inp.phone)
    except sms.Invalid as e:
        raise HTTPException(422, str(e))


@app.post("/api/requests/{rid}/why")
def api_why(rid: str, inp: WhyIn):
    """The tenant asks why their repair is where it is; a real answer from the record."""
    from . import askwhy
    try:
        return askwhy.answer(rid, inp.question)
    except askwhy.NotFound:
        raise HTTPException(404, "no such request")


@app.post("/api/requests/{rid}/review")
def api_review(rid: str, inp: ReviewIn):
    """The tenant asks a person to review it: goes on the coordinator's phone list."""
    from . import askwhy
    try:
        return askwhy.request_review(rid, inp.message)
    except askwhy.NotFound:
        raise HTTPException(404, "no such request")


@app.post("/api/requests/{rid}/decision")
def api_decide(rid: str, d: DecisionIn):
    from . import sms
    try:
        out = service.decide(rid, d)
        # a changed tier or a staff question reaches the tenant by text too
        if d.action in ("override", "request_info"):
            out["sms"] = sms.after_result(out, update=d.action == "override")
        return out
    except service.NotFound:
        raise HTTPException(404, "no such request")
    except service.Invalid as e:
        raise HTTPException(422, str(e))


@app.get("/api/queue")
def api_queue(tier: Optional[str] = None, community: Optional[str] = None,
              order: str = "need"):
    """The ranked queue. order=cost shows, for contrast only, how an
    efficiency-first system would reorder it; `shift` is the change in place."""
    rows = service.queue_view(tier, community)
    if order == "cost":
        need_pos = {r["request_id"]: r["position"] for r in rows}
        rows = _cost_order(rows)
        for i, r in enumerate(rows, 1):
            r["shift"] = need_pos[r["request_id"]] - i
            r["display_pos"] = i
    else:
        for r in rows:
            r["shift"], r["display_pos"] = 0, r["position"]
    return rows


@app.get("/api/export")
def api_export(format: str = "csv", scope: str = "queue", tier: Optional[str] = None,
               remote: Optional[bool] = None, q: Optional[str] = None,
               area: Optional[str] = None, past: Optional[bool] = None):
    """Download requests as CSV or Excel. scope=queue (ranked, as on screen) or all."""
    from . import export
    if format not in ("csv", "xlsx") or scope not in ("queue", "all"):
        raise HTTPException(422, "format must be csv or xlsx; scope must be queue or all")
    data = export.rows(scope, tier or None, remote, q, area or None, past)
    body = export.to_csv(data) if format == "csv" else export.to_xlsx(
        data, "Queue" if scope == "queue" else "All requests")
    media = ("text/csv; charset=utf-8" if format == "csv" else
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return Response(body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{export.filename(format)}"'})


@app.get("/api/communities")
def api_communities():
    cs = communities()
    return [{"group": g, "communities": [{"name": n, "remote": cs[n].remote} for n in names]}
            for g, names in _community_groups()]


@app.get("/api/alerts")
def api_alerts():
    """Immediate work that cannot be made safe within the target, by region and trade."""
    return service.backlog_alerts()


@app.get("/api/contacts")
def api_contacts():
    """Reports a person must phone about: still unclear, or a withdrawal."""
    return service.contact_list()


@app.get("/api/trips")
def api_trips():
    """Confirmed trips, newest first."""
    return scheduler.trips_view()


@app.get("/api/trips/preview")
def api_trip_preview():
    """The recommended trips right now. Recomputed on every call, so it follows
    the queue, priorities and crew locations as they change. Stores nothing."""
    from .tripsettings import threshold
    return {"teams": scheduler.team_locations(),
            "rules": {**policy()["trips"], "community_threshold_multiple": threshold()},
            "trips": [scheduler.to_dict(t) for t in scheduler.plan(commit=False)]}


@app.post("/api/trips/plan")
def api_plan(anchor: Optional[str] = None):
    """Confirm the recommended trips (or just the one led by `anchor`): jobs
    become scheduled with an arrival time."""
    plans = scheduler.plan(commit=True, only=anchor)
    return [scheduler.to_dict(t) for t in plans if anchor is None or t.anchor.request_id == anchor]


@app.post("/api/trips/{trip_id}/cancel")
def api_trip_cancel(trip_id: str, body: TripChangeIn):
    return _trip_change(lambda: scheduler.cancel_trip(trip_id, body.reason, body.actor))


@app.post("/api/trips/{trip_id}/remove")
def api_trip_remove(trip_id: str, body: TripChangeIn):
    if not body.request_id:
        raise HTTPException(422, "say which job to remove (request_id)")
    return _trip_change(lambda: scheduler.remove_from_trip(trip_id, body.request_id, body.reason, body.actor))


@app.post("/api/trips/{trip_id}/complete")
def api_trip_complete(trip_id: str, body: TripChangeIn | None = None):
    actor = body.actor if body else "coordinator-demo"
    return _trip_change(lambda: scheduler.complete_trip(trip_id, actor))


def _trip_change(fn):
    try:
        return fn()
    except KeyError:
        raise HTTPException(404, "no such trip")
    except scheduler.TripError as e:
        raise HTTPException(409, str(e))


@app.post("/api/teams/{trade_region}")
def api_team(trade_region: str, location: str):
    try:
        scheduler.set_team_location(trade_region, location)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return scheduler.team_locations()


@app.get("/api/policy/trip-threshold")
def api_threshold_whatif():
    """What each trip-threshold setting means for remote waits, trips and cost."""
    from . import whatif
    return whatif.scenarios()


@app.post("/api/policy/trip-threshold")
def api_set_threshold(inp: ThresholdIn):
    """A coordinator sets the trip threshold, with a reason. Recorded."""
    from . import tripsettings
    try:
        tripsettings.set_threshold(inp.multiple, inp.reason, inp.actor)
    except tripsettings.Invalid as e:
        raise HTTPException(422, str(e))
    from . import whatif
    return whatif.scenarios()


@app.get("/api/metrics/equity")
def api_equity():
    return metrics.equity()


@app.get("/api/health")
def health():
    from . import db
    return {"ok": True, "database": "connected" if db.ping() else "unreachable",
            "policy": policy()["version"], "communities": len(communities()),
            "reader": reader_status(), "rules": _rules_fingerprint(),
            "service_targets_verified": policy().get("service_targets_verified", False)}


def _rules_fingerprint() -> str:
    from .extract import _code_fingerprint
    return _code_fingerprint()


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse("/tenant", status_code=302)


@app.get("/tenant", response_class=HTMLResponse)
def tenant_form(request: HttpRequest):
    return T.TemplateResponse(request, "tenant_lodge.html",
                              {"section": "tenant", "community_groups": _community_groups()})


@app.post("/tenant/lodge", response_class=HTMLResponse)
def tenant_lodge(request: HttpRequest, text: Annotated[str, Form()],
                 community: Annotated[str, Form()],
                 phone: Annotated[str, Form()] = "",
                 vulnerability: Annotated[list[str], Form()] = []):
    from . import sms
    text = text.strip()
    if not text:
        return _error(request, "Write a few words about what is wrong.")
    mobile = sms.normalise_mobile(phone)
    if not mobile:
        return _error(request, sms.mobile_problem(phone))
    try:
        out = service.lodge(LodgeIn(text=text, community=community, phone=mobile,
                                    vulnerability=vulnerability))
    except service.Invalid as e:
        return _error(request, str(e))
    sms.after_result(out)
    if out["status"] == "awaiting_tenant":
        return T.TemplateResponse(request, "_question.html",
                                  {"question": out["question"],
                                   "request_id": out["request_id"]})
    return T.TemplateResponse(request, "_docket.html", _docket_ctx(out["request_id"], out))


@app.post("/tenant/{rid}/clarify", response_class=HTMLResponse)
def tenant_clarify(request: HttpRequest, rid: str, answer: Annotated[str, Form()]):
    answer = answer.strip()
    if not answer:
        return _error(request, "Type an answer first.")
    try:
        out = service.clarify(rid, answer)
    except (service.NotFound, service.Invalid) as e:
        return _error(request, str(e))
    from . import sms
    sms.after_result(out)
    return T.TemplateResponse(request, "_docket.html", _docket_ctx(rid, out))


@app.get("/tenant/{rid}", response_class=HTMLResponse)
def tenant_record(request: HttpRequest, rid: str):
    try:
        v = service.request_view(rid)
    except service.NotFound:
        raise HTTPException(404, "No repair with that reference.")
    if v["status"] == "awaiting_tenant" or not v["assessment"]:
        ctx = {"section": "tenant", "question": v["question"], "request_id": rid}
    else:
        a = v["assessment"]
        ctx = {"section": "tenant", "question": None, "request_id": rid,
               "tier": a["tier"], "paragraphs": _paragraphs(a["explanation_tenant"]),
               "trip_update": (v["trip"] or {}).get("tenant_update")}
    return T.TemplateResponse(request, "tenant_result.html", ctx)


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

def _cost_order(rows: list[dict]) -> list[dict]:
    """What an efficiency-first system would do: nearest first, then tier.

    Shown for contrast only. FairTriage never ranks this way.
    """
    from .policy import TIER_ORDER

    def km(r):
        c = communities()[r["community"]]
        depot = trade_capacity()[c.trade_region]["depot"]
        return road_km(depot, r["community"])
    from .reference import travel_days
    return sorted(rows, key=lambda r: (travel_days(r["community"]), km(r),
                                       TIER_ORDER[r["tier"]]))


@app.get("/coordinator", response_class=HTMLResponse)
def coord_queue(request: HttpRequest, order: str = "need", tier: str = "",
                community: str = ""):
    rows = service.queue_view(tier or None, community or None)
    need_pos = {r["request_id"]: i for i, r in enumerate(rows, 1)}
    moved_down = 0
    if order == "cost":
        rows = _cost_order(rows)
        for i, r in enumerate(rows, 1):
            r["shift"] = need_pos[r["request_id"]] - i
            r["display_pos"] = i
            moved_down += int(r["shift"] < 0 and r["remote"])
    else:
        for r in rows:
            r["shift"] = 0
            r["display_pos"] = r["position"]
    return T.TemplateResponse(request, "coord_queue.html", {
        "section": "queue", "rows": rows, "order": order, "tier": tier,
        "community": community, "communities": list(communities()),
        "moved_down": moved_down, "policy_version": policy()["version"],
        "contacts": service.contact_list(),
        "rules_version": _rules_fingerprint()})


@app.get("/coordinator/trips", response_class=HTMLResponse)
def coord_trips(request: HttpRequest, error: str = ""):
    from .tripsettings import threshold
    t = policy()["trips"]
    return T.TemplateResponse(request, "coord_trips.html", {
        "section": "trips", "error": error,
        "preview": [scheduler.to_dict(p) for p in scheduler.plan(commit=False)],
        "trips": scheduler.trips_view(), "teams": scheduler.team_locations(),
        "community_groups": _community_groups(), "t": t, "r": t["routing"],
        "multiple": threshold()})


@app.post("/coordinator/team")
def coord_team(trade_region: Annotated[str, Form()], location: Annotated[str, Form()]):
    try:
        scheduler.set_team_location(trade_region, location)
    except ValueError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/coordinator/trips?error={quote(str(e))}", status_code=303)
    return RedirectResponse("/coordinator/trips", status_code=303)


@app.post("/coordinator/trips/plan")
def coord_plan():
    scheduler.plan(commit=True)
    return RedirectResponse("/coordinator/trips", status_code=303)


@app.get("/coordinator/equity", response_class=HTMLResponse)
def coord_equity(request: HttpRequest):
    return T.TemplateResponse(request, "coord_equity.html",
                              {"section": "equity", "m": metrics.equity()})


@app.get("/coordinator/{rid}", response_class=HTMLResponse)
def coord_detail(request: HttpRequest, rid: str, error: str = ""):
    try:
        v = service.request_view(rid)
    except service.NotFound:
        raise HTTPException(404, "No request with that reference.")
    return T.TemplateResponse(request, "coord_detail.html",
                              {"section": "queue", "r": v, "error": error})


@app.post("/coordinator/{rid}/decide")
def coord_decide(rid: str, action: Annotated[str, Form()],
                 to_tier: Annotated[str, Form()] = "",
                 reason: Annotated[str, Form()] = ""):
    try:
        service.decide(rid, DecisionIn(action=action, to_tier=to_tier or None,
                                       reason=reason or None))
    except service.Invalid as e:
        from urllib.parse import quote
        return RedirectResponse(f"/coordinator/{rid}?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/coordinator/{rid}", status_code=303)
