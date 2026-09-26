"""
Le moteur local : l'installation, et le moteur lancé le temps d'un cycle.

Tout passe par de vrais processus et un vrai serveur HTTP sur la boucle locale,
avec des archives minuscules à la place des 3 Go. Ce qui compte ici n'est pas
le modèle, c'est ce que l'utilisateur ne voit pas : un fichier corrompu qui
passerait pour installé, ou un moteur qui resterait chargé après le cycle.
"""

import hashlib
import io
import json
import socket
import sys
import tarfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Un faux moteur : un serveur qui répond à la sonde, lancé comme le vrai
# (même chemin, mêmes arguments). `env` et pas sys.executable : un chemin avec
# une espace (« Pro AR ») casse la ligne shebang.
FAUX_MOTEUR = f"""#!/usr/bin/env python3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
port = int(sys.argv[sys.argv.index("--port") + 1])
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("content-length", "2")
        self.end_headers(); self.wfile.write(b"{{}}")
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


def _tar(fichiers: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for nom, contenu in fichiers.items():
            info = tarfile.TarInfo(nom)
            info.size = len(contenu)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(contenu))
    return buf.getvalue()


@pytest.fixture
def depot(tmp_path, monkeypatch):
    """Un faux seau R2 servi en HTTP, et un SYNAPSE_HOME jetable."""
    import moteur_local
    racine = tmp_path / "r2"
    racine.mkdir()
    srv = ThreadingHTTPServer(("127.0.0.1", 0),
                              partial(SimpleHTTPRequestHandler, directory=str(racine)))
    srv.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"

    archives = {
        "moteur": _tar({"sinam-moteur/sinam-moteur": FAUX_MOTEUR.encode()}),
        "modele": _tar({"config.json": b"{}"}),
        "adaptateur": _tar({"adapter_config.json": b"{}"}),
    }

    def publier(corrompre=None):
        fichiers = []
        for role, octets in archives.items():
            (racine / f"{role}.tar").write_bytes(octets)
            somme = hashlib.sha256(octets).hexdigest()
            if role == corrompre:
                somme = "0" * 64
            fichiers.append({"role": role, "url": f"{base}/{role}.tar",
                             "taille": len(octets), "sha256": somme})
        (racine / "manifeste.json").write_text(json.dumps({"version": "t1", "fichiers": fichiers}))

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SYNAPSE_HOME", str(home))
    monkeypatch.setattr(moteur_local, "MANIFESTE_URL", f"{base}/manifeste.json")
    monkeypatch.setattr(moteur_local, "compatibilite", lambda: None)
    moteur_local._poser(etat=None)
    yield publier
    srv.shutdown()


def _attendre_fin(moteur_local):
    for _ in range(100):
        if moteur_local.etat()["etat"] != "telechargement":
            return moteur_local.etat()
        time.sleep(0.05)
    raise AssertionError("installation jamais terminée")


def test_install_then_uninstall(depot):
    import moteur_local
    depot()
    assert moteur_local.etat()["etat"] == "absent"
    moteur_local.installer_en_fond()
    e = _attendre_fin(moteur_local)
    assert e["etat"] == "installe" and e["version"] == "t1"
    assert (moteur_local.dossier() / "moteur" / "sinam-moteur" / "sinam-moteur").exists()
    # aucune archive ni dossier temporaire ne reste derrière
    assert sorted(p.name for p in moteur_local.dossier().iterdir()) == \
        ["adaptateur", "installe.json", "modele", "moteur"]
    moteur_local.desinstaller()
    assert moteur_local.etat()["etat"] == "absent"


def test_a_wrong_checksum_is_never_installed(depot):
    """Un fichier corrompu ou remplacé en route ne doit pas passer pour
    installé : l'app proposerait le tri local sur un moteur cassé."""
    import moteur_local
    depot(corrompre="modele")
    moteur_local.installer_en_fond()
    e = _attendre_fin(moteur_local)
    assert e["etat"] == "erreur" and "empreinte" in e["erreur"]
    assert not moteur_local.est_installe()


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_session_starts_then_stops_the_engine(depot, monkeypatch):
    """Le moteur ne vit que le temps de la session : ~3 Go rendus après."""
    import moteur_local
    depot()
    moteur_local.installer_en_fond()
    _attendre_fin(moteur_local)
    port = _port_libre()
    monkeypatch.setenv("SYNAPSE_LOCAL_LLM_PORT", str(port))
    base = f"http://127.0.0.1:{port}"

    with moteur_local.session():
        assert moteur_local._pret(base)
        with moteur_local.session():      # réentrant : le digest pendant un cycle
            assert moteur_local._pret(base)
        assert moteur_local._pret(base)   # la session intérieure n'a rien arrêté
    assert not moteur_local._pret(base)


def test_session_without_engine_is_a_connection_error(depot, monkeypatch):
    """Le cycle traite ConnectionError comme une coupure : captures gardées
    en file, et pas de repli vers le cloud."""
    import moteur_local
    monkeypatch.setenv("SYNAPSE_LOCAL_LLM_PORT", str(_port_libre()))
    with pytest.raises(ConnectionError):
        with moteur_local.session():
            pass
