"""Louvain community detection, deterministic by construction.

networkx has a Louvain, and it was what `/graph` used, but it shuffles the node
order with a seeded RNG: `seed=42` is reproducible for one process, yet it is
one draw among many, and the draw it landed on is not a good one. On the karate
club benchmark, seed 42 scores 0.3854 where twenty other seeds range from 0.3952
to 0.4198. Worse for us, no other language can reproduce Python's shuffle, so
the core could never agree with the backend on the zones of the same map.

This implementation visits nodes in sorted-id order, breaks gain ties by the
smallest community index, and is therefore reproducible anywhere. The Rust core
runs the same algorithm line for line (`snapshot.rs::assign_communities`), and
both are pinned to the same expected partition in their test suites.

Quality is not sacrificed: on the karate club it scores 0.4188, the high end of
what networkx draws.
"""

RESOLUTION = 1.0

_MAX_PASSES = 100   # local moving; convergence is typically under ten
_MAX_LEVELS = 20    # aggregations; each one shrinks the graph


class _Graph:
    """Undirected weighted graph over dense indices. Self-loops are held apart
    because they count twice in a node's degree — they appear as soon as a level
    of communities is collapsed into single nodes."""

    def __init__(self, n: int):
        self.adj: list[list[tuple[int, float]]] = [[] for _ in range(n)]
        self.self_w: list[float] = [0.0] * n

    def __len__(self) -> int:
        return len(self.adj)

    def add_edge(self, a: int, b: int, w: float) -> None:
        if a == b:
            self.self_w[a] += w
        else:
            self.adj[a].append((b, w))
            self.adj[b].append((a, w))

    def degree(self, i: int) -> float:
        return sum(w for _, w in self.adj[i]) + 2.0 * self.self_w[i]

    def total_weight(self) -> float:
        """Total edge weight, each edge once: the `m` of the modularity formula."""
        return sum(self.degree(i) for i in range(len(self))) / 2.0


def _one_level(g: _Graph, resolution: float) -> list[int]:
    """One Louvain pass: every node moves to the neighbouring community that
    gains the most modularity, repeated until nothing moves. Staying put scores
    exactly 0, so a node only leaves for a real gain."""
    n = len(g)
    com = list(range(n))
    m = g.total_weight()
    if m <= 0.0:
        return com  # no edges: every node is its own community
    deg = [g.degree(i) for i in range(n)]
    stot = list(deg)

    for _ in range(_MAX_PASSES):
        moved = False
        for u in range(n):
            w2c: dict[int, float] = {}
            for v, w in g.adj[u]:
                w2c[com[v]] = w2c.get(com[v], 0.0) + w
            own = com[u]
            k = deg[u]
            stot[own] -= k
            remove_cost = (-w2c.get(own, 0.0) / m
                           + resolution * (stot[own] * k) / (2.0 * m * m))
            best, best_gain = own, 0.0
            # sorted(): equal gains must fall the same way every run, and the
            # same way as the core's BTreeMap scan.
            for c, w in sorted(w2c.items()):
                gain = remove_cost + w / m - resolution * (stot[c] * k) / (2.0 * m * m)
                if gain > best_gain:
                    best, best_gain = c, gain
            stot[best] += k
            if best != own:
                com[u] = best
                moved = True
        if not moved:
            break
    return com


def _compress(com: list[int]) -> tuple[list[int], int]:
    """Relabel communities 0..k in order of first appearance, walking nodes in
    index order."""
    seen: dict[int, int] = {}
    out = []
    for c in com:
        if c not in seen:
            seen[c] = len(seen)
        out.append(seen[c])
    return out, len(seen)


def _aggregate(g: _Graph, com: list[int], k: int) -> _Graph:
    """Collapse each community into a single node: edges inside it become that
    node's self-loop, edges between two of them are summed."""
    out = _Graph(k)
    between: dict[tuple[int, int], float] = {}
    for u in range(len(g)):
        out.self_w[com[u]] += g.self_w[u]
        for v, w in g.adj[u]:
            if u >= v:
                continue  # each edge is stored twice; take it once
            a, b = com[u], com[v]
            if a == b:
                out.self_w[a] += w
            else:
                key = (a, b) if a < b else (b, a)
                between[key] = between.get(key, 0.0) + w
    for (a, b), w in sorted(between.items()):
        out.add_edge(a, b, w)
    return out


def louvain_communities(node_ids, edges, resolution: float = RESOLUTION) -> list[set]:
    """Partition `node_ids` into communities. `edges` is an iterable of
    (from, to, weight); parallel edges are summed, self-loops and edges pointing
    outside `node_ids` are dropped. Returns a list of sets of ids, in no
    particular order — the caller numbers them (`canonical_community_ids`)."""
    ids = sorted(set(node_ids))
    if not ids:
        return []
    index = {nid: i for i, nid in enumerate(ids)}

    weights: dict[tuple[int, int], float] = {}
    for a, b, w in edges:
        ia, ib = index.get(a), index.get(b)
        if ia is None or ib is None or ia == ib:
            continue
        key = (ia, ib) if ia < ib else (ib, ia)
        weights[key] = weights.get(key, 0.0) + float(w)

    graph = _Graph(len(ids))
    for (a, b), w in sorted(weights.items()):
        graph.add_edge(a, b, w)

    membership = list(range(len(graph)))
    current = graph
    for _ in range(_MAX_LEVELS):
        com, k = _compress(_one_level(current, resolution))
        if k == len(current):
            break  # nothing merged: this is the final partition
        membership = [com[c] for c in membership]
        current = _aggregate(current, com, k)
        if k == 1:
            break

    groups: dict[int, set] = {}
    for i, c in enumerate(membership):
        groups.setdefault(c, set()).add(ids[i])
    return list(groups.values())
