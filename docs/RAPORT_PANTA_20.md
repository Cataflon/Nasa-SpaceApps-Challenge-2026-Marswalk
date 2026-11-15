# Raport: respectarea limitei de pantă de 20°

**Data:** 15.11.2026. **Cod verificat:** copia de pe laptop (`D:\NasaSpaceApp`), sit **Jezero** (implicit în `config.py`), plus înregistrarea de ecran din demo.
**Cum am verificat:** traseele produse de cod au fost evaluate independent cu straturile backend-ului (`slope.npy`, `unsafe.npy`), care sunt sursa limitei. Scriptul `verify_slope.py` reface toate verificările.

## Concluzia pe scurt

**Algoritmul din backend respectă limita.** Traseele care o încalcă vin din alte surse: un **al doilea algoritm de rutare, în frontend**, cu altă limită și alte date, și **traseul mock** din contract. Pe deasupra, harta 3D are relieful **exagerat vertical de 6 ori**, așa că și traseele corecte par să urce pe pereți.

| Sursa traseului | Trasee testate | Peste 20° sau `unsafe` | Pantă maximă reală |
|---|---|---|---|
| Backend `plan_route` (toate combinațiile de ținte × 3 preseturi) | 21 | **0** | 18,5° |
| Motorul live, cu traseu planificat (scenariul demo, 260 min) | 163 de căi în mesaje | **0** | 12,5° |
| Motorul live **fără** traseu planificat (mock-ul din contract) | căile din mesaje | **30** | 22,3°, cu salturi de 9 celule |
| **Frontend `routing.worker.js`** (previzualizare și waypoint trip) | 56 | **19** | **58,3°**, prin celule `unsafe` |

---

## Constatări

### P1. Frontendul are propriul A*, cu limita de 25° și pe alte date (CRITIC)

`frontend/src/terrain/routing.worker.js` calculează în browser traseele pentru:
- „Terrain preview” (butoanele *Slope weighted* și *Shortest*);
- „Waypoint trip” (`useWaypointTrip.js`).

Diferențe față de backend:

| | Backend (`core/costmap.py`) | Worker frontend |
|---|---|---|
| Limita | `meta.max_slope_deg` = 20° | **25°, scrisă în cod** (`if(sl>25)continue`) |
| Ce înseamnă „pantă” | panta celulei din `slope.npy` (date fine, conservator) | panta **direcțională** între două celule vecine, pe 20 m |
| Datele | `data/processed/jezero/elevation.npy` + `slope.npy` | `frontend/public/terrain/jezero.json` (grila de afișare, `displayOnly: true`) |
| Masca `unsafe` | da | **nu** |
| Ordinea opririlor | cea mai scurtă | ordinea din listă |

**Grila frontendului „nu vede” pantele abrupte.** Din cele 5.103 celule pe care backendul le consideră peste 20°, **4.922 (96 %)** apar sub 20° pe grila `jezero.json`. Cele două grile de elevație diferă în medie cu 9,6 m, cu maximum 63 m.

**Rezultat:** 19 din 56 de trasee ale workerului trec prin celule peste 20°, iar valoarea raportată în panou e mult sub cea reală. Exemple:

| Destinație | Varianta | „Maximum path slope” afișat | Panta reală (strat backend) |
|---|---|---|---|
| `carbonate_rim` (123, 10) | Slope weighted | **7,8°** | **36,9°** (29 celule > 20°, 1 `unsafe`) |
| `carbonate_rim` (123, 10) | Shortest | 22,6° | 28,7° |
| punct (100, 47) | Slope weighted | 11,7° | 40,3° |
| punct (260, 75) | Shortest | 11,9° | 58,3° (4 celule `unsafe`) |

Spre `carbonate_rim`, backendul găsește un traseu valid (≤ 18,5°). Workerul trece printr-o zonă pe care backendul o interzice.

### P2. Când backendul refuză un punct, aplicația afișează traseul workerului (MAJOR)

`App.jsx`: `tripRoute = route ? null : trip.result`. Dacă nu există plan de la backend, se afișează traseul local.

Backendul refuză corect (422) un punct propriu pus pe o pantă peste 20° (`register_custom_stops`: „terrain that is too steep or unsafe”). În acest caz nu există plan, deci se afișează traseul din worker, care urcă panta.

Din înregistrare nu pot spune sigur ce traseu era afișat. Punctul era pe o creastă, iar playerul era în modul „Route preview”, deci acest lanț se potrivește cu ce se vede.

### P3. Pornirea live fără traseu planificat folosește mock-ul din contract (MAJOR)

`engine._start`: fără `route_id`, se ia `store.latest()` sau `shared/contracts/route_response.json`.

Mock-ul are coordonatele sitului **sintetic**, cu puncte rare (salturi de 9 celule), desenate ca linii drepte. Pe Jezero trece prin celule de 22,3° și nu are legătură cu terenul.

La fel, `planRoute` din `api/client.js` cade pe mock la orice eroare 5xx sau de rețea.

### P4. Relieful 3D e exagerat de 6 ori (EFECT VIZUAL)

`frontend/terrain/build_blender.py`: `VERTICAL_SCALE = 6.0` (eticheta mică din colț: „vertical 6×”).

| Panta reală | Cum arată pe harta 3D |
|---|---|
| 5° | 28° |
| 10° | 47° |
| 15° | 58° |
| 20° | 65° |

Un traseu perfect valid, de 12-15°, arată ca o cățărare pe perete. O parte din impresia din demo vine de aici, nu din algoritm.

### P5. Două surse de elevație (DE ȘTIUT)

Backendul folosește `slope.npy` (maximum 64,6°, conservator, calculat din date mai fine decât 20 m). Frontendul folosește `jezero.json`, un CTX de 20 m mult mai neted.

Nu e o eroare în sine, dar **orice calcul de pantă făcut în frontend va contrazice backendul**.

### Ce e în regulă
- `costmap.static_cost` pune `inf` peste `meta.max_slope_deg` și pe `unsafe`. `meta.json`, `Limits` și validatorul folosesc toate 20°.
- `temp_cost` (live) păstrează celulele interzise ca `inf`. Excepția e doar celula de start, ca astronautul să poată ieși dintr-o poziție interzisă.
- Punctele proprii pe pante interzise sunt respinse de backend cu mesaj clar.
- Cap-coadă, traseul live nu trece prin nicio celulă peste 20° (pantă maximă sub astronaut: 10,3°).

---

## Remediere

| # | Ce | Cine | Efort |
|---|---|---|---|
| R1 | **O singură sursă de rutare: backendul.** Previzualizarea și waypoint trip cer traseul de la `POST /api/route` (sub 50 ms cu cache). Dacă păstrați workerul pentru previzualizare instant, îl hrăniți cu masca backendului (vezi R1b) și scrieți pe ecran „previzualizare, nevalidată”. | rol 4 + rol 3 | 1-2 h |
| R1b | Endpoint `GET /api/passable`: masca de celule permise (`static_cost` finit), 250.000 de biți ≈ 31 KB, plus `max_slope_deg`. Workerul respinge celulele interzise după mască, nu după panta lui. | rol 3 | 30 min |
| R2 | Fără fallback pe traseul local când backendul refuză. Se afișează eroarea din 422, iar backendul propune cea mai apropiată celulă validă (`suggested: {row, col}`) pe care utilizatorul o acceptă cu un clic. | rol 3 (sugestie), rol 4 (UI) | 1 h |
| R3 | Pornirea live fără traseu: 409 „Plan a route first” în loc de mock. Fallback pe mock în frontend doar în modul mock explicit (`LIVE_MOCK=1`), niciodată pe Jezero. | rol 3, rol 4 | 30 min |
| R4 | Exagerare verticală 2× implicit, cu comutator 1× / 2× / 6× și etichetă vizibilă. Traseul colorat după panta **reală** (din backend): verde < 10°, galben 10-15°, portocaliu 15-20°. | rol 4 | 1 h |
| R5 | „Maximum path slope” afișat din backend: câmp opțional nou `budget.max_slope_deg` (maximul `slope.npy` pe traseu), nu calculat în browser. | rol 2 + rol 4 | 30 min |
| R6 | Teste: (a) backend: orice cale emisă (plan, alternative, live) are toate celulele ≤ `max_slope_deg` și nu e `unsafe`; (b) frontend: workerul, cu o mască de test, nu trece prin celule interzise; (c) `verify_slope.py` în CI sau rulat înainte de demo. | rol 2, rol 4 | 1 h |

**Ordinea pentru demo:** R3 și R2 (10 minute fiecare, elimină traseele mock și fallback-ul), apoi R1, apoi R4 (ce văd jurații). R5 și R6 după.

### Prompt pentru agent (rolurile 3 și 4, cu acordul echipei)

```
Marswalk Copilot: limita de pantă de 20° trebuie respectată de TOT ce aplicația desenează ca traseu.
Backendul o respectă; problemele sunt în frontend și în fallback-uri. Citește RAPORT_PANTA_20.md.
Ai voie: backend/app/api/**, backend/app/live/**, frontend/src/**, testele lor, notele rol3.md/rol4.md.
Nu schimbi algoritmii din backend/app/core (doar câmpul opțional budget.max_slope_deg, dacă rolul 2 nu
l-a adăugat deja). Git doar status/diff.

1. R3: LiveEngine.start fără route_id și fără traseu în store → eroare (POST /api/live/control întoarce
   409 „Plan a route first”), nu mock. Mock-ul doar cu LIVE_MOCK=1. În client.js, planRoute nu mai cade
   pe mock la 5xx dacă situl nu e mock (X-Mock lipsă la /api/site): afișează eroarea.
2. R2: în App.jsx nu mai folosi trip.result (workerul) ca traseu când backendul a refuzat (422) sau nu
   răspunde. În register_custom_stops, la celulă interzisă, întoarce în 422 și `suggested` = cea mai
   apropiată celulă cu static_cost finit și accesibilă din habitat (inele Chebyshev, ordine (row, col)).
   UI: mesajul + buton „Mută punctul aici”.
3. R1: previzualizarea (Slope weighted / Shortest) și waypoint trip folosesc POST /api/route (preset
   safe, respectiv fast). Dacă păstrezi workerul pentru răspuns instant: endpoint GET /api/passable
   (mască pe biți din static_cost finit + max_slope_deg), workerul respinge celulele interzise după
   mască, limita citită din site, fără 25 în cod; eticheta „Preview — not validated” până vine
   răspunsul backendului, apoi traseul backendului îl înlocuiește.
4. R4: exagerarea verticală implicit 2×, comutator 1×/2×/6× vizibil; traseul colorat după panta reală
   (budget.max_slope_deg și pantele pe segmente din backend, nu din grila jezero.json).
5. R5: „Maximum path slope” din budget.max_slope_deg (backend).
6. Teste: backend — orice path din /api/route, din alternativele live și din tick.remaining_path are
   celulele ≤ meta.max_slope_deg și nu e unsafe (pe situl sintetic și pe Jezero dacă există); 409 la
   start fără plan; 422 cu suggested. Frontend (node --test) — workerul cu o mască de test nu trece
   prin celule interzise.
7. La final rulează verify_slope.py --repo . --site jezero și dă-mi ieșirea: toate liniile trebuie OK.
```

## Cum re-verifici
```
.venv\Scripts\python verify_slope.py --repo . --site jezero
```
Partea de frontend cere `node` în PATH. Toate liniile trebuie să fie `[OK]` după remediere.
