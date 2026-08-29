"""Exporter un jeu d'entraînement depuis les baselines certifiées par le corpus.

L'idée qui rend le pilote possible sans réécrire 500 sorties à la main :

Le corpus ne contient PAS de sorties attendues, il contient des ASSERTIONS
(« cette capture laisse une tâche », « cette fiche doit naître »). Une baseline,
elle, contient la sortie complète du modèle de référence. Un cas dont toutes les
assertions passent est donc une sortie VÉRIFIÉE : le corpus ne l'a pas écrite,
il l'a certifiée. C'est ce qu'on exporte.

Un cas rouge est exclu, jamais recopié : sa sortie est précisément celle qu'on ne
veut pas apprendre. Ce qu'il faudrait à la place demande une écriture à la main,
et c'est le seul endroit du pilote qui coûte du temps humain.

Le prompt d'entraînement est COURT à dessein. Tout l'intérêt est que les
frontières fines passent dans les poids au lieu de vivre dans 23 ko de prose qui
se déplacent l'un l'autre à chaque édition.
"""
import json, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
_TODAY, _OWNER = "2026-07-13", "Alexis"

SYSTEM_COURT = (
    "You classify a personal capture into a memory record. Answer with one JSON object "
    "and nothing else, with exactly these keys:\n"
    '{"language","memories":[{"note","kind","owner","event_date","event_recurring","summary"}],'
    '"is_ephemeral","ephemeral_content","cancels_action","classification_confidence",'
    '"entities","relations","project_entries","obsoleted_facts","resources"}\n'
    'kind is one of "task","event","episode","note". Dates are absolute (YYYY-MM-DD).\n'
    f"Today is {_TODAY}. The author is {_OWNER}."
)

def exporter(labels: list[str], sortie: Path) -> None:
    vus, lignes, rejets = set(), [], {"rouge": 0, "illisible": 0, "doublon": 0}
    for label in labels:
        p = BASE / "baselines" / f"{label}.json"
        b = json.loads(p.read_text())
        for cid, c in b["cases"].items():
            if cid in vus:
                rejets["doublon"] += 1; continue
            if c.get("gaps"):
                rejets["rouge"] += 1; continue
            if not isinstance(c.get("parsed"), dict):
                rejets["illisible"] += 1; continue
            vus.add(cid)
            lignes.append({
                "id": cid, "set": c.get("set"),
                "messages": [
                    {"role": "system", "content": SYSTEM_COURT},
                    {"role": "user", "content": c["text"]},
                    {"role": "assistant",
                     "content": json.dumps(c["parsed"], ensure_ascii=False)},
                ],
            })
    sortie.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lignes))
    par_set: dict[str, int] = {}
    for l in lignes:
        par_set[l["set"]] = par_set.get(l["set"], 0) + 1
    print(f"exemples certifiés : {len(lignes)}  →  {sortie}")
    print(f"rejetés : {rejets['rouge']} rouges, {rejets['illisible']} illisibles, "
          f"{rejets['doublon']} doublons")
    print("par famille :", dict(sorted(par_set.items(), key=lambda kv: -kv[1])))
    n = sum(len(json.dumps(l["messages"], ensure_ascii=False)) for l in lignes)
    print(f"taille moyenne d'un exemple : {n // max(len(lignes),1)} caractères")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="jeu d'entraînement depuis les baselines")
    ap.add_argument("labels", nargs="+", help="labels de baseline à fusionner")
    ap.add_argument("--sortie", default="pilote-train.jsonl")
    a = ap.parse_args()
    exporter(a.labels, Path(a.sortie))
