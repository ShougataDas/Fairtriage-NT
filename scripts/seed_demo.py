"""Populate a demo queue.

    python scripts/seed_demo.py                       # 90 rows + demo cases
    python scripts/seed_demo.py --data fairtriage_v3.csv --n 150
    python scripts/seed_demo.py --model               # read rows with the .env model

Draws real report text from the migrated dataset, backdates lodgement so the
queue has history, then adds the curated cases the presentation uses.
Clarification questions raised during seeding are answered from the row's
own context, so seeding never stalls.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fairtriage import config, db, graph, service  # noqa: E402
from fairtriage.reference import communities  # noqa: E402
from fairtriage.schemas import LodgeIn  # noqa: E402

DEMO = [
    # (text, community, vulnerability, days_ago, alternative_toilet)
    ("powa plug hot make crack sound", "Darwin (Ludmilla)", [], 0.1, None),
    ("The socket gets very hot and makes a crackling sound when I use it.",
     "Darwin (Nightcliff)", [], 0.2, None),
    ("Just checking if this app works. Also the powerpoint in the kitchen has been "
     "sparking since Tuesday.", "Wadeye", ["elderly"], 3, None),
    ("the only toilet is blocked", "Darwin (Malak)", ["children"], 1, False),
    ("the only toilet is blocked", "Maningrida", ["children"], 1, False),
    ("aircon bin broken since wet season start, old lady live here", "Wadeye",
     ["elderly"], 76, None),
    ("There is no gas smell.", "Palmerston", [], 0.5, None),
    ("its fine now dont worry about it", "Galiwinku", [], 80, None),
    ("kitchen cupboard door came off the hinge", "Darwin (Karama)", [], 4, None),
    ("The home is fine, just the back room floods a bit when it rains",
     "Gunbalanya", [], 20, None),
]


def reset() -> None:
    graph.reset()
    if not db.ping():
        sys.exit(f"\nCannot reach MongoDB at {config.settings().mongo_url}.\n"
                 f"Start MongoDB (or set FAIRTRIAGE_MONGO_URL), then run this again.")
    db.drop_all()          # a running server can stay up: it simply sees the new data


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _set_age(request_id: str, days_ago: float) -> None:
    """Immediate jobs are made safe within hours; backdating one by weeks would
    show a queue state that does not happen."""
    db.update_request(request_id, {"lodged_at": _iso(days_ago)})


STREETS = ["Smith", "Stuart", "Mitchell", "Cavenagh", "McMillans", "Bagot", "Trower", "Dick Ward",
           "Lee Point", "Rothdale", "Chung Wah", "Temira", "Gsell", "Farrar", "Woodroffe"]


def _address(rng: random.Random, community: str) -> str:
    """A plausible demo address: street numbers in towns, lot numbers in
    remote communities, where houses are usually known by lot."""
    if communities()[community].remote:
        return f"Lot {rng.randint(10, 480)}"
    unit = f"Unit {rng.randint(1, 12)}, " if rng.random() < 0.3 else ""
    return f"{unit}{rng.randint(1, 140)} {rng.choice(STREETS)} {rng.choice(['Street', 'Road', 'Crescent', 'Drive'])}"


def _answer_for(question: str, row) -> str:
    q = question.lower()
    if "only toilet" in q:
        return "yes it is the only one" if not row.get("alternative_toilet") else "no there is another"
    if "lock" in q:
        return "no we cannot lock it"
    if "light" in q or "power" in q:
        return "no, not near anything electrical"
    return "the tap in the kitchen is broken"


def _progress(done: int, total: int, out: dict) -> None:
    fell_back = any(f["code"] == "extraction_fallback" for f in out.get("flags", []))
    print(f"  [{done}/{total}] {out.get('tier', out['status']):<11}"
          f"{' (model failed, keyword rules used)' if fell_back else ''}", flush=True)


def seed(data: Path | None, n: int, seed_: int) -> None:
    reset()
    rng = random.Random(seed_)
    names = list(communities())

    rows = []
    if data and data.exists():
        import pandas as pd
        df = pd.read_csv(data)
        df = df[df.actionability_label == "Repair"].sample(n=min(n, len(df)),
                                                           random_state=seed_)
        rows = df.to_dict("records")
    else:
        print(f"no dataset at {data}; seeding demo cases only")

    lodged = asked = 0
    total = len(rows) + len(DEMO)
    for r in rows:
        comm = r.get("community") if r.get("community") in names else rng.choice(names)
        vul = json.loads(r["vulnerability"]) if isinstance(r.get("vulnerability"), str) else []
        alt = r.get("alternative_toilet")
        alt = None if alt is None or (isinstance(alt, float)) else bool(alt)
        out = service.lodge(LodgeIn(text=r["report_text"], community=comm,
                                    address=_address(rng, comm),
                                    vulnerability=vul, alternative_toilet=alt),
                            lodged_at=_iso(rng.lognormvariate(1.8, 1.0)))
        if out["status"] == "awaiting_tenant":
            asked += 1
            out = service.clarify(out["request_id"], _answer_for(out["question"], r))
        if out.get("tier") == "Immediate":
            _set_age(out["request_id"], rng.uniform(0.05, 0.4))
        lodged += 1
        _progress(lodged, total, out)

    for text, comm, vul, days, alt in DEMO:
        out = service.lodge(LodgeIn(text=text, community=comm, vulnerability=vul,
                                    address=_address(rng, comm),
                                    alternative_toilet=alt), lodged_at=_iso(days))
        if out["status"] == "awaiting_tenant":
            out = service.clarify(out["request_id"], "yes only one")
        lodged += 1
        _progress(lodged, total, out)

    # leave one question genuinely pending, so the demo can answer it live
    service.lodge(LodgeIn(text="toilet is blocked.", community="Belyuen", address="Lot 57"),
                  lodged_at=_iso(0.05))

    print(f"seeded {lodged} requests ({asked} needed a clarifying answer), "
          f"plus 1 left awaiting the tenant")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "fairtriage_v3.csv"))
    ap.add_argument("--n", type=int, default=90)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--model", action="store_true",
                    help="read seed rows with the model set in .env (uses API quota: "
                         "one or two calls per row). Default: keyword rules")
    a = ap.parse_args()
    if not a.model:
        # Seeding 90+ rows would exhaust a free-tier daily allowance before the
        # demo starts. Each stored reading records which extractor made it.
        os.environ["FAIRTRIAGE_EXTRACTOR"] = "keyword"
        config.reset_caches()
    print(f"seeding with: {config.reader_status()['label']}")
    seed(Path(a.data), a.n, a.seed)


if __name__ == "__main__":
    main()
