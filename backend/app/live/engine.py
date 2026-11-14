"""Motorul de tick-uri (1 tick = 1 minut simulat).

Pe fiecare tick:
  senzori -> evenimente -> deplasare (O₂, doză) -> pericole + predicție -> traseul e afectat?
    nu -> CONTINUE (nimic de trimis în afară de `tick`)
    da -> alternative -> validator + regula (decision.choose) -> mesaj `decision` IMEDIAT
          -> explicația (LLM sau șablon) vine separat, ca mesaj `explanation`

`step()` e sincron și determinist (testele îl apelează direct, fără ceas real).
`run()` îl apelează în buclă, publică mesajele și lansează explicațiile asincron.

Orice funcție din `core` (rolul 2) sau `scenario` (rolul 1) care aruncă încă
NotImplementedError are un fallback simplu aici. Când e implementată, motorul o
folosește automat, fără modificări.

Până e gata motorul real, `mock_stream` redă mesajele din shared/contracts/live_messages.json
(activat cu LIVE_MOCK=1).
"""

import asyncio
import copy
import json
import logging
import math
from collections.abc import AsyncIterator, Awaitable, Callable

from app.config import CONTRACTS_DIR
from app.core import alternatives as core_alternatives
from app.core import hazards as core_hazards
from app.core.budget import O2_PCT_PER_MIN_PER_WATT, O2_PCT_PER_MIN_REST, tobler_speed_ms
from app.core.decision import choose
from app.core.site_data import get_site
from app.core.types import Alternative, Decision, Limits
from app.live import scenario as scenario_mod
from app.live.store import RouteStore
from app.live.store import routes as default_routes
from app.llm import explain as default_explain
from app.llm.summary import build_summary

log = logging.getLogger(__name__)

# --- Presupuneri (de documentat de rolul 1 în docs/how-we-calculate.md) ---
WALK_WATTS = 220.0  # putere metabolică suplimentară la mers în costum
O2_PCT_PER_MIN_WALK = O2_PCT_PER_MIN_REST + O2_PCT_PER_MIN_PER_WATT * WALK_WATTS
SUIT_LEAK_PCT_PER_MIN = 0.15
FATIGUE_SPEED_FACTOR = 0.8
FATIGUE_O2_FACTOR = 1.15
DEFAULT_SUNSET_MIN = 420.0
DEFAULT_WAIT_MIN = 30
SOLAR_DOSE_MULTIPLIER = 20.0
SOLAR_DURATION_MIN = 60

# --- Parametrii motorului ---
REEVAL_MIN = 5  # cât de des se reevaluează un pericol care lovește încă traseul
HIT_HORIZON_MIN = 60  # cât de departe în viitor verifică fallback-ul dacă traseul e lovit
MAX_DURATION_MIN = 720  # siguranță: simularea se oprește după 12 ore

# Valori implicite pentru pericolele injectate fără parametri. Furtunile mobile pornesc
# lateral față de traseu și se deplasează spre el, ca să ajungă în ~offset/viteză secunde.
HAZARD_DEFAULTS = {
    "dust_devil": {"axes_m": [150, 150], "speed_ms": 3.0, "intensity": 0.5, "offset_m": 600},
    "local_storm": {"axes_m": [1800, 1100], "speed_ms": 2.5, "intensity": 0.7, "offset_m": 2500},
    "regional_storm": {"axes_m": [30000, 30000], "speed_ms": 0.0, "intensity": 0.9, "offset_m": 0},
    "marsquake": {"axes_m": [300, 300], "speed_ms": 0.0, "intensity": 1.0, "offset_m": 0},
}

Cell = tuple[int, int]


def _contract(name: str):
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _cell(p) -> Cell:
    return (int(round(p[0])), int(round(p[1])))


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _polyline_len(points: list) -> float:
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


class LiveEngine:
    def __init__(
        self,
        *,
        seed: int = 42,
        clock_speed: float = 10.0,
        limits: Limits = Limits(),
        preset: str = "safe",
        store: RouteStore | None = None,
        site_provider: Callable = get_site,
        explain_fn: Callable[[dict], Awaitable[dict]] | None = None,
        scheduled_events: list | None = None,
    ):
        self.seed = seed
        self.clock_speed = clock_speed  # minute simulate pe secundă reală
        self.limits = limits
        self.preset = preset
        self.store = store or default_routes
        self.site_provider = site_provider
        self.explain_fn = explain_fn or default_explain
        self._scheduled_override = scheduled_events  # None = evenimentele scenariului / demo
        self._subscribers: set[asyncio.Queue] = set()
        self.reset()

    # ------------------------------------------------------------------ control

    def reset(self) -> None:
        self.state = "idle"  # idle | running | paused | finished
        self.t_min = 0
        self.route: dict | None = None
        self.pos: tuple[float, float] | None = None
        self.remaining: list[Cell] = []
        self.traveled: list[Cell] = []
        self.stops_left: list[dict] = []  # {"id", "cell", "dwell_min"}
        self.returning = False
        self.o2_pct = 100.0
        self.dose_msv = 0.0
        self.fatigue = 1.0
        self.leak_pct_per_min = 0.0
        self.dose_mult = 1.0
        self.dose_mult_until = -1
        self.wait_until: int | None = None
        self.dwell_left = 0
        self.hazards: list[dict] = []
        self._hazard_counter = 0
        self.pending_events: list[dict] = []
        self.scheduled: list[dict] = []
        self.sensors_series: list[dict] | None = None
        self.sunset_min = DEFAULT_SUNSET_MIN
        self.last_tick: dict | None = None
        self._last_eval_t: dict[str, int] = {}
        self._last_decision_key: tuple | None = None
        self._explain_queue: list[dict] = []
        self._site = None
        self._meta: dict = {}

    def start(self, route_id: str | None = None, speed: float | None = None) -> None:
        """Pornește (sau reia) ieșirea. Fără route_id: ultimul traseu planificat, apoi mock-ul."""
        if speed is not None:
            self.clock_speed = speed
        if self.state in ("paused", "running") and route_id is None:
            self.state = "running"  # reia, sau doar schimbă viteza dacă rula deja
            return
        if route_id is not None:
            route = self.store.get(route_id)
            if route is None:
                raise KeyError(route_id)
        else:
            route = self.store.latest() or {**_contract("route_response.json"), "route_id": "mock"}
        self.reset()
        self.load(route)
        self.state = "running"

    def pause(self) -> None:
        if self.state == "running":
            self.state = "paused"

    def set_speed(self, speed: float) -> None:
        self.clock_speed = speed

    def inject(self, event: str, params: dict | None = None) -> None:
        """Evenimentul se aplică la următorul tick."""
        self.pending_events.append({"event": event, "params": dict(params or {})})

    def load(self, route: dict) -> None:
        self._site = self.site_provider()
        self._meta = self._site.meta if self._site is not None else _contract("site.json")
        self.route = copy.deepcopy(route)
        path = [_cell(p) for p in route["path"]]
        self.pos = (float(path[0][0]), float(path[0][1]))
        self.remaining = path[1:]
        self.traveled = [path[0]]
        self.stops_left = [
            {"id": s["id"], "cell": path[s["index_in_path"]], "dwell_min": int(s.get("dwell_min", 0))}
            for s in route.get("stops", [])
            if 0 <= s.get("index_in_path", -1) < len(path)
        ]
        self.sunset_min = float(route.get("budget", {}).get("sunset_min", DEFAULT_SUNSET_MIN))

        scenario_events = scenario_mod.DEMO_SCENARIO_EVENTS
        try:
            sc = scenario_mod.generate(self.seed, MAX_DURATION_MIN, None)
            self.sensors_series = sc.sensors
            scenario_events = sc.events
        except NotImplementedError:
            self.sensors_series = None
        events = self._scheduled_override if self._scheduled_override is not None else scenario_events
        self.scheduled = sorted(
            ({"t_min": int(e.t_min), "event": e.event, "params": dict(e.params)} for e in events),
            key=lambda e: e["t_min"],
        )

    # ------------------------------------------------------------------ tick

    def step(self) -> list[dict]:
        """Avansează un minut simulat și întoarce mesajele (tick, event, decision)."""
        if self.state != "running":
            return []
        self.t_min += 1
        t = self.t_min
        msgs: list[dict] = []

        due = [e for e in self.scheduled if e["t_min"] <= t]
        self.scheduled = [e for e in self.scheduled if e["t_min"] > t]
        for ev in due + self.pending_events:
            msgs.append(self._apply_event(ev, t))
        self.pending_events = []

        sensors = self._sensors(t)
        moving = self._advance_minute()
        speed = self._speed_ms() if moving else 0.0
        walk = O2_PCT_PER_MIN_WALK * (FATIGUE_O2_FACTOR if self.fatigue < 1 else 1.0)
        self.o2_pct -= (walk if moving else O2_PCT_PER_MIN_REST) + self.leak_pct_per_min
        self.dose_msv += sensors["dose_rate_usv_h"] / 60.0 / 1000.0
        self._expire_hazards(t)

        msgs.insert(0, self._tick_message(t, sensors, speed))

        decision_msg = self._check_hazards(t)
        if decision_msg is not None:
            msgs.append(decision_msg)

        msgs.extend(self._check_end(t))
        return msgs

    # ------------------------------------------------------------------ deplasare

    @property
    def cell_size_m(self) -> float:
        return float(self._meta.get("cell_size_m", 20))

    def _speed_ms(self) -> float:
        slope_tan = 0.0
        if self._site is not None and self.remaining and "elevation" in self._site.layers:
            elev = self._site.layers["elevation"]
            a, b = _cell(self.pos), self.remaining[0]
            d = _dist(a, b) * self.cell_size_m
            if d > 0:
                slope_tan = float(elev[b] - elev[a]) / d
        return tobler_speed_ms(slope_tan, self.fatigue)

    def _flat_speed_ms(self) -> float:
        return tobler_speed_ms(0.0, self.fatigue)

    def _advance_minute(self) -> bool:
        """Mută astronautul un minut pe traseu. Întoarce True dacă a mers."""
        if self.wait_until is not None:
            if self.t_min <= self.wait_until:
                return False
            self.wait_until = None
        if self.dwell_left > 0:
            self.dwell_left -= 1
            return False
        if not self.remaining:
            return False

        budget = self._speed_ms() * 60.0 / self.cell_size_m  # celule în acest minut
        while budget > 1e-9 and self.remaining:
            target = self.remaining[0]
            d = _dist(self.pos, target)
            if d <= budget:
                budget -= d
                self.pos = (float(target[0]), float(target[1]))
                self.remaining.pop(0)
                self.traveled.append(target)
                stop = next((s for s in self.stops_left if s["cell"] == target), None)
                if stop is not None:
                    self.stops_left.remove(stop)
                    self.dwell_left = stop["dwell_min"]
                    break
            else:
                f = budget / d
                self.pos = (self.pos[0] + (target[0] - self.pos[0]) * f, self.pos[1] + (target[1] - self.pos[1]) * f)
                budget = 0
        return True

    def _remaining_minutes(self) -> tuple[float, float]:
        """(minute de mers, minute de oprire) până la capătul traseului curent."""
        dist_m = _polyline_len([self.pos] + self.remaining) * self.cell_size_m
        walk = dist_m / self._flat_speed_ms() / 60.0
        dwell = self.dwell_left + sum(s["dwell_min"] for s in self.stops_left)
        return walk, dwell

    def _o2_after(self, walk_min: float, rest_min: float) -> float:
        walk_rate = O2_PCT_PER_MIN_WALK * (FATIGUE_O2_FACTOR if self.fatigue < 1 else 1.0)
        return self.o2_pct - walk_rate * walk_min - O2_PCT_PER_MIN_REST * rest_min - self.leak_pct_per_min * (walk_min + rest_min)

    # ------------------------------------------------------------------ senzori și evenimente

    def _sensors(self, t: int) -> dict:
        if self.sensors_series:
            s = dict(self.sensors_series[min(t, len(self.sensors_series) - 1)])
        else:
            s = dict(scenario_mod.BASELINE)
        if t <= self.dose_mult_until:
            s["dose_rate_usv_h"] = s["dose_rate_usv_h"] * self.dose_mult
        return s

    def _apply_event(self, ev: dict, t: int) -> dict:
        kind, params = ev["event"], ev["params"]
        if kind in HAZARD_DEFAULTS:
            self.hazards.append(self._new_hazard(kind, params, t))
        elif kind == "solar_particle_event":
            self.dose_mult = float(params.get("dose_rate_multiplier", SOLAR_DOSE_MULTIPLIER))
            self.dose_mult_until = t + int(params.get("duration_min", SOLAR_DURATION_MIN))
        elif kind == "suit_leak":
            self.leak_pct_per_min += float(params.get("leak_pct_per_min", SUIT_LEAK_PCT_PER_MIN))
        elif kind == "fatigue":
            self.fatigue *= float(params.get("speed_factor", FATIGUE_SPEED_FACTOR))
        return {"type": "event", "t_min": t, "event": kind, "severity": params.get("severity", "high"), "params": params}

    def _new_hazard(self, kind: str, params: dict, t: int) -> dict:
        d = HAZARD_DEFAULTS[kind]
        self._hazard_counter += 1
        hid = f"{kind}_{self._hazard_counter}"
        # Unde va fi astronautul când ajunge pericolul (furtunile mobile) sau peste 15 min (cele fixe).
        arrival_min = d["offset_m"] / d["speed_ms"] / 60.0 if d["speed_ms"] > 0 else 15.0
        ahead = self._point_ahead(arrival_min)
        if "center" in params:
            center = (float(params["center"]["row"]), float(params["center"]["col"]))
            velocity = tuple(params.get("velocity_ms", [0.0, d["speed_ms"]]))
        else:
            # Pornește la vest de un punct de pe traseu și se mișcă spre est, peste el.
            center = (ahead[0], ahead[1] - d["offset_m"] / self.cell_size_m)
            velocity = (0.0, d["speed_ms"])
        return {
            "id": hid,
            "kind": kind,
            "t0": t,
            "center0": center,
            "axes_m": list(params.get("axes_m", d["axes_m"])),
            "angle_deg": float(params.get("angle_deg", 0.0)),
            "intensity": float(params.get("intensity", d["intensity"])),
            "velocity_ms": [float(velocity[0]), float(velocity[1])],
        }

    def _point_ahead(self, minutes: float) -> tuple[float, float]:
        """Punctul de pe traseul rămas în care va fi astronautul peste `minutes` (fără opriri)."""
        pts = [self.pos] + self.remaining
        total = _polyline_len(pts)
        if total == 0:
            return self.pos
        goal = min(total, self._flat_speed_ms() * 60.0 * minutes / self.cell_size_m)
        acc = 0.0
        for a, b in zip(pts, pts[1:]):
            d = _dist(a, b)
            if acc + d >= goal:
                f = (goal - acc) / d
                return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
            acc += d
        return pts[-1]

    # ------------------------------------------------------------------ pericole

    def _hazard_center(self, h: dict, t: float) -> tuple[float, float]:
        sec = (t - h["t0"]) * 60.0
        vy, vx = h["velocity_ms"]
        return (h["center0"][0] + vy * sec / self.cell_size_m, h["center0"][1] + vx * sec / self.cell_size_m)

    def _hazard_contract(self, h: dict, t: int) -> dict:
        """Forma JSON din contract. Folosește core.hazards dacă e implementat, altfel mișcare liniară."""
        r, c = self._hazard_center(h, t)
        current = {
            "id": h["id"],
            "kind": h["kind"],
            "center": {"row": round(r, 1), "col": round(c, 1)},
            "axes_m": h["axes_m"],
            "angle_deg": h["angle_deg"],
            "intensity": h["intensity"],
            "velocity_ms": h["velocity_ms"],
        }
        try:
            return core_hazards.to_contract(core_hazards.from_contract(current, self.cell_size_m, t), t, self.cell_size_m)
        except NotImplementedError:
            pass
        forecast = []
        for k in core_hazards.FORECAST_STEPS_MIN:
            fr, fc = self._hazard_center(h, t + k)
            grow = 1 + core_hazards.UNCERTAINTY_GROWTH_PER_MIN * k
            forecast.append({"t_min": t + k, "center": {"row": round(fr, 1), "col": round(fc, 1)},
                             "axes_m": [round(a * grow) for a in h["axes_m"]]})
        return {**current, "forecast": forecast}

    def _inside(self, h: dict, point, t: float) -> bool:
        """Punctul e în elipsa prezisă la momentul t? (axele cresc cu orizontul)."""
        r, c = self._hazard_center(h, t)
        grow = 1 + core_hazards.UNCERTAINTY_GROWTH_PER_MIN * max(0.0, t - self.t_min)
        a, b = h["axes_m"][0] * grow, h["axes_m"][1] * grow
        dy = (point[0] - r) * self.cell_size_m
        dx = (point[1] - c) * self.cell_size_m
        ang = math.radians(h["angle_deg"])
        x = dx * math.cos(ang) + dy * math.sin(ang)
        y = -dx * math.sin(ang) + dy * math.cos(ang)
        return (x / a) ** 2 + (y / b) ** 2 < 1.0

    def _path_with_eta(self, path: list, t: int) -> list[tuple[tuple[float, float], float]]:
        """Fiecare punct al traseului cu minutul estimat de sosire (viteză pe teren plat)."""
        speed_cells_min = self._flat_speed_ms() * 60.0 / self.cell_size_m
        out, eta = [], float(t + (self.dwell_left or 0))
        if self.wait_until is not None:
            eta = max(eta, float(self.wait_until))
        prev = path[0]
        for p in path:
            eta += _dist(prev, p) / speed_cells_min
            out.append((p, eta))
            prev = p
        return out

    def _hits(self, h: dict, path: list, t: int) -> float | None:
        """Minutul primului contact dintre traseu și pericol, sau None."""
        try:
            pts = self._path_with_eta(path, t)
            hz = core_hazards.from_contract(self._hazard_contract(h, t), self.cell_size_m, t)
            hit, eta = core_hazards.route_hit([_cell(p) for p, _ in pts], [e for _, e in pts], [hz], self.cell_size_m)
            return eta if hit else None
        except NotImplementedError:
            pass
        for p, eta in self._densify(path, t):
            if eta - t > HIT_HORIZON_MIN:
                break
            if self._inside(h, p, eta):
                return eta
        return None

    def _densify(self, path: list, t: int, step_cells: float = 5.0):
        """Puncte la fiecare ~100 m pe traseu, cu ETA, ca verificarea să nu sară peste pericol."""
        pts = self._path_with_eta(path, t)
        if not pts:
            return
        yield pts[0]
        for (a, ea), (b, eb) in zip(pts, pts[1:]):
            n = max(1, int(_dist(a, b) / step_cells))
            for i in range(1, n + 1):
                f = i / n
                yield ((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), ea + (eb - ea) * f)

    def _expire_hazards(self, t: int) -> None:
        rows, cols = self._meta.get("shape", [500, 500])

        def gone(h):
            r, c = self._hazard_center(h, t)
            margin = max(h["axes_m"]) / self.cell_size_m
            return r < -margin or r > rows + margin or c < -margin or c > cols + margin

        self.hazards = [h for h in self.hazards if not gone(h)]

    # ------------------------------------------------------------------ decizie

    def _check_hazards(self, t: int) -> dict | None:
        if not self.hazards or self.pos is None:
            return None
        path = [self.pos] + self.remaining
        hits = []
        for h in self.hazards:
            eta = self._hits(h, path, t)
            if eta is not None:
                hits.append((eta, h))
        if not hits:
            return None
        eta, h = min(hits, key=lambda x: (x[0], x[1]["id"]))
        if t - self._last_eval_t.get(h["id"], -10**9) < REEVAL_MIN:
            return None
        self._last_eval_t[h["id"]] = t
        return self._decide(t, h, eta)

    def _decide(self, t: int, h: dict, eta: float) -> dict | None:
        alts = self._alternatives(t, h)
        decision = choose(alts, self.preset, self.limits)
        key = (decision.decision, decision.alternative_id, h["id"])
        if key == self._last_decision_key:
            return None
        self._last_decision_key = key
        self._apply_decision(decision, t)

        decision_id = f"d_{t}"
        eta_min = max(0, int(round(eta - t)))
        summary = build_summary(decision, t_min=t, hazard_kind=h["kind"], eta_hazard_min=eta_min, limits=self.limits)
        self._explain_queue.append({"decision_id": decision_id, "t_min": t, "summary": summary})
        return {
            "type": "decision",
            "decision_id": decision_id,
            "t_min": t,
            "decision": decision.decision,
            "alternative_id": decision.alternative_id,
            "reason_code": decision.reason_code,
            "hazard_id": h["id"],
            "eta_hazard_min": eta_min,
            "alternatives": [self._alt_json(a) for a in decision.alternatives],
            "explanation": None,
        }

    def _alternatives(self, t: int, h: dict) -> list[Alternative]:
        if self._site is not None:
            try:
                core_hz = [core_hazards.from_contract(self._hazard_contract(x, t), self.cell_size_m, t) for x in self.hazards]
                return core_alternatives.generate(
                    self._site, _cell(self.pos), list(self.remaining), [s["id"] for s in self.stops_left],
                    core_hz, t, self.o2_pct, self.dose_msv, self.sunset_min, self.preset,
                )
            except NotImplementedError:
                pass
        return self._fallback_alternatives(t, h)

    def _fallback_alternatives(self, t: int, h: dict) -> list[Alternative]:
        """Varianta minimă fără rolul 2: continuă, așteaptă sau întoarce-te pe drumul parcurs."""
        regional = h["kind"] == "regional_storm"
        dose_rate = self._sensors(t)["dose_rate_usv_h"]

        def dose_after(minutes):
            return self.dose_msv + dose_rate * minutes / 60.0 / 1000.0

        here = _cell(self.pos)
        walk, dwell = self._remaining_minutes()
        cont_o2 = self._o2_after(walk, dwell)
        current = Alternative(
            id="current", kind="CONTINUE", path=[here] + list(self.remaining), extra_min=0,
            o2_end_pct=cont_o2, dose_msv=dose_after(walk + dwell), risk=0.8,
            arrival_habitat_min=t + walk + dwell, sunset_min=self.sunset_min, crosses_hazard=True,
        )
        wait = Alternative(
            id="wait", kind="WAIT", path=[here], extra_min=DEFAULT_WAIT_MIN,
            o2_end_pct=cont_o2 - O2_PCT_PER_MIN_REST * DEFAULT_WAIT_MIN,
            dose_msv=dose_after(walk + dwell + DEFAULT_WAIT_MIN), risk=0.9 if regional else 0.3,
            arrival_habitat_min=t + walk + dwell + DEFAULT_WAIT_MIN, sunset_min=self.sunset_min, crosses_hazard=regional,
        )
        back = [here] + [p for p in reversed(self.traveled) if p != here]
        back_walk = _polyline_len(back) * self.cell_size_m / self._flat_speed_ms() / 60.0
        values = {tg["id"]: float(tg.get("science_value", 1)) for tg in self._meta.get("targets", [])}
        planned = [s["id"] for s in self.route.get("stops", [])] if self.route else []
        total = sum(values.get(s, 1.0) for s in planned) or 1.0
        lost = [s["id"] for s in self.stops_left]
        ret = Alternative(
            id="return", kind="RETURN", path=back, extra_min=0,
            o2_end_pct=self._o2_after(back_walk, 0), dose_msv=dose_after(back_walk), risk=0.05,
            arrival_habitat_min=t + back_walk, sunset_min=self.sunset_min,
            science_lost=lost, science_lost_value=sum(values.get(s, 1.0) for s in lost) / total,
        )
        if self.returning:
            return [current, wait]  # deja pe drumul de întoarcere
        return [current, wait, ret]

    def _apply_decision(self, decision: Decision, t: int) -> None:
        alt = next((a for a in decision.alternatives if a.id == decision.alternative_id), None)
        if alt is None or decision.decision == "CONTINUE":
            return
        if decision.decision == "WAIT":
            self.wait_until = t + int(round(alt.extra_min))
            return
        here = _cell(self.pos)
        path = [_cell(p) for p in alt.path]
        self.remaining = path[1:] if path and path[0] == here else path
        if decision.decision in ("RETURN", "EMERGENCY"):
            self.returning = True
            self.stops_left = []
            self.dwell_left = 0
            self.wait_until = None

    @staticmethod
    def _alt_json(a: Alternative) -> dict:
        out = {
            "id": a.id, "kind": a.kind, "valid": a.valid, "violations": list(a.violations),
            "extra_min": int(round(a.extra_min)), "o2_end_pct": round(a.o2_end_pct, 1),
            "dose_msv": round(a.dose_msv, 2), "risk": round(a.risk, 2),
            "path": [list(_cell(p)) for p in a.path],
        }
        if a.science_lost:
            out["science_lost"] = list(a.science_lost)
        return out

    # ------------------------------------------------------------------ mesaje

    def _tick_message(self, t: int, sensors: dict, speed: float) -> dict:
        walk, dwell = self._remaining_minutes()
        budget = self.route.get("budget", {}) if self.route else {}
        msg = {
            "type": "tick",
            "t_min": t,
            "astronaut": {"row": round(self.pos[0], 1), "col": round(self.pos[1], 1), "speed_ms": round(speed, 2)},
            "sensors": {
                "o2_pct": round(self.o2_pct, 1),
                "dust_tau": sensors["dust_tau"],
                "wind_ms": sensors["wind_ms"],
                "temp_c": sensors["temp_c"],
                "pressure_pa": sensors["pressure_pa"],
                "dose_rate_usv_h": round(sensors["dose_rate_usv_h"], 1),
                "dose_total_msv": round(self.dose_msv, 3),
            },
            "hazards": [self._hazard_contract(h, t) for h in self.hazards],
            "route_id": self.route.get("route_id") if self.route else None,
            "remaining_path": [list(_cell(self.pos))] + [list(p) for p in self.remaining],
            "budget": {
                "o2_end_pct": round(self._o2_after(walk, dwell), 1),
                "return_by_min": budget.get("return_by_min", self.sunset_min - self.limits.sunset_margin_min),
                "sunset_min": self.sunset_min,
            },
            "point_of_no_return": self.route.get("point_of_no_return") if self.route else None,
        }
        self.last_tick = msg
        return msg

    def _check_end(self, t: int) -> list[dict]:
        end = None
        if self.o2_pct <= 0:
            end = "o2_depleted"
        elif not self.remaining and self.dwell_left == 0 and self.wait_until is None:
            end = "egress_complete"
        elif t >= MAX_DURATION_MIN:
            end = "time_limit"
        if end is None:
            return []
        self.state = "finished"
        return [{"type": "event", "t_min": t, "event": end, "severity": "info", "params": {
            "o2_pct": round(self.o2_pct, 1), "dose_total_msv": round(self.dose_msv, 3)}}]

    # ------------------------------------------------------------------ explicații

    def take_explain_jobs(self) -> list[dict]:
        jobs, self._explain_queue = self._explain_queue, []
        return jobs

    async def explain_job(self, job: dict) -> dict:
        try:
            out = await self.explain_fn(job["summary"])
        except Exception as exc:  # explicația nu are voie să oprească motorul
            log.warning("Explicația a eșuat: %s", exc)
            from app.llm import templates

            out = {"text": templates.render(job["summary"]["decision"], **job["summary"]), "source": "template"}
        return {"type": "explanation", "decision_id": job["decision_id"], "t_min": job["t_min"],
                "source": out["source"], "text": out["text"]}

    async def explain_pending(self) -> list[dict]:
        """Rulează toate explicațiile în așteptare (folosit în teste)."""
        return [await self.explain_job(j) for j in self.take_explain_jobs()]

    # ------------------------------------------------------------------ publicare

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        if self.last_tick is not None:
            q.put_nowait(self.last_tick)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, msg: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning("Client WebSocket prea lent, mesaj aruncat.")

    async def _explain_and_publish(self, job: dict) -> None:
        self.publish(await self.explain_job(job))

    async def run(self) -> None:
        """Bucla de fundal: un tick la fiecare 1/clock_speed secunde cât timp rulează."""
        tasks: set[asyncio.Task] = set()
        while True:
            if self.state != "running":
                await asyncio.sleep(0.05)
                continue
            try:
                for msg in self.step():
                    self.publish(msg)
            except Exception:
                log.exception("Eroare în step(); simularea e pusă pe pauză.")
                self.state = "paused"
            for job in self.take_explain_jobs():
                task = asyncio.create_task(self._explain_and_publish(job))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            await asyncio.sleep(1.0 / max(self.clock_speed, 0.1))


engine = LiveEngine()


async def mock_stream(interval_s: float = 1.0) -> AsyncIterator[dict]:
    messages = _contract("live_messages.json")
    while True:
        for msg in messages:
            yield msg
            await asyncio.sleep(interval_s)
