"""Écrire des CAPTURES de corpus pour UNE frontière, dans un contexte propre.

    python -m scripts.parity.generer R4b --combien 6
    python -m scripts.parity.generer R4b | python -m scripts.parity.etiqueter

Ce script ne produit **que des captures** : `id`, `text`, `frontiere`,
`arbitrage`. L'étiquette attendue est posée par `etiqueter.py`, dans un second
appel qui, lui, voit tout.

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
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import corpus, providers  # noqa: E402
from scripts.parity.context import TODAY  # noqa: E402

_ICI = Path(__file__).resolve().parent

# Ce qu'une capture a le droit de porter, et rien de plus. Tout le reste est une
# assertion, donc le travail de l'étape suivante.
CHAMPS_CAPTURE = {"id", "text", "frontiere", "arbitrage"}


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


def valider(cas: dict) -> int:
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
    for champ in ("id", "text", "frontiere", "arbitrage"):
        if not str(cas.get(champ) or "").strip():
            print(f"⚠ {cas.get('id', '?')} : `{champ}` vide", file=sys.stderr)
            alertes += 1
    return alertes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frontiere", help="le code exact, ex. R4b, G-SVO, P-TYPE")
    ap.add_argument("--combien", type=int, default=6)
    ap.add_argument("--modele", default="anthropic:claude-haiku-4-5-20251001")
    args = ap.parse_args()

    ligne = ligne_de_frontiere(args.frontiere)
    systeme = (_ICI / "generation.md").read_text()
    ici, ailleurs = textes_existants(args.frontiere)

    demande = "\n".join([
        f"Frontière à couvrir : {args.frontiere}",
        "",
        "Sa ligne dans la carte des frontières, telle quelle :",
        ligne,
        "",
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

    # On valide la forme ici plutôt que de laisser un JSON cassé arriver plus
    # loin : une ligne mal formée coûte plus cher à trouver à l'étape suivante.
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
        mauvais += valider(cas)
        bons += 1
        print(json.dumps(cas, ensure_ascii=False))

    print(f"\n{bons} captures, {mauvais} avertissement(s). "
          f"Étiqueter avec : python -m scripts.parity.etiqueter",
          file=sys.stderr)


if __name__ == "__main__":
    main()
