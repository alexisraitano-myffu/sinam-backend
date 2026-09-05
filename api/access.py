"""Le jeton d'accès au backend : d'où il vient, et pourquoi il n'y a plus de
repli silencieux.

Le backend écoute sur `0.0.0.0` et s'annonce en mDNS. Sans jeton, n'importe
quel appareil du même Wi-Fi lit et écrit toute la mémoire, et le contrôle
d'authentification retournait précisément « rien à vérifier » quand aucun jeton
n'était configuré. C'était censé n'arriver qu'en développement ; ça arrivait sur
une machine réelle, servie au réseau, sans que rien ne le signale.

L'ordre de résolution, désormais :

1. `SYNAPSE_API_TOKEN` s'il est posé (LaunchAgent, tâche planifiée, shell) ;
2. sinon le jeton déjà persisté dans `SYNAPSE_HOME/api_token` — le relire AVANT
   d'en fabriquer un est ce qui évite de désappairer les clients déjà
   configurés à chaque réinstallation ;
3. sinon un jeton neuf, écrit là en 0600 et annoncé dans le log.

`SYNAPSE_DEV_NO_AUTH=1` coupe l'authentification, explicitement, jamais par
omission — et un jeton posé dans l'environnement l'emporte sur ce drapeau, pour
qu'un test qui veut vraiment de l'auth en ait. Le démarrage crie si le mode
ouvert est actif ailleurs que sur la boucle locale.
"""

import logging
import os
import secrets
from pathlib import Path

log = logging.getLogger(__name__)

# Un jeton fabriqué est relu ensuite depuis le fichier ; le cache évite d'aller
# sur le disque à chaque requête, et il est indexé par chemin pour qu'un
# SYNAPSE_HOME déplacé (les tests) ne serve pas le jeton d'un autre.
_cache: dict[str, str] = {}


def dev_no_auth() -> bool:
    return bool(os.environ.get("SYNAPSE_DEV_NO_AUTH"))


def token_path() -> Path:
    """Lu à l'appel, pas à l'import : `SYNAPSE_HOME` bouge sous les tests."""
    home = os.environ.get("SYNAPSE_HOME")
    base = Path(home) if home else Path.home() / ".synapse"
    return base / "api_token"


def resolve_token() -> str | None:
    """Le jeton que le backend accepte et présente. None seulement en mode
    développement explicite."""
    env = os.environ.get("SYNAPSE_API_TOKEN")
    if env:
        return env
    if dev_no_auth():
        return None
    path = token_path()
    key = str(path)
    if key not in _cache:
        _cache[key] = _read_or_create(path)
    return _cache[key]


def _read_or_create(path: Path) -> str:
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 0600 dès la création : pas de fenêtre où le jeton serait lisible.
        fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(fd, token.encode("utf-8"))
        finally:
            os.close(fd)
        log.warning(
            "aucun jeton configuré : un jeton d'accès a été créé dans %s. "
            "Il est à recopier dans l'app pour que cet appareil parle au backend.",
            path)
    except OSError as exc:
        # Écrire est impossible (disque en lecture seule, droits) : on garde
        # quand même un jeton en mémoire. Il changera au prochain démarrage,
        # ce qui est gênant mais reste préférable à servir sans jeton.
        log.error("jeton d'accès non persistable dans %s (%s) : il ne survivra "
                  "pas au redémarrage", path, exc)
    return token


def harden_home(home: Path) -> None:
    """Resserrer les droits du dossier de données, et de la base elle-même.

    La base était en 0644 dans un dossier 0755 : lisible par tout processus de
    la machine, quel que soit l'utilisateur. Sur un Mac personnel ça veut dire
    que n'importe quelle application installée peut lire la mémoire entière
    sans rien demander à personne — ce dossier n'est pas couvert par les
    protections de macOS, qui ne visent que Documents, Bureau et
    Téléchargements. FileVault, lui, ne protège que machine éteinte.

    Le jeton d'accès était déjà créé en 0600 ; la mémoire, non. C'était
    l'inverse de la hiérarchie qu'on veut.

    Meilleur effort et silencieux : un système de fichiers qui ne porte pas ces
    droits (un volume monté, un partage) ne doit pas empêcher le backend de
    démarrer.
    """
    try:
        home.mkdir(parents=True, exist_ok=True)
        os.chmod(home, 0o700)
    except OSError:
        return
    for name in ("synapse.db", "synapse.db-wal", "synapse.db-shm", "api_token"):
        try:
            target = home / name
            if target.exists():
                os.chmod(target, 0o600)
        except OSError:
            pass


def warn_if_open(host: str) -> None:
    """Crié au démarrage : le mode ouvert sur autre chose que la boucle locale
    est exactement la configuration qui a laissé fuiter une mémoire entière."""
    if not dev_no_auth():
        return
    if host in ("127.0.0.1", "localhost", "::1"):
        log.warning("SYNAPSE_DEV_NO_AUTH : authentification désactivée (boucle locale)")
        return
    log.error(
        "SYNAPSE_DEV_NO_AUTH est actif ET le serveur écoute sur %s : toute "
        "l'API, mémoire comprise, est ouverte à quiconque partage ce réseau.",
        host)
