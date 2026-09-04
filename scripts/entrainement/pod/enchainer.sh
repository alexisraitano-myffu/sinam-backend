#!/usr/bin/env bash
# L'enchainement complet, detache. Trois choses dans cet ordre, et le NU
# D'ABORD : c'est le repere, et il doit etre mesure le meme jour, avec la meme
# quantification et le meme harnais que l'entraine. Comparer a un chiffre plus
# ancien a deja coute quatre cas d'illusion le 03/09.
set -uo pipefail
cd /workspace
export QUANT="${QUANT:-nf4}"

echo "=== $(date -u +%H:%M:%S) 1/3 mesure du NU ($QUANT) ==="
python -u mesurer.py "Qwen/Qwen3.5-4B" "nu-$QUANT" > nu.log 2>&1 \
  || { echo "ECHEC: mesure du nu"; exit 1; }

echo "=== $(date -u +%H:%M:%S) 2/3 entrainement ==="
python -u entrainer.py > entrainement.log 2>&1 &
ENTR=$!
while [ ! -d adaptateur/checkpoint-60 ]; do
  kill -0 $ENTR 2>/dev/null || { echo "ECHEC: entrainement mort avant le point 60"; exit 1; }
  sleep 30
done
sleep 20                       # laisser la sauvegarde se terminer
kill $ENTR 2>/dev/null; sleep 5
echo "=== $(date -u +%H:%M:%S) arrete au point 60 ==="

echo "=== $(date -u +%H:%M:%S) 3/3 mesure de L'ENTRAINE ==="
python -u mesurer.py "Qwen/Qwen3.5-4B" "lora-60-$QUANT" \
  /workspace/adaptateur/checkpoint-60 > entraine.log 2>&1 \
  || { echo "ECHEC: mesure de l'entraine"; exit 1; }

echo "=== $(date -u +%H:%M:%S) FINI ==="
touch /workspace/FINI
