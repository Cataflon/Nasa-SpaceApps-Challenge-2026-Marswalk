# Marswalk — contract de integrare frontend / backend / algoritm

Versiune de proiectare: **1.1**, 14 noiembrie 2026. Aplicația rămâne Electron.

**Statut:** document de implementare și predare către rolurile 2 și 3. Secțiunile „1.1” sunt cerințe propuse, nu endpointuri deja implementate. Contractele curente din `shared/contracts/` rămân sursa de compatibilitate pentru API-ul actual. Nu au fost modificate backendul, algoritmul sau fișierele shared prin această actualizare.

Artefacte asociate: [schema cererii 1.1](route-request-v1.1.schema.json), [exemple JSON](examples.json). Schema verifică structura; regulile dependente de teren, ID-uri și starea misiunii se validează semantic în backend.

## 1. Responsabilități și limite

| Componentă | Responsabilitate |
|---|---|
| Frontend | Selecții, waypointuri locale, ordonare, formulare, validare preliminară, camere, layere, preview, prezentarea datelor primite |
| Backend / rol 3 | Validare autoritativă, versiuni/site, registru de planuri și misiuni, controale, evenimente, WebSocket, erori, integrarea senzorilor |
| Algoritm / rol 2 | Rutare, fezabilitate, bugete O₂/timp/doză, ordinea opririlor, alternative, replanificare și motivarea deciziei |
| Date / rol 1 | Grile aliniate, rezoluție, nodata, proveniență, incertitudine și praguri justificate |

Preview-ul local A* folosește altitudinile sursă și limita locală de pantă; nu poate emite un GO pentru viața astronautului. Numele/tagul unui waypoint nu dovedește existența unui adăpost sau a unui pericol. Frontendul nu inventează precizie măsurată ori diagnostic hardware.

## 2. Workflow complet

1. Deschidere aplicație: citește site-ul și, după implementarea extensiei, capabilitățile și revizia terenului. Fără backend, afișează explicit demonstrație.
2. Planning: explorare teren → selecție → nume/tag → salvare waypoint. Site-urile științifice și punctele proprii pot fi selectate în Mission plan. Trip itinerary păstrează o ordine vizibilă.
3. Preview local: unește segmente habitat → opriri → habitat opțional; arată profil și măsurători geometrice. Fără verdict/buget de misiune.
4. Plan validat: trimite cererea 1.1; backendul validează punctele, construiește contextul algoritmului, calculează traseul/bugetele și salvează contextul sub `route_id`. UI afișează rezultatul numai dacă răspunsul corespunde cererii și reviziei curente.
5. Open simulation: aceeași cale și aceeași poziție sunt consumate de hartă, FPV și ceas. Preview poate fi derulat/resetat fără schimbarea telemetriei.
6. Start EVA: cere explicit pornirea planului validat. WebSocket furnizează poziția, resursele, senzorii și pericolele. Resume continuă sesiunea, nu creează o misiune nouă.
7. Inject event: formularul validează câmpurile; backendul validează din nou și confirmă aplicarea. Replanificarea produce o nouă revizie de cale, cu aceleași opriri proprii în context.
8. Copilot: status compact deasupra hărții, detalii la cerere când există o decizie. Nu există flux de chat „Ask the copilot”. Explicația asincronă se atașează prin `decision_id`.
9. Sensors: detalii pe același flux folosit de sumar, tracker și ceas. Schimbarea paginii nu recreează senzorii, sursa sau ceasul demo.
10. Pause ține poziția. Reset șterge starea de rulare, evenimentele și istoricul misiunii, păstrând planul inițial. Un plan nou nu suprascrie o misiune running/paused fără reset explicit.

## 3. Coordonate, timp și versiuni

- `shape = [rows, cols]`. Origine nord-vest; row crește spre sud, col spre est. Un punct de plan este o pereche de indici întregi în `[0, rows-1] × [0, cols-1]`.
- Calea JSON este `[[row,col], ...]`, niciodată `[x,y]`. Poziția live poate fi fracționară. Interpolarea trebuie să rămână pe segmentul curent al căii, inclusiv când dusul și întorsul se suprapun.
- `cell_size_m` este distanța pe sol. Distanțele, elevațiile, semiaxele și ascensiunea sunt în metri sursă. Exagerarea verticală 6× și grosimea bazei sunt numai pentru afișare; nu intră în costuri/pante/bugete.
- Pentru calcul geometric: x = col × cell, y = row × cell în planul terenului; centrul celulei folosește offsetul +0,5 conform algoritmului. Rendererul poate translata originea în centrul mesh-ului fără să schimbe indicii.
- Bearing: 0° nord, 90° est, sens orar. `angle_deg` al pericolului are altă referință: semiaxa A se măsoară **de la est, în sens orar spre sud**, conform `core/hazards.py`.
- `velocity_ms = [south_m_s, east_m_s]`. `axes_m = [semi_axis_a_m, semi_axis_b_m]`, nu diametre.
- `t_min` este timpul simulat în minute de la începutul scenariului; `speed` este minute simulate / secundă reală, între 1 și 60. Nu amestecați `t_min` cu ora locală a calculatorului.
- Ora recepției este afișată o singură dată în blocul de telemetrie. 1.1 adaugă `sent_at` ISO-8601 UTC, `mission_id`, `seq`, `route_revision`, `terrain_revision` și `source` la mesajele live.
- `terrain_revision` trebuie să identifice determinist datele și transformarea (manifest/revizie sau hash), nu doar numele Jezero. Dacă grila algoritmului diferă de grila modelului, serverul trebuie să publice transformarea și limitele; clientul nu presupune că doi indici egali descriu aceeași poziție.

## 4. API existent și extensii necesare

| Resursă | Disponibil acum | Cerință 1.1 |
|---|---|---|
| GET `/api/site` | shape, cell_size_m, habitat, targets și metadate | revizie, nodata, proveniență și transformare explicită |
| GET `/api/capabilities` | Nu este implementat | negociere custom_stops, ordered_stops, event_parameters, sensor_health, seek/reverse |
| POST `/api/route` | start, stops ca ID-uri de catalog, preset, durată, retur | opriri proprii, ordinea cerută, revizii și client_request_id |
| POST `/api/live/control` | start/pause/reset/speed | identitate sesiune, ACK și reguli de tranziție explicite |
| POST `/api/live/event` | event + params arbitrar în schemă | validare pe tip, ACK de aplicare, ID și erori pe câmp |
| WS `/api/live` | tick/decision/explanation/event | snapshot la reconectare, seq și delimitarea sesiunilor |
| GET `/api/point` | citire metadate punct, când disponibil | valori/sursă/incertitudine per layer și revizia grilei |

Extensia capabilities este propusă. Frontendul actual nu face încă această negociere și nu trimite cererea 1.1. Până la integrarea backendului, selecțiile proprii din Mission plan generează preview local. Nu trimiteți `note_*` ca ID de catalog către API-ul actual.

## 5. Planning — cerere 1.1

Exemplul complet este `examples.json:route_request` și respectă schema asociată.

- `stops` este lista ordonată de ID-uri, amestec de catalog și custom. `custom_stops` conține definițiile pentru ID-urile proprii referite.
- Fiecare custom stop are `id`, `name`, `row`, `col`, `tag`, `dwell_min`. Nu există un scor științific arbitrar dat de utilizator. Algoritmul acordă valoare zero sau o valoare calibrată și justificată de date.
- `stop_order: request` obligă algoritmul să viziteze opririle în ordine. `optimize` permite schimbarea ordinii, dar răspunsul trebuie să o returneze explicit. Nu optimizați ordinea în tăcere.
- Backendul respinge ID-uri duplicate, coliziuni cu catalogul, definiții lipsă, coordonate în afara site-ului, celule nodata/blocate, tag-uri necunoscute și durate invalide. Maximum 100 opriri. Nume de maximum 60 caractere, fără markup executabil.
- Nu înregistrați punctele clientului global în catalog. Construiți un overlay/context imutabil per plan și păstrați-l în RouteStore; engine și replanificatorul trebuie să folosească același overlay. O ștergere locală nu schimbă retroactiv o misiune deja pornită.
- `tag: shelter` rămâne candidat neconfirmat; nu devine refugiu sigur. `tag: hazard` nu înlocuiește un eveniment spațial validat.
- Planificarea se face pe sursa de elevație și straturile aliniate, cu return_to_habitat, buget complet, limite de pantă, lumină, O₂ și doză. O legătură inaccesibilă nu poate fi înlocuită cu o linie dreaptă sau cu ruta demo.
- Pentru custom stops, un backend fără suport întoarce eroare explicită; nu răspunde 200 cu o rută înregistrată care ignoră punctele.
- Aliniați orizonturile: formularul actual permite maximum 1440 min, dar motorul live are `MAX_DURATION_MIN = 720`. Capabilities trebuie să publice limita efectivă de simulare; până la aliniere, backendul respinge explicit un plan care ar necesita rulare dincolo de orizont sau îl marchează neexecutabil. Nu promiteți o EVA de 24 h care se termină automat după 12 h.

### Răspuns route 1.1

Păstrați câmpurile curente: `route_id`, `preset`, `path`, `stops`, `budget`, `point_of_no_return`, `elevation_profile`, `verdict`. Adăugați identitatea/reviziile cererii și `validation_status: validated | partial | unavailable`.

Fiecare oprire rezolvată trebuie să includă `id`, `name`, `row`, `col`, `source: catalog | custom`, `index_in_path`, `eta_min`, `dwell_min`, `visit_order`. `index_in_path` trebuie să distingă vizitele în puncte suprapuse. Ordinea și dwell sunt comune plannerului, FPV-ului și motorului.

| Câmp buget | Unitate / semantică |
|---|---|
| distance_m | distanța completă a planului, inclusiv returul cerut |
| duration_min | mers + toate staționările + întârzieri planificate |
| o2_start_pct / o2_end_pct | procente 0–100, cu rezerva documentată |
| dose_msv | doză integrată pe întregul plan |
| return_by_min | termenul de întoarcere pe aceeași axă temporală |
| sunset_min | apusul site-ului/scenariului, nu o constantă de UI |

`elevation_profile` are distanțe cumulative monotone, valori sursă neexagerate și același capăt ca path. `GO | CAUTION | NO-GO` trebuie însoțit de coduri de încălcare și ipoteze. Un plan parțial sau nevalidat nu poate porni o EVA validată. Nu folosiți zero pentru o metrică absentă: folosiți null și motivul indisponibilității.

## 6. Algoritm — interfață internă cerută

Input logic: context site/revizie, grile aliniate și măști nodata, poziție inițială, opriri rezolvate și ordinea lor, preset, timp de start, durată maximă, retur, limite calibrate, starea costumului și scenariul curent.

Output logic: path, leg-uri per oprire, bugete, profil, verdict + încălcări, proveniență/ipoteze și motivarea alegerii. Dacă o oprire devine inaccesibilă, raportați explicit stop_id și motivul; nu o eliminați fără decizie vizibilă.

La replanificare, inputul include opririle încă nevizitate și contextul custom al planului, resursele **actuale**, poziția actuală, pericolele actuale/predicții și staționarea în curs. Alternativele trebuie să declare validitatea, încălcările și bugetele pe aceeași bază de comparație. Ruta aleasă începe din poziția actuală, fără teleportare.

Deciziile rămân `CONTINUE | REROUTE | WAIT | RETURN | EMERGENCY`. Pentru WAIT se publică durata și condiția de reevaluare; pentru RETURN se publică ruta către habitat; EMERGENCY include motivul și acțiunea recomandată. Nu tratați o simplă notă shelter ca soluție de urgență validată.

## 7. Simulare și sincronizare

| Stare | Comandă permisă | Rezultat cerut |
|---|---|---|
| idle | start cu route_id validat | running, poziție inițială, snapshot |
| running | pause | paused la poziția curentă |
| paused | start fără route_id nou | running în aceeași mission_id |
| running/paused | speed | schimbă rata, păstrează progresul |
| idle/running/paused/finished | reset | idle, curăță scenariul și istoricul rulării |
| finished | start | respins până la reset |

Backendul trebuie să confirme controlul cu `ok`, `state`, `t_min`; 1.1 adaugă mission_id, route_id, speed și command_id. Comenzile cu același command_id nu se aplică de două ori. Speed nu avansează timpul când misiunea este paused.

**Nu există seek/reverse live în API-ul actual.** Pasul înainte/înapoi și sliderul sunt doar preview. Capabilitățile trebuie să rămână false până la implementarea unui snapshot/replay determinist cu restaurarea completă a senzorilor, resurselor și evenimentelor.

Tick-ul curent conține astronaut, remaining_path, sensors, hazards, budget și t_min. Backendul este autoritatea poziției live. Clientul interpolează pentru randare, fără să consume resurse. Pe pauză sau deconectare îngheață interpolarea. Un remaining_path cu un singur punct înseamnă sosire, nu eroare.

## 8. Evenimente — payloaduri și validare

Corpul curent este `{event, params}`; exemplele sunt în JSON. Câmpurile de mai jos sunt cele citite de motor; limitele UI sunt garduri tehnice, nu praguri științifice validate.

| Tip | Parametri expuși |
|---|---|
| local_storm / regional_storm / dust_devil / marsquake | center {row,col}, axes_m [a,b], angle_deg, intensity, velocity_ms [south,east] |
| solar_particle_event | dose_rate_multiplier, duration_min |
| suit_leak | leak_pct_per_min, pierdere suplimentară de puncte procentuale O₂/min |
| fatigue | speed_factor, multiplicator al vitezei, nu procent |

Validare: numere finite; centru în teren; a,b între 1 și 100000 m; unghi 0–360°; intensitate 0–1; viteze -100–100 m/s; multiplicator doză 1–100; durată 1–10080 min; pierdere O₂ 0,001–10 pp/min; factor viteză 0,01–1. Backendul trebuie să restrângă aceste limite dacă modelul calibrat cere asta și să publice schema/limitele prin capabilities.

Un centru explicit este important: logica implicită poate plasa pericolul înaintea astronautului și folosește alte valori de scenariu. Cererea UI trimite centru și toți parametrii spațiali. Nu confundați raza cu diametrul; nu aplicați exagerarea verticală.

Extensie 1.1: ACK cu `event_id`, `accepted`, `applied_t_min`, `effective_params`, mission_id. Confirmați separat acceptarea și aplicarea; logul WebSocket include aceleași event_id și effective_params. Respingeți chei necunoscute/incompatibile, valori invalide și injectarea fără misiune activă. Nu aplicați parțial un payload invalid.

Demo-ul frontend folosește scene înregistrate: nu garantează aplicarea parametrilor editați. UI spune explicit acest lucru. Testarea parametrilor fizici se face cu backendul real.

## 9. Senzori — un singur flux pentru toate paginile

| Cheie | Unitate | Interpretare |
|---|---|---|
| o2_pct | % | rezerva estimată de O₂, 0–100 |
| dose_rate_usv_h | µSv/h | rată externă de doză, ≥0 |
| dose_total_msv | mSv | doză acumulată, ≥0; nu rată |
| temp_c | °C | temperatură ambientală, ≥-273,15 |
| pressure_pa | Pa | presiune atmosferică, ≥0; nu presiunea costumului |
| wind_ms | m/s | viteză vânt, ≥0 |
| dust_tau | adimensional | opacitate optică, ≥0 |

`sensor_health` opțional este indexat după aceeași cheie. Per canal: `state: ok | warning | fault`, `message`, `accuracy: {value,unit} | null`. Precizia este o incertitudine absolută documentată, nu un scor de încredere inventat din valoare. Lipsa diagnosticului înseamnă doar „Plausible”, nu „Nominal”.

- Fault: valoarea afișată este indisponibilă peste tot, inclusiv tracker/ceas. Nu se revine la o citire veche fără marcaj de staleness.
- Warning: valoare vizibilă cu motivul; dacă este invalidă pentru analiză, se exclude din trend și decizii. Backendul trebuie să publice validitatea și calitatea per eșantion pentru a permite asta fără euristici.
- Link pierdut: se păstrează ultima valoare cu stare stale/warning și ora recepției; nu se generează eșantioane zero.
- Demo: sursă comună în App, diagnostic simulat și istoric separat de misiune. Selectarea demo nu injectează măsurători în backend.
- Flux real 1.1: publicați sampled_at și un identificator de eșantion; sumarul și pagina detaliată trebuie să arate același eșantion/precizie/stare. O singură afișare a orei recepției per bloc este suficientă.

## 10. WebSocket, reconectare și erori

1.1 păstrează tipurile existente și adaugă un envelope comun: schema_version, mission_id, seq, t_min, sent_at, source și route_revision. Clientul ignoră mesaje din altă misiune, duplicate și revizii depășite. t_min poate rămâne identic pentru decizie/explicație; ordinea este dată de seq.

La abonare/reconectare trimiteți snapshot atomic cu state, plan/revizie activă, poziție, senzori, buget, pericole, opriri vizitate și ultima decizie. Un reset/new mission are identitate nouă sau eveniment explicit; t_min mai mic fără delimitare nu trebuie confundat cu un mesaj întârziat. Explicațiile se leagă numai prin decision_id; pot sosi mai târziu fără a schimba ruta.

Coduri propuse: 400 cerere incompatibilă; 404 site/route/session lipsă; 409 misiune activă/revizie veche; 422 câmp sau oprire invalidă/inaccesibilă; 503 serviciu indisponibil. Formatul este `examples.json:error`. Păstrați compatibilitatea cu `detail` în adaptorul client până la migrare.

Erorile de validare 4xx nu declanșează fallback demo. Căderea serviciului poate oferi mod demo etichetat, dar nu poate transforma un plan custom invalid într-un GO înregistrat. Cererile anulate/vechi nu suprascriu planul curent.

## 11. Livrare și criterii de acceptare

1. Rol 1: manifest de grile, revizie, nodata, transformări și proveniență.
2. Rol 2: suport intern pentru opriri rezolvate/custom, ordine explicită, leg-uri și propagarea lor în replanificare; teste pe bugete/fezabilitate și trasee dus-întors suprapuse.
3. Rol 3: schema 1.1, validare semantică, context per route, capabilities, ACK-uri, snapshot și erori. Adăugați suportul înainte de a publica custom_stops=true.
4. Rol 4: negocierea capabilities, serializarea 1.1 și consumul identităților/reviziilor, cu retragerea fallbackului local numai când serverul confirmă suportul. Această migrare de wire protocol nu este încă implementată.

Acceptare comună obligatorie:

- Plan cu sit + două waypointuri în ordinea cerută, retur opțional, opriri și ETA corecte, profil și buget pentru aceeași cale.
- Punct în afara grilei/nodata sau inaccesibil: eroare pe câmp/stop_id, fără rută substituită.
- Start → Pause → Resume: aceeași poziție și mission_id; Speed nu resetează; Reset revine la planul inițial.
- Furtună cu centru și raze distincte: geometria și viteză din UI coincid cu effective_params și câmpul algoritmului; replanificarea păstrează opririle custom.
- O₂ warning/fault apare identic în ambele pagini și pe dispozitive; precizia absentă rămâne necunoscută.
- Deconectare/reconectare: fără salt la o cale veche, fără duplicarea evenimentelor, fără doză/O₂ resetate accidental.
- Datele de afișare 6× nu schimbă costurile sau pantele; angajamentul de latență/FPS se măsoară separat pe hardware țintă, nu se deduce din build.

Comenzile de verificare frontend sunt documentate în `frontend/design/planning-and-operations.md`. Testele frontend nu înlocuiesc testele de integrare backend/algoritm cerute mai sus.
