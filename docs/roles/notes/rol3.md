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

### Sesiunea din 14.11: cererile rolului 2 aplicate în API și în motor (făcut de rolul 2, cu acordul utilizatorului)

- Cererea „Rolul 1: când `scenario.generate` e gata”: **rezolvat** (verificat în această sesiune):
  `engine.load` folosește `scenario.generate(seed, 720, demo_events(site_id))`, iar senzorii vin din
  scenariu.
- `POST /api/route`: `plan_route` aruncă acum `ValueError` cu mesaje în engleză (start în afara grilei,
  start sau țintă din care nu se ajunge la habitat), verificate din `cost_to_home` înainte de `astar`;
  ruta le dă mai departe ca 422. `point_of_no_return` null rămâne null (test).
- Motorul (`live/engine.py`): `alternatives.generate` se cheamă doar pentru un contact în ≤ 30 min
  (`benchmark.REACT_WINDOW_MIN`). După o decizie RETURN traseul e definitiv (`committed_return`): fără
  `generate`; o furtună „doar RETURN” apărută după aceea primește o decizie de confirmare RETURN pe
  același drum (`_confirm_return`, validată; EMERGENCY dacă drumul nu mai respectă limitele).
  EMERGENCY nu blochează replanificarea. Teste noi în `tests/live/test_engine.py` (3).
- Lifespan: thread daemon de încălzire (`warm_up_core`: import OR-Tools, un `plan_route`, un
  `generate`) și pornirea benchmark-ului. `GET /api/benchmark`: `api/bench_cache.py`, calculat o dată
  într-un proces separat (pornit dintr-un thread), 503 + `Retry-After` până e gata, apoi din cache,
  500 la eroare. `MARSWALK_WARMUP=0` / `MARSWALK_BENCHMARK_AT_STARTUP=0` le opresc. Teste:
  `tests/api/test_core_integration.py`.
- Scena demo are acum 4 decizii (30 REROUTE, 80 EMERGENCY, 90 RETURN `exit_zone`, 125 RETURN);
  testul Jezero din `tests/scenario` e actualizat, plus unul nou pe situl sintetic.

- **Mesaj nou pe WebSocket, `state`** (14.11): `{"type": "state", "state": "idle|running|paused|finished", "t_min", "speed", "route_id", "reason"}`. Se trimite la conectare (primul mesaj), la start / pauză / reluare / reset / schimbarea vitezei și la final (`reason`: `egress_complete`, `o2_depleted`, `time_limit`; `error` dacă motorul a crăpat și s-a pus pe pauză).
- **`compute_ms`** în mesajul `decision`: cât au durat alternativele + regula, în ms. Doar pentru afișare.
- **`GET /api/benchmark`**: rămâne varianta rolului 2 (`api/bench_cache.py`, pornit la startup, 503 + `Retry-After` până e gata, cu `headline`). Varianta mea (`live/benchmark_cache.py`) a fost scoasă la merge, ca să nu existe două.
- **`GET /api/point`** are acum `sources`: pentru fiecare strat, `mission`, `instrument`, `data_type`, `source` (`nasa` sau `assumption`), `analog_of`, `derived`, din `meta.json`. Pe situl sintetic e `{}`.

- **Replanificarea live** (14.11, `app/live/replan.py` + motorul; plan și rezultate în `docs/plan-replanificare-live.md`):
  - **Când replanifică:** la fiecare tick există un watchdog; replanifică imediat la eveniment, la 5 min periodic și la apropierea unui pericol.
  - **Candidații** sunt trasee complete (poziție → ținte → habitat) care ocolesc pericolul pe ambele drumuri.
  - **Alegerea** pune destinația întâi; RETURN rămâne doar dacă nicio variantă care atinge țintele nu e validă.
  - **Rezultat:** la un cutremur pe traseu, decizia e acum REROUTE, nu RETURN.
  - **Câmpuri noi în `decision`:** `trigger` (`event` / `hazard` / `budget` / `proximity` / `periodic`) și `route_version`. `hazard_id` și `eta_hazard_min` pot fi `null` la o replanificare de buget.
  - **Câmp nou în `tick`:** `route_version`.
  - **Coduri noi în `reason_code`:** `BETTER_ROUTE`, `LIMITS_EXCEEDED`, `HYSTERESIS`.
  - **După merge-ul cu rolul 2 (14.11):** motorul cheamă `replan.py`, nu `alternatives.generate`.
    - `REACT_WINDOW_MIN` (30 min) se păstrează doar pentru watchdog-ul de pericol;
    - `committed_return` + `_confirm_return` se păstrează pentru furtuna regională (confirmare RETURN fără replanificare);
    - alte pericole apărute pe drumul spre casă se replanifică la fel ca la dus (cerința echipei: ocolire dacă O₂ permite);
    - cele 3 teste T6d ale rolului 2 din `test_engine.py` sunt adaptate la `replan.candidates`; testul „generate doar în fereastra de 30 min” e înlocuit, pentru că evenimentele noi se replanifică imediat.

**Pentru rolul 4:**
- când `tick.route_version` crește, traseul activ s-a schimbat: `remaining_path` e deja cel nou; traseul vechi se poate șterge sau estompa;
- ascultă `type === "state"`: `running` → butonul „Pause EVA”; `paused` → „Resume”; `finished` → „Restart” + motivul; `idle` → „Start EVA”;
- contorul „Pământul vs. copilotul”: `decision.compute_ms` față de `site.earth_delay_min.round_trip`;
- cifra de titlu: `GET /api/benchmark` → `headline` (503 + `Retry-After` cât rulează; arată un loader);
- popup-ul de la click: `sources[strat].instrument · sources[strat].mission`, iar dacă `source === "assumption"`, scrie „model”.

- **Compatibilitate cu frontendul final (P1, 14.11)**, după `frontend/contracts/FRONTEND_BACKEND_ALGORITHM.md` §5, §7, §8, §10:
  - **`POST /api/live/event`:**
    - parametrii se validează pe tipul evenimentului (`schemas.EVENT_PARAMS`): centru în grilă, semiaxe 1–100 000 m, unghi 0–360°, intensitate 0–1, viteză ±100 m/s, multiplicator de doză 1–100, durată 1–10 080 min, scurgere 0,001–10 %/min, factor de oboseală 0,01–1;
    - cheile necunoscute → 422;
    - fără misiune activă (`running` / `paused`) → **409**;
    - răspunsul are în plus `params`, adică parametrii efectivi primiți de motor.
  - **`POST /api/live/control start`:**
    - după `finished` → **409** până la reset;
    - cu un `route_id` cât rulează sau e pe pauză → **409** (un plan nou nu înlocuiește în tăcere o misiune în curs);
    - `start` fără `route_id` pe pauză reia, ca înainte.
  - **`POST /api/route`:** `max_duration_min` ≤ 720 (orizontul motorului) și `start_time_min` ≥ 0, altfel 422.
  - **Erorile 422** au `detail` **text** (de exemplu `params.axes_m.0: Input should be greater than or equal to 1`), plus lista originală în `errors`.
  - **Situl implicit e `jezero`** (`config.py`); testele rămân pe situl sintetic prin `tests/conftest.py`.
  - **Teste adaptate:**
    - `tests/contracts/test_contracts_requests_enums.py`: evenimentul din contract se injectează după start;
    - `tests/regression/test_reg_live.py`: xfail-ul AUDIT-004 (centru aberant) e scos, pentru că e reparat.

**Pentru rolul 4 (după P1):**
- formularul de plan permite 1440 min, dar backendul acceptă maximum **720** (eroare 422 cu textul limitei);
- mesajul WebSocket `{"type": "state", …}` e trimis, dar `client.js:101` îl filtrează: fără el, butonul rămâne blocat la finalul EVA;
- la 409 pe `start` sau `event`, `detail` spune ce trebuie făcut („Reset the mission…”, „Start the mission before injecting events.”).

### Arhitectura de rutare V2 în motor și în API (făcut de rolul 2, cu acordul utilizatorului)

- `live/engine.py` folosește pipeline-ul V2 din core (`core/replanner.plan`), nu `live/replan.py`.
- Faza drumului `phase` (OUTBOUND / INBOUND), separată de modul de alertă `mode` (NOMINAL / MONITOR /
  REACT / EMERGENCY, K 15 / 5 / 1 / 1 din `core/modes.py`); `mode` în `tick`, `phase` / `flags` /
  `omitted` în `decision` (adăugate și în `live_messages.json`).
- Eliminate: regula „după RETURN nu mai replanifici” (`committed_return`, `_confirm_return`); drumul spre
  casă se replanifică la fel ca la dus. Nivel 3: pericol adăugat / actualizat / șters, eveniment de stare,
  intrare în amprentă; reutilizare după hash-ul stării canonice; evenimente în ordinea (t, seq).
- `step()` rulează pe un thread în `run()` (AUDIT-008 reparat), comenzile iau un `RLock`.
- `POST /api/live/event`: formatul vechi (cu validarea parametrilor: AUDIT-004 reparat) și HazardSpec cu
  `op` add / update / remove (`live_event.json` → `_hazard_spec_example`), ambele cu validarea
  de mai sus și 409 fără misiune activă. Evenimente noi:
  `crewmate_injured`, `comm_loss`, `custom`.
- `REPLAN_EVERY_MIN` și `PROXIMITY_M` au plecat din motor (K pe mod și `core_modes.PROXIMITY_M`).

- **O₂ și viteza în motor = modelul planificatorului (15.11).** Rezolvă problema „de decis” din notele rolului 2: 220 W fix (0,281 %/min) față de ~0,194 %/min în planificator.
  - **Cum se calculează acum:**
    - motorul nu mai folosește `WALK_WATTS`;
    - fiecare minut se parcurge segment cu segment, cu viteza Tobler și O₂-ul din `core.budget._walk`, după panta segmentului;
    - bugetul unui minut e timpul (1 min), nu distanța;
    - proiecțiile (`tick.budget.o2_end_pct`, watchdog-ul de buget) folosesc același model pe traseul rămas.
  - **Reparat pe parcurs:** viteza se calcula de la celula rotunjită. Când rotunjirea cădea pe celula următoare, panta ieșea 0 și astronautul urca pantele cu viteza de pe teren plat.
  - **Rezultat**, traseu spre `clay_delta`, fără pericole:

    | Sit | Plan | Live |
    |---|---|---|
    | Jezero | 148 min, 71,4% O₂ | 149 min, 71,2% |
    | sintetic | 145 min, 73,4% | 146 min, 73,3% |

    Fără RETURN pe `O2_RESERVE` fără pericol.
  - `O2_PCT_PER_MIN_WALK` rămâne exportat, ca rată pe teren plat a modelului nou (0,194 %/min).
  - Test: `test_live_o2_matches_planner_budget`.

- **Puncte proprii în planificare (P3, 15.11)**, după `shared/contracts/README.md` → „Puncte proprii”:
  - **Cererea:** `POST /api/route` acceptă `custom_stops` (`id: note_…`, `name`, `row`, `col`, `tag`, `dwell_min`), cu id-urile lor în `stops`.
  - **Validare:** în grilă, teren permis, accesibil din habitat, fără duplicate sau definiții lipsă, nume fără `<>`; altfel 422 cu text.
  - **Înregistrare:** punctele devin ținte ale sitului marcate `custom: true` (`planning.register_custom_stops`). Așa le folosesc neschimbate planificatorul, `core/replanner` (live) și motorul. Sunt ascunse în `/api/site` și în chat.
  - **Ordinea** o alege planificatorul; răspunsul are `visit_order`, `source`, `omitted`, `validation_status`.
  - **Verificat:** Olivine + 2 puncte proprii → GO; EVA live cu cutremur: toate opririle vizitate, acasă cu 79% O₂.
- **Planning, ecran nou (frontend, 15.11, cerut de utilizator):**
  - harta pe tot ecranul, iar listele de sub ea au dispărut (Your trip, Elevation profile, Science sites, Mission plan, Mission budget, Route analysis);
  - la click pe hartă → „Add to trip” (popup-ul existent);
  - în stânga hărții e un panou semi-transparent (`MissionOverlay.jsx`) cu opririle, estimarea backendului (verdict, O₂, distanță, durată, „Return by” LTST, punct de neîntoarcere, doză), setările (prioritate, durată, întoarcere) și „Open simulation”;
  - estimarea se cere automat la fiecare schimbare (`useMissionEstimate.js`, cu 400 ms întârziere) și e blocată cât rulează o EVA.

- **Pentru rolul 2: „destinația întâi” în `core/selection.py` (15.11, cu acordul utilizatorului).**
  - **Problema** (reprodusă în aplicație): cu un cutremur lângă astronaut, o reevaluare de proximitate alegea RETURN deși traseul curent (ocolirea) era valid. Scorul S unic dădea câștig întoarcerii prin O₂-ul rămas (știința are doar 0,15 la `safe`), iar RETURN e definitiv.
  - **Reparația:**
    - `selection.tier()`: 0 = ajunge la toate țintele, 1 = sare peste ținte, 2 = RETURN / adăpost; pe INBOUND totul e la nivelul 0;
    - `order_key` = (nivel, S, prioritate, id);
    - un traseu curent valid nu e înlocuit de o variantă de nivel mai slab.
    
    Scorul S, histerezisul și EMERGENCY rămân neschimbate în interiorul aceluiași nivel.
  - **Verificat pe Jezero** (Olivine + Clay, cutremur de 80–300 m pus pe traseu lângă astronaut): în toate cele 4 cazuri REROUTE, ambele ținte vizitate, acasă cu 63–66% O₂. Scena demo: min 30 REROUTE (`detour_free`, ca în `demo.md`), 80 EMERGENCY, 93 REROUTE, egress la min 150, Clay vizitat.
  - Test: `tests/core/test_selection.py::test_destination_first_valid_detour_beats_cheaper_return`.
  - **Atenție:** benchmark-ul și testele de scenă (`tests/scenario`, `tests/integration/test_sc_*`) pot avea alte cifre sau decizii. Trebuie rulate din nou, iar `benchmark.json` și `demo.md` actualizate.

- **Așteptare, „step back” și reluarea țintelor (15.11, cu acordul utilizatorului; cod și în fișierele rolului 2):**
  - **`core/replanner.py`:**
    - `W_MAX_MIN` 30 → 120: o așteptare mai lungă e respinsă doar de validator (O₂, apus);
    - candidat nou `step_back` (tip WAIT): când poziția e în drumul pericolului, astronautul se retrage la cea mai apropiată celulă din afara amprentei pe toată durata așteptării (+100 m), așteaptă cât trebuie, apoi continuă spre ținte;
    - `ReplanState.hold` și `_route_dwell`: oprirea planificată intră în watchdog și în evaluarea traseului curent.
  - **`core/types.py`:** `Alternative.hold_index` / `hold_min`.
  - **`core/selection.py`:** `step_back` are prioritatea lui `wait`. ROUTE_OK și histerezisul nu blochează o variantă de nivel mai bun (necesar pentru reluare).
  - **Motorul:**
    - execută `step_back` (`self.hold`: oprirea la locul sigur);
    - **RESUME**: după RETURN / EMERGENCY, țintele sunt puse deoparte (bug reparat: înainte erau șterse), iar la fiecare 5 min și la sosirea acasă se încearcă reluarea lor (`_try_resume`, `reason_code: HAZARD_CLEARED`, `trigger: resume`).
  - **Verificat pe Jezero** (spre Clay):

    | Scenariu | Rezultat |
    |---|---|
    | furtună lentă peste traseu | ocolire, Clay atinsă |
    | furtună rapidă de 1,6 km care îl prinde | EMERGENCY, apoi reluare la min 7, Clay atinsă, acasă cu 70% O₂ |
    | furtună pe lângă traseu | continuă |
    | O₂ 52% | RETURN definitiv |
    | fronturi de 2 km | `step_back` și `wait` valide, Clay atinsă |

    Scena demo e neschimbată.
  - **LLM:** promptul v3 descrie `step_back` și reluarea.
  - **Frontend:** etichetele din `utils.js` și `DecisionPanel` sunt în engleză.
  - **Teste:** `test_selection.py` (2), `test_engine.py::test_return_keeps_targets_for_resume`.
  - **Cunoscut:** cu o furtună mare și rapidă, decizia poate oscila EMERGENCY ↔ reluare de câteva ori până trece furtuna.

## În lucru

## Cereri


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
