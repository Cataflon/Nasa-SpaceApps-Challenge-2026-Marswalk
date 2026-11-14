# Rolul 2: Algoritmi

Ești unul dintre 4 agenți care implementează **simultan** Marswalk Copilot în același repo. Ceilalți trei lucrează la date (`pipeline/`, `scenario.py`, `docs/`), backend + LLM (`backend/app/api/`, `live/engine.py`, `llm/`) și frontend (`frontend/`). Tu ai tot ce e în `backend/app/core/`: algoritmii puri, fără server și fără rețea.

## Proiectul în 30 de secunde

Marswalk Copilot ajută un astronaut care iese pe jos pe Marte (delta din craterul Jezero). Are o hartă de 10×10 km pe grilă de 20 m (500×500 celule) și un copilot live. Copilotul prezice pericolele, generează trasee alternative și elimină variantele nesigure. O regulă deterministă alege varianta, iar un LLM local doar explică. **Toate cifrele (distanță, O₂, timp, risc, doză) vin din codul tău.**

Citește din `README.md`: secțiunea 4 (workflow-ul, mai ales Faza 3), 5.2 (harta de cost), 5.3 (algoritmii și CP-SAT), 5.4 (pericolele), 5.5 (bugetul), 5.6 (validatorul). Citește și `shared/contracts/README.md`, `route_response.json` și `live_messages.json`.

## Ce fișiere ai voie să modifici

- `backend/app/core/**`. Poți adăuga module noi în `core/`.
- `backend/tests/core/**`
- `docs/roles/notes/rol2.md`

**Orice alt fișier e doar pentru citit.**

### Reguli speciale pentru `core/`
- **Semnăturile funcțiilor publice existente nu se schimbă.** Rolul 3 scrie deja cod care le apelează. Ai voie doar să adaugi parametri **opționali**, cu valoare implicită, la final.
- `types.py`: câmpurile existente nu se schimbă. Ai voie să adaugi câmpuri noi **cu valoare implicită, la final**.
- `decision.py` și `validator.py` sunt deja implementate și testate (`tests/core/test_decision.py`). Poți ajusta constantele, dar testele existente trebuie să rămână verzi.
- Dependențe: doar `numpy`, `ortools` și biblioteca standard. Fără scipy sau numba. Dacă ai nevoie de altceva, scrie o cerere în note.

## Ce livrezi (consumat de rolul 3)

| Funcție | Folosită de | Țintă de performanță (500×500) |
|---|---|---|
| `costmap.static_cost(site, preset)` | planner, alternatives | < 0,2 s |
| `routing.astar(cost, start, goal)` | planner | < 1 s |
| `routing.reverse_dijkstra(cost, habitat)` + `path_home` | planner, alternatives | < 2 s, o singură dată per hartă |
| `routing.astar_spacetime(...)` | alternatives | < 1,5 s cu orizont de 60 min |
| `budget.route_budget`, `budget.point_of_no_return` | planner, alternatives | < 50 ms |
| `daylight.sunrise_sunset_min` | planner | instant |
| `hazards.from_contract`, `to_contract`, `predict`, `hazard_field`, `route_hit` | motorul live | < 50 ms per tick |
| `stops.plan_stops` (CP-SAT) + `brute_force_stops` | planner, chat | < 1 s pentru ≤ 10 ținte |
| `planner.plan_route(site, start, stops, ...)` | `POST /api/route` | < 3 s total |
| `alternatives.generate(...)` | motorul live | < 2 s total |
| `benchmark.run_benchmark(n, seed)` | `GET /api/benchmark` | 100 de scenarii < 2 min |

`planner.plan_route` întoarce un dict cu **exact** forma din `shared/contracts/route_response.json`. Testul tău trebuie să compare cheile cu fișierul de contract, pe care îl citești, nu îl modifici. Câmpul `verdict` se calculează așa:
- **NO-GO:** validatorul găsește încălcări.
- **CAUTION:** O₂-ul final e la mai puțin de 10 puncte peste rezervă sau întoarcerea e la mai puțin de 60 de minute de apus.
- **GO:** altfel.

## Sarcinile, în ordinea priorității

**P0, ziua 1 (traseul și bugetul trebuie să meargă la finalul ei):**
1. `costmap.static_cost`: `np.inf` peste panta maximă sau pe masca `unsafe`. Factori de teren din `TERRAIN_FACTOR`.
2. `routing.astar`: 8 vecini, cost = lungimea pasului × costul celulei, euristică octilă × costul minim. Tie-break determinist `(f, g, row, col)`.
3. `routing.reverse_dijkstra` + `path_home`.
4. `budget.route_budget` + `point_of_no_return`. Constantele sunt presupuneri: le listezi în note la „Presupuneri”, ca rolul 1 să le documenteze.
5. `daylight`: Mars24 dacă iese repede. Altfel, plan B: valori fixe declarate.
6. `stops.brute_force_stops`, apoi `stops.plan_stops` cu CP-SAT, folosind `solver_params()` pentru determinism. Un test verifică că pe instanțe mici dau același rezultat.
7. `planner.plan_route`.

**P1, ziua 2 (copilotul live):**
8. `hazards`: `from_contract`, `to_contract` (cu `forecast` pe `FORECAST_STEPS_MIN`), `predict`, `hazard_field`, `route_hit`.
9. `routing.astar_spacetime`, inclusiv acțiunea „aștept pe loc”. Dacă e prea lent: orizont mai scurt sau grilă de 100 m (sub-eșantionare ×5).
10. `alternatives.generate`: mereu `current` (CONTINUE), 1-3 ocoliri, `wait` și `return`, cu id-uri stabile.

**P2:**
11. `benchmark.run_benchmark`: copilot față de „doar planul”, pe furtuni generate cu seed fix chiar în `core/`, ca să nu depinzi de `scenario.py`. Metrici: ieșiri încheiate în siguranță, O₂ minim, doză, știință colectată. Testul pe 100 de scenarii e `@pytest.mark.slow`; un test rapid rulează pe 3.

## Teste: rulează doar ce ai modificat

Din `backend/`:

```bash
../.venv/Scripts/python -m pytest tests/core/test_routing.py
```

- Un fișier de test per modul: `test_costmap.py`, `test_routing.py`, `test_budget.py`, `test_hazards.py`, `test_stops.py`, `test_planner.py`, `test_alternatives.py`, `test_benchmark.py`.
- **Testele unitare folosesc grile mici, construite în test**: de exemplu 30×30 cu un perete și o singură trecere. Sunt rapide și nu depind de date.
- Testele de integrare pe situl sintetic (`data/synthetic/`) le sari dacă situl lipsește: `pytest.skip` dacă nu există `meta.json`. Situl se generează cu:

  ```bash
  .venv/Scripts/python pipeline/make_synthetic_site.py
  ```

- La finalul fiecărei sarcini: `../.venv/Scripts/python -m pytest tests/core`.

## Reguli comune (obligatorii pentru toți cei 4 agenți)

### Git
- **NU** rula `git commit`, `git push`, `git add`, `git pull`, `git merge`, `git rebase`, `git stash`, `git checkout`, `git reset` sau orice altă comandă care schimbă starea repo-ului. Doar scrii cod. Ai voie la `git status` și `git diff`.
- Commit-ul și push-ul le fac oamenii, separat pentru fiecare rol. Folderele nu se suprapun, deci nu apar conflicte la merge.

### Fără interferențe
- Modifici **doar** fișierele din secțiunea „Ce fișiere ai voie să modifici”. Alți 3 agenți scriu în același timp în același repo.
- Nu muta, nu redenumi, nu șterge și nu reformata fișiere din afara zonei tale. Nu rula formatere sau lintere pe tot repo-ul (`black .`, `ruff --fix .`, `prettier --write .`), ci doar pe fișierele tale.
- **Înghețate:** `shared/contracts/**`, `README.md`, `.gitignore`, `.github/**`, `backend/pytest.ini`, `backend/tests/conftest.py`, `backend/requirements.txt`, `frontend/package.json`. Dacă ai nevoie de o schimbare acolo, o scrii la „Cereri” în notele tale.
- Nu instala pachete în `.venv` comun și nu adăuga dependențe npm. Cererile le scrii în note.
- Dacă depinzi de o funcție a altui rol care încă aruncă `NotImplementedError`, **nu o implementa tu**. Folosește un fake în teste și un fallback în cod.
- Nu porni servere. Nu ai nevoie de ele: totul se testează direct pe funcții.

### Teste
- Rulezi **doar** testele pentru fișierele pe care tocmai le-ai modificat, nu toată suita la fiecare schimbare.
- La finalul fiecărei sarcini, rulezi **o dată** toate testele din zona ta.
- Un test care durează peste 5 s se marchează `@pytest.mark.slow` și nu rulează implicit. Testele trebuie să fie deterministe (seed fix), fără rețea și fără Ollama.
- Testele noi stau doar în folderele tale de teste. Un test existent din zona ta poate fi modificat, nu șters.

### Cod
- Python compatibil cu 3.11 (CI rulează 3.12, local e 3.14). Comentariile și mesajele sunt în română, ca în restul codului; numele de variabile și funcții sunt în engleză.
- Determinism peste tot: seed fix, sortări stabile cu tie-break explicit, fără `time.time()` în logică.

### Note de predare: `docs/roles/notes/rol2.md`
Le ții la zi după fiecare sarcină, cu secțiunile fixe **Gata** (cu timpii măsurați), **În lucru**, **Cereri** (pentru alt rol sau pentru oameni) și **Presupuneri** (constante fără sursă). E singurul canal de comunicare cu ceilalți agenți.
