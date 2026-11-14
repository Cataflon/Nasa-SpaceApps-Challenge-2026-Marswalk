"""F0: modelul unificat de hazard (ARHITECTURA_RUTARE_V2 §2): normalizare, revizii, re-ancorare."""

import json
import math

import pytest

from app.config import CONTRACTS_DIR
from app.core import hazard_spec as hs

CELL = 20.0
SHAPE = (500, 500)


def storm(**over):
    """Furtuna personalizată din §2.3 (centrul în celule)."""
    d = {"id": "user_storm_1", "kind": "custom", "scope": "local",
         "shape": {"center": {"row": 220, "col": 30}, "axes_m": [1800, 1100], "theta_deg": 90},
         "motion": [{"from_min": 72, "velocity_ms": [0, 2.5]}],
         "growth": {"alpha_m_per_min": 15, "cap_axes_m": [2400, 1600]},
         "lifetime": {"start_min": 72, "duration_min": 120},
         "effects": {"block": "core", "core_fraction": 0.5, "soft_halo": True, "speed_mult": 0.6,
                     "o2_mult": 1.1, "exposure_limit_min": 0},
         "uncertainty": {"sigma_rel": 0.2, "horizon_cap_min": 15}, "hub_effect": "none"}
    d.update(over)
    return d


def test_v2_example_normalizes():
    res = hs.normalize(storm(), cell_size_m=CELL, t_now=72, shape=SHAPE)
    assert res.ok and res.warnings == []
    s = res.spec
    assert s.center_m == ((220 + 0.5) * CELL, (30 + 0.5) * CELL)
    assert s.axes_m == (1800.0, 1100.0) and s.cap_axes_m == (2400.0, 1600.0)
    assert (s.start_min, s.end_min) == (72.0, 192.0)
    assert s.effects.speed_mult == 0.6 and s.effects.o2_mult == 1.1 and s.effects.block == "core"
    assert s.rev == 1 and s.scope == "local" and not s.ignored


def test_old_contract_params_normalize():
    ev = json.loads((CONTRACTS_DIR / "live_event.json").read_text(encoding="utf-8"))
    res = hs.normalize(ev["params"], ev["event"], cell_size_m=CELL, t_now=10, shape=SHAPE)
    assert res.ok
    assert res.spec.kind == "local_storm" and res.spec.theta_deg == 15.0
    assert res.spec.velocity_at(10) == (0.0, 2.5) and res.spec.alpha_m_per_min == 30.0  # implicitul clasei


@pytest.mark.parametrize("bad", [
    {"shape": {"center": {"row": float("nan"), "col": 3}, "axes_m": [100, 100]}},
    {"shape": {"center": {"row": 3, "col": 3}, "axes_m": [100, "abc"]}},
    {"shape": {"center": {"row": 3, "col": 3}, "axes_m": [100, 100]}, "motion": [{"velocity_ms": [math.inf, 0]}]},
])
def test_nan_or_garbage_is_rejected_with_code(bad):
    res = hs.normalize({"kind": "custom", **bad}, cell_size_m=CELL)
    assert not res.ok and res.error == hs.ERR_NAN and res.spec is None


def test_negative_axes_and_missing_center_are_rejected():
    assert hs.normalize({"kind": "custom", "shape": {"center": {"row": 1, "col": 1}, "axes_m": [-5, 10]}},
                        cell_size_m=CELL).error == hs.ERR_SHAPE
    assert hs.normalize({"kind": "local_storm"}, cell_size_m=CELL).error == hs.ERR_CENTER
    assert hs.normalize("not a dict").error == hs.ERR_SHAPE


def test_absurd_speed_is_capped_with_warning():
    res = hs.normalize(storm(motion=[{"from_min": 0, "velocity_ms": [300, 400]}]), cell_size_m=CELL, t_now=0)
    assert res.ok and hs.WARN_SPEED in res.warnings
    vy, vx = res.spec.velocity_at(0)
    assert math.hypot(vy, vx) == pytest.approx(hs.V_HAZARD_MAX_MS)
    assert vy / vx == pytest.approx(0.75)  # direcția rămâne


def test_small_axes_become_one_cell_and_small_hazard_is_ignored():
    res = hs.normalize({"kind": "dust_devil", "shape": {"center": {"row": 10, "col": 10}, "axes_m": [5, 12]}},
                       cell_size_m=CELL)
    assert res.ok and res.spec.axes_m == (CELL, CELL)
    assert res.spec.ignored and hs.WARN_IGNORED in res.warnings and not res.spec.is_geometric()


def test_missing_fields_take_class_defaults_and_clamps():
    res = hs.normalize({"kind": "fatigue"}, cell_size_m=CELL)
    assert res.ok and res.spec.scope == "point" and res.spec.effects.speed_mult == 0.8
    assert res.spec.effects.o2_mult == 1.15
    res = hs.normalize(storm(uncertainty={"sigma_rel": 7}, growth={"alpha_m_per_min": -3}), cell_size_m=CELL, t_now=72)
    assert res.spec.sigma_rel == 1.0 and res.spec.alpha_m_per_min == 0.0
    res = hs.normalize({"kind": "unknown_thing", "shape": {"center": {"row": 1, "col": 1}, "axes_m": [100, 100]}},
                       cell_size_m=CELL)
    assert res.ok and hs.WARN_KIND in res.warnings
    injured = hs.normalize({"kind": "crewmate_injured"}).spec
    assert (injured.effects.speed_mult, injured.effects.o2_mult) == (0.5, 1.5)


def test_growth_is_additive_and_capped():
    s = hs.normalize(storm(), cell_size_m=CELL, t_now=72).spec
    assert s.axes_at(72) == (1800.0, 1100.0)
    assert s.axes_at(82) == (1950.0, 1250.0)
    assert s.axes_at(500) == (2400.0, 1600.0)  # plafonul
    plain = hs.normalize(storm(growth={"alpha_m_per_min": 10}), cell_size_m=CELL, t_now=72).spec
    assert plain.cap_axes_m == (1800 + 10 * hs.H_CONE_MIN, 1100 + 10 * hs.H_CONE_MIN)  # implicit: a0 + α·H_CONE


def test_motion_on_segments():
    s = hs.normalize(storm(motion=[{"from_min": 0, "velocity_ms": [0, 2]}, {"from_min": 10, "velocity_ms": [1, 0]}]),
                     cell_size_m=CELL, t_now=0).spec
    y0, x0 = s.center_at(0)
    y, x = s.center_at(20)
    assert x - x0 == pytest.approx(2 * 600) and y - y0 == pytest.approx(1 * 600)


def test_update_reanchors_without_position_jump():
    reg = hs.HazardRegistry(CELL, SHAPE)
    reg.apply("add", storm(), t_now=72)
    before = reg.specs["user_storm_1"].center_at(100)
    res = reg.apply("update", {"id": "user_storm_1", "motion": [{"from_min": 100, "velocity_ms": [0, 5]}]}, t_now=100)
    s = res.spec
    assert res.ok and res.op == "update" and s.rev == 2
    assert s.t0_min == 100 and s.center_at(100) == pytest.approx(before)  # fără salt
    assert s.center_at(110)[1] - s.center_at(100)[1] == pytest.approx(5 * 600)
    assert s.effects.speed_mult == 0.6 and s.end_min == 192.0  # restul câmpurilor rămân
    assert reg.revisions() == (("user_storm_1", 2),)


def test_update_on_missing_id_is_add_and_add_on_existing_is_update():
    reg = hs.HazardRegistry(CELL, SHAPE)
    res = reg.apply("update", storm(), t_now=72)
    assert res.ok and res.op == "add" and hs.WARN_UPDATE_AS_ADD in res.warnings and res.spec.rev == 1
    res = reg.apply("add", storm(intensity=0.5), t_now=80)
    assert res.op == "update" and hs.WARN_ADD_AS_UPDATE in res.warnings and res.spec.rev == 2
    assert reg.apply("remove", {"id": "nope"}, t_now=80).error == hs.ERR_UNKNOWN_ID
    assert reg.apply("remove", {"id": "user_storm_1"}, t_now=80).ok and reg.specs == {}
    assert reg.apply("explode", {}, t_now=1).error == hs.ERR_OP


def test_invalid_update_keeps_old_spec():
    reg = hs.HazardRegistry(CELL, SHAPE)
    reg.apply("add", storm(), t_now=72)
    res = reg.apply("update", {"id": "user_storm_1", "shape": {"axes_m": [float("nan"), 3]}}, t_now=80)
    assert not res.ok and reg.specs["user_storm_1"].rev == 1


def test_large_coverage_becomes_global():
    res = hs.normalize({"kind": "custom", "shape": {"center": {"row": 250, "col": 250}, "axes_m": [9000, 9000]}},
                       cell_size_m=CELL, shape=SHAPE)
    assert res.ok and res.spec.scope == "global" and hs.WARN_GLOBAL in res.warnings
    assert not res.spec.is_geometric()
    res = hs.normalize({"kind": "custom", "shape": {"center": {"row": 250, "col": 250}, "axes_m": [3000, 3000]}},
                       cell_size_m=CELL, shape=SHAPE)
    assert res.spec.scope == "local"


def test_conversion_roundtrip_and_contract():
    s = hs.normalize(storm(), cell_size_m=CELL, t_now=72).spec
    h = hs.to_hazard(s, 82)
    assert h.center_m == s.center_at(82) and h.axes_m == s.axes_at(82) and h.velocity_ms == (0.0, 2.5)
    back = hs.from_hazard(h, cell_size_m=CELL)
    assert back.center_at(82) == pytest.approx(h.center_m) and back.velocity_at(82) == h.velocity_ms
    c = hs.to_contract(s, 82, CELL)
    assert {"id", "kind", "center", "axes_m", "forecast", "rev", "scope", "ignored"} <= set(c)
    json.dumps(c)
    g = hs.to_contract(hs.normalize({"kind": "regional_storm"}).spec, 5, CELL)
    assert g["scope"] == "global" and g["forecast"] == []


def test_registry_order_is_total_and_deterministic():
    reg = hs.HazardRegistry(CELL, SHAPE)
    for hid in ("b", "a", "c"):
        reg.apply("add", storm(id=hid), t_now=72)
    assert [s.id for s in reg.active(100)] == ["a", "b", "c"]
    assert reg.active(10) == []  # încă inactive (start_min = 72)
