"""L4 b: server REAL (uvicorn într-un subproces pe portul 8002), @slow.

Situl e setat inexistent (MARSWALK_SITE=audit_no_site), deci API-ul folosește traseul mock din contract și
motorul folosește alternativele de rezervă: testul verifică transportul (broadcast, deconectare,
reconectare), nu algoritmii. Clientul WebSocket e `websockets`, dependență tranzitivă a uvicorn[standard]
(din requirements.txt); dacă lipsește, testele se sar.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

websockets = pytest.importorskip("websockets")
pytestmark = pytest.mark.slow

PORT = 8002
BASE, WS = f"http://127.0.0.1:{PORT}", f"ws://127.0.0.1:{PORT}/api/live"
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server():
    env = dict(os.environ, LLM_ENABLED="0", MARSWALK_SITE="audit_no_site", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api.main:app", "--port", str(PORT), "--log-level", "warning"],
                            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)  # așteptarea pornirii serverului real (singurul sleep, inevitabil aici)
        else:
            pytest.fail("serverul nu a pornit pe 8002")
        yield BASE
    finally:
        proc.terminate()
        proc.wait(10)


async def _listen(log, name, stop, n_max=None):
    async with websockets.connect(WS) as ws:
        while not stop.is_set():
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), 0.3))
            except asyncio.TimeoutError:
                continue
            log.append((name, m))
            if n_max and sum(1 for x, _ in log if x == name) >= n_max:
                return


async def _start(http, speed=60):
    r = (await http.post("/api/route", json={"start": {"row": 300, "col": 200}, "stops": ["clay_delta"]})).json()
    await http.post("/api/live/control", json={"action": "reset"})
    await http.post("/api/live/control", json={"action": "start", "route_id": r["route_id"], "speed": speed})


def test_three_clients_receive_identical_decisions(server):
    """3 clienți simultani primesc aceleași mesaje decision (broadcast, ROL3 sarcina 4)."""
    async def main():
        log, stop = [], asyncio.Event()
        async with httpx.AsyncClient(base_url=server, timeout=10) as http:
            tasks = [asyncio.create_task(_listen(log, n, stop)) for n in "ABC"]
            await asyncio.sleep(0.3)
            await _start(http)
            await http.post("/api/live/event", json={"event": "regional_storm", "params": {}})
            t_end = time.perf_counter() + 8
            while time.perf_counter() < t_end and not all(
                    any(x == n and m["type"] == "decision" for x, m in log) for n in "ABC"):
                await asyncio.sleep(0.1)
            stop.set()
            await asyncio.gather(*tasks)
        per = {n: [m for x, m in log if x == n and m["type"] == "decision"] for n in "ABC"}
        assert per["A"], "nicio decizie primită"
        assert per["A"] == per["B"] == per["C"]

    asyncio.run(main())


def test_disconnect_does_not_affect_others_and_reconnect_gets_current_state(server):
    """Un client care pleacă la mijloc nu oprește ceilalți; la reconectare primește starea curentă (ultimul tick)."""
    async def main():
        log, stop = [], asyncio.Event()
        async with httpx.AsyncClient(base_url=server, timeout=10) as http:
            stay = asyncio.create_task(_listen(log, "stay", stop))
            leaver = asyncio.create_task(_listen(log, "leave", stop, n_max=5))
            await asyncio.sleep(0.3)
            await _start(http, speed=20)
            await leaver  # clientul pleacă după 5 mesaje
            before = max(m["t_min"] for x, m in log if x == "stay" and m["type"] == "tick")
            await asyncio.sleep(1.0)
            after = max(m["t_min"] for x, m in log if x == "stay" and m["type"] == "tick")
            assert after > before, "clientul rămas nu mai primește tick-uri"
            state = (await http.post("/api/live/control", json={"action": "speed", "speed": 20})).json()
            async with websockets.connect(WS) as ws:
                first = json.loads(await asyncio.wait_for(ws.recv(), 2))
            assert first["type"] == "tick" and first["t_min"] >= state["t_min"] - 1
            stop.set()
            await stay

    asyncio.run(main())
