"""Les 186 questions du harnais, jouées sur le Mac par mlx-lm.

Même rôle que `mesurer.py` sur le pod, même format de sortie, donc le fichier
produit se note avec le VRAI `score.py` par le provider `rejeu`.

Reprend là où il s'est arrêté : ~45 s par question sur un M1 8 Go, soit plus de
deux heures, et un Mac qui s'endort ne doit pas coûter la passe entière.
"""
import json
import os
import sys
import time
from pathlib import Path

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

RACINE = Path(__file__).resolve().parent
MODELE = os.environ.get("MODELE", "mlx-community/Qwen3.5-4B-MLX-4bit")


def main():
    nom = sys.argv[1] if len(sys.argv) > 1 else "lora-60-mlx"
    adaptateur = sys.argv[2] if len(sys.argv) > 2 else str(RACINE / "adaptateurs" / "mlx-60")
    if adaptateur in ("-", "nu"):
        adaptateur = None

    p = json.loads((RACINE / "questions.json").read_text())
    cible = RACINE / "reponses" / f"{nom}.json"
    cible.parent.mkdir(parents=True, exist_ok=True)

    faites = {}
    if cible.is_file():
        faites = {r["cle"]: r for r in json.loads(cible.read_text())}
        print(f"reprise : {len(faites)} reponses deja la", flush=True)

    m, tok = load(MODELE, adapter_path=adaptateur)
    sampler = make_sampler(temp=0.0)
    print(f"### {nom} ({MODELE}" + (f" + {adaptateur}" if adaptateur else " NU") + ")", flush=True)

    out, t0 = [], time.time()
    for i, q in enumerate(p["questions"], 1):
        if q["cle"] in faites:
            out.append(faites[q["cle"]]); continue
        msgs = [{"role": "system", "content": p["systemes"][q["sys"]]},
                {"role": "user", "content": q["user"]}]
        texte = tok.apply_chat_template(msgs, tokenize=False,
                                        add_generation_prompt=True,
                                        enable_thinking=False)
        t1 = time.time()
        rep = generate(m, tok, prompt=texte, max_tokens=p["max_tokens"],
                       sampler=sampler, verbose=False)
        out.append({"cle": q["cle"], "text": rep, "stop_reason": "stop",
                    "prompt_tokens": None, "output_tokens": None,
                    "latency_s": round(time.time() - t1, 1)})
        # on écrit à CHAQUE réponse : deux heures de calcul ne doivent jamais
        # tenir dans la seule mémoire d'un processus.
        cible.write_text(json.dumps(out, ensure_ascii=False))
        if i % 5 == 0 or i == len(p["questions"]):
            reste = (len(p["questions"]) - i) * (time.time() - t0) / max(i - len(faites), 1)
            print(f"  {i}/{len(p['questions'])} — reste ~{reste/60:.0f} min", flush=True)

    vides = sum(1 for r in out if not r["text"].strip())
    print(f"### {nom} FINI : {len(out)} reponses, {vides} vides, "
          f"{(time.time()-t0)/60:.0f} min", flush=True)
    print(f"-> {cible}")


if __name__ == "__main__":
    main()
