# How we calculate

Source for the in-app "How we calculate" screen and for the slides. Every number has a source or is marked **assumption**.

| Quantity | Formula / value | Source | Status |
|---|---|---|---|
| Walking speed | Tobler: `6·exp(-3.5·|tan θ + 0.05|)` km/h × suit factor 0.6 | Tobler (1993); suit factor | assumption |
| O₂ consumption | 0.12 %/min at rest, ~0.25 %/min walking (220 W extra metabolic load) | NASA NTRS (Apollo EVAs, suited walking tests) | to verify |
| O₂ reserve on arrival | 30% | — | assumption |
| Maximum slope | 25° | NASA human EVA studies | to verify |
| Margin before sunset | 30 min | — | assumption |
| Surface dose rate | ~10 µSv/h (order of magnitude) | Curiosity RAD | to verify |
| Dose limit per EVA | 1 mSv | — | assumption |
| Solar particle event | dose rate × 20 for 60 min | — | assumption |
| Suit leak | +0.15 %/min O₂ | — | assumption |
| Fatigue | speed × 0.8, O₂ × 1.15 | — | assumption |
| Sunset | Mars24 | NASA GISS | TODO |
| Effective sunset with dust | `sunset − max(0, τ − 0.5)·30` min | — | assumption |
| Weight presets | see `backend/app/core/costmap.py` | — | fixed, chosen by the team |
