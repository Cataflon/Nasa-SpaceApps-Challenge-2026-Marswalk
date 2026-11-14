# Plan de implementare: replanificarea live a traseului

> Scop: în timpul ieșirii, copilotul verifică la fiecare tick dacă traseul activ mai e bun. La un eveniment (testăm cu **cutremurul**, pentru că e fix și nu depinde de conul furtunilor) calculează trasee noi. Dacă există unul care **ajunge la destinație, se întoarce acasă și ocolește pericolul**, îl alege, iar traseul vechi e abandonat. Întoarcerea (RETURN) rămâne doar pentru cazul în care niciun astfel de traseu nu trece regulile de siguranță.
>
> Baza teoretică: documentul „Arhitectura deterministă de rutare și replanificare dinamică” (secțiunile citate ca §N). Unde ne abatem de la el, scrie explicit de ce.

---

## 0. Ce se întâmplă acum la un cutremur și de ce iese RETURN

Cutremurul implicit (`HAZARD_DEFAULTS["marsquake"]`) e o zonă fixă de 300 m rază, pusă pe traseu acolo unde va fi astronautul peste 15 min. Fiind fix, **nu are con de predicție**, deci problema furtunilor nu-l afectează. Cu toate astea, decizia e RETURN din trei motive:

1. **Ocolirea refăcea doar jumătate de drum.** `alternatives._detours` caută un drum nou doar de la poziție până la următoarea țintă, apoi lipește **restul traseului vechi** (țintă → habitat). Dus și întorsul trec de obicei pe același culoar, deci întoarcerea trece tot prin cutremur. Rezultatul: `HAZARD` pe toate ocolirile.
2. **Ocolirile sunt aproape identice.** Cele 3 preset-uri ale A\* spațiu-timp dau trasee la +1-3 min de cel curent, nu ocoliri reale pe flancuri.
3. **Scorul preferă întoarcerea.** `score = risc + 0,15 × știința pierdută`: o ocolire validă cu risc peste 0,15 pierde în fața RETURN (scor 0,15).

În plus, în motor:
- se replanifică doar când un pericol taie traseul;
- nu există căutare periodică a unui traseu mai bun;
- RETURN e definitiv (`stops_left = []`).

> **Pasul F0, rezultat (14.11):** confirmat pe ambele situri. Traseu spre `clay_delta`, cutremur injectat la minutul 3:
>
> | Sit | Ocolirile de acum | Unde ating cutremurul | Ocolirea refăcută și pe întors |
> |---|---|---|---|
> | Jezero | `detour_north`/`detour_south`: risc 1,0 → `HAZARD` | **doar pe ÎNTORS** (după țintă) | risc 0,09, O₂ la habitat 68%, 285 m de centru → **validă** |
> | sintetic | `detour_west`: risc 1,0 → `HAZARD` | **doar pe ÎNTORS** | risc 0,00, O₂ 73% → **validă** |
>
> WAIT e inutil la cutremur (pericol fix): risc 1,0 și după 90 de minute. `alternatives.generate` durează 440-600 ms (A\* spațiu-timp × 3 preset-uri), iar un A\* 2D pe grila completă pentru drumul de întoarcere durează doar ~30 ms. Deci varianta din §3.1 (A\* 2D pe C_temp) e și corectă, și de ~10 ori mai rapidă.

---

## 1. Rezultatul dorit (criterii de acceptare)

| # | Situație (cutremur injectat fără parametri, pe traseul spre țintă) | Ce trebuie să iasă |
|---|---|---|
| A1 | Se poate ocoli și O₂ / apusul permit | **REROUTE** în același tick. Traseul nou: poziție → țintă → habitat, fără nicio celulă cu risc ≥ 0,3. Traseul vechi nu mai apare ca `current`. |
| A2 | Cutremurul e chiar peste țintă (ținta inaccesibilă) | **RETURN**, pe un drum spre casă care ocolește zona. |
| A3 | Ocolirea există, dar încalcă rezerva de O₂ sau apusul | **RETURN**; ocolirile apar respinse, cu `O2_RESERVE` / `DAYLIGHT`. |
| A4 | Cutremur lângă traseu, dar nu pe el | **CONTINUE**, fără mesaj `decision`. |
| A5 | Cutremur peste poziția astronautului | Graful rămâne conex (§3.3). Se găsește ieșirea cea mai scurtă din zonă, apoi traseul spre țintă sau acasă. |
| A6 | Aceeași intrare, rulată de două ori | Aceeași decizie și același traseu, bit cu bit (§1). |
| A7 | Fără evenimente noi, traseul rămâne valid | Fără „pâlpâire”: nicio schimbare de traseu fără o îmbunătățire ≥ 12% (histerezis, §5.2). |

---

## 2. Arhitectura

```
engine.step()  (1 tick = 1 minut simulat; la viteza 10 = 10 tick-uri pe secundă reală)
 │
 ├─ deplasare, O₂, doză, pericole
 │
 ├─ NIVEL 1  watchdog (fiecare tick, < 1 ms)       ── §6 nivelul 1
 │    • traseul rămas e lovit de vreun pericol în [t, t+90 min]?
 │    • bugetul ține? (O₂ la habitat ≥ rezervă, sosire ≤ apus − 30 min)
 │
 ├─ trigger?
 │    • NIVEL 3  imediat: eveniment nou în acest tick / watchdog invalid / pericol < 450 m   ── §6 nivelul 3
 │    • NIVEL 2  periodic: t % 5 == 0 și există pericole active sau suntem în WAIT/RETURN    ── §6 nivelul 2
 │
 └─ replan.replan(...)  ← modulul nou
      1. C_temp = cost static + penalizare graduală a pericolelor                  ── §3.3
      2. candidați: CONTINUE, DETOUR_NORTH, DETOUR_SOUTH, DETOUR_FREE, WAIT, RETURN ── §4.2
         (fiecare = traseu COMPLET: poziție → ținte rămase → habitat)
      3. buget + risc pe fiecare (route_budget, route_risk cu eta)                 ── §3.2
      4. validator (cele 5 reguli, neschimbat)                                     ── §5.1
      5. arbitru pe niveluri: destinația întâi, apoi S(π), apoi histerezis         ── §5.2 (modificat)
      → Decision
 │
 └─ dacă decizia sau geometria traseului s-a schimbat:
      motorul înlocuiește traseul activ, crește `route_version`, trimite `decision` pe WS;
      explicația LLM pleacă asincron (ca acum)
```

### Unde stă codul

| Fișier | Ce | Cine |
|---|---|---|
| `backend/app/live/replan.py` (**nou**) | pașii 1-5: C_temp, candidații, arbitrul pe niveluri | rolul 3 |
| `backend/app/live/engine.py` | bucla pe 3 niveluri, aplicarea deciziei, `route_version`, RESUME | rolul 3 |
| `backend/app/core/*` | **neatins**: refolosim `static_cost`, `astar`, `home_tree`/`path_home`, `route_budget`, `route_risk`, `hazard_field`, `validator` | rolul 2 |
| `backend/app/core/hazards.py` | **doar** plafonul conului `R_max` (F5, pentru furtuni, nu pentru cutremur) | rolul 2, cu acordul lor |

De ce un modul nou în `live/` și nu modificări în `core/alternatives.py` și `decision.py`: benchmark-ul rolului 2 folosește `alternatives.generate` și `decision.choose`. Dacă le lăsăm neatinse, benchmark-ul și testele lor rămân stabile și nu avem conflicte de merge. Când noul replanificator se dovedește mai bun, rolul 2 poate muta benchmark-ul pe el.

---

## 3. Algoritmul, pas cu pas

### 3.1. Costul temporar C_temp (§3.3)

```python
def temp_cost(site, hazards, t_min, horizon_min, preset) -> np.ndarray:
    base = static_cost(site, preset)                   # inf pe pante > max și pe celulele unsafe
    field = max over k in 0..horizon step 5 of hazard_field(hazards, t_min + k)   # amprenta pe orizont
    penalty = M_HAZARD * field                         # graduală: 0 la margine, M în centru
    penalty[field >= LETHAL] = inf                     # nucleul letal: doar pentru regional_storm
    return base + penalty
```

- **Penalizare graduală, nu interdicție.** Graful rămâne conex: chiar dacă astronautul e în zonă, A\* găsește cea mai scurtă ieșire (criteriul A5). Validatorul respinge oricum traseele care ating risc ≥ 0,3.
- **Cutremurul e fix**, deci amprenta pe orizont e chiar elipsa lui. Pentru furtuni, „max pe orizont” e amprenta măturată, iar plafonul `R_max` (F5) o ține finită.
- `M_HAZARD` ≫ costul static al unei celule (de exemplu 1000 × costul mediu), ca A\* să ocolească ori de câte ori există un ocol fizic.
- **De ce A\* 2D și nu spațiu-timp** (§4): e mai rapid și dă ocoliri vizibile, cu adevărat pe flancuri. Conflictul temporal (§3.2) se verifică după aceea, pe traseul complet, cu `route_risk(path, eta)`. Deci un traseu care trece prin spatele unei furtuni după ce a plecat nu e respins.

### 3.2. Cei 6 candidați (§4.2), fiecare traseu complet

Notații: `pos` = poziția curentă; `stops` = țintele rămase, în ordinea din plan; `home` = habitatul.

```python
def full_route(pos, via, stops, cost):
    """pos → [waypoint] → stop1 → stop2 → … → home, fiecare segment cu A* pe C_temp."""
    points = [pos] + ([via] if via else []) + stops + [home]
    return concat(astar(cost, a, b) for a, b in pairs(points))   # None dacă un segment nu are drum
```

| ID | Prioritate | Construcție | Rol |
|---|---|---|---|
| `current` (CONTINUE) | 0 | traseul activ rămas, neschimbat | evită devierile inutile |
| `detour_north` (REROUTE) | 1 | `full_route(pos, W_nord, stops)` | ocolire clară pe flancul stâng |
| `detour_south` (REROUTE) | 2 | `full_route(pos, W_sud, stops)` | ocolire clară pe flancul drept |
| `detour_free` (REROUTE) | 3 | `full_route(pos, None, stops)` pe C_temp | plasă de siguranță: culoare înguste |
| `wait` (WAIT) | 4 | rămâne pe loc W minute, apoi `current` | pentru pericole care trec; la cutremur nu ajută |
| `return` (RETURN) | 5 | `path_home` din Dijkstra invers; dacă e lovit, `astar(pos, home)` pe C_temp | întoarcerea garantată |

**Waypoint-urile N/S** (§4.2):
1. `P` = primul punct al traseului activ cu risc ≥ 0,3 (locul impactului).
2. `d` = direcția traseului în `P`, ca medie a ultimelor ~10 celule dinainte (mai stabilă decât un singur segment).
3. `n⊥` = perpendiculara pe `d`. „Nord” = partea din stânga direcției de mers, „sud” = partea din dreapta. Numele rămân `detour_north` / `detour_south` ca să se potrivească cu `prompts.alt_name`.
4. `W = P ± n⊥ × (R_max + d_clear)`, cu `R_max` = semiaxa mare a pericolului (plafonată) și `d_clear` = 200 m.
5. Lipire de grilă: cea mai apropiată celulă cu cost finit și `field < 0,1`, căutată în spirală în **ordine fixă** (N, NE, E, SE, S, SV, V, NV), pentru determinism (§1.3). Dacă nu există pe o rază de 1 km, candidatul lipsește.

**Viteză:**
- Segmentele care nu ating pericolul refolosesc traseele deja calculate: Dijkstra invers spre casă și segmentele din planul inițial.
- Doar segmentele afectate trec prin A\*.
- Dacă un candidat iese identic cu altul, păstrăm doar unul (cel cu prioritatea mai mică).

### 3.3. Evaluare (§3.2)

Pentru fiecare candidat, exact ca `alternatives.evaluate` de acum:
- `route_budget(path, …, dwell la ținte, o2_start = O₂ acum)` → eta pe fiecare celulă, O₂ la habitat, doza, ora sosirii;
- `route_risk(path, eta, hazards)`: intensitatea maximă **la momentul în care astronautul e în celulă**;
- `science_lost` = țintele rămase pe care traseul nu le atinge (pentru RETURN: toate);
- totul împachetat în `Alternative`, ca validatorul, mesajul WS și LLM-ul să rămână neschimbate.

### 3.4. Validatorul (§5.1): neschimbat

`core.validator.validate`: rezerva de O₂, apusul cu marjă, panta, doza, pericolul. O variantă invalidă nu ajunge niciodată la astronaut.

### 3.5. Arbitrul pe niveluri (§5.2, modificat)

**Abatere de la document:** scorul `S(π)` din §5.2 nu conține știința. RETURN consumă cel mai puțin O₂ și timp, deci ar câștiga aproape mereu, exact problema de acum. De aceea alegerea se face **întâi pe niveluri**, iar `S(π)` contează doar **în interiorul** aceluiași nivel:

```python
def arbitrate(cands, current, last_choice):
    valid = [c for c in cands if c.valid]

    # Nivel 0: traseul activ e valid și nu atinge pericolul → rămâne (cu histerezis, mai jos)
    # Nivel 1: variante valide care ating TOATE țintele rămase (detour_*, wait)
    # Nivel 2: variante valide care sar peste ținte, dar ating restul   (F6, opțional)
    # Nivel 3: return (valid)
    # Nivel 4: EMERGENCY → ruta de cost minim spre casă (§5.1)

    tier = lambda c: 0 if c is current else 1 if not c.science_lost and c.kind != "RETURN" \
                     else 3 if c.kind == "RETURN" else 2
    best = min(valid, key=lambda c: (tier(c), round(S(c), 6), PRIORITY[c.id], c.id))
```

`S(π)` din §5.2, cu termeni normalizați la 0..1 și rotunjit la 6 zecimale:
`S = 0,45 · risc + 0,30 · (O₂ consumat / 100) + 0,15 · (timp extra / 120 min) + 0,10 · (doză / doza maximă)`

**Histerezis (§5.2, δ = 12%):**
- dacă traseul activ e **invalid**: se adoptă imediat `best`;
- dacă e **valid**: se schimbă doar dacă `best` e într-un nivel mai bun sau `(S_curr − S_best) / max(S_curr, 1e-6) ≥ 0,12`. Asta oprește pâlpâirea (criteriul A7).

**„Cel vechi nu mai e luat în considerare”:** după un REROUTE, traseul ales **devine** traseul activ. La următoarea replanificare, `current` e noul traseu, iar vechiul dispare complet: nu mai e candidat și nu mai e desenat ca activ.

---

## 4. Bucla din motor (§6), modificările din `engine.py`

```python
def step(self):
    ...                                   # deplasare, O₂, doză, evenimente (ca acum)
    trigger = self._watchdog(t)           # NIVEL 1: "hazard" | "budget" | "proximity" | None
    if new_hazard_this_tick:              # NIVEL 3: eveniment injectat
        trigger = "event"
    elif trigger is None and t % REPLAN_EVERY_MIN == 0 and self._worth_replanning():
        trigger = "periodic"              # NIVEL 2
    if trigger:
        msgs += self._replan(t, trigger)
```

| Funcție | Ce face |
|---|---|
| `_watchdog(t)` | `route_hit` pe traseul rămas, pe orizontul de 90 min, pentru fiecare pericol; `_o2_after(...)` vs rezervă; ora sosirii vs apus − 30; distanța până la cel mai apropiat pericol < 450 m. Ieftin, rulează la fiecare tick. |
| `_worth_replanning()` | Există pericole active sau suntem într-un WAIT / RETURN cauzat de pericol. Fără pericole, nu are rost replanificarea periodică. |
| `_replan(t, trigger)` | Cronometrează (`compute_ms`), apelează `replan.replan(...)`, apoi `_apply`. Trimite `decision` doar dacă decizia **sau geometria traseului** s-a schimbat (hash pe `path`). |
| `_apply(decision)` | REROUTE: `self.remaining = alt.path`, `stops_left` rămân, `route_version += 1`. WAIT: `wait_until`. RETURN: păstrăm țintele în `self.suspended_stops`, nu le ștergem (pentru RESUME). |
| RESUME (F4) | Într-un RETURN cauzat de pericol, replanificarea periodică încearcă și candidații spre `suspended_stops`. Dacă unul e valid (nivelul 1), decizia e `REROUTE` cu `reason_code: "HAZARD_CLEARED"`, deci astronautul reia drumul spre țintă. |

**De ce nu afectează determinismul** (§1.1): replanificarea rulează **în interiorul** tick-ului `t`, pe timp logic. Dacă un calcul durează 300 ms, tick-ul următor pleacă mai târziu în timp real, dar rezultatul e identic. Dacă replanificarea depășește ~200 ms, mutăm `step()` în `asyncio.to_thread`, ca WebSocket-ul și chatul să nu înghețe. Logica rămâne aceeași.

---

## 5. Mesajele: modificări minime, compatibile

Mesajul `decision` rămâne cum e; câmpurile noi sunt **opționale**:

| Câmp | Exemplu | Pentru ce |
|---|---|---|
| `trigger` | `"event"`, `"periodic"`, `"watchdog"`, `"proximity"` | UI și LLM: „replanificat pentru că…” |
| `route_version` | `3` | UI-ul știe că traseul activ s-a schimbat |
| `compute_ms` | `84.0` | contorul „Pământul vs. copilotul” (există deja) |

`tick.remaining_path` are deja traseul nou din tick-ul următor, deci harta 3D îl desenează fără nicio modificare. LLM-ul primește aceeași formă de `summary`; în `prompts.alt_name` trebuie adăugat doar `detour_free`.

---

## 6. Pașii de implementare

| Pas | Ce | Fișiere | Timp estimat |
|---|---|---|---|
| **F0** | Scriptul de diagnoză pentru cutremur: confirmă cauza din §0.1 | scratch | 15 min |
| **F1** | `replan.py`: `temp_cost`, `full_route`, waypoint-urile N/S, `detour_free`, `return`, `wait`, evaluarea | `live/replan.py` | 2-3 h |
| **F2** | Arbitrul pe niveluri + `S(π)` + histerezis 12% | `live/replan.py` | 45 min |
| **F3** | Motorul: watchdog (pericol + buget + proximitate), trigger pe eveniment, periodic la 5 min, `_apply`, `route_version`, `trigger` | `live/engine.py` | 1,5 h |
| **F4** | RESUME după un RETURN cauzat de pericol | `live/engine.py` | 1 h |
| **F5** | Plafonul `R_max` pe tip de pericol, ca să funcționeze și furtunile | `core/hazards.py` (rolul 2) | 15 min |
| **F6** | Opțional: nivelul 2, „sar peste o țintă, le fac pe celelalte” | `live/replan.py` | 1 h |

**Stare (14.11):**
- ✅ F0.
- ✅ F1, în `app/live/replan.py` (`Situation`, `candidates`):
  - pe același cutremur, toate ocolirile ies valide: Jezero `detour_south` / `detour_north` / `detour_free` cu risc 0, O₂ 68-70%, +4…12 min; sintetic `detour_west` / `detour_east` / `detour_free` cu risc 0, O₂ 72-73%;
  - WAIT și `current` rămân respinse (`HAZARD`); RETURN e valid, dar pierde ținta;
  - timp ~145 ms (față de 440-600 ms la `alternatives.generate`), determinist;
  - numele ocolirilor sunt geografice (latura waypoint-ului față de impact); prioritatea internă e stânga = 1, dreapta = 2, liberă = 3 (`Situation.priority`).
- ✅ F2, în `replan.py` (`tier`, `s_score`, `arbitrate`, `replan`). Verificat pe ambele situri:

  | Caz | Decizie | Timp |
  |---|---|---|
  | A1, cutremur pe traseu | **REROUTE** `detour_free` (risc 0, ținta păstrată) | ~150 ms |
  | A2, cutremur peste țintă | **RETURN** | ~9 ms |
  | A3, cutremur de 5 km peste astronaut | **EMERGENCY** pe ruta spre casă | ~25 ms |
  | A4, cutremur departe de traseu | **CONTINUE** (`ROUTE_OK`) | ~60 ms |

  O țintă aflată chiar în zona de risc nu mai primește ocoliri: oricum ar fi respinse, iar A\* spre ea explora toată harta (2-2,5 s → 9 ms).
  Coduri noi de motiv: `BETTER_ROUTE` (traseul valid e înlocuit de unul cu S cu ≥ 12% mai mic sau dintr-un nivel mai bun), `LIMITS_EXCEEDED` (traseul curent încalcă O₂, apusul sau doza, fără pericol).
- ✅ F3, în `engine.py`:
  - **Bucla pe 3 niveluri:** `_check_route` cu triggerele `event` / `hazard` / `budget` / `proximity` / `periodic`.
  - **Calculul:** `_situation` → `replan.replan`; fallback-ul vechi rămâne fără sit sau pe traseul mock.
  - **Traseul nou devine cel activ** (`route_version` crește, `suspended_stops` la RETURN).
  - **Ce se anunță:** o decizie care nu schimbă traseul nu se anunță, decât ca răspuns la un eveniment nou.
  - **Rutarea ține 100 m distanță de pericol** (`SAFETY_MARGIN_M`, §3.2).
  - **Scurgerea în costum** intră în bugetul candidaților.
  - **Verificat cap-coadă**, cutremur la minutul 3:

    | Sit | Decizie | Distanța minimă față de centru (raza 300 m) | Final |
    |---|---|---|---|
    | Jezero | REROUTE `detour_free` (+7 min) | 400 m | ținta atinsă, acasă cu 61% O₂ |
    | sintetic | REROUTE (+2 min) | 400 m | ținta atinsă, acasă cu 63% O₂ |

    Un tick obișnuit durează ~0,5 ms; cel cu replanificarea, ~150 ms.
- Teste: `tests/live/test_replan.py`, `tests/live/test_engine.py` (`test_marsquake_on_route_is_avoided_end_to_end`, `test_engine_applies_replan_decision`).

Ordinea: F0 → F1 → F2 → F3 dau deja criteriile A1-A7 cu cutremurul. F4 și F5 vin după, F6 doar dacă rămâne timp.

---

## 7. Cum testăm

**Automat (puține teste, doar ce contează):**
1. A1: cutremur pe traseu → `REROUTE`, iar traseul ales nu are nicio celulă cu risc ≥ 0,3 și se termină în habitat.
2. A2: cutremur peste țintă → `RETURN`.
3. A6: aceeași replanificare de două ori → rezultat identic.

**Manual, în aplicație:**
1. Planifici `clay_delta`, apeși Start EVA, aștepți 2-3 minute.
2. Injectezi **marsquake**: apare cercul de 300 m pe traseu, în fața astronautului.
3. În același tick: decizia **REROUTE**. Pe hartă, ocolirea N/S e linia plină portocalie, iar celelalte variante sunt gri sau roșu punctat (respinse).
4. Astronautul ocolește, ajunge la țintă și se întoarce pe un drum care nu trece prin cutremur.
5. DevTools → WS: `decision.trigger = "event"`, `compute_ms` și `route_version` crescut.

---

## 8. Riscuri și limite

- **Timpul de calcul pe Jezero** (500 × 500): fiecare A\* complet durează zeci până la sute de ms. Avem până la 3 detururi × (2-3 segmente). Măsuri: refolosim segmentele neafectate, rulăm A\* doar pe porțiunea din jurul pericolului și, la nevoie, mutăm `step()` în thread (§4).
- **Furtunile** rămân nerealiste până la F5. Cu F1-F3 făcute, plafonul `R_max` e singurul lucru care le lipsește.
- **Ordinea țintelor** rămâne cea din planul inițial. Nu reordonăm țintele la replanificare: CP-SAT e prea lent pentru un tick și nici nu e cerut aici.
