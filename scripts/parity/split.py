"""SYN-171 — étage 5 : le classifieur en DEUX appels, mesuré comme un seul.

Pourquoi. Mesuré le 2026-08-20 sur les 59 cas, tableau 2×2 complet (prompt v14/v23 ×
schéma contraint/libre) : E2B émet 33-34 notes sous le prompt v14 et 22 sous le v23,
identiquement avec et sans schéma. Le schéma est disculpé, l'abondance de faits aussi
(v14 sans schéma produit 56 faits ET garde 33 notes). C'est le prompt seul — et
précisément les répétitions retirées à la compaction, dont « la note n'est jamais
absorbée », martelée à quatre endroits.

L'hypothèse testée ici : ces répétitions ne sont nécessaires que parce que les sorties
se CONCURRENCENT dans un appel unique. Séparées en deux appels, l'invariant n'est plus
une consigne — l'appel graphe n'a pas de champ `atomic_note`, il ne peut pas le mettre
à null. La règle disparaît du prompt au lieu d'être répétée.

Les deux appels sont volontairement INDÉPENDANTS : l'extracteur ne reçoit pas la
décision du routeur. C'est le test pur. Un enchaînement rendrait de la cohérence mais
rétablirait le couplage qu'on cherche justement à supprimer — et on ne pourrait plus
dire si le gain vient de la séparation ou de l'ordre.

Ce module ne se lance pas seul : c'est `baseline.py run` qui joue le corpus, ici
comme ailleurs. Il y a eu deux lanceurs jusqu'au 2026-08-25, et ils ont divergé
exactement comme on pouvait le craindre — celui qui NOTAIT les réponses appelait
le prompt en un seul appel, abandonné en production depuis le 2026-08-21, et
celui qui appelait les vrais prompts ne notait rien. On mesurait donc avec
application un prompt que plus personne n'exécute.

La sortie est FUSIONNÉE au format d'un appel unique, pour que `path_of`, les baselines
et `baseline diff` marchent sans la moindre modification : un résultat qui ne se compare
pas aux mesures d'hier ne vaut rien.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import context, providers  # noqa: E402
from scripts.parity.schema import CLASSIFY_SCHEMA  # noqa: E402

# Les deux moitiés du classifieur. Depuis leur adoption (SYN-171, 2026-08-21)
# elles sont des prompts de PRODUCTION comme les autres : versionnées dans
# sinam-core, lues à l'exécution par le core. Le harnais lit les mêmes
# fichiers — il ne teste pas une variante, il teste ce qui tourne.
SPLIT_DIR = Path(
    os.environ.get("SYNAPSE_SPLIT_PROMPTS_DIR",
                   str(context.CORE_CLASSIFIER.parent)))
_HALVES = {"note.md": "classifier-note.md", "graph.md": "classifier-graph.md"}


def _half_path(prompt_file: str) -> Path:
    p = SPLIT_DIR / _HALVES.get(prompt_file, prompt_file)
    if not p.is_file():
        raise SystemExit(
            f"moitié introuvable : {p}\n"
            "SYNAPSE_SPLIT_PROMPTS_DIR doit pointer vers un dossier contenant "
            "classifier-note.md et classifier-graph.md."
        )
    return p

# Découpe du schéma racine par appartenance, pas par recopie : les deux sous-schémas
# se dérivent de CLASSIFY_SCHEMA, donc ils ne peuvent pas dériver de lui.
_NOTE_FIELDS = ("language", "atomic_note", "atomic_note_kind", "atomic_note_owner",
                "event_date",
                "event_recurring", "is_ephemeral", "classification_confidence", "summary")
_GRAPH_FIELDS = ("language", "entities", "relations", "project_entries",
                 "obsoleted_facts")


def _subschema(fields: tuple[str, ...]) -> dict:
    return {
        "type": "object",
        "properties": {k: CLASSIFY_SCHEMA["properties"][k] for k in fields},
        "required": list(fields),
    }


NOTE_SCHEMA = _subschema(_NOTE_FIELDS)
GRAPH_SCHEMA = _subschema(_GRAPH_FIELDS)


def _system(prompt_file: str) -> list[str]:
    """Prompt de la moitié + l'échafaudage, dans l'ordre où le core l'assemble.

    ⚠ Corrigé le 2026-08-24 (trouvé en instruisant SYN-190). Cette fonction
    envoyait le bloc des types aux DEUX moitiés et le bloc projets à AUCUNE, alors
    que le core (`Brain::build_classify_params`) réserve types et projets à la
    moitié GRAPHE et n'envoie l'auteur aux deux. C'est la divergence exacte que le
    harnais existe pour éviter : trois blocs sur quatre étaient mal adressés.

    Conséquence assumée : les empreintes des baselines `*-split` d'avant cette
    date ne coïncident plus avec celles d'après, donc elles ne se comparent plus.
    C'est le comportement voulu — une empreinte qui bouge dit qu'on a changé
    l'énoncé, et on l'a bel et bien changé.

    Le corollaire mesuré en août (« l'échafaudage est le même pour les deux
    appels, donc le surcoût est additif, ~+10 % ») portait sur cette assemblée
    fausse : à remesurer.
    """
    prompt = context.load_prompt(_half_path(prompt_file))
    blocks = [prompt]
    # Une moitié ne lit que ce qu'elle peut écrire : `entities[].type`,
    # `facts[].predicate` et `project_entries[]` n'existent que côté graphe.
    if prompt_file == "graph.md":
        blocks += [context.static_types_block(), context.static_projects_block()]
    # L'auteur compte pour les deux : la moitié note en a besoin pour distinguer
    # une action rapportée de celle de l'auteur (SYN-182), la graphe pour résoudre
    # « je »/« mon » sur la bonne entité.
    blocks.append(context.static_owner_block())
    return blocks


def classify_split(model: str, text: str, schema: bool, temperature: float) -> tuple[dict | None, dict]:
    """Les deux appels, fusionnés au format d'un appel unique.

    Retourne (fusion, diag). `fusion` vaut None si AUCUNE des deux moitiés n'a produit
    de JSON — une seule moitié perdue laisse l'autre exploitable, ce qui est justement
    une propriété du découpage qu'on veut voir dans les chiffres, pas masquer.
    """
    a = providers.call(model, _system("note.md"), text, context.CLASSIFY_MAX_TOKENS,
                       providers.DEFAULT_NUM_CTX, NOTE_SCHEMA if schema else None, temperature)
    b = providers.call(model, _system("graph.md"), text, context.CLASSIFY_MAX_TOKENS,
                       providers.DEFAULT_NUM_CTX, GRAPH_SCHEMA if schema else None, temperature)
    note = context.parse_classify(a.text, a.stop_reason)
    graph = context.parse_classify(b.text, b.stop_reason)
    diag = {"note_parsed": note is not None, "graph_parsed": graph is not None,
            "latency_s": round(a.latency_s + b.latency_s, 2),
            "prompt_tokens": max(a.prompt_tokens or 0, b.prompt_tokens or 0),
            # Le coût se compte sur la SOMME des deux appels, jamais sur le max :
            # le max sert à vérifier qu'un prompt est bien passé (piège num_ctx),
            # il sous-estime la facture d'un facteur ~2 sur un run découpé.
            "input_tokens": (a.prompt_tokens or 0) + (b.prompt_tokens or 0),
            "uncached_tokens": (a.extra.get("uncached_input_tokens") or 0)
                               + (b.extra.get("uncached_input_tokens") or 0),
            "output_tokens": (a.output_tokens or 0) + (b.output_tokens or 0)}
    if note is None and graph is None:
        return None, diag
    merged: dict = {}
    merged.update(note or {})
    # Le graphe ne peut pas écraser la note : il n'a aucune clé en commun avec elle
    # hormis `language`, et la moitié note fait autorité dessus (elle a lu le texte
    # pour l'écrire dedans).
    # ⚠ Cette liste doit rester celle du core (`llm.rs::merge_halves`), à
    # l'identique. Trouvé le 2026-08-25 : `obsoleted_facts` y manquait, donc la
    # moitié graphe le produisait et le harnais le jetait. Les cinq cas NEG-b
    # sortaient « négation absente » alors que la production, elle, la voyait.
    # Un harnais qui perd un champ ne mesure pas une régression, il en invente
    # une, et c'est pire : on corrige alors ce qui marchait.
    for k in ("entities", "relations", "project_entries", "obsoleted_facts"):
        merged[k] = (graph or {}).get(k) or []
    merged.setdefault("language", (graph or {}).get("language"))
    return merged, diag


# $/Mtok (entrée, lecture de cache, sortie). Une mesure dont on ignore le prix
# finit par se relancer sans qu'on sache ce qu'elle coûte : c'est ce qui est
# arrivé le 2026-08-21, 22 baselines Haiku plus tard.
_TARIFS = {"claude-haiku-4-5-20251001": (1.00, 0.10, 5.00)}


def _cout(model: str, cases: dict) -> str:
    tarif = _TARIFS.get(model)
    if not tarif:
        return ""
    entree, cache, sortie = tarif
    nc = sum(c.get("uncached_tokens") or 0 for c in cases.values())
    lu = sum((c.get("input_tokens") or 0) - (c.get("uncached_tokens") or 0)
             for c in cases.values())
    out = sum(c.get("output_tokens") or 0 for c in cases.values())
    usd = (nc * entree + lu * cache + out * sortie) / 1e6
    return (f"coût     : ~{usd:.2f} $  "
            f"({nc/1000:.0f}k entrée · {lu/1000:.0f}k relus du cache · {out/1000:.0f}k sortie)")
