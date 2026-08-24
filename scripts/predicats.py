"""SYN-190 — la santé du vocabulaire de prédicats, et sa normalisation.

Le bloc de contexte (`llm.rs::active_predicates_block`) montre au modèle les
prédicats déjà en usage pour qu'il les réutilise. Ça n'a de sens que si ce
vocabulaire reste court et généralisable : lui montrer quatre-vingt-dix noms
jetables lui enseigne que le jetable est la norme.

Ce module sert à le VOIR, puis à le nettoyer.

    python -m scripts.predicats rapport
    python -m scripts.predicats proposer --out /tmp/fusions.json
    python -m scripts.predicats appliquer /tmp/fusions.json          # à blanc
    python -m scripts.predicats appliquer /tmp/fusions.json --pour-de-vrai

**Rien n'est appliqué sans un fichier de fusions relu à la main.** Renommer un
prédicat réécrit la mémoire de l'utilisateur : c'est irréversible sans sauvegarde,
et une fusion fausse fait disparaître un fait sous un autre.

Le critère qui compte n'est pas le nombre d'occurrences, c'est le nombre
d'ENTITÉS DISTINCTES portant le prédicat. Un nom utilisé trois fois sur la même
entité reste une phrase déguisée en nom ; un nom porté par deux entités est du
vocabulaire. C'est le même ordre que celui du bloc de contexte.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from db import cursor_to_dicts, get_connection  # noqa: E402

# Les têtes de `SINGLE_VALUED_FAMILIES` (`routing.rs:45`), miroir du prompt. Elles
# gagnent comme nom canonique dans une fusion : ce sont les SEULES que la mémoire
# sait périmer, donc ramener un synonyme vers elles répare le supersede, alors que
# l'inverse le casserait.
TETES_DE_FAMILLE = ["works_at", "job_title", "lives_in", "has_birthday",
                    "phone", "email", "age"]

# Affixes qui ne portent pas de sens propre : `is_cousin_of` et `cousin_of` sont
# le même prédicat, `works_at` et `worked_at` aussi. Les retirer donne une
# signature comparable. Volontairement court — un stemmer agressif fusionnerait
# `born_on` et `borrows`, et une fusion fausse coûte plus cher qu'un doublon.
_STRIP_PREFIX = ("is_", "has_", "was_", "were_")
_STRIP_SUFFIX = ("_of", "_to", "_for")
_STOP = {"the", "a", "an"}


def _signature(predicate: str) -> str:
    """La forme comparable d'un prédicat : minuscules, affixes vides retirés,
    verbes ramenés à leur radical, mots triés. Deux prédicats de même signature
    disent très probablement la même chose."""
    p = predicate.strip().lower()
    for pre in _STRIP_PREFIX:
        if p.startswith(pre):
            p = p[len(pre):]
    for suf in _STRIP_SUFFIX:
        if p.endswith(suf):
            p = p[: -len(suf)]
    mots = []
    for m in re.split(r"[_\s]+", p):
        if not m or m in _STOP:
            continue
        # Radical très prudent : pluriel et passé seulement.
        for term in ("ing", "ed", "es", "s"):
            if len(m) > 4 and m.endswith(term):
                m = m[: -len(term)]
                break
        mots.append(m)
    return " ".join(sorted(mots))


def _facts(conn) -> list[dict]:
    return cursor_to_dicts(conn.execute(
        "SELECT predicate, COUNT(*) n, COUNT(DISTINCT entity_id) ents FROM facts "
        "WHERE obsoleted_at IS NULL AND archived_at IS NULL AND predicate IS NOT NULL "
        "GROUP BY predicate ORDER BY ents DESC, n DESC, predicate ASC"))


def _relations(conn) -> list[dict]:
    return cursor_to_dicts(conn.execute(
        "SELECT predicate, COUNT(*) n, COUNT(DISTINCT entity_from) ents FROM relations "
        "WHERE COALESCE(review_status,'confirmed') <> 'pending' AND predicate IS NOT NULL "
        "GROUP BY predicate ORDER BY ents DESC, n DESC, predicate ASC"))


def cmd_rapport(args) -> int:
    conn = get_connection()
    for nom, rows in (("FAITS", _facts(conn)), ("RELATIONS", _relations(conn))):
        total = len(rows)
        generaux = [r for r in rows if r["ents"] >= 2]
        uniques = [r for r in rows if r["n"] == 1]
        etabli = ", ".join(f"{r['predicate']}({r['ents']})" for r in generaux) or "(aucun)"

        print(f"\n=== {nom} ===")
        print(f"  {total} prédicats distincts")
        print(f"  {len(generaux)} portés par 2 entités ou plus  ← le vrai vocabulaire")
        print(f"  {len(uniques)} utilisés une seule fois "
              f"({100 * len(uniques) // max(total, 1)} %)")
        print(f"  établi : {etabli}")

    f = _facts(conn)
    part = 100 * len([r for r in f if r["ents"] >= 2]) // max(len(f), 1)
    print(f"\nIndicateur à suivre : {part} % des prédicats de fait généralisent. "
          f"Il doit MONTER au fil des captures ; s'il baisse, la dérive a repris.")
    return 0


# Une valeur de REMPLISSAGE ne dit rien : toute l'information du fait est alors
# dans le nom du prédicat. C'est le seul cas où le mot qui distingue deux
# prédicats voisins EST la valeur, et donc le seul cas où la réécriture est sûre.
_REMPLISSAGE = {"true", "false", "yes", "no", "oui", "non", "1", "0", "", "none", "null"}


def _granularite(conn, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Les prédicats dont le NOM porte la valeur.

    Motif : deux prédicats qui ne diffèrent que d'un mot. `supports_manual_tagging`
    et `supports_automatic_tagging` ne sont PAS des synonymes — les fusionner
    détruirait l'information. Ils disent la même affirmation avec deux valeurs, et
    le mot qui les sépare EST la valeur. La correction n'est donc pas un renommage
    mais une réécriture : prédicat élargi + valeur remplie.

    C'est le motif dominant de la dérive, et celui que la ressemblance par
    embedding signale le plus fort tout en donnant le plus mauvais conseil.

    **Le discriminant est la VALEUR ACTUELLE, pas le nom.** `supports_manual_tagging`
    vaut « true » : la valeur ne dit rien, donc « manual » est bien la valeur, et la
    réécriture est sûre. `is_primary_channel_for` vaut « Navi distribution » : la
    valeur dit déjà quelque chose, donc « primary » n'est PAS la valeur mais une
    seconde dimension, et réécrire écraserait la première. Le second cas sort en
    `a_trancher` : il demande un jugement, pas une règle.

    Rend (réécritures sûres, cas à trancher à la main).
    """
    def valeurs(pred: str) -> list[str]:
        return [str(r["value"] or "").strip().lower() for r in cursor_to_dicts(
            conn.execute("SELECT value FROM facts WHERE predicate = ? "
                         "AND obsoleted_at IS NULL AND archived_at IS NULL", [pred]))]

    par_mots = [(r["predicate"], r["predicate"].split("_")) for r in rows]
    vus, sûrs, a_trancher = set(), [], []
    for i, (a, ma) in enumerate(par_mots):
        for b, mb in par_mots[i + 1:]:
            if len(ma) != len(mb) or len(ma) < 3:
                continue
            diff = [k for k in range(len(ma)) if ma[k] != mb[k]]
            if len(diff) != 1:
                continue
            k = diff[0]
            cible = "_".join(ma[:k] + ma[k + 1:])
            if (cible, a, b) in vus:
                continue
            vus.add((cible, a, b))
            va, vb = valeurs(a), valeurs(b)
            porteuse = [v for v in va + vb if v not in _REMPLISSAGE]
            if porteuse:
                a_trancher.append({
                    "vers_possible": cible, "predicats": [a, b],
                    "pourquoi": "la valeur actuelle porte déjà du sens "
                                f"({porteuse[0]!r}) : réécrire l'écraserait",
                })
                continue
            sûrs.append({"vers": cible,
                         "reecrire": [{"de": a, "valeur": ma[k]},
                                      {"de": b, "valeur": mb[k]}]})
    return sûrs, a_trancher


def cmd_proposer(args) -> int:
    """Regroupe les prédicats de même signature et propose un nom canonique.

    Deux sources, gardées séparées dans la sortie parce qu'elles n'ont pas la même
    fiabilité : la signature lexicale (précise, peu de rappel) et le voisinage par
    embedding (l'inverse). La deuxième n'est qu'une PISTE : c'est le même outil que
    la fusion d'entités de SYN-61, où il propose et n'applique jamais.
    """
    conn = get_connection()
    sortie: dict = {"facts": [], "relations": [], "granularite": [],
                    "a_trancher": [], "pistes": []}

    for cle, rows in (("facts", _facts(conn)), ("relations", _relations(conn))):
        groupes: dict[str, list[dict]] = {}
        for r in rows:
            groupes.setdefault(_signature(r["predicate"]), []).append(r)
        for sig, membres in sorted(groupes.items()):
            if len(membres) < 2:
                continue
            # Le canonique : une graine si elle est dans le groupe (c'est elle qui
            # porte l'appartenance à une famille mono-valuée), sinon le plus général.
            tete = next((m for m in membres if m["predicate"] in TETES_DE_FAMILLE), None)
            canon = (tete or membres[0])["predicate"]
            sortie[cle].append({
                "canonique": canon,
                "fusionner": [m["predicate"] for m in membres if m["predicate"] != canon],
                "signature": sig,
                "detail": {m["predicate"]: {"n": m["n"], "entites": m["ents"]} for m in membres},
            })

    sortie["granularite"], sortie["a_trancher"] = _granularite(conn, _facts(conn))
    if args.embeddings:
        sortie["pistes"] = _pistes_embedding(_facts(conn), args.seuil)

    args.out.write_text(json.dumps(sortie, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(sortie["facts"]) + len(sortie["relations"])
    print(f"{n} groupe(s) lexical(aux), {len(sortie['granularite'])} réécriture(s) "
          f"de granularité SÛRE(S), {len(sortie['a_trancher'])} cas à trancher, "
          f"{len(sortie['pistes'])} piste(s) par embedding")
    print(f"→ {args.out}")
    print("\nRelis le fichier, corrige les canoniques, SUPPRIME ce que tu refuses, "
          "puis `appliquer`. Rien n'est écrit avant.")
    if sortie["pistes"]:
        print("⚠ Les `pistes` par embedding NE SONT PAS des propositions : les vrais "
              "synonymes et les inverses y ont les mêmes scores (parent_of ⇄ child_of "
              "= 0,82). À relire une par une, jamais à recopier en bloc.")
    return 0


def _pistes_embedding(rows: list[dict], seuil: float) -> list[dict]:
    """Voisins proches par embedding du NOM du prédicat.

    ⚠ **À LIRE, JAMAIS À APPLIQUER TEL QUEL.** Mesuré le 2026-08-24 : les scores
    des vrais synonymes et ceux des paires à ne jamais fusionner se recouvrent
    complètement. `interviewed_at` ⇄ `interviewed_by` sort à 0,955, plus haut que
    `works_as` ⇄ `works_at` (0,696) ; `parent_of` ⇄ `child_of` sort à 0,817 alors
    que ce sont des INVERSES, et les fusionner retournerait le sens du graphe.

    Aucun seuil ne sépare les deux populations. C'est pour ça que la passe du core
    n'utilise l'embedding QUE contre les familles mono-valuées, où l'enjeu est net.
    Ici on garde la vue complète parce qu'un humain la relit, mais elle sert à
    repérer, pas à décider.
    """
    import struct

    from embeddings import embed_text

    noms = [r["predicate"] for r in rows]
    vecs = {}
    for nom in noms:
        raw = embed_text(nom.replace("_", " "))
        vecs[nom] = struct.unpack(f"{len(raw) // 4}f", raw)
    out = []
    for i, a in enumerate(noms):
        for b in noms[i + 1:]:
            score = sum(x * y for x, y in zip(vecs[a], vecs[b]))
            if score >= seuil and _signature(a) != _signature(b):
                out.append({"a": a, "b": b, "score": round(score, 3)})
    return sorted(out, key=lambda d: -d["score"])


def cmd_appliquer(args) -> int:
    plan = json.loads(args.mapping.read_text(encoding="utf-8"))
    conn = get_connection()
    total = 0
    for cle, table, col in (("facts", "facts", "entity_id"),
                            ("relations", "relations", "entity_from")):
        for groupe in plan.get(cle, []):
            canon = groupe["canonique"]
            for ancien in groupe["fusionner"]:
                rows = cursor_to_dicts(conn.execute(
                    f"SELECT COUNT(*) n FROM {table} WHERE predicate = ?", [ancien]))
                n = rows[0]["n"] if rows else 0
                if not n:
                    continue
                total += n
                print(f"  {ancien:38} → {canon:24} ({n} ligne(s))")
                if args.pour_de_vrai:
                    # ⚠ Les entités touchées voient leur résumé devenir obsolète :
                    # il est DÉRIVÉ des faits actifs (SYN-89). Sans ce marquage, la
                    # fiche continue d'afficher une phrase construite sur l'ancien
                    # nom, et plus rien ne la régénère.
                    conn.execute(
                        f"UPDATE entities SET summary_stale = 1 WHERE id IN "
                        f"(SELECT {col} FROM {table} WHERE predicate = ?)", [ancien])
                    conn.execute(
                        f"UPDATE {table} SET predicate = ? WHERE predicate = ?",
                        [canon, ancien])
    for groupe in plan.get("granularite", []):
        cible = groupe["vers"]
        for item in groupe["reecrire"]:
            rows = cursor_to_dicts(conn.execute(
                "SELECT COUNT(*) n FROM facts WHERE predicate = ?", [item["de"]]))
            n = rows[0]["n"] if rows else 0
            if not n:
                continue
            total += n
            print(f"  {item['de']:38} → {cible}={item['valeur']!r} ({n} ligne(s))")
            if args.pour_de_vrai:
                conn.execute(
                    "UPDATE entities SET summary_stale = 1 WHERE id IN "
                    "(SELECT entity_id FROM facts WHERE predicate = ?)", [item["de"]])
                # La valeur d'origine est ÉCRASÉE : sur ce motif elle ne porte rien
                # (« true », « yes »), toute l'information est dans le nom. Vérifier
                # dans le passage à blanc avant de lancer pour de vrai.
                conn.execute(
                    "UPDATE facts SET predicate = ?, value = ? WHERE predicate = ?",
                    [cible, item["valeur"], item["de"]])

    print(f"\n{total} ligne(s) concernée(s).")
    if not args.pour_de_vrai:
        print("À BLANC — rien n'a été écrit. Relance avec --pour-de-vrai.")
    else:
        print("Écrit. Deux suites obligatoires :")
        print("  1. `python reembed.py` — les résumés régénérés changent les vecteurs ;")
        print("  2. vérifier les faits que la fusion rend MONO-VALUÉS : rapprocher deux "
              "noms d'une même famille (`works_as` → `job_title`) fait périmer le plus "
              "ancien à la prochaine écriture, ce qui est le but, mais se voit.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SYN-190 — vocabulaire de prédicats")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rapport", help="santé du vocabulaire")
    r.set_defaults(func=cmd_rapport)

    p = sub.add_parser("proposer", help="proposer des fusions (n'écrit rien en base)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--embeddings", action="store_true",
                   help="ajouter les voisins par embedding (plus lent, plus de rappel)")
    p.add_argument("--seuil", type=float, default=0.80)
    p.set_defaults(func=cmd_proposer)

    a = sub.add_parser("appliquer", help="appliquer un fichier de fusions relu")
    a.add_argument("mapping", type=Path)
    a.add_argument("--pour-de-vrai", action="store_true")
    a.set_defaults(func=cmd_appliquer)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
