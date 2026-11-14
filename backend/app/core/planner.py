"""Punctul de intrare pentru planificare, apelat de POST /api/route.

Leagă: costmap.static_cost -> stops (ordinea) -> routing.astar pe segmente -> budget
-> routing.reverse_dijkstra (punct de neîntoarcere) -> validator -> verdict.
"""

from app.core.site_data import Site
from app.core.types import Cell


def plan_route(
    site: Site,
    start: Cell,
    stops: list[str],
    preset: str = "safe",
    start_time_min: float = 0,
    max_duration_min: float = 300,
    return_to_habitat: bool = True,
) -> dict:
    """Întoarce un dict cu EXACT forma din shared/contracts/route_response.json.

    `stops` sunt id-uri din site.meta["targets"]. Dacă lista are >1 țintă, ordinea o decide
    stops.plan_stops (sau brute_force_stops ca plan B).

    TODO (rolul 2).
    """
    raise NotImplementedError
