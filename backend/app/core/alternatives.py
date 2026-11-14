"""Generatorul de alternative pentru un tick live în care traseul e afectat de pericol."""

from app.core.hazards import Hazard
from app.core.site_data import Site
from app.core.types import Alternative, Cell


def generate(
    site: Site,
    position: Cell,
    remaining_path: list[Cell],
    remaining_stops: list[str],
    hazards: list[Hazard],
    t_min: float,
    o2_pct: float,
    dose_msv: float,
    sunset_min: float,
    preset: str = "safe",
) -> list[Alternative]:
    """Toate variantele candidate, NEVALIDATE (validarea o face decision.choose).

    Trebuie să includă mereu:
      - "current"  (kind CONTINUE): traseul rămas, cu crosses_hazard calculat
      - 1-3 ocoliri (kind REROUTE) din A* spațiu-timp cu preset-uri diferite
      - "wait"     (kind WAIT): stai pe loc până trece pericolul prezis
      - "return"   (kind RETURN): ruta de întoarcere din reverse_dijkstra

    Id-urile sunt stabile și deterministe (ex. "detour_north", "detour_south", "wait", "return").

    TODO (rolul 2).
    """
    raise NotImplementedError
