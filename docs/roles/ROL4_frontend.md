# Rolul 4: Frontend

Ești unul dintre 4 agenți care implementează **simultan** Marswalk Copilot în același repo. Ceilalți trei lucrează la date (`pipeline/`, `docs/`), algoritmi (`backend/app/core/`) și backend + LLM (`backend/app/api/`, `live/`, `llm/`). Tu ai tot `frontend/`: ce vede juriul la demo.

## Proiectul în 30 de secunde

Marswalk Copilot ajută un astronaut care iese pe jos pe Marte (delta din craterul Jezero). Are o hartă hiperlocală de 10×10 km pe grilă de 20 m (500×500 celule) și un copilot live. La fiecare minut simulat, copilotul prezice pericolele (furtuni care se mișcă, radiație), generează trasee alternative, elimină variantele nesigure și alege una. Decizia apare **imediat**, iar explicația LLM-ului vine **separat**, după 2-3 s. Demo-ul de 2 minute (secțiunea 8 din README) e construit pe ecranul tău.

Citește din `README.md`: secțiunile 4 (workflow-ul), 5.9 (frontendul) și 8 (demo-ul). Citește și tot `shared/contracts/`: formele JSON de acolo sunt cele pe care le primești.

## Ce fișiere ai voie să modifici

- `frontend/**`, **în afară de** `frontend/package.json` și `frontend/package-lock.json`
- `docs/roles/notes/rol4.md`

**Orice alt fișier e doar pentru citit.** Poți **importa** (doar citire) din `shared/contracts/` (alias-ul `@contracts`) și `docs/how-we-calculate.md` (prin `?raw`).

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
3. **Harta:**
   - pan și zoom (rotița și drag pe `viewBox`)
   - opacitate per strat și legende din `terrain_classes` și `mineral_classes`
   - **la hover**, valorile din `GET /api/point`, cu debounce și fallback silențios
   - habitatul, țintele cu imaginea de la oprire (`targets[].image`, poate fi `null`)
4. **Ieșirea live:**
   - astronautul **interpolat lin** între tick-uri, cu urma lăsată în spate
   - furtuna curentă și **conul de predicție** (elipsele din `forecast`, tot mai transparente pe măsură ce orizontul crește)
   - alternativele colorate pe tip: cele invalide punctate cu roșu, cea aleasă îngroșată
   - punctul de neîntoarcere
5. **Controalele simulării:** start, pauză, reset și viteza ceasului (`POST /api/live/control`), plus butoanele de evenimente (`POST /api/live/event`).
6. **Panoul copilotului:** decizia apare imediat, cu „se gândește…” până sosește `explanation` cu același `decision_id`. Afișezi sursa explicației (llm, template sau cache), tabelul alternativelor cu motivele de respingere și istoricul deciziilor.

**P1, ziua 2:**
7. **Chatul:** citește streamul NDJSON (`chat_stream.json`). Apelurile de unelte apar ca etichete, iar un mesaj `route` desenează traseul pe hartă.
8. **Ecranul „Cum calculăm”:** importă `docs/how-we-calculate.md?raw` și randează-l cu un mini-renderer propriu de markdown (titluri, tabele, liste), fără dependențe noi.

**P2, bonus:**
9. **Vederea HUD** (ce vede astronautul în cască): O₂, timpul până la apus, săgeata spre următorul punct al traseului, alertele.
10. **Survival Guide printabil:** CSS de print, cu traseul, opririle, punctul de neîntoarcere și regulile.

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
- React 18 cu componente funcționale și hook-uri, JavaScript (JSX), fără TypeScript. Textele din UI sunt în română; numele de variabile în engleză.
- Coordonatele pe hartă: `x = col`, `y = row`, iar `viewBox` e în celule de grilă. Mărimile în metri se împart la `cell_size_m`.

### Note de predare: `docs/roles/notes/rol4.md`
Le ții la zi după fiecare sarcină, cu secțiunile fixe **Gata**, **În lucru**, **Cereri** (pentru alt rol sau pentru oameni) și **Presupuneri**. E singurul canal de comunicare cu ceilalți agenți.
