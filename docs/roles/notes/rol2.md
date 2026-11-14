# Note rolul 2

## Gata

### R2-0: pornire, utilitare de grilă și de test

- `backend/app/core/grid.py` (nou): `pad_and_flatten`, `to_flat`, `to_cell`, `NEIGHBORS`, `octile`.
  Grila de cost devine o listă plată cu bordură de `inf`, ca buclele cu `heapq` din `routing.py`
  să nu verifice marginile la fiecare vecin. Celulele rămân `(row, col)` din grila originală;
  doar indexul plat ține cont de bordură (`Wp = W + 2`). `NaN` (nodata) devine `inf`.
- `backend/tests/core/grids.py` (nou, helperi): `make_site`, `wall_with_gap`, `synthetic_site_or_skip`.
  `make_site` citește `shared/contracts/meta.json` și construiește fiecare strat cu `dtype`-ul de acolo.
- `backend/tests/core/test_grid.py` (nou): 13 teste.
- Teste: `python -m pytest tests/core` → 19 trecute în 0,2 s (6 în `test_decision.py` + 13 noi).

Timpi măsurați pe situl sintetic 500×500 (Python 3.14.6, numpy 2.5.4, mediana din 15 rulări):

| Funcție | Măsurat | Țintă |
|---|---|---|
| `grid.pad_and_flatten(cost)` | 5,4 ms (max 7,1 ms) | fără țintă proprie; 0,5 % din bugetul de 1 s al lui `routing.astar` |
| `grid.to_cell` + `grid.octile`, o dată pentru fiecare din cele 250.000 de celule | 70 ms | fără țintă proprie; cazul cel mai rău pentru euristica A*, 7 % din bugetul de 1 s |

### Harta de cost: `costmap.static_cost`

- `backend/app/core/costmap.py`: `static_cost(site, preset)` implementat; semnătura, `PRESETS`,
  `TERRAIN_FACTOR` și `hazard_cost` sunt neschimbate.
  `cost = f_slope × TERRAIN_FACTOR[teren] + w_radiation × rad_norm`, cu
  `f_slope = 1 + SLOPE_K × (pantă / max_slope)²` și `rad_norm = radiație / max(radiație)`.
  `inf` peste `meta.max_slope_deg`, pe masca `unsafe` și pe `NaN`. Vectorizat, float64.
- `ValueError` dacă habitatul sau o țintă cade pe o celulă interzisă ori în afara grilei
  (greșeală de date, pentru rolul 1), dacă stratul `terrain` are o clasă fără factor, sau dacă
  preset-ul nu există.
- Cache per `(id(site), preset)`, cu referință slabă la sit: intrarea dispare când situl e
  eliberat, deci un sit nou care primește același `id` nu ia costul celui vechi (verificat: din
  7 situri create pe rând, 2 au refolosit un `id`). Nou: `clear_cost_cache()`.
- `backend/tests/core/test_costmap.py` (nou): 20 de teste.
- Teste: `python -m pytest tests/core` → 39 trecute în 0,4 s.

Timpi măsurați pe situl sintetic 500×500 (mediana din 25 de rulări):

| Funcție | Măsurat | Țintă |
|---|---|---|
| `costmap.static_cost(site, "safe")`, fără cache | 7,7 ms (max 13,5 ms) | < 0,2 s |
| `costmap.static_cost(site, "safe")`, din cache | 0,0003 ms | < 0,2 s |

Pe situl sintetic: 1,34 % din celule sunt interzise; costul finit e între 2,96 și 13,97 la
`safe`, 1,49 și 12,49 la `fast`, 1,98 și 12,98 la `science`.

## În lucru

- Urmează D1: `routing.astar` peste `grid.py` (8 vecini, euristică octilă × cost minim,
  tie-break `(f, g, row, col)`).

## Cereri

- **Pentru rolul 3:** tabloul întors de `static_cost` e doar pentru citire (același obiect
  ajunge la toți apelanții, din cache). `cost + altceva` merge; o modificare pe loc
  (`cost[mask] = ...`, `cost += ...`) aruncă `ValueError`. Cine are nevoie face `cost.copy()`.
  Dacă straturile unui `Site` se schimbă pe loc, trebuie apelat `costmap.clear_cost_cache()`.
- **Pentru echipă, de decis (normalizarea radiației):** cu `rad_norm = radiație / max`, termenul
  de radiație e aproape constant pe situl sintetic. Radiația e între 9,82 și 10,18 µSv/h, deci
  `rad_norm` e între 0,964 și 1,0, iar la `safe` termenul stă între 1,93 și 2,00 pe toată harta,
  pe când `pantă × teren` variază între 1,0 și 12,0. Două urmări:
  radiația nu ghidează traseul, iar preset-ul `safe` ajunge să penalizeze panta relativ mai
  puțin decât `fast` (la limita de pantă, pe rocă: 6,0 față de 3,0 pe plat la `safe`, adică 2×;
  4,5 față de 1,5 la `fast`, adică 3×). Am implementat exact formula cerută. Varianta min–max,
  `(rad − min) / (max − min)`, ar face termenul să varieze între 0 și `w_radiation`; e o
  schimbare de o linie și nu strică testul „plat, rocă, radiație 0 → exact 1,0”.
- Nimic blocant.
- Pentru oameni, de știut: `.venv` nu exista local. L-am creat cu `python -m venv .venv` și
  `pip install -r backend/requirements.txt` (exact lista înghețată, fără pachete în plus, fără
  `npm install`). Situl sintetic l-am generat cu `pipeline/make_synthetic_site.py`, nemodificat.
  Ambele sunt în `.gitignore`.

## Presupuneri

Constante fără sursă, pentru rolul 1 (de documentat sau de înlocuit cu valori cu sursă).
Deocamdată sunt cele găsite în schelet; nu am schimbat niciuna.

| Unde | Constantă | Valoare | Ce înseamnă |
|---|---|---|---|
| `types.Limits` | `o2_reserve_pct` | 30 % | rezerva de O₂ la sosirea în habitat |
| `types.Limits` | `sunset_margin_min` | 30 min | marja față de apusul efectiv |
| `types.Limits` | `max_slope_deg` | 25° | panta maximă pe jos, în costum |
| `types.Limits` | `max_dose_msv` | 1,0 mSv | doza maximă pe ieșire |
| `costmap.PRESETS` | `w_hazard` / `w_radiation` / `w_science` | safe 10 / 2 / 0,15; fast 4 / 0,5 / 0,2; science 6 / 1 / 0,4 | ponderile celor 3 preset-uri |
| `costmap.TERRAIN_FACTOR` | rocă / regolit / nisip / bolovani | 1,0 / 1,2 / 1,8 / 3,0 | multiplicator de cost pe teren |
| `costmap` | `SLOPE_K` | 3,0 | la limita de pantă, mersul costă de 1 + 3 = 4 ori mai mult decât pe plat; forma pătratică `1 + K·(s/max)²` e tot o alegere |
| `costmap` | normalizarea radiației | `radiație / max(radiație pe sit)` | radiația intră în cost ca fracție din maximul sitului, nu în µSv/h; costul nu e comparabil între situri |
| `costmap` | `RADIATION_EPS` | 1e-9 | protecție tehnică la împărțire când radiația e zero peste tot, nu fizică |
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

Doar în teste (nu afectează produsul):

| Unde | Constantă | Valoare | Ce înseamnă |
|---|---|---|---|
| `tests/core/grids.py` | `WALL_SLOPE_DEG` | 40° | panta peretelui din grilele de test, aleasă peste limita de 25° |
