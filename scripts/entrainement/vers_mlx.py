"""Convertir le jeu en ce que `mlx_lm lora` sait lire, sur le Mac.

`construire.py` produit quatre fichiers organisés par MOITIÉ (note / graphe),
parce que c'est comme ça qu'on les relit. mlx-lm, lui, veut un dossier avec
`train.jsonl`, `valid.jsonl` et `test.jsonl`, une conversation par ligne et
rien d'autre que `messages`.

Les deux moitiés sont MÉLANGÉES dans le même jeu, et c'est voulu : la
production les fait tourner sur le même modèle, avec deux appels que seul le
prompt système distingue. Entraîner deux adaptateurs séparés apprendrait à deux
modèles ce qu'un seul doit savoir, et doublerait ce qu'il faut charger sur
l'appareil.

Le `valid` est prélevé sur le TRAIN, jamais sur le test : le test ne se regarde
qu'une fois, à la fin. Le prélèvement respecte la même contrainte que la découpe
d'origine, puisqu'il ne touche qu'à des cas déjà retenus pour l'entraînement.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
JEU = _REPO / "scripts" / "entrainement" / "jeu"
SORTIE = JEU / "mlx"


def lire(nom: str) -> list[dict]:
    f = JEU / nom
    if not f.exists():
        raise SystemExit(f"{f} absent — lancer d'abord "
                         "`python -m scripts.entrainement.construire --ecrire`")
    # mlx-lm refuse les clés qu'il ne connaît pas : `id` reste dans
    # `provenance.json`, qui sert justement à retrouver un cas après coup.
    return [{"messages": json.loads(l)["messages"]} for l in f.read_text().splitlines() if l]


def ecrire(nom: str, lignes: list[dict]) -> None:
    (SORTIE / nom).write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes))
    print(f"écrit : {(SORTIE / nom).relative_to(_REPO)}  ({len(lignes)} lignes)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--part-valid", type=float, default=0.10)
    ap.add_argument("--graine", type=int, default=13)
    args = ap.parse_args()

    SORTIE.mkdir(parents=True, exist_ok=True)
    train = lire("note-train.jsonl") + lire("graphe-train.jsonl")
    test = lire("note-test.jsonl") + lire("graphe-test.jsonl")

    rng = random.Random(args.graine)
    rng.shuffle(train)
    n = max(1, round(len(train) * args.part_valid))
    ecrire("valid.jsonl", train[:n])
    ecrire("train.jsonl", train[n:])
    ecrire("test.jsonl", test)

    long_max = max(sum(len(m["content"]) for m in x["messages"])
                   for x in train + test)
    print(f"\nconversation la plus longue : {long_max} caractères "
          f"(~{long_max // 4} tokens) — dimensionner --max-seq-length dessus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
