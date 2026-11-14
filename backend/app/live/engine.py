"""Motorul de tick-uri (1 tick = 1 minut simulat).

Pe fiecare tick: senzori -> pericol + predicție -> traseul e afectat?
  nu -> CONTINUE
  da -> alternative -> validator -> regula (decision.choose) -> mesaj `decision` IMEDIAT
        -> în paralel LLM -> mesaj `explanation` (sau șablon dacă pică)

Până e gata motorul real, `mock_stream` redă mesajele din shared/contracts/live_messages.json.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from app.config import CONTRACTS_DIR


class LiveEngine:
    def __init__(self, seed: int = 42, clock_speed: float = 1.0):
        self.seed = seed
        self.clock_speed = clock_speed  # minute simulate pe secundă reală
        self.t_min = 0.0
        self.pending_events: list[dict] = []
        self.paused = True

    def inject(self, event: str, params: dict) -> None:
        self.pending_events.append({"event": event, "params": params, "t_min": self.t_min})

    async def run(self) -> AsyncIterator[dict]:
        """TODO (rolul 3): bucla reală, folosind app.core.* și app.llm.explain."""
        raise NotImplementedError
        yield {}


async def mock_stream(interval_s: float = 1.0) -> AsyncIterator[dict]:
    messages = json.loads((CONTRACTS_DIR / "live_messages.json").read_text(encoding="utf-8"))
    while True:
        for msg in messages:
            yield msg
            await asyncio.sleep(interval_s)
