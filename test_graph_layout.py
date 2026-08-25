"""Offline test for SYN-64 semantic layout edges (embedding-kNN soft springs)."""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _vec(*xs) -> bytes:
    return struct.pack(f"<{len(xs)}f", *xs)


def _ins(conn, eid, name, emb):
    conn.execute(
        "INSERT INTO entities (id, type, canonical_name, status, embedding) "
        "VALUES (?,?,?, 'active', ?)", (eid, "concept", name, emb))


def test_semantic_edges_links_close_vectors(isolated_db):
    from db import get_connection
    from graph_layout import semantic_edges
    conn = get_connection()
    try:
        with conn:
            _ins(conn, "e1", "Guitare", _vec(1.0, 0.0, 0.0, 0.0))
            _ins(conn, "e2", "Piano", _vec(0.98, 0.20, 0.0, 0.0))   # ~cos 0.98 to e1
            _ins(conn, "e3", "Tennis", _vec(0.0, 0.0, 1.0, 0.0))    # orthogonal → no edge
        nodes = [{"id": "e1", "kind": "entity"}, {"id": "e2", "kind": "entity"}, {"id": "e3", "kind": "entity"}]
        edges = semantic_edges(conn, nodes)
        pairs = {frozenset((e["from"], e["to"])) for e in edges}
        assert frozenset(("e1", "e2")) in pairs                     # close vectors → linked
        assert frozenset(("e1", "e3")) not in pairs                 # below the 0.62 cosine floor
        assert all(e.get("semantic") and e["confidence"] > 0 for e in edges)
    finally:
        conn.close()


def test_semantic_edges_empty_when_no_embeddings(isolated_db):
    from db import get_connection
    from graph_layout import semantic_edges
    conn = get_connection()
    try:
        with conn:
            conn.execute("INSERT INTO entities (id, type, canonical_name, status) VALUES ('x','concept','X','active')")
        # notes are skipped (entities only); no embeddings → no edges, no crash
        assert semantic_edges(conn, [{"id": "x", "kind": "entity"}, {"id": "n:1", "kind": "atomic_note"}]) == []
    finally:
        conn.close()


def test_semantic_edges_match_the_core(isolated_db):
    """The fixture is shared with the Rust core
    (`snapshot.rs::semantic_springs_match_the_backend`): same vectors, same
    expected pairs and weights. If one side drifts, the map served over HTTP and
    the map rebuilt offline stop grouping the same entities."""
    from db import get_connection
    from graph_layout import semantic_edges
    vectors = {
        "e1": (1.00, 0.00, 0.00, 0.00),
        "e2": (0.95, 0.31, 0.00, 0.00),
        "e3": (0.90, 0.44, 0.00, 0.00),
        "e4": (0.00, 1.00, 0.00, 0.00),
        "e5": (0.00, 0.95, 0.31, 0.00),
        "e6": (0.00, 0.00, 0.00, 1.00),   # orthogonal to everything: stays alone
    }
    conn = get_connection()
    try:
        with conn:
            for eid, v in vectors.items():
                _ins(conn, eid, eid.upper(), _vec(*v))
        nodes = [{"id": eid, "kind": "entity"} for eid in vectors]
        got = sorted((e["from"], e["to"], e["confidence"]) for e in semantic_edges(conn, nodes))
        assert got == [
            ("e1", "e2", 0.4278),
            ("e1", "e3", 0.4043),
            ("e2", "e3", 0.4456),
            ("e4", "e5", 0.4278),
        ]
    finally:
        conn.close()
