"""
Offline tests for the P2P sync transport: /sync/*
endpoints, owner-lock run-guard, peer pull (HTTP stubbed — the "peer" is a
second real core Storage in a temp dir), cursor advance and the
double-routed-rows dedup pass. No network, no Claude API.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client(isolated_db, monkeypatch):
    # Auth coupée EXPLICITEMENT : sans ce drapeau le backend se fabrique un
    # jeton plutôt que de servir ouvert. Un test qui pose SYNAPSE_API_TOKEN
    # rallume l'auth, le jeton d'environnement l'emportant sur le drapeau.
    monkeypatch.delenv("SYNAPSE_API_TOKEN", raising=False)
    monkeypatch.setenv("SYNAPSE_DEV_NO_AUTH", "1")
    monkeypatch.delenv("SYNAPSE_SYNC_PEERS", raising=False)
    from fastapi.testclient import TestClient
    from api.app import app
    return TestClient(app)


def _conn():
    from db import get_connection
    return get_connection()


# ── /sync/changes + /sync/status ─────────────────────────────────────────────

def test_sync_changes_exposes_protocol_v1(client):
    client.post("/capture", json={"id": "cap-1", "content": "note à répliquer"})
    page = client.get("/sync/changes", params={"since": 0, "limit": 10000}).json()
    assert page["protocol"] == 1
    assert page["next"] > 0
    row = next(r for r in page["rows"] if r["t"] == "inbox" and r["pk"] == "cap-1")
    assert row["cols"]["content"]["v"] == "note à répliquer"
    assert "hlc" in row["cols"]["content"]


def test_sync_status_shape(client):
    status = client.get("/sync/status").json()
    assert status["device_id"]
    assert status["journal_seq"] >= 0
    assert status["owner"] is None          # fresh install: nobody owns the cycle
    assert status["is_owner"] is False
    assert status["cursors"] == {}
    assert status["space_id"] is None       # fresh install: no space founded yet


# ── Owner-lock + run-guard ───────────────────────────────────────────────────

def test_owner_implicit_claim_then_guard_blocks_foreign_device(client):
    from api.sync_peers import ensure_cycle_owner
    from core_store import get_store

    # First run on a fresh install: self-claim, then pass.
    ensure_cycle_owner()
    me = get_store().sync_device_id()
    owner = client.get("/sync/owner").json()
    assert owner["owner"]["device_id"] == me
    assert owner["is_owner"] is True
    ensure_cycle_owner()  # still owner → still passes

    # Hand the lock to another device: the guard must now refuse, and the
    # cycle endpoint must 409 before doing any work.
    claimed = client.put("/sync/owner", json={"device_id": "other-mac"}).json()
    assert claimed["owner"]["device_id"] == "other-mac"
    assert claimed["owner"]["epoch"] == 2
    with pytest.raises(Exception) as exc:
        ensure_cycle_owner()
    assert "409" in str(getattr(exc.value, "status_code", "")) or \
        getattr(exc.value, "status_code", None) == 409
    r = client.post("/dream-cycle/run")
    assert r.status_code == 409
    # the guard's detail is structured so clients render a human
    # message (code + owner identity + epoch).
    detail = r.json()["detail"]
    assert detail["code"] == "not_cycle_owner"
    assert detail["owner_device_id"] == "other-mac"
    assert detail["epoch"] == 2
    assert "other-mac" in detail["message"]

    # Claiming it back (epoch 3) reopens the cycle.
    client.put("/sync/owner", json={})
    ensure_cycle_owner()


# ── Peer pull (HTTP stubbed, real second Storage) ────────────────────────────

class _Resp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        pass


@pytest.fixture
def peer(tmp_path_factory):
    """A second real core database standing in for the other Mac."""
    import sinam_core
    peer_dir = tmp_path_factory.mktemp("peer-home")
    store = sinam_core.Storage(str(peer_dir / "synapse.db"))
    gate = sinam_core.connect(str(peer_dir / "synapse.db"))
    return store, gate


@pytest.fixture
def stubbed_http(peer, monkeypatch):
    """Route sync_peers' HTTP calls to the peer Storage, no sockets."""
    store, _ = peer

    class _Requests:
        # L'espace dont le pair se réclame, que les tests de cloisonnement
        # déplacent : None = un pair d'avant les espaces.
        space_id = None

        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            if url.endswith("/sync/status"):
                return _Resp(json.dumps({"device_id": store.sync_device_id(),
                                         "space_id": _Requests.space_id}))
            if url.endswith("/sync/changes"):
                return _Resp(store.sync_changes_since(
                    int(params["since"]), int(params["limit"])))
            raise AssertionError(f"unexpected URL {url}")

    from api import sync_peers
    monkeypatch.setattr(sync_peers, "requests", _Requests)
    return _Requests


def test_pull_from_peer_bootstraps_and_is_idempotent(client, peer, stubbed_http):
    store, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('pc-1', 'depuis le pair', 'test')", [])
    gate.execute(
        "INSERT INTO atomic_notes (id, content, kind) VALUES ('pn-1', 'note du pair', 'note')", [])
    gate.execute(
        "INSERT INTO entities (id, canonical_name, type) VALUES ('pe-1', 'Pixel', 'concept')", [])

    from api.sync_peers import pull_from_peer
    report = pull_from_peer("http://127.0.0.1:8000")
    assert report["peer_device"] == store.sync_device_id()
    assert report["rows_created"] >= 3
    assert report["cursor"] > 0

    conn = _conn()
    try:
        assert conn.execute("SELECT content FROM inbox WHERE id='pc-1'").fetchone()[0] \
            == "depuis le pair"
        assert conn.execute("SELECT count(*) FROM atomic_notes WHERE id='pn-1'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM entities WHERE id='pe-1'").fetchone()[0] == 1
        # Cursor persisted per peer device.
        saved = conn.execute("SELECT v FROM sync_meta WHERE k = ?",
                             (f"cursor:{store.sync_device_id()}",)).fetchone()[0]
        assert int(saved) == report["cursor"]
    finally:
        conn.close()

    # Second pull: cursor did its job, nothing new lands.
    again = pull_from_peer("http://127.0.0.1:8000")
    assert again["rows_created"] == 0
    assert again["rows_deleted"] == 0

    # And the peer's deletes replicate as tombstones on the next pull.
    gate.execute("DELETE FROM inbox WHERE id='pc-1'", [])
    third = pull_from_peer("http://127.0.0.1:8000")
    assert third["rows_deleted"] == 1
    conn = _conn()
    try:
        assert conn.execute("SELECT count(*) FROM inbox WHERE id='pc-1'").fetchone()[0] == 0
    finally:
        conn.close()


def test_pull_skips_self(client, monkeypatch):
    from api import sync_peers
    from core_store import get_store

    class _Requests:
        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            return _Resp(json.dumps({"device_id": get_store().sync_device_id()}))

    monkeypatch.setattr(sync_peers, "requests", _Requests)
    report = sync_peers.pull_from_peer("http://127.0.0.1:8000")
    assert report["skipped"] == "self"


# ── Cloisonnement des espaces ────────────────────────────────────────────────

def _found_space(space_id: str) -> None:
    """Fonder notre espace sans passer par le cycle (claim_owner + ensure_space
    en tireraient un au hasard)."""
    conn = _conn()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO space (id, space_id, name) "
                         "VALUES ('space', ?, 'Ma mémoire')", (space_id,))
    finally:
        conn.close()


def test_pull_refuses_a_peer_from_another_space(client, peer, stubbed_http):
    """Le scénario de la fuite : deux mémoires étrangères sur un même Wi-Fi.
    mDNS les fait se voir, le jeton ne les distingue pas, l'espace si."""
    store, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('etranger', 'sa mémoire', 'test')", [])
    _found_space("le-mien")
    stubbed_http.space_id = "le-sien"

    from api.sync_peers import pull_from_peer
    report = pull_from_peer("http://127.0.0.1:8000")
    assert report["skipped"] == "other_space"

    conn = _conn()
    try:
        assert conn.execute(
            "SELECT count(*) FROM inbox WHERE id='etranger'").fetchone()[0] == 0
    finally:
        conn.close()


def test_pull_accepts_a_peer_from_our_space(client, peer, stubbed_http):
    store, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('nôtre', 'même espace', 'test')", [])
    _found_space("partagé")
    stubbed_http.space_id = "partagé"

    from api.sync_peers import pull_from_peer
    report = pull_from_peer("http://127.0.0.1:8000")
    assert report["rows_created"] >= 1


def test_pull_refuses_a_space_we_never_joined_when_not_virgin(client, peer, stubbed_http):
    """Nous n'avons pas d'espace mais nous avons vécu : rien ne justifie
    d'avaler la mémoire d'un inconnu qui, lui, en a un."""
    _, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('inconnu', 'chez lui', 'test')", [])
    conn = _conn()
    try:
        with conn:
            conn.execute("INSERT INTO inbox (id, content, source) "
                         "VALUES ('à moi', 'déjà vécu', 'test')")
    finally:
        conn.close()
    stubbed_http.space_id = "le-sien"

    from api.sync_peers import pull_from_peer
    assert pull_from_peer("http://127.0.0.1:8000")["skipped"] == "no_space"


def test_virgin_install_bootstraps_the_space_then_forgets_the_hint(client, peer, stubbed_http):
    """L'appairage pose l'espace visé, le bootstrap l'utilise, et la vraie
    ligne `space` arrivée le remplace."""
    _, gate = peer
    gate.execute("INSERT INTO space (id, space_id, name) "
                 "VALUES ('space', 'espace-du-membre', 'Sa mémoire')", [])
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('du-membre', 'sa capture', 'test')", [])
    stubbed_http.space_id = "espace-du-membre"

    from api.sync_peers import (clear_joining_space_id, expected_space_id,
                                pull_from_peer, set_joining_space_id)
    set_joining_space_id("espace-du-membre")
    conn = _conn()
    try:
        assert expected_space_id(conn) == "espace-du-membre"
    finally:
        conn.close()

    report = pull_from_peer("http://127.0.0.1:8000")
    assert report["rows_created"] >= 1

    conn = _conn()
    try:
        assert conn.execute(
            "SELECT space_id FROM space WHERE id='space'").fetchone()[0] == "espace-du-membre"
        # L'indice provisoire a été effacé : c'est la ligne répliquée qui parle.
        assert conn.execute(
            "SELECT count(*) FROM sync_meta WHERE k='joining_space_id'").fetchone()[0] == 0
    finally:
        conn.close()
    clear_joining_space_id()


def test_known_peers_ignores_another_space_before_any_contact(client, monkeypatch):
    """Le jeton part dès la première requête : un pair d'un autre espace ne
    doit pas être contacté du tout, pas seulement refusé après coup."""
    from api import discovery, sync_peers
    _found_space("le-mien")
    monkeypatch.setattr(discovery, "_PEERS", {
        "moi": {"name": "moi", "url": "http://ami.test:8000",
                "device_id": "d1", "space_id": "le-mien"},
        "autre": {"name": "autre", "url": "http://etranger.test:8000",
                  "device_id": "d2", "space_id": "le-sien"},
        "muet": {"name": "muet", "url": "http://ancien.test:8000",
                 "device_id": "d3", "space_id": None},
    })
    urls = {p["url"] for p in sync_peers.known_peers()}
    assert "http://ami.test:8000" in urls
    assert "http://etranger.test:8000" not in urls
    # Un pair muet (version antérieure) reste contacté, comme le serveur
    # tolère un appelant muet.
    assert "http://ancien.test:8000" in urls

    # Le mode strict ferme les deux tolérances d'un coup.
    monkeypatch.setenv("SYNAPSE_SYNC_STRICT_SPACE", "1")
    urls = {p["url"] for p in sync_peers.known_peers()}
    assert urls == {"http://ami.test:8000"}


def test_mdns_advert_carries_the_space(client):
    from api import discovery
    _found_space("annoncé")
    discovery._SELF_SPACE_ID = None      # vider le cache du module
    assert discovery._self_space_id() == "annoncé"


def test_sync_changes_refuses_a_caller_from_another_space(client):
    _found_space("le-mien")
    assert client.get("/sync/changes", params={"since": 0},
                      headers={"X-Sinam-Space": "le-sien"}).status_code == 403
    # Sans en-tête : toléré le temps de la migration des clients.
    assert client.get("/sync/changes", params={"since": 0}).status_code == 200
    assert client.get("/sync/changes", params={"since": 0},
                      headers={"X-Sinam-Space": "le-mien"}).status_code == 200


def test_sync_changes_strict_mode_refuses_a_silent_caller(client, monkeypatch):
    _found_space("le-mien")
    monkeypatch.setenv("SYNAPSE_SYNC_STRICT_SPACE", "1")
    assert client.get("/sync/changes", params={"since": 0}).status_code == 403
    assert client.get("/sync/changes", params={"since": 0},
                      headers={"X-Sinam-Space": "le-mien"}).status_code == 200


def test_sync_push_refuses_a_caller_from_another_space(client, peer):
    store, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('poussé', 'chez lui', 'test')", [])
    changes = store.sync_changes_since(0, 1000)
    _found_space("le-mien")

    assert client.post("/sync/push", content=changes,
                       headers={"X-Sinam-Space": "le-sien"}).status_code == 403
    conn = _conn()
    try:
        assert conn.execute(
            "SELECT count(*) FROM inbox WHERE id='poussé'").fetchone()[0] == 0
    finally:
        conn.close()


# ── Dedup of double-routed derived rows ──────────────────────────────────────

def test_dedup_collapses_twin_derived_rows(client):
    conn = _conn()
    try:
        with conn:
            conn.execute("INSERT INTO inbox (id, content) VALUES ('cap-x', 'source')")
            conn.execute("INSERT INTO entities (id, canonical_name) VALUES ('ent-1', 'Alexis')")
            # Twin notes: same capture, same content — two devices routed it.
            conn.execute(
                "INSERT INTO atomic_notes (id, content, kind, provenance_capture_id) "
                "VALUES ('n-bbb', 'même note', 'note', 'cap-x')")
            conn.execute(
                "INSERT INTO atomic_notes (id, content, kind, provenance_capture_id) "
                "VALUES ('n-aaa', 'même note', 'note', 'cap-x')")
            # A legitimately different note on the same capture must survive.
            conn.execute(
                "INSERT INTO atomic_notes (id, content, kind, provenance_capture_id) "
                "VALUES ('n-ccc', 'autre contenu', 'note', 'cap-x')")
            # Twin facts.
            conn.execute(
                "INSERT INTO facts (id, entity_id, predicate, value, provenance_capture_id) "
                "VALUES ('f-bbb', 'ent-1', 'aime', 'le café', 'cap-x')")
            conn.execute(
                "INSERT INTO facts (id, entity_id, predicate, value, provenance_capture_id) "
                "VALUES ('f-aaa', 'ent-1', 'aime', 'le café', 'cap-x')")
    finally:
        conn.close()

    from api.sync_peers import dedup_after_pull
    removed = dedup_after_pull()
    assert removed == {"atomic_notes": 1, "facts": 1}

    conn = _conn()
    try:
        notes = [r[0] for r in conn.execute(
            "SELECT id FROM atomic_notes ORDER BY id").fetchall()]
        assert notes == ["n-aaa", "n-ccc"]  # smallest uuid of the twins + the distinct one
        facts = [r[0] for r in conn.execute("SELECT id FROM facts ORDER BY id").fetchall()]
        assert facts == ["f-aaa"]
        # The collapse journals tombstones → it replicates to peers.
        tomb = conn.execute(
            "SELECT count(*) FROM sync_log WHERE col = '-' AND pk IN ('n-bbb', 'f-bbb')"
        ).fetchone()[0]
        assert tomb == 2
    finally:
        conn.close()

    # Idempotent.
    assert dedup_after_pull() == {}


# ── Push (the phone sends its pages, it can't be pulled from) ────────────────

def test_sync_push_applies_a_peer_changeset(client, peer):
    store, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('push-1', 'depuis le tel', 'ios')", [])
    gate.execute(
        "INSERT INTO atomic_notes (id, content, kind) VALUES ('push-n1', 'note du tel', 'note')", [])
    page = store.sync_changes_since(0, 10000)

    r = client.post("/sync/push", content=page,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    report = r.json()
    assert report["rows_created"] >= 2
    assert "reembedded" in report and "deduped" in report

    conn = _conn()
    try:
        assert conn.execute(
            "SELECT content FROM inbox WHERE id='push-1'").fetchone()[0] == "depuis le tel"
        assert conn.execute(
            "SELECT count(*) FROM atomic_notes WHERE id='push-n1'").fetchone()[0] == 1
    finally:
        conn.close()

    # Re-pushing the same page is an echo — nothing changes.
    again = client.post("/sync/push", content=page,
                        headers={"Content-Type": "application/json"}).json()
    assert again["rows_created"] == 0
    assert again["rows_updated"] == 0
    assert again["rows_deleted"] == 0


def test_sync_push_rejects_garbage(client):
    r = client.post("/sync/push", content="pas du json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400


# ── Espace + registre d'appareils ────────────────────────────────────────────

def test_register_self_device_seeds_then_only_refreshes(client):
    from api.sync_peers import register_self_device
    from core_store import get_store
    me = get_store().sync_device_id()

    register_self_device()
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT name, platform, last_seen FROM devices WHERE device_id = ?",
            (me,)).fetchone()
        assert row is not None and row[0] and row[1]
        # Un rename utilisateur survit aux boots suivants.
        with conn:
            conn.execute("UPDATE devices SET name = 'Mon Mac' WHERE device_id = ?", (me,))
    finally:
        conn.close()

    register_self_device()
    conn = _conn()
    try:
        name = conn.execute(
            "SELECT name FROM devices WHERE device_id = ?", (me,)).fetchone()[0]
        assert name == "Mon Mac"
    finally:
        conn.close()


def test_ensure_space_is_owner_only(client):
    from api.sync_peers import claim_owner, ensure_space, get_space
    from core_store import get_store

    # Pas d'owner → pas de création (une réplique fraîche ne fonde jamais).
    ensure_space()
    conn = _conn()
    try:
        assert get_space(conn) is None
    finally:
        conn.close()

    # Owner = moi → fondation, puis idempotent.
    claim_owner(get_store().sync_device_id())
    ensure_space()
    ensure_space()
    conn = _conn()
    try:
        space = get_space(conn)
        assert space and space["name"] == "Ma mémoire" and space["space_id"]
    finally:
        conn.close()

    # Owner = un autre device → un non-owner ne fonde rien.
    conn = _conn()
    try:
        with conn:
            conn.execute("DELETE FROM space")
            conn.execute("UPDATE sync_owner SET device_id = 'other-device'")
    finally:
        conn.close()
    ensure_space()
    conn = _conn()
    try:
        assert get_space(conn) is None
    finally:
        conn.close()


def test_space_and_devices_endpoints(client):
    from api.sync_peers import claim_owner, ensure_space, register_self_device
    from core_store import get_store
    me = get_store().sync_device_id()

    register_self_device()
    claim_owner(me)
    ensure_space()

    body = client.get("/space").json()
    assert body["space"]["name"] == "Ma mémoire"
    assert body["device_id"] == me and body["owner_device_id"] == me

    renamed = client.patch("/space", json={"name": "Mémoire d'Alexis"}).json()
    assert renamed["space"]["name"] == "Mémoire d'Alexis"
    assert client.patch("/space", json={"name": "  "}).status_code == 422

    devices = client.get("/devices").json()["devices"]
    assert len(devices) == 1
    assert devices[0]["is_self"] and devices[0]["is_owner"] and not devices[0]["revoked"]

    # Garde-fous de révocation : soi-même et l'owner sont intouchables.
    assert client.patch(f"/device/{me}", json={"revoked": True}).status_code == 409
    conn = _conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO devices (device_id, name, platform) "
                "VALUES ('peer-1', 'Pixel', 'android')")
    finally:
        conn.close()

    out = client.patch("/device/peer-1", json={"name": "Pixel d'Alexis",
                                               "revoked": True}).json()
    assert out["name"] == "Pixel d'Alexis" and out["revoked"]

    # Un pair révoqué est sauté par la boucle de pull.
    from api.sync_peers import device_revoked
    conn = _conn()
    try:
        assert device_revoked(conn, "peer-1") is True
    finally:
        conn.close()

    restored = client.patch("/device/peer-1", json={"revoked": False}).json()
    assert not restored["revoked"]
    assert client.patch("/device/inconnu", json={"name": "x"}).status_code == 404


# ── Appairage ────────────────────────────────────────────────────────────────

def test_pairing_end_to_end_transfers_secrets(client, monkeypatch):
    """Member offers a QR → joiner scans (real core crypto) → member approves
    with key opt-in → joiner opens the sealed payload and gets space_id, token
    and the key. No token needed on the joiner endpoints."""
    import base64
    import json
    from sinam_core import pairing_accept, pairing_offer_addrs, pairing_open

    from api.sync_peers import claim_owner, ensure_space
    from core_store import get_store

    from api import tls
    tls.ensure_cert()  # le membre a son certificat avant de montrer le QR

    # Member founds a space + has a key; the request carries a bearer token.
    monkeypatch.setenv("SYNAPSE_API_TOKEN", "member-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    claim_owner(get_store().sync_device_id())
    ensure_space()
    auth = {"Authorization": "Bearer member-token"}

    # 1. Member starts the offer (auth required).
    assert client.post("/pair/offer").status_code == 401
    qr = client.post("/pair/offer", headers=auth).json()["qr"]
    assert pairing_offer_addrs(qr) is not None

    # 2. Joiner scans locally (core), submits accept_pub — NO auth.
    accept_pub, joiner_key = pairing_accept(qr)
    req = client.post("/pair/request", json={
        "accept_pub_b64": base64.b64encode(accept_pub).decode(),
        "name": "Pixel d'Alexis", "platform": "android"}).json()
    request_id = req["request_id"]

    # 3. Member sees the pending request and approves with the key.
    pend = client.get("/pair/pending", headers=auth).json()["requests"]
    assert any(p["request_id"] == request_id and p["name"] == "Pixel d'Alexis" for p in pend)
    assert client.post("/pair/approve", headers=auth,
                       json={"request_id": request_id, "include_key": True}).status_code == 200

    # 4. Joiner polls, opens the sealed payload with its channel key.
    res = client.get(f"/pair/result/{request_id}").json()
    assert res["status"] == "approved"
    offer_pub = base64.b64decode(_offer_pub_from_qr(qr))
    opened = pairing_open(joiner_key, offer_pub, accept_pub, res["sealed"])
    payload = json.loads(opened)
    assert payload["token"] == "member-token"
    assert payload["space_id"]
    assert payload["anthropic_key"] == "sk-ant-secret"
    # L'empreinte du certificat ne peut voyager que par ce canal :
    # c'est le seul qui soit authentifié par le QR. Le certificat existe depuis
    # le début du test, donc c'est bien une empreinte et pas un champ vide.
    from api import tls
    assert payload["cert_sha256"] == tls.fingerprint()
    assert len(payload["cert_sha256"]) == 64

    # 5. One-shot: a second poll no longer returns the secret.
    assert client.get(f"/pair/result/{request_id}").json()["status"] == "expired"


def test_a_second_offer_does_not_kill_the_first(client, monkeypatch):
    """Le défaut du 29/08 : l'écran « Ajouter un appareil » demande une offre
    dès son ouverture, depuis n'importe quel appareil de l'espace. La première
    devenait caduque en silence et le joiner lisait « QR invalide » alors que
    son QR était bon."""
    import base64
    import json

    from sinam_core import pairing_accept, pairing_open

    from api.sync_peers import claim_owner, ensure_space
    from core_store import get_store

    monkeypatch.setenv("SYNAPSE_API_TOKEN", "member-token")
    claim_owner(get_store().sync_device_id())
    ensure_space()
    auth = {"Authorization": "Bearer member-token"}

    # Une première offre est affichée et scannée...
    qr1 = client.post("/pair/offer", headers=auth).json()["qr"]
    accept_pub, joiner_key = pairing_accept(qr1)
    offer_pub = base64.b64decode(_offer_pub_from_qr(qr1))

    # ...puis un autre appareil de l'espace en demande une seconde.
    qr2 = client.post("/pair/offer", headers=auth).json()["qr"]
    assert qr2 != qr1

    # Le joiner de la PREMIÈRE offre annonce laquelle il a scannée.
    req = client.post("/pair/request", json={
        "accept_pub_b64": base64.b64encode(accept_pub).decode(),
        "offer_pub_b64": base64.b64encode(offer_pub).decode(),
        "name": "Pixel", "platform": "android"}).json()
    assert "request_id" in req, req

    assert client.post("/pair/approve", headers=auth, json={
        "request_id": req["request_id"], "include_key": False}).status_code == 200

    res = client.get(f"/pair/result/{req['request_id']}").json()
    assert res["status"] == "approved"
    opened = pairing_open(joiner_key, offer_pub, accept_pub, res["sealed"])
    assert opened is not None, "la charge doit s'ouvrir malgré l'offre concurrente"
    assert json.loads(opened)["space_id"]


def test_a_pending_request_survives_a_new_offer(client, monkeypatch):
    """Une demande déjà déposée ne doit pas disparaître parce qu'une autre
    offre a démarré : c'est `_requests.clear()` qui la tuait."""
    import base64

    from sinam_core import pairing_accept

    from api.sync_peers import claim_owner, ensure_space
    from core_store import get_store

    monkeypatch.setenv("SYNAPSE_API_TOKEN", "member-token")
    claim_owner(get_store().sync_device_id())
    ensure_space()
    auth = {"Authorization": "Bearer member-token"}

    qr1 = client.post("/pair/offer", headers=auth).json()["qr"]
    accept_pub, _ = pairing_accept(qr1)
    rid = client.post("/pair/request", json={
        "accept_pub_b64": base64.b64encode(accept_pub).decode(),
        "offer_pub_b64": _offer_pub_from_qr(qr1),
        "name": "Pixel", "platform": "android"}).json()["request_id"]

    client.post("/pair/offer", headers=auth)  # un autre écran s'ouvre

    pending = client.get("/pair/pending", headers=auth).json()["requests"]
    assert any(p["request_id"] == rid for p in pending), \
        "la demande en cours a été effacée par la nouvelle offre"


def test_a_joiner_that_names_no_offer_still_works(client, monkeypatch):
    """Repli pour un client d'une version antérieure : sans `offer_pub_b64`,
    on retombe sur l'offre la plus récente, comme avant."""
    import base64

    from sinam_core import pairing_accept, pairing_open

    from api.sync_peers import claim_owner, ensure_space
    from core_store import get_store

    monkeypatch.setenv("SYNAPSE_API_TOKEN", "member-token")
    claim_owner(get_store().sync_device_id())
    ensure_space()
    auth = {"Authorization": "Bearer member-token"}

    qr = client.post("/pair/offer", headers=auth).json()["qr"]
    accept_pub, joiner_key = pairing_accept(qr)
    rid = client.post("/pair/request", json={
        "accept_pub_b64": base64.b64encode(accept_pub).decode(),
        "name": "Ancien", "platform": "android"}).json()["request_id"]
    client.post("/pair/approve", headers=auth,
                json={"request_id": rid, "include_key": False})
    res = client.get(f"/pair/result/{rid}").json()
    offer_pub = base64.b64decode(_offer_pub_from_qr(qr))
    assert pairing_open(joiner_key, offer_pub, accept_pub, res["sealed"]) is not None


def test_pairing_denied_and_key_optout(client, monkeypatch):
    import base64
    import json
    from sinam_core import pairing_accept, pairing_open

    from api.sync_peers import claim_owner, ensure_space
    from core_store import get_store

    monkeypatch.setenv("SYNAPSE_API_TOKEN", "member-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    claim_owner(get_store().sync_device_id())
    ensure_space()
    auth = {"Authorization": "Bearer member-token"}

    qr = client.post("/pair/offer", headers=auth).json()["qr"]
    accept_pub, joiner_key = pairing_accept(qr)

    # Opt-OUT of the key.
    rid = client.post("/pair/request", json={
        "accept_pub_b64": base64.b64encode(accept_pub).decode(),
        "name": "Mac", "platform": "darwin"}).json()["request_id"]
    client.post("/pair/approve", headers=auth,
                json={"request_id": rid, "include_key": False})
    res = client.get(f"/pair/result/{rid}").json()
    offer_pub = base64.b64decode(_offer_pub_from_qr(qr))
    payload = json.loads(pairing_open(joiner_key, offer_pub, accept_pub, res["sealed"]))
    assert "anthropic_key" not in payload

    # A denied request tells the joiner nothing sealed.
    rid2 = client.post("/pair/request", json={
        "accept_pub_b64": base64.b64encode(accept_pub).decode(),
        "name": "X", "platform": "y"}).json()["request_id"]
    client.post("/pair/deny", headers=auth, json={"request_id": rid2})
    assert client.get(f"/pair/result/{rid2}").json()["status"] == "denied"


def _offer_pub_from_qr(qr: str) -> str:
    # QR wire form: "v|offer_pub_b64|secret_b64|addrs"
    return qr.split("|")[1]


# ── Transport chiffré + épinglage du certificat (vrai TLS, sans stub) ────────
# Ici on ne stubbe PAS le réseau : un vrai serveur HTTPS auto-signé tourne sur la
# boucle locale, pour prouver que le tir refuse le clair réseau, épingle au 1er
# contact (TOFU) et refuse un certificat qui a changé.

def _make_self_signed(tmp_dir):
    import datetime
    import hashlib as _h
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test peer")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(subj).issuer_name(subj)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(
            [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    certfile = Path(tmp_dir) / "c.pem"
    keyfile = Path(tmp_dir) / "k.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    fp = _h.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return str(certfile), str(keyfile), fp


import contextlib  # noqa: E402


@contextlib.contextmanager
def _tls_peer_server(store, certfile, keyfile, space_id=None):
    import http.server
    import ssl as _ssl
    import threading
    from urllib.parse import parse_qs, urlparse

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/sync/status"):
                body = json.dumps({"device_id": store.sync_device_id(),
                                   "space_id": space_id}).encode()
            elif self.path.startswith("/sync/changes"):
                q = parse_qs(urlparse(self.path).query)
                since = int(q.get("since", ["0"])[0])
                limit = int(q.get("limit", ["5000"])[0])
                body = store.sync_changes_since(since, limit).encode()
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile, keyfile)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"https://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def test_pull_refuses_cleartext_to_a_network_peer(client):
    from api.sync_peers import pull_from_peer
    rep = pull_from_peer("http://192.168.1.50:8000")
    assert rep["skipped"] == "cleartext_network_peer"


def test_pull_over_tls_pins_the_cert_on_first_contact(client, peer, tmp_path):
    store, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('pt-1','via tls','test')", [])
    certfile, keyfile, fp = _make_self_signed(tmp_path)
    from api.sync_peers import get_peer_cert, pull_from_peer
    with _tls_peer_server(store, certfile, keyfile) as base:
        rep = pull_from_peer(base)
    assert rep["peer_device"] == store.sync_device_id()
    assert rep["rows_created"] >= 1
    # TOFU: l'empreinte présentée est mémorisée pour ce pair.
    assert get_peer_cert(store.sync_device_id()) == fp


def test_pull_refuses_a_changed_cert(client, peer, tmp_path):
    store, gate = peer
    gate.execute(
        "INSERT INTO inbox (id, content, source) VALUES ('pt-2','ne passe pas','test')", [])
    certfile, keyfile, _fp = _make_self_signed(tmp_path)
    from api.sync_peers import pull_from_peer, set_peer_cert
    set_peer_cert(store.sync_device_id(), "0" * 64)  # une empreinte différente
    with _tls_peer_server(store, certfile, keyfile) as base:
        rep = pull_from_peer(base)
    assert rep["skipped"] == "cert_mismatch"
    conn = _conn()
    try:
        assert conn.execute(
            "SELECT count(*) FROM inbox WHERE id='pt-2'").fetchone()[0] == 0
    finally:
        conn.close()


def test_pull_with_known_pin_refuses_before_any_request(client, peer, tmp_path):
    """Avec l'empreinte déjà connue (hint mDNS), le mauvais certificat est
    refusé au handshake — le jeton ne part jamais."""
    store, _gate = peer
    certfile, keyfile, _fp = _make_self_signed(tmp_path)
    from api.sync_peers import pull_from_peer, set_peer_cert
    set_peer_cert(store.sync_device_id(), "0" * 64)
    with _tls_peer_server(store, certfile, keyfile) as base:
        rep = pull_from_peer(base, peer_device_hint=store.sync_device_id())
    assert rep["skipped"] == "cert_mismatch"
