"""Les 186 questions du harnais, jouées par le serveur llama.cpp du moteur Windows.

Même rôle et même format de sortie que `mesurer_mlx.py`, donc le fichier
produit se note avec le VRAI `score.py` par le provider `rejeu`. La différence
voulue : on passe par `llama-server`, c'est-à-dire par le binaire et les
réglages qu'on livre, et non par une bibliothèque appelée à côté. Ce qu'on
mesure est ce que reçoit la personne qui installe.

    llama-server -m <modele.gguf> --lora <adaptateur.gguf> --port 8767 \
        <moteur_local.REGLAGES_LLAMACPP>
    python mesurer_llamacpp.py <nom> [http://127.0.0.1:8767]

Reprend là où il s'est arrêté, comme la mesure MLX.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent


def demander(base: str, systeme: str, user: str, max_tokens: int) -> dict:
    corps = {
        "model": "default_model",
        "messages": [{"role": "system", "content": systeme},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        # Redit à chaque requête, en plus du réglage du serveur : une réflexion
        # ouverte servirait un autre modèle que celui qu'on a entraîné.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(f"{base}/v1/chat/completions",
                                 data=json.dumps(corps).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as rep:
        return json.loads(rep.read())


def main():
    nom = sys.argv[1] if len(sys.argv) > 1 else "lora-60-llamacpp"
    base = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8767").rstrip("/")

    p = json.loads((RACINE / "questions.json").read_text())
    cible = RACINE / "reponses" / f"{nom}.json"
    cible.parent.mkdir(parents=True, exist_ok=True)
    faites = {}
    if cible.is_file():
        faites = {r["cle"]: r for r in json.loads(cible.read_text())}
        print(f"reprise : {len(faites)} reponses deja la", flush=True)

    print(f"### {nom} ({base})", flush=True)
    out, t0 = [], time.time()
    for i, q in enumerate(p["questions"], 1):
        if q["cle"] in faites:
            out.append(faites[q["cle"]]); continue
        t1 = time.time()
        r = demander(base, p["systemes"][q["sys"]], q["user"], p["max_tokens"])
        choix = r["choices"][0]
        usage = r.get("usage") or {}
        out.append({"cle": q["cle"], "text": choix["message"].get("content") or "",
                    "stop_reason": "max_tokens" if choix.get("finish_reason") == "length" else "stop",
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "latency_s": round(time.time() - t1, 1)})
        cible.write_text(json.dumps(out, ensure_ascii=False))
        if i % 5 == 0 or i == len(p["questions"]):
            reste = (len(p["questions"]) - i) * (time.time() - t0) / max(i - len(faites), 1)
            print(f"  {i}/{len(p['questions'])} : reste ~{reste/60:.0f} min", flush=True)

    vides = sum(1 for r in out if not r["text"].strip())
    print(f"### {nom} FINI : {len(out)} reponses, {vides} vides, "
          f"{(time.time()-t0)/60:.0f} min", flush=True)
    print(f"-> {cible}")


if __name__ == "__main__":
    main()
