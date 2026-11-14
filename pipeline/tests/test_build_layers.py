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


# --- datele roverului Perseverance și artefactele ------------------------------------------------

WPS = [{"sol": 13, "lat": 18.44463, "lon": 77.45089, "elev_geoid": -2569.9, "i": 0},
       {"sol": 14, "lat": 18.44463, "lon": 77.45089, "elev_geoid": -2569.9, "i": 1},  # aceeași celulă
       {"sol": 652, "lat": 18.4525, "lon": 77.4077, "elev_geoid": -2545.5, "i": 2},
       {"sol": 686, "lat": 18.4534, "lon": 77.4085, "elev_geoid": -2545.2, "i": 3},
       {"sol": 1500, "lat": 18.4541, "lon": 77.2557, "elev_geoid": -2400.0, "i": 4}]  # în afara pătratului


def test_rover_position_is_median_of_sol_window():
    lat, lon = bl.rover_position(WPS, (652, 686))
    assert lat == pytest.approx((18.4525 + 18.4534) / 2) and lon == pytest.approx((77.4077 + 77.4085) / 2)
    assert bl.rover_position(WPS, (2000, 2100)) is None and bl.rover_position([], (13, 13)) is None


def test_rover_traverse_keeps_order_drops_duplicates_and_outside():
    path = bl.rover_traverse(WPS)
    assert path[0] == list(bl.latlon_to_cell(18.44463, 77.45089))
    assert len(path) == 3  # duplicatul și punctul din afara pătratului lipsesc


def test_vertical_offset_vs_rover():
    elev = np.full((bl.N, bl.N), -2560.0, dtype=np.float32)
    many = [{**w, "i": k, "elev_geoid": -2566.0} for k, w in enumerate(WPS[:4] * 5)]
    chk = bl.vertical_offset_vs_rover(elev, many)
    assert chk["offset_m"] == pytest.approx(6.0) and chk["mean_abs_dev_m"] == 0
    assert bl.vertical_offset_vs_rover(elev, WPS) is None  # prea puține puncte


def test_locate_prefers_rover_and_falls_back():
    depot = next(a for a in bl.ARTIFACTS if a["id"] == "three_forks_depot")
    lat, lon, src = bl.locate(depot, WPS)
    assert src.startswith(bl.ROVER_SOURCE) and "sols 652-686" in src
    lat, lon, src = bl.locate(depot, [])
    assert (lat, lon, src) == (depot["lat"], depot["lon"], bl.APPROX_SOURCE)


def test_locate_uses_ingenuity_flight_log():
    first = next(a for a in bl.ARTIFACTS if a["id"] == "ingenuity_first_flight")
    lat, lon, src = bl.locate(first, [], {1: (18.44486, 77.45102), 72: (18.49727, 77.32253)})
    assert (lat, lon) == (18.44486, 77.45102) and "flight 1" in src
    # epava (zborul 72) e în afara pătratului de 10×10 km, de aceea nu e pe hartă
    r, c = bl.latlon_to_cell(18.49727, 77.32253)
    assert not (0 <= c < bl.N)


def test_artifact_definitions():
    ids = [a["id"] for a in bl.ARTIFACTS]
    assert len(ids) == len(set(ids)) and "three_forks_depot" in ids
    for a in bl.ARTIFACTS:
        assert a["type"] in {"recovery_target", "landmark", "historical_hardware", "hazard_debris"}, a["id"]
        assert a["name"].isascii() or "é" in a["name"]  # texte în engleză
        if a["type"] == "hazard_debris":
            assert a["caution_radius_m"] > 0, a["id"]


def test_synthetic_artifacts_match_contract():
    import make_synthetic_site as mss

    assert mss.ARTIFACTS == CONTRACT["artifacts"]
    for a in mss.ARTIFACTS:
        assert 0 <= a["row"] < bl.N and 0 <= a["col"] < bl.N


# --- capitolul 5: terenul (THEMIS) și mineralele (unități ancorate) ------------------------------


def test_terrain_from_themis_classes():
    n = 40
    slope = np.full((n, n), 5.0, dtype=np.float32)
    elev = np.zeros((n, n), dtype=np.float32)
    nir = np.tile(np.linspace(0, 1, n, dtype=np.float32), (n, 1))  # rece (nisip) -> cald (rocă)
    t = bl.terrain_from_themis(nir, slope, elev)
    assert t[0, 0] == 2 and t[0, -1] == 0 and t[0, n // 2] == 1
    slope[10, 10] = 30.0  # pantă mare: rocă (și bolovani, pentru că rugozitatea e mare)
    t = bl.terrain_from_themis(nir, slope, elev)
    assert t[10, 10] in (0, 3)
    assert set(np.unique(bl.terrain_from_themis(None, slope, elev))) <= {0, 1, 3}  # fără THEMIS: fără nisip


def test_disk_and_delta_masks():
    import manual_units as mu

    m = mu.disk_mask([(10, 10)], 3, (30, 30))
    assert m[10, 13] and not m[10, 14] and m.sum() == 29  # disc de rază 3 pe grilă
    elev = np.zeros((30, 30), dtype=np.float32)
    elev[:10, :10] = 100.0  # platou
    elev[20:, 20:] = 100.0  # alt platou, neconectat
    d = mu.delta_mask(elev, (2, 2), floor_m=0.0, min_rise_m=50.0, reachable_from=reachable_from)
    assert d[:10, :10].all() and not d[20:, 20:].any()
    assert not mu.delta_mask(elev, (15, 15), 0.0, 50.0, reachable_from).any()


def test_minerals_from_units_marks_targets():
    elev = np.zeros((bl.N, bl.N), dtype=np.float32)
    targets = [{"kind": "olivine", "row": 100, "col": 100}, {"kind": "carbonate", "row": 300, "col": 300}]
    minerals, units = bl.minerals_from_units(elev, [], (250, 250), targets, log=lambda *_: None)
    assert minerals[100, 100] == 3 and minerals[300, 300] == 2 and minerals[0, 0] == 0
    assert {u["id"] for u in units} >= {"delta_deposits", "seitah", "margin_unit"}


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


def test_jezero_terrain_and_minerals(jezero):
    meta, layers = jezero
    terrain, minerals = layers["terrain"], layers["minerals"]
    assert set(np.unique(terrain)) <= {0, 1, 2, 3} and set(np.unique(minerals)) <= {0, 1, 2, 3}
    frac = [float(np.mean(terrain == k)) for k in range(4)]
    assert frac[1] > 0.3 and 0.01 < frac[2] < 0.5  # regolit dominant, ceva nisip
    kind_class = {"clay": 1, "carbonate": 2, "olivine": 3}
    for t in meta["targets"]:
        assert minerals[t["row"], t["col"]] == kind_class[t["kind"]], t["id"]  # ținta stă pe mineralul ei
    assert 0.05 < float(np.mean(minerals == 1)) < 0.6  # delta (argile) e o parte importantă a sitului
    assert meta["layers"]["minerals"]["units"] and meta["layers"]["terrain"]["instrument"]


def test_jezero_matches_rover_ground_truth(jezero):
    """Altitudinea DTM-ului se potrivește cu cea măsurată de Perseverance (dacă au fost date)."""
    meta, _ = jezero
    chk = meta["provenance"].get("rover_vertical_check")
    if not chk:
        pytest.skip("situl a fost construit fără waypoint-urile roverului")
    assert chk["n_points"] >= 100
    assert abs(chk["offset_m"]) < 0.5  # după calibrare
    assert chk["mean_abs_dev_m"] < 10


def test_jezero_artifacts_and_traverse(jezero):
    meta, layers = jezero
    arts = {a["id"]: a for a in meta["artifacts"]}
    assert "three_forks_depot" in arts and "landing_site" in arts
    for a in arts.values():
        assert 0 <= a["row"] < bl.N and 0 <= a["col"] < bl.N
        assert a["status"] in {"verified", "to verify"} and a["source"]
    if meta.get("rover_traverse"):
        assert arts["three_forks_depot"]["status"] == "verified"
        # depozitul e la ~300 m de ținta de argilă (ambele la baza frontului deltei)
        clay = next(t for t in meta["targets"] if t["id"] == "clay_delta")
        d = math.hypot(arts["three_forks_depot"]["row"] - clay["row"], arts["three_forks_depot"]["col"] - clay["col"])
        assert d * meta["cell_size_m"] < 500
        path = meta["rover_traverse"]["path"]
        assert len(path) > 50 and all(0 <= r < bl.N and 0 <= c < bl.N for r, c in path)
