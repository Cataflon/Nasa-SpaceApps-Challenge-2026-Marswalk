"""Clientul Ollama. Nu e niciodată pe calea critică: decizia e deja trimisă când rulează."""

import json
import logging

import httpx

from app.config import LLM_ENABLED, LLM_TIMEOUT_S, OLLAMA_MODEL, OLLAMA_URL
from app.llm import prompts, templates
from app.llm.cache import cache

log = logging.getLogger(__name__)

OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 120}


async def explain(summary: dict) -> dict:
    """Întoarce {"text": ..., "source": "llm" | "template" | "cache"}.

    `summary` vine din `llm.summary.build_summary` (conține `decision`, `alternative_id`,
    `alternative_ids` și cifrele folosite de șablon: o2_end_pct, eta_hazard_min, extra_min).
    """
    fallback = {
        "text": templates.render(summary["decision"], **summary),
        "source": "template",
    }
    if not LLM_ENABLED:
        return fallback

    if (hit := cache.get(summary)) is not None:
        return {**hit, "source": "cache"}

    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "keep_alive": -1,
        "format": prompts.response_schema(summary.get("alternative_ids", [])),
        "options": OPTIONS,
        "messages": [
            {"role": "system", "content": prompts.SYSTEM},
            {"role": "user", "content": prompts.user_prompt(summary)},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_S) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=body)
            resp.raise_for_status()
        out = json.loads(resp.json()["message"]["content"])
    except Exception as exc:  # timeout, Ollama oprit, JSON invalid
        log.warning("LLM indisponibil, folosesc șablonul: %s", exc)
        return fallback

    # Verificare de consistență: LLM-ul nu are voie să schimbe decizia.
    if out.get("decizie") != summary["decision"] or out.get("alternativa_id") != summary.get("alternative_id"):
        log.warning("LLM-ul a contrazis decizia, folosesc șablonul: %s", out)
        return fallback

    result = {"text": out["motiv"], "source": "llm"}
    cache.put(summary, result)
    return result


async def warm_up() -> None:
    """Încarcă modelul în VRAM la pornire, ca prima explicație să fie rapidă."""
    if not LLM_ENABLED:
        return
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": "ok", "keep_alive": -1, "options": {"num_predict": 1}},
            )
        log.info("Modelul %s e încălzit.", OLLAMA_MODEL)
    except Exception as exc:
        log.warning("Nu am putut încălzi modelul (%s). Explicațiile vor veni din șabloane.", exc)
