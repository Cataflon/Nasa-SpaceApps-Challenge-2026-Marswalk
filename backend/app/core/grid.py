"""Reprezentarea grilei pentru căutările cu heapq (A*, Dijkstra, A* spațiu-timp).

Buclele din routing.py rulează în Python pur, deci contează fiecare operație per vecin. Două trucuri:

- grila se aplatizează într-o listă Python (indexarea unei liste e mult mai rapidă decât a unui
  np.ndarray, element cu element);
- în jurul grilei se pune o bordură de o celulă cu cost `inf`. Un vecin din afara hărții cade pe
  bordură și e respins de același test „cost infinit” care respinge și celulele interzise, deci
  nu mai verificăm marginile la fiecare pas.

Convenție: funcțiile primesc și întorc celule `(row, col)` din grila ORIGINALĂ (fără bordură).
Doar indexul plat ține cont de bordură. `Wp` = lățimea grilei cu bordură = W + 2.
"""

import math

import numpy as np

from app.core.types import Cell

SQRT2 = math.sqrt(2.0)


def pad_and_flatten(cost: np.ndarray) -> tuple[list[float], int]:
    """Grila de cost cu bordură de `inf`, aplatizată rând cu rând. Întoarce (listă, Wp).

    NaN (nodata în datele reale) devine `inf`, adică celulă interzisă. Intrarea nu se modifică.
    """
    if cost.ndim != 2:
        raise ValueError(f"Harta de cost trebuie să fie 2D, am primit {cost.ndim}D.")
    height, width = cost.shape
    padded = np.full((height + 2, width + 2), np.inf, dtype=np.float64)
    padded[1:-1, 1:-1] = cost
    padded[np.isnan(padded)] = np.inf
    return padded.ravel().tolist(), width + 2


def to_flat(cell: Cell, Wp: int) -> int:
    """Celulă (row, col) din grila originală -> index în lista cu bordură."""
    return (cell[0] + 1) * Wp + (cell[1] + 1)


def to_cell(idx: int, Wp: int) -> Cell:
    """Index din lista cu bordură -> celulă (row, col) din grila originală."""
    return (idx // Wp - 1, idx % Wp - 1)


def NEIGHBORS(Wp: int) -> tuple[tuple[int, float], ...]:
    """Cei 8 vecini ca (deplasare în indexul plat, lungimea pasului în celule).

    Ordine fixă: N, S, V, E (pas 1), apoi NV, NE, SV, SE (pas √2). Depinde de Wp, de aceea e
    funcție și nu constantă; se apelează o singură dată, înaintea buclei de căutare.
    """
    return (
        (-Wp, 1.0),
        (Wp, 1.0),
        (-1, 1.0),
        (1, 1.0),
        (-Wp - 1, SQRT2),
        (-Wp + 1, SQRT2),
        (Wp - 1, SQRT2),
        (Wp + 1, SQRT2),
    )


def neighbor_moves(Wp: int) -> tuple[tuple[int, float, int, int], ...]:
    """Cei 8 vecini ca (deplasare, lungimea pasului, latură_a, latură_b), pentru regula
    „fără tăierea colțurilor”.

    Pentru o mutare pe diagonală, `latură_a` și `latură_b` sunt deplasările către cele două
    celule ortogonale pe lângă care trece (cea de pe rând și cea de pe coloană). Mutarea e
    permisă doar dacă ambele sunt finite: un obstacol de 20 m nu se traversează pe colț.
    Pentru o mutare dreaptă, laturile sunt 0 (adică celula curentă, mereu finită), ca bucla de
    căutare să aplice același test la toți vecinii. Aceeași ordine ca la NEIGHBORS.
    """
    moves = []
    for delta, step in NEIGHBORS(Wp):
        if step == 1.0:
            moves.append((delta, step, 0, 0))
        else:
            row_part = -Wp if delta < 0 else Wp
            moves.append((delta, step, row_part, delta - row_part))
    return tuple(moves)


def octile(a: Cell, b: Cell) -> float:
    """Distanța octilă între două celule, în celule: cel mai scurt drum cu 8 vecini pe grilă liberă.

    Înmulțită cu costul minim al hărții, e euristica admisibilă pentru A*.
    """
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])
    return max(dr, dc) + (SQRT2 - 1.0) * min(dr, dc)
