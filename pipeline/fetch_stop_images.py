"""Imaginile Perseverance de la fiecare oprire -> data/processed/jezero/png/stops/<target_id>.jpg.

Pentru fiecare țintă din meta.json:
  1. solul roverului cu waypoint-ul cel mai apropiat de țintă (M20_waypoints.json, NASA/JPL);
  2. imaginile brute ale acelui sol, din API-ul public Mars 2020 (mars.nasa.gov/rss/api, feed raw_images);
  3. alegerea (deterministă): Mastcam-Z stânga, culoare naturală (filtrul ZCAM_L0_RGB), cadru întreg,
     privind spre teren (−30° … −1° sub orizont), cât mai aproape de −10°; dacă nu există, Navcam stânga;
  4. imaginea „large” (1200 px) descărcată în data/raw/jezero/stops/ (ignorat de git), redusă la
     960 px lățime, JPEG ≤ 300 KB în data/processed/jezero/png/stops/;
  5. stops.json lângă imagini: sursa fiecăreia (imageid, sol, instrument, credit, link). build_layers.py
     îl citește și completează targets[].image = "/static/layers/stops/<id>.jpg" + image_source.

Rulare: .venv-pipeline/Scripts/python pipeline/fetch_stop_images.py   (cere Pillow și internet)
"""

import argparse
import io
import json
import math
import urllib.request
from pathlib import Path

import fetch_stac as fs
from build_layers import OUT, RAW, latlon_to_local, load_waypoints

API = "https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json&ver=1.2&num=100&page={page}&sol={sol}"
USER_AGENT = "Mozilla/5.0 (research client)"
STOPS_DIR = "stops"
MAX_BYTES = 300_000
WIDTH = 960
MAX_WAYPOINT_DIST_M = 150.0
EL_RANGE = (-30.0, -1.0)
EL_PREFERRED = -10.0


def nearest_sol(lat: float, lon: float, waypoints: list[dict]) -> tuple[int, float]:
    """(sol, distanța m) pentru waypoint-ul roverului cel mai apropiat de punct."""
    x, y = latlon_to_local(lat, lon)

    def dist(w):
        wx, wy = latlon_to_local(w["lat"], w["lon"])
        return math.hypot(wx - x, wy - y)

    best = min(waypoints, key=lambda w: (dist(w), w["sol"]))
    return int(best["sol"]), dist(best)


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def select_image(images: list[dict]) -> dict | None:
    """Imaginea pentru oprire, sau None. Deterministă: aceeași listă -> aceeași alegere."""
    def candidates(instrument: str, rgb_only: bool) -> list[dict]:
        out = []
        for im in images:
            cam, ext = im.get("camera", {}), im.get("extended", {})
            el = _num(ext.get("mastEl"))
            if cam.get("instrument") != instrument or el is None or not (EL_RANGE[0] <= el <= EL_RANGE[1]):
                continue
            if rgb_only and cam.get("filter_name") != "ZCAM_L0_RGB":
                continue
            if im.get("sample_type") != "Full" or not im.get("image_files", {}).get("large"):
                continue
            dims = [int(v) for v in str(ext.get("dimension", "(0,0)")).strip("()").split(",")]
            if dims[0] * dims[1] < 1000 * 1000:
                continue
            out.append((abs(el - EL_PREFERRED), -dims[0] * dims[1], im["imageid"], im))
        return [c[-1] for c in sorted(out, key=lambda c: c[:3])]

    for instrument, rgb in (("MCZ_LEFT", True), ("NAVCAM_LEFT", False)):
        found = candidates(instrument, rgb)
        if found:
            return found[0]
    return None


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def sol_images(sol: int, cache: Path) -> list[dict]:
    """Toate imaginile brute ale unui sol (paginat), cu cache local în data/raw."""
    path = cache / f"sol_{sol:04d}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    images, page = [], 0
    while True:
        batch = json.loads(_get(API.format(page=page, sol=sol))).get("images", [])
        images += batch
        if len(batch) < 100 or page > 30:
            break
        page += 1
    fs.atomic_write_text(path, json.dumps(images, ensure_ascii=False))
    return images


def to_jpeg(raw: bytes, max_bytes: int = MAX_BYTES, width: int = WIDTH) -> bytes:
    """Redimensionat la `width` px lățime, JPEG cu calitatea cea mai mare care încape în max_bytes."""
    from PIL import Image

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)
    for quality in (88, 84, 80, 75, 70, 65, 60):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue()
    raise ValueError("imaginea nu încape în limita de mărime")


def image_source(im: dict, sol: int, dist_m: float) -> dict:
    return {
        "imageid": im["imageid"], "sol": int(im["sol"]), "instrument": im["camera"]["instrument"],
        "filter": im["camera"].get("filter_name"), "credit": im.get("credit", "NASA/JPL-Caltech"),
        "date_taken_utc": im.get("date_taken_utc"), "link": im.get("link"), "url": im["image_files"]["large"],
        "mast_el_deg": round(float(im["extended"]["mastEl"]), 1), "mast_az_deg": round(float(im["extended"]["mastAz"]), 1),
        "rover_waypoint_sol": sol, "rover_to_target_m": round(dist_m),
    }


def fetch(site: Path = OUT, raw: Path = RAW) -> dict:
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    waypoints = load_waypoints(raw)
    cache = raw / STOPS_DIR
    cache.mkdir(parents=True, exist_ok=True)
    out_dir = site / "png" / STOPS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = {}
    for t in meta["targets"]:
        sol, dist = nearest_sol(t["lat"], t["lon"], waypoints)
        if dist > MAX_WAYPOINT_DIST_M:
            print(f"  {t['id']}: roverul n-a fost mai aproape de {dist:.0f} m, fără imagine")
            continue
        im = select_image(sol_images(sol, cache))
        if im is None:
            print(f"  {t['id']}: nicio imagine potrivită în solul {sol}")
            continue
        raw_path = cache / f"{im['imageid']}.jpg"
        if not raw_path.exists():
            raw_path.write_bytes(_get(im["image_files"]["large"]))
        jpg = to_jpeg(raw_path.read_bytes())
        tmp = out_dir / f".{t['id']}.jpg.tmp"
        tmp.write_bytes(jpg)
        tmp.replace(out_dir / f"{t['id']}.jpg")
        sources[t["id"]] = image_source(im, sol, dist)
        print(f"  {t['id']}: sol {sol} ({dist:.0f} m), {im['camera']['instrument']} {im['imageid']}, {len(jpg) // 1024} KB")
    fs.atomic_write_text(out_dir / "stops.json", json.dumps(sources, indent=2, ensure_ascii=False) + "\n")
    return sources


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--site", type=Path, default=OUT)
    p.add_argument("--raw", type=Path, default=RAW)
    a = p.parse_args()
    fetch(a.site, a.raw)
    print("Gata. Rulează apoi pipeline/build_layers.py ca targets[].image să intre în meta.json.")


if __name__ == "__main__":
    main()
