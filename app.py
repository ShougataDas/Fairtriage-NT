"""Entrypoint for hosts that look for `app` in ./app.py (Vercel's FastAPI preset).

Run locally with: python -m uvicorn fairtriage.api:app --reload --port 8000
"""

from fairtriage.api import app  # noqa: F401
