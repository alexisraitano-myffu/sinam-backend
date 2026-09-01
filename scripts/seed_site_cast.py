"""Le casting que le site raconte, posé dans la mémoire de démonstration.

Le site sinam raconte une mémoire précise depuis son premier écran : Marion,
amie de longue date, son fils Elio né le 12 mars, Marc et son livre sur les
cartes anciennes, la carbonara de Julien. Trente-trois mentions de Marion,
dix-sept d'Elio. Les captures d'écran du site doivent montrer CETTE
mémoire-là, sinon l'image dément le texte posé juste à côté.

`scripts/seed_demo_map.py` fabrique le volume (95 entités en communautés
denses, ce qui fait une belle carte) mais avec un autre casting. Ce script
ajoute par-dessus les quatre personnes du site et ce qui les relie, sans rien
toucher de l'existant.

Idempotent : les lignes portent des identifiants préfixés (`site-`, `sitef-`,
`siter-`, notes marquées `source_ids='site-demo'`) et sont effacées à chaque
passage. `--clean` les retire et s'arrête là.

    SYNAPSE_HOME=~/.synapse-shots python -m scripts.seed_site_cast
    SYNAPSE_HOME=~/.synapse-shots python -m scripts.seed_site_cast --clean

⚠️ Écrit dans le SYNAPSE_HOME configuré. À ne lancer que sur une base de
démonstration, jamais sur ~/.synapse.

Les écritures passent par les déclencheurs de synchro habituels : le téléphone
appairé les tire à la prochaine synchro, il n'y a rien à pousser à la main.
"""

import json
import math
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")

from db import get_connection
from embeddings import embed_text

TODAY = date.today()
TAU = 30.0  # τ d'Ebbinghaus en jours, comme dream_cycle/decay.py


def force(jours: int) -> float:
    """La force mémoire qui décroît avec le temps. Sert à ce que la carte
    montre des nœuds pâles : sans ça, tout est vif et l'oubli ne se voit pas."""
    return round(math.exp(-jours / TAU), 3)


def jour(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


# ── Le casting ────────────────────────────────────────────────────────────────
# (clé, nom, type, résumé, jours depuis la dernière mention, nb de mentions)
GENS = [
    ("marion", "Marion", "person",
     "Amie de longue date. Un fils, Elio, né le 12 mars. A repris le travail "
     "en septembre, après le congé.", 2, 9),
    ("elio", "Elio", "person",
     "Le fils de Marion, né le 12 mars.", 2, 4),
    ("marc", "Marc", "person",
     "Lit beaucoup, conseille souvent. Le livre sur les cartes anciennes vient "
     "de lui.", 11, 5),
    ("julien", "Julien", "person",
     "Cuisine. La carbonara vient de lui, et la règle sur la crème aussi.", 24, 6),
]

# (clé de l'entité, prédicat, valeur, confiance)
FAITS = [
    ("marion", "a_pour_enfant", "Elio", 0.94),
    ("marion", "lien", "amie de longue date", 0.88),
    ("marion", "situation_professionnelle", "a repris le travail", 0.71),
    ("marion", "habite", "Nantes", 0.55),          # le fait faible, à valider
    ("elio", "date_de_naissance", "12 mars", 0.96),
    ("elio", "a_pour_parent", "Marion", 0.92),
    ("marc", "a_conseille", "un livre sur les cartes anciennes", 0.87),
    ("julien", "cuisine", "carbonara — guanciale, pecorino, jamais de crème", 0.91),
]

# (de, prédicat, vers, confiance, statut de relecture)
LIENS = [
    ("marion", "parent_de", "elio", 0.95, "confirmed"),
    ("marc", "ami_de", "marion", 0.62, "confirmed"),
    # Celui-là reste à valider : la fiche du site doit montrer qu'on ne décide
    # pas tout seul à la place de quelqu'un.
    ("julien", "collegue_de", "marion", 0.48, "pending"),
]

# (titre, contenu, entités citées, jours, genre, date d'événement, récurrent)
NOTES = [
    ("Marion a eu un petit garçon",
     "Marion a eu un petit garçon le 12 mars, il s'appelle Elio.",
     ["Marion", "Elio"], 41, "note", None, 0),
    ("Déjeuner avec Marion",
     "Déjeuner avec Marion vendredi, elle reprend le travail.",
     ["Marion"], 2, "event", (TODAY + timedelta(days=3)).isoformat(), 0),
    ("Anniversaire d'Elio",
     "Anniversaire d'Elio, le 12 mars.",
     ["Elio", "Marion"], 41, "event", f"{TODAY.year + 1}-03-12", 1),
    ("Le livre conseillé par Marc",
     "Marc a conseillé un livre sur les cartes anciennes.",
     ["Marc"], 11, "note", None, 0),
    ("La carbonara de Julien",
     "La carbonara de Julien : guanciale, pecorino, jamais de crème, hors du feu.",
     ["Julien"], 24, "note", None, 0),
    ("Rappeler Marion pour le week-end",
     "Rappeler Marion pour le week-end.",
     ["Marion"], 1, "task", (TODAY + timedelta(days=2)).isoformat(), 0),
]


def nettoyer(conn) -> None:
    conn.execute("DELETE FROM relations WHERE id LIKE 'siter-%'")
    conn.execute("DELETE FROM facts WHERE id LIKE 'sitef-%'")
    conn.execute("DELETE FROM entities WHERE id LIKE 'site-%'")
    conn.execute("DELETE FROM atomic_notes WHERE source_ids = 'site-demo'")


def main() -> None:
    conn = get_connection()
    if "--clean" in sys.argv:
        with conn:
            nettoyer(conn)
        print("Casting du site retiré.")
        return

    with conn:
        nettoyer(conn)

        ids = {}
        for cle, nom, typ, resume, jours, mentions in GENS:
            eid = f"site-{cle}"
            ids[cle] = eid
            conn.execute(
                "INSERT INTO entities (id, type, canonical_name, mention_count, "
                "persistence_value, summary, last_mentioned, status, memory_strength, "
                "embedding) VALUES (?,?,?,?,?,?,?, 'active', ?, ?)",
                (eid, typ, nom, mentions, 5, resume, jour(jours), force(jours),
                 embed_text(f"{nom}. {resume}")),
            )

        for i, (cle, pred, val, conf) in enumerate(FAITS):
            conn.execute(
                "INSERT INTO facts (id, entity_id, predicate, value, confidence, "
                "persistence_value) VALUES (?,?,?,?,?,4)",
                (f"sitef-{i}", ids[cle], pred, val, conf),
            )

        for i, (a, pred, b, conf, statut) in enumerate(LIENS):
            conn.execute(
                "INSERT INTO relations (id, entity_from, predicate, entity_to, "
                "confidence, review_status) VALUES (?,?,?,?,?,?)",
                (f"siter-{i}", ids[a], pred, ids[b], conf, statut),
            )

        for titre, contenu, cites, jours, genre, quand, recurrent in NOTES:
            conn.execute(
                "INSERT INTO atomic_notes (title, content, summary, entities_mentioned, "
                "memory_strength, last_reactivated_at, created_at, kind, event_date, "
                "event_recurring, source_ids) VALUES (?,?,?,?,?,?,?,?,?,?, 'site-demo')",
                (titre, contenu, contenu, json.dumps(cites, ensure_ascii=False),
                 force(jours), jour(jours), jour(jours), genre, quand, recurrent),
            )

    e = conn.execute("SELECT COUNT(*) FROM entities WHERE id LIKE 'site-%'").fetchone()[0]
    f = conn.execute("SELECT COUNT(*) FROM facts WHERE id LIKE 'sitef-%'").fetchone()[0]
    r = conn.execute("SELECT COUNT(*) FROM relations WHERE id LIKE 'siter-%'").fetchone()[0]
    n = conn.execute("SELECT COUNT(*) FROM atomic_notes WHERE source_ids='site-demo'").fetchone()[0]
    print(f"Casting du site posé : {e} personnes, {f} faits, {r} liens, {n} notes.")


if __name__ == "__main__":
    main()
