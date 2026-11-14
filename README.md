# Marswalk Copilot

> **Harta îți spune pe unde să mergi. Copilotul îți spune când să schimbi drumul și dacă te mai poți întoarce.**

NASA Space Apps Challenge 2026: ideea, planul complet și sursele de date.

---

## 1. Ideea

### Problema

Primii astronauți pe Marte vor ieși din habitat pe jos, cu oxigen limitat, fără GPS și cu ajutor de pe Pământ care vine cu 4-24 de minute întârziere. În timpul ieșirii, condițiile se pot schimba: o furtună de praf, o rafală de radiație, oboseală sau o problemă la costum. Astronautul trebuie să decidă singur și repede: continuă, ocolește, așteaptă sau se întoarce?

Unelte precum Mars Trek arată datele ca straturi pe o hartă globală, dar challenge-ul spune explicit că nu sunt făcute pentru zona mică a unei singure ieșiri și nu iau decizii.

### Soluția

Marswalk Copilot are două părți:

1. **O hartă hiperlocală** (10×10 km în jurul deltei Jezero) construită din date din mai multe misiuni NASA: relief, imagine, minerale, termic, radiație, vreme.
2. **Un copilot** care urmărește ieșirea în timp real. La fiecare pas citește senzorii, prezice unde va fi pericolul, generează trasee alternative, elimină variantele nesigure, iar un LLM local alege dintre variantele sigure și explică decizia.

### Principii

- **Cifrele vin din cod, nu din LLM.** Distanța, O₂-ul, timpul și riscul se calculează determinist.
- **LLM-ul alege și explică.** Primește un rezumat compact și alternative deja calculate, apoi răspunde în JSON fix.
- **Validatorul are ultimul cuvânt.** Nicio variantă nesigură nu ajunge la astronaut.
- **Sistemul merge și fără LLM.** Dacă Ollama nu răspunde, o regulă implicită decide.
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

## 4. Arhitectura

```
┌───────────────────────────────────────────────────────────────┐
│ 1. DATE                                                       │
│  statice (NASA): relief, pantă, imagine, minerale, termic,    │
│                  radiație, geologie                           │
│  dinamice (simulate, calibrate pe NASA): praf, vânt, temp.,   │
│                  furtuni, evenimente solare                   │
└──────────────────────────────┬────────────────────────────────┘
                               ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. FUZIUNE: hartă de cost + hartă de pericol cost(x, y, t)    │
└──────────────────────────────┬────────────────────────────────┘
                               ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. MOTOR LIVE (tick = 1 min simulat)                          │
│  senzori → model pericol → predicție → traseul e afectat?     │
│     nu → CONTINUE                                             │
│     da → 4. ALGORITMI: ocolire / așteptare / întoarcere       │
│          → 5. VALIDATOR (O₂, lumină, pantă, radiație)         │
│          → 6. LLM (Ollama): alege + explică [fallback: regulă]│
└──────────────────────────────┬────────────────────────────────┘
                               ▼ WebSocket
┌───────────────────────────────────────────────────────────────┐
│ 7. FRONTEND: hartă cu straturi, astronaut, furtună + con de   │
│ predicție, trasee alternative, buget O₂, decizie, HUD         │
└───────────────────────────────────────────────────────────────┘
```

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
- Ponderile `w_*` pot fi ajustate de LLM.

### 5.3 Algoritmii

| Algoritm | Rol |
|---|---|
| A* | Traseul inițial habitat → țintă |
| A* spațiu-timp | Ocolirea unui pericol care se mișcă: o celulă e interzisă doar cât timp pericolul e acolo |
| Dijkstra invers de la habitat | Costul de întoarcere din orice punct: punctul de neîntoarcere și ruta de urgență, instant |
| Generator de alternative | Trasee cu ponderi diferite: rapid, sigur, științific |
| Ordonarea opririlor | Ordinea țintelor științifice (forță brută la ≤6 opriri) |

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
- **Când rulează:** doar la evenimente și la cererile din chat.
- **Intrare:** rezumatul situației și alternativele deja validate.
- **Ieșire:**

```json
{"decizie": "CONTINUE|REROUTE|WAIT|RETURN|EMERGENCY",
 "alternativa_id": "ocolire_nord",
 "ponderi": {"siguranta": 0.7, "stiinta": 0.3},
 "motiv": "Furtuna ajunge în 16 min; ocolirea lasă 31% O₂..."}
```

- **Chat cu unelte** pentru planificare: `plan_route`, `oxygen_budget`, `layer_value`, `science_stops`, `daylight`.
- **Fallback:** dacă nu răspunde în ~3 s sau JSON-ul e invalid, se alege alternativa validă cu cel mai mic risc.

### 5.8 Backendul (FastAPI, Python 3.11)

| Rută | Rol |
|---|---|
| `GET /api/site` | Zona, limitele, habitatul, țintele |
| `GET /api/layers` | Straturile (PNG și legendă) |
| `GET /api/point` | Valorile tuturor straturilor într-un punct |
| `POST /api/route` | Traseu + buget + verdict GO / CAUTION / NO-GO |
| `POST /api/chat` | Chat cu agentul (streaming) |
| `WS /api/live` | Simularea live: tick-uri, evenimente, decizii |
| `POST /api/live/event` | Injectează un eveniment |
| `GET /api/benchmark` | Copilot față de „doar planul", pe aceleași scenarii |

### 5.9 Frontendul (React + Vite, pornit din machetă)

- **Harta:** straturi activabile, habitat, astronaut în mișcare, furtuna cu conul de predicție, traseul curent, alternativele colorate, punctul de neîntoarcere.
- **Panoul copilotului:** decizia curentă, explicația, chatul și uneltele chemate.
- **Bugetul:** O₂, timp, lumină, doză și profilul de altitudine.
- **Controale de simulare:** start/pauză, viteza ceasului, butoane de evenimente.
- **Imagini Perseverance** la opriri.
- **Bonus:** vedere HUD (ce vede astronautul în cască) și Survival Guide printabil.
- **Ecranul „Cum calculăm":** formulele, pragurile și sursele.

---

## 6. Structura repo-ului

```
marswalk-copilot/
├── backend/app/
│   ├── main.py          # rute API + WebSocket
│   ├── site_data.py     # încarcă grilele
│   ├── costmap.py       # fuziunea straturilor
│   ├── routing.py       # A*, A* spațiu-timp, Dijkstra invers
│   ├── budget.py        # viteză, O₂, doză, punct de neîntoarcere
│   ├── daylight.py      # Mars24
│   ├── hazards.py       # modelul pericolelor + predicție
│   ├── scenario.py      # generatorul de date dinamice
│   ├── live.py          # motorul live
│   ├── validator.py     # reguli hard
│   ├── llm.py           # Ollama + scheme + fallback
│   └── benchmark.py
├── pipeline/
│   ├── fetch_stac.py    # caută și decupează HiRISE + CTX
│   ├── build_layers.py  # pantă, agregare 20 m, CRISM, THEMIS, radiație
│   └── make_synthetic_site.py
├── frontend/            # React, pornit din machetă
├── data/processed/jezero/
└── docs/
```

---

## 7. Planul pe două zile

**Reguli:** la sfârșitul zilei 1 merg traseul și bugetul pe date reale. La mijlocul zilei 2 merge reroute-ul live. Tot ce vine după e bonus.

### Ziua 1: fundația

| Interval | Backend | Algoritmi | Date | Frontend |
|---|---|---|---|---|
| H0–H3 | Repo, FastAPI, `/health`, situl sintetic | A* pe situl sintetic | `fetch_stac.py`: caută HiRISE + CTX pentru Jezero | Portează macheta, date mock |
| H3–H7 | `/site`, `/layers`, `/route` | Dijkstra invers, punctul de neîntoarcere | Decupaj 10×10 km, pantă, agregare la 20 m | Hartă + straturi + traseu |
| H7–H12 | `budget.py`, `daylight.py` | `hazards.py`: furtuna care se mișcă, predicția | CRISM, THEMIS, stratul de radiație | Bugetul, profilul de altitudine |

**Gata la sfârșitul zilei 1:** harta Jezero reală, traseul A*, bugetul și punctul de neîntoarcere.

### Ziua 2: copilotul live

| Interval | Backend | Algoritmi | Date | Frontend |
|---|---|---|---|---|
| H12–H18 | WebSocket `/live` | A* spațiu-timp, alternativele, validatorul | `scenario.py` calibrat pe MEDA, REMS, RAD | Astronaut animat, furtuna, conul, alternativele |
| H18–H24 | `llm.py` + fallback, chatul | Histerezis, WAIT și RETURN | Imaginile Perseverance la opriri | Panoul de decizie, explicația, chatul |
| H24–H30 | Benchmark | Teste pe scenarii | Ecranul „Cum calculăm", sursele | HUD sau Survival Guide (bonus) |
| H30–H34 | Stabilizare | Stabilizare | Slide-uri, video demo | Finisaje |
| H34–H36 | Îngheț de cod | | Repetiție demo | |

Ajustați orele după deadline-ul real. Înregistrați video-ul de rezervă cu cel puțin 3-4 ore înainte de termen.

### Rolurile (pentru 4 oameni)

| Rol | Responsabil de |
|---|---|
| Backend | FastAPI, buget, live, WebSocket, LLM |
| Algoritmi | A*, spațiu-timp, Dijkstra invers, pericole, validator, benchmark |
| Date & prezentare | Pipeline STAC, straturi, scenarii, surse, slide-uri, video |
| Frontend | Hartă, animație, panouri, HUD |

Pentru 2-3 oameni: Backend + Algoritmi devin o persoană, iar Date & prezentare preia și o parte din frontend după ziua 1.

---

## 8. Demo-ul (≈2 min)

1. Harta Jezero cu straturile: „date din 5 misiuni NASA" (15 s).
2. Planificare: „Vreau o probă de argilă de la deltă, am 5 ore" → traseu, buget, punct de neîntoarcere, imaginea Perseverance de la țintă (25 s).
3. Pornim ieșirea, iar astronautul merge pe hartă (10 s).
4. Furtună locală la jumătatea drumului: apare conul de predicție, apar 3 alternative, validatorul elimină una, LLM-ul alege ocolirea și explică (35 s).
5. Furtună regională: sistemul decide RETURN, pentru că nu poate fi ocolită (15 s).
6. Benchmark: copilot față de „doar planul", pe 100 de scenarii (15 s).
7. Închidere: HUD-ul sau Survival Guide-ul (5 s).

---

## 9. Riscuri și plan B

| Risc | Plan B |
|---|---|
| STAC-ul e lent sau DTM-ul nu se decupează | Doar CTX; dacă nici asta nu merge, situl sintetic + straturile NASA arătate separat |
| CRISM sau THEMIS durează prea mult | Ținte științifice puse manual după harta geologică USGS |
| Ollama e lent sau nu e instalat | Fallback pe regulă; LLM-ul doar explică, cu mesajul „se gândește…" |
| A* spațiu-timp e prea lent | Orizont mai scurt sau zona furtunii „umflată" static |
| Integrarea frontend–backend întârzie | Frontendul rulează pe scenarii înregistrate (mock) |
| Internetul pică la demo | Totul local + video de rezervă |
| Juriul întreabă dacă AI-ul poate greși | AI-ul alege doar dintre variante validate; benchmark-ul o arată |

---

## 10. Cum răspundem criteriilor juriului

| Criteriu | Argument |
|---|---|
| **Influence** | Siguranța primelor ieșiri umane pe Marte; aceeași logică ajută salvamontul pe Pământ |
| **Creativity** | Replanificare în timp real cu predicția pericolului, nu o hartă statică |
| **Validity** | DTM-uri oficiale NASA/USGS, date din 5 misiuni, decizii deterministe, benchmark măsurat |
| **Relevance** | Acoperă cerințele: hiperlocal, ≥3 tipuri de date, siguranță, radiație, mobilitate în costum, obiective științifice, imagini de la sol |
| **Presentation** | Demo vizual: furtuna se mișcă, traseul se reface, decizia e explicată |
