"""Generatorul de scenarii: serii de timp pentru praf, vânt, temperatură, presiune, radiație + evenimente.

Valorile sunt calibrate pe Perseverance MEDA (Jezero), Curiosity REMS și RAD (Gale). Seed fix ->
scenarii reproductibile. În prezentare: „scenarii simulate, calibrate pe MEDA, REMS și RAD”.

Modelul, pe scurt:
  - fiecare mărime = ciclu diurn (după ora solară locală, LTST) + zgomot corelat (Ornstein-Uhlenbeck);
  - vântul are și rafale rare;
  - evenimentele adaugă anvelope netede (rampă, platou, coborâre) peste serii;
  - temperatura se calculează la final, pentru că praful îi micșorează amplitudinea diurnă;
  - doza scade ușor când presiunea crește (mai multă atmosferă deasupra).

Toate numerele aleatoare se trag ÎNAINTE de evenimente, cu dimensiuni fixe, deci adăugarea unui
eveniment nu schimbă restul scenariului: minutele dinaintea evenimentului rămân identice.

Partea spațială a furtunilor (unde e furtuna pe hartă) o face core/hazards.py (rolul 2). Aici e doar
ce „simt” senzorii astronautului în timp. O₂-ul și doza totală le calculează motorul (rolul 3).

Etichete de proveniență: vezi SENSOR_LABELS.
"""

import json
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------------------------
# Constante calibrate. „de verificat” = cifră din literatură citată din memorie, încă necitită
# efectiv; „presupunere” = aleasă de noi. Lista completă e și în docs/sources.md.
# ---------------------------------------------------------------------------------------------

# Timpul pe Marte. Un sol = 24 h 39 min 35 s = 1479,6 min terestre (NASA GISS Mars24).
SOL_MIN = 1479.6
MARS_HOUR_MIN = SOL_MIN / 24.0
EVA_START_LTST_H = 9.0  # presupunere: ieșirea pornește la 09:00 ora solară locală

# Opacitatea prafului (tau). Jezero, primul an Mars 2020: tau ~0,3-1,0, tipic ~0,5-0,7
# (Lemmon et al. 2022, GRL, „Dust, sand, and winds within an active Martian storm in Jezero crater”;
# Mastcam-Z + MEDA SkyCam). de verificat
TAU_MEAN = 0.6
TAU_SIGMA = 0.05  # variația lentă într-o zi fără furtună (presupunere)
TAU_TAU_MIN = 120.0  # timpul de corelație al zgomotului (presupunere)
TAU_RANGE = (0.1, 10.0)  # MY34: tau > 8 la Gale (Guzewich et al. 2019, GRL). de verificat

# Vântul la ~1,5 m. Jezero: slab dimineața (~2-4 m/s), maxim după-amiaza (~6-10 m/s), rafale
# (Newman et al. 2022, Science Advances, „The dynamic atmospheric and aeolian environment of Jezero
# crater, Mars”; MEDA WS). de verificat
WIND_BASE_MS = 3.0
WIND_DIURNAL_MS = 4.0  # amplitudinea în plus la vârful de după-amiază
WIND_PEAK_LTST_H = 14.0
WIND_SIGMA_MS = 1.0
WIND_TAU_MIN = 10.0
GUST_PROB_PER_MIN = 1 / 25  # presupunere
GUST_MEAN_MS = 3.0  # presupunere
WIND_RANGE = (0.0, 40.0)

# Temperatura aerului la ~1,5 m. Jezero: ~-85 °C înainte de răsărit, ~-20 °C după-amiaza devreme
# (Munguira et al. 2023, JGR Planets, temperaturile MEDA ATS). de verificat
TEMP_MEAN_C = -52.5
TEMP_AMP_C = 32.5
TEMP_PEAK_LTST_H = 13.5
TEMP_SIGMA_C = 1.0
TEMP_TAU_MIN = 20.0
# Praful reduce amplitudinea diurnă (încălzire mai slabă ziua): factor 1/(1 + k·(tau − TAU_MEAN)).
# Efect observat în furtunile din Jezero și Gale (Lemmon et al. 2022); valoarea k e presupunere.
TEMP_DUST_DAMPING = 0.35
TEMP_RANGE = (-110.0, 10.0)

# Presiunea. Jezero: ~650-770 Pa de-a lungul anului, maree termică de câteva procente pe zi
# (Sánchez-Lavega et al. 2023, JGR Planets, presiunea MEDA PS). de verificat
PRESSURE_MEAN_PA = 720.0
PRESSURE_DIURNAL_PA = 12.0
PRESSURE_PEAK_LTST_H = 8.0  # maximul de dimineață al mareei diurne
PRESSURE_SIGMA_PA = 1.0
PRESSURE_TAU_MIN = 60.0
PRESSURE_RANGE = (550.0, 900.0)

# Doza. RAD la Gale: 0,21 mGy/zi doză absorbită ≈ 8,8 µGy/h; doza echivalentă 0,64 mSv/zi ≈ 27 µSv/h
# (Hassler et al. 2014, Science, „Mars' surface radiation environment measured with the Mars Science
# Laboratory's Curiosity rover”). Unitatea e µSv/h (Sievert = doză ECHIVALENTĂ), deci folosim
# 0,64 mSv/zi / 24 h = 26,7 µSv/h. Decizia echipei (14.11.2026). de verificat
# Același fond îl folosește și stratul radiation.npy (pipeline/make_synthetic_site.py).
DOSE_RATE_USV_H = 26.7
DOSE_SIGMA_FRAC = 0.03  # presupunere
DOSE_TAU_MIN = 60.0
# Doza scade când presiunea crește (Rafkin et al. 2014, JGR Planets, variația diurnă a dozei RAD).
# Coeficientul e presupunere: ±1,7% presiune -> ∓~1,5% doză.
DOSE_PRESSURE_COEF = 0.9

# ---------------------------------------------------------------------------------------------
# Evenimentele: parametrii impliciți (suprascriși din `params`).
# ---------------------------------------------------------------------------------------------

# Vârtej de praf: scurt, vânt mare, presiunea scade câțiva Pa (MEDA a detectat sute de vârtejuri,
# cu scăderi tipice de 0,5-3 Pa; Newman et al. 2022). de verificat
DUST_DEVIL = {"intensity": 0.5, "peak_after_min": 0.0, "duration_min": 3.0,
              "tau_add": 0.5, "wind_add_ms": 15.0, "pressure_drop_pa": 3.0}
# Furtună locală care trece peste astronaut. Furtuna din Jezero din ianuarie 2022: tau ~2,
# rafale > 20 m/s (Lemmon et al. 2022). de verificat
LOCAL_STORM = {"intensity": 0.7, "peak_after_min": 16.0, "duration_min": 30.0, "rise_min": 8.0,
               "tau_add": 2.0, "wind_add_ms": 15.0}
# Furtună regională: crește treptat și nu se termină în timpul ieșirii (durează zile).
REGIONAL_STORM = {"intensity": 0.9, "ramp_min": 120.0, "tau_peak": 3.0, "wind_add_ms": 10.0}
# Furtună solară (SEP): multiplicatorul dozei. Contractul (live_messages.json) folosește
# `dose_rate_multiplier` și `duration_min`. RAD a înregistrat creșteri de câteva ori până la zeci
# de ori față de fond (sept. 2017: Zeitlin et al. 2018, GRL; mai 2024: ~8 mGy cumulat, NASA).
# de verificat
SOLAR_PARTICLE_EVENT = {"dose_rate_multiplier": 20.0, "duration_min": 60.0, "rise_min": 10.0,
                        "decay_min": 30.0}

# Evenimentele care nu schimbă senzorii de mediu: efectul lor (zonă blocată, consum de O₂,
# viteză) îl aplică motorul (rolul 3) și core/ (rolul 2).
NON_SENSOR_EVENTS = {"marsquake", "suit_leak", "fatigue"}
SENSOR_EVENTS = {"dust_devil", "local_storm", "regional_storm", "solar_particle_event"}
ALLOWED_EVENTS = SENSOR_EVENTS | NON_SENSOR_EVENTS  # = _allowed_events din live_event.json

SENSOR_KEYS = ("dust_tau", "wind_ms", "temp_c", "pressure_pa", "dose_rate_usv_h")

# Etichetele fiecărei mărimi: tip de date, misiunea și instrumentul pe care sunt calibrate.
SENSOR_LABELS = {
    "dust_tau": {"data_type": "atmospheric", "mission": "Mars 2020 Perseverance", "instrument": "MEDA SkyCam + Mastcam-Z", "unit": "tau"},
    "wind_ms": {"data_type": "atmospheric", "mission": "Mars 2020 Perseverance", "instrument": "MEDA WS", "unit": "m/s"},
    "temp_c": {"data_type": "atmospheric", "mission": "Mars 2020 Perseverance + MSL Curiosity", "instrument": "MEDA ATS, REMS", "unit": "°C"},
    "pressure_pa": {"data_type": "atmospheric", "mission": "Mars 2020 Perseverance + MSL Curiosity", "instrument": "MEDA PS, REMS", "unit": "Pa"},
    "dose_rate_usv_h": {"data_type": "radiation", "mission": "MSL Curiosity", "instrument": "RAD", "unit": "µSv/h"},
}

# Valorile constante, folosite de motor (rolul 3) ca fallback. Media la începutul ieșirii.
BASELINE = {
    "dust_tau": TAU_MEAN,
    "wind_ms": 5.0,
    "temp_c": -40.0,
    "pressure_pa": PRESSURE_MEAN_PA,
    "dose_rate_usv_h": DOSE_RATE_USV_H,
}


@dataclass
class ScheduledEvent:
    t_min: float
    event: str
    params: dict = field(default_factory=dict)


@dataclass
class Scenario:
    seed: int
    duration_min: int
    sensors: list[dict]  # un dict pe minut
    events: list[ScheduledEvent]


# ---------------------------------------------------------------------------------------------
# Ajutoare
# ---------------------------------------------------------------------------------------------


def ltst_hours(t_min: np.ndarray) -> np.ndarray:
    """Ora solară locală (0-24) pentru minutele de la începutul ieșirii."""
    return (EVA_START_LTST_H + t_min / MARS_HOUR_MIN) % 24.0


def _diurnal(t_min: np.ndarray, peak_h: float) -> np.ndarray:
    """Cosinus cu perioada de un sol și maximul la ora `peak_h` (LTST); valori în [-1, 1]."""
    return np.cos(2 * np.pi * (ltst_hours(t_min) - peak_h) / 24.0)


def _ou(eps: np.ndarray, sigma: float, tau_min: float) -> np.ndarray:
    """Zgomot corelat Ornstein-Uhlenbeck (pas de 1 min) din zgomot alb standard deja tras."""
    phi = float(np.exp(-1.0 / tau_min))
    scale = sigma * np.sqrt(1 - phi**2)
    out = np.empty_like(eps)
    x = sigma * eps[0]  # pornim din distribuția staționară
    for i, e in enumerate(eps):
        if i:
            x = phi * x + scale * e
        out[i] = x
    return out


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _envelope(t: np.ndarray, start: float, rise: float, plateau: float, fall: float) -> np.ndarray:
    """0 înainte de `start`, crește lin în `rise` min, 1 pe `plateau`, scade lin în `fall` min."""
    up = _smoothstep((t - start) / max(rise, 1e-9))
    down = 1.0 - _smoothstep((t - (start + rise + plateau)) / max(fall, 1e-9))
    return np.where(t < start, 0.0, up * down)


def _params(defaults: dict, params: dict) -> dict:
    out = {**defaults, **{k: v for k, v in params.items() if k in defaults}}
    if "intensity" in out:
        out["intensity"] = float(np.clip(out["intensity"], 0.0, 1.0))
    return out


def _local_storm_duration(params: dict) -> float:
    """Cât ține trecerea furtunii: 2 × semiaxa mare / viteză, dacă sunt date; altfel implicit."""
    if "duration_min" in params:
        return float(params["duration_min"])
    axes, vel = params.get("axes_m"), params.get("velocity_ms")
    if axes and vel:
        speed = float(np.hypot(*vel))
        if speed > 0.1:
            return float(np.clip(2 * max(axes) / speed / 60.0, 10.0, 120.0))
    return LOCAL_STORM["duration_min"]


def _event_key(ev: ScheduledEvent) -> tuple:
    return (float(ev.t_min), ev.event, json.dumps(ev.params, sort_keys=True, default=str))


# ---------------------------------------------------------------------------------------------
# Generatorul
# ---------------------------------------------------------------------------------------------


def generate(seed: int = 42, duration_min: int = 300, events: list[ScheduledEvent] | None = None) -> Scenario:
    """Scenariul complet: `duration_min + 1` dicturi (minutele 0..duration_min inclusiv).

    Fiecare dict are exact cheile din SENSOR_KEYS, ca float-uri Python (serializabile JSON).
    Aceeași intrare dă exact aceeași ieșire. Ridică ValueError pentru evenimente necunoscute.
    """
    if duration_min < 0:
        raise ValueError("duration_min must be >= 0")
    events = sorted(events or [], key=_event_key)
    for ev in events:
        if ev.event not in ALLOWED_EVENTS:
            raise ValueError(f"Unknown event: {ev.event!r}. Allowed: {sorted(ALLOWED_EVENTS)}")

    n = int(duration_min) + 1
    t = np.arange(n, dtype=np.float64)
    rng = np.random.default_rng(seed)

    # 1. Toate numerele aleatoare, în ordine fixă și cu dimensiuni fixe.
    eps = rng.standard_normal((5, n))
    gust_on = rng.random(n) < GUST_PROB_PER_MIN
    gust_amp = rng.exponential(GUST_MEAN_MS, n)

    # 2. Seriile de bază.
    tau = TAU_MEAN + _ou(eps[0], TAU_SIGMA, TAU_TAU_MIN)
    wind_diurnal = np.clip(_diurnal(t, WIND_PEAK_LTST_H), 0, None)  # vântul crește doar ziua
    wind = WIND_BASE_MS + WIND_DIURNAL_MS * wind_diurnal + _ou(eps[1], WIND_SIGMA_MS, WIND_TAU_MIN)
    wind = wind + np.where(gust_on, gust_amp, 0.0)
    pressure = (PRESSURE_MEAN_PA + PRESSURE_DIURNAL_PA * _diurnal(t, PRESSURE_PEAK_LTST_H)
                + _ou(eps[2], PRESSURE_SIGMA_PA, PRESSURE_TAU_MIN))
    temp_noise = _ou(eps[3], TEMP_SIGMA_C, TEMP_TAU_MIN)
    dose_noise = _ou(eps[4], DOSE_SIGMA_FRAC, DOSE_TAU_MIN)
    dose_mult = np.ones(n)

    # 3. Evenimentele (deterministe, fără numere aleatoare).
    for ev in events:
        t0, p = float(ev.t_min), ev.params or {}
        if ev.event == "dust_devil":
            q = _params(DUST_DEVIL, p)
            env = q["intensity"] * _envelope(t, t0 + q["peak_after_min"], 1.0, max(q["duration_min"] - 2, 0), 1.0)
            tau += q["tau_add"] * env
            wind += q["wind_add_ms"] * env
            pressure -= q["pressure_drop_pa"] * env
        elif ev.event == "local_storm":
            q = _params(LOCAL_STORM, p)
            dur = _local_storm_duration(p)
            rise = min(q["rise_min"], dur / 2)
            start = t0 + max(q["peak_after_min"] - rise, 0.0)
            env = q["intensity"] * _envelope(t, start, rise, max(dur - 2 * rise, 0.0), rise)
            tau += q["tau_add"] * env
            wind += q["wind_add_ms"] * env
        elif ev.event == "regional_storm":
            q = _params(REGIONAL_STORM, p)
            env = q["intensity"] * _envelope(t, t0, q["ramp_min"], np.inf, 1.0)
            tau += max(q["tau_peak"] - TAU_MEAN, 0.0) * env
            wind += q["wind_add_ms"] * env
        elif ev.event == "solar_particle_event":
            q = _params(SOLAR_PARTICLE_EVENT, p)
            env = _envelope(t, t0, q["rise_min"], max(q["duration_min"] - q["rise_min"], 0.0), q["decay_min"])
            dose_mult *= 1.0 + (max(float(q["dose_rate_multiplier"]), 1.0) - 1.0) * env
        # marsquake, suit_leak, fatigue: fără efect pe senzorii de mediu.

    tau = np.clip(tau, *TAU_RANGE)
    wind = np.clip(wind, *WIND_RANGE)
    pressure = np.clip(pressure, *PRESSURE_RANGE)

    # 4. Temperatura: praful micșorează amplitudinea diurnă.
    damping = 1.0 / (1.0 + TEMP_DUST_DAMPING * np.clip(tau - TAU_MEAN, 0, None))
    temp = TEMP_MEAN_C + TEMP_AMP_C * _diurnal(t, TEMP_PEAK_LTST_H) * damping + temp_noise
    temp = np.clip(temp, *TEMP_RANGE)

    # 5. Doza: fond × presiune × zgomot × furtuni solare.
    dose = (DOSE_RATE_USV_H * (1.0 - DOSE_PRESSURE_COEF * (pressure - PRESSURE_MEAN_PA) / PRESSURE_MEAN_PA)
            * (1.0 + dose_noise) * dose_mult)
    dose = np.clip(dose, 0.0, None)

    sensors = [
        {"dust_tau": round(float(a), 3), "wind_ms": round(float(b), 2), "temp_c": round(float(c), 2),
         "pressure_pa": round(float(d), 1), "dose_rate_usv_h": round(float(e), 3)}
        for a, b, c, d, e in zip(tau, wind, temp, pressure, dose)
    ]
    return Scenario(seed=seed, duration_min=int(duration_min), sensors=sensors, events=events)


def with_event(scenario: Scenario, event: ScheduledEvent) -> Scenario:
    """Același scenariu plus un eveniment injectat live (POST /api/live/event).

    Minutele dinaintea evenimentului rămân identice, deci motorul poate înlocui scenariul
    în mijlocul ieșirii fără salturi în valorile deja trimise.
    """
    return generate(scenario.seed, scenario.duration_min, [*scenario.events, event])


def sensors_at(scenario: Scenario, t_min: float) -> dict:
    """Senzorii la minutul `t_min` (rotunjit în jos), limitat la intervalul scenariului."""
    i = int(np.clip(np.floor(t_min), 0, len(scenario.sensors) - 1))
    return dict(scenario.sensors[i])


# Scenariul demo-ului (README, secțiunea 8), pe situl sintetic. Furtuna locală pornește la 3 km
# vest de traseul habitat -> clay_delta, se mișcă spre est cu 2,5 m/s și ajunge pe traseu în
# ~16 min. Furtuna regională vine mai târziu și impune RETURN.
DEMO_SCENARIO_EVENTS = [
    ScheduledEvent(72, "local_storm", {"center": {"row": 220, "col": 30}, "axes_m": [1800, 1100], "velocity_ms": [0.0, 2.5], "intensity": 0.7}),
    ScheduledEvent(170, "regional_storm", {"intensity": 0.9}),
]

# Pe Jezero (data/processed/jezero): habitatul e la (229, 264), lângă locul de aterizare, iar
# clay_delta la (211, 115), la baza frontului deltei, ~3 km vest. Traseul merge spre vest, deci
# furtuna locală vine din SUD (3 km sub capătul vestic al traseului) și urcă spre nord cu 2,5 m/s
# (vy < 0 = spre nord, row crește spre sud), tăind traseul în ~20 min.
JEZERO_DEMO_EVENTS = [
    ScheduledEvent(72, "local_storm", {"center": {"row": 361, "col": 150}, "axes_m": [1800, 1100], "angle_deg": 90,
                                       "velocity_ms": [-2.5, 0.0], "intensity": 0.7}),
    ScheduledEvent(170, "regional_storm", {"intensity": 0.9}),
]

# Coordonatele furtunii depind de sit (habitatul și țintele sunt în alte celule).
DEMO_EVENTS_BY_SITE: dict[str, list[ScheduledEvent]] = {
    "synthetic": DEMO_SCENARIO_EVENTS,
    "jezero": JEZERO_DEMO_EVENTS,
}


def demo_events(site_id: str = "synthetic") -> list[ScheduledEvent]:
    """Evenimentele demo pentru situl dat (copie), cu fallback pe situl sintetic."""
    evs = DEMO_EVENTS_BY_SITE.get(site_id, DEMO_SCENARIO_EVENTS)
    return [ScheduledEvent(e.t_min, e.event, json.loads(json.dumps(e.params))) for e in evs]
