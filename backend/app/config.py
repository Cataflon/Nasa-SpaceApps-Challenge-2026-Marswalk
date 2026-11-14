"""Setări globale. Totul se poate suprascrie din variabile de mediu."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CONTRACTS_DIR = ROOT / "shared" / "contracts"

# "synthetic" -> data/synthetic, altfel data/processed/<site_id>
SITE_ID = os.getenv("MARSWALK_SITE", "synthetic")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# qwen3:4b-instruct (Qwen3-4B-Instruct-2507): ~2,9 GB în VRAM, fără mod de gândire, tool calling.
# Atenție: tag-ul `qwen3:4b` simplu e varianta „Thinking”, care gândește mereu și e prea lentă.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "3"))
LLM_ENABLED = os.getenv("LLM_ENABLED", "1") == "1"

# 1 = WebSocket-ul redă live_messages.json în buclă, în loc de motorul real (util pentru frontend).
LIVE_MOCK = os.getenv("LIVE_MOCK", "0") == "1"

FRONTEND_ORIGINS =os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")


def site_dir(site_id: str = SITE_ID) -> Path:
    if site_id == "synthetic":
        return DATA_DIR / "synthetic"
    return DATA_DIR / "processed" / site_id
