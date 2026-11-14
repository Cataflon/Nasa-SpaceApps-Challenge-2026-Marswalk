"""Alegerea și ordinea opririlor științifice cu CP-SAT (OR-Tools).

Problemă de orientare: maximizează valoarea științifică sub limitele de timp și O₂.
Costurile între ținte vin din Dijkstra pe harta de cost (matrice mică, ≤15 ținte).

Determinism: num_workers = 1, random_seed fix, max_deterministic_time (NU max_time_in_seconds).
Plan B: forță brută la ≤6 opriri (`brute_force_stops`).

Problema (aceeași la ambele metode): drumul pornește și se termină la "habitat";
    Σ travel_min + Σ dwell_min ≤ max_duration_min
    o2_start − Σ travel_o2 − Σ dwell × O2_PCT_PER_MIN_REST ≥ o2_reserve
Obiectiv lexicografic: (1) valoarea științifică maximă; (2) la egalitate, durata minimă;
(3) la egalitate, lista de id-uri cea mai mică lexicografic (o listă mai scurtă care e prefix
al alteia e mai mică).

CP-SAT lucrează doar cu întregi, deci ambele metode compară pe aceleași valori scalate, rotunjite
o singură dată: minute × 10, procente O₂ × 100, valoare științifică × 100. Cifrele întoarse în
StopPlan (durată, O₂ final, valoare) sunt recalculate din valorile reale, nerotunjite.
"""

import inspect
import itertools
from dataclasses import dataclass

from app.core.budget import O2_PCT_PER_MIN_REST

HOME = "habitat"
MINUTES_SCALE = 10
O2_SCALE = 100
VALUE_SCALE = 100
MAX_BRUTE_FORCE_TARGETS = 6


@dataclass
class StopPlan:
    order: list[str]  # id-urile țintelor, în ordinea vizitei
    science_value: float
    duration_min: float
    o2_end_pct: float
    optimal: bool


def _scale(x: float, factor: int) -> int:
    return int(round(x * factor))


def _arc(table: dict, a: str, b: str) -> float:
    try:
        return table[(a, b)]
    except KeyError:
        raise KeyError(f"Lipsește arcul ({a!r}, {b!r}) din matricea de deplasare.") from None


class _Problem:
    """Datele problemei, cu ținte sortate și coeficienți întregi calculați o singură dată."""

    def __init__(self, target_ids, science_value, dwell_min, travel_min, travel_o2_pct,
                 max_duration_min, o2_start_pct, o2_reserve_pct):
        self.ids = sorted(target_ids)
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("target_ids conține duplicate.")
        if HOME in self.ids:
            raise ValueError(f"{HOME!r} nu poate fi țintă.")
        self.nodes = [HOME] + self.ids
        self.raw = (science_value, dwell_min, travel_min, travel_o2_pct)
        self.o2_start, self.o2_reserve = o2_start_pct, o2_reserve_pct
        n = len(self.nodes)
        self.travel = [[_scale(_arc(travel_min, a, b), MINUTES_SCALE) if a != b else 0 for b in self.nodes] for a in self.nodes]
        self.o2 = [[_scale(_arc(travel_o2_pct, a, b), O2_SCALE) if a != b else 0 for b in self.nodes] for a in self.nodes]
        self.dwell = [0] + [_scale(dwell_min[t], MINUTES_SCALE) for t in self.ids]
        self.dwell_o2 = [0] + [_scale(dwell_min[t] * O2_PCT_PER_MIN_REST, O2_SCALE) for t in self.ids]
        self.value = [0] + [_scale(science_value[t], VALUE_SCALE) for t in self.ids]
        self.max_duration = _scale(max_duration_min, MINUTES_SCALE)
        self.o2_budget = _scale(o2_start_pct, O2_SCALE) - _scale(o2_reserve_pct, O2_SCALE)
        self.n = n

    def scaled(self, order_idx: list[int]) -> tuple[int, int, int]:
        """(valoare, durată, O₂ consumat) scalate pentru o ordine de indici de noduri (fără habitat)."""
        tour = [0] + order_idx + [0]
        duration = sum(self.travel[a][b] for a, b in zip(tour, tour[1:])) + sum(self.dwell[i] for i in order_idx)
        o2 = sum(self.o2[a][b] for a, b in zip(tour, tour[1:])) + sum(self.dwell_o2[i] for i in order_idx)
        return sum(self.value[i] for i in order_idx), duration, o2

    def feasible(self, duration: int, o2: int) -> bool:
        return duration <= self.max_duration and o2 <= self.o2_budget

    def plan(self, order: list[str], optimal: bool) -> StopPlan:
        """StopPlan cu cifrele reale (nerotunjite) pentru ordinea dată."""
        science_value, dwell_min, travel_min, travel_o2_pct = self.raw
        tour = [HOME] + order + [HOME] if order else []  # turul gol: nicio deplasare
        duration = sum(travel_min[(a, b)] for a, b in zip(tour, tour[1:])) + sum(dwell_min[t] for t in order)
        o2_used = sum(travel_o2_pct[(a, b)] for a, b in zip(tour, tour[1:]))
        o2_used += sum(dwell_min[t] * O2_PCT_PER_MIN_REST for t in order)
        return StopPlan(
            order=list(order),
            science_value=float(sum(science_value[t] for t in order)),
            duration_min=float(duration),
            o2_end_pct=float(self.o2_start - o2_used),
            optimal=optimal,
        )


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
    """Planul optim cu CP-SAT: AddCircuit pe arce booleene, cu buclă pe nod pentru țintele sărite.

    Etapa 1: maximize Σ valoare × BIG − durată (criteriile 1 și 2). Etapa 2, criteriul 3: cu
    valoarea și durata fixate la cele găsite, se alege pas cu pas, de la habitat, nodul următor
    cel mai mic (întâi întoarcerea acasă, apoi id-urile în ordine alfabetică). Statusul etapei 1:
    OPTIMAL → optimal=True, FEASIBLE → False, altfel plan gol.
    """
    from ortools.sat.python import cp_model

    p = _Problem(target_ids, science_value, dwell_min, travel_min, travel_o2_pct,
                 max_duration_min, o2_start_pct, o2_reserve_pct)
    model = cp_model.CpModel()
    n = p.n
    x = {(i, j): model.NewBoolVar(f"x_{i}_{j}") for i in range(n) for j in range(n)}
    model.AddCircuit([(i, j, x[i, j]) for i in range(n) for j in range(n)])
    # Bucla pe habitat = turul gol; atunci toate țintele sunt sărite.
    for i in range(1, n):
        model.AddImplication(x[0, 0], x[i, i])
    visit = [None] + [x[i, i].Not() for i in range(1, n)]

    duration = sum(p.travel[i][j] * x[i, j] for i in range(n) for j in range(n) if i != j)
    duration += sum(p.dwell[i] * visit[i] for i in range(1, n))
    o2_used = sum(p.o2[i][j] * x[i, j] for i in range(n) for j in range(n) if i != j)
    o2_used += sum(p.dwell_o2[i] * visit[i] for i in range(1, n))
    value = sum(p.value[i] * visit[i] for i in range(1, n))
    model.Add(duration <= p.max_duration)
    model.Add(o2_used <= p.o2_budget)

    big = sum(max(row) for row in p.travel) + sum(p.dwell) + 1  # > orice durată posibilă
    model.Maximize(value * big - duration)

    solver = solver_params()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return p.plan([], optimal=False)
    optimal = status == cp_model.OPTIMAL

    # Etapa 2: criteriul lexicografic pe lista de id-uri, cu valoarea și durata fixate.
    model.Add(value == solver.Value(value))
    model.Add(duration == solver.Value(duration))
    order: list[int] = []
    last = 0
    while True:
        candidates = [0] + [j for j in range(1, n) if j not in order and j != last]
        # Rangul: 0 = întoarcerea acasă, apoi țintele în ordinea id-urilor (deja sortate).
        model.Minimize(sum(j * x[last, j] for j in candidates))
        stage = solver_params()
        if stage.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break  # nu ar trebui să se întâmple: soluția din etapa 1 e mereu posibilă
        nxt = next(j for j in candidates if stage.Value(x[last, j]))
        if nxt == 0:
            break
        model.Add(x[last, nxt] == 1)
        order.append(nxt)
        last = nxt
    return p.plan([p.nodes[i] for i in order], optimal=optimal)


def solver_params():
    """Parametrii CP-SAT care fac rezultatul reproductibil."""
    from ortools.sat.python import cp_model

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 42
    solver.parameters.max_deterministic_time = 5.0
    return solver


def brute_force_stops(*args, **kwargs) -> StopPlan:
    """Plan B: încearcă toate permutările tuturor submulțimilor (≤6 ținte → 1957 de ordini).

    Primește aceleași argumente ca plan_stops (poziționale în aceeași ordine sau numite) și
    folosește aceeași problemă, aceleași valori scalate și același obiectiv lexicografic. Lista
    goală e mereu o soluție validă (valoare 0). Peste 6 ținte → ValueError.
    """
    bound = inspect.signature(plan_stops).bind(*args, **kwargs)
    p = _Problem(**bound.arguments)
    if len(p.ids) > MAX_BRUTE_FORCE_TARGETS:
        raise ValueError(f"Forța brută acceptă cel mult {MAX_BRUTE_FORCE_TARGETS} ținte, am primit {len(p.ids)}.")

    best_key, best_order = (0, 0, []), []  # (−valoare, durată, id-uri); turul gol
    for k in range(1, len(p.ids) + 1):
        for order_idx in itertools.permutations(range(1, p.n), k):
            value, duration, o2 = p.scaled(list(order_idx))
            if not p.feasible(duration, o2):
                continue
            order = [p.nodes[i] for i in order_idx]
            key = (-value, duration, order)
            if key < best_key:
                best_key, best_order = key, order
    return p.plan(best_order, optimal=True)
