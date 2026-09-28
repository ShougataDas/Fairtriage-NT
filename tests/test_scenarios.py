"""The 15 scenario cases as tests. See tests/scenarios.py and TEST_CASES.md."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from scenarios import SCENARIOS  # noqa: E402


@pytest.mark.parametrize("sc", SCENARIOS, ids=[f"{s['id']:02d}-{s['group']}" for s in SCENARIOS])
def test_scenario(sc):
    from run_scenarios import run_case
    r = run_case(sc)
    assert not r["problems"], r["problems"]


@pytest.mark.parametrize("a,b", [
    ("smoke is coming from the fridge socket", "fridge power socket make smoke yesterday"),
    ("the kettle cord is burning", "burning smell from the kettle cord"),
])
def test_word_order_does_not_change_the_reading(a, b):
    """Regression for scenario 9: device-first word order was missed."""
    from fairtriage.extract import KeywordExtractor
    k = KeywordExtractor()
    assert k.extract(a).endangers_person == k.extract(b).endangers_person is True


@pytest.mark.parametrize("text", [
    "socket has no sparks, no heat and is working normally",
    "the fridge socket is not smoking any more",
    "only one socket is dead and there is no smell, heat or flashing",
])
def test_negation_inside_a_match_cancels_it(text):
    """Regression: 'socket ... sparks' matched as one span with the 'no' inside
    it, and the negation check only looked before and after. Precision fell
    from 0.926 to 0.853 before this was caught by the evaluation."""
    from fairtriage.extract import KeywordExtractor
    assert not KeywordExtractor().extract(text).endangers_person, text
