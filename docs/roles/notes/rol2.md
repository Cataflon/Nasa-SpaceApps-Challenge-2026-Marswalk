# Note rolul 2

## Gata

Teste: `python -m pytest tests/core` → 77 trecute în 0,7 s
(`test_decision` 6, `test_grid` 14, `test_costmap` 27, `test_routing` 30).

### R2-0: pornire, utilitare de grilă și de test

- `backend/app/core/grid.py` (nou): `pad_and_flatten`, `to_flat`, `to_cell`, `NEIGHBORS`, `octile`.
  Grila de cost devine o listă plată cu bordură de `inf`, ca buclele cu `heapq` din `routing.py`
  să nu verifice marginile la fiecare vecin. Celulele rămân `(row, col)` din grila originală;
  doar indexul plat ține cont de bordură (`Wp = W + 2`). `NaN` (nodata) devine `inf`.
- Adăugat la R2-2: `neighbor_moves(Wp)`, cei 8 vecini împreună cu cele două celule ortogonale
  pe lângă care trece fiecare diagonală. E locul unic al regulii „fără tăierea colțurilor”;
  `reverse_dijkstra` și `astar_spacetime` îl vor folosi tot pe el.
- `backend/tests/core/grids.py` (nou, helperi): `make_site`, `wall_with_gap`, `synthetic_site_or_skip`.
  `make_site` citește `shared/contracts/meta.json` și construiește fiecare strat cu `dtype`-ul de acolo.
- `backend/tests/core/test_grid.py` (nou): 13 teste.

### R2-1: harta de cost, `costmap.static_cost` (cu corecția de normalizare și `slope_k`)

- `backend/app/core/costmap.py`: `static_cost(site, preset)` implementat; semnătura,
  `TERRAIN_FACTOR`, `hazard_cost` și cheile existente din `PRESETS` sunt neschimbate.
  `cost = f_slope × TERRAIN_FACTOR[teren] + w_radiation × rad_norm`, cu
  `f_slope = 1 + slope_k × (pantă / max_slope)²` și
  `rad_norm = (rad − rad.min()) / max(rad.min(), RADIATION_EPS)`.
  `inf` peste `meta.max_slope_deg`, pe masca `unsafe` și pe `NaN`. Vectorizat, float64.
- `PRESETS` are o cheie nouă, `slope_k` (safe 5,0; science 3,0; fast 1,5). Un preset fără ea
  folosește `SLOPE_K = 3,0`.
- `ValueError` dacă habitatul sau o țintă cade pe o celulă interzisă ori în afara grilei
  (greșeală de date, pentru rolul 1), dacă stratul `terrain` are o clasă fără factor, sau dacă
  preset-ul nu există.
- Cache per `(id(site), preset)`, cu referință slabă la sit: intrarea dispare când situl e
  eliberat, deci un sit nou care primește același `id` nu ia costul celui vechi (verificat: din
  7 situri create pe rând, 2 au refolosit un `id`). `clear_cost_cache()` îl golește.
- `backend/tests/core/test_costmap.py`: 27 de teste.

### R2-2: `routing.astar`

- `backend/app/core/routing.py`: `astar(cost, start, goal)` implementat peste `grid.py`.
  8 vecini, costul unui pas = lungimea pasului × costul celulei în care intri, euristică
  octilă × costul minim finit (admisibilă, deci traseul e optim), coadă `(f, g, idx)`, adică
  `(f, g, row, col)`, cu eliminare leneșă după `g`.
- **Fără tăierea colțurilor:** o diagonală e permisă doar dacă ambele celule ortogonale pe
  lângă care trece sunt finite. Un perete de celule care se ating doar în colțuri e deci închis.
- `None` dacă start sau goal e pe o celulă interzisă, ori sunt izolate una de alta; `[start]`
  dacă start == goal. `ValueError` dacă start sau goal e în afara grilei ori harta are costuri
  negative. Celulele din traseu sunt `int` simplu (merg în JSON).
- `backend/tests/core/test_routing.py` (nou): 30 de teste. Optimalitatea e verificată față de un
  Dijkstra scris independent în test (cu aceeași regulă de colț), pe 8 grile aleatoare cu seed fix.
- `reverse_dijkstra`, `path_home` și `astar_spacetime` sunt încă neimplementate.

### Timpi măsurați pe situl sintetic 500×500

Python 3.14.6, numpy 2.5.4; mediana din mai multe rulări.

| Funcție | Măsurat | Țintă |
|---|---|---|
| `grid.pad_and_flatten(cost)` | 5,4 ms (max 7,1 ms) | fără țintă proprie; inclus în timpul lui `astar` |
| `costmap.static_cost(site, "safe")`, fără cache | 7,1 ms (max 10,4 ms) | < 0,2 s |
| `costmap.static_cost(site, "safe")`, din cache | 0,0003 ms | < 0,2 s |
| `routing.astar`, habitat → `clay_delta` (121 celule, 2,9 km) | 28–31 ms, după preset | < 1 s |
| `routing.astar`, habitat → `carbonate_rim` (181 celule, 4,1 km) | 45–51 ms | < 1 s |
| `routing.astar`, habitat → `olivine_floor` (131 celule, 2,9 km) | 30–32 ms | < 1 s |
| `routing.astar`, colț la colț, (0,0) → (499,499), 537 celule | 0,64 s (o rulare din 3: **1,38 s**) | < 1 s, la limită |
| `routing.astar`, țintă izolată (fără traseu, explorează toată harta) | **1,56 s (max 1,68 s)** | < 1 s, **depășit** |

Timpii lui `astar` sunt cu regula „fără tăierea colțurilor” (cu ≈ 10–20 % mai lent decât fără ea).

Pe situl sintetic: 1,34 % din celule sunt interzise. Costul finit e între 1,03 și 18,04 la
`safe`, 1,02 și 12,02 la `science`, 1,01 și 7,51 la `fast`. Termenul de radiație e între 0 și
0,074 la `safe` (`rad_norm` între 0 și 0,037).

## În lucru

- Urmează `routing.reverse_dijkstra` + `path_home`.
- De preluat din `docs/roles/PARAMETRI_REFERINTA.md` (apărut în timpul R2-2, citit, încă
  neaplicat), la pașii care le ating:
  - `budget.py`: constantele cu sursă din §4.2 (`P_REST` 176 W, `M_TOTAL` 196 kg, `C_LEVEL` 0,59,
    `ETA_UP` 0,22, rezervor 418 L, 0,000711 %/min/W) și justificarea pentru `SUIT_FACTOR` 0,6;
  - registrul `core/params.py` (un singur loc pentru constante, cu nivel A/B/C și sursă);
  - `hazards.py`: `SIGMA_V` calibrat pe variabilitatea vântului (R2-11).
  Tabelul de la „Presupuneri” de mai jos rămâne până atunci cu valorile din cod.
- `max_slope_deg` 25 → 20 (propus acolo, de aprobat de echipă): `static_cost` citește limita
  din `site.meta`, deci nu cere schimbări în `costmap.py`; doar `Limits.max_slope_deg` e separat.

## Cereri

- **Pentru rolul 3:** tabloul întors de `static_cost` e doar pentru citire (același obiect
  ajunge la toți apelanții, din cache). `cost + altceva` merge; o modificare pe loc
  (`cost[mask] = ...`, `cost += ...`) aruncă `ValueError`. Cine are nevoie face `cost.copy()`.
  Dacă straturile unui `Site` se schimbă pe loc, trebuie apelat `costmap.clear_cost_cache()`.
- **Pentru rolul 3:** `astar` întoarce `None` când nu există traseu (inclusiv când start sau
  goal e pe o celulă interzisă) și aruncă `ValueError` pentru celule în afara grilei. Când ținta
  e izolată, răspunsul vine abia după ~1,6 s, pentru că A* trebuie să epuizeze harta. După ce
  există `reverse_dijkstra`, verificarea ieftină va fi `cost_to_home[celulă] == inf`, înainte de
  a chema `astar`.
- **Pentru oameni, de decis (start pe celulă interzisă, în live):** conform pasului R2-2, `astar`
  întoarce `None` dacă celula de start are cost `inf`. În ieșirea live, dacă un pericol e pus
  ca `inf` peste celula în care se află astronautul, din acea celulă nu mai iese niciun traseu.
  De hotărât la `astar_spacetime` / `alternatives.generate`: fie pericolul intră doar ca cost
  finit (`hazard_cost`), fie celula de start e exceptată acolo.
- **Pentru oameni, de decis (preset-urile dau aproape același traseu pe situl sintetic):**
  cu `slope_k` pe preset, traseele habitat → `clay_delta` diferă între `safe` și `fast`, dar
  numai prin 3 celule din 121; au aceeași lungime (2897 m) și aceeași pantă maximă (7,3°).
  `science` și `fast` dau trasee identice la toate cele 3 ținte, iar spre `olivine_floor` toate
  preset-urile dau același traseu. Cauza: situl sintetic e aproape plat (pantă mediană 0,43°,
  percentila 90 la 1,5°), deci `f_slope` e ≈ 1 aproape peste tot, la orice `slope_k`.
  Urmare pentru `alternatives.generate`: preset-urile singure nu vor produce ocoliri distincte
  pe acest sit. Ocolirile vor trebui să vină din termenul de pericol (`w_hazard × câmp`) sau din
  blocarea pe rând a unei părți a pericolului (nord / sud).
- **Pentru oameni, de știut:** `.venv` nu exista local. L-am creat cu `python -m venv .venv` și
  `pip install -r backend/requirements.txt` (exact lista înghețată, fără pachete în plus, fără
  `npm install`). Situl sintetic l-am generat cu `pipeline/make_synthetic_site.py`, nemodificat.
  Ambele sunt în `.gitignore`.

## Presupuneri

Constante și alegeri fără sursă, pentru rolul 1 (de documentat sau de înlocuit cu valori cu sursă).

| Unde | Constantă | Valoare | Ce înseamnă |
|---|---|---|---|
| `types.Limits` | `o2_reserve_pct` | 30 % | rezerva de O₂ la sosirea în habitat |
| `types.Limits` | `sunset_margin_min` | 30 min | marja față de apusul efectiv |
| `types.Limits` | `max_slope_deg` | 25° | panta maximă pe jos, în costum |
| `types.Limits` | `max_dose_msv` | 1,0 mSv | doza maximă pe ieșire |
| `costmap.PRESETS` | `w_hazard` / `w_radiation` / `w_science` | safe 10 / 2 / 0,15; fast 4 / 0,5 / 0,2; science 6 / 1 / 0,4 | ponderile celor 3 preset-uri |
| `costmap.PRESETS` | `slope_k` | safe 5,0; science 3,0; fast 1,5 | cât penalizează preset-ul panta: la limita de pantă, mersul costă de 1 + `slope_k` ori mai mult decât pe plat (6× / 4× / 2,5×). Valorile sunt alese ca preset-urile să dea trasee diferite, nu măsurate |
| `costmap` | `SLOPE_K` | 3,0 | `slope_k` implicit pentru un preset fără cheie; forma pătratică `1 + k·(s/max)²` e tot o alegere |
| `costmap.TERRAIN_FACTOR` | rocă / regolit / nisip / bolovani | 1,0 / 1,2 / 1,8 / 3,0 | multiplicator de cost pe teren |
| `costmap` | normalizarea radiației | `(rad − rad.min()) / rad.min()` | excesul relativ față de minimul sitului; vezi mai jos |
| `costmap` | `RADIATION_EPS` | 1e-9 | protecție tehnică la împărțire când minimul radiației e zero, nu fizică |
| `routing.astar` | costul unui pas | lungimea pasului × costul celulei în care intri | convenție; alternativa ar fi media celor două celule |
| `routing.astar` | tăierea colțurilor | interzisă | o diagonală cere ambele celule ortogonale libere; regulă de siguranță (un obstacol de 20 m nu se traversează pe colț), nu o valoare măsurată |
| `budget` | `SUIT_FACTOR` | 0,6 | costumul reduce viteza la 60 % |
| `budget` | `MARS_G_FACTOR` | 1,0 | ajustarea pentru 0,38 g încă nu e aplicată |
| `budget` | `O2_PCT_PER_MIN_REST` | 0,12 %/min | consumul de O₂ în repaus |
| `budget` | `O2_PCT_PER_MIN_PER_WATT` | 0,0006 %/min/W | consumul de O₂ pe watt metabolic |
| `budget.tobler_speed_ms` | 6 km/h, −3,5, +0,05 | funcția lui Tobler | forma are sursă (Tobler 1993), dar e calibrată pe Pământ, fără costum |
| `hazards` | `UNCERTAINTY_GROWTH_PER_MIN` | 0,005 | axele furtunii cresc cu 0,5 % pe minut de predicție |
| `hazards` | `FORECAST_STEPS_MIN` | 10, 20, 30, 45, 60, 90, 120, 180 | orizonturile de predicție |
| `decision` | `RISK_THRESHOLD` | 0,3 | sub acest risc, traseul curent continuă |
| `decision` | `MIN_IMPROVEMENT` | 0,2 | histerezis: alternativa trebuie să fie cu ≥ 20 % mai bună |
| `daylight.effective_sunset_min` | 30 min per unitate de tau peste 0,5 | liniar | cu cât apune „mai devreme” când e praf |
| `stops.solver_params` | `random_seed` 42, `max_deterministic_time` 5,0 | CP-SAT | alegeri de determinism, nu fizică |

**Normalizarea radiației (decizia rolului 2).** Radiația intră în cost ca exces relativ față de
minimul sitului: un strat uniform nu costă nimic, iar o zonă cu 10 % mai multă radiație costă
`w_radiation × 0,1` în plus. Motivul:
- împărțirea la maxim lăsa un decalaj aproape constant pe toată harta (1,93–2,00 la `safe`), care
  făcea ca `safe` să penalizeze panta relativ mai puțin decât `fast`;
- min–max ar întinde la 0..1 și un strat aproape uniform, adică ar amplifica zgomotul (±1,8 % pe
  situl sintetic) până la valoarea unei pante.

Limita dură pe doză rămâne în validator. De știut: dacă minimul stratului e 0 (de exemplu nodata
codat ca 0) și restul e pozitiv, împărțirea se face la `RADIATION_EPS` și costul iese uriaș; un
astfel de strat trebuie curățat de rolul 1 înainte.

Doar în teste (nu afectează produsul):

| Unde | Constantă | Valoare | Ce înseamnă |
|---|---|---|---|
| `tests/core/grids.py` | `WALL_SLOPE_DEG` | 40° | panta peretelui din grilele de test, aleasă peste limita de 25° |
