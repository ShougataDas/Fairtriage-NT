"""End-to-end request loop: the three worked cases, the pause, the resume."""

from fairtriage import service
from fairtriage.schemas import DecisionIn, LodgeIn


def test_case1_misspelled_electrical_is_immediate():
    r = service.lodge(LodgeIn(text="powa plug hot make crack sound", community="Darwin (Ludmilla)"))
    assert r["tier"] == "Immediate"
    assert "powa plug hot make crack sound" in r["explanation_tenant"], "must quote the original"


def test_case2_asks_one_question_then_answer_decides_tier():
    r = service.lodge(LodgeIn(text="toilet is blocked.", community="Maningrida"))
    assert r["status"] == "awaiting_tenant"
    assert "only toilet" in r["question"]
    urgent = service.clarify(r["request_id"], "yes only one")
    assert urgent["tier"] == "Urgent"

    r = service.lodge(LodgeIn(text="toilet is blocked.", community="Maningrida"))
    routine = service.clarify(r["request_id"], "no there is another")
    assert routine["tier"] == "Routine"


def test_clarified_explanation_quotes_the_report_not_the_answer():
    r = service.lodge(LodgeIn(text="toilet is blocked.", community="Wadeye"))
    out = service.clarify(r["request_id"], "yes only one")
    assert "You told us: \u201ctoilet is blocked.\u201d" in out["explanation_tenant"]
    assert "You said: \u201cyes only one\u201d" in out["explanation_tenant"]


def test_unresolved_answer_is_flagged_not_guessed():
    r = service.lodge(LodgeIn(text="toilet is blocked.", community="Wadeye"))
    out = service.clarify(r["request_id"], "dunno")
    assert any(f["code"] == "clarification_unresolved" for f in out["flags"])


def test_case3_buried_hazard_in_remote_community():
    r = service.lodge(LodgeIn(
        text="Just checking if this app works. Also the powerpoint in the kitchen has "
             "been sparking since Tuesday.", community="Wadeye", vulnerability=["elderly"]))
    assert r["tier"] == "Immediate"
    assert r["rank"] == 1


def test_only_one_clarification_round():
    r = service.lodge(LodgeIn(text="help", community="Belyuen"))
    assert r["status"] == "awaiting_tenant"
    out = service.clarify(r["request_id"], "not sure")
    assert out["status"] != "awaiting_tenant", "must not loop forever"


def test_clarify_rejected_when_not_waiting():
    r = service.lodge(LodgeIn(text="the only toilet is blocked", community="Belyuen"))
    import pytest
    with pytest.raises(service.Invalid):
        service.clarify(r["request_id"], "yes")


def test_withdrawal_is_never_auto_closed():
    r = service.lodge(LodgeIn(text="its fine now dont worry about it", community="Galiwinku"))
    assert r["status"] == "awaiting_confirmation"
    assert "We have not closed your repair" in r["explanation_tenant"]


def test_override_requires_reason_and_reaches_tenant():
    import pytest
    r = service.lodge(LodgeIn(text="the only toilet is blocked", community="Belyuen"))
    with pytest.raises(service.Invalid):
        service.decide(r["request_id"], DecisionIn(action="override", to_tier="Routine"))
    out = service.decide(r["request_id"], DecisionIn(
        action="override", to_tier="Immediate", reason="Tenant is on dialysis at home"))
    assert out["tier"] == "Immediate"
    assert "Tenant is on dialysis at home" in out["explanation_tenant"]


def test_downgrading_immediate_needs_second_reviewer():
    import pytest
    r = service.lodge(LodgeIn(text="bare wire showing in the hallway", community="Belyuen"))
    assert r["tier"] == "Immediate"
    with pytest.raises(service.Invalid):
        service.decide(r["request_id"], DecisionIn(
            action="override", to_tier="Routine", reason="looked at photo, looks fine"))
    ok = service.decide(r["request_id"], DecisionIn(
        action="override", to_tier="Routine",
        reason="electrician confirmed isolated, second reviewer: J. Smith"))
    assert ok["tier"] == "Routine"


def test_decisions_are_append_only():
    from fairtriage import db
    r = service.lodge(LodgeIn(text="the only toilet is blocked", community="Belyuen"))
    service.decide(r["request_id"], DecisionIn(action="approve"))
    service.decide(r["request_id"], DecisionIn(action="override", to_tier="Immediate",
                                               reason="water now on the floor"))
    rows = db.history(db.DECISIONS, r["request_id"])
    assert [d["action"] for d in rows] == ["approve", "override"]
    # an override adds a new assessment; the first is kept, never overwritten
    assert len(db.history(db.ASSESSMENTS, r["request_id"])) == 2


def test_tenant_words_are_never_altered_by_household_facts():
    """Regression: a known second toilet was appended to a ROOF report and then
    quoted back to the tenant as if they had written it."""
    r = service.lodge(LodgeIn(text="roof leak on the light", community="Darwin (Malak)",
                              alternative_toilet=True))
    v = service.request_view(r["request_id"])
    assert v["text_original"] == "roof leak on the light"
    assert "toilet" not in r["explanation_tenant"].lower()


def test_household_toilet_fact_still_settles_the_question():
    r = service.lodge(LodgeIn(text="toilet is blocked", community="Wadeye",
                              alternative_toilet=False))
    assert r["status"] != "awaiting_tenant" and r["tier"] == "Urgent"
    assert "You told us: \u201ctoilet is blocked\u201d" in r["explanation_tenant"]


def test_storm_report_end_to_end():
    r = service.lodge(LodgeIn(text="i roof was gone in last night cyclone", community="Wadeye"))
    assert r["tier"] == "Immediate"
    assert "not dangerous" not in r["explanation_tenant"]
