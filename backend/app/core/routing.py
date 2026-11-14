"""Căutarea traseelor pe grilă.

- A*: traseul inițial habitat -> țintă
- A* spațiu-timp: ocolirea unui pericol care se mișcă
- Dijkstra invers: costul de întoarcere din orice celulă (punct de neîntoarcere, rută de urgență)

Conectivitate 8 vecini. Costul unei mutări între celulele a și b:

    lungimea pasului (1 sau √2) × (cost[a] + cost[b]) / 2

adică jumătate de pas în fiecare celulă. Costul e același în ambele sensuri, deci drumul optim
de la X la habitat e inversul drumului optim de la habitat la X, iar Dijkstra invers și A* dau
aceleași trasee.

Fără tăierea colțurilor: o mutare pe diagonală e permisă doar dacă ambele celule ortogonale pe
lângă care trece sunt finite. Altfel traseul s-ar strecura printre două obstacole lipite pe
diagonală, iar un obstacol de 20 m nu se traversează pe colț.
"""

import heapq
import math
from collections.abc import Callable

import numpy as np

from app.core.grid import SQRT2, neighbor_moves, pad_and_flatten, to_cell, to_flat
from app.core.types import Cell


def _check_inside(name: str, cell: Cell, shape: tuple[int, int]) -> None:
    if not (0 <= cell[0] < shape[0] and 0 <= cell[1] < shape[1]):
        raise ValueError(f"Celula {name} {tuple(cell)} e în afara grilei {shape[0]}×{shape[1]}.")


def _half_step_moves(Wp: int) -> tuple[tuple[int, float, int, int], ...]:
    """Mutările din grid.neighbor_moves, cu lungimea pasului deja înjumătățită.

    Costul unei mutări e pas × media celor două celule = (pas / 2) × (cost[a] + cost[b]).
    """
    return tuple((delta, step * 0.5, side_a, side_b) for delta, step, side_a, side_b in neighbor_moves(Wp))


def _check_no_negative(cost: np.ndarray) -> float:
    """Costul minim finit al hărții (inf dacă nu există celule finite). Negativ -> ValueError."""
    finite = cost[np.isfinite(cost)]
    min_cost = float(finite.min()) if finite.size else math.inf
    if min_cost < 0:
        raise ValueError(f"Harta de cost are valori negative (minim {min_cost}).")
    return min_cost


def astar(cost: np.ndarray, start: Cell, goal: Cell) -> list[Cell] | None:
    """Cel mai ieftin traseu start -> goal, sau None dacă nu există.

    Întoarce lista de celule (row, col), cu start și goal incluse; `[start]` dacă start == goal.
    Euristica e distanța octilă × costul minim finit al hărții: nu supraestimează niciodată,
    deci traseul e optim. Coada e ordonată după (f, g, index), adică (f, g, row, col), ca
    rezultatul să fie identic la fiecare rulare.

    None: start sau goal e pe o celulă interzisă, ori cele două sunt izolate una de alta.
    ValueError: start sau goal în afara grilei, ori costuri negative.
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
    if flat[start_idx] == inf or flat[goal_idx] == inf:
        return None
    if start_idx == goal_idx:
        return [start]

    min_cost = _check_no_negative(cost)  # finit: există cel puțin celulele de start și țintă

    moves = _half_step_moves(Wp)
    diagonal_extra = SQRT2 - 1.0
    goal_row, goal_col = divmod(goal_idx, Wp)

    g_score = [inf] * len(flat)
    parent = [-1] * len(flat)
    g_score[start_idx] = 0.0

    # Intrările din coadă sunt (f, g, index). Indexul plat crește cu (row, col), deci ordinea e
    # exact cea cerută: (f, g, row, col).
    heap = [(0.0, 0.0, start_idx)]
    push, pop = heapq.heappush, heapq.heappop
    found = False

    while heap:
        _, g_current, current = pop(heap)
        # Eliminare leneșă: o intrare veche, cu g mai mare decât cel deja știut, se sare.
        if g_current > g_score[current]:
            continue
        if current == goal_idx:
            found = True
            break
        current_cost = flat[current]

        for delta, half_step, side_a, side_b in moves:
            neighbor = current + delta
            cell_cost = flat[neighbor]
            # Sărim: celulă interzisă sau pe bordură (în afara hărții), ori diagonală care ar
            # tăia colțul unei celule interzise. La mutările drepte laturile sunt celula curentă.
            if cell_cost == inf or flat[current + side_a] == inf or flat[current + side_b] == inf:
                continue
            g_new = g_current + half_step * (current_cost + cell_cost)
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

    Rulează o dată per hartă. Întoarce (cost_to_home, parent_index), ambele de forma grilei:

    - `cost_to_home` (float64): costul celui mai ieftin drum până la habitat; 0 la habitat,
      `inf` unde nu se poate ajunge (celulă interzisă sau izolată);
    - `parent_index` (int32): indexul plat, fără bordură (row × W + col), al pasului următor
      spre casă; -1 la habitat și la celulele din care nu se poate ajunge.

    Aceleași reguli ca la `astar` (costul mutării, fără tăierea colțurilor), deci `path_home`
    dă exact inversul traseului pe care A* îl găsește de la habitat.

    Utilizare dublă: grila de intrare nu trebuie să fie „costul”. Cu o grilă de O₂ pe celulă,
    rezultatul e O₂-ul necesar ca să ajungi acasă din orice punct; cu o grilă de minute pe
    celulă, e timpul până acasă. În ambele cazuri drumul ales e cel care minimizează acea mărime.

    ValueError: habitat în afara grilei, ori valori negative.
    """
    habitat = (int(habitat[0]), int(habitat[1]))
    _check_inside("habitat", habitat, cost.shape)
    _check_no_negative(cost)
    height, width = cost.shape

    flat, Wp = pad_and_flatten(cost)
    inf = math.inf
    dist = [inf] * len(flat)
    parent = [-1] * len(flat)
    habitat_idx = to_flat(habitat, Wp)

    if flat[habitat_idx] != inf:
        dist[habitat_idx] = 0.0
        # Intrările sunt (distanță, index): la distanțe egale iese întâi indexul mai mic.
        heap = [(0.0, habitat_idx)]
        push, pop = heapq.heappush, heapq.heappop
        moves = _half_step_moves(Wp)

        while heap:
            d_current, current = pop(heap)
            if d_current > dist[current]:  # eliminare leneșă
                continue
            current_cost = flat[current]

            for delta, half_step, side_a, side_b in moves:
                neighbor = current + delta
                cell_cost = flat[neighbor]
                if cell_cost == inf or flat[current + side_a] == inf or flat[current + side_b] == inf:
                    continue
                d_new = d_current + half_step * (current_cost + cell_cost)
                if d_new < dist[neighbor]:
                    dist[neighbor] = d_new
                    parent[neighbor] = current
                    push(heap, (d_new, neighbor))

    # Înapoi la forma grilei, fără bordură.
    cost_to_home = np.array(dist, dtype=np.float64).reshape(height + 2, Wp)[1:-1, 1:-1].copy()
    padded_parent = np.array(parent, dtype=np.int64).reshape(height + 2, Wp)[1:-1, 1:-1]
    # Indexul din lista cu bordură -> index plat fără bordură (row × W + col).
    unpadded = (padded_parent // Wp - 1) * width + (padded_parent % Wp - 1)
    parent_index = np.where(padded_parent >= 0, unpadded, -1).astype(np.int32)
    return cost_to_home, parent_index


def path_home(parent_index: np.ndarray, start: Cell) -> list[Cell]:
    """Reconstruiește ruta de întoarcere din rezultatul lui reverse_dijkstra.

    Întoarce celulele de la `start` până la habitat, cu ambele capete; `[habitat]` dacă start e
    chiar habitatul. Listă goală dacă din `start` nu se poate ajunge acasă.

    Caz limită: un habitat complet izolat (niciun vecin accesibil) nu poate fi deosebit, doar
    din `parent_index`, de o celulă inaccesibilă, deci și pentru el rezultatul e listă goală.

    RuntimeError dacă părinții formează un ciclu (tablou corupt): se fac cel mult H × W pași.
    """
    if parent_index.ndim != 2:
        raise ValueError(f"parent_index trebuie să fie 2D, am primit {parent_index.ndim}D.")
    start = (int(start[0]), int(start[1]))
    _check_inside("start", start, parent_index.shape)
    height, width = parent_index.shape

    row, col = start
    nxt = int(parent_index[row, col])
    if nxt == -1:
        # -1 înseamnă fie habitatul, fie o celulă din care nu se poate ajunge acasă. Habitatul
        # e cel spre care arată cel puțin un vecin; spre o celulă inaccesibilă nu arată nimeni.
        own_index = row * width + col
        neighborhood = parent_index[max(row - 1, 0) : row + 2, max(col - 1, 0) : col + 2]
        return [start] if bool((neighborhood == own_index).any()) else []

    path = [start]
    for _ in range(height * width):
        row, col = divmod(nxt, width)
        path.append((row, col))
        nxt = int(parent_index[row, col])
        if nxt == -1:
            return path
    raise RuntimeError("parent_index conține un ciclu: ruta spre casă nu se termină.")
