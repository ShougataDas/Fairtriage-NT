"""Option 1: separating jobs inside the Immediate tier."""

from fairtriage import service
from fairtriage.extract import KeywordExtractor
from fairtriage.schemas import LodgeIn

K = KeywordExtractor()


def test_flooded_house_outranks_a_lock_that_will_not_catch():
    """Both Immediate, neither vulnerable. The lock was reported FIRST, and
    before v4 it would have stayed ahead on arrival time alone."""
    lock = service.lodge(LodgeIn(text="the lock does not hold on the front door",
                                 community="Darwin (Parap)"), lodged_at="2026-09-01T00:00:00+00:00")
    flood = service.lodge(LodgeIn(text="my house is flooded last night",
                                  community="Darwin (Parap)"), lodged_at="2026-09-02T00:00:00+00:00")
    assert lock["tier"] == flood["tier"] == "Immediate"
    v_lock = service.request_view(lock["request_id"])["assessment"]["need"]
    v_flood = service.request_view(flood["request_id"])["assessment"]["need"]
    assert v_flood > v_lock


def test_hazard_the_tenant_has_made_safe_ranks_below_a_live_one():
    live = service.lodge(LodgeIn(text="power point is sparking in the kitchen", community="Wadeye"))
    safe = service.lodge(LodgeIn(text="power point was sparking so i switched it off at the meter box",
                                 community="Wadeye"))
    assert live["tier"] == safe["tier"] == "Immediate"
    n_live = service.request_view(live["request_id"])["assessment"]["need"]
    n_safe = service.request_view(safe["request_id"])["assessment"]["need"]
    assert n_live > n_safe


def test_isolation_is_never_assumed():
    assert not K.extract("power point is sparking").tenant_isolated
    assert not K.extract("strong gas smell around the stove").tenant_isolated


def test_isolation_is_read_when_stated():
    assert K.extract("gas smell so we turned the gas off at the bottle").tenant_isolated
    assert K.extract("the power is off at the switchboard now, socket was smoking").tenant_isolated


def test_extent_whole_house_vs_one_room():
    assert K.extract("no power to the whole house").whole_dwelling
    assert K.extract("i roof was gone in last night cyclone").whole_dwelling
    assert not K.extract("no power in the kitchen").whole_dwelling
    assert not K.extract("power point is sparking in the laundry").whole_dwelling


def test_make_safe_advice_given_only_when_not_already_safe():
    live = service.lodge(LodgeIn(text="power point is sparking", community="Belyuen"))
    assert "switch the power off at the meter box" in live["explanation_tenant"]
    safe = service.lodge(LodgeIn(text="socket sparked so i switched it off at the meter box",
                                 community="Belyuen"))
    assert "Thank you for making it safe" in safe["explanation_tenant"]
    assert "switch the power off" not in safe["explanation_tenant"]


def test_advice_passes_the_verifier():
    from fairtriage.explain import verify
    r = service.lodge(LodgeIn(text="strong gas smell around the stove", community="Wadeye"))
    a = service.request_view(r["request_id"])["assessment"]
    assert verify(a["explanation_tenant"], a["facts"]) == []


def test_gas_is_whole_house_exposure_and_outranks_a_lock():
    """Regression: gas scored as a one-fixture fault and ranked below a lock."""
    assert K.extract("strong gas smell around the stove").whole_dwelling
    lock = service.lodge(LodgeIn(text="the lock does not hold", community="Darwin (Parap)"),
                         lodged_at="2026-09-01T00:00:00+00:00")
    gas = service.lodge(LodgeIn(text="strong gas smell around the stove", community="Darwin (Parap)"),
                        lodged_at="2026-09-02T00:00:00+00:00")
    n = lambda r: service.request_view(r["request_id"])["assessment"]["need"]
    assert n(gas) > n(lock)


def test_a_lock_is_not_whole_house_extent():
    assert not K.extract("the lock does not hold").whole_dwelling
    assert not K.extract("main entry door has come off and the house is open").whole_dwelling
