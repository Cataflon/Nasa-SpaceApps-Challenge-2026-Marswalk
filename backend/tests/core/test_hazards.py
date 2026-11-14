import json
import time

import numpy as np
import pytest

from app.config import CONTRACTS_DIR
from app.core.hazards import (
    FORECAST_STEPS_MIN,
    Hazard,
    from_contract,
    hazard_field,
    predict,
    route_hit,
    route_risk,
    to_contract,
)

CELL = 20.0


def contract_storm() -> dict:
    ticks = json.loads((CONTRACTS_DIR / "live_messages.json").read_text(encoding="utf-8"))
    return next(m for m in ticks if m["type"] == "tick")["hazards"][0]


def storm(row, col, a, b, *, angle=0.0, intensity=1.0, v=(0.0, 0.0), t0=0.0) -> Hazard:
    return Hazard("s", "local_storm", ((row + 0.5) * CELL, (col + 0.5) * CELL), (a, b), angle, intensity, v, t0)


def test_round_trip_keeps_center_and_axes():
    d = contract_storm()
    out = to_contract(from_contract(d, CELL, t0_min=72), 72, CELL)

    assert out["center"] == d["center"] and out["axes_m"] == d["axes_m"]
    assert set(out) == set(d) and set(out["forecast"][0]) == set(d["forecast"][0])
    assert [f["t_min"] for f in out["forecast"]] == [72 + s for s in FORECAST_STEPS_MIN]


def test_reproduces_contract_forecast():
    d = contract_storm()  # col 30, vx = 2,5 m/s, semiaxe 1800×1100, la t = 72
    out = to_contract(from_contract(d, CELL, t0_min=72), 72, CELL)

    for expected in d["forecast"]:  # +10 min: col 105, 1950×1250; +20 min: col 180, 2100×1400
        got = next(f for f in out["forecast"] if f["t_min"] == expected["t_min"])
        assert got == expected


def test_from_contract_defaults_and_errors():
    h = from_contract({"kind": "dust_devil", "center": {"row": 1, "col": 2}, "axes_m": [60, 60], "intensity": 0.5}, CELL, 12.7)
    assert (h.id, h.angle_deg, h.velocity_ms) == ("dust_devil_12", 0.0, (0.0, 0.0))
    with pytest.raises(ValueError, match="shape"):
        from_contract({"kind": "regional_storm", "intensity": 0.9}, CELL)


def test_field_zero_outside_and_intensity_at_center():
    field = hazard_field([storm(50, 50, 200.0, 100.0, intensity=0.7)], 0.0, (100, 100), CELL)

    assert field.dtype == np.float32
    assert field[50, 50] == pytest.approx(0.7)
    assert field[50, 59] == pytest.approx(0.7 * (1 - 0.9**2))  # 180 m din 200 m pe a
    assert field[50, 60] == 0.0 and field[55, 50] == 0.0  # exact pe margine: 200 m pe a, 100 m pe b
    assert field[50, 61] == 0.0 and field[0, 0] == 0.0


def test_rotation_by_90_swaps_axes():
    flat = hazard_field([storm(50, 50, 300.0, 100.0)], 0.0, (100, 100), CELL)
    turned = hazard_field([storm(50, 50, 300.0, 100.0, angle=90.0)], 0.0, (100, 100), CELL)

    np.testing.assert_allclose(turned, flat.T, atol=1e-6)


def test_route_hit_on_crossing_path_gives_correct_minute():
    # Furtună fixă, rază 100 m care crește cu 15 m/min; traseul coboară pe coloana centrului,
    # o celulă pe minut. Primul punct cu intensitate ≥ 0,3: rândul 13, la minutul 13.
    hazards = [storm(25, 50, 100.0, 100.0)]
    path = [(r, 50) for r in range(40)]
    eta = [float(r) for r in range(40)]

    assert route_hit(path, eta, hazards, CELL, threshold=0.3) == (True, 13.0)
    # Același rezultat ca citirea din hazard_field la momentul fiecărui punct.
    first = next(i for i, (r, c) in enumerate(path) if hazard_field(hazards, eta[i], (60, 100), CELL)[r, c] >= 0.3)
    assert first == 13


def test_route_hit_parallel_far_away_is_false():
    hazards = [storm(25, 400, 300.0, 300.0, v=(0.0, 0.5))]
    path = [(r, 50) for r in range(40)]
    eta = [float(r) for r in range(40)]

    assert route_hit(path, eta, hazards, CELL) == (False, None)
    assert route_risk(path, eta, hazards, CELL) == 0.0


def test_route_risk_agrees_with_route_hit():
    hazards = [storm(25, 50, 100.0, 100.0, intensity=0.8)]
    path, eta = [(r, 50) for r in range(40)], [float(r) for r in range(40)]

    risk = route_risk(path, eta, hazards, CELL)
    assert risk == pytest.approx(0.8)
    assert route_hit(path, eta, hazards, CELL, threshold=risk)[0]
    assert not route_hit(path, eta, hazards, CELL, threshold=risk + 1e-6)[0]


def test_regional_storm_covers_whole_grid():
    regional = from_contract({"kind": "regional_storm", "intensity": 0.9}, CELL, shape=(500, 500))
    field = hazard_field([regional], 0.0, (500, 500), CELL)

    assert np.all(field > 0.0) and field.max() == pytest.approx(0.9, abs=1e-3)


def test_predict_moves_center_and_grows_axes_additively():
    h = predict(storm(10, 10, 500.0, 300.0, v=(1.0, -2.0)), 30.0)
    assert h.center_m == pytest.approx((210.0 + 1800.0, 210.0 - 3600.0))
    assert h.axes_m == pytest.approx((500.0 + 450.0, 300.0 + 450.0))


def test_hazard_field_500_under_50_ms():
    hazards = [storm(220, 30, 1800.0, 1100.0, angle=15.0, intensity=0.7, v=(0.0, 2.5), t0=72),
               storm(100, 400, 120.0, 120.0, intensity=0.9),
               from_contract({"kind": "regional_storm", "intensity": 0.5}, CELL, shape=(500, 500))]
    hazard_field(hazards, 100.0, (500, 500), CELL)  # încălzire
    started = time.perf_counter()
    hazard_field(hazards, 100.0, (500, 500), CELL)
    assert time.perf_counter() - started < 0.05
