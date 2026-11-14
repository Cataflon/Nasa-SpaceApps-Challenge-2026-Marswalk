"""Situl sintetic: un fund de crater cu o deltă în NV, cratere mici, câmpuri de bolovani și dune.

Produce exact formatul pe care îl va produce și pipeline-ul real (vezi shared/contracts/meta.json),
ca echipa să poată lucra până sunt gata datele NASA.

Rulare (din rădăcina repo-ului):  python pipeline/make_synthetic_site.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from pngio import categorical, hillshade, ramp, write_png

ROOT = Path(__file__).resolve().parents[1]
N = 500
CELL_M = 20.0
MAX_SLOPE_DEG = 25.0

HABITAT = (300, 200)
TARGETS = [
    {"id": "clay_delta", "name": "Argilă, frontul deltei", "kind": "clay", "row": 180, "col": 140, "science_value": 10, "dwell_min": 30, "image": None},
    {"id": "carbonate_rim", "name": "Carbonați, marginea", "kind": "carbonate", "row": 120, "col": 260, "science_value": 7, "dwell_min": 20, "image": None},
    {"id": "olivine_floor", "name": "Olivină, fundul craterului", "kind": "olivine", "row": 340, "col": 330, "science_value": 4, "dwell_min": 15, "image": None},
]
DELTA_APEX_M = (1200.0, 0.0)  # (y, x)
DELTA_RADIUS_M = 3600.0


def smooth_noise(rng: np.random.Generator, beta: float = 3.0) -> np.ndarray:
    """Zgomot 1/f^beta, normalizat la [-1, 1]."""
    white = rng.standard_normal((N, N))
    fy = np.fft.fftfreq(N)[:, None]
    fx = np.fft.fftfreq(N)[None, :]
    f = np.hypot(fy, fx)
    f[0, 0] = 1.0
    field = np.real(np.fft.ifft2(np.fft.fft2(white) / f ** (beta / 2)))
    return field / np.abs(field).max()


def build(seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:N, 0:N].astype(np.float64) * CELL_M

    # Fundul craterului, ușor înclinat spre SE, cu ondulații.
    elev = -2540.0 - 0.003 * (x + y - 10000) + 6.0 * smooth_noise(rng, 3.2)

    # Delta: un evantai din NV cu un front abrupt. Lățimea frontului variază cu unghiul,
    # deci frontul are porțiuni de netrecut (>25°) și rampe pe unde se poate urca.
    dy, dx = y - DELTA_APEX_M[0], x - DELTA_APEX_M[1]
    r = np.hypot(dy, dx)
    theta = np.arctan2(dy, dx)
    front_width = 35.0 + 140.0 * (0.5 + 0.5 * np.sin(5 * theta + 0.7))
    delta_mask = 1.0 / (1.0 + np.exp(-(DELTA_RADIUS_M - r) / front_width))
    elev += delta_mask * (55.0 + 20.0 * np.clip(1 - r / DELTA_RADIUS_M, 0, 1))

    # Cratere mici, departe de habitat și de ținte.
    keep_clear = [HABITAT] + [(t["row"], t["col"]) for t in TARGETS]
    craters = []
    while len(craters) < 14:
        cy, cx = rng.uniform(300, 9700, 2)
        radius = rng.uniform(60, 350)
        if all(np.hypot(cy - rr * CELL_M, cx - cc * CELL_M) > radius + 400 for rr, cc in keep_clear):
            craters.append((cy, cx, radius))
    rim_ring = np.zeros((N, N), dtype=bool)
    for cy, cx, radius in craters:
        d = np.hypot(y - cy, x - cx) / radius
        depth, rim = 0.2 * 2 * radius, 0.04 * 2 * radius
        bowl = np.where(d < 1, -depth * (1 - d**2) + rim, rim * np.exp(-(((d - 1) / 0.35) ** 2)))
        elev += bowl
        rim_ring |= (d > 0.8) & (d < 1.5)

    # Pad nivelat pentru habitat.
    hr, hc = HABITAT
    pad = np.hypot(y - hr * CELL_M, x - hc * CELL_M) < 120
    elev[pad] = elev[hr, hc]

    gy, gx = np.gradient(elev, CELL_M)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)

    # Teren: 0 rocă, 1 regolit, 2 nisip, 3 bolovani.
    n_terrain = smooth_noise(rng, 2.5)
    terrain = np.ones((N, N), dtype=np.uint8)
    low = elev < np.percentile(elev, 35)
    terrain[low & (n_terrain > 0.15)] = 2
    terrain[(slope > 12) | ((delta_mask > 0.2) & (delta_mask < 0.8))] = 0
    terrain[rim_ring & (n_terrain < 0.3)] = 3
    terrain[(n_terrain < -0.55) & ~pad] = 3

    # Minerale: 0 nimic, 1 argilă, 2 carbonat, 3 olivină.
    n_min = smooth_noise(rng, 2.0)
    minerals = np.zeros((N, N), dtype=np.uint8)
    front_band = np.abs(r - DELTA_RADIUS_M) < 250
    minerals[front_band & (n_min > -0.2)] = 1
    for t, cls in ((TARGETS[1], 2), (TARGETS[2], 3)):
        d = np.hypot(y - t["row"] * CELL_M, x - t["col"] * CELL_M)
        minerals[(d < 700) & (n_min + (1 - d / 700) > 0.6)] = cls
    for t, cls in zip(TARGETS, (1, 2, 3)):
        minerals[t["row"] - 2 : t["row"] + 3, t["col"] - 2 : t["col"] + 3] = cls

    # Radiație la suprafață (µSv/h): mai mică la altitudine joasă (mai multă atmosferă deasupra).
    # Ordinul de mărime ~10 µSv/h e cel raportat de Curiosity RAD; variația e o presupunere.
    radiation = (10.0 * np.exp((elev - elev.mean()) / 11000.0) + 0.2 * smooth_noise(rng, 3.0)).astype(np.float32)

    unsafe = slope > 35.0  # înlocuitor pentru masca FOM din datele reale

    return {
        "elevation": elev.astype(np.float32),
        "slope": slope,
        "terrain": terrain,
        "minerals": minerals,
        "radiation": radiation,
        "unsafe": unsafe,
    }


def write(layers: dict[str, np.ndarray], out: Path, seed: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "png").mkdir(exist_ok=True)
    for name, grid in layers.items():
        np.save(out / f"{name}.npy", grid)

    contract = json.loads((ROOT / "shared" / "contracts" / "meta.json").read_text(encoding="utf-8"))
    meta = {**contract, "source": "synthetic", "seed": seed, "targets": TARGETS,
            "habitat": {"row": HABITAT[0], "col": HABITAT[1]}}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    elev, slope = layers["elevation"], layers["slope"]
    shade = hillshade(elev, CELL_M)
    tint = ramp(elev, [(0, (90, 55, 40)), (0.5, (170, 105, 70)), (1, (230, 190, 150))]).astype(np.float32)
    write_png(out / "png" / "elevation.png", (tint * (0.35 + 0.65 * shade[..., None])).astype(np.uint8))
    write_png(out / "png" / "slope.png", ramp(slope, [(0, (40, 160, 90)), (0.5, (240, 200, 60)), (1, (200, 40, 40))], 0, 35))
    write_png(out / "png" / "terrain.png", categorical(layers["terrain"], {
        0: (120, 110, 100, 160), 1: (190, 140, 100, 0), 2: (235, 200, 120, 160), 3: (80, 60, 60, 200)}))
    write_png(out / "png" / "minerals.png", categorical(layers["minerals"], {
        1: (60, 170, 200, 190), 2: (230, 230, 240, 190), 3: (110, 170, 60, 190)}))
    write_png(out / "png" / "radiation.png", ramp(layers["radiation"], [(0, (40, 40, 120)), (1, (240, 220, 60))]))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows (cp1252) nu are diacritice
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=ROOT / "data" / "synthetic")
    args = p.parse_args()

    layers = build(args.seed)
    write(layers, args.out, args.seed)

    slope = layers["slope"]
    print(f"Sit sintetic scris în {args.out}")
    print(f"  pantă: medie {slope.mean():.1f}°, max {slope.max():.1f}°, interzis (>{MAX_SLOPE_DEG:.0f}°): {(slope > MAX_SLOPE_DEG).mean():.1%}")
    for name, (r, c) in [("habitat", HABITAT)] + [(t["id"], (t["row"], t["col"])) for t in TARGETS]:
        ok = "ok" if slope[r, c] <= MAX_SLOPE_DEG else "PREA ABRUPT"
        print(f"  {name:<14} ({r},{c}): pantă {slope[r, c]:.1f}° {ok}")


if __name__ == "__main__":
    main()
