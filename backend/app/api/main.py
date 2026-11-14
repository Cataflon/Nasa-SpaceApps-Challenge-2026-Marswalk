"""Rutele API + WebSocket (rolul 3).

Rutele încă neimplementate întorc mock-urile din shared/contracts/ și antetul `X-Mock: 1`,
ca frontendul să poată lucra de la început.

Pornire (din folderul backend/):  uvicorn app.api.main:app --reload
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import CONTRACTS_DIR, FRONTEND_ORIGINS, LIVE_MOCK, SITE_ID, site_dir
from app.core.site_data import get_site
from app.live import planning
from app.live.engine import engine, mock_stream
from app.llm import warm_up
from app.llm.chat import chat_stream
from app.schemas import ChatRequest, LiveControl, LiveEvent, RouteRequest


LAYER_LABELS = {
    "elevation": "Elevation",
    "slope": "Slope",
    "terrain": "Terrain",
    "minerals": "Minerals",
    "radiation": "Radiation",
}


def contract(name: str) -> dict | list:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    warm = asyncio.create_task(warm_up())  # nu blochează pornirea
    loop = asyncio.create_task(engine.run())  # bucla live, inactivă până la /api/live/control start
    yield
    for task in (warm, loop):
        task.cancel()


app = FastAPI(title="Marswalk Copilot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"])

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
        "targets": meta["targets"],
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
    return {"row": row, "col": col, "values": s.value_at(row, col)}


@app.post("/api/route")
def route(req: RouteRequest, response: Response):
    """Traseu + buget + verdict. Rulează în threadpool (funcție sincronă), deci nu blochează live-ul.

    Cât timp `planner.plan_route` (rolul 2) aruncă NotImplementedError, întoarce mock-ul
    din contract cu `X-Mock: 1`. Traseul primește mereu un `route_id` nou și e salvat
    pentru motorul live.
    """
    try:
        result, mock = planning.plan(
            list(req.stops),
            start=(req.start.row, req.start.col),
            preset=req.preset,
            start_time_min=req.start_time_min,
            max_duration_min=req.max_duration_min,
            return_to_habitat=req.return_to_habitat,
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
async def live_event(ev: LiveEvent):
    engine.inject(ev.event, ev.params)
    return {"accepted": True, "event": ev.event, "state": engine.state, "t_min": engine.t_min}


@app.post("/api/live/control")
async def live_control(ctrl: LiveControl):
    if ctrl.action == "start":
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
    # TODO (rolul 2): core.benchmark.run_benchmark()
    raise HTTPException(501, "Benchmark is not implemented yet.")
