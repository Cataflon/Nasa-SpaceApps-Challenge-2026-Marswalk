import json
import math

import numpy as np
import pytest

from app.config import CONTRACTS_DIR
from app.core.grid import NEIGHBORS, SQRT2, octile, pad_and_flatten, to_cell, to_flat
from grids import WALL_SLOPE_DEG, make_site, wall_with_gap


def numbered(rows: int, cols: int) -> np.ndarray:
    """Grilă în care fiecare celulă are o valoare unică, ca o conversie greșită să se vadă."""
    return np.arange(rows * cols, dtype=np.float64).reshape(rows, cols)


def corners_and_center(rows: int, cols: int) -> list[tuple[int, int]]:
    return [(0, 0), (0, cols - 1), (rows - 1, 0), (rows - 1, cols - 1), (rows // 2, cols // 2)]


# Grila nepătrată prinde inversarea rând/coloană, pe care una pătrată o ascunde.
@pytest.mark.parametrize("rows, cols", [(30, 30), (4, 7), (7, 4)])
def test_round_trip_corners_and_center(rows, cols):
    cost = numbered(rows, cols)
    flat, Wp = pad_and_flatten(cost)

    assert Wp == cols + 2
    assert len(flat) == (rows + 2) * (cols + 2)
    for cell in corners_and_center(rows, cols):
        idx = to_flat(cell, Wp)
        assert to_cell(idx, Wp) == cell
        assert flat[idx] == cost[cell]


def test_round_trip_every_cell():
    rows, cols = 5, 8
    flat, Wp = pad_and_flatten(numbered(rows, cols))
    cells = [(r, c) for r in range(rows) for c in range(cols)]

    indices = [to_flat(cell, Wp) for cell in cells]
    assert len(set(indices)) == len(cells)
    assert [to_cell(i, Wp) for i in indices] == cells
    # Tot ce nu e celulă reală e bordură.
    assert sum(math.isinf(v) for v in flat) == len(flat) - len(cells)


def test_corner_neighbors_fall_on_inf_border():
    rows, cols = 30, 30
    flat, Wp = pad_and_flatten(numbered(rows, cols))

    for cell in corners_and_center(rows, cols)[:4]:
        idx = to_flat(cell, Wp)
        neighbor_costs = [flat[idx + delta] for delta, _ in NEIGHBORS(Wp)]
        # Un colț are 3 vecini reali; ceilalți 5 sunt în afara hărții, deci pe bordură.
        assert sum(math.isinf(v) for v in neighbor_costs) == 5
        real = sorted(to_cell(idx + delta, Wp) for delta, _ in NEIGHBORS(Wp) if not math.isinf(flat[idx + delta]))
        assert len(real) == 3
        assert all(0 <= r < rows and 0 <= c < cols for r, c in real)


def test_center_neighbors_are_the_eight_around():
    rows, cols = 30, 30
    flat, Wp = pad_and_flatten(numbered(rows, cols))
    center = (rows // 2, cols // 2)
    idx = to_flat(center, Wp)

    found = [(to_cell(idx + delta, Wp), step) for delta, step in NEIGHBORS(Wp)]

    assert not any(math.isinf(flat[idx + delta]) for delta, _ in NEIGHBORS(Wp))
    expected = {(center[0] + dr, center[1] + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)} - {center}
    assert {cell for cell, _ in found} == expected
    # Lungimea pasului: 1 pe direcțiile drepte, √2 pe diagonale.
    for cell, step in found:
        diagonal = cell[0] != center[0] and cell[1] != center[1]
        assert step == (SQRT2 if diagonal else 1.0)


def test_neighbors_order_is_fixed():
    assert NEIGHBORS(32) == NEIGHBORS(32)
    assert [delta for delta, _ in NEIGHBORS(32)] == [-32, 32, -1, 1, -33, -31, 31, 33]


def test_octile():
    assert octile((3, 3), (3, 3)) == 0.0
    assert octile((0, 0), (0, 5)) == 5.0
    assert octile((0, 0), (5, 0)) == 5.0
    assert octile((0, 0), (4, 4)) == pytest.approx(4 * SQRT2)
    # 3 pași pe diagonală + 1 drept.
    assert octile((0, 0), (3, 4)) == pytest.approx(3 * SQRT2 + 1)
    assert octile((2, 9), (7, 1)) == octile((7, 1), (2, 9))


def test_pad_and_flatten_keeps_input_and_blocks_nan():
    cost = np.ones((3, 4), dtype=np.float32)
    cost[1, 2] = np.nan
    cost[2, 0] = np.inf
    before = cost.copy()

    flat, Wp = pad_and_flatten(cost)

    np.testing.assert_array_equal(cost, before)
    assert math.isinf(flat[to_flat((1, 2), Wp)])
    assert math.isinf(flat[to_flat((2, 0), Wp)])
    assert flat[to_flat((0, 0), Wp)] == 1.0
    assert all(type(v) is float for v in flat)


def test_pad_and_flatten_rejects_non_2d():
    with pytest.raises(ValueError):
        pad_and_flatten(np.ones(5))


# --- helperii din grids.py: tot restul testelor se sprijină pe ei ---


def test_wall_with_gap_has_single_gap():
    n, gap_row = 30, 5
    slope = wall_with_gap(n, gap_row)

    wall = slope[:, n // 2]
    assert slope.shape == (n, n) and slope.dtype == np.float32
    assert np.flatnonzero(wall < WALL_SLOPE_DEG).tolist() == [gap_row]
    # În afara peretelui, terenul e plat.
    assert np.count_nonzero(slope) == n - 1


def test_make_site_matches_contract_layers():
    contract = json.loads((CONTRACTS_DIR / "meta.json").read_text(encoding="utf-8"))
    slope = wall_with_gap()
    site = make_site(slope)

    assert set(site.layers) == set(contract["layers"])
    for name, spec in contract["layers"].items():
        assert site.layers[name].shape == slope.shape
        assert site.layers[name].dtype == np.dtype(spec["dtype"])
    assert set(site.meta) == set(contract)
    assert site.shape == (30, 30) and site.cell_size_m == 20.0
    assert WALL_SLOPE_DEG > site.meta["max_slope_deg"]

    # Habitatul și ținta implicită sunt de o parte și de alta a peretelui, pe teren liber.
    target = site.meta["targets"][0]
    assert set(target) == set(contract["targets"][0])
    assert site.habitat[1] < 15 < target["col"]
    assert site.layers["slope"][site.habitat] == 0.0
    assert site.layers["slope"][target["row"], target["col"]] == 0.0


def test_make_site_layer_override():
    slope = wall_with_gap(10, 2)
    elevation = np.full((10, 10), -2540.0)
    site = make_site(slope, cell=5.0, habitat=(1, 1), elevation=elevation)

    assert site.cell_size_m == 5.0 and site.habitat == (1, 1)
    assert site.layers["elevation"].dtype == np.float32
    assert float(site.layers["elevation"][0, 0]) == -2540.0
    with pytest.raises(ValueError):
        make_site(slope, no_such_layer=elevation)
