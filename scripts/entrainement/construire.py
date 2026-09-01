"""Fabriquer le jeu d'entraînement à partir des baselines déjà payées.

Le corpus ne porte que des ASSERTIONS (`note`, `kind`, `facts_min`…), jamais la
sortie JSON attendue. Il n'y a donc rien à entraîner tel quel. Mais les
baselines récentes, elles, stockent la sortie complète du modèle sous `parsed` :
442 des 500 cas ont déjà une réponse Haiku qui passe toutes leurs assertions.
Ce script les récolte au lieu de repayer une passe.

Le filtre est le CORPUS, jamais le prompt. C'est ce qui rend la récolte légitime
malgré la garde anti-distillation : une sortie n'entre dans le jeu que si les
étiquettes écrites à la main la valident. Sur les axes que le corpus n'affirme
pas, en revanche, le modèle apprendra bel et bien les choix de Haiku — c'est la
limite assumée, et elle se réduit en étiquetant plus, pas en filtrant mieux.

⚠ Les `gaps` figés dans un fichier de baseline ont été calculés avec les
étiquettes DU JOUR DE LA PASSE. Cinq ont changé depuis le 30/08. On les
recalcule donc systématiquement contre le corpus d'aujourd'hui, en mémoire, sans
réécrire aucune baseline (`baseline rescore`, lui, réécrit le fichier en place).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from scripts.parity import score, split  # noqa: E402
from scripts.parity.corpus import SETS  # noqa: E402

BASELINES = _REPO / "scripts" / "parity" / "baselines"
SORTIE = _REPO / "scripts" / "entrainement" / "jeu"

# Ordre de préférence, du plus proche de la production au plus lointain. Une
# sortie récoltée tôt gagne : à qualité égale (toutes passent le corpus), on veut
# celle qu'a produite le prompt qui tourne aujourd'hui, pour que le style des
# champs non contraints soit homogène d'un exemple à l'autre.
PRIORITE = [
    "regles-v4-a", "regles-v4-b", "regles-v3-150", "regles-v2-150",
    "apres-reecriture-30-08", "apres-225-224", "ordinaire-apres-revue",
    "corpus-complet-20260828", "controle-3-correctifs", "controle-porte-et-graphe",
    "corpus-complet-20260825",
]

# Importées, jamais recopiées : c'est la liste qui dit quel champ appartient à
# quelle moitié, et le harnais a déjà payé deux fois le prix d'une copie qui
# dérive (`obsoleted_facts` puis `resources`, perdus en silence).
NOTE_FIELDS = split._NOTE_FIELDS
GRAPH_FIELDS = split._GRAPH_FIELDS


def systeme_court(prompt_file: str) -> str:
    """L'entête et le bloc DATES, sans le corps de règles.

    C'est CE prompt qu'on veut à l'inférence après entraînement, et donc CE
    prompt qu'il faut mettre dans les exemples : ce que le système dit pendant
    l'entraînement est ce que le modèle apprend à attendre. Entraîner avec le
    prompt complet apprendrait au modèle à mieux le suivre, pas à s'en passer,
    et la facture par note ne bougerait pas d'un centime.

    Ce qui reste est exactement ce qui ne peut PAS passer dans les poids :

      * l'entête — le rôle, la consigne de langue et le schéma JSON de sortie.
        Un schéma appris de mémoire dérive au premier champ ajouté ;
      * le bloc DATES — il énonce le jour courant et les deux semaines qui
        l'entourent. Il change tous les jours, donc il ne peut être que du
        contexte, jamais un poids.

    Le corps de règles, lui, est stable : c'est lui qu'on paie 4 700 tokens à
    chaque note et lui qu'on cherche à graver.
    """
    t = split._half_path(prompt_file).read_text()
    dates = re.search(r"<!-- DATES:DEBUT.*?<!-- DATES:FIN -->", t, re.S)
    if dates is None:
        raise SystemExit(f"bloc DATES introuvable dans {prompt_file}")
    return t.split("═══")[0].rstrip() + "\n\n" + dates.group(0)


def cas_du_corpus() -> dict[str, dict]:
    return {c["id"]: c for jeu in SETS.values() for c in jeu}


def recolter(cas: dict[str, dict]) -> tuple[dict[str, dict], dict[str, str]]:
    """Une sortie propre par cas, et d'où elle vient."""
    retenu: dict[str, dict] = {}
    origine: dict[str, str] = {}
    for label in PRIORITE:
        f = BASELINES / f"{label}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        if not d.get("model", "").startswith("anthropic"):
            continue
        for cid, rec in d.get("cases", {}).items():
            if cid in retenu or cid not in cas:
                continue
            parsed = rec.get("parsed")
            if not isinstance(parsed, dict):
                continue
            # Le recalcul contre les étiquettes d'aujourd'hui, pas contre celles
            # du jour de la passe.
            if score.gaps(cas[cid], parsed):
                continue
            retenu[cid] = parsed
            origine[cid] = label
    return retenu, origine


def demi(parsed: dict, champs: tuple[str, ...]) -> str:
    """La moitié demandée, en JSON canonique : ordre du schéma, pas d'espaces.

    Le modèle doit apprendre UNE forme. Laisser l'ordre des clés varier d'un
    exemple à l'autre lui ferait dépenser de la capacité sur du bruit de mise en
    page au lieu de la décision.
    """
    obj = {k: parsed.get(k) for k in champs}
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def decouper(cas: dict[str, dict], ids: list[str], part_test: float,
             graine: int) -> tuple[set[str], set[str]]:
    """80/20, avec une contrainte qui n'est pas négociable.

    Les DEUX côtés de chaque frontière restent à l'entraînement. Si on entraîne
    sur le corpus, le corpus DEVIENT la spécification : une règle qu'il ne
    démontre pas n'existera pas pour le modèle. Retirer un côté d'une frontière
    pour le mettre en test ne fait pas un test plus dur, il fait une
    spécification trouée.

    Le test se compose donc des cas SANS frontière, tirés à proportion par jeu et
    par langue pour que la répartition du test ressemble à celle du corpus.
    """
    # ⚠ LA DÉCOUPE SE FAIT PAR TEXTE, PAS PAR IDENTIFIANT. Le corpus réutilise
    # volontairement la même capture sous plusieurs identifiants pour éprouver
    # des axes différents : « acheter du pain » est à la fois `p1` et
    # `g-ephemeral-trivial`. Séparer les identifiants laisserait donc le MÊME
    # texte des deux côtés, et le modèle retrouverait au test une phrase vue à
    # l'entraînement. Mesuré le 2026-09-01 : six textes fuyaient ainsi.
    groupes: dict[str, list[str]] = collections.defaultdict(list)
    for i in ids:
        groupes[cas[i]["text"].strip().lower()].append(i)
    # Un groupe n'est éligible au test que si AUCUN de ses membres ne porte de
    # frontière : les deux côtés d'une frontière doivent rester à
    # l'entraînement, et un texte partagé emmènerait le reste avec lui.
    eligibles = [t for t, membres in groupes.items()
                 if not any(cas[i].get("frontiere") for i in membres)]
    vise = round(len(ids) * part_test)
    strates: dict[tuple, list[str]] = collections.defaultdict(list)
    for t in eligibles:
        tete = sorted(groupes[t])[0]
        strates[(cas[tete].get("set_"), cas[tete].get("language") or "fr")].append(t)
    rng = random.Random(graine)
    test: set[str] = set()
    n_eligibles = sum(len(groupes[t]) for t in eligibles)

    def prendre(textes: list[str]) -> None:
        for t in textes:
            test.update(groupes[t])

    # Un tour par strate, à proportion, puis complément au fil de l'eau : une
    # strate de trois cas ne doit pas disparaître du test par arrondi.
    for cle in sorted(strates, key=lambda k: (str(k[0]), str(k[1]))):
        pool = sorted(strates[cle])
        rng.shuffle(pool)
        n = max(1, round(len(pool) * vise / max(1, n_eligibles)))
        prendre(pool[:n])
    reste = [t for t in sorted(eligibles) if not (set(groupes[t]) & test)]
    rng.shuffle(reste)
    while len(test) < vise and reste:
        prendre([reste.pop()])
    return set(ids) - test, test


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--part-test", type=float, default=0.20)
    ap.add_argument("--graine", type=int, default=13)
    ap.add_argument("--systeme", choices=("court", "complet"), default="court",
                    help="court (défaut) : entête + bloc DATES, ce qu'on veut à "
                         "l'inférence. complet : le prompt de production entier, "
                         "pour mesurer ce que l'entraînement apporte à prompt égal.")
    ap.add_argument("--ecrire-prompts-courts", metavar="DOSSIER",
                    help="écrire les deux moitiés courtes dans DOSSIER, à "
                         "pointer ensuite par SYNAPSE_SPLIT_PROMPTS_DIR. Un "
                         "modèle entraîné sur le prompt court se mesure AVEC "
                         "le prompt court : lui envoyer celui de production "
                         "poserait une question qu'il n'a jamais vue, et on "
                         "conclurait à l'échec de l'entraînement.")
    ap.add_argument("--ecrire", action="store_true",
                    help="écrire les fichiers ; sans ce drapeau, on ne fait que "
                         "compter (rien n'est produit à l'aveugle)")
    args = ap.parse_args()

    if args.ecrire_prompts_courts:
        d = Path(args.ecrire_prompts_courts)
        d.mkdir(parents=True, exist_ok=True)
        for source, cible in (("note.md", "classifier-note.md"),
                              ("graph.md", "classifier-graph.md")):
            texte = systeme_court(source)
            (d / cible).write_text(texte)
            print(f"écrit : {d / cible}  ({len(texte)} car)")
        # Le harnais refuse un écart d'un seul caractère entre les deux blocs
        # DATES. Les moitiés ne peuvent pas s'inclure l'une l'autre, et deux
        # rappels de dates divergents ont déjà daté « le 24 » à un mois d'écart.
        os.environ["SYNAPSE_SPLIT_PROMPTS_DIR"] = str(d)
        import importlib
        importlib.reload(split)
        split.bloc_dates_identique()
        print("bloc DATES identique entre les deux moitiés : vérifié")
        return 0

    cas = cas_du_corpus()
    for jeu, liste in SETS.items():
        for c in liste:
            c["set_"] = jeu
    retenu, origine = recolter(cas)
    manquants = sorted(set(cas) - set(retenu))

    print(f"corpus            : {len(cas)} cas")
    print(f"sorties récoltées : {len(retenu)}  (aucun appel API)")
    print(f"sans sortie propre: {len(manquants)}")
    print()
    print("provenance :")
    for lab, n in collections.Counter(origine.values()).most_common():
        print(f"  {n:4d}  {lab}")

    ids = sorted(retenu)
    train, test = decouper(cas, ids, args.part_test, args.graine)
    print()
    print(f"entraînement : {len(train)} cas  ->  {2 * len(train)} paires")
    print(f"test         : {len(test)} cas   ->  {2 * len(test)} paires")
    lt = collections.Counter(cas[i].get("language") or "fr" for i in test)
    la = collections.Counter(cas[i].get("language") or "fr" for i in train)
    print(f"langue train : {dict(la)}")
    print(f"langue test  : {dict(lt)}")
    fr_test = sum(1 for i in test if cas[i].get("frontiere"))
    print(f"frontières laissées en test : {fr_test}  (doit valoir 0)")

    if manquants:
        print()
        print("cas sans sortie propre, à arbitrer à la main ou à rejouer :")
        for i in manquants:
            print(f"  {i:34s} {cas[i].get('set_','')}")

    if not args.ecrire:
        print("\n(compte seul — relancer avec --ecrire pour produire les fichiers)")
        return 0

    SORTIE.mkdir(parents=True, exist_ok=True)
    if args.systeme == "court":
        sys_note, sys_graph = systeme_court("note.md"), systeme_court("graph.md")
    else:
        sys_note = "\n\n".join(split._system("note.md"))
        sys_graph = "\n\n".join(split._system("graph.md"))
    print()
    print(f"système « {args.systeme} » : note {len(sys_note)} car · "
          f"graphe {len(sys_graph)} car")
    for nom, champs, systeme in (("note", NOTE_FIELDS, sys_note),
                                 ("graphe", GRAPH_FIELDS, sys_graph)):
        for part, groupe in (("train", train), ("test", test)):
            f = SORTIE / f"{nom}-{part}.jsonl"
            with f.open("w") as fh:
                for i in sorted(groupe):
                    fh.write(json.dumps({"id": i, "messages": [
                        {"role": "system", "content": systeme},
                        {"role": "user", "content": cas[i]["text"]},
                        {"role": "assistant", "content": demi(retenu[i], champs)},
                    ]}, ensure_ascii=False) + "\n")
            print(f"écrit : {f.relative_to(_REPO)}  ({len(groupe)} lignes)")
    (SORTIE / "provenance.json").write_text(json.dumps(
        {"origine": origine, "train": sorted(train), "test": sorted(test),
         "manquants": manquants, "graine": args.graine, "systeme": args.systeme}, ensure_ascii=False, indent=1))
    print(f"écrit : {(SORTIE / 'provenance.json').relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
