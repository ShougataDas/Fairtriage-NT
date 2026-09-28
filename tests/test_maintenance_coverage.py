"""Coverage across maintenance scenarios, one message per situation.

Written to find gaps, not to confirm existing rules: every category a public
housing maintenance line in the Top End hears, in plain, hurried and
second-language wording. The expected tier follows NT immediate-repair
guidance (anything that can hurt someone today, or leaves the house open)
and the policy ladder (essential service lost -> Urgent, otherwise Routine).

A case marked `ask` must stop for the one clarifying question rather than be
ranked on a guess.
"""

import pytest

from fairtriage.extract import KeywordExtractor
from fairtriage.normalise import normalise, reconcile
from fairtriage.policy import tier_of

K = KeywordExtractor()

IMMEDIATE = [
    # electrical
    "power point is sparking",
    "the switchboard is buzzing and smells like burning",
    "wires hanging out of the ceiling where the light was",
    "got a tingle off the kitchen tap, i think its electric",
    "my son got a small shock from the fridge door",
    "lights keep flickering and there is a burning smell",
    "water leaking into the light fitting in the bathroom",
    "the hot water system is sparking at the bottom",
    "power point melted and is black around the edges",
    "extension lead socket smoking",
    # gas
    "strong gas smell in the kitchen",
    "gas bottle outside is hissing",
    "the heater gives off fumes and we get headaches",
    # water
    "burst pipe under the house, water is gushing and wont stop",
    "water pouring through the ceiling into the lounge",
    # sewage
    "sewage coming up through the shower drain",
    "toilet overflowing with poo all over the floor",
    "septic tank is overflowing into the yard where kids play",
    # structure and storm
    "roof blew off in the storm",
    "a tree fell on the house and smashed the roof",
    "ceiling is sagging and cracking, looks like it will fall",
    "part of the ceiling fell down in the bedroom",
    "the verandah is falling down",
    "floor boards gave way in the hallway",
    "front steps collapsed, nobody can get in safely",
    "balcony railing is loose and wobbly, kids lean on it",
    "rain coming in the roof onto the bed",
    "house flooded after the rain last night",
    # security
    "back door won't lock",
    "someone smashed the front window and we cannot lock the house",
    "window glass is broken and there is sharp glass everywhere",
    "front door kicked in and wont close",
    # hazardous materials
    "the old fibro wall is cracked and broken, might be asbestos",
    # second-language and hurried
    "powa point make spark and smoke",
    "gas smell strong inside house",
    "door broke cant lock it",
    "roof water come inside kids room onto light",
    "wata coming out everywhere from pipe cant stop",
    "toilet flood poo water in bathroom",
]

URGENT = [
    "no water in the house",
    "bore pump stopped working, we have no water",
    "the water tank is empty and nothing comes out of the taps",
    "no power to the whole house",
    "no hot water since friday",
    "hot water system is broken",
    "stove not working, cant cook anything",
    "none of the burners work",
    "the only toilet is blocked",
    "smoke alarm is not working",
    "smoke alarm keeps beeping even with a new battery",
    "we are locked out, the key broke in the lock",
    # second-language
    "no wata for house",
    "hot water no working",
    "stove no work cant cook",
    "toilet broke, only one toilet",
]

ROUTINE = [
    "the tap in the kitchen is dripping",
    "kitchen cupboard door came off the hinge",
    "flyscreen on the bedroom window has a big hole",
    "cracked tile in the bathroom",
    "hole in the bedroom wall",
    "paint is peeling off the walls",
    "black mould on the bathroom ceiling",
    "termites in the door frame",
    "cockroaches everywhere in the kitchen",
    "the front gate is broken",
    "back fence is leaning",
    "gutters are blocked with leaves",
    "one light in the bedroom does not work",
    "ceiling fan is not working",
    "aircon is not cooling",
    "air conditioner is making a loud noise",
    "washing machine tap is leaking",
    "toilet keeps running after flushing",
    "kitchen sink is slow to drain",
    "shower head is broken",
    "oven light is broken",
    "one burner on the stove does not heat",
    "fridge is not cold",
    "clothesline is broken",
    "garden tap is leaking",
    "security screen door is torn",
    "window latch is broken but the window still closes",
    "low water pressure in the shower",
    "toilet seat is broken",
    "towel rail fell off the wall",
    "curtain rod fell down",
    "crack in the wall in the lounge",
    "possums in the roof at night",
    "tv antenna is broken",
    # second-language
    "tap bin leak long time",
    "fridge not cold no more",
    "light no work in kitchen",
    "fan broke in bedroom",
]

ASK = [
    "the toilet wont flush",          # only toilet?
    "something wrong with the shower",
    "the house has a problem",
]


def read(text):
    """The production reading: original and spelling-corrected text, reconciled."""
    a = K.extract(text)
    norm, _ = normalise(text)
    return a if norm == text else reconcile(a, K.extract(norm))[0]


def _tier(text):
    return tier_of(read(text))[0]


@pytest.mark.parametrize("text", IMMEDIATE)
def test_immediate(text):
    assert _tier(text) == "Immediate", text


@pytest.mark.parametrize("text", URGENT)
def test_urgent(text):
    assert _tier(text) == "Urgent", text


@pytest.mark.parametrize("text", ROUTINE)
def test_routine(text):
    e = read(text)
    assert tier_of(e)[0] == "Routine", text
    assert e.in_queue and e.trade, f"{text}: a repair with no trade cannot be scheduled"


@pytest.mark.parametrize("text", ASK)
def test_asks_rather_than_guesses(text):
    from fairtriage.schemas import Actionability, DecisiveFact
    e = read(text)
    assert e.actionability == Actionability.UNCLEAR or e.missing_decisive_fact != DecisiveFact.NONE, text


def test_every_repair_gets_a_trade():
    for text in IMMEDIATE + URGENT + ROUTINE:
        e = read(text)
        if e.in_queue:
            assert e.trade, f"{text}: no trade"
