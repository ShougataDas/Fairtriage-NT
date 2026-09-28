"""Every test gets its own database and checkpoint store."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # an in-memory MongoDB, fresh for every test. To run the same tests against
    # a real server: FAIRTRIAGE_TEST_MONGO_URL=mongodb://localhost:27017
    real = os.environ.get("FAIRTRIAGE_TEST_MONGO_URL")
    monkeypatch.setenv("FAIRTRIAGE_MONGO_URL", real or "mongomock://")
    monkeypatch.setenv("FAIRTRIAGE_MONGO_DB", f"test_{tmp_path.name}"[:60])
    monkeypatch.setenv("FAIRTRIAGE_EXTRACTOR", "keyword")
    from fairtriage import config, db, graph, reference
    # Never read the developer's .env or real keys: a test must not reach a
    # live API, spend credit, or depend on the network.
    monkeypatch.setitem(config.Settings.model_config, "env_file", None)
    for var in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    config.reset_caches()
    reference.reset()
    db.reset_engine()
    graph.reset()
    yield
    graph.reset()
    if real:
        db.drop_all()            # leave nothing behind on a real server
    db.reset_engine()
