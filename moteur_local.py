"""Le moteur local : l'installer à la demande, le lancer le temps d'un cycle.

Trois morceaux, décrits par un manifeste publié à côté des installeurs :
le moteur (le serveur mlx_lm empaqueté, `moteur_entry.py`), les poids du modèle
et l'adaptateur entraîné. Rien n'est livré avec l'app : seul celui qui choisit
le tri local télécharge ~3 Go.

Le moteur ne tourne PAS en permanence. Le modèle occupe ~3 Go de mémoire, sur des
machines qui peuvent n'en avoir que 8 : on le lance au début d'un cycle et on
l'arrête à la fin (`session()`). Le prix est un démarrage de quelques secondes
par cycle, contre 3 Go rendus le reste de la journée.
"""
import contextlib
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
from pathlib import Path

from config import BASE_DIR

MANIFESTE_URL = os.environ.get(
    "SYNAPSE_MOTEUR_MANIFESTE",
    "https://pub-91e19c4a15ec4d9ab1a26673a2b7c0ce.r2.dev/moteur-local/manifeste.json",
)
# Les trois morceaux, chacun dans son dossier, dans cet ordre de téléchargement.
MORCEAUX = ("moteur", "modele", "adaptateur")
# En dessous, le système swappe pendant le cycle au point de le rendre inutilisable.
MEMOIRE_MIN = 8 * 1024 ** 3
DEMARRAGE_MAX_S = 180


def dossier() -> Path:
    # Relu à chaque appel : les tests déplacent SYNAPSE_HOME.
    return Path(os.getenv("SYNAPSE_HOME", BASE_DIR)) / "moteur-local"


def _installe_json() -> Path:
    return dossier() / "installe.json"


# ── Ce que la machine sait faire ─────────────────────────────────────────────

def _memoire_totale() -> int | None:
    try:
        return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                  text=True, timeout=5).stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def compatibilite() -> str | None:
    """None si la machine peut faire tourner le moteur, sinon la raison, dite
    pour l'utilisateur. MLX n'existe que sur les puces Apple."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return "Le tri local demande pour l'instant un Mac à puce Apple."
    mem = _memoire_totale()
    if mem is not None and mem < MEMOIRE_MIN:
        return "Le tri local demande au moins 8 Go de mémoire."
    return None


# ── État et installation ─────────────────────────────────────────────────────

_verrou = threading.Lock()
_progression: dict = {"etat": None}


def etat() -> dict:
    """Ce que l'app affiche. `etat` vaut `incompatible`, `absent`,
    `telechargement`, `installe` ou `erreur`."""
    raison = compatibilite()
    if raison:
        return {"etat": "incompatible", "raison": raison}
    with _verrou:
        p = dict(_progression)
    if p.get("etat") in ("telechargement", "erreur"):
        return p
    try:
        info = json.loads(_installe_json().read_text())
        return {"etat": "installe", "version": info.get("version"),
                "taille": info.get("taille")}
    except (OSError, ValueError):
        return {"etat": "absent"}


def est_installe() -> bool:
    return etat()["etat"] == "installe"


def _poser(**champs) -> None:
    with _verrou:
        _progression.clear()
        _progression.update(champs)


def _telecharger(url: str, cible: Path, sha256: str, deja: int, total: int) -> None:
    """Télécharge `url` dans `cible`, en reprenant un `.part` interrompu, et
    vérifie l'empreinte. 3 Go sur un wifi de testeuse coupent : reprendre
    évite de tout recommencer."""
    part = cible.with_name(cible.name + ".part")
    recu = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={recu}-"} if recu else {})
    with urllib.request.urlopen(req, timeout=60) as rep:
        if recu and rep.status != 206:        # le serveur ignore la reprise
            recu = 0
        with open(part, "ab" if recu else "wb") as f:
            while bloc := rep.read(1 << 20):
                f.write(bloc)
                recu += len(bloc)
                _poser(etat="telechargement", recu=deja + recu, total=total)
    h = hashlib.sha256()
    with open(part, "rb") as f:
        while bloc := f.read(1 << 20):
            h.update(bloc)
    if h.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise ValueError(f"empreinte fausse pour {cible.name} : fichier supprimé, à retenter")
    part.replace(cible)


def _installer() -> None:
    racine = dossier()
    racine.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(MANIFESTE_URL, timeout=30) as rep:
        manif = json.load(rep)
    fichiers = manif["fichiers"]
    total = sum(f["taille"] for f in fichiers)
    deja = 0
    for f in fichiers:
        if f["role"] not in MORCEAUX:
            raise ValueError(f"morceau inconnu dans le manifeste : {f['role']!r}")
        archive = racine / f"{f['role']}.tar"
        if not archive.exists():
            _telecharger(f["url"], archive, f["sha256"], deja, total)
        deja += f["taille"]
        # Extraire à côté puis renommer : un dossier à moitié extrait ne doit
        # jamais passer pour un morceau installé.
        tmp = racine / f"{f['role']}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        shutil.rmtree(racine / f["role"], ignore_errors=True)
        tmp.replace(racine / f["role"])
        archive.unlink()
    binaire = racine / "moteur" / "sinam-moteur" / "sinam-moteur"
    binaire.chmod(0o755)
    _installe_json().write_text(json.dumps({"version": manif["version"], "taille": total}))


def installer_en_fond() -> dict:
    """Lance l'installation si elle n'est pas déjà en cours. L'app suit
    l'avancement par `etat()`."""
    raison = compatibilite()
    if raison:
        return {"etat": "incompatible", "raison": raison}
    with _verrou:
        if _progression.get("etat") == "telechargement":
            return dict(_progression)
        _progression.clear()
        _progression.update(etat="telechargement", recu=0, total=None)

    def tache():
        try:
            _installer()
            _poser(etat=None)
        except Exception as e:  # noqa: BLE001 — dit à l'utilisateur, jamais avalé
            _poser(etat="erreur", erreur=f"{type(e).__name__}: {e}")

    threading.Thread(target=tache, daemon=True, name="moteur-local-install").start()
    return etat()


def desinstaller() -> None:
    shutil.rmtree(dossier(), ignore_errors=True)
    _poser(etat=None)


# ── Le serveur, le temps d'un cycle ──────────────────────────────────────────

_session_verrou = threading.Lock()
_session_proc: subprocess.Popen | None = None
_session_niveau = 0


def _pret(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/v1/models", timeout=2) as rep:
            return rep.status == 200
    except OSError:
        return False


@contextlib.contextmanager
def session():
    """Moteur lancé à l'entrée, arrêté à la sortie. Réentrant : le résumé de la
    semaine appelé pendant un cycle réutilise le moteur déjà chargé.

    Un moteur qui ne démarre pas lève ConnectionError, que le cycle traite comme
    une coupure réseau : run interrompu, captures laissées en file, et surtout
    aucun repli vers le cloud."""
    import llm_target

    global _session_proc, _session_niveau
    base = llm_target.local_base_url()
    with _session_verrou:
        if _session_niveau == 0:
            if _pret(base):
                # Déjà servi (développement : un serveur lancé à la main).
                _session_proc = None
            else:
                _session_proc = _lancer(base)
        _session_niveau += 1
    try:
        yield
    finally:
        with _session_verrou:
            _session_niveau -= 1
            if _session_niveau == 0 and _session_proc is not None:
                _session_proc.terminate()
                try:
                    _session_proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    _session_proc.kill()
                _session_proc = None


def _lancer(base: str) -> subprocess.Popen:
    if not est_installe():
        raise ConnectionError("tri local choisi mais moteur local absent : "
                              "l'installer depuis Réglages → Tri")
    racine = dossier()
    port = base.rsplit(":", 1)[1]
    journal = open(Path(os.getenv("SYNAPSE_HOME", BASE_DIR)) / "moteur-local.log", "ab")
    proc = subprocess.Popen(
        [str(racine / "moteur" / "sinam-moteur" / "sinam-moteur"),
         "--model", str(racine / "modele"),
         "--adapter-path", str(racine / "adaptateur"),
         "--port", port],
        stdout=journal, stderr=subprocess.STDOUT,
    )
    fin = time.monotonic() + DEMARRAGE_MAX_S
    while time.monotonic() < fin:
        if proc.poll() is not None:
            raise ConnectionError(f"le moteur local s'est arrêté au démarrage "
                                  f"(code {proc.returncode}), voir moteur-local.log")
        if _pret(base):
            return proc
        time.sleep(1)
    proc.kill()
    raise ConnectionError(f"le moteur local ne répond pas après {DEMARRAGE_MAX_S} s")
