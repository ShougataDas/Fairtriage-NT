"""The extraction contract.

One Pydantic model drives three things: the JSON schema sent to the LLM in
strict mode, validation of what comes back, and the columns written to the
database. Change a field here and all three move together.

Every field is something a person could verify by reading the tenant's
message. Nothing here is a priority, a score or a judgement about the
tenant. Those are computed later, by arithmetic.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Actionability(str, Enum):
    REPAIR = "repair"
    NO_ISSUE = "no_issue"
    QUESTION = "question"
    FOLLOW_UP = "follow_up"
    WITHDRAWAL = "withdrawal"
    OUT_OF_SCOPE = "out_of_scope"
    UNCLEAR = "unclear"


class HazardDomain(str, Enum):
    ELECTRICAL = "electrical"
    WATER = "water"
    SANITATION = "sanitation"
    SECURITY = "security"
    CLIMATE = "climate"
    GAS = "gas"
    ESSENTIAL = "essential"
    STRUCTURAL = "structural"
    PEST = "pest"
    MINOR = "minor"
    NONE = "none"


class Habitability(str, Enum):
    UNINHABITABLE = "uninhabitable"
    SEVERELY_IMPAIRED = "severely_impaired"
    IMPAIRED = "impaired"
    COSMETIC = "cosmetic"
    NONE = "none"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DecisiveFact(str, Enum):
    NONE = ""
    ONLY_TOILET = "only_toilet"
    WHOLE_DWELLING = "whole_dwelling"
    NEAR_ELECTRICS = "near_electrics"
    CAN_SECURE = "can_secure"
    COOKING_POSSIBLE = "cooking_possible"
    INDOORS = "indoors"


NOT_IN_QUEUE = {Actionability.NO_ISSUE, Actionability.QUESTION,
                Actionability.OUT_OF_SCOPE, Actionability.WITHDRAWAL,
                Actionability.UNCLEAR}

TRADE_FOR_DOMAIN = {
    HazardDomain.ELECTRICAL: "Electrician",
    HazardDomain.WATER: "Plumber",
    HazardDomain.SANITATION: "Plumber",
    HazardDomain.SECURITY: "Locksmith",
    HazardDomain.CLIMATE: "Electrician",
    HazardDomain.GAS: "Gas Fitter",
    HazardDomain.ESSENTIAL: "Plumber",
    HazardDomain.STRUCTURAL: "Builder",
    HazardDomain.PEST: "Pest Control",
    HazardDomain.MINOR: "Handyperson",
    HazardDomain.NONE: "",
}

JOB_HOURS_FOR_DOMAIN = {
    HazardDomain.ELECTRICAL: 2.0, HazardDomain.WATER: 2.0,
    HazardDomain.SANITATION: 2.0, HazardDomain.SECURITY: 1.0,
    HazardDomain.CLIMATE: 1.5, HazardDomain.GAS: 2.0,
    HazardDomain.ESSENTIAL: 2.5, HazardDomain.STRUCTURAL: 4.0,
    HazardDomain.PEST: 1.5, HazardDomain.MINOR: 1.0, HazardDomain.NONE: 0.0,
}


class Extraction(BaseModel):
    """What the model is allowed to tell us about a message."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    actionability: Actionability
    hazard_domain: HazardDomain
    is_active: bool
    endangers_person: bool = Field(
        description="Physical harm or major damage is possible TODAY: sparking, "
                    "exposed wire, burning smell, water reaching electrics, gas smell, "
                    "sewage indoors, uncontrolled flooding or major water loss, a house "
                    "that cannot be locked. Mirrors NT immediate-repair guidance. Not "
                    "'annoying', not 'waited a long time'.")
    essential_service_lost: bool = Field(
        description="No water, no power, no usable toilet, no way to cook, no "
                    "hot water, or no working smoke alarm.")
    habitability: Habitability
    whole_dwelling: bool = Field(
        default=False,
        description="The whole household is exposed to the harm: flooded, roof gone, "
                    "no power or water to the house, or a gas leak. False for one "
                    "fixture or one room, and false for a door or lock problem.")
    emergency_000: bool = Field(
        default=False,
        description="Life is at risk right now: fire, flames, an explosion, someone "
                    "electrocuted, injured, unconscious or not breathing. The tenant "
                    "must be told to call 000. Hedged wording still counts: 'perhaps "
                    "the gas is on fire' is an emergency.")
    person_hurt: bool = Field(
        default=False,
        description="Someone has been or may have been hurt (a fall, bleeding, a knock "
                    "to the head). The tenant is told to call 000 for an ambulance and "
                    "staff phone them. It does NOT make the repair more urgent: rank the "
                    "repair on the house's own facts.")
    tenant_isolated: bool = Field(
        default=False,
        description="The tenant SAYS they have already made it safe: power switched "
                    "off at the meter box, gas turned off at the bottle, water off at "
                    "the mains. Never assumed. False unless the message says so.")
    evidence_phrase: str = Field(
        description="The tenant's own words that justify this, copied VERBATIM.")
    confidence: Confidence
    missing_decisive_fact: DecisiveFact = Field(
        description="The ONE absent fact that would change the outcome, or empty.")

    @property
    def in_queue(self) -> bool:
        return self.actionability not in NOT_IN_QUEUE

    @property
    def trade(self) -> str:
        return TRADE_FOR_DOMAIN[self.hazard_domain]

    @property
    def job_hours(self) -> float:
        return JOB_HOURS_FOR_DOMAIN[self.hazard_domain]


def openai_strict_schema() -> dict:
    """JSON schema in the shape OpenAI strict mode accepts.

    Strict mode rejects `$ref`, `default` and optional properties, and the
    schema Pydantic generates uses all three. So: inline every $ref, drop
    defaults, and list every property as required, recursively.
    """
    import copy
    raw = Extraction.model_json_schema()
    defs = raw.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
                extra = {k: v for k, v in node.items() if k != "$ref"}
                target.update(extra)
                node = target
            node = {k: resolve(v) for k, v in node.items()
                    if k not in ("default", "title")}
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}).keys())
            return node
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(raw)


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------

class LodgeIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    community: str
    # street address inside the community: where the crew goes. Never used in
    # ranking; never quoted in the verified explanation (house numbers are not
    # facts about the repair).
    address: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=30)
    vulnerability: list[str] = Field(default_factory=list)
    alternative_toilet: Optional[bool] = None


class ClarifyIn(BaseModel):
    answer: str = Field(min_length=1, max_length=500)


class TripChangeIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=400)
    request_id: Optional[str] = None
    actor: str = "coordinator-demo"


class DecisionIn(BaseModel):
    action: str = Field(pattern="^(approve|override|request_info)$")
    to_tier: Optional[str] = None
    reason: Optional[str] = None
    actor: str = "coordinator-demo"
