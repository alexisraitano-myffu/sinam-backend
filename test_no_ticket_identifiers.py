"""Ce dépôt est public : aucun identifiant de ticket dans les fichiers commités.

Un identifiant nu renvoie à un tableau que le lecteur ne peut pas ouvrir, et il
publie la cadence d'un backlog privé. La règle est écrite dans les deux
`CLAUDE.md` ; ce test est ce qui l'empêche de rester une intention.

Ce qu'il ne couvre PAS, et qui reste à la main : les messages de commit, et
l'historique déjà poussé.
"""
import re
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent
IDENTIFIANT = re.compile(rb"SYN-\d+")

# Le corpus de parité rejoue des captures réalistes ; une capture peut nommer un
# outil de suivi sans que ce soit un identifiant du backlog de ce dépôt.
EXEMPTS = {"test_no_ticket_identifiers.py"}


def fichiers_suivis() -> list[str]:
    sortie = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RACINE, capture_output=True, check=True
    ).stdout
    return [f.decode() for f in sortie.split(b"\0") if f]


@pytest.mark.skipif(
    not (RACINE / ".git").exists(), reason="hors d'une copie de travail git"
)
def test_aucun_identifiant_de_ticket_dans_les_fichiers_commites():
    fautifs = []
    for nom in fichiers_suivis():
        if nom in EXEMPTS:
            continue
        chemin = RACINE / nom
        try:
            octets = chemin.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            continue  # sous-module, ou fichier supprimé mais encore indexé
        if b"\0" in octets[:8192]:
            continue  # binaire
        for numero, ligne in enumerate(octets.split(b"\n"), 1):
            if IDENTIFIANT.search(ligne):
                fautifs.append(f"{nom}:{numero}: {ligne.decode(errors='replace').strip()[:120]}")

    assert not fautifs, (
        "identifiants de ticket dans des fichiers commités — écris la raison, pas "
        "le numéro (cf. CLAUDE.md) :\n  " + "\n  ".join(fautifs[:20])
    )
