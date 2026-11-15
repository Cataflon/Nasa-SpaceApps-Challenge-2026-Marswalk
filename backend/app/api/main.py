"""Rutele API + WebSocket (rolul 3).

Rutele încă neimplementate întorc mock-urile din shared/contracts/ și antetul `X-Mock: 1`,
ca frontendul să poată lucra de la început.

Pornire (din folderul backend/):  uvicorn app.api.main:app --reload
"""

import asyncio
import json
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.api.bench_cache import BenchmarkCache
from app.config import CONTRACTS_DIR, FRONTEND_ORIGINS, LIVE_MOCK, SITE_ID, site_dir
from app.core import alternatives, hazard_spec, planner
from app.core.hazards import Hazard
from app.core.site_data import get_site
from app.live import planning, scenario
from app.live.engine import engine, mock_stream
from app.llm import warm_up
from app.llm.chat import chat_stream
from app.schemas import EVENT_PARAMS, ChatRequest, LiveControl, LiveEvent, RouteRequest


LAYER_LABELS = {
    "elevation": "Elevation",
    "slope": "Slope",
    "terrain": "Terrain",
    "minerals": "Minerals",
    "radiation": "Radiation",
}


def contract(name: str) -> dict | list:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


log = logging.getLogger(__name__)

# 0 = fără încălzirea core-ului / fără benchmark la pornire (de exemplu în teste sau pe un laptop slab).
CORE_WARMUP = os.getenv("MARSWALK_WARMUP", "1") == "1"
BENCHMARK_AT_STARTUP = os.getenv("MARSWALK_BENCHMARK_AT_STARTUP", "1") == "1"
BENCHMARK_N, BENCHMARK_SEED = 100, 42
BENCHMARK_RETRY_AFTER_S = 30  # ≈ jumătate din durata unui benchmark complet (~1 min)
bench = BenchmarkCache(BENCHMARK_N, BENCHMARK_SEED)


def warm_up_core() -> None:
    """Mută costurile primului apel la pornire: importul OR-Tools (~0,8 s), cele două Dijkstra din
    plan_route (~1,5 s, apoi în cache per sit) și minutes_grid din alternatives.generate."""
    try:
        import ortools.sat.python.cp_model  # noqa: F401

        s = get_site()
        if s is None or not s.meta.get("targets"):
            return
        stop = s.meta["targets"][0]["id"]
        plan = planner.plan_route(s, s.habitat, [stop])
        path = [tuple(c) for c in plan["path"]]
        probe_cell = path[len(path) // 4]
        cell = s.cell_size_m
        probe = Hazard("warmup", "dust_devil", ((probe_cell[0] + 0.5) * cell, (probe_cell[1] + 0.5) * cell),
                       (65.0, 65.0), 0.0, 0.9, (0.0, 0.0), 0.0)
        alternatives.generate(s, path[0], path, [stop], [probe], 0.0, 100.0, 0.0, float(plan["budget"]["sunset_min"]))
    except Exception:  # încălzirea nu are voie să oprească pornirea
        log.exception("Încălzirea core-ului a eșuat.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    warm = asyncio.create_task(warm_up())  # nu blochează pornirea
    loop = asyncio.create_task(engine.run())  # bucla live, inactivă până la /api/live/control start
    if CORE_WARMUP:  # thread daemon: nu blochează nici pornirea, nici oprirea
        threading.Thread(target=warm_up_core, name="core-warmup", daemon=True).start()
    if BENCHMARK_AT_STARTUP and get_site() is not None:
        bench.start()
    yield
    for task in (warm, loop):
        task.cancel()
    bench.stop()


app = FastAPI(title="Marswalk Copilot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def readable(errors: list[dict]) -> str:
    """Erorile Pydantic ca un singur text în engleză: „params.axes_m.0: Input should be …; …”."""
    parts = []
    for e in errors:
        loc = ".".join(str(x) for x in e.get("loc", ()) if x != "body")
        parts.append(f"{loc}: {e.get('msg', 'invalid value')}" if loc else e.get("msg", "invalid value"))
    return "; ".join(parts) or "Invalid request."


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """422 cu `detail` text (frontendul afișează `detail` doar dacă e string) + lista originală în `errors`."""
    return JSONResponse(status_code=422, content={"detail": readable(exc.errors()),
                                                  "errors": jsonable_encoder(exc.errors())})

_png_dir = site_dir() / "png"
if _png_dir.exists():
    app.mount("/static/layers", StaticFiles(directory=_png_dir), name="layers")


@app.get("/api/health")
def health():
    return {"status": "ok", "site": SITE_ID, "site_loaded": get_site() is not None}


@app.get("/api/site")
def site(response: Response):
    s = get_site()
    if s is None:
        response.headers["X-Mock"] = "1"
        return contract("site.json")
    meta = s.meta
    return {
        "site_id": meta["site_id"],
        "name": meta["name"],
        "cell_size_m": meta["cell_size_m"],
        "shape": meta["shape"],
        "center": meta["center"],
        "habitat": meta["habitat"],
        "max_slope_deg": meta["max_slope_deg"],
        "targets": planning.catalog_targets(meta),
        # Hardware NASA ca POI (rolul 1) + traseul real al roverului Perseverance (doar pe Jezero).
        "artifacts": meta.get("artifacts", []),
        "rover_traverse": meta.get("rover_traverse"),
        # Ceasul de întoarcere și contorul „Pământul vs. copilotul” (constante de la rolul 1).
        "eva_start_ltst_h": scenario.EVA_START_LTST_H,
        "earth_delay_min": {"one_way": scenario.EARTH_ONE_WAY_DELAY_MIN,
                            "round_trip": scenario.EARTH_ROUND_TRIP_MIN,
                            "source": scenario.EARTH_DELAY_SOURCE},
        "layers": [
            {"id": name, "label": LAYER_LABELS.get(name, name), "png": f"/static/layers/{name}.png", "unit": spec["unit"],
             # Etichetele de proveniență scrise de pipeline (rolul 1), dacă există.
             **{k: spec[k] for k in LAYER_LABEL_KEYS if k in spec}}
            for name, spec in meta["layers"].items()
            if name != "unsafe"
        ],
    }


# Chei opționale din meta.json -> layers.<strat>, transmise frontendului (rolul 1 le completează).
LAYER_LABEL_KEYS = ("data_type", "mission", "instrument", "source", "analog_of", "product_id")
# Varianta scurtă pentru click pe hartă („slope 12° · HiRISE · MRO”); product_id e prea lung aici.
POINT_SOURCE_KEYS = ("mission", "instrument", "data_type", "source", "analog_of", "derived")


@app.get("/api/layers")
def layers(response: Response):
    return site(response)["layers"]


@app.get("/api/point")
def point(row: int, col: int):
    s = get_site()
    if s is None:
        raise HTTPException(503, "Site data not generated. Run pipeline/make_synthetic_site.py.")
    rows, cols = s.shape
    if not (0 <= row < rows and 0 <= col < cols):
        raise HTTPException(400, "Cell is outside the grid.")
    layers = s.meta.get("layers", {})
    sources = {name: {k: spec[k] for k in POINT_SOURCE_KEYS if k in spec}
               for name, spec in layers.items() if any(k in spec for k in POINT_SOURCE_KEYS)}
    return {"row": row, "col": col, "values": s.value_at(row, col), "sources": sources}


@app.post("/api/route")
def route(req: RouteRequest, response: Response):
    """Traseu + buget + verdict. Rulează în threadpool (funcție sincronă), deci nu blochează live-ul.

    Situl generat -> `planner.plan_route` (rolul 2); fără sit, mock-ul din contract cu `X-Mock: 1`.
    ValueError din planner (start sau țintă din care nu se ajunge la habitat) -> 422 cu mesajul lui
    (în engleză). Planner-ul dă mereu `route_id = "plan_0"`; aici primește un id nou din stoc
    (`routes.add`) și e salvat pentru motorul live. `point_of_no_return` poate fi null și rămâne null.
    """
    try:
        result, mock = planning.plan(
            list(req.stops),
            start=(req.start.row, req.start.col),
            preset=req.preset,
            start_time_min=req.start_time_min,
            max_duration_min=req.max_duration_min,
            return_to_habitat=req.return_to_habitat,
            store=not req.preview,
            custom_stops=list(req.custom_stops),
        )
    except planning.PlanningError as exc:
        raise HTTPException(422, str(exc)) from exc
    if mock:
        response.headers["X-Mock"] = "1"
    return result


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Chat cu unelte, în streaming NDJSON (vezi shared/contracts/chat_stream.json)."""

    async def lines():
        async for item in chat_stream(req.message, req.history):
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


# Rutele live sunt `async def`: rulează pe aceeași buclă ca motorul, deci fără curse între thread-uri.


@app.post("/api/live/event")
async def live_event(body: dict = Body(...)):
    """Injectează un eveniment. Două formate (ARHITECTURA_RUTARE_V2 §2.2, `live_event.json`):

    - vechi: `{"event": <_allowed_events>, "params": {...}}`: parametrii se validează pe tipul evenimentului
      (422, cu câmpul greșit) și se întorc exact cum îi primește motorul la tick-ul următor;
    - HazardSpec: `{"op": "add" | "update" | "remove", "id": ..., "kind": ..., "shape": ..., "motion": ...}`:
      NaN, centru nenumeric, forme nevalide → 422 cu un cod stabil, înainte să ajungă la motor.
    Ambele cer o misiune activă (409).
    """
    if "op" in body:
        op = body.get("op")
        if op not in hazard_spec.OPS:
            raise HTTPException(422, f"Invalid op: {op!r}. Allowed: {list(hazard_spec.OPS)}.")
        if op in ("update", "remove") and not body.get("id"):
            raise HTTPException(422, f"Operation {op!r} requires `id`.")
        if op == "add" or (op == "update" and ("shape" in body or "motion" in body)):
            check = hazard_spec.normalize({**body, "shape": {"center": {"row": 0, "col": 0}, **body.get("shape", {})}}
                                          if op == "update" else body, body.get("kind"))
            if not check.ok:
                raise HTTPException(422, f"Invalid hazard spec: {check.error}.")
        _require_active_eva()
        kind = str(body.get("kind") or "custom")
        engine.inject(kind, body)
        return {"accepted": True, "event": kind, "op": op, "id": body.get("id"), "state": engine.state,
                "t_min": engine.t_min}
    try:
        ev = LiveEvent(**body)
    except ValidationError as exc:
        raise HTTPException(422, readable(exc.errors())) from exc
    try:
        params = EVENT_PARAMS[ev.event].model_validate(ev.params).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(422, readable([{**e, "loc": ("params", *e["loc"])} for e in exc.errors()])) from exc
    if "center" in params:
        s = get_site()
        rows, cols = s.shape if s is not None else contract("site.json")["shape"]
        c = params["center"]
        if not (0 <= c["row"] < rows and 0 <= c["col"] < cols):
            raise HTTPException(422, f"params.center: ({c['row']}, {c['col']}) is outside the {rows}x{cols} grid.")
    _require_active_eva()
    engine.inject(ev.event, params)
    return {"accepted": True, "event": ev.event, "params": params, "state": engine.state, "t_min": engine.t_min}


def _require_active_eva() -> None:
    if engine.state not in ("running", "paused"):
        raise HTTPException(409, f"No active EVA (state: {engine.state}). Start the mission before injecting events.")


@app.post("/api/live/control")
async def live_control(ctrl: LiveControl):
    if ctrl.action == "start":
        if engine.state == "finished":
            # O misiune încheiată nu mai are nimic de pierdut: un start nou o resetează singur și pornește
            # ruta cerută (sau din nou aceeași rută, dacă route_id lipsește).
            if ctrl.route_id is not None and engine.store.get(ctrl.route_id) is None:
                raise HTTPException(404, f"Route {ctrl.route_id} does not exist. Plan it with POST /api/route.")
            previous = (engine.route or {}).get("route_id")
            route_id = ctrl.route_id or (previous if engine.store.get(previous or "") else None)
            engine.reset()
            engine.start(route_id, ctrl.speed)
            return {"ok": True, "state": engine.state, "t_min": engine.t_min}
        if ctrl.route_id is not None and engine.state in ("running", "paused"):
            # Un plan nou nu înlocuiește în tăcere o misiune în curs: întâi reset.
            raise HTTPException(409, f"An EVA is {engine.state}. Reset the mission before starting route {ctrl.route_id}.")
        try:
            engine.start(ctrl.route_id, ctrl.speed)
        except KeyError:
            raise HTTPException(404, f"Route {ctrl.route_id} does not exist. Plan it with POST /api/route.")
    elif ctrl.action == "pause":
        engine.pause()
    elif ctrl.action == "reset":
        engine.reset()
    elif ctrl.action == "speed":
        if ctrl.speed is None:
            raise HTTPException(422, "Action 'speed' requires the `speed` field (1-60).")
        engine.set_speed(ctrl.speed)
    return {"ok": True, "state": engine.state, "t_min": engine.t_min}


@app.websocket("/api/live")
async def live(ws: WebSocket):
    await ws.accept()
    if LIVE_MOCK:
        try:
            async for msg in mock_stream(interval_s=1.0):
                await ws.send_json(msg)
        except WebSocketDisconnect:
            pass
        return

    queue = engine.subscribe()
    try:
        while True:
            await ws.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        engine.unsubscribe(queue)


@app.get("/api/benchmark")
def benchmark():
    """Copilot vs. „doar planul” pe BENCHMARK_N scenarii (seed fix), cu `headline`.

    Se calculează o singură dată (pornit la startup, ~1 min, în fundal); până e gata: 503 cu
    `Retry-After`. Dacă serverul a pornit fără benchmark, prima cerere îl pornește.
    """
    if bench.result is not None:
        return bench.result
    if get_site() is None:
        raise HTTPException(503, "Site data not generated. Run pipeline/make_synthetic_site.py.")
    if bench.error is not None:
        raise HTTPException(500, f"Benchmark failed: {bench.error}")
    bench.start()
    raise HTTPException(503, f"Benchmark is still running ({BENCHMARK_N} scenarios, about 1 minute). Retry later.",
                        headers={"Retry-After": str(BENCHMARK_RETRY_AFTER_S)})
