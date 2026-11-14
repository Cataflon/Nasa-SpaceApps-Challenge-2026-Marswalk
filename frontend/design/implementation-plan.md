# Marswalk — plan frontend și direcție vizuală

Data: 14 noiembrie 2026. Livrabil: plan și concept navigabil, fără modificarea aplicației existente.

Actualizare după implementare: dashboardul de bază este implementat. Direcția vizuală activă, confirmată ulterior de utilizator, este Vision UI Dashboard / Billing reinterpretat în negru și portocaliu: meniu lateral, carduri de telemetrie, panouri rotunjite și degrade discret. Referință: https://demos.creative-tim.com/vision-ui-dashboard-react/#/billing . Paleta cyan și navigarea orizontală descrise mai jos aparțin conceptului inițial și sunt înlocuite de această direcție.

Următorul pas explicit: model Blender al reliefului Jezero din GeoTIFF USGS, cu .blend, export GLB optimizat și transformare comună cu grila traseelor. Exportul ortografic este fallback pentru dispozitivele mici; integrarea modelului 3D interactiv va avea nevoie de renderer și de coordonarea dependențelor cu echipa. Acest pas nu este încă executat.

## Decizia de produs

O aplicație cu trei experiențe: centrul de misiune pe desktop, navigatorul astronautului pe telefon/ceas și monitorizarea senzorilor/echipamentelor. Aceeași stare de misiune și aceleași decizii alimentează toate ecranele. Desktopul păstrează harta în prim-plan; telefonul prioritizează următoarea indicație; ceasul prioritizează direcția și alerta curentă.

## Ce există în cod

- App.jsx: schelet cu hartă, straturi, planificarea primei ținte și abonare live. Pauza actuală oprește abonarea UI, nu controlează motorul backend.
- MapView.jsx: imagini de straturi și suprapuneri SVG, alternative, furtună, forecast, habitat, ținte și poziție. Lipsesc pan/zoom și interpolarea.
- client.js: REST cu fallback și WS cu redare repetată de mock la eroare. Trebuie reconectare, eliminarea timerelor duplicate, validarea mesajelor și stare explicită de conexiune.
- Deciziile și explicațiile sunt memorate separat în App; asocierea trebuie făcută după decision_id, inclusiv când explicațiile vin târziu.
- Nu am găsit prepare_dtm.py în lista fișierelor repo-ului. Pregătirea GeoTIFF/Blender necesită un livrabil nou al rolului 1.

## Direcție vizuală

Hartă dominantă, topografie vizibilă, panouri liniștite cu puține delimitări. Titluri și texte aliniate la stânga; cifre aliniate la dreapta în liste. Fără efecte decorative care concurează cu traseul.

Paletă propusă: bazalt #151B22, panouri #202A34, text #EEF3F5, traseu cyan #68D8ED, avertizare #EFBF69, critic #FA8B8B. Solul își primește culoarea din materialul cartografic. Forma și eticheta dublează codul de culoare.

Tipografie: propunere IBM Plex Sans pentru UI și cifre tabulare; în MVP folosim fontul de sistem până sunt pregătite fonturile locale și licența. Corp 14–16 px, valori 24–32 px, indicație navigator 32–40 px. Grilă de spațiere 8 px, colțuri moderate, fără majuscule decorative. Animațiile reprezintă poziția și schimbarea rutei; respectă reduced-motion.

```
Desktop 1366 × 768
┌─────────────────────────────────────────────────────────────────┐
│ Marswalk / Jezero        Misiune  Senzori         Conexiune       │
├───────────────────────────────────────────────┬─────────────────┤
│ Straturi · Nord · Urmărește astronautul         │ Copilot         │
│                                               │ Decizie         │
│            Hartă mare ~75%                     │ Explicație      │
│     habitat — traseu — astronaut — ținte       │ Buget           │
│            furtună + predicție                 │ Opriri          │
│                                               │ Detalii la clic │
├───────────────────────────────────────────────┴─────────────────┤
│ O₂ · lumină · doză       Start / Pauză / Reset      Timp / Viteză│
└─────────────────────────────────────────────────────────────────┘

Telefon 390 × 844             Ceas, țintă inițială ~200 × 240 CSS px
┌──────────────────────┐     ┌───────────────────┐
│ Indicație + distanță  │     │ Alertă / conexiune│
│                      │     │ Direcție          │
│ Hartă locală         │     │ Distanță segment  │
│ centrată pe poziție   │     │ O₂                │
│                      │     └───────────────────┘
│ O₂ · lumină · alertă  │
│ Navigare / Status    │
└──────────────────────┘
```

Alternative evaluate: panouri flotante peste o hartă fullscreen sau hartă cu panou lateral fix/retractabil. Recomand a doua pentru MVP: text lizibil, fără acoperirea pericolelor. Fullscreen rămâne o acțiune explicită. Ceasul are un layout dedicat, nu dashboard micșorat. În prima etapă este un mod web de demonstrație; un produs watchOS/Wear OS nativ necesită o etapă separată.

## Hartă reală și Blender

1. Rolul 1 inspectează GeoTIFF: CRS marțian, transformare afină, unități, datum vertical, NoData, întindere și acoperire. Centrul din mock nu este suficient pentru georeferențiere. Dimensiunile/erorile enumerate în mesajul utilizatorului rămân de verificat în metadate.
2. Se fixează aceeași zonă de 10 × 10 km pentru datele de calcul și imagine. HiRISE este sursa preferată; CTX acoperă golurile. Grila de calcul rămâne 20 m pentru compatibilitatea curentă. Rezoluția afișării este independentă.
3. Panta se calculează la rezoluția sursei și se agregă conservator conform rolului 1. Decimarea vizuală nu schimbă grila folosită la siguranță.
4. DTM-ul furnizează înălțimi. Pentru aspect fotografic este necesară o ortoimagine separată; alternativ, Blender produce relief umbrit cu material neutru.
5. MVP: Blender pregătește un render ortografic vertical, nord în sus, fără perspectivă, cu aceeași întindere ca grila. Exportul local PNG/WebP este fundalul SVG. Imaginile și traseele folosesc aceeași transformare de pan/zoom. Se verifică alinierea în minimum trei puncte, inclusiv habitat și ținte.
6. Contractul de asset propus: site_id, versiune, sursă, CRS, bounds, grid transform, rows/cols, cell_size_m, origine, orientare, image_url și dimensiuni. Se adaugă prin coordonare, nu prin schimbarea unilaterală a shared/contracts.
7. Ulterior: mesh optimizat GLB, niveluri de detaliu și textură. Vizualizarea 3D în browser necesită un renderer, de exemplu Three.js, deci o dependență aprobată de echipă. Ruta 3D se proiectează pe același relief și transformare. Telefonul/ceasul păstrează varianta 2D.

Pentru coordonate la centrele celulelor: x = col și y = row în SVG; conversia în coordonatele rasterului trebuie să documenteze dacă transformarea referă colțul sau centrul pixelului, pentru a evita o deplasare de jumătate de celulă. În Blender, axele și originea locală sunt declarate în export; exagerarea verticală, dacă există vizual, nu intră în calcule.

## Livrări, în ordine

### A. Dashboard de bază

- AppShell cu navigare Misiune / Senzori / Cum calculăm; hartă 70–80% din spațiul principal, panou lateral ~300 px pe laptop.
- useSite, useRoute, useLive și reducer pentru starea misiunii; client.js rămâne singurul strat de rețea.
- Hartă 2D cu fallback vizibil, straturi, legendă, pan/zoom, habitat și ținte.
- Formular cu mai multe opriri, preset, durată maximă; traseu, verdict și buget din API.
- Stări încărcare, fără traseu, eroare, mock, deconectat. Erorile de validare 422 se afișează, nu sunt ascunse prin succes mock.
- Acceptare: 1366 × 768 și 1920 × 1080, harta rămâne dominantă, planul poate fi creat pe mock fără backend.

### B. Navigare live și demo

- Start/pauză/reset/viteză controlează motorul prin /api/live/control; feedback la succes sau eșec.
- Interpolare numai între poziții cunoscute, de-a lungul segmentelor traseului; fără extrapolare la pierderea conexiunii.
- Urmă, traseu rămas, punct de neîntoarcere, forecast cu orizonturi distincte, alternative valide/invalide.
- Reducer corelează decision/explanation după decision_id; istoricul și explicațiile vechi nu suprascriu decizia curentă.
- WebSocket: reconectare cu backoff, curățare, deduplicare; la reconectare se cere snapshot coerent. Pauza păstrează conexiunea și explicațiile în curs.
- Acceptare: furtună → alternative → decizie imediată → explicație întârziată; reset elimină vechea misiune; conexiune pierdută marchează datele învechite.

### C. Telefon și ceas

- Telefon: indicație dominantă, hartă locală, O₂, timp/lumină, alertă; detalii într-un panou la cerere. Test vizual la 320, 390 și 430 px.
- Ceas: direcție, distanță până la următorul segment, O₂ și alertă prioritară; ținte de interacțiune generoase, fără tabele și chat.
- Direcția nord-sus se poate deriva din ruta locală. O săgeată relativă la orientarea astronautului cere heading real; nu confundăm direcția segmentului cu orientarea corpului.
- Poziția reală este o dependență de localizare. Demo-ul folosește poziții simulate; geolocația browserului de pe Pământ nu se folosește pe harta Marte.
- Desktopul și dispozitivele primesc aceeași misiune de la backend; snapshot, session_id și sequence sunt cereri pentru rolul 3. PWA/cache offline se planifică ulterior, fără a prezenta datele memorate drept live.

### D. Senzori, prevenție și mentenanță

- Date existente: O₂, dust_tau, wind_ms, temp_c, pressure_pa, dose_rate_usv_h, dose_total_msv. Temperatura/presiunea sunt de mediu; nu le etichetăm drept valori ale costumului.
- MVP: valoare, unitate, sursă, istoricul disponibil în sesiune și timpul ultimei recepții. Timpul recepției nu este timpul măsurării.
- Extensie propusă: sensor_id, measured_at sau t_min, received_at, quality, status, praguri cu sursa lor, device_id, battery_pct, fault_codes, calibration_due și service_due.
- Afișăm explicit necunoscut / indisponibil / învechit. Datele absente nu înseamnă stare sănătoasă.
- Prevenția folosește pragurile și alertele definite de backend; mentenanța inițială este stare, jurnal și verificări programate. Predicția defecțiunilor necesită date și model validate, nu se deduce din senzorii de mediu.
- Acceptare: valori absente și conexiune pierdută, alertă fără dependență exclusivă de culoare, confirmarea vizuală nu șterge cauza alertei.

### E. Relief real și finisare vizuală

- Înlocuirea fundalului mock cu exportul Blender aliniat, fără schimbarea componentelor de rutare.
- Ajustări tipografice, contrast traseu/relief, grosimea liniilor la zoom, opacități, touch, tastatură și reduced-motion.
- Profil de altitudine SVG, chat NDJSON și documentație; ulterior comparație benchmark și Survival Guide.
- După schimbările aplicației: npm run build și verificare vizuală pe mock și cu backend. Fără framework nou de teste.

## Responsabilități și interfețe

| Rol | Responsabilitate pentru plan |
|---|---|
| 1 — Date | GeoTIFF, decupare, pregătire Blender, export cartografic aliniat, clase teren/minerale, imagini ținte, proveniență și scenarii |
| 2 — Algoritmi | Costuri, rute, bugete, limite, forecast, alternative, validare și verdict; definește sensul și unitățile metricilor |
| 3 — Backend | API/WS, control simulare, difuzare către dispozitive, snapshot/reconectare, explicații, contracte noi de telemetrie |
| 4 — Frontend | Dashboard, hartă și suprapuneri, navigator, senzor/status, accesibilitate, performanță și demo |

## Referințe consultate

- Anthropic frontend-design, citit din sursa oficială: https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md — direcție vizuală intenționată, tipografie, ierarhie, două etape plan/execuție. Nu a fost instalat local.
- Catalog Figma dashboard: https://www.figma.com/templates/dashboard-designs/ — consultat.
- Dashboard layout ideas: https://www.figma.com/community/file/1208363071768116045/dashboards-layout-ideas/ — referință găsită în catalogul oficial, pagina individuală blocată de robots.txt.
- Simple dashboard mockup: https://www.figma.com/community/file/1048559673287861086/dashboard/ — aceeași limitare; util ca reper pentru densitate redusă.
- Patterns & layouts UI kit: https://www.figma.com/community/file/1023011749277923602/patterns-layouts-ui-kit/ — referință Goldman Sachs din https://www.figma.com/templates/design-layouts/; pagina individuală blocată.
- Apple watchOS UI kit: https://www.figma.com/community/file/1540060090060216489/watchos-26 — legătură din https://developer.apple.com/design/resources/; pagina individuală blocată. Referință de anatomie a ecranului, nu alegerea unei platforme native.
- USGS: https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_hirise_dtm_mosaic — răspuns 403 la deschidere; produsul este indexat de căutare.
- Documentație oficială HiRISE și licență CC0 pentru colecție: https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms/

Fișierele TIFF indicate de utilizator nu au fost descărcate; nu este generat încă un model Blender. Schița folosește doar coordonatele mock, nu topografie Jezero. Figma nu este conectat; nu au fost importate sau modificate fișiere Figma.
