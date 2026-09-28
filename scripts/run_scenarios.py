"""Run the 15 scenarios against the real system and report expected vs actual.

    python scripts/run_scenarios.py
    python scripts/run_scenarios.py --queue     # against a seeded demo queue

Uses a throwaway database unless --queue is given, so results are repeatable.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def run_case(sc: dict) -> dict:
    from fairtriage import service
    from fairtriage.schemas import LodgeIn

    exp = sc["expect"]
    out = service.lodge(LodgeIn(text=sc["text"], community=sc["community"],
                                vulnerability=sc.get("vulnerability", [])))
    problems, notes = [], []
    rid = out["request_id"]

    if out["status"] == "awaiting_tenant":
        notes.append(f"asked: {out['question']}")
        if "asks" in exp:
            if exp["asks"] not in out["question"].lower():
                problems.append(f"asked the wrong question: {out['question']}")
        else:
            problems.append(f"asked a question when none was expected: {out['question']}")
        if "answer" in exp:
            out = service.clarify(rid, exp["answer"])
            notes.append(f"answered '{exp['answer']}'")
    elif "asks" in exp:
        problems.append(f"expected a question about '{exp['asks']}', got none")

    view = service.request_view(rid)
    a = view["assessment"] or {}
    facts = a.get("facts") or {}
    ext = (view["extractions"][-1]["payload"] if view["extractions"] else {})
    tier = a.get("tier", "(held)")
    text = a.get("explanation_tenant", "")

    want_tier = exp.get("tier_after", exp.get("tier"))
    if want_tier and tier != want_tier:
        problems.append(f"tier {tier}, expected {want_tier}")
    if "status" in exp and view["status"] != exp["status"]:
        problems.append(f"status {view['status']}, expected {exp['status']}")
    for fld in ("whole_dwelling", "tenant_isolated"):
        if fld in exp and ext.get(fld) != exp[fld]:
            problems.append(f"{fld}={ext.get(fld)}, expected {exp[fld]}")
    if "advice" in exp and exp["advice"] not in text:
        problems.append(f"no make-safe advice ('{exp['advice']}')")
    if "says" in exp and exp["says"] not in text:
        problems.append(f"tenant text missing '{exp['says']}'")
    if facts.get("rank") is not None and facts.get("rank") != facts.get("darwin_rank"):
        problems.append("rank depends on location")

    wait = (facts.get("wait") or {}).get("range_text", "")
    return {"id": sc["id"], "group": sc["group"], "tier": tier,
            "need": a.get("need"), "rank": facts.get("rank"), "wait": wait,
            "status": view["status"], "notes": notes, "problems": problems,
            "tenant_text": text}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", action="store_true", help="run against the seeded demo DB")
    ap.add_argument("--show", type=int, help="print the full tenant text for one case")
    a = ap.parse_args()

    if not a.queue:
        os.environ["FAIRTRIAGE_MONGO_URL"] = "mongomock://"     # throwaway, in memory

    from scenarios import SCENARIOS
    results = [run_case(s) for s in SCENARIOS]

    print(f"{'#':>2}  {'group':<30}{'tier':<11}{'need':>5}  {'wait':<22}result")
    print("-" * 90)
    for r in results:
        need = f"{r['need']:.0f}" if r["need"] else "-"
        mark = "PASS" if not r["problems"] else "FAIL"
        print(f"{r['id']:>2}  {r['group']:<30}{r['tier']:<11}{need:>5}  {r['wait']:<22}{mark}")
        for n in r["notes"]:
            print(f"{'':<6}{n}")
        for p in r["problems"]:
            print(f"{'':<6}! {p}")
    failed = [r for r in results if r["problems"]]
    print("-" * 90)
    print(f"{len(results) - len(failed)} of {len(results)} passed")

    if a.show:
        r = next(x for x in results if x["id"] == a.show)
        print(f"\n--- tenant text, case {a.show} ---\n{r['tenant_text']}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
