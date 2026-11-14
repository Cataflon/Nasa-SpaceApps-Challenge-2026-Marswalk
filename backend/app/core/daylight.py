"""Lumina zilei după algoritmul Mars24 (Allison & McEwen 2000, NASA GISS).

Referință: https://www.giss.nasa.gov/tools/mars24/  (registru §5, nivel A).
Perturbațiile planetare (termenii PBS) sunt omise: eroarea pe Ls e de ordinul a 0,01°.
"""

import math
from datetime import datetime, timezone

# A (IERS): TT − UTC = 32,184 s + 37 secunde intercalate, neschimbat din 2017.
TT_MINUS_UTC_S = 69.184
# A, registru §5 (Mars24): o oră marțiană = 1/24 dintr-un sol.
MARS_HOUR_S = 3698.98
# C: altitudinea Soarelui la răsărit/apus. Refracția e neglijabilă în atmosfera subțire, iar
# discul solar văzut de pe Marte are ≈ 0,35°; −0,5° ia marginea discului, cu rotunjire.
SUNRISE_ALTITUDE_DEG = -0.5

_J2000_JD = 2451545.0
_UNIX_EPOCH_JD = 2440587.5


def _delta_j2000_days(sol_start_utc: str) -> float:
    """Zile TT de la J2000 (Mars24, pașii A-1…A-5). Fără fus orar = UTC."""
    moment = datetime.fromisoformat(sol_start_utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    jd_ut = _UNIX_EPOCH_JD + moment.timestamp() / 86400.0
    return jd_ut + TT_MINUS_UTC_S / 86400.0 - _J2000_JD


def _orbit(dt_j2000: float) -> tuple[float, float]:
    """(Ls, ν − M) în grade, Mars24 pașii B-1…B-5, fără perturbații."""
    m = math.radians(19.3871 + 0.52402073 * dt_j2000)  # anomalia medie
    alpha_fms = 270.3871 + 0.524038496 * dt_j2000  # ascensiunea dreaptă a soarelui mediu fictiv
    center = (
        (10.691 + 3.0e-7 * dt_j2000) * math.sin(m)
        + 0.623 * math.sin(2 * m)
        + 0.050 * math.sin(3 * m)
        + 0.005 * math.sin(4 * m)
        + 0.0005 * math.sin(5 * m)
    )  # ecuația centrului, ν − M
    return (alpha_fms + center) % 360.0, center


def mars_ls_deg(sol_start_utc: str) -> float:
    """Longitudinea solară Ls (grade, 0..360) la momentul dat."""
    return _orbit(_delta_j2000_days(sol_start_utc))[0]


def solar_declination_deg(ls_deg: float) -> float:
    """Declinația solară (grade), registru §5: asin(0,42565 sin Ls) + 0,25° sin Ls."""
    s = math.sin(math.radians(ls_deg))
    return math.degrees(math.asin(0.42565 * s)) + 0.25 * s


def ltst_hours(lon_deg: float, sol_start_utc: str) -> float:
    """Ora solară locală reală (ore marțiene, 0..24) la longitudinea ESTICĂ `lon_deg`.

    Mars24 lucrează cu longitudine vestică: Λ = 360 − lon_est.
    """
    dt = _delta_j2000_days(sol_start_utc)
    ls, center = _orbit(dt)
    ls_rad = math.radians(ls)
    eot_deg = 2.861 * math.sin(2 * ls_rad) - 0.071 * math.sin(4 * ls_rad) + 0.002 * math.sin(6 * ls_rad) - center
    west_lon = (360.0 - lon_deg) % 360.0
    return (_mst_from_dt(dt) - west_lon / 15.0 + eot_deg / 15.0) % 24.0


def _mst_from_dt(dt_j2000: float) -> float:
    """Ora medie la meridianul 0 (MST), Mars24 pasul C-2. 44796 e în SOLURI (data marțiană MSD),
    deci se adună înainte de înmulțirea cu 24."""
    msd = (dt_j2000 + _J2000_JD - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626
    return (24.0 * msd) % 24.0


def mst_hours(sol_start_utc: str) -> float:
    """Ora solară medie la meridianul 0 al lui Marte (ore marțiene, 0..24)."""
    return _mst_from_dt(_delta_j2000_days(sol_start_utc))


def sunrise_sunset_min(lat_deg: float, lon_deg: float, sol_start_utc: str) -> tuple[float, float]:
    """Răsăritul și apusul, în minute de la începutul ieșirii (`sol_start_utc`, ISO 8601).

    Unități: rezultatul e în minute TERESTRE (aceeași unitate ca motorul live), nu în minute
    marțiene; o oră marțiană = MARS_HOUR_S = 3698,98 s. `lon_deg` e longitudine estică (Jezero
    ≈ 77,45°E).

    Se întorc răsăritul și apusul aceleiași zile: apusul e primul apus de după start, iar
    răsăritul e cu durata zilei înainte (poate fi negativ dacă ieșirea începe ziua). Deci
    răsărit < apus mereu. La noapte sau zi polară (nu e cazul la Jezero), unghiul orar se
    limitează la 0° sau 180°.
    """
    ls = mars_ls_deg(sol_start_utc)
    phi, delta = math.radians(lat_deg), math.radians(solar_declination_deg(ls))
    cos_h0 = (math.sin(math.radians(SUNRISE_ALTITUDE_DEG)) - math.sin(phi) * math.sin(delta)) / (
        math.cos(phi) * math.cos(delta)
    )
    half_day_h = math.degrees(math.acos(max(-1.0, min(1.0, cos_h0)))) / 15.0  # ore marțiene

    minutes_per_mars_hour = MARS_HOUR_S / 60.0
    to_sunset_h = (12.0 + half_day_h - ltst_hours(lon_deg, sol_start_utc)) % 24.0
    sunset = to_sunset_h * minutes_per_mars_hour
    return sunset - 2.0 * half_day_h * minutes_per_mars_hour, sunset


def effective_sunset_min(sunset_min: float, dust_tau: float) -> float:
    """Apusul efectiv: mai devreme cu cât praful e mai gros (presupunere liniară)."""
    return sunset_min - max(0.0, dust_tau - 0.5) * 30.0
