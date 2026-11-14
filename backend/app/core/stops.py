"""Alegerea și ordinea opririlor științifice cu CP-SAT (OR-Tools).

Problemă de orientare: maximizează valoarea științifică sub O₂, apus și doză.
Costurile între ținte vin din Dijkstra pe harta de cost (matrice mică, ≤15 ținte).

Determinism: num_workers = 1, random_seed fix, max_deterministic_time (NU max_time_in_seconds).
Plan B: forță brută la ≤6 opriri (`brute_force_stops`).
"""

from dataclasses import dataclass


@dataclass
class StopPlan:
    order: list[str]  # id-urile țintelor, în ordinea vizitei
    science_value: float
    duration_min: float
    o2_end_pct: float
    optimal: bool


def plan_stops(
    target_ids: list[str],
    science_value: dict[str, float],
    dwell_min: dict[str, float],
    travel_min: dict[tuple[str, str], float],  # include "habitat" ca nod
    travel_o2_pct: dict[tuple[str, str], float],
    max_duration_min: float,
    o2_start_pct: float,
    o2_reserve_pct: float,
) -> StopPlan:
    """TODO (rolul 2): cp_model cu AddCircuit (arce opționale, habitat start/final)."""
    raise NotImplementedError


def solver_params():
    """Parametrii CP-SAT care fac rezultatul reproductibil."""
    from ortools.sat.python import cp_model

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 42
    solver.parameters.max_deterministic_time = 5.0
    return solver


def brute_force_stops(*args, **kwargs) -> StopPlan:
    """Plan B: încearcă toate permutările submulțimilor (≤6 ținte)."""
    raise NotImplementedError
