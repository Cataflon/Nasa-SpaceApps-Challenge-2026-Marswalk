"""Caută produsele NASA/USGS pentru Jezero în STAC-ul USGS și decupează fereastra de 10×10 km.

Citește doar fereastra din COG-uri (rasterio, prin HTTP range requests), fără să descarce fișierele
întregi. Tot ce se descarcă primește etichete de proveniență în `data/raw/jezero/manifest.json`
(misiune, instrument, tip de date, ID produs, link, licență, rezoluție), folosite mai departe de
build_layers.py pentru `meta.json` și de frontend la click pe hartă.

Ce aducem (colecțiile din https://stac.astrogeology.usgs.gov/geostac/):
  - mro_hirise_socet_dtms          DTM HiRISE 1 m + FOM (calitate) + ortoimagine   topographic, optical
  - mro_ctx_controlled_usgs_dtms   DTM CTX ~20 m + ortoimagine (acoperă tot pătratul) topographic, optical
  - mo_themis_controlled_mosaics   THEMIS IR zi / noapte, 100 m                     thermal
  - M20_waypoints.json (NASA/JPL, harta https://science.nasa.gov/mission/mars-2020-perseverance/location-map/)
    pozițiile localizate ale roverului Perseverance, cu altitudinea față de areoid: traseul real,
    depozitul Three Forks, calibrarea verticală a DTM-ului.                     rover localization
CRISM (minerale) NU e în STAC-ul USGS: vine din PDS / ODE sau din harta geologică (plan B).
Datele meteo (MEDA, REMS) și radiația (RAD) nu sunt produse orbitale: sunt în scenario.py.

Rulare (cu mediul separat, vezi docs/roles/ROL1_date.md):
  .venv-pipeline/Scripts/python pipeline/fetch_stac.py --list-collections
  .venv-pipeline/Scripts/python pipeline/fetch_stac.py --dry-run          # doar caută și afișează
  .venv-pipeline/Scripts/python pipeline/fetch_stac.py                    # caută și decupează tot
  .venv-pipeline/Scripts/python pipeline/fetch_stac.py --hirise-step 1    # HiRISE la 1 m (lent)

Documentație: https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms
"""

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAC_API = "https://stac.astrogeology.usgs.gov/api/"
DEFAULT_OUT = ROOT / "data" / "raw" / "jezero"

# Centrul zonei de lucru: locul de aterizare Perseverance (Octavia E. Butler Landing, 18,4447°N
# 77,4508°E, planetocentric, longitudine est), cu frontul deltei la ~2-3 km vest. Decizia echipei:
# 18,44 / 77,45, ca în shared/contracts/meta.json.
CENTER_LAT, CENTER_LON = 18.44, 77.45
HALF_SIZE_KM = 5.0
MARGIN_KM = 0.5  # margine la decupare, ca reproiectarea și panta să nu aibă efecte de bord
MARS_RADIUS_M = 3396190.0  # sfera Mars 2015 (IAU), aceeași ca în CRS-ul produselor USGS
KM_PER_DEG_LAT = 2 * math.pi * MARS_RADIUS_M / 360 / 1000  # ≈ 59,27 km

GRID_CELL_M = 20.0
GRID_N = 500

# Pozițiile roverului Perseverance (datele hărții oficiale de localizare). Fiecare punct are
# sol, lat, lon (planetocentric, est) și elev_geoid (altitudinea față de areoid, în m).
WAYPOINTS_URL = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"
WAYPOINTS_FILE = "m20_waypoints.json"
# Zborurile Ingenuity (aceeași hartă oficială): aeroporturile, poziția finală după zborul 72.
HELI_URL = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/m20_heli_waypoints.json"
HELI_FILE = "m20_heli_waypoints.json"

# Ce aducem din fiecare colecție și cum îl etichetăm.
COLLECTIONS = {
    "hirise_dtm": {
        "collection": "mro_hirise_socet_dtms",
        "assets": {"dtm": "topographic", "fom": "quality", "ortho_0": "optical"},
        "mission": "Mars Reconnaissance Orbiter (MRO)",
        "instrument": "HiRISE",
        "resampling": {"dtm": "average", "fom": "nearest", "ortho_0": "average"},
    },
    "ctx_dtm": {
        "collection": "mro_ctx_controlled_usgs_dtms",
        "assets": {"dtm": "topographic", "orthoimage": "optical"},
        "mission": "Mars Reconnaissance Orbiter (MRO)",
        "instrument": "CTX",
        "resampling": {"dtm": "nearest", "orthoimage": "nearest"},
        "max_items": 3,  # cele mai bune, după acoperirea ferestrei
    },
    "themis_ir": {
        "collection": "mo_themis_controlled_mosaics",
        "assets": {"image": "thermal"},
        "mission": "Mars Odyssey",
        "instrument": "THEMIS IR",
        "resampling": {"image": "nearest"},
    },
}


@dataclass
class Product:
    """Un fișier decupat, cu etichetele lui de proveniență."""

    kind: str  # hirise_dtm / ctx_dtm / themis_ir
    item_id: str
    asset: str
    data_type: str  # topographic / optical / thermal / quality
    mission: str
    instrument: str
    collection: str
    href: str
    file: str = ""  # relativ la directorul de ieșire
    gsd_m: float | None = None  # rezoluția nativă
    read_res_m: float | None = None  # rezoluția la care am citit
    license: str | None = None
    datetime: str | None = None
    coverage: float | None = None  # fracția din fereastră cu date valide
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------
# Geometria (doar math, fără rasterio: testabilă în CI)
# ---------------------------------------------------------------------------------------------


def bbox(half_km: float = HALF_SIZE_KM, lat: float = CENTER_LAT, lon: float = CENTER_LON) -> tuple[float, float, float, float]:
    """(lon_min, lat_min, lon_max, lat_max) în grade, longitudine est, planetocentric."""
    dlat = half_km / KM_PER_DEG_LAT
    dlon = half_km / (KM_PER_DEG_LAT * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def local_proj4(lat: float = CENTER_LAT, lon: float = CENTER_LON) -> str:
    """CRS-ul grilei: echirectangular centrat pe zonă, cu scara reală la latitudinea centrului.

    Produsele USGS au paralela standard la ecuator, deci la 18,44° un metru est-vest din proiecție
    înseamnă doar cos(18,44°) ≈ 0,95 m pe teren. Grila noastră trebuie să aibă 20 m reali.
    """
    return f"+proj=eqc +lat_ts={lat} +lat_0={lat} +lon_0={lon} +R={MARS_RADIUS_M:.0f} +units=m +no_defs +type=crs"


def grid_bounds(n: int = GRID_N, cell_m: float = GRID_CELL_M, margin_m: float = 0.0) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) ale grilei în CRS-ul local (metri, centrul = 0, 0)."""
    half = n * cell_m / 2 + margin_m
    return (-half, -half, half, half)


def bbox_overlap(a: tuple, b: tuple) -> float:
    """Fracția din `a` acoperită de `b` (bbox-uri lon/lat sau metri)."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = (a[2] - a[0]) * (a[3] - a[1])
    return (w * h) / area if area > 0 else 0.0


def rank_items(items: list[dict], target_bbox: tuple) -> list[dict]:
    """Ordine deterministă: acoperire mai mare întâi, apoi rezoluție mai bună, apoi ID-ul.

    `items` sunt dicturi {"id", "bbox", "gsd", "coverage"?}; `coverage` (fracția validă măsurată)
    are prioritate față de suprapunerea bbox-urilor dacă există.
    """
    def key(it):
        cov = it.get("coverage")
        cov = bbox_overlap(target_bbox, tuple(it["bbox"])) if cov is None else cov
        return (-round(cov, 4), it.get("gsd") or 1e9, it["id"])

    return sorted(items, key=key)


# ---------------------------------------------------------------------------------------------
# STAC + rasterio
# ---------------------------------------------------------------------------------------------

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",  # nu lista directorul S3 la fiecare deschidere
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "VSI_CACHE": "TRUE",
}


def _client():
    from pystac_client import Client

    return Client.open(STAC_API)


def list_collections() -> None:
    for col in _client().get_collections():
        if col.id.startswith(("mro_", "mo_", "mgs_", "msl_", "m2020_")):
            print(f"{col.id:<45} {col.title}")


def search(collection: str, target_bbox: tuple | None = None) -> list:
    items = list(_client().search(collections=[collection], bbox=target_bbox or bbox(HALF_SIZE_KM + MARGIN_KM)).items())
    return sorted(items, key=lambda it: it.id)


def measure_coverage(href: str, src_bounds_fn) -> float:
    """Fracția validă din fereastră, citită la rezoluție mică (overview), ca să alegem produsele."""
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as ds:
        win = from_bounds(*src_bounds_fn(ds.crs), transform=ds.transform)
        full = win.width * win.height
        win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
        h, w = max(1, int(win.height // 32)), max(1, int(win.width // 32))
        mask = ds.read_masks(1, window=win, out_shape=(h, w))
        inside = (win.width * win.height) / full if full else 0.0
        return float(inside * (np.count_nonzero(mask) / mask.size))


def crop(href: str, out_path: Path, src_bounds_fn, step_m: float | None = None, resampling: str = "nearest") -> dict:
    """Decupează fereastra din COG și o scrie ca GeoTIFF, în CRS-ul nativ al produsului.

    `step_m`: rezoluția la care citim (None = nativă). Rasterio folosește automat overview-urile
    COG, deci la 4 m se transferă ~1/16 din date față de 1 m.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import Window, from_bounds

    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as ds:
        win = from_bounds(*src_bounds_fn(ds.crs), transform=ds.transform)
        win = win.intersection(Window(0, 0, ds.width, ds.height)).round_offsets().round_lengths()
        factor = max(1.0, (step_m or ds.res[0]) / ds.res[0])
        out_h, out_w = max(1, int(win.height / factor)), max(1, int(win.width / factor))
        data = ds.read(window=win, out_shape=(ds.count, out_h, out_w), resampling=getattr(Resampling, resampling))
        transform = ds.window_transform(win) @ rasterio.Affine.scale(win.width / out_w, win.height / out_h)
        profile = ds.profile.copy()
        profile.update(driver="GTiff", width=out_w, height=out_h, transform=transform, compress="deflate",
                       tiled=True, blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
        for k in ("photometric",):
            profile.pop(k, None)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Scriere atomică: fișier temporar unic + os.replace. O rulare întreruptă sau două rulări
        # în paralel nu lasă niciodată un GeoTIFF scris pe jumătate sub numele final.
        tmp = out_path.with_name(f".{out_path.stem}.{os.getpid()}.tmp.tif")
        try:
            with rasterio.open(tmp, "w", **profile) as dst:
                dst.write(data)
            os.replace(tmp, out_path)
        finally:
            tmp.unlink(missing_ok=True)
        return {"read_res_m": abs(transform.a), "shape": [out_h, out_w], "native_res_m": ds.res[0]}


def src_bounds_factory(margin_km: float = MARGIN_KM):
    """Funcție crs_sursă -> limitele ferestrei (cu margine) în acel CRS."""
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    local = CRS.from_string(local_proj4())
    bounds = grid_bounds(margin_m=margin_km * 1000)

    def fn(dst_crs):
        return transform_bounds(local, dst_crs, *bounds, densify_pts=21)

    return fn


def fetch_all(out: Path, hirise_step_m: float = 4.0, dry_run: bool = False, kinds: list[str] | None = None) -> list[Product]:
    src_bounds = src_bounds_factory()
    target = bbox(HALF_SIZE_KM)
    products: list[Product] = []
    for kind, spec in COLLECTIONS.items():
        if kinds and kind not in kinds:
            continue
        items = search(spec["collection"])
        print(f"\n== {kind}: {spec['collection']} -> {len(items)} item-uri peste zonă")
        if kind == "themis_ir":
            items = [it for it in items if it.id.endswith(("_nir", "_dir"))]

        # Alegerea: CTX -> cele mai bune `max_items` după acoperirea reală (citită la rezoluție mică).
        ranked = []
        for it in items:
            main_asset = next(iter(spec["assets"]))
            cov = None
            if "max_items" in spec and not dry_run:
                try:
                    cov = measure_coverage(it.assets[main_asset].href, src_bounds)
                except Exception as e:  # un produs stricat nu oprește tot pipeline-ul
                    print(f"   ! {it.id}: nu pot măsura acoperirea ({e})")
                    cov = 0.0
            ranked.append({"id": it.id, "bbox": it.bbox, "gsd": it.properties.get("gsd"), "coverage": cov, "item": it})
        ranked = rank_items(ranked, target)[: spec.get("max_items", len(ranked))]

        for r in ranked:
            it = r["item"]
            for asset, data_type in spec["assets"].items():
                if asset not in it.assets:
                    continue
                p = Product(kind=kind, item_id=it.id, asset=asset, data_type=data_type, mission=spec["mission"],
                            instrument=spec["instrument"], collection=spec["collection"], href=it.assets[asset].href,
                            gsd_m=it.properties.get("gsd"), license=it.properties.get("license"),
                            datetime=it.properties.get("datetime") and str(it.properties["datetime"]),
                            coverage=r["coverage"])
                p.file = f"{kind}/{it.id}__{asset}.tif"
                cov_txt = f", acoperire {r['coverage']:.0%}" if r["coverage"] is not None else ""
                print(f"   {it.id} [{asset}] gsd {p.gsd_m and round(p.gsd_m, 2)} m{cov_txt}")
                if not dry_run:
                    step = hirise_step_m if kind == "hirise_dtm" else None
                    try:
                        info = crop(p.href, out / p.file, src_bounds, step, spec["resampling"][asset])
                    except Exception as e:
                        print(f"   ! eșec la decupare: {e}")
                        continue
                    p.read_res_m = round(info["read_res_m"], 3)
                    p.extra = {"shape": info["shape"]}
                    print(f"     -> {p.file} {info['shape']} la {p.read_res_m} m")
                products.append(p)
    return products


def fetch_waypoints(out: Path, url: str = WAYPOINTS_URL, filename: str = WAYPOINTS_FILE) -> Path:
    """Descarcă un strat GeoJSON al hărții NASA (implicit pozițiile roverului, ~600 KB) în `out/filename`.

    Sursa e fișierul de date din spatele hărții oficiale NASA de localizare a roverului.
    User-Agent generic: nu trimitem nimic despre echipă sau utilizator.
    """
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "marswalk-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    data = json.loads(text)  # validăm înainte să scriem
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError(f"Răspuns neașteptat de la {url}")
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    atomic_write_text(path, text)
    print(f"\n== {data.get('name', filename)}: {len(data['features'])} puncte -> {path}")
    return path


def write_manifest(out: Path, products: list[Product], hirise_step_m: float) -> Path:
    """Scrie manifest.json. Produsele de alte tipuri decât cele aduse acum (rulare cu --only)
    se păstrează din manifestul vechi; ordinea e deterministă (tip, item, asset)."""
    path = out / "manifest.json"
    fresh_kinds = {p.kind for p in products}
    kept = []
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        kept = [q for q in old.get("products", []) if q["kind"] not in fresh_kinds]
    all_products = sorted(kept + [asdict(p) for p in products], key=lambda q: (q["kind"], q["item_id"], q["asset"]))
    manifest = {
        "site_id": "jezero",
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON},
        "bbox_lonlat": [round(v, 6) for v in bbox(HALF_SIZE_KM)],
        "margin_km": MARGIN_KM,
        "local_crs": local_proj4(),
        "grid": {"n": GRID_N, "cell_m": GRID_CELL_M, "bounds_local_m": grid_bounds()},
        "hirise_step_m": hirise_step_m,
        "stac_api": STAC_API,
        "products": all_products,
    }
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return path


def atomic_write_text(path: Path, text: str) -> None:
    """Scrie un fișier text atomic (temporar + os.replace), ca cititorii să nu vadă jumătăți."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--list-collections", action="store_true")
    p.add_argument("--collection", help="doar caută item-urile dintr-o colecție")
    p.add_argument("--dry-run", action="store_true", help="caută și afișează, fără să descarce")
    p.add_argument("--only", nargs="*", choices=[*COLLECTIONS, "waypoints"], help="doar anumite tipuri de produse")
    p.add_argument("--hirise-step", type=float, default=4.0, help="rezoluția de citire HiRISE în m (1 = nativ)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    print(f"centru {CENTER_LAT}°N {CENTER_LON}°E, bbox (lon_min, lat_min, lon_max, lat_max):",
          tuple(round(v, 4) for v in bbox()))
    if args.list_collections:
        list_collections()
    elif args.collection:
        for it in search(args.collection):
            print(it.id, [round(v, 3) for v in it.bbox], list(it.assets))
    else:
        rasters = [k for k in (args.only or COLLECTIONS) if k in COLLECTIONS]
        if rasters:
            products = fetch_all(args.out, args.hirise_step, args.dry_run, rasters)
            if not args.dry_run:
                print("\nmanifest:", write_manifest(args.out, products, args.hirise_step))
        if not args.dry_run and (not args.only or "waypoints" in args.only):
            fetch_waypoints(args.out)
            fetch_waypoints(args.out, HELI_URL, HELI_FILE)


if __name__ == "__main__":
    main()
