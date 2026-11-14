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

## În lucru

## Cereri

- **Rolul 1:** când `scenario.generate` e gata, motorul îl folosește automat (`generate(seed, 720, None)`; `Scenario.events` înlocuiesc `DEMO_SCENARIO_EVENTS`).

## Presupuneri

Constantele din `app/live/engine.py` (de documentat de rolul 1 în `docs/how-we-calculate.md`):

| Constantă | Valoare | Ce înseamnă |
|---|---|---|
| `WALK_WATTS` | 220 W | putere metabolică suplimentară la mers în costum; dă ~0,25% O₂/min la mers față de 0,12% în repaus |
| `SUIT_LEAK_PCT_PER_MIN` | 0,15 %/min | consum suplimentar la o scurgere în costum |
| `FATIGUE_SPEED_FACTOR` / `FATIGUE_O2_FACTOR` | 0,8 / 1,15 | efectul oboselii |
| `SOLAR_DOSE_MULTIPLIER`, `SOLAR_DURATION_MIN` | ×20, 60 min | furtuna solară |
| `DEFAULT_WAIT_MIN` | 30 min | cât durează varianta WAIT în fallback |
| `HAZARD_DEFAULTS` | vezi codul | mărimea și viteza pericolelor injectate fără parametri |
