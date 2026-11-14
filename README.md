# Marswalk Copilot

> **Harta îți spune pe unde să mergi. Copilotul îți spune când să schimbi drumul și dacă te mai poți întoarce.**

NASA Space Apps Challenge 2026: ideea, planul complet și sursele de date.

## Pornire rapidă

Cerințe: Python 3.11+, Node 18+, opțional [Ollama](https://ollama.com) cu `qwen2.5:7b-instruct`. Pe Windows, din rădăcina repo-ului:

```powershell
scripts\setup.ps1   # .venv, dependențe, npm, sit sintetic
scripts\dev.ps1     # backend :8000 + frontend :5173
```

Manual:

```bash
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt
.venv/Scripts/python pipeline/make_synthetic_site.py
cd backend && ../.venv/Scripts/python -m uvicorn app.api.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

Teste: `cd backend && ../.venv/Scripts/python -m pytest`.

**Starea scheletului:** rutele încă neimplementate întorc mock-urile din `shared/contracts/` (antet `X-Mock: 1`), iar WebSocket-ul live redă `live_messages.json`. Funcțiile de făcut au `TODO (rolul N)` și `NotImplementedError`. Deja funcționale: situl sintetic, încărcarea sitului, validatorul, regula de decizie, șabloanele și clientul LLM cu fallback.

---

## 🆕 Noutăți (14.11.2026): 7 adăugări ieftine, cu impact mare

> **Fiecare rol citește aici ce are nou de implementat.** Detaliile sunt și în fișierul rolului (`docs/roles/ROLn_*.md`), în caseta „🆕 NOU” de la început.

Challenge-ul se numește chiar **„Interplanetary Survival Guide”**. Adăugările de mai jos leagă proiectul direct de temă, folosind date pe care le avem deja.

| # | Ce | De ce | Rol 1 (date) | Rol 2 (algoritmi) | Rol 3 (backend) | Rol 4 (frontend) |
|---|---|---|---|---|---|---|
| 1 | **Survival Guide printabil**, mutat din bonus în **prioritate (P1)**: o fișă de o pagină per ieșire cu traseul, ora-limită de întoarcere, punctul de neîntoarcere și ce faci la furtună locală / regională / solară | Cea mai bună potrivire cu tema, pentru câteva ore de lucru | Textul regulilor: `docs/survival-guide.md` | — (datele există deja în `plan_route`) | — | Pagina printabilă (CSS de print) |
| 2 | **Contorul „Pământul vs. copilotul”**: „ajutorul de la Houston ar ajunge în 14 min · copilotul a decis în 0,05 s” | O idee pe care juriul o reține imediat | Întârzierea Pământ-Marte, cu sursă: `scenario.EARTH_ONE_WAY_DELAY_MIN` | — | `compute_ms` în mesajul `decision` + întârzierea în `/api/site` | Contorul în panoul copilotului |
| 3 | **Ceasul de întoarcere ca cifră principală**: „Te întorci până la 14:20” | E prima informație pe care o vrea un astronaut | Ora de start a ieșirii (LTST): `scenario.EVA_START_LTST_H` | `return_by_min` corect în buget | `eva_start_ltst_h` în `/api/site` | Cifra mare, mereu vizibilă |
| 4 | **Click pe orice punct de pe hartă**, cu valorile din fiecare misiune și sursa lor: „pantă 12° · HiRISE · MRO” | Face vizibile cele „5 misiuni” și întărește partea de hartă | `mission` / `instrument` / `product_id` pe fiecare strat din `meta.json` | — | `sources` în `GET /api/point` | Popup la click |
| 5 | **Un singur număr de titlu din benchmark**: „Copilotul a adus astronautul acasă în siguranță în X% din furtuni; planul fix, în Y%” | Pe primul slide și în video | Pe slide și în video | `headline` în `run_benchmark` | `headline` în `GET /api/benchmark` | Afișat în UI |
| 6 | **Ecranul „Cum calculăm”**, cu fiecare constantă marcată **sursă** sau **presupunere** | Onestitatea despre limite crește încrederea (Validity) | `docs/how-we-calculate.md` complet, mutat la **P1** | Toate constantele la nivel de modul, cu comentariul `sursă:` sau `presupunere` | — | Badge-uri pe coloana „Status” |
| 7 | **Un slide despre Pământ (Influence):** același motor, cu un model de teren din munții noștri, pentru salvamont | Doar pe slide, **nu în cod** | `docs/slides.md` | — | — | — |

**Câmpuri noi în contracte, toate opționale** (se adaugă cu acordul echipei; până atunci frontendul are fallback):
- `site.json`: `eva_start_ltst_h` (ex. `9.0`), `earth_delay_min` (`{"one_way": 14, "round_trip": 28, "source": "…"}`), iar în `layers[]` etichetele `mission`, `instrument`, `data_type`, `source` (deja trimise de `/api/site`).
- `GET /api/point`: `sources` (`{"slope": {"mission": "MRO", "instrument": "HiRISE", "data_type": "topographic"}, …}`).
- `live_messages.json`, mesajul `decision`: `compute_ms` (cât a durat decizia; se măsoară doar pentru afișare, nu intră în logică).
- `GET /api/benchmark`: `headline` (`{"copilot_safe_pct": X, "plan_safe_pct": Y, "n_scenarios": 100}`).

---

## 1. Ideea

### Problema

Primii astronauți pe Marte vor ieși din habitat pe jos, cu oxigen limitat, fără GPS și cu ajutor de pe Pământ care vine cu 4-24 de minute întârziere. În timpul ieșirii, condițiile se pot schimba: o furtună de praf, o rafală de radiație, oboseală sau o problemă la costum. Astronautul trebuie să decidă singur și repede: continuă, ocolește, așteaptă sau se întoarce?

Unelte precum Mars Trek arată datele ca straturi pe o hartă globală, dar challenge-ul spune explicit că nu sunt făcute pentru zona mică a unei singure ieșiri și nu iau decizii.

### Soluția

Marswalk Copilot are două părți:

1. **O hartă hiperlocală** (10×10 km în jurul deltei Jezero) construită din date din mai multe misiuni NASA: relief, imagine, minerale, termic, radiație, vreme.
2. **Un copilot** care urmărește ieșirea în timp real. La fiecare pas citește senzorii, prezice unde va fi pericolul, generează trasee alternative, elimină variantele nesigure și alege determinist varianta sigură cu riscul cel mai mic. Un LLM local explică decizia pe limba astronautului.

### Principii

- **Cifrele vin din cod, nu din LLM.** Distanța, O₂-ul, timpul și riscul se calculează determinist.
- **Codul decide, LLM-ul explică.** Regula alege varianta, iar LLM-ul primește situația și decizia deja luată și scrie motivul. LLM-ul nu se află pe calea critică.
- **Validatorul are ultimul cuvânt.** Nicio variantă nesigură nu ajunge la astronaut.
- **Sistemul merge și fără LLM.** Dacă Ollama nu răspunde, decizia rămâne aceeași și explicația vine dintr-un șablon.
- **Fiecare etapă e un demo complet.**

---

## 2. Zona de lucru

- **Locul:** frontul deltei din craterul Jezero (centrul craterului ≈ 18,4°N, 77,5°E). E bine documentat, are DTM HiRISE și ținte științifice clare (argile, carbonați, probele Perseverance).
- **Perimetrul:** ~10×10 km, adică raza unei ieșiri realiste pe jos (3-5 km de la habitat).
- **Grila pentru algoritmi:** 20 m, deci 500×500 = 250.000 de celule. E suficient de rapid pentru replanificare live.
- **Afișarea:** imagini de 0,25-1 m, separat de grila de calcul.
- **Combinarea datelor:** CTX (~20 m) acoperă tot pătratul, iar HiRISE (1 m) fâșia principală peste deltă, cu prioritate acolo unde există.

---

## 3. Sursele de date

### A. Date NASA statice (straturile hărții)

| Strat | Misiune / instrument | Tip de date | De unde | Rol în aplicație |
|---|---|---|---|---|
| Relief de detaliu + imagine | MRO HiRISE DTM (1 m) + ortoimagini (0,25 m), hillshade, FOM | topografic, optic | [USGS STAC](https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms) | Pantă, obstacole, fundalul hărții; FOM maschează zonele nesigure |
| Relief de context | MRO CTX DTM (~20 m) | topografic | [AWS Open Data](https://registry.opendata.aws/nasa-usgs-controlled-mro-ctx-dtms/) (CC0) | Acoperirea completă a zonei de 10×10 km |
| Catalog și API | — | — | [STAC docs](https://stac.astrogeology.usgs.gov/docs/data/) | Căutare după coordonate, citire de COG fără descărcarea fișierelor întregi |
| Relief global | MGS MOLA | topografic | [NASA Mars Trek](https://trek.nasa.gov/mars/) | Doar contextul și alegerea locului |
| Minerale | MRO CRISM | spectral | [PDS Geosciences / ODE](https://ode.rsl.wustl.edu/mars/) | Ținte științifice (argile, carbonați) |
| Rocă și nisip | Mars Odyssey THEMIS (inerție termică) | termic | [THEMIS](https://themis.mars.asu.edu/) și Mars Trek | Costul de mers pe tipuri de teren |
| Geologie | Harta geologică Jezero, USGS SIM 3464 | geologic | [doi:10.3133/sim3464](https://doi.org/10.3133/sim3464) | Contextul științific al opririlor |
| Imagini de la sol | Perseverance (Mastcam-Z, Navcam) | optic | [Raw images](https://mars.nasa.gov/mars2020/multimedia/raw-images/) | „Ce vei vedea" la fiecare oprire |

### B. Date NASA pentru calibrarea simulării

| Variabilă | Misiune / instrument | De unde | Folosit pentru |
|---|---|---|---|
| Praf (opacitate tau), vânt, temperatură, presiune | Perseverance MEDA, Curiosity REMS | [PDS Atmospheres Node](https://atmos.nmsu.edu/) | Valori realiste în seriile simulate |
| Furtuni de praf (mărime, frecvență, deplasare) | MRO MARCI, MCS | [Rapoarte meteo MARCI](https://www.msss.com/msss_images/latest_weather.html) | Modelul furtunii |
| Doză de radiație, evenimente solare | Curiosity RAD, MAVEN | [PDS PPI Node](https://pds-ppi.igpp.ucla.edu/) | Stratul de radiație și evenimentul „furtună solară" |
| Lumina zilei | Algoritmul Mars24 (NASA GISS) | [Mars24](https://www.giss.nasa.gov/tools/mars24/) | Răsărit, apus, fereastra de lucru |

### C. Surse pentru formule

| Ce | Sursă |
|---|---|
| Consum metabolic și de O₂ în costum | Rapoarte [NASA NTRS](https://ntrs.nasa.gov/) despre ieșirile Apollo și testele de mers în costum |
| Viteza de mers după pantă | Funcția lui Tobler, ajustată pentru gravitația Marte (0,38 g) și costum |
| Praguri de pantă și rezerve | Studii NASA de ieșiri umane (de verificat), altfel declarate ca presupuneri |

### D. Date generate de noi

- **Generatorul de scenarii** (`scenario.py`): serii de timp pentru praf, vânt, temperatură și radiație, plus furtuni care se mișcă. Valorile sunt calibrate pe datele de la punctul B și au seed fix, deci sunt reproductibile.
- **Situl sintetic:** un crater fals, cu deltă și obstacole, ca echipa să poată lucra până sunt gata datele reale.

În prezentare scriem clar: *„scenarii simulate, calibrate pe MEDA, REMS și RAD"*.

**Total:** 6+ tipuri de date (topografic, optic, spectral, termic, atmosferic, radiație) din cel puțin 5 misiuni (MRO, Odyssey, MGS, Perseverance, Curiosity, MAVEN). Challenge-ul cere minimum 3.

> ⚠️ Doar linkurile de la A (STAC și AWS) au fost citite efectiv. Cele de la B și C sunt cunoscute din memorie: verificați-le rapid înainte să intre în prezentare.

---

## 4. Workflow-ul

Pe scurt: **codul decide, LLM-ul explică.** Workflow-ul are 3 faze.

### Faza 1: Pregătirea datelor (offline, o singură dată)

Rulăm `pipeline/` înainte de demo, iar rezultatul se salvează pe disc. De aici, backendul doar citește fișiere, fără internet.

```
STAC (HiRISE + CTX) ──► decupaj 10×10 km ──► pantă ──► grilă 20 m
CRISM, THEMIS, radiație ───────────────────────────────► aceeași grilă
                                                          │
                                         elevation.npy, slope.npy, terrain.npy, …
```

### Faza 2: Planificarea (înainte de ieșire)

Astronautul spune: „Vreau proba de argilă de la deltă, am 5 ore."

1. **A\*** găsește traseul habitat → țintă pe harta de cost.
2. **Dijkstra invers** calculează, o singură dată, costul de întoarcere din orice celulă. De aici iese punctul de neîntoarcere.
3. **Bugetul** calculează pe traseu timpul, O₂-ul, doza și ora apusului.
4. **Validatorul** dă verdictul GO / CAUTION / NO-GO.
5. **LLM-ul** (opțional) explică planul în chat.

### Faza 3: Ieșirea live (inima proiectului)

Un **tick = 1 minut simulat**. La fiecare tick:

```
┌─ 1. SENZORI ── scenario.py dă: poziție, O₂, praf, vânt, radiație
│
├─ 2. PERICOL ── hazards.py: unde e furtuna acum + unde va fi la t+10…t+180
│
├─ 3. VERIFICARE ── traseul rămas intersectează pericolul prezis?
│        │
│        ├── NU ──► CONTINUE (nimic nu se schimbă, majoritatea tick-urilor)
│        │
│        └── DA ──► 4. ALTERNATIVE (ocolire nord, ocolire sud, WAIT, RETURN)
│                       │  calculate cu A* spațiu-timp + Dijkstra invers
│                       ▼
│                   5. VALIDATOR ── elimină ce încalcă O₂ / lumină / pantă / doză
│                       │
│                       ▼
│                   6. REGULA ── alege varianta validă cu riscul cel mai mic
│                       │        (determinist, < 50 ms)
│                       ▼
│                   7. UI (WebSocket) ── decizia apare IMEDIAT pe hartă
│                       │
│                       ▼  (în paralel, nu blochează)
│                   8. LLM ── primește situația + decizia → scrie „de ce"
│                            (2-3 s; dacă pică → text din șablon)
└─ următorul tick
```

**Histerezisul** împiedică traseul să se schimbe din minut în minut: se schimbă doar dacă riscul trece pragul și alternativa e clar mai bună.

### Exemplu concret (scena 4 din demo)

- **Minutul 72:** praful crește, iar senzorii văd o furtună locală la 3 km vest, care se deplasează spre est.
- **Predicția:** furtuna taie traseul în 16 minute.
- **Alternativele:** ocolire nord (+25 min, O₂ final 31%), ocolire sud (+40 min, O₂ final 22%), WAIT, RETURN.
- **Validatorul:** elimină ocolirea sud, pentru că 22% e sub rezerva de 30%.
- **Regula:** alege ocolirea nord, care are cel mai mic risc. Pe hartă, traseul se redesenează instant.
- **LLM-ul**, 2 secunde mai târziu: *„Furtuna ajunge pe traseu în 16 min. Ocolirea nord adaugă 25 min și lasă 31% O₂, peste rezerva de 30%."*

Dacă furtuna e regională, nicio ocolire nu trece validatorul și regula alege RETURN pe ruta din Dijkstra invers.

### Cine face ce

| Componentă | Determinist? | Poate greși decizia? |
|---|---|---|
| A*, Dijkstra, buget | da | nu, sunt doar calcule |
| Validator | da | nu, sunt reguli fixe |
| Regula de alegere | da | nu |
| LLM | aproape | **nu**, doar explică |

---

## 5. Componentele

### 5.1 Pipeline-ul de date (offline, o singură dată)

1. Caută DTM-urile HiRISE și CTX pentru Jezero în API-ul STAC (`pystac-client`).
2. Citește doar fereastra de 10×10 km din COG (`rasterio`).
3. Calculează panta la rezoluția completă.
4. Agregă la grila de 20 m, păstrând panta maximă din fiecare celulă, ca să nu se piardă obstacolele.
5. Adaugă CRISM, THEMIS și radiația, reeșantionate pe aceeași grilă.
6. Salvează `elevation.npy`, `slope.npy`, `terrain.npy`, `minerals.npy`, `radiation.npy`, `meta.json`, plus PNG-urile pentru frontend.

### 5.2 Harta de cost

```
cost = distanță × f(pantă) × f(teren) + w_pericol × pericol(x, y, t) + w_radiatie × doză
```

- Pantă peste limită (de exemplu 25°) sau FOM nesigur înseamnă celulă interzisă.
- Ponderile `w_*` vin din 3 preset-uri fixe: **sigur**, **rapid**, **științific**. Nu le modifică LLM-ul, ca harta de cost să rămână deterministă.

### 5.3 Algoritmii

| Algoritm | Rol |
|---|---|
| A* | Traseul inițial habitat → țintă |
| A* spațiu-timp | Ocolirea unui pericol care se mișcă: o celulă e interzisă doar cât timp pericolul e acolo |
| Dijkstra invers de la habitat | Costul de întoarcere din orice punct: punctul de neîntoarcere și ruta de urgență, instant |
| Generator de alternative | Trasee cu ponderi diferite: rapid, sigur, științific |
| CP-SAT (OR-Tools) | Ce ținte științifice vizitezi și în ce ordine, ca să maximizezi valoarea științifică sub O₂, apus și doză. Costurile între ținte vin din Dijkstra. Rulează la planificare și la re-planificarea live, când bugetul scade („renunțăm la carbonat, păstrăm argila”). Plan B: forță brută la ≤6 opriri |
| Regula de decizie | Alege dintre alternativele validate pe cea cu riscul cel mai mic (filtru + sortare, < 1 ms) |

**CP-SAT determinist:** `num_workers = 1`, `random_seed` fix și limită `max_deterministic_time`, nu `max_time_in_seconds`. Limita în secunde depinde de viteza CPU-ului și poate schimba rezultatul.

### 5.4 Modelul de pericol

- **Furtuna:** o zonă eliptică, cu intensitate mai mare în centru, care se mișcă cu viteză și direcție date.
- **Predicție** la t+10, t+20, … t+180 min, cu raza mărită pe măsură ce crește orizontul (incertitudine).
- **Clasificare:** dust devil (ocolibil), furtună locală (ocolibilă sau adăpost), furtună regională (întoarcere obligatorie).
- **Histerezis:** traseul se schimbă doar dacă riscul trece pragul și alternativa e mai bună cu cel puțin X%.
- **Alte evenimente:** furtună solară (adăpost sau întoarcere), cutremur (zonă blocată), scurgere în costum (consum mai mare), oboseală (viteză mai mică, consum mai mare).

### 5.5 Bugetul

- **Viteza:** Tobler după pantă × factorul de costum × factorul de echipament × oboseala.
- **O₂:** după efortul metabolic pe fiecare segment.
- **Doza de radiație:** integrată pe traseu.
- **Punctul de neîntoarcere:** din Dijkstra invers.
- **Lumina:** apusul efectiv din Mars24, mai devreme dacă e praf.

### 5.6 Validatorul (reguli hard)

- O₂ la sosirea în habitat ≥ rezerva (de exemplu 30%).
- Întoarcere cu ≥ 30 min înainte de apusul efectiv.
- Pantă ≤ limita maximă.
- Doza de radiație ≤ limita pe ieșire.
- Traseul nu trece prin pericol în fereastra prezisă.

### 5.7 LLM-ul (Ollama)

- **Hardware de dezvoltare/demo:** Ryzen 7 7840HS, 24 GB RAM, RTX 4050 cu 6 GB VRAM.
- **Model decizie (live):** `qwen2.5:7b-instruct` (Q4, ~4,7 GB, intră complet în VRAM, rapid). Alternativă de testat: `qwen3:8b` cu thinking oprit. Rezervă: `qwen2.5:3b` sau `llama3.2:3b`.
- **Model chat/explicații (opțional):** un 14B (ex. `qwen2.5:14b`) nu încape în 6 GB și se împarte între GPU și CPU, deci e mai lent (câțiva tokeni/s). Se folosește doar unde latența nu contează, nu pentru decizia live.
- **Setări:** `temperature: 0`, `seed: 42`, format cu schemă JSON, context mic (2-4k) ca să rămână în VRAM.
- **Rol:** doar explică. Decizia e deja luată de regulă și afișată în UI înainte ca LLM-ul să înceapă.
- **Când rulează:** doar la evenimente (pas 8 din Faza 3) și la cererile din chat. Rulează asincron și nu blochează tick-ul.
- **Intrare:** prompt scurt (< 500 de tokeni). Partea fixă (instrucțiunile) stă la început, ca Ollama să o refolosească din cache, iar partea variabilă (situația, alternativele validate, decizia aleasă) la sfârșit.
- **Ieșire** (schemă JSON, ~60 de tokeni):

```json
{"decizie": "REROUTE",
 "alternativa_id": "ocolire_nord",
 "motiv": "Furtuna ajunge pe traseu în 16 min. Ocolirea nord adaugă 25 min și lasă 31% O₂, peste rezerva de 30%."}
```

  `decizie` și `alternativa_id` sunt copiate din decizia regulii (servesc ca verificare de consistență), iar `motiv` are maxim 25 de cuvinte.
- **Viteză:** `keep_alive: -1` și un request de încălzire la pornirea backendului, ca prima explicație să nu plătească încărcarea modelului.
- **Chat cu unelte** pentru planificare: `plan_route`, `oxygen_budget`, `layer_value`, `science_stops`, `daylight`. Puține unelte, cu parametri simpli, pentru că un 7B le apelează nesigur.
- **Fallback:** dacă nu răspunde în ~3 s, JSON-ul e invalid sau `alternativa_id` nu se potrivește cu decizia, se afișează un text din șablon (ex. „Furtună pe traseu în {t} min. Ocolire {nume}: O₂ final {o2}%.").
- **Reproductibilitate:** `temperature: 0` și `seed` reduc variația, dar nu o garantează la bit. De aceea explicațiile se pun în cache după hash-ul stării, iar demo-ul și benchmark-ul se repetă identic.

### 5.8 Backendul (FastAPI, Python 3.11)

| Rută | Rol |
|---|---|
| `GET /api/site` | Zona, limitele, habitatul, țintele, ora de start a ieșirii (`eva_start_ltst_h`), întârzierea Pământ-Marte (`earth_delay_min`) |
| `GET /api/layers` | Straturile (PNG, legendă și etichetele de misiune / instrument) |
| `GET /api/point` | Valorile tuturor straturilor într-un punct + sursa fiecăruia (`sources`: misiune, instrument) |
| `POST /api/route` | Traseu + buget + verdict GO / CAUTION / NO-GO |
| `POST /api/chat` | Chat cu agentul (streaming) |
| `WS /api/live` | Simularea live: tick-uri, evenimente, decizii |
| `POST /api/live/event` | Injectează un eveniment |
| `GET /api/benchmark` | Copilot față de „doar planul", pe aceleași scenarii, plus numărul de titlu (`headline`) |

### 5.9 Frontendul (React + Vite, pornit din machetă)

- **Ceasul de întoarcere, cifra principală de pe ecran:** „Te întorci până la 14:20” (ora locală pe Marte, LTST), mereu vizibil, nu ascuns într-un panou.
- **Harta:** straturi activabile, habitat, astronaut în mișcare, furtuna cu conul de predicție, traseul curent, alternativele colorate, punctul de neîntoarcere.
- **Click pe orice punct:** valorile din fiecare strat cu misiunea și instrumentul lor („pantă 12° · HiRISE · MRO”).
- **Panoul copilotului:** decizia curentă, explicația, chatul și uneltele chemate, plus contorul **„Pământul vs. copilotul”** („ajutorul de la Houston ar ajunge în 14 min · copilotul a decis în 0,05 s”).
- **Bugetul:** O₂, timp, lumină, doză și profilul de altitudine.
- **Controale de simulare:** start/pauză, viteza ceasului, butoane de evenimente.
- **Imagini Perseverance** la opriri.
- **Survival Guide printabil (prioritate, nu bonus):** o pagină per ieșire, cu traseul, ora-limită de întoarcere, punctul de neîntoarcere și ce faci la furtună locală / regională / solară.
- **Numărul de titlu din benchmark:** „acasă în siguranță: copilot X% · plan fix Y%”.
- **Ecranul „Cum calculăm":** formulele, pragurile și sursele; fiecare constantă e marcată **sursă** sau **presupunere**.
- **Bonus:** vedere HUD (ce vede astronautul în cască).

---

## 6. Structura repo-ului (monorepo)

```
marswalk-copilot/
├── pipeline/                  # date offline (rolul 1)
│   ├── fetch_stac.py          # caută și decupează HiRISE + CTX
│   ├── build_layers.py        # pantă, agregare 20 m, CRISM, THEMIS, radiație
│   └── make_synthetic_site.py # crater fals, gata în prima oră
├── backend/
│   ├── app/
│   │   ├── api/               # FastAPI: rute REST + WebSocket (rolul 3)
│   │   │   └── main.py
│   │   ├── core/              # algoritmi puri, fără server (rolul 2)
│   │   │   ├── site_data.py   # încarcă grilele
│   │   │   ├── costmap.py     # fuziunea straturilor + preset-uri de ponderi
│   │   │   ├── routing.py     # A*, A* spațiu-timp, Dijkstra invers
│   │   │   ├── hazards.py     # modelul pericolelor + predicție
│   │   │   ├── budget.py      # viteză, O₂, doză, punct de neîntoarcere
│   │   │   ├── daylight.py    # Mars24
│   │   │   ├── validator.py   # reguli hard
│   │   │   ├── decision.py    # regula de alegere dintre alternative
│   │   │   ├── stops.py       # CP-SAT: alegerea și ordinea opririlor
│   │   │   └── benchmark.py
│   │   ├── live/              # motorul de tick-uri (rolul 3)
│   │   │   ├── engine.py
│   │   │   └── scenario.py    # generatorul de date dinamice
│   │   └── llm/               # Ollama (rolul 3)
│   │       ├── client.py
│   │       ├── prompts.py
│   │       ├── templates.py   # explicații de rezervă
│   │       └── cache.py
│   └── tests/
├── frontend/                  # React + Vite, pornit din machetă (rolul 4)
├── shared/
│   └── contracts/             # exemple JSON pentru API și mesajele WS + mock-uri
├── data/
│   ├── raw/                   # DTM-uri descărcate (în .gitignore)
│   ├── processed/jezero/      # .npy + meta.json (mici, intră în git)
│   └── synthetic/
├── docs/                      # „Cum calculăm", surse, slide-uri
└── scripts/                   # pornire dev, înregistrare demo
```

- **`core/` e separat de `api/`:** algoritmii sunt funcții Python pure, testabile fără server, deci rolul 2 nu așteaptă după backend.
- **`shared/contracts/`** fixează forma JSON-urilor din prima oră, ca frontendul să lucreze pe mock-uri până e gata backendul.
- **În git intră doar grilele procesate.** Un `.npy` de 500×500 are ~1 MB; DTM-urile brute rămân în `data/raw/`, ignorat.

---

## 7. Planul pe două zile

**Reguli:** la sfârșitul zilei 1 merg traseul și bugetul pe date reale. La mijlocul zilei 2 merge reroute-ul live. Tot ce vine după e bonus.

### Ziua 1: fundația

| Interval | Backend | Algoritmi | Date | Frontend |
|---|---|---|---|---|
| H0–H1 | **Toți:** contractele (`meta.json`, semnăturile din `core/`, `shared/contracts/`) | | Situl sintetic | |
| H1–H3 | Repo, FastAPI, `/health`, Ollama instalat + încălzit | A* pe situl sintetic | `fetch_stac.py`: caută HiRISE + CTX pentru Jezero | Portează macheta, date mock |
| H3–H7 | `/site`, `/layers`, `/route` | Dijkstra invers, punctul de neîntoarcere | Decupaj 10×10 km, pantă, agregare la 20 m | Hartă + straturi + traseu |
| H7–H12 | `budget.py`, `daylight.py` | `hazards.py`: furtuna care se mișcă, predicția | CRISM, THEMIS, stratul de radiație | Bugetul, profilul de altitudine |

**Gata la sfârșitul zilei 1:** harta Jezero reală, traseul A*, bugetul și punctul de neîntoarcere.

### Ziua 2: copilotul live

| Interval | Backend | Algoritmi | Date | Frontend |
|---|---|---|---|---|
| H12–H18 | WebSocket `/live` | A* spațiu-timp, alternativele, validatorul | `scenario.py` calibrat pe MEDA, REMS, RAD | Astronaut animat, furtuna, conul, alternativele |
| H18–H24 | `llm/` (explicații) + șabloane, chatul; `compute_ms`, `sources`, `eva_start_ltst_h` | Histerezis, WAIT și RETURN, CP-SAT pentru opriri | Imaginile Perseverance la opriri, `survival-guide.md` | Panoul de decizie, explicația, chatul, contorul Pământ vs. copilot, ceasul de întoarcere |
| H24–H30 | Benchmark + `headline` | Teste pe scenarii, `headline` în benchmark | Ecranul „Cum calculăm” (fiecare constantă: sursă / presupunere), sursele | **Survival Guide printabil**, apoi HUD (bonus) |
| H30–H34 | Stabilizare | Stabilizare | Slide-uri (numărul de titlu, slide-ul salvamont), video demo | Finisaje |
| H34–H36 | Îngheț de cod | | Repetiție demo | |

Ajustați orele după deadline-ul real. Înregistrați video-ul de rezervă cu cel puțin 3-4 ore înainte de termen.

### Rolurile (echipă de 4)

| Rol | Foldere | Ce face | Livrează către |
|---|---|---|---|
| **1. Date & prezentare** | `pipeline/`, `data/`, `docs/` | sit sintetic (prima oră!), STAC, straturi, calibrarea scenariilor, surse, slide-uri, video | `.npy` + `meta.json` → rolul 2 |
| **2. Algoritmi** | `backend/app/core/` | harta de cost, A\*, A\* spațiu-timp, Dijkstra invers, pericole, buget, validator, regula de decizie, CP-SAT, benchmark | funcții Python → rolul 3 |
| **3. Backend & LLM** | `backend/app/api/`, `live/`, `llm/` | FastAPI, WebSocket, motorul de tick-uri, Ollama, prompturi, șabloane, chat cu unelte; integrarea finală | JSON pe REST/WS → rolul 4 |
| **4. Frontend** | `frontend/` | harta, straturile, animația, conul furtunii, panourile, HUD | demo-ul |

- **LLM-ul nu are rol separat:** doar explică, deci e o muncă de 4-6 ore, legată direct de motorul live.
- **Rolul 3 îl ia cine are laptopul cu GPU**, pentru că Ollama rulează acolo și demo-ul pornește de pe el.

Instrucțiunile complete pentru fiecare rol (pentru 4 agenți care lucrează în paralel) sunt în [docs/roles/](docs/roles/README.md).

### Regulile de lucru

1. **Ora 0 (o oră, toți împreună):** stabiliți contractele: formatul grilelor (`meta.json`), semnăturile funcțiilor din `core/` (de exemplu `plan_route(grid, start, goal, preset) -> Route`) și JSON-urile din `shared/contracts/`.
2. **Situl sintetic e gata în prima oră**, ca nimeni să nu aștepte datele reale.
3. **Fiecare om lucrează în folderele lui, pe branch-ul lui, și face merge în `main` des**, de câteva ori pe zi.
4. **Prima integrare cap-coadă se face la finalul zilei 1**, chiar dacă e urâtă.

---

## 8. Demo-ul (≈2 min)

0. Deschidere cu numărul de titlu: „Copilotul a adus astronautul acasă în siguranță în X% din furtuni; planul fix, în Y%” (5 s).
1. Harta Jezero cu straturile: „date din 5 misiuni NASA”. Click pe un punct: „pantă 12° · HiRISE · MRO” (15 s).
2. Planificare: „Vreau o probă de argilă de la deltă, am 5 ore" → traseu, buget, punct de neîntoarcere, imaginea Perseverance de la țintă și ceasul mare „Te întorci până la 14:20” (25 s).
3. Pornim ieșirea, iar astronautul merge pe hartă (10 s).
4. Furtună locală la jumătatea drumului: apare conul de predicție, apar alternativele, validatorul elimină una, regula alege ocolirea instant, iar LLM-ul explică de ce. Contorul: „Houston ar răspunde în 28 min · copilotul a decis în 0,05 s” (35 s).
5. Furtună regională: sistemul decide RETURN, pentru că nu poate fi ocolită; ceasul de întoarcere se actualizează (15 s).
6. Benchmark: copilot față de „doar planul", pe 100 de scenarii (10 s).
7. Închidere: Survival Guide-ul printabil al ieșirii (5 s).

---

## 9. Riscuri și plan B

| Risc | Plan B |
|---|---|
| STAC-ul e lent sau DTM-ul nu se decupează | Doar CTX; dacă nici asta nu merge, situl sintetic + straturile NASA arătate separat |
| CRISM sau THEMIS durează prea mult | Ținte științifice puse manual după harta geologică USGS |
| Ollama e lent sau nu e instalat | Decizia nu e afectată (o ia regula); explicația vine din șablon |
| A* spațiu-timp e prea lent | Orizont mai scurt (30-60 min), grilă de 100 m la replanificare, `numpy`/`numba`, sau zona furtunii „umflată" static |
| Integrarea frontend–backend întârzie | Frontendul rulează pe scenarii înregistrate (mock) |
| Internetul pică la demo | Totul local + video de rezervă |
| Juriul întreabă dacă AI-ul poate greși | AI-ul nu ia decizia: o ia regula, dintre variante validate. LLM-ul doar explică; benchmark-ul rulează fără LLM și e reproductibil |

---

## 10. Cum răspundem criteriilor juriului

| Criteriu | Argument |
|---|---|
| **Influence** | Siguranța primelor ieșiri umane pe Marte; un slide arată același motor, cu un model de teren din munții noștri, pentru salvamont |
| **Creativity** | Replanificare în timp real cu predicția pericolului, nu o hartă statică; contorul „Pământul vs. copilotul” |
| **Validity** | DTM-uri oficiale NASA/USGS, date din 5 misiuni (vizibile la click pe hartă), decizii deterministe, benchmark măsurat, ecranul „Cum calculăm” cu fiecare constantă marcată sursă sau presupunere |
| **Relevance** | Acoperă cerințele: hiperlocal, ≥3 tipuri de date, siguranță, radiație, mobilitate în costum, obiective științifice, imagini de la sol; produce chiar un **Survival Guide** per ieșire |
| **Presentation** | Demo vizual: furtuna se mișcă, traseul se reface, decizia e explicată; un singur număr de titlu din benchmark |
