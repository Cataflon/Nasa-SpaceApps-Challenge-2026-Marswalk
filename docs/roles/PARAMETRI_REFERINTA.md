# Marswalk Copilot — registrul parametrilor de referință

Toate valorile pe care le folosește simularea (generatorul de scenarii, harta de cost, bugetul, pericolele, validatorul), fiecare cu sursa ei și cu un nivel de încredere. Scopul: orice cifră care apare pe ecran sau în prezentare să poată fi urmărită până la o măsurătoare NASA sau la o presupunere declarată.

Căutat și verificat pe 14 noiembrie 2026. Linkurile sunt la final, numerotate [S1]…[S20].

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
| Durata solului | 24 h 39,5 min | A | [S2] |
| Temperatura aerului, ciclu zilnic tipic | −83 °C înainte de răsărit → −23 °C la prânz | A | [S3] |
| Temperatura solului, ciclu zilnic tipic | −83 °C → +5 °C | A | [S3] |
| Temperatura medie a aerului | ≈ −55 °C; diferență zi-noapte 50-60 °C | A | [S2] |
| Variația sezonieră a temperaturii aerului | foarte mică | A | [S4] |
| Presiunea, prima zi de măsurători (Ls ≈ 5°) | ≈ 718 Pa | A | [S5] |
| Ciclul zilnic al presiunii | maxim la 7-8 h LMST, minim între 12 și 16 h LMST | A | [S6] |
| Vântul | mai calm în medie decât la alte situri; rafale turbulente de la calm la 10-15 m/s în secunde-minute | A | [S7] |
| Distribuția vitezei vântului | Weibull (parametrii se ajustează pe datele MEDA descărcate) | A (forma) / B (parametrii) | [S7] |
| Opacitatea prafului (tau), sezon liniștit | ≈ 0,5 | A | [S8] |
| Prima furtună regională deasupra Jezero | Ls ≈ 153-156° | A | [S9] |

**Recomandare pentru `scenario.py`:**
- temperatura: sinusoidă zilnică între −83 și −23 °C, cu maximul la prânz, plus zgomot de ±2,5 K (amplitudinea fluctuațiilor de la prânz) [S10];
- presiunea: medie ≈ 720 Pa + componenta de maree termică (maxim dimineața, minim după-amiaza), amplitudine de calibrat pe MEDA;
- vântul: eșantionat dintr-o distribuție Weibull ajustată pe MEDA, nu o sinusoidă. Turbulența e cea care dă vârfurile [S7];
- tau: 0,5 ca valoare de bază; crește doar la evenimentele de praf.

## 2. Radiația (stratul `radiation`, scenariul, validatorul)

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Doza echivalentă GCR la suprafață (Gale, 2012-2013) | **0,67 mSv/zi ≈ 28 µSv/h** | A | [S11] |
| Doza absorbită GCR la suprafață | 0,210 ± 0,040 mGy/zi ≈ 8,75 µGy/h | A | [S12] |
| Variația zi-noapte a dozei absorbite | între 180 și 225 µGy/zi (ciclul presiunii) | A | [S12] |
| Variația pe ciclul solar | GCR la suprafață a crescut cu ~50% de la maxim la minim solar | A | [S13] |
| Furtuna solară (SPE) din septembrie 2017, cea mai mare văzută de RAD | doza **× 2-3** față de fond, creștere pe parcursul câtorva ore | A | [S14] |
| Evoluția după vârf | scădere lentă pe ~36 h | A | [S15] |

> ⚠️ **Două corecturi față de repo:**
> 1. `scenario.BASELINE["dose_rate_usv_h"] = 10.0` e, de fapt, ordinul de mărime al dozei **absorbite** (µGy/h), etichetat ca doză **echivalentă** (µSv/h). Valoarea corectă pentru µSv/h e **≈ 28**.
> 2. Exemplul din `shared/contracts/live_messages.json` are `"dose_rate_multiplier": 20` pentru furtuna solară. Cea mai mare furtună solară măsurată la suprafața lui Marte a dat **× 2-3** [S14]. Valoarea implicită realistă: **2,5**.

Observații:
- Gale e la −4,4 km față de nivelul de referință MOLA; Jezero e mai sus, deci cu ceva mai puțină atmosferă deasupra și o doză puțin mai mare. Diferența e mică; o declarăm ca nivel B.
- Cu 28 µSv/h, o ieșire de 8 ore primește ≈ 0,22 mSv; chiar cu o furtună solară × 3 tot timpul, ≈ 0,7 mSv. Limita din validator (`max_dose_msv = 1.0`) aproape că nu va fi atinsă niciodată. Asta e **realist**: pe suprafață, radiația contează prin acumulare pe toată misiunea, nu pe o singură ieșire. În prezentare o spunem așa, nu o ascundem.

## 3. Pericolele (modelul de pericol, rolul 2; generatorul, rolul 1)

### 3.1 Vârtejurile de praf (dust devils) — pericolul care se poate ocoli

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Frecvența de formare la Jezero | 1,3-3,4 / km² / sol (crește din primăvară spre vară) | A | [S16] |
| Frecvența, altă estimare | 2,0-3,0 / km² / sol | A | [S17] |
| Diametrul | mediu 20-29 m, median 25 m, între 5 și 135 m | A | [S16], [S17] |
| Vârtejuri > 100 m | ≈ 0,1 / km² / sol | A | [S17] |
| Ora de vârf | 12:00-13:00 timp solar local adevărat | A | [S16] |
| Direcția de deplasare | aceeași cu vântul de fond | A | [S16] |
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
| Celule convective în furtuni | 20-40 km (până la 135 × 60 km) | A | [S18], [S19] |
| Vânt măsurat în celulele furtunilor | 20-45 m/s | A | [S19] |
| Viteza de deplasare a unei furtuni urmărite de pe orbită | ≈ 70 km/h | A | [S20] |
| Furtună regională | de mărimea Statelor Unite sau mai mare | A | [S21] |
| Avertizare | furtunile regionale se văd de pe orbită (MARCI) zilnic, cu zile înainte | A | [S21] |

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
| Viteza Apollo pe teren plat | ≈ 2,2 km/h (A7L, Lună) | A | [S22] |
| Progres Apollo 15 | 1 → 1,5 → 2 km/h, cu antrenamentul de pe suprafață | A | [S23] |
| Viteza nominală maximă considerată pentru Apollo | 2,2 mph ≈ 3,5 km/h | A | [S24] |
| Pragul VO₂max pe Marte, test cu costum | atins la 3,5 mph ≈ 5,6 km/h | A | [S24] |
| Viteza nominală de mers folosită în planificarea NASA a traverselor | 4 km/h | A | [S25] |
| **Recomandat: viteza pe plat** | **3,0 km/h** = Tobler pe plat (5,04 km/h) × `SUIT_FACTOR` 0,6 | B | între datele Apollo și limita nominală |
| Panta maximă de mers (concept NASA pentru ieșirile de pe Lună) | **20°** | A | [S26] |
| Panta maximă traversată de Apollo 15 | ~17° | A | [S26] |
| Distanța maximă de la habitat, întoarcere pe jos | 10 km (presupunerea NASA, din experiența Apollo) | A | [S27] |

> ⚠️ **Corectură:** `max_slope_deg = 25` (în `meta.json` și în `Limits`) depășește limita de 20° din conceptul NASA de operațiuni [S26]. **Recomandat: 20°.** Ambele locuri sunt înghețate, deci schimbarea se cere echipei. Până atunci, `SLOPE_K` face ca pantele de 20-25° să fie oricum foarte scumpe.

Raza zonei noastre (3-5 km de habitat) e confortabil sub limita de 10 km [S27]: o validare bună pentru slide.

### 4.2 Metabolismul și oxigenul

| Parametru | Valoare | Nivel | Sursă |
|---|---|---|---|
| Rata metabolică medie pe ieșirile Apollo | 234 kcal/h ≈ 272 W ≈ 930 BTU/h | A | [S28] |
| Intervalul pe ieșirile Apollo | 780-1200 BTU/h | A | [S29] |
| Rata de proiectare a rucsacului Apollo (PLSS) | 1200 BTU/h, pentru 4 h | A | [S30] |
| Activitate ușoară în costum | 600 BTU/h ≈ 176 W | A | [S31] |
| Parametri standard pentru simularea unei ieșiri | 8 h la 1000 BTU/h | A | [S31] |
| Urcare 500 m pe pantă de 30% (16,7°), test la sol | 1656-1747 BTU/h (≈ 500 W) | A | [S32] |
| Ratele Apollo pe Lună față de testele la sol | până la 50% mai mici | A | [S32] |
| Echivalentul energetic al O₂ (coeficient respirator 0,82) | 4,825 kcal / litru O₂ | A | [S33] |
| Masa astronaut + costum, greutatea pe Marte | 583-927 N → **157-250 kg**, media ≈ 196 kg | B | [S34] |

**Modelul recomandat (calibrat pe două puncte măsurate):**

```
P = P_REST + M_TOTAL × (C_LEVEL × v + G_MARS × max(0, v_vertical) / ETA_UP)
```

| Constantă | Valoare | Nivel | De unde |
|---|---|---|---|
| `P_REST` | 176 W (600 BTU/h) | A | [S31] |
| `M_TOTAL` | 196 kg | B (de verificat) | media greutăților „Mars equivalent, cu om” din [S24] (583-927 N împărțite la 3,71); tabelul din sursă nu spune explicit dacă e masă sau greutate, deci confirmați înainte de prezentare |
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
| 1 | ✅ **Făcut (rolul 1):** `dose_rate_usv_h` 10 → 28; ciclul zilnic ±11%; furtuna solară × 2,5 cu creștere de ore și scădere pe 36 h | `live/scenario.py` | rolul 1 |
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

- [S1] Rodriguez-Manfredi et al. (2023), *The diverse meteorology of Jezero crater over the first 250 sols of Perseverance on Mars*, Nature Geoscience — https://link.springer.com/article/10.1038/s41561-022-01084-0
- [S2] EurekAlert / UPV-EHU (2023), *The rich meteorology of Mars studied in detail from the Perseverance rover* — https://www.eurekalert.org/news-releases/977001
- [S3] Munguira (2023), *Daily records of atmospheric temperature with Perseverance* — https://www.marsdaily.com/reports/Daily_records_of_atmospheric_temperature_with_Perseverance_999.html
- [S4] Munguira et al. (2023), *Near Surface Atmospheric Temperatures at Jezero From Mars 2020 MEDA Measurements*, JGR Planets — https://eld.bl.uk/catalog/100183927930_0x000001
- [S5] NASA / Fox News (2021), primul raport meteo MEDA — https://www.foxnews.com/science/nasa-gets-first-weather-report-from-mars-rover-landing-site
- [S6] Sánchez-Lavega et al., presiunea la Jezero, JGR Planets (preprint) — https://arxiv.org/pdf/2401.12931.pdf
- [S7] Viúdez-Moreiras et al. (2022), *Winds at the Mars 2020 Landing Site. 2. Wind Variability and Turbulence* — https://ntrs.nasa.gov/api/citations/20230001086/downloads/Guzewich.winds.STI.pdf
- [S8] Savijärvi et al., Jezero (tau ≈ 0,5 la Ls 308°) — https://dydaktyka.fizyka.umk.pl/Karwasz/FiChA/Biblio/Jezero_Mars.pdf
- [S9] Hernández-Bernal / Sánchez-Lavega et al. (2025), perturbații atmosferice la Jezero, MY36 — https://arxiv.org/pdf/2501.05337
- [S10] Munguira et al., EGU23 — https://presentations.copernicus.org/EGU23/EGU23-5885_presentation.pdf
- [S11] Hassler et al. (2014), Science; comunicat — https://phys.org/news/2013-12-scientists-publish-surface-mars.amp
- [S12] Hassler et al. (2014), *Mars' Surface Radiation Environment Measured with the MSL Curiosity Rover* — https://typeset.io/pdf/mars-surface-radiation-environment-measured-with-the-mars-244eildtx0.pdf
- [S13] Guo et al. (2021), review MSL/RAD, Astron. Astrophys. Rev. — https://springerlink.bibliotecabuap.elogim.com/content/pdf/10.1007/s00159-021-00136-5.pdf
- [S14] Zeitlin et al. (2018), *Analysis of the Radiation Hazard Observed by RAD … September 2017 SPE*, GRL — https://eld.bl.uk/catalog/100084451995_0x000001
- [S15] Zeitlin et al. (2018), rezumat — https://www.bexus.org/et/people/forstner/publication/zeitlin-2018
- [S16] Toledo et al. (2023), *Dust Devil Frequency of Occurrence and Radiative Effects at Jezero Crater*, JGR Planets — https://digital.inta.es:8443/jspui/bitstream/20.500.12666/868/1/
- [S17] Hueso et al. (2023), *Convective Vortices and Dust Devils Detected and Characterized by Mars 2020*, JGR Planets — https://searchworks.jioinstitute.edu.in/articles/edb__162055620
- [S18] Sánchez-Lavega et al., furtuni texturate (VMC/HRSC/MARCI) — https://core.ac.uk/download/483448177.pdf
- [S19] Sánchez-Lavega et al., EPSC2021-251 — https://meetingorganizer.copernicus.org/EPSC2021/EPSC2021-251.html
- [S20] ESA Mars Express / phys.org (2022) — https://phys.org/news/2022-11-martian-storms-churn-earth-like-clouds.pdf
- [S21] NASA JPL, *NASA Mars Orbiter Tracks Back-to-Back Regional Storms* — https://www.jpl.nasa.gov/news/nasa-mars-orbiter-tracks-back-to-back-regional-storms/
- [S22] Physics World, mersul pe Lună (date Apollo) — https://physicsworld.com/?p=100152
- [S23] OSTI, mobilitatea astronauților Apollo — https://www.osti.gov/servlets/purl/7168757
- [S24] NASA ICES-2026, *Mars Mass* (studiul 10 km Walkback) — https://ntrs.nasa.gov/api/citations/20260005410/downloads/Mars_Mass_ICES2026_Presentation_Final.pdf
- [S25] Bellcomm TR-69-340-4 (1969), costuri de traversare lunară — https://ntrs.nasa.gov/api/citations/19700009560/downloads/19700009560.pdf
- [S26] NASA, *EVA Lunar Surface Concept of Operations* — https://www.nasa.gov/wp-content/uploads/2020/01/topic_1-_eva_lunar_surface_concept_of_operations.pdf
- [S27] *The Walkback Test* (NASA JSC, ICES 2007) — https://core.ac.uk/works/15254764
- [S28] NASA NTRS 19910001262 (rate metabolice EVA) — https://ntrs.nasa.gov/api/citations/19910001262/downloads/19910001262.pdf
- [S29] NASA TN D-7883, evaluarea metabolică Apollo — https://www.nasa.gov/wp-content/uploads/static/history/alsj/tnD7883Metabolic.pdf
- [S30] NASA, rucsacul Apollo (PLSS) — https://ntrs.nasa.gov/api/citations/19720019460/downloads/19720019460.pdf
- [S31] Aerospace Medicine and Human Performance 90(2), parametri de simulare EVA — https://meridian-asma-published.prime-prod-local.pubfactory.com/downloadpdf/view/journals/amhp/90/2/article-p84.pdf
- [S32] NASA NTRS 20220009964, cerințe fizice în teste EVA — https://ntrs.nasa.gov/citations/20220009964
- [S33] DTIC ADA386372, echivalentul caloric al O₂ — https://apps.dtic.mil/sti/pdfs/ADA386372.pdf
- [S34] = [S24], tabelul greutăților echivalente pe Marte
