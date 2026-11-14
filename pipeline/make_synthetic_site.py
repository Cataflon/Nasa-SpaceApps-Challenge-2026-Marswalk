"""Situl sintetic: un fund de crater cu o deltă în NV, cratere mici, câmpuri de bolovani și dune.

Produce exact formatul pe care îl va produce și pipeline-ul real (vezi shared/contracts/meta.json),
ca echipa să poată lucra până sunt gata datele NASA.

Rulare (din rădăcina repo-ului):  python pipeline/make_synthetic_site.py
Verificare că situl de pe disc e la zi (cod de ieșire 1 dacă nu):  python pipeline/make_synthetic_site.py --check

data/synthetic/ e în .gitignore, deci fiecare își generează situl local. Ca să nu lucreze
oameni diferiți pe versiuni diferite, meta.json are `generator_version`; `--check` o compară
cu versiunea din cod. Dacă schimbi geometria sitului, crești GENERATOR_VERSION.
"""

import argparse
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np

from pngio import categorical, hillshade, ramp, write_png

ROOT = Path(__file__).resolve().parents[1]
N = 500
CELL_M = 20.0
MAX_SLOPE_DEG = 25.0
UNSAFE_SLOPE_DEG = 35.0  # înlocuitor pentru FOM-ul HiRISE
# v1: schelet inițial. v2: front de deltă abrupt (pereți de netrecut + rampe), etichete pe straturi.
# v3: radiația în doză echivalentă RAD (~26,7 µSv/h în loc de ~10).
# v4: textele vizibile în engleză (numele țintelor și sitului, etichetele straturilor).
# v5: `artifacts` (hardware NASA ca POI) și `rover_traverse` (None pe situl sintetic).
# v6: Ingenuity = Wright Brothers Field (primul zbor); epava e în afara hărții Jezero.
GENERATOR_VERSION = 6
# Doza echivalentă la suprafață: RAD 0,64 mSv/zi = 26,7 µSv/h (Hassler et al. 2014, Science).
# Aceeași valoare ca scenario.DOSE_RATE_USV_H (backend/app/live/scenario.py).
DOSE_RATE_USV_H = 26.7
DEFAULT_OUT = ROOT / "data" / "synthetic"

# Etichetele fiecărui strat: ce tip de date e și ce instrument NASA imită în situl real.
# Textele apar în UI (popup-ul de la click pe hartă), deci sunt în engleză.
LAYER_LABELS = {
    "elevation": {"data_type": "topographic", "analog_of": "MRO HiRISE DTM + MRO CTX DTM"},
    "slope": {"data_type": "topographic", "analog_of": "derived from DTM (max slope per cell)"},
    "terrain": {"data_type": "thermal", "analog_of": "Mars Odyssey THEMIS (thermal inertia)"},
    "minerals": {"data_type": "spectral", "analog_of": "MRO CRISM"},
    "radiation": {"data_type": "radiation", "analog_of": "Curiosity RAD (altitude model)"},
    "unsafe": {"data_type": "topographic", "analog_of": "HiRISE DTM FOM (here: slope > 35°)"},
}

HABITAT = (300, 200)

# Hardware NASA real, pus pe situl sintetic în poziții ANALOGE celor de pe Jezero (față de habitat
# și ținte), ca demo-ul să arate reperele reale și pe harta sintetică. Același format ca în
# data/processed/jezero/meta.json (vezi build_layers.ARTIFACTS). Pozițiile reale sunt pe situl Jezero.
SYNTH_NOTE = " (synthetic map: position is illustrative; real position on the Jezero site)"
ARTIFACTS = [
    {"id": "three_forks_depot", "name": "Three Forks Sample Depot (10 sample tubes)", "type": "recovery_target",
     "row": 186, "col": 150, "caution_radius_m": 0,
     "note": "Ten titanium tubes with rock cores and atmosphere, left by Perseverance for Mars Sample Return." + SYNTH_NOTE},
    {"id": "landing_site", "name": "Octavia E. Butler Landing (Perseverance touchdown)", "type": "landmark",
     "row": 292, "col": 210, "caution_radius_m": 0, "note": "Where Perseverance touched down on 18 February 2021." + SYNTH_NOTE},
    {"id": "descent_stage", "name": "Mars 2020 Descent Stage (sky crane) crash site", "type": "hazard_debris",
     "row": 274, "col": 188, "caution_radius_m": 150, "note": "Sharp metal debris and possible hydrazine residue: keep clear." + SYNTH_NOTE},
    {"id": "backshell_parachute", "name": "Backshell and supersonic parachute", "type": "hazard_debris",
     "row": 228, "col": 205, "caution_radius_m": 100, "note": "Risk of snagging on cables and fabric." + SYNTH_NOTE},
    {"id": "heat_shield", "name": "Mars 2020 heat shield", "type": "historical_hardware",
     "row": 345, "col": 255, "caution_radius_m": 50, "note": "Carbon-composite heat shield with ablative cork." + SYNTH_NOTE},
    {"id": "ingenuity_first_flight", "name": "Wright Brothers Field (Ingenuity's first flight)", "type": "historical_hardware",
     "row": 289, "col": 214, "caution_radius_m": 0,
     "note": "First powered, controlled flight on another planet (19 April 2021)." + SYNTH_NOTE},
]
for _a in ARTIFACTS:
    _a.update(source="synthetic", status="synthetic")
TARGETS = [
    {"id": "clay_delta", "name": "Clay, delta front", "kind": "clay", "row": 180, "col": 140, "science_value": 10, "dwell_min": 30, "image": None},
    {"id": "carbonate_rim", "name": "Carbonates, delta margin", "kind": "carbonate", "row": 120, "col": 260, "science_value": 7, "dwell_min": 20, "image": None},
    {"id": "olivine_floor", "name": "Olivine, crater floor", "kind": "olivine", "row": 340, "col": 330, "science_value": 4, "dwell_min": 15, "image": None},
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
    # deci frontul are pereți de netrecut (>25°, ~1/4 din front) și rampe pe unde se poate urca.
    # Panta maximă a logisticei ≈ înălțime / (4 · lățime): la 12 m -> ~55°, la 170 m -> ~6°.
    dy, dx = y - DELTA_APEX_M[0], x - DELTA_APEX_M[1]
    r = np.hypot(dy, dx)
    theta = np.arctan2(dy, dx)
    front_width = 12.0 + 160.0 * (0.5 + 0.5 * np.sin(5 * theta + 0.7))
    delta_mask = 1.0 / (1.0 + np.exp(np.clip(-(DELTA_RADIUS_M - r) / front_width, -60, 60)))
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
    # Fondul e doza echivalentă RAD (DOSE_RATE_USV_H); variația cu altitudinea (scala ~11 km, cât
    # înălțimea de scară a atmosferei) și zgomotul sunt presupuneri.
    radiation = (DOSE_RATE_USV_H * np.exp((elev - elev.mean()) / 11000.0)
                 + 0.5 * smooth_noise(rng, 3.0)).astype(np.float32)

    unsafe = slope > UNSAFE_SLOPE_DEG  # înlocuitor pentru masca FOM din datele reale

    return {
        "elevation": elev.astype(np.float32),
        "slope": slope,
        "terrain": terrain,
        "minerals": minerals,
        "radiation": radiation,
        "unsafe": unsafe,
    }


def walkable(layers: dict[str, np.ndarray], max_slope_deg: float = MAX_SLOPE_DEG) -> np.ndarray:
    return (layers["slope"] <= max_slope_deg) & ~layers["unsafe"]


def reachable_from(ok: np.ndarray, start: tuple[int, int]) -> np.ndarray:
    """Celulele accesibile din `start` pe celule permise, cu 8 vecini (ca A*-ul rolului 2).

    Diagonala e permisă doar dacă ambele celule ortogonale sunt permise, ca un traseu să nu
    „strecoare” printre doi pereți atinși doar în colț.
    """
    rows, cols = ok.shape
    seen = np.zeros_like(ok, dtype=bool)
    if not ok[start]:
        return seen
    seen[start] = True
    queue = deque([start])
    while queue:
        r, c = queue.popleft()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if (dr or dc) and 0 <= nr < rows and 0 <= nc < cols and ok[nr, nc] and not seen[nr, nc]:
                    if dr and dc and not (ok[r + dr, c] and ok[r, c + dc]):
                        continue
                    seen[nr, nc] = True
                    queue.append((nr, nc))
    return seen


def labeled_layers(layer_specs: dict, source: str, extra: dict | None = None) -> dict:
    """Specificațiile straturilor din contract + etichetele de proveniență."""
    extra = extra or {}
    return {name: {**spec, **LAYER_LABELS.get(name, {}), "source": source, **extra.get(name, {})}
            for name, spec in layer_specs.items()}


def write(layers: dict[str, np.ndarray], out: Path, seed: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "png").mkdir(exist_ok=True)
    for name, grid in layers.items():
        np.save(out / f"{name}.npy", grid)

    contract = json.loads((ROOT / "shared" / "contracts" / "meta.json").read_text(encoding="utf-8"))
    slope = layers["slope"]
    meta = {**contract, "source": "synthetic", "seed": seed, "targets": TARGETS,
            "habitat": {"row": HABITAT[0], "col": HABITAT[1]},
            "artifacts": ARTIFACTS, "rover_traverse": None,
            "layers": labeled_layers(contract["layers"], "synthetic"),
            "generator_version": GENERATOR_VERSION,
            # Amprentă informativă: dacă diferă între doi colegi, nu au același sit.
            "fingerprint": {"forbidden_pct": round(float((slope > MAX_SLOPE_DEG).mean() * 100), 2),
                            "elevation_mean_m": round(float(layers["elevation"].mean()), 1)}}
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


def check(out: Path) -> int:
    """0 dacă situl de pe disc e generat de versiunea curentă, 1 altfel."""
    meta_path = out / "meta.json"
    if not meta_path.exists():
        print(f"Situl sintetic lipsește din {out}. Rulează: python pipeline/make_synthetic_site.py")
        return 1
    found = json.loads(meta_path.read_text(encoding="utf-8")).get("generator_version", 1)
    if found != GENERATOR_VERSION:
        print(f"Situl sintetic e vechi (v{found}, codul e v{GENERATOR_VERSION}). "
              "Rulează: python pipeline/make_synthetic_site.py")
        return 1
    print(f"Situl sintetic e la zi (v{GENERATOR_VERSION}).")
    return 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows (cp1252) nu are diacritice
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--check", action="store_true", help="doar verifică versiunea sitului de pe disc")
    args = p.parse_args()

    if args.check:
        sys.exit(check(args.out))

    layers = build(args.seed)
    write(layers, args.out, args.seed)

    slope = layers["slope"]
    print(f"Sit sintetic scris în {args.out}")
    print(f"  pantă: medie {slope.mean():.1f}°, max {slope.max():.1f}°, interzis (>{MAX_SLOPE_DEG:.0f}°): {(slope > MAX_SLOPE_DEG).mean():.1%}")
    reach = reachable_from(walkable(layers), HABITAT)
    for name, (r, c) in [("habitat", HABITAT)] + [(t["id"], (t["row"], t["col"])) for t in TARGETS]:
        ok = "ok" if slope[r, c] <= MAX_SLOPE_DEG else "PREA ABRUPT"
        acc = "accesibil" if reach[r, c] else "INACCESIBIL din habitat"
        print(f"  {name:<14} ({r},{c}): pantă {slope[r, c]:.1f}° {ok}, {acc}")


if __name__ == "__main__":
    main()
