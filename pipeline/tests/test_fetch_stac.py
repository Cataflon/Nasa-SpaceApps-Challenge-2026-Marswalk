"""Teste pentru fetch_stac.py.

- geometria și alegerea produselor: doar math, rulează și în CI (fără rasterio);
- decuparea: pe un GeoTIFF local generat în test (rasterio, fără rețea), sărit dacă lipsește rasterio;
- căutarea reală în STAC: `@pytest.mark.slow` (rețea), rulează doar cu `-m slow`.
"""

import json
import math

import pytest

import fetch_stac as fs

CONTRACT = json.loads((fs.ROOT / "shared" / "contracts" / "meta.json").read_text(encoding="utf-8"))


# --- geometria --------------------------------------------------------------------------------


def test_center_matches_contract():
    assert (fs.CENTER_LAT, fs.CENTER_LON) == (CONTRACT["center"]["lat"], CONTRACT["center"]["lon"])


def test_bbox_is_10_km_square_on_mars():
    lon0, lat0, lon1, lat1 = fs.bbox()
    assert lon0 < fs.CENTER_LON < lon1 and lat0 < fs.CENTER_LAT < lat1
    ns_km = (lat1 - lat0) * fs.KM_PER_DEG_LAT
    ew_km = (lon1 - lon0) * fs.KM_PER_DEG_LAT * math.cos(math.radians(fs.CENTER_LAT))
    assert ns_km == pytest.approx(10.0, rel=1e-9)
    assert ew_km == pytest.approx(10.0, rel=1e-9)
    assert fs.KM_PER_DEG_LAT == pytest.approx(59.27, abs=0.01)


def test_grid_is_500_cells_of_20_m():
    xmin, ymin, xmax, ymax = fs.grid_bounds()
    assert (xmax - xmin) / fs.GRID_CELL_M == fs.GRID_N == CONTRACT["shape"][1]
    assert (ymax - ymin) / fs.GRID_CELL_M == fs.GRID_N == CONTRACT["shape"][0]
    assert fs.GRID_CELL_M == CONTRACT["cell_size_m"]
    assert fs.grid_bounds(margin_m=500)[0] == xmin - 500


def test_local_crs_is_true_scale_at_center():
    p = fs.local_proj4()
    assert f"+lat_ts={fs.CENTER_LAT}" in p and f"+lon_0={fs.CENTER_LON}" in p and "+R=3396190" in p


def test_bbox_overlap():
    a = (0, 0, 10, 10)
    assert fs.bbox_overlap(a, (0, 0, 10, 10)) == 1.0
    assert fs.bbox_overlap(a, (5, 0, 20, 10)) == 0.5
    assert fs.bbox_overlap(a, (20, 20, 30, 30)) == 0.0


def test_rank_items_deterministic():
    target = (0, 0, 10, 10)
    items = [
        {"id": "b", "bbox": [0, 0, 10, 10], "gsd": 20.1, "coverage": 0.9},
        {"id": "a", "bbox": [0, 0, 10, 10], "gsd": 20.1, "coverage": 0.9},
        {"id": "c", "bbox": [0, 0, 10, 10], "gsd": 20.0, "coverage": 0.9},
        {"id": "d", "bbox": [0, 0, 10, 10], "gsd": 6.0, "coverage": 1.0},
        {"id": "e", "bbox": [5, 0, 10, 10], "gsd": 6.0, "coverage": None},  # 50% din bbox
    ]
    ids = [it["id"] for it in fs.rank_items(items, target)]
    assert ids == ["d", "c", "a", "b", "e"]
    assert ids == [it["id"] for it in fs.rank_items(list(reversed(items)), target)]


def test_products_are_labeled():
    for kind, spec in fs.COLLECTIONS.items():
        assert spec["mission"] and spec["instrument"] and spec["collection"], kind
        assert set(spec["assets"]) == set(spec["resampling"]), kind
        assert set(spec["assets"].values()) <= {"topographic", "optical", "thermal", "quality"}, kind


def test_write_manifest_merges_partial_runs(tmp_path):
    def prod(kind, item):
        return fs.Product(kind=kind, item_id=item, asset="dtm", data_type="topographic", mission="MRO",
                          instrument="X", collection="c", href="h", file=f"{kind}/{item}.tif")

    fs.write_manifest(tmp_path, [prod("ctx_dtm", "C1"), prod("hirise_dtm", "H1")], 4.0)
    fs.write_manifest(tmp_path, [prod("hirise_dtm", "H2")], 4.0)  # ca la --only hirise_dtm
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [(p["kind"], p["item_id"]) for p in m["products"]] == [("ctx_dtm", "C1"), ("hirise_dtm", "H2")]
    assert m["center"] == {"lat": fs.CENTER_LAT, "lon": fs.CENTER_LON}
    assert m["products"][0]["mission"] == "MRO"


# --- decuparea pe un raster local (rasterio, fără rețea) --------------------------------------


@pytest.fixture
def mars_cog(tmp_path):
    """Un GeoTIFF 1 m în CRS-ul produselor USGS (echirectangular, paralela standard la ecuator)."""
    rasterio = pytest.importorskip("rasterio")
    np = pytest.importorskip("numpy")
    from rasterio.transform import from_origin

    crs = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +R=3396190 +units=m +no_defs +type=crs"
    r = fs.MARS_RADIUS_M
    x0 = r * math.radians(fs.CENTER_LON) - 8000
    y0 = r * math.radians(fs.CENTER_LAT) + 8000
    n = 16000 // 4  # 16 km la 4 m (pixel mare ca testul să fie rapid)
    rows, cols = np.mgrid[0:n, 0:n]
    data = (rows * 0.5 + cols * 0.25).astype("float32")
    path = tmp_path / "src.tif"
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32", crs=crs,
                       transform=from_origin(x0, y0, 4.0, 4.0), nodata=-32767.0, tiled=True) as ds:
        ds.write(data, 1)
    return path


def test_crop_reads_only_the_window(mars_cog, tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    out = tmp_path / "crop.tif"
    info = fs.crop(str(mars_cog), out, fs.src_bounds_factory(), step_m=None)
    with rasterio.open(out) as ds:
        b = transform_bounds(ds.crs, CRS.from_string(fs.local_proj4()), *ds.bounds)
        # fereastra (10 km + 2 × 0,5 km margine) e acoperită, iar restul rasterului (16 km) nu e citit
        assert b[0] <= -5500 + 5 and b[2] >= 5500 - 5 and b[1] <= -5500 + 5 and b[3] >= 5500 - 5
        assert ds.width < 16000 / 4 and ds.height < 16000 / 4
        # E-V: 11 km pe teren = 11 / cos(18,44°) km în proiecția cu paralela la ecuator
        assert ds.width * 4 == pytest.approx(11000 / math.cos(math.radians(fs.CENTER_LAT)), rel=0.01)
        assert ds.height * 4 == pytest.approx(11000, rel=0.01)
    assert info["native_res_m"] == pytest.approx(4.0)


def test_crop_decimates_to_step(mars_cog, tmp_path):
    rasterio = pytest.importorskip("rasterio")
    out = tmp_path / "crop8.tif"
    info = fs.crop(str(mars_cog), out, fs.src_bounds_factory(), step_m=8.0, resampling="average")
    assert info["read_res_m"] == pytest.approx(8.0, rel=0.01)
    with rasterio.open(out) as ds:
        assert ds.res[0] == pytest.approx(8.0, rel=0.01)


# --- STAC real (rețea) ------------------------------------------------------------------------


@pytest.mark.slow
def test_stac_has_hirise_and_ctx_over_jezero():
    pytest.importorskip("pystac_client")
    hirise = fs.search(fs.COLLECTIONS["hirise_dtm"]["collection"])
    ctx = fs.search(fs.COLLECTIONS["ctx_dtm"]["collection"])
    assert hirise and all("dtm" in it.assets for it in hirise)
    assert ctx and all("dtm" in it.assets for it in ctx)
