"""Căutarea traseelor pe grilă.

- A*: traseul inițial habitat -> țintă
- A* spațiu-timp: ocolirea unui pericol care se mișcă
- Dijkstra invers: costul de întoarcere din orice celulă (punct de neîntoarcere, rută de urgență)

Conectivitate 8 vecini. Costul unei mutări = lungimea pasului (1 sau √2) × cost[celulă].
"""

from collections.abc import Callable

import numpy as np

from app.core.types import Cell


def astar(cost: np.ndarray, start: Cell, goal: Cell) -> list[Cell] | None:
    """Cel mai ieftin traseu start -> goal, sau None dacă nu există.

    TODO (rolul 2): heapq + euristica distanță octilă × cost minim.
    Tie-break determinist: (f, g, row, col).
    """
    raise NotImplementedError


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
