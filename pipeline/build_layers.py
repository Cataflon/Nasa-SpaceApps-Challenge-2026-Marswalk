"""Construiește straturile pe grila de 20 m din datele brute (data/raw/jezero -> data/processed/jezero).

Pași:
  1. Grila: 500×500 celule de 20 m în CRS-ul local (fetch_stac.local_proj4), cu scara reală la
     latitudinea zonei. Produsele USGS au paralela standard la ecuator, deci se reproiectează.
  2. Elevația la rezoluție fină (4 m = 5×5 pixeli pe celulă): CTX (~20 m) e baza și acoperă tot
     pătratul; DTM-urile HiRISE au prioritate unde există, după ce le corectăm decalajul vertical
     față de CTX (mediana diferenței) și le îmbinăm cu tranziție lină la margini (fără trepte false).
  3. Panta la rezoluția fină, apoi agregare la 20 m păstrând MAXIMUL din celulă (obstacolele mici
     nu dispar). Elevația la 20 m = media celor 5×5 pixeli.
  4. `unsafe` = pantă > 35° la rezoluția fină. FOM-ul HiRISE din STAC e o vizualizare RGB fără
     legendă publicată, deci nu îi interpretăm culorile; îl folosim doar ca mască de proveniență.
  5. Radiația: același model ca situl sintetic (doza RAD după altitudine), declarat presupunere.
     Terenul și mineralele: provizorii aici (din pantă), înlocuite de capitolul 5 (THEMIS, CRISM
     sau harta geologică USGS SIM 3464 în pipeline/manual_units.py).
  6. Habitatul pe cel mai plat teren de lângă locul de aterizare Perseverance; țintele reale,
     mutate pe cea mai apropiată celulă accesibilă din habitat (≤ 25°).
  7. Scrie .npy + meta.json (același format ca make_synthetic_site.py) + PNG-urile.

Rulare (mediul .venv-pipeline, după fetch_stac.py):
  .venv-pipeline/Scripts/python pipeline/build_layers.py
"""

import argparse
import json
import math
import os
import sys
import warnings
from pathlib import Path

import numpy as np

import fetch_stac as fs
from make_synthetic_site import LAYER_LABELS, reachable_from
from pngio import categorical, hillshade, ramp, write_png

ROOT = fs.ROOT
RAW = fs.DEFAULT_OUT
OUT = ROOT / "data" / "processed" / "jezero"

N = fs.GRID_N
CELL_M = fs.GRID_CELL_M
FINE = 5  # pixeli fini pe latura unei celule: 20 m / 5 = 4 m (= rezoluția de citire HiRISE)
FINE_M = CELL_M / FINE
MAX_SLOPE_DEG = 25.0
UNSAFE_SLOPE_DEG = 35.0  # ROL1: „unde nu există FOM, din pantă > 35°”
FEATHER_M = 100.0  # lățimea tranziției HiRISE -> CTX (presupunere)
DOSE_RATE_USV_H = 28.0  # RAD, doză echivalentă 0,67 mSv/zi (Hassler, SwRI 2013); = scenario.DOSE_RATE_USV_H

# Locul de aterizare Perseverance (Octavia E. Butler Landing): primul punct din waypoint-urile
# oficiale ale roverului (sol 13, fără deplasare). NASA/JPL, M20_waypoints.json
LANDING_LATLON = (18.44463, 77.45089)
HABITAT_SEARCH_CELLS = 15  # căutăm terenul cel mai plat pe o rază de 300 m
TARGET_SNAP_CELLS = 25  # o țintă se poate muta cel mult 500 m până la o celulă accesibilă

# Ținte reale (coordonate planetocentrice, longitudine est). Poziția = mediana pozițiilor roverului
# Perseverance din campania respectivă (`rover_sols`, din M20_waypoints.json), adică locul unde a
# lucrat efectiv; `lat`/`lon` sunt fallback-ul dacă fișierul de waypoint-uri lipsește.
# `name` și `note` apar în UI și pe Survival Guide, deci sunt în engleză (regula echipei).
TARGETS = [
    {"id": "clay_delta", "name": "Clay, delta front (Hawksbill Gap)", "kind": "clay",
     "lat": 18.4514, "lon": 77.4049, "rover_sols": (500, 599), "science_value": 10, "dwell_min": 30, "image": None,
     "note": "Clay-bearing mudstone at the base of the delta front, studied by Perseverance during the delta campaign"},
    {"id": "carbonate_rim", "name": "Carbonates, crater margin unit", "kind": "carbonate",
     "lat": 18.4826, "lon": 77.3648, "rover_sols": (800, 899), "science_value": 7, "dwell_min": 20, "image": None,
     "note": "Carbonate-bearing margin unit along the inner crater rim, explored by Perseverance"},
    {"id": "olivine_floor", "name": "Olivine, Séítah (crater floor)", "kind": "olivine",
     "lat": 18.4335, "lon": 77.4422, "rover_sols": (200, 299), "science_value": 4, "dwell_min": 15, "image": None,
     "note": "Olivine-rich cumulate (Séítah formation), sampled by Perseverance"},
]

# Hardware NASA și repere reale din pătrat: puncte de interes statice (POI), NU intră în rutare.
# `type`: recovery_target / landmark / historical_hardware / hazard_debris. `caution_radius_m` e
# doar pentru afișare (cerc de precauție pe hartă). `rover_sols`: poziția vine din waypoint-urile
# roverului (verificat); altfel `lat`/`lon` sunt aproximative (status "to verify").
ARTIFACTS = [
    {"id": "three_forks_depot", "name": "Three Forks Sample Depot (10 sample tubes)", "type": "recovery_target",
     "lat": 18.4530, "lon": 77.4084, "rover_sols": (652, 686), "caution_radius_m": 0,
     "note": "Ten titanium tubes with rock cores and atmosphere, left on the surface by Perseverance (Dec 2022 - Jan 2023) for Mars Sample Return."},
    {"id": "landing_site", "name": "Octavia E. Butler Landing (Perseverance touchdown)", "type": "landmark",
     "lat": 18.44463, "lon": 77.45089, "rover_sols": (13, 13), "caution_radius_m": 0,
     "note": "Where Perseverance touched down on 18 February 2021."},
    {"id": "descent_stage", "name": "Mars 2020 Descent Stage (sky crane) crash site", "type": "hazard_debris",
     "lat": 18.4510, "lon": 77.4460, "caution_radius_m": 150,
     "note": "Sharp metal debris and possible hydrazine residue: keep clear."},
    {"id": "backshell_parachute", "name": "Backshell and supersonic parachute", "type": "hazard_debris",
     "lat": 18.4700, "lon": 77.4500, "caution_radius_m": 100,
     "note": "Backshell and parachute on the surface: risk of snagging on cables and fabric."},
    {"id": "heat_shield", "name": "Mars 2020 heat shield", "type": "historical_hardware",
     "lat": 18.4267, "lon": 77.4697, "caution_radius_m": 50,
     "note": "Carbon-composite heat shield with ablative cork, ~1.5 km southeast of the landing site."},
    # Epava Ingenuity (zborul 72, Airfield Chi, 18,4973°N 77,3225°E) e la ~2 km VEST de pătrat, deci
    # pe hartă punem locul primului zbor (Wright Brothers Field), care e lângă locul de aterizare.
    {"id": "ingenuity_first_flight", "name": "Wright Brothers Field (Ingenuity's first flight)", "type": "historical_hardware",
     "lat": 18.44486, "lon": 77.45102, "heli_flight": 1, "caution_radius_m": 0,
     "note": "First powered, controlled flight on another planet (19 April 2021). After 72 flights, Ingenuity rests at "
             "Airfield Chi, about 2 km west of this map (last flight 18 January 2024)."},
]
ROVER_SOURCE = "NASA/JPL Perseverance localization waypoints (M20_waypoints.json)"
HELI_SOURCE = "NASA/JPL Ingenuity flight log (m20_heli_waypoints.json)"
APPROX_SOURCE = "approximate, to verify on the NASA location map"


# ---------------------------------------------------------------------------------------------
# Funcții pure (numpy), testate și în CI
# ---------------------------------------------------------------------------------------------


def latlon_to_local(lat: float, lon: float, lat0: float = fs.CENTER_LAT, lon0: float = fs.CENTER_LON) -> tuple[float, float]:
    """(x, y) în metri în CRS-ul local echirectangular (lat_ts = lat_0 = centrul)."""
    r = fs.MARS_RADIUS_M
    x = r * math.cos(math.radians(lat0)) * math.radians(lon - lon0)
    y = r * math.radians(lat - lat0)
    return x, y


def local_to_cell(x: float, y: float, n: int = N, cell_m: float = CELL_M) -> tuple[int, int]:
    """Celula (row, col) care conține punctul; row crește spre sud, col spre est."""
    half = n * cell_m / 2
    return int(math.floor((half - y) / cell_m)), int(math.floor((x + half) / cell_m))


def latlon_to_cell(lat: float, lon: float) -> tuple[int, int]:
    return local_to_cell(*latlon_to_local(lat, lon))


def cell_to_latlon(row: int, col: int, n: int = N, cell_m: float = CELL_M) -> tuple[float, float]:
    """Centrul celulei, în grade."""
    half = n * cell_m / 2
    x, y = (col + 0.5) * cell_m - half, half - (row + 0.5) * cell_m
    r = fs.MARS_RADIUS_M
    lat = fs.CENTER_LAT + math.degrees(y / r)
    lon = fs.CENTER_LON + math.degrees(x / (r * math.cos(math.radians(fs.CENTER_LAT))))
    return lat, lon


def blocks(a: np.ndarray, k: int) -> np.ndarray:
    """(H, W) -> (H/k, k, W/k, k), pentru agregări pe blocuri k×k."""
    h, w = a.shape
    return a.reshape(h // k, k, w // k, k)


def block_nanmax(a: np.ndarray, k: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # blocuri numai NaN -> NaN, e intenționat
        return np.nanmax(blocks(a, k), axis=(1, 3))


def block_nanmean(a: np.ndarray, k: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(blocks(a, k), axis=(1, 3))


def slope_deg(elev: np.ndarray, pixel_m: float) -> np.ndarray:
    """Panta în grade (diferențe centrale). NaN se propagă la vecini: fără pante false la margini."""
    gy, gx = np.gradient(elev.astype(np.float64), pixel_m)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


def feather(valid: np.ndarray, width_px: int) -> np.ndarray:
    """Pondere 0..1: crește liniar de la marginea zonei valide spre interior, pe `width_px` pixeli.

    Eroziuni succesive cu 4 vecini (fără scipy): ponderea = câte eroziuni a supraviețuit pixelul.
    Marginea grilei NU e margine de date: o fâșie HiRISE care atinge marginea pătratului rămâne
    cu pondere 1 acolo (altfel am pierde degeaba detaliul HiRISE pe margini).
    """
    w = np.zeros(valid.shape, dtype=np.float32)
    m = valid.copy()
    for _ in range(width_px):
        w += m
        e = m.copy()
        e[1:, :] &= m[:-1, :]
        e[:-1, :] &= m[1:, :]
        e[:, 1:] &= m[:, :-1]
        e[:, :-1] &= m[:, 1:]
        m = e
    return w / max(width_px, 1)


def vertical_bias(src: np.ndarray, ref: np.ndarray, min_overlap: int = 1000) -> float:
    """Decalajul vertical median src − ref pe zona comună (0 dacă suprapunerea e prea mică)."""
    both = np.isfinite(src) & np.isfinite(ref)
    if both.sum() < min_overlap:
        return 0.0
    return float(np.median(src[both] - ref[both]))


def weighted_median(values: list[float], weights: list[float]) -> float:
    """Mediana ponderată (deterministă: sortare stabilă după valoare)."""
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    total = sum(weights)
    acc = 0.0
    for i in order:
        acc += weights[i]
        if acc >= total / 2:
            return float(values[i])
    return float(values[order[-1]])


def blend_onto(base: np.ndarray, top: np.ndarray, width_px: int) -> np.ndarray:
    """`top` peste `base`, cu tranziție lină de `width_px` pixeli la marginea lui `top`."""
    valid = np.isfinite(top)
    w = feather(valid, width_px)
    out = base.copy()
    no_base = ~np.isfinite(base)
    out[valid] = np.where(no_base[valid], top[valid], w[valid] * top[valid] + (1 - w[valid]) * base[valid])
    return out


def flattest_near(slope: np.ndarray, center: tuple[int, int], radius: int, window: int = 3) -> tuple[int, int]:
    """Celula cu cea mai mică pantă maximă pe o fereastră (2·window+1)², lângă `center`.

    Tie-break determinist: distanța față de centru, apoi (row, col).
    """
    r0, c0 = center
    best = None
    rows, cols = slope.shape
    for r in range(max(window, r0 - radius), min(rows - window, r0 + radius + 1)):
        for c in range(max(window, c0 - radius), min(cols - window, c0 + radius + 1)):
            if (r - r0) ** 2 + (c - c0) ** 2 > radius ** 2:
                continue
            m = float(np.nanmax(slope[r - window : r + window + 1, c - window : c + window + 1]))
            key = (round(m, 3), (r - r0) ** 2 + (c - c0) ** 2, r, c)
            if best is None or key < best:
                best = key
    if best is None:
        raise ValueError("Nicio celulă în raza de căutare pentru habitat.")
    return best[2], best[3]


def snap_to_reachable(reach: np.ndarray, cell: tuple[int, int], radius: int) -> tuple[int, int] | None:
    """Cea mai apropiată celulă accesibilă (euclidian, tie-break row, col), sau None."""
    r0, c0 = cell
    rows, cols = reach.shape
    rr, cc = np.mgrid[max(0, r0 - radius) : min(rows, r0 + radius + 1), max(0, c0 - radius) : min(cols, c0 + radius + 1)]
    d2 = (rr - r0) ** 2 + (cc - c0) ** 2
    ok = reach[rr, cc] & (d2 <= radius ** 2)
    if not ok.any():
        return None
    cand = sorted(zip(d2[ok].tolist(), rr[ok].tolist(), cc[ok].tolist()))
    return cand[0][1], cand[0][2]


def rover_position(waypoints: list[dict], sols: tuple[int, int] | None) -> tuple[float, float] | None:
    """Mediana pozițiilor roverului în intervalul de soluri (inclusiv), sau None."""
    if not sols or not waypoints:
        return None
    pts = [w for w in waypoints if sols[0] <= w["sol"] <= sols[1]]
    if not pts:
        return None
    return float(np.median([w["lat"] for w in pts])), float(np.median([w["lon"] for w in pts]))


def rover_traverse(waypoints: list[dict], n: int = N) -> list[list[int]]:
    """Traseul roverului în celule, în ordinea solurilor, doar în pătrat, fără celule repetate consecutiv."""
    path: list[list[int]] = []
    for w in waypoints:
        r, c = latlon_to_cell(w["lat"], w["lon"])
        if 0 <= r < n and 0 <= c < n and (not path or path[-1] != [r, c]):
            path.append([r, c])
    return path


def vertical_offset_vs_rover(elevation: np.ndarray, waypoints: list[dict]) -> dict | None:
    """Decalajul DTM − altitudinea măsurată de rover (față de areoid), pe punctele din pătrat."""
    d = []
    for w in waypoints:
        r, c = latlon_to_cell(w["lat"], w["lon"])
        if 0 <= r < elevation.shape[0] and 0 <= c < elevation.shape[1] and w.get("elev_geoid") is not None:
            d.append(float(elevation[r, c]) - float(w["elev_geoid"]))
    if len(d) < 10:
        return None
    d = np.array(d)
    med = float(np.median(d))
    return {"n_points": int(d.size), "offset_m": round(med, 2),
            "mean_abs_dev_m": round(float(np.mean(np.abs(d - med))), 2),
            "p95_abs_dev_m": round(float(np.percentile(np.abs(d - med), 95)), 2)}


# Teren din THEMIS IR de noapte (proxy pentru inerția termică: roca rămâne caldă noaptea și apare
# luminoasă, nisipul fin se răcește repede și apare întunecat) + rugozitatea din DTM-ul HiRISE.
# Pragurile sunt presupuneri (percentile în sit), declarate în meta.json.
THEMIS_SAND_MAX = 0.25  # IR noapte normalizat sub acest prag + pantă mică -> nisip
THEMIS_ROCK_MIN = 0.75  # peste acest prag -> rocă la vedere
ROCK_SLOPE_DEG = 20.0  # pe pante mari, roca e la vedere indiferent de THEMIS
SAND_MAX_SLOPE_DEG = 12.0
BOULDER_ROUGHNESS_DEG = 12.0  # panta maximă la 4 m minus panta la 20 m: relief mărunt (bolovani)


def normalize_percentiles(a: np.ndarray, lo: float = 2, hi: float = 98) -> np.ndarray:
    v = a[np.isfinite(a)]
    if v.size == 0:
        return np.full(a.shape, 0.5, dtype=np.float32)
    p0, p1 = np.percentile(v, [lo, hi])
    return np.clip((np.nan_to_num(a, nan=float(np.median(v))) - p0) / max(p1 - p0, 1e-9), 0, 1).astype(np.float32)


def terrain_from_themis(nir: np.ndarray | None, slope: np.ndarray, elevation: np.ndarray) -> np.ndarray:
    """0 rocă, 1 regolit, 2 nisip, 3 bolovani. Fără THEMIS: doar din pantă și rugozitate."""
    roughness = slope - slope_deg(elevation, CELL_M)
    terrain = np.ones(slope.shape, dtype=np.uint8)  # regolit
    if nir is not None:
        n = normalize_percentiles(nir)
        terrain[(n < THEMIS_SAND_MAX) & (slope < SAND_MAX_SLOPE_DEG)] = 2
        terrain[n > THEMIS_ROCK_MIN] = 0
    terrain[slope > ROCK_SLOPE_DEG] = 0
    terrain[roughness > BOULDER_ROUGHNESS_DEG] = 3
    return terrain


def minerals_from_units(elevation: np.ndarray, waypoints: list[dict], habitat: tuple[int, int],
                        targets: list[dict], log=print) -> tuple[np.ndarray, list[dict]]:
    """Stratul `minerals` din unitățile din manual_units.py; țintele primesc clasa lor (5×5)."""
    import manual_units as mu

    minerals = np.zeros(elevation.shape, dtype=np.uint8)
    r0, c0 = habitat
    floor = float(np.median(elevation[max(0, r0 - 25) : r0 + 26, max(0, c0 - 25) : c0 + 26]))
    used = []
    for u in mu.UNITS:
        if u["method"] == "dem_delta":
            mask = mu.delta_mask(elevation, latlon_to_cell(*u["seed_latlon"]), floor, u["min_rise_m"], reachable_from)
        else:
            pts = [latlon_to_cell(w["lat"], w["lon"]) for w in waypoints if u["rover_sols"][0] <= w["sol"] <= u["rover_sols"][1]]
            pts = [(r, c) for r, c in pts if 0 <= r < N and 0 <= c < N]
            mask = mu.disk_mask(pts, u["buffer_m"] / CELL_M, elevation.shape) if pts else np.zeros(elevation.shape, bool)
        minerals[mask] = u["class"]
        used.append({"id": u["id"], "class": u["class"], "name": u["name"], "source": u["source"],
                     "cells_pct": round(float(mask.mean() * 100), 2)})
        log(f"Unitate {u['id']:<22} clasa {u['class']}: {mask.mean():.1%} din sit")
    kind_class = {"clay": 1, "carbonate": 2, "olivine": 3}
    for t in targets:
        cls = kind_class.get(t["kind"])
        if cls:
            minerals[max(0, t["row"] - 2) : t["row"] + 3, max(0, t["col"] - 2) : t["col"] + 3] = cls
    return minerals, used


def provisional_terrain(slope: np.ndarray) -> np.ndarray:
    """Teren provizoriu din pantă (capitolul 5 îl înlocuiește cu THEMIS / harta geologică)."""
    terrain = np.ones(slope.shape, dtype=np.uint8)  # regolit
    terrain[slope > 12] = 0  # rocă la vedere pe pante
    terrain[slope > 30] = 3  # blocuri sub pereți abrupți
    return terrain


def radiation_model(elev: np.ndarray) -> np.ndarray:
    """Doza RAD după altitudine: mai mare unde e mai puțină atmosferă deasupra (presupunere)."""
    return (DOSE_RATE_USV_H * np.exp((elev - float(np.nanmean(elev))) / 11000.0)).astype(np.float32)


# ---------------------------------------------------------------------------------------------
# Reproiectare (rasterio)
# ---------------------------------------------------------------------------------------------


def warp_to_grid(path: Path, shape: tuple[int, int], resampling: str = "bilinear", band: int = 1) -> np.ndarray:
    """Un GeoTIFF reproiectat pe grila locală (float32, NaN unde nu are date)."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject

    dst = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(path) as ds:
        src = ds.read(band, masked=True).astype(np.float32).filled(np.nan)
        reproject(src, dst, src_transform=ds.transform, src_crs=ds.crs, src_nodata=np.nan,
                  dst_transform=from_bounds(*fs.grid_bounds(), shape[1], shape[0]),
                  dst_crs=CRS.from_string(fs.local_proj4()), dst_nodata=np.nan,
                  resampling=getattr(Resampling, resampling))
    return dst


def load_manifest(raw: Path) -> dict:
    path = raw / "manifest.json"
    if not path.exists():
        raise SystemExit(f"Lipsește {path}. Rulează întâi: python pipeline/fetch_stac.py")
    return json.loads(path.read_text(encoding="utf-8"))


def _products(manifest: dict, kind: str, asset: str) -> list[dict]:
    return [p for p in manifest["products"] if p["kind"] == kind and p["asset"] == asset]


def hirise_priority(p: dict, has_fom: set[str]) -> tuple:
    """Ordinea HiRISE (prima = cea mai bună): cu FOM, producție nouă (U) față de veche (A), ID."""
    return (p["item_id"] not in has_fom, not p["item_id"].endswith("_U01"), p["item_id"])


def build_elevation(manifest: dict, raw: Path, log=print) -> dict:
    """Elevația fină (4 m), panta, sursa pe celulă și decalajele verticale aplicate."""
    fine_shape = (N * FINE, N * FINE)

    # CTX: baza. Ordinea după acoperirea măsurată la fetch, apoi ID; fiecare aliniat vertical la primul.
    ctx = sorted(_products(manifest, "ctx_dtm", "dtm"), key=lambda p: (-(p.get("coverage") or 0), p["item_id"]))
    if not ctx:
        raise SystemExit("Niciun DTM CTX în manifest: CTX e obligatoriu (acoperă tot pătratul).")
    base, used, biases = None, [], {}
    for p in ctx:
        e = warp_to_grid(raw / p["file"], fine_shape, "bilinear")
        if base is None:
            base = e
        else:
            b = vertical_bias(e, base)
            biases[p["item_id"]] = round(b, 2)
            e -= b
            base = np.where(np.isfinite(base), base, e)
        used.append(p["item_id"])
    log(f"CTX: {len(used)} DTM-uri, acoperire {np.isfinite(base).mean():.1%}, decalaje {biases}")

    # HiRISE: de la cel mai slab la cel mai bun, fiecare peste ce e dedesubt (cel mai bun câștigă).
    has_fom = {p["item_id"] for p in _products(manifest, "hirise_dtm", "fom")}
    hirise = sorted(_products(manifest, "hirise_dtm", "dtm"), key=lambda p: hirise_priority(p, has_fom))
    elev = base.copy()
    weights: list[tuple[float, float]] = []
    hirise_mask = np.zeros(fine_shape, dtype=bool)
    width = int(round(FEATHER_M / FINE_M))
    for p in reversed(hirise):
        h = warp_to_grid(raw / p["file"], fine_shape, "bilinear")
        b = vertical_bias(h, base)
        biases[p["item_id"]] = round(b, 2)
        h -= b
        elev = blend_onto(elev, h, width)
        hirise_mask |= np.isfinite(h)
        log(f"HiRISE {p['item_id']}: acoperire {np.isfinite(h).mean():.1%}, decalaj față de CTX {b:+.2f} m")
        weights.append((b, float(np.isfinite(h).mean())))

    # Referința verticală: HiRISE DTEEC („E” = elevații față de areoid) e cu ~20-40 m sub CTX-ul USGS
    # (altă referință). Mutăm tot rezultatul pe areoid, ca altitudinile să se potrivească cu valorile
    # publicate pentru Jezero: mediana decalajelor HiRISE, ponderată cu acoperirea.
    datum_shift = weighted_median([b for b, _ in weights], [w for _, w in weights]) if weights else 0.0
    elev = elev + datum_shift
    log(f"Referință verticală: areoid (HiRISE), deplasare {datum_shift:+.2f} m față de CTX")

    return {"elev_fine": elev, "hirise_fine": hirise_mask, "biases_m": biases, "datum_shift_m": round(datum_shift, 2),
            "ctx_ids": used, "hirise_ids": [p["item_id"] for p in hirise], "has_fom": sorted(has_fom)}


def build_ortho(manifest: dict, raw: Path) -> np.ndarray:
    """Imaginea de fundal 500×500, 0..1: ortoimaginile HiRISE peste CTX, normalizate pe percentile."""
    def norm(a):
        v = a[np.isfinite(a)]
        if v.size == 0:
            return a
        lo, hi = np.percentile(v, [1, 99])
        return np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)

    img = np.full((N, N), np.nan, dtype=np.float32)
    for p in sorted(_products(manifest, "ctx_dtm", "orthoimage"), key=lambda p: (-(p.get("coverage") or 0), p["item_id"])):
        o = norm(warp_to_grid(raw / p["file"], (N, N), "average"))
        img = np.where(np.isfinite(img), img, o)
    for p in sorted(_products(manifest, "hirise_dtm", "ortho_0"), key=lambda p: p["item_id"]):
        o = norm(warp_to_grid(raw / p["file"], (N, N), "average"))
        img = np.where(np.isfinite(o), o, img)
    return np.nan_to_num(img, nan=0.5)


# ---------------------------------------------------------------------------------------------
# Construcția sitului
# ---------------------------------------------------------------------------------------------


def load_waypoints(raw: Path = RAW) -> list[dict]:
    """Pozițiile roverului Perseverance (sol, lat, lon, elev_geoid), ordonate după sol; [] dacă lipsesc."""
    path = raw / fs.WAYPOINTS_FILE
    if not path.exists():
        return []
    feats = json.loads(path.read_text(encoding="utf-8"))["features"]
    pts = [{"sol": int(f["properties"]["sol"]), "lat": float(f["properties"]["lat"]), "lon": float(f["properties"]["lon"]),
            "elev_geoid": f["properties"].get("elev_geoid"), "i": i} for i, f in enumerate(feats)]
    return sorted(pts, key=lambda w: (w["sol"], w["i"]))


def load_heli(raw: Path = RAW) -> dict[int, tuple[float, float]]:
    """Zborurile Ingenuity: număr zbor -> (lat, lon) al aterizării; {} dacă fișierul lipsește."""
    path = raw / fs.HELI_FILE
    if not path.exists():
        return {}
    feats = json.loads(path.read_text(encoding="utf-8"))["features"]
    return {int(f["properties"]["Flight"]): (float(f["properties"]["Lat"]), float(f["properties"]["Lon"])) for f in feats}


def locate(item: dict, waypoints: list[dict], heli: dict | None = None) -> tuple[float, float, str]:
    """(lat, lon, sursa): din jurnalul Ingenuity sau din pozițiile roverului, altfel fallback."""
    if item.get("heli_flight") is not None and heli and item["heli_flight"] in heli:
        lat, lon = heli[item["heli_flight"]]
        return lat, lon, f"{HELI_SOURCE}, flight {item['heli_flight']}"
    pos = rover_position(waypoints, item.get("rover_sols"))
    if pos:
        a, b = item["rover_sols"]
        return pos[0], pos[1], f"{ROVER_SOURCE}, sols {a}-{b}" if a != b else f"{ROVER_SOURCE}, sol {a}"
    return item["lat"], item["lon"], APPROX_SOURCE


def place_artifacts(waypoints: list[dict], log=print, heli: dict | None = None) -> list[dict]:
    """Hardware-ul NASA din pătrat, ca POI (row/col + lat/lon + sursă). Cele din afara pătratului se sar."""
    out = []
    for a in ARTIFACTS:
        lat, lon, source = locate(a, waypoints, heli)
        r, c = latlon_to_cell(lat, lon)
        if not (0 <= r < N and 0 <= c < N):
            log(f"Artefact {a['id']}: în afara pătratului, sărit")
            continue
        out.append({"id": a["id"], "name": a["name"], "type": a["type"], "row": r, "col": c,
                    "lat": round(lat, 5), "lon": round(lon, 5), "caution_radius_m": a["caution_radius_m"],
                    "note": a["note"], "source": source,
                    "status": "verified" if source.startswith((ROVER_SOURCE, HELI_SOURCE)) else "to verify"})
        log(f"Artefact {a['id']:<20} ({r}, {c}) {out[-1]['status']}")
    return out


def place_sites(slope: np.ndarray, unsafe: np.ndarray, waypoints: list[dict] | None = None,
                log=print) -> tuple[tuple[int, int], list[dict]]:
    waypoints = waypoints or []
    habitat = flattest_near(slope, latlon_to_cell(*LANDING_LATLON), HABITAT_SEARCH_CELLS)
    walk = (slope <= MAX_SLOPE_DEG) & ~unsafe
    reach = reachable_from(walk, habitat)
    log(f"Habitat {habitat}: pantă {slope[habitat]:.1f}°, accesibil {reach.mean():.1%} din sit")

    targets = []
    for t in TARGETS:
        t_lat, t_lon, source = locate(t, waypoints)
        want = latlon_to_cell(t_lat, t_lon)
        if not (0 <= want[0] < N and 0 <= want[1] < N):
            raise SystemExit(f"Ținta {t['id']} ({t_lat}, {t_lon}) e în afara pătratului de 10×10 km.")
        got = snap_to_reachable(reach, want, TARGET_SNAP_CELLS)
        if got is None:
            raise SystemExit(f"Ținta {t['id']}: nicio celulă accesibilă pe o rază de {TARGET_SNAP_CELLS * CELL_M:.0f} m.")
        moved = math.hypot(got[0] - want[0], got[1] - want[1]) * CELL_M
        lat, lon = cell_to_latlon(*got)
        log(f"Țintă {t['id']:<14} {want} -> {got} (mutată {moved:.0f} m), pantă {slope[got]:.1f}°")
        targets.append({"id": t["id"], "name": t["name"], "kind": t["kind"], "row": int(got[0]), "col": int(got[1]),
                        "science_value": t["science_value"], "dwell_min": t["dwell_min"], "image": t["image"],
                        "lat": round(lat, 5), "lon": round(lon, 5), "snapped_m": round(moved),
                        "note": t["note"], "source": source})
    return habitat, targets


def layer_labels(manifest: dict, elev_info: dict, themis: bool = False, units: list[dict] | None = None) -> dict:
    """Etichetele de proveniență pentru fiecare strat (misiune, instrument, produse)."""
    dtm_ids = elev_info["hirise_ids"] + elev_info["ctx_ids"]
    topo = {"data_type": "topographic", "mission": "MRO", "instrument": "HiRISE + CTX", "source": "nasa",
            "product_id": ", ".join(dtm_ids)}
    themis_ids = ", ".join(p["item_id"] for p in manifest["products"] if p["kind"] == "themis_ir")
    terrain = ({"data_type": "thermal", "mission": "Mars Odyssey + MRO", "instrument": "THEMIS night IR + HiRISE roughness",
                "source": "nasa", "product_id": themis_ids,
                "derived": "classes from thermal-inertia proxy and DTM roughness; thresholds are assumptions"}
               if themis else
               {"data_type": "thermal", "mission": "MRO", "instrument": "HiRISE slope and roughness (no THEMIS)",
                "source": "assumption"})
    minerals = {"data_type": "spectral", "mission": "Mars 2020 Perseverance + MRO",
                "instrument": "rover-confirmed units (PIXL/SHERLOC) + delta outline from HiRISE/CTX DTM",
                "source": "assumption",
                "derived": "approximate unit outlines; CRISM not available in USGS STAC",
                "units": units or []}
    # Textele apar în UI (popup-ul de la click pe hartă), deci sunt în engleză.
    return {
        "elevation": {**topo, "analog_of": None},
        "slope": {**topo, "derived": f"max slope of {FINE_M:.0f} m pixels"},
        "terrain": terrain,
        "minerals": minerals,
        "radiation": {"data_type": "radiation", "mission": "MSL Curiosity", "instrument": "RAD (altitude model)",
                      "source": "assumption"},
        "unsafe": {**topo, "derived": f"slope > {UNSAFE_SLOPE_DEG:.0f}° at {FINE_M:.0f} m (FOM legend not published)"},
    }


def build(raw: Path = RAW, log=print) -> tuple[dict[str, np.ndarray], dict]:
    manifest = load_manifest(raw)
    info = build_elevation(manifest, raw, log)
    elev_fine = info["elev_fine"]
    slope_fine = slope_deg(elev_fine, FINE_M)

    elevation = block_nanmean(elev_fine, FINE)
    slope = block_nanmax(slope_fine, FINE)
    if np.isnan(elevation).any() or np.isnan(slope).any():
        # nu ar trebui (CTX acoperă tot), dar nu lăsăm NaN în straturi: costmap-ul ar strica traseele
        fallback = slope_deg(np.nan_to_num(elevation, nan=float(np.nanmean(elevation))), CELL_M)
        slope = np.where(np.isnan(slope), fallback, slope)
        elevation = np.nan_to_num(elevation, nan=float(np.nanmean(elevation)))
    unsafe = block_nanmax(np.where(np.isfinite(slope_fine), slope_fine, 0), FINE) > UNSAFE_SLOPE_DEG

    # Calibrarea verticală pe adevărul de la sol: altitudinile măsurate de Perseverance (față de
    # areoid) în punctele lui de localizare. Scădem decalajul median (panta nu se schimbă).
    waypoints = load_waypoints(raw)
    rover_check = vertical_offset_vs_rover(elevation, waypoints)
    if rover_check:
        elevation = elevation - rover_check["offset_m"]
        after = vertical_offset_vs_rover(elevation, waypoints)
        rover_check = {**after, "applied_shift_m": -rover_check["offset_m"]}
        log(f"Calibrare pe rover: {after['n_points']} puncte, decalaj corectat {rover_check['applied_shift_m']:+.2f} m, "
            f"abatere medie rămasă {after['mean_abs_dev_m']} m")

    layers = {
        "elevation": elevation.astype(np.float32),
        "slope": slope.astype(np.float32),
        "terrain": provisional_terrain(slope),
        "minerals": np.zeros((N, N), dtype=np.uint8),
        "radiation": radiation_model(elevation),
        "unsafe": unsafe,
    }
    habitat, targets = place_sites(layers["slope"], unsafe, waypoints, log)

    # Capitolul 5: terenul din THEMIS IR de noapte + rugozitate, mineralele din unitățile ancorate.
    nir_products = [p for p in manifest["products"] if p["kind"] == "themis_ir" and p["item_id"].endswith("_nir")]
    nir = warp_to_grid(raw / nir_products[0]["file"], (N, N), "bilinear") if nir_products else None
    layers["terrain"] = terrain_from_themis(nir, layers["slope"], layers["elevation"])
    layers["minerals"], units = minerals_from_units(layers["elevation"], waypoints, habitat, targets, log)
    for k, name in enumerate(("bedrock", "regolith", "sand", "boulders")):
        log(f"Teren {name:<9} {np.mean(layers['terrain'] == k):.1%}")
    artifacts = place_artifacts(waypoints, log, load_heli(raw))
    traverse = rover_traverse(waypoints)
    hirise_cells = block_nanmean(info["hirise_fine"].astype(np.float32), FINE)

    contract = json.loads((ROOT / "shared" / "contracts" / "meta.json").read_text(encoding="utf-8"))
    labels = layer_labels(manifest, info, themis=bool(nir_products), units=units)
    meta = {
        **contract,
        "site_id": "jezero",
        "name": "Jezero crater, delta front (Perseverance landing site)",
        "source": "nasa",
        "crs": fs.local_proj4(),
        "center": {"lat": fs.CENTER_LAT, "lon": fs.CENTER_LON},
        "habitat": {"row": int(habitat[0]), "col": int(habitat[1])},
        "targets": targets,
        "artifacts": artifacts,
        "rover_traverse": {
            "name": "Perseverance traverse (inside this map)",
            "source": f"{ROVER_SOURCE}: {fs.WAYPOINTS_URL}",
            "sols": [min(w["sol"] for w in waypoints), max(w["sol"] for w in waypoints)] if waypoints else None,
            "path": traverse,
        } if traverse else None,
        "layers": {name: {**spec, **{k: v for k, v in labels[name].items() if v is not None}}
                   for name, spec in contract["layers"].items()},
        "provenance": {
            "stac_api": manifest["stac_api"],
            "hirise_dtms": info["hirise_ids"],
            "hirise_with_fom": info["has_fom"],
            "ctx_dtms": info["ctx_ids"],
            "themis": [p["item_id"] for p in manifest["products"] if p["kind"] == "themis_ir"],
            "vertical_bias_m": info["biases_m"],
            "vertical_datum": f"areoid (HiRISE DTEEC); CTX shifted by {info['datum_shift_m']:+.2f} m",
            "rover_vertical_check": rover_check,
            "hirise_coverage_pct": round(float(hirise_cells.mean() * 100), 1),
            "fine_resolution_m": FINE_M,
            "license": "CC0-1.0 (USGS Astrogeology ARD)",
        },
        "fingerprint": {"forbidden_pct": round(float((layers["slope"] > MAX_SLOPE_DEG).mean() * 100), 2),
                        "unsafe_pct": round(float(unsafe.mean() * 100), 2),
                        "elevation_mean_m": round(float(elevation.mean()), 1)},
    }
    meta["_ortho"] = build_ortho(manifest, raw)  # doar pentru PNG, nu se scrie în meta.json
    meta["_hirise_cells"] = hirise_cells
    return layers, meta


def write(layers: dict[str, np.ndarray], meta: dict, out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "png").mkdir(exist_ok=True)
    ortho = meta.pop("_ortho")
    meta.pop("_hirise_cells", None)
    for name, grid in layers.items():
        # Scriere atomică: backendul care pornește în timpul build-ului nu citește un .npy pe jumătate.
        tmp = out / f".{name}.{os.getpid()}.tmp.npy"
        try:
            np.save(tmp, grid)
            os.replace(tmp, out / f"{name}.npy")
        finally:
            tmp.unlink(missing_ok=True)
    fs.atomic_write_text(out / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

    elev, slope = layers["elevation"], layers["slope"]
    shade = hillshade(elev, CELL_M)
    # Fundalul: ortoimaginea HiRISE/CTX, ușor colorată în tonuri de Marte și umbrită cu reliefului.
    tint = ramp(elev, [(0, (150, 95, 65)), (1, (225, 180, 140))]).astype(np.float32) / 255
    base = (0.75 * ortho + 0.25 * shade)[..., None] * (0.55 + 0.45 * tint)
    write_png(out / "png" / "elevation.png", np.clip(base * 255 * 1.25, 0, 255).astype(np.uint8))
    write_png(out / "png" / "slope.png", ramp(slope, [(0, (40, 160, 90)), (0.5, (240, 200, 60)), (1, (200, 40, 40))], 0, 35))
    write_png(out / "png" / "terrain.png", categorical(layers["terrain"], {
        0: (120, 110, 100, 160), 1: (190, 140, 100, 0), 2: (235, 200, 120, 160), 3: (80, 60, 60, 200)}))
    write_png(out / "png" / "minerals.png", categorical(layers["minerals"], {
        1: (60, 170, 200, 190), 2: (230, 230, 240, 190), 3: (110, 170, 60, 190)}))
    write_png(out / "png" / "radiation.png", ramp(layers["radiation"], [(0, (40, 40, 120)), (1, (240, 220, 60))]))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, default=RAW)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()

    layers, meta = build(args.raw)
    write(layers, meta, args.out)
    fp = meta["fingerprint"]
    print(f"\nSit Jezero scris în {args.out}")
    print(f"  elevație medie {fp['elevation_mean_m']} m, interzis (>25°) {fp['forbidden_pct']}%, unsafe {fp['unsafe_pct']}%,"
          f" HiRISE pe {meta['provenance']['hirise_coverage_pct']}% din celule")


if __name__ == "__main__":
    main()
