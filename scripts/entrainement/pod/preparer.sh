#!/usr/bin/env bash
# Sans vLLM. Il ne servait qu'a l'inference rapide, et il est pris entre deux
# contraintes qui s'excluent : le pilote de ces hotes est en CUDA 12.8, ce qui
# force un vLLM ancien, qui epingle un transformers qui ne connait pas Qwen 3.5.
# transformers genere seul, plus lentement, et l'entrainement n'en a jamais
# eu besoin.
set -euo pipefail
P="pip install -q --break-system-packages"
$P "transformers>=5" peft accelerate bitsandbytes
rm -rf /root/.cache/pip          # 5 Go de cache sur 20 de disque
python - <<'PY'
import torch, transformers, peft, bitsandbytes
from transformers import AutoConfig
print("torch", torch.__version__, "| cuda", torch.cuda.is_available(), "|",
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-")
print("transformers", transformers.__version__, "| peft", peft.__version__,
      "| bitsandbytes", bitsandbytes.__version__)
print("architecture :", AutoConfig.from_pretrained("Qwen/Qwen3.5-4B").model_type)
PY
echo "### PREPARATION FINIE"
