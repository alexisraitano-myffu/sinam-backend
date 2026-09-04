"""Porter un adaptateur LoRA entraîné avec peft vers ce que mlx-lm sait lire.

Pourquoi ce script existe : l'entraînement tourne sur un GPU loué, donc sous
`peft`, alors que le modèle qui tournera vraiment sur le Mac est servi par
`mlx_lm`. Les deux stockent le MÊME adaptateur sous deux conventions.

Les deux différences, lues dans `mlx_lm/tuner/lora.py` et non devinées :

* les noms. peft écrit `base_model.model.model.layers.N.N.lora_A.weight`,
  mlx-lm attend `model.layers.N.N.lora_a`.
* les transpositions. mlx-lm calcule `delta = (scale * lora_b.T) @ lora_a.T`
  pour un poids de forme (sortie, entrée), donc `lora_a` est (entrée, r) et
  `lora_b` est (r, sortie) : exactement les transposées des matrices peft, qui
  sont (r, entrée) et (sortie, r).

LE PIÈGE, et la raison du contrôle final : `mlx_lm` charge l'adaptateur avec
`load_weights(strict=False)`. Une clé mal nommée n'est pas une erreur, elle est
IGNORÉE. Comme mlx-lm initialise `lora_b` à zéro, un adaptateur qui n'a pas été
chargé est un adaptateur inerte : le modèle répond exactement comme le modèle
nu, sans un mot d'avertissement, et on mesurerait le nu en croyant mesurer
l'entraîné. Le script relit donc les poids DEPUIS LE MODÈLE et refuse de rendre
la main s'ils n'y sont pas.
"""
import json
import sys
from pathlib import Path

import mlx.core as mx
from mlx.utils import tree_flatten
import numpy as np
from safetensors import safe_open
from safetensors.numpy import save_file


def prefixe_du_modele(modele: str) -> str:
    """Ce qui précède `.layers.` dans les noms de poids du modèle MLX.

    Il ne va PAS de soi : Qwen 3.5 4B est servi enveloppé, ses poids
    s'appellent `language_model.model.layers.N...` et non `model.layers.N...`.
    Un préfixe codé en dur produirait exactement l'échec silencieux que le
    contrôle final attrape. On le lit donc dans l'index des poids, sans charger
    le modèle.
    """
    if Path(modele).is_dir():
        chemin = Path(modele)
    else:
        from huggingface_hub import snapshot_download
        chemin = Path(snapshot_download(modele, local_files_only=True))
    index = chemin / "model.safetensors.index.json"
    if index.is_file():
        noms = json.loads(index.read_text())["weight_map"].keys()
    else:
        f = safe_open(str(chemin / "model.safetensors"), "numpy")
        noms = f.keys()
    for n in noms:
        if ".layers." in n:
            return n.split(".layers.")[0] + ".layers."
    sys.exit(f"aucun poids de couche trouvé dans {chemin}")


def convertir(source: Path, cible: Path, prefixe: str) -> dict:
    cfg = json.loads((source / "adapter_config.json").read_text())
    r, alpha = cfg["r"], cfg["lora_alpha"]

    f = safe_open(str(source / "adapter_model.safetensors"), "numpy")
    poids, modules, couches = {}, set(), set()
    for cle in f.keys():
        # base_model.model.model.layers.7.self_attn.q_proj.lora_A.weight
        if ".layers." not in cle:
            sys.exit(f"clé inattendue, conversion abandonnée : {cle}")
        reste = cle.split(".layers.", 1)[1]
        num, reste = reste.split(".", 1)
        mod, ab = reste.rsplit(".lora_", 1)
        lettre = ab[0].lower()
        t = f.get_tensor(cle).astype(np.float32)
        # (r, entrée) -> (entrée, r) et (sortie, r) -> (r, sortie)
        poids[f"{prefixe}{num}.{mod}.lora_{lettre}"] = np.ascontiguousarray(t.T)
        modules.add(mod); couches.add(int(num))

    cible.mkdir(parents=True, exist_ok=True)
    save_file(poids, str(cible / "adapters.safetensors"))
    (cible / "adapter_config.json").write_text(json.dumps({
        "fine_tune_type": "lora",
        "num_layers": max(couches) + 1,
        "lora_parameters": {
            "rank": r, "scale": alpha / r, "dropout": 0.0,
            "keys": sorted(modules),
        },
    }, indent=2))
    return {"tenseurs": len(poids), "couches": len(couches),
            "modules": sorted(modules), "scale": alpha / r}


def controler(modele: str, cible: Path) -> None:
    """Charger pour de vrai, et vérifier que les poids sont ARRIVÉS."""
    from mlx_lm import load
    m, _ = load(modele, adapter_path=str(cible))

    attendus = {}
    f = safe_open(str(cible / "adapters.safetensors"), "numpy")
    for cle in f.keys():
        attendus[cle] = f.get_tensor(cle)

    params = dict(tree_flatten(m.parameters()))
    manquants = [c for c in attendus if c not in params]
    if manquants:
        sys.exit(f"ARRÊT : {len(manquants)} poids LoRA absents du modèle chargé, "
                 f"dont {manquants[:2]}. Les noms ne correspondent pas et "
                 f"load_weights les a ignorés en silence.")

    ecarts = [c for c in attendus
              if not np.allclose(np.array(params[c], copy=False), attendus[c], atol=1e-5)]
    if ecarts:
        sys.exit(f"ARRÊT : {len(ecarts)} poids chargés diffèrent du fichier, "
                 f"dont {ecarts[:2]}.")

    # lora_b vaut zéro à l'initialisation : s'il l'est resté partout, rien
    # n'a été appliqué, même si les noms collent.
    bs = [np.array(params[c], copy=False) for c in attendus if c.endswith("lora_b")]
    non_nuls = sum(1 for b in bs if np.abs(b).max() > 0)
    if non_nuls == 0:
        sys.exit("ARRÊT : tous les lora_b sont nuls, l'adaptateur est inerte.")
    print(f"  contrôle : {len(attendus)} poids présents et identiques au fichier, "
          f"{non_nuls}/{len(bs)} lora_b non nuls")


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    modele = sys.argv[3] if len(sys.argv) > 3 else "mlx-community/Qwen3.5-4B-MLX-4bit"
    prefixe = prefixe_du_modele(modele)
    print(f"  préfixe du modèle : {prefixe}")
    info = convertir(src, dst, prefixe)
    print(f"  converti : {info['tenseurs']} tenseurs, {info['couches']} couches, "
          f"scale {info['scale']}, modules {info['modules']}")
    controler(modele, dst)
    print(f"  -> {dst}")
