"""Écrire des cas de corpus pour UNE frontière, dans un contexte propre.

    python -m scripts.parity.generer R4b --combien 6
    python -m scripts.parity.generer R4b --modele anthropic:claude-opus-4-5

Ce que ce script garantit, et qui est toute sa raison d'être : le générateur ne
voit NI `classifier-note.md` NI `classifier-graph.md`. Il reçoit le prompt de
génération, la ligne de la carte des frontières, et les textes déjà présents.
Rien d'autre.

Sans ça, écrire les cas depuis les règles produirait des cas que ces règles
gèrent déjà : un corpus dérivé du règlement ne peut pas trouver un trou que le
règlement n'a pas. Passer par un appel séparé est le seul moyen de le garantir
plutôt que de l'espérer.

La sortie va sur stdout et N'EST PAS écrite dans le corpus. Un cas entre par la
revue, à la main, jamais par un script.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import corpus, providers, score  # noqa: E402
from scripts.parity.context import TODAY  # noqa: E402

_ICI = Path(__file__).resolve().parent


def ligne_de_frontiere(code: str) -> tuple[str, str]:
    """La ligne de `frontieres.md` pour cette frontière, et son titre de section.

    Le titre compte autant que la ligne. « Ligne 4, note » dit vers QUOI la
    frontière résout ; sans lui le générateur doit le deviner, et la première
    passe a montré qu'il devine à l'envers — six captures justes, six étiquettes
    fausses toutes dans le même sens.

    Un titre de section n'est pas une règle de routage : il nomme la
    destination, pas les conditions ni les exceptions. La garde qui interdit au
    générateur de lire les prompts de production tient toujours.
    """
    titre = ""
    for ligne in (_ICI / "frontieres.md").read_text().splitlines():
        if ligne.startswith("#"):
            titre = ligne.lstrip("# ").strip()
        if ligne.startswith(f"| {code} |"):
            return ligne, titre
    raise SystemExit(
        f"frontière « {code} » introuvable dans frontieres.md. "
        f"Elle s'écrit exactement comme la première colonne du tableau.")


def textes_existants(code: str) -> list[str]:
    """Les captures déjà écrites pour cette frontière, pour ne pas les refaire."""
    vus = []
    for jeu in corpus.SETS.values():
        for cas in jeu:
            if (cas.get("frontiere") or "").strip() == code:
                vus.append(cas["text"])
    return vus


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frontiere", help="le code exact, ex. R4b, G-SVO, P-TYPE")
    ap.add_argument("--combien", type=int, default=6)
    ap.add_argument("--modele", default="anthropic:claude-haiku-4-5-20251001")
    args = ap.parse_args()

    _ligne, _titre = ligne_de_frontiere(args.frontiere)
    systeme = (_ICI / "generation.md").read_text()
    deja = textes_existants(args.frontiere)

    demande = "\n".join([
        f"Frontière à couvrir : {args.frontiere}",
        "",
        f"Elle appartient à : {_titre}. C'est la DESTINATION vers laquelle elle "
        f"résout, et elle décide de tes étiquettes.",
        "",
        "Sa ligne dans la carte des frontières, telle quelle :",
        _ligne,
        "",
        f"Le temps de référence est {TODAY}, un lundi. Toute date relative se "
        f"résout par rapport à lui, et tes étiquettes portent la date absolue.",
        "",
        ("Captures déjà écrites pour cette frontière, à ne pas refaire :\n"
         + "\n".join(f"  - {t}" for t in deja)) if deja
        else "Aucune capture n'existe encore pour cette frontière.",
        "",
        f"Écris {args.combien} cas. Une ligne JSON par cas, rien autour.",
    ])

    r = providers.call(args.modele, [systeme], demande, max_tokens=4000,
                       temperature=1.0)
    if not r.ok:
        raise SystemExit(f"appel échoué : {r}")

    # On valide la forme ici plutôt que de laisser un JSON cassé arriver au
    # corpus : une ligne mal formée coûte plus cher à trouver plus tard.
    bons = mauvais = 0
    for ligne in r.text.splitlines():
        ligne = ligne.strip().strip("`")
        if not ligne.startswith("{"):
            continue
        try:
            cas = json.loads(ligne)
        except ValueError as e:
            print(f"⚠ ligne illisible ({e}) : {ligne[:80]}", file=sys.stderr)
            mauvais += 1
            continue
        inconnus = set(cas) - corpus.CHAMPS
        if inconnus:
            print(f"⚠ {cas.get('id')} : champs inconnus {sorted(inconnus)}",
                  file=sys.stderr)
            mauvais += 1
        # Les valeurs, pas seulement les noms de champs. La deuxième passe a
        # rendu six fois kind="reflection", qui n'existe pas : la validation
        # par nom de champ l'avait laissé passer sans un mot.
        if cas.get("kind") and cas["kind"] not in score.VALID_NOTE_KINDS:
            print(f"⚠ {cas.get('id')} : kind={cas['kind']!r} n'existe pas "
                  f"(attendu : {', '.join(sorted(score.VALID_NOTE_KINDS))})",
                  file=sys.stderr)
            mauvais += 1
        if cas.get("kind") and not cas.get("note"):
            print(f"⚠ {cas.get('id')} : un kind sans note ne veut rien dire",
                  file=sys.stderr)
            mauvais += 1
        if "valide" in cas:
            print(f"⚠ {cas.get('id')} : `valide` est posé par un humain, jamais ici",
                  file=sys.stderr)
            mauvais += 1
        if not (set(cas) - corpus.META):
            print(f"⚠ {cas.get('id')} : n'asserte rien, ne mesurerait rien",
                  file=sys.stderr)
            mauvais += 1
        bons += 1
        print(json.dumps(cas, ensure_ascii=False))

    print(f"\n{bons} cas, {mauvais} avertissement(s). "
          f"Rien n'a été écrit dans le corpus : la revue est humaine.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
