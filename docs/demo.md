# Demo script (≈ 2 min)

Who presents: one person drives the app, one person speaks. The lines in *italics* are what the speaker says. Every number below was measured on the Jezero site (`MARSWALK_SITE=jezero`). If a number on screen differs, say the number on screen.

**The scene is scripted in code, so it is identical in every run.** The live engine loads `scenario.demo_events("jezero")` and replays three hazards at fixed simulated minutes (see [how-we-calculate.md](how-we-calculate.md), section 7). The test `backend/tests/scenario/test_scenario.py::test_demo_scene_decisions_on_jezero` checks the three decisions: REROUTE at min 30, immediate return at min 80, RETURN at min 125. If that test is green, the demo will behave as written.

## Before going on stage

- [ ] `MARSWALK_SITE=jezero`, backend and frontend running (`scripts\dev.ps1`). Ollama running, or not: the decisions are the same, only the explanation text comes from a template.
- [ ] Benchmark result loaded once beforehand (it takes ~30 s on Jezero; do not run it live).
- [ ] Simulation reset; speed set so one simulated minute ≈ 0.1-0.2 s.
- [ ] The Survival Guide print view opens (browser print preview, not a real printer).
- [ ] Backup: screen recording of a full run, on the laptop and on a USB stick.

## Timeline

| Time | On screen (what to press) | What to say |
|---|---|---|
| **0:00-0:05** | Title slide with the benchmark headline | *"In 100 simulated dust storms, our copilot brought the astronaut home safely 81 times. Following the fixed plan: 51."* |
| **0:05-0:20** | Jezero map with its layers. Click the clay target at the delta front; the popup shows `slope 7° · HiRISE + CTX · MRO` and the other layers with their mission and instrument. Turn on the **NASA hardware** layer: the Three Forks sample depot, the landing site, the descent stage | *"This is a 10 by 10 km map of Jezero crater, built from NASA data: HiRISE and CTX terrain from Mars Reconnaissance Orbiter, THEMIS from Mars Odyssey, and Perseverance's own route. Every value says where it comes from. These are the 10 sample tubes Perseverance left at Three Forks."* |
| **0:20-0:45** | Plan: habitat → *Clay, delta front*, preset **safe**, 5 hours. Show the route (5.9 km), the budget (148 min, O₂ 100 → 71%, 0.07 mSv), the verdict **GO**, the picture at the stop, and the big clock **Return by 11:56** (local solar time) | *"I want a clay sample from the delta and I have five hours. The copilot plans the route, the oxygen and the radiation dose, and gives me one number: be back by 11:56."* |
| **0:45-0:55** | **Start** the EVA. The astronaut walks west along the route; O₂, dust, wind and dose update every simulated minute | *"The EVA starts at 08:00 local time. Sensors update every minute: dust, wind, temperature, pressure, radiation."* |
| **0:55-1:25** | **Min 30 (08:29): large dust devil**, 130 m wide, carried by the wind toward the route. Pause on the decision card: the forecast cone, the alternatives, the validator crossing out the ones that still touch the cone, the rule choosing **REROUTE (detour north)**, the explanation. The counter: **"Houston's help would arrive in 27 min · copilot decided in <0.1 s"** | *"A dust devil, 130 metres wide, is heading for the route. The copilot predicts where it will be, draws alternatives, the validator removes the unsafe ones, and the rule picks the detour to the north. The AI only explains the choice. On this date, a message from Earth takes 11 minutes one way: help from Houston would come in 27 minutes. The copilot decided in a fraction of a second."* |
| **1:25-1:40** | **Min 80 (09:18): storm front**, 30 km long, moving at 15 m/s, while the astronaut is sampling at the clay target. No alternative avoids it (all marked HAZARD), so the copilot sends the astronaut home now (**EMERGENCY**). The return clock updates | *"Now a storm front, 30 kilometres long, at 54 km/h. You cannot walk around it. The copilot does not pretend: it stops the sampling and sends the astronaut home immediately."* |
| **1:40-1:48** | **Min 125 (10:02): regional storm** warning (seen from orbit) → **RETURN**, confirming the way home. Egress complete at **min 145** (10:21) | *"A regional storm is coming. The answer is always the same: go home. The astronaut is back at 10:21, well before the limit."* |
| **1:48-1:55** | Benchmark panel: copilot vs fixed plan on 100 storms | *"Same 100 storms, same seed, no AI in the loop: safe 81% versus 51%. The copilot never turned a safe walk into an unsafe one. The price is science: it brought back 41% of the samples, because when in doubt it goes home."* |
| **1:55-2:00** | **Survival Guide** print view of this EVA: route, return-by time, point of no return, what to do in a local, regional or solar storm | *"And this is the one-page Interplanetary Survival Guide for this walk. Thank you."* |

## The numbers, and where they come from

| Number | Value | Source |
|---|---|---|
| Benchmark headline | copilot 81% safe, fixed plan 51% (100 scenarios, seed 42, Jezero) | `data/processed/jezero/benchmark.json` (`pipeline/run_benchmark.py`, which calls `core/benchmark.run_benchmark`); re-run after any change in role 2's code or the site data |
| Benchmark details | 30 scenarios rescued, 0 made worse; science 41% vs 100%; mean dose 0.045 vs 0.072 mSv | same run |
| Route | 5.9 km, 148 min, O₂ 100 → 71.4%, 0.069 mSv, GO | `plan_route(jezero, habitat, ["clay_delta"], "safe")` |
| Return by | 11:56 local true solar time (min 243); sunset 18:16 | EVA start 08:00 LTST (`scenario.EVA_START_LTST_H`, Mars24) |
| Earth delay | 11.0 min one way, 27 min for help (2 × 11 + 5) | JPL approximate Keplerian elements, 2026-11-14 |
| Hazard sizes | dust devil 130 m at 3 m/s; front 30 × 5 km at 15 m/s | team parameter registry §3, [S16]-[S19] |

## If something goes wrong

| Problem | What to do |
|---|---|
| The decision card appears too fast to talk over it | Pause the simulation; the decision stays on screen |
| One frame freezes for ~1 s at min 125 | Known: the regional storm decision takes ~1.2 s to compute. Keep talking |
| Ollama is slow or down | Nothing to do: the explanation comes from the template, the decision is the same |
| The live engine fails | Switch to the screen recording |
| Someone asks "can the AI get it wrong?" | *"The AI does not decide. A fixed rule picks among options the validator has already checked. The benchmark runs without the AI and gives the same result every time."* |
| Someone asks "why a dust devil at 08:30?" | *"Honest answer: at Jezero they peak around midday. We moved it earlier so the demo fits in two minutes. The size and speed are real."* |
