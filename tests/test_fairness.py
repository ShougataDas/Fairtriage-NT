"""Fairness properties, tested as properties rather than asserted in prose."""

import pytest

from fairtriage import service
from fairtriage.reference import communities
from fairtriage.schemas import LodgeIn

FAULTS = [
    "power point is sparking in the kitchen",
    "the only toilet is blocked",
    "no water coming out of the taps",
    "kitchen cupboard door came off the hinge",
]


@pytest.mark.parametrize("text", FAULTS)
def test_counterfactual_location_invariance(text):
    """Same message, every community: tier and need must be identical."""
    seen = set()
    for c in communities():
        r = service.lodge(LodgeIn(text=text, community=c), lodged_at="2026-01-01T00:00:00+00:00")
        v = service.request_view(r["request_id"])
        seen.add((v["assessment"]["tier"], v["assessment"]["need"]))
    assert len(seen) == 1, f"location changed the outcome: {seen}"


def test_rank_equals_location_free_rank_everywhere():
    for i, c in enumerate(communities()):
        service.lodge(LodgeIn(text=FAULTS[i % len(FAULTS)], community=c))
    for row in service.queue_view():
        facts = service.request_view(row["request_id"])["assessment"]["facts"]
        assert facts["rank"] == facts["darwin_rank"]


def test_distance_changes_wait_but_not_rank():
    near = service.lodge(LodgeIn(text="the only toilet is blocked", community="Darwin (Malak)"),
                         lodged_at="2026-01-01T00:00:00+00:00")
    far = service.lodge(LodgeIn(text="the only toilet is blocked", community="Maningrida"),
                        lodged_at="2026-01-01T00:00:00+00:00")
    assert near["tier"] == far["tier"]
    assert far["wait"]["central"] > near["wait"]["central"]
    # an urgent remote job is reached by charter within hours, so no travel gap
    # is claimed; a routine one waits for a trip, and the tenant is told why
    far_routine = service.lodge(LodgeIn(text="the kitchen cupboard door came off the hinge",
                                        community="Maningrida"))
    assert "The difference is travel, not priority." in far_routine["explanation_tenant"]


REGISTERS = [
    ["powa plug hot make crack sound",
     "the power point gets hot and crackles",
     "power socket is very hot and making crack sound when we use",
     "The power outlet in the kitchen becomes hot and emits a crackling sound during use."],
    ["no wata", "no water coming out of the taps",
     "water is not come from tap since morning",
     "There has been no water supply to the dwelling since this morning."],
    ["tolet blok, only one", "the only toilet is blocked",
     "we have one toilet only and it is block",
     "The dwelling's sole toilet is blocked and cannot be used."],
    ["cant lock door", "the front door will not lock",
     "front door not locking, we cannot lock proper",
     "The external front door cannot be locked."],
]


@pytest.mark.parametrize("variants", REGISTERS)
def test_paraphrase_invariance(variants):
    """The same fault written four ways must land in the same tier. This is the
    test for whether plainer or second-language English is penalised."""
    tiers = set()
    for t in variants:
        r = service.lodge(LodgeIn(text=t, community="Wadeye"))
        if r["status"] == "awaiting_tenant":
            r = service.clarify(r["request_id"], "yes")
        tiers.add(r["tier"])
    assert len(tiers) == 1, f"register changed the tier: {dict(zip(variants, tiers))}"
