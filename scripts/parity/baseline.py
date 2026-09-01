"""Figer une baseline, puis diffé deux baselines.

Le gate dit « utilisable / inutilisable ». Ce module-ci ne juge rien : il
enregistre ce qu'un modèle répond sur TOUT le corpus, avec l'empreinte du
contexte, pour qu'on puisse changer le prompt et prouver ce qui a bougé.

C'est l'outil qui manquait aux trois décisions de modèle prises depuis juillet :
à chaque fois on a mesuré l'après sans avoir gardé l'avant.

    python -m scripts.parity.baseline run anthropic:claude-haiku-4-5-20251001 \
        --label avant-arbitrages
    python -m scripts.parity.baseline diff avant-arbitrages apres-arbitrages

Il joue LES DEUX MOITIÉS du classifieur, c'est-à-dire ce que le core exécute
réellement depuis le 2026-08-21. `--appel-unique` rejoue l'ancien `classifier.md`,
et sert à une seule chose : relire une baseline d'avant cette date. Toute mesure
prise avec ce drapeau sur une règle écrite depuis est fausse par construction, et
le lanceur le dit à l'écran.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import context, providers, score, split  # noqa: E402
from scripts.parity.corpus import SETS  # noqa: E402
from scripts.parity.paths import path_of  # noqa: E402
from scripts.parity.schema import CLASSIFY_SCHEMA  # noqa: E402

SNAP_DIR = _REPO / "scripts" / "parity" / "baselines"

# Les axes qu'on diffe. Volontairement les signaux de ROUTAGE seulement : le
# texte d'une note varie d'une exécution à l'autre sans que ce soit une
# régression, alors qu'une branche qui bascule en est toujours une (ou une
# correction, et c'est justement ce qu'on veut voir).
DIFFED = ("has_note", "kind", "memories", "facts", "relations", "projects")


def _frontiere(case: dict, ecart: str) -> str:
    """Rattacher un écart à la frontière qu'il concerne.

    On lit le NOM DE L'AXE en tête de l'écart plutôt que d'annoter chaque cas à
    la main : une étiquette recopiée à côté d'une assertion finit toujours par la
    contredire, et c'est alors elle qu'on croit.
    """
    for axe, frontiere in score.AXES.items():
        if ecart.startswith(axe) or ecart.startswith(f"{axe} attendu"):
            return frontiere
    if ecart.startswith("atomicité"):
        return score.AXES["facts_min"]
    if ecart.startswith("relation"):
        return score.AXES["rel"]
    if ecart.startswith("entrée projet"):
        return score.AXES["proj"]
    if ecart.startswith("entité"):
        return score.AXES["entity_expected"]
    if ecart.startswith("valeur inventée"):
        return score.AXES["forbidden_value"]
    if ecart.startswith("prédicat interdit"):
        return score.AXES["forbidden_predicate"]
    # Trois axes dont l'écart s'énonce en français et non par leur nom de clé :
    # sans ces lignes ils tombaient dans « autre », c'est-à-dire dans le tas où
    # l'on ne regarde plus.
    if ecart.startswith("négation"):
        return score.AXES["no_obsolete" if "de trop" in ecart else "obsoletes"]
    if ecart.startswith("renommage"):
        return score.AXES["no_rename" if "de trop" in ecart else "renamed_to"]
    if "À valider" in ecart:
        return score.AXES["needs_review"]
    return "autre"


def cmd_run(args) -> int:
    if args.prompt and not args.appel_unique:
        raise SystemExit("--prompt ne s'applique qu'à --appel-unique : les deux "
                         "moitiés se lisent dans sinam-core, là où le core les lit.")
    schema = CLASSIFY_SCHEMA if args.schema else None
    sets = args.sets.split(",") if args.sets else list(SETS)
    vises = {c.strip() for c in args.cas.split(",") if c.strip()} if args.cas else None
    if vises:
        connus = {k["id"] for s_ in SETS.values() for k in s_}
        if vises - connus:
            raise SystemExit(f"cas inconnu(s) : {', '.join(sorted(vises - connus))}")
    print(f"modèle   : {args.model}")

    if args.appel_unique:
        system = context.classifier_system(Path(args.prompt) if args.prompt else None)
        fp = context.fingerprint(system)
        print(f"contexte : {sum(len(b) for b in system)} caractères · empreinte {fp}")
        print("⚠ appel unique : `classifier.md` n'est plus exécuté en production "
              "depuis le 2026-08-21. Ce que ce run mesure d'une règle écrite depuis "
              "cette date ne veut rien dire.")
    else:
        note, graphe = split._system("note.md"), split._system("graph.md")
        fp_note, fp_graph = context.fingerprint(note), context.fingerprint(graphe)
        fp = f"{fp_note}+{fp_graph}"
        print(f"appel 1  : {sum(len(b) for b in note)} car · empreinte {fp_note}")
        print(f"appel 2  : {sum(len(b) for b in graphe)} car · empreinte {fp_graph}")
    if vises:
        print(f"corpus   : {len(vises)} cas nommés")
    else:
        print(f"corpus   : {', '.join(sets)}")
    print()

    out: dict = {"model": args.model, "fingerprint": fp, "label": args.label,
                 "schema_constrained": bool(schema), "split": not args.appel_unique,
                 "temperature": args.temperature, "cases": {}}
    ecarts = 0
    par_frontiere: dict[str, list[str]] = {}
    joues = 0
    demi = 0
    for set_name in sets:
        for case in SETS[set_name]:
            if vises is not None and case["id"] not in vises:
                continue
            joues += 1
            if args.appel_unique:
                reply = providers.call(args.model, system, case["text"],
                                       context.CLASSIFY_MAX_TOKENS, args.num_ctx, schema,
                                       args.temperature)
                parsed = context.parse_classify(reply.text, reply.stop_reason)
                diag = {"latency_s": reply.latency_s, "prompt_tokens": reply.prompt_tokens}
            else:
                parsed, diag = split.classify_split(args.model, case["text"],
                                                    bool(schema), args.temperature)
                if not (diag["note_parsed"] and diag["graph_parsed"]):
                    demi += 1
            rec = path_of(parsed)
            gaps = score.gaps(case, parsed)
            # `parsed` en dernier, et à dessein : `path_of` y met un booléen
            # « ça s'est lu », alors que la notation et `revue --baseline` ont
            # besoin de l'OBJET. L'ordre inverse rend un booléen là où le reste
            # du harnais attend un dictionnaire.
            rec.update(set=set_name, text=case["text"], **diag,
                       confidence=(parsed or {}).get("classification_confidence"),
                       gaps=gaps, axes=score.axes_of(case), parsed=parsed)
            out["cases"][case["id"]] = rec
            if gaps:
                ecarts += 1
                for axe in gaps:
                    par_frontiere.setdefault(_frontiere(case, axe), []).append(case["id"])
            # À 500 cas, une ligne par cas rend la sortie illisible et noie les
            # trois qui comptent. `--tout` restaure l'ancien comportement quand on
            # veut voir passer le corpus entier.
            if gaps or args.tout or not rec.get("parsed"):
                mark = "✗" if not rec.get("parsed") else ("•" if gaps else "·")
                detail = f"  ({'; '.join(gaps)})" if gaps else ""
                print(f"  {mark} {case['id']:22} "
                      f"note={str(rec.get('has_note')):5} kind={str(rec.get('kind')):6} "
                      f"f={rec.get('facts')} r={rec.get('relations')}{detail}", flush=True)

    print(f"\n{joues - ecarts}/{joues} cas conformes à l'étiquette validée.")
    if demi:
        print(f"⚠ {demi} cas où une seule des deux moitiés a répondu — c'est le coût "
              f"propre au découpage, il ne se lit pas comme une erreur de jugement.")
    if par_frontiere:
        print("\nÉcarts par frontière (voir scripts/parity/frontieres.md) :")
        for frontiere, ids in sorted(par_frontiere.items(),
                                     key=lambda kv: -len(kv[1])):
            liste = ", ".join(sorted(set(ids))[:6])
            reste = f" (+{len(set(ids)) - 6})" if len(set(ids)) > 6 else ""
            print(f"  {frontiere:12} {len(ids):3}  {liste}{reste}")
    out["ecarts"] = ecarts
    out["par_frontiere"] = {k: sorted(set(v)) for k, v in par_frontiere.items()}
    ligne = split._cout(args.model.split(":", 1)[-1], out["cases"])
    if ligne:
        print(f"\n{ligne}")

    # Combien de la fenêtre le prompt a mangé. Le gate vérifie déjà qu'il ENTRE
    # (`prompt_tokens < num_ctx`) — mais entrer ne suffit pas : il faut aussi
    # qu'il reste de la place pour ÉCRIRE. Avec `--context-shift`, un prompt qui
    # occupe presque toute la fenêtre fait évincer ses propres premières lignes
    # pendant la génération : le modèle répond sans les règles qu'on lui a
    # données, et la mesure impute au modèle un défaut de fenêtre.
    seen = [r["prompt_tokens"] for r in out["cases"].values() if r.get("prompt_tokens")]
    if seen:
        worst = max(seen)
        libre = args.num_ctx - worst
        alerte = "  ⚠ SOUS le budget de sortie" if libre < context.CLASSIFY_MAX_TOKENS else ""
        print(f"\nfenêtre  : prompt ≤ {worst} tokens sur num_ctx={args.num_ctx} "
              f"→ {libre} libres pour écrire (budget {context.CLASSIFY_MAX_TOKENS}){alerte}")
        out["prompt_tokens_max"] = worst

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{args.label}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ baseline écrite : {path.relative_to(_REPO)}  ({len(out['cases'])} cas)")
    return 0


def cmd_diff(args) -> int:
    a = json.loads((SNAP_DIR / f"{args.before}.json").read_text(encoding="utf-8"))
    b = json.loads((SNAP_DIR / f"{args.after}.json").read_text(encoding="utf-8"))

    if a["fingerprint"] != b["fingerprint"]:
        print(f"⚠ empreintes de contexte différentes : {a['fingerprint']} → "
              f"{b['fingerprint']} — c'est attendu si le prompt a changé, "
              f"suspect sinon.")
    if a["model"] != b["model"]:
        print(f"⚠ modèles différents : {a['model']} → {b['model']} — le diff mélange "
              f"alors l'effet du prompt et celui du modèle.")

    ids = sorted(set(a["cases"]) | set(b["cases"]))
    changed = 0
    for cid in ids:
        ca, cb = a["cases"].get(cid), b["cases"].get(cid)
        if ca is None:
            print(f"  + {cid:22} cas neuf")
            continue
        if cb is None:
            print(f"  − {cid:22} cas disparu")
            continue
        deltas = [f"{k}: {ca.get(k)!r} → {cb.get(k)!r}"
                  for k in DIFFED if ca.get(k) != cb.get(k)]
        if deltas:
            changed += 1
            print(f"  ~ {cid:22} ({ca.get('set')})")
            for d in deltas:
                print(f"      {d}")
    total = len(ids)
    print(f"\n{changed} cas modifiés sur {total}. "
          f"{'Aucune bascule de branche.' if not changed else ''}")
    print("Un changement n'est pas une régression : c'est à toi de dire, cas par "
          "cas, si la nouvelle branche est celle que tu voulais.")
    return 0


def cmd_rescore(args) -> int:
    """Renoter une baseline contre les étiquettes d'AUJOURD'HUI, sans rappeler le modèle.

    Les réponses sont stockées ; les écarts, eux, sont dérivés des étiquettes du
    moment où la passe a tourné. Une revue qui corrige une étiquette laisse donc
    derrière elle des baselines qui accusent le modèle d'un écart que plus personne
    n'assert. Renoter est gratuit — c'est un calcul, pas un appel.
    """
    chemin = SNAP_DIR / f"{args.label}.json"
    if not chemin.is_file():
        raise SystemExit(f"baseline introuvable : {chemin}")
    data = json.loads(chemin.read_text(encoding="utf-8"))
    cases = {c["id"]: c for jeu in SETS.values() for c in jeu}
    av = ap = 0
    par_frontiere: dict[str, list[str]] = {}
    for cid, rec in data["cases"].items():
        case = cases.get(cid)
        if case is None:
            print(f"  ? {cid:22} cas disparu du corpus, écarts laissés tels quels")
            continue
        anciens = rec.get("gaps") or []
        neufs = score.gaps(case, rec.get("parsed"))
        av += bool(anciens)
        ap += bool(neufs)
        if anciens != neufs:
            print(f"  ~ {cid}")
            for g in anciens:
                if g not in neufs:
                    print(f"      parti  : {g}")
            for g in neufs:
                if g not in anciens:
                    print(f"      apparu : {g}")
        rec["gaps"] = neufs
        rec["axes"] = score.axes_of(case)
        for axe in neufs:
            par_frontiere.setdefault(_frontiere(case, axe), []).append(cid)
    data["ecarts"] = ap
    data["par_frontiere"] = {k: sorted(set(v)) for k, v in par_frontiere.items()}
    data["rescored"] = str(date.today())
    if not args.sec:
        chemin.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{av} cas en écart avec les anciennes étiquettes → {ap} avec celles d'aujourd'hui."
          + ("  (à sec, rien écrit)" if args.sec else f"  → {chemin.name} réécrite"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="baselines de parité")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="jouer le corpus et figer une baseline")
    r.add_argument("model")
    r.add_argument("--label", required=True)
    r.add_argument("--prompt", help="fichier de prompt, avec --appel-unique seulement")
    r.add_argument("--appel-unique", action="store_true",
                   help="rejouer `classifier.md`, le prompt en un seul appel abandonné "
                        "en production le 2026-08-21. Sert à relire une baseline "
                        "d'avant cette date, pas à mesurer aujourd'hui.")
    r.add_argument("--sets", help=f"sous-ensembles séparés par des virgules ({', '.join(SETS)})")
    r.add_argument("--cas", help="ne jouer que ces cas, par identifiant, séparés par des "
                                 "virgules. Pour bissecter une régression sans repayer les "
                                 "familles entières : six cas coûtent six cas.")
    r.add_argument("--schema", action="store_true")
    r.add_argument("--num-ctx", type=int, default=providers.DEFAULT_NUM_CTX)
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--tout", action="store_true",
                   help="afficher les cas conformes aussi (défaut : seulement les écarts)")
    r.set_defaults(func=cmd_run)

    rs = sub.add_parser("rescore", help="renoter une baseline contre les étiquettes "
                                       "d'aujourd'hui, sans rappeler le modèle")
    rs.add_argument("label")
    rs.add_argument("--sec", action="store_true", help="montrer sans réécrire le fichier")
    rs.set_defaults(func=cmd_rescore)

    d = sub.add_parser("diff", help="comparer deux baselines")
    d.add_argument("before")
    d.add_argument("after")
    d.set_defaults(func=cmd_diff)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
