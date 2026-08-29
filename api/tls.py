"""Le certificat du lien local : fabrication, empreinte, et pourquoi il est
auto-signé.

Le backend et l'app se parlent par ADRESSE IP, sur un réseau domestique, sans
nom de domaine et sans autorité de certification joignable. Aucune autorité ne
peut donc signer quoi que ce soit d'utile ici, et vérifier un nom d'hôte n'a
aucun sens face à un `192.168.1.x` qui change de réseau en réseau.

La confiance vient d'ailleurs : l'empreinte SHA-256 du certificat voyage dans
la charge d'appairage, déjà chiffrée et authentifiée de bout en bout par
l'échange de clés du QR ou du code. Le client épingle cette empreinte et
n'accepte que ce certificat-là. C'est la forme habituelle du « trust on first
use » quand le premier contact, lui, est authentifié par autre chose : ici, le
fait d'avoir eu le QR sous les yeux.

Le certificat vit dans `SYNAPSE_HOME`, à côté du jeton d'accès, et survit donc
aux réinstallations : le refabriquer invaliderait l'empreinte épinglée par tous
les appareils déjà appairés, exactement comme refabriquer le jeton les
désappairerait.
"""

import datetime as _dt
import hashlib
import ipaddress
import logging
import os
import socket
from pathlib import Path

log = logging.getLogger(__name__)

# Dix ans : ce certificat n'est révoqué par personne et n'est vérifié que par
# son empreinte. Une expiration courte n'apporterait aucune sécurité ici, elle
# ne ferait que casser la sync un matin sans prévenir.
_VALIDITY_DAYS = 3650


def _home() -> Path:
    home = os.environ.get("SYNAPSE_HOME")
    return Path(home) if home else Path.home() / ".synapse"


def cert_path() -> Path:
    return _home() / "tls_cert.pem"


def key_path() -> Path:
    return _home() / "tls_key.pem"


def tls_port() -> int:
    return int(os.environ.get("SYNAPSE_API_TLS_PORT", "8443"))


def _local_ips() -> list[str]:
    """Les adresses par lesquelles on peut nous joindre, pour les mettre en SAN.
    Le SAN d'IP ne sert pas à la vérification (le client épingle l'empreinte et
    ne vérifie aucun nom), mais un certificat sans SAN du tout fait tousser
    certaines piles avant même d'arriver à notre contrôle."""
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    return sorted(ips)


def ensure_cert() -> tuple[Path, Path] | None:
    """Le couple (certificat, clé), fabriqué au besoin. None si `cryptography`
    manque : le backend continue alors en clair plutôt que de ne pas démarrer."""
    cert, key = cert_path(), key_path()
    if cert.exists() and key.exists():
        return cert, key
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
    except ImportError:
        log.warning("cryptography absent : pas de TLS, le lien local reste en clair")
        return None

    private = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sinam local link")])
    now = _dt.datetime.now(_dt.timezone.utc)
    sans = [x509.IPAddress(ipaddress.ip_address(ip)) for ip in _local_ips()]
    sans.append(x509.DNSName("localhost"))
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=_VALIDITY_DAYS))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    certificate = builder.sign(private, hashes.SHA256())

    cert.parent.mkdir(parents=True, exist_ok=True)
    key_bytes = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(str(key), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, key_bytes)
    finally:
        os.close(fd)
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    log.warning("certificat du lien local créé dans %s (empreinte %s)",
                cert, fingerprint())
    return cert, key


def fingerprint() -> str | None:
    """L'empreinte SHA-256 du certificat, en hexadécimal minuscule sans
    séparateur. C'est elle qui part dans la charge d'appairage et que le client
    épingle ; elle ne dépend pas de la clé privée, donc la publier ne donne
    rien à personne, mais elle ne doit venir que d'un canal authentifié."""
    cert = cert_path()
    if not cert.exists():
        return None
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        der = x509.load_pem_x509_certificate(cert.read_bytes()).public_bytes(Encoding.DER)
    except Exception:  # noqa: BLE001 — pas de certificat lisible = pas d'empreinte
        return None
    return hashlib.sha256(der).hexdigest()
