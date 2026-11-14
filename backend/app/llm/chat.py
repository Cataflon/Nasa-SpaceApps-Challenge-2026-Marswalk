"""Chatul cu astronautul: LLM-ul înțelege cererea și apelează uneltele, codul dă cifrele.

`chat_stream(message, history)` produce liniile din shared/contracts/chat_stream.json:
  tool_call -> tool_result -> (route) -> token... -> done

Cu Ollama: tool calling real, în streaming, cel mult MAX_TOOL_ROUNDS runde de unelte.
Fără Ollama (oprit, dezactivat, eroare înainte de primul mesaj): fallback pe cuvinte-cheie,
care apelează aceleași unelte și răspunde din șabloane. Linia `done` spune ce sursă a răspuns.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator

import httpx

from app.config import LLM_ENABLED, OLLAMA_MODEL, OLLAMA_URL
from app.llm import tools

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
MAX_HISTORY = 8
CHAT_TIMEOUT_S = 30.0  # chatul nu e pe calea critică; doar decizia live are limita de 3 s
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 4096}

SYSTEM_TEMPLATE = """You are the copilot of an astronaut walking on Mars, at Jezero crater. The astronaut starts every EVA at the habitat.
Science targets on this map:
{targets}

Rules:
- Use the tools for every number (time, oxygen, dose, distance, slope). Never invent or estimate numbers yourself.
- If the astronaut wants to go somewhere or collect a sample, call plan_route. If they ask what is worth sampling, call science_stops.
- If a tool returns an error, fix the arguments and try again, or explain the problem briefly.
- If the request is unclear, ask one short question.
- Answer in English, at most 60 words, plain text, no emojis, no markdown. Lead with the answer or the action."""


class LLMUnavailable(RuntimeError):
    pass


def system_prompt() -> str:
    lines = [f"- {t['id']}: {t['name']} ({t.get('kind', '?')}, science value {t.get('science_value', '?')})"
             for t in tools.targets()]
    return SYSTEM_TEMPLATE.format(targets="\n".join(lines))


async def chat_stream(message: str, history: list[dict] | None = None) -> AsyncIterator[dict]:
    history = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-MAX_HISTORY:]
    if LLM_ENABLED:
        started = False
        try:
            async for item in _ollama_chat(message, history):
                started = True
                yield item
            return
        except Exception as exc:  # Ollama oprit, timeout, răspuns invalid
            log.warning("Chatul LLM a eșuat: %s", exc)
            if started:
                yield {"type": "token", "text": " (The copilot language model stopped responding.)"}
                yield {"type": "done", "source": "llm", "error": True}
                return
    async for item in fallback_chat(message):
        yield item


# ---------------------------------------------------------------- Ollama


async def _run_tool(name: str, args) -> AsyncIterator[dict]:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    yield {"type": "tool_call", "name": name, "args": args}
    result, route = await asyncio.to_thread(tools.execute, name, args)
    yield {"type": "tool_result", "name": name, "result": result}
    if route is not None:
        yield {"type": "route", "route": route}


async def _ollama_chat(message: str, history: list[dict]) -> AsyncIterator[dict]:
    messages = [{"role": "system", "content": system_prompt()}, *history, {"role": "user", "content": message}]
    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_S) as client:
        for _ in range(MAX_TOOL_ROUNDS + 1):
            body = {
                "model": OLLAMA_MODEL, "messages": messages, "tools": tools.TOOL_SPECS,
                "stream": True, "think": False, "keep_alive": -1, "options": OPTIONS,
            }
            content, calls = "", []
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise LLMUnavailable(chunk["error"])
                    msg = chunk.get("message", {})
                    if msg.get("content"):
                        content += msg["content"]
                        yield {"type": "token", "text": msg["content"]}
                    calls.extend(msg.get("tool_calls") or [])

            if not calls:
                yield {"type": "done", "source": "llm"}
                return

            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            for call in calls:
                fn = call.get("function", {})
                name, result = fn.get("name", ""), None
                async for item in _run_tool(name, fn.get("arguments", {})):
                    if item["type"] == "tool_result":
                        result = item["result"]
                    yield item
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, ensure_ascii=False)})

    yield {"type": "token", "text": "I could not finish that request. Please ask in a simpler way."}
    yield {"type": "done", "source": "llm"}


# ---------------------------------------------------------------- fallback fără LLM

_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h\b|hrs?\b|hours?\b)")
_MINUTES = re.compile(r"(\d+)\s*(?:min\b|mins\b|minutes?\b)")
STATUS_WORDS = ("status", "happening", "around me", "how am i", "where am i", "situation")
OXYGEN_WORDS = ("oxygen", "o2", "o₂")
DAYLIGHT_WORDS = ("sunset", "daylight", "dark", "return by", "time left", "how long")
TERRAIN_WORDS = ("terrain", "slope", "mineral", "what is at", "what's at", "ground")
SCIENCE_WORDS = ("what should", "best", "recommend", "worth", "science", "which sample", "where should")
PLAN_WORDS = ("route", "plan", "go to", "take me", "sample", "walk", "visit", "get to")


def _duration_min(text: str) -> float | None:
    if m := _HOURS.search(text):
        return float(m.group(1)) * 60
    if m := _MINUTES.search(text):
        return float(m.group(1))
    return None


def _mentioned_targets(text: str) -> list[str]:
    found = []
    for t in tools.targets():
        words = {t.get("kind", ""), t["id"].replace("_", " "), t["name"].lower()}
        if any(w and w in text for w in words):
            found.append(t["id"])
    return found


def route_intent(message: str) -> tuple[str, dict] | None:
    """Unealta și parametrii ghiciți din cuvinte-cheie, sau None (mesajul de ajutor)."""
    text = message.lower()
    stops = _mentioned_targets(text)
    duration = _duration_min(text)
    preset = "fast" if ("fast" in text or "quick" in text) else "science" if "science first" in text else "safe"

    if any(w in text for w in STATUS_WORDS):
        return "eva_status", {}
    if any(w in text for w in OXYGEN_WORDS):
        return "oxygen_budget", {"stops": stops} if stops else {}
    if not stops and any(w in text for w in DAYLIGHT_WORDS):  # „how long to the clay?” e o cerere de traseu
        return "daylight", {}
    if stops and any(w in text for w in TERRAIN_WORDS):
        return "layer_value", {"target": stops[0]}
    if stops:
        args = {"stops": stops, "preset": preset}
        if duration:
            args["max_duration_min"] = duration
        return "plan_route", args
    if any(w in text for w in SCIENCE_WORDS + PLAN_WORDS):
        return "science_stops", {"max_duration_min": duration} if duration else {}
    return None


HELP = ("I can plan a route to a science target (for example: \"Plan a route to the clay sample, I have 5 hours\"), "
        "check your oxygen, daylight and terrain, suggest the best science stops, or report your EVA status.")


def describe(name: str, r: dict) -> str:
    """Răspunsul din șablon pentru rezultatul unei unelte (în engleză)."""
    if "error" in r:
        return f"I couldn't do that: {r['error']}"
    note = " (Estimate: the route planner is not final yet.)" if r.get("note") else ""
    if name == "plan_route":
        names = {t["id"]: t["name"] for t in tools.targets()}
        stops = ", ".join(names.get(s, s) for s in r["stops"]) or "the target"
        return (f"Route to {stops}: {r.get('duration_min')} min round trip, "
                f"{r.get('o2_at_habitat_pct')}% O2 on arrival (reserve {r.get('o2_reserve_pct'):.0f}%), "
                f"return by {r.get('return_by_ltst', '?')}. Verdict: {r.get('verdict')}.{note}")
    if name == "oxygen_budget":
        if "status" in r:
            return "No EVA in progress. Tell me which targets you plan to visit and I will estimate the oxygen."
        if "o2_now_pct" in r:
            return f"O2 now {r['o2_now_pct']}%, about {r['o2_at_habitat_pct']}% on arrival at the habitat (reserve {r['o2_reserve_pct']:.0f}%)."
        return f"About {r['o2_at_habitat_pct']}% O2 on arrival, {r['margin_pct']} points above the {r['o2_reserve_pct']:.0f}% reserve.{note}"
    if name == "daylight":
        text = f"Sunset at {r['sunset_ltst']} local time. Be back at the habitat by {r['return_by_ltst']}."
        if "minutes_left_before_return_by" in r:
            text += f" That is {r['minutes_left_before_return_by']} min from now."
        return text
    if name == "layer_value":
        parts = [f"slope {r['slope_deg']} degrees" if "slope_deg" in r else None,
                 f"terrain {r['terrain']}" if "terrain" in r else None,
                 f"minerals {r['minerals']}" if "minerals" in r else None,
                 f"radiation {r['radiation_usv_h']} uSv/h" if "radiation_usv_h" in r else None]
        return f"At {r.get('name', 'that point')}: " + ", ".join(p for p in parts if p) + "."
    if name == "science_stops":
        if not r["suggested_stops"]:
            return f"No science target fits in {r['max_duration_min']:.0f} min with a safe oxygen reserve."
        best = r["ranked"][0]
        return (f"Best fit for {r['max_duration_min']:.0f} min: {', '.join(r['suggested_stops'])}. "
                f"Top target: {best['name']} (science value {best['science_value']}).{note}")
    if name == "eva_status":
        if r.get("status"):
            return "No EVA in progress."
        text = f"At {r['now_ltst']}: O2 {r['o2_now_pct']}%, about {r['o2_at_habitat_pct']}% on arrival."
        if r["active_hazards"]:
            text += f" Active hazards: {', '.join(r['active_hazards'])}."
        if "last_decision" in r:
            d = r["last_decision"]
            text += f" Last decision: {d['decision']} ({d['alternative_id']})."
        return text
    return "Done."


async def fallback_chat(message: str) -> AsyncIterator[dict]:
    intent = route_intent(message)
    if intent is None:
        yield {"type": "token", "text": HELP}
        yield {"type": "done", "source": "fallback"}
        return
    name, args = intent
    result = None
    async for item in _run_tool(name, args):
        if item["type"] == "tool_result":
            result = item["result"]
        yield item
    yield {"type": "token", "text": describe(name, result)}
    yield {"type": "done", "source": "fallback"}
