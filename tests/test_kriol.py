"""Kriol reports are ranked like the same report in English.

Found in a live test: "powa bin finish la ola haus, mela nomo gat lait" was
asked a vague question, and a sparking wire written in Kriol was not queued.
"""

import pytest

from fairtriage import service
from fairtriage.normalise import normalise
from fairtriage.schemas import LodgeIn


@pytest.mark.parametrize("kriol,english", [
    ("powa bin finish la ola haus", "power has gone la whole house"),
    ("mela nomo gat lait", "we no light"),
    ("dor im brok, mela kaan lok im", "door is broken, we cannot lock im"),
    ("wata im kam ap la flowa", "water im coming up la floor"),
])
def test_kriol_is_normalised(kriol, english):
    assert normalise(kriol)[0] == english


def test_english_words_are_not_changed():
    text = "i cut my lip on the broken window, can you fix it"
    assert normalise(text)[0] == text


@pytest.mark.parametrize("text,tier", [
    ("powa bin finish la ola haus, mela nomo gat lait, pridj im stop", "Urgent"),
    ("det lektrik wiya im spakin la kitchen wol, mela frait", "Immediate"),
    ("dor im brok, mela kaan lok im", "Immediate"),
    ("no more water come out tap, water bin finish", "Urgent"),
    ("windo im krak lilbit", "Routine"),
])
def test_kriol_reports_are_ranked_without_a_vague_question(text, tier):
    r = service.lodge(LodgeIn(text=text, community="Numbulwar", phone="0412345678"))
    assert r["status"] == "ranked", (text, r.get("question"))
    assert r["tier"] == tier, text


def test_kriol_only_toilet_is_asked_then_urgent():
    r = service.lodge(LodgeIn(text="toilet im blok, wata im kam ap la floor",
                              community="Numbulwar", phone="0412345678"))
    assert r["question"] == "Is this the only toilet in the house?"
    assert service.clarify(r["request_id"], "yes")["tier"] == "Urgent"
