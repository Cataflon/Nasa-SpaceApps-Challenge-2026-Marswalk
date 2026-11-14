# Hazardurile unei ieșiri pe jos la Jezero: ce avem și ce lipsește

Document intern al echipei (rolul 1), 14.11.2026. Pentru fiecare hazard: cât durează, cât de periculos e, ce trebuie făcut și cum apare în aplicație. Sursele sunt la final, majoritatea NASA/JPL.

**Cât de sigure sunt cifrele:**
- ✔ = citit de noi direct în sursă (pagina NASA sau textul complet din NTRS), aceleași valori ca în `PARAMETRI_REFERINTA.md`;
- fără ✔ = preluat din rezumatele surselor găsite la căutare, nu citit încă pe pagină. Trebuie verificat înainte să apară pe un slide.

---

## 1. Hazardurile implementate

### Evenimente live (lista din `shared/contracts/live_event.json`)

| Hazard | Cât durează | Cât de periculos | Ce trebuie făcut | În aplicație |
|---|---|---|---|---|
| **Vârtej de praf** | trece în secunde-minute. Se formează 1,3-3,4 / km² / sol, mai ales la 12-13 (ora solară locală); diametru mediu 29 m, cele mari peste 100 m ✔ | **Mic → mediu.** Cele mici nu contează; cele mari au vânt puternic și praf. În 2025, Perseverance a înregistrat descărcări electrice (scântei) în vârtejuri. | Ignori vârtejurile mici; pe cele mari le ocolești sau aștepți să treacă. Eviți ieșirile la prânz. | ✅ ocolire (REROUTE), cu con de predicție |
| **Front de furtună locală** | trece peste astronaut în minute, dar furtuna ține zile. Celulele au 20-40 km, vântul peste ele ajunge la 140 km/h ✔ | **Mediu → ridicat.** Vizibilitate aproape zero, praf în costum, nu se poate ocoli. | Dacă ajungi la habitat înaintea frontului, pleci imediat. Altfel stai pe loc până trece, apoi te întorci. | ✅ întoarcere imediată (EMERGENCY) |
| **Furtună regională / globală** | săptămâni; cea globală, luni. Cea din 2018 a acoperit planeta ~4 luni, cu opacitate ~11 (record); scăderea a durat ~43 de soli. | **Ridicat.** Întuneric, frig, nu se mai poate lucra afară; rover-ul Opportunity a murit în ea. | Nu pleci dacă se anunță din orbită. Dacă te prinde afară, te întorci imediat. | ✅ RETURN; nu se termină în timpul ieșirii |
| **Furtună solară** (particule energetice) | crește în ore; în 2017 valorile mari au ținut **peste două zile** ✔. Avertizarea vine cu ~30 min - 1 h înainte. | **Mediu la suprafață:** doza a crescut de 2-3 ori, „mai mult decât dublu” față de orice măsurătoare anterioară ✔, pentru că atmosfera protejează. E mult mai grav în zborul spre Marte. | Mergi la adăpost (habitatul) sau te întorci, imediat după alertă. | ✅ doza × 2,5, cu creștere și scădere lentă (48 h) |
| **Cutremur** | secunde-minute de zguduire. InSight a înregistrat 1.319 cutremure în ~4 ani; cel mai mare, ~magnitudine 5 (mai 2022). Sursa principală e falia Cerberus Fossae, departe de Jezero. | **Mic direct.** Riscul real sunt căderile de pietre de pe pante abrupte. | Te oprești și te depărtezi de pante și de baza frontului deltei. | ✅ zonă de ~300 m (presupunere: nu există date seismice pentru Jezero) |
| **Scurgere în costum** | până ajungi acasă | **Ridicat** | Te întorci imediat, pe drumul cel mai scurt. | ✅ consum suplimentar de O₂ (0,15 %/min, presupunere) |
| **Oboseală** | ore | **Mediu** | Renunți la oprirea cea mai îndepărtată; nu depășești ora de întoarcere. | ✅ viteză × 0,8, O₂ × 1,15 (presupuneri) |

### Hazarduri fixe pe hartă

| Hazard | Cât durează | Pericol | În aplicație |
|---|---|---|---|
| Pante > 20° | permanent | căderi, efort mare (limita NASA de mers în costum ✔) | ✅ interzise în trasee |
| Stânci > 35° | permanent | ridicat | ✅ stratul „unsafe” (afișare și a doua plasă de siguranță) |
| Nisip, bolovani | permanent | mers lent, alunecare | ✅ mers mai „scump” pe harta de cost |
| Radiația de fond | permanentă, 0,67 mSv/zi ✔ | mic pe o ieșire, contează pe toată misiunea | ✅ stratul de radiație și doza din buget |
| Noaptea și frigul (−83 °C ✔) | în fiecare noapte | ridicat dacă te prinde afară | ✅ marjă de 30 min față de apus |
| Resturi de la aterizare | permanent | tăieri, agățare în cabluri și în parașută | ✅ cercuri de precauție (poziții măsurate pe imaginea HiRISE, ±150 m) |

---

## 2. Hazarduri care lipsesc

| Hazard | Cât durează | Cât de periculos | Ce trebuie făcut | Recomandare |
|---|---|---|---|---|
| **Praful toxic** (perclorați, silice, oxizi de fier fini) | **permanent, peste tot** | **Mediu pe termen lung:** plămâni; perclorații afectează tiroida. NASA îl consideră gestionabil cu limite de expunere. | Cureți costumul de praf înainte de a intra; filtre HEPA, „suitport” (costumul se andochează din exterior, praful rămâne afară). | **Doar în Survival Guide.** E un risc după ieșire, nu unul de traseu. |
| **Pierderea legăturii** | local: minute-ore. Când Marte e în spatele Soarelui: ~2 săptămâni, o dată la ~26 de luni. | **Mediu:** fără ajutor de pe Pământ | Urmezi ultimul plan; ora de întoarcere nu depinde de legătură. Nu planifici ieșiri lungi în perioada aceea. | E deja în Survival Guide. Ca eveniment simulat ar cere schimbarea contractului (`live_event.json`). |
| **Coechipier rănit** | până ajungeți acasă | **Ridicat** | NASA cere ca un astronaut să-și poată căra colegul 2 km, pe pante de până la 20°. Fără ieșiri singur. | **Cea mai importantă lipsă.** Ar schimba punctul de neîntoarcere: nu doar „am destul O₂”, ci „pot căra un coleg până acasă”. |
| **Descărcări electrice în praf** | secunde, doar în vârtejuri și furtuni | necunoscut (descoperite în 2025); posibil risc pentru electronică | Eviți vârtejurile, ceea ce aplicația face deja. | O notă în Survival Guide |
| **Impact de meteorit** | instantaneu | **neglijabil local:** InSight a legat de impacturi doar 6 evenimente în 4 ani, pe toată planeta | nimic practic | Nu merită implementat |

### Ce poate face fiecare

- **Rolul 1** (fișierele lui):
  - în Survival Guide: secțiunea despre praful toxic și nota despre descărcările electrice;
  - rândurile noi în `how-we-calculate.md`, cu sursele;
  - verificarea pe paginile NASA a cifrelor fără ✔ de mai sus.
- **Echipa:** un eveniment nou, „coechipier rănit” sau „pierderea legăturii”. Lista de evenimente e în contractul comun, iar efectul lor îl calculează motorul (rolul 3) și alternativele (rolul 2).

---

## Surse

- **Cutremure:**
  - [NASA InSight, Science Highlights](https://science.nasa.gov/mission/insight/science-highlights/)
  - [JPL, setul de date seismice](https://dataverse.jpl.nasa.gov/dataset.xhtml?persistentId=doi:10.48577/jpl.2JHENN&version=1.0&selectTab=termsTab)
  - [JPL, cutremure din impacturi de meteoriți](https://www.jpl.nasa.gov/news/nasas-insight-finds-marsquakes-from-meteoroids-go-deeper-than-expected/)
- **Furtuna globală din 2018:**
  - [NASA NTRS 20190027303](https://ntrs.nasa.gov/citations/20190027303)
  - [JPL, Opportunity](https://www.jpl.nasa.gov/news/opportunity-hunkers-down-during-dust-storm/)
  - [JPL, opacitatea 10,8](https://www.jpl.nasa.gov/news/nasa-encounters-the-perfect-storm-for-science/)
- **Praful toxic:**
  - [NASA NTRS 20250000969](https://ntrs.nasa.gov/citations/20250000969)
  - [NASA, limitele de expunere](https://www.nasa.gov/general/establishing-crew-exposure-limits-of-martian-dust/)
  - [JPL, Perseverance și praful](https://www.jpl.nasa.gov/news/nasas-perseverance-offers-clues-to-protect-crews-from-mars-dust/)
- **Conjuncția solară:**
  - [JPL](https://www.jpl.nasa.gov/news/whats-mars-solar-conjunction-and-why-does-it-matter/)
  - [NASA NTRS 20220013418](https://ntrs.nasa.gov/api/citations/20220013418/downloads/ASCEND-Communication%20Delays,%20Disruptions,%20and%20Blackouts%20for%20Crewed%20Mars%20Missions.pdf)
- **Descărcări electrice** (Chide et al. 2025, *Nature* 647):
  - [CNRS](https://www.cnrs.fr/en/press/electric-discharges-detected-mars-first-time)
  - [IRAP](https://www.irap.omp.eu/en/2025/11/electric-discharges-detected-on-mars-for-the-first-time/)
- **Furtuni solare:**
  - [NASA/JPL 2017](https://www.jpl.nasa.gov/news/large-solar-storm-sparks-global-aurora-and-doubles-radiation-levels-on-the-martian-surface/) ✔
  - [NASA NTRS 20150001237](https://ntrs.nasa.gov/api/citations/20150001237/downloads/20150001237.pdf) (30 min de avertizare)
  - [NASA, SOHO](https://www.nasa.gov/news-release/spacecraft-aids-in-forecast-of-solar-radiation-storms/)
  - [NASA NTRS 20240009831](https://ntrs.nasa.gov/api/citations/20240009831/downloads/NAS%20BPS%20Simonsen%20v4%20strives.pdf)
- **Salvarea unui coleg (2 km, 20°):** [NASA Lunar Rescue](https://www.nasa.gov/get-involved/south-pole-safety-designing-the-nasa-lunar-rescue-system/)
- **Celulele furtunilor și vântul:** [ESA, Mars Express](https://www.esa.int/Science_Exploration/Space_Science/Mars_Express/Martian_dust_storms_churn_up_Earth-like_clouds) ✔
- **Vârtejurile:** Toledo et al. 2023, [NASA NTRS 20250010686](https://ntrs.nasa.gov/citations/20250010686) ✔
- **Doza de fond, temperaturile, panta de 20°, resturile de la aterizare:** vezi `docs/sources.md` și `docs/roles/PARAMETRI_REFERINTA.md`.
