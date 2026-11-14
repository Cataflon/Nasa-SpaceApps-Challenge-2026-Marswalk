# Sources

Every dataset, tool and paper behind Marswalk Copilot, what we use it for, and how far we have checked it.

**How this list was checked (14 Nov 2026):**

- **Links:** each URL was opened automatically and had to return HTTP 200 (after redirects).
- **Papers:** each DOI was looked up in the [Crossref](https://www.crossref.org/) registry, and the first author, year, title and journal had to match what we cite. One DOI quoted from memory was wrong and has been corrected (Zeitlin 2018).
- **Data:** we downloaded the datasets ourselves and used them in the pipeline (`pipeline/fetch_stac.py`, `pipeline/build_layers.py`).

**Status values:**

- `verified`: the link opens, or the DOI matches, and we use the data or paper directly.
- `link verified`: the link or DOI is correct, but we have not yet checked every number we quote from it against the full text.
- `to verify`: we could not open it, or we have not used it yet.

**Totals:**

- **7 data types:** topographic, optical, thermal, spectral, atmospheric, radiation, rover localization. The challenge asks for at least 3.
- **4 missions whose data we actually use:**
  - MRO: HiRISE, CTX, plus CRISM through the papers in section D;
  - Mars Odyssey: THEMIS;
  - Mars 2020: Perseverance with MEDA, the Ingenuity helicopter and the rover localizations;
  - MSL Curiosity: RAD, REMS.
- **Context only:** MGS MOLA (via Mars Trek) and MAVEN.

## A. Orbital data in the map (static layers)

| Source | Mission / instrument | Data type | What we use | Link | Status |
|---|---|---|---|---|---|
| USGS Astrogeology GeoSTAC (catalog and API) | — | catalog | Search by bounding box and windowed COG reads: no full-file downloads | [GeoSTAC](https://stac.astrogeology.usgs.gov/geostac/) · [API](https://stac.astrogeology.usgs.gov/api/) · [docs](https://stac.astrogeology.usgs.gov/docs/data/) | verified |
| HiRISE DTMs, collection `mro_hirise_socet_dtms` | MRO HiRISE | topographic, optical | 5 DTMs (1 m, read at 4 m) cover 94.4% of the map: elevation, slope (max of 4 m pixels), orthoimage background. The FOM is used only as a provenance mask (its colour legend is not published). | [USGS docs](https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms/) · [PDS data set](https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=MRO-M-HIRISE-5-DTM-V1.0) | verified |
| CTX DTMs, collection `mro_ctx_controlled_usgs_dtms` | MRO CTX | topographic, optical | Best 3 of 36 DTMs (~20 m): full-coverage base under HiRISE, CC0 licence | [AWS Open Data](https://registry.opendata.aws/nasa-usgs-controlled-mro-ctx-dtms/) | verified |
| THEMIS IR controlled mosaics, collection `mo_themis_controlled_mosaics` (`mc13_syrtis_major_nir` / `_dir`) | Mars Odyssey THEMIS | thermal | Night IR as a thermal-inertia proxy for terrain classes (sand / regolith / bedrock) | [THEMIS](https://themis.mars.asu.edu/) | verified |
| CRISM spectral data | MRO CRISM | spectral | **Not used directly** (not in USGS STAC). Mineral units come from rover-confirmed sites plus the CRISM papers in section D. | [PDS Geosciences ODE](https://ode.rsl.wustl.edu/mars/) | to verify |
| Geologic map of Jezero crater and the Nili Planum region (Sun & Stack 2020, USGS SIM 3464) | — (MRO data) | geologic | Context for the mineral units and the science stops | [doi:10.3133/sim3464](https://doi.org/10.3133/sim3464) | link verified |
| NASA Mars Trek | MGS MOLA and others | topographic | Global context and choosing the site only (not in the pipeline) | [Mars Trek](https://trek.nasa.gov/mars/) | verified |

## B. Rover and helicopter data (ground truth)

| Source | Mission / instrument | Data type | What we use | Link | Status |
|---|---|---|---|---|---|
| Perseverance location map | Mars 2020 | rover localization | The official map behind the two datasets below | [science.nasa.gov location map](https://science.nasa.gov/mission/mars-2020-perseverance/location-map/) | verified |
| Perseverance localization waypoints (`M20_waypoints.json`, sols 13-2022) | Mars 2020 Perseverance | rover localization | 306 localized positions inside the map, each with elevation above the areoid: (1) vertical calibration of our DTM (residual 5.2 m), (2) target positions (median rover position per campaign), (3) Three Forks depot and landing site, (4) the real rover traverse on the map | [JSON](https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json) | verified |
| Ingenuity flight log (`m20_heli_waypoints.json`, flights 0-72) | Mars 2020 Ingenuity | localization | Wright Brothers Field (flight 1). The final position after flight 72 (Airfield Chi, 18.4973° N, 77.3225° E) lies about 2 km west of the map. | [JSON](https://mars.nasa.gov/mmgis-maps/M20/Layers/json/m20_heli_waypoints.json) | verified |
| Perseverance raw images (Mastcam-Z, Navcam) | Mars 2020 | optical (ground) | "What you will see" image at each stop (P2) | [Raw images](https://mars.nasa.gov/mars2020/multimedia/raw-images/) | to verify (not used yet) |
| Mars 2020 landing hardware: descent stage, backshell + parachute, heat shield | Mars 2020 | — | Approximate positions only, shown with status "to verify". No official coordinates were found: the JPL pages tried return 404. | — | to verify |

## C. Simulation calibration (weather and radiation scenarios, `backend/app/live/scenario.py`)

| Paper / source | Mission / instrument | What we take from it | DOI / link | Status |
|---|---|---|---|---|
| SwRI press release, 9 Dec 2013, "Scientists publish surface radiation measurements from Mars" (quoting D. Hassler) | MSL RAD | "average GCR dose equivalent rate of 0.67 millisieverts per day from August 2012 to June 2013 on the Martian surface" → 28 µSv/h background | [phys.org](https://phys.org/news/2013-12-scientists-publish-surface-mars.amp) | verified (sentence read on the page) |
| Hassler et al. 2014, *Science*, "Mars' Surface Radiation Environment Measured with the Mars Science Laboratory's Curiosity Rover" | MSL RAD | 0.21 mGy/day absorbed dose; daily cycle 180-225 µGy/day (±11%) | [10.1126/science.1244797](https://doi.org/10.1126/science.1244797) | link verified |
| Rafkin et al. 2014, *JGR Planets*, "Diurnal variations of energetic particle radiation at the surface of Mars…" | MSL RAD | dose decreases when pressure (atmospheric column) increases | [10.1002/2013JE004525](https://doi.org/10.1002/2013JE004525) | link verified |
| Zeitlin et al. 2018, *GRL*, "Analysis of the Radiation Hazard Observed by RAD on the Surface of Mars During the September 2017 Solar Particle Event" | MSL RAD | solar particle event: dose × 2-3, rising over hours, decaying over ~36 h → × 2.5 in the scenario | [10.1029/2018GL077760](https://doi.org/10.1029/2018GL077760) | link verified |
| Munguira et al. 2023, *JGR Planets*, "Near Surface Atmospheric Temperatures at Jezero From Mars 2020 MEDA Measurements" | Mars 2020 MEDA | diurnal air temperature range (−83 °C to −23 °C), ±2.5 K fluctuations at midday | [10.1029/2022JE007559](https://doi.org/10.1029/2022JE007559) | link verified |
| Viúdez-Moreiras et al. 2022, *JGR Planets*, "Winds at the Mars 2020 Landing Site. 2. Wind Variability and Turbulence" (registry [S7]) | Mars 2020 MEDA | Weibull fits by time of day (Table 1, used in the scenario wind), turbulence intensity 36% by day and 22% by night (for role 2's storm noise). Transcription checked: Table 1 reproduces the means and percentiles of Table 2 | [NTRS 20230001086](https://ntrs.nasa.gov/citations/20230001086) | verified (full text read) |
| Savijärvi et al., Jezero dust opacity (registry [S8]) | Mars 2020 | quiet-season tau ≈ 0.5 | [PDF](https://dydaktyka.fizyka.umk.pl/Karwasz/FiChA/Biblio/Jezero_Mars.pdf) | to verify |
| Newman et al. 2022, *Science Advances*, "The dynamic atmospheric and aeolian environment of Jezero crater, Mars" | Mars 2020 MEDA | diurnal winds, gusts, dust devils and their pressure drops | [10.1126/sciadv.abn3783](https://doi.org/10.1126/sciadv.abn3783) | link verified |
| Sánchez-Lavega et al. 2023, *JGR Planets*, "Mars 2020 Perseverance Rover Studies of the Martian Atmosphere Over Jezero From Pressure Measurements" | Mars 2020 MEDA | mean pressure (~720 Pa) and thermal tide amplitude | [10.1029/2022JE007480](https://doi.org/10.1029/2022JE007480) | link verified |
| Lemmon et al. 2022, *GRL*, "Dust, Sand, and Winds Within an Active Martian Storm in Jezero Crater" | Mars 2020 MEDA, Mastcam-Z | dust opacity (tau) and winds during a local storm | [10.1029/2022GL100126](https://doi.org/10.1029/2022GL100126) | link verified |
| Guzewich et al. 2019, *GRL*, "Mars Science Laboratory Observations of the 2018/Mars Year 34 Global Dust Storm" | MSL REMS, Mastcam | upper bound of dust opacity during a global storm | [10.1029/2018GL080839](https://doi.org/10.1029/2018GL080839) | link verified |
| PDS Atmospheres Node (MEDA / REMS raw data) | Mars 2020 MEDA, MSL REMS | raw series, for a possible future calibration | [atmos.nmsu.edu](https://atmos.nmsu.edu/) | to verify (TLS certificate error from our network) |
| MARCI weather reports | MRO MARCI | storm size and frequency (context) | [MSSS weather](https://www.msss.com/msss_images/latest_weather.html) | verified (link) |
| PDS PPI Node (RAD data) | MSL RAD, MAVEN | raw radiation data (context) | [pds-ppi.igpp.ucla.edu](https://pds-ppi.igpp.ucla.edu/) | verified (link) |

## D. Geology and mineralogy (mineral units, `pipeline/manual_units.py`)

| Paper | What we take from it | DOI | Status |
|---|---|---|---|
| Goudge et al. 2015, *JGR Planets*, "Assessing the mineralogy of the watershed and fan deposits of the Jezero crater paleolake system, Mars" | Fe/Mg smectite clays in the western delta (CRISM) → delta = clay unit | [10.1002/2014JE004782](https://doi.org/10.1002/2014JE004782) | link verified |
| Horgan et al. 2020, *Icarus*, "The mineral diversity of Jezero crater: Evidence for possible lacustrine carbonates on Mars" | carbonates in the margin unit → carbonate unit | [10.1016/j.icarus.2019.113526](https://doi.org/10.1016/j.icarus.2019.113526) | link verified |
| Liu et al. 2022, *Science*, "An olivine cumulate outcrop on the floor of Jezero crater, Mars" | olivine cumulate in Séítah → olivine unit | [10.1126/science.abo2756](https://doi.org/10.1126/science.abo2756) | link verified |
| Farley et al. 2022, *Science*, "Aqueously altered igneous rocks sampled on the floor of Jezero crater, Mars" | crater floor (Máaz / Séítah) context | [10.1126/science.abo2196](https://doi.org/10.1126/science.abo2196) | link verified |

## E. Formulas and models

| What | Source | Link | Status |
|---|---|---|---|
| Walking speed vs slope | Tobler (1993), hiking function, adjusted by a suit factor (assumption) | — (technical report, no DOI) | to verify |
| Suited metabolic rate (Apollo lunar EVAs) | Waligora et al. 1975, *Apollo Experience Report: Assessment of Metabolic Expenditures*, NASA TN D-7883: 822-1267 kJ/h (780-1200 BTU/h) over 158.8 h of lunar EVA (Table I, p. 8-9) | [NTRS 19750010199](https://ntrs.nasa.gov/citations/19750010199) | verified (PDF read) |
| O₂ model used by the budget | team parameter registry (`docs/roles/PARAMETRI_REFERINTA.md`, §4.2): 100% tank = 8 h at 1000 BTU/h = 418 L O₂; 4.825 kcal per litre O₂ | registry sources [S31] [S33] | link verified |
| Other NASA EVA metabolic reports | Waligora & Horrigan 1975 (NTRS 19760005584); Paul 2011, Apollo-Skylab-STS-135 (NTRS 20110023042, abstract only); Greenlund 2017, Apollo EVA operational assessment (NTRS 20170007261) | [ntrs.nasa.gov](https://ntrs.nasa.gov/) (reached through the NTRS API) | link verified |
| Earth-Mars light delay on the demo date | Standish, "Keplerian Elements for Approximate Positions of the Major Planets" (JPL Solar System Dynamics): 1.319 AU on 2026-11-14 → 11.0 min one way; checked on the Jan 2025 opposition and the Nov 2023 conjunction | `earth_mars_light_min()` in `scenario.py` | verified (checked on known dates) |
| Sol length, local true solar time, sunset | Mars24 (NASA GISS) | [Mars24](https://www.giss.nasa.gov/tools/mars24/) | verified (link) |

## Still open

- The exact numbers we quote from each paper (section C) have not been checked against the full texts yet: the DOIs are correct, but the values are marked "to verify" in the code.
- Landing hardware positions (descent stage, backshell + parachute, heat shield): no official coordinates found.
- HiRISE FOM colour legend: not published on the USGS or HiRISE pages; it may be in the PDS data set documentation linked above.
- PDS Atmospheres and NASA NTRS did not open from our network: retry from another connection.
