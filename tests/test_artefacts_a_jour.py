"""La roue installée est-elle celle du dépôt d'aujourd'hui ?

Le 30/08, la réponse était non pendant deux jours et rien ne pouvait le dire.
La roue du venv datait d'avant un relèvement de palier dans le routage, donc la
suite affichait 197 verts en validant un comportement que le cœur n'appliquait
plus. La version du paquet ne sert à rien pour ça : `sinam_core` reste en 0.1.0
d'une construction à l'autre.

Le cœur grave donc à la compilation une empreinte du CONTENU de ses sources, et
ce fichier la recalcule depuis le dépôt voisin. Un hash de commit ne suffirait
pas : il dirait « à jour » sur un arbre modifié et pas encore commité, ce qui
est l'état normal d'une journée de travail.

⚠ Ces tests se SAUTENT quand les sources du cœur sont absentes, ils n'échouent
jamais. Un utilisateur installe la roue sans avoir le dépôt à côté, et un rouge
pour un fichier absent apprend à ignorer le rouge.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_CORE = Path(__file__).resolve().parents[2] / "sinam-core"
_CRATES = _CORE / "crates"


def _sans_les_tests(source: str) -> str:
    """Le contenu d'un fichier avant son bloc de tests.

    Les tests ne changent aucun comportement : les hacher ferait rougir ce
    garde-fou sur une modification qui ne peut rien casser, et un rouge qu'on
    apprend à ignorer ne garde plus rien. Mesuré le 2026-09-01, retirer sept
    fixtures périmées suffisait à déclarer la roue en retard.
    """
    i = source.find("\n#[cfg(test)]")
    if i >= 0:
        return source[:i + 1]
    return "" if source.startswith("#[cfg(test)]") else source


def _empreinte_du_depot() -> str:
    """Le miroir exact de `crates/sinam-core-py/build.rs`.

    Toute divergence entre les deux rendrait ce test rouge en permanence, donc
    faux, donc ignoré. Les quatre choses qui doivent coïncider mot pour mot :
    les deux dossiers parcourus et leurs préfixes, le tri par chemin relatif,
    la troncature au bloc de tests, et le séparateur nul entre chemin et
    contenu.
    """
    fichiers: list[tuple[str, Path]] = []
    for dossier, prefixe in ((_CRATES / "sinam-core" / "src", "sinam-core"),
                             (_CRATES / "sinam-core-py" / "src", "sinam-core-py")):
        for chemin in dossier.rglob("*.rs"):
            rel = f"{prefixe}/{chemin.relative_to(dossier).as_posix()}"
            fichiers.append((rel, chemin))
    fichiers.sort(key=lambda x: x[0])
    h = hashlib.sha256()
    for rel, chemin in fichiers:
        h.update(rel.encode())
        h.update(b"\0")
        h.update(_sans_les_tests(chemin.read_text()).encode())
        h.update(b"\0")
    return h.hexdigest()[:12]


def test_la_roue_installee_est_celle_du_depot():
    if not (_CRATES / "sinam-core" / "src").is_dir():
        pytest.skip(f"dépôt core absent ({_CRATES})")
    import sinam_core

    attendu = _empreinte_du_depot()
    installe = sinam_core.empreinte_source()
    assert installe == attendu, (
        f"la roue installée porte l'empreinte {installe}, le dépôt {attendu}. "
        "Elle a été construite avant les sources actuelles, donc ce que cette "
        "suite mesure n'est pas ce que le cœur fait. Reconstruire :\n"
        "  cd sinam-core/crates/sinam-core-py && maturin build --release\n"
        "  pip install --force-reinstall --no-deps "
        "sinam-core/target/wheels/sinam_core-*.whl"
    )


def test_les_prompts_deployes_ne_sont_pas_en_retard():
    """Le piège `prepareAppResources` : réinstaller le binaire bundlé recopie
    les prompts de son paquet dans SYNAPSE_HOME, ce qui peut faire RECULER la
    version déployée. Les fichiers portent alors la date du jour, donc rien ne
    se voit : le 30/08, le déployé était en 17 contre 32 au dépôt, et ce Mac
    classait avec un prompt de deux semaines.
    """
    import sinam_core

    maison = Path(os.environ.get("SYNAPSE_HOME", Path.home() / ".synapse"))
    manifeste = maison / "prompts" / "manifest.json"
    if not manifeste.is_file():
        pytest.skip(f"aucun prompt déployé ({manifeste})")

    deploye = json.loads(manifeste.read_text()).get("version", 0)
    attendu = sinam_core.version_prompts_attendue()
    assert deploye >= attendu, (
        f"prompts déployés en version {deploye}, le cœur en attend {attendu}. "
        f"Recopier ceux du dépôt vers {maison / 'prompts'}."
    )


def test_un_seul_bloc_de_tests_par_fichier_du_coeur():
    """La convention qui rend la troncature sûre.

    L'empreinte ignore tout ce qui suit le premier `#[cfg(test)]`. Ça ne vaut
    que si chaque fichier n'en a qu'un, et en fin de fichier — c'est le cas des
    quinze aujourd'hui. Un deuxième bloc placé au milieu ferait disparaître du
    VRAI code de l'empreinte, en silence, et la garde cesserait de garder sans
    que rien ne rougisse.
    """
    if not (_CRATES / "sinam-core" / "src").is_dir():
        pytest.skip(f"dépôt core absent ({_CRATES})")
    fautifs = []
    for dossier in ("sinam-core", "sinam-core-py"):
        for chemin in (_CRATES / dossier / "src").rglob("*.rs"):
            n = chemin.read_text().count("\n#[cfg(test)]")
            if n > 1:
                fautifs.append(f"{chemin.name} ({n} blocs)")
    assert not fautifs, (
        "plusieurs blocs de tests dans un même fichier : l'empreinte tronque au "
        "premier et perdrait du vrai code — " + ", ".join(fautifs))
