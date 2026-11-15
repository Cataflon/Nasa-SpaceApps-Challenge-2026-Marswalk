"""Turul cel mai scurt în metri: metrica pe întregi, matricea de distanțe și ordinea opririlor.

Metrica (cerința „traseul cel mai scurt în metri”). Fiecare pas pe grilă are o lungime întreagă:
ORTHO = 1000 unități pe un pas ortogonal, DIAG = 1414 pe unul diagonal (1000 unități = o celulă =
`cell_size_m`, adică 20 m pe siturile noastre). Celulele interzise rămân cele din `static_cost`
(inf: pantă > 20°, `unsafe`, NaN), iar regula anti-colț e aceeași ca la A* (routing.py).

Cheia de comparație a unui drum e lexicografică: (distanță, cost_preset, row, col). Presetul alege
doar între drumuri la fel de lungi. Ca să rămână o singură cheie întreagă (un singur `int` în heap),
costul unui pas a → b este

    pas_dist × (SCALE + h[a] + h[b]),   cu h[x] = round(PRESET_RES × cost_preset[x] / 2)

adică `pas_dist × SCALE` (distanța) plus `pas_dist × (h[a] + h[b])` ≈ PRESET_RES × ORTHO ×
cost_preset_mediu × pas (componenta de preset, rotunjită o dată pe celulă, nu pe pas: așa rămâne
exact simetrică). SCALE e ales mai mare decât componenta de preset maximă a ORICĂRUI drum de pe
hartă: un drum optim e simplu, deci are cel mult N − 1 pași (N = rows × cols), fiecare cu
componenta ≤ DIAG × 2 × h_max. Cu SCALE = (N − 1) × DIAG × 2 × h_max + 1, suma presetului pe tot
traseul rămâne < SCALE, deci compararea cheilor totale e exact compararea (distanță, preset):
distanța = cheie // SCALE, presetul = cheie % SCALE. Totul în `int` Python (fără overflow).

Ordinea opririlor (`shortest_tour`): Held-Karp exact până la HELD_KARP_MAX_STOPS opriri, cel mai
apropiat vecin + 2-opt + Or-opt peste (marcat `approx = True`). Egalitățile se rup lexicografic
după id-urile opririlor, în ordinea vizitei.
"""

import heapq
import weakref
from array import array
from dataclasses import dataclass, field

import numpy as np

from app.core.costmap import static_cost
from app.core.site_data import Site
from app.core.types import Cell

ORTHO = 1000  # unități pe un pas ortogonal (1000 = o celulă)
DIAG = 1414  # unități pe un pas diagonal (√2 × 1000, trunchiat la întreg)
# presupunere (C): rezoluția componentei de preset (1/100 dintr-o unitate de cost pe celulă). Contează
# doar la departajarea drumurilor de aceeași lungime.
PRESET_RES = 100
# presupunere (C): pragul până la care ordinea e exactă (Held-Karp, memorie O(2^n · n): 49 152 de
# stări la 12 opriri, sub 300 ms); peste el, euristică (cel mai apropiat vecin + 2-opt + Or-opt).
HELD_KARP_MAX_STOPS = 12
HOME = "habitat"
UNREACHABLE = "UNREACHABLE"
UNKNOWN = "UNKNOWN"

_DP_INF = 1 << 61  # „infinit” în tabelele numpy int64 (INF + INF < 2^63)


# ------------------------------------------------------------------ grila întreagă


@dataclass(frozen=True)
class IntGrid:
    """Grila cu bordură, aplatizată: hh[i] = SCALE/2 + h[i] pentru celulele permise, 0 = interzis."""

    hh: list
    Wp: int
    shape: tuple[int, int]
    scale: int


_grid_cache: dict[int, tuple[weakref.ref, IntGrid]] = {}


def int_grid(cost: np.ndarray) -> IntGrid:
    """Grila întreagă pentru o hartă de cost (în cache per tablou: `static_cost` întoarce același obiect)."""
    hit = _grid_cache.get(id(cost))
    if hit is not None and hit[0]() is cost:
        return hit[1]
    grid = _build_grid(cost)
    try:
        key = id(cost)
        ref = weakref.ref(cost, lambda r, key=key: _grid_cache.pop(key, None) if _grid_cache.get(key, (None,))[0] is r else None)
        _grid_cache[key] = (ref, grid)
    except TypeError:
        pass  # obiect fără referințe slabe: fără cache
    return grid


def _build_grid(cost: np.ndarray) -> IntGrid:
    c = np.asarray(cost, dtype=np.float64)
    if c.ndim != 2:
        raise ValueError(f"Harta de cost trebuie să fie 2D, am primit {c.ndim}D.")
    finite = np.isfinite(c)
    if finite.any() and float(c[finite].min()) < 0:
        raise ValueError(f"Harta de cost are valori negative (minim {float(c[finite].min())}).")
    h = np.zeros(c.shape, dtype=np.int64)
    h[finite] = np.rint(c[finite] * (PRESET_RES / 2.0)).astype(np.int64)
    h_max = int(h.max()) if h.size else 0
    rows, cols = c.shape
    scale = (rows * cols - 1) * DIAG * 2 * h_max + 1
    scale += scale % 2  # par: SCALE/2 e întreg
    padded = np.zeros((rows + 2, cols + 2), dtype=np.int64)
    padded[1:-1, 1:-1] = np.where(finite, scale // 2 + h, 0)
    return IntGrid(padded.ravel().tolist(), cols + 2, (rows, cols), scale)


def _moves(Wp: int):
    """(deplasare, lungime în unități, latură_a, latură_b), aceeași ordine ca grid.neighbor_moves."""
    out = []
    for delta, w in ((-Wp, ORTHO), (Wp, ORTHO), (-1, ORTHO), (1, ORTHO),
                     (-Wp - 1, DIAG), (-Wp + 1, DIAG), (Wp - 1, DIAG), (Wp + 1, DIAG)):
        if w == ORTHO:
            out.append((delta, w, 0, 0))
        else:
            row_part = -Wp if delta < 0 else Wp
            out.append((delta, w, row_part, delta - row_part))
    return tuple(out)


def octile_units(a: Cell, b: Cell) -> int:
    """Distanța exactă pe grilă liberă, în unități: 1000 × max + 414 × min."""
    dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
    return ORTHO * max(dr, dc) + (DIAG - ORTHO) * min(dr, dc)


def path_units(path: list[Cell]) -> int:
    """Lungimea unui traseu în unități (pașii ortogonali 1000, diagonali 1414)."""
    total = 0
    for a, b in zip(path, path[1:]):
        dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
        total += DIAG if dr and dc else (ORTHO if dr or dc else 0)
    return total


def units_to_m(units: int, cell_size_m: float) -> float:
    return units / ORTHO * float(cell_size_m)


# ------------------------------------------------------------------ câmpul de distanțe


@dataclass
class DistanceField:
    """Rezultatul lui `distance_field`: cheile până la ținte și părinții (pentru reconstruirea segmentelor)."""

    source: Cell
    keys: dict  # Cell -> cheia lexicografică totală (int) sau None dacă ținta e inaccesibilă
    parent: array  # indexul plat cu bordură al predecesorului; -1 = sursa sau nevizitat
    Wp: int
    scale: int
    complete: bool = False  # căutare pe harta întreagă (fără ținte): orice celulă atinsă are părinți

    def units(self, cell: Cell) -> int | None:
        k = self.keys.get((int(cell[0]), int(cell[1])))
        return None if k is None else k // self.scale

    def preset_part(self, cell: Cell) -> int | None:
        k = self.keys.get((int(cell[0]), int(cell[1])))
        return None if k is None else k % self.scale

    def segment(self, cell: Cell) -> list[Cell] | None:
        """Celulele de la sursă la `cell` (ambele incluse), din părinți; None dacă ținta nu a fost fixată."""
        cell = (int(cell[0]), int(cell[1]))
        Wp, parent = self.Wp, self.parent
        idx = (cell[0] + 1) * Wp + cell[1] + 1
        if self.keys.get(cell) is None:
            inside = 0 <= idx < len(parent) and 0 <= cell[0] and 0 <= cell[1] < Wp - 2
            if not (self.complete and inside and (parent[idx] != -1 or cell == self.source)):
                return None
        out = []
        while idx != -1:
            out.append((idx // Wp - 1, idx % Wp - 1))
            idx = parent[idx]
        out.reverse()
        return out


def distance_field(site: Site, source: Cell, preset: str = "safe", targets=None,
                   cost: np.ndarray | None = None) -> DistanceField:
    """Dijkstra din `source` pe metrica lexicografică (distanță, preset), cu oprire timpurie.

    `targets`: celulele de interes; căutarea se oprește când toate sunt fixate (scoase din coadă).
    Cu ținte, căutarea folosește potențialul SCALE × min_t octilă(x, t) (Dijkstra pe costuri reduse,
    adică A* cu o euristică consistentă, fixă pe toată căutarea): cheile rămân exacte, doar se
    explorează mai puțin. Fără ținte, harta întreagă (doar părinții sunt utili atunci).

    `cost`: harta de cost (implicit `static_cost(site, preset)`; în live, C_temp). Coada e ordonată după
    (cheie + potențial, index), iar indexul plat crește cu (row, col). Nu aruncă pentru surse sau ținte
    interzise ori în afara grilei: ele apar cu cheia None.

    Arborele de părinți e canonic: la chei egale, părintele e predecesorul optim cu indexul cel mai mic
    (adică (row, col) minim). Orice pas costă strict mai mult decât scade potențialul (h ≥ 50 pe celulele
    permise, pentru că static_cost ≥ 1), deci toți predecesorii optimi ai unui nod sunt fixați înaintea
    lui, iar segmentul sursă → țintă nu depinde de mulțimea de ținte (cu sau fără oprire timpurie).
    """
    grid = int_grid(static_cost(site, preset) if cost is None else cost)
    return _search(grid, source, targets)


def _search(grid: IntGrid, source: Cell, targets) -> DistanceField:
    hh, Wp, scale = grid.hh, grid.Wp, grid.scale
    rows, cols = grid.shape
    source = (int(source[0]), int(source[1]))
    n = len(hh)
    want = {}
    for t in (targets or []):
        t = (int(t[0]), int(t[1]))
        want[t] = None
    parent = [-1] * n
    inside = 0 <= source[0] < rows and 0 <= source[1] < cols
    src = (source[0] + 1) * Wp + source[1] + 1 if inside else -1
    if src < 0 or not hh[src]:
        return DistanceField(source, want, array("i", parent), Wp, scale)

    remaining = {}
    for t in want:
        if 0 <= t[0] < rows and 0 <= t[1] < cols and hh[(t[0] + 1) * Wp + t[1] + 1]:
            remaining[(t[0] + 1) * Wp + t[1] + 1] = t
    goals = [(idx // Wp, idx % Wp) for idx in remaining]  # (row, col) cu bordură: diferențele sunt aceleași
    use_potential = bool(remaining)
    big = 1 << 400
    g = [big] * n
    closed = bytearray(n)
    g[src] = 0
    moves = _moves(Wp)
    extra = DIAG - ORTHO

    def potential(idx):
        r, c = divmod(idx, Wp)
        best = big
        for gr, gc in goals:
            dr = r - gr if r > gr else gr - r
            dc = c - gc if c > gc else gc - c
            o = ORTHO * dr + extra * dc if dr > dc else ORTHO * dc + extra * dr
            if o < best:
                best = o
        return best * scale

    pot = {src: potential(src) if use_potential else 0}
    heap = [pot[src] * n + src]
    push, pop = heapq.heappush, heapq.heappop
    left = len(remaining)
    while heap:
        item = pop(heap)
        cur = item % n
        if closed[cur]:
            continue
        closed[cur] = 1
        if cur in remaining:
            want[remaining[cur]] = g[cur]
            left -= 1
            if left == 0:
                break
        g_cur = g[cur]
        h_cur = hh[cur]
        for delta, w, sa, sb in moves:
            nb = cur + delta
            h_nb = hh[nb]
            if not h_nb or closed[nb]:
                continue
            if sa and (not hh[cur + sa] or not hh[cur + sb]):
                continue
            ng = g_cur + w * (h_cur + h_nb)
            if ng == g[nb]:
                if cur < parent[nb]:
                    parent[nb] = cur  # părinte canonic: cel mai mic index dintre predecesorii optimi
                continue
            if ng < g[nb]:
                g[nb] = ng
                parent[nb] = cur
                if use_potential:
                    p = pot.get(nb)
                    if p is None:
                        p = pot[nb] = potential(nb)
                    push(heap, (ng + p) * n + nb)
                else:
                    push(heap, ng * n + nb)
    return DistanceField(source, want, array("i", parent), Wp, scale, complete=not use_potential)


# ------------------------------------------------------------------ matricea turului


@dataclass
class TourMatrix:
    """Distanțele (unități) și segmentele între habitat și toate țintele din meta, pentru un preset."""

    nodes: list[str]  # [HOME] + id-urile țintelor, sortate
    cells: dict[str, Cell]
    units: np.ndarray  # n × n int64; -1 = inaccesibil
    preset_part: np.ndarray  # n × n int64; componenta de preset a cheii; -1 = inaccesibil
    scale: int
    fields: dict[str, DistanceField] = field(repr=False, default_factory=dict)

    def index(self, node: str) -> int:
        return self.nodes.index(node)

    def distance(self, a: str, b: str) -> int | None:
        d = int(self.units[self.index(a), self.index(b)])
        return None if d < 0 else d

    def segment(self, a: str, b: str) -> list[Cell] | None:
        """Segmentul a → b din părinții sursei care l-a fixat (fără A*); inversat dacă l-a fixat b."""
        if a == b:
            return [self.cells[a]]
        f = self.fields.get(a)
        if f is not None and f.keys.get(self.cells[b]) is not None:
            return f.segment(self.cells[b])
        f = self.fields.get(b)
        if f is not None and f.keys.get(self.cells[a]) is not None:
            seg = f.segment(self.cells[a])
            return seg[::-1] if seg else None
        return None


_matrix_cache: dict[tuple, tuple[weakref.ref, object, tuple, TourMatrix]] = {}


def _signature(site: Site) -> tuple:
    meta = site.meta
    targets = tuple((str(t["id"]), int(t["row"]), int(t["col"])) for t in meta.get("targets", []))
    return (meta.get("site_id"), meta.get("version"), tuple(site.shape), tuple(site.habitat), targets)


def tour_matrix(site: Site, preset: str = "safe") -> TourMatrix:
    """Matricea pentru habitat + toate țintele din meta, o dată per (sit, preset), în cache.

    Invalidare ca la `static_cost`: intrarea e valabilă cât timp situl e același obiect (referință
    slabă), `static_cost(site, preset)` întoarce același tablou (deci după `clear_cost_cache()` se
    recalculează) și semnătura (site_id, versiune, formă, habitat, ținte) e neschimbată.

    Simetrie: costul unui pas e același în ambele sensuri, deci nodul i caută doar nodurile j > i
    (n − 1 căutări cu oprire timpurie); d(j, i) = d(i, j), segmentul j → i = inversul lui i → j.
    """
    cost = static_cost(site, preset)
    sig = _signature(site)
    key = (id(site), preset)
    hit = _matrix_cache.get(key)
    if hit is not None and hit[0]() is site and hit[1] is cost and hit[2] == sig:
        return hit[3]
    matrix = _build_matrix(site, cost, preset)
    full_key = key

    def forget(ref, full_key=full_key):
        entry = _matrix_cache.get(full_key)
        if entry is not None and entry[0] is ref:
            del _matrix_cache[full_key]

    _matrix_cache[key] = (weakref.ref(site, forget), cost, sig, matrix)
    return matrix


def cached_matrix(site: Site, preset: str = "safe") -> TourMatrix | None:
    """Matricea din cache dacă e încă valabilă, fără s-o calculeze (None altfel)."""
    hit = _matrix_cache.get((id(site), preset))
    if hit is None or hit[0]() is not site or hit[2] != _signature(site):
        return None
    try:
        cost = static_cost(site, preset)
    except ValueError:
        return None
    return hit[3] if hit[1] is cost else None


def clear_tour_cache() -> None:
    _matrix_cache.clear()
    _grid_cache.clear()


def _build_matrix(site: Site, cost: np.ndarray, preset: str) -> TourMatrix:
    targets = {str(t["id"]): (int(t["row"]), int(t["col"])) for t in site.meta.get("targets", [])}
    nodes = [HOME] + sorted(targets)
    cells = {HOME: tuple(int(v) for v in site.habitat), **targets}
    n = len(nodes)
    units = np.full((n, n), -1, dtype=np.int64)
    preset_part = np.full((n, n), -1, dtype=np.int64)
    np.fill_diagonal(units, 0)
    np.fill_diagonal(preset_part, 0)
    grid = int_grid(cost)
    fields: dict[str, DistanceField] = {}
    for i in range(n - 1):
        src = nodes[i]
        f = _search(grid, cells[src], [cells[nodes[j]] for j in range(i + 1, n)])
        fields[src] = f
        for j in range(i + 1, n):
            k = f.keys.get(cells[nodes[j]])
            if k is not None:
                units[i, j] = units[j, i] = k // grid.scale
                preset_part[i, j] = preset_part[j, i] = k % grid.scale
    return TourMatrix(nodes, cells, units, preset_part, grid.scale, fields)


# ------------------------------------------------------------------ ordinea opririlor


@dataclass
class Tour:
    order: list[str]
    distance_units: int  # 0 pentru turul gol
    approx: bool = False
    excluded: list[dict] = field(default_factory=list)  # [{"id": ..., "reason": UNREACHABLE | UNKNOWN}]


def shortest_tour(matrix: TourMatrix, start: str, stops: list[str], return_to_habitat: bool = True,
                  start_units: dict | None = None) -> Tour:
    """Ordinea opririlor care minimizează distanța totală start → opriri (→ habitat).

    `start`: un nod din matrice (de obicei HOME). Pentru un start care nu e nod fix (o poziție
    oarecare) se dă `start_units` = {id: unități sau None} spre fiecare oprire și spre HOME, de
    exemplu dintr-un `distance_field` din acea poziție. Turul închis se termină la HOME, cel deschis
    la ultima oprire. Opririle inaccesibile din start (sau, la turul închis, fără drum spre casă) se
    exclud cu motivul UNREACHABLE, id-urile necunoscute cu UNKNOWN; nicio excepție.

    ≤ 2 opriri: direct; ≤ HELD_KARP_MAX_STOPS: Held-Karp exact; peste: euristică, `approx = True`.
    La distanțe egale câștigă ordinea cea mai mică lexicografic după id-uri.
    """
    excluded: list[dict] = []
    known = set(matrix.nodes)
    ids = []
    for s in dict.fromkeys(stops):
        if s not in known or s == HOME:
            excluded.append({"id": s, "reason": UNKNOWN})
        else:
            ids.append(s)
    ids.sort()

    def from_start(node: str) -> int | None:
        if start_units is not None:
            v = start_units.get(node)
            return None if v is None else int(v)
        if start not in known:
            return None
        return matrix.distance(start, node)

    to_home = from_start(HOME) if return_to_habitat else 0
    reach = []
    for s in ids:
        ok = from_start(s) is not None and (not return_to_habitat or (to_home is not None and matrix.distance(s, HOME) is not None))
        (reach if ok else excluded).append(s if ok else {"id": s, "reason": UNREACHABLE})
    excluded.sort(key=lambda e: e["id"])
    k = len(reach)
    if k == 0:
        return Tour([], int(to_home or 0) if return_to_habitat else 0, False, excluded)

    idx = [matrix.index(s) for s in reach]
    ds = np.array([from_start(s) for s in reach], dtype=np.int64)
    pair = matrix.units[np.ix_(idx, idx)].astype(np.int64)
    pair[pair < 0] = _DP_INF
    if return_to_habitat:
        de = matrix.units[idx, matrix.index(HOME)].astype(np.int64)
        de[de < 0] = _DP_INF
    else:
        de = np.zeros(k, dtype=np.int64)  # turul deschis: nod final fictiv, la distanță 0 de orice oprire

    if k <= 2:
        order_idx = _small(ds, pair, de)
        approx = False
    elif k <= HELD_KARP_MAX_STOPS:
        order_idx = _held_karp(ds, pair, de)
        approx = False
    else:
        order_idx = _heuristic(ds, pair, de)
        approx = True
    order = [reach[i] for i in order_idx]
    return Tour(order, _tour_cost(order_idx, ds, pair, de), approx, excluded)


def _tour_cost(order, ds, pair, de) -> int:
    if not order:
        return 0
    total = int(ds[order[0]]) + int(de[order[-1]])
    for a, b in zip(order, order[1:]):
        total += int(pair[a, b])
    return total


def _small(ds, pair, de) -> list[int]:
    if len(ds) == 1:
        return [0]
    a, b = _tour_cost([0, 1], ds, pair, de), _tour_cost([1, 0], ds, pair, de)
    return [0, 1] if a <= b else [1, 0]


def _held_karp(ds, pair, de) -> list[int]:
    """Held-Karp vectorizat pe măști. g[mask, j] = drumul minim care pleacă din j, trece prin toate
    opririle din `mask` (j ∈ mask) și se termină la capăt (habitat sau nodul fictiv). Se calculează pe
    straturi după numărul de biți; în fiecare strat, pentru fiecare j, toate măștile deodată.

    Reconstrucția merge înainte, din start: la fiecare pas se alege cea mai mică oprire (după id)
    care încă duce la optim (acc + d(curent, j) + g[rest, j] == opt). Așa ordinea e cea mai mică
    lexicografic în sensul vizitei; un vector de predecesori clasic ar da cea mai mică ordine
    citită de la capăt spre start.
    """
    k = len(ds)
    full = (1 << k) - 1
    masks = np.arange(1 << k, dtype=np.int64)
    bits = np.zeros(1 << k, dtype=np.int64)
    for j in range(k):
        bits += (masks >> j) & 1
    g = np.full((1 << k, k), _DP_INF, dtype=np.int64)
    for j in range(k):
        g[1 << j, j] = de[j]
    for size in range(2, k + 1):
        layer = masks[bits == size]
        for j in range(k):
            m = layer[(layer >> j) & 1 == 1]
            prev = m ^ (1 << j)
            vals = (g[prev] + pair[j][None, :]).min(axis=1)
            g[m, j] = np.minimum(vals, _DP_INF)
    totals = np.minimum(ds + g[full], _DP_INF)
    opt = int(totals.min())
    order: list[int] = []
    mask, acc, dcur = full, 0, ds
    while mask:
        for j in range(k):
            if (mask >> j) & 1 and acc + int(dcur[j]) + int(g[mask, j]) == opt:
                order.append(j)
                acc += int(dcur[j])
                mask ^= 1 << j
                dcur = pair[j]
                break
        else:  # nu ar trebui să se întâmple (opt finit); protecție împotriva unei bucle infinite
            order += [j for j in range(k) if (mask >> j) & 1]
            break
    return order


def _heuristic(ds, pair, de) -> list[int]:
    """Cel mai apropiat vecin, apoi 2-opt și Or-opt (segmente de 1-3) până la convergență.

    Ordine fixă de evaluare (i crescător, apoi j crescător), prima îmbunătățire strictă se aplică;
    la egalitate nu se schimbă nimic, deci rezultatul e determinist.
    """
    k = len(ds)
    P = pair.tolist()
    S = [int(x) for x in ds]
    E = [int(x) for x in de]
    left = list(range(k))
    order = []
    cur = None
    while left:
        row = S if cur is None else P[cur]
        nxt = min(left, key=lambda j: (row[j], j))
        order.append(nxt)
        left.remove(nxt)
        cur = nxt

    def cost(o):
        total = S[o[0]] + E[o[-1]]
        for a, b in zip(o, o[1:]):
            total += P[a][b]
        return total

    best = cost(order)
    improved = True
    while improved:
        improved = False
        for i in range(k - 1):  # 2-opt: inversează order[i..j]
            for j in range(i + 1, k):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                c = cost(cand)
                if c < best:
                    order, best, improved = cand, c, True
        for seg in (1, 2, 3):  # Or-opt: mută un segment de 1-3 opriri în altă poziție
            for i in range(k - seg + 1):
                block = order[i:i + seg]
                rest = order[:i] + order[i + seg:]
                for p in range(len(rest) + 1):
                    if p == i:
                        continue
                    cand = rest[:p] + block + rest[p:]
                    c = cost(cand)
                    if c < best:
                        order, best, improved = cand, c, True
                        break
                else:
                    continue
                break
    return order
