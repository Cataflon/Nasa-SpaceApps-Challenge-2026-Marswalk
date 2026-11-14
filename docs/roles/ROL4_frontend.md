# Rolul 4: Frontend

> ## 🆕 NOU (14.11.2026): citește întâi asta
> Echipa a adăugat 7 funcționalități legate direct de tema challenge-ului („Interplanetary Survival Guide”). Tabelul complet e în `README.md`, secțiunea „🆕 Noutăți”. **Rolul tău are cele mai multe** (detaliile sunt mai jos, marcate 🆕). Toate merg și pe mock, cu fallback-urile indicate:
> 1. **Ceasul de întoarcere, cifra principală** (P0): „Te întorci până la 14:20”, mare, mereu vizibil, nu ascuns într-un panou.
> 2. **Contorul „Pământul vs. copilotul”** (P0): „ajutorul de la Houston ar ajunge în 28 min · copilotul a decis în 0,05 s”, la fiecare decizie.
> 3. **Click pe orice punct de pe hartă** (P0): popup cu valoarea fiecărui strat **și** misiunea / instrumentul lui („pantă 12° · HiRISE · MRO”).
> 4. **Survival Guide printabil, mutat din bonus în P1:** o pagină per ieșire.
> 5. **Numărul de titlu din benchmark** (P1): „acasă în siguranță: copilot X% · plan fix Y%”.
> 6. **„How we calculate”** (P1): badge-uri pe coloana „Status” (`source`, `assumption`, `to verify`).
> 7. 🆕🆕 **Hardware NASA real pe hartă (adăugat după, P1, ~1 h):** strat activabil „NASA hardware” din `site.artifacts` (depozitul de probe Three Forks, locul de aterizare, sky crane-ul, parașuta, scutul termic, Ingenuity), cu iconițe per `type`, cerc de precauție (`caution_radius_m`), popup și **traseul real al roverului Perseverance** din `site.rover_traverse`. Datele sunt **deja** în `/api/site` și în mock-ul `site.json`. Detalii la sarcina 3, marcate 🆕🆕.

Ești unul dintre 4 agenți care implementează **simultan** Marswalk Copilot în același repo. Ceilalți trei lucrează la date (`pipeline/`, `docs/`), algoritmi (`backend/app/core/`) și backend + LLM (`backend/app/api/`, `live/`, `llm/`). Tu ai tot `frontend/`: ce vede juriul la demo.

## Proiectul în 30 de secunde

Marswalk Copilot ajută un astronaut care iese pe jos pe Marte (delta din craterul Jezero). Are o hartă hiperlocală de 10×10 km pe grilă de 20 m (500×500 celule) și un copilot live. La fiecare minut simulat, copilotul prezice pericolele (furtuni care se mișcă, radiație), generează trasee alternative, elimină variantele nesigure și alege una. Decizia apare **imediat**, iar explicația LLM-ului vine **separat**, după 2-3 s. Demo-ul de 2 minute (secțiunea 8 din README) e construit pe ecranul tău.

Citește din `README.md`: secțiunile 4 (workflow-ul), 5.9 (frontendul) și 8 (demo-ul). Citește și tot `shared/contracts/`: formele JSON de acolo sunt cele pe care le primești.

## Ce fișiere ai voie să modifici

- `frontend/**`, **în afară de** `frontend/package.json` și `frontend/package-lock.json`
- `docs/roles/notes/rol4.md`

**Orice alt fișier e doar pentru citit.** Poți **importa** (doar citire) din `shared/contracts/` (alias-ul `@contracts`), `docs/how-we-calculate.md` și 🆕 `docs/survival-guide.md` (prin `?raw`).

Dependențele sunt doar `react` și `vite`. Graficele (profilul de altitudine, barele de buget) le desenezi direct în SVG. Dacă ai nevoie neapărat de o bibliotecă, o scrii la „Cereri” în note.

## Cum lucrezi fără backend

- `npm run dev` pornește pe portul 5173. Dacă backendul nu răspunde, `src/api/client.js` cade automat pe mock-urile din `shared/contracts/` (badge-ul „date mock”).
- Pentru contractele noi (`live_control.json`, `chat_stream.json`) adaugi tot în `client.js` fallback-uri pe mock. Chatul în mod mock redă liniile din `chat_stream.json`, cu o mică pauză între ele.
- Pentru backendul real al rolului 3, care rulează pe portul 8001, pornești cu `BACKEND_URL=http://localhost:8001`. `vite.config.js` citește deja această variabilă.
- `src/api/client.js` e **singurul** loc cu `fetch` și `WebSocket`.

## Sarcinile, în ordinea priorității

**P0, ziua 1:**
1. **Structură:** sparge `App.jsx` în hook-uri (`useSite`, `useRoute`, `useLive` cu WebSocket, reconectare și fallback pe mock) și componente mici.
2. **Planificarea:** alegi țintele (mai multe), preset-ul (`safe`, `fast`, `science`) și durata maximă, apoi trimiți `POST /api/route`. Afișezi verdictul (GO / CAUTION / NO-GO), bugetul, punctul de neîntoarcere și **profilul de altitudine** în SVG, din `elevation_profile`.
   - 🆕 **Ceasul de întoarcere, cifra principală de pe ecran:** „Te întorci până la 14:20”, cu cel mai mare font din pagină, mereu vizibil (header sau colț fix), nu ascuns într-un panou. Ora locală pe Marte (LTST): `h = eva_start_ltst_h + return_by_min / 61.65` (o oră marțiană = 61,65 min). `eva_start_ltst_h` vine din `/api/site`, cu fallback `9.0`; `return_by_min` vine din `budget` (traseu) sau din `tick.budget` (live). Se actualizează la fiecare decizie; dacă timpul rămas e sub 30 min, se colorează în avertizare.
3. **Harta:**
   - pan și zoom (rotița și drag pe `viewBox`)
   - opacitate per strat și legende din `terrain_classes` și `mineral_classes`
   - **la hover**, valorile din `GET /api/point`, cu debounce și fallback silențios
   - 🆕 **la click pe orice punct**, un popup cu toate straturile: valoarea, unitatea **și sursa**, de forma „pantă 12° · HiRISE · MRO”. Sursa vine din `sources` în `/api/point` sau, dacă lipsește, din etichetele `layers[]` din `/api/site` (`mission`, `instrument`, `data_type`, `analog_of`). Pe situl sintetic apare „sintetic (analog: HiRISE)”. Face vizibile cele „5 misiuni NASA”.
   - habitatul, țintele cu imaginea de la oprire (`targets[].image`, poate fi `null`)
   - 🆕🆕 **Stratul „NASA hardware” (activabil, pornit implicit la demo)** din `site.artifacts`. Sursa: [harta oficială a roverului Perseverance](https://science.nasa.gov/mission/mars-2020-perseverance/location-map/). Câmpuri: `id`, `name`, `type`, `row`, `col`, `caution_radius_m`, `note`, `source`, `status`. Fallback: `[]` dacă lipsește.
     - **Iconiță diferită per `type`:** `recovery_target` (depozitul Three Forks, evidențiat: „10 sample tubes”), `landmark` (locul de aterizare Octavia E. Butler), `historical_hardware` (Ingenuity, scutul termic), `hazard_debris` (sky crane, parașuta + backshell).
     - **Cerc de precauție** cu raza `caution_radius_m / cell_size_m` celule în jurul `hazard_debris` (roșu-portocaliu, semitransparent). E doar vizual: **nu** intră în rutare.
     - **Popup la click/hover:** `name`, `note` și o etichetă mică cu `status` (`verified` = poziție din datele roverului, `to verify`, `synthetic`).
     - **Traseul real al roverului** din `site.rover_traverse.path` (`[[row, col], …]`, doar pe situl Jezero; `null` pe cel sintetic): o linie subțire, punctată, cu legenda „Perseverance traverse (sols …)”.
     - **La demo:** ținta `clay_delta` e la ~200 m de depozitul Three Forks. Replica: „Go recover the titanium sample tubes Perseverance left at Three Forks!”.
4. **Ieșirea live:**
   - astronautul **interpolat lin** între tick-uri, cu urma lăsată în spate
   - furtuna curentă și **conul de predicție** (elipsele din `forecast`, tot mai transparente pe măsură ce orizontul crește)
   - alternativele colorate pe tip: cele invalide punctate cu roșu, cea aleasă îngroșată
   - punctul de neîntoarcere
5. **Controalele simulării:** start, pauză, reset și viteza ceasului (`POST /api/live/control`), plus butoanele de evenimente (`POST /api/live/event`).
6. **Panoul copilotului:** decizia apare imediat, cu „se gândește…” până sosește `explanation` cu același `decision_id`. Afișezi sursa explicației (llm, template sau cache), tabelul alternativelor cu motivele de respingere și istoricul deciziilor.
   - 🆕 **Contorul „Pământul vs. copilotul”** la fiecare decizie: „Ajutorul de la Houston ar ajunge în **28 min** · copilotul a decis în **0,05 s**”. `earth_delay_min.round_trip` vine din `/api/site` (fallback 28), iar `compute_ms` din mesajul `decision` (fallback: timpul dintre `tick` și `decision` măsurat în browser, marcat „≈”). O singură linie, vizibilă de la 3 m.

**P1, ziua 2:**
7. **Chatul:** citește streamul NDJSON (`chat_stream.json`). Apelurile de unelte apar ca etichete, iar un mesaj `route` desenează traseul pe hartă.
8. **Ecranul „How we calculate”:** importă `docs/how-we-calculate.md?raw` și randează-l cu un mini-renderer propriu de markdown (titluri, tabele, liste), fără dependențe noi. 🆕 Valorile din coloana „Status” (`source`, `assumption`, `to verify`) apar ca badge-uri colorate, ca juriul să vadă imediat ce e măsurat și ce e presupus.
9. 🆕 **Survival Guide printabil (mutat din bonus):** o pagină A4 per ieșire, cu buton „Print” și CSS `@media print`:
   - harta mică a traseului cu opririle și punctul de neîntoarcere;
   - **ora-limită de întoarcere**, mare, și punctul de neîntoarcere (ora și locul);
   - bugetul pe scurt (O₂ final, doză, apus);
   - regulile „ce faci la furtună locală / regională / solară…”, importate din `docs/survival-guide.md?raw` (scris de rolul 1; până există, un text placeholder).
10. 🆕 **Numărul de titlu din benchmark:** „Copilotul a adus astronautul acasă în siguranță în **X%** din furtuni; planul fix, în **Y%**”, din `GET /api/benchmark` → `headline`. Apare în header sau pe un ecran dedicat; fallback: ascuns dacă ruta întoarce 501.

**P2, bonus:**
11. **Vederea HUD** (ce vede astronautul în cască): O₂, timpul până la apus, săgeata spre următorul punct al traseului, alertele.

**Design:** temă întunecată de Marte (pornește de la variabilele din `styles.css`), cifre `tabular-nums`, layout care merge și pe ecran de laptop la 1366 px. La demo totul trebuie să se citească de la 3 metri.

## Teste: doar build-ul

Din `frontend/`:

```bash
npm run build
```

Durează ~1 s și prinde erorile de import și de sintaxă. Nu adăuga framework de teste. După fiecare sarcină mai mare, verifică vizual în browser, pe mock-uri.

## Reguli comune (obligatorii pentru toți cei 4 agenți)

### Git
- **NU** rula `git commit`, `git push`, `git add`, `git pull`, `git merge`, `git rebase`, `git stash`, `git checkout`, `git reset` sau orice altă comandă care schimbă starea repo-ului. Doar scrii cod. Ai voie la `git status` și `git diff`.
- Commit-ul și push-ul le fac oamenii, separat pentru fiecare rol. Folderele nu se suprapun, deci nu apar conflicte la merge.

### Fără interferențe
- Modifici **doar** fișierele din secțiunea „Ce fișiere ai voie să modifici”. Alți 3 agenți scriu în același timp în același repo.
- Nu muta, nu redenumi, nu șterge și nu reformata fișiere din afara zonei tale. Nu rula formatere pe tot repo-ul (`prettier --write .` din rădăcină), ci doar pe `frontend/src`.
- **Înghețate:** `shared/contracts/**`, `README.md`, `.gitignore`, `.github/**`, `frontend/package.json`, `frontend/package-lock.json`, tot `backend/`. Dacă ai nevoie de o schimbare acolo (de exemplu un câmp nou în contract), o scrii la „Cereri” în notele tale.
- Nu rula `npm install <pachet>`. Doar `npm install` simplu, dacă lipsește `node_modules`.
- Dacă o rută din backend nu există încă sau întoarce 501, nu o implementa tu. Folosește mock-ul.
- Pornești doar Vite, pe 5173. Dacă portul e ocupat, folosește 5174 (`npm run dev -- --port 5174`). Nu porni backendul.

### Teste
- Rulezi doar `npm run build`, nu altceva, la fiecare schimbare.

### Cod
- React 18 cu componente funcționale și hook-uri, JavaScript (JSX), fără TypeScript. **Toate textele din UI sunt în engleză** (juriul e internațional); numele de variabile în engleză, comentariile pot rămâne în română.
- Coordonatele pe hartă: `x = col`, `y = row`, iar `viewBox` e în celule de grilă. Mărimile în metri se împart la `cell_size_m`.

### Note de predare: `docs/roles/notes/rol4.md`
Le ții la zi după fiecare sarcină, cu secțiunile fixe **Gata**, **În lucru**, **Cereri** (pentru alt rol sau pentru oameni) și **Presupuneri**. E singurul canal de comunicare cu ceilalți agenți.
