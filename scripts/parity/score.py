"""SYN-184 — le scoring, en un seul endroit.

Jusqu'ici il vivait dans `gate.py::_quality_notes`, donc il ne servait qu'aux 12
cas de l'étage 1 : les 49 autres étaient ENREGISTRÉS et jamais jugés. C'est
tenable à 59 cas, où on relit le diff à l'œil. À 500, non.

Ce module prend un cas et une réponse parsée, et rend la liste des écarts. Rien
d'autre. Les étages l'appellent, l'outil de revue aussi.

Six axes ouverts ici que la carte des frontières (`frontieres.md`) réclamait, et
sans lesquels les cas correspondants seraient inertes :

    obsoletes             la capture retire-t-elle bien le fait qu'elle nie
    no_obsolete           et ne retire-t-elle RIEN quand elle ne nie rien
    needs_review          la confiance atteint-elle la file « À valider »
    event_date            le relatif a-t-il été résolu en absolu
    language              la langue détectée est-elle la bonne
    forbidden_predicate   ce fait ne doit PAS naître
    entity_expected       cette entité mérite son nœud
    no_entity             celle-ci non

Les trois derniers existaient déjà comme champs dans `corpus.py` et n'étaient lus
par personne.
"""
from __future__ import annotations

import re

VALID_NOTE_KINDS = {"note", "task", "event", "episode"}

# Miroir de `routing.rs:39` (REVIEW_CONFIDENCE_THRESHOLD_DEFAULT). Le prompt, lui,
# dit au modèle « < 0,6 quand tu hésites vraiment ». On score sur 0,7 et pas sur
# 0,6 parce que ce qui compte n'est pas d'obéir au prompt, c'est d'ATTEINDRE la
# file de validation : une capture à 0,65 est douteuse et arrive bien en revue.
REVIEW_THRESHOLD = 0.7

# Chaque axe pointe la frontière qu'il sert, pour agréger un rapport par
# frontière au lieu d'une liste de 500 lignes.
AXES = {
    "note": "routage",
    "kind": "routage",
    "ephemeral": "X-EPH",
    "owner": "R1e",
    "recurring": "R2e/R3e",
    "event_date": "R2d",
    "language": "X-LANG",
    "needs_review": "X-CONF",
    "rel": "P-FR",
    "proj": "R0",
    "facts_min": "X-ONE",
    "entity_expected": "P-PERS",
    "no_entity": "P-PERS",
    "forbidden_value": "P-DEDUC",
    "forbidden_predicate": "P-BDAY",
    "obsoletes": "NEG-b",
    "no_obsolete": "NEG-c",
    "drop_guard": "perte",
}


def has_note(parsed: dict) -> bool:
    note = parsed.get("atomic_note")
    return bool(note) and str(note).strip().lower() not in ("", "null", "none")


def kind_of(parsed: dict) -> str | None:
    """Le kind APRÈS normalisation du core (`routing.rs:196`).

    Mesurer la sortie brute surestimerait l'échec là où la production s'en sort,
    et le masquerait là où « task » silencieusement dégradé en « note » fait
    vraiment perdre une tâche.
    """
    if not has_note(parsed):
        return None
    raw = parsed.get("atomic_note_kind")
    return raw if isinstance(raw, str) and raw else "note"


def _nullable_str(value) -> str | None:
    """Chaîne vide et « null » textuel valent None : c'est ce que produisent les
    petits modèles quand on leur demande un champ nullable."""
    got = value.strip() if isinstance(value, str) else None
    if not got or got.lower() in ("null", "none"):
        return None
    return got


def _entity_names(parsed: dict) -> set[str]:
    names = set()
    for e in parsed.get("entities") or []:
        canonical = e.get("canonical_name")
        if isinstance(canonical, str) and canonical.strip():
            names.add(canonical.strip().lower())
        for alias in e.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                names.add(alias.strip().lower())
    return names


def _all_facts(parsed: dict) -> list[dict]:
    out = []
    for e in parsed.get("entities") or []:
        out.extend(f for f in (e.get("facts") or []) if isinstance(f, dict))
    return out


def _count_durable(parsed: dict) -> int:
    """Faits + relations. L'atomicité (SYN-98) se mesure sur les deux : un lien
    entre deux entités nommées sort en relation, jamais en fait, et compter les
    seuls faits sanctionnerait le modèle qui a raison."""
    return len(_all_facts(parsed)) + len(parsed.get("relations") or [])


def gaps(case: dict, parsed: dict | None, skip: tuple[str, ...] = ()) -> list[str]:
    """Les écarts entre l'étiquette validée et ce que le modèle a rendu.

    Un champ absent du cas = axe non vérifié : on ne reproche jamais à un modèle
    une exigence que personne ne lui a formulée. C'est la même règle qu'à
    l'étage 4 (`prose.py`), et elle a été payée trois fois là-bas.
    """
    if not parsed:
        return ["réponse inexploitable"]

    out: list[str] = []
    note = has_note(parsed)
    kind = kind_of(parsed)

    # `drop_guard` : la capture doit laisser une trace DURABLE (note, entrée
    # projet, fait ou relation). Une intention éphémère ne compte pas, elle
    # expire en 48 h : c'est le mode d'échec historique.
    #
    # Il était vérifié dans `gate.py::_check_blocking`, donc UNIQUEMENT sur les
    # 12 cas de l'étage 1. Les huit autres cas qui le portent (`t1`..`t7`, `a1`,
    # `a2`, `x-mixed-tense`, `x-pure-episode`…) l'assertaient dans le vide :
    # deux d'entre eux n'assertaient même rien d'autre. Ici il compte partout.
    # Le gate le passe en `skip`, sinon il le compterait deux fois.
    if case.get("drop_guard") and "drop_guard" not in skip:
        kept = (note or bool(parsed.get("project_entries"))
                or _count_durable(parsed) > 0)
        if not kept:
            expire = " (classée éphémère : expire en 48 h)" \
                if parsed.get("is_ephemeral") else ""
            out.append(f"drop_guard : capture sans trace durable{expire}")

    # --- routage ---------------------------------------------------------
    if "note" in case and note != case["note"]:
        out.append(f"note attendue={case['note']} obtenue={note}")

    if case.get("kind") and note:
        raw = parsed.get("atomic_note_kind")
        if kind != case["kind"]:
            got = f"{kind} (brut={raw!r}, défaut du core)" if raw != kind else kind
            out.append(f"kind attendu={case['kind']} obtenu={got}")

    if "ephemeral" in case and bool(parsed.get("is_ephemeral")) != case["ephemeral"]:
        out.append(f"ephemeral attendu={case['ephemeral']}")

    # SYN-182 — le propriétaire de l'action. None = l'auteur ; un nom veut dire
    # que la capture rapportait l'action de quelqu'un d'autre.
    if "owner" in case:
        got = _nullable_str(parsed.get("atomic_note_owner"))
        if got != case["owner"]:
            out.append(f"owner attendu={case['owner']!r} obtenu={got!r}")

    if "recurring" in case and bool(parsed.get("event_recurring")) != case["recurring"]:
        out.append(f"recurring attendu={case['recurring']} "
                   f"obtenu={bool(parsed.get('event_recurring'))}")

    # R2d — la résolution du relatif à l'absolu. Un modèle qui rend « mardi »
    # passait jusqu'ici sans que rien ne le voie.
    if "event_date" in case:
        got = _nullable_str(parsed.get("event_date"))
        want = case["event_date"]
        if want is None:
            if got is not None:
                out.append(f"event_date attendu absent, obtenu {got!r}")
        elif got != want:
            forme = "" if got is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", got) \
                else " (pas au format YYYY-MM-DD)"
            out.append(f"event_date attendu={want} obtenu={got!r}{forme}")

    # X-LANG — la langue est le seul champ qui décide dans quelle langue la note
    # sera ÉCRITE. Se tromper là traduit les mots de l'utilisateur.
    if "language" in case:
        got = _nullable_str(parsed.get("language"))
        got = got.lower()[:2] if got else None
        if got != case["language"]:
            out.append(f"language attendu={case['language']!r} obtenu={got!r}")

    # X-CONF — la capture atteint-elle la file « À valider » ? Les deux sens
    # comptent : un doute absent perd la capture en silence, un doute de trop
    # noie la file et la rend inutilisable.
    if "needs_review" in case:
        conf = parsed.get("classification_confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else 1.0
        atteint = conf < REVIEW_THRESHOLD
        if atteint != case["needs_review"]:
            attendu = "doit passer par « À valider »" if case["needs_review"] \
                else "ne doit PAS encombrer « À valider »"
            out.append(f"{attendu} : confiance {conf} (seuil {REVIEW_THRESHOLD})")

    # --- graphe ----------------------------------------------------------
    if case.get("rel"):
        rels = parsed.get("relations") or []
        if not any(case["rel"] in str(r.get("predicate", "")).lower() for r in rels):
            out.append(f"relation '{case['rel']}' absente")

    if case.get("proj") and not (parsed.get("project_entries") or []):
        out.append("entrée projet absente")

    if case.get("facts_min"):
        n = _count_durable(parsed)
        if n < case["facts_min"]:
            out.append(f"atomicité : {n} fait(s)/relation(s) pour "
                       f"{case['facts_min']} attendu(s)")

    # P-PERS — l'échelle de persistance décide du nœud. Les deux côtés existaient
    # dans le corpus depuis le 21/08 et n'étaient lus par personne.
    if case.get("entity_expected"):
        if case["entity_expected"].strip().lower() not in _entity_names(parsed):
            out.append(f"entité '{case['entity_expected']}' absente")

    if case.get("no_entity"):
        if case["no_entity"].strip().lower() in _entity_names(parsed):
            out.append(f"entité '{case['no_entity']}' créée alors qu'elle est "
                       f"sous le seuil de persistance")

    # P-DEDUC / P-BDAY — dire qu'un fait ne doit PAS naître. Sans ces deux axes,
    # « la fête ne produit aucun has_birthday » n'est pas exprimable, et une
    # invention ne se voit qu'à la relecture.
    if case.get("forbidden_value"):
        needle = case["forbidden_value"].lower()
        for f in _all_facts(parsed):
            if needle in str(f.get("value", "")).lower():
                out.append(f"valeur inventée : {f.get('predicate')}="
                           f"{f.get('value')!r}")
                break

    # NEG-b / NEG-c — la négation d'un fait. Le premier axe vérifie qu'elle est
    # EXPRIMÉE, le second qu'elle ne l'est pas à tort. Les deux comptent autant :
    # une négation manquée laisse un faux durable sur la fiche, une négation de
    # trop retire une vérité, et personne ne remarque qu'un fait a disparu.
    if case.get("obsoletes"):
        want = case["obsoletes"]
        want_pred, _, want_val = want.partition("=")
        got = _obsoleted(parsed)
        hit = [
            o for o in got
            if str(o.get("predicate", "")).strip().lower() == want_pred.strip().lower()
            and (not want_val
                 or str(o.get("value") or "").strip().lower() == want_val.strip().lower())
        ]
        if not hit:
            vu = ", ".join(
                f"{o.get('predicate')}={o.get('value')!r}" for o in got) or "rien"
            out.append(f"négation '{want}' absente (obsoleted_facts : {vu})")

    if case.get("no_obsolete"):
        got = _obsoleted(parsed)
        if got:
            vu = ", ".join(f"{o.get('predicate')}={o.get('value')!r}" for o in got)
            out.append(f"négation de trop : {vu}")

    if case.get("forbidden_predicate"):
        needle = case["forbidden_predicate"].lower()
        for f in _all_facts(parsed):
            if needle in str(f.get("predicate", "")).lower():
                out.append(f"prédicat interdit : {f.get('predicate')}="
                           f"{f.get('value')!r}")
                break

    return out


def _obsoleted(parsed: dict) -> list[dict]:
    return [o for o in (parsed.get("obsoleted_facts") or []) if isinstance(o, dict)]


def axes_of(case: dict) -> list[str]:
    """Les axes que ce cas vérifie réellement.

    Présence de la clé, pas vérité de la valeur : `owner=None` et
    `event_date=None` sont des assertions à part entière (« ce champ doit rester
    vide »), et ce sont même les plus utiles, celles qui empêchent un modèle de
    remplir un champ à tout hasard.

    Sert à prouver qu'une frontière est couverte, et à repérer un cas qui
    n'asserte rien du tout.
    """
    return [k for k in AXES if k in case]
