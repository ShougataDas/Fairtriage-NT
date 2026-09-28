"""The OpenAI path, tested with a fake client standing in for the API.

This checks everything short of the live network call: that the key is read,
that the request is strict-mode JSON schema at temperature 0, that the
response is validated, and that a missing key falls back to keyword rules
and flags the job.
"""

import json

from fairtriage import config
from fairtriage import extract as E


class FakeCompletions:
    def __init__(self, reply, captured):
        self.reply, self.captured = reply, captured

    def create(self, **kw):
        self.captured.update(kw)

        class Msg:
            content = json.dumps(self.reply)

        class Choice:
            message = Msg()

        class Resp:
            choices = [Choice()]
        return Resp()


def fake_openai(reply, captured):
    class FakeClient:
        def __init__(self, api_key=None, timeout=None, **kw):
            captured["api_key"] = api_key
            self.chat = type("C", (), {"completions": FakeCompletions(reply, captured)})()
    return FakeClient


REPLY = {"actionability": "repair", "hazard_domain": "structural", "is_active": True,
         "endangers_person": True, "essential_service_lost": False,
         "habitability": "uninhabitable", "whole_dwelling": True, "tenant_isolated": False,
         "evidence_phrase": "roof was gone", "confidence": "high", "missing_decisive_fact": ""}


def test_key_is_read_from_plain_OPENAI_API_KEY(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    config.reset_caches()
    assert config.settings().openai_api_key == "sk-test-123"
    assert config.reader_status()["mode"] == "engine"       # key alone does not switch it on


def test_request_is_strict_schema_and_response_validates(monkeypatch):
    import openai
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    config.reset_caches()
    captured = {}
    monkeypatch.setattr(openai, "OpenAI", fake_openai(REPLY, captured))
    ex = E.OpenAIExtractor(model="gpt-test").extract("i roof was gone in last night cyclone")
    assert ex.endangers_person and ex.whole_dwelling
    assert captured["api_key"] == "sk-test-123"
    assert captured["temperature"] == 0
    rf = captured["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert "$ref" not in json.dumps(rf["json_schema"]["schema"])
    assert "i roof was gone" in captured["messages"][0]["content"]


def test_missing_key_falls_back_and_flags(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("FAIRTRIAGE_EXTRACTOR", "openai")
    config.reset_caches()
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    r = E.extract("power point is sparking")
    assert r.fallback is True and r.extraction.endangers_person
    assert config.reader_status()["ok"] is False


def test_malformed_model_reply_falls_back(monkeypatch):
    import openai
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("FAIRTRIAGE_EXTRACTOR", "openai")
    config.reset_caches()
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    monkeypatch.setattr(openai, "OpenAI", fake_openai({"nonsense": 1}, {}))
    r = E.extract("the only toilet is blocked")
    assert r.fallback is True


# ---------------------------------------------------------------------------
# Gemini (OpenAI-compatible endpoint) and Claude (forced tool call)
# ---------------------------------------------------------------------------

def fake_openai_with_base(reply, captured):
    class FakeClient:
        def __init__(self, api_key=None, timeout=None, base_url=None, **kw):
            captured.update(api_key=api_key, base_url=base_url, **kw)
            self.chat = type("C", (), {"completions": FakeCompletions(reply, captured)})()
    return FakeClient


def test_gemini_uses_google_endpoint_and_its_own_key(monkeypatch):
    import openai
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    config.reset_caches()
    captured = {}
    monkeypatch.setattr(openai, "OpenAI", fake_openai_with_base(
        {**REPLY, "missing_decisive_fact": "none"}, captured))
    ex = E.GeminiExtractor().extract("i roof was gone in last night cyclone")
    assert ex.endangers_person and ex.missing_decisive_fact.value == ""
    assert captured["api_key"] == "gm-test"
    assert "generativelanguage.googleapis.com" in captured["base_url"]
    assert captured["max_retries"] == 0          # no hidden SDK retries
    assert captured["model"] == config.settings().gemini_model
    enum = captured["response_format"]["json_schema"]["schema"]["properties"][
        "missing_decisive_fact"]["enum"]
    assert "" not in enum and "none" in enum


def fake_anthropic_module(tool_input, captured):
    import types

    class Messages:
        def create(self, **kw):
            captured.update(kw)
            block = types.SimpleNamespace(type="tool_use", input=tool_input)
            return types.SimpleNamespace(content=[block])

    class Anthropic:
        def __init__(self, api_key=None, timeout=None, max_retries=None):
            captured.update(api_key=api_key, max_retries=max_retries)
            self.messages = Messages()

    return types.SimpleNamespace(Anthropic=Anthropic)


def test_anthropic_forces_schema_tool(monkeypatch):
    import sys
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    config.reset_caches()
    captured = {}
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic_module(REPLY, captured))
    ex = E.AnthropicExtractor().extract("i roof was gone in last night cyclone")
    assert ex.endangers_person and ex.whole_dwelling
    assert captured["api_key"] == "sk-ant-test"
    assert captured["tool_choice"] == {"type": "tool", "name": "record_extraction"}
    assert captured["tools"][0]["input_schema"]["additionalProperties"] is False
    assert captured["model"] == config.settings().anthropic_model


def test_provider_selected_by_setting(monkeypatch):
    for name, cls in E.EXTRACTORS.items():
        monkeypatch.setenv("FAIRTRIAGE_EXTRACTOR", name)
        config.reset_caches()
        assert isinstance(E._primary(), cls)
        assert config.reader_status()["ok"] is False     # no key in tests


def test_missing_provider_key_falls_back(monkeypatch):
    monkeypatch.setenv("FAIRTRIAGE_EXTRACTOR", "anthropic")
    config.reset_caches()
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    r = E.extract("power point is sparking")
    assert r.fallback is True and r.extraction.endangers_person


def test_permanent_error_disables_provider_after_first_failure(monkeypatch):
    """A retired model name (404) must not cost two failed calls per message."""
    calls = []

    class NotFound(Exception):
        status_code = 404

    class Retired:
        name, model = "gemini", "gemini-old"

        def extract(self, text):
            calls.append(text)
            raise NotFound("model is no longer available")

    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    first = E.extract("power point is sparking", primary=Retired())
    second = E.extract("the only toilet is blocked", primary=Retired())
    assert first.fallback and second.fallback
    assert second.extraction.essential_service_lost      # still read, by the rules
    assert len(calls) == 1


def test_timeout_is_retried(monkeypatch):
    calls = []

    class Flaky:
        name, model = "gemini", "gemini-flaky"

        def extract(self, text):
            calls.append(text)
            raise TimeoutError("slow")

    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    E.extract("power point is sparking", primary=Flaky())
    E.extract("the only toilet is blocked", primary=Flaky())
    assert len(calls) == 2 * (E.RETRIES + 1)


def test_busy_model_is_skipped_after_repeated_failures(monkeypatch):
    """After three busy failures in a row, tenants are answered by the rules at
    once, without a call to the model, and staff can see why."""
    calls = []

    class Busy(Exception):
        status_code = 503

    class Overloaded:
        name, model = "gemini", config.settings().gemini_model

        def extract(self, text):
            calls.append(text)
            raise Busy("high demand")

    monkeypatch.setenv("FAIRTRIAGE_EXTRACTOR", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    config.reset_caches()
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    for i in range(config.settings().breaker_failures):
        assert E.extract(f"power point sparking {i}", primary=Overloaded()).fallback
    n = len(calls)
    r = E.extract("the only toilet is blocked", primary=Overloaded())
    assert r.fallback and r.extraction.essential_service_lost
    assert len(calls) == n                      # the model was not called
    status = config.reader_status()
    assert status["ok"] is False and "busy" in status["label"]


def test_time_budget_caps_retries(monkeypatch):
    calls = []

    class Slow:
        name, model = "gemini", "gemini-slow"

        def extract(self, text):
            calls.append(text)
            raise TimeoutError("slow")

    monkeypatch.setenv("FAIRTRIAGE_LLM_BUDGET_S", "0.1")
    config.reset_caches()
    E.extract("power point is sparking", primary=Slow())
    assert len(calls) == 1                      # no time left to retry
