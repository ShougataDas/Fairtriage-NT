"""The request loop, as a LangGraph.

LangGraph is used for exactly one thing it does that plain function calls
don't: the clarification pause. "toilet is blocked" cannot be ranked without
knowing whether it is the only toilet, so the graph asks, INTERRUPTS, and is
resumed later — possibly minutes later, over a separate HTTP request — with
the answer folded in. The checkpointer makes that pause durable: the checkpoint lives in MongoDB with everything else.

    normalise -> extract x2 -> reconcile -> gate -+-> clarify (interrupt) -> normalise
                                                  +-> assess -> END

Everything after `gate` is deterministic.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from .config import policy, settings
from .extract import extract
from .normalise import normalise, reconcile
from .policy import assess
from .schemas import Actionability, Confidence, DecisiveFact, Extraction

QUESTIONS = {
    DecisiveFact.ONLY_TOILET: "Is this the only toilet in the house?",
    DecisiveFact.WHOLE_DWELLING: "Is the whole house affected, or just one room?",
    DecisiveFact.NEAR_ELECTRICS: "Is the water near any light, power point or wiring?",
    DecisiveFact.CAN_SECURE: "Can you still lock the house up?",
    DecisiveFact.COOKING_POSSIBLE: "Can you still cook with anything else?",
    DecisiveFact.INDOORS: "Is the sewage coming inside the house, or only outside?",
}
GENERIC_Q = ("Can you tell us what is wrong and where in the house? "
             "If anything is dangerous, say so.")

# The system knows WHICH fact it asked about, so it interprets the answer
# against that question and appends an explicit statement, rather than
# hoping the extractor works out that "yes only one" means "only toilet".
# (affirmative statement, negative statement, yes-words, no-words)
ANSWER_FRAMES = {
    DecisiveFact.ONLY_TOILET: (
        "This is the only toilet in the house.", "There is another toilet in the house.",
        r"\b(yes|yeah|yep|yup|only|just one|one only|only one|correct|true|that'?s it)\b",
        r"\b(no|nah|nope|another|second|two|other|2)\b"),
    DecisiveFact.WHOLE_DWELLING: (
        "The whole house is affected.", "Only one room is affected.",
        r"\b(whole|all|every|everything|entire|yes)\b",
        r"\b(one room|just|only the|no|nah|part)\b"),
    DecisiveFact.NEAR_ELECTRICS: (
        "The water is near a light, power point or wiring.",
        "The water is not near anything electrical.",
        r"\b(yes|yeah|yep|near|close|light|power|wire|switch|socket)\b",
        r"\b(no|nah|nope|not near|away|nowhere)\b"),
    DecisiveFact.CAN_SECURE: (
        "The house can be locked.", "The house cannot be locked.",
        r"\b(yes|yeah|yep|can lock|it locks|still lock)\b",
        r"\b(no|nah|nope|can'?t|cannot|won'?t)\b"),
    DecisiveFact.COOKING_POSSIBLE: (
        "We can still cook with something else.", "We cannot cook at all.",
        r"\b(yes|yeah|yep|microwave|bbq|barbecue|other)\b",
        r"\b(no|nah|nope|nothing|can'?t|cannot)\b"),
    DecisiveFact.INDOORS: (
        "Sewage is coming inside the house.", "The sewage is only outside.",
        r"\b(inside|in the house|indoors|in here|floor|yes)\b",
        r"\b(outside|only outside|yard|no)\b"),
}


def interpret_answer(fact: DecisiveFact, answer: str) -> str:
    """Turn a short answer into an explicit statement about the asked fact.

    Negatives are checked first where both could match, because "no, there
    is another one" contains no yes-word but "yes only one" must not be read
    as a no. Unrecognised answers pass through untouched.
    """
    import re
    frame = ANSWER_FRAMES.get(fact)
    a = answer.lower().strip()
    if not frame:
        return answer
    yes_stmt, no_stmt, yes_rx, no_rx = frame
    yes, no = bool(re.search(yes_rx, a)), bool(re.search(no_rx, a))
    if yes and not no:
        return yes_stmt
    if no and not yes:
        return no_stmt
    if yes and no:
        # "yes only one" -> yes ; "no, there's another" -> no. Lead word decides.
        lead = a.split()[0] if a.split() else ""
        if re.match(r"(no|nah|nope)", lead):
            return no_stmt
        return yes_stmt
    return answer


def _add(a: list, b: list) -> list:
    return (a or []) + (b or [])


class State(TypedDict, total=False):
    request_id: str
    text_original: str
    text_current: str
    text_normalised: str
    lexicon_changes: list
    extraction: dict
    extraction_meta: list
    diffs: dict
    rounds: int
    clarification: list          # [question, answer]
    evidence_original: str       # quote from the first reading, before any answer
    clarification_resolved: bool
    household_note: str          # facts from records, read but never quoted
    vulnerability: list
    flags: Annotated[list, _add]
    tier: str
    tier_reason: str
    need: float
    components: list
    weights_version: str


# ---------------------------------------------------------------------------

def n_normalise(s: State) -> dict:
    text = s.get("text_current") or (
        f"{s['text_original']} {s['household_note']}" if s.get("household_note")
        else s["text_original"])
    norm, changes = normalise(text)
    return {"text_current": text, "text_normalised": norm, "lexicon_changes": changes}


def n_extract(s: State) -> dict:
    texts = [s["text_current"]]
    if s["text_normalised"] != s["text_current"]:
        texts.append(s["text_normalised"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(extract, texts))

    a = results[0].extraction
    b = results[1].extraction if len(results) > 1 else a
    merged, diffs = reconcile(a, b)

    flags = []
    if diffs:
        flags.append({"code": "normalisation_changed_outcome", "detail": diffs,
                      "action": "human review", "audience": "coordinator"})
    if any(r.fallback for r in results):
        flags.append({"code": "extraction_fallback",
                      "detail": "model unavailable, read by the offline triage engine",
                      "action": "mandatory human review", "audience": "coordinator"})

    meta = [{"source": "original" if i == 0 else "normalised", "extractor": r.extractor,
             "model": r.model, "cache_hit": r.cache_hit, "fallback": r.fallback,
             "payload": r.extraction.model_dump(mode="json")}
            for i, r in enumerate(results)]
    out = {"extraction": merged.model_dump(mode="json"), "diffs": diffs,
           "extraction_meta": meta, "flags": flags}
    # The explanation must quote what the tenant REPORTED, not their answer to
    # our question. Keep the first reading's evidence.
    if not s.get("evidence_original"):
        # Evidence must be the tenant's own words. If the reading picked a
        # phrase from a household note or from our interpretation of an
        # answer, quote the original message instead.
        ev = merged.evidence_phrase
        out["evidence_original"] = ev if ev and ev in s["text_original"] else s["text_original"][:200]
    return out


def gate(s: State) -> Literal["clarify", "assess"]:
    ex = Extraction.model_validate(s["extraction"])
    # A dangerous job is ranked at once. Asking first would delay a hazard.
    if ex.endangers_person or ex.emergency_000:
        return "assess"
    if s.get("rounds", 0) >= policy()["extraction"]["max_clarification_rounds"]:
        return "assess"
    if ex.actionability == Actionability.UNCLEAR:
        return "clarify"
    if ex.in_queue and ex.confidence == Confidence.LOW:
        return "clarify"
    if ex.in_queue and ex.missing_decisive_fact != DecisiveFact.NONE:
        return "clarify"
    return "assess"


def n_clarify(s: State) -> dict:
    """Ask ONE question and pause. Not a form: someone with sewage in the house
    will not fill in a form."""
    ex = Extraction.model_validate(s["extraction"])
    q = QUESTIONS.get(ex.missing_decisive_fact, GENERIC_Q)
    answer = interrupt({"question": q, "request_id": s["request_id"]})
    statement = interpret_answer(ex.missing_decisive_fact, answer)
    combined = f"{s['text_current']} {statement}".strip()
    return {"text_current": combined, "rounds": s.get("rounds", 0) + 1,
            "clarification": [q, answer],
            "clarification_resolved": statement != answer}


def n_assess(s: State) -> dict:
    ex = Extraction.model_validate(s["extraction"])
    res = assess(ex, s.get("vulnerability") or [])

    flags = []
    if ex.emergency_000:
        flags.append({"code": "emergency_000",
                      "detail": "life may be at risk now; tenant told to call 000",
                      "action": "phone the tenant now and confirm 000 was called",
                      "audience": "coordinator"})
    if ex.actionability == Actionability.UNCLEAR and s.get("clarification"):
        flags.append({"code": "needs_phone_call",
                      "detail": "still unclear after asking once",
                      "action": "phone the tenant", "audience": "coordinator"})
    if ex.actionability == Actionability.WITHDRAWAL:
        flags.append({"code": "withdrawal_needs_confirmation",
                      "detail": "resolved, or given up? never auto-close",
                      "action": "contact tenant", "audience": "coordinator"})
    if ex.confidence == Confidence.LOW and ex.in_queue:
        flags.append({"code": "low_confidence", "detail": "reading uncertain",
                      "action": "human review", "audience": "coordinator"})
    if (ex.missing_decisive_fact != DecisiveFact.NONE and ex.in_queue
            and not s.get("clarification")):
        flags.append({"code": "decisive_fact_unknown",
                      "detail": ex.missing_decisive_fact.value,
                      "action": "confirm with tenant", "audience": "coordinator"})
    if s.get("clarification") and not s.get("clarification_resolved", True):
        flags.append({"code": "clarification_unresolved",
                      "detail": f"asked '{s['clarification'][0]}', answer "
                                f"'{s['clarification'][1]}' did not settle it",
                      "action": "phone the tenant", "audience": "coordinator"})
    if s.get("vulnerability"):
        flags.append({"code": "self_reported_vulnerability",
                      "detail": ", ".join(s["vulnerability"]),
                      "action": "verify against tenancy record", "audience": "coordinator"})

    return {"tier": res.tier, "tier_reason": res.tier_reason, "need": res.need,
            "components": [c.__dict__ for c in res.components],
            "weights_version": res.version, "flags": flags}


# ---------------------------------------------------------------------------

def build(checkpointer=None):
    g = StateGraph(State)
    g.add_node("normalise", n_normalise)
    g.add_node("extract", n_extract)
    g.add_node("clarify", n_clarify)
    g.add_node("assess", n_assess)
    g.set_entry_point("normalise")
    g.add_edge("normalise", "extract")
    g.add_conditional_edges("extract", gate, {"clarify": "clarify", "assess": "assess"})
    g.add_edge("clarify", "normalise")
    g.add_edge("assess", END)
    return g.compile(checkpointer=checkpointer)


_app = None


def _checkpointer():
    """Where a paused question waits for the tenant's answer. In MongoDB, so
    an answer given minutes later, to another server process, still resumes it.
    The in-memory stand-in used by tests cannot run the MongoDB saver, so the
    tests keep checkpoints in memory instead."""
    if settings().mongo_url.startswith("mongomock"):
        from langgraph.checkpoint.memory import InMemorySaver
        return InMemorySaver()
    from langgraph.checkpoint.mongodb import MongoDBSaver
    from .db import client
    return MongoDBSaver(client(), db_name=settings().mongo_db)


def app():
    global _app
    if _app is None:
        _app = build(_checkpointer())
    return _app


def reset() -> None:
    global _app
    _app = None


def config_for(request_id: str) -> dict:
    return {"configurable": {"thread_id": request_id}}
