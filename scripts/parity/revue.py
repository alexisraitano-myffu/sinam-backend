"""SYN-184 — l'outil de revue : valider les étiquettes du corpus, une par une.

Il ne mesure aucun modèle. Il sert à trancher ce que la BONNE réponse aurait dû
être, ce qui est la seule chose qu'une machine ne peut pas produire à notre
place. Le reste du harnais suppose ces étiquettes justes ; si elles ne le sont
pas, tout ce qu'il mesure est faux avec assurance.

    python -m scripts.parity.revue --rapport
    python -m scripts.parity.revue --jeu adversarial
    python -m scripts.parity.revue --frontiere NEG-b --baseline haiku-v28-final
    python -m scripts.parity.revue --cas x-attend-noun,x-no-invention

`--baseline` affiche, à côté de l'étiquette, ce que ce modèle a RÉELLEMENT
produit sur le cas. Arbitrer contre une trace vaut mieux qu'arbitrer dans
l'abstrait : c'est comme ça qu'on a découvert que trois assertions étaient plus
larges que leur propre justification.

Chaque action écrit tout de suite, et ne réécrit QUE la ligne du cas : le diff
git d'une session de revue se lit cas par cas.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import corpus as C  # noqa: E402
from scripts.parity import lexique as L  # noqa: E402
from scripts.parity import score  # noqa: E402

SNAP_DIR = _REPO / "scripts" / "parity" / "baselines"

# L'ordre canonique d'une ligne. Il n'a aucune importance pour le chargeur et
# toute son importance pour le diff : deux cas voisins doivent se comparer à
# l'œil, et une réécriture ne doit jamais permuter des clés au passage.
ORDRE = ["id", "text", "wm", "repeat", "expect", "note", "kind", "ephemeral",
         "owner", "recurring", "event_date", "language", "needs_review",
         "drop_guard", "rel", "proj", "facts_min", "entity_expected", "no_entity",
         "forbidden_value", "forbidden_predicate", "obsoletes", "no_obsolete",
         "renamed_to", "no_rename",
         "frontiere", "why", "ambigu", "arbitrage", "valide"]

G, J, R, B, N = "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"
D = "\033[2m"

# Un cas dont le `why` porte l'une de ces marques a demandé une DÉCISION : le
# prompt ne le tranchait pas seul, ou l'axe ne mesure qu'une partie de la règle.
# C'est là que se cachent les erreurs qui contaminent une famille entière, et
# c'est donc là que la relecture humaine rapporte le plus.
MARQUES = ("n'est PAS asserté", "pas asserté", "⚠", "ne tranche pas", "ne dit pas",
           "question ouverte", "limite connue", "à ouvrir", "ne définit", "ne mesure",
           "assumée", "Conséquence assumée")


def porte_une_decision(cas: dict) -> bool:
    return any(m in (cas.get("why") or "") for m in MARQUES)


def echantillon(par_famille: int = 2) -> list[tuple[str, dict]]:
    """Les cas à relire en priorité : toutes les décisions, plus un sondage.

    Relire 150 cas coûte des heures et confirme surtout du mécanique. Ce qui se
    cherche ici n'est pas l'erreur isolée, c'est l'erreur SYSTÉMATIQUE — une
    règle du prompt mal lue, qui se retrouve alors dans toute une famille. Le
    sondage par famille existe pour ça : deux cas ordinaires suffisent à la
    révéler, là où le trentième cas d'une même règle n'apprend plus rien.

    Le tirage est déterministe (indices régulièrement espacés sur les
    identifiants triés) : deux personnes qui lancent la commande relisent le
    même échantillon, et une session interrompue reprend le même.
    """
    lot: list[tuple[str, dict]] = []
    for famille, cas in sorted(C.JEUX.items()):
        decisions = [k for k in cas if porte_une_decision(k)]
        lot += [(famille, k) for k in decisions]
        reste = sorted((k for k in cas if k not in decisions), key=lambda k: k["id"])
        if not reste:
            continue
        pas = max(1, len(reste) // par_famille)
        lot += [(famille, k) for k in reste[::pas][:par_famille]]
    return lot


def _serialiser(cas: dict) -> str:
    inconnus = set(cas) - C.CHAMPS
    if inconnus:
        raise SystemExit(f"champs inconnus : {sorted(inconnus)}")
    return json.dumps({k: cas[k] for k in ORDRE if k in cas}, ensure_ascii=False)


def ecrire(jeu: str, cas: dict) -> None:
    """Remplacer la ligne de ce cas, et elle seule."""
    chemin = C.CORPUS_DIR / f"{jeu}.jsonl"
    lignes = chemin.read_text().splitlines()
    for i, ligne in enumerate(lignes):
        if ligne.strip() and json.loads(ligne)["id"] == cas["id"]:
            lignes[i] = _serialiser(cas)
            chemin.write_text("\n".join(lignes) + "\n")
            return
    raise SystemExit(f"{cas['id']} introuvable dans {chemin.name}")


def _valeur(brut: str):
    """« true », « 3 », « null », « Marie » — au plus proche de ce qui est tapé."""
    brut = brut.strip()
    if brut == "":
        return None
    try:
        return json.loads(brut)
    except ValueError:
        return brut


def _bloc(titre: str, lignes, indent: str = "  ") -> None:
    print(f"\n{B}{titre}{N}")
    for ligne in lignes:
        print(f"{indent}{ligne}")


def _branche(cas: dict, jeu: str) -> list[str]:
    """Ce qu'un cas scénario prouve, en français, et contre quel témoin.

    Un cas scénario ne se juge pas sur une sortie mais sur une BRANCHE, tenue
    sur N passes. Et il ne prouve rien tout seul : sa valeur est l'écart, ou
    l'absence d'écart, avec le même texte dans un autre fil. Sans le témoin
    affiché, la revue porte sur une phrase isolée, ce qui n'est pas la question
    posée.
    """
    e = cas["expect"]
    dits = []
    if "note" in e:
        dits.append("une note" if e["note"] else "aucune note")
    if e.get("kind"):
        dits.append(f"de genre {e['kind']}")
    if "confidence_below" in e:
        dits.append(f"sous {e['confidence_below']} de confiance")
    if "ephemeral" in e:
        dits.append("éphémère" if e["ephemeral"] else "non éphémère")
    lignes = [f"{', '.join(dits) or e}, sur "
              f"{cas.get('repeat', 1)} passes identiques"]

    temoins = [k["id"] for k in C.charger(jeu)
               if k["id"] != cas["id"] and k.get("text") == cas.get("text")]
    if temoins:
        lignes += ["", "Le même texte est mesuré ailleurs dans ce jeu, et c'est "
                       "LÀ qu'est la question :",
                   "  " + ", ".join(temoins),
                   "La bonne réponse n'est pas « que vaut cette phrase » mais "
                   "« la réponse doit-elle bouger d'un fil à l'autre »."]
    return lignes


def _afficher(cas: dict, jeu: str, i: int, total: int, trace: dict | None,
              technique: bool = False) -> None:
    marque = f"{G}validé {cas['valide']}{N}" if cas.get("valide") else f"{J}non validé{N}"
    if cas.get("arbitrage"):
        marque = f"{J}ta décision est écrite, en attente de traduction{N}"
    if cas.get("ambigu"):
        marque += f" · {J}le prompt ne tranche pas (hors décompte){N}"
    print(f"\n{'─' * 78}\n{B}[{i}/{total}] {cas['id']}{N}  ·  {jeu}  ·  {marque}")
    print(f"\n  « {cas['text']} »")
    if cas.get("wm"):
        # Le fil se LIT et ne s'écrit pas. `_build_day_context` le passe au
        # classifieur en contexte seule-lecture pour que « elle », « ce
        # projet », « hier » se résolvent ; seule la capture ci-dessus produit
        # une sortie. L'ancienne formule, « dit juste avant », laissait croire
        # le contraire, et une revue a été rendue sur cette lecture-là.
        print(f"    {D}↑ la seule capture notée. Ce qui suit est du contexte "
              f"lu, qui ne produit RIEN :{N}")
        for w in cas.get("wm") or []:
            print(f"      {D}·{N} « {w} »")

    if technique:
        return _technique(cas, trace)

    # Ce que le cas tranche. Le code de frontière est un index, pas une
    # explication : on affiche la phrase, et le code seulement en petit.
    lignes = []
    for code, phrase in L.tranche(cas):
        bouts = textwrap.wrap(phrase, 68)
        lignes.append(f"{bouts[0]}  {D}[{code}]{N}")
        lignes += [f"  {b}" for b in bouts[1:]]
    if lignes:
        _bloc("CE QUE CE CAS TRANCHE", lignes)

    dit = L.dit(cas)
    if dit:
        print(f"\n{B}LA RÉPONSE ACTUELLE{N}")
        for question, phrases in dit:
            print(f"  {J}{question}{N}")
            for ph in phrases:
                for k, bout in enumerate(textwrap.wrap(ph, 70)):
                    print(f"    {'·' if k == 0 else ' '} {bout}")
    elif "expect" in cas:
        _bloc("LA RÉPONSE ACTUELLE",
              _branche(cas, jeu))
    else:
        print(f"\n  {R}Ce cas n'asserte rien : il ne vérifie rien.{N}")

    muets = L.muet(cas)
    if muets:
        _bloc("CE CAS NE DIT RIEN SUR",
              textwrap.wrap(" · ".join(muets), 74)
              + [f"{D}donc rien ne sera jugé là-dessus, et tu n'as pas à "
                 f"l'arbitrer ici{N}"])

    if cas.get("why"):
        _bloc("POURQUOI CETTE RÉPONSE",
              [l for w in cas["why"].split("\n") for l in textwrap.wrap(w, 74)])

    if cas.get("arbitrage"):
        _bloc(f"{J}CE QUE TU AS DIT{N}",
              [l for w in cas["arbitrage"].split("\n") for l in textwrap.wrap(w, 74)])

    if trace is not None:
        _trace(cas, trace)


def _technique(cas: dict, trace: dict | None) -> None:
    """La vue d'origine : les axes bruts, pour quand on veut la mécanique."""
    if cas.get("frontiere"):
        print(f"frontière : {cas['frontiere']}")
    axes = [k for k in score.AXES if k in cas]
    print(f"\n{B}étiquette{N}")
    if not axes and "expect" not in cas:
        print(f"  {R}aucune assertion : ce cas ne vérifie rien{N}")
    for k in axes:
        print(f"  {k:20} = {json.dumps(cas[k], ensure_ascii=False):<24} → {score.AXES[k]}")
    if "expect" in cas:
        print(f"  {'expect':20} = {json.dumps(cas['expect'], ensure_ascii=False)}"
              f"   ({cas.get('repeat', 1)} passes)")
    if cas.get("why"):
        print(f"\n{B}pourquoi{N}\n  " + cas["why"].replace("\n", "\n  "))
    if trace is not None:
        _trace(cas, trace)


def _trace(cas: dict, trace: dict) -> None:
    parsed = trace.get("parsed") or {}
    ecarts = score.gaps(cas, parsed) if parsed else ["réponse inexploitable"]
    etat = f"{G}conforme{N}" if not ecarts else f"{R}{len(ecarts)} écart(s){N}"
    print(f"\n{B}CE QUE LE MODÈLE A PRODUIT{N} — {etat}")
    print(f"  note={trace.get('has_note')} kind={trace.get('kind')} "
          f"ephemeral={trace.get('ephemeral')} faits={trace.get('facts')} "
          f"relations={trace.get('relations')} projets={trace.get('projects')}")
    for e in ecarts:
        print(f"  {R}·{N} {e}")


def _saisir_libre(invite: str) -> str:
    """Un paragraphe, terminé par une ligne vide.

    Une seule ligne ne suffisait pas : ce qu'on demande ici est un RAISONNEMENT,
    et un raisonnement qu'il faut tasser sur une ligne se raccourcit jusqu'à ne
    plus rien dire.
    """
    print(f"\n{J}{invite}{N}")
    print(f"{D}(plusieurs lignes possibles · ligne vide pour terminer · "
          f"rien du tout pour annuler){N}")
    lignes = []
    while True:
        try:
            ligne = input("  ")
        except (EOFError, KeyboardInterrupt):
            break
        if not ligne.strip():
            break
        lignes.append(ligne.rstrip())
    return "\n".join(lignes).strip()


MENU = ("[o] d'accord  [d] je dis autre chose  [t] vue technique  "
        "[a] le prompt ne tranche pas  [s] passer  [q] quitter")
MENU_TECH = ("[m] modifier un axe  [p] pourquoi  [f] frontière  "
             "[a] le prompt ne tranche pas  [h] revenir au français  "
             "[s] passer  [q] quitter")


def reviser(cas_par_jeu: list[tuple[str, dict]], traces: dict) -> None:
    aujourdhui = date.today().isoformat()
    total = len(cas_par_jeu)
    i = 0
    technique = False
    while i < total:
        jeu, cas = cas_par_jeu[i]
        _afficher(cas, jeu, i + 1, total, traces.get(cas["id"]), technique)
        menu = MENU_TECH if technique else MENU
        try:
            choix = input(f"\n{menu}\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\ninterrompu — tout ce qui était écrit l'est déjà.")
            return
        if choix == "q":
            return
        if choix in ("", "s"):
            i += 1
            continue
        if choix == "t":
            technique = True
            continue
        if choix == "h":
            technique = False
            continue
        if choix == "o":
            cas["valide"] = aujourdhui
            ecrire(jeu, cas)
            print(f"{G}validé{N}")
            i += 1
        elif choix == "d":
            texte = _saisir_libre(
                "Dis ce qui devrait se passer avec cette capture, et pourquoi. "
                "Avec tes mots.")
            if not texte:
                print("annulé")
                continue
            cas["arbitrage"] = texte
            # Sa décision remplace l'étiquette actuelle : la garder validée
            # ferait passer pour arbitré ce qu'il vient justement de contester.
            cas.pop("valide", None)
            ecrire(jeu, cas)
            print(f"{G}écrit.{N} Je le traduirai en axes, et tu reverras la "
                  f"traduction avant qu'elle compte.")
            i += 1
        elif choix == "m":
            champ = input("axe (vide = annuler) : ").strip()
            if not champ:
                continue
            if champ not in C.CHAMPS:
                print(f"{R}axe inconnu.{N} Connus : {', '.join(sorted(score.AXES))}")
                continue
            v = _valeur(input(f"{champ} = (vide = retirer l'axe) : "))
            if v is None:
                cas.pop(champ, None)
            else:
                cas[champ] = v
            # Modifier une étiquette PÉRIME sa validation : elle portait sur
            # l'ancienne. La revalider est un geste, pas un effet de bord.
            cas.pop("valide", None)
            ecrire(jeu, cas)
            print(f"{J}écrit, et la validation est retirée : l'étiquette a changé.{N}")
        elif choix == "p":
            cas["why"] = input("pourquoi : ").strip() or cas.get("why", "")
            ecrire(jeu, cas)
        elif choix == "f":
            cas["frontiere"] = input("frontière : ").strip()
            ecrire(jeu, cas)
        elif choix == "a":
            cas["ambigu"] = not cas.get("ambigu")
            ecrire(jeu, cas)
            print("le prompt ne tranche pas : hors décompte"
                  if cas["ambigu"] else "revenu dans le décompte")
        else:
            print("?")


def rapport() -> None:
    tous = [(j, k) for j, cas in C.JEUX.items() for k in cas]
    valides = [k for _, k in tous if k.get("valide")]
    print(f"{B}corpus{N} : {len(tous)} cas, "
          f"{len({k['text'] for _, k in tous})} textes distincts")
    print(f"validés : {len(valides)}/{len(tous)}")
    print("\npar jeu")
    for jeu, cas in sorted(C.JEUX.items()):
        v = sum(1 for k in cas if k.get("valide"))
        print(f"  {jeu:14} {len(cas):4} cas   {v:4} validés")

    par_frontiere: dict[str, int] = {}
    for _, k in tous:
        par_frontiere[k.get("frontiere") or "—"] = \
            par_frontiere.get(k.get("frontiere") or "—", 0) + 1
    print("\npar frontière")
    for f, n in sorted(par_frontiere.items()):
        print(f"  {f:14} {n:4}")

    couverture: dict[str, int] = {}
    for _, k in tous:
        for axe in score.axes_of(k):
            couverture[score.AXES[axe]] = couverture.get(score.AXES[axe], 0) + 1
    print("\naxes exercés (frontière ← nombre de cas qui l'assertent)")
    for f, n in sorted(couverture.items(), key=lambda x: -x[1]):
        print(f"  {f:14} {n:4}")

    en_attente = [k["id"] for _, k in tous if k.get("arbitrage")]
    if en_attente:
        print(f"\n{J}décisions écrites, en attente de traduction{N} : "
              f"{', '.join(en_attente)}")

    inertes = C.inertes()
    if inertes:
        print(f"\n{J}cas qui n'assertent rien{N} : {', '.join(inertes)}")
    if C.AMBIGUOUS:
        print(f"{J}cas ambigus (hors décompte){N} : {', '.join(sorted(C.AMBIGUOUS))}")


def arbitrages() -> None:
    """Ce qu'Alexis a dit, et que personne n'a encore traduit en axes.

    Le point de rendez-vous entre les deux moitiés du travail : il décide, la
    machine traduit, et la traduction lui revient avant de compter.
    """
    en_attente = [(j, k) for j, cas in sorted(C.JEUX.items()) for k in cas
                  if k.get("arbitrage")]
    if not en_attente:
        print("aucune décision en attente de traduction.")
        return
    print(f"{B}{len(en_attente)} décision(s) à traduire en axes{N}")
    for jeu, k in en_attente:
        print(f"\n{'─' * 78}\n{B}{k['id']}{N}  ·  {jeu}")
        print(f"  « {k['text']} »")
        axes = [a for a in score.AXES if a in k]
        print(f"  {D}étiquette actuelle : "
              f"{', '.join(f'{a}={json.dumps(k[a], ensure_ascii=False)}' for a in axes) or 'aucune'}{N}")
        for w in k["arbitrage"].split("\n"):
            for ligne in textwrap.wrap(w, 74):
                print(f"  {J}│{N} {ligne}")


def main() -> int:
    ap = argparse.ArgumentParser(description="SYN-184 — revue des étiquettes du corpus")
    ap.add_argument("--rapport", action="store_true", help="état des lieux, sans rien écrire")
    ap.add_argument("--jeu", help="ne revoir qu'un fichier corpus/<jeu>.jsonl")
    ap.add_argument("--frontiere", help="ne revoir que les cas d'une frontière")
    ap.add_argument("--cas", help="ne revoir que ces cas, par identifiant, séparés par "
                                  "des virgules. Implique --tous : on rouvre un cas "
                                  "nommément parce qu'on le sait mal étiqueté.")
    ap.add_argument("--tous", action="store_true",
                    help="y compris les cas déjà validés (défaut : seulement les autres)")
    ap.add_argument("--echantillon", nargs="?", type=int, const=2, metavar="N",
                    help="ne relire que les cas qui portent une décision, plus N cas "
                         "ordinaires par famille (défaut 2). Cherche l'erreur systématique, "
                         "pas l'erreur isolée.")
    ap.add_argument("--baseline", help="afficher ce que ce modèle a produit (baselines/<nom>.json)")
    ap.add_argument("--arbitrages", action="store_true",
                    help="lister les décisions écrites en français qui attendent "
                         "d'être traduites en axes")
    args = ap.parse_args()

    if args.rapport:
        rapport()
        return 0

    if args.arbitrages:
        arbitrages()
        return 0

    if args.jeu and args.jeu not in C.JEUX:
        raise SystemExit(f"jeu inconnu : {args.jeu}. Connus : {', '.join(C.JEUX)}")
    if args.echantillon:
        brut = echantillon(args.echantillon)
    else:
        jeux = {args.jeu: C.JEUX[args.jeu]} if args.jeu else C.JEUX
        brut = [(j, k) for j, cas in jeux.items() for k in cas]
    vises = {c.strip() for c in args.cas.split(",") if c.strip()} if args.cas else None
    if vises:
        connus = {k["id"] for _, k in brut}
        inconnus = vises - connus
        if inconnus:
            raise SystemExit(f"cas inconnu(s) : {', '.join(sorted(inconnus))}")
    lot = [(j, k) for j, k in brut
           if (args.tous or vises or not k.get("valide"))
           and (not args.jeu or j == args.jeu)
           and (not args.frontiere or k.get("frontiere") == args.frontiere)
           and (vises is None or k["id"] in vises)]
    if not lot:
        print("rien à revoir avec ces filtres.")
        return 0
    if args.echantillon:
        d = sum(1 for _, k in lot if porte_une_decision(k))
        print(f"{B}échantillon{N} : {len(lot)} cas sur "
              f"{sum(len(v) for v in C.JEUX.values())}, dont {d} qui portent une décision.")

    traces = {}
    if args.baseline:
        chemin = SNAP_DIR / f"{args.baseline}.json"
        if not chemin.is_file():
            raise SystemExit(f"baseline introuvable : {chemin}")
        traces = json.loads(chemin.read_text()).get("cases", {})

    reviser(lot, traces)
    print("\nfini.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
