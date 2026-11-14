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


def nearest_exit(cost: np.ndarray, start: Cell, outside: np.ndarray) -> list[Cell] | None:
    """Cel mai ieftin traseu de la `start` până la prima celulă cu `outside` True (Dijkstra).

    Folosit când astronautul e deja în interiorul unui pericol: `cost` include atunci pericolul ca
    termen finit (costmap.hazard_cost), iar `outside` marchează celulele din afara lui. Aceleași
    reguli de mutare ca `astar`; căutarea se oprește la prima celulă exterioară scoasă din coadă,
    deci explorează doar interiorul pericolului. La costuri egale câștigă indexul mai mic
    (row, col), ca rezultatul să fie determinist.

    Întoarce celulele de la start la ieșire (inclusiv); `[start]` dacă startul e deja afară.
    None: startul e interzis sau nu există nicio celulă exterioară accesibilă.
    ValueError: start în afara grilei, forme diferite sau costuri negative.
    """
    start = (int(start[0]), int(start[1]))
    _check_inside("start", start, cost.shape)
    outside = np.asarray(outside, dtype=bool)
    if outside.shape != cost.shape:
        raise ValueError(f"Masca `outside` are forma {outside.shape}, harta are {cost.shape}.")
    _check_no_negative(cost)

    flat, Wp = pad_and_flatten(cost)
    goal = np.pad(outside, 1).ravel().tolist()  # bordura e False: nu e o ieșire
    inf = math.inf
    s_idx = to_flat(start, Wp)
    if flat[s_idx] == inf:
        return None

    dist = {s_idx: 0.0}
    parent = {s_idx: -1}
    heap = [(0.0, s_idx)]
    push, pop = heapq.heappush, heapq.heappop
    moves = _half_step_moves(Wp)
    while heap:
        d_current, current = pop(heap)
        if d_current > dist[current]:
            continue
        if goal[current]:
            path = []
            while current != -1:
                path.append(to_cell(current, Wp))
                current = parent[current]
            return path[::-1]
        current_cost = flat[current]
        for delta, half_step, side_a, side_b in moves:
            neighbor = current + delta
            cell_cost = flat[neighbor]
            if cell_cost == inf or flat[current + side_a] == inf or flat[current + side_b] == inf:
                continue
            d_new = d_current + half_step * (current_cost + cell_cost)
            if d_new < dist.get(neighbor, inf):
                dist[neighbor] = d_new
                parent[neighbor] = current
                push(heap, (d_new, neighbor))
    return None


def astar_spacetime(
    cost: np.ndarray,
    start: Cell,
    goal: Cell,
    t0_min: float,
    blocked_at: Callable[[float], np.ndarray],
    minutes_per_cell: np.ndarray,
    horizon_min: float = 60,
    downsample: int = 1,
) -> list[tuple[Cell, float]] | None:
    """Traseu care evită celulele blocate la momentul la care astronautul ar ajunge în ele.

    `blocked_at(t_min)` întoarce o mască bool (pericolul prezis la t). Starea e (celulă, k), cu
    k = floor(t / DT_MIN), t = minutele de la t0_min. Măștile se calculează o singură dată, câte
    una pe interval: masca k e `blocked_at(t0_min + k × DT_MIN)`, pentru k < K = horizon_min / DT_MIN.

    Mutări: cei 8 vecini (aceleași reguli ca `astar`), care durează exact minutes_per_cell[dest] ×
    pas (timpul nu se rotunjește, doar k); și „aștept pe loc” până la începutul intervalului
    următor, cu costul `_wait_cost` proporțional cu timpul așteptat. O stare e interzisă dacă
    celula e inf în cost sau blocată în intervalul sosirii. Celula de start nu se verifică la
    k = 0 (astronautul e deja acolo).

    Dincolo de orizont (k ≥ K) pericolul nu se mai verifică: căutarea devine un A* obișnuit. E
    corect doar dacă orizontul acoperă trecerea pericolului; orizontul îl alege apelantul.

    `downsample` = f > 1 (plan B pentru viteză): căutarea se face pe blocuri de f × f celule,
    conservator (cost = maximul blocului, inf dacă oricare celulă e inf; blocat dacă oricare
    celulă e blocată; timp = maximul × f), iar traseul se proiectează înapoi pe grila fină prin
    centrele blocurilor, cu Bresenham. Poate închide un pasaj mai îngust decât un bloc.

    Întoarce [(celulă, t_min), ...] de la start la goal; o așteptare apare ca aceeași celulă
    repetată cu timp crescător. None: nicio soluție (de exemplu, totul blocat pe tot orizontul).
    """
    start = (int(start[0]), int(start[1]))
    goal = (int(goal[0]), int(goal[1]))
    _check_inside("start", start, cost.shape)
    _check_inside("goal", goal, cost.shape)
    f = int(downsample)
    if f < 1 or f != downsample:
        raise ValueError(f"downsample trebuie să fie un întreg ≥ 1, am primit {downsample}.")
    if start == goal:
        return [(start, float(t0_min))] if np.isfinite(cost[start]) else None

    K = int(horizon_min // DT_MIN)
    masks = [np.asarray(blocked_at(t0_min + k * DT_MIN), dtype=bool) for k in range(K)]
    minutes = np.asarray(minutes_per_cell, dtype=np.float64)

    if f > 1:
        coarse = _coarsen(cost, minutes, masks, f, start, goal)
        if coarse is not None:
            c_cost, c_minutes, c_masks, c_start, c_goal = coarse
            states = _spacetime_search(c_cost, c_start, c_goal, c_minutes, c_masks, K)
            if states is None:
                return None
            return _project(states, f, start, goal, t0_min, cost.shape)
        # Start și goal în același bloc: distanța e mică, căutăm direct pe grila fină.

    states = _spacetime_search(cost, start, goal, minutes, masks, K)
    if states is None:
        return None
    return [(cell, float(t0_min + t)) for cell, t in states]


# Lungimea unui interval de timp în A* spațiu-timp (minute).
DT_MIN = 1
# C: costul așteptării pe minut = WAIT_COST_FACTOR × costul pe minut al celei mai ieftine celule
# (cost minim / minutele ei). Cu 1,0, a aștepta un minut costă cât a merge un minut pe terenul cel
# mai bun: nici gratuit (altfel A* ar aștepta fără motiv), nici interzis.
WAIT_COST_FACTOR = 1.0


def _wait_cost(min_cost: float, minutes: np.ndarray, cost: np.ndarray) -> float:
    usable = minutes[np.isfinite(cost) & np.isfinite(minutes) & (minutes > 0)]
    min_minutes = float(usable.min()) if usable.size else 1.0
    return WAIT_COST_FACTOR * min_cost / min_minutes * DT_MIN


def _spacetime_search(cost, start, goal, minutes, masks, K):
    """A* pe stări (celulă, interval). Întoarce [((row, col), k), ...] sau None."""
    flat, Wp = pad_and_flatten(cost)
    s_idx, g_idx = to_flat(start, Wp), to_flat(goal, Wp)
    inf = math.inf
    if flat[s_idx] == inf or flat[g_idx] == inf:
        return None
    min_cost = _check_no_negative(cost)
    wait_cost = _wait_cost(min_cost, minutes, cost)

    # Minutele unei mutări drepte / diagonale care intră în celulă. Timpul se ține exact (nu
    # rotunjit la intervale): pe 20 m o celulă ia ≈ 0,4 min, iar rotunjirea la minimum un interval
    # ar umfla timpul de ≈ 2,5 ori și ar verifica pericolul la momente greșite.
    padded_minutes = np.full((cost.shape[0] + 2, Wp), np.inf)
    padded_minutes[1:-1, 1:-1] = minutes
    padded_minutes[~np.isfinite(padded_minutes)] = 0.0  # celulele inf sunt respinse oricum după cost
    time_straight = padded_minutes.ravel().tolist()
    time_diagonal = (padded_minutes * SQRT2).ravel().tolist()
    # Măștile ca bytes aplatizați, cu bordură: indexarea dă direct 0/1, iar memoria rămâne mică.
    blocked = [np.pad(m, 1).astype(np.uint8).tobytes() for m in masks]

    moves = _half_step_moves(Wp)
    diagonal_extra = SQRT2 - 1.0
    goal_row, goal_col = divmod(g_idx, Wp)
    n_cells = len(flat)

    def heuristic(idx: int) -> float:
        row, col = divmod(idx, Wp)
        d_row, d_col = abs(row - goal_row), abs(col - goal_col)
        return min_cost * (d_row + diagonal_extra * d_col if d_row > d_col else d_col + diagonal_extra * d_row)

    # Cheia unei stări: min(k, K) × n_cells + idx, cu k = floor(t / DT_MIN) (un singur întreg;
    # dincolo de orizont, k se comasează). Pentru fiecare cheie se ține timpul exact al celei mai
    # bune sosiri.
    start_key = s_idx
    best = {start_key: 0.0}
    arrival = {start_key: 0.0}
    parent = {start_key: -1}
    closed = set()
    heap = [(heuristic(s_idx), 0.0, 0.0, s_idx)]
    push, pop = heapq.heappush, heapq.heappop

    while heap:
        _, g, t, cur = pop(heap)
        k = int(t // DT_MIN)
        key = (k if k < K else K) * n_cells + cur
        if key in closed or g > best[key]:
            continue
        closed.add(key)
        if cur == g_idx:
            states = []
            while key != -1:
                states.append((to_cell(key % n_cells, Wp), arrival[key]))
                key = parent[key]
            states.reverse()
            return states

        cur_cost = flat[cur]
        for delta, half_step, side_a, side_b in moves:
            nb = cur + delta
            nb_cost = flat[nb]
            if nb_cost == inf or flat[cur + side_a] == inf or flat[cur + side_b] == inf:
                continue
            nt = t + (time_straight[nb] if half_step == 0.5 else time_diagonal[nb])
            nk = int(nt // DT_MIN)
            if nk < K and blocked[nk][nb]:
                continue
            ng = g + half_step * (cur_cost + nb_cost)
            nkey = (nk if nk < K else K) * n_cells + nb
            if ng < best.get(nkey, inf):
                best[nkey], arrival[nkey], parent[nkey] = ng, nt, key
                push(heap, (ng + heuristic(nb), ng, nt, nb))

        # Așteptarea: până la începutul intervalului următor, doar în orizont.
        if k < K:
            nk = k + 1
            if nk < K and blocked[nk][cur]:
                continue
            ng = g + wait_cost * ((nk * DT_MIN - t) / DT_MIN)
            nkey = (nk if nk < K else K) * n_cells + cur
            if ng < best.get(nkey, inf):
                best[nkey], arrival[nkey], parent[nkey] = ng, float(nk * DT_MIN), key
                push(heap, (ng + heuristic(cur), ng, float(nk * DT_MIN), cur))
    return None


def _coarsen(cost, minutes, masks, f, start, goal):
    """Grila de blocuri f × f (conservatoare). None dacă start și goal cad în același bloc."""
    rows, cols = cost.shape
    c_start, c_goal = (start[0] // f, start[1] // f), (goal[0] // f, goal[1] // f)
    if c_start == c_goal:
        return None
    hc, wc = -(-rows // f), -(-cols // f)

    def blocks(arr, fill, reduce):
        padded = np.full((hc * f, wc * f), fill, dtype=arr.dtype)
        padded[:rows, :cols] = arr
        return reduce(padded.reshape(hc, f, wc, f), axis=(1, 3))

    clean = np.where(np.isnan(cost), np.inf, cost)
    c_cost = blocks(clean.astype(np.float64), np.inf, np.max)
    c_minutes = blocks(minutes, np.inf, np.max) * f
    c_masks = [blocks(m, False, np.any) for m in masks]
    # Blocurile de start și de goal iau costul celulei reale, ca un obstacol vecin din același
    # bloc să nu facă imposibilă toată planificarea.
    c_cost[c_start] = clean[start]
    c_cost[c_goal] = clean[goal]
    return c_cost, c_minutes, c_masks, c_start, c_goal


def _bresenham(a: Cell, b: Cell) -> list[Cell]:
    """Celulele de pe segmentul a → b, cu ambele capete (Bresenham, 8 vecini)."""
    (r0, c0), (r1, c1) = a, b
    dr, dc = abs(r1 - r0), abs(c1 - c0)
    sr, sc = (1 if r1 > r0 else -1), (1 if c1 > c0 else -1)
    err = dr - dc
    cells = [(r0, c0)]
    while (r0, c0) != (r1, c1):
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r0 += sr
        if e2 < dr:
            err += dr
            c0 += sc
        cells.append((r0, c0))
    return cells


def _project(states, f, start, goal, t0_min, shape):
    """Traseul pe blocuri → grila fină: prin centrele blocurilor, timpii interpolați liniar."""
    rows, cols = shape
    waypoints = []
    for i, ((br, bc), t) in enumerate(states):
        if i == len(states) - 1:
            cell = goal
        elif (br, bc) == states[0][0]:
            cell = start  # inclusiv așteptările în blocul de start
        else:
            cell = (min(br * f + f // 2, rows - 1), min(bc * f + f // 2, cols - 1))
        waypoints.append((cell, float(t0_min + t)))

    path = [waypoints[0]]
    for (a, t_a), (b, t_b) in zip(waypoints, waypoints[1:]):
        if a == b:
            path.append((b, t_b))  # așteptare
            continue
        line = _bresenham(a, b)[1:]
        for j, cell in enumerate(line, start=1):
            path.append((cell, t_a + (t_b - t_a) * j / len(line)))
    return path


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
