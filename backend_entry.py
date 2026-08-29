"""Entry point for the PyInstaller-bundled backend.

Runs uvicorn on 127.0.0.1:8765 so the desktop app can talk to the LaunchAgent
without exposing the API to the LAN.

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
    import uvicorn

    from api.app import app

    port = int(os.environ.get("SYNAPSE_PORT", "8765"))
    host = os.environ.get("SYNAPSE_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
