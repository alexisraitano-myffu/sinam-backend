"""Le palier exigé d'une entité qui n'a rien d'autre pour elle.

Ce fichier n'existait pas, et c'est ce qui a coûté deux jours de faux vert. Le
28/08, `LONE_ENTITY_PERSISTENCE` est passé de 2 à 4 dans le core. Aucun test
Python ne visait ce palier ; sept le traversaient par accident pour aller
mesurer autre chose. Quand la wheel a rattrapé le core, ces sept-là sont
tombés, et le seul changement qui comptait n'était signalé nulle part.

D'où la division : ici on mesure le verrou, et lui seul. Un futur ajustement du
palier doit faire rougir CE fichier, et laisser les autres verts.

La règle telle que le core l'écrit (`routing.rs`) : une entité inconnue, jamais
vue, sans relation et portant un seul fait doit atteindre une persistance de 4.
Dès qu'elle a n'importe quoi d'autre pour elle, une relation par exemple, le
palier ordinaire de 2 reprend. Et un fait qui n'est QUE la date de l'occurrence
ne compte pas, quelle que soit sa persistance.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _route(entities, relations=()):
    from datetime import datetime, timezone
    from db import get_connection
    from dream_cycle import cycle
    classified = {"input_type": "fact", "entities": list(entities),
                  "relations": list(relations), "project_entries": []}
    conn = get_connection()
    try:
        cycle._process_entry({"id": 1, "content": "capture de test"}, None, conn,
                             datetime.now(timezone.utc).isoformat(), False, False,
                             classified=classified)
    finally:
        conn.close()


def _noms():
    from db import cursor_to_dicts, get_connection
    conn = get_connection()
    try:
        return [r["canonical_name"] for r in cursor_to_dicts(
            conn.execute("SELECT canonical_name FROM entities"))]
    finally:
        conn.close()


def _entite(nom, persistance, predicat="is", type_="concept"):
    return {"canonical_name": nom, "type": type_, "type_proposal": None,
            "aliases": [], "summary": "", "attributes": {},
            "facts": [{"predicate": predicat, "value": "x",
                       "persistence_value": persistance,
                       "evidence_strength": "explicit"}]}


def test_seule_au_monde_sous_le_palier_ne_cree_rien(isolated_db):
    _route([_entite("Vivatech", 3)])
    assert _noms() == [], "3 ne suffit pas à une entité qui n'a rien d'autre"


def test_seule_au_monde_au_palier_cree_la_fiche(isolated_db):
    _route([_entite("Vivatech", 4)])
    assert _noms() == ["Vivatech"], "4 est le palier, il doit passer"


def test_la_date_redite_ne_compte_pas_meme_au_palier(isolated_db):
    """« Vivatech c'est le 24 » porte un fait daté et rien d'autre.

    C'est le cas qui a motivé le relèvement : la persistance mesure la nature de
    ce qui est affirmé, pas ce qu'on sait de l'entité, donc une simple date
    pouvait sortir à 3 ou 4 selon la passe. Le prédicat, lui, ne bouge pas.
    """
    _route([_entite("Vivatech", 4, predicat="event_date")])
    assert _noms() == [], "un fait qui n'est que la date ne fonde pas une fiche"


def test_une_relation_suffit_a_rendre_le_palier_ordinaire(isolated_db):
    """Le verrou ne relève PAS le palier de tout le monde.

    Sans ce test, remonter `MIN_ENTITY_PERSISTENCE` à 4 par mégarde passerait
    inaperçu : les trois premiers resteraient verts.
    """
    _route([_entite("Alexis", 4, type_="person"), _entite("Léna", 2, type_="person")],
           relations=[{"from": "Alexis", "predicate": "works_with", "to": "Léna",
                       "confidence": 0.9}])
    assert "Léna" in _noms(), "portée par une relation, 2 suffit"
