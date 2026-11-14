"""T6: API-ul cu core-ul real pe situl sintetic (skip dacă situl lipsește) + cache-ul de benchmark."""

import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.api.bench_cache import BenchmarkCache
from app.core import planner
from app.core.costmap import static_cost
from app.core.site_data import get_site
from app.live.store import routes

client = TestClient(main.app)  # fără `with`: lifespan-ul (warm-up, benchmark) nu pornește aici


@pytest.fixture
def site():
    s = get_site()
    if s is None:
        pytest.skip("Situl sintetic lipsește: rulează pipeline/make_synthetic_site.py.")
    return s


@pytest.fixture(autouse=True)
def clean_store():
    routes.clear()
    yield
    routes.clear()


# --- T6a / T6c: POST /api/route cu planner.plan_route real ---


def test_route_uses_real_planner_and_store_ids(site):
    req = {"start": {"row": site.habitat[0], "col": site.habitat[1]}, "stops": [site.meta["targets"][0]["id"]]}
    first, second = client.post("/api/route", json=req), client.post("/api/route", json=req)
    assert first.status_code == second.status_code == 200
    assert "X-Mock" not in first.headers
    assert [first.json()["route_id"], second.json()["route_id"]] == ["plan_0", "plan_1"]  # din stoc, nu „plan_0” mereu
    body = first.json()
    assert body["path"][0] == list(site.habitat) and body["path"][-1] == list(site.habitat)
    assert body["verdict"] in ("GO", "CAUTION", "NO-GO")
    assert routes.get("plan_1")["path"] == body["path"]


def test_route_from_forbidden_cell_is_422_in_english(site):
    forbidden = np.argwhere(~np.isfinite(static_cost(site, "safe")))
    row, col = (int(v) for v in forbidden[0])
    r = client.post("/api/route", json={"start": {"row": row, "col": col}, "stops": [site.meta["targets"][0]["id"]]})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail.isascii() and "cannot reach the habitat" in detail


def test_planner_checks_reachability_before_astar(site, monkeypatch):
    """O țintă cu cost_to_home = inf e respinsă din tabloul lui reverse_dijkstra, fără niciun astar."""
    cost_to_home, parent = planner.home_tree(site, "safe")
    target = site.meta["targets"][0]
    patched = cost_to_home.copy()
    patched[target["row"], target["col"]] = np.inf
    monkeypatch.setattr(planner, "home_tree", lambda s, p: (patched, parent))

    def no_astar(*a, **k):
        raise AssertionError("astar nu trebuie chemat pentru o țintă inaccesibilă")

    monkeypatch.setattr(planner, "astar", no_astar)
    with pytest.raises(ValueError, match="not reachable"):
        planner.plan_route(site, site.habitat, [target["id"]])
    with pytest.raises(ValueError, match="outside"):
        planner.plan_route(site, (-1, 5), [target["id"]])


def test_point_of_no_return_null_stays_null(site, monkeypatch):
    real = planner.plan_route

    def without_pnr(*args, **kwargs):
        return {**real(*args, **kwargs), "point_of_no_return": None}

    monkeypatch.setattr(main.planner, "plan_route", without_pnr)
    req = {"start": {"row": site.habitat[0], "col": site.habitat[1]}, "stops": [site.meta["targets"][0]["id"]]}
    r = client.post("/api/route", json=req)
    assert r.status_code == 200 and r.json()["point_of_no_return"] is None
    assert routes.latest()["point_of_no_return"] is None


def test_static_cost_is_read_only_for_api_callers(site):
    cost = static_cost(site, "safe")
    with pytest.raises(ValueError):
        cost[0, 0] = 1.0
    copy = cost.copy()
    copy[0, 0] = 1.0  # pe copie se poate


# --- T6e: încălzirea core-ului ---


def test_warm_up_core_fills_the_caches(site):
    main.warm_up_core()
    for key in ("home:safe", "o2_home", "minutes"):
        entry = planner._cache.get((id(site), key))
        assert entry is not None and entry[0]() is site, key
    started = time.perf_counter()
    planner.plan_route(site, site.habitat, [site.meta["targets"][0]["id"]])
    assert time.perf_counter() - started < 0.5  # după încălzire, fără Dijkstra


# --- T6f: GET /api/benchmark ---


def test_benchmark_is_503_until_ready_then_cached(site, monkeypatch):
    gate, calls = threading.Event(), []
    fake = {"n": 3, "seed": 42, "plan_only": {}, "copilot": {}, "per_scenario": [],
            "headline": {"copilot_safe_pct": 80.0, "plan_safe_pct": 60.0, "n_scenarios": 3}}

    def slow(n, seed):
        calls.append((n, seed))
        gate.wait(5)
        return fake

    cache = BenchmarkCache(3, 42, compute=slow)
    monkeypatch.setattr(main, "bench", cache)
    r = client.get("/api/benchmark")
    assert r.status_code == 503 and int(r.headers["Retry-After"]) > 0
    assert client.get("/api/benchmark").status_code == 503  # încă rulează, nu pornește a doua oară
    gate.set()
    cache._thread.join(5)
    for _ in range(2):
        r = client.get("/api/benchmark")
        assert r.status_code == 200 and r.json()["headline"] == fake["headline"]
    assert calls == [(3, 42)]  # calculat o singură dată


def test_benchmark_failure_is_500(site, monkeypatch):
    def broken(n, seed):
        raise RuntimeError("boom")

    cache = BenchmarkCache(3, 42, compute=broken)
    monkeypatch.setattr(main, "bench", cache)
    assert client.get("/api/benchmark").status_code == 503
    cache._thread.join(5)
    r = client.get("/api/benchmark")
    assert r.status_code == 500 and "boom" in r.json()["detail"]


def test_benchmark_without_site_is_503(monkeypatch):
    monkeypatch.setattr(main, "bench", BenchmarkCache(3, 42, compute=lambda n, s: {}))
    monkeypatch.setattr(main, "get_site", lambda: None)
    assert client.get("/api/benchmark").status_code == 503


@pytest.mark.slow
def test_benchmark_real_core_in_subprocess(site):
    """Calea reală: run_benchmark în procesul separat, pe 2 scenarii, cu `headline`."""
    cache = BenchmarkCache(2, 42)
    cache.start()
    cache._thread.join(120)
    assert cache.error is None, cache.error
    h = cache.result["headline"]
    assert h["n_scenarios"] == 2 and 0 <= h["copilot_safe_pct"] <= 100 and 0 <= h["plan_safe_pct"] <= 100


def test_benchmark_stop_terminates_subprocess_and_allows_restart(site):
    cache = BenchmarkCache(100, 42)
    cache.start()
    time.sleep(0.2)  # oprirea poate veni oricând: înainte, în timpul sau după pornirea procesului
    cache.stop()
    cache._thread.join(30)
    assert not cache.running and cache.result is None and cache.error is None  # oprirea nu e eroare
    assert cache._proc is not None and not cache._proc.is_alive()
