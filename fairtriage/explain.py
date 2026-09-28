"""Explanations, built from the arithmetic.

Content determination is deterministic: the fact sheet holds every claim
that may be made, each traceable to a number or a stored field. Surface
realisation may be neural, but a model is only ever given the facts and
asked to say them — never told the outcome and asked to justify it. A
justification written after seeing the answer is a plausible story about a
decision, not the decision.

verify() rejects any rendering that invents a number, drops a required
claim, or adds an apology or a delivery promise. The template is the
default. A stilted true sentence beats a fluent false one when someone is
being told why their house has not been fixed.
"""

from __future__ import annotations

import re

from .wait import WaitEstimate, fmt_range, plural_days

# Standard make-safe advice, given only for Immediate jobs the tenant has not
# already made safe. Advice, not a promise: no times, no numbers.
MAKE_SAFE = {
    "electrical": "If it is safe to do so, switch the power off at the meter box and keep everyone away from it.",
    "gas": "If it is safe to do so, turn the gas off at the bottle. Do not use light switches or flames, and open doors and windows.",
    "water": "If you can, turn the water off at the mains tap.",
    "sanitation": "Keep children and pets away from the affected area and wash hands after any contact.",
    "structural": "Keep everyone out of the damaged part of the house.",
    "security": "If you can, secure the opening temporarily and keep valuables with you.",
}

TENANT_FACTOR = {
    "habitability": "how much the problem stops you using your home",
    "vulnerability": "who lives in the house",
}


def fact_sheet(*, request_id: str, text_original: str, evidence: str, tier: str,
               tier_reason: str, need: float, components: list, rank: int | None,
               tier_size: int | None, darwin_rank: int | None,
               wait: WaitEstimate | None, reach: dict | None, flags: list,
               clarification: tuple[str, str] | None, override: dict | None,
               actionability: str, weights_version: str,
               hazard_domain: str = "", tenant_isolated: bool = False,
               emergency: bool = False) -> dict:
    facts = {
        "request_id": request_id, "tier": tier, "tier_reason": tier_reason,
        "need": need, "rank": rank, "tier_size": tier_size,
        "darwin_rank": darwin_rank, "evidence": evidence,
        "text_original": text_original, "actionability": actionability,
        "components": [{"name": c.name, "raw": c.raw, "weight": c.weight,
                        "contribution": c.contribution, "detail": c.detail}
                       for c in components],
        "wait": None if wait is None else {
            "low": wait.low, "high": wait.high, "central": wait.central,
            "high_hours": wait.high_hours,
            "darwin": wait.darwin_central, "range_text": fmt_range(wait),
            "gap_days": wait.gap_days, "ratio": wait.ratio,
            "breakdown": wait.breakdown},
        "reachability": reach, "flags": flags,
        "clarification": clarification, "override": override,
        "distance_used_in_need": False, "weights_version": weights_version,
        "hazard_domain": hazard_domain, "tenant_isolated": tenant_isolated,
        "emergency": emergency,
        "not_counted": ["how far a tradesperson has to travel",
                        "how the message was written"],
    }
    return facts


# ---------------------------------------------------------------------------

def render_tenant(f: dict) -> str:
    L: list[str] = []
    tier = f["tier"]

    if tier == "NotInQueue":
        if f["actionability"] == "withdrawal":
            return (
                "Thanks for letting us know.\n\n"
                f"You told us: \u201c{f['evidence']}\u201d\n\n"
                "We have not closed your repair. A staff member will contact you to "
                "check whether it has been fixed or whether you would still like "
                "someone to come. If it is still a problem, you do not have to wait "
                "for that call — reply here.\n\n"
                f"Reference {f['request_id']}.")
        if f["actionability"] == "unclear":
            L = ["We could not tell from your message what needs fixing, so a staff "
                 "member will phone you to find out.", "",
                 f"You told us: \u201c{f['evidence']}\u201d"]
            if f["clarification"]:
                q, a = f["clarification"]
                L.append(f"We asked: \u201c{q}\u201d You said: \u201c{a}\u201d")
            L += ["", "If there is a fire, or anyone is hurt, call 000 now.",
                  "If something is dangerous, such as sparks, a gas smell, water near "
                  "power or sewage inside, send a new report saying so and it will go "
                  "straight to the top.", "", f"Reference {f['request_id']}."]
            return "\n".join(L)
        return (
            "We did not find a repair to book from your message.\n\n"
            f"You told us: \u201c{f['evidence']}\u201d\n\n"
            "If something is wrong, tell us what and where, and we will look again.\n\n"
            f"Reference {f['request_id']}.")

    w = f["wait"]
    if f.get("emergency"):
        L.append("If there is a fire, or anyone is hurt, call 000 now and get "
                 "everyone out of the house. Do not wait for us.")
        L.append("")
        L.append("Once everyone is safe, a staff member will phone you to arrange "
                 "the repair.")
        L.append("")
    elif w:
        L.append(f"Expect a tradesperson {w['range_text']}.")
        if tier == "Immediate":
            L.append("Immediate repairs are attended first, to make the problem safe.")
        tw = (w.get("breakdown") or {}).get("trip_wait_days")
        if tw is not None:
            L.append("Routine repairs here are done when a maintenance trip comes to your "
                     "community." + (" One is due now." if tw < 1 else
                                     f" The next one is expected in about "
                                     f"{plural_days(max(int(round(tw)), 1))}."))
        if f["reachability"] and f["reachability"]["remote"] and w["gap_days"] >= 1:
            L.append(f"A repair like yours in Darwin would usually take about "
                     f"{plural_days(max(round(w['darwin']), 1))}. The difference is "
                     f"travel, not priority.")
        if f["reachability"] and f["reachability"]["road_status"] != "open":
            L.append(f"The road to your community is {f['reachability']['road_status']} "
                     f"at the moment, which is part of the wait.")
        L.append("")
    L.append(f"Your repair is in the {tier} group.")
    L.append("")
    L.append(f"You told us: \u201c{f['evidence']}\u201d")
    if f["clarification"]:
        q, a = f["clarification"]
        L.append(f"We asked: \u201c{q}\u201d You said: \u201c{a}\u201d")
    L.append(f"It is {tier} because {f['tier_reason']}.")
    L.append("")

    advice = MAKE_SAFE.get(f.get("hazard_domain", ""))
    # In an emergency the only instruction is to get out and call 000. Advice
    # like "turn the gas off at the bottle" is right for a gas SMELL and wrong
    # for gas that is on fire: it sends someone towards the danger.
    if f.get("emergency"):
        pass
    elif tier == "Immediate" and advice and not f.get("tenant_isolated"):
        L.append(advice)
        L.append("")
    elif tier == "Immediate" and f.get("tenant_isolated"):
        L.append("Thank you for making it safe. Keep it that way until a tradesperson arrives.")
        L.append("")

    if f["rank"] and f["tier_size"]:
        L.append(f"You are number {f['rank']} of {f['tier_size']} in the {tier} group.")
    L.append("Where you live was not used to decide your position."
             + (f" The same repair in Darwin would also be number {f['darwin_rank']}."
                if f["darwin_rank"] else ""))
    L.append("")

    if f["override"]:
        L.append(f"A staff member changed this by hand. Their reason: "
                 f"\u201c{f['override']['reason']}\u201d")
        L.append("")

    if tier != "Immediate":
        L.append("If we have missed something, or it gets worse — sparks, a burning "
                 "smell, water near power, sewage inside, the roof or walls damaged, "
                 "rain coming in — tell us and it will be looked at again straight away.")
        L.append("")
    L.append(f"A staff member will confirm this. You can ask a person to review it. "
             f"Reference {f['request_id']}.")
    return "\n".join(L)


def render_coordinator(f: dict) -> str:
    L = [f"{f['request_id']}  {f['tier']}  need {f['need']:.0f}/100"
         + (f"  #{f['rank']} of {f['tier_size']}" if f["rank"] else "")]
    L.append(f"  tenant's words: \u201c{f['evidence']}\u201d")
    L.append(f"  tier because: {f['tier_reason']}")
    for c in f["components"]:
        L.append(f"    {c['name']:<14} {c['raw']:.2f} x {c['weight']:.2f} = "
                 f"{c['contribution']:.3f}   ({c['detail']})")
    r = f["reachability"]
    if r:
        L.append(f"  reachability: {r['access']} · {r['road_km_est']:.0f} km est · "
                 f"road {r['road_status']}")
    L.append("  distance was NOT used to set the tier or the need score")
    if f["wait"]:
        L.append(f"  wait: {f['wait']['range_text']}  (Darwin equivalent "
                 f"{f['wait']['darwin']} days, gap {f['wait']['gap_days']} days)")
    for fl in f["flags"]:
        L.append(f"  ! {fl['code']}: {fl.get('detail', '')}")
    L.append(f"  policy {f['weights_version']}  ·  PENDING HUMAN APPROVAL")
    return "\n".join(L)


# ---------------------------------------------------------------------------

BANNED = ["sorry", "apologi", "we regret", "unfortunately", "as soon as possible",
          "guarantee", "will definitely", "promise"]
_NUM = re.compile(r"\d+(?:\.\d+)?")


def allowed_numbers(f: dict) -> set[str]:
    nums: set[str] = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            nums.add(str(int(v)) if float(v).is_integer() else str(v))
            nums.add(str(int(round(v))))
            nums.add(str(max(int(round(v)), 1)))
        elif isinstance(v, str):
            nums.update(_NUM.findall(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    # identifiers are not facts: digits inside a random reference suffix must
    # never become numbers an explanation is allowed to state
    walk({k: v for k, v in f.items() if k not in ("request_id", "weights_version")})
    return nums


def verify(text: str, f: dict) -> list[str]:
    problems = []
    ok = allowed_numbers(f)
    # the reference number is printed verbatim; don't scan its digits as claims
    # 000 is the emergency number, not a claim about the repair. Match it only
    # as a standalone number, so "3000" or a reference like NTF3-00001 is untouched.
    scan = re.sub(r"(?<![\w-])000(?![\w-])", " ", text.replace(f["request_id"], " "))
    for n in _NUM.findall(scan):
        if n not in ok:
            problems.append(f"invented number {n}")
    low = text.lower()
    for b in BANNED:
        if b in low:
            problems.append(f"unsupported promise or apology: {b}")
    if f["tier"] != "NotInQueue" and f["tier"].lower() not in low:
        problems.append("tier missing")
    if f["request_id"] not in text:
        problems.append("reference missing")
    return problems


# ---------------------------------------------------------------------------

def render_trip_update(f: dict) -> str | None:
    """One short update once a confirmed trip includes the tenant's repair.

    Built from stored facts only and checked like every other tenant text:
    if it would state a number that is not in the facts, it is not shown."""
    days = f["eta_days"]
    when = "within a day" if days < 1 else f"in about {plural_days(max(int(round(days)), 1))}"
    text = (f"Update: a maintenance trip to {f['community']} has been planned. "
            f"Your repair is stop {f['stop']} of {f['stops']} on that trip. "
            f"Expect a tradesperson {when}. This can change if the road closes or a more "
            f"dangerous job comes in. Reference {f['request_id']}.")
    ok = allowed_numbers(f)
    scan = text.replace(f["request_id"], " ")
    bad = [n for n in _NUM.findall(scan) if n not in ok]
    bad += [b for b in BANNED if b in text.lower()]
    return None if bad else text

