"""Evaluate extraction against a labelled dataset.

    python scripts/run_eval.py                                # keyword, test split
    python scripts/run_eval.py --extractor openai --limit 300 # needs OPENAI_API_KEY
    python scripts/run_eval.py --extractor gemini --limit 300 # needs GEMINI_API_KEY
    python scripts/run_eval.py --extractor anthropic --limit 300  # needs ANTHROPIC_API_KEY

Runs the same path as production: normalise, read both texts, reconcile.
Reports per-field macro-F1, the two safety metrics, per-probe accuracy, and
paraphrase invariance. Writes reports/eval_<extractor>.md.

READ THIS BEFORE QUOTING ANY NUMBER. Rows with label_source=derived were
labelled by a rule in migrate_config.py, not by people. Scoring against them
measures agreement with that rule. Quote only numbers computed on
human-labelled rows, and report Cohen's kappa beside them.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from sklearn.metrics import f1_score, precision_recall_fscore_support  # noqa: E402

from fairtriage.extract import EXTRACTORS, KeywordExtractor  # noqa: E402
from fairtriage.normalise import normalise, reconcile  # noqa: E402

# the dataset has three actionability classes; the system has seven
TO_DATASET = {"repair": "Repair", "no_issue": "NoIssue", "question": "NoIssue",
              "out_of_scope": "NoIssue", "unclear": "Unclear",
              "withdrawal": "Unclear", "follow_up": "Unclear"}


def read(ex, text: str):
    norm, _ = normalise(text)
    a = ex.extract(text)
    if norm == text:
        return a, False
    merged, diffs = reconcile(a, ex.extract(norm))
    return merged, bool(diffs)


def as_bool(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "fairtriage_v3.csv"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--extractor", default="offline", choices=["offline", "keyword", *EXTRACTORS])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    df = pd.read_csv(a.data)
    df = df[df.split == a.split] if a.split != "all" else df
    if a.limit:
        df = df.sample(n=min(a.limit, len(df)), random_state=1)
    ex = KeywordExtractor() if a.extractor in ("offline", "keyword") else EXTRACTORS[a.extractor]()

    rows, errors = [], 0
    for _, r in df.iterrows():
        try:
            e, changed = read(ex, str(r.report_text))
        except Exception:
            errors += 1
            continue
        rows.append({
            "challenge": r.challenge_type, "group": r.paraphrase_group,
            "label_source": r.label_source,
            "act_true": r.actionability_label, "act_pred": TO_DATASET[e.actionability.value],
            "danger_true": as_bool(r.endangers_person), "danger_pred": e.endangers_person,
            "ess_true": as_bool(r.essential_service_lost), "ess_pred": e.essential_service_lost,
            "norm_changed": changed,
        })
    res = pd.DataFrame(rows)

    lines = [f"# Extraction evaluation: {a.extractor}, split={a.split}", ""]
    src = res.label_source.value_counts().to_dict()
    lines.append(f"Rows scored: {len(res)} (errors {errors}). Label sources: {src}.")
    if src.get("derived"):
        lines += ["", "> **Most labels here are derived by rule, not human.** These numbers "
                  "measure agreement with the migration rule. Do not quote them as accuracy. "
                  "Re-run on the blind-annotated set and report kappa beside the result.", ""]

    def f1(t, p):
        return f1_score(res[t], res[p], average="macro", zero_division=0)

    lines += ["## Per-field macro-F1", "", "| Field | Macro-F1 |", "|---|---|",
              f"| actionability | {f1('act_true', 'act_pred'):.3f} |",
              f"| endangers_person | {f1('danger_true', 'danger_pred'):.3f} |",
              f"| essential_service_lost | {f1('ess_true', 'ess_pred'):.3f} |", ""]

    danger = res[res.danger_true]
    fnr = 1 - danger.danger_pred.mean() if len(danger) else float("nan")
    dismissed = danger[danger.act_pred != "Repair"]
    lines += ["## Safety", "",
              f"- **Critical-hazard false-negative rate:** {fnr:.1%} "
              f"({int((~danger.danger_pred).sum())} of {len(danger)} dangerous reports missed)",
              f"- **False dismissal rate:** {len(dismissed) / max(len(danger), 1):.1%} "
              f"({len(dismissed)} dangerous reports routed out of the queue)",
              f"- Normalisation changed the reading on {res.norm_changed.mean():.1%} of messages; "
              f"each would be escalated to a human.", ""]

    p, r_, _, _ = precision_recall_fscore_support(res.danger_true, res.danger_pred,
                                                  average="binary", zero_division=0)
    lines.append(f"Danger precision {p:.3f}, recall {r_:.3f}.")
    lines.append("")

    lines += ["## By challenge type", "", "| Challenge | n | Actionability acc. | Danger acc. |",
              "|---|---|---|---|"]
    for ch, g in res.groupby("challenge"):
        lines.append(f"| {ch} | {len(g)} | {(g.act_true == g.act_pred).mean():.1%} | "
                     f"{(g.danger_true == g.danger_pred).mean():.1%} |")
    lines.append("")

    groups = res.groupby("group").filter(lambda g: len(g) > 1)
    if len(groups):
        broken = [k for k, g in groups.groupby("group")
                  if g.danger_pred.nunique() > 1 or g.ess_pred.nunique() > 1]
        n = groups.group.nunique()
        lines += ["## Paraphrase invariance", "",
                  f"{n - len(broken)} of {n} paraphrase groups read identically across registers."
                  + (f" Broken: {', '.join(broken)}." if broken else ""),
                  f"With only {n} groups this is a smoke test, not a measurement. "
                  "Aim for 40 or more.", ""]

    out = ROOT / "reports" / f"eval_{a.extractor}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
