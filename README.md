# Marswalk Copilot

> **The map tells you where to walk. The copilot tells you when to change course and whether you can still make it back.**

A project for the **NASA Space Apps Challenge 2026**, challenge [Interplanetary Survival Guide: Martian Map](https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/).

Marswalk Copilot is an application for an astronaut on a surface walk (EVA) on Mars, in **Jezero crater**. It has two parts:

1. **A hyperlocal map** of 10 × 10 km, built from data from several NASA missions (MRO, Mars Odyssey, Mars 2020, MSL). The astronaut plans the EVA on it: science targets, route, oxygen, return time and point of no return.
2. **A live copilot** that follows the EVA minute by minute. It scans the surroundings, predicts where hazards will be (dust storms, dust devils, marsquakes, radiation), replans the route and decides: continue, detour, wait or turn back. A local LLM explains each decision to the astronaut.

> **Language:** the application (interface, API messages, LLM explanations) is in English for the international jury. The team's internal notes (role files, `docs/roles/`) are in Romanian.

---

## Contents

1. [Principles](#1-principles)
2. [What the astronaut sees](#2-what-the-astronaut-sees)
3. [Site and data](#3-site-and-data)
4. [How it works](#4-how-it-works)
5. [Safety limits and events](#5-safety-limits-and-events)
6. [Results: benchmark](#6-results-benchmark)
7. [Getting started](#7-getting-started)
8. [API](#8-api)
9. [Repository layout](#9-repository-layout)
10. [Tests](#10-tests)
11. [Desktop app and hosting](#11-desktop-app-and-hosting)
12. [Team and documentation](#12-team-and-documentation)
13. [Known limitations](#13-known-limitations)

---

## 1. Principles

- **The code decides, the LLM explains.** Route, O₂, time, dose and the decision itself are computed deterministically. The LLM receives the situation and the decision already taken, and only writes the reason.
- **The validator has the last word.** No option that breaks a safety limit reaches the astronaut as a normal recommendation.
- **The destination comes first.** When a hazard appears, the copilot first tries to keep every target (detour, wait, step back), then to drop some of them. Going home is the last resort and is not final: if the hazard passes, the EVA resumes.
- **It works without the LLM.** If Ollama does not answer within 3 s, the decision stays the same and the explanation comes from a template.
- **One routing algorithm: the backend.** The frontend does not compute routes. It only displays what the backend plans, with the same limits.

---

## 2. What the astronaut sees

The application has three pages.

### Planning

- A 3D map of the area (USGS CTX relief, vertically exaggerated 6× for readability), with the habitat and the three science targets.
- Click a target or anywhere on the terrain → **Add to trip**. Your own waypoints can be added as well.
- When you click a point, the map shows the route computed by the backend in two variants: **Safety** (penalises slope) and **Minimum time**.
- **The Mission panel**, updated on every change to the itinerary:
  - the GO / CAUTION / NO-GO verdict;
  - the stops, in the order chosen by the planner;
  - O₂ on return, distance, duration;
  - **Return by** (local time on Mars, LTST), the point of no return and the dose.
- Below the map, the route's **elevation and slope profile**.
- **Start simulation** starts the live EVA at 1× speed. While an EVA is running, **End EVA & edit plan** stops it and unlocks the plan.

### Simulation

- **The Scan line:** the result of scanning the surroundings every simulated minute. The states are `clear`, `watch`, `warning` and `danger`, for example "Dust devil 1.1 km away, not on your route: safe to continue."
- **The Copilot card:** the current decision (Continue / Reroute / Wait / Return / Emergency), the LLM's explanation, the compared alternatives and the decision history.
- **Three views:**
  - the map with the astronaut, the remaining route, the hazards and their forecast;
  - a **first-person tracker** (what the astronaut sees ahead);
  - an **EVA watch** with compasses towards the habitat and along the route.
- **Controls:** start, pause, reset, clock speed (1×–60×) and **placing events on the map** (dust devil, dust storm, marsquake, solar particle event, suit leak, fatigue).

### Sensors

A panel with the suit and environment sensors: O₂, radiation dose rate, temperature, pressure, wind, dust opacity.

---

## 3. Site and data

### The area

- **Location:** the delta front in Jezero crater, centred on **18.44° N, 77.45° E**, explored by Perseverance and Ingenuity.
- **Extent:** 10 × 10 km, the range of a realistic walk.
- **Planning grid:** 500 × 500 cells of 20 m (250,000 cells).
- **Science targets** confirmed in the literature:

| Target | What is there | Source |
|---|---|---|
| Clay, delta front (Hawksbill Gap) | Fe/Mg clays in the delta | Goudge et al. 2015 (CRISM) |
| Carbonates, crater margin unit | carbonates on the crater margin | Horgan et al. 2020 |
| Olivine, Séítah (crater floor) | olivine cumulate | Liu et al. 2022 |

- **Real NASA hardware**, as points of interest: the Three Forks sample depot (10 tubes for Mars Sample Return), the Mars 2020 landing hardware, Ingenuity, plus Perseverance's real traverse (306 localised positions).

### Map layers (`data/processed/jezero/`)

| Layer | Data type | Mission / instrument | Role |
|---|---|---|---|
| `elevation` | topographic | MRO HiRISE (5 DTMs, 94% of the area) + CTX | relief, ascent, walking speed |
| `slope` | topographic | HiRISE + CTX (maximum of the 4 m slopes in each cell) | the 20° limit, walking cost |
| `unsafe` | topographic | HiRISE + CTX (slope > 35° at 4 m) | forbidden cells |
| `terrain` | thermal | Mars Odyssey THEMIS night IR + HiRISE roughness | terrain classes: sand, bedrock, boulders |
| `minerals` | spectral | units confirmed by Perseverance (PIXL/SHERLOC) + delta outline; CRISM papers | science targets |
| `radiation` | radiation | altitude model calibrated on MSL RAD | dose integrated along the route |

### Data for the simulation and its calibration

| What | Source |
|---|---|
| Wind, gusts, dust devils | Mars 2020 MEDA (Viúdez-Moreiras 2022, Newman 2022) |
| Pressure, temperature, dust opacity | MEDA, Mastcam-Z, Curiosity REMS |
| Radiation and the solar particle event (dose ×2.5) | MSL RAD (Hassler 2014, Zeitlin 2018), MAVEN |
| Dust storms | MRO MARCI |
| Daylight, local time, sunset | the Mars24 algorithm (NASA GISS) |
| Suited O₂ consumption | Apollo reports (Waligora 1975, NASA TN D-7883) |
| Walking speed vs slope | Tobler's hiking function, with a suit factor |
| "What you will see" images at each target | Perseverance Mastcam-Z (raw images) |

The full list, with links and DOIs: [docs/sources.md](docs/sources.md). Every constant is marked **source** or **assumption** in [docs/how-we-calculate.md](docs/how-we-calculate.md).

---

## 4. How it works

```
pipeline/ (offline, once)                   backend/ (FastAPI)                          frontend/ (React + three.js)
──────────────────────────                  ────────────────────────────────            ────────────────────────────
USGS STAC: HiRISE + CTX DTM ─┐              core/  deterministic algorithms             Planning: 3D map + Mission
THEMIS, mineral units ───────┼─► .npy +     live/  simulation engine (1 tick = 1 min)   Simulation: scan, copilot,
RAD model, Mastcam-Z images ─┘   meta.json  llm/   Ollama: explanations + chat           tracker, EVA watch
                                 (20 m grid) api/  REST + WebSocket  ◄──────────────►   Sensors
                                                    │
                                                    └─► local Ollama (qwen3:4b-instruct)
```

### Phase 1: the data (offline)

`pipeline/` searches USGS STAC for the DTMs and reads only the 10 × 10 km window. It computes slope at full resolution and aggregates it to 20 m, keeping the maximum slope so obstacles are not lost. Then it adds the terrain classes, minerals and radiation. The output (`.npy`, `meta.json`, PNGs, target images) is committed to git. The backend only reads these files and needs no internet access.

### Phase 2: planning

1. **Cost map:** `(1 + slope_k · (slope / 20°)²) × terrain factor + radiation`. Above 20° or on `unsafe` cells the cost is infinite. The preset (Safety / Minimum time / Science value) changes the weights.
2. **Routing:**
   - **A\*** for each segment;
   - **reverse Dijkstra** from the habitat (the cost of returning from any cell, which also gives the point of no return);
   - the **shortest order of the stops**, with CP-SAT (OR-Tools) when a subset of targets must be chosen.
3. **Budget:** time, O₂, dose, return-by time and sunset.
4. **The validator** gives the GO / CAUTION / NO-GO verdict.

Custom waypoints (`custom_stops`) are validated by the backend. A point on forbidden slope, or one that cannot be reached, is rejected with a clear message.

### Phase 3: the live EVA

One **tick = 1 simulated minute**. On every tick the engine:

1. **Moves the astronaut** along the route at Tobler speed and consumes O₂ and dose with the same model as the planner (plan vs live differ by less than 0.2 O₂ points).
2. **Scans the surroundings** (`tick.scan`) and announces every new situation: clear route, a distant hazard that does not reach the route, a hazard on the route.
3. **Forecasts the hazards.** Each hazard (`HazardSpec`) has a shape, velocity, lifetime and effect (blocks its core, or penalises a halo). The forecast reaches 3 hours ahead, with growing uncertainty.
4. **Re-evaluates the route** according to an alert mode: `NOMINAL` (every 15 min), `MONITOR` (5 min), `REACT` and `EMERGENCY` (every minute). It also re-evaluates immediately on a new event or when a hazard is within 450 m.
5. **Generates alternatives:** the current route, detours, waiting in place, stepping back and waiting, leaving the zone, dropping a blocked stop, returning, sheltering.
6. **Validates them and chooses deterministically.**
   - The choice works in tiers: first the options that keep every stop, then those that drop some, and only then the return home.
   - Within a tier, the best score wins.
   - A hysteresis stops the route from changing every minute.
7. **Sends the decision immediately** over the WebSocket. The LLM's explanation arrives separately, 1–3 s later, without blocking the simulation.
8. **Resumes the EVA** when the hazard has passed (`HAZARD_CLEARED`). On the way home, the remaining targets are rechecked every 5 minutes.

### The LLM

- **Model:** `qwen3:4b-instruct`, run locally through Ollama, without thinking mode, at `temperature 0`, with a JSON schema for the answer. Each explanation takes about 1.5–2 s.
- **Input:** short facts (the decision, the hazard and its distance, whether it reaches the route, O₂ on arrival, dose vs the limit).
- **Output:** one sentence of at most 25 words.
- **Cache and fallback:**
  - answers are cached by situation summary, prompt version and model;
  - if the LLM is late, returns invalid JSON or contradicts the decision, the template text is used instead.
- **Chat with tools** for planning (`plan_route`, `oxygen_budget`, `layer_value`, `science_stops`, `daylight`, `eva_status`), available at `POST /api/chat`.

---

## 5. Safety limits and events

### The limits (validator)

| Rule | Limit |
|---|---|
| O₂ on arrival at the habitat | at least **30%** |
| Return | at least **30 min before sunset** (dust brings sunset earlier) |
| Maximum slope on the route | **20°** (NASA lunar EVA concept of operations; Apollo 15 crossed ~17°) |
| Radiation dose per EVA | at most **1 mSv** |
| Hazards | the route does not cross a hazard's core within the forecast window |

The astronaut's rules on one page: [docs/survival-guide.md](docs/survival-guide.md).

### Simulated events

| Event | What it does | Typical copilot response |
|---|---|---|
| `dust_devil` | small moving vortex | detour or wait |
| `local_storm` (dust front) | wide, fast front | wait or step back, then resume |
| `regional_storm` | large storm; covers the whole map only if it is huge | return only if its forecast reaches the route |
| `marsquake` | static zone for 60 min, blocks slopes above 15° | reconfigures the route |
| `solar_particle_event` | dose ×2.5 across the whole site for 4 hours | continue while the dose stays below the limit |
| `suit_leak` | higher O₂ consumption | budget replan, possibly return |
| `fatigue` | slower walking, higher consumption | budget replan |

---

## 6. Results: benchmark

The copilot compared with "the initial plan only", on **100 dust storm scenarios** at Jezero (same storms for both strategies, no LLM, seed 42):

| | Plan only | Copilot |
|---|---|---|
| Home safely | 51% | **81%** |
| Minimum O₂ on arrival | 70% | 60.3% |
| Mean dose | 0.072 mSv | 0.045 mSv |
| Targets visited | 100% | 41% |

The copilot rescued 30 EVAs and made none worse. The price of safety is lost science: it heads home more often.

> These numbers come from `data/processed/jezero/benchmark.json`, measured on 14 Nov, before the latest live replanning changes (destination-first tiers, step back, resume). Rerun with `pipeline/run_benchmark.py`.

---

## 7. Getting started

### Requirements

- **Python 3.11+**, **Node 18+**.
- Optional: **[Ollama](https://ollama.com)** with the model used:

```bash
ollama pull qwen3:4b-instruct
```

### Install and run (Windows, from the repository root)

```powershell
scripts\setup.ps1   # .venv, Python dependencies, npm install, synthetic site
scripts\dev.ps1     # backend :8000 + frontend :5173, in separate windows
```

The app: http://localhost:5173. Backend status: http://localhost:8000/api/health.

### Manually

Backend, from `backend/`:

```bash
../.venv/Scripts/python.exe -m uvicorn app.api.main:app --reload --port 8000
```

Frontend, from `frontend/`:

```bash
npm install
npm run dev
```

### Configuration (backend environment variables)

| Variable | Default | What it does |
|---|---|---|
| `MARSWALK_SITE` | `jezero` | the site: `jezero` (real data) or `synthetic` |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama address |
| `OLLAMA_MODEL` | `qwen3:4b-instruct` | LLM model |
| `LLM_ENABLED` | `1` | `0` = templates only, no LLM |
| `LLM_TIMEOUT_S` | `3` | when to fall back to the template |
| `MARSWALK_SCAN_ANNOUNCE` | `1` | scan announcements ("safe to continue") |
| `MARSWALK_DEMO_EVENTS` | `0` | `1` = the demo scenario's scheduled events |
| `FRONTEND_ORIGINS` | `http://localhost:5173` | allowed origins (CORS) |

The frontend forwards `/api` to `BACKEND_URL` (default `http://localhost:8000`, in `frontend/vite.config.js`).

### Rebuilding the data (optional)

The processed Jezero data is already in the repository. To rebuild it from USGS STAC:
- install `pipeline/requirements.txt`;
- run `pipeline/fetch_stac.py`, then `pipeline/build_layers.py`.

The synthetic site used by the tests is built by `pipeline/make_synthetic_site.py`.

---

## 8. API

| Route | Purpose |
|---|---|
| `GET /api/health` | backend and site status |
| `GET /api/site` | area, habitat, targets, limits, layers with their provenance, NASA hardware, rover traverse |
| `GET /api/layers` | layers (PNG + legend), served from `/static/layers/` |
| `GET /api/point?row=&col=` | values of every layer at a point, with mission and instrument |
| `POST /api/route` | route + budget + verdict; accepts custom waypoints (`custom_stops`) and `preview: true` (not stored for the simulation) |
| `POST /api/chat` | chat with the agent (NDJSON streaming) |
| `WS /api/live` | the live simulation: `state`, `tick` (with `scan`), `event`, `decision` and `explanation` messages |
| `POST /api/live/control` | `start` / `pause` / `reset` / `speed`; a `start` after a finished EVA starts a new one |
| `POST /api/live/event` | inject an event (simple format, or a `HazardSpec` with `op` = `add` / `update` / `remove`) |
| `GET /api/benchmark` | benchmark results and the headline numbers |

The exact shape of every message: the examples in [shared/contracts/](shared/contracts/) and [shared/contracts/README.md](shared/contracts/README.md). The frontend's proposed contract (v1.1): [frontend/contracts/FRONTEND_BACKEND_ALGORITHM.md](frontend/contracts/FRONTEND_BACKEND_ALGORITHM.md).

---

## 9. Repository layout

```
├── pipeline/                 # offline data (role 1)
│   ├── fetch_stac.py         # finds and crops HiRISE + CTX from USGS STAC
│   ├── build_layers.py       # slope, 20 m aggregation, terrain (THEMIS), minerals, radiation
│   ├── fetch_stop_images.py  # Mastcam-Z images of the targets
│   ├── meda_winds.py         # MEDA wind statistics
│   ├── run_benchmark.py      # copilot vs plan benchmark
│   └── make_synthetic_site.py
├── data/
│   ├── processed/jezero/     # .npy, meta.json, PNGs, benchmark.json (in git)
│   └── synthetic/            # synthetic site for the tests
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI: REST + WebSocket (role 3)
│   │   ├── core/             # deterministic algorithms, no server (role 2)
│   │   │   ├── costmap.py, costfield.py   # static and time-dependent cost maps
│   │   │   ├── routing.py, planner.py, stops.py, tour.py   # A*, Dijkstra, CP-SAT, stop order
│   │   │   ├── budget.py, daylight.py, validator.py        # budget, Mars24, hard rules
│   │   │   ├── hazard_spec.py, hazards.py, storms.py, conflict.py   # hazards and forecast
│   │   │   ├── replanner.py, selection.py, modes.py        # live replanning
│   │   │   └── benchmark.py
│   │   ├── live/             # simulation engine, scenario, planning for the API (role 3)
│   │   ├── llm/              # Ollama: prompts, templates, cache, chat with tools (role 3)
│   │   ├── config.py, schemas.py
│   └── tests/
├── frontend/                 # React 18 + Vite + three.js (role 4)
│   ├── src/
│   │   ├── pages/            # Planning, Simulation, Sensors
│   │   ├── components/       # map/, planning/, simulation/, sensors/
│   │   ├── mission/          # state shared by the pages (MissionContext)
│   │   ├── hooks/, api/, terrain/, simulation/, sensors/
│   ├── public/terrain/       # 3D relief model (USGS CTX) and display grid
│   ├── desktop/              # Electron app for Windows
│   ├── contracts/            # frontend ↔ backend contract v1.1
│   └── tests/, e2e/
├── shared/contracts/         # JSON examples of the API and live messages (also the mocks)
├── docs/                     # sources, calculations, survival guide, demo, slides, roles
└── scripts/                  # setup.ps1, dev.ps1, llm_bench.py
```

- `core/` is separate from `api/`: the algorithms are pure Python functions, testable without a server.
- `shared/contracts/` fixes the shape of the JSON messages. If the backend does not answer, the frontend shows these examples, labelled "DEMO DATA".

---

## 10. Tests

Backend, from `backend/`:

```bash
../.venv/Scripts/python.exe -m pytest
```

The tests run on the synthetic site, without the LLM (`tests/conftest.py`).

Frontend unit tests (Node), from `frontend/`:

```bash
node --test tests/
```

`frontend/e2e/` holds a Playwright test, which needs Playwright installed and the app running.

---

## 11. Desktop app and hosting

**Desktop (Windows, Electron)**, from `frontend/`:
- `npm run desktop` builds the interface and opens it in its own window;
- `npm run desktop:package` produces `release/Marswalk-win32-x64/Marswalk.exe`.

The backend stays a separate process, set through `BACKEND_URL`. Details: [frontend/desktop/README.md](frontend/desktop/README.md).

**Hosting with the local LLM:** everything runs on the laptop that has Ollama. Only the built frontend is published, through a tunnel (for example Cloudflare Tunnel to `vite preview`), and it forwards `/api` and the WebSocket to the local backend.
- The 3D relief model is ~34 MB, so the first load depends on the laptop's upload speed.
- For public access, a named tunnel with caching on `/terrain/*` is recommended.

---

## 12. Team and documentation

| Role | Folders | Responsibilities |
|---|---|---|
| **1. Data & presentation** | `pipeline/`, `data/`, `docs/` | NASA data, layers, scenario calibration, sources, slides, video |
| **2. Algorithms** | `backend/app/core/` | cost map, routing, hazards, budget, validator, replanning, benchmark |
| **3. Backend & LLM** | `backend/app/api/`, `live/`, `llm/` | API, WebSocket, live engine, scanning, Ollama, prompts, integration |
| **4. Frontend** | `frontend/` | 3D map, planning, simulation, tracker, watch, sensors, desktop app |

| Document | Contents |
|---|---|
| [docs/sources.md](docs/sources.md) | every data source and paper, with links |
| [docs/how-we-calculate.md](docs/how-we-calculate.md) | formulas and constants, each marked source / assumption |
| [docs/survival-guide.md](docs/survival-guide.md) | the astronaut's rules, on one page |
| [docs/hazards-research.md](docs/hazards-research.md) | research on the hazards |
| [docs/demo.md](docs/demo.md), [docs/slides.md](docs/slides.md), [docs/pitch.md](docs/pitch.md) | demo, slides, pitch |
| [docs/RAPORT_PANTA_20.md](docs/RAPORT_PANTA_20.md) | check of the 20° slope limit (Romanian) |
| [docs/plan-replanificare-live.md](docs/plan-replanificare-live.md) | live replanning plan (Romanian) |
| [docs/roles/](docs/roles/README.md) | instructions per role, routing architecture V2, reference parameters, work notes (Romanian) |

---

## 13. Known limitations

- **Layers in the interface.** The map shows relief and slope, but not the minerals, terrain and radiation layers, even though the backend serves them (`/api/layers`). The slope shown and the elevation profile are computed on the frontend's display grid, not on the backend's slope layer.
- **Backend features not yet shown in the interface:**
  - the Mastcam-Z images of the targets;
  - the chat with the agent;
  - the values at a clicked point (`/api/point`);
  - the benchmark;
  - the "Houston vs copilot" counter (`compute_ms`);
  - the survival guide.
- **One simulation per server.** Everyone connected to the same backend sees and controls the same EVA.
- **Starting without a plan.** A `start` with no `route_id` and no planned route uses the example route from the contract. The interface always sends the planned route.
- **The marsquake zone is only penalised on flat ground**, not blocked, so the copilot may cross it.
- **The scenarios are simulated**, calibrated on MEDA, REMS and RAD, not live data from Mars.
- **The benchmark should be rerun** after the latest live replanning changes (see section 6).
