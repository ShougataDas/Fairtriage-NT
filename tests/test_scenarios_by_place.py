"""31 scenarios across every section and 20 places, run end to end through
lodge -> (one question) -> rank -> tenant message. Waits are checked as a
shape (hours vs days, trip wait for remote routine), since their size moves
with the queue; tiers and outcomes are exact."""

import pytest

from fairtriage import service
from fairtriage.schemas import LodgeIn

# (no, place, message, answer if asked, tier, wait shape)
#   wait shape: "hours" | "days" | "trip" (remote routine, waits for a trip) | None
CASES = [
    (1, "Darwin (Nightcliff)", "the power point in the kitchen is sparking when I plug the kettle in", None, "Immediate", "hours"),
    (2, "Katherine", "there are bare wires hanging out of the wall in the hallway", None, "Immediate", "hours"),
    (3, "Humpty Doo", "no power to the whole house since last night, the fridge is off", None, "Urgent", "days"),
    (4, "Galiwinku", "one light in the bedroom does not work, the rest are fine", None, "Routine", "trip"),
    (5, "Wadeye", "water is dripping from the ceiling onto the light switch", None, "Immediate", "hours"),
    (6, "Palmerston (Gray)", "a pipe burst under the sink and water is spraying everywhere, I cannot turn it off", None, "Immediate", "hours"),
    (7, "Batchelor", "the kitchen tap is dripping all the time", None, "Routine", "days"),
    (8, "Maningrida", "no water coming out of any tap in the house", None, "Urgent", "days"),
    (9, "Darwin (Karama)", "the only toilet is blocked and will not flush", None, "Urgent", "days"),
    (10, "Numbulwar", "sewage is coming up through the shower drain into the bathroom", None, "Immediate", "hours"),
    (11, "Pine Creek", "no hot water for three days, only cold showers", None, "Urgent", "days"),
    (12, "Darwin (Malak)", "I can smell gas near the stove", None, "Immediate", "hours"),
    (13, "Coolalinga", "the front door lock is broken and I cannot lock the house", None, "Immediate", "hours"),
    (14, "Wurrumiyanga", "the bedroom window latch is loose", None, "Routine", "trip"),
    (15, "Belyuen", "the cyclone blew part of the roof off and rain is coming into the lounge", None, "Immediate", "hours"),
    (16, "Darwin (Casuarina)", "there is a small hairline crack in the bathroom wall", None, "Routine", "days"),
    (17, "Katherine", "the air conditioner stopped working and my mum is elderly with a heart condition", None, "Routine", "days"),
    (18, "Palmerston", "the ceiling fan in the spare room wobbles", None, "Routine", "days"),
    (19, "Wadeye", "there are cockroaches in the kitchen cupboards", None, "Routine", "trip"),
    (20, "Darwin (Parap)", "the kitchen cupboard door came off the hinge", None, "Routine", "days"),
    (21, "Gunbalanya", "the fly screen on the back door has a big rip", None, "Routine", "trip"),
    # fire: "call 000" and a phone call replace the wait line
    (22, "Darwin (Ludmilla)", "there is smoke and flames coming from the power board", None, "Immediate", None),
    (23, "Katherine", "my neighbour is outside with a knife threatening us", None, "NotInQueue", None),
    # a floor someone fell through will hurt the next person: made safe first
    (24, "Palmerston (Zuccoli)", "my son fell through the rotten floorboards and cut his leg", None, "Immediate", "hours"),
    (25, "Maningrida", "toilet broke no flush water everywhere floor", "yes", "Urgent", "days"),
    (26, "Darwin (Nightcliff)", "the elecrtic socket is smokin and smell burnin", None, "Immediate", "hours"),
    # the answer says what and where: it must be ranked, not sent to a phone call
    (27, "Humpty Doo", "something is wrong in the bathroom", "the shower drain is blocked and water stays in the shower", "Routine", "days"),
    # an outside door that will not close cannot be secured: NT immediate-repair guidance
    (28, "Batchelor", "Hi, I would like to submit a maintenance request for an issue that needs checking",
     "the back door will not close properly", "Immediate", "hours"),
    (29, "Darwin (Parap)", "thanks, the tap was fixed last week, all good now", None, "NotInQueue", None),
    (30, "Katherine", "how do I check where my repair is up to?", None, "NotInQueue", None),
    (31, "Palmerston", "please cancel my request, I fixed it myself", None, "NotInQueue", None),
]


def run(place, text, answer):
    r = service.lodge(LodgeIn(text=text, community=place))
    if r["status"] == "awaiting_tenant":
        assert answer, f"asked an unexpected question: {r['question']}"
        r = service.clarify(r["request_id"], answer)
    return r


@pytest.mark.parametrize("no, place, text, answer, tier, shape", CASES, ids=[f"#{c[0]}" for c in CASES])
def test_scenario(no, place, text, answer, tier, shape):
    r = run(place, text, answer)
    assert r["tier"] == tier, (no, r["tier"], r.get("status"))
    # the wait line: first, unless a "call 000" line rightly comes before it
    first = next((l for l in r["explanation_tenant"].splitlines() if l.startswith("Expect")), "")
    if shape == "hours":
        assert "hour" in first, (no, first)
    elif shape == "days":
        assert "day" in first and r["wait"]["breakdown"]["trip_wait_days"] is None, (no, first)
    elif shape == "trip":
        assert r["wait"]["breakdown"]["trip_wait_days"] is not None, (no, first)
    assert not any(f["code"] == "explanation_check_failed" for f in r["flags"]), no


def test_fire_and_violence_say_000_first():
    for place, text in [("Darwin (Ludmilla)", "there is smoke and flames coming from the power board"),
                        ("Katherine", "my neighbour is outside with a knife threatening us")]:
        r = run(place, text, None)
        assert "000" in r["explanation_tenant"].splitlines()[0], text
    r = run("Katherine", "my neighbour is outside with a knife threatening us", None)
    assert r["status"] == "needs_phone_call"


def test_someone_hurt_is_flagged_for_a_phone_call():
    r = run("Palmerston (Zuccoli)", "my son fell through the rotten floorboards and cut his leg", None)
    assert any(f["code"] == "person_hurt" for f in r["flags"])


@pytest.mark.parametrize("text, status", [
    ("thanks, the tap was fixed last week, all good now", "not_in_queue"),
    ("how do I check where my repair is up to?", "not_in_queue"),
    ("please cancel my request, I fixed it myself", "awaiting_confirmation"),
])
def test_non_repairs(text, status):
    assert run("Palmerston", text, None)["status"] == status
