#!/usr/bin/env bash
# Prépare les trois archives du moteur local et leur manifeste, prêts à déposer
# sur R2 (`moteur-local/` dans le seau des téléchargements).
#
#   scripts/paqueter-moteur.sh <version>
#
# Sortie : dist/moteur-local/<version>/{moteur,modele,adaptateur}.tar + manifeste.json
#
# Les poids ne sont PAS reconstruits : ce sont ceux du cache Hugging Face, à la
# révision épinglée ci-dessous, c'est-à-dire exactement ceux qu'a lus la mesure
# (`scripts/entrainement/pod/mesurer_mlx.py`). Changer de révision, c'est changer
# de modèle, donc remesurer avant de publier.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:?version, ex. 1}"
MODELE_REPO="mlx-community/Qwen3.5-4B-MLX-4bit"
MODELE_REVISION="32f3e8ecf65426fc3306969496342d504bfa13f3"
ADAPTATEUR="scripts/entrainement/pod/adaptateurs/mlx-60"
BASE_URL="https://pub-91e19c4a15ec4d9ab1a26673a2b7c0ce.r2.dev/moteur-local/$VERSION"

SNAP="$HOME/.cache/huggingface/hub/models--${MODELE_REPO//\//--}/snapshots/$MODELE_REVISION"
[ -f "$SNAP/model.safetensors" ] || { echo "✘ poids absents du cache : $SNAP" >&2; exit 1; }
[ -f "$ADAPTATEUR/adapters.safetensors" ] || { echo "✘ adaptateur absent : $ADAPTATEUR" >&2; exit 1; }

SORTIE="dist/moteur-local/$VERSION"
rm -rf "$SORTIE"; mkdir -p "$SORTIE"

echo "▸ moteur (PyInstaller)"
.venv/bin/pyinstaller --noconfirm --distpath build/moteur-dist --workpath build/moteur-work \
    sinam-moteur.spec > build/moteur-build.log 2>&1 \
    || { echo "✘ PyInstaller, voir build/moteur-build.log" >&2; exit 1; }
# On teste le RÉSULTAT : un binaire qui ne sait même pas afficher son aide ne
# chargera pas de modèle.
build/moteur-dist/sinam-moteur/sinam-moteur --help >/dev/null
# Signature, sur le modèle de sinam-app/scripts/build-dist.sh : du plus profond
# vers l'extérieur (toucher un binaire signé invalide sa signature), les
# .framework en tant que bundles, l'exécutable en dernier avec ses droits.
# Téléchargé par le backend, le moteur ne porte pas l'attribut de quarantaine
# et tournerait non signé ; signé, il se laisse vérifier.
[ -f "$HOME/Apple-signing/notarisation.env" ] && . "$HOME/Apple-signing/notarisation.env"
MOTEUR=build/moteur-dist/sinam-moteur
if [ -n "${SINAM_SIGN_IDENTITY:-}" ]; then
    N=0
    while IFS= read -r -d '' f; do
        case "$f" in *.framework/*) continue ;; esac
        case "$(file -b "$f")" in
            *Mach-O*) codesign --force --timestamp --options runtime \
                          --sign "$SINAM_SIGN_IDENTITY" "$f" 2>/dev/null; N=$((N + 1)) ;;
        esac
    done < <(find "$MOTEUR" -type f -d -print0)
    while IFS= read -r -d '' fw; do
        codesign --force --timestamp --options runtime --sign "$SINAM_SIGN_IDENTITY" "$fw"
        N=$((N + 1))
    done < <(find "$MOTEUR" -type d -name "*.framework" -d -print0)
    codesign --force --timestamp --options runtime \
        --entitlements scripts/moteur-local/moteur.entitlements \
        --sign "$SINAM_SIGN_IDENTITY" "$MOTEUR/sinam-moteur"
    codesign --verify --strict "$MOTEUR/sinam-moteur"
    # Signé, il doit encore savoir démarrer : les droits manquants ne se voient
    # qu'à l'exécution.
    "$MOTEUR/sinam-moteur" --help >/dev/null
    echo "   $N binaires signés, plus l'exécutable"
else
    echo "   ⚠ SINAM_SIGN_IDENTITY absente : moteur NON signé (à ne pas publier tel quel)"
fi
# Compressé, lui : 375 Mo de bibliothèques tombent à ~145.
tar -czf "$SORTIE/moteur.tar" -C build/moteur-dist sinam-moteur

echo "▸ modèle ($MODELE_REPO @ ${MODELE_REVISION:0:8})"
# -h suit les liens du cache (les fichiers y sont des liens vers les blobs).
# Pas de compression : les poids quantifiés ne se compressent pas, et on
# paierait la décompression chez chaque utilisateur pour rien.
tar -chf "$SORTIE/modele.tar" -C "$SNAP" --exclude .gitattributes .
# Apache 2.0 demande que la licence voyage avec les poids qu'on redistribue.
tar -rf "$SORTIE/modele.tar" -C scripts/moteur-local LICENSE-Qwen3.5.txt NOTICE-modele.txt

echo "▸ adaptateur"
tar -cf "$SORTIE/adaptateur.tar" -C "$ADAPTATEUR" adapters.safetensors adapter_config.json

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
json.dump({"version": version, "fichiers": fichiers},
          open(os.path.join(sortie, "manifeste.json"), "w"), indent=2)
print(f"   {sum(f['taille'] for f in fichiers) / 1e9:.2f} Go au total")
PY
echo "✔ $SORTIE"
