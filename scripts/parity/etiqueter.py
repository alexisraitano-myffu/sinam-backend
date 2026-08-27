"""Poser l'étiquette attendue sur des captures déjà écrites.

    python -m scripts.parity.generer R4b | python -m scripts.parity.etiqueter
    python -m scripts.parity.etiqueter brouillon.jsonl --modele anthropic:claude-opus-4-5

La seconde moitié d'un travail coupé en deux. `generer.py` écrit les captures
SANS voir les règles, pour ne pas se contenter d'illustrer ce que le moteur sait
déjà faire. Ce script fait l'inverse : il reçoit les deux prompts de production
en entier plus la carte des frontières, et n'a rien d'autre à faire que d'en
dériver la réponse attendue.

Ce qui était interdit à l'écriture est obligatoire ici, et c'est tout l'intérêt
de la coupure. Une étiquette écrite sans les règles est fausse une fois sur deux
— trois passes l'ont montré, chacune fausse d'une manière différente. Une
capture écrite avec les règles est inutile, et ça ne se voit jamais.

Un LOT est envoyé en un appel, pas une capture à la fois : les prompts pèsent
~15 000 tokens et sont identiques d'un cas à l'autre. Envoyés une fois, ils
franchissent le plancher du cache Haiku (~4 096 tokens) et sont relus au dixième
du prix ; envoyés par capture, ils se paient plein tarif à chaque fois.

La sortie va sur stdout et N'EST PAS écrite dans le corpus. Un cas entre par la
revue, à la main, jamais par un script.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import context, corpus, providers, score, split  # noqa: E402

_ICI = Path(__file__).resolve().parent


def savoir_complet() -> str:
    """Tout ce que l'étiqueteur a le droit de lire, en UN bloc.

    Un seul bloc, et pas quatre : `providers.call` ne pose le marqueur de cache
    que sur le premier. Quatre blocs ne feraient donc cacher que la consigne
    (~2 000 tokens), sous le plancher de Haiku, et les 15 000 tokens de prompts
    de production se paieraient plein tarif à chaque lot.
    """
    note = context.load_prompt(split._half_path("note.md"))
    graph = context.load_prompt(split._half_path("graph.md"))
    return "\n\n".join([
        (_ICI / "etiquetage.md").read_text(),
        "# Le prompt de production, moitié NOTE\n\n" + note,
        "# Le prompt de production, moitié GRAPHE\n\n" + graph,
        "# La carte des frontières\n\n" + (_ICI / "frontieres.md").read_text(),
    ])


_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_JOURS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
             "sunday")
# Le nom du jour → son index ISO, dans les deux langues du corpus.
_INDEX_JOUR = {nom: i for i, nom in enumerate(_JOURS)}
_INDEX_JOUR.update({nom: i for i, nom in enumerate(_JOURS_EN)})


def jour_nomme(texte: str) -> int | None:
    """L'index ISO du jour de semaine nommé dans une capture, s'il est unique.

    Un seul jour nommé, une seule lecture possible. Deux jours (« jeudi ou
    vendredi »), on ne vérifie rien : le contrôle doit se taire quand il ne
    sait pas, sinon il devient du bruit et on cesse de le lire.
    """
    trouves = {_INDEX_JOUR[m] for m in re.findall(
        r"[a-zéèêîôûàç]+", texte.lower()) if m in _INDEX_JOUR}
    return trouves.pop() if len(trouves) == 1 else None


def calendrier(avant: int = 9, apres: int = 16) -> str:
    """Les jours autour du temps de référence, nommés, un par ligne.

    Le modèle a résolu « avant jeudi » en 2026-07-17, qui est un vendredi. Une
    addition de jours faite de tête se trompe sans prévenir, et une étiquette
    datée à côté fait corriger un moteur qui avait raison. On ne demande donc
    plus l'arithmétique : on donne la table et on demande de la lire.

    La fenêtre couvre les deux sens, parce que le sens de résolution appartient
    au temps du verbe : « jeudi » regarde devant, « jeudi dernier » derrière.
    """
    zero = dt.date.fromisoformat(context.TODAY)
    lignes = []
    for delta in range(-avant, apres + 1):
        jour = zero + dt.timedelta(days=delta)
        repere = "  ← temps de référence" if delta == 0 else ""
        lignes.append(f"  {jour.isoformat()} {_JOURS[jour.weekday()]}{repere}")
    return "\n".join(lignes)


def lire_captures(source: Path | None) -> list[dict]:
    """Les captures à étiqueter, depuis un fichier ou stdin."""
    brut = source.read_text() if source else sys.stdin.read()
    captures = []
    for ligne in brut.splitlines():
        ligne = ligne.strip().strip("`")
        if not ligne.startswith("{"):
            continue
        try:
            captures.append(json.loads(ligne))
        except ValueError as e:
            print(f"⚠ ligne illisible ({e}) : {ligne[:80]}", file=sys.stderr)
    if not captures:
        raise SystemExit(
            "aucune capture reçue. Attendu : une ligne JSON par capture, sur "
            "stdin ou dans le fichier passé en argument.")
    return captures


def valider(cas: dict, capture: dict | None) -> int:
    """Les avertissements d'un cas étiqueté. 0 = rien à signaler."""
    alertes = 0
    ident = cas.get("id", "?")

    inconnus = set(cas) - corpus.CHAMPS
    if inconnus:
        print(f"⚠ {ident} : champs inconnus {sorted(inconnus)}", file=sys.stderr)
        alertes += 1

    # Les VALEURS, pas seulement les noms de champs. Une des passes a rendu six
    # fois kind="reflection", qui n'existe pas : la validation par nom de champ
    # l'avait laissé passer sans un mot.
    if cas.get("kind") and cas["kind"] not in score.VALID_NOTE_KINDS:
        print(f"⚠ {ident} : kind={cas['kind']!r} n'existe pas "
              f"(attendu : {', '.join(sorted(score.VALID_NOTE_KINDS))})",
              file=sys.stderr)
        alertes += 1
    if cas.get("kind") and not cas.get("note"):
        print(f"⚠ {ident} : un kind sans note ne veut rien dire", file=sys.stderr)
        alertes += 1
    if "valide" in cas:
        print(f"⚠ {ident} : `valide` est posé par un humain, jamais ici",
              file=sys.stderr)
        alertes += 1
    if not (set(cas) - corpus.META):
        print(f"⚠ {ident} : n'asserte rien, ne mesurerait rien", file=sys.stderr)
        alertes += 1

    # Le jour de la semaine se vérifie sans modèle, donc il se vérifie ici. Le
    # calendrier est fourni dans la demande et « avant jeudi » est quand même
    # sorti en 2026-07-17, un vendredi. Une consigne qui se contrôle pour rien
    # ne mérite pas de rester une consigne.
    jour = jour_nomme(capture["text"]) if capture else None
    date = cas.get("event_date")
    if jour is not None and isinstance(date, str):
        try:
            posee = dt.date.fromisoformat(date)
        except ValueError:
            print(f"⚠ {ident} : event_date={date!r} n'est pas une date",
                  file=sys.stderr)
            alertes += 1
        else:
            if posee.weekday() != jour:
                print(f"⚠ {ident} : la capture dit « {_JOURS[jour]} », "
                      f"l'étiquette pose {date}, un {_JOURS[posee.weekday()]}",
                      file=sys.stderr)
                alertes += 1

    # Le texte est le cas. Une faute d'orthographe « corrigée » en passant fait
    # mesurer autre chose que ce qui a été écrit, et rien ne le dirait.
    if capture is None:
        print(f"⚠ {ident} : n'était pas dans les captures envoyées", file=sys.stderr)
        alertes += 1
    elif cas.get("text") != capture.get("text"):
        print(f"⚠ {ident} : le texte a été modifié\n"
              f"    envoyé : {capture.get('text')!r}\n"
              f"    rendu  : {cas.get('text')!r}", file=sys.stderr)
        alertes += 1
    return alertes


def cout(spec: str, r: providers.Reply) -> str:
    """Ce que le lot a coûté. Une mesure dont on ignore le prix se relance sans
    qu'on sache ce qu'elle coûte, et c'est déjà arrivé 22 fois cet été."""
    tarif = split._TARIFS.get(providers.parse_spec(spec)[1])
    if not tarif or r.prompt_tokens is None:
        return ""
    entree, cache, sortie = tarif
    nc = r.extra.get("uncached_input_tokens", r.prompt_tokens)
    ecrit = r.extra.get("cache_creation_input_tokens", 0)
    lu = r.prompt_tokens - nc - ecrit
    # Écrire le cache coûte 1,25 fois l'entrée, le relire 0,1 fois. Les compter
    # ensemble au prix de la lecture ferait annoncer un dixième du vrai prix sur
    # le PREMIER lot, qui est justement celui qui écrit tout le préfixe.
    usd = (nc * entree + ecrit * entree * 1.25 + lu * cache
           + (r.output_tokens or 0) * sortie) / 1e6
    # Un lot sans une seule lecture de cache dit que le préfixe est passé sous
    # le plancher du modèle, ce qui ne se voit pas dans le seul total.
    alerte = "  ⚠ aucun cache n'a mordu" if lu == 0 and not ecrit else ""
    return (f"coût     : ~{usd:.3f} $  ({nc/1000:.1f}k entrée · "
            f"{ecrit/1000:.1f}k cache écrit · {lu/1000:.1f}k relus · "
            f"{(r.output_tokens or 0)/1000:.1f}k sortie){alerte}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", type=Path,
                    help="fichier de captures ; par défaut stdin")
    ap.add_argument("--modele", default="anthropic:claude-haiku-4-5-20251001")
    args = ap.parse_args()

    captures = lire_captures(args.source)
    par_id = {c.get("id"): c for c in captures}

    demande = "\n".join([
        f"Le temps de référence est {context.TODAY}. L'auteur des captures est "
        f"{context.OWNER}.",
        "",
        "Le calendrier autour de lui. Toute date de ton étiquette se LIT ici, "
        "elle ne se calcule pas :",
        calendrier(),
        "",
        f"Étiquette les {len(captures)} captures ci-dessous. Rends chacune "
        f"complétée, une ligne JSON par cas, rien autour.",
        "",
        *[json.dumps(c, ensure_ascii=False) for c in captures],
    ])

    # Température 0 : l'étiquette dérive de règles écrites, donc deux passes sur
    # la même capture doivent rendre la même chose. C'est l'inverse du
    # générateur, où la variance EST ce qu'on cherche.
    r = providers.call(args.modele, [savoir_complet()], demande,
                       max_tokens=8000, temperature=0.0)
    if not r.ok:
        raise SystemExit(f"appel échoué : {r}")

    bons = mauvais = 0
    rendus = set()
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
        mauvais += valider(cas, par_id.get(cas.get("id")))
        rendus.add(cas.get("id"))
        bons += 1
        print(json.dumps(cas, ensure_ascii=False))

    # Une capture avalée sans être rendue est le pire cas : elle ne lève rien et
    # elle disparaît du lot sans que personne ne la cherche.
    for perdue in [i for i in par_id if i not in rendus]:
        print(f"⚠ {perdue} : envoyée, jamais rendue", file=sys.stderr)
        mauvais += 1

    print(f"\n{bons}/{len(captures)} cas étiquetés, {mauvais} avertissement(s). "
          f"Rien n'a été écrit dans le corpus : la revue est humaine.",
          file=sys.stderr)
    print(cout(args.modele, r), file=sys.stderr)


if __name__ == "__main__":
    main()
