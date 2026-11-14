"""Planificarea unui traseu: validare + planner (rolul 2) + fallback pe mock + salvare.

Folosit de `POST /api/route` și de unealta `plan_route` din chat, ca ambele să dea exact
același rezultat. Mesajele de eroare sunt în engleză (ajung la utilizator).
"""

import json

from app.config import CONTRACTS_DIR
from app.core import planner
from app.core.site_data import get_site
from app.live.store import routes


class PlanningError(ValueError):
    """Cerere invalidă (țintă necunoscută, start în afara grilei, țintă inaccesibilă)."""


def _contract(name: str) -> dict:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def site_meta() -> dict:
    """Meta-ul sitului activ, sau site.json din contracte dacă situl nu e generat."""
    s = get_site()
    return s.meta if s is not None else _contract("site.json")


def plan(
    stops: list[str],
    start: tuple[int, int] | None = None,
    preset: str = "safe",
    start_time_min: float = 0,
    max_duration_min: float = 300,
    return_to_habitat: bool = True,
    store: bool = True,
) -> tuple[dict, bool]:
    """Întoarce (traseul în forma din route_response.json, e_mock).

    `start` implicit = habitatul. Cu `store=True`, traseul primește `route_id` = `plan_N`
    și e salvat pentru motorul live.
    """
    meta = site_meta()
    if start is None:
        start = (meta["habitat"]["row"], meta["habitat"]["col"])
    rows, cols = meta["shape"]
    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        raise PlanningError(f"Start cell ({start[0]}, {start[1]}) is outside the {rows}×{cols} grid.")
    if not stops:
        raise PlanningError("Choose at least one target.")
    known = {t["id"] for t in meta["targets"]}
    unknown = [s for s in stops if s not in known]
    if unknown:
        raise PlanningError(f"Unknown targets: {', '.join(unknown)}. Available: {', '.join(sorted(known))}.")

    s = get_site()
    result: dict | None = None
    if s is not None:
        try:
            result = planner.plan_route(
                s, tuple(start), list(stops),
                preset=preset, start_time_min=start_time_min,
                max_duration_min=max_duration_min, return_to_habitat=return_to_habitat,
            )
        except NotImplementedError:
            result = None
        except ValueError as exc:  # ex. țintă inaccesibilă; mesajul planner-ului e în engleză
            raise PlanningError(str(exc)) from exc

    mock = result is None
    if mock:
        result = {**_contract("route_response.json"), "preset": preset}
    if store:
        routes.add(result)
    return result, mock
