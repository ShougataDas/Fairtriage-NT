from fairtriage import service
from fairtriage.explain import verify
from fairtriage.schemas import LodgeIn


def facts_for(text, community="Wadeye"):
    r = service.lodge(LodgeIn(text=text, community=community))
    if r["status"] == "awaiting_tenant":
        r = service.clarify(r["request_id"], "yes")
    return service.request_view(r["request_id"])["assessment"]


def test_every_template_passes_its_own_verifier():
    for t in ["power point is sparking", "the only toilet is blocked",
              "kitchen cupboard door came off the hinge", "There is no gas smell.",
              "its fine now dont worry about it", "i need help"]:
        a = facts_for(t)
        assert verify(a["explanation_tenant"], a["facts"]) == [], t


def test_verifier_catches_invented_numbers_and_promises():
    a = facts_for("the only toilet is blocked")
    bad = a["explanation_tenant"] + "\nSorry! A plumber will definitely arrive within 37 hours."
    problems = verify(bad, a["facts"])
    assert any("37" in p for p in problems)
    assert any("sorry" in p for p in problems)
    assert any("definitely" in p for p in problems)


def test_tenant_is_told_what_did_not_count():
    a = facts_for("the only toilet is blocked", "Maningrida")
    assert "Where you live was not used to decide your position." in a["explanation_tenant"]


def test_digits_in_the_reference_id_are_not_permitted_claims():
    """Regression: the verifier harvested digits from the random ID suffix, so
    an invented '37 hours' passed whenever the suffix contained 37."""
    a = facts_for("the only toilet is blocked")
    f = dict(a["facts"])
    f["request_id"] = "NTF3-00001-37ab"
    text = a["explanation_tenant"].replace(a["facts"]["request_id"], f["request_id"])
    assert verify(text, f) == []                              # the ID itself is fine
    assert any("37" in p for p in verify(text + " Within 37 hours.", f))


def test_tenants_own_words_are_not_checked_as_our_promises():
    """Regression: a tenant who wrote "as soon as possible" tripped the check
    that stops US promising it, flagging a correct explanation as failed."""
    from fairtriage import service
    from fairtriage.schemas import LodgeIn
    r = service.lodge(LodgeIn(text="the kitchen tap is leaking, please fix it as soon as possible, sorry",
                              community="Darwin (Parap)"))
    assert not any(f["code"] == "explanation_check_failed" for f in r["flags"])
    from fairtriage.explain import verify
    facts = {"request_id": "NTF3-00001-abcd", "tier": "Routine"}
    assert verify("We will fix it as soon as possible. Routine. NTF3-00001-abcd", facts)  # ours: still caught
