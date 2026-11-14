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

### Doza = doză echivalentă RAD, 26,7 µSv/h (decizia echipei, 14.11) — înlocuită cu 28 µSv/h, vezi „Registrul aplicat”
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

### Registrul aplicat + reparații în motorul live (14.11, cu acordul oamenilor)
**Scenariul (`scenario.py`), după `PARAMETRI_REFERINTA.md`:**
- doza de fond **28 µSv/h** (0,67 mSv/zi: comunicatul SwRI din 9.12.2013, fraza citită pe pagină), cu ciclu zilnic **±11%** invers cu presiunea (`DOSE_DIURNAL_FRAC`);
- furtuna solară **× 2,5**: crește în 2 h, platou până la 4 h, scade pe 36 h (Zeitlin 2018);
- tau de bază **0,5**; temperatura **−83 → −23 °C**, vârf la 12:30, zgomot ±2,5 K;
- vântul are marginala **Weibull** (k = 2, media 3 m/s dimineața, 6 m/s la 14:00). Rafalele vin din coada distribuției: copulă gaussiană peste zgomotul corelat. Constantele `GUST_*` au dispărut.
- durata trecerii unei furtuni se calculează acum din întinderea elipsei **pe direcția de mers**: un front de 30 × 5 km care înaintează perpendicular trece în ~6 min, nu într-o oră.

**Scena demo nouă** (`DEMO_SCENARIO_EVENTS` pe sintetic, `JEZERO_DEMO_EVENTS` pe Jezero), cu mărimi reale:
- min 30: vârtej mare (130 m, 3 m/s) → **REROUTE**;
- min 80: frontul unei furtuni (30 × 5 km, 15 m/s) peste astronautul de la `clay_delta` → nicio variantă nu-l evită → **EMERGENCY** (întoarcere imediată);
- min 125: furtună regională → **RETURN**.

Verificată rulând motorul cu alternativele reale ale rolului 2: test `test_demo_scene_decisions_on_jezero` (~2 s).

**Motorul live (`engine.py`, al rolului 3; modificări minime):**
1. **Crash** la prima decizie cu alternativele reale: `alternatives.generate` (din `aff051f`) cere ca `remaining_path` să înceapă la poziția curentă, iar motorul trimitea traseul fără ea. Testul existent nu prindea, pentru că înlocuiește `generate` cu o funcție falsă.
2. **Pericol nevăzut în timpul opririi:** `_path_with_eta` verifica poziția doar la sfârșitul opririi. Un front care trecea peste astronaut cât stătea la țintă nu declanșa nicio decizie. Acum fiecare minut al opririi e verificat.
3. **Evenimentele demo nu porneau deloc:** motorul chema `generate(seed, 720, None)`, deci fără evenimente. Acum folosește `demo_events(meta.site_id)`, iar senzorii le includ. Evenimentele injectate intră în scenariu cu `with_event`, deci praful, vântul și doza cresc corect.
4. **Furtuna solară** e luată din scenariu (× 2,5 cu rampă). Multiplicatorul propriu al motorului mai e folosit doar ca fallback fără scenariu.
5. **`HAZARD_DEFAULTS`** (butoanele de injectare fără parametri): vârtej de 130 m la 4 m/s; `local_storm` = front 30 × 5 km la 15 m/s.
6. **Apusul fără plan** se calculează ca în planner (≈ 633 min), nu 420.
7. **Reevaluarea furtunii regionale** după RETURN e sărită: costa ~1,2 s pe tick și ar fi blocat demo-ul la 10 min/s.

**Altele:**
- `test_uses_core_alternatives_when_available`: scos patch-ul inutil pe `from_contract`. Acum trece.
- `MissionSheet.jsx`: fallback `?? 9` → `?? 8`.
- Contractul `live_messages.json`: SPE 20 → 2,5 (240 min); doza la minutul 72 → 25,3 µSv/h (dimineața presiunea e mare, deci doza e mai mică).
- Pipeline: `DOSE_RATE_USV_H = 28` în `make_synthetic_site.py` (**v7**) și în `build_layers.py`. Am regenerat situl sintetic și am reconstruit Jezero: s-au schimbat doar `radiation.npy` și `radiation.png`, elevația are același hash.
- `how-we-calculate.md` și `sources.md` sunt actualizate. Am documentat și `SIGMA_REL` / `HIT_THRESHOLD`, noi la rolul 2.

### 8. `docs/demo.md` și `docs/slides.md` (în engleză)
- **`demo.md`:** demo de 2 minute, secundă cu secundă: ce se apasă și ce se spune. Conține numărul de titlu, click-ul cu sursa, hardware-ul NASA, ceasul „Return by 11:56”, contorul „27 min vs < 0,1 s”, cele trei decizii de la minutele 30, 80 și 125, benchmark-ul și Survival Guide-ul. Mai are o listă de verificare înainte de scenă și un tabel „dacă ceva merge prost”.
- **`slides.md`:** 11 slide-uri, fiecare legat de un criteriu al juriului.
  - Primul slide are numărul de titlu, măsurat pe Jezero (100 de scenarii, seed 42): **copilot 81%, plan fix 51%**. Copilotul a salvat 30 de ieșiri și n-a stricat niciuna. Prețul e știința: 41% din probe față de 100%.
  - Slide-ul Influence: același motor pentru salvamont, într-un tabel Marte ↔ munții noștri.
  - Slide-ul despre limite e onest: 33 de constante cu sursă, 36 de presupuneri, 4 de verificat.
- **README §8** e actualizat cu scena nouă și cifrele reale. Am corectat „5 misiuni” → **4** (MRO, Mars Odyssey, Mars 2020, MSL; MGS și MAVEN apar doar ca context în `sources.md`).

### Răspuns la cererile din notele celorlalte roluri (14.11, doar în `pipeline/` și `data/`)
- **Rolul 4: alinierea reliefului 3D.** Fișier nou **`data/processed/jezero/grid.json`**, generat de `pipeline/grid_alignment.py`. Conține georeferențierea grilei (proj4, geotransform GDAL, formula centrului de celulă, colțurile în lat/lon), datumul elevației (areoid, corecția pe rover −5,76 m, NoData: niciunul) și blocul `to_frontend_terrain` cu transformarea exactă spre `frontend/public/terrain/jezero.json`.
  - **Grilele NU se suprapun celulă cu celulă.** Relieful vostru e în proiecția nativă a mozaicului USGS (echirectangulară, `lat_ts = 0`), al nostru e echirectangular local (`lat_ts = 18,44°`). Centrul e același; rândurile coincid (`their_row ≈ row + 0,39`), dar pe est-vest `their_col ≈ 249,5 + (col − 249,5) / cos 18,44° + 0,1`. Cele 500 de coloane ale noastre acoperă 527 de pixeli la voi, deci la margini diferența ajunge la ~13 pixeli (~260 m).
  - **Măsurat**, cu corelația pantelor: 0,33 dacă tratați grilele ca identice, 0,62 cu transformarea exactă, 0,67 cu un decalaj rezidual de **~40 m spre nord** (diferența dintre mozaicul CTX TRN și DTM-urile noastre HiRISE/CTX; e raportat, nu aplicat). Altitudinile noastre sunt cu **6,75 m mai jos** (mediană; MAD 4,3 m), pentru că sunt calibrate pe cele 306 puncte ale roverului.
  - Pentru suprapuneri (traseu, habitat, ținte, hardware NASA): treceți fiecare celulă `(row, col)` prin formula din `grid.json`.
- **Rolul 2: zgomotul furtunilor cu sursă.** Fișier nou **`data/processed/jezero/wind_stats.json`**, generat de `pipeline/meda_winds.py`. Sursa e [S7] = Viúdez-Moreiras et al. 2022 (NTRS 20230001086), **citit în textul complet**. Conține:
  - Weibull pe intervale orare: dimineața 07-10 h c = 3,02 m/s, k = 2,01 (media 2,68); prânz 10-15 h c = 5,28, k = 2,16 (media 4,67); după-amiază 15-18 h c = 6,80, k = 3,02 (media 6,08); totalul c = 3,57, k = 1,49;
  - **intensitatea turbulenței TI = σv / v: 36 ± 10 % ziua, 22 ± 10 % noaptea**; σv = 1,85 ± 0,57 m/s ziua;
  - la vârtejuri: c crește cu 65 %, vârfurile ajung la 9,2 × vântul de fond.

  Vârtejurile merg cu vântul de fond, deci zgomotul relativ de viteză din `storms.py` (acum 15 %) poate fi TI-ul de zi, cu 36 % ca limită de sus. Articolul nu dă o cifră pentru variabilitatea direcției. Transcrierea e verificată: din (c, k) din Tabelul 1 se reobțin media și percentilele 95/99 % din Tabelul 2 (`pipeline/tests/test_meda_winds.py`).
- **Rolul 2: straturile sunt sigure pentru harta de cost.** Radiația are minimul 27,5 µSv/h (fără 0, fără NaN), niciun strat nu are NaN, iar habitatul și țintele sunt pe celule permise (pantă ≤ 7,4°, sub 20°). Testul `test_layers_safe_for_costmap` păzește asta în CI. Doza (cererea veche cu ≈ 10 → 28) e rezolvată din capitolul 8.

### Vântul din scenariu calibrat pe MEDA (14.11, doar fișierele rolului 1)
- `scenario.py`: `WIND_WEIBULL_BY_LTST` = Tabelul 1 din Viúdez-Moreiras et al. 2022 (c, k pe 7 intervale LTST). Media și k se interpolează liniar între mijloacele intervalelor (`wind_weibull_at`). Au dispărut `WIND_WEIBULL_K`, `WIND_MEAN_MS`, `WIND_DIURNAL_MS` și `WIND_PEAK_LTST_H`. `BASELINE["wind_ms"]` e 5,0 → 2,5 (media MEDA la 08:00).
- Teste noi în `tests/scenario`: mediile pe ore (2,68 / 4,67 / 6,08 m/s) și tabelul identic cu `data/processed/jezero/wind_stats.json`.
- `how-we-calculate.md` (vântul trece pe `source`) și `sources.md` ([S7] e „verified (full text read)”).

### `docs/survival-guide.md` (în engleză, sarcina 6)
- Pentru fișa printabilă a fiecărei ieșiri; rolul 4 îl importă cu `?raw`. Conține:
  - un tabel cu limitele: O₂ ≥ 30% la sosire, înapoi cu 30 min înainte de apus, pantă ≤ 20°, doză ≤ 1 mSv pe ieșire, ajutorul de pe Pământ în ~27 min;
  - „Before you leave” și „Your three numbers” (ora de întoarcere, punctul de neîntoarcere, O₂ la sosire);
  - câte 2-3 reguli la imperativ pentru: vârtej de praf, front de furtună, furtună regională, furtună solară, scurgere în costum, oboseală, cutremur, pierderea legăturii cu habitatul.
- Pragurile **nu sunt inventate**: `pipeline/tests/test_survival_guide.py` le citește din cod (`types.Limits`, `meta.json`, `scenario.py`, `engine.py`) și pică dacă textul nu le mai potrivește.
- Același test verifică formatul pentru mini-renderer-ul rolului 4 (titluri, liste „- ”, bold, tabele; fără liste numerotate, link-uri sau cursive) și lungimea (sub 750 de cuvinte, o pagină A4 de reguli).
- **Pentru rolul 4:** fișierul există; înlocuiți textul placeholder din Survival Guide cu `docs/survival-guide.md?raw`, randat ca `how-we-calculate.md` în `Information.jsx`.

### Registrul echipei cu surse oficiale (14.11, la cererea oamenilor)
- `PARAMETRI_REFERINTA.md`: fiecare sursă [S1]-[S34] trimite acum la DOI-ul oficial (verificat în Crossref) sau la o pagină NASA (NTRS, nasa.gov, jpl.nasa.gov, NSSDC).
  - Scoase: Fox News, MarsDaily, EurekAlert, Physics World, phys.org, typeset.io, proxy-ul universitar `elogim.com`, cataloagele `eld.bl.uk` / `jioinstitute`, `bexus.org`, `core.ac.uk`, preprinturile arXiv (înlocuite cu versiunile publicate) și PDF-ul neoficial Savijärvi (nu mai răspunde).
  - Înlocuitorii NASA: comunicatul NASA din 9.12.2013 (0,67 mSv/zi), JPL 2017 (furtuna solară „dublează” doza), JPL 2021 (primul raport meteo, 718 Pa), Hassler 2014 în NTRS, presiunea MEDA în NTRS (maximum 761 Pa), Walkback Test în NTRS și modelul NASA al vitezei Apollo (NTRS 20250001829: v = 0,75 − 0,01·θ m/s → 2,7 km/h pe plat).
- Valori reale adăugate, marcate cu ✔ (citite în textul complet sau pe pagina NASA): Weibull MEDA pe ore și turbulența, presiunea 718 / 761 Pa, doza 0,67 mSv/zi, dublarea dozei în sept. 2017, viteza Apollo, intervalul metabolic Apollo (TN D-7883). Corecturile deja aplicate (doza, SPE, vântul, panta 20°) sunt marcate ✅.
- **Opacitatea de bază 0,5 rămâne „de verificat”:** sursa ei inițială a dispărut. Am legat-o de Lemmon et al. 2022 (DOI + NTRS), dar nu i-am citit textul complet.
- Aceleași înlocuiri în fișierele mele: `sources.md`, `how-we-calculate.md` (opacitatea trece pe `to verify`) și comentariile din `scenario.py`.

### Imaginile Perseverance de la opriri (sarcina 11)
- `pipeline/fetch_stop_images.py` (rulat o dată, cere internet și Pillow):
  - pentru fiecare țintă ia solul roverului cu waypoint-ul cel mai apropiat (`clay_delta` → sol 647, la 9 m; `carbonate_rim` → sol 843, la 90 m; `olivine_floor` → sol 204, la 4 m);
  - din API-ul public Mars 2020 (`raw_images`) alege determinist un cadru Mastcam-Z stânga, în culoare naturală, privind spre teren (−30° … −1°); dacă nu există, ia Navcam;
  - îl reduce la 960 px, JPEG ≤ 300 KB (81 / 108 / 128 KB).
- Imaginile sunt în `data/processed/jezero/png/stops/<id>.jpg` (intră în git), iar sursa lor în `png/stops/stops.json`. `build_layers.attach_stop_images` completează `targets[].image = "/static/layers/stops/<id>.jpg"` și `targets[].image_source` (imageid, sol, instrument, credit NASA/JPL-Caltech/ASU, link, data). Un build offline le păstrează.
- Verificat: backendul le servește (200, `image/jpeg`); le-am văzut pe toate trei (ondule la baza deltei, blocuri la marginea carbonaților, afloriment în Séítah).
- Teste: `pipeline/tests/test_stop_images.py` (alegerea, legarea, fișierele din git). `sources.md`: rândul imaginilor e „verified”.
- **Pentru rolul 4:** afișați `target.image` la oprire, cu creditul din `target.image_source.credit` („NASA/JPL-Caltech/ASU”).

### Panta maximă = 20° (decizia echipei, 14.11)
- `MAX_SLOPE_DEG = 20` în `make_synthetic_site.py` (**v8**) și în `build_layers.py`. Ambele scriu acum explicit `max_slope_deg: 20` în `meta.json`, peste valoarea din contract.
- Situl sintetic e regenerat, Jezero e reconstruit: habitatul și țintele **nu s-au mutat** (pantă ≤ 7,4°). Terenul interzis pe Jezero e 2,05% (era 0,86%). Doar `meta.json` și `grid.json` (amprenta) s-au schimbat.
- Scena demo dă aceleași trei decizii (testul pe Jezero trece). `how-we-calculate.md`: rândul pantei e 20°, `source` [S26].

## În lucru

## Cereri

- **Pentru rolurile 2 + 3 (panta 20°, AUDIT-011):** datele au acum 20°. Mai trebuie schimbat în fișierele voastre: `backend/app/core/types.py` → `Limits.max_slope_deg = 20.0` (rolul 2) și `shared/contracts/meta.json` + `shared/contracts/site.json` → `"max_slope_deg": 20` (contract comun; mock-ul pe care îl vede frontendul fără sit). După asta, testul `test_max_slope_is_the_same_everywhere` trece și i se poate scoate `xfail`.

- **Pentru rolul 2 (testele de audit, `backend/tests/regression/test_reg_live.py`):** AUDIT-001, AUDIT-002 și AUDIT-036 sunt reparate de rolul 1 în `bf5f062` (capitolul 8, vezi „Registrul aplicat”). Testele lor trec acum și, fiind `xfail(strict=True)`, apar ca FAILED (XPASS). Scoateți marcajul `xfail` de pe `test_engine_real_core_hazard_on_route_produces_decision`, `test_engine_default_schedules_demo_events` și `test_injected_local_storm_raises_sensor_dust`. CI-ul nu e afectat, pentru că nu rulează `tests/regression`.
- **Pentru rolul 4 (AUDIT-026):** cea mai simplă rezolvare e să folosiți `data/processed/jezero/elevation.npy`. E deja în grila backendului (500 × 500, 20 m reali pe teren, HiRISE + CTX, calibrat pe rover). Alternativ, păstrați decupajul vostru și treceți punctele prin formula din `grid.json`.

- **Pentru rolurile 2 + 3 (benchmark în UI):** `GET /api/benchmark` întoarce încă 501, iar `run_benchmark` nu are `headline`. Pe Jezero, `run_benchmark()` durează ~30 s, deci trebuie calculat o dată și ținut în cache, nu la fiecare cerere. Cifrele din slide-uri sunt măsurate pe 14.11; dacă se schimbă algoritmul, trebuie remăsurate.
- **Pentru rolul 2:** cifrele cerute pentru zgomotul din `storms.py` sunt acum în `data/processed/jezero/wind_stats.json` (vezi mai sus). După ce le preluați, `calibrate_sigma_v` dă un `SIGMA_REL` cu sursă.
- **Pentru rolul 4:** folosiți `data/processed/jezero/grid.json` ca să puneți traseul și punctele pe relieful 3D (grilele diferă pe est-vest cu factorul 1 / cos 18,44°).
- **Pentru rolul 2 (de discutat):** furtunile din benchmark (`storms.py`) au propriul model, separat de scenariul demo. Registrul (§3) cere mărimi reale: front de zeci de km, vârtejuri ≤ 135 m. Merită verificat dacă `storms.py` le respectă.
- **Pentru rolul 4:** interfața are încă texte în română (`utils.js`: „Furtună locală”…, butoanele „Trimite”, „Ceas”, „Apus”…). Regula echipei cere engleză pentru tot ce vede juriul.

- **Pentru rolul 2 (performanță, de văzut):** decizia pentru furtuna regională (`alternatives.generate` cu pericol pe toată grila) durează **~1,2 s**. La 10 minute simulate pe secundă, demo-ul are o pauză de ~1 s în acel moment. Celelalte decizii durează 0,1-0,3 s.
- ~~Echipa: `max_slope_deg` 25 → 20~~: **decis 20°**; datele sunt actualizate, restul e cererea de mai sus pentru rolurile 2 + 3.
- ~~Rolul 3: `sensors_at` / `with_event` / `demo_events`~~: **rezolvat** (de rolul 1, cu acordul oamenilor; vezi mai sus).
- ~~Rolul 2: normalizarea radiației~~: **rezolvat de rolul 2**. `static_cost` folosește excesul relativ `(rad − min) / min`, care nu depinde de scară.
- ~~Mock-ul `live_messages.json` cu doza 9,8~~: **rezolvat**. Acum doza la minutul 72 e 25,3 µSv/h.
- ~~Rolurile 2 + 3: test picat `test_uses_core_alternatives_when_available`~~: **rezolvat**.
- ~~Rolul 3: `DEFAULT_SUNSET_MIN = 420`~~: **rezolvat** (apusul se calculează ca în planner).
- ~~Rolul 4: fallback `?? 9` în `MissionSheet.jsx`~~: **rezolvat** (8).
- ~~Oameni: recomandările registrului pentru `scenario.py`~~: **aplicate**.
- **Pentru oameni (de verificat, P2):** legenda culorilor FOM HiRISE (produsele `DTFEC_*`) nu e pe paginile USGS sau UA. Se poate căuta în arhiva PDS `MRO-M-HIRISE-5-DTM-V1.0`. Până atunci, `unsafe` = pantă > 35°.
- **Pentru oameni / rolul 4 (amânat, de reamintit):** `npm install` avertizează că scriptul `postinstall` al `esbuild@0.21.5` nu e aprobat (`npm install-scripts approve esbuild`). Dacă `npm run build` pică, de acolo e.

## Presupuneri
- Scenarii: ieșirea pornește la 08:00 LTST. Ciclul diurn e un cosinus, deci minimul de temperatură e ~00:30, nu chiar înainte de răsărit (pentru o ieșire de zi contează doar partea de zi). Sunt presupuneri: zgomotul (sigma, timpi de corelație), interpolarea liniară între intervalele Weibull MEDA, amortizarea temperaturii de către praf, legarea ciclului dozei de mareea presiunii și amplitudinile evenimentelor. Vârtejul demo e la 08:30, deși vârful lor e la 12-13 LTST: alegere de demo. Cifrele din literatură sunt marcate „de verificat” în cod; le verific la `docs/sources.md`.
- Doza: RAD a măsurat la Gale (~-4,5 km); Jezero e mai sus (~-2,6 km), deci are puțină atmosferă în minus deasupra și probabil o doză puțin mai mare. Folosim valoarea Gale.
- Jezero: coordonatele țintelor sunt aproximative, după traversa Perseverance și harta USGS SIM 3464 (de verificat pe Mars Trek). Tranziția HiRISE -> CTX are 100 m. Radiația e modelul după altitudine (scala 11 km).
- Fetch: HiRISE citit la 4 m (nu 1 m), din motive de timp și volum. Panta „la rezoluție completă” se face deci la 4 m: prinde obstacolele de peste ~8 m, nu bolovanii de 1-2 m.
- Situl sintetic: geometria e inventată (înălțimea frontului ~55-75 m, lățimea între 12 și 172 m). Pe situl real, frontul vine din DTM.
