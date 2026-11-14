"""Uneltele pe care LLM-ul le poate apela din chat (direcția om → cod).

Toate cifrele vin de aici, din cod. LLM-ul doar alege unealta și parametrii, apoi
formulează răspunsul din rezultat. Rezultatele sunt compacte, cu chei și texte în engleză.
"""

from app.core.site_data import get_site
from app.core.types import Limits
from app.live import planning
from app.live import scenario as scenario_mod
from app.live.engine import engine

PRESETS = ["safe", "fast", "science"]
LIMITS = Limits()

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "plan_route",
            "description": "Plan an EVA route from the habitat to one or more science targets and back to the habitat. "
                           "Returns duration, O2 left when back at the habitat, radiation dose, return-by time and a GO / CAUTION / NO-GO verdict. "
                           "Use it whenever the astronaut names a target or a sample they want (clay, carbonate, olivine...).",
            "parameters": {
                "type": "object",
                "properties": {
                    "stops": {"type": "array", "items": {"type": "string"}, "description": "Target ids, in any order."},
                    "preset": {"type": "string", "enum": PRESETS, "description": "safe (default), fast, or science."},
                    "max_duration_min": {"type": "number", "description": "Time available for the EVA, in minutes."},
                },
                "required": ["stops"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "oxygen_budget",
            "description": "Oxygen left when the astronaut is back at the habitat after visiting a set of stops, compared with the safety reserve. "
                           "Without stops, returns the oxygen status of the current EVA.",
            "parameters": {
                "type": "object",
                "properties": {"stops": {"type": "array", "items": {"type": "string"}}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "layer_value",
            "description": "Terrain facts at a science target or a map cell: elevation, slope, terrain type, minerals, radiation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target id (preferred)."},
                    "row": {"type": "integer"},
                    "col": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "science_stops",
            "description": "Rank the science targets that fit in the available time, most valuable first, and propose a combination. "
                           "Use it ONLY when the astronaut has not named a target and asks what is worth visiting.",
            "parameters": {
                "type": "object",
                "properties": {"max_duration_min": {"type": "number", "description": "Time available, in minutes."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "daylight",
            "description": "Sunset time and the latest safe return time, as Mars local solar time (LTST) and EVA minutes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "eva_status",
            "description": "Live status of the current EVA: time, oxygen, dose, active hazards and the copilot's last decision.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_NAMES = [t["function"]["name"] for t in TOOL_SPECS]


class ToolError(ValueError):
    pass


# ---------------------------------------------------------------- ajutoare


def targets() -> list[dict]:
    return planning.site_meta()["targets"]


def _as_list(stops) -> list:
    """LLM-ul trimite uneori o singură țintă ca text, nu ca listă."""
    if stops is None:
        return []
    return [stops] if isinstance(stops, str) else list(stops)


def resolve_target(name: str) -> str:
    """Id-ul țintei din ce scrie LLM-ul: id exact, tip („clay”) sau o bucată din nume."""
    key = str(name).strip().lower().replace(" ", "_")
    by_id = {t["id"]: t for t in targets()}
    if key in by_id:
        return key
    for t in targets():
        if key == t.get("kind") or key in t["id"] or key.replace("_", " ") in t["name"].lower():
            return t["id"]
    raise ToolError(f"Unknown target '{name}'. Available: {', '.join(sorted(by_id))}.")


def ltst(t_min: float) -> str:
    """Ora solară locală marțiană (LTST) la minutul `t_min` al ieșirii, ca „HH:MM”."""
    hours = scenario_mod.EVA_START_LTST_H + t_min / scenario_mod.MARS_HOUR_MIN
    h, m = divmod(int(round(hours * 60)), 60)
    return f"{h % 24:02d}:{m:02d}"


def _sunset_min() -> float:
    if engine.route is not None:
        return float(engine.sunset_min)
    return 420.0


def _route_summary(route: dict, mock: bool) -> dict:
    b = route.get("budget", {})
    pnr = route.get("point_of_no_return") or {}
    out = {
        "route_id": route.get("route_id"),
        "stops": [s["id"] for s in route.get("stops", [])],
        "preset": route.get("preset"),
        "distance_km": round(b.get("distance_m", 0) / 1000, 1),
        "duration_min": b.get("duration_min"),
        "o2_at_habitat_pct": b.get("o2_end_pct"),
        "o2_reserve_pct": LIMITS.o2_reserve_pct,
        "dose_msv": b.get("dose_msv"),
        "return_by_min": b.get("return_by_min"),
        "return_by_ltst": ltst(b["return_by_min"]) if "return_by_min" in b else None,
        "point_of_no_return_min": pnr.get("t_min"),
        "verdict": route.get("verdict"),
        "violations": route.get("violations", []),
    }
    if mock:
        out["note"] = "estimate from the placeholder planner"
    return {k: v for k, v in out.items() if v is not None}


# ---------------------------------------------------------------- uneltele


def plan_route(stops, preset="safe", max_duration_min=300) -> tuple[dict, dict]:
    ids = [resolve_target(s) for s in _as_list(stops)]
    if preset not in PRESETS:
        preset = "safe"
    try:
        route, mock = planning.plan(ids, preset=preset, max_duration_min=float(max_duration_min or 300))
    except planning.PlanningError as exc:
        raise ToolError(str(exc)) from exc
    return _route_summary(route, mock), route


def oxygen_budget(stops=None) -> dict:
    if _as_list(stops):
        ids = [resolve_target(s) for s in _as_list(stops)]
        try:
            route, mock = planning.plan(ids, store=False)
        except planning.PlanningError as exc:
            raise ToolError(str(exc)) from exc
        o2 = route.get("budget", {}).get("o2_end_pct")
        out = {"stops": ids, "o2_at_habitat_pct": o2, "o2_reserve_pct": LIMITS.o2_reserve_pct,
               "margin_pct": round(o2 - LIMITS.o2_reserve_pct, 1) if o2 is not None else None}
        if mock:
            out["note"] = "estimate from the placeholder planner"
        return out
    tick = engine.last_tick
    if tick is None:
        return {"status": "no EVA in progress", "hint": "give stops to estimate a plan"}
    return {"o2_now_pct": tick["sensors"]["o2_pct"], "o2_at_habitat_pct": tick["budget"]["o2_end_pct"],
            "o2_reserve_pct": LIMITS.o2_reserve_pct}


def layer_value(target=None, row=None, col=None) -> dict:
    meta = planning.site_meta()
    if target is not None:
        tid = resolve_target(target)
        t = next(x for x in meta["targets"] if x["id"] == tid)
        row, col, where = t["row"], t["col"], {"target": tid, "name": t["name"]}
    elif row is not None and col is not None:
        where = {"row": int(row), "col": int(col)}
    else:
        raise ToolError("Give a target id, or row and col.")
    site = get_site()
    if site is None:
        raise ToolError("Map layers are not available (site data not generated).")
    rows, cols = site.shape
    if not (0 <= int(row) < rows and 0 <= int(col) < cols):
        raise ToolError("That cell is outside the map.")
    v = site.value_at(int(row), int(col))
    terrain = meta.get("terrain_classes", {}).get(str(int(v["terrain"])), v["terrain"]) if "terrain" in v else None
    minerals = meta.get("mineral_classes", {}).get(str(int(v["minerals"])), v["minerals"]) if "minerals" in v else None
    out = {
        **where,
        "elevation_m": round(v["elevation"], 1) if "elevation" in v else None,
        "slope_deg": round(v["slope"], 1) if "slope" in v else None,
        "max_slope_deg": meta.get("max_slope_deg"),
        "terrain": terrain,
        "minerals": minerals,
        "radiation_usv_h": round(v["radiation"], 1) if "radiation" in v else None,
        "unsafe": bool(v["unsafe"]) if "unsafe" in v else None,
    }
    return {k: x for k, x in out.items() if x is not None}


def science_stops(max_duration_min=300) -> dict:
    limit = float(max_duration_min or 300)
    ranked, any_mock = [], False
    for t in sorted(targets(), key=lambda x: (-x.get("science_value", 0), x["id"])):
        try:
            route, mock = planning.plan([t["id"]], max_duration_min=limit, store=False)
        except planning.PlanningError:
            continue
        any_mock |= mock
        b = route.get("budget", {})
        fits = b.get("duration_min", 0) <= limit and b.get("o2_end_pct", 0) >= LIMITS.o2_reserve_pct
        ranked.append({"id": t["id"], "name": t["name"], "kind": t.get("kind"), "science_value": t.get("science_value"),
                       "round_trip_min": b.get("duration_min"), "o2_at_habitat_pct": b.get("o2_end_pct"), "fits": fits})

    combo = []
    for r in ranked:  # adaugă, în ordinea valorii, cât timp combinația încape
        if not r["fits"]:
            continue
        try:
            route, mock = planning.plan(combo + [r["id"]], max_duration_min=limit, store=False)
        except planning.PlanningError:
            continue
        b = route.get("budget", {})
        if b.get("duration_min", 0) <= limit and b.get("o2_end_pct", 0) >= LIMITS.o2_reserve_pct:
            combo.append(r["id"])
    out = {"max_duration_min": limit, "ranked": ranked, "suggested_stops": combo}
    if any_mock:
        out["note"] = "estimate from the placeholder planner"
    return out


def daylight() -> dict:
    sunset = _sunset_min()
    return_by = sunset - LIMITS.sunset_margin_min
    out = {
        "eva_start_ltst": ltst(0),
        "sunset_min": sunset, "sunset_ltst": ltst(sunset),
        "return_by_min": return_by, "return_by_ltst": ltst(return_by),
        "margin_before_sunset_min": LIMITS.sunset_margin_min,
    }
    if engine.route is not None:
        out["now_min"] = engine.t_min
        out["now_ltst"] = ltst(engine.t_min)
        out["minutes_left_before_return_by"] = round(return_by - engine.t_min)
    return out


def eva_status() -> dict:
    tick = engine.last_tick
    if engine.route is None or tick is None:
        return {"state": engine.state, "status": "no EVA in progress"}
    out = {
        "state": engine.state,
        "t_min": tick["t_min"], "now_ltst": ltst(tick["t_min"]),
        "o2_now_pct": tick["sensors"]["o2_pct"], "o2_at_habitat_pct": tick["budget"]["o2_end_pct"],
        "dose_total_msv": tick["sensors"]["dose_total_msv"],
        "dust_tau": tick["sensors"]["dust_tau"], "wind_ms": tick["sensors"]["wind_ms"],
        "active_hazards": sorted({h["kind"] for h in tick["hazards"]}),
        "returning_home": engine.returning,
        "stops_left": [s["id"] for s in engine.stops_left],
    }
    if engine.last_decision:
        out["last_decision"] = engine.last_decision
    return out


_TOOLS = {
    "oxygen_budget": oxygen_budget,
    "layer_value": layer_value,
    "science_stops": science_stops,
    "daylight": daylight,
    "eva_status": eva_status,
}


def execute(name: str, args: dict | None) -> tuple[dict, dict | None]:
    """Rulează o unealtă. Întoarce (rezultat compact, traseu complet sau None).

    Erorile de parametri devin {"error": "..."} în rezultat, ca LLM-ul să poată corecta.
    """
    args = dict(args or {})
    try:
        if name == "plan_route":
            allowed = {"stops", "preset", "max_duration_min"}
            return plan_route(**{k: v for k, v in args.items() if k in allowed})
        if name not in _TOOLS:
            raise ToolError(f"Unknown tool '{name}'. Available: {', '.join(TOOL_NAMES)}.")
        fn = _TOOLS[name]
        allowed = set(fn.__code__.co_varnames[: fn.__code__.co_argcount])
        return fn(**{k: v for k, v in args.items() if k in allowed}), None
    except (ToolError, TypeError) as exc:
        return {"error": str(exc)}, None
