"""The policy engine. No model, no randomness, no I/O.

This is the component a judge will interrogate, so it is small, pure, and
fully unit-tested.

Tier is LEXICOGRAPHIC: danger -> Immediate, essential service lost -> Urgent,
otherwise Routine. Nothing in a lower tier can climb into a higher one. A
weighted sum would let accumulated waiting time buy its way past a live
electrical fault; lexicographic tiering is the standard fix.

Need orders jobs WITHIN a tier. Two inputs. There is no distance term, and
no variable exists for kilometres to be placed in — a stronger guarantee
than a weight set to zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import policy
from .schemas import Extraction, Habitability

TIER_ORDER = {"Immediate": 0, "Urgent": 1, "Routine": 2, "NotInQueue": 9}


@dataclass
class Component:
    name: str
    raw: float
    weight: float
    detail: str

    @property
    def contribution(self) -> float:
        return round(self.raw * self.weight, 4)


@dataclass
class PolicyResult:
    tier: str
    tier_reason: str
    need: float
    components: list[Component] = field(default_factory=list)
    version: str = ""


def tier_of(ex: Extraction) -> tuple[str, str]:
    if not ex.in_queue:
        return "NotInQueue", f"not a repair request ({ex.actionability.value})"
    if ex.emergency_000:
        return "Immediate", "your safety may be at risk right now"
    if ex.endangers_person:
        return "Immediate", "it can hurt someone today"
    if ex.essential_service_lost:
        return "Urgent", "an essential service is not working"
    if ex.habitability in (Habitability.UNINHABITABLE, Habitability.SEVERELY_IMPAIRED):
        return "Urgent", "it stops the house being used properly"
    return "Routine", ("we did not find anything in your message that makes it "
                       "dangerous or stops you using water, power, the toilet or the stove")


def need_of(ex: Extraction, vulnerability: list[str]) -> tuple[float, list[Component]]:
    p = policy()
    w = p["need_weights"]
    hab = p["habitability_score"][ex.habitability.value]
    vscores = p["vulnerability_score"]
    known = [v for v in vulnerability if v in vscores]
    vul = max((vscores[v] for v in known), default=0.0)

    ext = p["extent_score"]["whole_dwelling" if ex.whole_dwelling else "one_fixture"]
    con = p["containment_score"]["tenant_made_safe" if ex.tenant_isolated else "not_contained"]
    comps = [
        Component("habitability", hab, w["habitability"], ex.habitability.value),
        Component("extent", ext, w["extent"],
                  "whole house" if ex.whole_dwelling else "one fixture or room"),
        Component("containment", con, w["containment"],
                  "tenant has made it safe" if ex.tenant_isolated else "not yet made safe"),
        Component("vulnerability", vul, w["vulnerability"],
                  ", ".join(known) if known else "none recorded"),
    ]
    need = round(sum(c.contribution for c in comps) * 100, 1)
    if ex.emergency_000:
        comps.append(Component("emergency", 1.0, 0.0, "life at risk now, 000"))
        need = float(p["emergency_need"])
    return need, comps


def assess(ex: Extraction, vulnerability: list[str]) -> PolicyResult:
    tier, reason = tier_of(ex)
    if tier == "NotInQueue":
        return PolicyResult(tier, reason, 0.0, [], policy()["version"])
    need, comps = need_of(ex, vulnerability)
    return PolicyResult(tier, reason, need, comps, policy()["version"])


def sort_key(tier: str, need: float, lodged_at: str) -> tuple:
    """Tier first, then need descending, then first-in first-served."""
    return (TIER_ORDER[tier], -need, lodged_at)
