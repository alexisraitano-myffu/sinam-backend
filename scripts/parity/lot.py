"""Un PAQUET de captures ordinaires : générer, dédupliquer, étiqueter, s'arrêter.

Pourquoi ce module et pas une boucle shell. Trois choses doivent tenir ensemble
et se perdent dès qu'on les sépare :

1. **Les appels d'un même paquet doivent se voir.** La garde anti-doublon de
   `generer.py` ne lit que le corpus SUR DISQUE, et rien n'y est écrit avant la
   revue humaine. Deux appels consécutifs réécriraient donc les mêmes captures.
   D'où `--deja`, alimenté ici au fil de l'eau.

2. **La proportion de langues est un paramètre du corpus, pas un hasard.** Elle
   devient l'a priori du modèle si on entraîne dessus : 11 % d'anglais
   enseignerait « le français est le défaut ». On vise donc une cible et on la
   calcule à partir de ce que le corpus porte DÉJÀ, au lieu de la deviner.

3. **Rien n'est versé au corpus.** Ce module écrit deux fichiers à côté et
   s'arrête. La revue est humaine, et un paquet de 70 captures étiquetées par
   un modèle est exactement le genre de chose qui se verse toute seule si on
   lui en laisse l'occasion.

    python -m scripts.parity.lot --combien 70 --sortie /tmp/lot1
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_ICI = Path(__file__).resolve().parent
_REPO = _ICI.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import corpus  # noqa: E402

# La cible du corpus fini. 500 captures dont 30 % d'anglais : ce sont les
# chiffres de l'étape 2, pas une préférence.
CIBLE_TOTALE = 500
CIBLE_ANGLAIS = 0.30
# Par appel. Au-delà, la sortie se fait tronquer : le budget couvre la
# réflexion du modèle en plus du texte, et ça ne lève aucune erreur.
PAR_APPEL = 10


def _langue(texte: str) -> str:
    """Français ou anglais, à la louche. Sert à COMPTER, jamais à étiqueter :
    le champ `language` d'une étiquette est posé par le modèle qui a lu la
    phrase, pas par cette heuristique."""
    t = f" {texte.lower()} "
    fr = sum(m in t for m in (" le ", " la ", " les ", " je ", " j'", " et ",
                              " de ", " du ", " un ", " une ", " que ", " pour ",
                              " chez ", " au ", " ce ", " il ", " elle ", " à "))
    en = sum(m in t for m in (" the ", " i ", " and ", " to ", " at ", " with ",
                              " on ", " my ", " of ", " is ", " for ", " a "))
    return "en" if en > fr else "fr"


def _etat_du_corpus() -> tuple[int, int]:
    """(captures, dont anglaises) dans le corpus versé."""
    total = anglais = 0
    for jeu in corpus.SETS.values():
        for cas in jeu:
            total += 1
            anglais += _langue(cas["text"]) == "en"
    return total, anglais


def _melange(combien: int) -> list[str]:
    """La langue de chaque appel, pour que le corpus FINI atteigne la cible.

    Le calcul part du manque, pas de la cible : si le corpus porte 11 %
    d'anglais et qu'on en veut 30 % sur 500, il faut bien plus de 30 %
    d'anglais dans ce qui reste à écrire. Viser 30 % ici raterait la cible de
    loin, et personne ne s'en apercevrait avant la fin.
    """
    total, anglais = _etat_du_corpus()
    manque_en = max(0, round(CIBLE_ANGLAIS * CIBLE_TOTALE) - anglais)
    reste = max(1, CIBLE_TOTALE - total)
    part_en = min(1.0, manque_en / reste)
    n_en = round(combien * part_en)
    print(f"corpus   : {total} captures, {anglais} anglaises ({anglais*100//max(total,1)} %)",
          file=sys.stderr)
    print(f"ce paquet: {n_en} anglaises sur {combien}, pour viser "
          f"{round(CIBLE_ANGLAIS*100)} % sur {CIBLE_TOTALE}", file=sys.stderr)
    return ["en"] * n_en + ["fr"] * (combien - n_en)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--combien", type=int, default=70)
    ap.add_argument("--sortie", type=Path, required=True,
                    help="préfixe : écrit <sortie>-captures.jsonl et "
                         "<sortie>-etiquete.jsonl")
    ap.add_argument("--modele", default="gemini:gemini-3.6-flash")
    args = ap.parse_args()

    langues = _melange(args.combien)
    brut = args.sortie.with_name(args.sortie.name + "-captures.jsonl")
    brut.write_text("")
    vus_ids: set[str] = set()

    # Un appel par langue et par tranche, pour que chacun reste sous le budget
    # et pour que `--deja` ait le temps de croître entre deux.
    tranches: list[tuple[str, int]] = []
    for lg in ("en", "fr"):
        n = langues.count(lg)
        while n > 0:
            tranches.append((lg, min(PAR_APPEL, n)))
            n -= PAR_APPEL

    for i, (lg, n) in enumerate(tranches, 1):
        print(f"\n[{i}/{len(tranches)}] {n} captures en {lg}", file=sys.stderr)
        r = subprocess.run(
            [sys.executable, "-m", "scripts.parity.generer", "--ordinaire",
             "--langue", lg, "--combien", str(n), "--modele", args.modele,
             "--deja", str(brut)],
            cwd=_REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-600:], file=sys.stderr)
            raise SystemExit(f"génération échouée à la tranche {i}")
        sys.stderr.write(r.stderr)
        # ⚠ Le générateur numérote ses cas à partir de 1 À CHAQUE APPEL
        # (`ord-en-001`…), donc deux tranches de la même langue se marchent
        # dessus. `corpus.py` refuse un id en double — les baselines sont
        # indexées dessus — et le versement a silencieusement perdu 15 captures
        # au paquet 1, dont les TEXTES étaient pourtant uniques. On désambiguïse
        # ici, où l'on sait de quelle tranche on parle.
        with brut.open("a") as f:
            for ligne in r.stdout.splitlines():
                if not ligne.strip():
                    continue
                cas = json.loads(ligne)
                if cas.get("id") in vus_ids:
                    cas["id"] = f"{cas['id']}-{i}"
                vus_ids.add(cas.get("id"))
                f.write(json.dumps(cas, ensure_ascii=False) + "\n")

    n_brut = sum(1 for l in brut.read_text().splitlines() if l.strip())
    print(f"\n{n_brut} captures écrites dans {brut.name}", file=sys.stderr)

    # L'étiquetage se fait aussi par tranches : un lot entier dans un appel se
    # fait tronquer, et une troncature ici rend un JSON valide mais amputé.
    etiq = args.sortie.with_name(args.sortie.name + "-etiquete.jsonl")
    etiq.write_text("")
    lignes = [l for l in brut.read_text().splitlines() if l.strip()]
    for i in range(0, len(lignes), PAR_APPEL):
        bout = lignes[i:i + PAR_APPEL]
        tmp = args.sortie.with_name(args.sortie.name + "-tranche.jsonl")
        tmp.write_text("\n".join(bout))
        print(f"\nétiquetage {i+1}-{i+len(bout)} sur {len(lignes)}", file=sys.stderr)
        r = subprocess.run(
            [sys.executable, "-m", "scripts.parity.etiqueter", str(tmp),
             "--modele", args.modele],
            cwd=_REPO, capture_output=True, text=True)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            raise SystemExit(f"étiquetage échoué sur la tranche {i}")
        with etiq.open("a") as f:
            for ligne in r.stdout.splitlines():
                if not ligne.strip():
                    continue
                cas = json.loads(ligne)
                # L'étiqueteur ignore le mode et colle un code de frontière à
                # presque tout : 49 captures sur 69 au premier paquet. Une
                # capture ordinaire n'en vise AUCUNE, et lui en prêter une
                # gonfle le compte de couverture avec des cas écrits pour autre
                # chose — plus le contrôle « tous du même côté » se met à crier
                # sur des familles qui n'existent pas. On le retire ici parce
                # que c'est ici qu'on sait dans quel mode on est.
                cas.pop("frontiere", None)
                f.write(json.dumps(cas, ensure_ascii=False) + "\n")
        tmp.unlink(missing_ok=True)

    n_etiq = sum(1 for l in etiq.read_text().splitlines() if l.strip())
    print(f"\n{n_etiq}/{n_brut} étiquetées → {etiq}", file=sys.stderr)
    print("RIEN n'a été versé au corpus : la revue est humaine.", file=sys.stderr)


if __name__ == "__main__":
    main()
