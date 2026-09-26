"""
Le mode local : un appel de modèle part au serveur local, et jamais ailleurs.

La promesse du mode local est « rien ne sort ». Elle se casse sans bruit : un
appelant oublié qui construit son propre client Anthropic continue de marcher,
et la fuite ne se voit dans aucun résultat. D'où deux gardes : le verrou du
client Anthropic, et un vrai appel du core qu'on regarde arriver sur un faux
serveur compatible OpenAI. Aucune clé, aucun réseau hors boucle locale.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Un config.json jetable, et aucune clé venue de l'environnement."""
    import config_store
    monkeypatch.setattr(config_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return config_store


def test_absent_mode_is_cloud(config_home):
    """Une installation d'avant le mode local garde son comportement."""
    assert config_home.get_llm_mode() == "cloud"


def test_a_damaged_mode_never_reads_as_local(config_home):
    config_home._save({"llm_mode": "LOCAL "})
    assert config_home.get_llm_mode() == "cloud"


def test_unknown_mode_is_refused(config_home):
    with pytest.raises(ValueError):
        config_home.set_llm_mode("gemma")


def test_local_needs_no_key(config_home):
    import llm_target
    config_home.set_llm_mode("local")
    t = llm_target.resolve()
    assert t.is_local and t.provider == "openai"
    assert t.api_key == "" and t.fuel_token is None
    assert t.base_url.startswith("http://127.0.0.1:")


def test_local_ignores_a_stored_key(config_home):
    """Passé du cloud au local, la clé reste enregistrée : elle ne doit plus
    servir à rien."""
    import llm_target
    config_home.set_anthropic_key("sk-ant-pas-une-vraie")
    config_home.set_llm_mode("local")
    assert llm_target.resolve().api_key == ""


def test_cloud_without_key_still_raises(config_home):
    import llm_target
    with pytest.raises(EnvironmentError):
        llm_target.resolve()


def test_anthropic_client_refuses_in_local_mode(config_home):
    """Le verrou : Batch API, noms de zones de la carte, et tout appelant futur
    passent par ce client."""
    import anthropic_client
    config_home.set_anthropic_key("sk-ant-pas-une-vraie")
    config_home.set_llm_mode("local")
    with pytest.raises(EnvironmentError):
        anthropic_client.get_client()
    assert anthropic_client.get_client_or_none() is None


def test_core_rejects_an_unknown_provider(isolated_db):
    """Le binding refuse un nom inconnu au lieu de retomber sur Anthropic, ce
    qui enverrait en silence les captures d'un utilisateur « 100 % local »
    dans le cloud."""
    from core_store import get_brain
    with pytest.raises(ValueError, match="provider inconnu"):
        get_brain().summarize_digest(
            "{}", "m", "", "/nulle-part", "2026-07-13", provider="gemma")


class _Recorder(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):  # noqa: N802 — la sonde de disponibilité du moteur
        self.send_response(200)
        self.send_header("content-length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        type(self).seen.append((self.path, body))
        out = json.dumps({"choices": [{
            "message": {"content": "Un résumé venu du modèle local."},
            "finish_reason": "stop",
        }]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_local_call_reaches_the_local_server(config_home, isolated_db, monkeypatch):
    """Un vrai appel du core, en mode local, arrive au serveur de la boucle
    locale dans le dialecte OpenAI, sans clé."""
    _Recorder.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("SYNAPSE_LOCAL_LLM_PORT", str(srv.server_port))
        config_home.set_llm_mode("local")

        from dream_cycle import digest
        conn = digest.get_connection()
        try:
            week = digest.gather_week(conn)
        finally:
            conn.close()
        text = digest.summarize_digest(week)

        assert "modèle local" in text
        assert _Recorder.seen, "aucune requête n'a atteint le serveur local"
        path, body = _Recorder.seen[0]
        assert path == "/v1/chat/completions"
        assert body["messages"][0]["role"] == "system"
    finally:
        srv.shutdown()
