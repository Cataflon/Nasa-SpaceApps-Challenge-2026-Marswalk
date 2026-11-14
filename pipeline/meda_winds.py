"""Statistica vântului MEDA la Jezero -> data/processed/jezero/wind_stats.json.

Cerere a rolului 2: zgomotul mișcării furtunilor din core/storms.py (viteză ±15 %, direcție 1°/min)
e o presupunere; registrul (PARAMETRI_REFERINTA.md, [S7]) trimite la variabilitatea vântului MEDA.

Sursa, citită în textul complet (NTRS 20230001086, descărcat prin API-ul NTRS în data/raw/refs/):
  Viúdez-Moreiras, de la Torre Juárez, Gómez-Elvira, Lorenz et al., „Winds at the Mars 2020 Landing
  Site. 2. Wind Variability and Turbulence”, JGR Planets (2022).
  - Tabelul 1: parametrii Weibull (c, k) pe intervale de ore LTST, vânt la 1,5 m, solurile ≤ 315;
  - Tabelul 2: media și percentilele 95 / 99 % (folosite aici doar ca verificare a transcrierii);
  - §4 (Fig. 6): σv = 0,57 ± 0,29 m/s noaptea și 1,85 ± 0,57 m/s ziua (vârfuri > 3,5 m/s la prânz);
    intensitatea turbulenței TI = σv / v pe 10 min: 36 ± 10 % ziua, 22 ± 10 % noaptea;
  - §5: în jurul vârtejurilor (scăderi de presiune), la prânz, c crește cu 65 %, k de la 2,16 la 2,36;
    vârfurile ajung la 9,2 × vântul de fond.

Rulare: python pipeline/meda_winds.py   (fără rasterio; fișierul de ieșire e determinist)
"""

import json
import math

import fetch_stac as fs
from build_layers import OUT

SOURCE = {
    "citation": "Viúdez-Moreiras D., de la Torre Juárez M., Gómez-Elvira J., Lorenz R.D. et al. (2022), "
                "Winds at the Mars 2020 Landing Site. 2. Wind Variability and Turbulence, JGR Planets",
    "ntrs": "https://ntrs.nasa.gov/citations/20230001086",
    "registry": "[S7]",
    "dataset": "Mars 2020 MEDA wind sensor at 1.5 m, mission sols <= 315 (MY36 Ls 22-153)",
    "checked": "values transcribed from the full text (Tables 1-2, sections 4-5); "
               "mean c*Gamma(1+1/k) checked against Table 2 in pipeline/tests/test_meda_winds.py",
}

# Tabelul 1 (Jezero): interval LTST -> (c m/s, k); Tabelul 2: media v și F^-1(0,95), F^-1(0,99).
WEIBULL_BY_TIMESLOT = {
    "early_morning": {"ltst_h": [3, 7], "c_ms": 1.31, "k": 1.97, "table2_mean_ms": 1.16, "p95_ms": 2.29, "p99_ms": 2.84},
    "morning": {"ltst_h": [7, 10], "c_ms": 3.02, "k": 2.01, "table2_mean_ms": 2.68, "p95_ms": 5.22, "p99_ms": 6.47},
    "midday": {"ltst_h": [10, 15], "c_ms": 5.28, "k": 2.16, "table2_mean_ms": 4.67, "p95_ms": 8.77, "p99_ms": 10.69},
    "afternoon": {"ltst_h": [15, 18], "c_ms": 6.80, "k": 3.02, "table2_mean_ms": 6.08, "p95_ms": 9.78, "p99_ms": 11.28},
    "nightfall": {"ltst_h": [18, 21], "c_ms": 3.24, "k": 1.97, "table2_mean_ms": 2.87, "p95_ms": 5.66, "p99_ms": 7.03},
    "night_1": {"ltst_h": [21, 24], "c_ms": 3.42, "k": 2.54, "table2_mean_ms": 3.04, "p95_ms": 5.26, "p99_ms": 6.23},
    "night_2": {"ltst_h": [0, 3], "c_ms": 2.13, "k": 1.49, "table2_mean_ms": 1.91, "p95_ms": 4.45, "p99_ms": 5.94},
}
WEIBULL_TOTAL = {"c_ms": 3.57, "k": 1.49, "table2_mean_ms": 3.22, "p95_ms": 7.46, "p99_ms": 9.95}

TURBULENCE = {
    "definition": "TI = standard deviation of wind speed / mean wind speed, over 10-min periods",
    "ti_day": {"mean": 0.36, "sd": 0.10},
    "ti_night": {"mean": 0.22, "sd": 0.10},
    "sigma_v_day_ms": {"mean": 1.85, "sd": 0.57, "midday_peaks_above": 3.5},
    "sigma_v_night_ms": {"mean": 0.57, "sd": 0.29},
}
VORTICES = {
    "midday_c_increase_frac": 0.65,
    "midday_k": {"all": 2.16, "around_pressure_drops": 2.36},
    "peak_over_background": 9.2,
}


def weibull_mean(c: float, k: float) -> float:
    return c * math.gamma(1.0 + 1.0 / k)


def weibull_quantile(c: float, k: float, p: float) -> float:
    return c * (-math.log(1.0 - p)) ** (1.0 / k)


def build() -> dict:
    slots = {}
    for name, s in WEIBULL_BY_TIMESLOT.items():
        slots[name] = {**s, "mean_ms": round(weibull_mean(s["c_ms"], s["k"]), 2)}
    return {
        "source": SOURCE,
        "weibull_by_timeslot": slots,
        "weibull_total": {**WEIBULL_TOTAL, "mean_ms": round(weibull_mean(WEIBULL_TOTAL["c_ms"], WEIBULL_TOTAL["k"]), 2)},
        "turbulence": TURBULENCE,
        "convective_vortices": VORTICES,
        "notes": [
            "Dust devils move with the background wind (registry 3.1), so the relative speed variability of a "
            "moving hazard can be taken from TI: 36 +/- 10 % in daytime (the current storms.py assumption is 15 %).",
            "TI is measured over 10-min windows at 1.5 m; the translation speed of a vortex averages over its size, "
            "so 36 % is an upper bound for its speed noise.",
            "The paper gives no single number for wind-direction variability; it reports full wind rotations at "
            "19-21 h LTST and strong direction disturbances during vortex passages.",
        ],
    }


def main() -> None:
    path = OUT / "wind_stats.json"
    fs.atomic_write_text(path, json.dumps(build(), indent=2, ensure_ascii=False) + "\n")
    print(f"Scris {path}")


if __name__ == "__main__":
    main()
