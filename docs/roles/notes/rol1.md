# Note rolul 1

## Gata

### 1. Situl sintetic v2 (`pipeline/make_synthetic_site.py`)
- **Frontul deltei e mai abrupt:** ~25% din front e perete de netrecut (> 25°), restul sunt rampe. Platoul deltei rămâne accesibil prin rampe. Panta maximă: 44°; celule interzise: 1,4%.
- `HABITAT`, `TARGETS`, numele, fișierele, tipurile și unitățile straturilor sunt **neschimbate**. Toate țintele sunt accesibile din habitat (verificat cu un flood-fill cu 8 vecini).
- `meta.json` are chei noi, **în plus** față de contract (nu s-a scos nimic):
  - `layers.<strat>.data_type` / `analog_of` / `source`: etichetele de proveniență pe fiecare strat;
  - `generator_version` (acum 2) și `fingerprint` (procent interzis, altitudinea medie).
- **Versiunea sitului:** `data/synthetic/` e în `.gitignore`, deci fiecare îl generează local. `python pipeline/make_synthetic_site.py --check` iese cu codul 1 dacă situl de pe disc e vechi. **După fiecare pull, rulați `python pipeline/make_synthetic_site.py`.**
- Teste: `pipeline/tests/test_synthetic.py` (9 teste, ~3 s). Marker-ul `slow` e înregistrat în `pipeline/tests/conftest.py`: testele lente se sar implicit și rulează cu `-m slow`.

### Modificări în afara zonei (cu acordul oamenilor)
- **`scripts/dev.ps1`:** dacă situl activ e cel sintetic, la pornire rulează `make_synthetic_site.py --check` și, dacă situl lipsește sau e vechi, îl regenerează.
- **`backend/app/api/main.py`, `GET /api/site`:** fiecare strat din `layers[]` primește și cheile opționale `data_type`, `mission`, `instrument`, `source`, `analog_of` și `product_id`, doar dacă există în `meta.json` (constanta `LAYER_LABEL_KEYS`). Câmpurile existente sunt neschimbate. **Rolul 4:** le puteți afișa ca etichete pe straturi.

### 2. Generatorul de scenarii (`backend/app/live/scenario.py`)
- `generate(seed, duration_min, events) -> Scenario`: semnătura și dataclass-urile sunt neschimbate. Un scenariu de 300 min se generează în ~18 ms.
- `sensors` are **`duration_min + 1`** dicturi (minutele 0..duration_min **inclusiv**), cu exact cele 5 chei, ca `float` Python (serializabile JSON direct).
- Modelul: ciclu diurn după ora solară locală (ieșirea pornește la 09:00 LTST), zgomot corelat Ornstein-Uhlenbeck și rafale de vânt. Praful scade amplitudinea temperaturii, iar doza scade când crește presiunea.
- Evenimente: `dust_devil` (2-5 min, vânt, praf, presiunea scade câțiva Pa), `local_storm` (fereastră de timp, vezi mai jos), `regional_storm` (rampă de 120 min, apoi rămâne), `solar_particle_event` (`dose_rate_multiplier`, implicit ×20, și `duration_min`, ca în `live_messages.json`). `marsquake`, `suit_leak` și `fatigue` nu schimbă senzorii. Un eveniment necunoscut ridică `ValueError`.
- **Fereastra de timp a furtunii locale:** vârful vine la `t_min + peak_after_min` (implicit 16 min), iar trecerea durează `duration_min`. Dacă lipsește, se calculează din geometrie: 2 × semiaxa mare / viteză (pentru demo: 24 min).
- Evenimentele **nu consumă numere aleatoare**, deci minutele dinaintea unui eveniment rămân identice.
- Funcții noi, pentru rolul 3:
  - `with_event(scenario, ev)`: adaugă un eveniment injectat live, fără salturi în trecut;
  - `sensors_at(scenario, t_min)`: index rotunjit în jos și limitat la interval;
  - `demo_events(site_id)`: evenimentele demo pentru fiecare sit;
  - `SENSOR_LABELS`: misiunea și instrumentul pentru fiecare mărime.
- Teste: `backend/tests/scenario/test_scenario.py`, 26 de teste, 0,2 s.

### Doza = doză echivalentă RAD, 26,7 µSv/h (decizia echipei, 14.11)
- RAD: 0,64 mSv/zi = 26,7 µSv/h (Hassler et al. 2014). Înainte era ~10, adică de fapt doza absorbită în µGy/h, etichetată greșit „µSv”.
- `scenario.DOSE_RATE_USV_H = 26.7`. Situl sintetic e acum **v3**: `radiation.npy` are media ~26,7 µSv/h. **Regenerați situl** (`dev.ps1` o face automat).
- O ieșire de 5 h dă ~0,13 mSv; o furtună solară ×20 timp de 60 min adaugă ~0,5 mSv. Limita de 1 mSv (`types.Limits`) se atinge doar la evenimente solare.

### 3. Căutarea și decuparea din STAC (`pipeline/fetch_stac.py`)
- Centrul: **18,44°N / 77,45°E** (= contractul, practic locul de aterizare Perseverance), cu frontul deltei la ~2-3 km vest.
- Produsele aduse (din GeoSTAC USGS), fiecare etichetat în `data/raw/jezero/manifest.json` cu misiunea, instrumentul, tipul de date, ID-ul produsului, link-ul, licența (CC0), rezoluția și acoperirea:

  | Tip | Colecție | Ce | Acoperire în 10×10 km |
  |---|---|---|---|
  | `hirise_dtm` | `mro_hirise_socet_dtms` | 5 DTM-uri (1 m, citite la 4 m), 4 cu FOM, ortoimagini | **94,4%** împreună |
  | `ctx_dtm` | `mro_ctx_controlled_usgs_dtms` | cele mai bune 3 din 36 DTM-uri (~20 m) + ortoimagini | 100% fiecare |
  | `themis_ir` | `mo_themis_controlled_mosaics` | mozaic IR zi + noapte (100 m) | 100% |

- Citire pe ferestre din COG (HTTP range), fără descărcarea fișierelor întregi: ~69 MB în total, ~3,5 min. `--hirise-step 1` = rezoluție nativă (lent), `--only <tip>` aduce doar un tip, `--dry-run` doar caută.
- **CRS:** produsele sunt echirectangulare cu paralela standard la ecuator, deci la 18,44° un metru est-vest din proiecție = 0,95 m pe teren. Grila noastră folosește `local_proj4()` (echirectangular centrat pe zonă), deci 20 m sunt chiar 20 m. Reproiectarea se face la capitolul 4 (`build_layers.py`).
- Mediu: `.venv-pipeline` (Python 3.14, rasterio 1.5.2 / GDAL 3.12, pystac-client, Pillow); `pipeline/requirements.txt` are acum și Pillow și pytest.
- Teste: `pipeline/tests/test_fetch_stac.py`. Geometria merge și în CI; decuparea pe un GeoTIFF local e sărită fără rasterio; căutarea STAC reală e `slow`.
- Scrierile (GeoTIFF și `manifest.json`) sunt atomice: fișier temporar + `os.replace`, deci o rulare întreruptă sau două rulări paralele nu lasă fișiere pe jumătate.

### 4. Situl real Jezero (`pipeline/build_layers.py` -> `data/processed/jezero/`, intră în git)
- **Pornire:** `MARSWALK_SITE=jezero`. Testat: toată suita backend (120 de teste) trece și pe Jezero; `static_cost` (0,007 s) și `astar` până la toate țintele (< 0,06 s) merg.
- **Proveniență:** elevația vine din CTX (bază, 3 DTM-uri aliniate vertical între ele) plus 5 DTM-uri HiRISE peste el, cu tranziție lină pe 100 m. HiRISE acoperă **94,4%** din celule.
- **Referința verticală: areoid.** HiRISE DTEEC e cu ~22-43 m sub CTX-ul USGS. Am mutat totul pe areoid (mediana ponderată a decalajelor, −33 m), deci elevația medie e −2553 m, ca în valorile publicate pentru fundul craterului.
- **Panta:** calculată la 4 m, apoi agregată la 20 m cu **maximul**. Interzis (> 25°): 0,86% din celule (escarpa deltei, marginile craterelor).
- **`unsafe`** = pantă > 35° la 4 m (0,13%). FOM-ul din STAC e o **vizualizare RGB fără legendă publicată**, deci nu îi interpretez culorile; vezi „Cereri”.
- **Habitat** (229, 264): cel mai plat teren lângă locul de aterizare Perseverance (pantă ≤ 4° pe 140 m în jur). 99,1% din sit e accesibil din habitat.
- **Ținte** (aceleași `id`-uri ca pe situl sintetic, deci frontendul și demo-ul nu se schimbă):
  - `clay_delta` (211, 115): baza frontului deltei, ~3 km vest de habitat;
  - `olivine_floor` (273, 213): Séítah, ~1,4 km sud-vest;
  - `carbonate_rim` (57, 47): ~5,5 km nord-vest, deci **intenționat departe**: CP-SAT trebuie să aleagă („renunțăm la carbonat, păstrăm argila”).
  - Fiecare are în plus `lat`/`lon`, `note` și `source`.
- `meta.json` are în plus `crs`, `provenance` (ID-urile produselor, decalajele verticale, referința verticală, acoperirea HiRISE, licența CC0) și `fingerprint`. Fiecare strat are `data_type`, `mission`, `instrument`, `source` și `product_id`.
- `png/elevation.png` = ortoimaginea HiRISE/CTX umbrită cu relieful: fundalul hărții e imaginea reală.
- **Provizoriu până la capitolul 5:** `terrain` e dedus din pantă, iar `minerals` e 0 peste tot (etichetate `source: assumption`).
- **Determinism:** două rulări dau fișiere identice bit cu bit. Build-ul durează ~6 s (după `fetch_stac.py`).
- **Demo Jezero:** `scenario.demo_events("jezero")`. Furtuna locală pornește la 3 km sud de traseul habitat -> `clay_delta` și urcă spre nord cu 2,5 m/s, tăind traseul în ~18 min.
- Teste: `pipeline/tests/test_build_layers.py`, 18 teste. Situl generat e validat și în CI: contract, etichete, valori plauzibile, habitat plat, ținte accesibile.

### După merge-ul cu engleza (regula echipei: tot ce vede utilizatorul sau juriul e în engleză)
- Situl sintetic e **v4** (doar textele: numele țintelor și ale sitului, etichetele straturilor). `dev.ps1` îl regenerează automat; manual: `python pipeline/make_synthetic_site.py`.
- Jezero: numele sitului și al țintelor, `note`, `source` și etichetele straturilor sunt în engleză. Straturile `.npy` sunt neschimbate.
- `scenario.py`: mesajele `ValueError` (care pot ajunge în `detail` la API) sunt în engleză.

### Hardware NASA și datele roverului Perseverance (14.11)
- **Sursa:** `M20_waypoints.json`, datele hărții oficiale [Perseverance location map](https://science.nasa.gov/mission/mars-2020-perseverance/location-map/). Conține 708 poziții localizate (solurile 13-2022), dintre care 306 în pătratul nostru, cu altitudinea față de areoid. Se descarcă cu `fetch_stac.py` (sau `--only waypoints`) în `data/raw/jezero/m20_waypoints.json`.
- **Calibrare verticală pe adevărul de la sol:** DTM-ul era cu +5,8 m peste altitudinile măsurate de rover; după corecție, abaterea medie rămasă e de 5,2 m pe 306 puncte (`provenance.rover_vertical_check`).
- **Țintele Jezero = locurile unde a lucrat roverul** (mediana pozițiilor din campanie):
  - `clay_delta`: solurile 500-599, baza frontului deltei;
  - `olivine_floor`: solurile 200-299, Séítah;
  - `carbonate_rim`: solurile 800-899, unitatea de margine.
  - `source` spune solurile.
- **`artifacts`** (în `meta.json`, contracte și `/api/site`): POI-uri statice, **nu** intră în rutare.
  - **Verificate din datele roverului:** `three_forks_depot` (solurile 652-686, roverul staționat cât a lăsat tuburile; la ~200 m de `clay_delta`) și `landing_site` (solul 13).
  - **„to verify”** (aproximative, din textul primit): `descent_stage` (cerc 150 m), `backshell_parachute` (100 m), `heat_shield`, `ingenuity_final`.
  - Pe situl sintetic, aceleași ID-uri, puse analog (`status: synthetic`, sit **v5**).
- **`rover_traverse`**: traseul real al roverului în celule (doar pe Jezero; `null` pe situl sintetic).
- **Modificări în afara zonei (cu acordul oamenilor):**
  - `shared/contracts/meta.json` și `site.json`: `artifacts` + `rover_traverse`;
  - `backend/app/api/main.py`: `/api/site` le trimite cu `meta.get`;
  - test nou `backend/tests/api/test_site_artifacts.py`;
  - casete 🆕🆕 în `README.md`, `ROL3`, `ROL4` și `shared/contracts/README.md`.
- `.npy`-urile Jezero se scriu acum atomic (problema de concurență din capitolul 4).

### 5. Terenul și mineralele Jezero (`build_layers.py`, `pipeline/manual_units.py`)
- **`terrain`** din THEMIS IR de noapte (proxy pentru inerția termică, mozaicul `mc13_syrtis_major_nir`) + rugozitatea HiRISE (panta la 4 m minus panta la 20 m):
  - 0 rocă = cele mai luminoase 25% sau pantă > 20°;
  - 2 nisip = cele mai întunecate 25% pe pante < 12°;
  - 3 bolovani = rugozitate > 12°;
  - 1 regolit = restul.
  - Rezultat: rocă 19,7%, regolit 67,1%, nisip 12,5% (concentrat în sud-vest, unde sunt dunele), bolovani 0,7%. Pragurile sunt presupuneri.
- **`minerals`** (planul B, fără CRISM în STAC) din unități **ancorate pe date reale** (`manual_units.py`):
  - argile = platoul deltei extras din DTM (> 50 m peste fundul craterului) + 250 m în jurul campaniei roverului la frontul deltei (solurile 400-699);
  - olivină = 400 m în jurul Séítah (solurile 200-340);
  - carbonați = 500 m în jurul unității de margine (solurile 750-899).
  - Fiecare țintă stă pe mineralul ei. Contururile sunt aproximative (`source: assumption`), iar unitățile apar în `meta.layers.minerals.units`.
- `how-we-calculate.md`: rânduri noi pentru elevație, pantă, `unsafe`, teren, minerale și pozițiile țintelor și artefactelor (în engleză, cu status).
- Teste: 4 noi + validarea pe Jezero (clase valide, proporții plauzibile, mineralul fiecărei ținte).

### Corecții după capitolul 5
- **Ingenuity:** din jurnalul oficial de zbor (`m20_heli_waypoints.json`, descărcat acum de `fetch_stac.py`), epava (zborul 72, **Airfield Chi**, nu „Sigma”) e la 18,4973°N / 77,3225°E, adică **~2 km în afara hărții**. Pe hartă e acum `ingenuity_first_flight` (Wright Brothers Field, zborul 1, **verificat**), iar nota spune unde e epava. Situl sintetic e **v6**; contractele sunt actualizate.
- **Delta (argile):** pragul a crescut de la 50 la 90 m peste fundul craterului; doar corpul principal al deltei din NV (14,7% din sit), fără terenul înalt din SV.
- **Séítah:** buffer de 700 m în loc de 400 (1,9% din sit).
- **Sky crane, parașuta și scutul termic** rămân „to verify”: paginile JPL cu pozițiile întorc 404.

### 6. `docs/sources.md` (în engleză)
- Toate sursele din README §3, plus tot ce folosim efectiv: STAC, HiRISE, CTX, THEMIS, waypoint-urile roverului și ale Ingenuity, 12 articole și harta SIM 3464.
- **Link-urile au fost deschise automat** (HTTP 200). **DOI-urile au fost verificate în Crossref** (autor, an, titlu, revistă).
- Citarea Zeitlin 2018 avea DOI greșit; e corectat în `scenario.py`: 10.1029/2018GL077760.
- Nu se deschid din rețeaua noastră: PDS Atmospheres (eroare de certificat TLS) și NASA NTRS (timeout). Sunt marcate „to verify”.
- Totaluri oneste: 7 tipuri de date, 4 misiuni folosite efectiv (MRO, Mars Odyssey, Mars 2020, MSL); MGS și MAVEN doar context.
- Test nou `pipeline/tests/test_sources.py`: fiecare DOI din cod, fiecare URL de date și fiecare colecție STAC folosită trebuie să apară în `sources.md`, cu status.

### Consumul de O₂: sursă NASA verificată din PDF (14.11)
- **NASA TN D-7883** (Waligora et al. 1975, *Apollo Experience Report: Assessment of Metabolic Expenditures*, NTRS 19750010199), Table I, p. 8-9: **822-1267 kJ/h = 228-352 W (780-1200 BTU/h)** pe 158,8 h de ieșiri pe Lună. E `[S29]` din registrul echipei, acum citit direct din PDF.
- PDF-urile NTRS sunt în `data/raw/refs/` (ignorat de git). Textul e extras cu `pypdf` în `.venv-pipeline`.
- Modelul de O₂ din `budget.py` (rolul 2, registrul §4.2) rămâne valabil: 176 W în repaus → 0,125 %/min, 272 W pe plat → 0,194 %/min. Valorile se încadrează în intervalul Apollo.

### 7. `docs/how-we-calculate.md` (în engleză): fiecare constantă
- 8 secțiuni, ~65 de rânduri: mers și costum, O₂, limite și verdict, lumina zilei, harta de cost și decizia, pericole, scenarii, hartă. Fiecare rând are valoarea **exact ca în cod**, numele constantei, sursa (`[S#]` din `PARAMETRI_REFERINTA.md`) și statusul `source` / `to verify` / `assumption`.
- **Test nou `pipeline/tests/test_how_we_calculate.py`:** citește toate constantele din `core/{budget,costmap,decision,hazards,daylight,planner}.py` și `live/engine.py`. Pică dacă una nu e documentată (cu excepția celor pur tehnice, listate în `IGNORED`). Verifică și că fiecare rând are un badge valid.
- **Ora de start aliniată:** `scenario.EVA_START_LTST_H` 9,0 → **8,0** = `planner.SOL_START_UTC` (Mars24-ul rolului 2 dă 07:59 LTST). Testul `test_eva_start_matches_planner` o ține sincronă.
- **Întârzierea Pământ-Marte la data demo-ului (14.11.2026):** 1,319 UA → **11,0 min** într-un sens. Ajutorul de la Houston = 2 × 11 + 5 min reacție = **27 min**. Calculul e în `scenario.earth_mars_light_min()` (elementele kepleriene JPL/Standish), verificat pe opoziția din ianuarie 2025 și conjuncția din noiembrie 2023.
- **`/api/site`** (cu acordul oamenilor) trimite acum `eva_start_ltst_h` și `earth_delay_min` (`one_way`, `round_trip`, `source`), deci ceasul de întoarcere și contorul din frontend au datele reale. Test în `tests/api/test_site_artifacts.py`.

## În lucru

## Cereri

- **Pentru rolul 3 (motorul live):**
  - Citiți senzorii cu `scenario.sensors_at(s, t_min)`, nu cu `s.sensors[int(t)]`: indexul e limitat la interval, deci nu apare `IndexError` după `duration_min`.
  - Pentru `POST /api/live/event`, înlocuiți scenariul cu `scenario.with_event(s, ScheduledEvent(t_min, event, params))`. Minutele trecute rămân identice.
  - Pentru demo, folosiți `scenario.demo_events(SITE_ID)` în loc de `DEMO_SCENARIO_EVENTS`, ca pe situl Jezero furtuna să fie pusă corect.
  - Valorile din `_allowed_events` care nu sunt la senzori (`suit_leak`, `fatigue`, `marsquake`) le aplicați voi pe O₂, viteză și zone blocate.

- ~~Rolul 2: normalizarea radiației~~: **rezolvat de rolul 2**. `static_cost` folosește excesul relativ `(rad − min) / min`, care nu depinde de scară.
- ~~Mock-ul `live_messages.json` cu doza 9,8~~: **rezolvat** (cu acordul oamenilor). Acum `dose_rate_usv_h: 26.5` și `dose_total_msv: 0.032` (72 min × 26,7 µSv/h).
- **Pentru rolurile 2 + 3 (test picat, nu de la rolul 1):** `tests/live/test_engine.py::test_uses_core_alternatives_when_available` pică pe `main` de la commit-ul `a67c375`, pentru că `hazards.predict` primește un `dict` în loc de `Hazard` (`AttributeError: 't0_min'`). Verificat pe o copie curată a HEAD.
- **Pentru rolul 3:** `engine.DEFAULT_SUNSET_MIN = 420`, dar apusul planificat la data demo-ului e ≈ 633 min (planner). E doar fallback, dar dacă motorul pornește fără plan, ceasul de întoarcere ar fi cu ~3,5 h mai devreme.
- **Pentru rolul 4:** `MissionSheet.jsx` are fallback `eva_start_ltst_h ?? 9`. Valoarea reală e 8 și vine acum din `/api/site`; schimbați fallback-ul la 8.
- **Pentru oameni (de decis):** registrul `PARAMETRI_REFERINTA.md` recomandă pentru `scenario.py` mai multe schimbări care nu sunt încă făcute:
  - furtuna solară × 2,5 (nu × 20), cu creștere pe ore și scădere pe 36 h;
  - tau de bază 0,5 (nu 0,6);
  - vânt Weibull;
  - doza 28 µSv/h (0,67 mSv/zi; eu am 26,7, din 0,64 în rezumatul Hassler 2014);
  - scena demo cu vârtej mare + front de furtună.
  
  Le pot face; schimbă comportamentul demo-ului.
- **Pentru rolul 3 (motorul live pe Jezero):** folosiți `scenario.demo_events(SITE_ID)`. Furtuna pe Jezero e calibrată pe traseul habitat (229, 264) -> `clay_delta` (211, 115). Dacă planner-ul alege alt traseu, ajustați `center` în `JEZERO_DEMO_EVENTS` sau spuneți-mi.
- **Pentru oameni (de verificat, P2):** legenda culorilor FOM HiRISE (produsele `DTFEC_*`) nu e pe paginile USGS sau UA. Se poate căuta în arhiva PDS `MRO-M-HIRISE-5-DTM-V1.0`. Până atunci, `unsafe` = pantă > 35°.
- **Pentru oameni / rolul 4 (amânat, de reamintit):** `npm install` avertizează că scriptul `postinstall` al `esbuild@0.21.5` nu e aprobat (`npm install-scripts approve esbuild`). Dacă `npm run build` pică, de acolo e.

## Presupuneri
- Scenarii: ieșirea pornește la 09:00 LTST. Ciclul diurn e un cosinus, deci minimul de temperatură e ~01:30, nu chiar înainte de răsărit (pentru o ieșire de zi contează doar partea de zi). Sunt presupuneri: zgomotul (sigma, timpi de corelație), rafalele, amortizarea temperaturii de către praf, legătura doză-presiune și amplitudinile evenimentelor. Cifrele din literatură sunt marcate „de verificat” în cod; le verific la `docs/sources.md`.
- Doza: RAD a măsurat la Gale (~-4,5 km); Jezero e mai sus (~-2,6 km), deci are puțină atmosferă în minus deasupra și probabil o doză puțin mai mare. Folosim valoarea Gale.
- Jezero: coordonatele țintelor sunt aproximative, după traversa Perseverance și harta USGS SIM 3464 (de verificat pe Mars Trek). Tranziția HiRISE -> CTX are 100 m. Radiația e modelul după altitudine (scala 11 km).
- Fetch: HiRISE citit la 4 m (nu 1 m), din motive de timp și volum. Panta „la rezoluție completă” se face deci la 4 m: prinde obstacolele de peste ~8 m, nu bolovanii de 1-2 m.
- Situl sintetic: geometria e inventată (înălțimea frontului ~55-75 m, lățimea între 12 și 172 m). Pe situl real, frontul vine din DTM.
