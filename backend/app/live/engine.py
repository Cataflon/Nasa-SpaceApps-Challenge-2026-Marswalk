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
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from app.config import CONTRACTS_DIR, DEMO_EVENTS
from app.core import alternatives as core_alternatives
from app.core import hazard_spec as core_spec
from app.core import hazards as core_hazards
from app.core import modes as core_modes
from app.core import replanner as core_replanner
from app.core.benchmark import REACT_WINDOW_MIN
from app.core import budget as core_budget
from app.core.budget import O2_PCT_PER_MIN_REST, EffectWindow, tobler_speed_ms
from app.core.daylight import sunrise_sunset_min
from app.core.planner import SOL_START_UTC
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
# O₂ la mers: același model ca planificatorul (core.budget._walk: puterea din viteza Tobler și din
# urcare), aplicat pe bucata de drum parcursă efectiv în fiecare minut. Înainte motorul folosea 220 W
# fix (0,281 %/min), iar planificatorul ~0,19 %/min pe plat: după ~15 min un plan cu marjă mică primea
# RETURN pe O2_RESERVE fără niciun pericol (notele rolului 2, 14.11).


def walk_rate_pct_per_min(fatigue: float = 1.0) -> float:
    """O₂ consumat pe minut de mers pe teren plat (%/min), după modelul planificatorului."""
    minutes, o2 = core_budget._walk(100.0, 0.0, fatigue)
    return float(o2 / minutes)


O2_PCT_PER_MIN_WALK = walk_rate_pct_per_min()  # ≈ 0,19 %/min pe plat, fără oboseală
SUIT_LEAK_PCT_PER_MIN = 0.15
FATIGUE_SPEED_FACTOR = 0.8
FATIGUE_O2_FACTOR = 1.15
# Rezerva de ultimă instanță; de obicei apusul vine din plan sau se calculează ca în planner
# (daylight + SOL_START_UTC, ≈ 633 min la Jezero pe 14.11.2026), vezi _planned_sunset_min.
DEFAULT_SUNSET_MIN = 420.0
DEFAULT_WAIT_MIN = 30
# Furtuna solară: aceleași valori ca scenariul (× 2,5, Zeitlin et al. 2018). Când există seria
# scenariului, creșterea pe ore și scăderea pe 36 h vin din ea; astea servesc doar fallback-ului.
SOLAR_DOSE_MULTIPLIER = scenario_mod.SOLAR_PARTICLE_EVENT["dose_rate_multiplier"]
SOLAR_DURATION_MIN = int(scenario_mod.SOLAR_PARTICLE_EVENT["duration_min"])

# --- Parametrii motorului ---
RESUME_EVERY_MIN = 5  # pe drumul spre casă după un pericol: cât de des se verifică dacă țintele se pot relua
REEVAL_MIN = 5  # cât de des se reevaluează un pericol care lovește încă traseul
# Bucla pe 3 niveluri (docs/plan-replanificare-live.md §4, „Arhitectura deterministă” §6):
# Nivelul 2 (periodic) folosește K pe mod (core/modes.py: 15 / 5 / 1 / 1), nivelul 3 de proximitate
# `core_modes.PROXIMITY_M`; constantele stau în core (ARHITECTURA_RUTARE_V2 §3, §11).
_STATE_EVENTS = ("suit_leak", "fatigue", "crewmate_injured")
_INJURED_SPEED, _INJURED_O2 = 0.5, 1.5  # = hazard_spec.CLASS_DEFAULTS["crewmate_injured"] (nivel C)
HIT_HORIZON_MIN = 60  # cât de departe în viitor verifică fallback-ul dacă traseul e lovit
MAX_DURATION_MIN = 720  # siguranță: simularea se oprește după 12 ore

# Valori implicite pentru pericolele injectate fără parametri. Furtunile mobile pornesc
# lateral față de traseu și se deplasează spre el, ca să ajungă în ~offset/viteză secunde.
# Mărimi reale (registrul echipei, §3): vârtej de praf mare = 100-135 m diametru, se mișcă odată cu
# vântul (câțiva m/s) -> se poate ocoli; „local_storm” = frontul unei furtuni de praf (celule de
# 20-40 km, 10-20 m/s) -> nu se poate ocoli pe harta de 10 km, decizia e WAIT sau RETURN.
HAZARD_DEFAULTS = {
    "dust_devil": {"axes_m": [65, 65], "speed_ms": 4.0, "intensity": 0.9, "offset_m": 600},
    "local_storm": {"axes_m": [15000, 2500], "angle_deg": 90.0, "speed_ms": 15.0, "intensity": 0.7, "offset_m": 9000},
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
        # step() rulează pe un thread (run), ca o replanificare de ~0,5 s să nu blocheze bucla asyncio
        # (AUDIT-008); comenzile care schimbă starea iau același lock, deci nu apar curse.
        self._lock = threading.RLock()
        self._clear()

    # ------------------------------------------------------------------ control

    def reset(self) -> None:
        with self._lock:
            self._clear()
        self.publish(self.state_message())

    def _clear(self) -> None:
        self.state = "idle"  # idle | running | paused | finished
        self.end_reason: str | None = None  # egress_complete | o2_depleted | time_limit | error
        self.t_min = 0
        self.route: dict | None = None
        self.pos: tuple[float, float] | None = None
        self.remaining: list[Cell] = []
        self.traveled: list[Cell] = []
        self.stops_left: list[dict] = []  # {"id", "cell", "dwell_min"}
        self.returning = False  # pe drumul spre casă (după RETURN sau EMERGENCY)
        # ARHITECTURA_RUTARE_V2 §6.1: faza drumului (OUTBOUND / INBOUND), separată de modul de alertă.
        # INBOUND după RETURN / shelter / EMERGENCY sau după ultima oprire; nu se revine în OUTBOUND.
        # Drumul spre casă se replanifică la fel ca la dus (nu mai există „după RETURN nu mai replanifici”).
        self.phase = "OUTBOUND"
        self._last_switch_t = -math.inf  # ultima schimbare de traseu (histerezis, DWELL_MIN)
        self.mode = core_modes.NOMINAL  # NOMINAL | MONITOR | REACT | EMERGENCY (§3)
        self._seq = 0  # ordinea totală a evenimentelor: (t, seq)
        self._last_hash: str | None = None  # starea canonică la ultima replanificare (reutilizare)
        self._last_periodic = -10**9
        self._was_inside = False
        self._state_event = False
        # Traseul s-a terminat departe de destinație (ex. la un refugiu improvizat): drumul spre casă e
        # pus din nou și tick-ul următor replanifică imediat (nivel 3), în loc să declare sosirea.
        self._force_replan = False
        self._pnr_floor: float | None = None  # V6: marja planului acceptat (calculată o dată, la nevoie)
        self._pnr_floor_ready = False
        self.injured = False
        self.comm_lost = False  # pierderea legăturii: doar semnal, fără opriri noi
        self.o2_pct = 100.0
        self.dose_msv = 0.0
        self.fatigue = 1.0
        self.leak_pct_per_min = 0.0
        self.dose_mult = 1.0
        self.dose_mult_until = -1
        self.wait_until: int | None = None
        self.hold: tuple | None = None  # (celulă, minute): oprirea planificată de un step_back
        self.dwell_left = 0
        self.hazards: list[dict] = []
        self._hazard_counter = 0
        self.pending_events: list[dict] = []
        self.scheduled: list[dict] = []
        self.sensors_series: list[dict] | None = None
        self._scenario = None
        self.sunset_min = DEFAULT_SUNSET_MIN
        self.last_tick: dict | None = None
        self.last_decision: dict | None = None
        self._last_eval_t: dict[str, int] = {}
        self._last_decision_key: tuple | None = None
        self.route_version = 0  # crește la fiecare traseu nou aplicat (REROUTE, RETURN, EMERGENCY)
        self.suspended_stops: list[dict] = []  # țintele lăsate la un RETURN (pentru RESUME, F4)
        self._last_resume_check = -10**9
        self._new_hazards: list[dict] = []  # pericolele apărute în tick-ul curent (nivelul 3)
        self._near: set[str] = set()  # pericolele care au declanșat deja replanificarea de proximitate
        self._last_budget_eval = -10**9
        self._last_problem: str | None = None  # suit_leak / fatigue / solar_particle_event
        self._explain_queue: list[dict] = []
        self._site = None
        self._meta: dict = {}

    def start(self, route_id: str | None = None, speed: float | None = None) -> None:
        """Pornește (sau reia) ieșirea. Fără route_id: ultimul traseu planificat, apoi mock-ul."""
        with self._lock:
            self._start(route_id, speed)

    def _start(self, route_id: str | None, speed: float | None) -> None:
        if speed is not None:
            self.clock_speed = speed
        if self.state in ("paused", "running") and route_id is None:
            self.state, self.end_reason = "running", None  # reia, sau doar schimbă viteza dacă rula deja
            self.publish(self.state_message())
            return
        if route_id is not None:
            route = self.store.get(route_id)
            if route is None:
                raise KeyError(route_id)
        else:
            route = self.store.latest() or {**_contract("route_response.json"), "route_id": "mock"}
        self._clear()
        self.load(route)
        self.state = "running"
        self.publish(self.state_message())

    def pause(self) -> None:
        with self._lock:
            if self.state != "running":
                return
            self.state = "paused"
        self.publish(self.state_message())

    def set_speed(self, speed: float) -> None:
        self.clock_speed = speed
        self.publish(self.state_message())

    def state_message(self) -> dict:
        """Starea simulării, trimisă pe WebSocket la fiecare schimbare (și la conectare)."""
        return {"type": "state", "state": self.state, "t_min": self.t_min, "speed": self.clock_speed,
                "route_id": (self.route or {}).get("route_id"), "reason": self.end_reason}

    def inject(self, event: str, params: dict | None = None) -> None:
        """Evenimentul se aplică la următorul tick, în ordinea (t, seq).

        `params` poate fi formatul vechi (live_event.json) sau un HazardSpec cu `op` add / update / remove
        (ARHITECTURA_RUTARE_V2 §2.2): un update re-ancorează pericolul la poziția curentă și crește `rev`.
        """
        self._seq += 1
        self.pending_events.append({"event": event, "params": dict(params or {}), "seq": self._seq})

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
        self.sunset_min = float(route.get("budget", {}).get("sunset_min") or self._planned_sunset_min())
        self.phase = "OUTBOUND" if self.stops_left else "INBOUND"

        # Evenimentele demo ale sitului curent (Jezero sau sintetic); senzorii le includ deja, deci
        # praful și vântul cresc exact când trece pericolul programat.
        if self._scheduled_override is not None:
            events = list(self._scheduled_override)
        else:
            events = scenario_mod.demo_events(self._meta.get("site_id", "synthetic"))
        try:
            self._scenario = scenario_mod.generate(self.seed, MAX_DURATION_MIN, events)
            self.sensors_series = self._scenario.sensors
        except NotImplementedError:
            self._scenario, self.sensors_series = None, None
        self.scheduled = sorted(
            ({"t_min": int(e.t_min), "event": e.event, "params": dict(e.params), "seq": i}
             for i, e in enumerate(events)),
            key=lambda e: (e["t_min"], e["seq"]),
        )

    # ------------------------------------------------------------------ tick

    def step(self) -> list[dict]:
        """Avansează un minut simulat și întoarce mesajele (tick, event, decision)."""
        with self._lock:
            return self._step()

    def _step(self) -> list[dict]:
        if self.state != "running":
            return []
        self.t_min += 1
        t = self.t_min
        msgs: list[dict] = []

        due = [e for e in self.scheduled if e["t_min"] <= t]
        self.scheduled = [e for e in self.scheduled if e["t_min"] > t]
        for ev in self.pending_events:
            self._add_to_scenario(ev, t)  # cele programate sunt deja în scenariu
        self._new_hazards = []
        self._state_event = False
        # Ordinea totală (t, seq): cele programate (inclusiv din trecut, aplicate acum cu avertisment),
        # apoi cele injectate, în ordinea sosirii.
        for ev in sorted(due, key=lambda e: (e["t_min"], e["seq"])) + sorted(self.pending_events, key=lambda e: e["seq"]):
            msg = self._apply_event(ev, t)
            if ev.get("t_min", t) < t:
                msg["warning"] = "EVENT_IN_PAST"
            msgs.append(msg)
        self.pending_events = []

        sensors = self._sensors(t)
        moving = self._advance_minute()
        speed = self._speed_ms() if moving else 0.0
        walk_min, walk_o2 = self._minute_walk
        rest_min = max(0.0, 1.0 - walk_min)
        self.o2_pct -= walk_o2 * self._o2_factor() + O2_PCT_PER_MIN_REST * rest_min + self.leak_pct_per_min
        self.dose_msv += sensors["dose_rate_usv_h"] / 60.0 / 1000.0
        self._expire_hazards(t)

        msgs.insert(0, self._tick_message(t, sensors, speed))

        decision_msg = self._check_route(t)
        msgs[0]["mode"] = self.mode  # modul calculat de watchdog în acest tick (§3)
        if decision_msg is not None:
            msgs.append(decision_msg)

        msgs.extend(self._check_end(t))
        return msgs

    # ------------------------------------------------------------------ deplasare

    @property
    def cell_size_m(self) -> float:
        return float(self._meta.get("cell_size_m", 20))

    def _speed_ms(self) -> float:
        """Viteza pe segmentul curent (de la poziția reală, nu de la celula rotunjită: rotunjirea
        cădea uneori chiar pe celula următoare, panta ieșea 0 și astronautul urca cu viteza de pe plat)."""
        slope_tan = 0.0
        if self.remaining:
            d = _dist(self.pos, self.remaining[0]) * self.cell_size_m
            if d > 0:
                slope_tan = (self._z(self.remaining[0]) - self._z(self.pos)) / d
        return tobler_speed_ms(slope_tan, self.fatigue)

    def _flat_speed_ms(self) -> float:
        return tobler_speed_ms(0.0, self.fatigue)

    def _z(self, p) -> float:
        """Altitudinea (m) într-un punct fracționar (row, col), interpolată biliniar; 0 fără sit."""
        if self._site is None or "elevation" not in self._site.layers:
            return 0.0
        elev = self._site.layers["elevation"]
        rows, cols = elev.shape
        r = min(max(float(p[0]), 0.0), rows - 1.0)
        c = min(max(float(p[1]), 0.0), cols - 1.0)
        r0, c0 = min(int(r), rows - 2) if rows > 1 else 0, min(int(c), cols - 2) if cols > 1 else 0
        r1, c1 = min(r0 + 1, rows - 1), min(c0 + 1, cols - 1)
        fr, fc = r - r0, c - c0
        top = elev[r0, c0] * (1 - fc) + elev[r0, c1] * fc
        bottom = elev[r1, c0] * (1 - fc) + elev[r1, c1] * fc
        return float(top * (1 - fr) + bottom * fr)

    def _walk_piece(self, a, b) -> tuple[float, float]:
        """(minute, O₂ %) pentru mersul de la a la b, cu modelul planificatorului (fără factori de stare)."""
        d_m = _dist(a, b) * self.cell_size_m
        if d_m <= 0:
            return 0.0, 0.0
        minutes, o2 = core_budget._walk(d_m, self._z(b) - self._z(a), self.fatigue)
        return float(minutes), float(o2)

    def _advance_minute(self) -> bool:
        """Mută astronautul un minut pe traseu. Întoarce True dacă a mers."""
        self._minute_walk = (0.0, 0.0)  # (minute de mers, O₂ %) în acest minut, citite de step()
        if self.wait_until is not None:
            if self.t_min <= self.wait_until:
                return False
            self.wait_until = None
        if self.dwell_left > 0:
            self.dwell_left -= 1
            return False
        if not self.remaining:
            return False

        # Un minut de mers, segment cu segment, fiecare cu viteza și O₂-ul după panta lui
        # (core.budget._walk, exact ca planificatorul): timpul, nu distanța, e bugetul minutului.
        time_left = 1.0  # minute
        walked_min = walked_o2 = 0.0
        while time_left > 1e-9 and self.remaining:
            target = self.remaining[0]
            start = self.pos
            need, o2 = self._walk_piece(start, target)
            if need <= time_left:
                time_left -= need
                self.pos = (float(target[0]), float(target[1]))
                walked_min, walked_o2 = walked_min + need, walked_o2 + o2
                self.remaining.pop(0)
                self.traveled.append(target)
                if self.hold is not None and tuple(self.hold[0]) == tuple(target):
                    self.dwell_left, self.hold = self.dwell_left + int(self.hold[1]), None  # step_back: așteaptă aici
                    break
                stop = next((s for s in self.stops_left if s["cell"] == target), None)
                if stop is not None:
                    self.stops_left.remove(stop)
                    if not self.stops_left:
                        self.phase = "INBOUND"
                    self.dwell_left = stop["dwell_min"]
                    break
            else:
                f = time_left / need  # pe un segment panta e constantă: timp și O₂ proporționale
                self.pos = (start[0] + (target[0] - start[0]) * f, start[1] + (target[1] - start[1]) * f)
                walked_min, walked_o2 = walked_min + time_left, walked_o2 + o2 * f
                time_left = 0.0
        self._minute_walk = (walked_min, walked_o2)
        return True

    def _remaining_walk(self) -> tuple[float, float]:
        """(minute de mers, O₂ % de mers) pe traseul rămas, cu panta fiecărui segment (ca planificatorul)."""
        pts = [self.pos] + self.remaining
        walk_min = walk_o2 = 0.0
        for a, b in zip(pts, pts[1:]):
            m, o = self._walk_piece(a, b)
            walk_min, walk_o2 = walk_min + m, walk_o2 + o
        return walk_min, walk_o2

    def _remaining_minutes(self) -> tuple[float, float]:
        """(minute de mers, minute de oprire) până la capătul traseului curent."""
        walk, _ = self._remaining_walk()
        dwell = self.dwell_left + sum(s["dwell_min"] for s in self.stops_left) + (self.hold[1] if self.hold else 0)
        return walk, dwell

    def _o2_at_end(self, extra_rest_min: float = 0.0) -> tuple[float, float, float]:
        """(O₂ % la capătul traseului, minute de mers, minute de oprire) cu ritmul de acum."""
        walk, walk_o2 = self._remaining_walk()
        dwell = (self.dwell_left + sum(s["dwell_min"] for s in self.stops_left) + extra_rest_min
                 + (self.hold[1] if self.hold else 0))
        return self._o2_after(walk, dwell, walk_o2), walk, dwell

    def _o2_factor(self) -> float:
        return _INJURED_O2 if self.injured else (FATIGUE_O2_FACTOR if self.fatigue < 1 else 1.0)

    def _o2_after(self, walk_min: float, rest_min: float, walk_o2: float | None = None) -> float:
        """O₂ după `walk_min` de mers și `rest_min` de repaus. `walk_o2`: O₂-ul de mers calculat pe
        traseu (cu pantă); lipsă = teren plat."""
        if walk_o2 is None:
            walk_o2 = walk_rate_pct_per_min(self.fatigue) * walk_min
        return (self.o2_pct - walk_o2 * self._o2_factor() - O2_PCT_PER_MIN_REST * rest_min
                - self.leak_pct_per_min * (walk_min + rest_min))

    # ------------------------------------------------------------------ senzori și evenimente

    def _sensors(self, t: int) -> dict:
        if self.sensors_series:
            s = dict(self.sensors_series[min(t, len(self.sensors_series) - 1)])
        else:
            s = dict(scenario_mod.BASELINE)
        if t <= self.dose_mult_until:
            s["dose_rate_usv_h"] = s["dose_rate_usv_h"] * self.dose_mult
        return s

    def _planned_sunset_min(self) -> float:
        """Apusul în minute de la start, calculat ca în planner, pentru un traseu fără budget.sunset_min."""
        center = self._meta.get("center") or {}
        try:
            return float(sunrise_sunset_min(center["lat"], center["lon"], SOL_START_UTC)[1])
        except (KeyError, TypeError, ValueError):
            return DEFAULT_SUNSET_MIN

    def _add_to_scenario(self, ev: dict, t: int) -> None:
        """Un eveniment injectat live intră în scenariu (scenario.with_event): senzorii îl simt de la t."""
        if self._scenario is None or ev["event"] not in scenario_mod.SENSOR_EVENTS:
            return
        params = dict(ev["params"])
        if ev["event"] == "local_storm" and "peak_after_min" not in params and "center" not in params:
            # Frontul implicit pornește la offset_m de traseu: vârful îl simte când ajunge la astronaut.
            d = HAZARD_DEFAULTS["local_storm"]
            params = {**params, "peak_after_min": d["offset_m"] / d["speed_ms"] / 60.0,
                      "axes_m": d["axes_m"], "angle_deg": d["angle_deg"], "velocity_ms": [0.0, d["speed_ms"]]}
        self._scenario = scenario_mod.with_event(self._scenario, scenario_mod.ScheduledEvent(t, ev["event"], params))
        self.sensors_series = self._scenario.sensors

    def _apply_event(self, ev: dict, t: int) -> dict:
        kind, params = ev["event"], ev["params"]
        if "op" in params:
            return self._apply_hazard_op(kind, params, t)
        if kind not in HAZARD_DEFAULTS:
            self._last_problem = kind  # pentru explicația unei replanificări de buget
        if kind in _STATE_EVENTS:
            self._state_event = True  # nivel 3 (§3)
        if kind == "crewmate_injured":
            self.fatigue *= _INJURED_SPEED
            self.injured = True
        elif kind == "comm_loss":
            self.comm_lost = True
        if kind in HAZARD_DEFAULTS:
            self.hazards.append(self._new_hazard(kind, params, t))
            self._new_hazards.append(self.hazards[-1])
        elif kind == "solar_particle_event" and self.sensors_series is None:
            self.dose_mult = float(params.get("dose_rate_multiplier", SOLAR_DOSE_MULTIPLIER))
            self.dose_mult_until = t + int(params.get("duration_min", SOLAR_DURATION_MIN))
        elif kind == "suit_leak":
            self.leak_pct_per_min += float(params.get("leak_pct_per_min", SUIT_LEAK_PCT_PER_MIN))
        elif kind == "fatigue":
            self.fatigue *= float(params.get("speed_factor", FATIGUE_SPEED_FACTOR))
        return {"type": "event", "t_min": t, "event": kind, "severity": params.get("severity", "high"), "params": params}

    def _apply_hazard_op(self, kind: str, params: dict, t: int) -> dict:
        """HazardSpec cu `op` (§2.2): add / update (re-ancorare, rev + 1) / remove. Un update pe un id
        inexistent e un add; un add pe un id existent e un update. Evenimentele de stare ca `kind`
        (ex. crewmate_injured) se aplică astronautului."""
        op, hid = params.get("op"), params.get("id")
        kind = params.get("kind") or kind
        msg = {"type": "event", "t_min": t, "event": kind, "severity": params.get("severity", "high"),
               "params": {k: v for k, v in params.items() if k != "severity"}}
        if kind in _STATE_EVENTS + ("comm_loss",):
            return {**self._apply_event({"event": kind, "params": {}}, t), "params": msg["params"]}
        existing = next((h for h in self.hazards if h["id"] == hid), None)
        if op == "remove":
            if existing is not None:
                self.hazards.remove(existing)
                self._new_hazards.append({**existing, "removed": True})
            else:
                msg["warning"] = core_spec.ERR_UNKNOWN_ID
            return msg
        shape = params.get("shape") if isinstance(params.get("shape"), dict) else {}
        motion = params.get("motion") if isinstance(params.get("motion"), list) else []
        velocity = (motion[-1].get("velocity_ms") if motion and isinstance(motion[-1], dict) else None) \
            or params.get("velocity_ms")
        if existing is not None:  # update (sau add pe un id existent): re-ancorare la poziția curentă
            if op == "add":
                msg["warning"] = core_spec.WARN_ADD_AS_UPDATE
            r, c = self._hazard_center(existing, t)
            existing.update(center0=(r, c), t0=t, rev=existing.get("rev", 1) + 1)
            if shape.get("axes_m") is not None:
                existing["axes_m"] = [float(v) for v in shape["axes_m"]]
            if shape.get("theta_deg") is not None:
                existing["angle_deg"] = float(shape["theta_deg"])
            if velocity is not None:
                existing["velocity_ms"] = [float(velocity[0]), float(velocity[1])]
            if "intensity" in params:
                existing["intensity"] = float(params["intensity"])
            existing["raw"] = {**existing.get("raw", {}), **{k: v for k, v in params.items()
                                                             if k in ("growth", "lifetime", "effects", "uncertainty", "hub_effect")}}
            self._new_hazards.append(existing)
            return msg
        if op == "update":
            msg["warning"] = core_spec.WARN_UPDATE_AS_ADD
        center = shape.get("center") or params.get("center")
        hz_kind = kind if kind in HAZARD_DEFAULTS else "custom"
        d = HAZARD_DEFAULTS.get(hz_kind, HAZARD_DEFAULTS["local_storm"])
        base = {"center": center, "axes_m": shape.get("axes_m") or params.get("axes_m") or d["axes_m"],
                "angle_deg": shape.get("theta_deg", params.get("angle_deg", 0.0)),
                "intensity": params.get("intensity", d["intensity"])}
        if velocity is not None:
            base["velocity_ms"] = velocity
        h = self._new_hazard(hz_kind if hz_kind in HAZARD_DEFAULTS else "local_storm",
                             {k: v for k, v in base.items() if v is not None}, t)
        if hid:
            h["id"] = str(hid)
        h["kind"] = kind
        h["raw"] = {k: v for k, v in params.items() if k in ("growth", "lifetime", "effects", "uncertainty", "hub_effect")}
        self.hazards.append(h)
        self._new_hazards.append(h)
        return msg

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
            "angle_deg": float(params.get("angle_deg", d.get("angle_deg", 0.0))),
            "intensity": float(params.get("intensity", d["intensity"])),
            "velocity_ms": [float(velocity[0]), float(velocity[1])],
            "rev": 1,
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
        # Cât stă pe loc (oprire la țintă sau WAIT), e tot în path[0]: verificăm fiecare minut,
        # altfel un front care trece peste el în timpul opririi nu e văzut.
        out.extend((path[0], float(k)) for k in range(t, int(eta)))
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

        # Pericolele cu durată (ex. zona de cutremur: 60 min, core/hazard_spec.py) expiră: algoritmul nu le
        # mai vede, deci nici harta (tick.hazards) nu le mai desenează.
        ended = {s.id for s in self._specs(t) if math.isfinite(s.end_min) and t > s.end_min}
        self.hazards = [h for h in self.hazards if not gone(h) and h["id"] not in ended]

    # ------------------------------------------------------------------ decizie

    def _contacts(self, t: int) -> list[tuple[float, dict]]:
        """Nivelul 1 (pericole): contactele cu traseul rămas pe H_WATCH, sortate după (minut, id)."""
        if not self.hazards or self.pos is None:
            return []
        path = [self.pos] + self.remaining
        hits = []
        for h in self.hazards:
            eta = self._hits(h, path, t)
            if eta is not None and eta - t <= core_spec.H_WATCH_MIN + 1e-9:
                hits.append((eta, h))
        return sorted(hits, key=lambda x: (x[0], x[1]["id"]))

    def _first_hit(self, t: int) -> tuple[float, dict] | None:
        """Primul contact în fereastra de reacție (H_REACT): acolo se declanșează replanificarea."""
        hits = [(eta, h) for eta, h in self._contacts(t) if eta - t <= REACT_WINDOW_MIN]
        return hits[0] if hits else None

    def _budget_broken(self, t: int) -> bool:
        """Nivelul 1 (buget): cu ritmul de acum (scurgere, oboseală incluse), traseul rămas mai ține?"""
        waiting = max(0, self.wait_until - t) if self.wait_until is not None else 0
        o2_end, walk, dwell = self._o2_at_end(waiting)
        arrival = t + walk + dwell
        return o2_end < self.limits.o2_reserve_pct or arrival > self.sunset_min - self.limits.sunset_margin_min

    def _nearby(self, t: int) -> dict | None:
        """Nivelul 3 (proximitate): primul pericol nou ajuns la < PROXIMITY_M de astronaut."""
        for h in self.hazards:
            if h["id"] in self._near:
                continue
            r, c = self._hazard_center(h, t)
            gap = math.hypot(r - self.pos[0], c - self.pos[1]) * self.cell_size_m - max(h["axes_m"])
            if gap < core_modes.PROXIMITY_M:
                self._near.add(h["id"])
                return h
        return None

    def _check_route(self, t: int) -> dict | None:
        """Bucla pe 3 niveluri (§6). Întoarce mesajul `decision` sau None.

        - nivelul 3, imediat: pericol nou în acest tick, sau pericol la < 450 m;
        - nivelul 1, watchdog: traseul rămas e lovit (cel mult o dată la REEVAL_MIN per pericol)
          sau bugetul nu mai ține (O2 sub rezervă, sosire după apus − marjă);
        - nivelul 2, periodic: la fiecare REPLAN_EVERY_MIN, cât există pericole active.
        Fără sit (fallback-ul fără rolul 2), doar watchdog-ul de pericol, ca înainte.
        """
        if self.pos is None:
            return None
        smart = self._site is not None
        # RESUME: pe drumul spre casă după un pericol, la RESUME_EVERY_MIN și la sosirea acasă (înainte de
        # egress), se verifică dacă țintele lăsate se pot relua.
        if smart and self.suspended_stops and self.returning \
                and (t - self._last_resume_check >= RESUME_EVERY_MIN or not self.remaining):
            self._last_resume_check = t
            msg = self._try_resume(t)
            if msg is not None:
                return msg
        contacts = self._contacts(t)
        hits = [(eta, x) for eta, x in contacts if eta - t <= REACT_WINDOW_MIN]
        hit = hits[0] if hits else None
        inside = any(self._inside(x, self.pos, t) for x in self.hazards)
        entered = inside and not self._was_inside
        self._was_inside = inside
        last = (self.last_decision or {}).get("decision")
        self.mode = core_modes.mode_for(contacts[0][0] - t if contacts else None, inside, self._state_event,
                                        last == "EMERGENCY" and bool(self.hazards))
        trigger, h, eta = None, None, None
        if smart and (self._new_hazards or self._state_event or self._force_replan):
            # Nivel 3: pericol adăugat / actualizat (rev) / șters, eveniment de stare sau traseu terminat
            # departe de destinație.
            self._force_replan = False
            newest = self._new_hazards[-1] if self._new_hazards else None
            trigger = "event"
            eta, h = hit if hit else (None, newest if newest and not newest.get("removed") else None)
        elif smart and entered:
            trigger = "hazard"  # nivel 3: astronautul a intrat într-o amprentă
            eta, h = hit if hit else (None, next(x for x in self.hazards if self._inside(x, self.pos, t)))
        elif hit is not None:
            eta, h = hit
            if t - self._last_eval_t.get(h["id"], -10**9) < REEVAL_MIN:
                return None
            trigger = "hazard"
        elif smart and self._budget_broken(t):
            if t - self._last_budget_eval < REEVAL_MIN:
                return None
            self._last_budget_eval = t
            trigger = "budget"
        elif smart and (near := self._nearby(t)) is not None:
            trigger, h = "proximity", near
        elif smart and self.hazards and core_modes.K_BY_MODE[self.mode] > 0 \
                and t - self._last_periodic >= core_modes.K_BY_MODE[self.mode]:
            trigger = "periodic"  # nivel 2: K adaptiv după mod
            self._last_periodic = t
        if trigger is None:
            return None
        if smart and trigger != "event":
            # Aceeași stare canonică (cu rev) ca la ultima replanificare → se refolosește rezultatul.
            key = self._state_key(t)
            if key == self._last_hash:
                return None
            self._last_hash = key
        if h is not None:
            self._last_eval_t[h["id"]] = t
        return self._decide(t, trigger, h, eta)

    def _state_key(self, t: int) -> str:
        here = _cell(self.pos)
        specs = self._specs(t)
        return core_modes.state_hash(position=here, remaining=self.remaining, stops=[x["id"] for x in self.stops_left],
                                     revisions=[(x.id, x.rev) for x in specs], o2_pct=round(self.o2_pct, 1),
                                     dose_msv=round(self.dose_msv, 3), phase=self.phase, effects=self._effects(t, specs))

    def _specs(self, t: int) -> list:
        """Pericolele motorului ca HazardSpec (ARHITECTURA_RUTARE_V2 §2), cu clasele implicite pe tip."""
        shape = tuple(self._meta.get("shape", [500, 500]))
        out = []
        for h in self.hazards:
            # Furtuna regională respectă cercul desenat (centru, rază, direcție): pericol local, cu nucleu
            # blocat, ca traiectoria ei să fie verificată ca la orice furtună. Dacă acoperă > 60 % din hartă
            # (ex. 30 km, valoarea implicită), normalize o face globală, ca înainte.
            extra = ({"scope": "local", "effects": {"block": "core", "soft_halo": True}}
                     if h["kind"] == "regional_storm" else {})
            res = core_spec.normalize(
                {"id": h["id"], "kind": h["kind"],
                  "shape": {"center": {"row": h["center0"][0], "col": h["center0"][1]}, "axes_m": list(h["axes_m"]),
                            "theta_deg": h["angle_deg"]},
                  "motion": [{"from_min": h["t0"], "velocity_ms": list(h["velocity_ms"])}],
                  "intensity": h["intensity"], "lifetime": {"start_min": h["t0"]}, **extra, **h.get("raw", {})},
                h["kind"], cell_size_m=self.cell_size_m, t_now=h["t0"], shape=shape, hazard_id=h["id"],
                rev=int(h.get("rev", 1)))
            if res.ok:
                out.append(res.spec)
        return out

    def _effects(self, t: int, specs: list) -> list:
        """Efectele active (§2.1, §8.4): ale astronautului (oboseală, scurgere) și ale pericolelor globale.
        Doza furtunii solare vine din senzori (rata curentă), deci nu se mai înmulțește aici."""
        out = []
        if self.fatigue < 1 or self.leak_pct_per_min > 0:
            out.append(EffectWindow(t, speed_mult=self.fatigue, o2_mult=self._o2_factor(),
                                    o2_add_pct_min=self.leak_pct_per_min, source="state"))
        for spec in specs:
            if spec.scope == "global" and spec.kind != "solar_particle_event":
                e = spec.effects
                out.append(EffectWindow(spec.start_min + spec.warning_min, spec.end_min, e.speed_mult, e.o2_mult,
                                        e.o2_add_pct_min, e.dose_mult, e.daylight_shift_min, spec.id))
        return out

    def _replan_state(self, t: int) -> core_replanner.ReplanState:
        """Starea live pentru replanificarea V2: traseul activ de la poziție până acasă, opriri, pericole."""
        here = _cell(self.pos)
        remaining = [here] + [c for i, c in enumerate(self.remaining) if i or c != here]
        specs = self._specs(t)
        waiting = max(0, self.wait_until - t) if self.wait_until is not None else 0
        return core_replanner.ReplanState(
            site=self._site, position=here, remaining_path=remaining, stops=[x["id"] for x in self.stops_left],
            specs=specs, t_now=float(t), o2_pct=self.o2_pct, dose_msv=self.dose_msv, sunset_min=self.sunset_min,
            preset=self.preset, effects=self._effects(t, specs), phase=self.phase,
            dwell_now_min=float(self.dwell_left + waiting), limits=self.limits, last_switch_t=self._last_switch_t,
            dose_rate_usv_h=float(self._sensors(t)["dose_rate_usv_h"]),
            pnr_floor_pct=self._plan_pnr_floor(), hold=self.hold,
        )

    def _plan_pnr_floor(self) -> float | None:
        """Marja O₂ − O₂ până acasă a planului acceptat, de la start, în condiții nominale (V6).

        Un plan CAUTION poate trece de punctul de neîntoarcere chiar de la planificare; fără această
        marjă, copilotul l-ar abandona la primul tick fără niciun pericol."""
        if self._pnr_floor_ready:
            return self._pnr_floor
        self._pnr_floor_ready = True
        if self._site is None or not self.route or not self.route.get("path"):
            return None
        path = [_cell(p) for p in self.route["path"]]
        state = core_replanner.ReplanState(
            site=self._site, position=path[0], remaining_path=path,
            stops=[s["id"] for s in self.route.get("stops", [])], specs=[],
            t_now=float(self.route.get("start_time_min") or 0.0), o2_pct=100.0, dose_msv=0.0,
            sunset_min=self.sunset_min, preset=self.preset, limits=self.limits)
        self._pnr_floor = core_replanner.plan_pnr_margin(state)
        return self._pnr_floor

    def _try_resume(self, t: int) -> dict | None:
        """RESUME (F4, 15.11): după un RETURN / EMERGENCY cauzat de pericol, verifică periodic dacă
        țintele lăsate au redevenit accesibile (pericolul a trecut, O₂-ul și lumina ajung). Replanificarea
        V2 se face ca și cum țintele ar fi încă în plan; dacă alege o variantă validă care le păstrează pe
        toate (nivelul 0, „destinația întâi”), astronautul reia drumul spre ele. Altfel continuă spre casă."""
        saved = (self.stops_left, self.phase)
        self.stops_left, self.phase = list(self.suspended_stops), "OUTBOUND"
        try:
            decision = core_replanner.plan(self._replan_state(t))[0]
        except (NotImplementedError, ValueError, KeyError, AttributeError, IndexError) as exc:
            log.warning("RESUME: replanificarea nu a mers (%s).", exc)
            decision = None
        chosen = next((a for a in decision.alternatives if a.id == decision.alternative_id), None) if decision else None
        if (decision is None or chosen is None or not chosen.valid or chosen.science_lost
                or decision.decision not in ("REROUTE", "WAIT")):
            self.stops_left, self.phase = saved
            return None
        self.suspended_stops, self.returning = [], False
        decision.reason_code = "HAZARD_CLEARED"
        return self._decide(t, "resume", None, None, decision)

    def _choose(self, t: int, h: dict | None) -> Decision:
        """Cu sit: replanificarea V2 din core (ARHITECTURA_RUTARE_V2). Fără sit sau dacă replanificarea
        nu merge (de ex. traseul mock din contract, fără celule vecine): varianta minimă de înainte."""
        if self._site is not None:
            try:
                return core_replanner.plan(self._replan_state(t))[0]
            except (NotImplementedError, ValueError, KeyError, AttributeError, IndexError) as exc:
                log.warning("Replanificarea V2 nu a mers (%s); folosesc varianta minimă.", exc)
        decision = choose(self._alternatives(t, h), self.preset, self.limits)
        decision.phase = self.phase
        return decision

    def _decide(self, t: int, trigger: str, h: dict | None, eta: float | None,
                decision: Decision | None = None) -> dict | None:
        started = time.perf_counter()
        announce = trigger == "event" or decision is not None  # eveniment nou sau decizie dată din afară
        decision = decision or self._choose(t, h)
        # Doar pentru afișare („copilotul a decis în 0,05 s”); nu intră în niciun calcul.
        compute_ms = round((time.perf_counter() - started) * 1000.0, 1)

        chosen = next((a for a in decision.alternatives if a.id == decision.alternative_id), None)
        here = _cell(self.pos)
        active = [here] + [c for i, c in enumerate(self.remaining) if i or c != here]
        same_route = (decision.decision in ("REROUTE", "RETURN", "EMERGENCY") and chosen is not None
                      and [tuple(p) for p in chosen.path] == active)
        if decision.decision == "CONTINUE" or same_route:
            # Traseul rămâne (sau decizia îl alege exact pe cel activ, de ex. RETURN reconfirmat).
            # Se anunță doar ca răspuns la un eveniment nou („am verificat, e ok”); replanificările
            # periodice, de proximitate sau de watchdog care nu schimbă nimic tac.
            if not announce:
                return None
        else:
            self._apply_decision(decision, t)  # traseul nou devine cel activ; vechiul dispare

        key = (decision.decision, decision.alternative_id, h["id"] if h else trigger)
        if key == self._last_decision_key and not announce:
            return None
        self._last_decision_key = key

        decision_id = f"d_{t}"
        eta_min = max(0, int(round(eta - t))) if eta is not None else None
        kind = h["kind"] if h else self._last_problem
        summary = build_summary(decision, t_min=t, hazard_kind=kind, eta_hazard_min=eta_min, limits=self.limits)
        self._explain_queue.append({"decision_id": decision_id, "t_min": t, "summary": summary})
        self.last_decision = {"t_min": t, "decision": decision.decision, "alternative_id": decision.alternative_id,
                              "hazard": kind, "eta_hazard_min": eta_min, "trigger": trigger}
        return {
            "type": "decision",
            "decision_id": decision_id,
            "t_min": t,
            "decision": decision.decision,
            "alternative_id": decision.alternative_id,
            "reason_code": decision.reason_code,
            "trigger": trigger,
            "hazard_id": h["id"] if h else None,
            "eta_hazard_min": eta_min,
            "route_version": self.route_version,
            "phase": decision.phase,
            "flags": list(decision.flags),
            "omitted": [dict(o) for o in decision.omitted],
            "alternatives": [self._alt_json(a) for a in decision.alternatives],
            "compute_ms": compute_ms,
            "explanation": None,
        }

    def _alternatives(self, t: int, h: dict) -> list[Alternative]:
        if self._site is not None:
            try:
                core_hz = [core_hazards.from_contract(self._hazard_contract(x, t), self.cell_size_m, t) for x in self.hazards]
                here = _cell(self.pos)
                # Contractul generate(): remaining_path începe la poziția curentă.
                remaining = [here] + [c for i, c in enumerate(self.remaining) if i or c != here]
                return core_alternatives.generate(
                    self._site, here, remaining, [s["id"] for s in self.stops_left],
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
        cont_o2, walk, dwell = self._o2_at_end()
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
        if getattr(alt, "hold_index", None) is not None and len(alt.path) > 1:
            # step_back: merge până la locul sigur, stă acolo hold_min minute, apoi continuă pe același traseu.
            path = [_cell(p) for p in alt.path]
            here = _cell(self.pos)
            self.remaining = path[1:] if path[0] == here else path
            self.hold = (path[alt.hold_index], int(round(alt.hold_min)))
            self.wait_until = None
            self.route_version += 1
            self._last_switch_t = t
            return
        if decision.decision == "WAIT" or alt.kind == "WAIT":
            # Și sub EMERGENCY: așteptarea pe loc nu înlocuiește traseul (calea ei are o singură celulă;
            # aplicată ca rută, ar goli traseul rămas și misiunea s-ar „termina” pe teren deschis).
            self.wait_until = t + max(1, int(round(alt.extra_min)))
            self._last_switch_t = t
            return
        here = _cell(self.pos)
        path = [_cell(p) for p in alt.path]
        self.remaining = path[1:] if path and path[0] == here else path
        self.wait_until = None
        self.hold = None  # un traseu nou anulează oprirea planificată a unui step_back
        self.route_version += 1
        self._last_switch_t = t
        is_return = decision.decision in ("RETURN", "EMERGENCY") or alt.kind == "RETURN"
        if alt.science_lost and not is_return:  # replan_stops / ocolire care renunță la o oprire
            self.stops_left = [x for x in self.stops_left if x["id"] not in alt.science_lost]
        if is_return:  # țintele se pun deoparte (nu se șterg): RESUME le poate relua după ce trece pericolul
            self.phase = "INBOUND"
            self.returning = True
            self.suspended_stops = self.stops_left + self.suspended_stops
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
        o2_end, _, _ = self._o2_at_end()
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
            "mode": self.mode,
            "remaining_path": [list(_cell(self.pos))] + [list(p) for p in self.remaining],
            "route_version": self.route_version,
            "budget": {
                "o2_end_pct": round(o2_end, 1),
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
            if self._resume_to_destination():
                return []
            end = "egress_complete"
        elif t >= MAX_DURATION_MIN:
            end = "time_limit"
        if end is None:
            return []
        self.state, self.end_reason = "finished", end
        return [{"type": "event", "t_min": t, "event": end, "severity": "info", "params": {
            "o2_pct": round(self.o2_pct, 1), "dose_total_msv": round(self.dose_msv, 3)}},
            self.state_message()]

    def _resume_to_destination(self) -> bool:
        """Traseul rămas e gol, dar astronautul nu e la destinația planului: pune drumul până acolo
        (A* pe costul static; altfel înapoi pe drumul parcurs) și cere o replanificare imediată.
        Întoarce False dacă astronautul e deja la destinație sau nu există sit (fallback-ul vechi)."""
        if self._site is None or not self.route or not self.route.get("path"):
            return False
        here, dest = _cell(self.pos), _cell(self.route["path"][-1])
        if here == dest:
            return False
        path = None
        try:
            from app.core.costmap import static_cost
            from app.core.routing import astar

            path = astar(static_cost(self._site, self.preset), here, dest)
        except (ValueError, IndexError, KeyError):
            path = None
        if not path:
            path = [here] + [p for p in reversed(self.traveled) if p != here]
            if path[-1] != dest:
                path.append(dest)
        self.remaining = path[1:] if path[0] == here else path
        self.route_version += 1
        self.phase = "INBOUND" if not self.stops_left else self.phase
        self._force_replan = True
        return True

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
        q.put_nowait(self.state_message())  # clientul nou află imediat dacă rulează, e pe pauză sau s-a terminat
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
                # Pe un thread: decizia (replanificarea V2) nu oprește bucla și nici UI-ul (AUDIT-008).
                for msg in await asyncio.to_thread(self.step):
                    self.publish(msg)
            except Exception:
                log.exception("Eroare în step(); simularea e pusă pe pauză.")
                self.state, self.end_reason = "paused", "error"
                self.publish(self.state_message())
            for job in self.take_explain_jobs():
                task = asyncio.create_task(self._explain_and_publish(job))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            await asyncio.sleep(1.0 / max(self.clock_speed, 0.1))


# Motorul aplicației: fără evenimentele programate ale scenariului demo, dacă nu sunt cerute (config.DEMO_EVENTS).
engine = LiveEngine(scheduled_events=None if DEMO_EVENTS else [])


async def mock_stream(interval_s: float = 1.0) -> AsyncIterator[dict]:
    messages = _contract("live_messages.json")
    while True:
        for msg in messages:
            yield msg
            await asyncio.sleep(interval_s)
