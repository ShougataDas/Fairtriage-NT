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
