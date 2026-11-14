# Note rolul 4

## Gata

- Pagina Navigare: dispozitiv tracker robust (ramă groasă, colțuri protejate, șuruburi, grip, taste laterale/frontale) și vizor first-person. Camera urmărește traseul ales, la 1,75 m în coordonatele sursă cu factorul vizual 6×; fără orbitare sau panoramă de sus în vizor.
- Traseul ales în Misiune (inclusiv varianta distanță/pantă) se păstrează în starea App și este transmis navigatorului. În simulare se prioritizează traseul rămas și poziția live; în preview se pot folosi sliderul, pașii de 50/100 m și redarea locală, fără modificarea simulării/O₂.
- Verificat în aplicația Windows: selectare carbonați în Misiune → Navigare păstrează traseul de 4,1 km; preview în mișcare afișează progres, direcție și distanță rămasă coerente. Verificate și funcțiile de interpolare pe traseu, proiecție a poziției și orientare la sosire. Build și ambalare desktop reușite.

- Relief texturat cu albedo/normal/roughness PBR 2048² procedurale, incluse în GLB; geometria sursă de 250000 de puncte și SHA-256 al grilei USGS sunt neschimbate. Umbre PCF, lumină principală caldă, fill discret și tone mapping în aplicația desktop.
- Habitat nou Blender/GLB inspirat de Mars Dune Alpha (NASA CHAPEA / ICON / BIG): pereți cu straturi de imprimare, cinci bolți joase, sas, ferestre, iluminat de acces, zonă EVA și echipamente. Model conceptual, mărit 12× ca marcaj în hartă; camera se apropie la selectarea habitatului. Nu este o reconstrucție arhitecturală certificată.
- Randările pentru relief și habitat inspectate; exportul PBR verificat (3 texturi incluse), build-ul și ambalarea Windows reușite. Încărcarea materialelor/umbrelor verificată vizual în desktop; inspecția camerei apropiate a fost limitată de minimizarea ferestrei de către utilizator.

- Reparat build-ul CI după ce un merge a fost comis cu marcaje de conflict în App.jsx, client.js, BudgetPanel.jsx și DecisionPanel.jsx. Păstrată arhitectura desktop/3D; adăugată compatibilitatea API liveControl, injectEvent cu params și subscribeLive fără callback de status. Reluarea backendului nu mai retrimite route_id (care ar reseta misiunea). `npm run build` trece local; nu s-au rulat comenzi Git care modifică repository-ul.

- Eliminată complet harta 2D din componentă. Vizualizare 3D unică pe desktop și mod compact, cu 250000 de vârfuri CTX native și triangulație comună cu traseele.
- Habitat modelat și etichetat distinct, puncte de interes etichetate/selectabile, raycast pentru selecție liberă, animație top → perspectivă traseu, revenire top și urmărire astronaut.
- Arhiva utilizatorului inspectată fără executare: adaptată logica A* și comparația variantelor la grila reală într-un Web Worker. Referință/documentare în `frontend/design/archive-integration.md`. Clasele sintetice și bugetele presupuse din arhivă nu se folosesc pentru validarea sitului.
- Verificat în aplicația Windows: încărcarea reliefului, etichetele, selecția liberă și perspectiva laterală cu trasee și metrici. Verificări algoritm: cele 3 ținte, un punct liber, teren plat, barieră imposibilă, limită de pantă și comparația distanțelor. Build-ul trece.

- Modelul Blender îmbunătățit la cererea utilizatorului: bază pătrată, pereți laterali, soclu separat, exagerare verticală de prezentare 6× și culori după altitudine. Originalele USGS nu se modifică; păstrate și ca atribut pe mesh. Metadatele GLB sincronizează traseul 3D cu factorul/baza. Preview randat și inspectat vizual.

- Distribuție Windows portabilă creată la `frontend/release/Marswalk-win32-x64/Marswalk.exe`, cu modelul și interfața incluse. Runtime Electron descărcat din release-ul oficial și verificat SHA-256 față de pachetul npm. Ambalare prin script local fără dependențe native suplimentare.
- Procesul aplicației pornește după eliminarea variabilei `ELECTRON_RUN_AS_NODE` injectate de mediul de execuție. Verificarea vizuală a ferestrei desktop nu este încheiată; lansarea de verificare s-a făcut cu WindowStyle Hidden.

- Generat și inspectat vizual `frontend/terrain/jezero.blend`, export `frontend/public/terrain/jezero.glb` (~2,25 MB, 62500 vârfuri) și previzualizare PNG. Verificate structura GLB și dimensiunile grilei. Material neutru, fără ortofotografie; altitudini fără exagerare verticală.
- Build frontend cu renderer 3D încărcat separat și active locale: reușit. Codul desktop trece verificarea de sintaxă Node.

- Continuare desktop/Blender autorizată de utilizator: adăugate Electron, Three.js și GeoTIFF în dependențele frontend (excepție explicită de la înghețarea inițială a pachetelor, necesară noii cerințe).
- Descărcat DTM USGS CTX 20 m și decupat 10 × 10 km la 18,44 N / 77,45 E, în `frontend/public/terrain/jezero.json`: 500 × 500, min −2651,13 m, max −2396,30 m. Sursa are proiecție equirectangulară Mars 2000 Sphere, rază 3396190 m; decupajul nu conține NoData.
- Adăugate pregătirea GeoTIFF, scriptul Blender, rendererul Three.js și fereastra desktop Electron cu server intern loopback și proxy API/WS. Instrucțiuni în `frontend/desktop/README.md`.

- Implementat dashboardul local: planificare, hartă SVG cu pan/zoom, simulare mock și client API/WS, decizii și explicații, buget/altitudine, navigare telefon/ceas, senzori, chat și documentație. Build-ul de producție trece.
- Design actualizat la cererea utilizatorului după Vision UI Dashboard / Billing: navigare laterală, carduri compacte de telemetrie, panouri rotunjite și degrade discret. Paletă negru/cărbune/portocaliu, inclusiv harta, graficele și modurile compacte. Nu s-au adăugat dependențe sau copiat componente MUI.
- Referință: https://demos.creative-tim.com/vision-ui-dashboard-react/#/billing și sursele publice Creative Tim pentru structura sidenav/paletă. Implementare proprie.

- 2026-11-14: analizate toate cele patru roluri, contractele și scheletul frontend.
- Plan în `frontend/design/implementation-plan.md`; concept navigabil în `frontend/design/marswalk-concept.html` (dashboard, telefon, ceas, senzori). Doar design/plan, fără schimbarea aplicației.
- Consultate ghidul oficial Anthropic frontend-design și cataloagele Figma. Paginile individuale Community sunt blocate de robots.txt; integrarea Figma a fost propusă, nu este confirmată.

## În lucru

- Următorul pas cerut explicit: realizarea modelului de relief în Blender din sursele USGS, apoi integrarea în zona hărții. În prezent este afișat doar un fundal schematic etichetat.
- Chrome local: verificată încărcarea noii teme și structura paginii; corectate importurile WorkspaceNavigation/MissionMetrics identificate la rulare. Inspecție vizuală parțială la lățime redusă; verificarea completă desktop/mobil rămâne de încheiat deoarece utilizatorul lucrează simultan în fereastră. Browserul integrat este indisponibil.

## Cereri

- Rolurile 1/2/3: pentru aliniere reală, publicați situl Jezero cu aceleași coordonate/proiecție/decupaj ca `frontend/public/terrain/jezero.json`, sau furnizați transformarea sitului pentru reproiectarea suprapunerilor. Nu folosiți pozițiile mock drept habitat și opriri validate pe acest relief.

- Rolul 1: inspectarea GeoTIFF-urilor USGS și pregătirea renderului Blender ortografic nord-sus, cu aceeași întindere ca grila de 20 m; metadate de transformare, sursă, NoData și versiune. `prepare_dtm.py` nu a fost găsit în repo.
- Rolul 3: propunere snapshot coerent pentru clienți noi/reconectați, identificator misiune, secvență mesaje și prospețime per senzor. Contractele actuale nu conțin starea de mentenanță.
- Rolurile 2/3: definiții și surse pentru praguri/alarmare; sensul măsurătorilor și unități. Temperatura/presiunea de mediu nu descriu costumul.
- Echipa: pentru modelul Blender cerut în pasul următor, livrare .blend + GLB optimizat + metadate de aliniere cu grila; rendererul 3D necesită o dependență aprobată. Exportul ortografic rămâne fallback pentru dispozitive mici, nu substituie modelul 3D cerut.

## Presupuneri

- Relieful CTX este real; traseele/pozițiile din mock sunt încă demonstrative. Nu s-au schimbat pipeline/core sau contractele comune pentru a pretinde validare pe terenul real.
- Desktopul include interfața și modelul local; backendul Python rămâne separat în această etapă. Aplicația folosește tehnologii web intern, dar rulează într-o fereastră Windows proprie.

- Telefonul și ceasul sunt inițial moduri UI web pentru demonstrație; aplicațiile native și senzorii hardware sunt etape separate.
- Navigarea reală cere localizare și heading; mock-urile furnizează poziție simulată, nu orientarea corpului.
- Prevenție MVP = alerte bazate pe reguli și date actuale; mentenanță = stare/jurnal/date de service când backendul le furnizează, fără predicții inventate.
- Nu s-au descărcat GeoTIFF-uri și nu s-a generat relief Blender în etapa de planificare.

- 2026-11-14: redesign Field Operations, inspired by the archive's mission sheet, connected departure/destination rail and prominent return time. Horizontal desktop masthead, compact instrument strip and a map-dominant workbench replace the large dashboard cards. Added expedition.css and MissionSheet; kept the terrain, FPV renderer, route algorithms and data unchanged. Responsive stacking retains the map first on narrow screens. No new dependencies.
- Validation: npm.cmd run build passes (existing Three.js chunk size warning only); portable Electron package refreshed. Native desktop visual QA checked the mission workbench, point selection and animated route perspective, planning panel, tracker page and telemetry. Narrow layout is implemented in CSS but was not visually tested at phone width in this pass.

- Design refinement requested by user: restored the earlier layout with left application navigation, large central terrain and mission panel on the right. Combined the compact telemetry and return clock with rounded surfaces, softer orange accents and regular typography. Removed console registration strips, artificial session labels and ruler decorations. Terrain and route behavior unchanged.

- Implemented equipment dashboard: six illustrated modules, central concept suit with selectable points, responsive dashed connectors, selected-module inspector/trend and separate equipment demo. No measured accuracy or hardware health is fabricated for the mission feed. Optional sensor_health adapter documented in frontend/design/equipment-assets.md.
- Added rugged EVA watch case, strap, dual north-up compass dials and route playback controls. Habitat bearing uses current position independently of the route; mission dial uses the live remaining path or selected preview. Added decorative watch to suit illustration only, without adding a sensor or hotspot. Built-in ImageGen asset and prompt documented in frontend/design/equipment-assets.md.
- Validation: build passes; 12 navigation assertions pass. Native desktop preview verified independent changing habitat/route bearings, distances and suit illustration. Existing large Three.js chunk warning remains.

## Verificarea notelor celorlalte roluri — 2026-11-14

Au fost verificate toate cele patru fișiere Markdown din docs/roles/notes.

- Rolul 1, cererea explicită pentru MissionSheet: fallback-ul eva_start_ltst_h a fost corectat de la 9 la 8. Valoarea din /api/site continuă să aibă prioritate; return_by_min din tick suprascrie bugetul planificat.
- Rolul 1, proveniența straturilor: adăugat panou pliabil Planning data sources în fișa misiunii. Afișează mission, instrument, data_type, source, analog_of și product_id când sunt furnizate. Sursele assumption/synthetic/to verify sunt etichetate distinct; lipsa metadatelor nu devine o sursă inventată. Panoul distinge straturile de planificare de relieful CTX împachetat pentru vizualizarea 3D.
- Rolul 3, start și WebSocket: deja implementat și verificat în cod. useLive deschide abonarea după planificare, butonul Start apelează POST /api/live/control; motorul livrează tick-uri după start și ultimul tick la o nouă abonare. Reluarea nu retrimite route_id. Viteza implicită este 10 minute simulate / secundă reală, trimisă explicit prin control.
- Rolul 2: nu există cereri directe pentru rolul 4 în notele sale. Cererile pentru backend, pipeline și deciziile de calibrare ale echipei rămân la autorii respectivi; nu au fost schimbate constantele sau algoritmii acestora.
- Reamintirea esbuild: build-ul este verificat separat; nu se modifică aprobările scripturilor npm dacă build-ul funcționează.
- Validare pentru această integrare: npm.cmd run build reușit; distribuția Windows portabilă actualizată. Avertismentul existent pentru dimensiunea chunk-ului Three.js rămâne, fără erori de compilare.

- Logo-ul furnizat de utilizator: copiate toate cele patru PNG-uri în frontend/public/images fără modificarea originalelor. Actualizate marca din navigare, ecranul de încărcare, faviconul și iconul ferestrei Electron. Distribuția release rămâne exclusă intenționat prin frontend/.gitignore; instrucțiuni pentru generarea locală și distribuirea întregului folder în frontend/desktop/README.md.

- Adăugat frontend/PORNIRE.md: instalare inițială Windows, două terminale pentru backend/Electron, actualizare după pull, Jezero/sintetic, Ollama opțional, build local și depanare. Comenzile au fost verificate față de package.json, config.py și scripturile curente; nu s-au reinstalat dependențe pentru o schimbare exclusiv de documentație.
- Iconiță nouă: pătrat rotunjit negru-maro cu logo-ul alb și elementele portocalii centrate, generat cu ImageGen din artwork-ul furnizat. Salvat în frontend/public/images/marswalk-app-icon.png, folosit de fereastra Electron și favicon. Build și actualizare pachet desktop reușite; promptul este în frontend/design/equipment-assets.md.

- Curățată imaginea costumului cu ceas prin ImageGen: eliminate resturile semitransparente din colțuri, păstrate proporțiile, poziția și dimensiunea 1024×1536. Dashboardul folosește eva-suit-watch-clean.png; verificarea canalului alpha confirmă transparență zero în cele 64 de probe din colțuri, față de valori semitransparente în imaginea veche.

## Mission Terrain Explorer

### Actualizare: planificare și operațiuni separate

- Follow-up UX: meniu persistent inclusiv în layout compact, waypointuri mutate deasupra hărții, itinerar ordonat cu rutare locală prin punctele salvate și întoarcere opțională la habitat. Tripul poate fi parcurs în preview pe hartă, tracker FPV și ceas.
- Senzorii au acum o singură sursă la nivel App: clock, selecție Mission feed/Equipment demo, stări warning/fault, istoric și valori comune în Sensors și Simulation. O₂ din dispozitive și O₂/vânt din instrumente folosesc aceleași citiri. Defectul nu mai cade înapoi pe o valoare veche.
- FPV netezește direcția înainte relativ la ochi, nu o țintă fixă ce poate rămâne în urmă. Preview-ul păstrează progresul inclusiv la trasee închise cu segmente suprapuse. Spații mai mari între hartă și dispozitive. Build/pachet reușite, 15 teste trecute și verificare nativă pentru trip, pas, senzor defect comun și meniu la scroll.
- Cerere pentru rolul 3: API-ul /api/route acceptă doar stops ca ID-uri din catalog. Pentru waypointuri în misiuni live este necesar suport pentru coordonate/opririle personalizate, validate pe grila site-ului și păstrate în contextul replanificării. Frontendul oferă deja traseu local și preview, dar nu inventează bugete sau verdict GO pentru aceste opriri.

- Trei pagini în aplicația Electron: Planning, Simulation și Sensors. Planning are hartă mare, layere în drawer, legendă, profil de altitudine, catalog științific, planner, buget și puncte cu tag salvate local. Aceeași hartă devine mini-fereastră la scroll. Site Overview și Reference nu mai apar în interfață.
- Simulation afișează harta în stânga și trackerul FPV plus ceasul simultan în dreapta. Poziție comună pentru toate; preview, pas înainte/înapoi și reset sincronizate. Telemetrie sumar sub ele, buton către Sensors și copilot doar în Simulation.
- Limită API păstrată explicit: motorul live nu are seek/reverse. Pașii sunt disponibili în preview; live folosește start/pause/reset/speed și evenimentele existente. Tagurile sunt adnotări locale, nu ID-uri de opriri acceptate de backend.
- Optimizări: cache pentru datele terenului/habitatului, index de distanță reutilizat, obiect de traseu stabil în preview, randare la schimbări și animații, rezoluții adaptate, fără workers de rutare în scenele de tracking/FPV. Nu s-a modificat grila USGS.
- Validare: build reușit, 13 teste Node trecute, verificare nativă Electron pentru PiP, plan, pas sincronizat, reset, start/pauză demo, sumar/detalii senzori, adăugare/eliminare punct și layere. Backend real și Playwright nu au fost verificate end-to-end în această sesiune. Detalii în frontend/design/planning-and-operations.md.

- Implementată cerința atașată: layout cu trei coloane, overview/straturi în stânga, relief central și știință/analiză în dreapta; secțiuni pliabile, toolbar flotant, fit al camerei, reset/follow/fullscreen, marcaje compacte cu ocluzie, scară proiectată și nord orientat după cameră.
- Straturi reale de elevație și pantă derivată din CTX, pericole din tick; minerale/dificultate dezactivate explicit fără raster aliniat. Mesh-ul și grila USGS nu au fost schimbate.
- Profil de altitudine din interpolarea exactă pe triunghiurile reliefului, legat interactiv de un punct pe traseu; rute existente colorate și alternative estompate; detaliile țintelor și preselectarea în planner păstrate. Fără date de risc/O₂ inventate.
- Validare: build reușit, 12 teste Node trecute, verificări native desktop pentru relief, selecție, top/perspectivă, Slope și profil sincronizat. Playwright indisponibil, fără script lint. Detalii, fișiere și limite în frontend/design/terrain-explorer.md.
