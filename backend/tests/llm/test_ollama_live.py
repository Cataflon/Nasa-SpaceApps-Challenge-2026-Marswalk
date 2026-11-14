"""Teste pe Ollama REAL. Nu rulează implicit și nici în CI.

Rulare (din backend/, cu Ollama pornit):
    ../.venv/Scripts/python -m pytest -m ollama
Dacă Ollama nu răspunde sau modelul nu e descărcat, testele sunt sărite, nu picate.
"""

import asyncio
import re
import time

import httpx
import pytest

from app.llm import client
from app.llm.samples import situations

pytestmark = pytest.mark.ollama

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿]")
SITUATIONS = situations()
# Lungimea cerută e ≤ 25 de cuvinte; acceptăm o mică depășire, dar nu paragrafe.
MAX_WORDS = 35


@pytest.fixture(scope="module", autouse=True)
def real_ollama():
    try:
        tags = httpx.get(f"{client.OLLAMA_URL}/api/tags", timeout=3).json()
    except Exception as exc:
        pytest.skip(f"Ollama nu răspunde la {client.OLLAMA_URL}: {exc}")
    if client.OLLAMA_MODEL not in {m["name"] for m in tags.get("models", [])}:
        pytest.skip(f"Modelul {client.OLLAMA_MODEL} nu e descărcat (ollama pull {client.OLLAMA_MODEL}).")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(client, "LLM_ENABLED", True)
        mp.setattr(client.cache, "get", lambda s: None)  # măsurăm modelul, nu cache-ul
        mp.setattr(client.cache, "put", lambda s, v: None)
        asyncio.run(client.warm_up())
        yield


@pytest.mark.parametrize("name,summary", SITUATIONS, ids=[n for n, _ in SITUATIONS])
def test_explanation_comes_from_llm_fast_and_clean(name, summary):
    t = time.perf_counter()
    out = asyncio.run(client.explain(summary))
    elapsed = time.perf_counter() - t

    # source == "llm" înseamnă: JSON valid, decizie și alternativă copiate corect, motiv nevid.
    assert out["source"] == "llm", f"a căzut pe șablon: {out['text']}"
    assert elapsed < client.LLM_TIMEOUT_S, f"{elapsed:.2f} s"
    assert not EMOJI.search(out["text"]), out["text"]
    assert len(out["text"].split()) <= MAX_WORDS, out["text"]


def test_same_input_same_text():
    """temperature 0 + seed fix: aceeași situație dă același text."""
    _, summary = SITUATIONS[0]
    texts = {asyncio.run(client.explain(summary))["text"] for _ in range(3)}
    assert len(texts) == 1, texts
