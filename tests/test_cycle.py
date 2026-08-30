"""
Non-regression tests for the unified Dream Cycle structure (Chantier A).

These run OFFLINE (no ANTHROPIC_API_KEY): they cover the package layout, the
episodic-memory schema migration, and the episodic-note writer — none of which
call the Claude API. The full classify→route pipeline (which does call the API)
lives in test_dream_cycle.py and is skipped without a key.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Package layout (guards the shadowing bug we fixed) ───────────────────────

def test_dream_cycle_package_not_shadowed():
    """`import dream_cycle` must resolve to the package, exporting the cycle."""
    import dream_cycle
    assert dream_cycle.__file__.endswith("dream_cycle/__init__.py")
    from dream_cycle import run_dream_cycle, main
    assert callable(run_dream_cycle) and callable(main)


# ── Schema migration (spec §3.1 episodic atomic_notes) ───────────────────────

def test_atomic_notes_has_episodic_columns(isolated_db):
    from db import get_connection
    conn = get_connection()
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(atomic_notes)")}
    finally:
        conn.close()
    assert {"summary", "entities_mentioned", "memory_strength"} <= cols


# ── Episodic note writer ─────────────────────────────────────────────────────
# episodic notes flow through the core's routing (_process_entry with
# the classifier's atomic_note), like production — the legacy writer is gone.

def _process(classified: dict, entry_id: int = 1, content: str = "capture de test"):
    from datetime import datetime, timezone
    from db import get_connection
    from dream_cycle import cycle
    conn = get_connection()
    try:
        return cycle._process_entry(
            {"id": entry_id, "content": content}, None, conn,
            datetime.now(timezone.utc).isoformat(), False, False,
            classified=classified)
    finally:
        conn.close()


def test_episodic_capture_creates_vectorized_note(isolated_db):
    from db import get_connection

    entry_content = "Hier soir, super dîner avec Marie à Lyon."
    classified = {
        "input_type": "episodic",
        "summary": "Dîné avec Marie à Lyon",
        "atomic_note": entry_content,
        "entities": [{"canonical_name": "Marie"}, {"canonical_name": "Lyon"}],
    }
    _process(classified, content=entry_content)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, summary, entities_mentioned, memory_strength FROM atomic_notes"
        ).fetchone()
        assert row is not None, "episodic note was not written"
        note_id, summary, entities_mentioned, memory_strength = row

        assert summary == "Dîné avec Marie à Lyon"
        assert set(json.loads(entities_mentioned)) == {"Marie", "Lyon"}
        assert memory_strength == 1.0

        vec = conn.execute(
            "SELECT embedding FROM atomic_notes_vec WHERE note_id = ?", (note_id,)
        ).fetchone()
        assert vec is not None, "episodic note was not vectorized"
    finally:
        conn.close()


def test_episodic_note_is_searchable(isolated_db):
    entry_content = "Hier soir, super dîner avec Marie à Lyon."
    _process({
        "input_type": "episodic",
        "summary": "Dîné avec Marie à Lyon",
        "atomic_note": entry_content,
        "entities": [{"canonical_name": "Marie"}],
    }, content=entry_content)

    import mcp_server.server as server
    search = getattr(server.search_memory, "fn", server.search_memory)
    results = json.loads(search("repas avec Marie", limit=3))

    assert results, "expected the episodic note to be searchable"
    assert results[0]["search_type"] == "vector"


# ── Entity creation (decoupled from fact confidence) ─────────────────────────
# routing lives in the core — the hand-built `resolved` dicts become
# classifier-shaped `classified` dicts driven through `_process_entry` (the
# core resolves entities itself against the database).

def _route(resolved: dict, source_id: int = 1, **extra):
    classified = {
        "input_type": "fact",
        "entities": [{k: v for k, v in e.items() if k != "existing_entity"}
                     for e in resolved.get("resolved_entities", [])],
        "relations": resolved.get("relations", []),
        "project_entries": resolved.get("project_entries", []),
    }
    classified.update(extra)
    return _process(classified, entry_id=source_id)


def _entities() -> list[dict]:
    from db import get_connection, cursor_to_dicts
    conn = get_connection()
    try:
        return cursor_to_dicts(conn.execute("SELECT * FROM entities"))
    finally:
        conn.close()


def test_entity_created_on_mention_even_without_high_confidence(isolated_db):
    """A non-high-confidence fact still creates the entity node; the fact itself
    lands in pending. `hedged` evidence is clamped to 0.84 (< the 0.85 facts
    threshold) regardless of persistence, so this exercises the decoupling: the
    entity exists (persistence 5 ≥ MIN_ENTITY_PERSISTENCE) while its fact waits
    for validation. (An *explicit* fact would correctly land in `facts`.)"""
    resolved = {
        "resolved_entities": [{
            "canonical_name": "Marie", "type": "person", "aliases": ["maman"],
            "summary": "La mère de l'utilisateur", "attributes": {"role": "mère"},
            "facts": [{
                "predicate": "has_birthday", "value": "2026-05-15",
                "persistence_value": 5, "evidence_strength": "hedged",
            }],
            "existing_entity": None,
        }],
        "relations": [],
    }
    _route(resolved)

    ents = _entities()
    assert len(ents) == 1
    marie = ents[0]
    assert marie["canonical_name"] == "Marie"
    assert marie["summary"] == "La mère de l'utilisateur"
    assert json.loads(marie["attributes"])["role"] == "mère"
    assert marie["persistence_value"] == 5

    # the fact is not confirmed yet — it should be pending, not in facts
    from db import get_connection
    conn = get_connection()
    try:
        facts = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM pending_facts").fetchone()[0]
    finally:
        conn.close()
    assert facts == 0 and pending == 1


def test_noise_entity_is_not_created(isolated_db):
    """An entity whose only fact is pure noise (persistence 1) and that is not in
    a relation must be skipped — anti-pollution garde-fou."""
    resolved = {
        "resolved_entities": [{
            "canonical_name": "Truc entendu en passant", "type": "concept",
            "aliases": [], "summary": None, "attributes": {},
            "facts": [{"predicate": "mentioned", "value": "x", "persistence_value": 1}],
            "existing_entity": None,
        }],
        "relations": [],
    }
    _route(resolved)
    assert _entities() == []


def test_relation_only_entity_is_created(isolated_db):
    """Entities that appear only in a relation (no standalone fact) are created so
    the relation has both endpoints."""
    resolved = {
        "resolved_entities": [
            {"canonical_name": "Marie", "type": "person", "aliases": [],
             "summary": None, "attributes": {}, "facts": [], "existing_entity": None},
            {"canonical_name": "Alexis", "type": "person", "aliases": [],
             "summary": None, "attributes": {}, "facts": [], "existing_entity": None},
        ],
        "relations": [{"from": "Marie", "predicate": "mere_de", "to": "Alexis"}],
    }
    _route(resolved)

    assert len(_entities()) == 2
    from db import get_connection
    conn = get_connection()
    try:
        rel_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    finally:
        conn.close()
    assert rel_count == 1


def test_fact_restating_relation_is_dropped(isolated_db):
    """Anti-redite: « Audric est le cousin d'Alexis » must NOT produce both a
    relation (Audric→Alexis) AND a twin fact (cousin_de = "Alexis") on Audric.
    The relation wins; the redundant fact is dropped at routing."""
    resolved = {
        "resolved_entities": [
            {"canonical_name": "Audric", "type": "person", "aliases": [],
             "summary": None, "attributes": {},
             "facts": [
                 {"predicate": "is_cousin_of", "value": "Alexis",
                  "persistence_value": 5, "evidence_strength": "explicit"},
                 {"predicate": "lives_in", "value": "Lyon",
                  "persistence_value": 4, "evidence_strength": "explicit"},
             ],
             "existing_entity": None},
            {"canonical_name": "Alexis", "type": "person", "aliases": [],
             "summary": None, "attributes": {}, "facts": [], "existing_entity": None},
        ],
        "relations": [{"from": "Audric", "predicate": "is_cousin_of",
                       "to": "Alexis", "confidence": 1.0}],
    }
    _route(resolved)
    from db import get_connection
    conn = get_connection()
    try:
        # only the literal-valued fact survives; the entity-valued twin is gone
        facts = [r[0] for r in conn.execute("SELECT predicate FROM facts")]
        pending = [r[0] for r in conn.execute(
            "SELECT json_extract(fact_data,'$.predicate') FROM pending_facts")]
        rel = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    finally:
        conn.close()
    assert "is_cousin_of" not in facts and "is_cousin_of" not in pending
    assert "lives_in" in facts or "lives_in" in pending  # literal fact kept
    assert rel == 1


def test_relation_confidence_gates_review_status(isolated_db):
    """A relation the classifier is unsure about (confidence < threshold) lands in
    « À valider » (review_status='pending'); a confident one persists live."""
    resolved = {
        "resolved_entities": [
            {"canonical_name": "Pierre", "type": "person", "aliases": [],
             "summary": None, "attributes": {}, "facts": [], "existing_entity": None},
            {"canonical_name": "Acme", "type": "concept", "aliases": [],
             "summary": None, "attributes": {}, "facts": [], "existing_entity": None},
            {"canonical_name": "Marie", "type": "person", "aliases": [],
             "summary": None, "attributes": {}, "facts": [], "existing_entity": None},
        ],
        "relations": [
            {"from": "Pierre", "predicate": "works_at", "to": "Acme", "confidence": 0.4},
            {"from": "Marie", "predicate": "knows", "to": "Pierre", "confidence": 0.95},
        ],
    }
    _route(resolved)
    from db import get_connection
    conn = get_connection()
    try:
        rows = dict(conn.execute(
            "SELECT predicate, review_status FROM relations").fetchall())
    finally:
        conn.close()
    assert rows["works_at"] == "pending"
    assert rows["knows"] == "confirmed"


def test_nameless_entity_skipped(isolated_db):
    resolved = {
        "resolved_entities": [{
            "canonical_name": "  ", "type": "concept", "aliases": [],
            "summary": None, "attributes": {},
            "facts": [{"predicate": "p", "value": "v", "persistence_value": 5}],
            "existing_entity": None,
        }],
        "relations": [],
    }
    _route(resolved)
    assert _entities() == []


# ── Intentions ───────────────────────────────────────────────────────────────

def test_intention_object_content_is_coerced_to_text(isolated_db):
    """Haiku sometimes returns ephemeral_content as an object ({'text': …}) or
    a list; the stored intention must be TEXT (coercion now in the core)."""
    from db import get_connection

    _process({
        "input_type": "ephemeral", "is_ephemeral": True,
        "ephemeral_content": {"text": "aller chercher les croquettes",
                              "when": "demain"},
    })
    conn = get_connection()
    try:
        rows = list(conn.execute("SELECT content FROM intentions"))
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "aller chercher les croquettes"


def _ancre_de_note_durable():
    """« Salon Vivatech le 20 juin » : un nom, une note datée, et rien d'autre.

    Zéro fait, zéro lien, aucune antériorité. C'est le cas exact que la
    quatrième condition de naissance couvrait, et le seul qu'elle couvrait
    seule.
    """
    return _route({
        "resolved_entities": [{
            "canonical_name": "Vivatech", "type": "concept",
            "aliases": [], "summary": None, "attributes": {},
            "facts": [],
        }],
        "relations": [],
    }, atomic_note="Salon Vivatech le 20 juin", atomic_note_kind="event",
       event_date="2026-06-20")


def test_durable_note_anchor_proposes_the_entity(isolated_db):
    """L'ancre d'une note durable PROPOSE la fiche, elle ne la crée plus.

    Cette quatrième condition avait été ouverte parce qu'une entité sans fait
    tombait sous le garde-fou anti-bruit : la date d'un salon vit dans la note
    de l'événement, pas dans un fait. La raison tient toujours, et l'ancre est
    conservée telle quelle — c'est sa CONSÉQUENCE qui change. Une fiche est
    l'objet le plus visible de la mémoire, et une fiche de trop ne se remarque
    pas plus qu'un renommage de trop.
    """
    from db import get_connection

    ids, _ = _ancre_de_note_durable()
    conn = get_connection()
    try:
        entites = list(conn.execute("SELECT canonical_name FROM entities"))
        props = list(conn.execute(
            "SELECT canonical_name, status FROM entity_creation_proposals"))
        notes = list(conn.execute("SELECT content FROM atomic_notes"))
    finally:
        conn.close()
    assert entites == [], "l'ancre ne doit plus fabriquer de fiche toute seule"
    assert ids == [], "aucune entité routée, donc rien à rendre à l'appelant"
    assert props == [("Vivatech", "pending")]
    # La capture, elle, n'attend pas : c'est l'entité qui est en question, pas
    # ce que l'utilisateur a écrit.
    assert len(notes) == 1


def test_le_repli_remet_la_creation_directe(isolated_db, monkeypatch):
    """Le levier de rollback du ticket, vérifié plutôt que promis."""
    from db import get_connection

    monkeypatch.setenv("SYNAPSE_ENTITY_CREATE_UNPROVEN", "1")
    ids, _ = _ancre_de_note_durable()
    conn = get_connection()
    try:
        entites = list(conn.execute("SELECT canonical_name FROM entities"))
        props = list(conn.execute("SELECT id FROM entity_creation_proposals"))
    finally:
        conn.close()
    assert entites == [("Vivatech",)]
    assert props == []
    assert len(ids) == 1


def test_validation_resolves_entity_by_alias(isolated_db):
    """Confirming a pending fact whose entity_canonical is an ALIAS must
    land on the canonical entity, not spawn a duplicate shell."""
    import json as _json
    from db import get_connection
    from dream_cycle.validation import record_and_apply_validation

    conn = get_connection()
    try:
        with conn:
            conn.execute("INSERT INTO entities (id, type, canonical_name, aliases, mention_count, persistence_value) "
                         "VALUES ('e-ch','person','Cici Huang','[\"Cici\"]',2,5)")
            conn.execute("INSERT INTO pending_facts (id, fact_data, validation_strategy) VALUES (?,?,?)",
                         ("p1", _json.dumps({"entity_canonical": "Cici", "predicate": "has_birthday",
                                             "value": "2026-06-16", "persistence_value": 5}), "passive"))
        with conn:
            res = record_and_apply_validation(conn, "p1", confirmed=True)
        assert res["status"] != "error"
        n_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        owner = conn.execute("SELECT entity_id FROM facts WHERE predicate='has_birthday'").fetchone()[0]
    finally:
        conn.close()
    assert n_entities == 1          # no duplicate shell
    assert owner == "e-ch"          # fact landed on the canonical entity


# ── Re-summary ───────────────────────────────────────────────────────────────

def test_fact_writes_flag_summary_stale(isolated_db):
    """Any fact write (insert via facts_store, lifecycle via API helper) must
    invalidate the entity's derived summary."""
    from db import get_connection
    from facts_store import insert_fact

    conn = get_connection()
    try:
        with conn:
            conn.execute("INSERT INTO entities (id, type, canonical_name, mention_count, persistence_value) "
                         "VALUES ('e40','person','Cici Huang',1,5)")
            insert_fact(conn, entity_id='e40', predicate='has_birthday',
                        value='2026-06-16', confidence=0.95)
        stale = conn.execute("SELECT summary_stale FROM entities WHERE id='e40'").fetchone()[0]
    finally:
        conn.close()
    assert stale == 1


def test_resummarize_uses_active_facts_and_clears_flag(isolated_db, monkeypatch):
    """step_resummarize derives from ACTIVE facts only (obsoleted excluded) and
    clears the stale flag. T5 : le POST part du core — stub HTTP local branché
    via le seam fuel (token syn-fuel- + SYNAPSE_FUEL_BASE_URL)."""
    import http.server
    import threading

    from db import get_connection
    from dream_cycle import cycle as cy

    seen = {}

    class _Stub(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["user"] = body["messages"][0]["content"]
            resp = json.dumps({
                "content": [{"type": "text",
                             "text": "Personne dont l'anniversaire est le 16 juin."}],
                "stop_reason": "end_turn",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "syn-fuel-test-stub")
    monkeypatch.setenv("SYNAPSE_FUEL_BASE_URL", f"http://127.0.0.1:{server.server_port}")

    conn = get_connection()
    try:
        with conn:
            conn.execute("INSERT INTO entities (id, type, canonical_name, summary, summary_stale, mention_count, persistence_value) "
                         "VALUES ('e41','person','Cici Huang','anniversaire la semaine prochaine',1,1,5)")
            conn.execute("INSERT INTO facts (id, entity_id, predicate, value, confidence) "
                         "VALUES ('f40','e41','has_birthday','2026-06-16',1.0)")
            conn.execute("INSERT INTO facts (id, entity_id, predicate, value, confidence, obsoleted_at) "
                         "VALUES ('f41','e41','has_birthday','2026-06-19',0.6,'2026-06-12T00:00:00')")
        # T5 : le core écrit sur sa propre connexion — pas de `with conn:` ici.
        regenerated = cy.step_resummarize([], conn, None)
        row = conn.execute("SELECT summary, summary_stale FROM entities WHERE id='e41'").fetchone()
    finally:
        conn.close()
        server.shutdown()
    # le prompt porte le fait actif, pas l'obsolète
    assert "2026-06-16" in seen["user"] and "2026-06-19" not in seen["user"]
    assert regenerated == ["e41"]
    assert row[0] == "Personne dont l'anniversaire est le 16 juin."
    assert row[1] == 0
