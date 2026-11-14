# Marswalk Copilot: arhitectura deterministă de rutare, versiunea 2

Înlocuiește documentul „Arhitectura Deterministă de Rutare și Replanificare Dinamică”. Include corecturile din `ANALIZA_ARHITECTURA_RUTARE.md` (S1-S15), toate hazardurile din `hazards-research.md`, calamități personalizabile, cazurile limită (ieșirea de pe hartă, pericol direct pe habitat) și mecanismul de eșantionare multi-rată cu schimbarea dinamică a parametrilor.

**Convenții păstrate din proiect:** celule `(row, col)`, `row` crește spre sud; 20 m/celulă; pantă maximă 20°; costul unei mutări = pas × media costurilor celor două celule (D2); radiația în cost e **relativă** (exces față de minim); un singur model de timp, `budget` (viteza Tobler × `SUIT_FACTOR`); presetări `safe | fast | science`; decizii `CONTINUE | REROUTE | WAIT | RETURN | EMERGENCY`; LLM-ul doar explică. Valorile fără sursă sunt nivel C (presupuneri) și se declară în „Presupuneri”.

**Ce e deja în cod și ce e nou:** `alternatives.generate`, `routing.nearest_exit` (ieșire din pericol), `hazards.*`, `decision.choose` și validatorul există. Partea nouă: modelul unificat de hazard cu efecte, testul de conflict continuu, grila de timp estimat, deduplicarea, setul de refugii, politica „off-map”, efecte globale și evenimente de stare. Ce din ele există deja pe ramura ta se verifică în cod înainte de implementare.

---

## 1. Invarianți

1. **Timp logic discret:** un tick = 1 minut simulat. Ceasul real nu intră în nicio decizie. Timpul de sosire în celule e fracționar (minute), dar toate evenimentele sunt aplicate la limita unui tick.
2. **Fără RNG în runtime.** RNG cu seed fix doar la generarea offline a scenariilor și a benchmarkului. Calamitățile din timpul rulării sunt funcții analitice ale parametrilor.
3. **Ordine totală:** orice sortare sau coadă folosește chei compuse până la un identificator unic (`(f, g, row, col)` la A*; `(S, prioritate, id)` la selecție; `(t, seq)` la evenimente).
4. **Aritmetică:** calcule în float64; comparații cu toleranță `EPS = 1e-9`; rotunjirea la 6 zecimale se aplică **doar** ieșirilor și cheii de hash, nu comparațiilor interne.
5. **Cod decide, LLM explică.**
6. **Fără „nicio decizie”:** pentru orice stare există o acțiune întoarsă. În cel mai rău caz `EMERGENCY` (secțiunea 9).
7. **Degradare deterministă:** când un calcul e prea scump, se oprește după un **număr de expandări** (`N_MAX`), nu după timp real. Același input dă același rezultat pe orice mașină.
8. **Sursă unică de timp și resurse:** `budget.timeline(...)` dă `eta_min`, `o2_pct`, `dose_msv_cum` pe fiecare punct, cu efectele active aplicate. Watchdog-ul, validatorul și punctul de neîntoarcere citesc din ea.

---

## 2. Modelul unificat de hazard (calamități personalizabile)

Orice calamitate, a sistemului sau injectată de utilizator, e o specificație `HazardSpec`. Tipurile din cercetare sunt doar seturi implicite de parametri; un tip `custom` poate combina orice.

```
HazardSpec
  id, rev (revizie, crește la fiecare modificare), kind, scope: local | global | point
  shape:    elipsă (centru, semiaxe a,b în m, orientare θ)       # local
  motion:   segmente [(de_la_min, viteză [vy, vx] m/s)]           # poziția: P0 + v·(t - t0), pe segmente
  growth:   alpha (m/min pe semiaxă), cap (semiaxe maxime, m)     # R(t) = min(R0 + alpha·Δt, cap)
  lifetime: start_min, durată_min | end_min
  effects:  block: none | core | all        core_fraction (0-1)
            soft_halo: bool                  # penalizare gradată în jurul nucleului
            speed_mult, o2_mult, o2_add_pct_min, dose_mult, daylight_shift_min
            exposure_limit_min               # cât timp în interior e tolerat (0 = deloc)
            hub_effect: none | degraded | unusable
  uncertainty: sigma_rel, horizon_cap_min                         # conul de predicție
  source: scenariu | utilizator | prognoză
```

Poziția, viteza și semiaxele folosesc convențiile din `types.Hazard` (metri de la colțul NV).

### 2.1 Clase și valorile lor implicite (nivel C dacă nu au sursă)

| Clasă | Hazarduri din cercetare | Scop | Efect principal | Decizie tipică |
|---|---|---|---|---|
| **Mobil local** | vârtej de praf mare, front de furtună locală | local | `block: core` + `soft_halo`; interior: `speed_mult` 0,5 | ocolire / așteptare / întoarcere |
| **Global** | furtună regională, furtună solară | global | `dose_mult`, `daylight_shift_min` (tau), `speed_mult` | refugiu / întoarcere |
| **Zonă statică** | zonă de cutremur (~300 m, presupunere), resturi de aterizare (±150 m), pante | local, viteză 0 | `block` pe celulele cu pantă > 15° din zonă, restul `soft_halo` | evitat în planificare |
| **Eveniment de stare** | scurgere în costum, oboseală, coechipier rănit | point | modifică astronautul: `o2_add_pct_min` 0,15, sau viteză × 0,8 și O₂ × 1,15, sau viteză × 0,5 și O₂ × 1,5 | întoarcere imediată sau renunțare la opriri |
| **Informativ** | pierderea legăturii | global | doar semnal: fără opriri noi, durata maximă redusă | niciuna din rutare |

**Reguli de normalizare (aplicate la fiecare `add` sau `update`, deterministe):**
- semiaxe: `max(valoare, cell_size_m)`; viteze: plafonate la `V_HAZARD_MAX = 40 m/s`; la depășire se plafonează și se emite avertisment, nu eroare;
- `sigma_rel` în [0, 1]; `alpha` ≥ 0; durata > 0; câmpuri lipsă → valorile implicite ale clasei;
- **pericol mic ignorat:** dacă `max(a, b) < IGNORE_RADIUS_M` (30 m), pericolul rămâne în listă, dar nu generează nicio replanificare (vârtejurile mici „nu contează”);
- **acoperire globală:** dacă amprenta la orice moment din orizont acoperă mai mult de `GLOBAL_COVERAGE = 60 %` din celule, pericolul e tratat ca **global** (doar multiplicatori), nu ca blocare geometrică (nu există ieșire de calculat);
- specificație invalidă (NaN, forme nevalide) → respinsă cu cod de eroare, fără excepție netratată.

### 2.2 Schimbarea dinamică a parametrilor (`update`)

Orice câmp se poate schimba în timpul rulării (viteză, creștere, plafon, `sigma_rel`, efecte, durată).
- Se crește `rev`. Poziția curentă prezisă devine **noua origine** (`P0 ← P(t_now)`, `t0 ← t_now`), ca să nu apară salturi.
- Se recalculează previziunile din starea curentă. Dacă setul de contacte prezise se schimbă, se declanșează **replanificare imediată** (nivel 3).
- `rev` intră în hash-ul stării, deci cache-ul explicațiilor nu servește un text pentru parametri vechi.
- Un `update` pe un `id` inexistent se tratează ca `add` (cu avertisment); un `add` pe `id` existent se tratează ca `update`.

### 2.3 Exemplu: furtuna personalizată din demo

```json
{ "op": "add", "id": "user_storm_1", "kind": "custom", "scope": "local",
  "shape": { "center": "…ca în types.Hazard…", "axes_m": [1800, 1100], "theta_deg": 90 },
  "motion": [{ "from_min": 72, "velocity_ms": [0, 2.5] }],
  "growth": { "alpha_m_per_min": 15, "cap_axes_m": [2400, 1600] },
  "lifetime": { "start_min": 72, "duration_min": 120 },
  "effects": { "block": "core", "core_fraction": 0.5, "soft_halo": true,
               "speed_mult": 0.6, "o2_mult": 1.1, "exposure_limit_min": 0 },
  "uncertainty": { "sigma_rel": 0.2, "horizon_cap_min": 15 }, "hub_effect": "none" }
```

---

## 3. Starea, modurile și bucla multi-rată

Stare: `S_t = (t, poziție, O₂, doză, traseu rămas, opriri rămase, hazarduri active cu rev, refugii, mod)`.

**Moduri (mașină de stări deterministă):**

| Mod | Condiție de intrare | Eșantionare K |
|---|---|---|
| `NOMINAL` | niciun hazard activ care atinge traseul în `H_WATCH` | doar watchdog (K = 15) |
| `MONITOR` | contact prezis în `H_WATCH` (90 min), dar peste `H_REACT` | K = 5 |
| `REACT` | contact ≤ `H_REACT` (30 min), astronaut în pericol, sau eveniment de stare | K = 1 |
| `SHELTERED` | astronaut în refugiu (habitat) | oprit; reintrare doar la comandă |
| `EMERGENCY` | niciun candidat valid | K = 1 |

**Faza drumului e separată de modul de alertă.** Faza `OUTBOUND` (mai sunt opriri) sau `INBOUND` (spre refugiu: s-a ales `RETURN`, `shelter` sau s-au terminat opririle) nu schimbă eșantionarea: `NOMINAL / MONITOR / REACT / EMERGENCY` și `K` adaptiv se aplică identic în ambele faze. Detaliile la secțiunea 6.1.

**Ordinea într-un tick (fixă):**
1. aplică evenimentele programate, sortate după `(t, seq)`; un eveniment din trecut se aplică acum, cu avertisment;
2. avansează astronautul pe traseu pe baza `eta_min` (sursa unică de timp);
3. avansează hazardurile (cinematică, creștere, expirări);
4. **nivel 1:** watchdog (mai jos);
5. decide dacă declanșezi replanificare (nivel 2 sau 3);
6. generează candidați → validează → scorează → alege cu histerezis;
7. emite mesajele; trimite starea canonică la LLM, asincron.

**Nivel 1, watchdog (fiecare tick, ținta < 50 ms):**
- testul de conflict continuu (secțiunea 4) pe traseul rămas, pe orizontul `H_WATCH`;
- astronautul e în interiorul unei amprente acum?
- marja de O₂ față de punctul de neîntoarcere; ora față de apus; limitele hărții; starea refugiului.
Rezultat: lista de contacte (`t_in`, `t_out`, expunere), nu doar un boolean.

**Nivel 2, periodic (la fiecare `K` ticks, dacă există hazarduri active):** re-evaluează candidații pe orizontul rămas (receding horizon), actualizează punctul de neîntoarcere. `K` se adaptează la mod (tabelul de mai sus), deci rata de eșantionare **se schimbă dinamic** odată cu situația.

**Nivel 3, întrerupere (replanificare imediată în tick-ul curent), la oricare:**
- hazard adăugat, șters sau cu `rev` schimbat, dacă setul de contacte prezise se schimbă;
- contact prezis ≤ `H_REACT` (30 min) sau noul contact intră în fereastra de reacție;
- astronautul a intrat într-o amprentă;
- eveniment de stare (scurgere, oboseală, coechipier rănit);
- refugiul afectat (secțiunea 8.5);
- încălcare detectată (O₂ sub rezerva proiectată, trecere de apusul efectiv);
- ieșire sau intrare de pe hartă.
Cel mult **o replanificare pe tick**; dacă hash-ul stării canonice e identic cu cel din tick-ul anterior, se refolosește rezultatul (fără recalcul).

**Orizonturi (nu se amestecă):** `H_WATCH = 90 min` doar avertizare (informativ, nu schimbă traseul); `H_REACT = 30 min` declanșează replanificarea; `H_CONE = 15 min` plafonează creșterea conului de incertitudine.

---

## 4. Predicția și testul de conflict continuu

**Poziția și semiaxele:** `P(t) = P0 + v·(t − t0)` pe segmente de mișcare; `a(t) = min(a0 + α·(t−t0), a_cap)`, la fel pentru `b`. Creștere **aditivă** cu plafon. Plafonul implicit e `a0 + α·H_CONE`; plafoane explicite le dă clasa sau utilizatorul. Plafonul se justifică prin calibrare (acoperire ≥ 95 % pe variabilitatea vântului MEDA, `calibrate_sigma_v`), nu prin faptul că „face ocolirile posibile”.

**Incertitudinea de direcție și viteză:** semiaxa perpendiculară pe mișcare primește `δ⊥(Δt) = min(σ_rel · |v| · Δt, δ_cap)`, cu `δ_cap = |v| · σ_rel · H_CONE`. Deci conul crește cu viteza relativă și se oprește la orizontul de replanificare.

**Amprenta cu marjă:** elipsa cu semiaxele mărite cu `SIDESTEP_MARGIN_M = 50 m` (`d_siguranță`).

**Testul de conflict continuu (corectează S1):** pentru fiecare segment de traseu `[p_i → p_{i+1}]` străbătut în `[τ_i, τ_{i+1}]` (din `eta_min`), în **felii de cel mult 1 tick**, cu semiaxele înghețate la capătul feliei (conservator):
1. poziția relativă: `r(s) = r0 + w·s`, unde `r0 = p_i − P_k(τ_i)`, `w = u − v`, `u = (p_{i+1} − p_i)/Δτ`;
2. se aduce în sistemul elipsei: `q(s) = S·R(−θ)·r(s)`, cu `S = diag(1/a_ef, 1/b_ef)`, deci `q(s) = q0 + z·s`;
3. conflict dacă `|q|² ≤ 1`: `(z·z)s² + 2(q0·z)s + (q0·q0 − 1) ≤ 0`. Discriminantul dă intervalul `[s1, s2]`; se intersectează cu `[0, Δτ]` și cu intervalul de activitate al hazardului;
4. `expunere` = suma duratelor intervalelor; `adâncime` = minimul lui `|q|` pe traseu.
Pentru așteptare (segment cu viteză 0) se aplică același test. Nicio eșantionare pe pași de 5 min: un vârtej rapid și mic nu mai poate trece neobservat.

**Fezabilitatea ocolirii (`can_sidestep`):** înainte de a genera ocolirile, `t_contact` = timpul până la primul contact; `d_necesar` = `a_perp(t_contact) + margine + d_clear`; dacă `v_astronaut · t_contact < d_necesar` → se omit ocolirile (`SIDESTEP_INFEASIBLE`) și rămân `wait`, `return`, `exit_zone`. `v_astronaut = v_Tobler × SUIT_FACTOR` din `budget`.

---

## 5. Câmpurile de cost

**Cost static** `C_static(v) = f_pantă(θ; slope_k preset) · f_teren + w_rad · rad_rel(v)`; `+∞` dacă `θ > 20°`, masca `unsafe` sau NaN. Mutarea `u→v` costă `pas · (C(u) + C(v))/2`.

**Grila de timp estimat `t_est(v)` (corectează S3):** Dijkstra înainte, din poziția curentă, cu costul = minute (pas / viteză locală, unde viteza ține cont de efectele active: oboseală, coechipier rănit). Se calculează o dată per replanificare. Timpul real se verifică apoi în validator; `t_est` e doar aproximarea cu care se construiește penalizarea.

**Penalizarea pericolelor:** pentru fiecare hazard activ `k` și celulă `v`, se evaluează amprenta la `t_est(v)`:
- în nucleu (`block ≠ none`): `+M_CORE` (finit); în halou: `+M_HALO · (1 − d_norm)²`;
- **pericol care conține deja astronautul** (start în interior): nu se pune `+∞`; costul rămâne finit și crește spre centru, deci există gradient de ieșire. `+∞` apare doar pentru pericole care nu conțin startul;
- suma pe pericole se plafonează la `M_MAX`, ca să nu apară `inf` aritmetic.
`C_temp = C_static + Σ Φ_k`.

Valorile implicite (nivel C): `M_CORE = 1000`, `M_HALO = 200`, `M_MAX = 5000`.

---

## 6. Generarea candidaților (ordine fixă, id-uri stabile)

| # | Id | Decizie | Construcție |
|---|---|---|---|
| 1 | `current` | CONTINUE | traseul rămas, neschimbat |
| 2-3 | `detour_<etichetă>` (două) | REROUTE | un waypoint pe fiecare latură a pericolului (mai jos), `A*(poz→W) ⊕ A*(W→țintă)` pe `C_temp` |
| 4 | `detour_free` | REROUTE | `A*(poz→țintă)` pe `C_temp`, fără waypoint |
| 5 | `wait` | WAIT | așteptare minimă `W` (mai jos) |
| 6 | `exit_zone` | REROUTE | ieșire pe drumul cel mai ieftin din amprentă, apoi spre țintă sau habitat |
| 7 | `replan_stops` | REROUTE | CP-SAT pe opririle rămase, fără cele blocate sau cu `t_ETA` în amprentă |
| 8 | `return` | RETURN | `Π_home` din Dijkstra invers; dacă are contact, `A*(poz→refugiu)` pe `C_temp` |
| 9 | `shelter` | RETURN | la hazarduri globale (furtună solară): refugiul cel mai apropiat, ignoră opririle |

**Waypoint-ul de ocolire (corectează S4, S10):**
1. se determină direcția de mers la primul contact și normala `n̂`; cele două laturi sunt `s ∈ {+1, −1}`;
2. `W_s = P_k(τ_W) + s · n̂ · (a_perp(τ_W) + SIDESTEP_MARGIN_M + D_CLEAR_M)`, cu `τ_W = t_est(W)`; **iterat de 3 ori** (punct fix), pentru că pericolul se mișcă până ajungi la `W`;
3. „cel mai apropiat nod valid”: căutare pe inele crescătoare (distanță Chebyshev), în ordine lexicografică `(row, col)`; dacă iese din hartă sau nu are celulă validă pe un inel de rază `R_SNAP`, candidatul se omite cu motiv (`WAYPOINT_OFF_MAP`);
4. **etichetă** din poziția lui `W` față de centrul pericolului: dacă `|Δrow| ≥ |Δcol|` → `north`/`south`, altfel `west`/`east`. Id-urile `detour_north`/`detour_south` din contract se păstrează când axa dominantă e nord-sud; altfel apar `detour_east`/`detour_west`. Frontendul nu trebuie să presupună doar nord/sud (de verificat cu rolurile 3 și 4).

**Așteptarea (corectează S12):** se caută cel mai mic `W ∈ {5, 10, …, W_MAX=30}` minute pentru care, după așteptare, traseul rămas nu mai are contact. Valid doar dacă poziția **rămâne în afara amprentei** pe toată durata `[t, t+W]` (testul continuu cu viteză 0). Dacă poziția e pe traiectoria pericolului, `wait` e invalid și rămân `exit_zone` / ocoliri / `return`.

**Deduplicare:** hash pe tuplul de celule; la traseu identic se păstrează candidatul cu prioritatea cea mai mică și se notează `merged_with`. Cel mult 8 candidați.

**Omiteri cu motiv (stabile, în ieșire):** `SIDESTEP_INFEASIBLE`, `WAYPOINT_OFF_MAP`, `NO_PATH`, `DUPLICATE`, `STOP_BLOCKED`, `HAZARD_GLOBAL`.


### 6.1 Drumul de întoarcere: aceeași optimizare ca la dus

**Problema din demo:** după `RETURN`, motorul nu mai replanifica (regula „după RETURN nu mai replanifici”, preluată din benchmark), iar drumul de întoarcere venea din `Π_home` (Dijkstra invers pe costul **static**, fără pericole). O furtună apărută pe drumul spre casă primea doar o confirmare pe același drum. Regula aceea se elimină.

**Principiul: un singur mecanism pentru orice segment.** Traseul rămas e o succesiune de segmente `poz → oprire_1 → … → oprire_n → refugiu`. Generarea, validarea, scorul și histerezisul lucrează pe **traseul rămas complet** (semantica `path` deja stabilită: până la refugiu). În faza `INBOUND` lista de opriri e goală, deci ținta e direct refugiul. Nimic altceva nu se schimbă.

**Ce se aplică identic în `INBOUND`:**
- watchdog-ul continuu pe drumul spre refugiu, la fiecare tick; aceleași orizonturi (`H_WATCH`, `H_REACT`, `H_CONE`) și aceleași declanșatoare de nivel 3;
- costul `C_temp` cu pericolele active (nu `C_static`), `t_est` din poziția curentă;
- `can_sidestep`, ocolirile pe ambele laturi cu waypoint iterat, `detour_free`, `wait` calculat, `exit_zone`;
- validatorul V1-V5, V7, V8 și scorul cu preset-ul curent; histerezisul cu `δ` și `DWELL_MIN`.

**Ce diferă (doar atât):**
| Element | `OUTBOUND` | `INBOUND` |
|---|---|---|
| Ținta | următoarea oprire, apoi refugiul | refugiul (cel mai apropiat valid din `S`) |
| Candidatul `current` | traseul rămas | drumul spre refugiu în curs |
| Candidatul `return` | `Π_home`, sau A* pe `C_temp` dacă are contact | coincide cu `current` sau cu `detour_free` → deduplicat |
| `replan_stops` | da | nu (fără opriri) |
| `shelter` | refugiul cel mai apropiat | **alt** refugiu din `S`, dacă există |
| V6 (punct de neîntoarcere) | se aplică | nu se aplică (ești deja pe drumul spre casă) |
| Termenul „știință pierdută” | da | 0 (nu mai există opriri) |
| Tipul deciziei | `REROUTE` / `WAIT` / `RETURN` | `REROUTE` / `WAIT` cu steagul `phase = INBOUND`; nu se reintră în `OUTBOUND` |

**`Π_home` rămâne, dar doar ca prim candidat ieftin:** dacă testul continuu nu găsește contact pe `Π_home(poz)`, se folosește direct (sub 0,1 ms). Dacă găsește contact, se generează setul complet de candidați pe `C_temp`. Dijkstra invers static nu se recalculează la fiecare tick; când `hub_effect` sau setul de refugii se schimbă, se recalculează o dată (multi-sursă).

**Cazuri limită specifice întoarcerii:**
- **Pericol între astronaut și habitat, fără ocolire posibilă:** `wait` în afara amprentei dacă O₂ permite (V1 cu așteptarea inclusă); altfel `exit_zone` + cel mai puțin expus drum; altfel alt refugiu; altfel `EMERGENCY`.
- **Pericol care ajunge pe habitat înaintea astronautului:** secțiunea 8.5 (grație, `wait` până la retragere, alt refugiu, `NO_SHELTER`).
- **O₂ strâns pe întoarcere:** ocolirile se elimină singure prin V1; dacă nimic nu trece V1, `EMERGENCY` cu cel mai scurt drum (secțiunea 9, pasul 4).
- **Eveniment de stare pe întoarcere** (scurgere, coechipier rănit): `timeline` se recalculează cu noile efecte; dacă drumul curent nu mai trece V1, se caută cel mai scurt drum valid pe `C_temp`.
- **Oscilație între două drumuri spre casă:** prevenită de același histerezis și `DWELL_MIN`.

**Benchmarkul** se aliniază: după `RETURN`, scenariile continuă să replanifice drumul spre refugiu, altfel scorul copilotului nu măsoară întoarcerea.

---

## 7. Validatorul (invarianți hard) și scorul

Fiecare candidat se simulează **cap-coadă, inclusiv întoarcerea la refugiu**, cu `budget.timeline` și efectele active (multiplicatori de O₂, doză, viteză).

| Invariant | Regulă |
|---|---|
| V1 O₂ | O₂ la sosirea în refugiu ≥ rezerva (30 %) |
| V2 Apus | sosirea ≤ apusul efectiv − 30 min (tau mută apusul) |
| V3 Pantă | max pantă pe traseu ≤ 20° |
| V4 Doză | doza cumulată ≤ `D_MAX`, cu `dose_mult` global aplicat pe intervale |
| V5 Expunere | pentru fiecare hazard, expunerea ≤ `exposure_limit_min` (0 pentru nucleu letal). Excepții: timpul de ieșire dintr-o amprentă care conține startul și **grația de refugiu** (secțiunea 8.5) |
| V6 Neîntoarcere | niciun punct de pe candidat nu depășește punctul de neîntoarcere calculat cu efectele active, cu excepția candidaților de tip RETURN |
| V7 Hartă | toate celulele și waypoint-urile în grilă; traseul nu iese din date |
| V8 Refugiu | refugiul de destinație nu e `unusable` la sosire |

**Scor** `S = Σ w_p(preset) · termen_p`, fiecare termen normalizat în [0, 1] (corectează S7):
`E_risc = min(1, expunere_min/10 + 0,5·integrala_halou)`, `U_O2 = 1 − (O₂_final − rezervă)/(100 − rezervă)`, `ΔT = clip(timp_extra/60)`, `R_doză = doza/D_MAX`, `științific_pierdut = valoare_pierdută/valoare_totală`.

| Preset | risc | O₂ | timp | doză | știință |
|---|---|---|---|---|---|
| `safe` | 0,55 | 0,25 | 0,10 | 0,05 | 0,05 |
| `fast` | 0,35 | 0,20 | 0,30 | 0,05 | 0,10 |
| `science` | 0,35 | 0,20 | 0,10 | 0,05 | 0,30 |

(valori nivel C; se aliniază cu constantele din `decision.py`.) Ordinea: `(S rotunjit la 6 zecimale, prioritatea strategiei, id)`.

**Histerezis:** dacă traseul curent e încă valid și **nu** e în `REACT` cu contact < 10 min și astronautul nu e în pericol, se schimbă numai dacă `(S_curr − S_best)/max(S_curr, 1e-6) ≥ δ = 0,12` **și** au trecut cel puțin `DWELL_MIN = 3` minute de la ultima schimbare. Dacă traseul curent e invalid, se adoptă imediat cel mai bun. Angajarea în `RETURN` înseamnă **doar** că nu se mai adaugă opriri științifice; geometria drumului spre refugiu se replanifică la fel ca la dus (secțiunea 6.1).

---

## 8. Cazuri limită

### 8.1 Hazard
| Caz | Regulă |
|---|---|
| Start în interiorul pericolului | cost finit în acel pericol (secțiunea 5); `exit_zone` e primul candidat; expunerea din ieșire e tolerată până la `T_EXIT + marjă` |
| Pericol injectat chiar pe astronaut | același caz; nivel 3 imediat |
| Pericol cu centrul în afara hărții | amprenta se calculează analitic, nu pe raster; contează doar partea care intră în grilă. Dacă nu atinge grila în `H_WATCH`, rămâne în listă, fără replanificare |
| Pericol care intră pe hartă mai târziu | apare în previziuni; contactul se calculează cu testul continuu |
| Pericol care acoperă harta (> 60 %) sau global | tratat ca global: doar multiplicatori de viteză, O₂, doză, apus; nicio blocare geometrică |
| Mai multe pericole suprapuse | `Φ` se sumează cu plafon; ocolirea se definește față de pericolul cu cel mai devreme contact; restul se validează; `detour_free` e plasa de siguranță; dacă pericolele închid traseul, rămân `wait` / `return` |
| Pericol mai rapid decât astronautul, spre el | `can_sidestep` fals → fără ocoliri; `wait` dacă iese din traiectorie, altfel `return`/`exit_zone` |
| Două evenimente în același minut | ordine `(t, seq)`; același `id` = `update` |
| Parametri invalizi (NaN, viteze absurde) | normalizare sau respingere cu cod; fără excepții |
| Eveniment programat în trecut | aplicat imediat, cu avertisment |

### 8.2 Țintă, opriri și harta
- **Pericol pe țintă:** oprirea e blocată până la `t_clear` sau, dacă pericolul e persistent (regional), eliminată; `replan_stops` și `return` raportează `science_lost`.
- **Țintă izolată sau habitat izolat:** testul `cost_to_home[celulă] == inf` înainte de A*; fără A* costisitor. Dacă refugiul nu e accesibil → `EMERGENCY` cu motiv `ISOLATED`.
- **Astronaut pe celulă interzisă (pantă > 20° după snapping, etc.):** celula de start e exceptată (cost finit) ca să poată ieși.

### 8.3 Ieșirea de pe hartă (`off_map`)
Date există doar în grilă; în afara ei costurile nu sunt cunoscute.
- **Planificarea** tratează marginea ca interzisă (`+∞`); niciun candidat nu iese din grilă (V7); waypoint-urile în afara hărții sunt omise.
- **Dacă astronautul e deja în afara hărții** (poziție injectată sau deriva): se trece în modul `OFF_MAP`. Se proiectează poziția pe cea mai apropiată celulă de margine (`project_to_grid`) și se planifică de acolo. Segmentul din afara hărții se estimează în linie dreaptă cu `c_medie` global (costul mediu al sitului) și se **marchează ca estimare**. Decizia e `RETURN`, cu avertisment `OFF_MAP`.
- **Hazard care iese de pe hartă:** se păstrează cât timp are amprenta în grilă; apoi se arhivează.
- Nicio funcție nu aruncă `ValueError` către apelant: cazurile se întorc ca motiv stabil (`OUT_OF_BOUNDS`).

### 8.4 Resurse și stări
| Caz | Regulă |
|---|---|
| O₂ deja sub rezervă la start | doar `return` și `shelter` pot fi valide; restul sunt eliminate |
| Trecut de apus | doar întoarcerea |
| Scurgere în costum | `o2_add_pct_min = 0,15` din momentul evenimentului; punctul de neîntoarcere se recalculează; de obicei `RETURN` direct pe drumul cel mai scurt, fără opriri |
| Oboseală | viteză × 0,8, O₂ × 1,15 (presupuneri din cercetare); se renunță la oprirea cea mai îndepărtată (`replan_stops`) |
| Coechipier rănit | viteză × 0,5, O₂ × 1,5, panta maximă rămâne 20°, `return` direct; punctul de neîntoarcere devine „pot căra un coleg până acasă” (valori nivel C) |
| Furtună solară | `dose_mult = 2,5` din `t_event + avertizare (30-60 min)` pentru ~48 h; decizie `shelter` dacă doza proiectată depășește bugetul; avertizarea permite întoarcere înainte de creștere |
| Furtună regională | global: tau mută apusul efectiv, viteză redusă; `RETURN` |
| Pierderea legăturii | nu schimbă rutarea: copilotul e autonom; blochează opririle noi și scade durata maximă |
| Cutremur | zonă statică ~300 m, cu `block` pe celulele cu pantă > 15°, durată scurtă (replici) |

### 8.5 Pericol direct pe habitat
Habitatul e **refugiu**. Se generalizează la o mulțime de refugii `S = {habitat, …}`; Dijkstra invers devine **multi-sursă** (cost spre cel mai apropiat refugiu), iar `Π_home` indică refugiul ales.
- **`hub_effect = none` sau `degraded`** (furtună sau vârtej peste habitat): habitatul rămâne refugiu. Ultimele celule din `HUB_GRACE_M = 100 m` nu intră în expunerea V5; se adaugă `AIRLOCK_MIN = 5 min` pentru intrare.
- **Pericol letal care vine peste habitat chiar când ajungi** (`hub_effect = none`, dar nucleul mobil trece peste ruta de sosire): `return` rămâne valid cu `exit_zone`; se compară cu `wait` în afara amprentei (corespondența cu `return_blocked_until` = timpul când amprenta se retrage).
- **`hub_effect = unusable`** (habitat distrus sau inaccesibil): `return` este invalid (V8). Stare `NO_SHELTER`:
  - dacă există alt refugiu în `S`, `return` se redirecționează acolo;
  - altfel se alege un **refugiu improvizat**: celula accesibilă cu minimul `(expunere, distanță)`, în ordine lexicografică; decizia e `EMERGENCY`, cu ceasul de O₂ afișat („timp rămas”);
  - se pornește un monitor: dacă pericolul se retrage, se reia `return`.
- **Pericol aplicat pe habitat după decizia de întoarcere:** nivel 3 (refugiu afectat); angajarea în `RETURNING` se reevaluează.

---

## 9. Selecția finală și `EMERGENCY`

1. Dacă `current` e valid și riscul e sub prag, `CONTINUE` (histerezis).
2. Altfel, cel mai bun candidat valid după scor.
3. Dacă niciun candidat nu e valid: `EMERGENCY` = `return`/`shelter` cu constrângerile relaxate (V2, V5 relaxate, în ordine; V1 și V7 nu se relaxează). Motiv și constrângerile relaxate sunt în ieșire.
4. Dacă nici `return` nu respectă V1 (O₂ insuficient): `EMERGENCY` cu steag `UNRECOVERABLE`: cel mai scurt drum către refugiu, cu timpul de O₂ rămas; nu se ascunde în ieșire.
5. Reguli de explicație: codurile de motiv sunt stabile (`ROUTE_OK`, `HAZARD_ON_ROUTE`, `SIDESTEP_INFEASIBLE`, `NO_VALID_OPTION`, `OFF_MAP`, `NO_SHELTER`, `HYSTERESIS`…); LLM-ul vede doar numerele din rezumat.

---

## 10. Scenarii de test (golden), pentru testele de integrare

Fiecare are intrare fixă, decizie așteptată și aserțiuni. Toate rulează pe situl sintetic și, unde se poate, pe grile mici.

| ID | Scenariu | Așteptat |
|---|---|---|
| SC-01 | fără hazarduri | `CONTINUE`, `ROUTE_OK` |
| SC-02 | vârtej mic (< 30 m) pe traseu | ignorat, `CONTINUE` |
| SC-03 | vârtej mare, traversare perpendiculară, contact în 20 min | `REROUTE` (ocolire) sau `WAIT` scurt; fără contact după |
| SC-04 | front de furtună care se apropie frontal, mai rapid decât astronautul | `SIDESTEP_INFEASIBLE`; `RETURN` sau `WAIT` |
| SC-05 | furtuna din demo (minutul 72): ocolire nord vs sud | două ocoliri distincte; varianta cu O₂ sub rezervă eliminată de validator |
| SC-06 | pericol pe astronaut | `exit_zone`, traseu de ieșire existent |
| SC-07 | furtună regională | `RETURN`; efecte globale (apus mutat) |
| SC-08 | furtună solară | `shelter`; doză × 2,5 în buget |
| SC-09 | scurgere în costum | `RETURN` direct, fără opriri |
| SC-10 | coechipier rănit | `RETURN`, punct de neîntoarcere recalculat |
| SC-11 | furtună peste habitat (`none`) | `RETURN` cu grație; sau `WAIT` în afara amprentei |
| SC-12 | habitat `unusable` | `NO_SHELTER`, refugiu improvizat, `EMERGENCY` |
| SC-13 | astronaut la marginea hărții, ocolirea cere ieșire | `WAYPOINT_OFF_MAP`, `RETURN` sau `detour_free` |
| SC-14 | astronaut în afara hărții | `OFF_MAP`, `RETURN` estimat |
| SC-15 | două furtuni care închid traseul | `wait` sau `return`; fără ocolire invalidă |
| SC-16 | pericol personalizat injectat la minutul X, apoi `update` de viteză | replanificare imediată după `update`; `rev` crește |
| SC-17 | pericol care trece în spatele astronautului înainte să ajungă acolo | `CONTINUE` (nu se blochează celule deja eliberate) |
| SC-18 | țintă izolată | `return` fără A* costisitor; `ISOLATED` |
| SC-19 | furtună injectată pe drumul de întoarcere, după `RETURN`, contact în 20 min | ocolire pe drumul spre casă (`REROUTE`, `phase = INBOUND`), nu confirmarea drumului vechi |
| SC-20 | aceeași furtună, oglindită: o dată pe dus, o dată pe întors | același tip de decizie și aceleași criterii de validare |
| SC-21 | furtună pe întoarcere, mai rapidă decât astronautul, O₂ suficient | `WAIT` în afara amprentei, apoi reluare spre habitat |
| SC-22 | furtună pe întoarcere, O₂ insuficient pentru ocolire sau așteptare | `EMERGENCY`, cel mai scurt drum, steag clar |

**Proprietăți (aceleași scenarii, 50+ cazuri cu seed fix):** nicio alternativă validă nu încalcă V1-V8; ieșirea e identică la două rulări; decizia aleasă ∈ mulțimea validă (sau `EMERGENCY`); expunerea calculată continuu ≥ expunerea eșantionată; adăugarea unui obstacol nu scade costul optim.

---

## 11. Parametri (nivel C dacă nu e specificat)

| Parametru | Valoare | Notă |
|---|---|---|
| `TICK_MIN` | 1 | |
| `K` per mod | 15 / 5 / 1 / 2 / 1 | secțiunea 3 |
| `H_WATCH`, `H_REACT`, `H_CONE` | 90, 30, 15 min | |
| `SIDESTEP_MARGIN_M`, `D_CLEAR_M` | 50, 50 | |
| `IGNORE_RADIUS_M` | 30 | vârtejurile mici nu contează (cercetare) |
| `GLOBAL_COVERAGE` | 0,6 | |
| `ALPHA` implicit | 15 m/min (vârtej), 30 m/min (front) | calibrare pe MEDA |
| `W_MAX`, pas | 30, 5 min | |
| `δ` histerezis, `DWELL_MIN` | 0,12, 3 min | |
| `HUB_GRACE_M`, `AIRLOCK_MIN` | 100 m, 5 min | |
| `M_CORE`, `M_HALO`, `M_MAX` | 1000, 200, 5000 | |
| `N_MAX` expandări | 600 000 | degradare deterministă |
| `V_HAZARD_MAX` | 40 m/s | vânt măsurat în celule 20-45 m/s (registru) |
| Rezervă O₂, margine apus, pantă | 30 %, 30 min, 20° | din `Limits` și registru |
| Oboseală, scurgere, furtună solară | ×0,8 / ×1,15; 0,15 %/min; ×2,5 | cercetare și registru (A/B) |
| Coechipier rănit | viteză ×0,5, O₂ ×1,5 | nivel C |

---

## 12. Impactul asupra rolurilor și a contractelor

| Rol | Ce schimbă |
|---|---|
| **2 (core)** | `hazards`: model unificat, testul continuu, `can_sidestep`; `routing`: grila de timp, Dijkstra multi-sursă, `project_to_grid`; `alternatives`: waypoint iterat, etichete, deduplicare, `replan_stops`, `shelter`; `budget`: `timeline` cu efecte; validator V5-V8; mod `OFF_MAP`; `alternatives.generate` funcționează cu lista de opriri goală (ținta = refugiul), `benchmark` replanifică și după RETURN |
| **3 (backend)** | se elimină regula „după RETURN nu mai replanifici”; watchdog și replanificare și în faza `INBOUND`; mașina de moduri și `K` adaptiv; ordinea tick-ului; evenimente `add`/`update` cu `rev`; hash de stare canonică; un singur replan pe tick |
| **1 (date)** | clase implicite de hazard, parametri cu surse, scenariile golden, generator de scenarii |
| **4 (frontend)** | formular pentru hazard personalizat; ocolire cu etichete `north/south/east/west`; stări `NO_SHELTER`, `OFF_MAP`, `UNRECOVERABLE` |
| **Contracte** (cu acordul tuturor) | `live_event.json`: câmpurile `HazardSpec`, `op`, `rev`; ieșirea de decizie: `reason`, `omitted` cu coduri, steaguri; ids `detour_*` ca șiruri libere |

---

## 13. Ordinea de implementare

1. Modelul `HazardSpec`, normalizarea și `update` cu re-ancorare; testul continuu cu teste pe cazuri cunoscute (verificat împotriva unei eșantionări foarte fine).
2. `budget.timeline` cu efecte; `t_est` (Dijkstra înainte pe timp).
3. `Φ` și `C_temp`; regula startului în pericol; `can_sidestep`.
4. Candidați: waypoint iterat și etichetare, `wait` calculat, `exit_zone`, deduplicare, `replan_stops`, `shelter`.
5. Validator V1-V8 și scorul normalizat cu preset-uri; histerezis cu dwell.
6. Refugii multiple și Dijkstra multi-sursă; politica `NO_SHELTER`; `OFF_MAP`.
7. Mașina de moduri și bucla multi-rată în motor.
8. Scenariile SC-01…SC-18 și proprietățile, apoi benchmarkul.

**Criterii de acceptare:** SC-01…SC-18 trec; proprietățile trec pe ≥ 50 de cazuri; ieșirea e identică la două rulări; replanificarea ≤ 0,5 s, watchdog < 50 ms (măsurate); niciun apel nu aruncă excepție pe intrările din cazurile limită.

**De decis cu echipa înainte de implementare:** etichetele `east/west` în contract; mulțimea de refugii (doar habitatul sau și altele); valorile pentru coechipier rănit; dacă `replan_stops` intră în prima versiune.
