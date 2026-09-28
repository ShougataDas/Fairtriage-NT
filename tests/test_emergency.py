"""Life at risk now: the answer is 'call 000', before anything else.

Regression for a real failure: a tenant answered our question with 'perhaps
the gas is on fire' and was told we could not work out what needed fixing.
The report then dropped out of the queue where no coordinator would see it.
"""

import pytest

from fairtriage import service
from fairtriage.extract import KeywordExtractor
from fairtriage.schemas import LodgeIn

K = KeywordExtractor()


def test_the_reported_failure_end_to_end():
    r = service.lodge(LodgeIn(text="not sure what it is", community="Darwin (Parap)"))
    assert r["status"] == "awaiting_tenant"
    out = service.clarify(r["request_id"], "perhaps the gas is on fire")
    assert out["tier"] == "Immediate"
    text = out["explanation_tenant"]
    assert text.startswith("If there is a fire, or anyone is hurt, call 000 now")
    assert "perhaps the gas is on fire" in text          # the answer is shown
    assert any(f["code"] == "emergency_000" for f in out["flags"])


def test_same_words_as_a_new_report_are_not_held_for_a_question():
    r = service.lodge(LodgeIn(text="perhaps the gas is on fire", community="Wadeye"))
    assert r["status"] != "awaiting_tenant", "an emergency must never wait on a question"
    assert r["tier"] == "Immediate" and r["rank"] == 1


@pytest.mark.parametrize("text", [
    "the kitchen caught fire",
    "flames coming out of the power point",
    "i think the stove might be on fire",
    "my son got a bad shock from the light switch",
    "the gas bottle exploded outside",
    "grandma collapsed on the floor, the heater is smoking",
])
def test_emergencies_in_other_words(text):
    e = K.extract(text)
    assert e.emergency_000 and e.endangers_person, text


@pytest.mark.parametrize("text", [
    "the fire alarm keeps beeping at night",
    "the fire extinguisher is missing from the kitchen",
    "there is no fire, just a smell of burnt toast",
    "there was a small fire last week but it is out now",
])
def test_fire_words_that_are_not_emergencies(text):
    assert not K.extract(text).emergency_000, text


def test_emergency_tops_the_immediate_tier():
    service.lodge(LodgeIn(text="power point is sparking", community="Belyuen"),
                  lodged_at="2026-01-01T00:00:00+00:00")
    r = service.lodge(LodgeIn(text="the kitchen caught fire", community="Belyuen"))
    assert r["rank"] == 1


def test_emergency_explanation_passes_the_verifier():
    from fairtriage.explain import verify
    r = service.lodge(LodgeIn(text="the kitchen caught fire", community="Wadeye"))
    a = service.request_view(r["request_id"])["assessment"]
    assert verify(a["explanation_tenant"], a["facts"]) == []


def test_unclear_after_asking_goes_to_a_person_not_nowhere():
    r = service.lodge(LodgeIn(text="something is off", community="Katherine"))
    out = service.clarify(r["request_id"], "dunno really")
    assert out["status"] == "needs_phone_call"
    assert "a staff member will phone you" in out["explanation_tenant"]
    assert "You said: \u201cdunno really\u201d" in out["explanation_tenant"]
    assert r["request_id"] in [c["request_id"] for c in service.contact_list()]


def test_a_dangerous_job_is_never_held_for_a_question():
    """'sewage coming inside' could ask something, but danger ranks at once."""
    r = service.lodge(LodgeIn(text="toilet overflowing onto the floor with sewage", community="Wadeye"))
    assert r["status"] != "awaiting_tenant"


@pytest.mark.parametrize("text", [
    "the pilot light on the hot water system wont stay alight",
    "the gas flame on the stove is yellow",
    "the burner flame is really weak",
    "the heater wont fire up in the mornings",
])
def test_normal_flames_are_not_000(text):
    """A tenant told to call 000 for a pilot light learns to ignore the warning."""
    assert not K.extract(text).emergency_000, text


def test_no_approach_advice_in_an_emergency():
    """Regression: a gas FIRE was told to 'turn the gas off at the bottle'.
    Right for a smell, dangerous for a fire."""
    r = service.lodge(LodgeIn(text="the gas bottle is on fire", community="Wadeye"))
    t = r["explanation_tenant"]
    assert "turn the gas off" not in t and "meter box" not in t
    assert "call 000 now" in t and "get everyone out" in t
    assert "Expect a tradesperson" not in t


def test_gas_smell_without_fire_still_gets_make_safe_advice():
    r = service.lodge(LodgeIn(text="strong gas smell around the stove", community="Wadeye"))
    assert "turn the gas off at the bottle" in r["explanation_tenant"]
    assert "call 000" not in r["explanation_tenant"]


@pytest.mark.parametrize("text", [
    "not sure the gas is on fire",
    "no idea but i think the kitchen is on fire",
    "dont know, the power point is sparking",
    "not sure but there is smoke coming out of the wall socket",
])
def test_hedges_never_cancel_a_hazard(text):
    from fairtriage.extract import KeywordExtractor
    e = KeywordExtractor().extract(text)
    assert e.endangers_person, text
