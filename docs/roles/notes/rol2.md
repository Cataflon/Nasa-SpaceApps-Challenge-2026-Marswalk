# Note rolul 2

## Gata

Teste: `python -m pytest tests/core` → 184 trecute, plus 2 lente (`-m slow`)
(`test_decision` 6, `test_grid` 14, `test_costmap` 27, `test_routing` 65, `test_budget` 11,
`test_daylight` 9, `test_stops` 14, `test_planner` 7, `test_hazards` 11, `test_alternatives` 15,
`test_benchmark` 5 + 2 lente).

### Sesiunea din 15.11: traseul cel mai scurt în metri (`core/tour.py`)

**Înainte:** ordinea opririlor venea din `stops.plan_stops` (CP-SAT: valoare științifică maximă, apoi
durata minimă, apoi id-urile), iar segmentele din A* pe `static_cost` al presetului (pas × media costului
celulelor) și din arborele `reverse_dijkstra` spre casă. Traseul era deci cel mai **ieftin** pe preset,
iar ordinea cea mai **rapidă**. (Specificația V2 nu are §6.2; cerința e cea din sesiune.)

**Acum (`route_metric="distance"`, implicit în `plan_route`):**
- metrica (`tour.py`): pas ortogonal 1000 de unități, diagonal 1414 (1000 = o celulă = 20 m); celulele
  interzise și regula anti-colț ca la A*. Cheia e lexicografică (distanță, preset, row, col), codată într-un
  singur `int`: `pas × (SCALE + h[a] + h[b])`, cu `h = round(PRESET_RES × cost / 2)` (rotunjit pe celulă,
  nu pe pas, ca să rămână exact simetric). SCALE > suma presetului pe orice drum de pe hartă (vezi
  „Presupuneri”), deci presetul alege doar între drumuri la fel de lungi;
- `distance_field`: Dijkstra pe grila bordată, cu heapq și întregi, oprire timpurie la ținte și potențialul
  SCALE × octila minimă spre ținte (A* consistent, cheile rămân exacte). Arborele de părinți e canonic (la
  chei egale câștigă predecesorul cu indexul minim), deci un segment nu depinde de mulțimea de ținte sau de
  cache;
- `tour_matrix`: habitat + toate țintele din meta, o dată per (sit, preset), în cache (referință slabă +
  același tablou `static_cost` + semnătura site_id/versiune/formă/habitat/ținte). Simetrie: nodul i caută
  doar nodurile j > i; segmentele se reconstruiesc din părinți, fără A*;
- `shortest_tour`: ≤ 2 opriri direct, ≤ 12 Held-Karp vectorizat pe măști (straturi după numărul de biți),
  reconstrucție înainte cu cel mai mic id care încă duce la optim (ordinea lexicografică în sensul vizitei;
  un vector de predecesori ar da ordinea minimă citită de la capăt); > 12: cel mai apropiat vecin + 2-opt +
  Or-opt, `approx = True`. Tur închis sau deschis; inaccesibile → `UNREACHABLE`, id-uri necunoscute →
  `UNKNOWN`, fără excepții;
- `plan_route`: ordinea din `shortest_tour`; dacă turul complet încalcă O₂ / apus / doză, `plan_stops` alege
  submulțimea după science_value cu timpii acelorași segmente, iar submulțimea se reordonează după distanță
  (dacă ordinea cea mai scurtă încalcă validatorul și ordinea CP-SAT nu, rămâne cea CP-SAT: siguranța
  înaintea distanței). `budget.distance_m` = unități / 1000 × cell_size_m. Cu 0-1 opriri, fără matrice
  (o căutare directă, calea în cache). Accesibilitatea se verifică tot din `home_tree` (aceeași mulțime de
  celule accesibile; testul din `tests/api` cere asta);
- `route_metric="cost"`: codul vechi neschimbat (doar mutat în `_assemble_by_cost`);
- live (`replanner._replan_stops`): un singur `distance_field` din poziție pe C_temp cu nucleele interzise
  (cost temporar ≥ M_CORE; dacă o oprire devine inaccesibilă, C_temp ca atare), distanțele dintre opriri din
  matricea statică, Held-Karp pe opririle rămase; segmentele trec apoi prin A* pe C_temp, candidați și
  validator. Doar în OUTBOUND.

**Abateri:** opririle scoase de CP-SAT nu apar în răspuns ca `science_lost` (contractul
`route_response.json` nu are câmpul; vezi „Cereri”). Ordinea Held-Karp folosește doar distanța (presetul
departajează segmentele, nu ordinea).

**Situl sintetic, habitat + cele 3 ținte (cererea în ordinea clay, carbonate, olivine):**

| Preset | Durată max. | Înainte: ordine, distanță | Acum: ordine, distanță |
|---|---|---|---|
| safe | 480 | olivine → carbonate → clay, 13 705 m, 338 min | clay → carbonate → olivine, 13 704 m, 338 min |
| fast | 480 | olivine → carbonate → clay, 13 705 m | clay → carbonate → olivine, 13 704 m |
| science | 480 | olivine → carbonate → clay, 13 705 m | clay → carbonate → olivine, 13 704 m |
| safe | 300 | carbonate → clay, 10 215 m, 253 min, O₂ 53,5 % | carbonate → clay, 9 890 m, 258 min, O₂ 50,3 % |
| fast | 300 | carbonate → clay, 9 891 m | carbonate → clay, 9 890 m |
| science | 300 | carbonate → clay, 10 203 m | carbonate → clay, 9 890 m |

La 480 min turul vechi avea deja lungimea minimă (terenul sintetic e deschis între ținte): același tur,
parcurs invers; la egalitate câștigă ordinea lexicografică. Diferența de 1 m vine din 1,414 față de √2.
La 300 min (olivine nu încape, CP-SAT o scoate), drumul cel mai scurt e cu 3,2 % mai scurt la `safe`, dar
urcă mai mult: +5 min și −3 puncte de O₂. Distanța e acum aceeași la toate presetele.

**Timpi (500 × 500, mediana din 3 rulări; primul apel în procese noi):**

| Măsurătoare | Țintă | Măsurat |
|---|---|---|
| `distance_field`, oprire timpurie (habitat → 3 ținte / cel mai rău din matrice) | < 0,5 s | 130 / 114 ms |
| `distance_field` pe harta întreagă (fără ținte, informativ) | — | 528 ms |
| `tour_matrix` rece (4 noduri) / din cache | < 2 s / < 1 ms | 456 ms / < 0,01 ms |
| `shortest_tour` 3 / 8 / 12 opriri | < 1 / 20 / 300 ms | 0,22 / 1,5 / 6,1 ms |
| `plan_route` primul apel (3 ținte / 1 țintă) | < 3 s | 1,56 / 1,30 s |
| `plan_route` cu cache (3 ținte, 480 min / 300 min cu CP-SAT / 1 țintă) | < 50 ms | 3,3 / 25 / 1,4 ms |
| `replan_stops` în live (o oprire blocată; din care ordinea) | < 0,6 s | 374 ms (145 ms) |

Primul apel: 1,3 s din 1,56 s sunt cele două `reverse_dijkstra` care existau și înainte (`home_tree` pentru
accesibilitate, `_o2_to_home` pentru punctul de neîntoarcere); matricea adaugă ~0,4 s. Într-un proces cu
mai multe situri 500 × 500 încărcate, primul apel urcă spre 3 s (presiune pe colectorul de gunoi), de aceea
încălzirea la pornire contează (vezi „Cereri”, rolul 3).

**Teste:** `tests/core/test_tour.py` (23): permutările cererii (SC-23, pe un sit mic și pe cel sintetic),
Held-Karp = forță brută pe 120 de cazuri (3-7 opriri, tur închis și deschis, start oarecare), segment =
Dijkstra independent cu cheie tuplu (distanța și presetul), octila exactă pe grilă liberă, presetul doar
între drumuri la fel de lungi, simetrie + inegalitatea triunghiului + cache, tur închis / deschis,
`UNREACHABLE`, 20 de rulări identice, `route_metric="cost"` = drumul vechi, CP-SAT doar când turul nu
încape, start în afara habitatului, ordinea live din poziție (cu și fără nucleu de pericol), arborele canonic.
Modificat: `test_planner.py::test_synthetic_three_targets_follow_plan_stops_order` cere acum
`route_metric="cost"`, pentru că verifică exact ordinea din `plan_stops`; cu metrica implicită, `plan_stops`
se cheamă doar când turul complet nu trece validatorul.

### Sesiunea din 14.11: cererile deschise, rezolvate (T1-T9, cu acordul utilizatorului)

Toate intrările de mai jos erau la „Cereri”; sunt **rezolvate în această sesiune**.

- **T1, panta maximă 20° (D1).** `types.Limits.max_slope_deg` = 20,0 (excepție aprobată pentru
  `types.py`); `shared/contracts/meta.json` și `site.json` → 20; `make_synthetic_site.MAX_SLOPE_DEG`
  era deja 20 (rolul 1, v8). `planner.PLANNER_LIMITS` = `Limits()`, deci harta de cost
  (`meta.max_slope_deg`), validatorul din planner și cel din motorul live folosesc aceeași limită.
  Testele din `test_costmap.py` care foloseau 25° trec acum pe 20°.
- **T2, doza (D4).** Era deja corectată la sursă de rolul 1: situl sintetic v7 are fondul de 28 µSv/h
  (doză echivalentă, RAD 0,67 mSv/zi), iar `scenario.DOSE_RATE_USV_H` = 28. Core-ul nu are factor.
  Teste existente: `pipeline/tests/test_synthetic.py::test_radiation_is_rad_dose_equivalent`,
  `tests/scenario/test_scenario.py` (28,0).
- **T3, relief în situl sintetic (v9).** `pipeline/make_synthetic_site.py`: o creastă cu șa între
  habitat și `carbonate_rim` (profil gaussian, flancuri ≈ 17°) și un front de deltă mai abrupt
  (lățimea 12-102 m în loc de 12-172 m). Fără numere aleatoare noi, deci restul sitului e identic.
  Rezultat: 1,26 % din celule au 12-18° (înainte 0,41 %); spre `carbonate_rim`, `fast` urcă direct
  peste flancul de 17° (181 de celule), `safe` și `science` ocolesc (186 / 185 de celule; 3 % celule
  comune cu `fast`); spre `olivine_floor` diferă și ele (60 % comune). Nicio celulă peste 20° pe
  trasee. Teste: `test_relief_ridge_and_delta_front_have_12_to_18_degree_zones` (pipeline),
  `test_synthetic_presets_give_different_routes_for_at_least_two_targets` (core).
- **T4, start în interiorul unui pericol (D2).** `alternatives.generate`: un pericol care acoperă
  deja celula de start (intensitate ≥ `BLOCK_THRESHOLD`) intră în căutări ca termen finit
  (`costmap.hazard_cost`), nu ca zonă blocată; celelalte rămân blocate. Variantă nouă
  **`exit_zone`** (kind `RETURN`): cea mai ieftină ieșire din pericol (`routing.nearest_exit`, nou:
  Dijkstra cu oprire la prima celulă exterioară) + drumul spre casă care nu reintră în pericol.
  Expunerea pe porțiunea de ieșire nu se numără la risc (e inevitabilă); cea de după, da. Furtuna
  regională nu intră aici (nu are „ieșire”). Teste: `test_start_inside_hazard_gives_valid_exit_zone`,
  `test_start_inside_hazard_is_deterministic`, `test_outside_hazard_stays_blocked_and_has_no_exit_zone`,
  `test_nearest_exit_*` (2). În scena demo, la minutul 90 frontul a ajuns peste astronaut, iar regula
  alege acum `exit_zone` (RETURN) după EMERGENCY-ul de la 80: testul Jezero are o decizie în plus,
  iar testul nou `test_demo_scene_decisions_on_synthetic` reproduce scena cap-coadă pe situl sintetic.
- **T5, ocoliri distincte (D3).** Generatorul nu le făcea așa: pe teren plat, cele 3 preset-uri dădeau
  același traseu, deci o singură ocolire. Acum: câte un waypoint pe fiecare latură a pericolului care
  atinge primul traseul (perpendicular pe poziție → țintă, prin centrul prezis la minutul contactului,
  la semiaxa mare + 100 m), `astar` poziție → waypoint → țintă pe costul cu pericolul ca termen finit,
  plus vechile ocoliri A* spațiu-timp. Se păstrează doar candidații cu < 50 % celule comune (până la
  țintă), în ordinea riscului; eticheta vine din semnul produsului vectorial. Teste:
  `test_two_detours_on_opposite_sides_are_distinct_and_stable` (grilă 30 × 30), `_side`, `_overlap`.
- **T6, backend.** (a) `POST /api/route` folosea deja `plan_route`; `route_id` din stoc, PNR null
  rămâne null (test nou). (b) `static_cost` read-only: niciun apelant din `api/`, `live/`, `llm/` nu
  modifică tabloul; test. (c) `plan_route` verifică accesibilitatea din `cost_to_home` (startul și
  fiecare țintă) înainte de orice `astar` și aruncă `ValueError` cu mesaj **în engleză** (ajunge în
  `detail` la 422); startul în afara grilei e tot `ValueError`. Am reparat și codificarea lui
  `planner.py` (era dublu codificat, mojibake în comentarii și în mesaje). (d) Motorul cheamă
  `generate` doar pentru un contact în ≤ `REACT_WINDOW_MIN` = 30 min; după o decizie **RETURN** nu mai
  replanifică (`committed_return`); o furtună „doar RETURN” apărută după aceea primește doar o
  confirmare RETURN pe același drum, fără `generate`. EMERGENCY nu e RETURN: motorul continuă să caute
  o variantă validă. (e) Lifespan: thread de încălzire (import OR-Tools, un `plan_route`, un `generate`).
  (f) `GET /api/benchmark`: `run_benchmark(100, 42)` pornit o dată la startup (`api/bench_cache.py`),
  503 + `Retry-After: 30` până e gata, apoi din cache; 500 dacă a eșuat. Calculul rulează într-un
  proces separat, pornit dintr-un thread: un minut de Python pe un thread din server ar ține GIL-ul și
  ar încetini bucla live. Variabile: `MARSWALK_WARMUP=0`, `MARSWALK_BENCHMARK_AT_STARTUP=0`.
  `run_benchmark` întoarce acum și **`headline`** = `{copilot_safe_pct, plan_safe_pct, n_scenarios}`.
  Definiția „acasă în siguranță”: ajuns în habitat, O₂ ≥ rezerva, doza ≤ limita, înainte de apus minus
  marjă, fără expunere ≥ 0,3 pe mișcarea reală a furtunii.
- **Performanța la furtuna regională** (cererea rolului 1, ~1,2 s): când toate pericolele sunt
  „doar RETURN”, `generate` nu mai calculează ocoliri (nu sunt un răspuns permis). Test: < 0,5 s.
- **T7, frontend.** `utils.js`: `hasSafeReturn`, `effectiveVerdict`, `pointOfNoReturnLabel`,
  `pointOfNoReturnCell`, `splitAtLastStop`; `BudgetPanel` arată „Punct de neîntoarcere” (sau „fără
  întoarcere sigură” și NO-GO, cu avertisment), `App` blochează pornirea pe verdictul efectiv,
  `TerrainView` pune un inel la PNR (doar dacă există) și desenează fiecare alternativă complet, cu
  întoarcerea de după ultima oprire mai estompată. Etichete noi: `exit_zone`, `detour_east/west`.
  Verificat cu mock-urile din contracte (ambele cazuri, `node --test`, script în afara repo-ului:
  `frontend/tests/` nu era în lista de fișiere permise). `npm run build` trece.
- **T8.** `shared/contracts/README.md`: „Alternative.path = traseul rămas complet, de la poziția
  curentă până la habitat; la wait, doar [position].”

**Benchmark (situl v9, seed 42, 100 de scenarii, 65 s):** acasă în siguranță: copilot **82 %**, doar
planul **51 %** (`headline`). Pe tipuri (plan → copilot): vârtejuri 51 → 62 din 67, fronturi 0 → 17 din
27, regionale 0 → 3 din 6. O₂ la sosire min/mediu: plan 72,0/72,0 %, copilot 43,2/77,7 %; știință
colectată 100 % / 53 %. Decizii: 41 CONTINUE, 18 REROUTE, 29 WAIT, 43 RETURN, 10 EMERGENCY.
**Un scenariu e mai puțin sigur cu copilotul** (`storm_77`, vârtej): copilotul alege WAIT, iar
mișcarea reală (cu zgomot) aduce vârtejul peste astronautul care așteaptă (expunere 0,87, față de 0,22
pe plan). Nu vine din T5 (fără ocolirile prin waypoint rezultatul e identic); e efectul sitului v9 asupra
furtunilor generate. Tabelul R2-11 de mai jos e pe situl vechi.

**Timpi (situl v9, Python 3.14, mediana):**

| Funcție | Măsurat | Țintă |
|---|---|---|
| `static_cost`, fără cache | 7,2 ms | < 0,2 s |
| `astar` habitat → ținte | 35-58 ms | < 1 s |
| `astar` colț la colț | 0,59 s | < 1 s (înainte depășit: 1,14 s) |
| `reverse_dijkstra` safe / fast / science | 0,70 / 0,72 / 0,70 s | < 2 s |
| `alternatives.generate`, furtună pe traseu, cache cald | 0,20 s | < 2 s |
| `alternatives.generate`, start în pericol | 0,12 s | < 2 s |
| `plan_route` 1 țintă, primul apel (fără importul OR-Tools) | 1,63 s | < 3 s |
| `plan_route` 1 țintă, cache cald | 0,002 s | < 3 s |
| `plan_route` 3 ținte, după cel de 1 țintă / cald | 0,33 / 0,28 s | < 3 s |
| `run_benchmark(100, 42)` | 65 s | < 2 min |
| importul OR-Tools | 0,87 s | mutat în încălzirea de la pornire |

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

### Cereri vechi, mutate aici: rezolvate în această sesiune

Textul lor complet e în istoricul git al acestui fișier; aici, doar rezolvarea.

- Rolul 3, `static_cost` doar pentru citire: **rezolvat în această sesiune** (T6b; niciun apelant nu
  modifică tabloul, test în `tests/api/test_core_integration.py`).
- Rolul 3, `astar` întoarce None / aruncă ValueError; verificarea ieftină prin `cost_to_home`:
  **rezolvat în această sesiune** (T6c, în `plan_route`).
- Rolul 3, conul relativ și fereastra de 30 min; fără replanificare după RETURN: **rezolvat în această
  sesiune** (T6d, în motor).
- Rolul 3, `GET /api/benchmark` calculat o dată, în cache: **rezolvat în această sesiune** (T6f).
- Rolul 3, `alternatives.generate` e gata, semantica lui `path`: **rezolvat în această sesiune**
  (T6d, T7, T8: scrisă și în `shared/contracts/README.md`).
- Rolul 3, planner-ul e gata pentru `POST /api/route`: **rezolvat în această sesiune** (T6a).
- Oameni, panta maximă (20° în planner, 25° în `Limits` și `meta.json`): **rezolvat în această
  sesiune** (T1, 20° peste tot).
- Rolul 3, importul OR-Tools la primul `POST /api/route`: **rezolvat în această sesiune** (T6e,
  încălzirea din lifespan).
- Rolul 1, doza ≈ 2,8× prea mică în stratul `radiation`: **rezolvat** (la sursă de rolul 1, situl v7
  și `scenario` la 28 µSv/h; verificat în această sesiune, T2).
- Oameni, start pe celulă interzisă în live: **rezolvat în această sesiune** (T4, pericolul care
  conține startul devine cost finit, varianta `exit_zone`).
- Oameni, preset-urile dau aproape același traseu; ocolirile nu pot veni doar din preset-uri:
  **rezolvat în această sesiune** (T3 relieful v9, T5 ocolirile prin waypoint).
- De știut, închise (informative, nu cereau nimic): `M_TOTAL` 196 kg și constantele de O₂ din
  registru; `PARAMETRI_REFERINTA.md` e în `docs/roles/`; convenția costului unei mutări (media celor
  două celule) rămâne cea aleasă; `.venv` creat local din `requirements.txt`.

## În lucru

### Arhitectura de rutare V2 (`docs/roles/ARHITECTURA_RUTARE_V2.md`, inclusiv §6.1 dus-întors)

Decizie (utilizatorul): pipeline-ul V2 stă în `backend/app/core`; `live/engine.py` îl cheamă în locul
lui `live/replan.py` (fișierul rolului 3 rămâne neatins). Constantele noi stau în module noi din `core`
(`pipeline/tests/test_how_we_calculate.py` cere ca orice constantă din `budget`, `costmap`, `decision`,
`hazards`, `daylight`, `planner`, `validator`, `live/engine.py` să fie în `docs/how-we-calculate.md`,
pe care nu îl pot modifica).

**Linia de bază (înainte de V2):** backend 433 trecute, 14 picate, 15 xfail, 37 deselectate. Dintre
cele 14: 8 XPASS(strict) (buguri reparate înainte: AUDIT-004 notificarea la eroare, 008, 009, 010
`run_benchmark`, 011, 015, 016, 017), `route_version` lipsă din `live_messages.json` (3 teste), panta
25° într-un test de chat, scena demo (WAIT la min 80 cu `replan.py`, 2 teste). `-m slow`: 14 trecute,
1 picat (`test_e2e_server`, uvicorn pe 8002), 1 xfail. Pipeline: 92 trecute, 1 picat
(`REPLAN_EVERY_MIN`, `PROXIMITY_M` din motor nedocumentate), 5 sărite.

**Harta specificație → cod (înainte de V2):**

| § | Exista | Parțial | Lipsea |
|---|---|---|---|
| 2 HazardSpec | `hazards.Hazard`, `from/to_contract`, `HAZARD_RESPONSES`, `HAZARD_DEFAULTS` (motor) | profil parabolic de intensitate | efecte, `rev`, re-ancorare, normalizare, < 30 m ignorat, > 60 % global |
| 3 Moduri | watchdog pe tick, REEVAL 5 min, periodic 5 min, proximitate 450 m | declanșatoare nivel 3 | NOMINAL/MONITOR/REACT/EMERGENCY, K adaptiv, `(t, seq)`, hash stare |
| 4 Conflict | `route_hit`/`route_risk` pe puncte, con aditiv `SIGMA_REL` | — | test pătratic pe felii, plafon H_CONE, δ⊥, expunere, `can_sidestep` |
| 5 Cost | `static_cost`, `hazard_cost`, `minutes_grid`, `reverse_dijkstra` (simetric) | start în pericol finit (T4) | `t_est`, Φ nucleu/halou/plafon, multi-sursă, N_MAX |
| 6 Candidați | `current`, waypoint pe laturi (o iterație), `wait`, `exit_zone`, `return`, `nearest_exit`, deduplicare 50 % | etichete după produsul vectorial, wait până la 90 | iterare ×3, inele, `WAYPOINT_OFF_MAP`, `detour_free`, `replan_stops`, `shelter`, `merged_with`, coduri de omitere |
| 6.1 Dus-întors | `generate` cu opriri goale | — | eliminarea regulii RETURN (`committed_return`, `_confirm_return`, benchmark `committed`), fază, `phase` |
| 7 Validator | V1-V4 + HAZARD binar, `decision.choose` (histerezis 20 %) | — | V5-V8, scor normalizat, δ = 0,12, DWELL_MIN |
| 8-9 Limită | `cost_to_home` înainte de A*, ValueError → 422 | — | off-map, refugii, hub_effect, NO_SHELTER, ISOLATED, UNRECOVERABLE |

**Făcut până acum:**
- Curățenie: scos `xfail` de pe cele 8 teste care treceau; `route_version` (tick, decision) și `trigger`
  adăugate în `live_messages.json`; testul de chat citește panta din meta.
- **F0** `core/hazard_spec.py`: `HazardSpec`, `Effects`, `CLASS_DEFAULTS`, `normalize` (coduri
  `NAN_VALUE`, `BAD_SHAPE`, `MISSING_CENTER`; avertismente `SPEED_CAPPED`, `SMALL_IGNORED`,
  `COVERAGE_GLOBAL`…), `HazardRegistry` (add/update/remove, `rev`, re-ancorare), conversii. 17 teste.
- **F1** `core/conflict.py`: test pătratic pe felii ≤ 1 tick, expunere, adâncime, δ⊥ plafonat,
  `can_sidestep`, `contains`; `hazards.route_hit` folosește testul continuu (semnătura neschimbată).
  9 teste (60 de cazuri față de eșantionarea la 1 s). Test modificat: `test_route_hit_on_crossing_path_
  gives_correct_minute` (contactul continuu cade la 14,28, între punctele 14 și 15; înainte, minutul 15).

- **F2** `budget.timeline` (sursa unică: `EffectWindow` cu multiplicatori de viteză / O₂ / doză, adaos
  O₂/min, apus mutat; `point_effects` pentru efectele locale; fără efecte = calculul vectorizat vechi,
  `route_budget` delegă la el), `budget.active_multipliers`, `budget.effective_sunset`;
  `costfield.t_est_grid` (Dijkstra înainte pe minute, blocuri 5 × 5). Consum pe plat = 0,194 %/min.
- **F3** `costfield.temp_cost` (nucleu M_CORE, halou M_HALO·(1 − d)², plafon M_MAX, `block = all` → +∞
  doar dacă nu conține startul, start în pericol → gradient de ieșire, zone statice blocate doar pe pante
  > 15°, evaluare la t_est); `routing.reverse_dijkstra_multi` (refugii, N_MAX), `routing.project_to_grid`.
  16 teste (F2 + F3).
- **F4** `validator`: V5 (`exposure_over_limit`), V6 `NO_RETURN_POINT` (nu pe RETURN / INBOUND),
  V7 `OFF_MAP`, V8 `NO_SHELTER`; `types.Alternative` / `Decision`: câmpuri noi la final;
  `core/selection.py`: scor §7 pe preset, ordine `(S, prioritate, id)`, histerezis δ = 0,12 +
  DWELL_MIN = 3, EMERGENCY cu relaxare V2 → V5, `UNRECOVERABLE`, RETURN → REROUTE în INBOUND.
  `decision.MIN_IMPROVEMENT` 0,2 → 0,12 (aliniat cu §7; `test_decision.py` rămâne verde). 9 teste.

- **F5** `core/replanner.py`: `ReplanState`, `watchdog` (nivel 1: contacte continue pe H_WATCH, astronaut
  în amprentă, O₂, apus, hartă, refugiu; ~3 ms), `generate_candidates` (ordine fixă: current, două ocoliri
  cu waypoint iterat ×3 + inele `(row, col)` + etichete după centrul pericolului, `detour_free`, `wait`
  ∈ {5..30} doar cu poziția în afara amprentei, `exit_zone` (REROUTE, ieșirea tolerată în V5),
  `replan_stops` (fără opririle blocate), `return` (Π_home doar fără contact, altfel A* pe C_temp),
  `shelter` (pericole globale); deduplicare cu `merged_with`; omiteri `SIDESTEP_INFEASIBLE`,
  `WAYPOINT_OFF_MAP`, `NO_PATH`, `DUPLICATE`, `STOP_BLOCKED`, `HAZARD_GLOBAL`), `plan` (selecție §9,
  steaguri `OFF_MAP`, `NO_SHELTER`, `ISOLATED`). Evaluare cap-coadă cu `timeline` + efecte locale,
  V5 cu excepțiile (ieșire, grația de refugiu HUB_GRACE_M, AIRLOCK_MIN), V6 cu efectele active.
  Pe situl sintetic: replanificare 0,12 s (cache cald), primul apel 0,75 s. 12 teste.
  - Abatere: ponderea științei din scorul §7 e aliniată cu `costmap.PRESETS[w_science]` (0,15 / 0,20 /
    0,40), restul scalate proporțional (altfel întoarcerea câștigă mereu prin O₂-ul rămas).
  - `alternatives.generate` rămâne API-ul vechi (testele lui neschimbate); motorul și benchmark-ul trec pe
    `replanner.plan`.
  - Rămas: `replan_stops` cu CP-SAT (acum doar elimină opririle blocate, păstrând ordinea).

- **F6** dus-întors: `live/engine.py` folosește `core.replanner.plan` (nu mai importă `live/replan.py`);
  `phase` OUTBOUND/INBOUND (INBOUND după RETURN/EMERGENCY/varianta RETURN sau după ultima oprire; nu se
  revine); scoase `committed_return`, `_confirm_return` și excepția din watchdog pentru pericolele
  doar-RETURN; `_specs` (pericolele motorului → HazardSpec), `_effects` (oboseală, scurgere, globale),
  `_replan_state`; `phase`, `flags`, `omitted` în mesajul `decision` (+ în `live_messages.json`);
  `step()` rulează pe un thread în `run()` cu un `RLock` (AUDIT-008 reparat de fapt: înainte testul trecea
  doar pentru că replanificarea era rapidă). `benchmark.py`: `replanner.plan`, fără `committed`, cu fază.
  Teste: SC-19, SC-20 (simetria), SC-21, SC-22, determinism în `tests/integration/test_sc_golden.py`.
  Teste modificate (comportament schimbat intenționat de §6.1): în `tests/live/test_engine.py`, falsurile
  trec de la `replan.candidates` la `core_replanner.generate_candidates`, iar
  `test_way_home_is_still_replanned_but_regional_is_confirmed` devine
  `test_way_home_is_replanned_like_the_way_out` (fără confirmare RETURN); testele demo din
  `tests/scenario` verifică acum criteriile V2 (decizie validă la min 30, faza nu revine în OUTBOUND,
  acasă cu O₂ ≥ rezervă), nu secvența fixă de la replanificatorul vechi.

- **F7** cazurile limită în `replanner`: OFF_MAP (proiecție + segment estimat în linie dreaptă, consumat
  înainte de candidați, steagul `ESTIMATED_OFF_MAP`, decizie RETURN cu motiv OFF_MAP); traseul legat cu
  A* după proiecție; ISOLATED fără A* (cost_to_home = inf pe celulă și vecini) pentru start (EMERGENCY)
  și pentru ținte (omisă cu `ISOLATED`); refugii multiple (`ReplanState.refuges`, Dijkstra multi-sursă),
  `hub_effect` none/degraded (grație 100 m + ecluză 5 min) / unusable (V8, `NO_SHELTER`, refugiu
  improvizat = cea mai apropiată celulă în afara amprentelor, EMERGENCY); furtuna regională → variantele
  care mai vizitează opriri sunt respinse (`RETURN_REQUIRED`); `effects_from_specs` (furtuna solară după
  avertizarea de 30 min, ×2,5, 48 h; regională: viteză × 0,8, apus −75 min; coechipier rănit × 0,5 / ×
  1,5; scurgere; oboseală); zona de cutremur: V5 numără doar timpul pe pantele > 15° din nucleu.
  17 teste (`tests/core/test_edge_cases.py`). Test modificat: `test_marsquake_on_route_is_avoided_end_to_end`
  (pe un sit plat zona nu blochează, conform §2.1; testul pune acum pante abrupte în zonă).

- **F8** `core/modes.py` (K pe mod 15/5/1/1, `mode_for`, `state_hash`, `PROXIMITY_M`); motorul: `mode`
  calculat la fiecare tick din contactele pe H_WATCH (MONITOR) / H_REACT, astronaut în amprentă,
  eveniment de stare, EMERGENCY (`mode` în mesajul `tick`, + în contract); nivel 2 periodic la K tick-uri
  după mod; nivel 3: pericol adăugat / actualizat / șters, eveniment de stare, intrare în amprentă;
  un singur replan pe tick; reutilizare când hash-ul stării canonice (cu `rev`) nu s-a schimbat;
  evenimente în ordinea (t, seq), cele din trecut aplicate acum cu `warning: EVENT_IN_PAST`;
  `op` add / update (re-ancorare, `rev` + 1) / remove; `crewmate_injured` (viteză × 0,5, O₂ × 1,5),
  `comm_loss`. `POST /api/live/event`: formatul vechi + HazardSpec cu `op`, validat (422 cu cod stabil);
  `live_event.json`: `_allowed_ops`, `_hazard_spec_example`, `_hazard_spec_update_example` (enumul vechi
  neschimbat, legat de `schemas.EventKind` / `scenario.ALLOWED_EVENTS` / `utils.js`). Constantele
  `REPLAN_EVERY_MIN`, `PROXIMITY_M` au plecat din motor (testul de documentare din pipeline trece).
  **AUDIT-004 reparat** (marcajul `xfail` scos). 9 teste (`tests/live/test_engine_modes.py`).

- **F9** `tests/integration/test_sc_synthetic.py`: SC-01…SC-12 și SC-14…SC-17 pe situl sintetic v9
  (traseul habitat → clay_delta → habitat), SC-13 / SC-18 în `test_replanner.py` / `test_edge_cases.py`
  (cer geometrie anume), SC-19…SC-22 în `test_sc_golden.py`; proprietățile §10 pe 50 de cazuri cu seed
  fix (`-m slow`): nicio excepție, ieșire identică la două rulări, decizia aleasă trece V1-V8 sau e
  EMERGENCY / UNRECOVERABLE, expunerea continuă ≥ cea eșantionată.
  - Teste lente modificate (comportament schimbat intenționat): `test_prop_site::test_benchmark_valid_
    alternatives_respect_limits_and_choice_is_valid` spionează acum `benchmark.replan` (benchmark-ul nu mai
    cheamă `choose`) și verifică V5 (`exposure_over_limit`) în locul lui `crosses_hazard` (ieșirea tolerată
    dintr-o zonă e validă); `test_int_planner_engine::test_engine_real_core_decides_at_each_scheduled_demo_
    minute` verifică doar pericolele programate cât rularea e activă (în V2, RETURN la min 30, acasă la 60).
  - **Teste la final:** backend 557 trecute, 14 xfail, 0 picate (571 colectate, 37 deselectate);
    `-m slow`: 16 din 17 rulate: 13 trecute (după 2 teste adaptate), 1 picat și înainte de V2 (`test_e2e_server` reconectare, cerere la rolul 3), testul de memorie pe 130 de scenarii sub `tracemalloc` oprit după ~40 min (nu a picat, e lent: vezi „Rămas”); `test_jezero_demo_return_clock…` nerulat; pipeline 93 trecute, 5 sărite.
  - **Timpi** (situl sintetic 500 × 500, 3 rulări, mediana): watchdog 3,3-6,0 ms (țintă < 50 ms);
    replanificare 0,117-0,124 s cu cache-ul sitului cald (țintă ≤ 0,5 s), primul apel ~0,75 s;
    `plan_route` primul apel într-un proces nou 1,16 s (1,15 / 1,16 / 1,22; țintă < 3 s).
  - **Benchmark** `run_benchmark(100, 42)`: copilot 85 % în siguranță (înainte 82 %), planul fix 51 %
    (neschimbat). Pe tipuri: vârtej 67/67, furtună locală 18/27, regională 0/6 (plecare prea târzie pentru
    orice răspuns). Niciun scenariu mai puțin sigur decât planul. Explicația (nedescompusă pe
    cauze): replanificarea pe întoarcere (înainte, după RETURN copilotul nu mai ocolea furtunile de pe
    drumul spre casă; acum le ocolește ca la dus) și testul continuu (vârtejurile mici nu mai trec
    printre eșantioane). Știința copilotului: 27 % (se întoarce des, iar furtunile locale lovesc traseul
    spre țintă). Durata: 91 s.

**Rămas:** ~~`replan_stops` cu CP-SAT~~ rezolvat pe 15.11 altfel: opririle rămase (fără cele blocate) se
reordonează după distanță cu Held-Karp (`tour.py`), ~0,15 s; CP-SAT nu mai e necesar aici. De urmărit: `routing.astar` (Python
pur) e ~50 % din timpul benchmark-ului (90 de apeluri × 55 ms pe 15 scenarii); sub `tracemalloc`, testul
de memorie pe 130 de scenarii devine foarte lent.

**Reparații după fluxul end-to-end pe jezero (14.11):**
- EMERGENCY care alegea `wait` (cale de o celulă) golea traseul, iar misiunea se „termina” cu
  `egress_complete` pe teren deschis; acum `wait` e aplicată ca așteptare (motor și benchmark), iar un
  traseu terminat departe de destinație pune drumul până acolo și replanifică imediat (nivel 3).
- `_emergency`: salvarea e întâi RETURN, apoi orice rută care se mișcă (pe întoarcere, traseul curent),
  abia apoi `wait`; înainte, cu O₂ sub rezervă pe drumul spre casă, astronautul aștepta pe loc până la
  epuizarea O₂-ului.
- V6 față de planul acceptat: un plan CAUTION care trece deja de punctul de neîntoarcere (estimarea O₂ până
  acasă e pesimistă: urcare pe fiecare celulă) era abandonat la minutul 1, fără pericol. Acum
  `ReplanState.pnr_floor_pct` = marja planului (`plan_pnr_margin`), pragul V6 = min(rezervă, marja − 2).
- `reason_code` la schimbare = încălcarea reală a traseului curent (ex. `NO_RETURN_POINT`, `O2_RESERVE`),
  nu mereu `HAZARD_ON_ROUTE`.
- Benchmark (100 de scenarii, seed 42): sintetic 77 % (planul 51 %), jezero 78 %. Cifra anterioară de 85 %
  era umflată de bugul cu `wait` (scenariul se oprea pe loc, fără expunere ulterioară): cu vechea regulă de
  salvare și bugul reparat ies 78 %; regula nouă costă un punct și elimină epuizarea O₂-ului.
- Rămas (de decis): motorul consumă O₂ cu `WALK_WATTS` fix (0,281 %/min), planificatorul cu `budget._walk`
  (~0,194 %/min pe plat); după ~15 min un plan cu marjă de 1 punct primește RETURN pe `O2_RESERVE`.

**Pasul următor:** niciunul pentru V2 (F0-F9 gata); cererile către rolurile 1, 3 și 4 sunt la „Cereri”.

## Cereri

- **Pentru rolul 1 (deschis, presupunere C):** zgomotul mișcării furtunilor din `storms.py` (viteză
  ±15 %, direcție 1°/min) nu e încă calibrat pe MEDA. Cifrele sunt acum în
  `data/processed/jezero/wind_stats.json` (Weibull + turbulență, [S7]); de preluat în `storms.py`,
  apoi `calibrate_sigma_v` dă un `SIGMA_REL` cu sursă. Răspuns la întrebarea rolului 1 despre mărimi:
  `storms.py` folosește deja mărimile din registru (vârtejuri 100-135 m, front 30 × 5 km la 10-20 m/s,
  regională cu rază ≈ 1000 km).
- **Pentru rolul 1 (nou, prezentare):** scena demo are acum **4 decizii**: 30 REROUTE, 80 EMERGENCY,
  **90 RETURN prin `exit_zone`** (frontul a ajuns peste astronaut; copilotul îl scoate pe drumul cel
  mai scurt din furtună), 125 RETURN (confirmare, fără replanificare). `docs/demo.md` și
  `docs/slides.md` descriu încă 3. Cifrele benchmark-ului s-au schimbat (situl v9, ocolirile noi):
  82 % copilot față de 51 % plan, 100 de scenarii; slide-urile trebuie remăsurate.
- **Pentru rolul 4 (nou):** `GET /api/benchmark` întoarce acum `headline`, dar abia după ~1 min de la
  pornire: până atunci 503 cu `Retry-After` (secunde). UI-ul încă nu afișează cifra. Eticheta pentru
  varianta nouă `exit_zone` e în `utils.js` (în română, ca restul panoului; regula echipei cere engleză).
- **Pentru cine întreține `backend/tests/regression/` (nou):** AUDIT-009, AUDIT-010 (`run_benchmark`)
  și AUDIT-011 sunt reparate; testele lor `xfail(strict=True)` trec acum și apar ca FAILED (XPASS).
  Trebuie scos marcajul de pe `test_route_error_detail_is_english_without_mojibake`,
  `test_run_benchmark_has_headline` și `test_max_slope_is_the_same_everywhere`. Testul
  `test_api_benchmark_returns_headline` cere 200 imediat; semantica cerută acum e 503 până e gata,
  apoi 200 (testul nou: `tests/api/test_core_integration.py`), deci acel test trebuie rescris.
  Fișierul nu era în lista de fișiere permise a sesiunii, deci nu l-am atins.
- **Pentru oameni (de știut):** benchmark-ul are un scenariu în care copilotul e mai puțin sigur
  decât planul (`storm_77`, WAIT sub un vârtej care deviază). Merită decis dacă WAIT trebuie să ceară
  o marjă mai mare față de vârtejuri (al căror singur răspuns permis e REROUTE).

- **Pentru rolul 1 (nou, arhitectura V2):** (a) de documentat în `docs/how-we-calculate.md` constantele noi
  (lista e la „Presupuneri”, blocul V2) și schimbarea `decision.MIN_IMPROVEMENT` 0,2 → 0,12 (documentul
  arată încă 0,2); (b) scena demo trebuie recalibrată pentru V2: vârtejul de la minutul 30 lovește traseul
  în ~4 min, deci ocolirea e infezabilă (§4) și copilotul se întoarce acasă înainte de front și de
  furtuna regională; pentru momentul „ocolire” e nevoie de un contact la ~15-20 min (ca în SC-03);
  (c) scenariile golden SC-01…SC-22 în `scenario.py` (evenimente `custom`, `crewmate_injured`,
  `comm_loss`, op `update`); (d) surse pentru parametrii C ai claselor de hazard (α 15 / 30 m/min,
  σ_rel, avertizarea de 30 min a furtunii solare, coechipier rănit × 0,5 / × 1,5).
- **Pentru rolul 3 (nou):** (a) `live/replan.py` nu mai e folosit de motor (pipeline-ul V2 e în
  `core/replanner.py`); propun retragerea lui și a `tests/live/test_replan.py`; (b) `schemas.LiveEvent`
  / `EventKind` nu cunosc `custom`, `crewmate_injured`, `comm_loss` și formatul cu `op`: deocamdată
  `POST /api/live/event` le tratează în `api/main.py` (body brut, validat prin `HazardSpec`);
  (c) `LiveEngine.step()` rulează acum pe un thread în `run()` (AUDIT-008), cu un `RLock` pe comenzi;
  (d) rezumatul pentru LLM poate folosi câmpurile noi `phase`, `flags`, `omitted`; (e) `tests/e2e/
  test_e2e_server.py::test_disconnect_does_not_affect_others_and_reconnect_gets_current_state` pică și
  înainte de V2: `subscribe()` trimite întâi un mesaj `state`, testul așteaptă `tick` (de aliniat testul
  sau `subscribe`).
- **Pentru rolul 4 (nou):** etichete noi de alternative: `detour_east`, `detour_west`, `detour_free`,
  `exit_zone` (acum REROUTE), `replan_stops`, `shelter` (id-urile `detour_*` sunt șiruri libere);
  `decision.phase` = `OUTBOUND` / `INBOUND` (pe întoarcere deciziile sunt REROUTE / WAIT, nu RETURN);
  `decision.flags`: `NO_SHELTER`, `OFF_MAP`, `UNRECOVERABLE`, `ISOLATED`; `decision.omitted`
  (`{id, reason}`: `SIDESTEP_INFEASIBLE`, `WAYPOINT_OFF_MAP`, `NO_PATH`, `DUPLICATE`, `STOP_BLOCKED`,
  `HAZARD_GLOBAL`, `ISOLATED`); coduri de încălcare noi `NO_RETURN_POINT`, `OFF_MAP`, `NO_SHELTER`;
  `tick.mode` (NOMINAL / MONITOR / REACT / EMERGENCY); formular pentru hazard personalizat
  (`live_event.json` → `_hazard_spec_example`, op add / update / remove).

- **Pentru rolul 3 (nou, 15.11, încălzire):** `tour.tour_matrix(site, preset)` pentru fiecare preset
  (`safe`, `fast`, `science`) la pornire, din `lifespan`, într-un thread (ca încălzirea existentă a lui
  `plan_route`): ~0,45 s per preset pe 500 × 500; după aceea orice plan cu mai multe opriri ia câțiva ms.
- **Pentru cine întreține `shared/contracts/` (nou, 15.11):** `route_response.json` nu are un câmp pentru
  opririle scoase din plan (nu încap în timp sau O₂). Propunere: `science_lost: [id]` opțional. Până
  atunci, planificatorul le lasă doar în afara listei `stops`, ca înainte.
- **Pentru cine întreține `backend/tests/regression/` (nou, 15.11):** AUDIT-005 e reparat de alinierea
  motorului la `core.budget._walk` (deja în HEAD, nu de schimbarea din sesiunea asta: O₂ la sosire 73,3 %
  față de 73,5 % în plan, la ambele metrici). `test_engine_o2_matches_plan_budget_without_events` apare
  ca FAILED (XPASS strict); trebuie scos marcajul `xfail`. Fișierul nu era în lista permisă.
## Presupuneri

Constante și alegeri fără sursă, pentru rolul 1 (de documentat sau de înlocuit cu valori cu sursă).

| Unde | Constantă | Valoare | Ce înseamnă |
|---|---|---|---|
| `types.Limits` | `o2_reserve_pct` | 30 % | rezerva de O₂ la sosirea în habitat |
| `types.Limits` | `sunset_margin_min` | 30 min | marja față de apusul efectiv |
| `types.Limits` | `max_slope_deg` | 20° | NU mai e presupunere: A [S26] (registrul §4.1), decizia D1; aceeași valoare în `meta.json`, `site.json` și situl sintetic |
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
| `alternatives` | `DETOUR_MARGIN_M` | 100 m | C: cât de departe de semiaxa mare a pericolului prezis se pune waypoint-ul ocolirii (5 celule de 20 m) |
| `alternatives` | `WAYPOINT_SCALES` | 1; 1,25; 1,5; 2 | C: de câte ori se îndepărtează waypoint-ul dacă celula e interzisă sau încă în pericol |
| `alternatives` | `MAX_DETOUR_OVERLAP` | 50 % | C: de la 50 % celule comune (din traseul mai scurt, până la țintă) două ocoliri sunt „aceeași variantă” |
| `alternatives` | pericol care conține startul | intensitate ≥ `BLOCK_THRESHOLD` (0,1) acum | C: același prag ca pentru blocare; un astfel de pericol devine `hazard_cost` (w_hazard × câmp), nu inf |
| `alternatives` | ieșirea din pericol (`exit_zone`) | prima celulă cu intensitate < 0,1 în câmpul de la t_min | C: câmpul e luat fix (ieșirea durează puțin față de mișcarea pericolului); expunerea până la ieșire nu se numără la risc |
| `alternatives` | pericole doar „doar RETURN” | fără ocoliri | C: REROUTE nu e un răspuns permis (HAZARD_RESPONSES), deci nu se calculează |
| `benchmark` | „acasă în siguranță” (`headline`) | în habitat, O₂ ≥ 30 %, doză ≤ 1 mSv, sosire ≤ apus − 30 min, expunere reală < 0,3 | definiția cerută de ROL2 (sarcina 11); pragurile sunt cele din `Limits` |
| motor (`live/engine.py`) | după RETURN | fără replanificare; furtuna „doar RETURN” primește doar confirmare | C: ca în benchmark (RETURN definitiv); EMERGENCY nu blochează replanificarea |
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

**Arhitectura V2 (ARHITECTURA_RUTARE_V2), constante noi; nivel C dacă nu e altfel spus:**

| Unde | Constantă | Valoare | Nivel / ce înseamnă |
|---|---|---|---|
| `hazard_spec` | `V_HAZARD_MAX_MS` | 40 m/s | B (registrul §3, vânt în celule 20-45 m/s): viteza maximă a unui pericol, peste e plafonată |
| `hazard_spec` | `IGNORE_RADIUS_M` | 30 m | C: pericol mai mic e ignorat (nu replanifică) |
| `hazard_spec` | `GLOBAL_COVERAGE` | 60 % | C: peste atât din hartă, pericolul e global (doar multiplicatori) |
| `hazard_spec` | `H_WATCH_MIN` / `H_REACT_MIN` / `H_CONE_MIN` | 90 / 30 / 15 min | C: avertizare / declanșare / plafonul conului |
| `hazard_spec` | `COVERAGE_STEP_MIN`, `COVERAGE_SAMPLES` | 15 min, 40 × 40 | tehnic: aproximarea acoperirii |
| `hazard_spec.CLASS_DEFAULTS` | α vârtej / front / custom | 15 / 30 / 15 m/min | C (§11, de calibrat pe MEDA) |
| `hazard_spec.CLASS_DEFAULTS` | interior vârtej și front | viteză × 0,5 | C (§2.1) |
| `hazard_spec.CLASS_DEFAULTS` | custom | σ_rel 0,2, viteză × 0,6 | C (exemplul §2.3) |
| `hazard_spec.CLASS_DEFAULTS` | cutremur | 300 m, 60 min, blocate pantele > 15° | C (~300 m din cercetare, presupunere) |
| `hazard_spec.CLASS_DEFAULTS` | resturi de aterizare | 150 m, block all | B (registru, ±150 m) |
| `hazard_spec.CLASS_DEFAULTS` | regională | viteză × 0,8, apus −75 min | C / derivat: `daylight.effective_sunset_min` cu tau 3 |
| `hazard_spec.CLASS_DEFAULTS` | furtună solară | doză × 2,5, avertizare 30 min, 48 h | B (registru [S14][S15]); avertizarea C |
| `hazard_spec.CLASS_DEFAULTS` | coechipier rănit | viteză × 0,5, O₂ × 1,5 | C (decizia echipei) |
| `hazard_spec.CLASS_DEFAULTS` | pierderea legăturii | durata maximă × 0,8 | C |
| `conflict` | `SIDESTEP_MARGIN_M`, `D_CLEAR_M` | 50 m, 50 m | C (§4) |
| `conflict` | `SLICE_MIN` | 1 min | §4: felii de cel mult un tick |
| `costfield` | `M_CORE`, `M_HALO`, `M_MAX` | 1000, 200, 5000 | C (§5) |
| `costfield` | `T_EST_DOWNSAMPLE` | blocuri 5 × 5 | C: aproximarea lui t_est (abatere notată) |
| `costfield` | `COST_HORIZON_MIN`, `SWEEP_STEP_MIN` | 240 min, 10 min | C / tehnic |
| `routing` | `N_MAX` | 600 000 expandări | C (§11): degradare deterministă |
| `selection` | ponderile scorului | tabelul §7, știința = `PRESETS[w_science]` | C; abatere: aliniere cu decision.py |
| `selection` | `DELTA`, `DWELL_MIN` | 0,12, 3 min | C (§7) |
| `selection` | `EXPOSURE_SCALE_MIN`, `EXTRA_TIME_SCALE_MIN`, `URGENT_CONTACT_MIN` | 10, 60, 10 min | §7 |
| `replanner` | `WAIT_STEP_MIN`, `W_MAX_MIN` | 5, 30 min | §6 |
| `replanner` | `WAYPOINT_ITERATIONS`, `R_SNAP_CELLS` | 3, 25 celule (500 m) | §6; raza C |
| `replanner` | `MAX_CANDIDATES` | 8 | §6 |
| `replanner` | `HUB_GRACE_M`, `AIRLOCK_MIN` | 100 m, 5 min | C (§8.5) |
| `replanner` | `HALO_SCALE_MIN` | 10 min | C: halou normalizat |
| `replanner` | `PNR_FLOOR_SLACK_PCT` | 2 % O₂ | C: toleranța V6 față de marja planului (deriva O₂ live vs. `timeline`) |
| `replanner` | V6: minutele până acasă | O₂ până acasă / 0,194 %/min | C: aproximare pentru adaosul de O₂ pe minut |
| `replanner` | furtuna regională | variantele care mai vizitează opriri sunt respinse | C: regula „doar RETURN” |
| `modes` | `K_BY_MODE` | 15 / 5 / 1 / 1 | C (§3) |
| `modes` | `PROXIMITY_M` | 450 m | C (rolul 3) |
| `budget.timeline` | efectele | evaluate la începutul fiecărui segment | C: eroare sub un segment (~0,4 min) |

**Traseul cel mai scurt în metri (`tour.py`, 15.11):**

| Unde | Constantă | Valoare | Nivel / ce înseamnă |
|---|---|---|---|
| `tour` | `ORTHO` / `DIAG` | 1000 / 1414 unități | convenție (cerința sesiunii): 1000 = o celulă = `cell_size_m`; diagonala = √2 × 1000 trunchiat. Distanța raportată = unități / 1000 × cell_size_m |
| `tour` | `PRESET_RES` | 100 | C: rezoluția componentei de preset (0,01 unități de cost pe celulă); contează doar între drumuri la fel de lungi |
| `tour` | `SCALE` | (rows × cols − 1) × DIAG × 2 × h_max + 1, rotunjit la par | derivat, nu presupunere: un drum optim e simplu, deci are ≤ N − 1 pași, fiecare cu componenta de preset ≤ DIAG × 2 × h_max (h_max = round(PRESET_RES × cost_max_finit / 2)); suma pe orice drum rămâne < SCALE, deci comparația e exact (distanță, preset). Pe 500 × 500, `safe`: h_max = 902, SCALE ≈ 6,4·10¹¹ |
| `tour` | `HELD_KARP_MAX_STOPS` | 12 | C: pragul ordinii exacte (memorie 2¹² × 12 stări, ~6 ms); peste el, euristică marcată `approx` |

