import json
import time

import pytest

from app.config import CONTRACTS_DIR
from app.core import planner
from app.core.planner import plan_route
from app.core.stops import plan_stops
from grids import make_site, synthetic_site_or_skip, wall_with_gap


def keys(obj) -> object:
    """Structura de chei, recursiv (listele după primul element), fără cheile care încep cu _."""
    if isinstance(obj, dict):
        return {k: keys(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [keys(obj[0])] if obj else []
    return None


@pytest.fixture(scope="module")
def small_site():
    return make_site(wall_with_gap(30, gap_row=5))


@pytest.fixture(scope="module")
def small_plan(small_site):
    return plan_route(small_site, small_site.habitat, ["target_east"])


def test_keys_match_contract_file(small_plan):
    contract = json.loads((CONTRACTS_DIR / "route_response.json").read_text(encoding="utf-8"))
    assert keys(small_plan) == keys(contract)


def test_small_grid_round_trip_through_target(small_site, small_plan):
    path = [tuple(c) for c in small_plan["path"]]
    target = small_site.meta["targets"][0]

    assert path[0] == path[-1] == small_site.habitat
    stop = small_plan["stops"][0]
    assert stop["id"] == "target_east"
    assert path[stop["index_in_path"]] == (target["row"], target["col"])
    assert (5, 15) in path  # prin singura trecere din perete
    assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1 for a, b in zip(path, path[1:]))


def test_result_is_plain_json(small_plan):
    assert json.loads(json.dumps(small_plan)) == small_plan


def test_unknown_target_raises(small_site):
    with pytest.raises(ValueError, match="nope"):
        plan_route(small_site, small_site.habitat, ["target_east", "nope"])


def test_tiny_duration_is_no_go(small_site):
    plan = plan_route(small_site, small_site.habitat, ["target_east"], max_duration_min=10)

    assert plan["verdict"] == "NO-GO"
    assert {"DAYLIGHT", "O2_RESERVE"} & set(plan["violations"])


# --- situl sintetic 500×500 ---


def test_synthetic_clay_delta_is_go_or_caution_under_3_s():
    site = synthetic_site_or_skip()
    started = time.perf_counter()
    plan = plan_route(site, site.habitat, ["clay_delta"])
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0, f"plan_route a durat {elapsed:.2f} s (ținta: < 3 s)"
    assert plan["verdict"] in ("GO", "CAUTION") and plan["violations"] == []
    assert plan["point_of_no_return"] is not None
    assert len(plan["elevation_profile"]) == 50


def test_synthetic_three_targets_follow_plan_stops_order(monkeypatch):
    site = synthetic_site_or_skip()
    ids = [t["id"] for t in site.meta["targets"]]
    seen = []

    def recording_plan_stops(**kwargs):
        result = plan_stops(**kwargs)
        seen.append(result)
        return result

    monkeypatch.setattr(planner, "plan_stops", recording_plan_stops)
    plan = plan_route(site, site.habitat, ids, max_duration_min=480)

    order = [s["id"] for s in plan["stops"]]
    assert len(seen) == 1 and seen[0].optimal
    assert order == seen[0].order and len(order) >= 2
    # Opririle apar pe traseu în ordinea dată, fiecare pe celula țintei.
    cells = {t["id"]: [t["row"], t["col"]] for t in site.meta["targets"]}
    indices = [s["index_in_path"] for s in plan["stops"]]
    assert indices == sorted(indices)
    assert all(plan["path"][s["index_in_path"]] == cells[s["id"]] for s in plan["stops"])
