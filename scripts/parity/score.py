"""Le scoring, en un seul endroit.

Jusqu'ici il vivait dans `gate.py::_quality_notes`, donc il ne servait qu'aux 12
cas de l'étage 1 : les 49 autres étaient ENREGISTRÉS et jamais jugés. C'est
tenable à 59 cas, où on relit le diff à l'œil. À 500, non.

Ce module prend un cas et une réponse parsée, et rend la liste des écarts. Rien
d'autre. Les étages l'appellent, l'outil de revue aussi.

Six axes ouverts ici que la carte des frontières (`frontieres.md`) réclamait, et
sans lesquels les cas correspondants seraient inertes :

    renamed_to            le renommage déclaré est-il proposé
    no_rename             et n'est-il pas proposé quand rien ne le déclare
    obsoletes             la capture retire-t-elle bien le fait qu'elle nie
    no_obsolete           et ne retire-t-elle RIEN quand elle ne nie rien
    cancels               l'action ANNULÉE est-elle nommée, dans les mots de la capture
    no_cancel             et le champ reste-t-il vide quand rien n'est annulé
    needs_review          la confiance atteint-elle la file « À valider »
    event_date            le relatif a-t-il été résolu en absolu
    language              la langue détectée est-elle la bonne
    forbidden_predicate   ce fait ne doit PAS naître
    entity_expected       cette entité mérite son nœud
    no_entity             celle-ci non
    entity_proposed       celle-ci ne doit PAS naître seule : elle passe en file
    fact_proposed         ce fait ne doit PAS être asserté : il passe en file de validation
    resource_url          ce lien est-il enregistré comme ressource
    resource_owner_type   et à quel TYPE d'entité appartient-il
    resource_comment      les mots de l'auteur sur le lien sont-ils gardés

Les trois derniers existaient déjà comme champs dans `corpus.py` et n'étaient lus
par personne.
"""
from __future__ import annotations

import re

from scripts.parity.context import TODAY


def _liste(valeur) -> list[str]:
    """Une chaîne, une liste de chaînes, ou rien. Toujours une liste en sortie.

    Une valeur qui n'est pas une chaîne est IGNORÉE plutôt que castée : un
    `no_entity: 1` casté en "1" mesurerait une entité nommée « 1 », qui
    n'existe jamais, et le cas passerait pour vert sans rien tester.
    """
    if valeur is None:
        return []
    if isinstance(valeur, str):
        return [valeur] if valeur.strip() else []
    if isinstance(valeur, (list, tuple)):
        return [v for v in valeur if isinstance(v, str) and v.strip()]
    return []

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
    "entity_proposed": "P-CREATE",
    "type_proposal": "P-TYPE",
    "no_type_proposal": "P-TYPE",
    "fact_proposed": "F-QUEUE",
    "fact_asserted": "F-QUEUE",
    "resource_url": "RES",
    "resource_owner_type": "RES",
    "resource_comment": "RES",
    # Ces deux-là sont GÉNÉRIQUES : ils disent « ceci ne doit pas naître », et
    # servent aujourd'hui à P-DEDUC, P-BDAY, EMO et PER-c. Les rattacher à une
    # frontière particulière gonflait son décompte avec les cas des autres.
    "forbidden_value": "interdit",
    "forbidden_predicate": "interdit",
    "obsoletes": "NEG-b",
    "no_obsolete": "NEG-c",
    "cancels": "NEG-d",
    "no_cancel": "NEG-d",
    "memories": "X-ONE",
    "renamed_to": "PER-b",
    "no_rename": "PER-b",
    "drop_guard": "perte",
}


def souvenirs(parsed: dict) -> list[dict]:
    """Miroir de `routing.rs::souvenirs`. Sixième copie du core dans ce fichier.

    `memories` est la forme canonique depuis le passage aux souvenirs multiples ; les champs au singulier
    restent lus en repli, parce qu'ils sont la sortie de toutes les baselines
    enregistrées avant ce jour. Un tableau à un élément se relit comme un
    scalaire, donc les axes existants ne changent pas de sens.
    """
    def lire(v: dict) -> dict | None:
        texte = str(v.get("note") or v.get("atomic_note") or "").strip()
        if not texte or texte.lower() in ("null", "none"):
            return None
        kind = v.get("kind") or v.get("atomic_note_kind")
        return {
            "note": texte,
            "kind": kind if isinstance(kind, str) and kind else "note",
            "owner": _nullable_str(v.get("owner") if "owner" in v
                                   else v.get("atomic_note_owner")),
            "event_date": _nullable_str(v.get("event_date")),
            "event_recurring": bool(v.get("event_recurring")),
            "summary": v.get("summary"),
        }

    liste = parsed.get("memories")
    if isinstance(liste, list) and liste:
        vus, out = set(), []
        for m in liste:
            if not isinstance(m, dict):
                continue
            s = lire(m)
            if s and s["note"].lower() not in vus:
                vus.add(s["note"].lower())
                out.append(s)
        return out
    un = lire(parsed)
    return [un] if un else []


def has_note(parsed: dict) -> bool:
    if souvenirs(parsed):
        return True
    # Miroir de `routing.rs` : renoncer est une décision, et une décision se
    # garde. Mesuré le 2026-08-28, le modèle cesse d'écrire la note dès qu'il
    # remplit `cancels_action` — il traite la capture comme réglée par le
    # pointeur. Quatre formulations et deux emplacements du prompt n'y ont rien
    # changé, donc le core repêche la capture brute en note. Sans ce miroir, le
    # harnais afficherait en perte des captures que la production garde.
    cancels = parsed.get("cancels_action")
    return bool(cancels) and str(cancels).strip().lower() not in ("", "null", "none")


def kind_of(parsed: dict) -> str | None:
    """Le kind APRÈS normalisation du core (`routing.rs:196`).

    Mesurer la sortie brute surestimerait l'échec là où la production s'en sort,
    et le masquerait là où « task » silencieusement dégradé en « note » fait
    vraiment perdre une tâche.
    """
    liste = souvenirs(parsed)
    if liste:
        return liste[0]["kind"]
    # Repêché par le core depuis le pointeur d'annulation : c'est une note.
    return "note" if has_note(parsed) else None


def _nullable_str(value) -> str | None:
    """Chaîne vide et « null » textuel valent None : c'est ce que produisent les
    petits modèles quand on leur demande un champ nullable."""
    got = value.strip() if isinstance(value, str) else None
    if not got or got.lower() in ("null", "none"):
        return None
    return got


def _ressource(parsed: dict, url: str) -> dict | None:
    """L'item de `resources` qui porte cette URL, ou None."""
    cible = url.strip().lower()
    for r in parsed.get("resources") or []:
        if isinstance(r, dict) and (r.get("url") or "").strip().lower() == cible:
            return r
    return None


def rien_garde(parsed: dict) -> bool:
    """Miroir de `routing.rs` : la capture n'a-t-elle RIEN laissé ?

    Troisième copie manuelle du core dans ce fichier, et la raison est la même
    que pour `confiance_du_fait` : sans elle, l'axe `needs_review` mesurerait
    la confiance du modèle au lieu de mesurer ce qui arrive vraiment. Or le
    modèle rend 1,0 sur un abandon évident, et il a raison — il note sa
    confiance dans le ROUTAGE. C'est l'ABANDON qui part en file, et c'est le
    core qui le décide, en comptant.

    Une fiche SANS fait, sans note et sans lien ne compte pas : un nom seul
    n'apprend rien.
    """
    if souvenirs(parsed):
        return False
    # Le repêchage de l'annulation a déjà écrit la note côté core : sans cette
    # ligne le harnais enverrait en file une capture que la production garde.
    if (parsed.get("cancels_action") or "").strip():
        return False
    for champ in ("relations", "project_entries", "resources", "obsoleted_facts"):
        if parsed.get(champ):
            return False
    for e in parsed.get("entities") or []:
        if isinstance(e, dict) and e.get("facts"):
            return False
    return True


def confiance_du_fait(persistence: int, evidence: str, existing: bool = False,
                      mentions: int = 1) -> float:
    """Miroir de `routing.rs::compute_confidence`. Les deux doivent bouger ensemble.

    Recopié, donc exposé au même piège que la liste de fusion de `split.py` : si
    la formule change côté Rust et pas ici, cet axe se met à mesurer une porte
    qui n'existe plus. C'est la deuxième copie manuelle du core dans ce fichier,
    et la raison de la garder est la même que pour `porte_de_creation` : sans
    elle, la destination d'un fait n'est pas exprimable dans une étiquette.
    """
    base = {"hedged": 0.65, "implicit": 0.40}.get(evidence, 0.92)
    bonus = 0.05 if existing else 0.0
    bonus += min(mentions * 0.02, 0.05)
    bonus += {5: 0.2, 4: 0.15, 3: 0.05, 2: 0.0, 1: -0.1}.get(persistence, 0.0)
    score = base + bonus
    if evidence == "hedged":
        score = min(score, 0.84)
    return max(0.0, min(1.0, score))


def porte_du_fait(parsed: dict, entite: str, predicat: str) -> str:
    """Où ce fait atterrit : « asserté », « proposé », « en revue », « absent ».

    Les trois destinations de `dispatch_facts` et leurs deux seuils, rejoués sur
    la sortie du classifieur. Le modèle ne choisit AUCUNE des trois : il choisit
    `evidence_strength` et `persistence_value`, et la porte fait le reste. C'est
    exactement pour ça que l'axe est utile — il mesure la conséquence, pas
    l'intention, et une étiquette « proposé » se lit sans connaître la formule.

    « existe déjà » est inatteignable ici pour la même raison qu'à la création :
    le harnais fige un contexte sans mémoire antérieure.
    """
    cible_e = entite.strip().lower()
    cible_p = predicat.strip().lower()
    for e in parsed.get("entities") or []:
        canon = (e.get("canonical_name") or "").strip().lower()
        alias = [(a or "").strip().lower() for a in (e.get("aliases") or [])]
        if cible_e not in (canon, *alias):
            continue
        for f in e.get("facts") or []:
            if not isinstance(f, dict):
                continue
            if cible_p not in str(f.get("predicate") or "").strip().lower():
                continue
            pers = f.get("persistence_value")
            pers = pers if isinstance(pers, int) else 3
            c = confiance_du_fait(pers, str(f.get("evidence_strength") or "explicit"))
            if c > 0.85:
                return "asserté"
            return "proposé" if c >= 0.5 else "en revue"
    return "absent"


def porte_de_creation(parsed: dict, nom: str) -> str:
    """Ce que `routing.rs` ferait de cette entité : « créée », « proposée », « ignorée ».

    Miroir délibéré du core, et il faut le savoir : la vraie décision est en
    Rust (`step4_route`), ici on la rejoue sur la sortie du classifieur. Les
    deux doivent bouger ensemble.

    Une des quatre clauses de naissance est INVÉRIFIABLE ici et le restera :
    « l'entité existe déjà ». Le harnais fige le contexte sans aucune mémoire
    antérieure, donc elle est toujours fausse. Ce que cet axe mesure, c'est
    donc la première rencontre, qui est justement le moment où la question se
    pose.
    """
    cible = nom.strip().lower()
    entite = None
    for e in parsed.get("entities") or []:
        canon = (e.get("canonical_name") or "").strip().lower()
        alias = [(a or "").strip().lower() for a in (e.get("aliases") or [])]
        if cible == canon or cible in alias:
            entite = e
            break
    if entite is None:
        return "absente"

    for rel in parsed.get("relations") or []:
        for bout in ("from", "to"):
            if (rel.get(bout) or "").strip().lower() == cible:
                return "créée"

    porteuse_de_lien = any(
        (r.get("entity_canonical") or "").strip().lower() == cible
        for r in (parsed.get("resources") or [])
    )
    if porteuse_de_lien:
        return "créée"

    faits = entite.get("facts") or []
    # Le core ne retombe PAS sur le défaut 3 quand il n'y a aucun fait : il
    # force 0, et c'est ce qui rend la clause « nommée en passant » atteignable.
    if faits:
        forte = max(
            (f.get("persistence_value") if isinstance(f.get("persistence_value"), int)
             else 3)
            for f in faits
        )
        # Le palier monte quand l'entité n'a RIEN d'autre pour elle : inconnue
        # (toujours vrai ici, le harnais n'a pas de mémoire), hors lien, hors
        # ressource, et UN seul fait. La persistance dit la nature de ce qui est
        # affirmé, pas ce qu'on sait de l'entité, et à 2 elle fabriquait une
        # fiche sur « Vivatech c'est le 24 ».
        palier = 4 if len(faits) <= 1 else 2
        # Un fait qui n'est QUE la date de l'occurrence ne dit rien de l'entité.
        # Discriminant stable, contrairement à la persistance : le modèle sort
        # 3 ou 4 sur la MÊME capture d'une passe à l'autre.
        date_redite = len(faits) == 1 and str(
            faits[0].get("predicate") or "").strip().lower() in ("event_date", "occurs_on")
        if forte >= palier and not date_redite:
            return "créée"

    # Un ÉPISODE ancre autant qu'une tâche ou un événement : il asserte que
    # quelque chose a eu lieu. L'exclure faisait IGNORER « Bibliothèque
    # Forney », sans fiche et sans question.
    return "proposée" if souvenirs(parsed) else "ignorée"


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


_MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
         "septembre", "octobre", "novembre", "decembre",
         "january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december")


def _sans_accents(texte: str) -> str:
    table = str.maketrans("éèêëàâäûüùîïôö", "eeeeaaauuuiioo")
    return texte.lower().translate(table)


def jour_nu_recale(date: str, capture: str, kind: str | None) -> str:
    """Miroir de `routing.rs::snap_bare_day`. Cinquième copie du core ici.

    Un jour NU sans mois se range du côté qu'ouvre le kind : un `episode` est
    déjà vécu, un `event` ou une `task` sont devant. Le temps du verbe ne sert
    à rien, il ment (« j'ai réservé pour le 28 » est au passé et vise le
    futur) ; le kind, lui, ne ment pas. Sans ce miroir, le harnais afficherait
    en écart une date que la production corrige.
    """
    vers_le_passe = {"episode": True, "event": False, "task": False}.get(kind or "")
    if vers_le_passe is None or len(date) < 10:
        return date
    if any(m in _sans_accents(capture) for m in _MOIS):
        return date
    tete = date[:10]
    try:
        y, m, d = int(tete[0:4]), int(tete[5:7]), int(tete[8:10])
    except ValueError:
        return date
    if (tete <= TODAY) == vers_le_passe:
        return date
    m += -1 if vers_le_passe else 1
    if m == 0:
        m, y = 12, y - 1
    elif m == 13:
        m, y = 1, y + 1
    import calendar
    if d > calendar.monthrange(y, m)[1]:
        return date
    return f"{y:04d}-{m:02d}-{d:02d}{date[10:]}"


def _all_facts(parsed: dict) -> list[dict]:
    out = []
    for e in parsed.get("entities") or []:
        out.extend(f for f in (e.get("facts") or []) if isinstance(f, dict))
    return out


def _count_durable(parsed: dict) -> int:
    """Faits + relations. L'atomicité se mesure sur les deux : un lien
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
            out.append("drop_guard : capture sans trace durable")

    # --- routage ---------------------------------------------------------
    if "note" in case and note != case["note"]:
        out.append(f"note attendue={case['note']} obtenue={note}")

    # une capture peut laisser PLUSIEURS souvenirs, donc les axes qui
    # portaient sur LE souvenir portent maintenant sur l'ENSEMBLE : ils passent
    # si l'un d'eux satisfait l'attente. Sur une capture à un seul souvenir, qui
    # est le cas normal, ça ne change rien du tout.
    liste = souvenirs(parsed)

    if case.get("kind") and note:
        vus = [m["kind"] for m in liste] or [kind]
        if case["kind"] not in vus:
            out.append(f"kind attendu={case['kind']} obtenu={', '.join(map(str, vus))}")

    # Le NOMBRE de souvenirs, quand le cas le dit. C'est l'axe qui voit la
    # sur-découpe : une capture hachée en trois passe tous les autres axes,
    # parce que chacun se contente d'un souvenir qui satisfait l'attente.
    if "memories" in case and len(liste) != case["memories"]:
        textes = " | ".join(m["note"][:40] for m in liste) or "aucun"
        out.append(f"souvenirs attendus={case['memories']} obtenus={len(liste)} ({textes})")

    # le propriétaire de l'action. None = l'auteur; un nom veut dire
    # que la capture rapportait l'action de quelqu'un d'autre.
    if "owner" in case:
        vus = [m["owner"] for m in liste] or [None]
        if case["owner"] not in vus:
            out.append(f"owner attendu={case['owner']!r} obtenu={vus!r}")

    if "recurring" in case:
        vus = [m["event_recurring"] for m in liste] or [False]
        if case["recurring"] not in vus:
            out.append(f"recurring attendu={case['recurring']} obtenu={vus}")

    # R2d — la résolution du relatif à l'absolu. Un modèle qui rend « mardi »
    # passait jusqu'ici sans que rien ne le voie.
    if "event_date" in case:
        vus = [m["event_date"] for m in liste]
        want = case["event_date"]
        if want is None:
            portees = [d for d in vus if d is not None]
            if portees:
                out.append(f"event_date attendu absent, obtenu {portees!r}")
        elif want not in vus:
            got = vus[0] if vus else None
            forme = "" if got is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", got) \
                else " (pas au format YYYY-MM-DD)"
            out.append(f"event_date attendu={want} obtenu={vus!r}{forme}")

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
        vide = rien_garde(parsed)
        atteint = conf < REVIEW_THRESHOLD or vide
        if atteint != case["needs_review"]:
            attendu = "doit passer par « À valider »" if case["needs_review"] \
                else "ne doit PAS encombrer « À valider »"
            out.append(f"{attendu} : confiance {conf} (seuil {REVIEW_THRESHOLD}), "
                       f"trace laissée={'aucune' if vide else 'oui'}")

    # --- graphe ----------------------------------------------------------
    # Une chaîne, ou une LISTE de fragments. Ouvert le 2026-08-25 sur la revue
    # d'Alexis : « Yanis is Marc and Julie's son and Léna's brother » nomme deux
    # liens, et l'axe n'en tenait qu'un. Compter les liens (`facts_min`) ne dit
    # pas LESQUELS, donc un modèle qui produit deux fois le même passait.
    if case.get("rel"):
        rels = parsed.get("relations") or []
        preds = [str(r.get("predicate", "")).lower() for r in rels]
        attendus = case["rel"] if isinstance(case["rel"], list) else [case["rel"]]
        # Un fragment peut nommer plusieurs mots pour le MÊME lien, séparés par
        # `|`. Ouvert le 2026-08-25 : l'étiquette exigeait `brother` et le modèle
        # rendait `sibling_of`, qui est le lien demandé sous un autre nom.
        # Arbitré par Alexis : ce qui compte est que l'identification fraternelle
        # se fasse, pas le mot choisi pour la dire.
        for attendu in attendus:
            variantes = [v.strip().lower() for v in str(attendu).split("|") if v.strip()]
            if not any(v in p for v in variantes for p in preds):
                out.append(f"relation '{attendu}' absente (vu : {preds or 'aucune'})")

    # PER-c — À QUELLE FICHE un fait s'accroche. Ouvert le 2026-08-29 sur la revue
    # d'Alexis : « les faits service lent et poisson frais doivent être ajoutés à
    # la brasserie du port ». `facts_min` compte les faits et ne dit pas où ils
    # vont ; un modèle qui accroche tout à l'auteur passait l'axe sans que la
    # fiche du lieu apprenne quoi que ce soit, ce qui est précisément le défaut.
    # Forme : {"la brasserie du port": 2} — au moins 2 faits SUR cette fiche.
    for nom, mini in (case.get("facts_on") or {}).items():
        cible = nom.strip().lower()
        n = 0
        for e in parsed.get("entities") or []:
            if str(e.get("canonical_name", "")).strip().lower() == cible:
                n += len([f for f in (e.get("facts") or []) if isinstance(f, dict)])
        if n < mini:
            out.append(f"fiche '{nom}' porte {n} fait(s) pour {mini} attendu(s)")

    # PER-d — une relation qui ne peut PAS se deviner doit partir en validation.
    # Ouvert le 2026-08-29 : « la relation ne peut pas être devinée, elle doit
    # être validée ». Une soirée à trois ne prouve pas que Julie et Romain sont
    # un couple. L'axe échoue des DEUX côtés : relation absente, ou posée avec
    # une confiance qui la fait naître sans que personne ne l'ait confirmée.
    for attendu in _liste(case.get("relation_proposed")):
        variantes = [v.strip().lower() for v in str(attendu).split("|") if v.strip()]
        vue = None
        for r in parsed.get("relations") or []:
            if any(v in str(r.get("predicate", "")).lower() for v in variantes):
                vue = r
                break
        if vue is None:
            out.append(f"relation '{attendu}' absente, elle devait partir en validation")
        elif float(vue.get("confidence") or 1.0) >= REVIEW_THRESHOLD:
            out.append(f"relation '{attendu}' posée à {vue.get('confidence')} "
                       f"(seuil {REVIEW_THRESHOLD}) : elle naît sans validation")

    if case.get("proj") and not (parsed.get("project_entries") or []):
        out.append("entrée projet absente")

    if case.get("facts_min"):
        n = _count_durable(parsed)
        if n < case["facts_min"]:
            out.append(f"atomicité : {n} fait(s)/relation(s) pour "
                       f"{case['facts_min']} attendu(s)")

    # P-PERS — l'échelle de persistance décide du nœud. Les deux côtés existaient
    # dans le corpus depuis le 21/08 et n'étaient lus par personne.
    # Une capture nomme souvent DEUX choses qui méritent chacune leur fiche
    # (« Léa m'a recommandé la pizzeria Chez Gino »), et le champ n'en tenait
    # qu'une : la seconde n'était pas mesurée. Les trois axes acceptent donc
    # une chaîne OU une liste, comme `rel` le fait déjà.
    for nom in _liste(case.get("entity_expected")):
        if nom.strip().lower() not in _entity_names(parsed):
            out.append(f"entité '{nom}' absente")

    # RES — un lien appartient à quelque chose, et ce quelque chose dit tout.
    # Le type de l'entité qui le reçoit distingue les deux formes : « le lien
    # donne accès à une chose qui a son identité » et « le lien EST la chose ».
    if case.get("resource_url"):
        r = _ressource(parsed, case["resource_url"])
        if r is None:
            vus = [x.get("url") for x in (parsed.get("resources") or [])]
            out.append(f"ressource '{case['resource_url']}' absente "
                       f"(vu : {vus or 'aucune'})")
        else:
            if case.get("resource_owner_type"):
                nom = (r.get("entity_canonical") or "").strip().lower()
                vu = next(
                    ((e.get("type") or "").strip().lower()
                     for e in (parsed.get("entities") or [])
                     if (e.get("canonical_name") or "").strip().lower() == nom),
                    None,
                )
                if vu != case["resource_owner_type"].strip().lower():
                    out.append(f"le lien appartient à un '{vu or 'rien'}' au lieu "
                               f"d'un '{case['resource_owner_type']}'")
            if "resource_comment" in case:
                attendu = case["resource_comment"]
                got = (r.get("user_comment") or "").strip()
                if attendu is None:
                    if got:
                        out.append(f"commentaire de trop sur le lien : {got!r}")
                elif attendu.strip().lower() not in got.lower():
                    out.append(f"les mots de l'auteur sur le lien sont perdus "
                               f"(attendu {attendu!r}, vu {got or 'rien'!r})")

    for nom in _liste(case.get("entity_proposed")):
        vu = porte_de_creation(parsed, nom)
        if vu != "proposée":
            out.append(f"entité '{nom}' : {vu} au lieu d'être proposée")

    # P-BDAY — la troisième marche de l'échelle anniversaire. « fait interdit »
    # et « fait asserté » ne suffisaient pas à dire la seule bonne réponse quand
    # la date vient d'une FÊTE : le jour est très probable et pas certain, donc
    # ni inventer ni jeter, demander.
    if case.get("fact_proposed"):
        ent, _, pred = case["fact_proposed"].partition(":")
        vu = porte_du_fait(parsed, ent, pred)
        if vu != "proposé":
            out.append(f"fait '{pred}' sur '{ent}' : {vu} au lieu d'être proposé")

    # La marche du HAUT de la même échelle, ouverte le 2026-08-30. Quand la
    # capture ÉNONCE la date, il n'y a rien à deviner et le fait doit être
    # asserté, pas proposé. L'axe existe parce que la règle des anniversaires
    # s'appuie désormais sur ce fait pour porter la récurrence annuelle : sans
    # lui, on retire la récurrence de la note sans vérifier que quoi que ce soit
    # la reprend.
    if case.get("fact_asserted"):
        ent, _, pred = case["fact_asserted"].partition(":")
        vu = porte_du_fait(parsed, ent, pred)
        if vu != "asserté":
            out.append(f"fait '{pred}' sur '{ent}' : {vu} au lieu d'être asserté")

    # P-TYPE — le type d'une entité ne s'invente pas : hors vocabulaire actif,
    # le modèle sort `concept` et remplit `type_proposal`, un humain valide.
    # Les deux axes vérifient l'APPARIEMENT, pas l'appartenance du type à la
    # liste : la liste est dynamique et vit en base, le harness ne l'a pas. Or
    # c'est bien l'appariement qui lâche — mesuré le 2026-08-20 sur E2B
    # contraint, `type_proposal` était rempli là où le type était déjà actif,
    # ce qui noie la file de validation sous des propositions inutiles.
    if case.get("type_proposal"):
        want = case["type_proposal"].strip().lower()
        vus = {str(e.get("canonical_name") or "").strip().lower():
               e.get("type_proposal")
               for e in (parsed.get("entities") or []) if isinstance(e, dict)}
        if want not in vus:
            out.append(f"entité '{case['type_proposal']}' absente, donc son "
                       f"type ne peut pas être proposé")
        elif not vus[want]:
            out.append(f"type de '{case['type_proposal']}' asserté sans "
                       f"proposition, la validation humaine est contournée")

    if case.get("no_type_proposal"):
        vus = [e.get("canonical_name") for e in (parsed.get("entities") or [])
               if isinstance(e, dict) and e.get("type_proposal")]
        if vus:
            out.append(f"type proposé de trop sur {vus}, alors que le type "
                       f"attendu est déjà actif")

    for nom in _liste(case.get("no_entity")):
        if nom.strip().lower() in _entity_names(parsed):
            out.append(f"entité '{nom}' créée alors qu'elle est "
                       f"sous le seuil de persistance")

    # P-DEDUC / P-BDAY — dire qu'un fait ne doit PAS naître. Sans ces deux axes,
    # « la fête ne produit aucun has_birthday » n'est pas exprimable, et une
    # invention ne se voit qu'à la relecture.
    if case.get("forbidden_value"):
        needle = case["forbidden_value"].lower()
        for f in _all_facts(parsed):
            valeur = jour_nu_recale(str(f.get("value", "")), case["text"], kind)
            if needle in valeur.lower():
                out.append(f"valeur inventée : {f.get('predicate')}={valeur!r}")
                break

    # PER-b — le renommage déclaré en capture. Le nom canonique titre la fiche
    # et sort dans le digest : le manquer laisse la mémoire afficher un nom que
    # l'utilisateur a lui-même corrigé, le proposer à tort lui pose une question
    # sur l'identité d'une entité alors que rien ne l'a demandé.
    if case.get("renamed_to"):
        want = case["renamed_to"].strip().lower()
        vus = [str(e.get("renamed_to") or "").strip().lower()
               for e in (parsed.get("entities") or []) if isinstance(e, dict)]
        if want not in vus:
            out.append(f"renommage vers '{case['renamed_to']}' absent "
                       f"(vu : {[v for v in vus if v] or 'aucun'})")

    if case.get("no_rename"):
        vus = [(e.get("canonical_name"), e.get("renamed_to"))
               for e in (parsed.get("entities") or [])
               if isinstance(e, dict) and str(e.get("renamed_to") or "").strip()]
        if vus:
            out.append(f"renommage de trop : {vus}")

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

    # NEG-d — l'action annulée. On ne mesure ici que le POINTEUR : le core
    # cherche ensuite la tâche visée, et cette moitié-là n'est pas mesurable
    # dans un harnais au contexte figé, qui n'a aucun état antérieur.
    if case.get("cancels"):
        got = (parsed.get("cancels_action") or "").strip().lower()
        if not got:
            out.append(f"action annulée non nommée (attendu ~ {case['cancels']!r})")
        else:
            # Les mots de la capture, pas les nôtres : on demande que le noyau
            # attendu s'y retrouve, pas une chaîne identique.
            noyau = case["cancels"].strip().lower()
            if noyau not in got and got not in noyau:
                out.append(f"action annulée {got!r}, attendu ~ {noyau!r}")

    if case.get("no_cancel"):
        got = (parsed.get("cancels_action") or "").strip()
        if got:
            out.append(f"annulation de trop : {got!r}")

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
