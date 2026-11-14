"""Lumina zilei după algoritmul Mars24 (NASA GISS).

Referință: https://www.giss.nasa.gov/tools/mars24/
"""


def sunrise_sunset_min(lat_deg: float, lon_deg: float, sol_start_utc: str) -> tuple[float, float]:
    """Răsăritul și apusul, în minute de la începutul ieșirii.

    TODO (rolul 2): Mars24 (Allison & McEwen 2000) -> declinație solară, ecuația timpului.
    Plan B: valori fixe pentru Jezero în sezonul ales, declarate ca presupunere.
    """
    raise NotImplementedError


def effective_sunset_min(sunset_min: float, dust_tau: float) -> float:
    """Apusul efectiv: mai devreme cu cât praful e mai gros (presupunere liniară)."""
    return sunset_min - max(0.0, dust_tau - 0.5) * 30.0
