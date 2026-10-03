# FairTriage NT

**Fair, explainable triage of housing repairs for Northern Territory communities.**

A tenant describes a fault in their own words, in plain, hurried or
second-language English. FairTriage works out what is observably wrong, decides
how urgent it is, estimates when a tradesperson can come, and explains all of it
to the tenant and to staff. Maintenance crews get recommended trips that fix as
many repairs as they safely can on the way. **A person approves every decision.**

Built for the CDU IT Code Fair, Trusted AI decision-support challenge.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-database-47A248?logo=mongodb&logoColor=white)
![Tests](https://img.shields.io/badge/tests-507%20passing-2f6b4f)

---

## What it does

**For tenants**
- Report a repair in your own words, with your address. At most **one**
  clarifying question, and only when the answer changes the priority
  ("Is this the only toilet in the house?").
- A clear answer that starts with **when to expect someone**, then why the job
  has its priority, your place in the queue, and how to stay safe while you wait.
- A danger like fire or someone hurt is told to **call 000 first**, before
  anything else.
- Track the repair by reference number, including the trip that will reach you.

**For staff**
- A live, ranked queue with an **area-by-area chart** of open repairs by
  priority (click an area to filter), search, a "needs a phone call" list,
  and **CSV / Excel download**.
- Each job shows the arithmetic behind its priority, flags that need a person,
  and exactly what the tenant was told. Approve, change the tier (with a reason
  the tenant sees), or ask for more information.
- A **trip planner** with a map: routes to remote communities, stops added on
  the way, expected arrival for every tenant, and why each trip is worth
  approving (repairs covered, travel saved, tenants reached sooner).
- **Approved trips** with live counts (active, completed, cancelled). Cancel an
  approval or take one job off a trip (with a reason): the jobs go back to the
  queue as before. Mark a trip completed when the crew is done. Every change
  is kept in the trip's history.
- **Fairness measurements** computed from the live queue.

## Principles

1. **Danger first.** Anything that can hurt someone today (sparking, gas,
   sewage inside, a house that cannot be locked) is made safe before anything else.
2. **Where you live never changes your place in the queue.** Distance changes
   *when* a crew can arrive, never *where* a job ranks. The ranking code has no
   distance variable, and every job shows the rank it would have in Darwin.
3. **Every decision is explainable.** Priorities are plain arithmetic over
   facts a person can check. Tenant messages are checked before they are shown:
   no invented numbers, no promises.
4. **Ask, don't guess.** If one missing fact would change the outcome, the
   system asks one question and waits.
5. **Nothing dispatches itself.** The system recommends; staff decide.

## How it works

```mermaid
flowchart LR
    T[Tenant report] --> N[Spelling normaliser]
    N --> R["Reader<br/>(triage engine or AI model)"]
    R --> F["Six checkable facts<br/>danger, essential service, extent..."]
    F -->|decisive fact missing| Q[Ask one question]
    Q --> R
    F --> P["Policy<br/>tier + need score"]
    P --> W[Wait estimate]
    P --> X[Explanation + verifier]
    W --> X
    X --> DB[(MongoDB)]
    DB --> S[Staff queue]
    DB --> TP["Trip planner<br/>routes, stops, arrivals"]
    S --> H{Staff decision}
    TP --> H
```

- **Reading.** Messages are read by the offline FairTriage triage engine by
  default: instant, and it works without internet. An AI model (Gemini, OpenAI
  or Claude) can be switched on; if it is slow or unavailable, the engine
  answers within 12 seconds and the job is flagged for review.
- **Ranking.** A strict tier ladder (Immediate, then Urgent, then Routine),
  then a need score within the tier from habitability, extent, containment
  and vulnerability.
- **Waiting.** Booking lead time, plus the hours of same-trade work ranked
  ahead in the region divided by that trade's crews, plus mobilisation and
  travel to remote communities. Remote routine jobs wait for the next trip.
  Recalculated live, so the queue and the tenant's page count down.
- **Trips.** The fastest route and slower alternatives over an NT road network
  (closed roads removed, restricted roads slowed). Jobs on the way are added
  in need order, never quickest first, only while nobody is made to wait
  too long.
- **Trip cost.** Each recommended trip shows a probable cost range: fuel,
  vehicle running costs and charter flights; accommodation, meals, freight
  and local vehicle hire; labour for every person for travel and on-site
  hours; parts and a stated contingency. Shown for budgeting and compared
  with separate trips, never used to decide who is served.

The full design, test findings and evaluation are in
**[docs/DESIGN.md](docs/DESIGN.md)**.

## Tech stack

| Part | Technology |
|---|---|
| Backend API | Python 3.10+, FastAPI, Pydantic |
| Request pipeline | LangGraph (the clarifying-question pause is stored in MongoDB) |
| Database | MongoDB (pymongo); in-memory mongomock for tests |
| Routing | networkx over `reference/road_network.csv` |
| Web app | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, SWR |
| Map | Leaflet + OpenStreetMap |
| Optional AI readers | Gemini, OpenAI, Anthropic Claude (structured output, temperature 0) |

## Getting started

### Prerequisites

- **Python 3.10+** and **Node.js 20+**
- **MongoDB**, one of:
  - [MongoDB Community Server](https://www.mongodb.com/try/download/community)
    installed on your computer ("Install as a service"), or
  - a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster (use its
    `mongodb+srv://...` connection string), or
  - Docker: `docker compose up` starts MongoDB and the backend together.

### 1. Clone

```bash
git clone https://github.com/ShougataDas/Fairtriage-NT.git
cd Fairtriage-NT
```

No settings file is needed: the defaults work with a local MongoDB and no API
keys. To change a setting, create a file named `.env` in this folder (it is
never committed) with any of the variables under [Configuration](#configuration).

### 2. Backend

```bash
pip install -r requirements-dev.txt
python scripts/seed_demo.py
python -m uvicorn fairtriage.api:app --reload --port 8000
```

`seed_demo.py` fills the database with about 100 realistic demo requests
(it empties the database first). At most 8 Immediate jobs are left open, a
few hours old; the rest are recorded as already made safe. Demo data ages
as the days pass, so seed again before a demo.

### 3. Web app (in a second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**.

| Page | Who | What |
|---|---|---|
| `/report` | Tenants | Report a repair |
| `/track/<reference>` | Tenants | Progress, explanation, trip update |
| `/coordinator` | Staff | Ranked queue, phone list, CSV / Excel download |
| `/coordinator/requests/<id>` | Staff | Priority breakdown, flags, decision |
| `/coordinator/trips` | Staff | Trip planner with map |
| `/coordinator/fairness` | Staff | Fairness measurements |

The web app calls the backend through `/api`. To use a backend somewhere
else, set `FAIRTRIAGE_API=https://your-backend` before `npm run dev` or
`npm run build`.

With `make` installed (macOS / Linux), `make demo` and `make web` do steps 2
and 3.

## Configuration

Settings are read from environment variables, or from a `.env` file in the
project folder. `.env` is ignored by git, so keys never reach the repository.
For example:

```
FAIRTRIAGE_MONGO_URL=mongodb+srv://user:password@cluster0.example.mongodb.net
FAIRTRIAGE_EXTRACTOR=keyword
```

| Variable | Default | Purpose |
|---|---|---|
| `FAIRTRIAGE_MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection string (Atlas: `mongodb+srv://...`) |
| `FAIRTRIAGE_MONGO_DB` | `fairtriage` | Database name |
| `FAIRTRIAGE_EXTRACTOR` | `keyword` | Who reads messages: `keyword` (offline engine), `gemini`, `openai`, `anthropic` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | empty | Key for the chosen AI reader |
| `FAIRTRIAGE_GEMINI_MODEL` / `_OPENAI_MODEL` / `_ANTHROPIC_MODEL` | `gemini-3.1-flash-lite` / `gpt-4.1-mini` / `claude-haiku-4-5-20251001` | Override the model name |
| `FAIRTRIAGE_LLM_BUDGET_S` | `12` | Longest a tenant waits for a model before the engine answers |

Every ranking weight, service target, wait assumption and trip rule is in
[`config/policy.yaml`](config/policy.yaml), versioned, and shown on screen
where it is used.

## Tests

```bash
python -m pytest tests/ -q
python scripts/run_scenarios.py
python scripts/run_eval.py
```

The first runs 507 tests on an in-memory database, so no server is needed.
The second runs the 16 demo scenarios in [TEST_CASES.md](TEST_CASES.md). The
third scores reading against the 12,000-row dataset in `data/`.

To run the same tests against a real MongoDB, set
`FAIRTRIAGE_TEST_MONGO_URL=mongodb://localhost:27017` first.

The suite covers about 100 maintenance scenarios (electrical, gas, water,
sewage, storm, structural, security, falls, asbestos, remote water supply,
appliances, pests and more), emergencies, hedged and second-language
wording, fairness (rank never depends on location), the trip planner's rules,
the API and the exports.

## API

JSON endpoints under `/api` (interactive docs at `http://localhost:8000/docs`):

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/requests` | Lodge a report `{text, community, address, phone?, vulnerability[]}` |
| POST | `/api/requests/{id}/clarify` | Answer the clarifying question |
| GET | `/api/requests/{id}` | Full record: assessment, history, trip |
| POST | `/api/requests/{id}/decision` | Approve, override (with reason) or request info |
| GET | `/api/queue` | Ranked queue (`?tier=`, `?community=`, `?order=cost` for contrast) |
| GET | `/api/export` | Download `?format=csv\|xlsx&scope=queue\|all` |
| GET | `/api/trips/preview` | Recommended trips with routes, map coordinates and benefits |
| POST | `/api/trips/plan` | Approve all trips, or one with `?anchor=<id>` |
| GET | `/api/trips` | Approved trips with status and history |
| POST | `/api/trips/{id}/cancel` | Withdraw an approval `{reason}`: jobs return to the queue |
| POST | `/api/trips/{id}/remove` | Take one job off a trip `{request_id, reason}` |
| POST | `/api/trips/{id}/complete` | Mark the trip's jobs completed |
| GET | `/api/metrics/equity` | Fairness measurements |
| GET | `/api/health` | Service, database and reader status |

## Project structure

```
fairtriage/          Python backend
  api.py             HTTP API (and the original server-rendered pages)
  extract.py         Readers: offline triage engine, Gemini / OpenAI / Claude
  normalise.py       Spelling normaliser that never touches hazard words
  graph.py           LangGraph pipeline with the clarifying-question pause
  policy.py          Tier and need score: pure arithmetic, no model
  wait.py            Wait estimates
  explain.py         Tenant and staff explanations, and their verifier
  scheduler.py       Trip planner
  routing.py         Road network and alternative routes
  db.py              MongoDB storage with append-only history
  export.py          CSV and Excel export
  metrics.py         Fairness measurements
frontend/            Next.js web app (presentation only; calls the API)
config/policy.yaml   Every weight and threshold
reference/           Communities, road network, crews, road status
scripts/             Seeding, evaluation, scenario runner, data builders
tests/               507 tests
docs/DESIGN.md       Design notes, test findings, evaluation
```

## Deployment (Vercel)

The backend and the web app deploy as **two Vercel projects from this one
repository**, with the data in **MongoDB Atlas**.

**1. Database: MongoDB Atlas (free)**
- Create a free cluster and a database user.
- Under *Network Access*, allow `0.0.0.0/0`: Vercel functions have no fixed IP address.
- Copy the connection string (`mongodb+srv://...`).
- Optionally fill it with demo data from your own computer:
  `FAIRTRIAGE_MONGO_URL="mongodb+srv://..." python scripts/seed_demo.py`

**2. Backend project**
- *New Project* → import this repository. Root Directory `./`, preset
  **FastAPI**. It finds the app through `app.py`.
- Environment variable: `FAIRTRIAGE_MONGO_URL` = your Atlas string. Add
  `FAIRTRIAGE_EXTRACTOR` and a key only if you switch an AI reader on.
- Deploy, then open `https://<backend>.vercel.app/api/health`: it should
  report `"database": "connected"`.

Vercel installs only `requirements.txt` (the server, about 210 MB). Tests,
seeding and evaluation use `requirements-dev.txt`. `.vercelignore` leaves the
web app, tests and dataset out of the backend bundle.

**3. Web app project**
- *New Project* → import the same repository again. Root Directory
  **`frontend`**, preset **Next.js**.
- Environment variable: `FAIRTRIAGE_API` = `https://<backend>.vercel.app`
  (no trailing slash). The `/api` proxy is fixed at build time, so redeploy
  after changing it.

## Limitations

- **Placeholder data:** crew numbers and their split by trade, booking lead
  times, mobilisation times and community
  coordinates are placeholders; road distances and speeds are approximate.
  Remote service targets are unverified (see `config/policy.yaml`).
- **No sign-in yet:** anyone who can reach the staff pages can act on them.
- **AI readers not evaluated live:** they are tested with stand-ins for the
  APIs, not against the live services.
- **Designed without the communities it concerns.** Before real use it would
  need community consultation, real maintenance data, and governance over who
  sets the weights.

More in [docs/DESIGN.md](docs/DESIGN.md#known-limitations).
