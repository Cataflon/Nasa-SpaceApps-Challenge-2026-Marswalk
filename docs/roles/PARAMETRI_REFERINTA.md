# Marswalk Copilot — registrul parametrilor de referință

Toate valorile pe care le folosește simularea (generatorul de scenarii, harta de cost, bugetul, pericolele, validatorul), fiecare cu sursa ei și cu un nivel de încredere. Scopul: orice cifră care apare pe ecran sau în prezentare să poată fi urmărită până la o măsurătoare NASA sau la o presupunere declarată.

Căutat și verificat pe 14 noiembrie 2026. Linkurile sunt la final, numerotate [S1]…[S34].

> **Actualizat 14.11 (rolul 1):** fiecare sursă trimite acum la **DOI-ul oficial** al articolului (verificat în Crossref) sau la o **pagină NASA** (NTRS, nasa.gov, jpl.nasa.gov, NSSDC). Link-urile de presă, oglinzile neoficiale, cataloagele de bibliotecă și accesele prin proxy universitar au fost înlocuite. **✔** = valoare citită de noi în textul complet sau pe pagina NASA; fără ✔ = cifră preluată din rezumat, de verificat înainte de prezentare.

## Nivelurile de încredere

| Nivel | Înseamnă | Cum îl prezentăm |
|---|---|---|
| **A — măsurat** | valoare publicată din date de misiune (MEDA, RAD, Apollo) | „măsurat de …” |
| **B — derivat** | calculat din valori A, cu o formulă standard | „derivat din …”, cu formula |
| **C — presupunere** | ales de noi, plauzibil, fără măsurătoare directă | „presupunere”, pe ecranul „Cum calculăm” |

Regula: **nicio constantă nu intră în cod fără nivel și sursă**, scrise în comentariu și în registrul `core/params.py` (propus la final).

---

## 1. Mediul de la Jezero (generatorul de scenarii, rolul 1)

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Coordonatele locului de aterizare Perseverance | 18,44°N, 77,45°E | A | [S1] |
| Durata solului | 24 h 39,5 min (24,6597 h) | A ✔ | [S2] |
| Temperatura aerului, ciclu zilnic tipic | −83 °C înainte de răsărit → −23 °C la prânz | A ✔ | [S3] |
| Temperatura solului, ciclu zilnic tipic | −83 °C înainte de răsărit → +5 °C la prânz | A ✔ | [S3] |
| Temperatura medie a aerului | ≈ −59 °C (media atmosferei marțiene, NSSDC; −55 °C nu apare în sursă); la Jezero aerul variază ~60 °C între noapte și prânz (−83 → −23 °C) | A ✔ | [S2] [S3] |
| Variația sezonieră a temperaturii aerului | foarte mică | A | [S4] |
| Presiunea, prima zi de măsurători (Ls ≈ 5°) | 718 Pa (modelele prevedeau 705-735 Pa) | A ✔ | [S5] |
| Maximul sezonier al presiunii medii zilnice | 761 Pa, în jurul solului 105 (Ls ≈ 55°) | A ✔ | [S6] |
| Ciclul zilnic al presiunii | maxim la 7-8 h LMST, minim între 12 și 16 h LMST | A | [S6] |
| Vântul | mai calm în medie decât la alte situri; rafale turbulente de la calm la 10-15 m/s în secunde-minute | A | [S7] |
| Distribuția vitezei vântului (1,5 m, solurile ≤ 315) | Weibull pe intervale orare (Tabelul 1): dimineața 07-10 h c = 3,02 m/s, k = 2,01 (media 2,7); prânz 10-15 h c = 5,28, k = 2,16 (media 4,7); după-amiază 15-18 h c = 6,80, k = 3,02 (media 6,1); total c = 3,57, k = 1,49 | A ✔ | [S7] |
| Intensitatea turbulenței (σ / medie pe 10 min) | 36 ± 10 % ziua, 22 ± 10 % noaptea; la vârtejuri vârfuri de 9,2 × vântul de fond | A ✔ | [S7] |
| Opacitatea prafului (tau), sezon liniștit | ≈ 0,5 (sursa inițială, un PDF neoficial, nu mai răspunde; de verificat în [S8]) | A | [S8] |
| Prima furtună regională deasupra Jezero | Ls ≈ 153-156° | A | [S9] |

**Recomandare pentru `scenario.py`:**
- temperatura: sinusoidă zilnică între −83 și −23 °C, cu maximul la prânz, plus zgomot de ±2,5 K (amplitudinea fluctuațiilor de la prânz) [S10];
- presiunea: medie ≈ 720 Pa + componenta de maree termică (maxim dimineața, minim după-amiaza), amplitudine de calibrat pe MEDA;
- vântul: eșantionat dintr-o distribuție Weibull ajustată pe MEDA, nu o sinusoidă. Turbulența e cea care dă vârfurile [S7]. ✅ **Făcut** în `scenario.py` cu Tabelul 1 din [S7]; cifrele sunt și în `data/processed/jezero/wind_stats.json`;
- tau: 0,5 ca valoare de bază; crește doar la evenimentele de praf.

## 2. Radiația (stratul `radiation`, scenariul, validatorul)

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Doza echivalentă GCR la suprafață (Gale, aug. 2012 - iun. 2013) | **0,67 mSv/zi ≈ 28 µSv/h** | A ✔ | [S11] |
| Doza absorbită GCR la suprafață | 0,210 ± 0,040 mGy/zi ≈ 8,75 µGy/h | A | [S12] |
| Variația zi-noapte a dozei absorbite | între 180 și 225 µGy/zi (ciclul presiunii) | A | [S12] |
| Variația pe ciclul solar | GCR la suprafață a crescut cu ~50% de la maxim la minim solar | A | [S13] |
| Furtuna solară (SPE) din septembrie 2017, cea mai mare văzută de RAD | doza **× 2-3** față de fond („mai mult decât dublă” față de orice măsurătoare anterioară, NASA/JPL), creștere pe parcursul câtorva ore | A ✔ (dublarea) | [S14] [S15] |
| Evoluția după vârf | „the high readings lasted more than two days” (NASA/JPL); scenariul scade pe 48 h | A ✔ | [S15] |

> ✅ **Două corecturi față de repo (ambele aplicate de rolul 1, 14.11):**
> 1. `scenario.BASELINE["dose_rate_usv_h"] = 10.0` e, de fapt, ordinul de mărime al dozei **absorbite** (µGy/h), etichetat ca doză **echivalentă** (µSv/h). Valoarea corectă pentru µSv/h e **≈ 28**.
> 2. Exemplul din `shared/contracts/live_messages.json` are `"dose_rate_multiplier": 20` pentru furtuna solară. Cea mai mare furtună solară măsurată la suprafața lui Marte a dat **× 2-3** [S14]. Valoarea implicită realistă: **2,5**.

Observații:
- Gale e la −4,4 km față de nivelul de referință MOLA; Jezero e mai sus, deci cu ceva mai puțină atmosferă deasupra și o doză puțin mai mare. Diferența e mică; o declarăm ca nivel B.
- Cu 28 µSv/h, o ieșire de 8 ore primește ≈ 0,22 mSv; chiar cu o furtună solară × 3 tot timpul, ≈ 0,7 mSv. Limita din validator (`max_dose_msv = 1.0`) aproape că nu va fi atinsă niciodată. Asta e **realist**: pe suprafață, radiația contează prin acumulare pe toată misiunea, nu pe o singură ieșire. În prezentare o spunem așa, nu o ascundem.

## 3. Pericolele (modelul de pericol, rolul 2; generatorul, rolul 1)

### 3.1 Vârtejurile de praf (dust devils) — pericolul care se poate ocoli

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Frecvența de formare la Jezero | 1,3-3,4 / km² / sol | A ✔ | [S16] |
| Frecvența, altă estimare | 2,0-3,0 / km² / sol | A | [S17] |
| Diametrul | mediu 29 m, median 25 m, între ~5 și ~132 m | A ✔ | [S16] |
| Vârtejuri > 100 m | ≈ 0,1 / km² / sol | A | [S17] |
| Ora de vârf | 12:00-13:00 timp solar local adevărat | A ✔ | [S16] |
| Direcția de deplasare | aceeași cu vântul de fond (direcția vârtejului se potrivește cu cea a vântului măsurat) | A ✔ | [S16] |
| Vântul în interior (caz extrem) | 25 m/s, cu o scădere de presiune de 9 Pa | A | [S17] |
| Scăderea de presiune la trecere | 0,3-6,5 Pa, durată 1-200 s | A | [S1] |

Pe harta noastră de 100 km², asta înseamnă **130-340 de vârtejuri pe sol, din care ~10 mai mari de 100 m**, aproape toate la prânz. Concluzii pentru simulare:
- vârtejurile mici (< 30 m) nu se ocolesc; contează doar cele mari (> 100 m), cu vânt intern de până la 25 m/s, care au deteriorat chiar senzorii de vânt MEDA [S17];
- viteza lor = viteza vântului de fond, deci incertitudinea predicției vine din variabilitatea vântului (motivul pentru care `SIGMA_V` se calibrează pe datele de vânt);
- planificarea poate evita fereastra 12-13 LTST: argumentul de prevenire de pe slide.

### 3.2 Furtunile de praf — atenție la scară

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Furtună „locală” (clasificarea standard) | arie < 1,6 × 10⁶ km² | A | [S18] |
| Celule convective în furtuni | 20-40 km | A ✔ | [S20] [S18] |
| Vânt deasupra celulelor furtunilor | până la 140 km/h ≈ 39 m/s | A ✔ | [S20] |
| Viteza de deplasare a unei furtuni urmărite de pe orbită | ≈ 70 km/h (**nu apare în [S20]**, care dă doar vântul; de verificat în [S18]) | A | [S18] |
| Furtună regională | „bigger than the United States” | A ✔ | [S21] |
| Avertizare | furtunile regionale sunt urmărite de pe orbită (MARCI), care dă roverelor „advance notice” (pagina nu spune câte zile) | A ✔ | [S21] |

> ⚠️ **Problemă de realism în scenariul demo:** „furtuna locală” din `DEMO_SCENARIO_EVENTS` are 1,8 × 1,1 km și se mișcă cu 2,5 m/s. O furtună locală reală are zeci-sute de kilometri, adică mai mare decât toată harta noastră, și se mișcă mult mai repede. Ea **nu se poate ocoli** pe 10 km; se așteaptă la adăpost sau se face întoarcerea.
>
> **Varianta realistă, fără schimbări de cod (doar de parametri și de nume):**
> - **pericolul ocolibil** din scena 4 = un **vârtej de praf mare** (100-135 m, vânt intern până la 25 m/s), care se mișcă odată cu vântul (câțiva m/s), apărut la prânz. Elipsa și conul din `hazards.py` se potrivesc perfect;
> - **pericolul neocolibil** = **frontul unei furtuni** (elipsă foarte alungită, de exemplu 30 km × 5 km, viteză 10-20 m/s), detectat la orizont: decizia corectă e WAIT (adăpost) sau RETURN, în funcție de ETA și de O₂;
> - **furtuna regională** = avertizare de pe orbită → RETURN imediat (ca acum).
>
> Asta face scenariul mai puternic la *Validity*: fiecare pericol are dimensiunea și viteza lui reală.

## 4. Astronautul și costumul (bugetul, rolul 2)

### 4.1 Mersul

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Viteza de mers Apollo (model NASA din traversele Apollo 12 și 14, EVA 2) | v = 0,75 − 0,01·θ m/s (θ = panta în grade) → **2,7 km/h** pe plat | A ✔ | [S22] |
| Progres Apollo 15 | ~1 → ~1,5 km/h în EVA 1, apoi 2,0 km/h în EVA 2 (Apollo 14, urcând 10°: ~1,7 km/h) | A ✔ | [S23] |
| Viteza nominală maximă considerată pentru Apollo | 2,2 mph ≈ 3,5 km/h | A ✔ | [S24] |
| Pragul VO₂max pe Marte, test cu costum | atins la 3,5 mph ≈ 5,6 km/h | A ✔ | [S24] |
| Viteza nominală de mers folosită în planificarea NASA a traverselor | 4 km/h | A ✔ | [S25] |
| **Recomandat: viteza pe plat** | **3,0 km/h** = Tobler pe plat (5,04 km/h) × `SUIT_FACTOR` 0,6 | B | între datele Apollo și limita nominală |
| Panta maximă de mers (concept NASA pentru ieșirile de pe Lună) | **20°** (✅ decizia echipei, 14.11) | A | [S26] |
| Panta maximă traversată de Apollo 15 | ~17° | A | [S26] |
| Distanța maximă de la habitat, întoarcere pe jos | 10 km (testul „Walkback” NASA JSC) | A ✔ | [S27] |

> ✅ **Decis 20° (echipa, 14.11).** Datele (`data/processed/jezero/meta.json`, situl sintetic) și planner-ul au 20°. Mai rămân `Limits.max_slope_deg` (rolul 2) și contractele `shared/contracts/meta.json` / `site.json` (rolurile 2-3), încă la 25°.

Raza zonei noastre (3-5 km de habitat) e confortabil sub limita de 10 km [S27]: o validare bună pentru slide.

### 4.2 Metabolismul și oxigenul

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Rata metabolică medie pe ieșirile Apollo | 234 kcal/h ≈ 272 W ≈ 930 BTU/h | A ✔ | [S28] |
| Intervalul pe ieșirile Apollo | 780-1200 BTU/h = 822-1267 kJ/h ≈ 228-352 W, pe 158,8 h de ieșiri (Tabelul I, p. 8-9) | A ✔ | [S29] |
| Rata de proiectare a rucsacului Apollo (PLSS) | 1200 BTU/h, pentru 4 h | A ✔ | [S30] |
| Activitate ușoară în costum | 600 BTU/h ≈ 176 W | A | [S31] |
| Parametri standard pentru simularea unei ieșiri | 8 h la 1000 BTU/h | A | [S31] |
| Urcare 500 m pe pantă de 30% (16,7°), test la sol | 1656-1747 BTU/h (≈ 500 W) | A ✔ | [S32] |
| Ratele Apollo pe Lună față de testele la sol | până la 50% mai mici | A ✔ | [S32] |
| Echivalentul energetic al O₂ (coeficient respirator 0,82) | 4,825 kcal / litru O₂ | A | [S33] |
| Masa astronaut + costum, greutatea pe Marte | 583-927 N → **157-250 kg**, media 728 N ≈ 196 kg | B ✔ | [S34] |

**Modelul recomandat (calibrat pe două puncte măsurate):**

```
P = P_REST + M_TOTAL × (C_LEVEL × v + G_MARS × max(0, v_vertical) / ETA_UP)
```

| Constantă | Valoare | Nivel | De unde |
|---|---|---|---|
| `P_REST` | 176 W (600 BTU/h) | A | [S31] |
| `M_TOTAL` | 196 kg | B ✔ | media greutăților „Mars equivalent (with human)” din [S24]: 728 N / 3,71 m/s². Tabelul e în lbf (N), deci sunt greutăți pe Marte, iar împărțirea la g e corectă |
| `G_MARS` | 3,71 m/s² | A | constantă fizică |
| `C_LEVEL` | 0,59 J/(kg·m) | B | calibrat: mers pe plat la 3,0 km/h → 272 W (media Apollo [S28]) |
| `ETA_UP` | 0,22 | **C** | presupunere: 0,2-0,25 e eficiența musculară tipică la urcare. **Nu e calibrată pe [S32]**: testul din [S32] dă ≈ 500 W la 30% pantă, dar fără viteza de mers publicată în rezumat nu se poate deduce eficiența. De verificat în raportul complet; până atunci, rata la urcare rămâne o presupunere declarată |

**Oxigenul în procente.** Rezervorul se definește prin ce trebuie să susțină: **100% = 8 h la 1000 BTU/h** [S31] = 1000 × 0,252 / 4,825 × 8 ≈ **418 litri O₂** (≈ 0,6 kg). Apoi:

```
O2_pct_per_min(P_W) = P_W × 0,860 kcal/h/W / 4,825 kcal/L / 60 / 418 L × 100
                    ≈ 0,000711 × P_W   (%/min, P în W)
```

| Activitate | Putere | O₂ |
|---|---|---|
| Repaus / așteptare în costum | 176 W | **0,125 %/min** (7,5 %/h) |
| Mers pe plat, 3 km/h | 272 W | 0,194 %/min (11,6 %/h) |
| Urcare pe pantă de 30% | ≈ 500 W (măsurat la sol, [S32]; modelul cu `ETA_UP` presupus poate da altă valoare, de comparat) | 0,355 %/min (21 %/h) |

Verificare de bun-simț: 5 h de mers pe plat consumă ≈ 58%, deci o ieșire de 5 h se încheie cu ~40% O₂, peste rezerva de 30%. Constantele actuale din `budget.py` (`O2_PCT_PER_MIN_REST = 0.12`, `O2_PCT_PER_MIN_PER_WATT = 0.0006`) erau deja foarte aproape (0,125 și 0,000711): acum au și sursă.

## 5. Lumina zilei

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Algoritmul | Mars24 (Allison & McEwen 2000) | A | NASA GISS |
| Declinația solară | asin(0,42565 sin Ls) + 0,25° sin Ls | A | Mars24 |
| Ora marțiană | 3698,98 s (1/24 dintr-un sol) | A | Mars24 |
| Apusul efectiv mai devreme cu praful | 30 min pe unitate de tau peste 0,5 | **C** | presupunere (`daylight.effective_sunset_min`) |

---

## Ce se schimbă în repo, pe roluri

| Rol | Schimbare | Unde | Cine aprobă |
|---|---|---|---|
| 2 | Constantele din `budget.py` → valorile din §4.2; `SUIT_FACTOR` 0,6 cu justificarea din §4.1 | `core/budget.py` | rolul 2 |
| 2 | Registrul unic `core/params.py` (mai jos) | `core/` | rolul 2 |
| 2 | `SIGMA_V` calibrat pe variabilitatea vântului (R2-11) | `core/hazards.py` | rolul 2 |
| 1 | ✅ **Făcut (rolul 1):** `dose_rate_usv_h` 10 → 28; ciclul zilnic ±11%; furtuna solară × 2,5 cu creștere de ore și scădere pe 48 h (NASA/JPL: peste două zile) | `live/scenario.py` | rolul 1 |
| 1 | ✅ **Făcut (rolul 1):** vânt Weibull, temperatură și presiune după §1, tau 0,5 | `live/scenario.py` | rolul 1 |
| 1 | ✅ **Făcut (rolul 1):** scena demo: vârtej mare (REROUTE, min 30) + front de furtună (întoarcere imediată, min 80) + regională (RETURN, min 125); verificată cu motorul și alternativele reale | `DEMO_SCENARIO_EVENTS`, `JEZERO_DEMO_EVENTS` | rolul 1 + echipa |
| 3 | ✅ **Făcut (rolul 1, cu acordul echipei):** `dose_rate_multiplier` implicit 2,5, luat din scenariu | `live/engine.py` | rolul 3 |
| toți | `max_slope_deg` 25 → 20 (încă de decis); ✅ exemplul SPE din contract 20 → 2,5 (făcut de rolul 1) | `meta.json`, `Limits`, `live_messages.json` (înghețate) | **echipa** |

## Registrul de parametri propus: `backend/app/core/params.py`

Un singur loc pentru toate constantele fizice și fiziologice, importat de `budget`, `costmap`, `hazards` (rolul 2) și, doar pentru citire, de `scenario.py` (rolul 1) și `engine.py` (rolul 3), ca simularea și planificarea să folosească **aceleași** cifre.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Param:
    value: float
    unit: str
    level: str      # "A" măsurat | "B" derivat | "C" presupunere
    source: str     # citare scurtă + link

G_MARS        = Param(3.71,     "m/s^2",  "A", "constantă fizică")
P_REST_W      = Param(176.0,    "W",      "A", "600 BTU/h, activitate ușoară în costum [S31]")
M_TOTAL_KG    = Param(196.0,    "kg",     "B", "media 583-927 N pe Marte / 3,71 [S34]")
C_LEVEL       = Param(0.59,     "J/(kg·m)","B", "calibrat: 272 W la 3 km/h, media Apollo [S28]")
ETA_UP        = Param(0.22,     "-",      "C", "presupunere: eficiență musculară tipică 0,2-0,25; de validat pe [S32]")
O2_TANK_L     = Param(418.0,    "L",      "B", "8 h la 1000 BTU/h [S31], 4,825 kcal/L [S33]")
O2_KCAL_PER_L = Param(4.825,    "kcal/L", "A", "RQ 0,82 [S33]")
SUIT_FACTOR   = Param(0.6,      "-",      "B", "plat 3,0 km/h, între Apollo 2,2 și nominal 3,5 km/h [S22][S24]")
DOSE_GCR_USVH = Param(28.0,     "µSv/h",  "A", "0,67 mSv/zi, RAD [S11]")
SPE_MULT      = Param(2.5,      "-",      "A", "× 2-3, SPE septembrie 2017 [S14]")
DD_PEAK_LTST  = Param(12.5,     "h",      "A", "vârf 12-13 LTST [S16]")
MAX_WALK_SLOPE= Param(20.0,     "deg",    "A", "concept NASA xEVA [S26]")
```

Din el se poate genera automat tabelul din `docs/how-we-calculate.md` (rolul 1): o singură sursă de adevăr, fără cifre copiate de mână.

---

## Surse

- [S1] Rodriguez-Manfredi et al. (2023), *The diverse meteorology of Jezero crater over the first 250 sols of Perseverance on Mars*, Nature Geoscience — https://doi.org/10.1038/s41561-022-01084-0
- [S2] NASA NSSDC, *Mars Fact Sheet* (durata zilei solare 24,6597 h) — https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html
- [S3] NASA Mars 2020, jurnalul misiunii: *Daily Records of Atmospheric Temperature With Perseverance* — https://mars.nasa.gov/mars2020/mission/status/472/daily-records-of-atmospheric-temperature-with-perseverance/
- [S4] Munguira et al. (2023), *Near Surface Atmospheric Temperatures at Jezero From Mars 2020 MEDA Measurements*, JGR Planets — https://doi.org/10.1029/2022JE007559
- [S5] NASA/JPL (2021), *NASA's First Weather Report From Jezero Crater on Mars* — https://www.jpl.nasa.gov/news/nasas-first-weather-report-from-jezero-crater-on-mars/
- [S6] Sánchez-Lavega et al. (2023), *Mars 2020 Perseverance Rover Studies of the Martian Atmosphere Over Jezero From Pressure Measurements*, JGR Planets — https://doi.org/10.1029/2022JE007480 · text complet în NASA NTRS 20230001083: https://ntrs.nasa.gov/citations/20230001083
- [S7] Viúdez-Moreiras et al. (2022), *Winds at the Mars 2020 Landing Site. 2. Wind Variability and Turbulence*, JGR Planets — text complet în NASA NTRS 20230001086: https://ntrs.nasa.gov/citations/20230001086
- [S8] Lemmon et al. (2022), *Dust, Sand, and Winds Within an Active Martian Storm in Jezero Crater*, GRL — https://doi.org/10.1029/2022GL100126 · înregistrarea NASA NTRS: https://ntrs.nasa.gov/citations/25241411458763 (sursa inițială, Savijärvi et al., era un PDF neoficial care nu mai răspunde)
- [S9] Sánchez-Lavega et al. (2025), *Martian Atmospheric Disturbances From Orbital Images and Surface Pressure at Jezero Crater, Mars, During Martian Year 36*, JGR Planets — https://doi.org/10.1029/2024JE008565
- [S10] Munguira et al. (2023), *Seasonal evolution of near surface atmospheric temperatures at Jezero as measured by the MEDA instrument*, EGU23-5885 — https://doi.org/10.5194/egusphere-egu23-5885
- [S11] NASA (9 dec. 2013), *NASA Rover Results Include First Age Measurement on Mars and Help for Human Exploration* („0.67 millisieverts per day from August 2012 to June 2013”) — https://www.nasa.gov/news-release/nasa-rover-results-include-first-age-measurement-on-mars-and-help-for-human-exploration/ · comunicatul SwRI: https://www.swri.org/newsroom/press-releases/swri-scientists-publish-first-radiation-measurements-the-surface-of-mars
- [S12] Hassler et al. (2014), *Mars' Surface Radiation Environment Measured with the Mars Science Laboratory's Curiosity Rover*, Science — https://doi.org/10.1126/science.1244797 · NASA NTRS 20180007641: https://ntrs.nasa.gov/citations/20180007641
- [S13] Guo et al. (2021), *Radiation environment for future human exploration on the surface of Mars: the current understanding based on MSL/RAD dose measurements*, Astron. Astrophys. Rev. — https://doi.org/10.1007/s00159-021-00136-5
- [S14] Zeitlin et al. (2018), *Analysis of the Radiation Hazard Observed by RAD on the Surface of Mars During the September 2017 Solar Particle Event*, GRL — https://doi.org/10.1029/2018GL077760
- [S15] NASA/JPL (2017), *Large Solar Storm Sparks Global Aurora and Doubles Radiation Levels on the Martian Surface* — https://www.jpl.nasa.gov/news/large-solar-storm-sparks-global-aurora-and-doubles-radiation-levels-on-the-martian-surface/
- [S16] Toledo et al. (2023), *Dust Devil Frequency of Occurrence and Radiative Effects at Jezero Crater, Mars, as Measured by MEDA Radiation and Dust Sensor*, JGR Planets — https://doi.org/10.1029/2022JE007494
- [S17] Hueso et al. (2023), *Convective Vortices and Dust Devils Detected and Characterized by Mars 2020*, JGR Planets — https://doi.org/10.1029/2022JE007516
- [S18] Sánchez-Lavega et al. (2022), *Cellular patterns and dry convection in textured dust storms at the edge of Mars North Polar Cap*, Icarus — https://doi.org/10.1016/j.icarus.2022.115183
- [S19] Sánchez-Lavega et al., *Dynamical Phenomena in Martian dust storms*, EPSC2021-251 — https://doi.org/10.5194/epsc2021-251
- [S20] ESA (15 nov. 2022), *Martian dust storms churn up Earth-like clouds* (Mars Express + NASA MARCI; celule de 20-40 km) — https://www.esa.int/Science_Exploration/Space_Science/Mars_Express/Martian_dust_storms_churn_up_Earth-like_clouds
- [S21] NASA JPL, *NASA Mars Orbiter Tracks Back-to-Back Regional Storms* — https://www.jpl.nasa.gov/news/nasa-mars-orbiter-tracks-back-to-back-regional-storms/
- [S22] NASA, ICES-2025-129, *A Consolidated Tool for Planning and Analyzing Simulated Exploration Traverses and Associated Metabolic Workload* (modelul vitezei Apollo, ecuația 2, din traversele Apollo 12 și 14; Tobler pentru Pământ, ecuația 1) — NASA NTRS 20250001829: https://ntrs.nasa.gov/citations/20250001829
- [S23] Los Alamos National Laboratory, LA-UR-89-3858 (OSTI, U.S. DOE), mobilitatea astronauților Apollo (citit în PDF) — https://www.osti.gov/servlets/purl/7168757
- [S24] NASA ICES-2026, *Mars Mass* (studiul 10 km Walkback) — https://ntrs.nasa.gov/api/citations/20260005410/downloads/Mars_Mass_ICES2026_Presentation_Final.pdf
- [S25] Bellcomm TR-69-340-4 (1969), costuri de traversare lunară — https://ntrs.nasa.gov/api/citations/19700009560/downloads/19700009560.pdf
- [S26] NASA, *EVA Lunar Surface Concept of Operations* — https://www.nasa.gov/wp-content/uploads/2020/01/topic_1-_eva_lunar_surface_concept_of_operations.pdf
- [S27] Vos et al. (2007), *The Walkback Test: A Study to Evaluate Suit and Life Support System Performance Requirements for a 10 km Lunar Traverse* (NASA JSC, ICES 2007) — NASA NTRS 20070016007: https://ntrs.nasa.gov/citations/20070016007 · https://doi.org/10.4271/2007-01-3133
- [S28] NASA NTRS 19910001262 (rate metabolice EVA) — https://ntrs.nasa.gov/api/citations/19910001262/downloads/19910001262.pdf
- [S29] Waligora et al. (1975), NASA TN D-7883, *Apollo Experience Report: Assessment of Metabolic Expenditures* (citit în PDF, Tabelul I) — NASA NTRS 19750010199: https://ntrs.nasa.gov/citations/19750010199
- [S30] NASA, *Apollo Portable Life Support System Performance Report* (rucsacul Apollo, PLSS) — https://ntrs.nasa.gov/api/citations/19720019460/downloads/19720019460.pdf
- [S31] *Carbon Monoxide Levels in the Extravehicular Mobility Unit by Modeling and Operational Testing*, Aerospace Medicine and Human Performance 90(2):84-91 (2019) — https://doi.org/10.3357/AMHP.5220.2019
- [S32] NASA NTRS 20220009964, cerințe fizice în teste EVA — https://ntrs.nasa.gov/citations/20220009964
- [S33] DTIC ADA386372 (U.S. DoD), echivalentul caloric al O₂ — https://apps.dtic.mil/sti/pdfs/ADA386372.pdf
- [S34] = [S24], tabelul greutăților echivalente pe Marte
