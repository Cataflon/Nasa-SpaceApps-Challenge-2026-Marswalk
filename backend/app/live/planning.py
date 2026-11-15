"""Planificarea unui traseu: validare + planner (rolul 2) + fallback pe mock + salvare.

Folosit de `POST /api/route` și de unealta `plan_route` din chat, ca ambele să dea exact
același rezultat. Mesajele de eroare sunt în engleză (ajung la utilizator).
"""

import json
import threading

import numpy as np

from app.config import CONTRACTS_DIR
from app.core import planner
from app.core.costmap import static_cost
from app.core.site_data import get_site
from app.live.store import routes

# Punctele proprii devin ținte ale sitului, marcate `custom: true`: planificatorul, replanificatorul
# live și motorul le găsesc după id ca pe orice țintă (fără să schimbăm algoritmii). `/api/site` și
# uneltele de chat le ascund. Valoarea științifică e 1 pentru toate (nu o alege utilizatorul): destul
# ca optimizatorul opririlor să nu le arunce ca „fără valoare”.
CUSTOM_SCIENCE_VALUE = 1
_custom_lock = threading.Lock()


class PlanningError(ValueError):
    """Cerere invalidă (țintă necunoscută, start în afara grilei, țintă inaccesibilă)."""


def _contract(name: str) -> dict:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def site_meta() -> dict:
    """Meta-ul sitului activ, sau site.json din contracte dacă situl nu e generat."""
    s = get_site()
    return s.meta if s is not None else _contract("site.json")


def catalog_targets(meta: dict) -> list[dict]:
    """Țintele științifice ale sitului, fără punctele proprii înregistrate de utilizatori."""
    return [t for t in meta["targets"] if not t.get("custom")]


def register_custom_stops(custom_stops: list, preset: str) -> None:
    """Validează punctele proprii și le înregistrează ca ținte `custom` ale sitului.

    Erori (PlanningError → 422, cu id-ul punctului): fără date de sit, coliziune cu un id din catalog,
    în afara grilei, celulă interzisă (pantă peste limită / nesigură) sau din care nu se ajunge acasă.
    """
    if not custom_stops:
        return
    s = get_site()
    if s is None:
        raise PlanningError("Custom stops need the site data. Run the data pipeline first.")
    rows, cols = s.shape
    catalog = {t["id"] for t in catalog_targets(s.meta)}
    cost = static_cost(s, preset)  # înainte de înregistrare: verificarea țintelor din catalog rămâne aceeași
    cost_to_home, _ = planner.home_tree(s, preset)
    for c in custom_stops:
        if c.id in catalog:
            raise PlanningError(f"custom_stops: id {c.id} collides with a catalog target.")
        if not (0 <= c.row < rows and 0 <= c.col < cols):
            raise PlanningError(f"custom_stops: {c.name} ({c.row}, {c.col}) is outside the {rows}x{cols} grid.")
        if not np.isfinite(cost[c.row, c.col]):
            raise PlanningError(f"custom_stops: {c.name} is on terrain that is too steep or unsafe. Pick a nearby point.")
        if not np.isfinite(cost_to_home[c.row, c.col]):
            raise PlanningError(f"custom_stops: {c.name} cannot be reached from the habitat. Pick a nearby point.")
    with _custom_lock:
        known = {t["id"]: i for i, t in enumerate(s.meta["targets"])}
        for c in custom_stops:
            target = {"id": c.id, "name": c.name, "kind": c.tag, "row": int(c.row), "col": int(c.col),
                      "science_value": CUSTOM_SCIENCE_VALUE, "dwell_min": float(c.dwell_min), "image": None,
                      "custom": True}
            if c.id in known:  # același punct, poate mutat: se actualizează
                s.meta["targets"][known[c.id]] = target
            else:
                s.meta["targets"].append(target)


def plan(
    stops: list[str],
    start: tuple[int, int] | None = None,
    preset: str = "safe",
    start_time_min: float = 0,
    max_duration_min: float = 300,
    return_to_habitat: bool = True,
    store: bool = True,
    custom_stops: list | None = None,
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
    if len(set(stops)) != len(stops):
        raise PlanningError("Each stop can appear only once.")
    custom_ids = {c.id for c in custom_stops or []}
    referenced = [c for c in custom_stops or [] if c.id in stops]
    register_custom_stops(referenced, preset)
    known = {t["id"] for t in catalog_targets(meta)} | {c.id for c in referenced}
    unknown = [s for s in stops if s not in known]
    if any(s.startswith("note_") and s not in custom_ids for s in unknown):
        raise PlanningError(f"Missing definition in custom_stops for: {', '.join(s for s in unknown if s.startswith('note_'))}.")
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
    else:
        _describe_stops(result, s.meta, stops)
        _terrain_numbers(result, s)
    if store:
        routes.add(result)
    else:
        result["route_id"] = "preview"
    return result, mock


def _terrain_numbers(result: dict, s) -> None:
    """Panta maximă și urcarea totală pe traseu, din straturile backendului (`slope`, `elevation`),
    ca frontendul să nu le mai calculeze pe grila lui de afișare (docs/RAPORT_PANTA_20.md, R5)."""
    path = [tuple(c) for c in result.get("path", [])]
    if not path or "budget" not in result or not hasattr(s, "layers"):
        return
    slope, elev = s.layers["slope"], s.layers["elevation"]
    z = [float(elev[r, c]) for r, c in path]
    result["budget"]["max_slope_deg"] = round(max(float(slope[r, c]) for r, c in path), 1)
    result["budget"]["ascent_m"] = round(sum(max(0.0, b - a) for a, b in zip(z, z[1:])), 1)


def _describe_stops(result: dict, meta: dict, requested: list[str]) -> None:
    """Completează opririle cu nume, poziție, sursă și ordinea vizitei; `omitted` = cerute, dar
    lăsate deoparte de planificator (nu încap în timp sau O₂)."""
    by_id = {t["id"]: t for t in meta["targets"]}
    for i, stop in enumerate(result.get("stops", []), start=1):
        t = by_id.get(stop["id"], {})
        stop.update({"name": t.get("name", stop["id"]), "row": t.get("row"), "col": t.get("col"),
                     "source": "custom" if t.get("custom") else "catalog", "visit_order": i})
    visited = {stop["id"] for stop in result.get("stops", [])}
    result["omitted"] = [sid for sid in requested if sid not in visited]
    result["validation_status"] = "validated"
