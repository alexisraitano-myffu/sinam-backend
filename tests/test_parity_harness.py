"""
Le harnais de parité mesure le classifieur. Ces tests mesurent le HARNAIS.

Ils tournent HORS LIGNE : aucun appel de modèle, aucune base, aucune clé. Ils
comparent des listes entre elles.

## Pourquoi ils existent

Le harnais recopie à la main quatre choses du core, et rien ne vérifiait
qu'elles correspondaient. Le piège s'est déclenché trois fois en trois jours :

- `obsoleted_facts` ajouté au core, absent de la liste de fusion du harnais.
  Les cinq cas de négation sortaient « négation absente » alors que la
  production la voyait.
- `resources`, exactement la même ligne, le même symptôme sur sept cas. Un
  commentaire avertissant du piège avait pourtant été écrit juste au-dessus la
  veille.
- `revue.ORDRE` n'avait pas suivi les axes ajoutés la veille : revoir un cas
  ressource aurait SUPPRIMÉ ses trois axes, en silence.

Le mode d'échec est le pire possible pour un outil de mesure. Le modèle répond
juste, la production marche, et le harnais annonce une régression. On corrige
alors ce qui marchait. Le commentaire d'avertissement a démontré qu'il ne
protège rien : il faut un test.

## Ce que ces tests NE couvrent pas

`score.porte_de_creation` et `score.porte_du_fait` sont des RÉÉCRITURES en
Python de deux portes du Rust, pas des copies. Aucune comparaison de source ne
peut les valider, et il vaut mieux l'écrire ici que laisser croire à une
couverture complète. Quand une de ces portes bouge côté Rust, seul un humain
peut faire bouger l'autre.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.parity import corpus, revue, score  # noqa: E402

# Le core est un dépôt VOISIN, pas une dépendance. Sur une machine qui n'a que
# le backend, le test de fusion se saute au lieu d'échouer : un test rouge pour
# un fichier absent apprend aux gens à ignorer le rouge.
_CORE_LLM = (Path(__file__).resolve().parents[2]
             / "sinam-core" / "crates" / "sinam-core" / "src" / "llm.rs")


def test_ordre_de_revue_couvre_tous_les_champs():
    """Écrire un cas doit le rendre RELISIBLE, pas seulement complet.

    `revue._serialiser` reconstruit la ligne du cas en suivant ORDRE, puis
    recopie en fin de ligne ce qu'ORDRE ne nomme pas : un axe oublié ici n'est
    donc plus perdu. Il est mal placé, et c'est ce que ce test défend — deux cas
    voisins doivent se comparer à l'œil, ce qui cesse d'être vrai dès que les
    axes ouverts s'entassent à la fin dans l'ordre où on les a écrits.
    """
    manquants = corpus.CHAMPS - set(revue.ORDRE)
    assert not manquants, (
        f"champs absents de revue.ORDRE : {sorted(manquants)}. Ils survivent "
        f"en fin de ligne, mais le corpus ne se relit plus en colonnes."
    )


def test_ordre_de_revue_n_invente_pas_de_champ():
    """L'inverse : un nom dans ORDRE qui n'est pas un champ déclaré est une
    faute de frappe qui ne se verra jamais, ORDRE ignorant silencieusement les
    clés absentes du cas."""
    inconnus = set(revue.ORDRE) - corpus.CHAMPS
    assert not inconnus, (
        f"noms inconnus dans revue.ORDRE : {sorted(inconnus)}"
    )


def test_les_axes_de_score_sont_des_champs_declares():
    """Un axe dont le nom n'est pas un champ déclaré ne lèvera rien : il ne
    vérifiera simplement jamais rien, et le cas passera pour vert en n'ayant
    rien mesuré. C'est le mode d'échec le plus coûteux d'un corpus."""
    inconnus = set(score.AXES) - corpus.CHAMPS
    assert not inconnus, (
        f"axes de score qui ne correspondent à aucun champ : {sorted(inconnus)}"
    )


_CORE_SCHEMA = (Path(__file__).resolve().parents[2]
                / "sinam-core" / "crates" / "sinam-core" / "src" / "schema.rs")


def test_types_semes_identiques_partout():
    """Quatrième occurrence du même piège, trouvée le 27/08.

    La liste des types d'entité est recopiée à la main à QUATRE endroits :
    `schema.rs` la sème en base, `llm.rs::FALLBACK_TYPES` la répète pour le cas
    dégradé, `api/app.py::EntityType` valide les éditions de fiche, et
    `lang_harness._BUILTIN_TYPES` la fige pour le harnais. Le 26/08, `resource`
    a été ajouté au premier et à aucun des autres : la fiche existait, et la
    route d'édition refusait de la typer.

    `schema.rs` fait foi, les autres doivent le suivre à l'identique.
    """
    if not _CORE_SCHEMA.is_file():
        import pytest
        pytest.skip(f"dépôt core absent ({_CORE_SCHEMA})")

    source = _CORE_SCHEMA.read_text()
    corps = source[source.index("for builtin in ["):]
    semes = re.findall(r'"([a-z_]+)"', corps[:corps.index("]")])
    assert semes, "la liste des builtins de schema.rs est introuvable"

    from scripts import lang_harness
    assert lang_harness._BUILTIN_TYPES == semes, (
        "le contexte figé du harnais a décroché des types semés : "
        f"{lang_harness._BUILTIN_TYPES} vs {semes}")

    llm = (_CORE_SCHEMA.parent / "llm.rs").read_text()
    repli = llm[llm.index("const FALLBACK_TYPES"):]
    assert re.findall(r'"([a-z_]+)"', repli[:repli.index(";")]) == semes, (
        "FALLBACK_TYPES a décroché des types semés : un core dégradé annoncerait "
        "au modèle un vocabulaire plus étroit que le sien.")

    app = (Path(__file__).resolve().parents[1] / "api" / "app.py").read_text()
    lit = app[app.index("EntityType = Literal["):]
    assert re.findall(r'"([a-z_]+)"', lit[:lit.index("]")]) == semes, (
        "EntityType a décroché des types semés : une fiche existerait sans qu'on "
        "puisse la typer à la main.")


def _cles_de_fusion_du_core() -> list[str]:
    """La liste `for key in [...]` de `llm.rs::merge_halves`."""
    source = _CORE_LLM.read_text()
    corps = source[source.index("pub fn merge_halves"):]
    m = re.search(r'for key in \[([^\]]+)\]', corps)
    assert m, "le `for key in [...]` de merge_halves est introuvable"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_liste_de_fusion_identique_au_core():
    """LE test de ce fichier, celui qui a coûté deux jours.

    Attention à ce qu'on compare : les deux fusions ne sont PAS symétriques, et
    c'est exactement la cause du bug. Le core copie TOUTES les clés du graphe
    puis laisse la note écraser ; sa liste ne sert qu'à garantir un tableau vide.
    Le harnais, lui, ne copie QUE les clés listées. Une clé nouvelle disparaît
    donc côté harnais et pas côté production — et comparer les comportements
    passerait au vert pendant que le bug est là. On compare les LISTES.
    """
    if not _CORE_LLM.is_file():
        import pytest
        pytest.skip(f"dépôt core absent ({_CORE_LLM}) : rien à comparer")

    from scripts.parity import split
    source = Path(split.__file__).read_text()
    m = re.search(r'for k in \(([^)]+)\)', source)
    assert m, "le `for k in (...)` de split.py est introuvable"
    harnais = re.findall(r'"([^"]+)"', m.group(1))

    assert harnais == _cles_de_fusion_du_core(), (
        "la liste de fusion du harnais a décroché de celle du core. "
        "Le harnais jettera en silence tout champ qui manque ici, et chaque cas "
        "qui l'asserte sortira en écart alors que la production, elle, le voit."
    )


def test_les_axes_disent_ce_que_la_citation_dit():
    """Quand un `why` cite Alexis entre guillemets sur la validation, l'axe
    `needs_review` doit dire la même chose que la citation.

    Mesuré le 2026-08-30 : cinq cas portaient l'inverse de la phrase citée juste
    au-dessus, dont trois avec le drapeau exactement retourné. Ils venaient tous
    de la passe de réétiquetage du matin, qui touchait un autre axe. Une passe
    qui déplace un axe en déplace d'autres par ricochet, et rien ne le signale.

    Volontairement étroit : seules les formulations sans ambiguïté sont testées,
    pour que le garde n'ait jamais à être arbitré.
    """
    import json
    from pathlib import Path

    SANS = ("pas besoin de validation", "pas de validation necessaire",
            "pas de validation nécessaire")
    AVEC = ("avec validation", "on veut une validation")

    fautes = []
    for f in sorted((Path(__file__).resolve().parents[1] / "scripts" / "parity" / "corpus").glob("*.jsonl")):
        for ligne in f.read_text(encoding="utf-8").splitlines():
            if not ligne.strip():
                continue
            cas = json.loads(ligne)
            why = (cas.get("why") or "").lower()
            if "tu avais écrit" not in why:
                continue
            cite = why[why.index("tu avais écrit"):]
            if any(m in cite for m in SANS) and cas.get("needs_review"):
                fautes.append(f"{cas['id']} : la citation dit non, l'axe dit oui")
            if any(m in cite for m in AVEC) and not cas.get("needs_review"):
                fautes.append(f"{cas['id']} : la citation dit oui, l'axe dit non")

    assert not fautes, "axes en désaccord avec la citation :\n  " + "\n  ".join(fautes)


def test_aucun_axe_ne_porte_le_nom_de_sa_propre_cle():
    """Un gabarit resté en place se lit comme une étiquette et ne s'attrape pas.

    `g-ord-en-005` portait `rel: "rel"`, c'est-à-dire le nom de la clé recopié
    en valeur par le générateur. Le cas ne pouvait jamais passer, et rien ne le
    disait : il ressemblait à une exigence que le modèle n'atteignait pas. Il a
    survécu à une validation humaine sous cette forme, ce qui montre bien que
    l'œil ne le voit pas.
    """
    import json
    fautifs = []
    for f in sorted((Path(__file__).resolve().parents[1] / "scripts" / "parity" / "corpus").glob("*.jsonl")):
        for ligne in f.read_text().splitlines():
            if not ligne.strip():
                continue
            cas = json.loads(ligne)
            for cle, valeur in cas.items():
                for x in (valeur if isinstance(valeur, list) else [valeur]):
                    if isinstance(x, str) and x == cle:
                        fautifs.append(f"{f.name}:{cas['id']} {cle}={x!r}")
    assert not fautifs, "axes dont la valeur est le nom de leur clé : " + ", ".join(fautifs)
