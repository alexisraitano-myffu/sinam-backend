"""
Le jeton d'accès : il n'y a plus de repli « pas de jeton, pas
d'authentification ».

C'est ce repli qui a laissé un backend servir toute une mémoire au Wi-Fi d'un
appartement. Les tests d'ici tiennent les trois propriétés qui le remplacent :
un jeton existe toujours, celui déjà posé est relu et non remplacé (sinon
chaque redémarrage désappaire les clients), et le mode ouvert doit être demandé
explicitement. Ni réseau, ni clé d'API, ni vraie base.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def guarded_client(isolated_db, monkeypatch):
    """Un backend sans rien de configuré : ni jeton, ni mode développement."""
    monkeypatch.delenv("SYNAPSE_API_TOKEN", raising=False)
    monkeypatch.delenv("SYNAPSE_DEV_NO_AUTH", raising=False)
    from fastapi.testclient import TestClient

    from api.access import _cache
    from api.app import app
    _cache.clear()
    return TestClient(app)


def test_a_backend_without_a_token_is_not_open(guarded_client, tmp_path):
    """Le cas de la fuite : rien de configuré, et le backend servait tout."""
    assert guarded_client.get("/feed").status_code == 401

    token = (tmp_path / "api_token").read_text(encoding="utf-8").strip()
    assert token
    assert guarded_client.get(
        "/feed", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_the_token_file_is_private_and_reused_not_regenerated(isolated_db, tmp_path,
                                                              monkeypatch):
    """Le piège : refabriquer un jeton à chaque démarrage désappairerait
    silencieusement tous les clients déjà configurés."""
    monkeypatch.delenv("SYNAPSE_API_TOKEN", raising=False)
    monkeypatch.delenv("SYNAPSE_DEV_NO_AUTH", raising=False)
    from api import access
    access._cache.clear()

    first = access.resolve_token()
    mode = (tmp_path / "api_token").stat().st_mode & 0o777
    assert mode == 0o600, f"jeton lisible par d'autres : {oct(mode)}"

    access._cache.clear()          # comme un redémarrage du backend
    assert access.resolve_token() == first


def test_an_environment_token_wins_over_the_file(isolated_db, monkeypatch):
    from api import access
    access._cache.clear()
    monkeypatch.delenv("SYNAPSE_DEV_NO_AUTH", raising=False)
    monkeypatch.setenv("SYNAPSE_API_TOKEN", "posé-par-le-launchagent")
    assert access.resolve_token() == "posé-par-le-launchagent"


def test_open_mode_must_be_asked_for_explicitly(isolated_db, monkeypatch):
    from api import access
    access._cache.clear()
    monkeypatch.delenv("SYNAPSE_API_TOKEN", raising=False)
    monkeypatch.setenv("SYNAPSE_DEV_NO_AUTH", "1")
    assert access.resolve_token() is None

    # Et un jeton posé dans l'environnement l'emporte sur le drapeau : un test
    # qui veut vraiment de l'authentification en a.
    monkeypatch.setenv("SYNAPSE_API_TOKEN", "je-veux-de-l-auth")
    assert access.resolve_token() == "je-veux-de-l-auth"


def test_startup_shouts_when_open_mode_serves_the_network(isolated_db, monkeypatch, caplog):
    import logging

    from api import access
    monkeypatch.setenv("SYNAPSE_DEV_NO_AUTH", "1")

    with caplog.at_level(logging.WARNING, logger="api.access"):
        access.warn_if_open("127.0.0.1")
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="api.access"):
        access.warn_if_open("0.0.0.0")
    assert [r for r in caplog.records if r.levelno >= logging.ERROR], \
        "écouter le réseau sans authentification doit crier"
