# How we calculate

Source for the in-app "How we calculate" screen and for the slides. Every number the copilot uses is listed here, with the file it lives in, where it comes from, and how sure we are.

**Status** (shown as a badge in the app):

- `source`: measured by a NASA mission, or derived from measured values with a stated formula.
- `to verify`: has a source, but the value or its interpretation still needs a check.
- `assumption`: chosen by us and declared as such.

Source numbers [S1]…[S34] follow the team's parameter registry (`docs/roles/PARAMETRI_REFERINTA.md`); the full list is at the end. Data sources and papers are also in `docs/sources.md`.

**Core rule:** the numbers come from code, not from the LLM. Distance, O₂, time, dose and risk are computed deterministically. The LLM only explains a decision that the code has already made.

## 1. Walking and the suit (`backend/app/core/budget.py`)

| Quantity | Value / formula | Source | Status |
|---|---|---|---|
| Walking speed vs slope | Tobler: `6·exp(-3.5·abs(tan θ + 0.05))` km/h × suit factor | Tobler (1993), registry §4.1 | source |
| Suit factor (`SUIT_FACTOR`) | 0.6 → 3.0 km/h on flat ground (Apollo crews walked ~2.2 km/h; nominal maximum 3.5 km/h) | [S22] [S24] | source |
| Mars gravity correction (`MARS_G_FACTOR`) | 1.0 (not applied on purpose: the suit limits speed, not gravity; a second correction would count it twice) | — | assumption |
| Mars gravity (`G_MARS`) | 3.71 m/s² | physical constant | source |
| Rest metabolic rate in suit (`P_REST_W`) | 176 W (600 BTU/h, light activity) | [S31] | source |
| Astronaut + suit mass (`M_TOTAL_KG`) | 196 kg (Mars-equivalent weights 583-927 N ÷ 3.71) | [S24] [S34] | to verify |
| Walking cost (`C_LEVEL`) | 0.59 J/(kg·m), calibrated so that 3 km/h on flat ground = 272 W (the Apollo average) | [S28] | source |
| Climbing efficiency (`ETA_UP`) | 0.22 (typical muscle efficiency 0.20-0.25) | not calibrated on [S32] | assumption |
| Metabolic power on a segment | `P = P_rest + M·(C_level·v + g·max(0, v_vertical) / η_up)` | registry §4.2 | source |
| Apollo lunar EVA metabolic rates (check) | 822-1267 kJ/h = 228-352 W (780-1200 BTU/h), 158.8 h of lunar EVA, Table I | NASA TN D-7883 (Waligora et al. 1975), [S29] | source |

## 2. Oxygen (`budget.py`, `backend/app/live/engine.py`)

| Quantity | Value / formula | Source | Status |
|---|---|---|---|
| O₂ tank = 100% | 8 h at 1000 BTU/h = 418 L O₂ (~0.6 kg) | [S31], 4.825 kcal per litre O₂ [S33] | source |
| O₂ per watt (`O2_PCT_PER_MIN_PER_WATT`) | 0.000711 %/min per W | derived from the two lines above | source |
| O₂ at rest / waiting (`O2_PCT_PER_MIN_REST`) | 0.125 %/min (176 W) | derived | source |
| O₂ walking on flat ground | 0.194 %/min (272 W) | derived | source |
| Extra walking power in the live engine (`WALK_WATTS`) | 220 W above rest → 0.281 %/min | — | assumption |
| O₂ reserve on arrival (`Limits.o2_reserve_pct`) | 30% | — | assumption |
| Suit leak event (`SUIT_LEAK_PCT_PER_MIN`) | +0.15 %/min O₂ | — | assumption |
| Fatigue event (`FATIGUE_SPEED_FACTOR`, `FATIGUE_O2_FACTOR`) | speed × 0.8, O₂ use × 1.15 | — | assumption |

## 3. Safety limits and the verdict (`backend/app/core/types.py`, `validator.py`, `planner.py`)

| Quantity | Value | Source | Status |
|---|---|---|---|
| Maximum walking slope, planning (`PLANNER_LIMITS`) | 20° (NASA lunar EVA concept of operations; Apollo 15 crossed ~17°) | [S26] | source |
| Maximum slope (`meta.max_slope_deg`, `planner.PLANNER_LIMITS`, `Limits.max_slope_deg`) | 20°: steeper cells are forbidden on the map (2.05% of Jezero) and in every route | NASA concept of operations for lunar EVAs: 20° maximum walking slope; Apollo 15 crossed ~17° [S26] | source |
| Margin before sunset (`Limits.sunset_margin_min`) | 30 min | — | assumption |
| Dose limit per EVA (`Limits.max_dose_msv`) | 1 mSv (a 5-8 h EVA gets ~0.13-0.22 mSv, so this limit is rarely reached: on Mars, radiation matters over a whole mission, not one EVA) | — | assumption |
| Verdict NO-GO | the validator finds any violation | — | source |
| Verdict CAUTION (`CAUTION_O2_MARGIN_PCT`, `CAUTION_SUNSET_MARGIN_MIN`) | final O₂ less than 10 points above the reserve, or return less than 60 min before sunset | team rule | assumption |
| Maximum walk-back distance | 10 km (NASA "walkback" test); our map radius is 3-5 km | [S27] | source |

## 4. Daylight (`backend/app/core/daylight.py`)

| Quantity | Value / formula | Source | Status |
|---|---|---|---|
| Sunrise and sunset | Mars24 algorithm (Allison & McEwen 2000) | NASA GISS Mars24 | source |
| Mars hour (`MARS_HOUR_S`) | 3698.98 s (1/24 of a sol, 24 h 39.6 min) | Mars24 | source |
| TT − UTC (`TT_MINUS_UTC_S`) | 69.184 s | IERS | source |
| Sun altitude at sunrise and sunset (`SUNRISE_ALTITUDE_DEG`) | −0.5° (edge of the solar disc) | — | assumption |
| Effective sunset with dust | `sunset − max(0, τ − 0.5) · 30` min | — | assumption |
| Live engine sunset without a plan | computed like the planner (Mars24 at the site centre, ≈ 633 min after the start on the demo date); `DEFAULT_SUNSET_MIN` = 420 min is only a last resort if the site has no centre | Mars24 | source |
| EVA start (`planner.SOL_START_UTC`, `scenario.EVA_START_LTST_H`) | 2026-11-14 14:22 UTC = 08:00 local true solar time at Jezero; the return clock in the app counts from it | Mars24 | source |

## 5. Cost map and route choice (`backend/app/core/costmap.py`, `decision.py`)

| Quantity | Value / formula | Source | Status |
|---|---|---|---|
| Cost of a cell | `(1 + slope_k·(slope / max_slope)²) × terrain_factor + w_radiation × radiation excess`; ∞ above the slope limit or on `unsafe` cells | team design | assumption |
| Slope penalty (`slope_k` per preset; `SLOPE_K` default) | safe 5.0 · fast 1.5 · science 3.0 (default 3.0) | — | assumption |
| Terrain factor (`TERRAIN_FACTOR`) | bedrock 1.0 · regolith 1.2 · sand 1.8 · boulders 3.0 | — | assumption |
| Hazard weight (`w_hazard`) | safe 10 · fast 4 · science 6 | — | assumption |
| Radiation weight (`w_radiation`) | safe 2.0 · fast 0.5 · science 1.0, applied to the relative excess over the site minimum | — | assumption |
| Science weight (`w_science`) | safe 0.15 · fast 0.2 · science 0.4 | — | assumption |
| Keep the current route below this risk (`RISK_THRESHOLD`) | 0.3 | — | assumption |
| Hysteresis (`MIN_IMPROVEMENT`) | an alternative must be at least 20% better before the route changes | — | assumption |

## 6. Hazards (`backend/app/core/hazards.py`, `backend/app/live/engine.py`)

| Quantity | Value / formula | Source | Status |
|---|---|---|---|
| Hazard shape | ellipse; intensity × max(0, 1 − d²), moving at constant velocity | team model | assumption |
| Forecast horizons (`FORECAST_STEPS_MIN`) | 10, 20, 30, 45, 60, 90, 120, 180 min | — | assumption |
| Forecast cone (`SIGMA_REL`) | semi-axes grow by 0.35 × speed × 60 m per minute ahead (a 15 m/s front: +315 m/min; a 3 m/s dust devil: +63 m/min). Calibrated by `benchmark.calibrate_sigma_v` on 100 scenarios (seed 42) for 95% coverage at every forecast horizon, on our simulated storm noise, not on MEDA data | — | assumption |
| Old absolute cone (`SIGMA_V`) | 0.25 m/s → +15 m/min; no longer used (one absolute value cannot fit both 15 m/s fronts and 3 m/s dust devils) | — | assumption |
| Contact threshold (`HIT_THRESHOLD`) | a point is "in the hazard" from intensity 0.3 (route hit, blocked cells, crosses-hazard flag) | team rule | assumption |
| Allowed responses (`HAZARD_RESPONSES`) | dust devil → reroute; local storm → reroute, wait or return; regional storm → return; solar particle event → shelter (wait) or return; marsquake → reroute or return | team rule | assumption |
| Dust devils at Jezero (reference) | 1.3-3.4 per km² per sol, median diameter 25 m (5-135 m), peak at 12-13 h local time, internal wind up to 25 m/s | [S16] [S17] | source |
| Shelter wait (`DEFAULT_WAIT_MIN`) | 30 min per WAIT decision | — | assumption |
| Default injected hazards (`HAZARD_DEFAULTS`) | dust devil 130 m across at 4 m/s · local storm = storm front 30 × 5 km at 15 m/s, starting 9 km away · regional storm 60 km, static · marsquake 300 m | sizes and speeds from [S16] [S17] [S18] [S19] | assumption |
| Real dust storm scale (reference) | storm cells 20-40 km, winds 20-45 m/s, regional storms visible from orbit days ahead | [S18] [S19] [S21] | source |

## 7. Weather and radiation scenarios (`backend/app/live/scenario.py`)

Simulated, seeded series ("simulated scenarios, calibrated on MEDA, REMS and RAD"). Each constant has its source in a code comment.

| Quantity | Value | Source | Status |
|---|---|---|---|
| Air temperature | daily cycle −83 °C before dawn to −23 °C at midday (peak 12:30 local time), noise ±2.5 K | Munguira et al. 2023 [S3] [S10] | source |
| Dust reduces the daily temperature swing | factor 1 / (1 + 0.35·(τ − 0.5)) | observed in Jezero storms (Lemmon et al. 2022); factor chosen by us | assumption |
| Pressure | 720 Pa ± 12 Pa thermal tide, maximum around 08:00 | Sánchez-Lavega et al. 2023 [S5] [S6] | source |
| Wind: distribution | Weibull: each minute is drawn from it; gusts come from its tail, not from a sine wave. Turbulence correlated over ~3 min | Viúdez-Moreiras et al. 2022 [S7] | source |
| Wind: parameters (`WIND_WEIBULL_BY_LTST`) | MEDA fits by time of day: morning 07-10 h c = 3.02 m/s, k = 2.01 (mean 2.7 m/s) · midday 10-15 h c = 5.28, k = 2.16 (mean 4.7) · afternoon 15-18 h c = 6.80, k = 3.02 (mean 6.1) · evening and night 1.2-3.0 m/s. Linear interpolation between the slot midpoints is our choice | Viúdez-Moreiras et al. 2022, Table 1 (full text, NTRS 20230001086) [S7]; also in `data/processed/jezero/wind_stats.json` | source |
| Wind turbulence (reference) | turbulence intensity (σ/mean over 10 min) 36 ± 10% by day, 22 ± 10% by night; around dust devils the Weibull scale rises by 65% and peaks reach 9.2 × the background wind | same paper, sections 4-5 | source |
| Dust opacity τ, quiet season | 0.5; rises only during dust events | Lemmon et al. 2022 [S8] (NASA NTRS record) | to verify |
| Surface dose rate | 28 µSv/h dose equivalent (0.67 mSv/day, galactic cosmic rays, Aug 2012 - Jun 2013; absorbed dose 0.21 mGy/day) | NASA news release of 9 Dec 2013 [S11] (checked on the page); Hassler et al. 2014 [S12] | source |
| Dose daily cycle (`DOSE_DIURNAL_FRAC`) | ±11% (180-225 µGy/day), lowest when pressure is highest; tied to the pressure tide by us | Hassler et al. 2014, Rafkin et al. 2014 [S12] | to verify |
| Solar particle event | dose × 2.5, rising over 2 h, peak until 4 h, then decaying over ~36 h (largest SPE seen on the surface, Sept 2017: × 2-3). The live engine takes these numbers from the scenario (`SOLAR_DOSE_MULTIPLIER`, `SOLAR_DURATION_MIN`) | Zeitlin et al. 2018 [S14] [S15] | to verify |
| Storm front (demo `local_storm`) | τ +2.0 and wind +15 m/s at full intensity; passage time = 2 × the ellipse's extent along its motion ÷ speed (a 30 × 5 km front at 15 m/s passes in ~6 min) | Lemmon et al. 2022; sizes [S18] [S19] | assumption |
| Regional storm (demo) | τ rises to 3.0 over 120 min and stays there | Guzewich et al. 2019 | assumption |
| Dust devil passing (demo) | τ +0.5, wind +15 m/s, pressure −3 Pa for 2-5 min | [S1] [S17] | source |
| Demo scene (`DEMO_SCENARIO_EVENTS`, `JEZERO_DEMO_EVENTS`) | min 30: large dust devil (130 m, 3 m/s with the wind) crosses the route ahead → REROUTE · min 80: storm front 30 × 5 km at 15 m/s reaches the astronaut at the clay target → nothing avoids it → immediate return · min 125: regional storm warning from orbit → RETURN. Real sizes and speeds; dust devils are rarer at 08:30 than at midday (a demo choice) | registry §3 [S16] [S17] [S18] [S19] [S21] | assumption |
| Earth-Mars light delay on the demo date | 11.0 min one way (1.319 AU on 2026-11-14); help from Houston = 2 × 11 + 5 min reaction time ≈ 27 min | JPL approximate Keplerian elements (Standish); reaction time chosen by us | source |

## 8. The map (`pipeline/fetch_stac.py`, `pipeline/build_layers.py`)

| Quantity | Value / formula | Source | Status |
|---|---|---|---|
| Map | 10 × 10 km around 18.44° N, 77.45° E (the Perseverance landing site), 500 × 500 cells of 20 m, local equirectangular projection with true scale at 18.44° | USGS STAC; Mars 2015 sphere, R = 3,396,190 m | source |
| Terrain elevation | HiRISE DTMs (read at 4 m) over CTX DTMs, areoid datum, calibrated on 306 Perseverance localizations (mean residual 5.2 m) | USGS Astrogeology STAC (MRO HiRISE, CTX); NASA M20 waypoints | source |
| Slope per 20 m cell | maximum of the 4 m slopes inside the cell (small obstacles are kept) | derived from the DTM | source |
| Unsafe cells | slope > 35° at 4 m (the HiRISE FOM legend is not published) | derived from the DTM | assumption |
| Radiation layer | surface dose × exp((elevation − mean) / 11 km): slightly more dose where there is less atmosphere above | RAD background [S11]; altitude scaling chosen by us | assumption |
| Terrain classes | THEMIS night IR (thermal-inertia proxy): darkest 25% on gentle slopes = sand, brightest 25% = bedrock; slope > 20° = bedrock; 4 m vs 20 m slope difference > 12° = boulders | Mars Odyssey THEMIS; thresholds chosen by us | assumption |
| Mineral units | delta deposits (clays) = plateau > 90 m above the crater floor; clays, olivine and carbonates within 250-700 m of where Perseverance studied them | HiRISE/CTX DTM; NASA M20 waypoints; Goudge 2015, Liu 2022, Horgan 2020 | assumption |
| Target and hardware positions | median rover position during each campaign (Three Forks depot: sols 652-686); Wright Brothers Field from the Ingenuity flight log | NASA M20 waypoints; Ingenuity flight log | source |
| Habitat | flattest cell (≤ 4° within 140 m) near the landing site | derived from the DTM | source |

## References

[S1] Rodriguez-Manfredi et al. 2023, *Nature Geoscience*, Jezero meteorology over the first 250 sols · [S3] [S4] Munguira et al. 2023, *JGR Planets*, near-surface temperatures at Jezero (MEDA) · [S5] [S6] Sánchez-Lavega et al. 2023, *JGR Planets*, pressure at Jezero · [S7] Viúdez-Moreiras et al. 2022, winds at the Mars 2020 landing site (NTRS 20230001086) · [S8] Lemmon et al. 2022, *GRL*, dust in Jezero (doi:10.1029/2022GL100126, NASA NTRS) · [S10] Munguira et al., EGU 2023, Jezero temperature fluctuations (doi:10.5194/egusphere-egu23-5885) · [S11] NASA news release of 9 Dec 2013: 0.67 mSv/day · [S12] Hassler et al. 2014, *Science*, doi:10.1126/science.1244797 · [S14] [S15] Zeitlin et al. 2018, *GRL*, doi:10.1029/2018GL077760 · [S16] Toledo et al. 2023, *JGR Planets*, dust devils at Jezero · [S17] Hueso et al. 2023, *JGR Planets*, convective vortices at Jezero · [S18] [S19] Sánchez-Lavega et al., dust storm cells · [S21] NASA JPL, back-to-back regional storms · [S22] Apollo walking speeds · [S24] NASA ICES-2026 "Mars Mass" (NTRS 20260005410) · [S26] NASA EVA Lunar Surface Concept of Operations · [S27] The Walkback Test (NASA JSC, ICES 2007) · [S28] NASA NTRS 19910001262, EVA metabolic rates · [S29] NASA TN D-7883, *Apollo Experience Report: Assessment of Metabolic Expenditures* (NTRS 19750010199) · [S31] *Aerospace Medicine and Human Performance* 90(2), EVA simulation parameters · [S32] NASA NTRS 20220009964 · [S33] DTIC ADA386372, caloric equivalent of oxygen · Tobler 1993, hiking function · Mars24, NASA GISS · Standish, "Keplerian Elements for Approximate Positions of the Major Planets", JPL.

Full links: `docs/roles/PARAMETRI_REFERINTA.md` (team registry) and `docs/sources.md`.
