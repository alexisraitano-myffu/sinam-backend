"""Écrire des CAPTURES de corpus pour UNE frontière, dans un contexte propre.

    python -m scripts.parity.generer R4b --combien 6
    python -m scripts.parity.generer R4b | python -m scripts.parity.etiqueter

Ce script ne produit **que des captures** : `id`, `text`, `frontiere`, `why`.
L'étiquette attendue est posée par `etiqueter.py`, dans un second appel qui,
lui, voit tout.

C'est la raison d'être des deux fichiers. Le générateur ne voit NI
`classifier-note.md` NI `classifier-graph.md` : sans ça, écrire les cas depuis
les règles produirait des cas que ces règles gèrent déjà, et un corpus dérivé du
règlement ne peut pas trouver un trou que le règlement n'a pas. Mais cette garde
lui retire aussi ce qu'il faudrait pour étiqueter juste, et les trois premières
passes l'ont montré : bonnes captures, étiquettes fausses à chaque fois.

Séparer, c'est payer la garde là où elle sert (l'écriture) et pas là où elle
coûte (l'étiquetage). Un appel séparé est le seul moyen de le garantir plutôt
que de l'espérer.

La sortie va sur stdout et N'EST PAS écrite dans le corpus. Un cas entre par la
revue, à la main, jamais par un script.
"""
from __future__ import annotations

import argparse
import json
import unicodedata
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import corpus, providers  # noqa: E402
from scripts.parity.context import TODAY  # noqa: E402

_ICI = Path(__file__).resolve().parent

# Ce qu'une capture a le droit de porter, et rien de plus. Tout le reste est une
# assertion, donc le travail de l'étape suivante.
CHAMPS_CAPTURE = {"id", "text", "frontiere", "why"}


def ligne_de_frontiere(code: str) -> str:
    """La ligne de `frontieres.md` pour cette frontière.

    La ligne SEULE, sans son titre de section. Le titre nomme la destination
    (« Ligne 4, note ») : il a été passé au générateur tant que celui-ci
    étiquetait, parce qu'il devinait la destination à l'envers. Il n'étiquette
    plus, donc le titre redevient ce qu'il a toujours été, une fuite de routage
    sans contrepartie.
    """
    for ligne in (_ICI / "frontieres.md").read_text().splitlines():
        if ligne.startswith(f"| {code} |"):
            return ligne
    raise SystemExit(
        f"frontière « {code} » introuvable dans frontieres.md. "
        f"Elle s'écrit exactement comme la première colonne du tableau.")


def precisions(code: str) -> list[str]:
    """Les paragraphes hors tableau qui nomment cette frontière.

    Une ligne de tableau tient sur une ligne, et certaines frontières ne
    tiennent pas dessus : la carte les développe en prose juste après, et ces
    paragraphes-là ne partaient nulle part. P-TYPE l'a montré, sa ligne disait
    « type strictement dans la liste active » sans dire de quoi c'était le
    type, et la vague est partie sur le type d'une note. Le paragraphe qui le
    disait existait, à trente lignes de là.

    Ce n'est pas une fuite de règles : la carte décrit ce qu'une frontière
    mesure, jamais comment le classifieur y répond.
    """
    blocs = (_ICI / "frontieres.md").read_text().split("\n\n")
    return [b.strip() for b in blocs
            if code in b and not b.lstrip().startswith("|")]


def textes_existants(code: str) -> tuple[list[str], list[str]]:
    """Les captures déjà écrites : celles de cette frontière, puis les autres.

    Les deux listes comptent. La première dit ce que la frontière couvre déjà ;
    la seconde évite qu'une capture rangée ailleurs soit réécrite ici, ce qui
    arrivait tant que la déduplication ne regardait que la frontière visée.
    """
    ici, ailleurs = [], []
    for jeu in corpus.SETS.values():
        for cas in jeu:
            cible = ici if (cas.get("frontiere") or "").strip() == code else ailleurs
            cible.append(cas["text"])
    return ici, ailleurs


def normaliser_id(cas: dict) -> None:
    """Un identifiant de corpus s'écrit en ascii, minuscules, tirets.

    Le modèle écrit « g-date-progrès-daté-annulé » et le reste du corpus est en
    ascii. Un identifiant sert à se citer entre fichiers, dans un ticket, dans
    une commande `--cas` : les accents s'y perdent. On translittère plutôt que
    de l'exiger dans le prompt, où ça n'a jamais tenu.
    """
    brut = unicodedata.normalize("NFD", str(cas.get("id") or ""))
    sans = "".join(c for c in brut if unicodedata.category(c) != "Mn")
    cas["id"] = "".join(c if c.isalnum() else "-" for c in sans.lower()).strip("-")
    while "--" in cas["id"]:
        cas["id"] = cas["id"].replace("--", "-")


def valider(cas: dict, ordinaire: bool = False) -> int:
    """Les avertissements d'une capture. 0 = rien à signaler."""
    alertes = 0
    inconnus = set(cas) - CHAMPS_CAPTURE
    if inconnus:
        # Une assertion écrite ici n'est pas seulement hors sujet : elle serait
        # écrite sans les règles, donc probablement fausse, et une étiquette
        # fausse fait corriger ce qui marchait.
        print(f"⚠ {cas.get('id')} : n'écrit pas les étiquettes {sorted(inconnus)}, "
              f"c'est le travail d'etiqueter.py", file=sys.stderr)
        alertes += 1
    # En mode ordinaire une capture ne vise AUCUNE frontière, et en réclamer
    # une pousserait le modèle à en inventer, ce qui fausserait le compte de
    # couverture au lieu de le remplir.
    obligatoires = ("id", "text", "why") if ordinaire \
        else ("id", "text", "frontiere", "why")
    for champ in obligatoires:
        if not str(cas.get(champ) or "").strip():
            print(f"⚠ {cas.get('id', '?')} : `{champ}` vide", file=sys.stderr)
            alertes += 1
    return alertes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frontiere", nargs="?",
                    help="le code exact, ex. R4b, G-SVO, P-TYPE. Omis avec "
                         "--ordinaire, qui ne vise aucune frontière.")
    ap.add_argument("--combien", type=int, default=6)
    ap.add_argument("--modele", default="anthropic:claude-haiku-4-5-20251001")
    ap.add_argument("--ordinaire", action="store_true",
                    help="écrire du volume BANAL au lieu de cas de bord. Le "
                         "corpus sert aussi de spécification si on entraîne un "
                         "modèle dessus, et ses proportions deviennent alors "
                         "l'a priori du modèle : un corpus fait uniquement de "
                         "bords enseignerait un monde où tout est ambigu.")
    ap.add_argument("--deja", type=Path,
                    help="un fichier de captures DÉJÀ générées mais pas encore "
                         "versées au corpus, à exclure aussi. Sans lui, deux "
                         "appels du même paquet ne se voient pas et réécrivent "
                         "les mêmes captures : la garde anti-doublon ne lit que "
                         "le corpus sur disque, et rien n'y est écrit avant la "
                         "revue humaine.")
    ap.add_argument("--langue", default="fr",
                    help="fr, en, … La cible du corpus est 30 %% d'anglais, et "
                         "il en portait 11 %% au 2026-08-29 : la proportion "
                         "n'a aucune importance pour une suite de tests et "
                         "enseignerait « le français est le défaut » à un "
                         "modèle entraîné.")
    args = ap.parse_args()

    if args.ordinaire == bool(args.frontiere):
        raise SystemExit(
            "Choisir l'un des deux : un code de frontière pour des cas de "
            "bord, ou --ordinaire pour du volume banal. Les deux ensemble "
            "n'ont pas de sens, aucun des deux non plus.")

    systeme = (_ICI / "generation.md").read_text()
    en_attente: list[str] = []
    if args.deja and args.deja.is_file():
        for ligne in args.deja.read_text().splitlines():
            ligne = ligne.strip()
            if ligne:
                en_attente.append(json.loads(ligne)["text"])
    if args.ordinaire:
        # Tout le corpus sert de garde anti-doublon : sans frontière visée, il
        # n'y a plus de « ici » et « ailleurs », il n'y a qu'un seul tas.
        ici, ailleurs = [], ([c["text"] for jeu in corpus.SETS.values()
                             for c in jeu] + en_attente)
        entete = [
            f"Mode ORDINAIRE. Aucune frontière à viser. Langue : {args.langue}.",
            "",
            "Écris des captures BANALES, celles qu'une personne tape sans y "
            "penser. Si tu hésites en écrivant l'une d'elles, c'est un cas de "
            "bord et il n'a pas sa place ici. N'écris pas le champ `frontiere`.",
            "",
        ]
    else:
        ici, ailleurs = textes_existants(args.frontiere)
        ailleurs = ailleurs + en_attente
        detail = precisions(args.frontiere)
        entete = [
            f"Frontière à couvrir : {args.frontiere}",
            "",
            "Sa ligne dans la carte des frontières, telle quelle :",
            ligne_de_frontiere(args.frontiere),
            "",
            ("Ce que la carte précise en plus sur cette frontière :\n\n"
             + "\n\n".join(detail) + "\n") if detail else "",
        ]

    demande = "\n".join([
        *entete,
        f"Le temps de référence est {TODAY}, un lundi. Écris tes dates en "
        f"relatif, comme une personne le fait ; les résoudre n'est pas ton "
        f"travail.",
        "",
        ("Captures déjà écrites pour cette frontière :\n"
         + "\n".join(f"  - {t}" for t in ici)) if ici
        else "Aucune capture n'existe encore pour cette frontière.",
        "",
        "Captures déjà présentes ailleurs dans le corpus, à ne pas réécrire :",
        "\n".join(f"  - {t}" for t in ailleurs),
        "",
        f"Écris {args.combien} captures. Une ligne JSON par cas, rien autour.",
    ])

    r = providers.call(args.modele, [systeme], demande, max_tokens=4000,
                       temperature=1.0)
    if not r.ok:
        raise SystemExit(f"appel échoué : {r}")

    # La déduplication se fait ici et pas dans le prompt. On lui donne la liste
    # des textes existants, et il en a recopié un au mot près : lui demander de
    # comparer des chaînes est lui demander ce qu'on sait calculer.
    def nu(s: str) -> str:
        return "".join(c for c in s.lower() if c.isalnum())

    connus = {nu(x): x for x in ici + ailleurs}

    bons = mauvais = 0
    for brute in r.text.splitlines():
        brute = brute.strip().strip("`")
        if not brute.startswith("{"):
            continue
        try:
            cas = json.loads(brute)
        except ValueError as e:
            print(f"⚠ ligne illisible ({e}) : {brute[:80]}", file=sys.stderr)
            mauvais += 1
            continue
        normaliser_id(cas)
        double = connus.get(nu(str(cas.get("text", ""))))
        if double is not None:
            print(f"⚠ {cas.get('id')} : doublon exact d'une capture existante, "
                  f"écarté — « {double} »", file=sys.stderr)
            mauvais += 1
            continue
        mauvais += valider(cas, args.ordinaire)
        bons += 1
        print(json.dumps(cas, ensure_ascii=False))

    print(f"\n{bons} captures, {mauvais} avertissement(s). "
          f"Étiqueter avec : python -m scripts.parity.etiqueter",
          file=sys.stderr)


if __name__ == "__main__":
    main()
