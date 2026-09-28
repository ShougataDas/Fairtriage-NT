"""Persistence, in MongoDB.

One document per repair request, holding the tenant's details and the CURRENT
assessment, so the queue is one query. Every assessment, reading and human
decision is also written to its own collection and never updated: an audit
trail that can be edited is not an audit trail.

    requests          one per report: text, dwelling, status, current assessment
    assessments       append-only history of every assessment
    extractions       append-only: every reading of every message
    decisions         append-only: every human decision
    trips             approved trips
    teams             where each region's crews are
    extraction_cache  readings by (rules fingerprint, reader, text)
    counters          sequence numbers for readable request ids

FAIRTRIAGE_MONGO_URL selects the server (default mongodb://localhost:27017).
"mongomock://" runs an in-memory stand-in, used by the tests.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from .config import settings

REQUESTS, ASSESSMENTS, EXTRACTIONS, DECISIONS = "requests", "assessments", "extractions", "decisions"
TRIPS, TEAMS, CACHE, COUNTERS = "trips", "teams", "extraction_cache", "counters"

OPEN_STATUSES = ("ranked", "approved")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_client = None
_db = None


def client():
    global _client
    if _client is None:
        url = settings().mongo_url
        if url.startswith("mongomock"):
            import mongomock
            _client = mongomock.MongoClient()
        else:
            from pymongo import MongoClient
            _client = MongoClient(url, serverSelectionTimeoutMS=5000, tz_aware=False)
    return _client


def db():
    global _db
    if _db is None:
        _db = client()[settings().mongo_db]
        _indexes(_db)
    return _db


def col(name: str):
    return db()[name]


def _indexes(d) -> None:
    d[REQUESTS].create_index([("status", ASCENDING)])
    d[REQUESTS].create_index([("dwelling.community", ASCENDING)])
    d[REQUESTS].create_index([("lodged_at", ASCENDING)])
    for name in (ASSESSMENTS, EXTRACTIONS, DECISIONS):
        d[name].create_index([("request_id", ASCENDING), ("seq", ASCENDING)])
    d[TRIPS].create_index([("created_at", DESCENDING)])


def next_seq(name: str) -> int:
    """Atomic counter: request numbers stay unique however many servers run."""
    doc = col(COUNTERS).find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    return int(doc["seq"])


def append(name: str, doc: dict) -> dict:
    """Insert into an append-only collection, with an ordering number."""
    doc = {**doc, "seq": next_seq(name), "created_at": doc.get("created_at") or now()}
    col(name).insert_one(doc)
    return doc


def history(name: str, request_id: str) -> list[dict]:
    return list(col(name).find({"request_id": request_id}, {"_id": 0}).sort("seq", ASCENDING))


def get_request(request_id: str) -> dict | None:
    return col(REQUESTS).find_one({"_id": request_id})


def update_request(request_id: str, fields: dict, inc: dict | None = None) -> None:
    op = {}
    if fields:
        op["$set"] = fields
    if inc:
        op["$inc"] = inc
    if not op:
        return
    col(REQUESTS).update_one({"_id": request_id}, op)


def open_requests() -> list[dict]:
    """Ranked or approved requests with a current, in-queue assessment."""
    return list(col(REQUESTS).find({
        "status": {"$in": list(OPEN_STATUSES)},
        "assessment": {"$ne": None},
        "assessment.tier": {"$ne": "NotInQueue"},
    }))


def ping() -> bool:
    try:
        client().admin.command("ping")
        return True
    except Exception:
        return False


def drop_all() -> None:
    """Delete every FairTriage collection. Used by the demo seed.

    Drops collections one by one rather than the database: a MongoDB Atlas
    user with read/write rights may drop collections but not databases."""
    d = client()[settings().mongo_db]
    for name in d.list_collection_names():
        if not name.startswith("system."):
            d.drop_collection(name)
    reset_engine()


def reset_engine() -> None:
    global _client, _db
    if _client is not None and not settings().mongo_url.startswith("mongomock"):
        _client.close()
    _client, _db = None, None
