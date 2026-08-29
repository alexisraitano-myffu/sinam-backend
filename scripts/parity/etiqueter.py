"""Poser l'étiquette attendue sur des captures déjà écrites.

    python -m scripts.parity.generer R4b | python -m scripts.parity.etiqueter
    python -m scripts.parity.etiqueter brouillon.jsonl --modele anthropic:claude-opus-4-5

La seconde moitié d'un travail coupé en deux. `generer.py` écrit les captures
SANS voir les règles, pour ne pas se contenter d'illustrer ce que le moteur sait
déjà faire. Ce script fait l'inverse : il reçoit les deux prompts de production
en entier plus la carte des frontières, et n'a rien d'autre à faire que d'en
dériver la réponse attendue.

Ce qui était interdit à l'écriture est obligatoire ici, et c'est tout l'intérêt
de la coupure. Une étiquette écrite sans les règles est fausse une fois sur deux
— trois passes l'ont montré, chacune fausse d'une manière différente. Une
capture écrite avec les règles est inutile, et ça ne se voit jamais.

Un LOT est envoyé en un appel, pas une capture à la fois : les prompts pèsent
~15 000 tokens et sont identiques d'un cas à l'autre. Envoyés une fois, ils
franchissent le plancher du cache Haiku (~4 096 tokens) et sont relus au dixième
du prix ; envoyés par capture, ils se paient plein tarif à chaque fois.

La sortie va sur stdout et N'EST PAS écrite dans le corpus. Un cas entre par la
revue, à la main, jamais par un script.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import context, corpus, providers, score, split  # noqa: E402

_ICI = Path(__file__).resolve().parent


def savoir_complet() -> str:
    """Tout ce que l'étiqueteur a le droit de lire, en UN bloc.

    Un seul bloc, et pas quatre : `providers.call` ne pose le marqueur de cache
    que sur le premier. Quatre blocs ne feraient donc cacher que la consigne
    (~2 000 tokens), sous le plancher de Haiku, et les 15 000 tokens de prompts
    de production se paieraient plein tarif à chaque lot.
    """
    note = context.load_prompt(split._half_path("note.md"))
    graph = context.load_prompt(split._half_path("graph.md"))
    return "\n\n".join([
        (_ICI / "etiquetage.md").read_text(),
        "# Le prompt de production, moitié NOTE\n\n" + note,
        "# Le prompt de production, moitié GRAPHE\n\n" + graph,
        "# La carte des frontières\n\n" + (_ICI / "frontieres.md").read_text(),
    ])


_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_JOURS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
             "sunday")
# Le nom du jour → son index ISO, dans les deux langues du corpus.
_INDEX_JOUR = {nom: i for i, nom in enumerate(_JOURS)}
_INDEX_JOUR.update({nom: i for i, nom in enumerate(_JOURS_EN)})


def jour_nomme(texte: str) -> int | None:
    """L'index ISO du jour de semaine nommé dans une capture, s'il est unique.

    Un seul jour nommé, une seule lecture possible. Deux jours (« jeudi ou
    vendredi »), on ne vérifie rien : le contrôle doit se taire quand il ne
    sait pas, sinon il devient du bruit et on cesse de le lire.
    """
    trouves = {_INDEX_JOUR[m] for m in re.findall(
        r"[a-zéèêîôûàç]+", texte.lower()) if m in _INDEX_JOUR}
    return trouves.pop() if len(trouves) == 1 else None


def calendrier(avant: int = 9, apres: int = 16) -> str:
    """Les jours autour du temps de référence, nommés, un par ligne.

    Le modèle a résolu « avant jeudi » en 2026-07-17, qui est un vendredi. Une
    addition de jours faite de tête se trompe sans prévenir, et une étiquette
    datée à côté fait corriger un moteur qui avait raison. On ne demande donc
    plus l'arithmétique : on donne la table et on demande de la lire.

    La fenêtre couvre les deux sens, parce que le sens de résolution appartient
    au temps du verbe : « jeudi » regarde devant, « jeudi dernier » derrière.
    """
    zero = dt.date.fromisoformat(context.TODAY)
    lignes = []
    for delta in range(-avant, apres + 1):
        jour = zero + dt.timedelta(days=delta)
        repere = "  ← temps de référence" if delta == 0 else ""
        lignes.append(f"  {jour.isoformat()} {_JOURS[jour.weekday()]}{repere}")
    return "\n".join(lignes)


def lire_captures(source: Path | None) -> list[dict]:
    """Les captures à étiqueter, depuis un fichier ou stdin."""
    brut = source.read_text() if source else sys.stdin.read()
    captures = []
    for ligne in brut.splitlines():
        ligne = ligne.strip().strip("`")
        if not ligne.startswith("{"):
            continue
        try:
            captures.append(json.loads(ligne))
        except ValueError as e:
            print(f"⚠ ligne illisible ({e}) : {ligne[:80]}", file=sys.stderr)
    if not captures:
        raise SystemExit(
            "aucune capture reçue. Attendu : une ligne JSON par capture, sur "
            "stdin ou dans le fichier passé en argument.")
    return captures


# La question « que laisse cette capture » se pose en UN mot au modèle, et le
# corpus la range en deux champs. La traduction est mécanique, donc elle vit
# dans le code : posée au modèle, elle sortait fausse une fois sur six.
SOUVENIRS = {"aucun": (False, None)}
SOUVENIRS.update({k: (True, k) for k in score.VALID_NOTE_KINDS})


# Le modèle a les prompts de PRODUCTION sous les yeux, et ils nomment leurs
# sorties autrement que le corpus. Renommer sous son nez marche mieux que le lui
# interdire : c'est le même geste que `souvenir`, et pour la même raison.
_ALIAS_MOTEUR = {"event_recurring": "recurring", "is_ephemeral": "ephemeral",
                 "atomic_note_owner": "owner", "event_date": "event_date"}


def traduire_souvenir(cas: dict) -> int:
    """`souvenir` → (`note`, `kind`). Rend le nombre d'avertissements."""
    ident = cas.get("id", "?")
    alertes = 0
    for pose in ("note", "kind"):
        if pose in cas:
            print(f"⚠ {ident} : `{pose}` se déduit de `souvenir`, ne l'écris pas",
                  file=sys.stderr)
            del cas[pose]
            alertes += 1
    for moteur, ici in _ALIAS_MOTEUR.items():
        if moteur in cas and moteur != ici:
            cas.setdefault(ici, cas.pop(moteur))
            cas.pop(moteur, None)
    mot = cas.pop("souvenir", None)
    if mot is None:
        return alertes
    if mot not in SOUVENIRS:
        print(f"⚠ {ident} : souvenir={mot!r} n'existe pas "
              f"(attendu : {', '.join(SOUVENIRS)})", file=sys.stderr)
        return alertes + 1
    note, kind = SOUVENIRS[mot]
    cas["note"] = note
    if kind:
        cas["kind"] = kind
    return alertes


# Les marqueurs qui disent le SENS du temps sans ambiguïté. Volontairement
# courts : un marqueur douteux ferait un avertissement douteux, et un contrôle
# qu'on apprend à ignorer ne contrôle plus rien.
# Le passé composé avec « être » manquait, et il a laissé passer exactement le
# cas pour lequel ce garde-fou existe : « Je suis allé au concert le 28 » a été
# daté au 28 du mois PROCHAIN sans un mot. Les verbes qui prennent « être » sont
# une liste fermée, on l'écrit plutôt que de deviner.
_ETRE = (r"(allé|allée|allés|parti|partie|partis|resté|restée|restés|venu|venue"
         r"|venus|revenu|revenue|sorti|sortie|sortis|rentré|rentrée|rentrés"
         r"|arrivé|arrivée|arrivés|monté|montée|descendu|descendue|tombé|tombée)")
_PASSE = re.compile(
    r"\b(hier|avant-hier|j'étais|j'ai |on a |la semaine dernière|le mois dernier"
    r"|dernier|dernière|yesterday|last (week|month|year)|i was|we were"
    rf"|(je suis|on est|il est|elle est|nous sommes|ils sont|elles sont) {_ETRE}"
    r"|i went|we went|i attended|we attended)\b")
_FUTUR = re.compile(
    r"\b(demain|après-demain|la semaine prochaine|le mois prochain|prochain"
    r"|prochaine|tomorrow|next (week|month|year))\b")


def normaliser_type(cas: dict) -> int:
    """`type_proposal` veut un NOM d'entité, l'étiqueteur répond oui ou non.

    Il raisonne juste — « ce type n'est pas dans la liste, il faut le proposer »
    — et écrit `true`. Or l'axe doit dire DE QUI le type est proposé, sinon il
    ne vérifie rien sur une capture qui porte deux entités. Le nom est déjà là,
    dans `entity_expected` : lui redemander serait lui demander ce qu'on sait
    recopier, et c'est le geste qui a déjà réglé `souvenir` et le jour de
    semaine.
    """
    if "type_proposal" not in cas:
        return 0
    v = cas.get("type_proposal")
    if isinstance(v, str) and v.strip():
        return 0
    cas.pop("type_proposal", None)
    if v in (None, False):
        cas["no_type_proposal"] = True
        return 0
    nom = cas.get("entity_expected")
    if not nom:
        print(f"⚠ {cas.get('id', '?')} : type_proposal={v!r} sans nom d'entité "
              f"à qui l'attacher, axe retiré", file=sys.stderr)
        return 1
    cas["type_proposal"] = nom
    return 0


def sens_du_temps(cas: dict, capture: dict | None) -> int:
    """Prévenir quand la date pointe à l'opposé du temps du verbe.

    « J'étais au concert de Nadia le 28 » est sorti daté au 28 du mois PROCHAIN.
    Le décalage du jour de semaine se recale tout seul ; celui-ci ne le peut
    pas, parce que le sens appartient au temps du verbe et que le corriger
    reviendrait à trancher à la place de la règle.

    On ne parle donc que quand un seul des deux sens est présent : « j'avais
    prévu de relancer Sophie, je vais le faire demain » en porte deux, et une
    phrase qui porte les deux ne prouve rien.
    """
    texte = ((capture or {}).get("text") or "").lower()
    date = cas.get("event_date")
    if not isinstance(date, str):
        return 0
    passe, futur = bool(_PASSE.search(texte)), bool(_FUTUR.search(texte))
    if passe == futur:
        return 0
    try:
        posee = dt.date.fromisoformat(date)
    except ValueError:
        return 0
    zero = dt.date.fromisoformat(context.TODAY)
    if passe and posee > zero:
        print(f"⚠ {cas.get('id', '?')} : la capture est au passé, "
              f"l'étiquette pose {date}, après le {context.TODAY}", file=sys.stderr)
        return 1
    if futur and posee < zero:
        print(f"⚠ {cas.get('id', '?')} : la capture est au futur, "
              f"l'étiquette pose {date}, avant le {context.TODAY}", file=sys.stderr)
        return 1
    return 0


def corriger_jour(cas: dict, capture: dict | None) -> int:
    """Recaler `event_date` sur le jour de semaine que la capture nomme.

    Le calendrier est fourni jour par jour dans la demande et le modèle décale
    quand même d'un jour, systématiquement dans le même sens : « jeudi » sort en
    vendredi, « vendredi » en samedi. Trois passes, jamais dans l'autre sens.

    On ne lui reprend que l'arithmétique. Le SENS de la résolution reste le
    sien, parce que c'est le temps du verbe qui le décide et que ça, il le lit
    bien : on garde sa date et on la fait glisser vers le jour nommé le plus
    proche, ce qui ne peut pas franchir une semaine.
    """
    ident = cas.get("id", "?")
    jour = jour_nomme((capture or {}).get("text") or "")
    date = cas.get("event_date")
    if jour is None or not isinstance(date, str):
        return 0
    try:
        posee = dt.date.fromisoformat(date)
    except ValueError:
        print(f"⚠ {ident} : event_date={date!r} n'est pas une date", file=sys.stderr)
        return 1
    if posee.weekday() == jour:
        return 0
    ecart = (jour - posee.weekday()) % 7
    glissement = ecart if ecart <= 3 else ecart - 7
    cas["event_date"] = (posee + dt.timedelta(days=glissement)).isoformat()
    print(f"↻ {ident} : la capture dit « {_JOURS[jour]} », l'étiquette posait "
          f"{date} ({_JOURS[posee.weekday()]}) → {cas['event_date']}",
          file=sys.stderr)
    return 0


def recoller_why(cas: dict, capture: dict | None) -> int:
    """`why` de la capture + `regle` de l'étiquette, recollés par le code.

    Demandé au modèle, ça ne marchait pas : il réécrivait le `why` de la capture
    quinze fois sur quarante-deux, et ce qu'il perdait était justement ce que la
    capture voulait mesurer — donc ce qu'on lit en premier à la revue. La
    question et la réponse se lisent ensemble ou ne s'arbitrent pas.
    """
    ident = cas.get("id", "?")
    regle = str(cas.pop("regle", "") or "").strip()
    question = str((capture or {}).get("why") or "").strip()
    if not regle:
        print(f"⚠ {ident} : pas de `regle`, l'étiquette ne dit pas d'où elle vient",
              file=sys.stderr)
    morceaux = [m for m in (question, regle) if m]
    if morceaux:
        cas["why"] = " — ".join(morceaux)
    return 0 if regle else 1


# Un identifiant de ticket n'a rien à faire dans un dépôt public. Le modèle ne
# les invente pas, il les recopie : la carte des frontières en porte encore
# onze, et il reprend celui de la ligne qu'on lui donne.
_INVENTE = re.compile(r"\b[A-Z]{2,4}-\d{1,4}\b")


def valider(cas: dict, capture: dict | None) -> int:
    """Les avertissements d'un cas étiqueté. 0 = rien à signaler."""
    alertes = 0
    ident = cas.get("id", "?")

    inconnus = set(cas) - corpus.CHAMPS
    if inconnus:
        print(f"⚠ {ident} : champs inconnus {sorted(inconnus)}", file=sys.stderr)
        alertes += 1

    # Les VALEURS, pas seulement les noms de champs. Une des passes a rendu six
    # fois kind="reflection", qui n'existe pas : la validation par nom de champ
    # l'avait laissé passer sans un mot.
    if cas.get("kind") and cas["kind"] not in score.VALID_NOTE_KINDS:
        print(f"⚠ {ident} : kind={cas['kind']!r} n'existe pas "
              f"(attendu : {', '.join(sorted(score.VALID_NOTE_KINDS))})",
              file=sys.stderr)
        alertes += 1
    if cas.get("kind") and not cas.get("note"):
        print(f"⚠ {ident} : un kind sans note ne veut rien dire", file=sys.stderr)
        alertes += 1
    # `valide` dit qu'un humain a validé ; `arbitrage` porte sa décision sur un
    # cas qui coinçait et met le cas dans SA file d'attente. Écrits ici, le
    # premier signe à sa place et le second remplit la file de bruit.
    for reserve in ("valide", "arbitrage"):
        if reserve in cas:
            print(f"⚠ {ident} : `{reserve}` est posé par un humain, jamais ici",
                  file=sys.stderr)
            alertes += 1
    if not (set(cas) - corpus.META):
        print(f"⚠ {ident} : n'asserte rien, ne mesurerait rien", file=sys.stderr)
        alertes += 1
    for reference in _INVENTE.findall(cas.get("why") or ""):
        print(f"⚠ {ident} : référence de ticket « {reference} » dans `why`, "
              f"elle vient de la carte et n'a rien à faire dans le corpus",
              file=sys.stderr)
        alertes += 1

    if capture is None:
        print(f"⚠ {ident} : n'était pas dans les captures envoyées", file=sys.stderr)
        alertes += 1
    # Le texte est le cas. Une faute d'orthographe « corrigée » en passant fait
    # mesurer autre chose que ce qui a été écrit, et rien ne le dirait.
    if capture is not None and cas.get("text") != capture.get("text"):
        print(f"⚠ {ident} : le texte a été modifié\n"
              f"    envoyé : {capture.get('text')!r}\n"
              f"    rendu  : {cas.get('text')!r}", file=sys.stderr)
        alertes += 1
    return alertes


def nom_present(cas: dict) -> int:
    """`entity_expected` et `no_entity` nomment quelque chose que la capture DIT.

    Deux défauts mesurés le 2026-08-29 sur un paquet de 70, tous deux
    invisibles à la relecture rapide et tous deux calculables :

    - neuf `no_entity` valaient `1` au lieu d'un nom. `score.py` fait
      `.strip().lower()` dessus : l'axe ne mesure rien et le cas passe pour
      vert. C'est le pire état possible pour un corpus.
    - « Manchester » a été posé sur la capture de la porte de garage d'Alex,
      qui ne parle pas de Manchester. Un nom emprunté à la capture d'à côté
      teste une entité qui n'existe nulle part.

    On ne demande donc pas au modèle de faire attention, on vérifie. Le nom
    doit apparaître dans le texte, aux accents et à la casse près.
    """
    alertes = 0
    nu = unicodedata.normalize("NFD", cas.get("text", "").lower())
    nu = "".join(c for c in nu if unicodedata.category(c) != "Mn")
    for champ in ("entity_expected", "no_entity"):
        val = cas.get(champ)
        if val is None:
            continue
        if not isinstance(val, str) or not val.strip():
            print(f"⚠ {cas.get('id')} : `{champ}` = {val!r} n'est pas un nom, "
                  f"l'axe ne mesurera rien — retiré", file=sys.stderr)
            cas.pop(champ)
            alertes += 1
            continue
        cible = unicodedata.normalize("NFD", val.lower())
        cible = "".join(c for c in cible if unicodedata.category(c) != "Mn")
        if cible not in nu:
            print(f"⚠ {cas.get('id')} : `{champ}` = {val!r} n'apparaît pas dans "
                  f"la capture — retiré", file=sys.stderr)
            cas.pop(champ)
            alertes += 1
    return alertes


def cout(spec: str, r: providers.Reply) -> str:
    """Ce que le lot a coûté. Une mesure dont on ignore le prix se relance sans
    qu'on sache ce qu'elle coûte, et c'est déjà arrivé 22 fois cet été."""
    tarif = split._TARIFS.get(providers.parse_spec(spec)[1])
    if not tarif or r.prompt_tokens is None:
        return ""
    entree, cache, sortie = tarif
    nc = r.extra.get("uncached_input_tokens", r.prompt_tokens)
    ecrit = r.extra.get("cache_creation_input_tokens", 0)
    lu = r.prompt_tokens - nc - ecrit
    # Écrire le cache coûte 1,25 fois l'entrée, le relire 0,1 fois. Les compter
    # ensemble au prix de la lecture ferait annoncer un dixième du vrai prix sur
    # le PREMIER lot, qui est justement celui qui écrit tout le préfixe.
    usd = (nc * entree + ecrit * entree * 1.25 + lu * cache
           + (r.output_tokens or 0) * sortie) / 1e6
    # Un lot sans une seule lecture de cache dit que le préfixe est passé sous
    # le plancher du modèle, ce qui ne se voit pas dans le seul total.
    alerte = "  ⚠ aucun cache n'a mordu" if lu == 0 and not ecrit else ""
    return (f"coût     : ~{usd:.3f} $  ({nc/1000:.1f}k entrée · "
            f"{ecrit/1000:.1f}k cache écrit · {lu/1000:.1f}k relus · "
            f"{(r.output_tokens or 0)/1000:.1f}k sortie){alerte}")


def un_seul_cote(cas: list[dict]) -> int:
    """Prévenir quand tous les cas d'une frontière tombent du même côté.

    Le prompt de génération demande des paires, et rien ne le vérifiait. Un
    seul côté n'apprend rien : il autorise « tout ce qui ressemble à X est X »
    à passer pour la bonne réponse, et c'est arrivé sur G-LINK, quatre captures
    sans note sur quatre.

    Le contrôle porte sur le LOT. Une frontière déjà couverte ailleurs dans le
    corpus n'est pas concernée, donc l'avertissement se lit comme une question,
    pas comme une faute.
    """
    par_frontiere: dict[str, set] = {}
    for k in cas:
        f = (k.get("frontiere") or "").strip()
        if f:
            par_frontiere.setdefault(f, set()).add(frozenset(
                (c, str(v)) for c, v in k.items() if c not in corpus.META))
    alertes = 0
    for f, cotes in sorted(par_frontiere.items()):
        if len(cotes) == 1 and sum(
                1 for k in cas if (k.get("frontiere") or "").strip() == f) > 1:
            print(f"⚠ {f} : tous les cas du lot portent la MÊME étiquette — "
                  f"l'autre côté de la frontière manque", file=sys.stderr)
            alertes += 1
    return alertes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", type=Path,
                    help="fichier de captures ; par défaut stdin")
    ap.add_argument("--modele", default="anthropic:claude-haiku-4-5-20251001")
    args = ap.parse_args()

    captures = lire_captures(args.source)
    par_id = {c.get("id"): c for c in captures}

    demande = "\n".join([
        f"Le temps de référence est {context.TODAY}. L'auteur des captures est "
        f"{context.OWNER}.",
        "",
        "Le calendrier autour de lui. Toute date de ton étiquette se LIT ici, "
        "elle ne se calcule pas :",
        calendrier(),
        "",
        f"Étiquette les {len(captures)} captures ci-dessous. Rends chacune "
        f"complétée, une ligne JSON par cas, rien autour.",
        "",
        *[json.dumps(c, ensure_ascii=False) for c in captures],
    ])

    # Température 0 : l'étiquette dérive de règles écrites, donc deux passes sur
    # la même capture doivent rendre la même chose. C'est l'inverse du
    # générateur, où la variance EST ce qu'on cherche.
    r = providers.call(args.modele, [savoir_complet()], demande,
                       max_tokens=8000, temperature=0.0)
    if not r.ok:
        raise SystemExit(f"appel échoué : {r}")

    bons = mauvais = 0
    rendus, sortis = set(), []
    for brute in r.text.splitlines():
        brute = brute.strip().strip("`")
        if not brute.startswith("{"):
            continue
        try:
            cas = json.loads(brute)
        except ValueError as e:
            print(f"⚠ ligne illisible ({e}) : {brute[:80]}", file=sys.stderr)
            mauvais += 1
            continue
        mauvais += traduire_souvenir(cas)
        mauvais += nom_present(cas)
        mauvais += recoller_why(cas, par_id.get(cas.get("id")))
        mauvais += normaliser_type(cas)
        mauvais += corriger_jour(cas, par_id.get(cas.get("id")))
        mauvais += sens_du_temps(cas, par_id.get(cas.get("id")))
        sortis.append(cas)
        mauvais += valider(cas, par_id.get(cas.get("id")))
        rendus.add(cas.get("id"))
        bons += 1
        print(json.dumps(cas, ensure_ascii=False))

    mauvais += un_seul_cote(sortis)

    # Une capture avalée sans être rendue est le pire cas : elle ne lève rien et
    # elle disparaît du lot sans que personne ne la cherche.
    for perdue in [i for i in par_id if i not in rendus]:
        print(f"⚠ {perdue} : envoyée, jamais rendue", file=sys.stderr)
        mauvais += 1

    print(f"\n{bons}/{len(captures)} cas étiquetés, {mauvais} avertissement(s). "
          f"Rien n'a été écrit dans le corpus : la revue est humaine.",
          file=sys.stderr)
    print(cout(args.modele, r), file=sys.stderr)


if __name__ == "__main__":
    main()
