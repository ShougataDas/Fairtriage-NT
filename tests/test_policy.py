"""The policy engine: the component a judge will interrogate."""

import pytest

from fairtriage.policy import assess, sort_key, tier_of
from fairtriage.schemas import (Actionability, Confidence, DecisiveFact, Extraction,
                                Habitability, HazardDomain)


def ex(**kw):
    base = dict(actionability=Actionability.REPAIR, hazard_domain=HazardDomain.WATER,
                is_active=True, endangers_person=False, essential_service_lost=False,
                habitability=Habitability.IMPAIRED, evidence_phrase="x",
                confidence=Confidence.HIGH, missing_decisive_fact=DecisiveFact.NONE)
    base.update(kw)
    return Extraction(**base)


def test_danger_is_immediate():
    assert tier_of(ex(endangers_person=True))[0] == "Immediate"


def test_essential_is_urgent():
    assert tier_of(ex(essential_service_lost=True))[0] == "Urgent"


def test_otherwise_routine():
    assert tier_of(ex())[0] == "Routine"


@pytest.mark.parametrize("act", [Actionability.NO_ISSUE, Actionability.QUESTION,
                                 Actionability.WITHDRAWAL, Actionability.UNCLEAR,
                                 Actionability.OUT_OF_SCOPE])
def test_non_requests_leave_the_queue(act):
    assert tier_of(ex(actionability=act))[0] == "NotInQueue"


def test_lexicographic_danger_beats_maximum_need_below():
    """Nothing in a lower tier can climb into a higher one."""
    worst_urgent = assess(ex(essential_service_lost=True,
                             habitability=Habitability.UNINHABITABLE),
                          ["medical_equipment"])
    mild_immediate = assess(ex(endangers_person=True, habitability=Habitability.COSMETIC), [])
    assert worst_urgent.need > mild_immediate.need            # higher need number...
    k_urgent = sort_key(worst_urgent.tier, worst_urgent.need, "2020-01-01")
    k_immediate = sort_key(mild_immediate.tier, mild_immediate.need, "2030-01-01")
    assert k_immediate < k_urgent                             # ...still ranks below


def test_need_has_no_location_input():
    """No variable exists for distance. Checked structurally, not by weight."""
    import inspect
    from fairtriage import policy
    src = inspect.getsource(policy.need_of) + inspect.getsource(policy.tier_of)
    for word in ("km", "distance", "community", "remote", "travel", "road"):
        assert word not in src, f"'{word}' appears in the ranking code"


def test_vulnerability_raises_need_within_tier_only():
    plain = assess(ex(), [])
    vul = assess(ex(), ["medical_equipment"])
    assert vul.need > plain.need and vul.tier == plain.tier == "Routine"


def test_ties_break_first_in_first_served():
    assert sort_key("Urgent", 50, "2026-01-01") < sort_key("Urgent", 50, "2026-01-02")


def test_weights_sum_to_one():
    from fairtriage.config import policy
    assert abs(sum(policy()["need_weights"].values()) - 1.0) < 1e-9
