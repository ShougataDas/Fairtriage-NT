"""Golden cases for the keyword extractor, which is also the offline fallback
and the evaluation baseline."""

import pytest

from fairtriage.extract import KeywordExtractor

K = KeywordExtractor()

CASES = [
    # text, actionability, danger, essential, missing
    ("powa plug hot make crack sound", "repair", True, False, ""),
    ("The socket gets very hot and makes a crackling sound when I use it.", "repair", True, False, ""),
    ("toilet is blocked.", "repair", False, False, "only_toilet"),
    ("the only toilet is blocked", "repair", False, True, ""),
    ("There is no gas smell.", "no_issue", False, False, ""),
    ("my home is looks fine.", "no_issue", False, False, ""),
    ("the gas leak was fixed last week", "no_issue", False, False, ""),
    ("i need help", "unclear", False, False, ""),
    ("its fine now dont worry about it", "withdrawal", False, False, ""),
    ("how long does a repair usually take?", "question", False, False, ""),
    ("still waiting on that job from last month", "follow_up", False, False, ""),
    ("my neighbours dog keeps getting in", "out_of_scope", False, False, ""),
    ("no water coming out of the taps", "repair", False, True, ""),
    ("cant lock the front door", "repair", True, False, ""),
    ("water dripping through the ceiling near the light", "repair", True, False, ""),
    ("kitchen cupboard door came off the hinge", "repair", False, False, ""),
    ("the gas leak was fixed but the tap drips", "repair", False, False, ""),
]


@pytest.mark.parametrize("text,act,danger,essential,missing", CASES)
def test_golden(text, act, danger, essential, missing):
    e = K.extract(text)
    assert e.actionability.value == act
    assert e.endangers_person is danger
    assert e.essential_service_lost is essential
    assert e.missing_decisive_fact.value == missing


BURIED = [
    "Just checking if this app works. Also the powerpoint in the kitchen has been sparking since Tuesday.",
    "hi, no problem with the house really. one thing, there is bare wire showing near the back door.",
    "all good here thanks. the only thing is sewage is coming up inside the laundry.",
    "Following up on the fence job from last month. Separately, I can smell gas near the stove.",
    "quick question about rent. also water is running down the wall onto the power point.",
]


@pytest.mark.parametrize("text", BURIED)
def test_buried_hazard_is_never_dismissed(text):
    """The dangerous failure: small talk hiding a live hazard."""
    e = K.extract(text)
    assert e.actionability.value == "repair", text
    assert e.endangers_person, text


def test_understatement_is_still_a_repair():
    e = K.extract("The home is fine, just the back room floods a bit when it rains")
    assert e.actionability.value == "repair"


def test_evidence_is_verbatim_from_the_message():
    msg = "Just checking if this app works. Also the powerpoint in the kitchen has been sparking since Tuesday."
    assert K.extract(msg).evidence_phrase in msg


DENIALS = [
    "there is no water leak anymore",
    "no water on the floor now",
    "the door is fine and locks ok",
    "we can lock the door fine",
    "the water is not coming in any more, roof is fixed",
    "There is no gas smell.",
]


@pytest.mark.parametrize("text", DENIALS)
def test_a_problem_described_as_gone_is_not_queued(text):
    """Regression: making negated faults count ('no water', 'cannot lock') must
    not turn 'no water leak anymore' into a lost water supply."""
    e = K.extract(text)
    assert e.actionability.value == "no_issue", text
    assert not e.essential_service_lost and not e.endangers_person, text


def test_negation_scope_stops_at_a_comma():
    e = K.extract("no water damage, just a dripping tap")
    assert e.actionability.value == "repair" and e.hazard_domain.value == "water"
    assert not e.essential_service_lost


@pytest.mark.parametrize("text", [
    "water is not come from tap since morning",     # second-language grammar
    "no water coming out of the taps",
    "There has been no water supply to the dwelling since this morning.",
])
def test_water_loss_detected_in_every_register(text):
    assert K.extract(text).essential_service_lost, text


@pytest.mark.parametrize("text", [
    "cant lock door", "the front door will not lock",
    "front door not locking, we cannot lock proper",
    "The external front door cannot be locked.",
])
def test_unsecurable_house_is_danger_in_every_register(text):
    assert K.extract(text).endangers_person, text


@pytest.mark.parametrize("text,domain", [
    ("ceiling fan in the bedroom is not working", "climate"),
    ("lights not working in the kitchen", "electrical"),
    ("water dripping from the ceiling", "water"),
    ("the tap in the kitchen is dripping", "water"),
    ("front windows wont close", "security"),
])
def test_right_trade_is_sent(text, domain):
    """Regression: 'ceiling' alone sent a plumber to a fan, 'lights' missed the
    electrician. A wrong domain means the wrong trade on the wrong trip."""
    assert K.extract(text).hazard_domain.value == domain
