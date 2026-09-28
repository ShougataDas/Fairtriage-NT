"""Written in our own words, NOT copied from the dataset.

The generated data repeats a small set of templates. Matching those strings
would raise scores without teaching the system anything that transfers to a
real tenant. These tests check the fixes generalise past that wording.
"""

import pytest

from fairtriage.extract import KeywordExtractor

K = KeywordExtractor()


@pytest.mark.parametrize("text", [
    "strong gas odour near the oven",
    "fumes from the gas bottle outside the kitchen",
    "you can hear the gas cylinder hissing",
    "a cable is dangling out of the wall near the bed",
    "water is running all over the floor from under the sink",
    "the pipe under the house has split and water keeps gushing",
    "sewage is backing up in the shower",
    "the back door frame got kicked in, anyone can walk in",
    "front lock is busted since the weekend",
])
def test_hazard_synonyms_are_danger(text):
    assert K.extract(text).endangers_person, text


@pytest.mark.parametrize("text", [
    "the shower drains normally now",
    "all the lights are working properly",
    "that patch on the ceiling is an old stain, all dry",
    "the back door locks properly again",
    "the stove works as normal",
])
def test_healthy_state_is_not_a_repair(text):
    e = K.extract(text)
    assert e.actionability.value != "repair", text


@pytest.mark.parametrize("text", [
    "i think something is wrong with the hot water but not sure",
    "the lights act weird at night, hard to say why",
    "fridge problem, please ring me",
    "there is a wet patch, no idea where it is from",
])
def test_vague_reports_are_asked_about_not_ranked(text):
    e = K.extract(text)
    assert e.actionability.value == "unclear", text
    assert e.confidence.value == "low"


def test_vague_but_dangerous_is_still_danger():
    """Uncertainty must never downgrade a hazard."""
    e = K.extract("not sure what it is but the power point is sparking")
    assert e.endangers_person and e.actionability.value == "repair"


def test_single_tap_dry_with_no_leak_is_not_supply_loss():
    e = K.extract("the tap is dry and does not leak")
    assert not e.essential_service_lost


def test_all_taps_dry_is_supply_loss():
    assert K.extract("all the taps have gone dry since lunch").essential_service_lost


@pytest.mark.parametrize("text", [
    "not sure but i think i can smell gas near the heater",
    "there's a smell coming from the bottle outside, kind of like gas",
    "maybe nothing but the insulation on the fridge cord is cracked",
    "you can see copper showing on the kettle cord",
])
def test_hedged_hazard_is_still_a_hazard(text):
    """Uncertainty must never downgrade danger. 'Seems like gas' is gas."""
    e = K.extract(text)
    assert e.endangers_person and e.actionability.value == "repair", text


@pytest.mark.parametrize("text", [
    "my house is flooded last night",
    "i roof was gone in last night cyclone",
    "Strong winds have removed several sheets from the roof and rain is entering the bedrooms",
    "A tree fell onto the house during a storm and damaged the roof",
    # our own wording, unlike the reports above
    "cyclone ripped half the tin off our roof",
    "the verandah came down in the storm",
    "big branch smashed through the bedroom ceiling",
    "whole place is under water after the storm",
])
def test_storm_and_structural_damage_is_immediate(text):
    """Regression: every one of these came out Routine, with the tenant told it
    was 'not dangerous'. In the Top End this is the core make-safe event."""
    e = K.extract(text)
    assert e.endangers_person and e.hazard_domain.value in ("structural", "water"), text


@pytest.mark.parametrize("text", [
    "the roof is fine after the storm",
    "small roof drip only during heavy rain",
])
def test_storm_words_alone_do_not_escalate(text):
    assert not K.extract(text).endangers_person, text


def test_heavy_ingress_is_urgent_not_routine():
    e = K.extract("large ceiling leak is soaking the bedroom")
    assert e.habitability.value == "severely_impaired"
