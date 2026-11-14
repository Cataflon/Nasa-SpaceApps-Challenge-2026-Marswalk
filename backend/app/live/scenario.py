"""Generatorul de scenarii: serii de timp pentru praf, vânt, temperatură, presiune, radiație + evenimente.

Valorile sunt calibrate pe Perseverance MEDA (Jezero), Curiosity REMS și RAD (Gale). Seed fix ->
scenarii reproductibile. În prezentare: „scenarii simulate, calibrate pe MEDA, REMS și RAD”.

Modelul, pe scurt:
  - fiecare mărime = ciclu diurn (după ora solară locală, LTST) + zgomot corelat (Ornstein-Uhlenbeck);
  - vântul are marginala Weibull (rafalele vin din coada distribuției);
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
import math
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------------------------
# Constante calibrate. „de verificat” = cifră din literatură citată din memorie, încă necitită
# efectiv; „presupunere” = aleasă de noi. Lista completă e și în docs/sources.md.
# ---------------------------------------------------------------------------------------------

# Timpul pe Marte. Un sol = 24 h 39 min 35 s = 1479,6 min terestre (NASA GISS Mars24).
SOL_MIN = 1479.6
MARS_HOUR_MIN = SOL_MIN / 24.0
# Ieșirea pornește la ≈ 08:00 ora solară locală: aceeași clipă ca planner-ul rolului 2
# (core/planner.SOL_START_UTC = 2026-11-14 14:22 UTC ≈ 08:00 LTST la Jezero). Frontendul afișează
# ceasul de întoarcere din ea, deci trebuie să fie identică cu a planner-ului (test în tests/scenario).
EVA_START_LTST_H = 8.0
DEMO_DATE_UTC = "2026-11-14T14:22:00Z"  # = core/planner.SOL_START_UTC

# Întârzierea Pământ-Marte la data demo-ului. Distanța din elementele kepleriene aproximative JPL
# (Standish, „Keplerian Elements for Approximate Positions of the Major Planets”, 1800-2050):
# 14.11.2026 -> 1,319 UA -> lumina face 10,97 min într-un sens. Verificat pe cazuri cunoscute:
# opoziția din 16.01.2025 -> 0,644 UA, conjuncția din 18.11.2023 -> 2,53 UA. Vezi earth_mars_light_min().
EARTH_ONE_WAY_DELAY_MIN = 11.0
MISSION_CONTROL_REACTION_MIN = 5.0  # presupunere: timpul echipei de la sol să analizeze și să răspundă
EARTH_ROUND_TRIP_MIN = 2 * EARTH_ONE_WAY_DELAY_MIN + MISSION_CONTROL_REACTION_MIN  # 27 min
EARTH_DELAY_SOURCE = "JPL approximate Keplerian elements (Standish); Earth-Mars distance 1.319 AU on 2026-11-14"

# Opacitatea prafului (tau). Sezonul liniștit la Jezero: tau ≈ 0,5 (registrul echipei [S8],
# Savijärvi et al.; Lemmon et al. 2022, GRL: ~0,3-1,0 în primul an Mars 2020). Crește doar la
# evenimentele de praf. Cu 0,5, apusul efectiv (daylight.effective_sunset_min) nu se mută fără furtună.
TAU_MEAN = 0.5
TAU_SIGMA = 0.05  # variația lentă într-o zi fără furtună (presupunere)
TAU_TAU_MIN = 120.0  # timpul de corelație al zgomotului (presupunere)
TAU_RANGE = (0.1, 10.0)  # MY34: tau > 8 la Gale (Guzewich et al. 2019, GRL). de verificat

# Vântul la ~1,5 m: eșantionat dintr-o distribuție Weibull, nu o sinusoidă cu rafale adăugate.
# Rafalele (de la calm la 10-15 m/s în minute) vin din coada distribuției (registrul [S7], Newman et
# al. 2022, Science Advances; MEDA WS). Turbulența = zgomot corelat pe câteva minute, trecut prin
# funcția de repartiție Weibull (copulă gaussiană), deci fiecare minut are exact marginala Weibull.
# Media urmează ciclul zilnic: calm dimineața, maxim după-amiaza. Forma k și mediile sunt de ajustat
# pe datele MEDA (registrul: nivel B pentru parametri). de verificat
WIND_WEIBULL_K = 2.0
WIND_MEAN_MS = 3.0  # media dimineața și noaptea
WIND_DIURNAL_MS = 3.0  # în plus la vârful de după-amiază (media ajunge la 6 m/s)
WIND_PEAK_LTST_H = 14.0
WIND_TAU_MIN = 3.0  # timpul de corelație al turbulenței (presupunere)
WIND_RANGE = (0.0, 40.0)

# Temperatura aerului la ~1,5 m. Jezero: −83 °C înainte de răsărit → −23 °C la prânz (registrul [S3]),
# fluctuații de ±2,5 K la prânz [S10] (Munguira et al. 2023, JGR Planets, MEDA ATS).
TEMP_MEAN_C = -53.0
TEMP_AMP_C = 30.0
TEMP_PEAK_LTST_H = 12.5
TEMP_SIGMA_C = 2.5
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

# Doza. RAD la Gale, aug. 2012 - iun. 2013: doza echivalentă GCR 0,67 mSv/zi (Hassler, comunicatul
# SwRI din 9.12.2013, registrul [S11]; verificat pe pagină) -> 0,67 / 24 = 27,9 ≈ 28 µSv/h. Doza
# absorbită: 0,21 mGy/zi (Hassler et al. 2014, Science [S12]). Unitatea e µSv/h (doză ECHIVALENTĂ).
# Același fond îl folosesc straturile radiation.npy (pipeline/make_synthetic_site.py, build_layers.py).
DOSE_RATE_USV_H = 28.0
DOSE_SIGMA_FRAC = 0.03  # presupunere
DOSE_TAU_MIN = 60.0
# Ciclul zilnic: doza absorbită variază între 180 și 225 µGy/zi, invers cu presiunea (mai multă
# atmosferă deasupra = mai puțină doză) -> ±11% (registrul [S12]; Rafkin et al. 2014). Legarea de
# anomalia presiunii (±PRESSURE_DIURNAL_PA = ±11%) e presupunerea noastră.
DOSE_DIURNAL_FRAC = 0.11

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
# Furtună solară (SEP): multiplicatorul dozei. Cea mai mare furtună solară văzută de RAD la suprafață
# (sept. 2017) a dat doza × 2-3 față de fond, cu creștere pe parcursul câtorva ore și scădere lentă
# pe ~36 h (Zeitlin et al. 2018, GRL, doi:10.1029/2018GL077760; registrul [S14] [S15]) -> × 2,5.
# Contractul (live_messages.json) folosește `dose_rate_multiplier` și `duration_min`
# (= creștere + platou; creșterea e cel mult duration_min). DOI-urile sunt verificate în docs/sources.md.
SOLAR_PARTICLE_EVENT = {"dose_rate_multiplier": 2.5, "duration_min": 240.0, "rise_min": 120.0,
                        "decay_min": 2160.0}

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
    """Cât ține trecerea furtunii peste astronaut: 2 × întinderea elipsei pe direcția de mers / viteză.

    Un front lung (30 × 5 km) care înaintează perpendicular pe axa lungă trece în câteva minute, nu
    într-o oră: contează semiaxa pe direcția vitezei. Unghiurile ca în core/hazards.py: `angle_deg`
    de la est, în sensul acelor de ceasornic pe hartă; viteza e (vy spre sud, vx spre est).
    """
    if "duration_min" in params:
        return float(params["duration_min"])
    axes, vel = params.get("axes_m"), params.get("velocity_ms")
    if axes and vel:
        speed = float(np.hypot(*vel))
        if speed > 0.1:
            phi = np.arctan2(vel[0], vel[1]) - np.radians(float(params.get("angle_deg", 0.0)))
            extent = float(np.hypot(axes[0] * np.cos(phi), axes[1] * np.sin(phi)))
            return float(np.clip(2 * extent / speed / 60.0, 3.0, 120.0))
    return LOCAL_STORM["duration_min"]


def _weibull(z: np.ndarray, mean: np.ndarray, k: float) -> np.ndarray:
    """Zgomot normal standard -> viteze cu marginala Weibull(k) și media dată (copulă gaussiană)."""
    u = 0.5 * (1.0 + _erf(z / np.sqrt(2.0)))
    u = np.clip(u, 1e-12, 1.0 - 1e-12)
    scale = mean / math.gamma(1.0 + 1.0 / k)
    return scale * (-np.log1p(-u)) ** (1.0 / k)


_erf = np.vectorize(math.erf, otypes=[np.float64])


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

    # 2. Seriile de bază.
    tau = TAU_MEAN + _ou(eps[0], TAU_SIGMA, TAU_TAU_MIN)
    wind_mean = WIND_MEAN_MS + WIND_DIURNAL_MS * np.clip(_diurnal(t, WIND_PEAK_LTST_H), 0, None)
    wind = _weibull(_ou(eps[1], 1.0, WIND_TAU_MIN), wind_mean, WIND_WEIBULL_K)
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
            rise = min(q["rise_min"], q["duration_min"])
            env = _envelope(t, t0, rise, q["duration_min"] - rise, q["decay_min"])
            dose_mult *= 1.0 + (max(float(q["dose_rate_multiplier"]), 1.0) - 1.0) * env
        # marsquake, suit_leak, fatigue: fără efect pe senzorii de mediu.

    tau = np.clip(tau, *TAU_RANGE)
    wind = np.clip(wind, *WIND_RANGE)
    pressure = np.clip(pressure, *PRESSURE_RANGE)

    # 4. Temperatura: praful micșorează amplitudinea diurnă.
    damping = 1.0 / (1.0 + TEMP_DUST_DAMPING * np.clip(tau - TAU_MEAN, 0, None))
    temp = TEMP_MEAN_C + TEMP_AMP_C * _diurnal(t, TEMP_PEAK_LTST_H) * damping + temp_noise
    temp = np.clip(temp, *TEMP_RANGE)

    # 5. Doza: fond × ciclul zilnic (invers cu presiunea) × zgomot × furtuni solare.
    pressure_cycle = (pressure - PRESSURE_MEAN_PA) / PRESSURE_DIURNAL_PA
    dose = (DOSE_RATE_USV_H * np.clip(1.0 - DOSE_DIURNAL_FRAC * pressure_cycle, 0.5, 1.5)
            * (1.0 + dose_noise) * dose_mult)
    dose = np.clip(dose, 0.0, None)

    sensors = [
        {"dust_tau": round(float(a), 3), "wind_ms": round(float(b), 2), "temp_c": round(float(c), 2),
         "pressure_pa": round(float(d), 1), "dose_rate_usv_h": round(float(e), 3)}
        for a, b, c, d, e in zip(tau, wind, temp, pressure, dose)
    ]
    return Scenario(seed=seed, duration_min=int(duration_min), sensors=sensors, events=events)


# Elementele kepleriene aproximative JPL (Standish), tabelul pentru 1800-2050:
# (a [UA], e, I [°], L [°], longitudinea periheliului [°], longitudinea nodului [°]) + ratele pe secol.
_KEPLER = {
    "earth": ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
              (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
    "mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
}
AU_KM = 149597870.7
C_KM_S = 299792.458


def _helio(planet: str, jd: float) -> tuple[float, float, float]:
    """Poziția heliocentrică ecliptică (UA) din elementele kepleriene aproximative."""
    t = (jd - 2451545.0) / 36525
    base, rate = _KEPLER[planet]
    a, e, inc, mean_long, peri, node = (b + r * t for b, r in zip(base, rate))
    m = np.radians((mean_long - peri + 180) % 360 - 180)
    w, inc, node = np.radians(peri - node), np.radians(inc), np.radians(node)
    ecc = m + e * np.sin(m)
    for _ in range(20):
        ecc -= (ecc - e * np.sin(ecc) - m) / (1 - e * np.cos(ecc))
    x, y = a * (np.cos(ecc) - e), a * np.sqrt(1 - e * e) * np.sin(ecc)
    cw, sw, cn, sn, ci, si = np.cos(w), np.sin(w), np.cos(node), np.sin(node), np.cos(inc), np.sin(inc)
    return (float((cw * cn - sw * sn * ci) * x + (-sw * cn - cw * sn * ci) * y),
            float((cw * sn + sw * cn * ci) * x + (-sw * sn + cw * cn * ci) * y),
            float(sw * si * x + cw * si * y))


def earth_mars_light_min(utc_iso: str) -> float:
    """Timpul luminii Pământ-Marte (minute, într-un sens) la momentul UTC dat (precizie ~1%)."""
    from datetime import datetime

    jd = datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).timestamp() / 86400 + 2440587.5
    dist_au = float(np.linalg.norm(np.subtract(_helio("earth", jd), _helio("mars", jd))))
    return dist_au * AU_KM / C_KM_S / 60


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


# Scena demo (README, secțiunea 8), cu pericole la mărimea lor reală (registrul echipei, §3):
#   1. min 30  - vârtej de praf MARE (130 m diametru, vânt intern ~25 m/s), purtat de vânt cu 3 m/s,
#                taie traseul în fața astronautului -> se poate ocoli: REROUTE (WAIT e și ea validă);
#   2. min 80  - FRONTUL unei furtuni de praf (30 × 5 km, 15 m/s), venit din vest, ajunge în ~10 min
#                peste astronautul aflat la clay_delta -> nicio variantă nu-l evită: întoarcere imediată
#                (EMERGENCY la regula rolului 2);
#   3. min 125 - avertizare de furtună REGIONALĂ de pe orbită -> RETURN (confirmă drumul spre habitat).
# Pozițiile sunt alese pe traseul planificat habitat -> clay_delta -> habitat (preset „safe”) și
# verificate rulând motorul live cu alternativele reale (tests/scenario: test_demo_scene_*).
# Vârtejurile au vârful la 12-13 LTST; la 08:30 sunt mai rare: e o alegere de demo, o spunem.
_DUST_DEVIL = {"axes_m": [65, 65], "intensity": 0.9, "peak_after_min": 5}  # trece pe lângă el în ~5 min
_FRONT = {"axes_m": [15000, 2500], "angle_deg": 90, "velocity_ms": [0.0, 15.0], "intensity": 0.7, "peak_after_min": 10}

# Situl sintetic: habitat (300, 200), traseul urcă spre nord-vest; vârtejul vine din vest.
DEMO_SCENARIO_EVENTS = [
    ScheduledEvent(30, "dust_devil", {**_DUST_DEVIL, "center": {"row": 219, "col": 122}, "velocity_ms": [0.0, 3.0]}),
    ScheduledEvent(80, "local_storm", {**_FRONT, "center": {"row": 183, "col": -325}}),
    ScheduledEvent(125, "regional_storm", {"intensity": 0.9}),
]

# Jezero (data/processed/jezero): habitatul la (229, 264), lângă locul de aterizare; clay_delta la
# (216, 123), la baza frontului deltei, ~3 km vest. Vârtejul vine din sud (vy < 0 = spre nord).
JEZERO_DEMO_EVENTS = [
    ScheduledEvent(30, "dust_devil", {**_DUST_DEVIL, "center": {"row": 262, "col": 175}, "velocity_ms": [-3.0, 0.0]}),
    ScheduledEvent(80, "local_storm", {**_FRONT, "center": {"row": 216, "col": -325}}),
    ScheduledEvent(125, "regional_storm", {"intensity": 0.9}),
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
