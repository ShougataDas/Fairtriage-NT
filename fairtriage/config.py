"""Runtime settings and the policy file."""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="FAIRTRIAGE_",
                                      extra="ignore")

    # MongoDB holds everything: requests, history, trips, crews, the paused
    # clarifying questions. "mongomock://" is an in-memory stand-in for tests.
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "fairtriage"
    policy_path: str = str(ROOT / "config" / "policy.yaml")
    reference_dir: str = str(ROOT / "reference")

    # "keyword" runs fully offline. "openai", "gemini" and "anthropic" each
    # need their own API key (see PROVIDERS below).
    extractor: str = "offline"
    openai_model: str = "gpt-4.1-mini"      # verify current model names
    # flash-lite: free-tier limits are per model, and full flash allows only 20
    # requests a day. Model names change often: ai.google.dev/gemini-api/docs/models
    gemini_model: str = "gemini-3.1-flash-lite"
    anthropic_model: str = "claude-haiku-4-5-20251001"
    # Keys are read from the names everyone expects, or the prefixed form.
    # Previously only FAIRTRIAGE_* names were read, so a key in .env was ignored.
    openai_api_key: str = Field(default="", validation_alias=AliasChoices(
        "OPENAI_API_KEY", "FAIRTRIAGE_OPENAI_API_KEY"))
    gemini_api_key: str = Field(default="", validation_alias=AliasChoices(
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "FAIRTRIAGE_GEMINI_API_KEY"))
    anthropic_api_key: str = Field(default="", validation_alias=AliasChoices(
        "ANTHROPIC_API_KEY", "FAIRTRIAGE_ANTHROPIC_API_KEY"))
    prompt_version: str = "extract-v3.1"
    llm_timeout_s: float = 20.0
    # a tenant never waits longer than this for a model, retries included;
    # after that the keyword rules answer and the job is flagged
    llm_budget_s: float = 12.0
    # after this many failed messages in a row, skip the model for a while
    breaker_failures: int = 3
    breaker_cooldown_s: float = 300.0

    # Text messages to tenants (Twilio). Without all three, texts are composed
    # and logged but not sent ("demo mode"), and the tenant is told so.
    twilio_account_sid: str = Field(default="", validation_alias=AliasChoices(
        "TWILIO_ACCOUNT_SID", "FAIRTRIAGE_TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str = Field(default="", validation_alias=AliasChoices(
        "TWILIO_AUTH_TOKEN", "FAIRTRIAGE_TWILIO_AUTH_TOKEN"))
    twilio_from_number: str = Field(default="", validation_alias=AliasChoices(
        "TWILIO_FROM_NUMBER", "FAIRTRIAGE_TWILIO_FROM_NUMBER"))
    # Sign-in. AUTH_SECRET signs session cookies: set a long random value in
    # production. The first admin is created the first time this username
    # signs in with this password; that admin then adds other staff.
    auth_secret: str = ""
    admin_username: str = "admin"
    admin_password: str = ""

    # where the tenant's tracking link in a text points
    public_web_url: str = "https://fairtriage-nt-web-one.vercel.app"


@lru_cache
def settings() -> Settings:
    return Settings()


@lru_cache
def policy() -> dict:
    with open(settings().policy_path) as fh:
        return yaml.safe_load(fh)


# extractor name -> (settings attribute for the key, for the model, env var to tell the user)
PROVIDERS = {
    "openai": ("openai_api_key", "openai_model", "OPENAI_API_KEY"),
    "gemini": ("gemini_api_key", "gemini_model", "GEMINI_API_KEY"),
    "anthropic": ("anthropic_api_key", "anthropic_model", "ANTHROPIC_API_KEY"),
}


# "<extractor>:<model>" -> error, for providers that failed in a way retrying
# cannot fix (bad model name, bad key, no credit). Cleared on restart.
PROVIDER_DOWN: dict[str, str] = {}
# "<extractor>:<model>" -> (monotonic time the pause ends, last error), for a
# model that failed several messages in a row (busy, timing out).
PROVIDER_COOLDOWN: dict[str, tuple[float, str]] = {}
# "<extractor>:<model>" -> messages failed in a row
FAILURES: dict[str, int] = {}


def reader_status() -> dict:
    """Which extractor is actually reading messages. Shown on screen: a judge
    should never have to guess whether a model is involved."""
    st = settings()
    if st.extractor in PROVIDERS:
        key_attr, model_attr, env = PROVIDERS[st.extractor]
        model = getattr(st, model_attr)
        down = PROVIDER_DOWN.get(f"{st.extractor}:{model}")
        cool = PROVIDER_COOLDOWN.get(f"{st.extractor}:{model}")
        if cool and cool[0] > time.monotonic():
            mins = max(1, round((cool[0] - time.monotonic()) / 60))
            return {"mode": st.extractor, "ok": False,
                    "label": f"Model {model} is busy: keyword rules for the next {mins} min, "
                             f"every job flagged"}
        if down:
            return {"mode": st.extractor, "ok": False,
                    "label": f"Model {model} failed, using keyword rules, every job "
                             f"flagged: {down[:120]}"}
        if getattr(st, key_attr):
            return {"mode": st.extractor, "ok": True,
                    "label": f"Model: {getattr(st, model_attr)} ({st.extractor})"}
        return {"mode": st.extractor, "ok": False,
                "label": f"Model selected but {env} is empty: using keyword rules, every job flagged"}
    return {"mode": "engine", "ok": True, "label": "FairTriage triage engine (offline)"}


def reset_caches() -> None:
    settings.cache_clear()
    PROVIDER_DOWN.clear()
    PROVIDER_COOLDOWN.clear()
    FAILURES.clear()
    policy.cache_clear()
