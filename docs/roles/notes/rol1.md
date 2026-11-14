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

## În lucru

## Cereri

- **Pentru rolul 3 (motorul live):**
  - Citiți senzorii cu `scenario.sensors_at(s, t_min)`, nu cu `s.sensors[int(t)]`: indexul e limitat la interval, deci nu apare `IndexError` după `duration_min`.
  - Pentru `POST /api/live/event`, înlocuiți scenariul cu `scenario.with_event(s, ScheduledEvent(t_min, event, params))`. Minutele trecute rămân identice.
  - Pentru demo, folosiți `scenario.demo_events(SITE_ID)` în loc de `DEMO_SCENARIO_EVENTS`, ca pe situl Jezero furtuna să fie pusă corect.
  - Valorile din `_allowed_events` care nu sunt la senzori (`suit_leak`, `fatigue`, `marsquake`) le aplicați voi pe O₂, viteză și zone blocate.

- ~~Rolul 2: normalizarea radiației~~: **rezolvat de rolul 2**. `static_cost` folosește excesul relativ `(rad − min) / min`, care nu depinde de scară.
- ~~Mock-ul `live_messages.json` cu doza 9,8~~: **rezolvat** (cu acordul oamenilor). Acum `dose_rate_usv_h: 26.5` și `dose_total_msv: 0.032` (72 min × 26,7 µSv/h).
- **Pentru rolul 3 (motorul live pe Jezero):** folosiți `scenario.demo_events(SITE_ID)`. Furtuna pe Jezero e calibrată pe traseul habitat (229, 264) -> `clay_delta` (211, 115). Dacă planner-ul alege alt traseu, ajustați `center` în `JEZERO_DEMO_EVENTS` sau spuneți-mi.
- **Pentru oameni (de verificat, P2):** legenda culorilor FOM HiRISE (produsele `DTFEC_*`) nu e pe paginile USGS sau UA. Se poate căuta în arhiva PDS `MRO-M-HIRISE-5-DTM-V1.0`. Până atunci, `unsafe` = pantă > 35°.
- **Pentru oameni / rolul 4 (amânat, de reamintit):** `npm install` avertizează că scriptul `postinstall` al `esbuild@0.21.5` nu e aprobat (`npm install-scripts approve esbuild`). Dacă `npm run build` pică, de acolo e.

## Presupuneri
- Scenarii: ieșirea pornește la 09:00 LTST. Ciclul diurn e un cosinus, deci minimul de temperatură e ~01:30, nu chiar înainte de răsărit (pentru o ieșire de zi contează doar partea de zi). Sunt presupuneri: zgomotul (sigma, timpi de corelație), rafalele, amortizarea temperaturii de către praf, legătura doză-presiune și amplitudinile evenimentelor. Cifrele din literatură sunt marcate „de verificat” în cod; le verific la `docs/sources.md`.
- Doza: RAD a măsurat la Gale (~-4,5 km); Jezero e mai sus (~-2,6 km), deci are puțină atmosferă în minus deasupra și probabil o doză puțin mai mare. Folosim valoarea Gale.
- Jezero: coordonatele țintelor sunt aproximative, după traversa Perseverance și harta USGS SIM 3464 (de verificat pe Mars Trek). Tranziția HiRISE -> CTX are 100 m. Radiația e modelul după altitudine (scala 11 km).
- Fetch: HiRISE citit la 4 m (nu 1 m), din motive de timp și volum. Panta „la rezoluție completă” se face deci la 4 m: prinde obstacolele de peste ~8 m, nu bolovanii de 1-2 m.
- Situl sintetic: geometria e inventată (înălțimea frontului ~55-75 m, lățimea între 12 și 172 m). Pe situl real, frontul vine din DTM.
