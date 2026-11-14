"""Căutarea traseelor pe grilă.

- A*: traseul inițial habitat -> țintă
- A* spațiu-timp: ocolirea unui pericol care se mișcă
- Dijkstra invers: costul de întoarcere din orice celulă (punct de neîntoarcere, rută de urgență)

Conectivitate 8 vecini. Costul unei mutări = lungimea pasului (1 sau √2) × cost[celulă].
„Celulă” = celula în care INTRI. Costul celulei de start nu contează, deci astronautul poate
pleca și dintr-o celulă devenită între timp interzisă (de exemplu acoperită de un pericol).
"""

import heapq
import math
from collections.abc import Callable

import numpy as np

from app.core.grid import NEIGHBORS, SQRT2, pad_and_flatten, to_cell, to_flat
from app.core.types import Cell


def _check_inside(name: str, cell: Cell, shape: tuple[int, int]) -> None:
    if not (0 <= cell[0] < shape[0] and 0 <= cell[1] < shape[1]):
        raise ValueError(f"Celula {name} {tuple(cell)} e în afara grilei {shape[0]}×{shape[1]}.")


def astar(cost: np.ndarray, start: Cell, goal: Cell) -> list[Cell] | None:
    """Cel mai ieftin traseu start -> goal, sau None dacă nu există.

    Întoarce lista de celule (row, col), cu start și goal incluse. Euristica e distanța octilă ×
    costul minim al hărții: nu supraestimează niciodată, deci traseul e optim. Coada e ordonată
    după (f, g, row, col), ca rezultatul să fie identic la fiecare rulare.

    None: ținta e pe o celulă interzisă sau e izolată de start. ValueError: start sau goal în
    afara grilei, ori costuri negative.
    """
    # int simplu, nu întreg numpy: altfel tot calculul de indici (și traseul întors) ar fi numpy.
    start = (int(start[0]), int(start[1]))
    goal = (int(goal[0]), int(goal[1]))
    _check_inside("start", start, cost.shape)
    _check_inside("goal", goal, cost.shape)

    flat, Wp = pad_and_flatten(cost)
    start_idx = to_flat(start, Wp)
    goal_idx = to_flat(goal, Wp)
    inf = math.inf
    if flat[goal_idx] == inf:
        return None
    if start_idx == goal_idx:
        return [start]

    finite = cost[np.isfinite(cost)]
    min_cost = float(finite.min())  # există cel puțin celula țintă
    if min_cost < 0:
        raise ValueError(f"Harta de cost are valori negative (minim {min_cost}).")

    neighbors = NEIGHBORS(Wp)
    diagonal_extra = SQRT2 - 1.0
    goal_row, goal_col = divmod(goal_idx, Wp)

    g_score = [inf] * len(flat)
    parent = [-1] * len(flat)
    closed = bytearray(len(flat))
    g_score[start_idx] = 0.0

    # Intrările din coadă sunt (f, g, index). Indexul plat crește cu (row, col), deci ordinea e
    # exact cea cerută: (f, g, row, col).
    heap = [(0.0, 0.0, start_idx)]
    push, pop = heapq.heappush, heapq.heappop
    found = False

    while heap:
        _, g_current, current = pop(heap)
        if closed[current]:
            continue
        if current == goal_idx:
            found = True
            break
        closed[current] = 1

        for delta, step in neighbors:
            neighbor = current + delta
            cell_cost = flat[neighbor]
            if cell_cost == inf:  # interzisă sau pe bordură (în afara hărții)
                continue
            g_new = g_current + step * cell_cost
            if g_new < g_score[neighbor]:
                g_score[neighbor] = g_new
                parent[neighbor] = current
                row, col = divmod(neighbor, Wp)
                d_row = row - goal_row if row > goal_row else goal_row - row
                d_col = col - goal_col if col > goal_col else goal_col - col
                if d_row > d_col:
                    octile = d_row + diagonal_extra * d_col
                else:
                    octile = d_col + diagonal_extra * d_row
                push(heap, (g_new + min_cost * octile, g_new, neighbor))

    if not found:
        return None

    path = []
    idx = goal_idx
    while idx != -1:
        path.append(to_cell(idx, Wp))
        idx = parent[idx]
    path.reverse()
    return path


def astar_spacetime(
    cost: np.ndarray,
    start: Cell,
    goal: Cell,
    t0_min: float,
    blocked_at: Callable[[float], np.ndarray],
    minutes_per_cell: np.ndarray,
    horizon_min: float = 60,
) -> list[tuple[Cell, float]] | None:
    """Traseu care evită celulele blocate la momentul la care astronautul ar ajunge în ele.

    `blocked_at(t_min)` întoarce o mască bool (pericolul prezis la t). Starea e (celulă, timp
    discretizat). Include și acțiunea „aștept pe loc”, ca WAIT să iasă natural.

    TODO (rolul 2). Dacă e prea lent: orizont mai scurt sau grilă de 100 m.
    """
    raise NotImplementedError


def reverse_dijkstra(cost: np.ndarray, habitat: Cell) -> tuple[np.ndarray, np.ndarray]:
    """Costul de întoarcere la habitat din fiecare celulă + părinții pentru reconstruirea rutei.

    Rulează o dată per hartă. Întoarce (cost_to_home, parent_index).

    TODO (rolul 2).
    """
    raise NotImplementedError


def path_home(parent_index: np.ndarray, start: Cell) -> list[Cell]:
    """Reconstruiește ruta de întoarcere din rezultatul lui reverse_dijkstra."""
    raise NotImplementedError
