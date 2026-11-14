"""Generatorul de scenarii: serii de timp pentru praf, vânt, temperatură, radiație + furtuni.

Valorile se calibrează pe Perseverance MEDA, Curiosity REMS și RAD (rolul 1 dă intervalele).
Seed fix -> scenarii reproductibile. În prezentare: „scenarii simulate, calibrate pe MEDA, REMS și RAD”.
"""

from dataclasses import dataclass, field

# TODO (rolul 1): înlocuiește cu valori calibrate și sursa lor.
BASELINE = {
    "dust_tau": 0.6,
    "wind_ms": 6.0,
    "temp_c": -40.0,
    "pressure_pa": 720.0,
    "dose_rate_usv_h": 10.0,  # ordinul de mărime raportat de RAD la suprafață
}


@dataclass
class ScheduledEvent:
    t_min: float
    event: str
    params: dict = field(default_factory=dict)


@dataclass
class Scenario:
    seed: int
    duration_min: int
    sensors: list[dict]  # un dict pe minut
    events: list[ScheduledEvent]


def generate(seed: int = 42, duration_min: int = 300, events: list[ScheduledEvent] | None = None) -> Scenario:
    """TODO: zgomot corelat (random walk cu numpy.random.default_rng(seed)) + efectul evenimentelor."""
    raise NotImplementedError


DEMO_SCENARIO_EVENTS = [
    ScheduledEvent(72, "local_storm", {"center": {"row": 220, "col": 30}, "axes_m": [1800, 1100], "velocity_ms": [0.0, 2.5], "intensity": 0.7}),
    ScheduledEvent(170, "regional_storm", {"intensity": 0.9}),
]
