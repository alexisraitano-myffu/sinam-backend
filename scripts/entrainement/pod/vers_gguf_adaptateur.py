"""Porter l'adaptateur MLX vers ce que llama.cpp sait lire, pour le moteur Windows.

Le chemin inverse de `vers_mlx_adaptateur.py`, puis le convertisseur officiel :

    mlx (adapters.safetensors)  ->  peft  ->  GGUF LoRA (convert_lora_to_gguf.py)

On repasse par peft plutôt que d'écrire le GGUF à la main : c'est le format que
lit le convertisseur de llama.cpp, et c'est lui qui connaît les noms GGUF de
Qwen 3.5 (`blk.N.attn_q`, `blk.N.ffn_down`…). Les deux transformations inverses
sont celles que documente `vers_mlx_adaptateur.py` : les noms, et la
transposition des deux matrices.

    python vers_gguf_adaptateur.py <adaptateur mlx> <sortie.gguf> <llama.cpp> <base hf>

`<base hf>` est un dossier contenant au moins `config.json` et le tokenizer de
`Qwen/Qwen3.5-4B`. Le convertisseur a besoin de torch : le lancer depuis un
environnement à part, pas depuis le .venv du backend.

LE CONTRÔLE QUI COMPTE n'est pas ici : un adaptateur GGUF peut se charger et ne
rien changer. `mesurer_llamacpp.py` est précédé, dans la passe du pod, d'une
comparaison avec et sans adaptateur sur les mêmes questions.
"""
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
from safetensors import safe_open
from safetensors.numpy import save_file


def vers_peft(source: Path, cible: Path) -> dict:
    cfg = json.loads((source / "adapter_config.json").read_text())
    lp = cfg["lora_parameters"]
    r = lp["rank"]
    alpha = lp["scale"] * r
    f = safe_open(str(source / "adapters.safetensors"), "numpy")
    poids, modules = {}, Counter()
    for cle in f.keys():
        # language_model.model.layers.7.self_attn.q_proj.lora_a
        reste = cle.split(".layers.", 1)[1]
        num, reste = reste.split(".", 1)
        mod, ab = reste.rsplit(".lora_", 1)
        # (entrée, r) -> (r, entrée) et (r, sortie) -> (sortie, r)
        poids[f"base_model.model.model.language_model.layers.{num}.{mod}"
              f".lora_{ab.upper()}.weight"] = np.ascontiguousarray(f.get_tensor(cle).T)
        modules[mod] += 1
    cible.mkdir(parents=True, exist_ok=True)
    save_file(poids, str(cible / "adapter_model.safetensors"))
    (cible / "adapter_config.json").write_text(json.dumps({
        "peft_type": "LORA", "r": r, "lora_alpha": alpha, "lora_dropout": 0.0,
        "bias": "none", "task_type": "CAUSAL_LM",
        "base_model_name_or_path": "Qwen/Qwen3.5-4B",
        "target_modules": sorted({m.split(".")[-1] for m in lp["keys"]}),
    }, indent=1))
    return {"tenseurs": len(poids), "r": r, "alpha": alpha, "modules": dict(modules)}


def main():
    src, sortie, llama, base = (Path(a) for a in sys.argv[1:5])
    with tempfile.TemporaryDirectory() as tmp:
        info = vers_peft(src, Path(tmp))
        print(f"  peft : {info['tenseurs']} tenseurs, r {info['r']}, alpha {info['alpha']}")
        subprocess.run([sys.executable, str(llama / "convert_lora_to_gguf.py"),
                        "--base", str(base), "--outtype", "f16",
                        "--outfile", str(sortie), tmp], check=True)

    # Tout tenseur de l'adaptateur doit avoir trouvé un poids GGUF : un nom non
    # reconnu ferait échouer le convertisseur, mais on recompte quand même.
    from gguf import GGUFReader
    n = len(GGUFReader(str(sortie)).tensors)
    if n != info["tenseurs"]:
        sys.exit(f"ARRÊT : {n} tenseurs dans le GGUF pour {info['tenseurs']} dans l'adaptateur")
    print(f"  -> {sortie} ({n} tenseurs)")


if __name__ == "__main__":
    main()
