"""
Semantic springs for the living map.

This module used to hold the map's whole layout: a ForceAtlas2 pass, an
incremental placement, and a `node_positions` table so the map looked the same
on reopen. All of it is gone. The solver lives in the Rust core now
(`snapshot.rs::place_nodes`), where the app and the backend read the same one
instead of each drawing its own, and positions are no longer persisted: the
solver is deterministic, and a map is allowed to move as the memory grows.

What stays here is the one thing the projection needs and the core also
computes: soft edges between entities whose embeddings are close, so that
vector-similar entities drift together and cluster together even when no
relation connects them. Layout-and-clustering material only, never returned to
the client, never counted in a node's degree.
"""

import os

from db import cursor_to_dicts

# Tunable via env; kept gentle so real relations still dominate the structure.
_SEMANTIC_K = int(os.environ.get("SYNAPSE_SEMANTIC_K", "4"))             # neighbours per entity
# 0.62, not the 0.80 this shipped with: measured on the real memory, the median
# best neighbour scores 0.626 and only 4 entities out of 60 have a neighbour at
# 0.80, so the old floor produced two edges in production and the feature was
# inert. Do not go below 0.55 either — past that the edges link anything and the
# zones stop reading (silhouette 0.372 → 0.203).
_SEMANTIC_MIN_SCORE = float(os.environ.get("SYNAPSE_SEMANTIC_MIN_SCORE", "0.62"))  # cosine floor
_SEMANTIC_WEIGHT = float(os.environ.get("SYNAPSE_SEMANTIC_WEIGHT", "0.45"))        # vs ~1.0 relations
_SEMANTIC_MAX_NODES = int(os.environ.get("SYNAPSE_SEMANTIC_MAX_NODES", "800"))     # O(n²) guard


def semantic_edges(conn, nodes: list[dict]) -> list[dict]:
    """Soft edges between entities with close embeddings (top-K cosine).

    Returns edge dicts `{from, to, confidence, semantic: True}` — `confidence` is the
    spring weight (`_SEMANTIC_WEIGHT × cosine`). Entities only (notes have no entity
    embedding); empty on any missing dependency / oversized graph so layout still works."""
    ent_ids = [n["id"] for n in nodes if n.get("kind") == "entity"]
    if len(ent_ids) < 3 or len(ent_ids) > _SEMANTIC_MAX_NODES:
        return []
    try:
        import numpy as np
        from entity_search import deserialize_vec
    except Exception:
        return []
    want = set(ent_ids)
    rows = [r for r in cursor_to_dicts(conn.execute(
        "SELECT id, embedding FROM entities "
        "WHERE embedding IS NOT NULL AND merged_into_id IS NULL AND status='active'"
    )) if r["id"] in want]
    if len(rows) < 3:
        return []
    ids = [r["id"] for r in rows]
    try:
        mat = np.array([deserialize_vec(r["embedding"]) for r in rows], dtype=np.float32)
    except (ValueError, TypeError):
        return []                                       # ragged dims (model changed mid-flight)
    if mat.ndim != 2 or mat.shape[0] != len(ids):
        return []
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms                                   # cosine = dot on unit vectors
    sims = mat @ mat.T
    np.fill_diagonal(sims, -1.0)                         # never pick self
    k = min(_SEMANTIC_K, len(ids) - 1)
    edges: list[dict] = []
    seen: set = set()
    for a in range(len(ids)):
        # Best K neighbours, ties broken by id: the core runs the same rule, and
        # an arbitrary pick would make the two maps disagree on close calls.
        ranked = sorted(range(len(ids)), key=lambda b: (-float(sims[a, b]), ids[b]))
        for b in ranked[:k]:
            score = float(sims[a, b])
            if score < _SEMANTIC_MIN_SCORE:
                break                                   # sorted: the rest is worse
            key = (a, b) if a < b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"from": ids[a], "to": ids[b],
                          "confidence": round(_SEMANTIC_WEIGHT * score, 4), "semantic": True})
    return edges
