"""Queue position. Rank depends on tier, need and lodgement time — nothing else.

darwin_rank is computed by the same function with location removed. It is
always equal to rank, and that equality is the point: it demonstrates in the
data, not in a claim, that where someone lives does not move their position.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import db
from .policy import TIER_ORDER, sort_key
from .reference import communities
from .schemas import Extraction

OPEN_STATUSES = ("ranked", "approved")


@dataclass
class OpenJob:
    request_id: str
    tier: str
    need: float
    lodged_at: str
    community: str
    trade_region: str
    key: tuple
    trade: str = "Handyperson"
    hours: float = 1.0


def job_trade(req: dict) -> tuple[str, float]:
    """The trade a request needs and roughly how many on-site hours it takes."""
    if not req.get("extraction"):
        return "Handyperson", 1.0
    ex = Extraction.model_validate(req["extraction"])
    return (ex.trade or "Handyperson"), (ex.job_hours or 1.0)


def open_jobs(exclude: str | None = None) -> list[OpenJob]:
    jobs = []
    for req in db.open_requests():
        if req["_id"] == exclude:
            continue
        a, comm = req["assessment"], req["dwelling"]["community"]
        trade, hours = job_trade(req)
        jobs.append(OpenJob(req["_id"], a["tier"], a["need_score"], req["lodged_at"], comm,
                            communities()[comm].trade_region,
                            sort_key(a["tier"], a["need_score"], req["lodged_at"]),
                            trade, hours))
    return jobs


@dataclass
class Position:
    rank: int
    tier_size: int
    darwin_rank: int
    jobs_ahead_region: int
    jobs_ahead_darwin: int
    jobs_ahead_trade: int = 0       # same trade, same region: the ones that delay this job
    hours_ahead: float = 0.0        # their on-site hours
    hours_ahead_darwin: float = 0.0  # the same, for the identical job in Darwin


def position(request_id: str, tier: str, need: float, lodged_at: str,
             community: str, trade: str = "Handyperson",
             jobs: list[OpenJob] | None = None) -> Position | None:
    """`jobs`: the open jobs, when the caller has already loaded them (the
    queue screen computes every row's position from one load)."""
    if tier == "NotInQueue":
        return None
    me = sort_key(tier, need, lodged_at)
    jobs = (open_jobs(exclude=request_id) if jobs is None
            else [j for j in jobs if j.request_id != request_id])
    same_tier = [j for j in jobs if j.tier == tier]
    rank = sum(1 for j in same_tier if j.key < me) + 1

    # location-free recomputation. Identical by construction; kept separate so
    # the equality is demonstrated rather than asserted.
    darwin_rank = sum(1 for j in same_tier if (TIER_ORDER[j.tier], -j.need, j.lodged_at) < me) + 1

    region = communities()[community].trade_region
    ahead = [j for j in jobs if j.key < me]
    mine = [j for j in ahead if j.trade_region == region and j.trade == trade]
    return Position(
        rank=rank, tier_size=len(same_tier) + 1, darwin_rank=darwin_rank,
        jobs_ahead_region=sum(1 for j in ahead if j.trade_region == region),
        jobs_ahead_darwin=sum(1 for j in ahead if j.trade_region == "Darwin"),
        jobs_ahead_trade=len(mine),
        hours_ahead=sum(j.hours for j in mine),
        hours_ahead_darwin=sum(j.hours for j in ahead
                               if j.trade_region == "Darwin" and j.trade == trade),
    )
