"""Entry point for the PyInstaller-bundled backend.

Délègue le service à `api.__main__.serve` : DEUX écoutes, le clair sur la
boucle locale (l'app desktop lui parle) et le TLS sur 8443 (les téléphones
épinglent le certificat). Historiquement ce fichier faisait un `uvicorn.run`
à plat sans TLS : le durcissement du lien local ne touchait donc que le chemin
`python -m api`, jamais le binaire que la prod et les testeurs exécutent. Le
partage ferme ce trou.

Le défaut mDNS posé plus bas ne décrit PAS ce que font les installs réelles :
l'installeur pose `SYNAPSE_DISABLE_MDNS` à la chaîne vide dans le LaunchAgent,
ce qui l'écrase et rallume l'annonce. C'est voulu, c'est ce qui permet au
téléphone de trouver l'ordinateur sans qu'on tape une IP. Ce qui cloisonne deux
mémoires voisines n'est pas l'invisibilité sur le réseau, c'est l'identifiant
d'espace comparé avant toute fusion. Le défaut ci-dessous ne vaut donc que pour
le binaire lancé à la main, sans l'environnement de l'installeur.
"""
import os
import sys
from pathlib import Path

# When frozen by PyInstaller, sys._MEIPASS points at the bundle's tmp dir.
# Add the bundle root and the regular project root to sys.path so imports work
# both in the binary and during `python backend_entry.py`.
if getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(sys._MEIPASS)))  # noqa: SLF001
    # Défaut prudent du binaire lancé sans environnement ; l'installeur
    # l'écrase délibérément (voir l'en-tête du module).
    os.environ.setdefault("SYNAPSE_DISABLE_MDNS", "1")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _sync_bundled_prompts() -> None:
    """The core reads its prompts (classifier, digest, …) as DATA from
    SYNAPSE_HOME/prompts at runtime. On tester machines nothing else deploys
    them, so the bundle ships a prompts/ dir (copied by build-backend.sh next
    to the executable) and we mirror it on every start: the deployed prompts
    always match the shipped brain. SYNAPSE_PROMPTS_DIR opts out entirely."""
    if not getattr(sys, "frozen", False) or os.environ.get("SYNAPSE_PROMPTS_DIR"):
        return
    source = Path(sys.executable).resolve().parent / "prompts"
    if not source.is_dir():
        return
    target = Path(os.environ.get("SYNAPSE_HOME", Path.home() / ".synapse")) / "prompts"
    target.mkdir(parents=True, exist_ok=True)
    for f in source.iterdir():
        if f.is_file():
            (target / f.name).write_bytes(f.read_bytes())


_sync_bundled_prompts()


def main() -> None:
    import asyncio

    from api.__main__ import serve

    asyncio.run(serve())


if __name__ == "__main__":
    main()
