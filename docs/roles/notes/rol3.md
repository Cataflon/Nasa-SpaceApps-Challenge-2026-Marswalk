# Note rolul 3

## Gata

- `llm/summary.py`: `build_summary(decision, t_min=, hazard_kind=, eta_hazard_min=)` produce rezumatul pentru `explain()`. Cifrele sunt rotunjite (cheie de cache stabilă), alternativa aleasă e mereu în enum, iar `"none"` se folosește când nu există rută. Teste: `tests/llm/test_summary.py`.
- `POST /api/route`: validează startul (în grilă), țintele (cunoscute, cel puțin una), apoi apelează `planner.plan_route`. Cade pe mock (`X-Mock: 1`) dacă situl lipsește sau planner-ul aruncă `NotImplementedError`; un `ValueError` din planner devine 422. Fiecare traseu primește `route_id` = `plan_N` de la API (suprascrie ce întoarce planner-ul) și e salvat în `app/live/store.py` (`routes.get(id)`, `routes.latest()`) pentru motorul live. Teste: `tests/api/test_route.py`.
- **Motorul live** (`app/live/engine.py`, singleton `engine`):
  - `step()` sincron (1 minut simulat) + `run()` în fundal, pornit din lifespan. Explicațiile rulează separat (`asyncio.create_task`), decizia pleacă imediat.
  - Evenimente: `local_storm`, `dust_devil`, `regional_storm`, `marsquake` (pericole pe hartă), `solar_particle_event` (doză ×20, 60 min), `suit_leak` (+0,15% O₂/min), `fatigue` (viteză ×0,8). Fără `params`, o furtună mobilă e plasată lateral și ajunge pe traseu exact când trece astronautul.
  - Sfârșit: evenimentele `egress_complete`, `o2_depleted`, `time_limit` (tip `event`, `severity: "info"`).
  - O decizie nouă se trimite doar dacă diferă de precedenta; un pericol care lovește încă traseul se reevaluează cel mult o dată la 5 min.
  - Teste: `tests/live/test_engine.py`, `tests/api/test_live_api.py`.
- `POST /api/live/control` (`start` cu `route_id` și `speed` opționale, `pause`, `reset`, `speed`) și `POST /api/live/event`, legate de motor. `start` fără `route_id` folosește ultimul traseu planificat, iar dacă nu există, traseul mock din contract.
- `LIVE_MOCK=1` face ca WebSocket-ul să redea `live_messages.json` în buclă, ca înainte.

**Pentru rolul 2:**
- Planner-ul poate arunca `ValueError("message in English")` când o țintă e inaccesibilă; mesajul ajunge la utilizator ca 422.
- Motorul apelează exact semnăturile existente: `hazards.from_contract(dict, cell_size_m, t)`, `hazards.to_contract(hazard, t, cell_size_m)`, `hazards.route_hit(path, eta, [hazard], cell_size_m)` (câte un pericol pe apel, ca să știe care lovește), `alternatives.generate(site, pos, remaining, stop_ids, hazards, t, o2, dose, sunset, preset)`. Până le implementezi, motorul are fallback: mișcare liniară, elipsă care crește cu orizontul și doar alternativele `current`, `wait`, `return` (deci fără ocoliri: decizia e RETURN sau WAIT).
- `from_contract` primește un pericol **fără** `forecast` (doar starea curentă).

**Pentru rolul 4:**
- WebSocket-ul nu mai trimite nimic până la `POST /api/live/control {"action": "start"}`. Butonul „Pornește ieșirea” trebuie să apeleze întâi ruta de control, apoi să deschidă WebSocket-ul (sau invers: la conectare primești imediat ultimul `tick`, dacă există).
- `speed` = minute simulate pe secundă reală (implicit 10). Pentru demo merge bine 10-20.

- **Ollama real, legat:** modelul implicit e `qwen3:4b-instruct` (`config.py`), cererile au `think: false`, promptul cere text simplu, fără emoji. Măsurat pe laptopul cu RTX 4050 (`scripts/llm_bench.py --repeat 2`, 20 de situații din `app/llm/samples.py`): încărcare 7,9 s; p50 1,31 s · p95 1,46 s · max 1,50 s; 40/40 de la LLM; 0 emoji; medie 16 cuvinte. Determinism: 15/20 situații dau același text la repetare (variația vine de pe GPU; cache-ul face demo-ul reproductibil).
- **Promptul de explicații, v2** (`app/llm/prompts.py`, `PROMPT_VERSION = 2`): modelul primește fapte formulate (acțiunea pe primul rând, unități, coduri traduse în cuvinte), nu JSON brut, plus 4 exemple de răspuns bun (REROUTE, RETURN, WAIT, EMERGENCY). Cache-ul de explicații depinde de versiunea promptului și de model. Măsurat pe `qwen3:4b-instruct`, 20 de situații: toate încep cu acțiunea corectă și au cifrele corecte; p50 1,85 s · p95 2,17 s · max 2,24 s (exemplele lungesc promptul; v1 era ~1,3 s); medie 21 de cuvinte, max 25.
- Teste pe Ollama real: `tests/llm/test_ollama_live.py`, marcate `ollama` (`pytest -m ollama`), sărite automat dacă Ollama nu rulează.
- **Chatul** (`POST /api/chat`, NDJSON după `chat_stream.json`; `app/llm/chat.py` + `app/llm/tools.py`):
  - Unelte: `plan_route`, `oxygen_budget`, `layer_value`, `science_stops`, `daylight`, `eva_status`. Toate cifrele vin din cod; planificarea folosește același serviciu ca `POST /api/route` (`app/live/planning.py`), deci un traseu planificat din chat poate fi pornit direct cu `/api/live/control start`.
  - Cu Ollama: tool calling real, în streaming, cel mult 3 runde de unelte, timeout 30 s. Fără Ollama: fallback pe cuvinte-cheie, cu aceleași unelte și răspunsuri din șabloane.
  - Linia `done` are în plus `source`: `"llm"` sau `"fallback"`.
  - Măsurat pe `qwen3:4b-instruct`, 8 întrebări: unealta corectă la toate (după ajustarea descrierilor), 1-3 s total, întrebările vagi primesc o întrebare de clarificare.
  - Teste: `tests/llm/test_chat.py` (Ollama simulat), `tests/api/test_chat_api.py`.

**Pentru rolul 4 (chat):** citește răspunsul linie cu linie (`fetch` + `ReadableStream`). `tool_call` → etichetă „Planning route…”, `route` → desenezi traseul pe hartă (are `route_id`, deci „Start EVA” îl poate porni), `token` → text adăugat, `done` → final.

## În lucru

## Cereri

- **Rolul 2, ocolirile live (testat pe 14.11 după merge):** motorul folosește acum `alternatives.generate` real, dar pe situl sintetic decizia nu e niciodată REROUTE. Exemple (traseu real spre `clay_delta`, pericol injectat la minutul 5):
  - `dust_devil` → toate alternativele au `HAZARD`, inclusiv `return` → EMERGENCY;
  - `marsquake` → `detour_west` are `HAZARD` și doar +1 min față de traseul curent → RETURN;
  - `local_storm` implicit (semiaxe 1,8 × 1,1 km) → nu se generează nicio ocolire.
  Cauze probabile: (1) ocolirile din A\* spațiu-timp sunt aproape identice cu traseul curent (+1-3 min), deci trec tot prin pericol; (2) conul de predicție crește foarte repede (`SIGMA_REL` 0,35 → la un dust devil de 3 m/s semiaxele cresc cu 63 m/min, deci peste 10 min orice traseu din zonă „trece prin pericol”). Pentru demo avem nevoie de cel puțin un caz în care o ocolire e validă.

- **Rolul 1:** când `scenario.generate` e gata, motorul îl folosește automat (`generate(seed, 720, None)`; `Scenario.events` înlocuiesc `DEMO_SCENARIO_EVENTS`).

## Presupuneri

Constantele din `app/live/engine.py` (de documentat de rolul 1 în `docs/how-we-calculate.md`):

| Constantă | Valoare | Ce înseamnă |
|---|---|---|
| `WALK_WATTS` | 220 W | putere metabolică suplimentară la mers în costum; dă ~0,25% O₂/min la mers față de 0,12% în repaus |
| `SUIT_LEAK_PCT_PER_MIN` | 0,15 %/min | consum suplimentar la o scurgere în costum |
| `FATIGUE_SPEED_FACTOR` / `FATIGUE_O2_FACTOR` | 0,8 / 1,15 | efectul oboselii |
| `SOLAR_DOSE_MULTIPLIER`, `SOLAR_DURATION_MIN` | ×2,5, 240 min, luate din `scenario.SOLAR_PARTICLE_EVENT` (🆕 rolul 1, 14.11; rampa vine din scenariu) | furtuna solară |
| `DEFAULT_WAIT_MIN` | 30 min | cât durează varianta WAIT în fallback |
| `HAZARD_DEFAULTS` | vezi codul (🆕 rolul 1, 14.11: vârtej 130 m, front 30 × 5 km la 15 m/s; vezi notes/rol1.md, „Registrul aplicat”) | mărimea și viteza pericolelor injectate fără parametri |
