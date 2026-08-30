"""Le corpus, dit en français.

Pourquoi ce module existe. L'outil de revue affichait l'étiquette dans la langue
interne du corpus : des noms d'axes, des codes de frontière, des valeurs JSON.
Or la personne qui arbitre ne possède pas cette langue, et n'a aucune raison de
l'apprendre : ce qu'elle possède, et que la machine ne possède pas, c'est la
décision. « Pour cette capture, voilà ce qui devrait se passer, et pourquoi. »
Traduire cette décision en axes est un travail mécanique, donc c'est le travail
de la machine.

Faire arbitrer dans la langue interne ne rend pas la revue plus rigoureuse, elle
la rend plus FAUSSE : chaque code mal relu est une étiquette erronée, et une
étiquette erronée contamine tout ce que le harnais mesurera ensuite avec
assurance.

Rien ici n'est un modèle : ce sont des tables. Une même étiquette rend toujours
la même phrase, sinon deux sessions de revue ne compareraient pas la même chose.
"""
from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------- les groupes
#
# Un axe seul ne veut rien dire pour un humain ; une QUESTION, si. Les axes sont
# donc regroupés par la question qu'ils servent, et c'est la question qu'on
# affiche. Le groupe sert deux fois : à dire ce que le cas tranche, et surtout à
# dire ce qu'il ne tranche PAS, qui est l'information qui manquait le plus.

GROUPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "trace":    ("Que laisse cette capture, et sous quelle forme ?", ("note", "kind")),
    "perte":    ("Cette capture peut-elle disparaître sans laisser de trace ?", ("drop_guard",)),
    "duree":    ("Est-ce un rappel qui expire en 48 h, ou quelque chose de durable ?", ("ephemeral",)),
    "qui":      ("À qui appartient l'action ?", ("owner",)),
    "quand":    ("Quelle date retient-on, et revient-elle chaque année ?", ("event_date", "recurring")),
    "langue":   ("Dans quelle langue la note s'écrit-elle ?", ("language",)),
    "doute":    ("Faut-il te consulter avant de garder ça ?", ("needs_review",)),
    "fiches":   ("Qui ou quoi mérite une fiche dans ta mémoire ?", ("entity_expected", "no_entity")),
    "durable":  ("Que retient-on comme faits, liens ou projets durables ?", ("facts_min", "rel", "proj")),
    "interdit": ("Qu'est-ce qui ne doit surtout PAS naître ?", ("forbidden_value", "forbidden_predicate")),
    "negation": ("Cette capture retire-t-elle quelque chose qui était vrai ?", ("obsoletes", "no_obsolete")),
    "nom":      ("Cette capture change-t-elle le nom d'une entité ?", ("renamed_to", "no_rename")),
}

# Ce qu'on écrit quand le cas ne dit rien du groupe. Plus court que la question,
# parce que ça s'affiche en liste.
MUETS = {
    "trace": "ce que la capture laisse",
    "perte": "le risque de la perdre",
    "duree": "sa durée de vie",
    "qui": "à qui est l'action",
    "quand": "la date retenue",
    "langue": "la langue",
    "doute": "s'il faut te consulter",
    "fiches": "les fiches créées",
    "durable": "les faits et les liens",
    "interdit": "ce qui ne doit pas naître",
    "negation": "ce qui cesse d'être vrai",
    "nom": "un renommage",
}

KINDS = {
    "note": "NOTE, une pensée à toi qui mérite de ressurgir",
    "task": "TÂCHE, quelque chose encore à faire",
    "event": "ÉVÉNEMENT, une occurrence datée à laquelle tu assistes",
    "episode": "ÉPISODE, quelque chose de déjà vécu",
}

LANGUES = {"fr": "français", "en": "anglais", "es": "espagnol",
           "de": "allemand", "it": "italien", "pt": "portugais"}

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre")


def date_lisible(iso: str) -> str:
    """« 2026-07-20 » → « lundi 20 juillet 2026 ».

    Le jour de la semaine n'est pas de la décoration : le contexte du harnais est
    figé un LUNDI, et la moitié des pièges de résolution de date en dépendent.
    """
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso)
    return f"{_JOURS[d.weekday()]} {d.day} {_MOIS[d.month - 1]} {d.year}"


def phrase(axe: str, valeur) -> str:
    """Un axe et sa valeur, dits en une phrase que n'importe qui peut contester."""
    if axe == "note":
        return ("La capture laisse une note." if valeur
                else "La capture ne laisse AUCUNE note.")
    if axe == "kind":
        return f"Cette note est de type {KINDS.get(valeur, valeur)}."
    if axe == "drop_guard":
        return ("Cette capture ne doit pas disparaître : au moins une trace "
                "durable (note, fait, lien ou entrée de projet).")
    if axe == "ephemeral":
        return ("Elle part en rappel de 48 h, puis expire." if valeur
                else "Elle n'expire pas : rien ne la transforme en rappel.")
    if axe == "owner":
        return ("L'action est la tienne." if valeur is None
                else f"L'action est celle de {valeur}, pas la tienne : "
                     "elle ne doit pas atterrir sur ta liste.")
    if axe == "event_date":
        return ("Aucune date ne doit être retenue." if valeur is None
                else f"La date retenue est le {date_lisible(valeur)}.")
    if axe == "recurring":
        return ("Elle revient chaque année." if valeur
                else "Elle ne revient pas : c'est une date unique.")
    if axe == "language":
        return f"La note s'écrit en {LANGUES.get(valeur, valeur)}, jamais traduite."
    if axe == "needs_review":
        return ("Tu dois être consulté : la classification est trop douteuse "
                "pour être gardée telle quelle." if valeur
                else "Tu ne dois PAS être consulté : ce cas est clair, et te "
                     "poser la question encombrerait la file pour rien.")
    if axe == "rel":
        return f"Un lien est créé entre deux entités, contenant « {valeur} »."
    if axe == "proj":
        return ("Une entrée est ajoutée à un projet EXISTANT." if valeur == "existing"
                else "Un nouveau projet est créé, avec sa première entrée.")
    if axe == "facts_min":
        n = valeur
        return (f"Au moins {n} chose{'s' if n > 1 else ''} durable"
                f"{'s' if n > 1 else ''} en sort{'ent' if n > 1 else ''} : "
                "des faits ou des liens, comptés ensemble.")
    if axe == "entity_expected":
        return f"« {valeur} » mérite sa fiche dans ta mémoire."
    if axe == "no_entity":
        return (f"« {valeur} » ne doit PAS créer de fiche : rien ne dit qu'on "
                "en reparlera.")
    if axe == "forbidden_value":
        return (f"Aucun fait ne doit contenir la valeur « {valeur} » : "
                "la capture ne le dit pas, l'inventer serait une faute.")
    if axe == "forbidden_predicate":
        return (f"Aucun fait dont le nom contient « {valeur} » ne doit naître.")
    if axe == "obsoletes":
        pred, _, val = str(valeur).partition("=")
        cible = f"« {pred} = {val} »" if val else f"tout ce qui est enregistré sous « {pred} »"
        return (f"Ce qui était vrai cesse de l'être : {cible} est retiré de la "
                "fiche (réversible, rien n'est effacé).")
    if axe == "no_obsolete":
        return ("Rien de ce qui était vrai ne doit être retiré. Une négation de "
                "trop enlève une vérité, et personne ne remarque qu'un fait a "
                "disparu.")
    if axe == "renamed_to":
        return (f"Un renommage vers « {valeur} » est PROPOSÉ, et jamais appliqué "
                "tout seul.")
    if axe == "no_rename":
        return ("Aucun renommage n'est proposé : ni la simple mention d'un nom, "
                "ni un surnom, qui est un alias.")
    return f"{axe} = {valeur}"


def dit(cas: dict) -> list[tuple[str, list[str]]]:
    """Ce que le cas tranche, groupé par question, en français."""
    out = []
    for cle, (question, axes) in GROUPES.items():
        presents = [a for a in axes if a in cas]
        if presents:
            out.append((question, [phrase(a, cas[a]) for a in presents]))
    return out


def muet(cas: dict) -> list[str]:
    """Ce que le cas ne tranche pas, et sur quoi personne ne sera donc jugé.

    C'est l'information qui manquait : sans elle, on croit devoir arbitrer toute
    la capture alors qu'on n'arbitre qu'une phrase.
    """
    return [MUETS[cle] for cle, (_, axes) in GROUPES.items()
            if not any(a in cas for a in axes)]


# ------------------------------------------------------------- les frontières
#
# Le code chiffré est un index, pas une explication. Il vient de `frontieres.md`
# et n'a de sens que pour qui vient de le lire.

FRONTIERES = {
    # La porte
    "G-DATE": "Une date annule la porte : ça devient une occurrence, quelle que soit la tournure.",
    "G-ATTR": "Un énoncé qui ne fait que décrire quelqu'un ne laisse pas de note.",
    "G-LINK": "Un lien nu, sans prise de position, ne laisse pas de note.",
    "G-PROGRESS": "Un progrès sur un projet est un moment vécu : il laisse un épisode, et son entrée de projet part côté graphe.",
    "G-STATUS": "Un statut (« c'est envoyé », « j'ai déjà mangé ») raconte un moment vécu : il laisse un épisode.",
    "G-ROUTINE": "Une corvée ou une séance ordinaire déjà faite laisse un épisode, sans qu'on pèse son intérêt.",
    "G-HABIT": "Une habitude ou un trait de biographie, sans moment précis, est du savoir durable et pas une note.",
    "G-SVO": "Si tout se reformule en « untel fait ceci », c'est un fait et pas une note.",
    # Ligne 0, projet
    "R0a": "Une entreprise à plusieurs étapes est un PROJET, jamais une simple tâche.",
    "R0b": "Un projet qui naît laisse quand même sa phrase fondatrice comme note.",
    "R0c": "Un projet se nomme par son domaine durable, pas par l'action du jour.",
    "R0d": "Deux projets dans une même capture donnent deux entrées, pas une.",
    # Ligne 1, tâche
    "R1a": "Un verbe à l'infinitif ou à l'impératif est une tâche.",
    "R1b": "Une action adressée à quelqu'un, ou une démarche administrative, est une tâche.",
    "R1c": "Deux mots suffisent à faire une tâche.",
    "R1d": "Une tâche avec une échéance reste une TÂCHE, elle ne devient pas un événement.",
    "R1e": "Quand la capture rapporte l'action de quelqu'un d'autre, la tâche lui appartient.",
    "R1f": "Une action annulée garde la décision, mais pas la tâche.",
    "R1g": "Une corvée encore à faire est une tâche ordinaire, sans jugement sur sa trivialité.",
    "R1h": "Aucun objet n'est trop ordinaire pour faire une tâche : la distinction consommable / durable a disparu.",
    "R1i": "Une course déjà faite est un épisode, jamais une tâche à refaire.",
    "R1j": "Envoyer, payer, classer, déclarer : c'est un engagement, si court soit l'énoncé.",
    # Ligne 2, événement
    "R2a": "Une occurrence datée à laquelle tu assistes est un événement.",
    "R2b": "Une date plus un nom suffisent, même sans verbe.",
    "R2c": "Une tâche, on la FAIT ; un événement, on y ASSISTE. Le verbe ne prouve rien.",
    "R2d": "Une date relative doit ressortir en date absolue.",
    "R2e": "Anniversaire : une fête donne un événement, une date nue un événement à faire valider, une naissance rien. Jamais de récurrence, elle est portée par la fiche.",
    "R2f": "Ce qui est déjà passé n'est plus un événement à venir, c'est du vécu.",
    # Ligne 3, épisode
    "R3a": "Dès qu'une autre personne nommée y figure, c'est un épisode, si ordinaire soit-il.",
    "R3b": "Seul, mais dans un lieu qui mérite d'être nommé : c'est quand même un épisode.",
    "R3c": "Une première fois, un record, un résultat mesurable font un épisode. Un ressenti aussi, désormais.",
    "R3d": "Un épisode peut aussi établir quelque chose de durable : on garde les deux.",
    "R3e": "Un épisode a une date, et une date passée qui revient chaque année doit survivre.",
    "R3f": "Un épisode ne porte aucun drapeau d'expiration : le drapeau éphémère est retiré.",
    "R3g": "Ce qui n'est pas encore vécu n'est pas un épisode, c'est une intention.",
    # Ligne 4, note
    "R4a": "Une pensée à la première personne mérite de ressurgir.",
    "R4b": "Une citation, ou une idée extérieure sur laquelle tu prends position, mérite la note.",
    "R4c": "Une observation qui ne se réduit à aucun fait mérite la note.",
    "R4d": "Une décision, y compris celle de renoncer, mérite la note.",
    "R4e": "La phrase qui fonde un projet est sa première note.",
    # Transverses
    "X-EPH": "Le drapeau éphémère est retiré. Tant que le champ existe, il ne doit plus jamais être posé à vrai.",
    "X-CONF": "Le doute doit atteindre la file « À valider » quand il est réel, et jamais autrement.",
    "X-LANG": "La note s'écrit dans la langue de la capture, sans jamais traduire tes mots.",
    "X-ONE": "COMBIEN de souvenirs une capture laisse : deux quand elle demanderait deux lignes dans un carnet.",
    # Graphe
    "P-DUR": "Un fait n'existe que pour du durable. Ne rien retenir est parfois la bonne réponse.",
    "P-DEDUC": "Déduire, oui. Inventer, non.",
    "P-FR": "Quand l'objet est quelqu'un, on fait un LIEN et pas un fait. Jamais les deux.",
    "P-PERS": "Ce dont on reparlera mérite une fiche ; ce qu'on croise une fois, non.",
    "P-HEDGE": "Un fait prudent ne vaut pas un fait explicite, et n'entre pas au même endroit.",
    "P-BDAY": "Un anniversaire est toujours un fait ; une fête n'en est pas un.",
    "P-TYPE": "Le modèle ne choisit jamais un type d'entité : il le propose, tu le valides.",
    "P-PROJF": "Un fait de projet fait aussi du projet une entité.",
    # Familles
    "PERS-a": "Quelqu'un croisé une seule fois ne mérite pas de fiche.",
    "PERS-b": "Quelqu'un désigné par un rôle (« ma mère », « mon dentiste ») : fiche ou pas ?",
    "PERS-c": "Deux personnes du même prénom ne doivent pas fusionner.",
    "PERS-d": "Un nom partiel puis le nom complet désignent la même personne.",
    "NEG-a": "Une action annulée : la décision se garde, la tâche non.",
    "NEG-b": "« Il ne travaille plus là » retire le fait devenu faux.",
    "NEG-c": "« Elle n'a pas de chat », dit pour la première fois, ne retire rien.",
    "NEG-b′": "Un remplacement n'est pas une négation : le nouveau fait périme l'ancien tout seul.",
    "NEG-b″": "Une négation nuancée ne retire rien : sur un peut-être, on garde.",
    "NEG-d": "Un événement annulé (et pas une tâche).",
    "NEG-e": "Une correction d'une capture antérieure (« en fait c'était mercredi »).",
    "PER-a": "Une capture qui périme un fait doit émettre le NOUVEAU fait.",
    "PER-b": "Un renommage déclaré se propose, jamais ne s'applique.",
    "PER-c": "Un état transitoire ne doit pas devenir un fait durable.",
    "EMO": "Un ressenti rattaché à une cause devient une note ; un état nu devient un épisode.",
}


def frontiere(code: str | None) -> str | None:
    if not code:
        return None
    return FRONTIERES.get(code) or FRONTIERES.get(code.upper())


# ------------------------------------------- quel cas couvre quelle frontière
#
# La carte (`frontieres.md`) nomme déjà, cas par cas, la frontière que chacun
# couvre. Recopier ce lien dans le corpus serait le figer en double, et un
# double diverge : on le LIT, à chaque affichage. 56 cas y gagnent une phrase
# qu'il aurait fallu inventer autrement, et un cas cité sous trois codes en
# affiche trois, ce qu'un champ unique n'aurait pas su dire.

def _index_carte() -> dict[str, list[str]]:
    import re
    from pathlib import Path
    carte = Path(__file__).resolve().parent / "frontieres.md"
    index: dict[str, list[str]] = {}
    if not carte.is_file():
        return index
    for ligne in carte.read_text().splitlines():
        if not ligne.startswith("|"):
            continue
        cols = [c.strip() for c in ligne.strip("|").split("|")]
        if len(cols) < 3:
            continue
        code = cols[0].strip("` ")
        if code not in FRONTIERES:
            continue
        for cas_id in re.findall(r"`([a-z0-9][a-z0-9\-.]*)`", cols[2]):
            index.setdefault(cas_id, []).append(code)
    return index


CARTE = _index_carte()


def tranche(cas: dict) -> list[tuple[str, str]]:
    """Les frontières que ce cas couvre : (code, phrase).

    D'abord celle que le cas déclare, puis celles que la carte lui attribue.
    """
    vus, out = set(), []
    for code in ([cas["frontiere"]] if cas.get("frontiere") else []) + CARTE.get(cas["id"], []):
        if code in vus:
            continue
        vus.add(code)
        out.append((code, FRONTIERES.get(code) or "(pas encore glosée)"))
    return out
