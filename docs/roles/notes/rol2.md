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

## În lucru

- Urmează D1: `routing.astar` peste `grid.py` (8 vecini, euristică octilă × cost minim,
  tie-break `(f, g, row, col)`).

## Cereri

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
