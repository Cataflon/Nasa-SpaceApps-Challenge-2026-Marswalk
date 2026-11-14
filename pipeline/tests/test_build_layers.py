"""Teste pentru build_layers.py și pentru situl Jezero generat (data/processed/jezero, intră în git).

- funcțiile pure (numpy): rulează și în CI;
- reproiectarea pe un GeoTIFF local: sărită fără rasterio;
- validarea sitului real: sărită dacă data/processed/jezero/meta.json lipsește.
"""

import json
import math

import numpy as np
import pytest

import build_layers as bl
import fetch_stac as fs
from make_synthetic_site import reachable_from

CONTRACT = json.loads((fs.ROOT / "shared" / "contracts" / "meta.json").read_text(encoding="utf-8"))
JEZERO = fs.ROOT / "data" / "processed" / "jezero"


# --- coordonate --------------------------------------------------------------------------------


def test_center_maps_to_middle_of_grid():
    assert bl.latlon_to_cell(fs.CENTER_LAT, fs.CENTER_LON) == (250, 250)


def test_cell_size_is_true_20_m_on_mars():
    """Un pas de o celulă spre est = 20 m reali (grila locală are scara corectă la 18,44°)."""
    lat_a, lon_a = bl.cell_to_latlon(250, 250)
    lat_b, lon_b = bl.cell_to_latlon(250, 251)
    r = fs.MARS_RADIUS_M
    east_m = r * math.cos(math.radians(lat_a)) * math.radians(lon_b - lon_a)
    assert east_m == pytest.approx(20.0, rel=1e-3)
    lat_c, _ = bl.cell_to_latlon(251, 250)
    assert r * math.radians(lat_a - lat_c) == pytest.approx(20.0, rel=1e-9)  # row crește spre sud


def test_latlon_roundtrip():
    for row, col in [(0, 0), (123, 456), (499, 499), (229, 264)]:
        assert bl.latlon_to_cell(*bl.cell_to_latlon(row, col)) == (row, col)


# --- agregare, pantă, îmbinare -----------------------------------------------------------------


def test_block_max_keeps_small_obstacles():
    fine = np.zeros((10, 10), dtype=np.float32)
    fine[7, 2] = 40.0  # un singur pixel abrupt
    agg = bl.block_nanmax(fine, 5)
    assert agg.shape == (2, 2) and agg[1, 0] == 40.0 and agg[0, 0] == 0.0
    assert bl.block_nanmean(fine, 5)[1, 0] == pytest.approx(40.0 / 25)


def test_block_ops_handle_all_nan():
    a = np.full((5, 5), np.nan, dtype=np.float32)
    assert np.isnan(bl.block_nanmax(a, 5)).all() and np.isnan(bl.block_nanmean(a, 5)).all()


def test_slope_of_known_plane():
    y, x = np.mgrid[0:20, 0:20] * 4.0
    plane = (x * math.tan(math.radians(30))).astype(np.float32)
    s = bl.slope_deg(plane, 4.0)
    assert np.allclose(s, 30.0, atol=1e-3)


def test_slope_does_not_invent_edges_at_nodata():
    e = np.zeros((10, 10), dtype=np.float32)
    e[:, 5:] = np.nan
    s = bl.slope_deg(e, 4.0)
    assert np.all(np.isnan(s[:, 4:])) and np.allclose(s[:, :4], 0)


def test_feather_ramps_from_edge():
    valid = np.zeros((30, 30), dtype=bool)
    valid[5:25, 5:25] = True
    w = bl.feather(valid, 5)
    assert w[0, 0] == 0 and w[5, 5] == pytest.approx(0.2) and w[15, 15] == 1.0
    assert np.all(np.diff(w[15, 5:11]) >= 0)
    # marginea grilei nu e margine de date
    full = np.ones((10, 10), dtype=bool)
    assert np.all(bl.feather(full, 4) == 1.0)


def test_blend_onto_has_no_step_at_edge():
    base = np.zeros((40, 40), dtype=np.float32)
    top = np.full((40, 40), np.nan, dtype=np.float32)
    top[:, 10:] = 10.0  # o treaptă de 10 m dacă ar fi lipită brut
    out = bl.blend_onto(base, top, 10)
    jumps = np.abs(np.diff(out[20, :]))
    assert jumps.max() <= 1.0 + 1e-6  # treapta e împărțită pe 10 pixeli
    assert out[20, 39] == pytest.approx(10.0, abs=1.0) and out[20, 0] == 0


def test_vertical_bias_and_weighted_median():
    ref = np.random.default_rng(0).normal(-2550, 30, (60, 60)).astype(np.float32)
    assert bl.vertical_bias(ref - 33.0, ref) == pytest.approx(-33.0)
    assert bl.vertical_bias(ref[:2, :2], ref[:2, :2]) == 0.0  # suprapunere prea mică
    assert bl.weighted_median([-21.7, -33.0, -31.0], [0.33, 0.51, 0.41]) == -31.0
    assert bl.weighted_median([5.0], [1.0]) == 5.0


def test_flattest_near_and_snap():
    slope = np.full((40, 40), 10.0, dtype=np.float32)
    slope[25:32, 25:32] = 0.5  # un platou
    assert bl.flattest_near(slope, (20, 20), radius=12) == (28, 28)
    reach = np.zeros((40, 40), dtype=bool)
    reach[30, 10] = reach[10, 30] = True
    assert bl.snap_to_reachable(reach, (20, 20), 15) == (10, 30)  # egal ca distanță: row mai mic
    assert bl.snap_to_reachable(reach, (0, 0), 3) is None


def test_targets_inside_square():
    for t in bl.TARGETS:
        r, c = bl.latlon_to_cell(t["lat"], t["lon"])
        assert 0 <= r < bl.N and 0 <= c < bl.N, t["id"]
    assert {t["id"] for t in bl.TARGETS} == {t["id"] for t in CONTRACT["targets"]}


# --- reproiectarea (rasterio, fără rețea) -------------------------------------------------------


def test_warp_to_grid_places_pixels_correctly(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    # Raster în CRS-ul produselor USGS (paralela standard la ecuator), cu valoarea = latitudinea.
    crs = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +R=3396190 +units=m +no_defs +type=crs"
    r = fs.MARS_RADIUS_M
    x0, y0, step, n = r * math.radians(77.30), r * math.radians(18.60), 50.0, 400
    ys = y0 - (np.arange(n) + 0.5) * step
    data = np.repeat(np.degrees(ys / r)[:, None], n, axis=1).astype("float32")
    path = tmp_path / "lat.tif"
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32", crs=crs,
                       transform=from_origin(x0, y0, step, step), nodata=-32767.0) as ds:
        ds.write(data, 1)
    out = bl.warp_to_grid(path, (50, 50), "bilinear")
    # Rândul 0 e marginea de nord, rândul 49 marginea de sud a pătratului de 10 km.
    lat_n, _ = bl.cell_to_latlon(0, 0, n=50, cell_m=200)
    lat_s, _ = bl.cell_to_latlon(49, 0, n=50, cell_m=200)
    assert out[0, 25] == pytest.approx(lat_n, abs=1e-3)
    assert out[49, 25] == pytest.approx(lat_s, abs=1e-3)


# --- situl Jezero generat (intră în git) ---------------------------------------------------------


@pytest.fixture(scope="module")
def jezero():
    if not (JEZERO / "meta.json").exists():
        pytest.skip("situl Jezero nu e generat (rulează fetch_stac.py + build_layers.py)")
    meta = json.loads((JEZERO / "meta.json").read_text(encoding="utf-8"))
    layers = {name: np.load(JEZERO / spec["file"]) for name, spec in meta["layers"].items()}
    return meta, layers


def test_jezero_matches_contract(jezero):
    meta, layers = jezero
    assert CONTRACT.keys() <= meta.keys()
    assert meta["site_id"] == "jezero" and meta["source"] == "nasa"
    assert meta["shape"] == CONTRACT["shape"] and meta["cell_size_m"] == CONTRACT["cell_size_m"]
    assert meta["center"] == CONTRACT["center"]
    for name, spec in CONTRACT["layers"].items():
        assert name in layers, name
        assert {k: meta["layers"][name][k] for k in ("file", "dtype", "unit")} == spec, name
        grid = layers[name]
        assert grid.shape == tuple(meta["shape"]) and str(grid.dtype) == spec["dtype"], name
        assert (JEZERO / spec["file"]).stat().st_size <= 2 * 1024 * 1024, name
        if name != "unsafe":
            assert (JEZERO / "png" / f"{name}.png").stat().st_size <= 1024 * 1024, name
        if grid.dtype.kind == "f":
            assert np.isfinite(grid).all(), name


def test_jezero_layers_are_labeled(jezero):
    meta, _ = jezero
    for name, spec in meta["layers"].items():
        assert spec.get("data_type") and spec.get("source") and spec.get("instrument"), name
    assert meta["layers"]["elevation"]["source"] == "nasa"
    assert "HiRISE" in meta["layers"]["slope"]["instrument"]
    assert meta["provenance"]["hirise_dtms"] and meta["provenance"]["ctx_dtms"]


def test_jezero_values_are_plausible(jezero):
    meta, layers = jezero
    elev, slope = layers["elevation"], layers["slope"]
    assert -2700 < float(elev.mean()) < -2400  # fundul craterului Jezero, față de areoid
    assert 0 <= float(slope.min()) and float(slope.max()) < 90
    assert 0.1 < (slope > 25).mean() * 100 < 15  # sunt obstacole, dar terenul e mergibil
    assert 24 < float(layers["radiation"].mean()) < 29
    assert meta["provenance"]["hirise_coverage_pct"] > 50


def test_jezero_habitat_flat_and_targets_reachable(jezero):
    meta, layers = jezero
    slope, unsafe = layers["slope"], layers["unsafe"]
    h = (meta["habitat"]["row"], meta["habitat"]["col"])
    assert slope[h[0] - 3 : h[0] + 4, h[1] - 3 : h[1] + 4].max() <= 8.0  # teren plat în jurul habitatului
    reach = reachable_from((slope <= meta["max_slope_deg"]) & ~unsafe, h)
    assert [t["id"] for t in meta["targets"]] == [t["id"] for t in CONTRACT["targets"]]
    for t in meta["targets"]:
        cell = (t["row"], t["col"])
        assert slope[cell] <= meta["max_slope_deg"] and not unsafe[cell], t["id"]
        assert reach[cell], t["id"]
        assert t["image"] is None or t["image"].startswith("/static/layers/stops/")
