"""Spelling normalisation, and reconciliation of the two readings.

A lexicon, not a model. Deterministic, inspectable, and it cannot invent a
hazard. The original text is never discarded: both versions are assessed,
and if they disagree on anything decision-bearing the case goes to a human.
That turns the normaliser from a hidden risk into a detector.

Build the lexicon from misspellings your own writers actually produce. Every
entry should trace to a real message.
"""

from __future__ import annotations

import re

from .schemas import Extraction

LEXICON: dict[str, str] = {
    # electrical
    "powa": "power", "powar": "power", "pawa": "power", "powr": "power",
    "powerpint": "powerpoint", "plag": "plug", "lecktrik": "electric",
    "lectric": "electric", "elektrik": "electric", "sparkin": "sparking",
    "sparkng": "sparking", "shok": "shock", "wiya": "wire", "wier": "wire",
    "lite": "light", "lyt": "light", "sokit": "socket",
    # water
    "wata": "water", "watta": "water", "wota": "water", "leekin": "leaking",
    "leking": "leaking", "leek": "leak", "pip": "pipe", "pyp": "pipe",
    "shawa": "shower", "showa": "shower", "hotwata": "hot water",
    # sanitation
    "tolet": "toilet", "toylet": "toilet", "toilit": "toilet",
    "blok": "blocked", "blokd": "blocked", "bloked": "blocked",
    "sewrage": "sewage", "suwage": "sewage", "snk": "sink", "sinck": "sink",
    # building / security
    "dor": "door", "doa": "door", "lok": "lock", "windo": "window",
    "windaw": "window", "seelin": "ceiling", "ceilin": "ceiling",
    "roofe": "roof",
    # climate / appliance
    "aircon": "air conditioner", "fridg": "fridge", "stov": "stove",
    "cooka": "stove", "fann": "fan",
    # general
    "bin": "been", "brokn": "broken", "brok": "broken", "bruk": "broken",
    "pls": "please", "plz": "please", "sumone": "someone", "kum": "come",
    "nt": "not", "bcz": "because", "hse": "house", "kichen": "kitchen",
    "gud": "good", "nogud": "no good", "cant": "cannot", "dont": "do not",
}

# never "corrected": these bear hazards, and a wrong correction changes the
# assessment silently
PROTECTED = {"gas", "smoke", "fire", "spark", "sparks", "shock", "sewage",
             "flood", "flooding", "burning", "smell"}

_WORD = re.compile(r"\b[\w']+\b")


def normalise(text: str) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []

    def repl(m: re.Match) -> str:
        w = m.group(0)
        low = w.lower()
        if low in PROTECTED or low not in LEXICON:
            return w
        out = LEXICON[low]
        changes.append((w, out))
        return out

    return _WORD.sub(repl, text), changes


DECISIVE = ("actionability", "hazard_domain", "endangers_person",
            "essential_service_lost")


def reconcile(a: Extraction, b: Extraction) -> tuple[Extraction, dict]:
    """Compare readings of the original and normalised text.

    Never pick a winner. On disagreement, take the MORE CAUTIOUS reading on
    the safety fields and escalate, so a spelling correction can never
    downgrade anything.
    """
    diffs = {}
    for f in DECISIVE:
        va, vb = getattr(a, f), getattr(b, f)
        if va != vb:
            diffs[f] = (getattr(va, "value", va), getattr(vb, "value", vb))

    if not diffs:
        return a, {}

    merged = a.model_copy(update={
        "endangers_person": a.endangers_person or b.endangers_person,
        "essential_service_lost": a.essential_service_lost or b.essential_service_lost,
    })
    # prefer whichever reading says this is an actionable repair
    if not a.in_queue and b.in_queue:
        merged = merged.model_copy(update={"actionability": b.actionability,
                                           "hazard_domain": b.hazard_domain})
    return merged, diffs
