# How we calculate

Source for the in-app "How we calculate" screen and for the slides. Every number has a source or is marked **assumption**.

**Status** (shown as a badge in the app): `source` = value taken from a source we actually read · `to verify` = known source, not yet read · `assumption` = chosen by us and declared as such.

| Quantity | Formula / value | Source | Status |
|---|---|---|---|
| Walking speed | Tobler: `6·exp(-3.5·abs(tan θ + 0.05))` km/h × suit factor 0.6 | Tobler (1993); suit factor | assumption |
| O₂ consumption | 0.12 %/min at rest, ~0.25 %/min walking (220 W extra metabolic load) | NASA NTRS (Apollo EVAs, suited walking tests) | to verify |
| O₂ reserve on arrival | 30% | — | assumption |
| Maximum slope | 25° | NASA human EVA studies | to verify |
| Margin before sunset | 30 min | — | assumption |
| Surface dose rate | 26.7 µSv/h dose equivalent (0.64 mSv/day; absorbed dose 0.21 mGy/day) | Curiosity RAD, Hassler et al. 2014, Science | to verify |
| Dose limit per EVA | 1 mSv | — | assumption |
| Solar particle event | dose rate × 20 for 60 min | — | assumption |
| Suit leak | +0.15 %/min O₂ | — | assumption |
| Fatigue | speed × 0.8, O₂ × 1.15 | — | assumption |
| Sunset | Mars24 | NASA GISS | to verify |
| Effective sunset with dust | `sunset − max(0, τ − 0.5)·30` min | — | assumption |
| Weight presets | see `backend/app/core/costmap.py` | — | assumption |
| EVA start time | 09:00 local true solar time (LTST); one Mars hour = 61.65 min | Mars24 (sol length) | assumption |
| Earth–Mars delay | ~3–22 min one way, depending on planetary positions; value for the demo date: TODO | JPL Horizons / NASA | to verify |
| Weather and radiation scenarios | see `backend/app/live/scenario.py` (each constant has its source in a comment) | Perseverance MEDA, Curiosity REMS and RAD | to verify |
| Terrain elevation | HiRISE DTMs (read at 4 m) over CTX DTMs, areoid datum, calibrated on 306 Perseverance localizations (mean residual 5.2 m) | USGS Astrogeology STAC (MRO HiRISE, CTX); NASA M20 waypoints | source |
| Slope per 20 m cell | maximum of the 4 m slopes inside the cell (small obstacles are kept) | derived from the DTM | source |
| Unsafe cells | slope > 35° at 4 m (the HiRISE FOM legend is not published) | derived from the DTM | assumption |
| Terrain classes | THEMIS night IR (thermal-inertia proxy): darkest 25% on gentle slopes = sand, brightest 25% = bedrock; slope > 20° = bedrock; 4 m vs 20 m slope difference > 12° = boulders | Mars Odyssey THEMIS; thresholds chosen by us | assumption |
| Mineral units | delta deposits (clays) = plateau > 50 m above the crater floor; clays, olivine and carbonates within 250-500 m of where Perseverance studied them | HiRISE/CTX DTM; NASA M20 waypoints; Goudge 2015, Liu 2022, Horgan 2020 | assumption |
| Target and hardware positions | median rover position during each campaign (Three Forks depot: sols 652-686) | NASA M20 waypoints | source |

> TODO (role 1, P1): one row for **every** constant in `core/` (budget, cost, validator, hazards, decision) and in `scenario.py`.
