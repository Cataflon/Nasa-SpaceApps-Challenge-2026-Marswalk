"""Georeferențierea grilei Jezero -> data/processed/jezero/grid.json (cerere a rolului 4).

Rolul 4 și-a decupat singur relieful 3D (frontend/public/terrain/jezero.json) din mozaicul USGS
Mars 2020 CTX TRN, în proiecția lui nativă: echirectangulară cu lat_ts = 0. Grila noastră e
echirectangulară LOCALĂ, cu lat_ts = lat_0 = 18,44° (pixeli de 20 m adevărați pe sol în ambele
direcții). Centrul e același, dar pe est-vest un pixel de 20 m „proiectat” la ei are doar
20 · cos(18,44°) ≈ 18,97 m pe sol: grilele NU se suprapun celulă cu celulă.

grid.json conține:
  - `grid`: CRS-ul (proj4), transformarea afină, formula centrului de celulă, colțurile în lat/lon;
  - `elevation`: unitatea, datumul, NoData, corecția verticală pe rover;
  - `to_frontend_terrain` (dacă fișierul rolului 4 există): formula exactă (row, col) -> (row, col)
    la ei și comparația măsurată (decalaj rezidual, corelația pantelor, diferența de altitudine).

Fișierul rolului 4 e doar CITIT. Rulare: python pipeline/grid_alignment.py   (fără rasterio)
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np

import fetch_stac as fs
from build_layers import OUT, cell_to_latlon

FRONTEND_TERRAIN = fs.ROOT / "frontend" / "public" / "terrain" / "jezero.json"
GRID_VERSION = 1


def grid_info(meta: dict) -> dict:
    """Georeferențierea grilei noastre, din meta.json (fără să citească straturile)."""
    rows, cols = meta["shape"]
    cell = float(meta["cell_size_m"])
    half_x, half_y = cols * cell / 2, rows * cell / 2
    corners = {name: [round(v, 6) for v in cell_to_latlon(r, c, n=rows, cell_m=cell)]
               for name, (r, c) in {"nw": (0, 0), "ne": (0, cols - 1), "sw": (rows - 1, 0),
                                     "se": (rows - 1, cols - 1)}.items()}
    return {
        "crs_proj4": meta["crs"],
        "shape": [rows, cols],
        "cell_size_m": cell,
        # GDAL: x = x0 + col·dx, y = y0 + row·dy (colțul NV al celulei), metri față de centru.
        "geotransform": [-half_x, cell, 0.0, half_y, 0.0, -cell],
        "cell_center_m": "x = (col + 0.5) * cell - width/2 (east), y = height/2 - (row + 0.5) * cell (north)",
        "cell_center_latlon": "lat = lat0 + deg(y / R), lon = lon0 + deg(x / (R cos lat0)), R = 3396190 m",
        "center": meta["center"],
        "corner_cell_centers_latlon": corners,
        "row_axis": "south", "col_axis": "east",
    }


def elevation_info(meta: dict) -> dict:
    prov = meta.get("provenance", {})
    return {
        "file": meta["layers"]["elevation"]["file"], "unit": "m", "dtype": meta["layers"]["elevation"]["dtype"],
        "nodata": None,  # grila e completă (CTX acoperă tot pătratul); verificat în pipeline/tests
        "datum": prov.get("vertical_datum"),
        "rover_vertical_check": prov.get("rover_vertical_check"),
        "products": meta["layers"]["elevation"].get("product_id"),
    }


def to_eqc0(rows: np.ndarray, cols: np.ndarray, meta: dict, origin: list, resolution: list) -> tuple:
    """(row, col) la noi -> (row, col) fracționar într-o grilă echirectangulară cu lat_ts = 0.

    `origin` = colțul NV (x, y) în metri proiectați (x = R·lon, y = R·lat), `resolution` = (dx, dy < 0).
    Indicii întorși sunt pe centrul de pixel (0 = centrul primului pixel).
    """
    n_rows, n_cols = meta["shape"]
    cell = float(meta["cell_size_m"])
    lat0, lon0 = math.radians(meta["center"]["lat"]), math.radians(meta["center"]["lon"])
    r_m = fs.MARS_RADIUS_M
    x = (cols + 0.5) * cell - n_cols * cell / 2
    y = n_rows * cell / 2 - (rows + 0.5) * cell
    lon = lon0 + x / (r_m * math.cos(lat0))
    lat = lat0 + y / r_m
    return (r_m * lat - origin[1]) / resolution[1] - 0.5, (r_m * lon - origin[0]) / resolution[0] - 0.5


def _bilinear(img: np.ndarray, rr: np.ndarray, cc: np.ndarray) -> np.ndarray:
    h, w = img.shape
    r0, c0 = np.floor(rr).astype(int), np.floor(cc).astype(int)
    fr, fc = rr - r0, cc - c0
    ok = (r0 >= 0) & (c0 >= 0) & (r0 < h - 1) & (c0 < w - 1)
    r0, c0 = np.clip(r0, 0, h - 2), np.clip(c0, 0, w - 2)
    v = (img[r0, c0] * (1 - fr) * (1 - fc) + img[r0 + 1, c0] * fr * (1 - fc)
         + img[r0, c0 + 1] * (1 - fr) * fc + img[r0 + 1, c0 + 1] * fr * fc)
    return np.where(ok, v, np.nan)


def _slope_corr(ours: np.ndarray, theirs: np.ndarray) -> float:
    gy0, gx0 = np.gradient(ours)
    gy, gx = np.gradient(theirs)
    m = np.isfinite(gx) & np.isfinite(gy)
    return float(np.corrcoef(np.concatenate([gx0[m], gy0[m]]), np.concatenate([gx[m], gy[m]]))[0, 1])


def compare(ours: np.ndarray, theirs: np.ndarray, meta: dict, origin: list, resolution: list) -> dict:
    """Cât de bine se potrivesc cele două DTM-uri, cu transformarea exactă și cu un decalaj rezidual.

    Decalajul rezidual se caută pe corelația pantelor (gradienților), mult mai sensibilă la
    deplasări decât altitudinea: întâi din pixel în pixel (±4 rânduri, ±10 coloane), apoi la 0,25 px.
    """
    rows, cols = np.mgrid[0:ours.shape[0], 0:ours.shape[1]]
    tr, tc = to_eqc0(rows, cols, meta, origin, resolution)

    def at(dr: float, dc: float) -> np.ndarray:
        return _bilinear(theirs, tr + dr, tc + dc)

    def score(dr: float, dc: float) -> float:
        return _slope_corr(ours, at(dr, dc))

    coarse = max(((score(dr, dc), dr, dc) for dr in range(-4, 5) for dc in range(-10, 11)),
                 key=lambda s: (round(s[0], 9), -abs(s[1]) - abs(s[2])))
    steps = np.arange(-1.0, 1.01, 0.25)
    best = max(((score(coarse[1] + a, coarse[2] + b), coarse[1] + a, coarse[2] + b) for a in steps for b in steps),
               key=lambda s: (round(s[0], 9), -abs(s[1]) - abs(s[2])))
    d = ours - at(0.0, 0.0)
    m = np.isfinite(d)
    naive = _slope_corr(ours, theirs) if theirs.shape == ours.shape else None
    cell = float(meta["cell_size_m"])
    return {
        "covered_pct": round(100.0 * float(m.mean()), 1),
        "elevation_ours_minus_theirs_m": {"median": round(float(np.median(d[m])), 2),
                                          "mad": round(float(np.median(np.abs(d[m] - np.median(d[m])))), 2)},
        "slope_correlation": {"same_cells_assumed": None if naive is None else round(naive, 3),
                              "exact_transform": round(score(0.0, 0.0), 3),
                              "with_residual_shift": round(best[0], 3)},
        "residual_shift": {"their_rows": float(best[1]), "their_cols": float(best[2]),
                           "north_m": round(-best[1] * abs(resolution[1]), 1),
                           "east_m_ground": round(best[2] * resolution[0] * math.cos(math.radians(meta["center"]["lat"])), 1),
                           "note": "between two different DTM products (USGS CTX TRN mosaic vs our HiRISE/CTX "
                                   "controlled DTMs); not applied, reported for alignment"},
        "our_grid_in_their_pixels": {"cols_span": round(float(tc[0, -1] - tc[0, 0]) + 1, 1),
                                     "rows_span": round(float(tr[-1, 0] - tr[0, 0]) + 1, 1),
                                     "cell_m": cell},
    }


def frontend_block(meta: dict, ours: np.ndarray, path: Path) -> dict | None:
    if not path.exists():
        return None
    f = json.loads(path.read_text(encoding="utf-8"))
    theirs = np.asarray(f["elevation"], dtype=np.float64).reshape(f["rows"], f["cols"])
    origin, resolution = [float(v) for v in f["origin"]], [float(v) for v in f["resolution"]]
    tr, tc = to_eqc0(np.array([0, 0, ours.shape[0] - 1]), np.array([0, ours.shape[1] - 1, 0]), meta, origin, resolution)
    lat_ts = meta["center"]["lat"]
    return {
        "file": path.relative_to(fs.ROOT).as_posix(),
        "source": f.get("source"), "source_url": f.get("sourceUrl"),
        "their_crs": "equirectangular, Mars 2000 sphere R = 3396190 m, lat_ts = 0, lon_0 = 0 "
                     "(x = R·lon, y = R·lat, radians)",
        "their_origin_m": origin, "their_resolution_m": resolution,
        "formula": {
            "their_row": f"(R * lat - {origin[1]}) / {resolution[1]} - 0.5",
            "their_col": f"(R * lon - {origin[0]}) / {resolution[0]} - 0.5",
            "with": "lat, lon of our cell centre (grid.cell_center_latlon), in radians",
            "approx": f"their_row ≈ row + {round(float(tr[0]), 2)}; their_col ≈ 249.5 + (col - 249.5) / cos({lat_ts}°) "
                      f"+ {round(float(tc[0]) - (249.5 - 249.5 / math.cos(math.radians(lat_ts))), 2)}",
        },
        "corners_in_their_pixels": {"nw": [round(float(tr[0]), 2), round(float(tc[0]), 2)],
                                    "ne": [round(float(tr[1]), 2), round(float(tc[1]), 2)],
                                    "sw": [round(float(tr[2]), 2), round(float(tc[2]), 2)]},
        "measured": compare(ours, theirs, meta, origin, resolution),
    }


def build(site_dir: Path = OUT, frontend: Path = FRONTEND_TERRAIN) -> dict:
    meta = json.loads((site_dir / "meta.json").read_text(encoding="utf-8"))
    ours = np.load(site_dir / "elevation.npy").astype(np.float64)
    return {
        "version": GRID_VERSION,
        "site_id": meta["site_id"],
        "fingerprint": meta.get("fingerprint"),
        "grid": grid_info(meta),
        "elevation": elevation_info(meta),
        "to_frontend_terrain": frontend_block(meta, ours, frontend),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--site", type=Path, default=OUT)
    p.add_argument("--frontend", type=Path, default=FRONTEND_TERRAIN)
    a = p.parse_args()
    info = build(a.site, a.frontend)
    fs.atomic_write_text(a.site / "grid.json", json.dumps(info, indent=2, ensure_ascii=False) + "\n")
    m = (info["to_frontend_terrain"] or {}).get("measured")
    print(f"Scris {a.site / 'grid.json'}")
    if m:
        print(f"  relieful rolului 4: corelația pantelor {m['slope_correlation']}, "
              f"decalaj rezidual {m['residual_shift']['north_m']} m N / {m['residual_shift']['east_m_ground']} m E, "
              f"altitudine noi − ei {m['elevation_ours_minus_theirs_m']}")


if __name__ == "__main__":
    main()
