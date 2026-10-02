"""Extraction: free text -> observable facts. The only place a model reads.

Three pieces:

  KeywordExtractor  Deterministic rules. Runs offline, so the demo cannot die
                    on dead wifi. Also the evaluation baseline: if the LLM
                    cannot beat this on human-labelled data, report that.

  OpenAIExtractor   Strict JSON schema at decode time, temperature 0. Strict
                    mode is what stops malformed JSON the night before.
  GeminiExtractor   The same, through Google's OpenAI-compatible endpoint.
  AnthropicExtractor  Claude, with the schema as a forced tool call.

  extract()         Cache -> primary -> one retry -> keyword fallback.
                    Every fallback result is FLAGGED for human review. A
                    degraded reading that is silently trusted is worse than
                    an outage.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass

import structlog

from .config import FAILURES, PROVIDER_COOLDOWN, PROVIDER_DOWN, PROVIDERS, settings
from . import db
from .db import CACHE, now
from .schemas import (
    Actionability, Confidence, DecisiveFact, Extraction, Habitability,
    HazardDomain, openai_strict_schema,
)

log = structlog.get_logger()


@dataclass
class ExtractResult:
    extraction: Extraction
    extractor: str
    model: str | None
    cache_hit: bool
    fallback: bool


# ---------------------------------------------------------------------------
# Keyword extractor
# ---------------------------------------------------------------------------

NEGATORS = r"(?:no|not|isn'?t|aren'?t|never|without|nothing|none)"
RESOLVED = (r"(?:was fixed|got fixed|been fixed|already fixed|fixed now|fixed last|is fixed|"
            r"(?:was|were|been|got|is|are|already|have|has|had) repaired|repaired (?:now|already|last)|"
            r"anymore|any more|no longer|stopped now|all fixed)")

# (pattern, domain, endangers_person, essential_service_lost)
DANGER_RULES = [
    (r"\bgas\b.{0,30}\b(smell|leak|hiss)|\b(smell|smells)\b.{0,15}\bgas\b"
     r"|\brotten[- ]egg\b"
     r"|\b(smell\w*|odou?r)\b.{0,50}\b(like|of) gas\b|\bgas[- ]?like (smell|odou?r)\b"
     r"|\b(gas|fuel|lpg)\b.{0,20}\b(odou?r|fumes?|stink\w*|whiff)\b"
     r"|\b(odou?r|fumes?|stink\w*|smell\w*)\b.{0,20}\b(gas|fuel|lpg)\b"
     r"|\bhiss\w*\b.{0,20}\b(gas|cylinder|bottle)\b|\b(gas|cylinder)\b.{0,20}\bhiss\w*"
     # fumes from a burning appliance: carbon monoxide risk
     r"|\b(heater|stove|oven|cooker|hot water( system| unit)?|fireplace)\b.{0,40}\b(fumes?|carbon monoxide)\b"
     r"|\b(fumes?|carbon monoxide)\b.{0,40}\b(heater|stove|oven|cooker|headaches?|dizzy)\b", "gas", False),
    # NT guidance lists MAJOR WATER LOSS as immediate, alongside electrical,
    # gas and sewer overflow. Uncontrolled flooding is danger, not a drip.
    (r"\b(burst|broken)\b.{0,25}\b(pipe|line|main)\b.{0,40}\b(flood\w*|pour\w*|rush\w*|spray\w*)"
     r"|\bflooding (the house|two rooms|the (whole )?house|rooms|everywhere)\b"
     r"|\b(pouring|rushing|gushing|spraying) (water )?(inside|into|across|from)\b"
     r"|\bwater\b.{0,20}\b(pouring|rushing|gushing)\b"
     r"|\b(leak|water)\b.{0,20}\b(will not|won'?t|cannot|can'?t) (stop|be stopped|turn off)\b"
     r"|\bcannot stop it\b|\brunning quickly across\b"
     r"|\b(water|pipe|tap|leak)\b.{0,40}\b(cannot|can'?t|won'?t|will not) (stop|be stopped|turn (it )?off)\b"
     r"|\b(spreading|flowing|running) (through|across|all over) the (house|floor|rooms?)\b"
     r"|\bflowing (continuously|non[- ]?stop|and will not stop)\b"
     r"|\bpipe\b.{0,15}\b(split|burst|broke)\b.{0,40}\b(flow\w*|pour\w*|gush\w*|spray\w*)", "water", False),
    (r"\bspark(s|ing|ed)?\b|\bsparkin\b", "electrical", False),
    (r"\b(bare|exposed|loose|hanging|dangling)\b.{0,20}\b(wir(e|es|ing)|cables?|leads?)\b"
     r"|\b(wir(e|es|ing)|cables?)\b.{0,25}\b(exposed|showing|hanging|bare|dangling|sticking out)\b", "electrical", False),
    (r"\b(burning|smoke)\b.{0,40}\b(smell|switch|wall|socket|plug|power)|\bsmoke smell\b", "electrical", False),
    # device FIRST, symptom after: "socket make smoke" must read the same as
    # "smoke from the socket". Second-language word order is common.
    (r"\b(socket|plug|power ?point|outlet|switch|switch ?board|fuse ?box|meter ?box|breaker|cord|lead)\b"
     r".{0,40}\b(hot|crackl\w*|crack|pop(ping)?|buzz\w*|melt\w*|flash\w*|scorch\w*|smok\w*|burning|spark\w*)\b",
     "electrical", False),
    # Appliances that are MEANT to get hot: only abnormal symptoms count. "hot"
    # and "burn" are excluded, or "water heater not giving hot water" and "one
    # burner does not heat" would read as fires.
    (r"\b(appliance|fridge|freezer|heater|kettle|stove|oven|cooktop|microwave|washing machine|dryer)\b"
     r".{0,40}\b(smok\w*|spark\w*|melt\w*|scorch\w*|burning (smell|plastic)|on fire|flames?|shock\w*)\b",
     "electrical", False),
    (r"\b(hot|crackl\w*|pop(ping)?)\b.{0,30}\b(socket|plug|power ?point|outlet)\b", "electrical", False),
    (r"\bshock\b", "electrical", False),
    # a tingle from a tap, sink or appliance is current leaking to earth
    (r"\b(tingle|tingling|tingly|zapped|zaps?)\b"
     r"|\bsmell\w* (like |of )?burn\w*|\bburn\w* (plastic )?smell\b", "electrical", False),
    # Storm, cyclone and structural damage. In the Top End this is the core
    # make-safe event: a house open to the weather or with part of it down.
    (r"\b(house|home|place|unit|flat|rooms?|bedrooms?|floor)\b.{0,15}\b(is|was|got|has been|are|were) (flooded|under water|underwater)\b"
     r"|\b(flooded|flood) (house|home|inside|rooms?)\b"
     r"|\b(house|home|unit|flat)\s+(flooded|flooding)\b"
     r"|\broof\b.{0,30}\b(gone|blown (off|away)|blew (off|away)|torn (off|away)|ripped (off|away)|came off|collapsed|caved in|missing|removed|lifted)\b"
     r"|\b(removed|ripped|tore|torn|blew|blown|lifted)\b.{0,30}\b(sheets?|panels?|iron|tin)\b.{0,20}\b(from|off) the roof\b"
     r"|\b(sheets?|panels?)\b.{0,20}\b(off|missing from|gone from) the roof\b"
     r"|\b(tree|branch|limb|palm)\b.{0,30}\b(fell|fallen|came down|landed|crashed|smashed|went)\b.{0,20}\b(on|onto|into|through)\b"
     r"|\b(smashed|crashed|came|went) (through|into) the (roof|ceiling|wall|window)\b"
     r"|\b(ceiling|wall|roof|verandah|veranda|awning)\b.{0,20}\b(collapsed|caved in|fell (in|down)|falling (in|down)|came down)\b"
     r"|\b(cyclone|storm|winds?)\b.{0,60}\b(damag\w*|removed|ripped|tore|torn|blown|destroy\w*|smashed)\b.{0,30}\b(roof|house|wall|windows?|ceiling)\b"
     r"|\brain\b.{0,20}\b(coming|entering|getting|pouring|pours) (in|into|inside)\b.{0,30}\b(bed|bedrooms?|rooms?|house|lounge|living)"
     r"|\b(ceiling|roof|wall)\b.{0,20}\b(sagging|sags|bowing|bulging|dropping)\b"
     r"|\b(will|going to|about to|might|could|gonna)\s+(fall|collapse|come down|cave in)\b"
     r"|\b(floor ?boards?|floor|deck|decking)\b.{0,20}\b(gave way|give way|giving way|collapsed|fell through|broke through|caved in)\b",
     "structural", False),
    # falls: steps, stairs, ramps, balconies, and the rails that stop people falling
    (r"\b(steps?|stairs?|staircase|ramp|balcony|verandah|veranda|deck)\b.{0,25}"
     r"\b(collapsed|broken|broke|gave way|falling (down|apart)|rotten|missing|caved in|unsafe)\b"
     r"|\b(railings?|handrails?|balustrades?|banisters?)\b.{0,30}\b(loose|wobbl\w*|broken|broke|fell|falling|missing|came off|gave way|unsafe)\b",
     "structural", False),
    # asbestos: damaged fibro releases fibres
    (r"\basbestos\b|\bfibro\b.{0,30}\b(broken|cracked|damaged|smashed|hole|crumbling)\b", "structural", False),
    (r"\binsulation\b.{0,30}\b(split|cracked|damaged|worn|melted|broken|missing|peeled)\b"
     r"|\b(metal|copper|live (parts?|wires?))\b.{0,20}\b(can be seen|showing|visible|exposed|sticking out)\b",
     "electrical", False),
    (r"\b(water|leak\w*|drip\w*|wet|rain)\b.{0,40}\b(on|near|onto|into|around|beside|over|through) (the |a )?(light\w*|power ?points?|sockets?|switch\w*|fittings?|meter box|fuse ?box|electric\w*)\b"
     r"|\bwater\b.{0,60}\b(light|power ?point|socket|switch|electric\w*|wir\w*)\b"
     r"|\b(light|power ?point|socket|switch)\b.{0,60}\bwater\b", "electrical", False),
    (r"\bsewage\b.{0,40}\b(inside|in the|coming up|into|laundry|bathroom|kitchen|floor)\b"
     r"|\bsewer water\b.{0,30}\binside\b"
     r"|\b(waste|dirty) (water )?\b.{0,30}\b(coming up|rising|onto the floor|into the (room|house))\b"
     r"|\boverflowing\b.{0,30}\b(into|onto|across) the (room|floor|house)\b"
     r"|\bcoming up (through|out of) the (drain|shower|toilet)\b"
     r"|\b(backing|backed|bubbling) up\b.{0,30}\b(drain|floor|toilet|shower|sink)\b"
     r"|\b(waste|sewage|dirty) (water )?\b.{0,15}\b(backing|backed|bubbling) up\b"
     r"|\b(poo|poop|faeces|feces|human waste|sewerage)\b.{0,40}\b(floor|everywhere|inside|bathroom|overflow\w*|flood\w*|coming up|yard)\b"
     r"|\btoilet\b.{0,20}\b(overflow\w*|flood\w*)\b"
     r"|\bseptic( tank)?\b.{0,30}\b(overflow\w*|leak\w*|full|backing up|bubbling|spilling)\b", "sanitation", False),
    (r"\b(can ?not|cant|can't|unable to|won'?t|will not|doesn'?t|does not)\b.{0,12}\block(ed|ing)?\b"
     r"|\bnot\s+lock(ing|s|ed)?\b"
     r"|\bcannot be secured\b|\bno way to (secure|lock)\b|\bhouse is open\b"
     r"|\banyone can (enter|get in|walk in|come in)\b"
     r"|\b(front|back|external|main|outside)\b.{0,20}\b(lock|door ?frame|frame)\b.{0,15}\b(broken|broke|busted|smashed|kicked in)\b"
     r"|\block\b.{0,20}\b(does not|doesn'?t|won'?t) (hold|catch|engage)\b"
     r"|\b(door|lock)\b.{0,15}\bhas come off\b|\bdoor\b.{0,20}\bwill not shut\b"
     r"|\block\b.{0,20}\b(broken|not working|won'?t work)\b.{0,30}\b(front|back|external)\b"
     r"|\b(front|back|main|external|outside|entry|side|laundry)\s+door\b.{0,25}\b(won'?t|will not|cannot|can'?t|does not|doesn'?t)\s+(close|shut)\b"
     r"|\bkicked in\b",
     "security", True),
    # broken glass cuts, and a broken pane leaves the house open
    (r"\b(smashed|shattered)\b.{0,20}\b(glass|window|door)\b|\b(glass|window)\b.{0,20}\b(smashed|shattered)\b"
     r"|\bbroken glass\b|\bsharp glass\b|\bglass\b.{0,20}\beverywhere\b"
     r"|\bwindow glass\b.{0,15}\bbroken\b", "security", False),
]

ESSENTIAL_RULES = [
    # second-language forms matter here: "water is not come" must score the
    # same as "no water coming out". Tested by test_paraphrase_invariance.
    # "no water in the ceiling" is not lost supply; "no water in the house" is
    (r"\bno (running )?water\b(?!\s+(leak\w*|damage|on\b|drip\w*|coming in|stain\w*|in (the )?(ceiling|roof|wall|floor)))"
     r"|\bno water supply\b"
     r"|\bwater\b.{0,15}\b(stopped|(is|has|gone|are|been) (off|dry))\b"
     r"|\bwater\b.{0,25}\bnot\s+(come|comes|coming|working|running|there)\b(?!\s+in\b)"
     r"|\b(all (the )?taps|the taps|taps) (are|run|have run|have gone|went) dry\b"
     r"|\btaps?\b.{0,20}\b(nothing comes? out|no water comes? out)\b"
     r"|\bnothing comes? out of the taps?\b"
     # remote communities: bore and rainwater tank supply
     r"|\b(water )?tank\b.{0,20}\b(empty|dry|run out|ran out)\b"
     r"|\bbore( pump)?\b.{0,30}\b(broken|broke|stopped|not working|dead|failed|no good)\b", "essential", True),
    (r"\bwhole house is affected\b", "essential", True),
    # A power cut, however it is said. "power" never means a power POINT,
    # board, cord or bill here: one dead socket is Routine.
    (r"\bno (power|electricity|electrics|electric|lights at all)\b"
     r"|\bpower\b(?!\s*(points?|sockets?|outlets?|boards?|cords?|leads?|plugs?|bills?|cards?))"
     r".{0,25}\b(out|off|cut|gone|down|dead|not working|not back|failed|stopped|going off|keeps going off)\b"
     r"|\belectricity\b.{0,25}\b(out|off|cut|gone|down|dead|not working|stopped|failed)\b"
     r"|\b(black ?out|power outage|outage|power cut|power failure)\b"
     r"|\b(house|home|unit|place|flat)\b.{0,15}\b(is |has gone |went |gone |all )?dark\b"
     r"|\bwhole house\b.{0,20}\bpower\b"
     r"|\b(safety switch|main switch|breaker|circuit breaker|rcd|trip switch)\b.{0,30}"
     r"\b(trip\w*|keeps? (going|turning) off|won'?t (reset|stay on)|will not (reset|stay on))\b"
     r"|\beverything (electrical|electric)\b.{0,20}\b(stopped|off|not working|dead)\b", "electrical", True),
    (r"\bno hot water\b|\bhot water\b.{0,20}\b(not working|no working|not work|no work|broken|broke|stopped|cold|dead|failed|gone)\b"
     r"|\bonly cold water\b|\bcold (water|showers?) only\b|\bshowers? (only )?(runs?|is|are) (only )?cold\b"
     r"|\b(hot water (system|unit|service|tank)|water heater|hws)\b.{0,25}"
     r"\b(not heating|not hot|broken|broke|not working|dead|stopped|failed|gone cold)\b", "essential", True),
    # a working smoke alarm is a legal minimum: without one a fire goes unnoticed
    (r"\bsmoke (alarms?|detectors?)\b.{0,40}\b(not working|doesn'?t work|does not work|no work\w*|broken|broke|beep\w*|chirp\w*|"
     r"keeps? going off|won'?t stop|missing|fell|dead|removed|no power|faulty)\b"
     r"|\bno smoke (alarm|detector)\b", "electrical", True),
    (r"\b(can ?not|cant|can't|unable to)\b.{0,10}\bcook\b|\bnone of the (stove|burners)\b"
     r"|\bwhole stove\b|\bnothing to cook (with|on)\b", "essential", True),
    # "only toilet", in either word order
    (r"\b(only|one|sole|single)\s+toilet\b|\btoilet\b.{0,30}\b(only one|one only|just one)\b"
     r"|\b(only one|one only|just one)\b.{0,20}\btoilet\b"
     r"|\bonly toilet in the house\b", "sanitation", False),
]

FAULT_RULES = [
    # pests first: "termites in the door frame" needs pest control, not a locksmith
    (r"\b(cockroach\w*|roach(es)?|termites?|white ants|ants|rats?|mice|mouse|possums?|bats|pests?|"
     r"bed ?bugs|fleas|wasps?|bees|vermin)\b", "pest"),
    (r"\bcupboard|\bflyscreen|\bhandle|\bhinge|\bdrawer|\bfly ?screen", "minor"),
    (r"\b(towel|curtain|shower) (rail|rod)s?\b|\bblinds?\b|\bshel(f|ves)\b|\bmirror\b|\bhooks?\b"
     r"|\btiles?\b|\bgrout\b|\bpaint\w*|\bplaster\b|\bcarpet\b|\blino\b|\bskirting\b"
     r"|\bhole\b.{0,20}\b(wall|door|floor)\b|\b(wall|door)\b.{0,20}\bhole\b"
     r"|\bmou?ld\w*\b|\bmildew\b"
     r"|\bfenc\w*|\bclothes ?line\b|\bletter ?box\b|\bcarport\b|\bshed\b|\bgutters?\b|\bantenna\b"
     r"|\b(hairline |small |thin )?cracks?\b|\bmesh\b|\b(window |security )?screens?\b.{0,20}\b(rip\w*|torn|hole|broken)\b", "minor"),
    (r"\btoilet\b", "sanitation"), (r"\bsewage|sewer\b", "sanitation"),
    (r"\bblocked\b", "sanitation"),
    # climate before water: "ceiling fan" is a fan, not a roof leak
    (r"\baircon|\bair ?con\w*|\bair conditioner|\bfans?\b|\bcooling\b", "climate"),
    (r"\bleak\w*|\bdrip\w*|\bflood\w*|\bburst\b|\bpipe\b|\btaps?\b|\bwater\b"
     r"|\bsinks?\b|\bdrains?\b|\bbasin\b|\btrough\b|\bshower\b", "water"),
    # a ceiling is only a water fault when something wet is happening to it
    (r"\broof\b|\bceiling\b.{0,30}\b(wet|leak\w*|drip\w*|water|stain\w*|mould|mold|damp|soak\w*)\b"
     r"|\brain\w*\b.{0,25}\b(coming|getting|pouring|leaking) (in|into|through)\b|\bdamp patch\b", "water"),
    (r"\bpower|\bsockets?\b|\boutlets?\b|\bplugs?\b|\blights?\b|\bswitch\w*|\belectric", "electrical"),
    # provided appliances
    (r"\b(fridge|freezer|washing machine|dryer|dishwasher|microwave|range ?hood|exhaust fan|smoke alarm)\b", "electrical"),
    (r"\blocks?\b|\bdoors?\b|\bwindows?\b|\bgate\b", "security"),
    (r"\bstove|\boven|\bburner|\bcook", "essential"),
    (r"\bcrack\w*\b.{0,15}\bwall\b|\bwall\b.{0,15}\bcrack", "structural"),
    (r"\bbroken|not working|won'?t work|doesn'?t work|stopped working|broke", "minor"),
]

FAILURE = (r"\b(broke\w*|won'?t|can'?t|cannot|stuck|leak\w*|drip\w*|block\w*|crack\w*|rip|ripped|torn|soak\w*|damp|"
           r"loose|fell|off|damaged|missing|jammed|torn|smash\w*|burst|stopped|dead|"
           r"flood\w*|hot|spark\w*)\b")
FAIL_PHRASES = (r"\b(not|isn'?t|aren'?t) (working|turning|closing|opening|flushing|draining|"
                r"heating|cooling|locking|running)\b|\b(does not|doesn'?t|won'?t|will not) "
                r"(work|turn|close|open|flush|drain|heat|cool|lock|start)\b|\bstopped working\b"
                r"|\b(does|do|did) nothing\b")
WORKING = (r"\b(fine|ok|okay|good|works|working|locks ok|can lock|normally|properly|"
           r"as normal|as usual|completely dry|all dry|no problems?)\b"
           r"|\bold\b.{0,15}\b(mark|stain|patch)\b|\b(mark|stain|patch)\b.{0,20}\b(old|dry)\b")
# The tenant signals they cannot say what is wrong. Without danger, this is a
# report to clarify, not a job to rank.
SEVERE = (r"\b(soaking|soaked|drenched|pouring|gushing)\b"
          r"|\b(large|big|heavy|major|bad)\b.{0,15}\b(leak\w*|drip\w*)\b"
          r"|\bleaking (heavily|badly|a lot)\b|\bwater everywhere\b"
          r"|\bcannot (use|sleep in|stay in) the\b"
          r"|\b(roof|ceiling)\b.{0,40}\bleak\w*.{0,60}\brain\w*|\brain\w*.{0,60}\b(roof|ceiling)\b.{0,40}\bleak\w*"
          r"|\blocked out\b|\b(can ?not|can'?t) get (in|inside|into the house)\b"
          r"|\bkey\b.{0,15}\b(broke|snapped|stuck)\b.{0,15}\block\b")
WHOLE_DWELLING = (r"\b(whole|entire|all the|every) (house|home|place|unit|rooms?)\b"
                  r"|\b(house|home|place)\b.{0,15}\b(is|was|got) (flooded|under water|dark)\b"
                  r"|\broof\b.{0,30}\b(gone|blown|torn|ripped|came off|collapsed|missing|removed|lifted)\b"
                  r"|\b(sheets?|panels?|iron|tin)\b.{0,30}\b(from|off) the roof\b"
                  r"|\bno (power|water|electricity)\b(?!.{0,15}\b(in|to) the (kitchen|bathroom|laundry|bedroom)\b)"
                  r"|\bflooding (the house|two rooms|rooms|everywhere)\b|\bspreading through the house\b")
# Extent means how much of the HOUSEHOLD is exposed to the harm, not where the
# fault sits. A gas leak starts at one stove but exposes everyone inside, so it
# counts as whole-house. An insecure door is serious, but is not added here:
# ranking a lock against live electrics is a values call, not an observation.
# The tenant says they have ALREADY made it safe. Never inferred.
ISOLATED = (r"\b(switched|turned|shut|flicked) (it |the power |the gas |the water |everything )?"
            r"(off|down)\b.{0,30}\b(at the |the )?(meter|meter ?box|switch ?board|fuse ?box|breaker|"
            r"mains?|bottle|cylinder|tap|valve)\b"
            r"|\b(power|gas|water|breaker|mains?)\b.{0,20}\b(is|are|has been|now) (off|switched off|turned off|isolated)\b"
            r"|\b(isolated|tripped) (it|the (power|circuit))\b")
# Life at risk NOW. Not a maintenance job: the answer is "call 000". Runs
# before everything else, and hedging never cancels it: "perhaps the gas is on
# fire" is an emergency. Fire equipment and fire alarms are excluded.
# Bare "flame", "alight" and "fire" are NOT enough: a stove flame is normal, a
# pilot light "stays alight", a heater "fires up". They only count with context.
EMERGENCY = (r"\b(on fire|caught fire|catch(es|ing)? (on )?fire|in flames|blaze|house fire|kitchen fire)\b"
             r"|\bflames?\b.{0,20}\b(coming|shooting|out of|everywhere|spreading|up the|in the (wall|roof|ceiling|house|kitchen|meter))\b"
             r"|\b(big|huge|tall|high) flames?\b"
             r"|\b(gas|stove|oven|heater|meter ?box|switch ?board|wall|roof|house|kitchen)\b.{0,20}"
             r"\b(burning up|exploded|explosion|went up)\b"
             r"|\b(fire|explosion)\b.{0,20}\b(in|inside|at|from|near) the (house|kitchen|bedroom|laundry|wall|roof|meter|stove)\b"
             r"|\b(exploded|explosion|blew up)\b"
             r"|\b(electrocuted|unconscious|not breathing|can'?t breathe|collapsed on)\b"
             r"|\b(got|had|took) a (bad |big |nasty )?(electric )?shock\b"
             r"|\bbadly (hurt|burnt|burned|cut|injured)\b")
# Danger to a PERSON that no tradesperson can fix: violence, weapons, threats,
# self-harm. Not a repair, so it never enters the repair queue or a trip; the
# tenant is told to call 000 first and staff see it at the top of the phone
# list. A weapon only counts with a person acting on it: "the knife drawer is
# broken" is a cupboard, "termites attacking the frame" is pests.
PERSONAL_DANGER = (
    r"\b(has|have|had|holding|holds|held|with|pulled|pulling|waving|carrying|got|grabbed)\s+(a\s+|an\s+|the\s+)?"
    r"(knife|knives|machete|gun|rifle|shotgun|pistol|weapon|axe|tomahawk|spear|crowbar|broken bottle)\b"
    r"|\b(knife|machete|gun|rifle|weapon|axe)\s+(in|at)\s+(his|her|their|my|your|our)\s+(hands?|throat|neck|head)\b"
    r"|\bpoint(ing|ed)\s+(a\s+)?(gun|knife|weapon)\b"
    r"|\b(stabb(ed|ing)|got stabbed|been shot|shot (him|her|them|me|someone))\b"
    r"|\b(hitting|bashing|punching|kicking|beating|choking|strangling|attacking|assaulting|hurting)\s+"
    r"(me|him|her|them|us|my|his|their|someone|somebody|each other)\b"
    r"|\b(bashed|beaten|beat up|attacked|assaulted|hit|punched)\s+(me|him|her|them|us|my|someone|somebody)\b"
    r"|\bthreat\w*\s+to\s+(kill|hurt|stab|bash|shoot|burn)\b|\b(going|gonna|wants?)\s+to\s+(kill|stab|shoot)\b"
    r"|\bdomestic violence\b|\bfamily violence\b|\b(being|been|getting)\s+(attacked|assaulted|bashed|beaten)\b"
    r"|\bsomeone\b.{0,20}\b(broke|breaking|forcing) (in|into the house)\b.{0,30}\b(now|still here|inside)\b"
)
SELF_HARM = (r"\b(kill(ing)? myself|end(ing)? my life|suicid\w*|want(s)? to die|hurt(ing)? myself|"
             r"harm(ing)? myself|take my (own )?life)\b")

# Someone has been hurt, or may have been: a fall from height, bleeding, a
# knock to the head. The tenant is told to call 000 for an ambulance, and the
# rest of the message is still read as a repair ("he fell off the roof, and now
# the roof leaks" is an injury AND a leak), so neither is lost.
INJURY = (
    r"\b(fell|fall|falls|fallen|falling|slipped|slip)\s+(off|from|through|down)\s+(the\s+|a\s+|our\s+)?"
    r"(roof|ladder|balcony|verandah|veranda|stairs?|steps|deck|tree|window|ceiling)\b"
    r"|\b(fell|fallen)\b.{0,40}\b(hurt|bleeding|injured|knocked out|broke (his|her|their|my) \w+|can'?t (move|get up|walk))\b"
    r"|\b(is|are|was|keeps?)\s+(bleeding|unconscious|not moving|knocked out)\b"
    r"|\bhit (his|her|their|my) head\b|\bbroke (his|her|their|my) (leg|arm|back|neck|hip|wrist|ankle)\b"
)

# Tenants rarely say "power cut": they list what stopped. Lights failing
# together with something else, or "nothing / none / all / everything" being
# off, is the house losing power. One light, or one socket, is not.
ELEC_ITEMS = (r"\b(lights?|fans?|fridges?|freezers?|tv|television|aircon|air ?con\w*|"
              r"power ?points?|sockets?|kettles?|microwaves?|washing machine|oven|stove|cooktop)\b")
OUTAGE = (r"\b(nothing|none|all|everything)\b.{0,40}\b(running|working|works|work|on|off|out|stopped|dead)\b"
          r"|\b(not|no|nothing) (work\w*|running|turn\w* on|comes? on|coming on)\b"
          r"|\b(stopped|dead|went out|gone off|won'?t (turn|come) on|cant turn on|can'?t turn on|all off|is off|are off)\b")
QUANTIFIER = r"\b(nothing|none of|all|everything)\b"


def _power_lost(low: str) -> bool:
    # "nothing is burning or sparking" reassures; it does not say nothing works
    low = re.sub(r"\bnothing (is |was )?(burning|sparking|smoking|leaking|hot|wrong|broken)\b", " ", low)
    # "one outlet does nothing but the other outlets work": one fault, power on
    if re.search(r"\b(the other|other|rest of the|everything else)\b.{0,25}\b(works?|working|fine|ok|okay)\b", low):
        return False
    items = set()
    for m in re.finditer(ELEC_ITEMS, low):
        w = m.group(1).replace(" ", "")
        items.add(w[:-1] if w.endswith("s") and not w.endswith("ss") else w)
    if len(items) < 2 or not re.search(OUTAGE, low):
        return False
    return len(items) >= 3 or "light" in items or bool(re.search(QUANTIFIER, low))


# a smoke alarm is not smoke: masked before the danger rules read a clause
SAFETY_DEVICE = r"\bsmoke (alarms?|detectors?)\b"
EMERGENCY_NOT = r"\bfire ?(alarm|extinguisher|place|pit|wood|works|blanket|door|escape|brigade|hydrant|ant|fly)"
UNCERTAIN = (r"\b(do ?n[o']?t know|dont know|not sure|unsure|no idea|can(no|')?t (describe|tell|explain)|"
             r"source unknown|unknown (source|cause)|no (other|more|further) details?|"
             r"seems? (funny|strange|weird|off)|acts? (funny|strange|weird)|something (is )?(wrong|off|funny)|"
             # "not right" says something IS wrong; read as a denial it was closed unasked
             r"(is |are |isn'?t |aren'?t |ain'?t )?(not|no) (right|good|working right|working properly)|"
             r"not certain|hard to (say|describe))\b")
VAGUE_ONLY = (r"^\W*(the |my |a |our )?(\w+ )?(problem|issue|trouble)\b"
              r"|\b(\w+) (problem|issue|trouble),? (please|pls|plz) (call|ring|contact)\b")
NO_ISSUE = r"\b(fine|all good|no problem\w*|nothing wrong|looks? (fine|good)|all ok|is ok|are ok|working (fine|well|good))\b"
# A request for a repair that never says what or where: ask, never dismiss.
GENERIC_REQUEST = (r"\b(maintenance|repair|service) (request|job|issue|problem)\b"
                   r"|\brequest(ing)? (a |an |for )?(repair|maintenance|inspection|tradesperson)\b"
                   r"|\bneeds? (to be )?(checked|repaired|fixed|looked at|inspected|sorted)\b"
                   r"|\b(an?|the|some) (issue|problem|fault)\b"
                   r"|\baffect\w* (the )?(normal )?use\b"
                   r"|\b(please|could you|can you|can someone) (come and )?(fix|repair|inspect|look at|check)\b"
                   r"|\b(send|arrange) (someone|a tradesperson|maintenance|the maintenance team)\b")
QUESTION = r"\?|\b(how long|what number|who pays|checking if|just checking|is this|does this app|when will)\b"
WITHDRAWAL = (r"\b(don'?t worry|never ?mind|forget (about )?it|don'?t send|no longer need|"
              r"not needed|can close|we will manage|we'?ll manage|already sorted|fixed it|"
              r"it'?s fine now|its fine now|all fine now)\b")
FOLLOW_UP = r"\b(still waiting|following up|any update|anyone coming|chasing)\b"
OUT_OF_SCOPE = r"\b(streetlight|street light|neighbou?r'?s|council|road outside)\b"


def _clauses(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\s+(?:but|also|and also|however|although|though)\s+",
                     text.strip(), flags=re.I)
    return [p.strip() for p in parts if p and p.strip()]


def _resolved(clause: str) -> bool:
    return bool(re.search(RESOLVED, clause.lower()))


def _negated(clause: str, match: re.Match) -> bool:
    # negation scope stops at a comma: in "no water damage, just a dripping
    # tap" the "no" belongs to the damage, not the tap
    # a negation INSIDE the matched span cancels it too: "socket has no sparks"
    # matches device-then-symptom, with the "no" in the middle
    if re.search(rf"\b{NEGATORS}\b", match.group(0).lower()):
        return True
    before = clause[max(0, match.start() - 25): match.start()].lower().split(",")[-1]
    # "maybe nothing but X" downplays X, it does not deny it
    before = re.sub(r"\b(maybe|probably|might be|could be|prob)?\s*nothing(\s+much)?\s+but\b", " ", before)
    # "not sure", "no idea" hedge what follows; they never deny it. Without this
    # "not sure the gas is on fire" read as "not ... on fire".
    before = re.sub(r"\b(not sure|not certain|unsure|no idea|do ?n[o']?t know|dont know)\b", " ", before)
    after = clause[match.end(): match.end() + 30].lower().split(",")[0]
    return bool(re.search(rf"\b{NEGATORS}\b", before) or re.search(RESOLVED, after)
                or re.search(RESOLVED, before))


class KeywordExtractor:
    name = "keyword-v3"
    model = None

    def extract(self, text: str) -> Extraction:
        t = text.strip()
        low = t.lower()
        clauses = _clauses(t) or [t]

        # ---- danger to a person: before everything, never downgraded by a hedge
        for cl in clauses:
            c = cl.lower()
            live = [m for m in re.finditer(PERSONAL_DANGER, c) if not _negated(c, m)]
            live += [m for m in re.finditer(SELF_HARM, c) if not _negated(c, m)]
            if live and not _resolved(c):
                return Extraction(
                    actionability=Actionability.OUT_OF_SCOPE, hazard_domain=HazardDomain.NONE,
                    is_active=True, endangers_person=True, essential_service_lost=False,
                    habitability=Habitability.NONE, whole_dwelling=False,
                    emergency_000=True, tenant_isolated=False, evidence_phrase=cl[:200],
                    confidence=Confidence.HIGH, missing_decisive_fact=DecisiveFact.NONE)

        # ---- emergency: before anything else, and never downgraded by a hedge
        for cl in clauses:
            c = cl.lower()
            stripped = re.sub(EMERGENCY_NOT, " ", c)
            live = [m for m in re.finditer(EMERGENCY, stripped) if not _negated(stripped, m)]
            if live and not _resolved(c):
                dom = ("gas" if re.search(r"\bgas\b", low)
                       else "electrical" if re.search(r"\b(power|socket|switch|wire|meter|shock|electr)", low)
                       else "structural")
                return Extraction(
                    actionability=Actionability.REPAIR, hazard_domain=HazardDomain(dom),
                    is_active=True, endangers_person=True, essential_service_lost=False,
                    habitability=Habitability.UNINHABITABLE, whole_dwelling=True,
                    emergency_000=True, tenant_isolated=False, evidence_phrase=cl[:200],
                    confidence=Confidence.HIGH, missing_decisive_fact=DecisiveFact.NONE)

        injury_clause = None
        for cl in clauses:
            c = cl.lower()
            if any(not _negated(c, m) for m in re.finditer(INJURY, c)) and not _resolved(c):
                injury_clause = cl
                break

        danger, danger_domain, danger_clause = False, None, None
        essential, ess_domain, ess_clause = False, None, None
        fault_domain, fault_clause, fault_failing = None, None, False

        for cl in clauses:
            c = cl.lower()
            cd = re.sub(SAFETY_DEVICE, "safety-device", c)
            for pat, dom, neg_is_fault in DANGER_RULES:
                ms = list(re.finditer(pat, cd))
                if ms and ((neg_is_fault and not _resolved(cd))
                           or any(not _negated(cd, m) for m in ms)):
                    danger, danger_domain, danger_clause = True, dom, cl
                    break
            for pat, dom, neg_is_fault in ESSENTIAL_RULES:
                ms = list(re.finditer(pat, c))
                if ms and ((neg_is_fault and not _resolved(c))
                           or any(not _negated(c, m) for m in ms)):
                    first = not essential
                    essential = True
                    if first or (dom == "electrical" and ess_domain != "electrical"):
                        ess_domain, ess_clause = dom, cl
            if fault_domain is None:
                # "not sparking, not hot and works fine" -> working.
                # "lights not working" -> a failure. So: positive state is read on
                # the text with negated phrases removed, and explicit failure
                # phrases ("not working", "does not turn") are read on the original.
                stripped = re.sub(r"\b(not|no|never|isn'?t)\s+(\w+\s+)?\w+", " ", c)
                working_only = (re.search(WORKING, stripped)
                                and not re.search(FAILURE, stripped)
                                and not re.search(FAIL_PHRASES, c))
                for pat, dom in FAULT_RULES:
                    # every match, not just the first: in "no water damage, just a
                    # dripping tap" the first hit ("water") is negated but the
                    # later one ("dripping") is a real fault
                    live = [m for m in re.finditer(pat, c) if not _negated(c, m)]
                    if live and not working_only and not _resolved(c):
                        fault_domain, fault_clause = dom, cl
                        fault_failing = bool(re.search(FAILURE, c) or re.search(FAIL_PHRASES, c))
                        break
            elif not fault_failing and (re.search(FAILURE, c) or re.search(FAIL_PHRASES, c)):
                # A clause that only MENTIONS part of the house ("fell from the
                # roof") gives way to one where something is failing ("the roof
                # is now leaking"): that is the repair the tenant is reporting.
                for pat, dom in FAULT_RULES:
                    live = [m for m in re.finditer(pat, c) if not _negated(c, m)]
                    if live and not _resolved(c):
                        fault_domain, fault_clause, fault_failing = dom, cl, True
                        break

        power_out = False
        if not (essential and ess_domain == "electrical") and _power_lost(low):
            essential, power_out = True, True
            ess_domain, ess_clause = "electrical", t

        has_fault = danger or essential or fault_domain is not None

        if injury_clause and not has_fault:
            return Extraction(
                actionability=Actionability.OUT_OF_SCOPE, hazard_domain=HazardDomain.NONE,
                is_active=True, endangers_person=True, essential_service_lost=False,
                habitability=Habitability.NONE, whole_dwelling=False,
                emergency_000=True, person_hurt=True, tenant_isolated=False,
                evidence_phrase=injury_clause[:200],
                confidence=Confidence.HIGH, missing_decisive_fact=DecisiveFact.NONE)

        # non-requests: only when no fault signal survives negation
        if not has_fault:
            # "no idea where it came from" is uncertainty, not "no problem".
            # Check it before the negation words can read it as a denial.
            if re.search(UNCERTAIN, low):
                return self._unclear(t)
            if re.search(WITHDRAWAL, low):
                return self._nonrequest(Actionability.WITHDRAWAL, t)
            if re.search(FOLLOW_UP, low):
                return self._nonrequest(Actionability.FOLLOW_UP, t)
            if re.search(OUT_OF_SCOPE, low):
                return self._nonrequest(Actionability.OUT_OF_SCOPE, t)
            if (re.search(GENERIC_REQUEST, low) and not re.search(NO_ISSUE, low)
                    and not re.search(RESOLVED, low)
                    # "maintenance request: the toilet flushes normally and is not
                    # blocked" says nothing is wrong; it is not a request to clarify
                    and not re.search(rf"\b{NEGATORS}\b", low) and not re.search(WORKING, low)):
                # "I need a repair" with no what or where: one question, not a refusal
                return self._unclear(t)
            if (re.search(NO_ISSUE, low) or re.search(rf"\b{NEGATORS}\b", low)
                    or re.search(RESOLVED, low)):
                return self._nonrequest(Actionability.NO_ISSUE, t)
            if re.search(QUESTION, low):
                return self._nonrequest(Actionability.QUESTION, t)
            return self._unclear(t)

        # a withdrawal that also names a fault is ambiguous: resolved, or given up?
        if re.search(WITHDRAWAL, low) and not danger:
            return self._nonrequest(Actionability.WITHDRAWAL, t, conf=Confidence.MEDIUM)

        # Uncertain or content-free reports go to the clarification gate as
        # UNCLEAR. Never when danger was found: a vague report of a hazard is
        # still a hazard.
        if not danger and not essential and (
                re.search(UNCERTAIN, low)
                or (re.search(VAGUE_ONLY, low) and not re.search(FAILURE, low)
                    and not re.search(FAIL_PHRASES, low))):
            return Extraction(
                actionability=Actionability.UNCLEAR, hazard_domain=HazardDomain(fault_domain or "none"),
                is_active=True, endangers_person=False, essential_service_lost=False,
                habitability=Habitability.NONE, evidence_phrase=(fault_clause or t)[:200],
                confidence=Confidence.LOW, missing_decisive_fact=DecisiveFact.NONE)

        domain = danger_domain or ess_domain or fault_domain
        evidence = danger_clause or ess_clause or fault_clause or t

        if danger:
            hab = Habitability.UNINHABITABLE
        elif essential or re.search(SEVERE, low):
            hab = Habitability.SEVERELY_IMPAIRED
        elif domain == "minor":
            hab = Habitability.COSMETIC
        else:
            hab = Habitability.IMPAIRED

        missing = DecisiveFact.NONE
        if (domain == "sanitation" and "toilet" in low and not essential and not danger
                and not re.search(r"\b(only|one|sole|single|other|second|another)\b.{0,10}\btoilet"
                                  r"|\btoilet\b.{0,30}\b(only one|one only|just one|another|second)\b", low)):
            missing = DecisiveFact.ONLY_TOILET

        vague = len(low.split()) < 3 and not danger
        return Extraction(
            actionability=Actionability.REPAIR,
            hazard_domain=HazardDomain(domain),
            is_active=not re.search(RESOLVED, low),
            endangers_person=danger,
            person_hurt=bool(injury_clause),
            essential_service_lost=essential,
            habitability=hab,
            whole_dwelling=bool(re.search(WHOLE_DWELLING, low)) or (danger and domain == "gas") or power_out,
            tenant_isolated=bool(re.search(ISOLATED, low)),
            evidence_phrase=evidence[:200],
            confidence=Confidence.LOW if vague else
                       (Confidence.HIGH if (danger or essential) else Confidence.MEDIUM),
            missing_decisive_fact=missing,
        )

    @staticmethod
    def _nonrequest(kind, text, conf=Confidence.HIGH):
        return Extraction(actionability=kind, hazard_domain=HazardDomain.NONE,
                          is_active=False, endangers_person=False,
                          essential_service_lost=False, habitability=Habitability.NONE,
                          evidence_phrase=text[:200], confidence=conf,
                          missing_decisive_fact=DecisiveFact.NONE)

    @staticmethod
    def _unclear(text):
        return Extraction(actionability=Actionability.UNCLEAR, hazard_domain=HazardDomain.NONE,
                          is_active=True, endangers_person=False,
                          essential_service_lost=False, habitability=Habitability.NONE,
                          evidence_phrase=text[:200], confidence=Confidence.LOW,
                          missing_decisive_fact=DecisiveFact.NONE)


# ---------------------------------------------------------------------------
# OpenAI extractor
# ---------------------------------------------------------------------------

PROMPT = """You read housing repair messages for a maintenance coordinator in the Northern Territory, Australia.

Tenants write briefly, often in second-language English or Aboriginal English, often without grammar. Judge what is described, never how it is written. "aircon bin broken 3 week, kids in house" is a clear and complete report.

Rules:
- Report only what the text supports.
- actionability: "repair" if any fault is described anywhere in the message, even after small talk. A message that opens "just checking if the app works" and then mentions sparking IS a repair.
- endangers_person: physical harm or major damage possible TODAY. Sparking, exposed or hanging wire, burning smell, hot or crackling socket, a tingle or shock from a tap or appliance, water reaching lights or power, gas or rotten-egg smell, fumes from a heater or stove, sewage or waste water inside or a septic tank overflowing, uncontrolled flooding or a burst pipe that cannot be stopped, a roof or ceiling collapsed or sagging, broken steps, stairs, floors or loose balcony railings, broken glass, damaged asbestos or fibro, a house that cannot be locked or a door that will not close. This mirrors NT immediate-repair guidance. Not "annoying". Not "waited a long time".
- A negated or already-fixed hazard is NOT a hazard: "there is no gas smell", "the leak was fixed last week".
- essential_service_lost: no water (including a broken bore pump or empty tank), no power to the house, no usable toilet, no way to cook, no hot water, no working smoke alarm.
- habitability "severely_impaired" when the tenant is locked out of the house.
- withdrawal: the tenant says not to come or that it is fine now. Do not decide whether it was actually fixed.
- evidence_phrase: copy the tenant's words VERBATIM. Never paraphrase.
- confidence "low" when the message is too vague to classify. Do not guess a hazard to fill the field.
- A message asking for a repair without saying what or where ("I'd like to submit a maintenance request about an issue") is actionability "unclear", never "no_issue": the tenant will be asked one question.
- whole_dwelling: true when the whole household is exposed to the harm: flooded, roof gone, no power or water to the house, or a gas leak (fumes reach everyone). False for one fixture or one room, and false for a door or lock problem.
- emergency_000: true when life is at risk right now: fire, flames, explosion, someone electrocuted, injured, unconscious or not breathing, violence or a weapon (someone with a knife, someone being hit or threatened), or someone talking about harming themselves. Hedged wording still counts ("perhaps the gas is on fire"). A fire alarm beeping is not an emergency.
- Violence, weapons, threats and self-harm are NOT repairs: set actionability "out_of_scope" with emergency_000 true and endangers_person true.
- person_hurt: true if someone has been or may have been hurt (a fall from a roof or ladder, bleeding, knocked out). It does NOT raise the repair's urgency: judge endangers_person from the house alone ("he fell off the roof and now the roof leaks" is person_hurt true, and the leak judged on its own).
- tenant_isolated: true ONLY if the tenant says they have already made it safe (power off at the meter box, gas off at the bottle, water off at the mains). Never assume it.
- missing_decisive_fact: the ONE absent fact that would change the outcome. A blocked toilet with no mention of whether it is the only toilet -> "only_toilet". Otherwise "".

Message:
{text}"""


def _llm_schema() -> dict:
    """The strict schema, with the empty "no missing fact" enum value spelled
    "none". Some providers reject an empty string as an enum member."""
    schema = openai_strict_schema()
    prop = schema["properties"]["missing_decisive_fact"]
    prop["enum"] = ["none" if v == "" else v for v in prop["enum"]]
    return schema


def _parse(payload: dict) -> Extraction:
    if payload.get("missing_decisive_fact") == "none":
        payload = {**payload, "missing_decisive_fact": ""}
    return Extraction.model_validate(payload)


def _key(provider: str) -> str:
    key_attr, _, env = PROVIDERS[provider]
    key = getattr(settings(), key_attr)
    if not key:
        # caught by extract(): falls back to keyword rules and flags the job
        raise RuntimeError(f"{env} is not set")
    return key


class OpenAIExtractor:
    """OpenAI chat completions with a strict JSON schema. Also serves any
    provider with an OpenAI-compatible endpoint (see GeminiExtractor)."""
    name = "openai"
    base_url: str | None = None

    def __init__(self, model: str | None = None):
        self.model = model or getattr(settings(), PROVIDERS[self.name][1])

    def extract(self, text: str) -> Extraction:
        from openai import OpenAI

        # max_retries=0: the SDK would otherwise retry silently, waiting as long
        # as the server asks (up to a minute), and every hidden attempt counts
        # against a free-tier allowance. extract() owns the retry policy.
        kw = {"api_key": _key(self.name), "timeout": min(settings().llm_timeout_s, settings().llm_budget_s),
              "max_retries": 0}
        if self.base_url:
            kw["base_url"] = self.base_url
        client = OpenAI(**kw)
        resp = client.chat.completions.create(
            model=self.model, temperature=0,
            messages=[{"role": "user", "content": PROMPT.format(text=text)}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "extraction", "strict": True,
                                             "schema": _llm_schema()}},
        )
        return _parse(json.loads(resp.choices[0].message.content))


class GeminiExtractor(OpenAIExtractor):
    """Gemini through Google's OpenAI-compatible endpoint, so the same client
    and the same strict schema are used. Free keys: aistudio.google.com."""
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"


class AnthropicExtractor:
    """Claude. The schema is given as the input of a single tool, and the model
    is forced to call that tool, so the reply is always schema-shaped JSON."""
    name = "anthropic"

    def __init__(self, model: str | None = None):
        self.model = model or settings().anthropic_model

    def extract(self, text: str) -> Extraction:
        import anthropic

        client = anthropic.Anthropic(api_key=_key(self.name),
                                     timeout=min(settings().llm_timeout_s, settings().llm_budget_s),
                                     max_retries=0)
        resp = client.messages.create(
            model=self.model, max_tokens=1024, temperature=0,
            tools=[{"name": "record_extraction",
                    "description": "Record the observable facts in the tenant's message.",
                    "input_schema": _llm_schema()}],
            tool_choice={"type": "tool", "name": "record_extraction"},
            messages=[{"role": "user", "content": PROMPT.format(text=text)}],
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        return _parse(dict(block.input))


EXTRACTORS = {"openai": OpenAIExtractor, "gemini": GeminiExtractor,
              "anthropic": AnthropicExtractor}


# ---------------------------------------------------------------------------
# Cache + fallback chain
# ---------------------------------------------------------------------------

def _code_fingerprint() -> str:
    """Hash of everything that decides a reading: the rules, the prompt, the
    schema and the normaliser. Any edit changes the key, so a cached reading
    made under old rules can never be served under new ones.

    Before this existed, the key covered only the text, prompt version and
    extractor name. Rule fixes were silently masked for any message already
    seen once: a report fixed in code still came back with the old tier.
    """
    global _FINGERPRINT
    if _FINGERPRINT is None:
        from pathlib import Path
        here = Path(__file__).parent
        h = hashlib.sha256()
        for name in ("extract.py", "normalise.py", "schemas.py"):
            h.update((here / name).read_bytes())
        _FINGERPRINT = h.hexdigest()[:16]
    return _FINGERPRINT


_FINGERPRINT: str | None = None


def _cache_key(text: str, extractor_id: str) -> str:
    raw = f"{settings().prompt_version}|{_code_fingerprint()}|{extractor_id}|{text}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _primary():
    cls = EXTRACTORS.get(settings().extractor)
    return cls() if cls else KeywordExtractor()


_keyword = KeywordExtractor()

# Two retries, a few seconds apart, then the flagged keyword fallback. Worst
# case is a few calls and ~6 s of waiting per message, never minutes.
RETRIES = 2
BACKOFF_S = (2.0, 4.0)


def extract(text: str, primary=None) -> ExtractResult:
    """Cache -> primary -> retry once -> keyword fallback (flagged)."""
    ex = primary or _primary()
    ex_id = f"{ex.name}:{getattr(ex, 'model', None)}"
    key = _cache_key(text, ex_id)

    hit = db.col(CACHE).find_one({"_id": key})
    if hit:
        return ExtractResult(Extraction.model_validate(hit["payload"]),
                             ex.name, getattr(ex, "model", None), True, False)

    if ex_id in PROVIDER_DOWN:
        # already failed permanently in this process: skip straight to the
        # (flagged) fallback instead of paying two failed calls per message
        return ExtractResult(_keyword.extract(text), _keyword.name, None, False, True)

    if _cooling_down(ex_id):
        # busy recently: answer at once from the rules instead of making a
        # tenant wait on a model that is failing (still flagged for review)
        return ExtractResult(_keyword.extract(text), _keyword.name, None, False, True)

    last_err = None
    deadline = time.monotonic() + settings().llm_budget_s
    for attempt in range(RETRIES + 1):
        try:
            result = ex.extract(text)
            db.col(CACHE).update_one(
                {"_id": key}, {"$set": {"payload": result.model_dump(mode="json"), "created_at": now()}},
                upsert=True)
            FAILURES.pop(ex_id, None)
            return ExtractResult(result, ex.name, getattr(ex, "model", None), False, False)
        except Exception as err:            # network, schema, timeout
            last_err = err
            log.warning("extraction_failed", attempt=attempt, error=str(err)[:200])
            if isinstance(ex, KeywordExtractor):
                break
            if _permanent(err):
                PROVIDER_DOWN[ex_id] = str(err)[:300]
                log.error("provider_disabled", provider=ex_id,
                          hint="fix the model name, key or billing, then restart")
                break
            if attempt < RETRIES:
                # overload (503) and per-minute limits (429) clear in seconds,
                # but never wait past the time budget for this message
                busy = getattr(err, "status_code", None) in (429, 503)
                pause = BACKOFF_S[attempt] if busy else 0.5
                if time.monotonic() + pause >= deadline:
                    break
                time.sleep(pause)

    if isinstance(ex, KeywordExtractor):
        raise last_err
    _note_failure(ex_id, last_err)
    log.error("extraction_fallback", error=str(last_err)[:200])
    return ExtractResult(_keyword.extract(text), _keyword.name, None, False, True)


# Circuit breaker. A model that keeps failing is skipped for a while, so every
# tenant is answered at once by the rules rather than each one waiting through
# the retries. Counts live in config.FAILURES, reset with the other caches.


def _note_failure(ex_id: str, err: Exception | None) -> None:
    if ex_id in PROVIDER_DOWN:
        return
    FAILURES[ex_id] = FAILURES.get(ex_id, 0) + 1
    st = settings()
    if FAILURES[ex_id] >= st.breaker_failures:
        PROVIDER_COOLDOWN[ex_id] = (time.monotonic() + st.breaker_cooldown_s, str(err)[:200])
        FAILURES[ex_id] = 0
        log.error("provider_cooling_down", provider=ex_id, seconds=st.breaker_cooldown_s)


def _cooling_down(ex_id: str) -> bool:
    until = PROVIDER_COOLDOWN.get(ex_id)
    if until and time.monotonic() < until[0]:
        return True
    PROVIDER_COOLDOWN.pop(ex_id, None)
    return False


def _permanent(err: Exception) -> bool:
    """Errors that retrying cannot fix: missing key, bad key, unknown model,
    rejected request, no credit. A timeout or a rate limit is worth a retry."""
    if isinstance(err, RuntimeError) and "is not set" in str(err):
        return True
    status = getattr(err, "status_code", None)
    if status in (400, 401, 403, 404):
        return True
    # 429 is either "slow down" (worth a retry) or "allowance used up": OpenAI
    # out of credit, or a Gemini free-tier DAILY limit. Only the second is final.
    msg = str(err).lower()
    return status == 429 and any(w in msg for w in ("insufficient_quota", "no credits",
                                                    "perday"))
