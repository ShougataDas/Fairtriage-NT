"""Essential services, described the way tenants actually describe them.

Written as a tester: a power cut is rarely reported as "no power". People list
what stopped ("fan, lights and fridge nothing is running"), name the event
("blackout", "power cut"), or describe the house ("it's dark"). Each must read
as an essential service lost (Urgent). The look-alikes at the bottom (one
light, one power point, a fridge not cold) must stay Routine.
"""

import pytest

from fairtriage.extract import KeywordExtractor
from fairtriage.normalise import normalise, reconcile
from fairtriage.policy import tier_of

K = KeywordExtractor()


def read(text):
    a = K.extract(text)
    norm, _ = normalise(text)
    return a if norm == text else reconcile(a, K.extract(norm))[0]


POWER_LOST = [
    # the report that prompted this file
    "electrical switch is not working, fan , lights and fridges nothing is running.",
    # listing what stopped
    "lights, fan and fridge all stopped working",
    "the lights and the fridge are not working",
    "nothing works, no lights no fan no fridge",
    "tv, fridge and lights all off and wont turn on",
    "none of the lights or power points work",
    "everything electrical stopped working",
    "all the lights went out and the fridge is off",
    # naming the event
    "the power is out",
    "power went off this morning and still not back",
    "power has been cut since yesterday",
    "blackout in our house since last night",
    "power outage at my unit",
    "electricity is not working",
    "no electricity in the house",
    "electricity gone since morning",
    # describing the house
    "house is dark, power gone",
    "the whole house is dark",
    # the switchboard
    "the safety switch keeps tripping and we have no power",
    "main switch tripped and will not reset",
    "the breaker keeps tripping and everything goes off",
    # second-language and hurried
    "no powa for house",
    "light no work, fridge no work, fan no work",
    "all light off cant turn on, fridge not cold",
    "power gone",
]

WATER_HOT_WATER_COOKING_LOST = [
    "only cold water comes out of the shower",
    "the hot water system is not heating",
    "water heater broken, cold showers only",
    "no water pressure at all, nothing comes out",
    "taps are dry",
    "the stove and the oven are both dead, we cannot cook",
    "nothing to cook with, the cooktop is dead",
]

STAYS_ROUTINE = [
    "one light in the bedroom does not work",
    "the fan is not working",
    "fridge is not cold",
    "the power point in the kitchen is not working",
    "bathroom light switch is broken",
    "electrical switch is not working",
    "the power board cord is frayed but works",          # not a power cut
    "the oven light is broken",
    "the lights are fine but the fan is noisy",
    # found by comparing against the 12,000-message dataset
    "fan has stopped but nothing is burning or sparking",
    "one outlet does nothing but the other outlets work",
    "the fan stopped and one stove element is not working, nothing is burning",
]


@pytest.mark.parametrize("text", POWER_LOST)
def test_power_lost_is_urgent(text):
    e = read(text)
    assert e.essential_service_lost, text
    assert tier_of(e)[0] in ("Urgent", "Immediate"), text
    assert e.trade == "Electrician", text


@pytest.mark.parametrize("text", WATER_HOT_WATER_COOKING_LOST)
def test_other_essentials_lost_are_urgent(text):
    e = read(text)
    assert tier_of(e)[0] in ("Urgent", "Immediate"), text


@pytest.mark.parametrize("text", STAYS_ROUTINE)
def test_look_alikes_stay_routine(text):
    e = read(text)
    assert tier_of(e)[0] == "Routine", text


# Regression: "the power socket has created short circuit. Whole home has power
# outage" was Urgent, 2 to 3 days. A short circuit is a live fault and a fire
# risk, like sparking: Immediate. A plain power cut stays Urgent.
@pytest.mark.parametrize("text", [
    "the power socket has created short circuit. Whole home has power outage",
    "there was a short circuit in the kitchen",
    "power point shorted and now no power anywhere",
    "the socket blew and tripped the power, nothing works",
    "the plug went bang and there is no power in the kitchen",
])
def test_a_short_circuit_is_electrical_danger(text):
    from fairtriage.extract import KeywordExtractor
    e = KeywordExtractor().extract(text)
    assert e.actionability.value == "repair" and e.endangers_person, text


def test_a_short_circuit_report_is_immediate_with_safety_advice():
    from fairtriage import service
    from fairtriage.schemas import LodgeIn
    r = service.lodge(LodgeIn(text="the power socket has created short circuit. Whole home has power outage",
                              community="Palmerston (Farrar)"))
    assert r["tier"] == "Immediate"
    assert "hours" in r["explanation_tenant"].splitlines()[0]
    assert "meter box" in r["explanation_tenant"]


@pytest.mark.parametrize("text, danger", [
    ("no short circuit, just the light bulb is gone", False),
    ("the fuse blew and we have no power", False),          # outage, not a live fault
    ("I am short of money for rent", False),
])
def test_short_words_that_are_not_a_short_circuit(text, danger):
    from fairtriage.extract import KeywordExtractor
    assert KeywordExtractor().extract(text).endangers_person is danger, text


@pytest.mark.parametrize("text", [
    "nothing electrical works in any room",
    "none of the lights come on",
    "none of the power points work",
    "all the lights are off",
])
def test_every_light_or_socket_out_is_a_lost_supply(text):
    from fairtriage.extract import KeywordExtractor
    e = KeywordExtractor().extract(text)
    assert e.actionability.value == "repair" and e.essential_service_lost, text


@pytest.mark.parametrize("text, kind", [
    ("nothing works in the house", "unclear"),        # was dismissed: "works" read as fine
    ("everything has stopped", "unclear"),
    ("nothing is wrong, everything works", "no_issue"),
    ("all the lights are working fine", "no_issue"),
])
def test_nothing_works_is_asked_about_not_dismissed(text, kind):
    from fairtriage.extract import KeywordExtractor
    assert KeywordExtractor().extract(text).actionability.value == kind, text


# Found by the release audit: Aboriginal English and Kriol phrasings, and a
# lost-cooking phrasing, were under-ranked or dismissed.
@pytest.mark.parametrize("text", [
    "toilet im broke, no flush, only one toilet here",     # "only toilet" in another clause
    "power bin finish whole house",                         # Kriol: the power has gone
    "no more water come out tap",                           # was dismissed as resolved
    "water bin finish",
    "the stove is not working and there is no other way to cook",
])
def test_lost_essential_services_in_other_words(text):
    from fairtriage.extract import KeywordExtractor
    e = KeywordExtractor().extract(text)
    assert e.actionability.value == "repair" and e.essential_service_lost, text


@pytest.mark.parametrize("text", [
    "no more water leaking now",
    "the tap was fixed, no more water leaking anymore",
    "I finished cooking, the stove is fine",
])
def test_no_more_and_finished_that_are_not_a_lost_service(text):
    from fairtriage.extract import KeywordExtractor
    assert not KeywordExtractor().extract(text).essential_service_lost, text
