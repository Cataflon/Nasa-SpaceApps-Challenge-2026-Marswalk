# Slides

Eleven slides, about 3 minutes plus the 2-minute live demo ([demo.md](demo.md)). Each slide names the judging criterion it serves. One idea per slide, big numbers, few words. Numbers were measured on 14.11.2026 on the Jezero site; the benchmark must be re-measured after any change to role 2's code (`GET /api/benchmark`, field `headline`).

---

## 1. Title: Marswalk Copilot *(Presentation)*

**The map tells you where to walk. The copilot tells you when to change your way, and whether you can still get back.**

> **The copilot brought the astronaut home safely in 81% of storms. The fixed plan: 51%.**
> 100 simulated storms · same seed · no AI in the loop

Visual: the Jezero map with the walked route and the detour around the dust devil.

---

## 2. The problem *(Relevance)*

- The first people on Mars will leave the habitat **on foot**, with limited oxygen and no GPS.
- Help from Earth is late: light takes **3 to 22 minutes** one way. On our demo date, 14 Nov 2026, it takes **11 min**, so an answer from Houston arrives in about **27 min**.
- Conditions change during a walk: dust devils, storm fronts, solar particle events, fatigue, a suit leak.
- Existing tools (Mars Trek) show global layers. They are not made for one walk, and they do not decide.

Visual: an astronaut icon on a route, a clock "27 min" on the Earth side.

---

## 3. The idea *(Creativity)*

Two parts:

1. **A hyperlocal map**: 10 × 10 km of Jezero crater at 20 m per cell, from NASA data.
2. **A live copilot**: every simulated minute it reads the sensors, predicts where each hazard will be, draws alternatives, removes the unsafe ones, and picks the safest. A local AI model explains the choice in plain words.

Visual: loop diagram, sensors → forecast cone → alternatives → validator → rule → explanation.

---

## 4. The map: real NASA data, every value labelled *(Validity, Relevance)*

| Layer | Mission · instrument |
|---|---|
| Elevation, slope, unsafe ground | MRO · HiRISE DTM (1 m, read at 4 m) + CTX DTM, USGS |
| Terrain | Mars Odyssey · THEMIS night infrared (thermal inertia proxy) + HiRISE roughness |
| Minerals | Mars 2020 · units confirmed by Perseverance (clay, carbonate, olivine) |
| Rover route, landing hardware, Ingenuity | Mars 2020 · official localization waypoints |
| Weather and radiation scenarios | calibrated on Mars 2020 MEDA and Curiosity REMS + RAD |

- **4 NASA missions, 7 data types.** Click any point: "slope 7° · HiRISE + CTX · MRO".
- **Checked against the rover:** our terrain model agrees with 306 Perseverance waypoints within 5.2 m (median absolute difference).
- **Real hardware on the map:** the Three Forks sample depot (10 tubes for Mars Sample Return), the landing site and Ingenuity's first flight.

---

## 5. Live demo *(Presentation)*

Switch to the app. Script: [demo.md](demo.md).

1. Plan: a clay sample from the delta front, 5.9 km, back by 11:56.
2. Min 30: a dust devil 130 m wide → **reroute**.
3. Min 80: a storm front 30 km long at 54 km/h → no way around it → **go home now**.
4. Min 125: a regional storm → **return** confirmed. Home at 10:21.

---

## 6. The code decides, the AI explains *(Validity)*

- **Numbers come from code**: distance, oxygen, time, dose and risk are computed, never generated.
- **A fixed rule** picks among alternatives that a **validator** has already checked (O₂ reserve, daylight, slope, dose, hazard).
- **The AI only explains** a decision that is already made. If it is slow or offline, the decision is the same and a template writes the explanation.
- **Earth vs copilot:** help from Houston in 27 min; the copilot decided in under 0.1 s.

---

## 7. Measured, not claimed *(Validity)*

100 storms (67 dust devils, 27 local storms, 6 regional storms), the same for both strategies, seed 42, no AI.

| | Fixed plan | Copilot |
|---|---|---|
| **Home safely** | **51%** | **81%** |
| Exposed to the storm | 49% | 19% |
| Mean radiation dose | 0.072 mSv | 0.045 mSv |
| Samples collected | 100% | 41% |

- The copilot rescued 30 walks and **never made a safe walk unsafe**.
- **The price is science:** when in doubt, it goes home. We show this; we do not hide it.

---

## 8. How we calculate: honest about the limits *(Validity)*

- Every constant in the decision code is listed in the app's **How we calculate** screen, with its source: **33 from published sources, 36 our own assumptions, 4 still to verify**. A test fails if someone adds a constant without documenting it.
- Sources: NASA technical reports (Apollo EVA metabolic rates, TN D-7883), peer-reviewed papers (DOIs checked in Crossref), USGS and NASA data catalogues.
- Known limits:
  - the weather is simulated (calibrated on MEDA, REMS and RAD), not live;
  - the storm noise model behind the benchmark is ours;
  - the position of 3 pieces of landing hardware is approximate (marked "to verify");
  - radiation per walk is small (0.07 mSv): on Mars, radiation matters over a whole mission.

---

## 9. The Interplanetary Survival Guide *(Relevance)*

One printable page for each walk:
- the route and the **return-by time**;
- the **point of no return**;
- what to do in a dust devil, a local, regional or solar storm, a suit leak, fatigue, a marsquake, or loss of contact.

The thresholds come from the same code as the copilot, so the paper and the app never disagree.

Visual: the printed page next to the map.

---

## 10. The same engine on Earth: mountain rescue *(Influence)*

Not in the code: an idea for what comes next.

| On Mars | In our mountains |
|---|---|
| HiRISE / CTX terrain | an open mountain elevation model (for example Copernicus DEM, 30 m) |
| oxygen in the suit | daylight, battery, body heat |
| dust devils, storm fronts | thunderstorms, fog, avalanche zones |
| help from Earth in 27 min | the mountain rescue team's arrival time |
| return to the habitat | reach the hut or the road before dark |

*"The copilot answers the same question for a hiker in our mountains: can I still get back safely, and which way?"*

---

## 11. Team and thanks

- Four roles: data & presentation · algorithms · backend & AI · frontend.
- Everything runs locally: FastAPI, React, a local LLM (Ollama).
- Code, data sources and every constant: in the repository.

**Marswalk Copilot: walk further, come back safely.**
