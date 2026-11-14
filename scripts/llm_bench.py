"""Măsoară LLM-ul real prin exact același cod ca backendul (`app.llm.explain`).

Rulare, din rădăcina repo-ului, cu Ollama pornit:
    .venv/Scripts/python scripts/llm_bench.py
    .venv/Scripts/python scripts/llm_bench.py --model qwen2.5:7b-instruct-q4_K_S
    .venv/Scripts/python scripts/llm_bench.py --repeat 3       # fiecare situație de 3 ori

Raportează: încărcarea modelului, latența (p50 / p95 / max), câte explicații au venit de la
LLM (restul = fallback pe șablon, cu motivul), emoji, lungimea textelor și determinismul.
"""

import argparse
import asyncio
import logging
import os
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿]")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", help="tag-ul Ollama (implicit: OLLAMA_MODEL sau valoarea din config.py)")
    p.add_argument("--repeat", type=int, default=1, help="de câte ori se trimite fiecare situație")
    p.add_argument("--timeout", type=float, default=None, help="limita în secunde (implicit LLM_TIMEOUT_S = 3)")
    return p.parse_args()


class FallbackReasons(logging.Handler):
    """Prinde avertismentele clientului, ca să știm DE CE a căzut pe șablon."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.last = None

    def emit(self, record):
        self.last = record.getMessage()


async def main(args) -> int:
    os.environ["LLM_ENABLED"] = "1"
    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model
    if args.timeout:
        os.environ["LLM_TIMEOUT_S"] = str(args.timeout)
    sys.path.insert(0, str(ROOT / "backend"))

    import httpx

    from app.llm import client
    from app.llm.samples import situations

    # Fără cache: vrem să măsurăm modelul, nu fișierul de cache.
    client.cache.get = lambda summary: None
    client.cache.put = lambda summary, value: None
    reasons = FallbackReasons()
    logging.getLogger("app.llm.client").addHandler(reasons)

    print(f"model: {client.OLLAMA_MODEL}   server: {client.OLLAMA_URL}   limită: {client.LLM_TIMEOUT_S} s")
    try:
        tags = httpx.get(f"{client.OLLAMA_URL}/api/tags", timeout=3).json()
    except Exception as exc:
        print(f"Ollama nu răspunde ({exc}). Pornește-l din Start și încearcă din nou.")
        return 2
    if client.OLLAMA_MODEL not in {m["name"] for m in tags.get("models", [])}:
        print(f"Modelul {client.OLLAMA_MODEL} nu e descărcat. Rulează: ollama pull {client.OLLAMA_MODEL}")
        return 2

    t0 = time.perf_counter()
    await client.warm_up()
    print(f"încărcare model (warm-up): {time.perf_counter() - t0:.1f} s\n")

    rows, texts = [], {}
    for name, summary in situations():
        for r in range(args.repeat):
            reasons.last = None
            t = time.perf_counter()
            out = await client.explain(summary)
            dt = time.perf_counter() - t
            rows.append((name, summary["decision"], dt, out, reasons.last))
            texts.setdefault(name, []).append(out["text"])

    lat = sorted(dt for *_, dt, _o, _r in [(n, d, dt, o, r) for n, d, dt, o, r in rows])
    llm = [r for r in rows if r[3]["source"] == "llm"]
    p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
    words = [len(r[3]["text"].split()) for r in llm]
    emoji = [r for r in llm if EMOJI.search(r[3]["text"])]
    stable = [n for n, ts in texts.items() if len(set(ts)) == 1]

    print(f"cereri: {len(rows)}   latență p50 {statistics.median(lat):.2f} s · p95 {p95:.2f} s · max {lat[-1]:.2f} s")
    print(f"de la LLM:           {len(llm)}/{len(rows)}   (restul au căzut pe șablon)")
    print(f"sub limita de timp:  {sum(dt < client.LLM_TIMEOUT_S for dt in lat)}/{len(rows)}")
    print(f"fără emoji:          {len(llm) - len(emoji)}/{len(llm)}")
    if words:
        print(f"cuvinte:             medie {statistics.mean(words):.0f} · max {max(words)}   (cerut: ≤ 25)")
    if args.repeat > 1:
        print(f"deterministe:        {len(stable)}/{len(texts)} situații dau același text la fiecare repetare")
    print()

    for name, decision, dt, out, reason in rows[:: args.repeat]:
        tag = "LLM " if out["source"] == "llm" else "ȘABL"
        print(f"{tag} {dt:4.2f}s  {decision:<9} {name:<18} {out['text']}")
        if out["source"] != "llm" and reason:
            print(f"{'':>34}↳ {reason[:150]}")
    return 0 if len(llm) == len(rows) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main(parse_args())))
