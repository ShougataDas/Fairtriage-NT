# FairTriage NT: design notes

The detail behind the [README](../README.md): how messages are read, how jobs
are ranked, how waits and trips are worked out, what the tests caught, and
what is still missing. Every weight and threshold mentioned here lives in
[`config/policy.yaml`](../config/policy.yaml).

## Is there any AI in it?

**Not by default.** With no settings, `FAIRTRIAGE_EXTRACTOR=keyword` and every
message is read by the hand-written rules in `fairtriage/extract.py`. All test
results and all evaluation numbers in this README come from those rules. `/api/health`
reports which reader is live, and staff screens warn if a switched-on model
stops answering.

To switch a model on, set `FAIRTRIAGE_EXTRACTOR` and the provider's key in `.env`:

| `FAIRTRIAGE_EXTRACTOR` | Key | Default model | How it gets structured output |
|---|---|---|---|
| `gemini` | `GEMINI_API_KEY` (free at aistudio.google.com) | `gemini-3.1-flash-lite` | strict JSON schema via Google's OpenAI-compatible endpoint |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5-20251001` | schema as a forced tool call |
| `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` | strict JSON schema |

Override the model with `FAIRTRIAGE_<PROVIDER>_MODEL`. All three use the same
prompt, the same schema and temperature 0.

If the key is missing, the account has no credit (HTTP 429), the API is
unreachable, or the reply does not match the schema, the request falls back to
the keyword rules and is flagged for mandatory human review. The model paths
are tested with fake clients standing in for the APIs
(`tests/test_openai_path.py`); the test suite never reads `.env` and never
calls a live API. **None of them has been evaluated against the live API.**
Run `python scripts/run_eval.py --extractor <provider> --limit 300` before
claiming anything about one.

**A busy model never keeps a tenant waiting.** Each message gets at most
12 seconds of model time, retries included (`FAIRTRIAGE_LLM_BUDGET_S`). After
three failed messages in a row the model is skipped for five minutes and the
keyword rules answer at once; every such job is flagged, and the staff screens
say the model is paused. Measured in September 2026, the Gemini free tier
returned "busy" (503) for every structured request on four different models,
and took 11 seconds for a two-word reply when it answered at all. That is
capacity on Google's side, not something code can fix: use the keyword rules,
or a paid tier.

**After updating the code, run `make clean && make seed`.** Readings are
cached, and the cache key now includes a fingerprint of the rules, so a rule
change can never be masked by an old reading. The fingerprint is shown at
`/api/health`, so you can check which rules a running copy is using.

Three bugs fixed on the way: the cache key ignored the rules, so a fixed
message kept its old reading on any machine that had seen it before; the settings loader only read `FAIRTRIAGE_*`
variables, so a key in `.env` was silently ignored; and the generated schema
used `$ref` and `default`, which strict mode rejects.

```bash
make test    # 334 tests
make scenarios   # the 16 cases in TEST_CASES.md
make eval    # scores extraction against data/fairtriage_v3.csv
```

## Maintenance scenarios covered

`tests/test_maintenance_coverage.py` holds about 100 reports across every
category a Top End maintenance line hears, in plain, hurried and
second-language wording, each with the tier it must get:

- **Immediate:** sparking, burning smell, a tingle from a tap, switchboard
  faults, gas smell or heater fumes, burst pipes, sewage inside, overflowing
  toilets or septic tanks, roofs off, sagging or fallen ceilings, floors
  giving way, broken steps and loose balcony railings, broken glass, damaged
  asbestos, doors that will not lock or close, flooding, storm damage.
- **Urgent:** no water (including bore pumps and empty tanks), no power, no hot
  water, no way to cook, the only toilet broken, a smoke alarm not working,
  locked out.
- **Routine:** taps, cupboards, flyscreens, tiles, walls, paint, mould, pests
  (sent to pest control), fences, gutters, drains, appliances, fans, air
  conditioning, fixtures.

Writing it found 34 gaps, all fixed: "no water in the house" had been read as
"no issue", and tiles, mould, pests, fences and appliances were sent to the
phone-call list as "unclear".

## How the wait is estimated

    lead time for the tier
      + hours of the same trade's work ranked ahead in the region
        / (that trade's crews x on-site hours per day)
      + mobilisation for a remote community (charter, barge, packing)
      + travel by the fastest route

Lead times (`wait.lead_days` in the policy: Immediate 0.1, Urgent 1, Routine
3 days) are placeholders for the department's real booking times; without
them a quiet queue showed routine jobs as "within a day". Policy v8 changed
the queue term: it used to be jobs ahead / all crews x half a day, which
barely moved the lead time, so every Immediate, Urgent and Routine job showed
nearly the same wait. Now a plumbing job waits behind plumbing work, not an
electrician's (`wait.trade_share` splits each region's crews by trade), a
four-hour structural job counts for more than a one-hour lock change, and
air- or barge-only communities add `wait.mobilise_days`. The range widens
with uncertainty (`wait.spread`: remote, road status, a long queue) instead
of a flat 25%.

The estimate is also **live**. The one stored with the assessment is what the
tenant was told on the day; the queue screen and the tenant's tracking page
recompute it from today's queue, using up the booking time first, so it
counts down while the job waits and moves when work ahead is finished or a
more dangerous job arrives. `wait.floor_days` stops an overdue routine job
being shown as "within hours".

**Immediate** work is made safe by on-call contractors around the clock
(`wait.make_safe`: crews on call per trade and region, an hour per make-safe
visit), with that trade's day crews dropping other work, so a normal day
stays within about 3 to 4 hours. When the queue pushes a job past
`make_safe.target_hours` (4), the tenant is still told the real time, the
report gets an `immediate_over_target` flag, and the queue screen shows a
banner by trade and region telling the coordinator to call more crews in.
Only when the job would be on time without the jobs ahead: a flight to a
remote community can take longer than the target on its own, and more crews
do not change that. Travel uses the trip
planner's own fastest route, so a closed road means the charter the planner
would send, not a week's delay. A **remote routine** job waits for the next
trip to its community, worked out with the planner's rule: now, if an urgent
job of the same trade is open there, otherwise when the community's oldest job
reaches `community_threshold_multiple` times its target. At the current 3.0
that is up to 75 days against a 25-day target; the estimate shows it rather
than hide it. Lowering that multiple is the lever, and a decision for the
department: the **Fairness page** shows, for each value from 1x to 4x, the
longest and average remote routine wait, the ratio to Darwin, the trips a
month and their cost (`fairtriage/whatif.py`), and lets a coordinator set it
with a recorded reason (`fairtriage/tripsettings.py`). The planner and every
live remote wait follow at once: a job already waiting moves by the change
times the target.

## A tenant asks why

`fairtriage/askwhy.py`, behind `POST /api/requests/{id}/why`. The answer is
assembled from the record and today's queue, never generated free text, so
every number is one the system holds:

1. the group and its reason, and what the group means;
2. how many repairs are ahead and why each is ahead: a more dangerous group,
   the same group with more need, or the same need reported earlier; and how
   many of those were reported later but go first, "nobody goes ahead
   because they live closer";
3. today's place, the same as the identical repair in Darwin, and the live
   wait, with travel named as part of WHEN, never of WHO;
4. what changed: staff decisions quoted with their reason (a repair moved
   down says so, and why), trips that were full, the wait told against today;
5. what would move it up, and how to reach a person.

It passes the same no-apology, no-promise rule as every tenant text.
`POST /api/requests/{id}/review` records a review request; it sits on the
coordinator's phone list with the tenant's message until a decision is
recorded on the request.

## Which crew goes

The crew that reaches the destination soonest, from any depot: when it
is free plus the fastest route from where it is. The home region's crew
keeps the job unless another arrives more than
`trips.home_crew_preference_hours` (0.5) sooner. Wadeye is in the Katherine
region, but with its road out the Katherine crew would drive three hours to
Darwin for the charter a Darwin crew takes straight away. Arrival time only,
never cost. The wait estimate uses the same nearest depot.

## How a trip's cost is estimated

`fairtriage/cost.py` gives each recommended trip a [low, high] cost in AUD
excluding GST, from `trip_cost` in the policy. Rates were checked against public sources in
October 2026 (ATO allowances, Darwin and remote diesel prices, Darwin trade
charge-out rates, Australian charter rates; each noted in the policy file);
those with no public source are marked UNVERIFIED there:

- **Transport:** road km out and back on the planner's own routes x litres per
  100 km (more on unsealed or restricted roads) x a fuel price range, vehicle
  running costs per km, and for flights the charter by flight hour (billed
  twice when the crew stays overnight and the aircraft goes home), plus
  landing fees.
- **Logistics:** accommodation per person per night away, meals and travel
  allowance per day, freight and a community vehicle when flying in. Tolls,
  parking and land permits are listed at $0 so it is visible they were
  considered.
- **Labour:** the tradesperson's hourly rate, and an assistant on remote
  roads or nights away, for travel hours plus on-site hours (job hours x 0.85
  to 1.4, plus set-up per stop), with overtime past 7.6 hours a day and an
  after-hours loading when the destination job is Immediate.
- **Other:** parts and materials per job by trade, and a 5 to 15%
  contingency for weather, road delays or a return visit.

Low takes every input at its low end and high at its high end, so the range
is deliberately wide: a planning estimate, not a quote. The same calculation
for one trip per job gives the "separate trips" figure. **Cost is never an
input to ranking or to which jobs a trip serves**; a test sets every rate to
an absurd value and checks the plans do not change. A remote community costs
more to reach, and that must not move its tenants down.

## Places covered

64 places: 33 Darwin suburbs, 13 in Palmerston, 6 in the Litchfield rural
area, and 12 regional and remote communities. The tenant dropdown groups them
by area. **Coordinates are approximate suburb and community centres**; replace
them from the NT Place Names Register before release.

## Ordering inside a tier

Every job that can hurt someone today is Immediate, so the Immediate tier also
needs its own order. Four factors, all in `config/policy.yaml`:

| Factor | Weight | Meaning |
|---|---|---|
| habitability | 0.35 | how much the house can still be used |
| extent | 0.15 | is the whole household exposed (flood, roof gone, gas) or one fixture |
| containment | 0.20 | has the tenant already made it safe (power off at the meter box, gas off at the bottle) |
| vulnerability | 0.30 | who lives there, as reported |

Containment is only credited when the tenant **says** they have done it.
Unknown counts as not contained, because assuming safety is the dangerous
error. Tenants with a live hazard are given make-safe advice while they wait.

This separates a flooded house from a sparking socket, and a live hazard from
one already switched off. It does **not** decide whether a lock that will not
catch outranks a hot socket. Nothing in a message can settle that; it is a
judgement about which harm matters more, and belongs to the department.

## The design in four sentences

The model reads and never decides: it turns a message into six facts a person
could check, and everything after that is arithmetic in `fairtriage/policy.py`.
Need and reachability never merge: distance changes when someone can arrive,
never where the job ranks, and the ranking code contains no distance variable
at all. If a decisive fact is missing ("is this the only toilet?") the system
asks one question and waits rather than guessing. Nothing dispatches itself.

## Layout

| Path | What it does |
|---|---|
| `fairtriage/extract.py` | Keyword extractor (offline, baseline, fallback) and OpenAI strict-schema extractor, with cache |
| `fairtriage/normalise.py` | Spelling lexicon with protected hazard words; reconciles readings of original and corrected text |
| `fairtriage/graph.py` | LangGraph pipeline. The clarification pause persists across requests in MongoDB |
| `fairtriage/db.py` | MongoDB: requests with their current assessment, plus append-only history of every assessment, reading and decision |
| `fairtriage/export.py` | CSV and Excel download of the queue or of every request |
| `fairtriage/policy.py` | Lexicographic tier plus within-tier need. No model, no I/O |
| `fairtriage/wait.py` | Wait estimate, and the same job's wait in Darwin |
| `fairtriage/explain.py` | Fact sheet, tenant and coordinator text, verifier |
| `fairtriage/scheduler.py` | Trip planner: triggers, route choice, stops on the way, expected arrivals, crew availability |
| `fairtriage/routing.py` | Road network with today's road status applied; fastest and alternative routes |
| `fairtriage/metrics.py` | Fairness measurements from the live queue |
| `config/policy.yaml` | Every weight and threshold, versioned |
| `frontend/` | Next.js web app for tenants and staff; calls the JSON API only |
| `reference/` | Communities, distance matrix, road network, crew capacity, road snapshot |

## Trip planner

`/coordinator/trips` recommends trips from the open queue, each job's
priority and where the crews are now. It is worked out again on every page
load, so it follows new reports, overrides and crew moves. Nothing is booked
until a coordinator confirms.

For each trip it compares the fastest route to the destination job with
slower routes that pass other places, over `reference/road_network.csv`
(highway corridors, suburban links, charter legs; closed roads removed and
restricted roads slowed, from the road snapshot). Then:

- **An Immediate job goes by the fastest route with no stops before it**, and
  the explanation says what the longer route could have served.
- **Otherwise jobs on a route are added in need order**, never quickest first,
  while the destination still arrives within 75% of its remaining time to
  target and no job on the trip is pushed past its own target.
- **The route with the best score is chosen:** value of the jobs served on the
  way (by tier, raised for time waited) minus 1.0 per extra hour of travel,
  minus a charter cost. A long route is not taken for nothing.
- **Crews are finite.** If a long trip would make a later urgent job wait past
  its target for the same crew, the long trip is shortened, and says why.
- **Every stop gets an expected arrival**: crew start + travel + work at the
  earlier stops. Confirming stores it, and the tenant's page shows "stop 2 of
  3, expect a tradesperson in about N days".

Example with the demo network (`tests/test_trip_routes.py`): an Urgent job at
Gunbalanya with dripping taps waiting at Batchelor and Pine Creek gives
`Darwin (Ludmilla) → Batchelor → Pine Creek → Gunbalanya`. Make the Gunbalanya
job Immediate and it becomes `Darwin (Ludmilla) → Gunbalanya`.

**Urgent overflow gets its own trip.** When more urgent jobs are waiting in
one community than a trip can hold, the rest now get further trips (another
crew, or the same crew once free). Before, they were counted as deferred and
nobody was sent: 5 of 12 Immediate jobs in one test.

**Why approve.** Each recommended trip reports, against one trip per job:
repairs covered, travel hours and km saved, tenants reached sooner than they
were told, and whether the destination job is still inside its target. The web
app shows the trip on a map (OpenStreetMap tiles; the route still draws
without internet) and each trip can be approved on its own
(`POST /api/trips/plan?anchor=<id>`).

**Daily runs** (`trips.daily_runs`). Darwin, Palmerston and towns within
daily reach have no trips; their crews work in day runs. For each trade in a
region, a run starts with the highest-ranked job still waiting, then adds
jobs of the same trade in need order while the day has room (on-site hours
and a working day) and each adds at most 30 minutes of driving. So who is on
a run is decided by the queue; only the order of visits is by road (nearest
place first from the depot). Runs are planned for today and tomorrow, one per
crew of that trade, less crews leaving today on a remote trip. An Immediate
job in town is never bundled: it is a make-safe call-out of its own. Runs and
call-outs are costed as local day work (no nights away; extra hours are
overtime).

The planner never changes a tier, a need score or a rank. Every weight is in
`config/policy.yaml` under `trips:` and printed on the page.

**Limits:** road kilometres and speeds are approximate; stops are planned on
the way out, not on the way back; crews are interchangeable within a region;
the wait is estimated from the queue until a trip is confirmed, and then
from the trip's arrival time.

## Results so far

Keyword extractor on the held-out **test split** (1,810 rows) of `fairtriage_v3.csv`,
before and after fixing the gaps the first evaluation exposed:

| | Before | After |
|---|---|---|
| Actionability macro-F1 | 0.643 | 0.810 |
| Danger macro-F1 | 0.883 | 0.963 |
| Critical hazards missed | 23.9% | 10.0% |
| Dangerous reports routed out of the queue | 6.4% | 0.2% |
| Danger precision / recall | 0.907 / 0.761 | 0.998 / 0.900 |
| Essential-service macro-F1 | 0.520 | 0.520 |
| Rank equal to location-free rank | 100% | 100% |

**These are not accuracy figures, for three reasons.**

1. 12,000 labels were derived by a rule in the migration script, not by people.
   Scoring against them measures agreement with that rule.
2. The fixes were designed by reading failure samples drawn from every split,
   including test. The test split is therefore not clean for these rules.
   The stronger evidence is `tests/test_generalisation.py`: 25 cases written in
   our own words, unlike the dataset's templates, which the fixes also pass.
3. Four probe labels were corrected during this work ("can't lock the front
   door", which the policy treats as immediate but the probe had marked safe).

Essential-service F1 did not move and was not chased. About half its misses
land in the same tier anyway (danger already makes them Immediate), and the
rest disagree with a migration rule that marks essential loss generously.
Separating real misses from label errors needs human labels.

Before quoting anything: label a 600-row sample blind with two annotators,
compute kappa with `merge_back.py annotate`, and re-run `make eval` on it.

## What the tests caught

Worth knowing, because each is a trust failure a judge could find:

- The tenant explanation quoted their answer ("yes only one") as their complaint.
- "yes only one" came out Routine, because the raw answer never said "toilet".
  Answers are now interpreted against the question actually asked.
- Second-language grammar scored lower: "water is not come from tap" missed the
  essential-service loss that "no water coming out" caught. Found by the
  paraphrase-invariance test, which is the brief's exact fairness concern.
- Faults phrased negatively ("cannot lock", "no water") were cancelled as denials.
  Fixing that briefly made "no water leak anymore" read as a lost water supply.
- "ceiling fan" sent a plumber; "lights" missed the electrician.
- The first danger definition was narrower than NT guidance, which lists major
  water loss as immediate. Critical-hazard misses fell from 56% to 24% once aligned.
- Vague reports ("no idea where the water is from") were ranked as confident
  repairs and never triggered the clarifying question. "no idea" was even read
  as "no problem".
- Hedged hazards were dismissed: "seems like gas" and "maybe nothing but the
  insulation is cracked" read as uncertain or denied. A hedged hazard is now
  always a hazard; uncertainty can never downgrade danger.
- Storm and cyclone damage had no rules at all. "My roof was gone in last night
  cyclone" came out Routine, and the tenant was told it was "not dangerous".
  Flooded homes, roofs lifted or torn off, trees or branches through the roof,
  and collapsed ceilings or verandahs are now make-safe Immediate jobs.
- Known household facts were appended to the tenant's message, so a roof leak
  report was quoted back ending "There is another toilet in the house." The
  tenant's words are now never altered.
- The verifier treated digits inside the random reference ID as permitted
  numbers, so an invented "37 hours" could pass. Found by a flaky test.

- The first version of within-tier extent counted "the house cannot be
  secured" as whole-house and gas as one fixture, so a lock tied with a flood
  and a gas leak ranked below a door. Extent now means household exposure.

- Second-language word order: "fridge power socket make smoke" was missed
  because the rule expected smoke before the socket. Widening it briefly broke
  80 negated reports ("socket has no sparks") because a negation *inside* a
  matched phrase was never checked. Fixing that lifted danger precision to 0.998.

- **A tenant said the gas might be on fire and was told we could not tell what
  needed fixing.** Their first message was vague, and "perhaps the gas is on
  fire" was their answer to our question. There was no rule for fire at all;
  the answer was not shown back to them; and a report still unclear after one
  question left the queue where no coordinator would see it. Now: an emergency
  layer runs before everything else and hedging never cancels it; the tenant is
  told to call 000 and get out before anything else, with no advice that sends
  them towards the danger; the job tops the queue; a dangerous job is never
  held waiting for an answer; and any report still unclear after asking goes to
  a "Needs a phone call" list above the coordinator queue.

**Dataset gap, again:** no row in `fairtriage_v3.csv` mentions fire, an
explosion or someone hurt, so the evaluation cannot measure the emergency
path. It is covered by `tests/test_emergency.py` only.

**Not built: duplicate detection.** Repeat reports currently stack as
separate jobs. Merging them by similar text within a community would be
wrong exactly when it matters most: after a cyclone, many different houses
send the same message. Merging needs a dwelling or tenancy ID on the report,
then same dwelling plus same fault within a time window.

**Dataset gap:** `fairtriage_v3.csv` contains no storm or cyclone reports, so
the evaluation cannot measure the storm fix. For the Top End that is the most
important category to add in the writing session.

## Known limitations

- **Placeholders:** crew numbers per region, and community coordinates, which are approximate.
- **Estimated distances:** road distance is straight-line times 1.35. Replace with shortest paths over
  the NT Government Controlled Roads KMZ; the column name stays the same.
- **Unverified service targets:** the remote targets (5 and 25 business days) come from a Government
  Employee Housing form. `service_targets_verified: false` in the policy file until checked against the
  Tenancy Management Support Services Handbook.
- **One trade per request:** a report with two faults gets one trade, even if it needs two.
- **Model paths unevaluated:** the OpenAI, Gemini and Claude extractors are written and tested with fake clients, but not evaluated against the live APIs here.
- **No real authentication:** the coordinator identity is a form field.
- **Designed without the communities it concerns.** Before anything like this went near a real dispatch
  queue it would need community consultation, real maintenance data, and governance over who sets the
  weights that does not sit with a student team.
