"""La découpe train/test ne doit rien laisser fuiter.

Deux propriétés, et la première ne se voit pas en regardant les identifiants.

Le corpus réutilise VOLONTAIREMENT la même capture sous plusieurs identifiants,
pour éprouver des axes différents : « acheter du pain » est à la fois `p1` et
`g-ephemeral-trivial`. Une découpe qui sépare les identifiants laisse donc le
même TEXTE des deux côtés, et le modèle retrouve au test une phrase apprise.
Mesuré le 2026-09-01 sur la première version : six textes fuyaient, et le score
de test s'en trouvait gonflé sans que rien ne le signale.

La seconde est l'inverse d'une fuite : les deux côtés de chaque frontière
doivent rester à l'ENTRAÎNEMENT. Si on entraîne sur le corpus, le corpus devient
la spécification, et une règle qu'il ne démontre pas n'existera plus pour
personne.
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.entrainement.construire import decouper  # noqa: E402
from scripts.parity.corpus import SETS  # noqa: E402


def _cas() -> dict:
    cas = {}
    for jeu, liste in SETS.items():
        for c in liste:
            c["set_"] = jeu
            cas[c["id"]] = c
    return cas


def test_aucun_texte_ne_traverse_la_decoupe():
    cas = _cas()
    train, test = decouper(cas, sorted(cas), 0.20, 13)
    assert not (train & test), "un identifiant ne peut pas être des deux côtés"
    par_texte = collections.defaultdict(list)
    for i in train | test:
        par_texte[cas[i]["text"].strip().lower()].append(i)
    fuites = {t: ids for t, ids in par_texte.items()
              if any(i in train for i in ids) and any(i in test for i in ids)}
    assert not fuites, f"textes à cheval sur train et test : {list(fuites.values())[:5]}"


def test_les_frontieres_restent_a_lentrainement():
    cas = _cas()
    train, test = decouper(cas, sorted(cas), 0.20, 13)
    en_test = [i for i in test if cas[i].get("frontiere")]
    assert not en_test, (
        "une frontière est passée en test : la spécification devient trouée, "
        f"{en_test[:5]}")


def test_la_decoupe_est_reproductible():
    """Même graine, même découpe. Sans ça, comparer deux entraînements ne veut
    rien dire : ils n'auraient pas été jugés sur les mêmes cas."""
    cas = _cas()
    a = decouper(cas, sorted(cas), 0.20, 13)
    b = decouper(cas, sorted(cas), 0.20, 13)
    assert a == b
