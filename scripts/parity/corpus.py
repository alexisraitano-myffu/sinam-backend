"""Le corpus étiqueté, chargé depuis `corpus/*.jsonl`.

Synthétique, donc committable dans ce dépôt public. Les labels dérivent
STRICTEMENT des prompts de production : ce sont leurs règles écrites, pas des
préférences. Un cas dont le prompt ne tranche pas porte `ambigu: true` et sort
du décompte d'échec — il reste joué, parce qu'un cas qu'on n'exécute pas est un
cas dont on ne sait rien.

**Pourquoi du JSONL et plus du Python.** Le corpus vise 500 cas et l'outil de
revue doit pouvoir RÉÉCRIRE un cas validé. On ne réécrit pas du source Python :
il aurait fallu se contenter d'afficher, donc rééditer 500 fois à la main. Une
ligne par cas, un fichier par famille, et le diff git d'une validation tient sur
une ligne.

Le raisonnement derrière une étiquette vit dans `why`, plus dans un commentaire.
Il est ainsi greppable, affiché par l'outil de revue, et il survit à la
réécriture — ce qu'un commentaire ne fait pas. Le contexte qui porte sur une
FAMILLE entière, lui, est dans `corpus/README.md`.

Champs, tous optionnels sauf `id` et `text`. **Un champ absent = axe non
vérifié** : on ne reproche jamais à un modèle une exigence que personne ne lui a
formulée. C'est `score.py` qui les lit, et lui seul.

    note        True/False : la capture doit-elle produire une atomic_note
    kind        note | task | event | episode, vérifié seulement si une note est produite
    owner       None = l'auteur ; un nom = l'action est celle de quelqu'un d'autre
    recurring   valeur attendue de event_recurring
    event_date  date absolue attendue (YYYY-MM-DD), ou None pour « doit rester vide »
    language    code ISO 639-1 attendu
    needs_review  la capture doit-elle atteindre la file « À valider »
    drop_guard  True : cette capture NE DOIT PAS disparaître (note, entrée projet,
                fait ou relation — au moins une trace durable). Garde-fou du bug
                historique « action terse classée éphémère puis droppée ».
    rel         fragment attendu dans un prédicat de relation, ou LISTE de fragments
                quand la capture nomme plusieurs liens
    proj        "new" | "existing" : une entrée projet est attendue
    facts_min   nombre minimal de faits + relations (atomicité)
    entity_expected / no_entity   l'échelle de persistance décide du nœud
    forbidden_value / forbidden_predicate   ce qui ne doit PAS naître
    obsoletes   "predicate" ou "predicate=valeur" que la capture doit périmer
    no_obsolete True : la capture ne doit RIEN périmer
    renamed_to  le nouveau nom que la capture déclare, à proposer et jamais à appliquer
    no_rename   True : la capture ne déclare aucun renommage
    wm / repeat / expect          mode scénario : le fil, les passes, la branche attendue
    frontiere   le code de `frontieres.md` que ce cas couvre
    why         pourquoi cette étiquette, et ce qu'on a mesuré pour la fixer
    ambigu      True : le prompt ne tranche pas, observé mais hors décompte
    valide      date à laquelle l'étiquette a été validée à la main
    arbitrage   ce qu'Alexis a DIT, avec ses mots, quand l'étiquette ne convenait
                pas. Ce n'est pas une étiquette : c'est la décision, en attente
                d'être traduite en axes. La traduction est mécanique, donc elle
                revient à la machine ; la décision ne l'est pas, donc elle
                revient à lui. Un cas qui en porte un n'est PAS validé.
"""
from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"

# Le contrat de forme. Un champ hors liste est une FAUTE DE FRAPPE, pas une
# extension : un axe mal nommé ne lève rien, il ne vérifie simplement rien, et
# le cas passe pour vert en n'ayant rien mesuré. C'est le mode d'échec le plus
# coûteux d'un corpus, parce qu'il est silencieux et qu'il grandit.
CHAMPS = {
    "id", "text", "note", "kind", "owner", "recurring", "event_date",
    "language", "needs_review", "drop_guard", "rel", "proj", "facts_min",
    "entity_expected", "no_entity", "entity_proposed", "fact_proposed",
    "type_proposal", "no_type_proposal",
    # Ouvert le 2026-08-30 : le pendant POSITIF de `fact_proposed`. Sept
    # anniversaires ont perdu leur récurrence au motif que le fait la porte,
    # sans qu'aucun axe ne vérifie que ce fait naît.
    "fact_asserted",
    "resource_url", "resource_owner_type", "resource_comment",
    "forbidden_value", "forbidden_predicate",
    "obsoletes", "no_obsolete", "renamed_to", "no_rename",
    "cancels", "no_cancel", "memories",
    # Ouverts le 2026-08-29 sur la revue d'Alexis : où un fait s'accroche, et
    # une relation qui doit passer par la validation au lieu de naître seule.
    "facts_on", "relation_proposed",
    "wm", "repeat", "expect", "frontiere", "why",
    "ambigu", "valide", "arbitrage",
}

# Les champs qui ne sont pas des assertions. Un cas qui n'a QUE ceux-là ne
# vérifie rien, et le chargeur le dit.
META = {"id", "text", "wm", "repeat", "frontiere", "why", "ambigu", "valide",
        "arbitrage"}


def charger(nom: str) -> list[dict]:
    """Un fichier `corpus/<nom>.jsonl` → la liste de ses cas, validée."""
    chemin = CORPUS_DIR / f"{nom}.jsonl"
    if not chemin.is_file():
        raise SystemExit(f"jeu de cas introuvable : {chemin}")
    cas = []
    for n, ligne in enumerate(chemin.read_text().splitlines(), 1):
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            k = json.loads(ligne)
        except ValueError as e:
            raise SystemExit(f"{chemin.name}:{n} — JSON invalide : {e}") from e
        if not k.get("id") or not k.get("text"):
            raise SystemExit(f"{chemin.name}:{n} — `id` et `text` sont obligatoires")
        inconnus = set(k) - CHAMPS
        if inconnus:
            raise SystemExit(
                f"{chemin.name}:{n} ({k['id']}) — champs inconnus : "
                f"{', '.join(sorted(inconnus))}. Un axe mal nommé ne vérifie rien.")
        cas.append(k)
    return cas


def _tous() -> dict[str, list[dict]]:
    jeux = {p.stem: charger(p.stem) for p in sorted(CORPUS_DIR.glob("*.jsonl"))}
    vus: dict[str, str] = {}
    for nom, cas in jeux.items():
        for k in cas:
            if k["id"] in vus:
                raise SystemExit(
                    f"id en double : {k['id']} dans {vus[k['id']]} et {nom}. "
                    "Les baselines sont indexées dessus.")
            vus[k["id"]] = nom
    return jeux


JEUX = _tous()

GATE_CASES = JEUX["gate"]
HARD_CASES = JEUX["hard"]
ATOMICITY_CASES = JEUX["atomicity"]
ADVERSARIAL_CASES = JEUX["adversarial"]
SCENARIO_CASES = JEUX["scenario"]

# Les cas que le prompt ne tranche pas : joués, jamais comptés comme échecs.
AMBIGUOUS = {k["id"] for cas in JEUX.values() for k in cas if k.get("ambigu")}

# Les jeux que `baseline.py` rejoue. Le scénario en est exclu : il a son propre
# étage, avec ses passes répétées et son fil de mémoire de travail.
SETS = {nom: cas for nom, cas in JEUX.items() if nom != "scenario"}


def inertes() -> list[str]:
    """Les cas qui n'assertent RIEN. Un corpus en accumule sans qu'on le voie."""
    return [k["id"] for cas in JEUX.values() for k in cas if not (set(k) - META)]
