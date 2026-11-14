# Îmbunătățiri propuse: evaluare și clasament

Evaluez cele 5 idei din captură și lista de obiecte NASA din Jezero. Criteriile sunt: cât ajută la demo și la jurizare, cât costă, în ce rol intră, și dacă faptele sunt corecte. Am verificat pe surse NASA/JPL/HiRISE și pe articole publicate. Unde nu am găsit sursă, scriu „neverificat”.

## Clasament

| # | Idee | Valoare | Cost | Rol | Verdict |
|---|---|---|---|---|---|
| 1 | Coridoare topologice pentru ocoliri | mare | ~1-2 h, în R2-10 | 2 (tu) | **Fă-o.** Scena din README cere deja „nord vs sud”. |
| 2 | Alerte vocale (Audio HUD) | mare la demo | ~1 h | 4 (frontend) | **Fă-o**, cu buton de activare. |
| 3 | Umbră radio (line-of-sight) | mare ca profunzime | ~3 h, pas nou R2-12 | 2 (tu) | **Fă-o după R2-10.** Merge cu adevărat doar pe relief real. |
| 4 | Repere NASA reale pe hartă | mediu spre mare | 20 min - 2 h | 1 + 4, cu acord pe contract | **Versiune minimă.** Doar obiectele verificate. |
| 5 | Furtuni cu fizică corectă (tau, soare, nu vânt) | mic ca cod, mare ca text | ~30 min, fără cod nou la tine | 1 + 3 | **Doar text și parametri.** Nu un model nou. |

Ordinea la tine: 1 în R2-10, apoi 3. Ideea 2 o dai colegului de frontend. Ideile 4 și 5 sunt de echipă.

---

## 1. Coridoare topologice pentru ocoliri (prioritate 1)

**Ce e deja în plan.** `alternatives.generate` trebuie să dea 1-3 ocoliri. README-ul (scena de demo) promite „ocolire nord +25 min” și „ocolire sud +40 min”. Dacă ocolirile ies din A* cu presetări diferite, riști trei trasee aproape identice, iar demo-ul pierde sensul.

**Propunere concretă (fără dependențe noi):**
1. Din starea hazardului iei elipsa și direcția traseului curent.
2. Pui câte un waypoint pe fiecare parte a elipsei: perpendicular pe traseu, la distanța `semi-axa mare + margine`.
3. Rulezi `astar(start → wp → țintă)` pentru fiecare parte. Costul se calculează pe harta care are hazardul ca `inf`.
4. Etichetezi „nord/sud” (sau „stânga/dreapta”) după semnul produsului vectorial, nu după coordonate fixe.
5. Verifici că variantele sunt distincte: suprapunere de celule sub 50% (Jaccard) sau distanță medie între trasee peste 2 × lățimea elipsei împărțită la 4. Dacă nu, elimini duplicatul.

**Teste:** grilă 30×30 cu hazard în mijloc. Aștepți exact 2 ocoliri pe părți opuse, ambele ocolesc elipsa, id-uri stabile, rezultat identic la două rulări.

**De ce înainte de LOS:** e deja în sarcina ta și îți dă singurele alternative care arată bine pe hartă.

---

## 2. Alerte vocale prin `speechSynthesis` (prioritate 2, rol 4)

- Browserul are API-ul gata, fără server și fără bibliotecă: la mesajul `explanation` apelezi `speechSynthesis.speak(new SpeechSynthesisUtterance(text))`.
- Vorbești **doar la schimbarea deciziei**, nu la fiecare tick. Înainte de fiecare mesaj nou apelezi `speechSynthesis.cancel()`, ca să nu se suprapună.
- Pune un **buton „Audio ON/OFF”**. Unele browsere cer o acțiune a utilizatorului înainte de a permite sunetul, iar clicul pe buton o oferă. (Comportamentul exact diferă între browsere; testează în cel pe care îl folosiți la demo.)
- Setezi `lang` după limba explicației (`ro-RO` sau `en-US`). Vocile disponibile depind de sistemul de operare, deci **verifică pe laptopul de demo** că există o voce potrivită. Dacă nu, folosește engleza în video.
- Pe jurizare globală, doar materialele trimise contează. Audio-ul se vede în video doar dacă îl înregistrezi cu sunet.

Nu atinge contractele: `explanation` există deja în `live_messages.json`.

---

## 3. Umbră radio / line-of-sight (prioritate 3, pas nou R2-12)

**Ce face:** calculează, din `elevation.npy`, celulele din care astronautul **nu vede** antena habitatului. Copilotul poate spune „în 12 min intri în zonă fără comunicații”.

**Fizică verificată de mine (nivel B, calcul propriu):**
- Marte are raza ≈ 3389,5 km. Orizontul pentru o antenă la 2 m e √(2·R·h) ≈ **3,7 km**. Între doi corespondenți la 2 m, linia dreaptă se oprește la ≈ **7,4 km** chiar pe teren perfect plat. Cu un catarg de 5 m la habitat, ≈ 9,5 km. Deci curbura trebuie inclusă. Pe harta de 10 km nu e neglijabilă (scădere ≈ 3,7 m la 5 km).
- Înălțimile antenelor sunt **presupuneri (C)**; arhitectura reală de comunicații (releu, rover, orbitere) nu o cunoaștem.

**Algoritm (numpy, fără scipy):**
- Pentru K raze de azimut (ex. 720), iei profilul de elevație cu pași de o celulă din habitat, scazi curbura `d²/(2R)` și calculezi unghiul de ridicare `(z − z_hab − h_ant) / d`.
- Celula e vizibilă dacă unghiul ei ≥ maximul cumulat (`np.maximum.accumulate`) al celulelor dinaintea ei.
- Rezultat: `visible` boolean 500×500, calculat o dată per sit și pus în cache ca `static_cost`. Țintă: < 0,2 s.

**Integrare fără a schimba contracte înghețate:**
- Variantă ușoară: `budget`/`planner` calculează `comms_loss_min` pe traseu (minute în umbră). Câmpul se adaugă la `Budget` cu valoare implicită și la „Cereri”, ca rolul 3 să-l poată citi.
- Variantă cu cost: termen mic `w_comms` în `static_cost` pentru presetul `safe`. Atenție la testele existente de costmap.
- **Nu** adăuga un cod nou de încălcare în validator fără acord: contractul listează codurile.

**Limită onestă:** pe situl sintetic, cu doar ~1,3% din celule peste 25°, umbrele vor fi mici. Pe relief real (marginea deltei, craterul) vor fi vizibile. Dacă vrei efectul în demo cu date sintetice, rolul 1 trebuie să facă un front de deltă mai abrupt.

---

## 4. Repere NASA reale pe hartă (versiune minimă)

### Ce am verificat

| Afirmație din propunere | Verdict | Ce am găsit |
|---|---|---|
| Punctul de aterizare Octavia E. Butler la 18,447°N, 77,452°E | **Aproape corect** | Surse publice dau 18,4447°N, 77,4508°E. Se potrivește cu centrul vostru 18,44 / 77,45. |
| Three Forks, 10 tuburi, la baza deltei | **Corect** | 10 tuburi: 7 carote de rocă, 1 regolit, 1 atmosferă și 1 martor (blank). Depozit pe teren plat lângă baza deltei (NASA, Herd et al. 2025). |
| Three Forks la 18,453°N, 77,408°E | **Neverificat** | Nu am găsit coordonate publicate. Dacă sunt corecte, ar fi la ~2,4 km vest de aterizare, ceea ce e plauzibil, dar nu e o sursă. Ia coordonatele din harta NASA a depozitului (PIA25682). |
| Ingenuity la „Airfield Sigma”, 1,5-2 km NV de deltă | **Greșit** | Zborul 72 a fost către și dinspre „Airfield Chi” din Valinor Hills. Poziția din jurnalul de zbor: ≈ 18,50°N, 77,32°E (sursă secundară care citează NASA). Asta e la **~8 km** de aterizare, **în afara pătratului de 10×10 km** (care se oprește la ~77,36°E). |
| Ingenuity „prăbușit” | **Nuanțat** | NASA: aterizare dură cu pale deteriorate. Elicopterul stă pe toate cele patru picioare, nu a fost distrus. Încă mai poate transmite date. |
| Parașuta și backshell „2 km la nord, 18,47°N 77,45°E” | **Imprecis** | Sursele diferă: ~1,1 km (imagine de la rover), „aproape o milă” (Wikipedia), „câteva mile spre NV” (Spaceflight Now). Direcția e spre vest/nord-vest, nu spre nord. |
| Sky Crane la ~670 m NV | **Direcția e corectă, distanța neverificată** | A zburat spre nord-vest și s-a prăbușit la distanță sigură, cu o dâră în V. Nu am găsit cifra de 670 m. |
| Scutul termic la ~1,5 km SE | **Direcție aproximativă, distanță neverificată** | Imaginea HiRISE îl arată în partea dreaptă (est) a rover-ului. Nu am găsit distanța. |
| Hidrazină reziduală, „zonă de evitat” | **Neverificat** | Extrapolare rezonabilă, nu fapt citat. Dacă o folosiți, marcați-o ca presupunere (C). |
| Greutăți de tungsten de 77 kg în crater de ~6 m lângă aterizare | **Greșit** | Cele două blocuri de 77 kg au fost aruncate sus, în afara atmosferei. Craterele (3-5 m) sunt la nord-vest de Jezero, departe de aterizare. Nu le puneți pe hartă. |
| Perseverance încă activ pe marginea craterului | **Corect** | Depinde de data prezentării; nu îl marcați ca obiect fix. |

### De ce contează erorile
Jurații NASA cunosc misiunea. Un marker pus greșit costă mai mult credibilitate decât câștigă efectul.

### Problema de fond cu situl sintetic
Pe un teren **sintetic**, coordonatele reale nu au sens: dealul „deltei” de pe harta voastră nu e delta reală. Obiectele reale se potrivesc doar pe date reale (HiRISE DTM). Pe sintetic, le marchezi ca „poziții ilustrative”.

### Versiunea minimă recomandată
1. **Three Forks ca țintă normală** în lista `targets` (fără câmp nou în contract). `kind` e un șir liber în exemple, dar verifică în `site_data` și în codul care citește `kind` că o valoare nouă (`sample_depot`) nu e respinsă.
2. Habitatul pus la punctul de aterizare real. Povestea: „baza echipajului e unde a coborât Perseverance, depozitul e la ~2,4 km”. E o ieșire de câțiva km, exact scara EVA-ului vostru.
3. Doar dacă mai aveți timp: un strat „Hardware NASA” cu 2-3 markere **verificate** (aterizare, Three Forks, backshell/parașută cu eticheta „aprox.”), fără Ingenuity (în afara hărții) și fără tungsten.
4. Formulare prudentă pentru Mars Sample Return: nu am verificat starea actuală a programului. Scrieți „scenariu inspirat de depozitul de probe Three Forks”, nu „legat de misiunea MSR în curs”.

### Dacă vreți un array `artifacts` în `meta.json`
E o schimbare de contract (fișiere înghețate, acord obligatoriu al tuturor rolurilor, plus frontend care îl desenează). Contractul folosește celule `row/col`, nu lat/lon, deci rolul 1 trebuie să convertească:

```
m_per_grad  = 2π · 3389,5 km / 360 ≈ 59,157 km
dy_m = (lat − lat_centru) · 59157          # nord = pozitiv
dx_m = (lon − lon_centru) · 59157 · cos(lat)
row  = 250 − dy_m / 20                     # row crește spre sud
col  = 250 + dx_m / 20
```

Pătratul de 10×10 km centrat la 18,44°N / 77,45°E acoperă ≈ 18,356-18,525°N și 77,361-77,539°E.

---

## 5. Furtuni cu fizică corectă (doar text și parametri)

**Ce e corect în propunere:** vântul nu e pericolul mecanic. Presiunea dinamică `q = ½·ρ·v²`, cu ρ ≈ 0,016 kg/m³ (P ≈ 720 Pa, T ≈ 240 K), dă la 25 m/s ≈ **5 Pa**, iar la 45 m/s ≈ **16 Pa**. Pe Pământ, la 25 m/s, e ≈ 375 Pa. Deci vântul marțian e de zeci de ori mai slab la aceeași viteză (calcul propriu, nivel B).

**Ce e slab fundamentat:** „prăbușirea vizibilității pe teren accidentat”. Opacitatea `tau` e pe toată coloana atmosferei, nu la nivelul solului. O estimare grosieră (nivel C): vizibilitatea ≈ 3,9·H/τ cu H ≈ 10 km dă ≈ 78 km la τ=0,5 și ≈ 8 km la τ=5. Pierderea reală de vizibilitate la scara omului apare doar în plume dense, locale.

**Pericolele reale, de formulat în explicații:** praful (uzura și contaminarea costumului), lumina mai slabă (temperatură, energie la habitat), navigația și comunicațiile degradate. Un vârtej mare de praf are vânt intern până la ~25 m/s și poate avaria senzori [vezi `PARAMETRI_REFERINTA.md`, S17].

**Ce faci concret (zero cod nou la rolul 2):**
- Rolul 1: în `scenario.py`, evenimentul `local_storm` să fie un **vârtej mare** (100-135 m), nu o furtună de 1,8 × 1,1 km. Asta era deja pe lista de corecții din `PARAMETRI_REFERINTA.md`.
- Rolul 3: șabloanele de explicație să nu spună „vânt periculos”, ci „zonă cu praf și vizibilitate redusă”.
- Nu adăugați o variabilă „energie solară”: modelul vostru nu are un consumator care să depindă de ea.

---

## Surse verificate

- Three Forks, hartă și descriere: https://www.jpl.nasa.gov/images/pia25682-perseverances-three-forks-sample-depot-map/ și https://science.nasa.gov/?p=1008066
- Conținutul depozitului (9 tuburi + 1 martor), Herd et al. 2025: https://pmc.ncbi.nlm.nih.gov/articles/PMC11745317/
- Componentele de aterizare în imaginea HiRISE: https://www.jpl.nasa.gov/images/pia24333-perseverance-and-mars-2020-spacecraft-components-on-the-surface/
- Direcții pentru parașută, scut termic și treapta de coborâre: https://spaceflightnow.com/2021/03/05/mars-reconnaissance-orbiter-camera-spots-perseverance-rover-after-landing/
- Coordonatele aterizării: https://en.wikipedia.org/wiki/Mars_2020
- Ingenuity, Valinor Hills și Airfield Chi: https://en.wikipedia.org/wiki/Ingenuity_(helicopter) ; poziția ≈ 18,50°N 77,32°E: https://marsprogress.com/missions/ingenuity/ (sursă secundară)
- Ingenuity rămâne pe picioare, aterizare dură: https://www.yahoo.com/tech/nasas-ingenuity-helicopter-opened-mars-124924253.html
- Greutățile de tungsten Mars 2020: https://meetingorganizer.copernicus.org/EPSC-DPS2025/EPSC-DPS2025-1780.html și https://www.sciencealert.com/nasa-punched-5-holes-into-mars-the-craters-revealed-a-surprise

Calculele marcate „nivel B/C” (orizont radio, presiune dinamică, vizibilitate) sunt ale mele, din formule standard, și trebuie tratate ca estimări.
