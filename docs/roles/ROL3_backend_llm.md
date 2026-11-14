# Rolul 3: Backend & LLM

> ## 🆕 NOU (14.11.2026): citește întâi asta
> Echipa a adăugat 7 funcționalități legate direct de tema challenge-ului („Interplanetary Survival Guide”). Tabelul complet e în `README.md`, secțiunea „🆕 Noutăți”. **Ce ai tu nou de făcut** (detaliile sunt mai jos, marcate 🆕). Toate câmpurile sunt **noi și opționale**, deci nimic existent nu se strică:
> 1. **`compute_ms` în mesajul `decision`:** cât a durat decizia (alternative + validator + regulă), măsurat cu `time.perf_counter()` **doar pentru afișare**, nu intră în logică. Alimentează contorul „Houston ar răspunde în 28 min · copilotul a decis în 0,05 s”.
> 2. **`/api/site` primește `eva_start_ltst_h` și `earth_delay_min`** (`{"one_way", "round_trip", "source"}`), luate din `app.live.scenario` (`EVA_START_LTST_H`, `EARTH_ONE_WAY_DELAY_MIN`, `EARTH_ROUND_TRIP_MIN`). Cât timp constantele de întârziere lipsesc, `getattr` cu fallback 14 / 28 min.
> 3. **`/api/point` primește `sources`:** pentru fiecare strat, `mission` / `instrument` / `data_type` / `source` din `meta["layers"][strat]`, pentru click-ul pe hartă („pantă 12° · HiRISE · MRO”). Pe situl sintetic, ce există (`data_type`, `analog_of`, `source`).
> 4. **`/api/benchmark` trimite mai departe `headline`** din `run_benchmark` („acasă în siguranță: copilot X% · plan fix Y%”).
> 5. **Scenariile (de la rolul 1, deja gata):** folosește `scenario.sensors_at(s, t_min)`, `scenario.with_event(s, ev)` și `scenario.demo_events(SITE_ID)`. Detalii în `docs/roles/notes/rol1.md`, la „Cereri”.

Ești unul dintre 4 agenți care implementează **simultan** Marswalk Copilot în același repo. Ceilalți trei lucrează la date (`pipeline/`, `scenario.py`, `docs/`), algoritmi (`backend/app/core/`) și frontend (`frontend/`). Tu ai serverul FastAPI, motorul live, LLM-ul și integrarea.

## Proiectul în 30 de secunde

Marswalk Copilot ajută un astronaut care iese pe jos pe Marte (delta din craterul Jezero). Are o hartă de 10×10 km pe grilă de 20 m și un copilot live: la fiecare minut simulat citește senzorii și prezice pericolele. Dacă traseul e afectat, generează alternative, le validează și o regulă deterministă alege una. Decizia pleacă **imediat** spre frontend, iar explicația LLM-ului vine **separat**, după 2-3 s. **Codul decide, LLM-ul explică.** Dacă Ollama pică, explicația vine dintr-un șablon.

Citește din `README.md`: secțiunea 4 (workflow-ul, mai ales Faza 3), 5.7 (LLM-ul), 5.8 (rutele). Citește și tot `shared/contracts/`: formele JSON de acolo sunt obligatorii.

## Ce fișiere ai voie să modifici

- `backend/app/api/**`
- `backend/app/live/__init__.py`, `backend/app/live/engine.py`. Poți adăuga module noi în `backend/app/live/`, **în afară de** `scenario.py`, care e al rolului 1.
- `backend/app/llm/**`
- `backend/app/schemas.py`, `backend/app/config.py`
- `backend/tests/api/**`, `backend/tests/live/**`, `backend/tests/llm/**`
- `docs/roles/notes/rol3.md`

**Orice alt fișier e doar pentru citit**, mai ales `backend/app/core/**` (rolul 2) și `backend/app/live/scenario.py` (rolul 1).

## Ce consumi de la alții (încă neimplementat, deci cu fallback)

| De la | Funcție | Fallback cât timp aruncă `NotImplementedError` |
|---|---|---|
| rolul 2 | `core.planner.plan_route(...)` | `route_response.json` + antetul `X-Mock: 1` (deja făcut) |
| rolul 2 | `core.hazards.*`, `core.alternatives.generate` | motorul redă `mock_stream` (deja făcut) |
| rolul 2 | `core.decision.choose` | **deja implementat**, folosește-l |
| rolul 2 | `core.benchmark.run_benchmark` | 501 |
| rolul 1 | `live.scenario.generate(...)` | `scenario.BASELINE` constant pe fiecare minut. 🆕 **Deja implementat:** folosește `sensors_at`, `with_event`, `demo_events` |

Prinde `NotImplementedError` **exact acolo unde apelezi**, ca integrarea să meargă automat când celelalte roluri termină, fără nicio modificare din partea ta.

## Sarcinile, în ordinea priorității

**P0, ziua 1:**
1. **`POST /api/route`:** apelează `planner.plan_route(get_site(), ...)`. Fallback pe mock, 422 pentru id-uri de ținte necunoscute. Păstrează traseele în memorie după `route_id`, pentru motorul live.
2. **Ollama pe laptopul cu GPU** (RTX 4050, 6 GB VRAM): verifică dacă e instalat (`ollama --version`) și dacă are modelul `qwen2.5:7b-instruct`. **Nu instala nimic tu.** Dacă lipsește, scrie la „Cereri” pentru oameni și continuă: codul merge și fără el.
3. **`llm/summary.py`:** construiește `summary` pentru `explain()` dintr-un `core.types.Decision`. Include `decision`, `alternative_id`, `alternative_ids` (doar cele valide), `eta_hazard_min`, `extra_min`, `o2_end_pct` și motivele de respingere. Totul compact, sub 500 de tokeni.

**P1, ziua 2 (până la mijlocul zilei, reroute-ul live trebuie să meargă):**
4. **`LiveEngine`**, ca singleton partajat între WebSocket și rutele de control:
   - **`step()` sincron**, care avansează un minut și întoarce lista de mesaje, plus `run()`, care apelează `step()` și doarme `1/speed` secunde. Testele apelează `step()` direct, fără ceas real.
   - **Starea:** poziția pe traseu, `t_min`, O₂, doza, oboseala, pericolele active, traseul curent.
   - **Pe tick:** scenariul dă senzorii, evenimentele injectate se aplică, apoi `hazards.route_hit`. Dacă traseul e lovit: `alternatives.generate`, `decision.choose`, mesaj `decision` **imediat**, apoi `asyncio.create_task(explain(...))`, care trimite mesajul `explanation`.
   - **Broadcast** către toți clienții WebSocket conectați.
   - **Mesajele urmează exact** `live_messages.json`.
   - 🆕 Mesajul `decision` are în plus `compute_ms`: durata reală de la detectarea loviturii până la alegerea regulii, cu `time.perf_counter()`. E doar pentru afișare; testele nu verifică o valoare anume, doar că e un număr ≥ 0.
   - 🆕 Senzorii: `scenario.sensors_at(s, t_min)`. Un eveniment injectat cu `POST /api/live/event` înlocuiește scenariul cu `scenario.with_event(s, ScheduledEvent(t_min, event, params))`. Demo-ul pornește cu `scenario.demo_events(SITE_ID)`.
5. **`POST /api/live/control`** (`start`, `pause`, `reset`, `speed`, după `live_control.json`) și **`POST /api/live/event`**, legate de motor.
6. **LLM-ul pe Ollama real:** măsoară latența, ajustează promptul și scrie cifrele în note. Ținta e sub 3 s pe 7B. Testele cu Ollama real sunt marcate `@pytest.mark.ollama`.

**P2:**
7. **`POST /api/chat`:** NDJSON în streaming, după `chat_stream.json`. Folosește tool calling din Ollama (`tools` în `/api/chat`) cu uneltele `plan_route`, `oxygen_budget`, `layer_value`, `science_stops`, `daylight`, care apelează funcțiile din `core`. Fallback fără Ollama: cuvinte-cheie mapate direct pe unelte, plus un răspuns din șablon.
8. **`GET /api/benchmark`:** rulează `core.benchmark.run_benchmark` într-un thread și pune rezultatul în cache. 🆕 Trimite mai departe `headline` (`copilot_safe_pct`, `plan_safe_pct`, `n_scenarios`) neschimbat.

**🆕 P1 (adăugat 14.11, mic, < 1 h în total):**
9. **`GET /api/site`:** adaugă `eva_start_ltst_h` (din `scenario.EVA_START_LTST_H`) și `earth_delay_min = {"one_way": …, "round_trip": …, "source": …}` (din `scenario.EARTH_ONE_WAY_DELAY_MIN` / `EARTH_ROUND_TRIP_MIN`, cu `getattr` și fallback 14 / 28 cât timp lipsesc). Etichetele straturilor (`LAYER_LABEL_KEYS`) sunt deja trimise.
10. **`GET /api/point`:** adaugă `sources = {strat: {k: meta["layers"][strat][k] for k in LAYER_LABEL_KEYS if k in …}}`, alături de `values`. Un test în `tests/api` verifică doar că `sources` are aceleași chei ca `values`.

## Teste: rulează doar ce ai modificat

Din `backend/`:

```bash
../.venv/Scripts/python -m pytest tests/live/test_engine.py
```

- `tests/api/` folosește `TestClient`, `tests/live/` apelează `engine.step()` cu fake-uri pentru `core`, prin `monkeypatch`, iar `tests/llm/` acoperă summary, șabloane și fallback.
- Testele **nu** depind de Ollama (`LLM_ENABLED=0` e setat în `conftest.py`) și nici de ceasul real.
- La finalul fiecărei sarcini: `../.venv/Scripts/python -m pytest tests/api tests/live tests/llm`.
- **Server de dezvoltare pe portul 8001**, nu 8000 (8000 e al oamenilor). Pornește-l din `backend/`:

  ```bash
  ../.venv/Scripts/python -m uvicorn app.api.main:app --port 8001
  ```

## Reguli comune (obligatorii pentru toți cei 4 agenți)

### Git
- **NU** rula `git commit`, `git push`, `git add`, `git pull`, `git merge`, `git rebase`, `git stash`, `git checkout`, `git reset` sau orice altă comandă care schimbă starea repo-ului. Doar scrii cod. Ai voie la `git status` și `git diff`.
- Commit-ul și push-ul le fac oamenii, separat pentru fiecare rol. Folderele nu se suprapun, deci nu apar conflicte la merge.

### Fără interferențe
- Modifici **doar** fișierele din secțiunea „Ce fișiere ai voie să modifici”. Alți 3 agenți scriu în același timp în același repo.
- Nu muta, nu redenumi, nu șterge și nu reformata fișiere din afara zonei tale. Nu rula formatere sau lintere pe tot repo-ul (`black .`, `ruff --fix .`, `prettier --write .`), ci doar pe fișierele tale.
- **Înghețate:** `shared/contracts/**`, `backend/app/core/**`, `README.md`, `.gitignore`, `.github/**`, `backend/pytest.ini`, `backend/tests/conftest.py`, `backend/requirements.txt`, `frontend/package.json`. Dacă ai nevoie de o schimbare acolo, o scrii la „Cereri” în notele tale.
- Nu instala pachete în `.venv` comun și nu adăuga dependențe npm. Cererile le scrii în note.
- Dacă depinzi de o funcție a altui rol care încă aruncă `NotImplementedError`, **nu o implementa tu**. Folosește un fake în teste și un fallback în cod.
- Nu porni servere pe porturile 8000 sau 5173. Al tău e 8001.

### Teste
- Rulezi **doar** testele pentru fișierele pe care tocmai le-ai modificat, nu toată suita la fiecare schimbare.
- La finalul fiecărei sarcini, rulezi **o dată** toate testele din zona ta.
- Un test care durează peste 5 s se marchează `@pytest.mark.slow` și nu rulează implicit. Testele trebuie să fie deterministe (seed fix), fără rețea și fără Ollama (excepție: cele marcate `ollama`).
- Testele noi stau doar în folderele tale de teste. Un test existent din zona ta poate fi modificat, nu șters.

### Cod
- Python compatibil cu 3.11 (CI rulează 3.12, local e 3.14). Numele de variabile și funcții sunt în engleză; comentariile pot rămâne în română.
- **Tot ce vede utilizatorul sau juriul e în engleză:** mesajele din API (`detail` la erori), textele generate (șabloane, explicații LLM), numele țintelor și straturilor, documentele de prezentare.
- Determinism peste tot: seed fix, fără `time.time()` în logica de decizie (doar în bucla `run()`).

### Note de predare: `docs/roles/notes/rol3.md`
Le ții la zi după fiecare sarcină, cu secțiunile fixe **Gata** (cu latențele LLM măsurate), **În lucru**, **Cereri** (pentru alt rol sau pentru oameni) și **Presupuneri**. E singurul canal de comunicare cu ceilalți agenți.
