"""Run the sinam API: `python -m api`.

Deux écoutes sur le même processus et la même application : le clair sur 8000,
le chiffré sur 8443. C'est délibéré et c'est temporaire.

Un lien local passe de clair à chiffré sans fenêtre où quelqu'un se retrouve
coupé : tant qu'un appareil de la beta n'a pas la mise à jour qui lui apprend
à épingler le certificat, il continue de parler en clair sur 8000, pendant
qu'un appareil à jour parle déjà en 8443. Le jour où plus personne n'est resté
en arrière, on ferme 8000 et il ne reste qu'une écoute.

La durée de vie de l'application (mDNS, boucle de sync, planificateur) est
portée par la PREMIÈRE écoute seulement : deux fois le même cycle de vie
voudrait dire deux annonces mDNS et deux boucles de tirage.
"""

import asyncio
import logging
import os

import uvicorn

log = logging.getLogger(__name__)


def _config(app, host: str, port: int, *, lifespan: str, ssl: dict | None = None):
    return uvicorn.Config(app, host=host, port=port, log_level="info",
                          lifespan=lifespan, **(ssl or {}))


async def serve() -> None:
    """Les deux écoutes (clair loopback + TLS 8443). Partagée par les DEUX
    entrypoints : `python -m api` (dev) et `backend_entry.py` (binaire bundlé,
    ce que la prod et les testeurs exécutent). Sans ce partage, un durcissement
    posé ici ne touche aucun runtime réel — c'est exactement ce qui était
    arrivé au TLS du lien local.

    Les noms d'env sont lus dans les deux conventions : `SYNAPSE_API_HOST/PORT`
    (serveur LAN) et, en repli, `SYNAPSE_HOST/PORT` (que le LaunchAgent du
    bundle pose). Le clair retombe de toute façon sur la boucle locale dès
    qu'un certificat existe, quel que soit l'hôte demandé."""
    from api.app import app
    from api.tls import ensure_cert, tls_port

    host = (os.environ.get("SYNAPSE_API_HOST")
            or os.environ.get("SYNAPSE_HOST") or "0.0.0.0")
    port = int(os.environ.get("SYNAPSE_API_PORT")
               or os.environ.get("SYNAPSE_PORT") or "8000")

    pair = None if os.environ.get("SYNAPSE_TLS_DISABLE") else ensure_cert()
    if pair is None:
        log.warning("pas de TLS : le lien local reste en clair sur %s", host)

    # Le clair n'écoute plus le réseau dès que le chiffré est disponible : il ne
    # sert plus qu'à l'app desktop, qui parle à sa boucle locale. Un appareil du
    # réseau n'a donc plus qu'un seul chemin, le chiffré, et ce qui n'a pas
    # migré se voit tout de suite au lieu de continuer en clair sans bruit.
    # Sans TLS on retombe sur l'ancien comportement plutôt que de couper tout
    # le monde, et le log le dit.
    clear_host = os.environ.get(
        "SYNAPSE_API_CLEARTEXT_HOST", "127.0.0.1" if pair is not None else host)
    configs = [_config(app, clear_host, port, lifespan="on")]

    if pair is not None:
        cert, key = pair
        configs.append(_config(
            app, host, tls_port(), lifespan="off",
            ssl={"ssl_certfile": str(cert), "ssl_keyfile": str(key)},
        ))
        log.info("clair sur %s:%d (boucle locale), chiffré sur %s:%d",
                 clear_host, port, host, tls_port())

    servers = [uvicorn.Server(c) for c in configs]
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(serve())
