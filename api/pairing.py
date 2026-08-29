"""Device pairing sessions — the MEMBER side.

The member (a device already in the space, holding the data + token + optional
key) shows a QR and, after the user approves, hands a joining device the
secrets it needs to join the mesh. The cryptography lives in the Rust core
(`sinam_core.PairingSession` / `pairing_*`, see `sinam-core/src/pairing.rs`):
this module is only the in-memory session state + the transport.

Security model. The joiner endpoints (`/pair/request`, `/pair/result`) are
UNauthenticated on purpose — a fresh device has no bearer token yet. That is
safe because everything those endpoints return is AEAD-sealed under a channel
key derived from the QR secret: an attacker who never saw the QR cannot derive
the key, so the sealed payload is useless to them. The member endpoints
(`/pair/offer`, `/pair/pending`, `/pair/approve`, `/pair/deny`) require the
bearer token: they drive the member's own device.

State is process-local and ephemeral (one active offer per member, short TTL):
pairing is a one-shot in-person action, nothing here is persisted.
"""

from __future__ import annotations

import os

from api import access as _access
import socket
import threading
import time
import uuid

from sinam_core import (
    CodePairing,
    PairingSession,
    pairing_code_confirm_verify,
    pairing_seal,
)

from config_store import get_anthropic_key
from db import first_row, get_connection

# TTL for an offer and for an unclaimed request. Pairing is done face to face
# in under a minute; anything older is stale and dropped.
_OFFER_TTL = 120.0
_REQUEST_TTL = 120.0
# online guesses allowed on one displayed code. SPAKE2 makes offline
# guessing impossible; this cap is what bounds the online kind.
_CODE_MAX_ATTEMPTS = 3

_lock = threading.Lock()
# Les offres QR vivantes, indexées par leur clé publique.
#
# C'était un emplacement unique, et une offre en écrasait une autre. Or l'écran
# « Ajouter un appareil » demande une offre dès son ouverture, depuis n'importe
# quel appareil de l'espace : un QR affiché ailleurs devenait caduc en silence,
# et le joiner qui l'avait scanné recevait une charge scellée sous une clé qu'il
# ne pouvait pas dériver. Il lisait « QR invalide », alors que son QR était bon.
# Plusieurs offres peuvent donc coexister ; le TTL les nettoie.
_offers: dict[bytes, dict] = {}
# one active 6-digit code offer (Mac↔Mac, no camera).
_code_offer: dict | None = None
# request_id -> pending/approved/denied request dict.
_requests: dict[str, dict] = {}


def _now() -> float:
    return time.monotonic()


def _prune(now: float) -> None:
    """Drop the offer + requests that have outlived their TTL. Caller holds
    the lock."""
    global _code_offer
    for pub in [k for k, o in _offers.items() if now - o["created"] > _OFFER_TTL]:
        _offers.pop(pub, None)
    if _code_offer is not None and now - _code_offer["created"] > _OFFER_TTL:
        _code_offer = None
    stale = [rid for rid, r in _requests.items() if now - r["created"] > _REQUEST_TTL]
    for rid in stale:
        _requests.pop(rid, None)


def _local_addrs() -> list[str]:
    """Reachable base URLs for THIS backend, for the QR. The primary LAN IP
    (via a dummy UDP connect, no traffic sent) + the API port."""
    port = os.environ.get("SYNAPSE_API_PORT", "8000")
    ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        ip = None
    addrs = []
    if ip:
        # Le chiffré d'abord : un client à jour prend la première adresse qui
        # répond, et c'est celle-là qu'on veut qu'il retienne. Le clair reste
        # derrière pour l'appareil qui ne sait pas encore épingler.
        from api.tls import cert_path, tls_port

        if cert_path().exists() and not os.environ.get("SYNAPSE_TLS_DISABLE"):
            addrs.append(f"https://{ip}:{tls_port()}")
        addrs.append(f"http://{ip}:{port}")
    return addrs


def start_offer() -> dict:
    """Begin showing a QR (member side). Replaces any prior offer. Returns
    `{qr}` — render `qr` as a QR code for the joiner to scan."""
    session, qr = PairingSession.offer(_local_addrs())
    with _lock:
        _prune(_now())
        pub = session.offer_pub()
        _offers[pub] = {"session": session, "qr": qr, "offer_pub": pub,
                        "created": _now()}
        # Les demandes en cours ne sont PAS vidées : elles visent une autre
        # offre, qui reste vivante à côté de celle-ci.
    return {"qr": qr}


def start_code_offer() -> dict:
    """Member side: begin a code pairing for a camera-less joiner
    (Mac↔Mac). Returns `{code}` — display it to the user, NEVER log it. A
    fresh code replaces the previous one and resets the attempt counter."""
    global _code_offer
    import secrets

    code = f"{secrets.randbelow(1_000_000):06d}"
    with _lock:
        _prune(_now())
        _code_offer = {"code": code, "attempts": 0, "created": _now()}
    return {"code": code}


def submit_code_request(msg_joiner: bytes, name: str, platform: str) -> dict:
    """Joiner side (unauthenticated): the joiner's SPAKE2 message.
    We run our half on the displayed code and answer with our message; the
    channel key exists on both sides but the request stays OUT of the
    approval queue until the joiner proves code knowledge (`confirm`)."""
    with _lock:
        _prune(_now())
        if _code_offer is None:
            raise _PairingError(409, "no active code offer")
        if _code_offer["attempts"] >= _CODE_MAX_ATTEMPTS:
            raise _PairingError(429, "too many attempts — show a new code")
        session = CodePairing(_code_offer["code"])
        msg_member = bytes(session.msg())
        channel_key = session.finish(msg_joiner)
        request_id = str(uuid.uuid4())
        _requests[request_id] = {
            "name": (name or "").strip()[:80] or "Nouvel appareil",
            "platform": (platform or "").strip()[:32] or "unknown",
            # AAD pair for seal/open: member message first, joiner second.
            "aad_a": msg_member,
            "aad_b": bytes(msg_joiner),
            "channel_key": channel_key,
            "status": "awaiting_confirm",
            "sealed": None,
            "created": _now(),
        }
        import base64

        return {"request_id": request_id,
                "msg": base64.b64encode(msg_member).decode("ascii")}


def confirm_code_request(request_id: str, mac: bytes) -> dict:
    """Verify the joiner's key-confirmation MAC. Success promotes
    the request into the human-approval queue; a mismatch burns one attempt
    and three misses kill the code (the user must display a new one)."""
    global _code_offer
    with _lock:
        _prune(_now())
        req = _requests.get(request_id)
        if req is None or req["status"] != "awaiting_confirm":
            raise _PairingError(404, "unknown or expired request")
        ok = pairing_code_confirm_verify(
            req["channel_key"], req["aad_a"], req["aad_b"], mac
        )
        if not ok:
            _requests.pop(request_id, None)
            if _code_offer is not None:
                _code_offer["attempts"] += 1
                if _code_offer["attempts"] >= _CODE_MAX_ATTEMPTS:
                    _code_offer = None
            raise _PairingError(403, "confirmation failed")
        req["status"] = "pending"
        return {"status": "pending"}


def submit_request(accept_pub: bytes, name: str, platform: str,
                   offer_pub: bytes | None = None) -> dict:
    """Joiner side (unauthenticated): submit the scanner's public key + who we
    are. Returns `{request_id}`. The member must still approve.

    `offer_pub` dit QUELLE offre a été scannée : sans lui on ne pourrait que
    deviner, et se tromper d'offre donne une clé de canal différente donc une
    charge que le joiner ne peut pas ouvrir. Absent (client d'une version
    antérieure) : on retombe sur la plus récente, ce qui est le comportement
    d'avant et reste juste tant qu'il n'y a qu'une offre.
    """
    with _lock:
        _prune(_now())
        if not _offers:
            raise _PairingError(409, "no active pairing offer")
        if offer_pub is not None:
            offer = _offers.get(offer_pub)
            if offer is None:
                raise _PairingError(409, "offer expired or replaced — restart pairing")
        else:
            offer = max(_offers.values(), key=lambda o: o["created"])
        channel_key = offer["session"].channel_key(accept_pub)
        request_id = str(uuid.uuid4())
        _requests[request_id] = {
            "name": (name or "").strip()[:80] or "Nouvel appareil",
            "platform": (platform or "").strip()[:32] or "unknown",
            "accept_pub": accept_pub,
            # L'offre visée voyage AVEC la demande : l'approbation scelle sous
            # cette offre-là, même si une autre est apparue entre-temps.
            "offer_pub": offer["offer_pub"],
            "channel_key": channel_key,
            "status": "pending",
            "sealed": None,
            "created": _now(),
        }
        return {"request_id": request_id}


def list_pending() -> list[dict]:
    """Member side: the requests awaiting the user's approval."""
    with _lock:
        _prune(_now())
        return [
            {"request_id": rid, "name": r["name"], "platform": r["platform"]}
            for rid, r in _requests.items()
            if r["status"] == "pending"
        ]


def approve(request_id: str, include_key: bool) -> dict:
    """Member side: the user approved. Seal the payload (space_id, name, the
    member's sync token, peer URLs, and the API key IFF opted in) under the
    request's channel key. The joiner fetches it via `/pair/result`."""
    with _lock:
        _prune(_now())
        req = _requests.get(request_id)
        if req is None:
            raise _PairingError(404, "unknown or expired request")
        if req["status"] != "pending":
            raise _PairingError(409, f"request already {req['status']}")
        if req.get("aad_a") is not None:
            # code channel: the AAD pair travelled with the request.
            aad_a, aad_b = req["aad_a"], req["aad_b"]
        else:
            # Canal QR : lié à l'offre que le joiner a scannée, pas à celle
            # qui se trouve affichée maintenant.
            if req.get("offer_pub") is None:
                raise _PairingError(409, "offer expired — restart pairing")
            aad_a, aad_b = req["offer_pub"], req["accept_pub"]
        payload = _build_payload(include_key)
        sealed = pairing_seal(req["channel_key"], aad_a, aad_b, payload)
        req["status"] = "approved"
        req["sealed"] = sealed
    return {"status": "approved"}


def deny(request_id: str) -> dict:
    with _lock:
        req = _requests.get(request_id)
        if req is None:
            raise _PairingError(404, "unknown or expired request")
        req["status"] = "denied"
        req["sealed"] = None
    return {"status": "denied"}


def poll_result(request_id: str) -> dict:
    """Joiner side (unauthenticated): poll for the outcome. On approval,
    returns the sealed payload ONCE, then consumes the request so the
    single-use secret can't be re-fetched."""
    with _lock:
        _prune(_now())
        req = _requests.get(request_id)
        if req is None:
            return {"status": "expired"}
        if req["status"] == "approved":
            sealed = req["sealed"]
            _requests.pop(request_id, None)  # one-shot delivery
            return {"status": "approved", "sealed": sealed}
        if req["status"] == "denied":
            _requests.pop(request_id, None)
            return {"status": "denied"}
        return {"status": "pending"}


def _build_payload(include_key: bool) -> bytes:
    """The secrets the joiner needs, as compact JSON bytes. Never logged."""
    import json

    from api.sync_peers import known_peers

    conn = get_connection()
    try:
        row = first_row(conn.execute(
            "SELECT space_id, name FROM space WHERE id = 'space'"))
    finally:
        conn.close()
    space_id = row["space_id"] if row else None
    space_name = (row["name"] if row else None) or "Ma mémoire"
    peers = [p["url"] for p in known_peers()] + _local_addrs()
    from api.tls import fingerprint as _cert_fingerprint

    payload = {
        # L'empreinte du certificat du lien local. Elle voyage ICI et nulle
        # part ailleurs : la charge est scellée sous une clé que seul celui qui
        # a scanné le QR (ou connu le code) peut dériver, donc c'est le seul
        # canal où une empreinte veut dire quelque chose. Annoncée en mDNS elle
        # ne prouverait rien, n'importe qui peut annoncer la sienne.
        "cert_sha256": _cert_fingerprint(),
        "space_id": space_id,
        "space_name": space_name,
        "token": _access.resolve_token() or "",
        "peers": sorted(set(peers)),
    }
    if include_key:
        key = get_anthropic_key()
        if key:
            payload["anthropic_key"] = key
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class _PairingError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)
