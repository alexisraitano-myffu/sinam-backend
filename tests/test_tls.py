"""
Le certificat du lien local, et ce qui le rend utilisable : il existe, il n'est
pas refabriqué, sa clé n'est lisible que par nous, et son empreinte part dans
la charge d'appairage. Ni réseau, ni clé d'API.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNAPSE_HOME", str(tmp_path))
    monkeypatch.delenv("SYNAPSE_TLS_DISABLE", raising=False)
    return tmp_path


def test_the_certificate_is_created_with_a_private_key(home):
    from api import tls

    pair = tls.ensure_cert()
    assert pair is not None
    cert, key = pair
    assert cert.exists() and key.exists()
    mode = os.stat(key).st_mode & 0o777
    assert mode == 0o600, f"clé privée lisible par d'autres : {oct(mode)}"


def test_the_certificate_is_never_regenerated(home):
    """Le refabriquer invaliderait l'empreinte épinglée par tous les appareils
    déjà appairés — le même piège que régénérer le jeton d'accès."""
    from api import tls

    tls.ensure_cert()
    first = tls.fingerprint()
    tls.ensure_cert()
    assert tls.fingerprint() == first


def test_the_fingerprint_is_a_sha256_of_the_certificate(home):
    import hashlib

    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    from api import tls

    cert, _ = tls.ensure_cert()
    der = x509.load_pem_x509_certificate(cert.read_bytes()).public_bytes(Encoding.DER)
    assert tls.fingerprint() == hashlib.sha256(der).hexdigest()
    assert len(tls.fingerprint()) == 64


def test_no_certificate_means_no_fingerprint(home):
    from api import tls

    assert tls.fingerprint() is None


def test_the_pairing_offer_leads_with_the_encrypted_address(home, monkeypatch):
    from api import pairing, tls

    tls.ensure_cert()
    addrs = pairing._local_addrs()
    assert addrs, "au moins une adresse joignable"
    assert addrs[0].startswith("https://"), "le chiffré passe en tête"
    assert any(a.startswith("http://") for a in addrs), \
        "le clair reste en repli tant que des appareils ne savent pas épingler"

    # Sans TLS, on retombe sur le clair seul plutôt que d'annoncer une adresse
    # qui ne répondrait pas.
    monkeypatch.setenv("SYNAPSE_TLS_DISABLE", "1")
    addrs = pairing._local_addrs()
    assert addrs and all(a.startswith("http://") for a in addrs)


def test_the_qr_carries_the_certificate_fingerprint(home, monkeypatch):
    """L'empreinte voyage dans le QR pour que le joiner épingle AVANT le premier
    contact — sinon sa première poignée https bute sur un certificat inconnu et
    l'appairage d'un appareil neuf échoue. Elle reste HORS de `_local_addrs()` :
    ces adresses-là repartent dans la liste des peers scellée à l'appairage, où
    une sentinelle n'aurait rien à faire."""
    from api import pairing, tls

    tls.ensure_cert()
    fp = tls.fingerprint()

    assert f"fp:{fp}" in pairing._qr_addrs(), "la sentinelle d'empreinte est dans le QR"
    assert all(not a.startswith("fp:") for a in pairing._local_addrs()), \
        "l'empreinte ne doit pas entrer dans les adresses réutilisées comme peers"

    # Sans certificat à épingler, pas de sentinelle : rien à annoncer.
    monkeypatch.setenv("SYNAPSE_TLS_DISABLE", "1")
    assert all(not a.startswith("fp:") for a in pairing._qr_addrs())
