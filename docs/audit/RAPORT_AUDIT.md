# Raport de audit: Marswalk Copilot

**Commit auditat:** `948351c` (14.11.2026, 16:11). Auditul a început pe `a67c375` + modificările *staged* ale rolului 2. În timpul auditului au intrat 7 commit-uri (`4404bb7`, `e630ce9`, `aff051f`, `6743322`, `25db42c`, `f81d4c8`/`bf5f062`, `1474aa8`, `948351c`). Constatările au fost reverificate pe `948351c`; cele reparate între timp sunt marcate **REPARAT**.

**Mediu:** Windows 11, Python 3.14.6 (`.venv`), numpy 2.5.4, fastapi 0.162.7, ortools 9.15, Node 24.22. Situl sintetic a fost regenerat **în afara repo-ului** (copie în scratchpad, v7), pentru că `data/synthetic/` local e la v1 (vezi AUDIT-023).

---

## 1. Sumar

- **Constatări deschise (CONFIRMAT):** 1 CRITIC, 9 MAJOR, 16 MINOR, 3 NOTĂ. **SUSPICIUNI:** 3. **Reparate în timpul auditului:** 9 (3 dintre ele erau CRITICE).
- **Cele 5 riscuri mari pentru demo:**
  1. **AUDIT-005:** O₂-ul afișat în live (≈ 61 % la sosire pe Jezero) contrazice planul (71,4 %) și textul din `docs/demo.md` („O₂ 100 → 71 %”).
  2. **AUDIT-042:** UI-ul nu are contorul „Houston vs copilot”, popup-ul cu sursa la click, numărul de titlu din benchmark și nici Survival Guide-ul, deși `docs/demo.md` le arată pe ecran.
  3. **AUDIT-010:** `GET /api/benchmark` întoarce 501, iar `run_benchmark` nu are `headline`; cifrele 81 % / 51 % din README nu vin din aplicație.
  4. **AUDIT-008:** decizia rulează sincron în bucla asyncio: la furtuna regională de la minutul 125, bucla stă 1,5 s (Jezero), deci WebSocket-ul și butoanele îngheață.
  5. **AUDIT-018:** „The return clock updates” (demo.md, minutul 80) nu se întâmplă: `return_by_min` rămâne 243 după EMERGENCY / RETURN.
- **Nu s-a putut verifica:** build-ul și lint-ul frontend (fără `node_modules`, iar `npm ci` cere rețea; `package.json` nu are scripturi `lint`, `test` sau `typecheck`); Playwright (cere rețea); LLM-ul real (Ollama absent, doar fake); coverage (pachetul nu e instalat, instalarea cere rețea); Linux/CI (doar citit, nerulat).

## 2. Tabelul constatărilor

| ID | Sev | Stare | Axă | Rol | Titlu scurt |
|---|---|---|---|---|---|
| AUDIT-005 | CRITIC | CONFIRMAT | B/D | 3 (+2) | Motorul consumă O₂ la mers cu 0,281 %/min; planul cu 0,194 %/min |
| AUDIT-004 | MAJOR | CONFIRMAT | E | 3 | Parametri aberanți la `/api/live/event` acceptați (200); `step()` aruncă și simularea intră în pauză fără niciun mesaj |
| AUDIT-008 | MAJOR | CONFIRMAT | E/I | 3 | Decizia (0,1-1,5 s) blochează bucla asyncio |
| AUDIT-018 | MAJOR | CONFIRMAT | A/H | 3 | `return_by_min` și `point_of_no_return` din tick rămân cele din plan după REROUTE/RETURN |
| AUDIT-006 | MAJOR | CONFIRMAT | C | 3 | Numerele din explicația LLM nu sunt verificate |
| AUDIT-007 | MAJOR | CONFIRMAT | D | 2 | `plan_route` adună `start_time_min` la apus |
| AUDIT-010 | MAJOR | CONFIRMAT | A/H | 2+3 | `run_benchmark` fără `headline`; `GET /api/benchmark` = 501 |
| AUDIT-042 | MAJOR | CONFIRMAT | G/H | 4 | UI-ul nu folosește `compute_ms`, `sources`, `headline`, `earth_delay_min`, `/api/point`; nu există Survival Guide |
| AUDIT-012 | MAJOR | CONFIRMAT | G/H | 4 | UI-ul e parțial în română (regula: UI în engleză) |
| AUDIT-017 | MAJOR | CONFIRMAT | A | 3 | Mesajul `decision` nu are `compute_ms` |
| AUDIT-011 | MINOR | CONFIRMAT | D/F | 2 (+echipa) | Panta maximă: 20° în planner, 25° în `Limits`, `meta.json` și harta de cost |
| AUDIT-026 | MINOR | CONFIRMAT | B | 4 (+1) | Relieful 3D (CTX, paralela standard 0°) are 18,97 m pe celulă est-vest, nu 20 m |
| AUDIT-009 | MINOR | CONFIRMAT | H | 2 | Erorile planner-ului ajung în `detail` 422 în română, iar `planner.py` e salvat cu mojibake |
| AUDIT-013 | MINOR | CONFIRMAT | A | 3 | Explicația din cache are `source: "cache"`, în afara enumului `llm|template` |
| AUDIT-014 | MINOR | CONFIRMAT | E | 3 | Un JSON valid care nu e obiect scapă din `explain()` ca AttributeError |
| AUDIT-015 | MINOR | CONFIRMAT | A | 3 | `/api/point` nu trimite `sources` |
| AUDIT-016 | MINOR | CONFIRMAT | A | 3 | `POST /api/chat` = 501 |
| AUDIT-019 | MINOR | CONFIRMAT | E | 3 | `decision_id = d_<t>` se repetă după reset |
| AUDIT-024 | MINOR | CONFIRMAT | D | 2+3 | `effective_sunset_min` (praful) nu e folosit nicăieri |
| AUDIT-028 | MINOR | CONFIRMAT | D | 2 | Un plan care renunță la toate țintele cerute primește GO |
| AUDIT-029 | MINOR | CONFIRMAT | A | 3 | `max_duration_min` negativ, NaN sau Infinity sunt acceptate de schemă |
| AUDIT-037 | MINOR | CONFIRMAT | A | 3 | Un număr care devine Infinity (`1e400`) dă 500 la serializarea erorii 422 |
| AUDIT-031 | MINOR | CONFIRMAT | E | 3 | Ceasul simulat derivă: la viteza 60 ies ≈ 37 min simulate pe secundă |
| AUDIT-022 | MINOR | CONFIRMAT | proces | 2 | Testul `plan_route < 3 s` e instabil (pică sub sarcină, trece singur) |
| AUDIT-023 | MINOR | CONFIRMAT | proces | 1+2 | `data/synthetic` local e v1; testele rolului 2 nu verifică versiunea |
| AUDIT-033 | MINOR | CONFIRMAT | H | oameni | CI nu rulează folderele noi; frontend fără lint/test |
| AUDIT-027 | NOTĂ | CONFIRMAT | I | 3 | `RouteStore` crește fără limită |
| AUDIT-032 | NOTĂ | CONFIRMAT | H | oameni | README: paragraful „Starea scheletului” e depășit; comanda de test e doar pentru Windows |
| AUDIT-025 | NOTĂ | CONFIRMAT | F | echipa | Diferențe rămase față de PARAMETRI_REFERINTA (panta maximă 25° față de 20°) |
| AUDIT-034 | NOTĂ | SUSPICIUNE | E | 2 | `_order_stops` prinde orice `Exception` din CP-SAT |
| AUDIT-035 | NOTĂ | SUSPICIUNE | E | 2+3 | `POST /api/route` (threadpool) și bucla live folosesc aceleași cache-uri fără lock |
| AUDIT-043 | NOTĂ | SUSPICIUNE | B | 4 (+1) | Originea grilei 3D vs grila backend pe Jezero, nealiniată verificabil |
| AUDIT-001 | CRITIC | REPARAT | E | 3 | `remaining_path` fără poziție: `generate` arunca ValueError și simularea intra în pauză |
| AUDIT-002 | CRITIC | REPARAT | F | 3 | Motorul nu programa evenimentele demo |
| AUDIT-003 | CRITIC | REPARAT (redefinit) | F | 1+2 | Scena README veche (ocolire nord / sud) dădea EMERGENCY |
| AUDIT-020 | MINOR | REPARAT | proces | 3 | Testul existent `test_uses_core_alternatives_when_available` era roșu |
| AUDIT-021 | MINOR | REPARAT | H | 1 | `test_how_we_calculate` cerea `HIT_THRESHOLD`, `SIGMA_REL` |
| AUDIT-036 | MINOR | REPARAT | F | 3 | Evenimentele injectate nu treceau prin `scenario.with_event` |
| AUDIT-038 | MAJOR | REPARAT | B | 1/2 | Ora EVA: 09:00 în scenariu, 08:00 în planner |
| AUDIT-039 | MINOR | REPARAT | A | 3 | `/api/site` fără `eva_start_ltst_h` / `earth_delay_min` |
| AUDIT-040 | NOTĂ | REPARAT | F | 1+3 | SPE × 20 (față de × 2,5 în registru), doza 26,7 µSv/h |

---

## 3. Constatările, una câte una

Scripturile de probă (`p01`…`p10`) sunt în anexă. Toate rulează din `<copie>/backend` cu situl sintetic v7: `PYTHONIOENCODING=utf-8 python ../../probes/pXX.py`. Pentru fiecare constatare CONFIRMAT există un test în `backend/tests/regression/` (xfail strict), cu excepțiile notate.

### AUDIT-005: O₂-ul din motorul live contrazice planul (CRITIC, CONFIRMAT, B/D, rolul 3 + 2)
- **Unde:** `backend/app/live/engine.py:47` `O2_PCT_PER_MIN_WALK = O2_PCT_PER_MIN_REST + O2_PCT_PER_MIN_PER_WATT * WALK_WATTS` (= 0,125 + 0,000711 × 220 = **0,281 %/min**) față de `backend/app/core/budget.py:47-59`, unde mersul pe plat consumă 0,000711 × (176 + 97) W = **0,194 %/min**.
- **Observat:** pe Jezero, planul dă O₂ final 71,4 %, iar motorul ajunge acasă cu 61,4 %. Pe sintetic, 73,4 % față de 63,6 %. `tick.budget.o2_end_pct` arată 61-64 % chiar de la minutul 1.
- **Așteptat:** 0,194 %/min la 3 km/h (`docs/roles/PARAMETRI_REFERINTA.md` §4.2) și aceeași cifră în plan și în live. `docs/demo.md` (rândul 0:20-0:45) spune „O₂ 100 → 71 %”.
- **Reproducere:** `p02_engine_after_fix.py` și `p09_jezero_demo.py`:
  ```
  plan GO {... 'o2_end_pct': 71.4 ...}
  tick 79 ({'o2_end_pct': 61.1, 'return_by_min': 243, 'sunset_min': 633.0}, ...)
  final finished 145 o2 61.4 plan o2_end 71.4
  1) O2 mers motor %/min: 0.28142  repaus: 0.125
  ```
- **Impact:** pe ecran apar două cifre de O₂ care se contrazic, chiar în demo. În live, alternativele vin din `route_budget` (0,194), dar O₂-ul curent scade cu 0,281, deci deciziile pornesc de la un O₂ mai mic decât cel real din model.
- **Remediere:** în `_advance_minute`, O₂-ul pe minut din aceeași formulă ca `budget._walk` (cu panta segmentului), nu `WALK_WATTS`. Efort ≈ 30-45 min.
- **Test:** `regression/test_reg_live.py::test_engine_o2_matches_plan_budget_without_events`.

### AUDIT-004: parametri aberanți la `/api/live/event` și pauza tăcută (MAJOR, CONFIRMAT, E, rolul 3)
- **Unde:** `backend/app/schemas.py:39-41` (`params: dict[str, Any]`, fără validare), `backend/app/live/engine.py` `_new_hazard` (`float(params["center"]["row"])`), `run()` (`except Exception: ... self.state = "paused"`, fără publicare).
- **Observat:** `{"center": {"row": "x", "col": 1}}`, `{"center": {"row": 1}}` și `{"duration_min": "abc"}` primesc **200 accepted**, apoi `step()` aruncă ValueError / KeyError. În `run()`, simularea intră în pauză, iar clienții nu primesc nimic: nici mesajul `event`, nici vreo eroare.
- **Așteptat:** `live_event.json` fixează forma lui `center` ({row, col} întregi); o intrare invalidă se respinge cu 422. Orice oprire a simulării se anunță clienților (ROL3: broadcast).
- **Reproducere:** `p04_api_probe.py`:
  ```
  event [center str]: control=200 event=200 -> step EXC ValueError: could not convert string to float: 'x'
  event [center fără col]: control=200 event=200 -> step EXC KeyError: 'col'
  event [SPE durată str]: control=200 event=200 -> step EXC ValueError: invalid literal for int() ...
  ```
  Faza 4 (`p08`, înainte de reparația AUDIT-001): după furtună, A și B primesc doar `{'tick': 72}`, starea e `paused`, fără niciun alt mesaj.
- **Impact:** un buton din UI cu parametri greșiți oprește demo-ul fără explicație.
- **Remediere:** un model Pydantic pentru `params` (center: CellModel, axes_m: 2 float > 0, velocity_ms: 2 float) și, în `run()`, `publish({"type": "event", "event": "engine_error", ...})`. Efort ≈ 45 min.
- **Teste:** `test_live_event_with_malformed_center_is_rejected`, `test_engine_run_notifies_clients_when_step_fails`.

### AUDIT-008: decizia blochează bucla asyncio (MAJOR, CONFIRMAT, E/I, rolul 3)
- **Unde:** `backend/app/live/engine.py`, `run()`: `for msg in self.step(): ...` e apelat direct într-un `async def`, iar `step()` cheamă `alternatives.generate` (CPU).
- **Observat:** durata `step()` cu decizie, pe Jezero: **99 ms** (vârtej), **362 ms** (front), **1482 ms** (furtună regională). Pe sintetic: 123-486 ms și 2194-2340 ms. Cu o pauză simulată de 0,5 s, bucla a stat 0,52 s.
- **Așteptat:** README §4: decizia apare „IMEDIAT” și LLM-ul „nu blochează”. `docs/demo.md` cere ≈ 0,1-0,2 s pe minut simulat.
- **Reproducere:** `p09_jezero_demo.py` (`t=125 decision RETURN return step=1482 ms`) și testul de regresie (`bucla blocată 0.52 s`).
- **Impact:** UI-ul îngheață 1,5 s la scena 5, iar `POST /api/live/control` așteaptă și el. Pe un laptop mai lent, mai mult.
- **Remediere:** `msgs = await asyncio.to_thread(self.step)` (cu lock pe starea motorului) sau un executor dedicat. Efort ≈ 1 h (cu atenție la cursele cu rutele de control).
- **Test:** `test_engine_decision_does_not_block_event_loop`.

### AUDIT-018: ceasul de întoarcere nu se actualizează după decizie (MAJOR, CONFIRMAT, A/H, rolul 3)
- **Unde:** `backend/app/live/engine.py`, `_tick_message`: `"return_by_min": budget.get("return_by_min", ...)` și `"point_of_no_return": self.route.get(...)` vin din planul inițial.
- **Observat:** pe Jezero, `return_by_min` = 243 la t = 79, 82, 126 și 130, adică înainte și după EMERGENCY / RETURN. La fel și PNR-ul.
- **Așteptat:** `docs/demo.md` 1:25-1:40: „The return clock updates”; README §8.5.
- **Reproducere:** `p09_jezero_demo.py` (rândurile `tick 79/82/126/130`).
- **Remediere:** după `_apply_decision`, recalculați `return_by_min` / PNR din `route_budget` pe traseul nou (aceleași funcții ca planner-ul). Efort ≈ 1 h.
- **Teste:** `test_tick_return_by_updates_after_return_decision` (fallback) și `test_jezero_demo_return_clock_updates_after_storm_front` (@slow, Jezero).

### AUDIT-006: numerele din explicația LLM nu sunt verificate (MAJOR, CONFIRMAT, C, rolul 3)
- **Unde:** `backend/app/llm/client.py:58-68`: se verifică doar `decision` și `alternative_id`.
- **Observat:** cu un Ollama fals care răspunde „Storm in 3 min. Detour adds 99 min, 12% O2 left.”, rezultatul e `{'source': 'llm', 'text': 'Storm in 3 min. Detour adds 99 min, 12% O2 left.'}`. Rezumatul avea 16 min, 25 min și 31 %.
- **Așteptat:** README §1 „Cifrele vin din cod, nu din LLM”; `prompts.SYSTEM` „Never invent numbers”. Promptul de audit cere fallback la un număr inventat.
- **Reproducere:** `p05_llm_probe.py`, prima linie.
- **Remediere:** extrageți numerele din `reason` (regex) și cereți ca fiecare să apară în valorile numerice din `summary` (cu rotunjire); altfel șablon. Efort ≈ 30 min.
- **Test:** `test_llm_reason_with_invented_number_falls_back_to_template`.

### AUDIT-007: apusul se mută cu `start_time_min` (MAJOR, CONFIRMAT, D, rolul 2)
- **Unde:** `backend/app/core/planner.py:114`: `sunset = start_time_min + sunrise_sunset_min(...)[1]`. Contrazice comentariul de la `planner.py:21-23` („începutul ieșirii (t = 0) e fix … apusul cade la ≈ 633 min de la start”).
- **Observat:** cu `start_time_min = 500`, rezultatul e `sunset_min = 1133`, sosire 645, **GO**, fără încălcări.
- **Așteptat:** apusul rămâne 633, deci sosirea la 645 > 603 dă DAYLIGHT, adică NO-GO.
- **Reproducere:** `p04_api_probe.py`:
  ```
  start_time_min=0: sunset_min=633 sosire=145 verdict=GO
  start_time_min=500: sunset_min=1133 sosire=645 verdict=GO viol=[]
  ```
- **Impact:** frontendul trimite mereu 0, deci demo-ul nu e afectat. Chatul și orice planificare târzie primesc însă GO greșit.
- **Remediere:** `sunset = sunrise_sunset_min(...)[1]` (fără `start_time_min`). Efort 5 min + un test.
- **Test:** `test_planner_sunset_does_not_move_with_start_time`.

### AUDIT-010: benchmark-ul nu ajunge în aplicație (MAJOR, CONFIRMAT, A/H, rolul 2 + 3)
- **Unde:** `backend/app/core/benchmark.py:167-168` (rezultatul nu are `headline`) și `backend/app/api/main.py` `benchmark()`: `raise HTTPException(501, ...)` cu `# TODO (rolul 2)`, deși `run_benchmark` e implementat.
- **Observat:** cheile rezultatului sunt `['copilot', 'n', 'per_scenario', 'plan_only', 'seed']`; `GET /api/benchmark` dă 501.
- **Așteptat:** README „Noutăți” #5 și ROL2 sarcina 11 (`headline = {copilot_safe_pct, plan_safe_pct, n_scenarios}`); ROL3 sarcina 8.
- **Reproducere:** `p07_benchmark_props.py` (`headline prezent: False`) și `p04` (`benchmark: 501`).
- **Remediere:** `headline` din `_summary(...)["safe_pct"]`; ruta cu `run_in_threadpool` și cache (≈ 1 min pentru 100 de scenarii). Efort ≈ 30 min.
- **Teste:** `test_run_benchmark_has_headline`, `test_api_benchmark_returns_headline`.

### AUDIT-042: funcțiile demo promise nu sunt în UI (MAJOR, CONFIRMAT, G/H, rolul 4)
- **Unde:** `frontend/src/**`: `grep -rn "compute_ms|sources|headline|earth_delay|/api/benchmark"` nu găsește nimic. `getPoint` (`frontend/src/api/client.js:38`) nu e apelat din nicio componentă. Nu există o pagină „Survival Guide” (doar CSS de print generic, `styles.css:318`).
- **Așteptat:** README „Noutăți” #1, #2, #4, #5 și `docs/demo.md` (0:05-0:20 popup „slope 7° · HiRISE + CTX · MRO”; 0:55-1:25 contorul „Houston's help would arrive in 27 min · copilot decided in <0.1 s”; 1:55-2:00 Survival Guide).
- **Reproducere:** `cd frontend/src && grep -rn "compute_ms\|sources\|headline\|earth_delay\|/api/benchmark" .` nu întoarce nimic; `grep -rn "getPoint(" --include=*.jsx .` nu întoarce nimic.
- **Impact:** 4 din cele 8 momente ale demo-ului nu au suport în aplicație.
- **Remediere:** 4 componente mici (contor, popup la click pe hartă cu `getPoint`, cifra de benchmark, pagina de print). Efort ≈ 3-4 h (rolul 4), după AUDIT-010/015/017.
- **Test:** fără test backend (lipsă de funcționalitate în frontend); specificațiile Playwright din `frontend/e2e/` acoperă parțial.

### AUDIT-012: UI parțial în română (MAJOR, CONFIRMAT, G/H, rolul 4)
- **Unde:** `frontend/src/utils.js:2-5` (`'Continuă traseul'`, `'Urmează ocolirea'`, `'Așteaptă'`, `'Urgență'`, evenimente, încălcări); `BudgetPanel.jsx` („O₂ estimat la întoarcere”, „Distanță planificată”…); `DecisionPanel.jsx`, `Planner.jsx`, `Navigator.jsx`, `TerrainView.jsx`; mesaje de eroare în `client.js` („Cererea nu a reușit”, „Chatul nu este disponibil”). În total, 51 de linii cu diacritice în 13 fișiere.
- **Așteptat:** README, „Limba”: „toată aplicația e în engleză (interfața …)”. `App.jsx` a fost tradus în `e630ce9`; restul nu.
- **Reproducere:** `grep -c "[ăâîșțĂÂÎȘȚ]" frontend/src/components/*.jsx frontend/src/utils.js …`
- **Remediere:** traducerea etichetelor; de preferat, un singur dicționar în `utils.js`. Efort ≈ 1 h.
- **Test:** `test_frontend_labels_are_english`.

### AUDIT-017: `decision` fără `compute_ms` (MAJOR, CONFIRMAT, A, rolul 3)
- **Unde:** `engine.py`, `_decide`: dict-ul mesajului nu are `compute_ms`.
- **Așteptat:** README „Noutăți” #2 și ROL3 sarcina 4. Contorul din demo depinde de el.
- **Reproducere:** `p02` (`compute_ms=False` la fiecare decizie).
- **Remediere:** `perf_counter()` în jurul lui `_alternatives` + `choose`. Efort 10 min.
- **Test:** `test_decision_message_has_compute_ms`.

### AUDIT-011: trei limite de pantă diferite (MINOR, CONFIRMAT, D/F, rolul 2 + echipa)
- **Unde:** `core/planner.py:27` `PLANNER_LIMITS = Limits(max_slope_deg=20.0)`; `core/types.py:14` `max_slope_deg = 25.0` (folosit de `decision.choose` și de motor); `shared/contracts/meta.json:10` = 25 (folosit de `static_cost`).
- **Impact:** o ocolire live prin 20-25° e validă, dar planul cu aceeași pantă e NO-GO. Pe situl sintetic, traseele au sub 8°, deci demo-ul nu e afectat.
- **Remediere:** o singură valoare (registrul cere 20°: `meta.json`, `Limits`, ambele înghețate, deci decizie de echipă). Efort 10 min după decizie.
- **Test:** `test_max_slope_is_the_same_everywhere`.

### AUDIT-026: scara relief 3D ≠ grila backend (MINOR, CONFIRMAT prin contradicție, B, rolul 4 + 1)
- **Surse care se contrazic:** `frontend/public/terrain/jezero.json` (`ProjStdParallel1GeoKey: 0`, `cell_size_m: 20`, „Equirectangular Mars 2000 Sphere”) față de `docs/roles/notes/rol1.md` §3 („la 18,44° un metru est-vest din proiecție = 0,95 m pe teren … grila noastră folosește `local_proj4()` … 20 m sunt chiar 20 m”).
- **Observat:** pe teren, celula 3D are 20 × cos(18,44°) = **18,97 m** est-vest. La marginea hărții (250 de celule) decalajul ajunge la ≈ 258 m, adică ≈ 13 celule; la `clay_delta` (≈ 150 de celule vest de centru) e ≈ 150 m.
- **Remediere:** reeșantionarea DTM-ului frontendului pe grila backend (`local_proj4`) sau scalarea X cu cos(lat). Efort ≈ 1 h.
- **Test:** `test_frontend_terrain_cells_are_20_m_on_ground`.

### AUDIT-009: erori de planificare în română, cu mojibake (MINOR, CONFIRMAT, H, rolul 2)
- **Unde:** `core/planner.py`, toate mesajele `ValueError` („Nu există traseu…”, „Ținte necunoscute…”). Fișierul e salvat dublu-codificat: `LeagÄƒ`, `neÃ®ntoarcere` sunt în fișier, iar `python -c "... 'Ä' in s"` dă True.
- **Observat:** `POST /api/route` cu start pe o celulă interzisă dă 422 `{"detail":"Nu existÄƒ traseu de la (0, 169) la (180, 140)."}`. Frontendul afișează `body.detail`.
- **Așteptat:** ROL2/ROL3: „mesajele din API (detail la erori) în engleză”.
- **Remediere:** resalvați `planner.py` în UTF-8 corect și traduceți mesajele. Efort 15 min.
- **Test:** `test_route_error_detail_is_english_without_mojibake`.

### AUDIT-013 / AUDIT-014: LLM, în afara contractului (MINOR, CONFIRMAT, A/E, rolul 3)
- **013:** `client.py:35-36` întoarce `{**hit, "source": "cache"}`; contractul spune că `source` e `llm` sau `template` (`shared/contracts/README.md`, „Mesajele live”). Probă: `p05` → `a doua oară (cache): {... 'source': 'cache'}`. Test: `test_llm_cached_explanation_source_is_contract_value`.
- **014:** `client.py:53-59`: `out.get(...)` e în afara `try`; un răspuns `["not","an","object"]` dă `AttributeError`. Probă: `p05` → `JSON listă -> EXCEPȚIE ne-prinsă: AttributeError`. Motorul îl prinde (`engine.py` `explain_job`), deci impactul e limitat. Test: `test_llm_non_object_json_falls_back_to_template`.
- **Remediere:** `source = "llm"` la cache-hit; `isinstance(out, dict)` în `try`. Efort 10 min.

### AUDIT-015 / AUDIT-016: rute neterminate (MINOR, CONFIRMAT, A, rolul 3)
- **015:** `GET /api/point` întoarce doar `row, col, values` (`main.py` `point`); ROL3 sarcina 10 cere `sources`. Probă `p04`: `point keys: ['col','row','values'] False`. Test: `test_api_point_has_sources_for_each_value`. În afara grilei dă 400 (nu 422); ROL3 nu fixează codul, deci nu e raportat separat.
- **016:** `POST /api/chat` dă 501 (`main.py`, `# TODO (rolul 3)`). În UI, chatul din `client.js` aruncă „Chatul nu este disponibil” (în română). Test: `test_api_chat_streams_ndjson`.

### AUDIT-019: `decision_id` nu e unic între rulări (MINOR, CONFIRMAT, E, rolul 3)
- **Unde:** `engine.py`, `_decide`: `decision_id = f"d_{t}"`; `reset()` nu anulează task-urile de explicație în curs.
- **Impact:** o explicație întârziată din rularea 1 (`d_30`) ajunge după reset și e salvată de frontend sub `d_30`, apoi afișată la decizia `d_30` din rularea 2.
- **Probă:** `p02` §3: `run1 [('d_30', ...)]`, `run2 [('d_30', ...)]`.
- **Remediere:** un contor de rulare în id (`d_<run>_<t>`) și anularea task-urilor la reset. Efort 20 min.
- **Test:** `test_decision_ids_are_unique_across_resets`.

### AUDIT-024: praful nu aduce apusul mai devreme (MINOR, CONFIRMAT, D, rolul 2 + 3)
- **Unde:** `core/daylight.py` `effective_sunset_min` nu e apelat nicăieri (`grep -rn effective_sunset_min backend/app` găsește doar definiția).
- **Așteptat:** README §5.5: „Lumina: apusul efectiv din Mars24, mai devreme dacă e praf”. `how-we-calculate.md` afișează formula.
- **Test:** `test_tick_sunset_is_earlier_with_dust`. Efort 20 min (motorul folosește `effective_sunset_min(sunset, dust_tau)` în validare).

### AUDIT-028: planul gol primește GO (MINOR, CONFIRMAT, D, rolul 2)
- **Observat:** trei ținte cu `max_duration_min = 1` dau 200 **GO**, `path=[[300,200]]`, `stops=[]`; o singură țintă cu 1 min dă NO-GO (DAYLIGHT). Probă: `p04`, cazul „toate țintele, 1 min”.
- **Impact:** UI-ul activează „Start EVA” pe un plan fără nicio țintă.
- **Remediere:** dacă nu rămâne nicio țintă cerută, verdict NO-GO cu un cod dedicat, sau 422. Efort 15 min.
- **Test:** `test_plan_that_drops_every_requested_target_is_not_go`.

### AUDIT-029 / AUDIT-037: validarea numerelor din cereri (MINOR, CONFIRMAT, A, rolul 3)
- **029:** `schemas.py:33-34`: `start_time_min`, `max_duration_min` fără limite. `-5` dă 200 (NO-GO, `return_by_min: -62`); `Infinity` dă 200 GO; `NaN` dă 422 cu mesajul intern „cannot convert float NaN to integer”. Test: `test_route_request_rejects_non_positive_duration`.
- **037:** `{"start": {"row": 1e400, ...}}`: Pydantic dă 422 cu `input: inf`, iar `json.dumps(allow_nan=False)` din răspunsul de eroare pică, deci **500**. Găsit de fuzz-ul din `unit_gaps`. Test: `test_route_with_infinite_number_is_422_not_500`.
- **Remediere:** `Field(gt=0, le=1440, allow_inf_nan=False)` și un handler `RequestValidationError` care curăță `input`. Efort 20 min.

### AUDIT-031: deriva ceasului simulat (MINOR, CONFIRMAT, E, rolul 3)
- **Unde:** `engine.py`, `run()`: `await asyncio.sleep(1.0 / clock_speed)` după `step()`, fără să scadă durata tick-ului.
- **Observat:** pe serverul real, la viteza 60: interval median **27-28 ms** pe tick (ar trebui 16,7 ms), deci ≈ 37 min simulate pe secundă, nu 60. Probă: `p08` (`interval tick median 27 ms`).
- **Test:** **niciunul** (depinde de ceasul real; un test ar fi instabil). Remediere: programare după `loop.time()` țintă. Efort 15 min.

### AUDIT-022: test de timp instabil (MINOR, CONFIRMAT, proces, rolul 2)
- `tests/core/test_planner.py::test_synthetic_clay_delta_is_go_or_caution_under_3_s` (aserțiunea `elapsed < 3.0`) a picat în 2 din 4 rulări complete pe `25db42c` / `948351c` și trece mereu singur (2,35 s). Rolul 2 a notat același lucru (3,29 s după benchmark). Nu e bug în cod: pragul nu are toleranță pentru CI. **Remediere:** pragul ×3 sau mutarea testului în `slow`.

### AUDIT-023: situl sintetic local e vechi (MINOR, CONFIRMAT, proces, rolul 1 + 2)
- `data/synthetic/meta.json` local nu are `generator_version` (deci v1), iar generatorul e la v7: `python pipeline/make_synthetic_site.py --check` iese cu 1. `backend/tests/core/grids.py:90-93` (`synthetic_site_or_skip`) nu verifică versiunea, deci testele rolului 2 rulează pe datele vechi fără avertisment. Testele noi de audit se sar cu motivul „situl sintetic de pe disc e v1, generatorul e v7: regenerați-l” (49 de teste în repo-ul real).
- **Remediere:** `python pipeline/make_synthetic_site.py`; în `grids.py`, aceeași verificare de versiune.

### AUDIT-033: CI (MINOR, CONFIRMAT, H, oameni)
- `.github/workflows/core.yml` rulează doar `pytest tests/core`, iar `service.yml` doar `tests/api tests/live tests/llm`: folderele noi (`contracts`, `unit_gaps`, `properties`, `integration`, `e2e`, `regression`) **nu rulează în CI**. `frontend.yml` face doar `npm run build`, iar `package.json` nu are `lint` / `test`. Niciun workflow nu generează situl sintetic, deci testele de integrare se sar în CI. Propunerea de workflow e în anexă.

### AUDIT-027, 032, 025 (NOTĂ, CONFIRMAT)
- **027:** `live/store.py:232-240`: fiecare `POST /api/route` adaugă un traseu cu `deepcopy`, fără limită. La o sesiune de demo e neglijabil, la un server pornit zile întregi nu.
- **032:** README, „Starea scheletului: rutele încă neimplementate întorc mock-urile … Funcțiile de făcut au TODO și NotImplementedError” nu mai e adevărat (NotImplementedError nu mai există în `backend/app`). „Teste: `cd backend && ../.venv/Scripts/python -m pytest`” e doar pentru Windows (pe Linux, `.venv/bin`).
- **025:** după `bf5f062` (doza 28, SPE × 2,5, tau 0,5) rămâne o singură diferență față de `PARAMETRI_REFERINTA.md`: panta maximă 25° în `meta.json` / `Limits` față de 20° [S26] (vezi AUDIT-011). Pericolele demo au acum dimensiunile din registru (vârtej 130 m, front 30 × 5 km la 15 m/s).

### SUSPICIUNI (fără test)
- **AUDIT-034:** `core/planner.py:205-210`: `except Exception:` în jurul lui `plan_stops` ascunde orice eroare reală din CP-SAT (de exemplu un `KeyError` în tabele) și trece pe forța brută fără log. Nereprodus.
- **AUDIT-035:** `POST /api/route` e `def`, deci rulează în threadpool, și citește / scrie `planner._cache` și `costmap._cost_cache` în timp ce bucla live le folosește în alt thread. Operațiile pe dict sunt atomice sub GIL, iar valorile sunt deterministe, deci riscul e mic. Nereprodus.
- **AUDIT-043:** pe Jezero, alinierea originii dintre `frontend/public/terrain/jezero.json` și grila `data/processed/jezero` nu a putut fi verificată (frontendul nu are transformarea; rol4 o cere în „Cereri”).

### Reparate în timpul auditului (reverificate pe `948351c`)
- **AUDIT-001 (CRITIC):** motorul trimitea `remaining_path` fără poziția curentă, iar `alternatives.py:48-50` arunca ValueError. Pe serverul real (Faza 4, `25db42c`), primul pericol pe traseu punea simularea pe pauză la t = 72, fără niciun mesaj. Reparat în `engine.py` (`remaining = [here] + …`). Testul `test_engine_real_core_hazard_on_route_produces_decision` a trecut din xfail în XPASS(strict), iar marcajul a fost scos.
- **AUDIT-002 (CRITIC):** `generate(seed, 720, None)` dădea `events=[]`, deci singleton-ul nu avea furtuni. Acum se folosește `scenario.demo_events(site_id)`. Test: `test_engine_default_schedules_demo_events`.
- **AUDIT-003 (CRITIC):** scena README veche (ocolire nord +25 min / sud eliminată) dădea EMERGENCY pe sintetic (furtuna blocheza poziția în 10 min; `p03`). Echipa a redefinit scena (`docs/demo.md`), iar pe Jezero rezultatul e exact cel scris (`p09`): `t=30 REROUTE detour_north`, `t=80 EMERGENCY`, `t=125 RETURN`.
- **AUDIT-020, 021:** testele roșii (`test_engine.py`, `test_how_we_calculate.py`) sunt verzi.
- **AUDIT-036:** injectarea trece acum prin `scenario.with_event`. Test: `test_injected_local_storm_raises_sensor_dust`.
- **AUDIT-038:** `EVA_START_LTST_H` = 8,0, identic cu LTST la `SOL_START_UTC` (7,98 h, verificat cu `daylight.ltst_hours`).
- **AUDIT-039:** `/api/site` trimite `eva_start_ltst_h` și `earth_delay_min`.
- **AUDIT-040:** SPE × 2,5 și doza 28 µSv/h, ca în registru.

## 4. Nesincronizări între roluri

| Rol A | Rol B | Fișiere | Ce diferă |
|---|---|---|---|
| 3 (motor) | 2 (buget) | `live/engine.py:47` / `core/budget.py:47-59` | O₂ la mers 0,281 vs 0,194 %/min (AUDIT-005) |
| 2 (planner) | 2/echipa (`Limits`, meta) | `planner.py:27` / `types.py:14` / `meta.json:10` | pantă 20° vs 25° (AUDIT-011) |
| 2 (benchmark) | 3 (API) / 4 (UI) / README | `benchmark.py` / `main.py` / `frontend/src` | `headline` lipsă, 501, nefolosit (AUDIT-010, 042) |
| 3 (motor) | 4 (UI) / README | `engine.py` / `docs/demo.md` | `compute_ms` lipsă, ceasul de întoarcere static (AUDIT-017, 018) |
| 3 (API) | 4 (UI) | `main.py` `point` / `client.js:38` | `sources` lipsă; `getPoint` neapelat (AUDIT-015, 042) |
| 4 (relief 3D) | 1 (grila sitului) | `public/terrain/jezero.json` / `notes/rol1.md` §3 | scară est-vest 18,97 vs 20 m (AUDIT-026) |
| 2 (`daylight`) | 3 (motor) | `daylight.py` / `engine.py` | apusul cu praf nefolosit (AUDIT-024) |
| 3 (LLM) | contracte | `client.py:35` / `shared/contracts/README.md` | `source: "cache"` (AUDIT-013) |
| 1 (scenariu) | 2 (planner) | `scenario.EVA_START_LTST_H` / `planner.SOL_START_UTC` | **REPARAT** (08:00 peste tot) |

## 5. Ce funcționează (verificat)

- **Algoritmii de bază (rolul 2):** pe 50 de perechi aleatoare pe situl real, traseele A* sunt continue, fără celule interzise și fără colțuri tăiate. Costul A* = Dijkstra invers (diferență maximă 3,4·10⁻¹³), A* e determinist octet cu octet, iar ordinea țintelor din cerere nu schimbă planul. `plan_route` dă JSON identic de două ori și trece `allow_nan=False`.
- **Cache-ul hărții de cost:** nu servește harta veche unui sit nou cu `id` refolosit (`id` refolosit în 4 din 40 de încercări, fără eroare) și e read-only.
- **Bugetul:** pe plat, 3,02 km/h și 0,1940 %/min, iar repausul 0,125 %/min: exact ca registrul §4.2.
- **Benchmark-ul (30 de scenarii):** nicio alternativă validă nu încalcă limitele, decizia e mereu din mulțimea validă sau RETURN/EMERGENCY, traseele alternativelor sunt continue și pe celule permise, iar același seed dă aceleași numere (primele n scenarii sunt identice la orice n).
- **Contractele:** `plan_route` / `POST /api/route`, `/api/site`, mesajele `tick`, `decision`, `explanation` și `event` au exact forma din `shared/contracts` (câmpurile în plus sunt cele opționale anunțate). Enumurile (decizii, preset-uri, verdict, evenimente, coduri de încălcare) sunt scrise identic în contracte, `schemas.py`, core, șabloane și `utils.js`.
- **Fallback-ul LLM:** la timeout, Ollama absent, JSON invalid sau decizie contrazisă, explicația vine din șablon, cu `source: template`.
- **Live:** cu un LLM lent, tick-urile continuă, iar explicația întârziată poartă `decision_id`-ul ei. Frontendul (`useMission.js` reducer, `DecisionPanel.jsx`) afișează explicația după `decision.decision_id`, deci o explicație veche nu o înlocuiește pe cea nouă. Pe serverul real: 3 clienți primesc aceleași decizii, deconectarea unuia nu îi afectează pe ceilalți, iar la reconectare primești ultimul tick. După reset, a doua rulare e identică cu prima.
- **Scena demo pe Jezero** (`docs/demo.md`) produce exact deciziile scrise.
- **Pipeline:** straturile au forma și dtype-ul din contract și intervale fizice corecte, panta e calculată cu `cell_size` (rampa de 1/20 dă 2,862°), habitatul e plat, iar toate țintele sunt accesibile. Pe Jezero: centrul 18,44 / 77,45, ca în contract.
- **Fără** markeri de conflict, fără `NotImplementedError`, fără scipy / numba / networkx în `core/`, fără secrete în repo.

## 6. Rețeaua de teste

### 6.1 Inventar

Rezultate pe copia cu situl sintetic v7 (`948351c` + testele de audit). În repo-ul real, cu `data/synthetic` v1, testele care cer situl se sar cu motivul „regenerați-l”: rezultatul e 64 trecute, 49 sărite, 11 xfailed.

| Fișier | Strat | Teste | Rezultat |
|---|---|---|---|
| `backend/tests/contracts/test_contracts_shapes.py` | L0 | 12 | 11 verzi, 1 skip (`/api/chat` 501) |
| `backend/tests/contracts/test_contracts_requests_enums.py` | L0 | 9 | verzi |
| `backend/tests/unit_gaps/test_gap_core.py` | L1 | 31 | verzi |
| `backend/tests/unit_gaps/test_gap_llm_live_api.py` | L1 | 30 (cu parametrizări) | verzi |
| `pipeline/tests/test_audit_layers.py` | L1 | 7 | verzi |
| `backend/tests/properties/test_prop_core.py` | L2 | 8 (câte ≥ 50 de cazuri) | verzi |
| `backend/tests/properties/test_prop_site.py` | L2 + L5 | 4 + 5 | slow, verzi |
| `backend/tests/integration/test_int_planner_engine.py` | L3 | 6 | verzi (1 slow) |
| `backend/tests/e2e/test_e2e_flow.py` | L4 a/c | 3 | verzi |
| `backend/tests/e2e/test_e2e_server.py` | L4 b | 2 | slow, verzi (server real pe 8002) |
| `frontend/tests/audit_pure.test.mjs` | L4 e | 6 | verzi |
| `frontend/e2e/marswalk.spec.js` | L4 d | 5 | **nerulate** |
| `backend/tests/regression/test_reg_live.py` | L6 | 12 | 3 verzi (gărzi pentru reparații), 8 xfail, 1 xfail slow |
| `backend/tests/regression/test_reg_core_api.py` | L6 | 15 | 15 xfail |

**Total pe straturi:** L0 21 · L1 68 · L2 12 · L3 6 · L4 11 (+5 specificații Playwright nerulate) · L5 5 · L6 27 (**24 xfail strict** = bugurile cunoscute, 3 gărzi). Suita rapidă de audit (fără slow) durează 22 s pe laptop (100 verzi, 1 skip, 23 xfail); suita existentă plus cea de audit, 61 s (365 verzi, 1 skip, 23 xfail, 0 roșii). Cele 13 teste slow de audit trec (benchmark-ul de 100 de scenarii cu tracemalloc durează câteva minute). Pragul de 60 s din prompt **nu** se poate respecta: suita existentă singură are 27-53 s.

Regula xfail strict a funcționat în timpul auditului: după merge-ul `948351c`, AUDIT-001, 002 și 036 au devenit `XPASS(strict)`, suita a picat intenționat, iar marcajele au fost scoase (acum sunt gărzi de regresie).

### 6.2 Mutații (5.4)

Copie separată (`scratchpad/mut`); suita rapidă (existentă + audit) cu `-x`; repo-ul real nu a fost atins. **13 din 13 mutante ucise** (12 cerute + serializarea contractului cu `np.int64`). Trei mutante au fost ucise întâi de un test de timp instabil (AUDIT-022); re-rulate cu `-k "not under and not seconds and not one_second"`, au fost ucise de teste funcționale.

| Funcție | Mutația | Ucisă de |
|---|---|---|
| `static_cost` | scoate masca `unsafe` | `core/test_costmap.py::test_unsafe_cell_is_forbidden` |
| `astar` | scoate regula colțurilor | `core/test_routing.py::test_path_goes_through_the_only_gap` |
| `reverse_dijkstra` | costul mutării greșit | `core/test_routing.py::test_path_home_ends_at_habitat_and_costs_cost_to_home[0]` |
| `route_budget` | scoate `/1000` (µSv → mSv) | `core/test_budget.py::test_dwell_adds_exactly_rest_o2_dose_and_time` |
| `point_of_no_return` | inversează comparația | `core/test_budget.py::test_point_of_no_return_hand_built` |
| `plan_stops` | `- duration` → `+ duration` | `core/test_stops.py::test_enough_time_visits_all_in_shortest_order[plan_stops]` |
| `hazards.predict` | semnul vitezei pe x | `core/test_hazards.py::test_reproduces_contract_forecast` |
| `hazards.route_hit` | prag imposibil (> 1) | `contracts/test_contracts_shapes.py::test_live_decision_and_explanation_messages_match_contract` |
| `alternatives.generate` | scoate `wait` | `core/test_alternatives.py::test_storm_on_route_gives_all_kinds` |
| validator | rezerva O₂ dezactivată | `contracts/test_contracts_requests_enums.py::test_violation_codes_are_all_labelled_in_frontend` |
| `decision.choose` | `<=` → `>=` la prag | `core/test_decision.py::test_safe_route_continues` |
| verificarea LLM | consistența decizie / id dezactivată | `llm/test_llm_fallback.py::test_llm_contradicting_decision_falls_back` |
| serializarea contractului | `np.int64` în `duration_min` | `api/test_api.py::test_route_returns_contract_shape` |

**Gol de test:** verificarea *numerelor* din explicația LLM nu se poate muta, pentru că nu există în cod (AUDIT-006). Testul care o cere e `regression/test_reg_core_api.py::test_llm_reason_with_invented_number_falls_back_to_template` (xfail). Mutantele neucise: **0**.

### 6.3 Matricea de acoperire

Legendă: ✔ acoperit · ✖ gol · (r) doar test de regresie xfail.

| Funcție / rută / mesaj | L0 | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|---|
| `costmap.static_cost` | | ✔ | ✔ | | | ✔ | |
| `routing.astar` | | ✔ | ✔ | | | ✔ | |
| `routing.astar_spacetime` | | ✔ | ✖ | ✔ | | ✖ | |
| `routing.reverse_dijkstra` / `path_home` | | ✔ | ✔ | | | ✔ | |
| `budget.route_budget` | | ✔ | ✔ | ✔ | | | ✔ |
| `budget.point_of_no_return` | | ✔ | ✔ | | | | |
| `daylight.*` | | ✔ | ✖ | | | | (r) |
| `stops.plan_stops` / `brute_force_stops` | | ✔ | ✔ | | | | |
| `hazards.*` | | ✔ | ✔ | ✔ | | | |
| `alternatives.generate` | | ✖ | ✔ | ✔ | ✔ | | |
| `validator` / `decision.choose` | | ✔ | ✔ | ✔ | | | |
| `planner.plan_route` | ✔ | | ✔ | ✔ | ✔ | ✔ | (r) |
| `benchmark.run_benchmark` | | | ✔ | | | ✔ | (r) |
| `llm.client.explain` / `summary` / `cache` / `templates` | ✔ | ✔ | | ✔ | ✔ | | (r) |
| `live.engine` (step, evenimente, reset, subscribe) | ✔ | ✔ | | ✔ | ✔ | | ✔ |
| `GET /api/site`, `/api/layers` | ✔ | ✔ | | | ✔ | | |
| `GET /api/point` | ✔ | ✔ | | | | | (r) |
| `POST /api/route` | ✔ | ✔ | | | ✔ | | (r) |
| `POST /api/live/control`, `/api/live/event` | ✔ | ✔ | | | ✔ | | (r) |
| `WS /api/live` | | | | | ✔ | | |
| `POST /api/chat`, `GET /api/benchmark` | ✖ (501) | | | | | | (r) |
| mesaj `tick` / `decision` / `explanation` / `event` | ✔ | | | ✔ | ✔ | | |
| `live/scenario.py` | | ✖ (acoperit de `tests/scenario` existent) | | ✔ | | | ✔ |
| pipeline (straturi, pantă, ținte) | ✔ | ✔ | | | | | |
| frontend (`navigation.js`, `utils.js`, `equipment.js`) | ✔ | ✔ | | | | | |
| frontend (`client.js`, `useMission.js` reducer, componente) | ✖ | ✖ | | | ✖ (Playwright nerulat) | | ✔ (text) |

Procentul de acoperire pe modul nu e disponibil: `coverage` nu e instalat, iar instalarea cere rețea.

**De extras (pentru testare fără DOM, nu le-am extras eu):** reducer-ul din `frontend/src/hooks/useMission.js` (nu e exportat, iar fișierul importă `react`) și funcțiile `request`, `fallback` și parsarea mesajelor din `frontend/src/api/client.js` (importă `@contracts/*.json` prin aliasul Vite). Mutate într-un modul pur (ex. `src/live/state.js`), ar putea fi testate cu `node --test`.

### 6.4 Cum se rulează

```bash
# din backend/
python -m pytest tests                     # rapid (existent + audit), fără slow
python -m pytest tests -m slow             # lent: benchmark 100, perf, server real pe 8002, Jezero
python -m pytest tests/e2e                 # doar e2e (fără slow)
python -m pytest tests/regression -rxX     # bugurile cunoscute (xfail strict)
# din rădăcină
python -m pytest pipeline/tests
node --test "frontend/tests/*.test.mjs"    # Node 24 nu acceptă directorul ca argument
# Playwright (nerulat în audit; instalare în afara repo-ului):
#   npm i --prefix /tmp/e2e-tools @playwright/test && npx --prefix /tmp/e2e-tools playwright install chromium
#   backend: cd backend && uvicorn app.api.main:app --port 8002
#   frontend: cd frontend && BACKEND_URL=http://127.0.0.1:8002 npx vite --port 5175
#   NODE_PATH=/tmp/e2e-tools/node_modules npx --prefix /tmp/e2e-tools playwright test frontend/e2e
```

**Atenție:** înainte de prima rulare, `python pipeline/make_synthetic_site.py`. Altfel, 49 de teste de audit se sar (motiv afișat).

### 6.5 Ce nu s-a putut rula
- `npm ci` / `vite build` / lint: fără `node_modules` local, iar instalarea cere rețea (interzisă în audit). Încercarea a dat `npm error network`.
- Playwright: idem; specificațiile sunt scrise, dar nerulate.
- Ollama real, coverage și CI pe Linux.

### 6.6 Cereri către echipă (fișiere înghețate)
1. **CI:** un workflow nou pentru folderele de audit (propunerea din anexă); în `core.yml` / `service.yml`, generarea sitului sintetic înainte de teste.
2. **`frontend/package.json`:** scripturi `test` (`node --test "tests/*.test.mjs"`) și, dacă echipa vrea, `@playwright/test` ca devDependency.
3. **`backend/requirements.txt`:** `websockets` e folosit de testele cu server real; azi vine tranzitiv din `uvicorn[standard]`. Fixați-l explicit dacă rămâne.
4. **`meta.json` / `types.Limits`:** decizia pe panta maximă (AUDIT-011).
5. **`backend/tests/core/grids.py`** (rolul 2): verificarea versiunii sitului (AUDIT-023).

## 7. Anexă

### 7.1 Scripturile de probă
Scripturile sunt păstrate integral în scratchpad-ul sesiunii de audit (`probes/p01…p10`) și rezumate mai jos. Fiecare a fost rulat pe copia repo-ului cu situl v7.

- `p01_engine_demo.py`: motorul real: evenimentele programate de singleton și scena demo (programată sau injectată la t = 72).
- `p02_engine_after_fix.py`: O₂ motor vs plan; scena cu `generate` reparat prin wrapper; explicațiile; două rulări după reset.
- `p03_why_no_detour.py`: de ce scena veche nu avea ocoliri (măștile blocate, `astar_spacetime` = None, efectul `SIGMA_REL`).
- `p04_api_probe.py`: chei `/api/site`, `/api/point`; 501; erori 422; fuzz `/api/route`; `start_time_min` vs apus; parametri aberanți la `/api/live/event`.
- `p05_llm_probe.py`: Ollama fals: număr inventat, cache, JSON listă, JSON invalid, timeout, decizie contrazisă.
- `p06_core_props.py`: 50 de perechi A*, cazuri limită, pantă la limită, cache `id`, rate O₂, PNR, determinism, pericole.
- `p07_benchmark_props.py`: 30 de scenarii: limitele alternativelor valide, decizia validă, trasee valide, determinism, `headline`.
- `p08_e2e_server.py`: Faza 4: uvicorn pe 8002, 2 clienți WebSocket, scenariul demo de două ori, oprirea serverului.
- `p09_jezero_demo.py`: scena din `docs/demo.md` pe Jezero: decizii, durata `step()`, ceasul de întoarcere, O₂.
- `p10_mutants.py`: cele 13 mutații (5.4) pe o copie separată.

Fragmentul-cheie din `p01` (pe `25db42c`, înainte de reparații):

```python
e = LiveEngine(store=store)          # singleton-ul real, fără override
e.start(rid)
print(e.scheduled)                   # -> []  (AUDIT-002)
e2 = LiveEngine(store=store, scheduled_events=scenario.demo_events("synthetic"))
e2.start(rid); run(e2, 300)          # -> EXC ValueError la t=72 (AUDIT-001)
```

### 7.2 Propunere `.github/workflows/e2e.yml` (NU a fost creat)

```yaml
name: audit (contracte, regresii, e2e)
on:
  push:
    paths: ["backend/**", "pipeline/**", "shared/contracts/**", "frontend/src/**", "frontend/tests/**"]
  pull_request:
    paths: ["backend/**", "pipeline/**", "shared/contracts/**", "frontend/src/**", "frontend/tests/**"]
jobs:
  backend:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip, cache-dependency-path: backend/requirements.txt }
      - run: pip install -r backend/requirements.txt
      - run: python pipeline/make_synthetic_site.py
      - run: python -m pytest tests/contracts tests/unit_gaps tests/properties tests/integration tests/e2e tests/regression -rxX
        working-directory: backend
      - run: python -m pytest tests -m slow
        working-directory: backend
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  frontend-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: node --test "frontend/tests/*.test.mjs"
```
