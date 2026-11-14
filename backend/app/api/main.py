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
from fastapi.staticfiles import StaticFiles

from app.config import CONTRACTS_DIR, FRONTEND_ORIGINS, SITE_ID, site_dir
from app.core.site_data import get_site
from app.live.engine import mock_stream
from app.llm import warm_up
from app.schemas import ChatRequest, LiveControl, LiveEvent, RouteRequest


def contract(name: str) -> dict | list:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(warm_up())  # nu blochează pornirea
    yield


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
            {"id": name, "label": name, "png": f"/static/layers/{name}.png", "unit": spec["unit"]}
            for name, spec in meta["layers"].items()
            if name != "unsafe"
        ],
    }


@app.get("/api/layers")
def layers(response: Response):
    return site(response)["layers"]


@app.get("/api/point")
def point(row: int, col: int):
    s = get_site()
    if s is None:
        raise HTTPException(503, "Situl nu e generat. Rulează pipeline/make_synthetic_site.py.")
    rows, cols = s.shape
    if not (0 <= row < rows and 0 <= col < cols):
        raise HTTPException(400, "Celulă în afara grilei.")
    return {"row": row, "col": col, "values": s.value_at(row, col)}


@app.post("/api/route")
def route(req: RouteRequest, response: Response):
    # TODO (rolul 3 + 2): costmap.static_cost -> routing.astar -> budget -> validator
    response.headers["X-Mock"] = "1"
    return contract("route_response.json")


@app.post("/api/chat")
async def chat(req: ChatRequest):
    # TODO (rolul 3): chat cu unelte (plan_route, oxygen_budget, layer_value, science_stops, daylight)
    raise HTTPException(501, "Chatul nu e implementat încă.")


@app.post("/api/live/event")
def live_event(ev: LiveEvent):
    # TODO (rolul 3): LiveEngine.inject(ev.event, ev.params)
    return {"accepted": True, "event": ev.event}


@app.post("/api/live/control")
def live_control(ctrl: LiveControl):
    # TODO (rolul 3): start / pause / reset / speed pe LiveEngine
    return {"ok": True, "state": "running" if ctrl.action == "start" else "paused", "t_min": 0}


@app.websocket("/api/live")
async def live(ws: WebSocket):
    await ws.accept()
    try:
        # TODO (rolul 3): înlocuiește cu LiveEngine.run()
        async for msg in mock_stream(interval_s=1.0):
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass


@app.get("/api/benchmark")
def benchmark():
    # TODO (rolul 2): core.benchmark.run_benchmark()
    raise HTTPException(501, "Benchmark-ul nu e implementat încă.")
