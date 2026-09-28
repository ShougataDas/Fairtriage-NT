"""If the model is down, the system degrades to keyword rules and says so."""

from fairtriage import extract as E


class Broken:
    name = "openai"
    model = "gpt-test"

    def extract(self, text):
        raise TimeoutError("api unreachable")


def test_failed_model_falls_back_and_is_flagged(monkeypatch):
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    r = E.extract("power point is sparking", primary=Broken())
    assert r.fallback is True
    assert r.extraction.endangers_person


def test_cache_makes_repeat_readings_identical():
    first = E.extract("the only toilet is blocked")
    second = E.extract("the only toilet is blocked")
    assert second.cache_hit and second.extraction == first.extraction


def test_a_rule_change_invalidates_cached_readings(monkeypatch):
    """Regression: the cache key ignored the rules, so a message read under old
    rules kept its old reading after the rules were fixed."""
    text = "fridge power socket make smoke yesterday, we scared to use"
    first = E.extract(text)
    assert E.extract(text).cache_hit                          # same code: cached
    monkeypatch.setattr(E, "_FINGERPRINT", "rules-were-edited")
    again = E.extract(text)
    assert not again.cache_hit                                 # new code: re-read
    assert again.extraction == first.extraction
