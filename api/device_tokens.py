"""Un jeton par appareil, pour que retirer un appareil veuille dire quelque chose.

Le problème qu'on répare
------------------------

« Retirer un appareil » posait `revoked_at` dans la table répliquée `devices`,
grisait une ligne dans les Réglages, et ne retirait l'accès à rien. Le jeton
était unique pour toute la mémoire et recopié dans chaque appareil à
l'appairage : le révoquer déconnectait tout le monde, ne pas le révoquer ne
coupait personne. Pour un geste dont tout l'intérêt est de reprendre le contrôle
d'un téléphone perdu ou vendu, c'était la promesse la plus dangereuse du
produit.

Chaque appairage délivre donc maintenant un jeton qui n'appartient qu'à
l'appareil qui vient d'entrer. Le retirer invalide le sien, et lui seul.

Ce qui est stocké
-----------------

**L'empreinte SHA-256, jamais le jeton.** Une base qui fuite ne doit pas livrer
les identifiants de tous les appareils du maillage — c'est le même raisonnement
que pour un mot de passe. La comparaison se fait donc sur l'empreinte, et la
valeur en clair n'existe qu'une fois, le temps de partir dans la charge scellée
de l'appairage.

Cette table ne se réplique PAS : elle n'est pas dans la liste des tables suivies
par le moteur de synchro. Un jeton est une porte d'entrée sur CE backend ; le
diffuser à tout le maillage donnerait à chaque appareil les clés de tous les
autres.

La fenêtre de migration
-----------------------

Les installs existantes partagent toutes le même jeton. Le refuser d'un coup
désappairerait tout le monde, y compris l'appareil depuis lequel on essaie de
réparer. L'ancien jeton commun reste donc accepté ; simplement, il n'est plus
délivré à personne, et un appareil qui se réappaire repart avec le sien.

Conséquence à assumer : tant qu'un appareil retiré détient l'ancien jeton
commun, la coupure ne le concerne pas. Elle sera complète le jour où le jeton
commun sera retiré — ce qui suppose que tous les appareils du maillage aient été
réappairés au moins une fois.
"""

import hashlib
import logging
import secrets

from db import get_connection

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS device_tokens (
    token_sha256 TEXT PRIMARY KEY,
    device_id    TEXT NOT NULL,
    label        TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_schema(conn=None) -> None:
    """Créée à la demande : le schéma appartient au cœur, et cette table-ci
    est locale au backend, donc elle n'a rien à y faire."""
    own = conn is None
    conn = conn or get_connection()
    try:
        with conn:
            conn.execute(_SCHEMA)
    finally:
        if own:
            conn.close()


def issue(device_id: str, label: str | None = None) -> str:
    """Fabriquer le jeton d'un appareil. Rendu EN CLAIR une seule fois — c'est
    l'appelant qui le met dans la charge scellée de l'appairage ; nous n'en
    gardons que l'empreinte."""
    token = secrets.token_urlsafe(32)
    conn = get_connection()
    try:
        ensure_schema(conn)
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO device_tokens "
                "(token_sha256, device_id, label) VALUES (?,?,?)",
                (_fingerprint(token), device_id, (label or "")[:80] or None))
    finally:
        conn.close()
    # Jamais le jeton dans le journal, ni sa longueur, ni son préfixe.
    log.info("jeton délivré à l'appareil %s", device_id)
    return token


def device_of(token: str) -> str | None:
    """L'appareil auquel ce jeton appartient, ou None s'il n'en est d'aucun."""
    if not token:
        return None
    conn = get_connection()
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT device_id FROM device_tokens WHERE token_sha256 = ?",
            (_fingerprint(token),)).fetchone()
    finally:
        conn.close()
    return str(row[0]) if row else None


def tokens_held_by(device_id: str) -> int:
    """Combien de jetons cet appareil détient. Sert à dire, dans la réponse au
    retrait, si la coupure va vraiment mordre : un appareil qui n'en a aucun ne
    tient que par le jeton commun, et celui-là ne se coupe pas
    individuellement."""
    conn = get_connection()
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM device_tokens WHERE device_id = ?",
            (device_id,)).fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def forget_device(device_id: str) -> int:
    """Détruire les jetons d'un appareil, définitivement.

    N'est PAS ce qu'un retrait appelle. Le retrait laisse la ligne en place
    exprès : c'est elle qui permet de reconnaître le porteur et de lui répondre
    « tu as été retiré » plutôt qu'un 401 indistinguable d'un jeton erroné —
    lequel enverrait l'utilisateur ressaisir une clé qui n'y est pour rien. Un
    jeton d'appareil retiré n'ouvre plus rien de toute façon.

    Réservé au jour où un appareil est oublié pour de bon.
    """
    conn = get_connection()
    try:
        ensure_schema(conn)
        with conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM device_tokens WHERE device_id = ?",
                (device_id,)).fetchone()
            removed = int(row[0]) if row else 0
            conn.execute(
                "DELETE FROM device_tokens WHERE device_id = ?", (device_id,))
    finally:
        conn.close()
    if removed:
        log.info("jetons détruits pour l'appareil %s (%d)", device_id, removed)
    return removed
