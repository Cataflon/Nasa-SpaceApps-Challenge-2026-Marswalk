"""Benchmark-ul pe situl Jezero -> data/processed/jezero/benchmark.json (cifrele de pe slide-uri).

Rulează `core.benchmark.run_benchmark` (rolul 2, doar apelat, nemodificat): 100 de furtuni cu seed fix,
copilotul față de „doar planul”, fără LLM, deci reproductibil. Durează ~30 s, de aceea rezultatul se
păstrează aici: slide-urile și demo-ul citează fișierul, iar GET /api/benchmark (rolul 3) îl poate servi
direct, în loc să-l recalculeze la fiecare cerere.

`headline` are forma din README („Noutăți”, #5): {"copilot_safe_pct", "plan_safe_pct", "n_scenarios"}.
Se rulează din nou după orice schimbare în algoritmii rolului 2 sau în datele sitului; `site_fingerprint`
arată pe ce date s-a măsurat (testul pică dacă situl s-a schimbat de atunci).

Rulare: .venv/Scripts/python pipeline/run_benchmark.py   (cere dependențele backendului)
"""

import argparse
import collections
import json
import sys

import fetch_stac as fs
from build_layers import OUT

N_SCENARIOS = 100
SEED = 42


def summarize(result: dict, meta: dict) -> dict:
    per = result["per_scenario"]
    pairs = collections.Counter((s["plan_safe"], s["copilot_safe"]) for s in per)
    decisions = collections.Counter(d for s in per for d in s["decisions"])
    return {
        "headline": {"copilot_safe_pct": result["copilot"]["safe_pct"], "plan_safe_pct": result["plan_only"]["safe_pct"],
                     "n_scenarios": result["n"]},
        "seed": result["seed"],
        "site_id": meta["site_id"],
        "site_fingerprint": meta["fingerprint"],
        "plan_only": result["plan_only"],
        "copilot": result["copilot"],
        "storm_kinds": dict(sorted(collections.Counter(s["kind"] for s in per).items())),
        "rescued_by_copilot": pairs[(False, True)],
        "made_worse_by_copilot": pairs[(True, False)],
        "decisions": dict(sorted(decisions.items())),
        "method": "core.benchmark.run_benchmark (role 2): same storms for both strategies, no LLM; "
                  "safe = home with exposure below the hazard threshold, O2 above the reserve, before sunset minus the margin",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--n", type=int, default=N_SCENARIOS)
    p.add_argument("--seed", type=int, default=SEED)
    a = p.parse_args()
    sys.path.insert(0, str(fs.ROOT / "backend"))
    from app.core.benchmark import run_benchmark
    from app.core.site_data import get_site

    site = get_site("jezero")
    if site is None:
        raise SystemExit("Situl Jezero lipsește: rulează pipeline/build_layers.py.")
    out = summarize(run_benchmark(a.n, a.seed, site), site.meta)
    fs.atomic_write_text(OUT / "benchmark.json", json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    h = out["headline"]
    print(f"copilot {h['copilot_safe_pct']}% · plan fix {h['plan_safe_pct']}% ({h['n_scenarios']} furtuni); "
          f"salvate {out['rescued_by_copilot']}, înrăutățite {out['made_worse_by_copilot']}; "
          f"știință {out['copilot']['science_pct']}% vs {out['plan_only']['science_pct']}%")


if __name__ == "__main__":
    main()
