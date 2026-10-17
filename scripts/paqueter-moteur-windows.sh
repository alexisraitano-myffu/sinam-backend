#!/usr/bin/env bash
# Prépare les trois archives du moteur local WINDOWS et leur manifeste, prêts à
# déposer sur R2 (`moteur-local/windows-x64/` dans le seau des téléchargements).
# Le pendant de `paqueter-moteur.sh` (Mac), et rien n'est compilé ici : tout se
# fait depuis un Mac ou un Linux.
#
#   scripts/paqueter-moteur-windows.sh <version> [adaptateur.gguf]
#
# Sortie : dist/moteur-local/windows-x64/<version>/{moteur,modele,adaptateur}.tar
#          + manifeste.json
#
# Tout est épinglé : le binaire llama.cpp, les poids GGUF, et donc la mesure
# `lora-60-llamacpp` (scripts/parity/baselines/). Changer l'un, c'est remesurer.
#
# L'adaptateur est celui que sort `scripts/entrainement/pod/vers_gguf_adaptateur.py`.
# Sans argument, on reprend celui du moteur Windows déjà publié, vérifié contre
# l'empreinte du manifeste en ligne.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:?version, ex. 1}"
ADAPTATEUR="${2:-}"
LLAMACPP_BUILD="b11712"
LLAMACPP_ZIP="llama-$LLAMACPP_BUILD-bin-win-vulkan-x64.zip"
LLAMACPP_SHA="7b80950ca99093f5a7b6d9ce2e2d52c5fa650f5fd3a583b1ad000dbd38ce6085"
MODELE_REPO="unsloth/Qwen3.5-4B-GGUF"
MODELE_REVISION="e87f176479d0855a907a41277aca2f8ee7a09523"
MODELE_FICHIER="Qwen3.5-4B-Q4_K_M.gguf"
MODELE_SHA="00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
SEAU="https://pub-91e19c4a15ec4d9ab1a26673a2b7c0ce.r2.dev/moteur-local"
BASE_URL="$SEAU/windows-x64/$VERSION"
CACHE="build/moteur-windows-cache"

verifier() {  # <fichier> <sha256>
    echo "$2  $1" | shasum -a 256 -c - >/dev/null || { echo "✘ empreinte fausse : $1" >&2; exit 1; }
}

SORTIE="dist/moteur-local/windows-x64/$VERSION"
rm -rf "$SORTIE" build/moteur-windows; mkdir -p "$SORTIE" "$CACHE" build/moteur-windows/sinam-moteur

echo "▸ moteur (llama.cpp $LLAMACPP_BUILD, Vulkan avec repli processeur)"
# Vulkan parce que c'est le seul GPU commun aux cartes NVIDIA, AMD et Intel ;
# la construction embarque aussi les moteurs processeur (ggml-cpu-*.dll), choisis
# au lancement selon la puce. Une machine sans GPU utilisable trie donc quand même.
[ -f "$CACHE/$LLAMACPP_ZIP" ] || curl -fL --retry 3 -o "$CACHE/$LLAMACPP_ZIP" \
    "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMACPP_BUILD/$LLAMACPP_ZIP"
verifier "$CACHE/$LLAMACPP_ZIP" "$LLAMACPP_SHA"
unzip -q "$CACHE/$LLAMACPP_ZIP" -d build/moteur-windows/sinam-moteur
[ -f build/moteur-windows/sinam-moteur/llama-server.exe ] || { echo "✘ llama-server.exe absent du zip" >&2; exit 1; }
cp scripts/moteur-local/qwen35.jinja scripts/moteur-local/LICENSE-llama.cpp.txt build/moteur-windows/sinam-moteur/
tar -czf "$SORTIE/moteur.tar" -C build/moteur-windows sinam-moteur

echo "▸ modèle ($MODELE_REPO @ ${MODELE_REVISION:0:8})"
# MODELE_GGUF évite de retélécharger 2,7 Go quand on les a déjà, vérifiés pareil.
GGUF="${MODELE_GGUF:-$CACHE/$MODELE_FICHIER}"
[ -f "$GGUF" ] || curl -fL --retry 3 -o "$GGUF" \
    "https://huggingface.co/$MODELE_REPO/resolve/$MODELE_REVISION/$MODELE_FICHIER"
verifier "$GGUF" "$MODELE_SHA"
mkdir -p build/moteur-windows/modele
cp scripts/moteur-local/LICENSE-Qwen3.5.txt build/moteur-windows/modele/
cp scripts/moteur-local/NOTICE-modele-windows.txt build/moteur-windows/modele/NOTICE-modele.txt
# Le nom attendu par moteur_local._commande ; -h suit un lien éventuel. Pas de
# compression : des poids quantifiés ne se compressent pas.
ln -sf "$(cd "$(dirname "$GGUF")" && pwd)/$(basename "$GGUF")" build/moteur-windows/modele/modele.gguf
tar -chf "$SORTIE/modele.tar" -C build/moteur-windows/modele modele.gguf LICENSE-Qwen3.5.txt NOTICE-modele.txt

echo "▸ adaptateur"
if [ -z "$ADAPTATEUR" ]; then
    echo "   reprise de celui du moteur Windows publié"
    read -r URL_ADA SHA_ADA < <(curl -fsSL "$SEAU/manifeste-windows-x64.json" | python3 -c \
        "import json,sys; f=[f for f in json.load(sys.stdin)['fichiers'] if f['role']=='adaptateur'][0]; print(f['url'], f['sha256'])")
    curl -fL --retry 3 -o "$SORTIE/adaptateur.tar" "$URL_ADA"
    verifier "$SORTIE/adaptateur.tar" "$SHA_ADA"
else
    # Un adaptateur qui charge et ne change rien passe partout sans bruit : on
    # vérifie au moins qu'il porte des tenseurs LoRA.
    python3 - "$ADAPTATEUR" <<'PY'
import struct, sys
with open(sys.argv[1], "rb") as f:
    magie, _, n = f.read(4), f.read(4), struct.unpack("<Q", f.read(8))[0]
if magie != b"GGUF" or n == 0:
    sys.exit(f"✘ {sys.argv[1]} n'est pas un adaptateur GGUF ({magie!r}, {n} tenseurs)")
print(f"   {n} tenseurs")
PY
    mkdir -p build/moteur-windows/adaptateur
    cp "$ADAPTATEUR" build/moteur-windows/adaptateur/adaptateur.gguf
    tar -cf "$SORTIE/adaptateur.tar" -C build/moteur-windows/adaptateur adaptateur.gguf
fi

echo "▸ manifeste"
python3 - "$SORTIE" "$VERSION" "$BASE_URL" <<'PY'
import hashlib, json, os, sys
sortie, version, base = sys.argv[1:4]
fichiers = []
for role in ("moteur", "modele", "adaptateur"):
    p = os.path.join(sortie, f"{role}.tar")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    fichiers.append({"role": role, "url": f"{base}/{role}.tar",
                     "taille": os.path.getsize(p), "sha256": h.hexdigest()})
json.dump({"version": f"windows-x64-{version}", "fichiers": fichiers},
          open(os.path.join(sortie, "manifeste.json"), "w"), indent=2)
print(f"   {sum(f['taille'] for f in fichiers) / 1e9:.2f} Go au total")
PY
echo "✔ $SORTIE"
cat <<FIN

Dépôt sur R2, dans cet ordre (le manifeste EN DERNIER : il annonce des
fichiers, qui doivent déjà être là) :
  1. les trois .tar sous moteur-local/windows-x64/$VERSION/
  2. $SORTIE/manifeste.json sous moteur-local/manifeste-windows-x64.json
Le manifeste Mac (moteur-local/manifeste.json) n'est pas concerné.
FIN
