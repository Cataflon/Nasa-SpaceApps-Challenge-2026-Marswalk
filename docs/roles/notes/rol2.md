# Note rolul 2

## Gata

Teste: `python -m pytest tests/core` → 173 trecute, plus 2 lente (`-m slow`)
(`test_decision` 6, `test_grid` 14, `test_costmap` 27, `test_routing` 62, `test_budget` 11,
`test_daylight` 9, `test_stops` 14, `test_planner` 7, `test_hazards` 11, `test_alternatives` 8,
`test_benchmark` 4 + 2 lente).

### R2-11: benchmark, generatorul de furtuni și calibrarea conului

**Copilot față de „doar planul”, 100 de scenarii (seed 42), habitat → `clay_delta` → habitat:**

| Metrică | Doar planul | Copilot |
|---|---|---|
| Ieșiri încheiate în siguranță | 56 % | **83 %** |
| Ieșiri cu expunere ≥ 0,3 (pe mișcarea reală a furtunii) | 44 % | 17 % |
| O₂ la sosire, minim / mediu | 71,8 % / 71,8 % | 57,2 % / 78,5 % |
| Doză medie | 0,0253 mSv | 0,0192 mSv |
| Știință colectată | 100 % | 52 % |

Pe tipuri (sigur / total): vârtejuri 56/67 → 62/67, fronturi 0/27 → 18/27, furtuni regionale
0/6 → 3/6. În niciun scenariu copilotul nu e mai puțin sigur decât planul. Decizii pe cele 100
de scenarii: 38 CONTINUE, 24 REROUTE, 31 WAIT, 42 RETURN, 17 EMERGENCY. Prețul siguranței:
copilotul renunță la țintă în aproape jumătate din ieșiri. Ultimele 3 furtuni regionale ajung
înainte ca astronautul să poată fi acasă.

- `storms.py` (nou): generator propriu, cu `default_rng((seed, i))` pe scenariu (primele
  scenarii sunt aceleași pentru orice n). Tipul după ponderi fixe; furtuna e țintită astfel
  încât marginea zonei periculoase să atingă traseul într-un minut aleator. Mișcarea reală are
  zgomot: viteza AR(1) cu 15 %, direcția derivă 1°/min. Mărimea reală e constantă; doar
  predicția are con. Dimensiunile și vitezele vin din registru: vârtejuri 100-135 m (§3.1),
  front 30 × 5 km la 10-20 m/s (§3.2), furtună regională cu rază ≈ 1000 km (§3.2).
- `benchmark.run_benchmark(n, seed, site=None)`: pași de 5 min. Copilotul vede pericolul
  observat (poziția reală de acum + viteza din ultimele 5 min) și decide prin `generate` →
  `choose`. Siguranța se judecă pe mișcarea reală. Reguli de simulare: decide doar dacă primul
  contact prezis e în ≤ 30 min (`REACT_WINDOW_MIN`); RETURN e definitiv; cel mult 8 decizii.
- **Conul de predicție, decizie luată cu utilizatorul:** calibrarea cu un `SIGMA_V` absolut
  (m/s) dădea 2,96 m/s (1,52 doar pe vârtejuri, 4,34 doar pe fronturi). Cu ea, copilotul alegea
  RETURN de la plecare în toate scenariile (100 % sigur, 0 % știință), pentru că o singură viteză
  absolută nu servește deodată fronturi de 15 m/s și vârtejuri de 4 m/s. Am trecut la un **con
  relativ la viteză**: semiaxele cresc cu `SIGMA_REL × |v| × 60 × Δ`. `SIGMA_V` a rămas în
  fișier, nefolosită.
- **`SIGMA_REL = 0,35`**, calibrat cu `calibrate_sigma_v(100, 42)`: cel mai mic coeficient pentru
  care centrul real e în elipsa prezisă în ≥ 95 % din cazuri, la fiecare orizont 10-180 min
  (fără furtunile regionale). Exemplul din `live_messages.json` corespunde lui 0,1; testele care
  îl reproduc folosesc 0,1 explicit. Calibrarea e pe modelul nostru de zgomot (nivel C), nu pe
  date MEDA.
- **Fereastra de reacție de 30 min e necesară.** Fără ea, copilotul reacționa la contacte prezise
  peste 100 de minute, unde conul de 95 % acoperă tot traseul, și alegea RETURN din habitat.

### R2-10: `alternatives.generate`

- Întoarce, nevalidate, în ordinea: `current` (CONTINUE), ocolirile `detour_<latură>` (REROUTE,
  sortate după id), `wait` (WAIT), `return` (RETURN). Cifrele vin din `route_budget` pe tot
  traseul până la habitat, pornind de la t_min, O₂ și doza curente.
- Ocolirile: `astar_spacetime` cu fiecare preset (safe, fast, science), `downsample=5`, orizont
  = min(180, momentul în care pericolul iese din dreptunghiul traseului, eșantionat din 10 în 10
  min). Măștile de blocare se calculează o dată și se refolosesc între preset-uri. Traseele
  identice se elimină (rămâne cel cu riscul cel mai mic). Latura: semnul produsului vectorial
  dintre direcția poziție → țintă și abaterea medie (nord/sud, sau est/vest dacă dreapta e aproape
  nord-sud); a doua cu aceeași latură primește sufixul preset-ului. Așteptările din A* spațiu-timp
  intră în buget ca staționări.
- `wait`: cel mai mic W din {5, 10, …, 90} pentru care nici poziția în timpul așteptării, nici
  traseul curent pornit la t + W nu mai sunt lovite. Dacă niciun W nu ajunge: W = 90, iar
  varianta trece prin pericol (validatorul o elimină).
- `return`: `path_home` din cache; dacă trece prin pericol, `astar_spacetime` spre habitat.
- `crosses_hazard = risk ≥ HIT_THRESHOLD` (constantă nouă în `hazards`, 0,3, folosită și ca
  prag implicit de `route_hit`), deci riscul și „trece prin pericol” nu se contrazic.
  **Excepție declarată:** pentru RETURN nu se numără pericolele al căror singur răspuns permis e
  RETURN (`HAZARD_RESPONSES`: furtuna regională). Altfel, la o furtună regională orice drum,
  inclusiv cel spre casă, ar fi invalid, iar regula ar da EMERGENCY în loc de RETURN.
- Integrare cu regula: pe grila mică, scena 4 (furtună pe drumul dus) → REROUTE; cu furtună
  regională → RETURN, ambele cu cifre calculate. Pe situl sintetic, furtuna care taie drumul spre
  `clay_delta` → o singură ocolire (cele 3 preset-uri dau același traseu), `detour_west`, +8 min,
  risc 0; `wait` 25 min, risc 0,29; regula alege REROUTE `detour_west`.

### R2-9: `routing.astar_spacetime`

- Starea e (celulă, k), cu k = floor(t / DT_MIN), DT_MIN = 1 min. Măștile `blocked_at` se
  calculează o dată pe interval (K = orizont / DT_MIN), ținute ca `bytes` aplatizați cu bordură:
  la 20 m, 60 de liste Python ar ocupa ≈ 120 MB, iar ca bytes ocupă ≈ 15 MB.
- Mutări: cei 8 vecini, cu aceleași reguli ca `astar` (D2, fără tăierea colțurilor, aceeași
  euristică), plus „aștept pe loc” până la intervalul următor. Interzis: cost inf sau celulă
  blocată în intervalul sosirii. Dincolo de orizont pericolul nu se mai verifică (A* obișnuit):
  e corect doar dacă orizontul acoperă trecerea pericolului.
- **Abatere de la textul pasului (timpul unei mutări):** pasul cerea timpul rotunjit la
  intervale, minimum 1. Pe 20 m o celulă se parcurge în ≈ 0,4 min, deci rotunjirea umfla timpul
  de ≈ 2,5 ori: sosirea ieșea la 123 min în loc de ≈ 60, iar pericolul era verificat la momente
  greșite. Timpul se ține acum exact; doar k (pentru mască și pentru cheia de vizitare) e
  rotunjit în jos, conform definiției k = floor(t / DT_MIN) din pas.
- Plan B, parametru nou `downsample=1` la final: blocuri f × f conservatoare (cost = maximul,
  inf dacă oricare celulă e inf; blocat dacă oricare e blocată; timp = maximul × f). Proiecția
  înapoi pe 20 m se face prin centrele blocurilor, cu Bresenham și timpi interpolați. Blocurile
  de start și de goal iau costul celulei reale. Dacă start și goal cad în același bloc, căutarea
  se face direct pe grila fină. Poate închide un pasaj mai îngust decât un bloc.
- Teste noi: 11. Pe situl sintetic, o furtună care traversează drumul habitat → `clay_delta`:
  traseul A* obișnuit intră în ea (`route_hit` la minutul 19,9); traseele spațiu-timp, la
  `downsample` 1 și 5, o ocolesc (`route_hit` = False) și ajung la 64,4, respectiv 67,2 min,
  față de 58,4 min fără pericol.

### R2-8: `hazards`

- `from_contract(d, cell, t0, shape=None)`: centrul din row/col devine metri la centrul celulei,
  `(row + 0,5) × cell`; valori implicite pentru `angle_deg`, `velocity_ms` și `id`. Un
  `regional_storm` fără centru acoperă toată grila (centrul grilei, semiaxe = diagonala); fără
  `shape` aruncă ValueError.
- `predict`: centrul + viteza × Δ × 60. **Decizie: semiaxele cresc aditiv**, cu `SIGMA_V × 60 × Δ`.
  Varianta multiplicativă veche (`UNCERTAINTY_GROWTH_PER_MIN`, +0,5 %/min) a rămas în fișier,
  marcată nefolosită. Motive: exemplul din `live_messages.json` crește ambele semiaxe cu aceeași
  valoare (+150 m în 10 min), iar fizic eroarea de poziție crește cu eroarea de viteză × timp.
  `SIGMA_V = 0,25 m/s` (+15 m/min) reproduce exact exemplul; e nivel C, de calibrat în R2-11.
- `hazard_field`: vectorizat, doar pe dreptunghiul care încadrează elipsa rotită; float32,
  maximul peste pericole. Convenție pentru unghi: de la est, în sensul acelor de ceasornic pe
  hartă (y spre sud).
- `route_hit` și funcția nouă `route_risk` folosesc aceeași funcție internă (intensitatea în
  fiecare punct la minutul sosirii, vectorizat), deci nu se pot contrazice; un test o verifică.
- `to_contract`: forma exactă din `tick.hazards[]`. Testul reproduce prognoza din contract: col 30
  → 105 la +10 min și → 180 la +20 min, cu semiaxe 1950×1250 și 2100×1400.

### R2-7: `planner.plan_route` — gata pentru `POST /api/route`

- Întoarce dict-ul cu exact cheile din `shared/contracts/route_response.json` (testul citește
  fișierul). Numere rotunjite: minute și metri la întreg, procente la o zecimală, doza la 3
  zecimale; `path` ca liste `[row, col]`; doar tipuri Python simple (`json.dumps` merge).
- Etape: `static_cost` (cache) → `reverse_dijkstra` pe cost (cache per sit și preset; drumurile
  habitat ↔ țintă vin din `path_home`) → la ≥ 2 ținte, `astar` țintă ↔ țintă o dată pe pereche
  neordonată, timp și O₂ recalculate pe fiecare sens cu `route_budget` → `plan_stops` (plan B
  `brute_force_stops`) → segmente lipite → `route_budget` cu staționările → punct de
  neîntoarcere din `reverse_dijkstra` pe `o2_cost_grid` (cache per sit) → `validator.violations`
  pe un `Alternative` construit din buget → verdict.
- `ValueError` pentru ținte necunoscute (cu id-urile) sau inaccesibile: rolul 3 → 422.
- Exemple pe situl sintetic: `["clay_delta"]` → GO, 145 min, O₂ final 73,2 %. Toate cele 3 ținte,
  limită 480 min → ordinea `clay_delta`, `carbonate_rim`, `olivine_floor`; CAUTION, 337 min,
  O₂ final 37,7 % (sub rezervă + 10).

Timpul lui `plan_route` pe situl sintetic și defalcarea pe etape:

| Caz / etapă | Timp |
|---|---|
| `plan_route(["clay_delta"])`, primul apel pe sit (rece) | 1,27 s (ținta: < 3 s) |
| `plan_route` cu toate cele 3 ținte, rece | 1,55 s (ținta: < 3 s) |
| același, al doilea apel pe același sit (cache cald) | 0,001 s (1 țintă) / 0,27 s (3 ținte) |
| etapa: `static_cost` | 0,008 s |
| etapa: `reverse_dijkstra` pe cost | 0,64 s, o dată per (sit, preset) |
| etapa: `o2_cost_grid` + `reverse_dijkstra` pe O₂ | 0,66 s, o dată per sit |
| etapa: `astar` țintă ↔ țintă, 3 perechi | 0,16 s |
| etapa: `plan_stops`, 3 ținte | ≈ 0,1 s (diferența din cazul cald cu 3 ținte) |
| etapa: `route_budget` + punct de neîntoarcere | ≈ 1 ms |

Fără importul OR-Tools (0,75 s, o dată per proces, vezi „Cereri”).

### R2-6: `stops` (CP-SAT + forță brută)

- O singură definiție a problemei (clasa internă `_Problem`), folosită de ambele metode:
  aceleași valori scalate, rotunjite o singură dată (minute × 10, O₂ × 100, valoare × 100),
  aceeași regulă de fezabilitate, același obiectiv lexicografic. Rata de repaus vine din
  `budget.O2_PCT_PER_MIN_REST`. Cifrele din `StopPlan` sunt recalculate din valorile reale.
- `plan_stops`: `AddCircuit` cu buclă pe fiecare țintă (sărită). Am pus buclă și pe habitat,
  pentru turul gol: fără ea, `AddCircuit` nu admite un circuit doar cu habitatul, deci planul gol
  ar fi imposibil. Bucla pe habitat obligă toate țintele să fie sărite.
  Etapa 1: `maximize Σ valoare × BIG − durată`, cu BIG > orice durată posibilă.
  **Etapa 2 (criteriul 3):** cu timpi simetrici, un tur și inversul lui au aceeași valoare și
  durată, deci egalitățile sunt frecvente. Cu valoarea și durata fixate, se alege pas cu pas,
  de la habitat, nodul următor cel mai mic (întâi întoarcerea acasă, apoi id-urile alfabetic):
  câte o rezolvare per oprire. Fără ea, CP-SAT și forța brută ar da ordini inverse.
  Statusul etapei 1 decide `optimal`.
- `brute_force_stops`: semnătura `*args, **kwargs` păstrată; argumentele se leagă de
  semnătura lui `plan_stops` (`inspect.signature(...).bind`). Toate permutările tuturor
  submulțimilor; > 6 ținte → `ValueError`; lista goală e soluție validă.
- Pe 30 de instanțe aleatoare (2-5 ținte, valori științifice întregi, deci cu egalități),
  cele două metode dau aceeași ordine, aceeași valoare și aceeași durată.

### R2-5: `daylight`, plan A (Mars24)

- `sunrise_sunset_min(lat, lon, sol_start_utc)`: Mars24 (Allison & McEwen 2000) fără termenii
  PBS de perturbație, doar `math`. Rezultatul e în **minute terestre** de la `sol_start_utc`;
  o oră marțiană = 3698,98 s. `lon_deg` e longitudine estică (Mars24 folosește vestică; conversia
  e în cod). Apusul = primul apus de după start; răsăritul = apus − durata zilei (poate fi
  negativ dacă ieșirea începe ziua), deci răsărit < apus mereu.
- Funcții publice noi: `mars_ls_deg`, `solar_declination_deg`, `ltst_hours`, `mst_hours`.
- Verificat față de exemplul din pagina Mars24 (2000-01-06 00:00 UTC): Ls = 277,19° și
  MST = 23,994 h. La aterizarea Perseverance (2021-02-18 20:55 UTC): Ls 5,65°, ora locală
  15,44 h, zi de 12,18 ore marțiene. La 2022-01-01: Ls 150,65°, zi de 12,62 ore marțiene.
- **Eroare estimată:** Ls ≈ 0,01° din perturbațiile omise (neglijabil). Răsăritul și apusul:
  ≈ ±5 min, dominat de alegerea `h0 = −0,5°` (refracție și disc). Praful e tratat separat, de
  `effective_sunset_min`.
- Greșeală găsită și corectată în timpul pasului: constanta 44796 din formula MST e în soluri,
  nu în ore (decalaj de 12 h). Testul nou pe exemplul Mars24 o prinde.

### R2-4: bugetul (`budget.py`) + câmpurile D4 din `types.Budget`

- `types.Budget`: câmpuri noi la final, cu valoare implicită: `eta_min`, `o2_pct`, `dose_msv_cum`
  (câte una pe punct, la sosirea în punct).
- `route_budget(...)`: vectorizat cu numpy. Parametri opționali noi, la final: `dwell_min_at`,
  `o2_start_pct=100`, `fatigue=1`, `limits=None`. `dose_rate_usv_h` acceptă număr sau grila
  `radiation`. Definițiile pentru `duration_min` și `return_by_min` sunt în docstring.
- `point_of_no_return`: ultimul index dintr-un șir neîntrerupt de la start cu
  `o2 − cost_to_home_o2 ≥ rezervă`; `None` dacă nici startul nu respectă rezerva.
- Funcții noi: `o2_cost_grid(site)` și `minutes_grid(site)`, cu panta luată la urcare
  (pesimist) și `inf` pe celulele interzise. Cu `reverse_dijkstra` dau O₂-ul și timpul până acasă.
- **Exemplu numeric:** 1 km pe plat = 19,9 min și 3,85 % O₂ (v = 0,84 m/s, P = 273 W).
  5 h de mers pe plat = 58,2 % O₂, în intervalul cerut de 40-60 %.
- Pe situl sintetic, habitat → `clay_delta` → habitat (241 de puncte, 5,8 km, 30 min la țintă):
  145 min, O₂ final 73,2 %, doză 0,024 mSv.

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
  8 vecini, euristică octilă × costul minim finit (admisibilă, deci traseul e optim), coadă
  `(f, g, idx)`, adică `(f, g, row, col)`, cu eliminare leneșă după `g`.
- **Costul unei mutări (D2), schimbat la R2-3:** lungimea pasului × media costurilor celor două
  celule, `pas × (cost[a] + cost[b]) / 2`. Înainte era „pas × costul celulei în care intri”,
  care nu e simetric: drumul optim X → habitat nu era mereu inversul drumului optim habitat → X.
  Cu media, costul e același în ambele sensuri, deci `path_home` dă exact inversul lui A*.
  Euristica rămâne admisibilă (fiecare jumătate de pas costă cel puțin `c_min / 2`).
- **Fără tăierea colțurilor:** o diagonală e permisă doar dacă ambele celule ortogonale pe
  lângă care trece sunt finite. Un perete de celule care se ating doar în colțuri e deci închis.
- `None` dacă start sau goal e pe o celulă interzisă, ori sunt izolate una de alta; `[start]`
  dacă start == goal. `ValueError` dacă start sau goal e în afara grilei ori harta are costuri
  negative. Celulele din traseu sunt `int` simplu (merg în JSON).
- `backend/tests/core/test_routing.py` (nou): optimalitatea e verificată față de un Dijkstra
  scris independent în test (aceeași convenție de cost și de colț), pe 8 grile aleatoare cu seed fix.

### R2-3: `routing.reverse_dijkstra` + `path_home`

- `reverse_dijkstra(cost, habitat) -> (cost_to_home, parent_index)`: un singur Dijkstra pornit
  din habitat. `cost_to_home` e float64 de forma grilei (0 la habitat, `inf` unde nu se poate
  ajunge). `parent_index` e int32, cu indexul plat fără bordură (`row × W + col`) al pasului
  următor spre casă și -1 la habitat și la celulele inaccesibile. Aceleași reguli ca `astar`
  (convenția D2, fără tăierea colțurilor). `ValueError` pentru habitat în afara grilei sau
  valori negative. Habitat pe celulă interzisă → totul `inf`, toți părinții -1.
- `path_home(parent_index, start)`: urmează părinții până la habitat, cu ambele capete.
  Celulă inaccesibilă → listă goală; start = habitat → `[habitat]`. Protecție la cicluri:
  cel mult H × W pași, apoi `RuntimeError`.
- Deosebirea habitat / inaccesibil (ambele au -1): habitatul e celula spre care arată cel puțin
  un vecin. Caz limită: un habitat complet izolat dă tot listă goală (nu se poate deosebi doar
  din `parent_index`).
- **Utilizare dublă (pentru R2-4):** aceeași funcție, pe o grilă de O₂ pe celulă, dă O₂-ul
  necesar până acasă din orice punct; pe o grilă de minute pe celulă, dă timpul până acasă.
  Test: `test_dual_use_minutes_grid_gives_time_to_home`.
- Teste noi în `test_routing.py`: 21. Pe 4 grile aleatoare (costuri reale, fără egalități):
  din fiecare celulă, `path_home` se termină la habitat, costul de-a lungul lui e egal cu
  `cost_to_home`, și e exact inversul lui `astar(habitat → celulă)`.
- Pe situl sintetic: 97,96 % din celule ajung acasă; 1766 de celule permise sunt totuși izolate
  de habitat (închise între pante). Traseele spre cele 3 ținte, din `path_home`, sunt identice
  cu inversul celor din `astar`.
- `astar_spacetime` e încă neimplementat.

### Timpi măsurați pe situl sintetic 500×500

Python 3.14.6, numpy 2.5.4; mediana din mai multe rulări.

| Funcție | Măsurat | Țintă |
|---|---|---|
| `grid.pad_and_flatten(cost)` | 5,4 ms (max 7,1 ms) | fără țintă proprie; inclus în timpul lui `astar` |
| `costmap.static_cost(site, "safe")`, fără cache | 7,1 ms (max 10,4 ms) | < 0,2 s |
| `costmap.static_cost(site, "safe")`, din cache | 0,0003 ms | < 0,2 s |
| `routing.astar`, habitat → `clay_delta` (121 celule, 2,9 km) | 29–35 ms, după preset | < 1 s |
| `routing.astar`, habitat → `carbonate_rim` (181 celule, 4,1 km) | 48–64 ms | < 1 s |
| `routing.astar`, habitat → `olivine_floor` (131 celule, 2,9 km) | 35–38 ms | < 1 s |
| `routing.astar`, colț la colț, (0,0) → (499,499), 537 celule | **1,14 s (max 1,25 s)** | < 1 s, **depășit** |
| `routing.astar`, țintă izolată (fără traseu, explorează toată harta) | **1,42 s (max 1,56 s)** | < 1 s, **depășit** |
| `routing.reverse_dijkstra`, `safe` / `fast` | 0,64 s / 0,69 s (max 1,16 s / 0,73 s) | < 2 s, o dată per hartă |
| `routing.reverse_dijkstra`, `science` | 1,26 s (max 1,28 s) | < 2 s, o dată per hartă |
| `routing.path_home` spre cele 3 ținte (121–181 celule) | 0,02–0,03 ms | fără țintă proprie |
| `routing.path_home` din cea mai depărtată celulă (301 celule) | 0,06 ms | fără țintă proprie |
| `budget.route_budget`, 241 de puncte, cu staționare și grila de radiație | 0,53 ms (max 0,85 ms) | < 50 ms |
| `budget.point_of_no_return`, 241 de puncte | 0,016 ms | < 50 ms |
| `budget.o2_cost_grid` / `minutes_grid` | 17 ms / 16 ms | fără țintă proprie |
| `routing.reverse_dijkstra` pe `o2_cost_grid` | 0,64 s | < 2 s, o dată per hartă |
| `daylight.sunrise_sunset_min` | 3,9 µs pe apel | instant |
| `stops.plan_stops`, 10 ținte | 0,17-0,19 s (max 0,20 s) | < 1 s pentru ≤ 10 ținte |
| `stops.plan_stops`, 6 / 15 ținte | 0,03 s / 0,93 s | 15 e peste țintă, doar informativ |
| `stops.brute_force_stops`, 6 ținte (1957 de ordini) | 0,018 s | fără țintă proprie |
| importul `ortools` (o dată per proces, la primul apel) | 0,75 s | de știut pentru primul `POST /api/route` |
| `hazards.hazard_field`, 500×500, furtună locală + dust devil | 1,4 ms | < 50 ms pe tick |
| `hazards.hazard_field`, 500×500, plus furtună regională (toată grila) | 7,7 ms (max 10,3 ms) | < 50 ms pe tick |
| `hazards.route_hit` / `route_risk`, 241 de puncte, 3 pericole | 0,11 ms | < 50 ms pe tick |
| `hazards.to_contract` (cu 8 pași de prognoză) | 0,04 ms | < 50 ms pe tick |
| `routing.astar_spacetime`, habitat → `clay_delta`, furtună, orizont 60 min, `downsample=5` | 0,07 s | < 1,5 s |
| `routing.astar_spacetime`, același caz, `downsample=1` (grila de 20 m) | 0,41 s | < 1,5 s |
| `routing.astar_spacetime` fără pericol, `downsample` 5 / 1 | 0,06 s / 0,45 s | < 1,5 s |
| cele 60 de măști `hazard_field ≥ 0,3` (incluse mai sus) | 0,025 s | — |
| `alternatives.generate`, situl sintetic, furtună pe traseu, cache cald | 0,16 s | < 2 s |
| `alternatives.generate`, primul apel pe sit (Dijkstra spre casă + `minutes_grid` intră în cache) | 0,79 s | < 2 s |
| `benchmark.run_benchmark(100, 42)` | 51-70 s | < 2 min |
| `benchmark.calibrate_sigma_v(100, 42)` | 2,2 s | fără țintă proprie |

De știut despre timpi: rulat imediat după testul de 100 de scenarii (peste un minut de calcul
susținut), testul `plan_route < 3 s` a picat o dată, cu 3,29 s. Singur trece (1,5 s), iar într-un
script, chiar după un benchmark, durează 1,34 s; GC-ul nu schimbă nimic. Cauza probabilă e
scăderea frecvenței procesorului laptopului sub sarcină. Testele lente nu rulează implicit, deci
suita normală (și CI-ul) nu e afectată.

Timpii lui `astar` sunt cu regula „fără tăierea colțurilor” și cu convenția D2 (media celor două
celule). Față de R2-2, traseele spre ținte au rămas sub 65 ms; cazul colț la colț a crescut de
la 0,64 s la 1,14 s. Ambele cazuri depășite sunt extreme (diagonala întregii hărți, respectiv
fără traseu), nu trasee de planificare. Diferența de timp între preset-uri la
`reverse_dijkstra` (`science` aproape dublu) nu o explic încă; e reproductibilă și sub țintă.

Pe situl sintetic: 1,34 % din celule sunt interzise. Costul finit e între 1,03 și 18,04 la
`safe`, 1,02 și 12,02 la `science`, 1,01 și 7,51 la `fast`. Termenul de radiație e între 0 și
0,074 la `safe` (`rad_norm` între 0 și 0,037).

## În lucru

- Toate funcțiile din `ROL2_algoritmi.md` sunt implementate (P0, P1, P2). Rămân de făcut doar
  dacă se cer: registrul `core/params.py` propus în `PARAMETRI_REFERINTA.md` și calibrarea
  zgomotului din `storms.py` pe date MEDA reale.
- De preluat din `docs/roles/PARAMETRI_REFERINTA.md`, la pașii care le ating (constantele
  din `budget.py` sunt deja preluate la R2-4):
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
  e izolată, răspunsul vine abia după ~1,4 s, pentru că A* trebuie să epuizeze harta. Verificarea
  ieftină, înainte de a chema `astar` de la habitat: `cost_to_home[celulă] == inf` din
  `reverse_dijkstra` (calculat o dată per hartă). Pentru traseul de întoarcere nu e nevoie de
  `astar` deloc: `path_home(parent_index, celulă)` durează sub 0,1 ms.
- **Pentru rolul 3 (motorul live, după R2-11):** conul de predicție e acum relativ la viteză
  (`hazards.SIGMA_REL = 0,35`). La orizonturi lungi conul acoperă tot traseul, deci chemați
  `alternatives.generate` doar dacă `route_hit` dă un contact în următoarele 30 de minute
  (`benchmark.REACT_WINDOW_MIN`); altfel continuați și verificați la tick-ul următor. După un
  RETURN, benchmark-ul nu mai replanifică; recomandăm la fel în motor.
  `GET /api/benchmark` → `benchmark.run_benchmark(n, seed)`: 100 de scenarii durează ≈ 1 min,
  deci rezultatul trebuie pus în cache sau calculat la pornire, nu la fiecare cerere.
- **Pentru rolul 1:** zgomotul mișcării furtunilor din `storms.py` (viteză ±15 %, direcție
  1°/min) e o presupunere. Registrul trimite la variabilitatea vântului MEDA [S7]; cu cifre de
  acolo, `calibrate_sigma_v` dă imediat un `SIGMA_REL` cu sursă.
- **Pentru rolul 3: `alternatives.generate` e gata.** Semantica lui `path` în fiecare
  `Alternative`: traseul rămas COMPLET, de la poziția curentă până la habitat (inclusiv opririle
  rămase); la `wait`, doar `[position]`, ca în `live_messages.json`. Celulele sunt tupluri
  `(row, col)` (în JSON devin liste). Variantele vin nevalidate: le trimiteți direct la
  `decision.choose`. `remaining_path` trebuie să înceapă la `position` (altfel ValueError).
  Un apel durează ≈ 0,16 s pe situl sintetic, cu cache-ul cald; primul apel pe un sit, ≈ 0,8 s.
  Apelați-l doar la tick-urile în care `hazards.route_hit` pe traseul rămas dă True.
- **Pentru rolul 3: planner-ul e gata.** `POST /api/route` poate trece de pe mock pe
  `planner.plan_route(site, start, stops, preset, start_time_min, max_duration_min,
  return_to_habitat)`. Întoarce exact forma din `route_response.json`; `route_id` e mereu
  `"plan_0"` (îl suprascrieți din stocul vostru). `ValueError` → 422 (ținte necunoscute sau
  inaccesibile). `point_of_no_return` poate fi `null` dacă nici startul nu respectă rezerva.
  Primul apel pe un sit durează ≈ 1,3-1,6 s (două Dijkstra, puse apoi în cache); următoarele,
  sub 0,3 s. Un `plan_route` de încălzire la pornire mută costul acolo.
- **Pentru oameni (pantă maximă):** validatorul din planner folosește 20° (registru, A [S26]);
  `Limits` și `meta.json` au încă 25°. Harta de cost permite deci 20-25°, iar un traseu prin
  asemenea pante iese NO-GO cu `SLOPE`. Pe situl sintetic nu se întâmplă (panta maximă pe
  traseele spre ținte: 7,3°). Rezolvarea curată e `max_slope_deg = 20` în `meta.json` și `Limits`.
- **Pentru rolul 3:** primul apel la `stops.plan_stops` dintr-un proces plătește importul
  OR-Tools (0,75 s). Dacă primul `POST /api/route` trebuie să fie rapid, un `import
  ortools.sat.python.cp_model` la pornirea backendului mută costul acolo.
- **Pentru oameni, de știut (R2-4):** pasul propunea `M_TOTAL` ≈ 170 kg și păstrarea
  constantelor de O₂ existente (0,12 și 0,0006). Am luat valorile din registru, după regula
  „constantele se iau din PARAMETRI_REFERINTA.md”: `M_TOTAL` 196 kg (B), 0,125 și 0,000711 (B).
  Cu ele, 5 h pe plat consumă 58,2 % O₂ (cu cele vechi: ≈ 53 %); ambele sunt în 40-60 %.
- **Pentru rolul 1 (doză):** `route_budget` folosește grila `radiation` așa cum vine, în µSv/h.
  Registrul (§2) arată că ≈ 10 pe situl sintetic e de fapt doză absorbită (µGy/h), iar doza
  echivalentă e ≈ 28 µSv/h. Dozele calculate sunt deci de ≈ 2,8 ori prea mici până se corectează
  stratul.
- **Pentru oameni, de știut:** pasul R2-3 cere să citesc `docs/PARAMETRI_REFERINTA.md`, dar
  fișierul e la `docs/roles/PARAMETRI_REFERINTA.md`. L-am citit de acolo.
- **Pentru oameni, de știut (convenția D2):** textul lui D2 nu e în repo. Costul unei mutări l-am
  ales, cu acordul utilizatorului, ca media celor două celule (vezi R2-3 la „Gata”), și am
  schimbat `astar` pe ea. Dacă D2 spune altceva, trebuie refăcute `astar` și `reverse_dijkstra`.
- **Pentru oameni, de decis (start pe celulă interzisă, în live):** conform pasului R2-2, `astar`
  întoarce `None` dacă celula de start are cost `inf`. În ieșirea live, dacă un pericol e pus
  ca `inf` peste celula în care se află astronautul, din acea celulă nu mai iese niciun traseu.
  De hotărât la `astar_spacetime` / `alternatives.generate`: fie pericolul intră doar ca cost
  finit (`hazard_cost`), fie celula de start e exceptată acolo.
- **Pentru oameni, de decis (preset-urile dau aproape același traseu pe situl sintetic):**
  cu convenția D2 actuală, traseul habitat → `clay_delta` e **identic** la toate cele trei
  preset-uri. Spre `carbonate_rim` și `olivine_floor`, `safe` diferă de `fast` (174, respectiv
  126 de celule comune), iar `science` și `fast` coincid la toate cele 3 ținte. Cauza: situl
  sintetic e aproape plat (pantă mediană 0,43°, percentila 90 la 1,5°), deci `f_slope` e ≈ 1
  aproape peste tot, la orice `slope_k`.
  Testul din R2-2 care cerea `safe ≠ fast` spre `clay_delta` a picat după schimbarea D2; l-am
  înlocuit cu ce e garantat (fiecare preset își găsește traseul optim după propria hartă).
  Urmare pentru `alternatives.generate`: preset-urile singure nu produc ocoliri distincte pe
  acest sit. Ocolirile vor trebui să vină din termenul de pericol (`w_hazard × câmp`) sau din
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
| `routing` (`astar`, `reverse_dijkstra`) | costul unei mutări (D2) | lungimea pasului × media costurilor celor două celule | convenție, nivel C: jumătate de pas în fiecare celulă; aleasă ca să fie simetrică, deci drumul spre casă e inversul drumului de la casă |
| `routing` (`astar`, `reverse_dijkstra`) | tăierea colțurilor | interzisă | o diagonală cere ambele celule ortogonale libere; regulă de siguranță (un obstacol de 20 m nu se traversează pe colț), nu o valoare măsurată |
| `budget` | `MARS_G_FACTOR` | 1,0 | C: rămâne 1,0 intenționat. Tobler e calibrată pe Pământ, dar pe Marte viteza e limitată de costum (`SUIT_FACTOR`), nu de gravitație; o corecție pentru 0,38 g ar număra de două ori |
| `budget` | `ETA_UP` | 0,22 | C: eficiența musculară la urcare (tipic 0,2-0,25); registrul spune că nu e calibrată pe [S32] |
| `budget.return_by_min` | „punctul cel mai îndepărtat” | distanța în linie dreaptă față de start; la egalitate, primul | C: convenție; întoarcerea = restul traseului după acel punct |
| `budget.point_of_no_return` | șir neîntrerupt de la start | se oprește la prima încălcare a rezervei | C: convenție; pe drumul de întoarcere condiția poate redeveni adevărată, dar acolo nu mai e „neîntoarcere” |
| `budget.o2_cost_grid` / `minutes_grid` | panta celulei luată la urcare | pesimist | C: direcția întoarcerii nu se știe dinainte; drumul ales de `reverse_dijkstra` e cel cu cel mai puțin O₂, nu neapărat cel mai ieftin după cost |

Constante din `budget.py` care au nivel și sursă în registru (scrise și în cod): `SUIT_FACTOR`
0,6 (B [S22][S24]), Tobler 6 km/h, −3,5, +0,05 (B, §4.1), `P_REST_W` 176 W (A [S31]),
`M_TOTAL_KG` 196 kg (B [S24][S34], de confirmat), `G_MARS` 3,71 (A), `C_LEVEL` 0,59 J/(kg·m)
(B [S28]), `O2_PCT_PER_MIN_PER_WATT` 0,000711 (B [S31][S33]), `O2_PCT_PER_MIN_REST` 0,125 (B).
| `hazards` | `UNCERTAINTY_GROWTH_PER_MIN` | 0,005 | NEFOLOSITĂ din R2-8 (înlocuită de `SIGMA_V`); păstrată doar pentru compatibilitate |
| `hazards` | `SIGMA_V` | 0,25 m/s | NEFOLOSITĂ din R2-11 (înlocuită de `SIGMA_REL`); păstrată doar pentru compatibilitate |
| `hazards` | `SIGMA_REL` | 0,35 | C (calibrat pe modelul nostru de zgomot, nu pe MEDA): semiaxele cresc cu 0,35 × viteza × timp; acoperă 95 % din cazuri la toate orizonturile 10-180 min |
| `storms` | `KIND_WEIGHTS` | vârtej 0,6 / front 0,3 / regională 0,1 | C: ponderi fixe |
| `storms` | `DUST_DEVIL_SPEED_MS` | 2-6 m/s | C: „câțiva m/s”, cu vântul de fond (registru §3.1) |
| `storms` | `REGIONAL_SPEED_MS` | 20 m/s | C: limita de sus a vitezelor din registru §3.2 |
| `storms` | `INTENSITY` | vârtej 0,9 / front 0,7 / regională 0,9 | C (0,7 ca în exemplul din contract) |
| `storms` | zgomotul mișcării | viteză AR(1): 15 %, corelație 0,9/min; direcție 1°/min | C: fără date MEDA descărcate; de înlocuit cu [S7] |
| `benchmark` | `REACT_WINDOW_MIN` | 30 min | C: copilotul decide doar pentru contacte prezise în următoarele 30 min |
| `benchmark` | `MAX_DECISIONS`, `STEP_MIN` | 8 decizii, pași de 5 min | C: limite de simulare |
| `benchmark` | viteza estimată | deplasarea observată în ultimele 5 min | C: estimatorul cel mai simplu |

Din registru, cu sursă (scrise și în cod): vârtejuri cu diametru 100-135 m (A [S16][S17]),
front 30 × 5 km (B [S18][S19]) la 10-20 m/s (B [S20]), furtună regională cu rază ≈ 1000 km
(B [S21]).
| `hazards` | profilul intensității | `intensity × max(0, 1 − d²)` | C: formă parabolică, maxim în centru, zero pe marginea elipsei; din docstring-ul scheletului |
| `hazards` | unghiul și centrul celulei | unghi de la est, în sensul acelor de ceasornic pe hartă; centrul celulei la `(row + 0,5) × cell` | C: convenții de coordonate |
| `hazards` | `FORECAST_STEPS_MIN` | 10, 20, 30, 45, 60, 90, 120, 180 | orizonturile de predicție |
| `decision` | `RISK_THRESHOLD` | 0,3 | sub acest risc, traseul curent continuă |
| `decision` | `MIN_IMPROVEMENT` | 0,2 | histerezis: alternativa trebuie să fie cu ≥ 20 % mai bună |
| `daylight.effective_sunset_min` | 30 min per unitate de tau peste 0,5 | liniar | cu cât apune „mai devreme” când e praf |
| `daylight` | `SUNRISE_ALTITUDE_DEG` | −0,5° | C: altitudinea Soarelui la răsărit/apus; refracția e neglijabilă în atmosfera subțire, discul solar are ≈ 0,35° |
| `daylight.sunrise_sunset_min` | care răsărit/apus | primul apus de după start, răsăritul aceleiași zile | C: convenție, ca răsărit < apus mereu |

Constante din `daylight.py` cu nivel și sursă (scrise și în cod): coeficienții Mars24 și
formula declinației (A, registru §5), `MARS_HOUR_S` 3698,98 s (A, registru §5),
`TT_MINUS_UTC_S` 69,184 s (A, IERS: 32,184 s + 37 secunde intercalate; registrul nu o conține).
| `stops.solver_params` | `random_seed` 42, `max_deterministic_time` 5,0 | CP-SAT | alegeri de determinism, nu fizică |
| `stops` | scalarea la întregi | minute × 10, O₂ × 100, valoare × 100 | C: rezoluție 0,1 min, 0,01 % O₂, 0,01 valoare; o limită poate fi depășită cu cel mult o rotunjire pe termen |
| `routing.astar_spacetime` | `DT_MIN` | 1 min | C: rezoluția în timp a pericolului; o mască pe minut |
| `routing.astar_spacetime` | `WAIT_COST_FACTOR` | 1,0 | C: un minut de așteptare costă cât un minut de mers pe terenul cel mai bun (cost minim / minutele lui); nici gratuit, nici interzis |
| `routing.astar_spacetime` | blocarea | doar în intervalul sosirii | C: nu se verifică intervalele traversate în timpul unei mutări (< 1 min pe 20 m) |
| `routing.astar_spacetime` | `downsample` | blocuri conservatoare, proiecție prin centre | C: proiecția fină nu e reverificată față de măștile la 20 m |
| `hazards` | `HIT_THRESHOLD` | 0,3 | C: intensitatea de la care un punct e „în pericol” (contact, `crosses_hazard`) |
| `alternatives` | `BLOCK_THRESHOLD` | 0,1 | C: celulele blocate pentru ocoliri, sub pragul de contact. Marja ține riscul ocolirilor clar sub pragul regulii (0,3) și sub penalizarea întoarcerii pentru știință (0,15 la `safe`) |
| `alternatives` | `WAIT_OPTIONS_MIN` | 5, 10, …, 90 min | C: din textul pasului |
| `alternatives` | orizontul ocolirilor | min(180, ieșirea pericolului din dreptunghiul traseului), pas de 10 min | C: dreptunghiul aproximează „zona traseului” |
| `alternatives` | RETURN și pericolele „doar RETURN” | nu se numără la `crosses_hazard` | C: întoarcerea e chiar răspunsul cerut la furtuna regională |
| `planner` | `SOL_START_UTC` | 2026-11-14 14:22 UTC | C: începutul fix al ieșirii, ≈ 08:00 ora locală la Jezero (Ls ≈ 22°); apusul la ≈ 633 min. Fix, ca planul să fie determinist |
| `planner` | `max_duration_min` | termen-limită raportat ca `DAYLIGHT` | C: validatorul nu are o regulă de durată; sosirea după start + durata maximă devine încălcare `DAYLIGHT` (termenul efectiv = minimul dintre apus − marjă și start + durată) |
| `planner` | `return_to_habitat=False` | validat ca și cum traseul s-ar termina acolo | C: O₂-ul și sosirea se iau la ultimul punct; staționarea la ultima țintă nu intră în buget |
| `planner` | `CAUTION_O2_MARGIN_PCT` / `CAUTION_SUNSET_MARGIN_MIN` | 10 puncte / 60 min | din `ROL2_algoritmi.md` (regula verdictului), nu fizică |
| `planner` | profilul de altitudine | 50 de puncte, interpolare liniară pe distanța cumulată | C: convenție de afișare |
| `stops` | criteriul 3 de egalitate | lista de id-uri cea mai mică lexicografic, prefixul înaintea listei mai lungi | C: convenție pentru determinism, cerută de pas |

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
