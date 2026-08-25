# SYN-184 — carte des frontières de décision

À quoi ça sert : le ticket demande de couvrir **les arêtes**, pas d'être exhaustif
sur ce que les gens écriront. Encore faut-il savoir où elles sont. Ce document
énumère chaque frontière énoncée par les deux prompts de production
(`classifier-note.md`, `classifier-graph.md`), dit ce qui la couvre aujourd'hui,
et nomme les trous. C'est lui qui décide quoi écrire, pas l'inspiration.

Règle de lecture : une frontière n'est couverte que si **les deux côtés** sont
étiquetés. Un seul côté n'apprend rien, il autorise la règle paresseuse (« tout
ce qui ressemble à X est X ») à passer pour la bonne réponse.

## Ce que le corpus actuel est vraiment

61 identifiants, mais **48 captures distinctes** : onze textes servent deux ou
trois fois, à cheval sur `GATE_CASES`, `HARD_CASES` et `ADVERSARIAL_CASES`.
« Répondre à l'e-mail de Vincent » compte trois fois (`g-task-addressed`, `t1`,
`x-owner-is-author`), « Marie a un chat qui s'appelle Gipsy » trois fois aussi.

Répartition de ces 48 : 42 en français, 5 en anglais, 1 en espagnol. Une seule
plume, une seule syntaxe, aucune capture dictée, tronquée, mal orthographiée ni à
cheval sur deux langues. C'est la contrainte n°2 du ticket, et elle n'est pas
tenue aujourd'hui.

---

## 1. La porte (`classifier-note.md`, avant la table)

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| G-DATE | « une date annule la porte », dans les deux sens de formulation | `e4`, `x-birthday-bare`, les 5 scénarios | Couvert **sur l'anniversaire seulement**. La date qui annule une AUTRE ligne de la porte (progrès daté, statut daté, corvée datée) n'a aucun cas. |
| G-ATTR | énoncé entièrement attributif (« X a / est / fait Y ») ⇒ pas de note | `f1`, `f2`, `g-type-fact`, `r1`, `r2` | Un seul côté. Manque le miroir : un énoncé attributif sur lequel l'auteur prend position, qui lui mérite la note. |
| G-LINK | lien nu sans prise de position | `u1`, `g-type-resource` | **Gelé**. Les deux assertions ont été retirées le 21/08, cible indécise jusqu'à SYN-186. Ne rien étiqueter ici tant que le ticket n'a pas tranché. |
| G-PROGRESS | progrès sur un projet ⇒ pas de note | rien | **Trou complet.** Zéro cas. C'est pourtant la capture la plus fréquente d'un utilisateur qui tient un projet. |
| G-STATUS | statut nu (« j'ai déjà mangé », « c'est envoyé ») ⇒ rien | rien | **Trou complet**, et il touche une zone de conflit : la ligne 1 dit que tout ce qui est ENVOYÉ est un engagement, la porte dit qu'un statut nu ne laisse rien. Les deux côtés sont à écrire ensemble. |
| G-ROUTINE | activité routinière solitaire déjà faite | `ep2`, `g-type-episodic`, `x-past-errand` ; miroirs `ep1`, `x-pure-episode`, `x-episode-first-time` | Correctement couvert, sauf la sortie « lieu digne d'être nommé » (voir R3b). |
| G-HABIT | habitude ou trait biographique sans moment situé | `x-habitual-past` | Un seul cas, un seul côté. Manque l'habitude AVEC moment situé, qui doit sortir en épisode. |
| G-SVO | garde-fou SVO : si tout se reformule en triplets, c'est un fait | `f1`, `f2`, `r1`, `r2` (indirect) | Aucun cas adverse : rien ne vérifie que le garde-fou ne mange pas une note qui se reformule en triplets tout en portant un mouvement. |

## 2. La table de routage

### Ligne 0, projet

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R0a | entreprise multi-étapes ⇒ projet, jamais simple tâche | `j1`, `j2`, `j3`, `g-project-new` | Un seul côté. Manque ce qui RESSEMBLE à un projet et n'en est pas. |
| R0b | l'énoncé fondateur sort en `kind="note"` | `j2`, `j3` n'assertent que `proj` | **Assertion manquante** : aucun cas ne vérifie que la note fondatrice existe. |
| R0c | nommer le projet par son DOMAINE durable, pas l'action ponctuelle | `j1` (implicite) | Jamais asserté. |
| R0d | plusieurs projets dans une même capture ⇒ une entrée chacun | rien | **Trou complet.** |

### Ligne 1, tâche

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R1a | verbe d'action à l'infinitif ou impératif | `t1`..`t7` | Bien couvert. |
| R1b | action adressée à une personne ou une organisation, démarche administrative | `t1`, `t2`, `t4`, `g-english-task` | Bien couvert. |
| R1c | deux mots suffisent (impératif, 2ᵉ personne) | rien | **Trou.** Le cas le plus court du corpus fait cinq mots. C'est exactement la forme sur laquelle le bug historique portait. |
| R1d | tâche AVEC échéance : reste `task`, remplit `event_date` | `t6` | Un cas, et `event_date` n'est asserté nulle part. |
| R1e | discours rapporté ⇒ `owner` = la personne | `x-reported-speech` | Un cas contre un miroir (`x-owner-is-author`). Manque le discours rapporté d'un ÉVÉNEMENT (pas d'une tâche), et le cas où deux personnes sont nommées. |
| R1f | action annulée ⇒ ligne 4 | `x-negation` | Un seul cas. |
| R1g | micro-course triviale ⇒ pas de note ET éphémère | `p1`, `p3`, `g-ephemeral-trivial` | Le consommable est couvert ; la **corvée ménagère** (« sortir les poubelles »), nommée par le prompt, ne l'est pas. |
| R1h | l'équipement durable n'est PAS un consommable | `p2`, `g-type-ephemeral` | Toute la frontière tient sur un seul objet, le harnais. Le prompt en nomme trois autres. |
| R1i | course au passé : faite, donc jamais un rappel | `x-past-errand` | Un seul cas. |
| R1j | envoyé / payé / classé / déclaré ⇒ engagement, même terse, même nom inconnu | `t2`, `t4` | Manque le cas sans aucun nom (« payer le loyer »), et le cas au nom volontairement opaque. |

### Ligne 2, événement

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R2a | occurrence datée à laquelle l'auteur assiste | `e1`, `e2`, `e3`, `x-attend-verb`, `x-attend-noun` | Bien couvert. |
| R2b | syntagme nominal sans verbe ⇒ quand même la note | `e1`, `e2`, `e3` | Bien couvert. |
| R2c | on FAIT une tâche, on ASSISTE à un événement ; le verbe ne prouve rien | `x-attend-verb`, `x-attend-noun` | Deux cas du même côté. Manque le miroir dur : un événement formulé avec un verbe d'action réel. |
| R2d | `event_date` absolue, résolution du relatif via `{today}` | `e2`, `e3` portent du relatif | **Jamais asserté, et le harnais ne sait pas le vérifier.** Un modèle qui rendrait « mardi » tel quel passerait. |
| R2e | anniversaire, trois formulations, trois réponses | `x-birthday-party`, `x-birthday-birth`, `x-birthday-bare`, `e4`, `g-atomicity-mixed` | La meilleure frontière du corpus. Mais `event_recurring` n'est asserté sur aucun des trois, alors que le champ est scoré. |
| R2f | déjà passé ⇒ ligne 3 | `x-mixed-tense` (partiel) | Faible. |

### Ligne 3, épisode

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R3a | une autre personne NOMMÉE ⇒ épisode, si ordinaire soit-il | `ep1`, `x-pure-episode` | Couvert. |
| R3b | personne d'autre, mais un LIEU digne d'être nommé | rien | **Trou.** Seule la sortie « accomplissement » est couverte. Sans ce cas, « solitaire ⇒ pas de note » reste une règle plausible. |
| R3c | accomplissement : première fois, record, résultat mesurable | `ep1`, `x-episode-first-time` ; contre-exemple `ep2` (un ressenti n'est pas un accomplissement) | Couvert. |
| R3d | l'épisode établit aussi du durable : la note ET le fait | `a3`, `x-mixed-tense` | L'exemple même du prompt (« j'ai appelé le plombier, il vient mardi ») n'est pas dans le corpus. |
| R3e | un épisode A une date, et une date passée qui REVIENT prend `event_recurring` | `x-past-recurring-date` | **Trou n°2 du ticket.** Un seul cas, `recurring` non asserté, et **aucun miroir** : pas une seule date passée qui ne revient pas. La frontière est donc inapprenable en l'état. |
| R3f | jamais éphémère | rien | Aucun épisode n'asserte `ephemeral=False`. |
| R3g | pas encore vécu ⇒ ligne 0 ou 1 | `t7` | Faible. |

### Ligne 4, note

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R4a | première personne réflexive | `n1`, `n3`, `g-note-reflexive` | Bien couvert. |
| R4b | citation, ou œuvre / auteur / idée externe sur laquelle l'auteur prend position | rien | **Trou complet.** Zéro cas, alors que c'est une des quatre entrées de la ligne. |
| R4c | observation contemplative qui ne se réduit à aucun fait | `n2` | Un cas. |
| R4d | une décision, y compris celle de renoncer | `x-negation` | Un cas. |
| R4e | énoncé fondateur d'un projet | voir R0b | Non asserté. |

## 3. Règles transverses (`classifier-note.md`)

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| X-EPH | les QUATRE conditions d'`is_ephemeral`, une seule qui manque suffit | `p1`, `p2`, `x-past-errand`, `n1`..`n3` | Le mécanisme est couvert. La **coexistence** note + éphémère, autorisée aux seules lignes 1 et 2, n'a aucun cas. |
| X-CONF | la confiance doit tomber sous 0,6 quand le modèle hésite vraiment | `x-birthday-bare` (non scoré), les scénarios | **Trou n°1 du ticket.** Aucune note ni aucun épisode étiqueté douteux. Mesuré le 21/08 : 0 sur ~90 épisodes et 0 sur ~200 notes sont jamais passés sous 0,7. La file « À valider » est décorative sur deux des quatre types. |
| X-LANG | détecter la langue, écrire la note dans la MÊME langue, ne jamais traduire | 5 cas EN, 1 ES | `language` n'est asserté nulle part. Aucune capture à cheval sur deux langues, aucune mal orthographiée, aucune tronquée. |
| X-ONE | exactement UNE note par capture, ou aucune | `a2`, `a3`, `g-atomicity-mixed` (implicite) | Jamais vérifié comme tel. |

## 4. Le prompt graphe (`classifier-graph.md`)

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| P-DUR | un fait n'existe que pour du DURABLE ; `facts: []` est une bonne réponse | `f1`, `f2` | Manque les trois interdits nommés par le prompt : redire la phrase de la capture, stocker une action ponctuelle, stocker une date qui appartient à l'événement. |
| P-DEDUC | déduire oui, inventer non | `g-atomicity-mixed`, `a1`, `x-no-invention` | Couvert sur le principe. La confiance ≈ 0,6 d'une relation déduite n'est jamais assertée. |
| P-FR | fait contre relation, anti-redite | `r1`, `r2`, `g-relation` | Couvert. |
| P-PERS | l'échelle de persistance décide du nœud | `x-pet-owned`, `x-pet-incidental` | Les deux côtés existent, **mais aucun des deux n'est scoré** (`entity_expected`, `no_entity` sont inertes). |
| P-HEDGE | `evidence_strength` : explicite / prudent / implicite | `h1`, `h2` | N'assertent que `note=False`. Le champ lui-même n'est jamais vérifié. |
| P-BDAY | un anniversaire est TOUJOURS un fait ; une fête n'en est pas un | `x-birthday-birth` (`facts_min`) | Le côté négatif (« la fête ne doit produire AUCUN `has_birthday` ») n'est pas exprimable : le harnais n'a pas d'assertion « ce prédicat est interdit ». |
| P-TYPE | type strictement dans la liste active, sinon `concept` + `type_proposal` | rien | **Trou complet.** Zéro cas. |
| P-PROJF | fait de projet (total, budget, palier atteint) ⇒ le projet devient aussi une entité | rien | **Trou complet.** |

## 5. Les sept files de validation

Ajouté après la passe du 2026-08-24. Chaque file a une condition d'entrée, et une
condition d'entrée est une frontière de décision comme une autre. Le corpus n'en
couvre qu'une, avec un seul cas.

| File | Condition d'entrée | Décidée par | Assertable ici | Cas |
|---|---|---|---|---|
| `atomic_notes.review_status` | confiance < 0,7, **ou** `recurrence_inferee` (récurrent et non-événement, ou récurrent et hésitant) | le modèle | oui | 1 |
| `pending_facts` | confiance de fait entre 0,5 et 0,85 | le core, dérivée d'`evidence_strength` | oui, indirectement | 0 |
| `review_queue` | confiance de fait < 0,5 | le core, même chaîne | oui, indirectement | 0 |
| `relations.review_status` | confiance de relation < 0,7 | le modèle, directement | oui | 0 |
| `entity_type_proposals` | l'entité ne rentre dans aucun type actif | le modèle | oui | 0 |
| `entity_merge_proposals` | doublon détecté (sous-chaîne puis embedding 0,85) | le core seul | non | |
| `project_attach_proposals` | similarité 0,30, marge 0,03 | le core seul | non, sauf le nommage | |

Le maillon le plus rentable est le deuxième, et il ne coûte qu'une assertion :
`compute_confidence` part d'`evidence_strength`, avec 0,92 pour `explicit`, 0,65
pour `hedged` plafonné à 0,84, et 0,40 pour `implicit`. Comme le seuil d'entrée
dans `facts` est 0,85, **un fait `hedged` ne peut jamais y arriver** : il tombe
mécaniquement dans `pending_facts`. Asserter `evidence_strength="hedged"` sur
`h1` et `h2`, qui n'assertent aujourd'hui que `note=False`, rend toute cette file
mesurable. Idem pour les déductions, que le prompt oblige à marquer `implicit`,
donc à 0,40 : elles partent en validation par construction, et rien ne le
vérifie.

## 6. Familles ajoutées par la passe du 2026-08-24

### PERS, les personnes

L'échelle de persistance n'est couverte que par les animaux (`x-pet-owned`,
`x-pet-incidental`). Sur les humains, rien, alors que c'est le type où un nœud
parasite coûte le plus cher : il crée une fiche.

| # | Frontière | Verdict |
|---|---|---|
| PERS-a | personne croisée une fois ⇒ persistance 1, sous `MIN_ENTITY_PERSISTENCE = 2` (`routing.rs:35`) | trou complet |
| PERS-b | personne désignée par un rôle et non par un nom (« ma mère », « mon dentiste ») | `f2` existe et n'asserte que `note=False` : personne ne dit si « ma mère » mérite un nœud |
| PERS-c | homonymes : deux Marie dans la même mémoire | trou complet |
| PERS-d | `aliases` : nom partiel puis nom complet | jamais asserté, et **jamais gouverné** (voir SYN-190) |

### NEG, les négations

`x-negation` couvre l'action annulée et c'est tout. C'est une famille, pas une
frontière.

SYN-189 a ouvert `obsoleted_facts` dans la moitié graphe, et avec lui les deux
axes `obsoletes` et `no_obsolete` de `score.py`. NEG-b et NEG-c sont donc
écrivables. Les deux se valent en importance et doivent être écrits ENSEMBLE :
une négation manquée laisse un faux durable sur la fiche, une négation de trop
retire une vérité, et personne ne remarque qu'un fait a disparu.

| # | Frontière | Verdict |
|---|---|---|
| NEG-a | action annulée ⇒ la décision se garde, la tâche non | couvert, 1 cas |
| NEG-b | négation d'un FAIT (« Pierre ne travaille plus chez Acme ») | **débloqué** (SYN-189) : asserter `obsoletes="works_at=Acme"`. Trou complet, écrivable dès maintenant |
| NEG-c | négation d'existence (« Marie n'a pas de chat ») | **débloqué** : asserter `no_obsolete=True` ET aucun fait. Une absence énoncée pour la première fois ne nie rien |
| NEG-b′ | un REMPLACEMENT n'est pas une négation (« il a quitté Acme pour Globex ») | **débloqué**, et c'est le piège du lot : la bonne réponse est un fait ordinaire avec la nouvelle valeur et `no_obsolete=True`, le supersede faisant le reste |
| NEG-b″ | négation nuancée (« je crois qu'il a quitté Acme ») | **débloqué** : `no_obsolete=True`. Retirer une connaissance sur un peut-être est pire que la garder |
| NEG-d | événement annulé (par opposition à la tâche annulée) | trou complet, TOUJOURS bloqué : annuler un événement demande de retrouver la note qui le porte, donc un rappel, pas un champ de sortie |
| NEG-e | correction d'une capture antérieure (« en fait c'était mercredi ») | trou complet, toujours bloqué : même rappel, plus le fil de mémoire de travail (mode scénario) |

### PEREMPTION, ce qui remplace ce qui était vrai

| # | Frontière | Verdict |
|---|---|---|
| PER-a | une capture qui périme un fait antérieur doit émettre le NOUVEAU fait, sur les 7 familles mono-valuées de `routing.rs:45` | trou complet, écrivable dès maintenant |
| PER-b | renommage d'entité déclaré en capture | **non branché**, bloqué par SYN-188 |
| PER-c | un état transitoire ne doit pas devenir un fait durable (`planned_new_name`) | trou complet, bloqué par SYN-188 |

La moitié qui relève du core ne peut pas être testée ici : le harnais fige le
contexte exprès, donc il n'a aucun état antérieur.

### EMO, la capture émotionnelle

Le prompt dit une seule chose, « A FEELING IS NOT AN ACHIEVEMENT », et seulement
pour un ressenti collé à une activité routinière (`ep2`). La capture émotionnelle
pure n'est tranchée nulle part et tombe en ligne 5 par défaut, sans que personne
ne l'ait décidé. **Rien n'est étiquetable ici tant que SYN-191 n'a pas tranché** :
un cas que le prompt ne tranche pas n'est pas un échec du modèle.

### Les cinq typologies, pas une

| Typologie | Valeurs | Couverture |
|---|---|---|
| `atomic_note_kind` | 4 | bien couvert |
| `entity type` | 6 builtin (`person`, `place`, `project`, `concept`, `organization`, `animal`, `schema.rs:273`) + les validés | zéro cas |
| `facts.category` | 8 (`identity`, `dates`, `work`, `places`, `relations`, `preferences`, `health`, `other`) | zéro cas. 39 % des faits en base l'ont à NULL |
| `persistence_value` | 1 à 5 | jamais assertée en tant que valeur |
| `evidence_strength` | 3 | `h1`/`h2` existent mais n'assertent que `note=False` |

**Précision sur P-TYPE, qui change l'écriture du cas.** Le modèle ne choisit
jamais un type : il pose `type: "concept"` et remplit `type_proposal`, un humain
valide, et le type entre alors dans `active_entity_types`. Le mécanisme tourne
(6 builtin plus 4 validés, 5 propositions toutes acceptées). Il faut donc **deux
cas, un de chaque côté** :

* une entité qui ne rentre dans aucun type actif : `type` doit rester dans la
  liste active ET `type_proposal` doit être rempli. Un modèle qui écrit
  `type: "recipe"` directement contourne la validation ;
* une entité qui rentre dans un type actif : `type_proposal` doit rester **null**.
  Sans ce miroir, un modèle qui propose à chaque fois noie la file, et le
  garde-fou devient du bruit qu'on clique sans lire.

## 7. Hors périmètre, écrit ici pour qu'on ne l'y cherche pas

**Les oublis.** La décroissance ne se teste pas avec ce corpus. Mais elle porte
un enjeu qui change le soin à mettre sur la ligne 3 : `decay.rs:37` fait décroître
un `episode` à τ/3, soit 10 jours contre 30. La frontière note/épisode n'est pas
un choix d'affichage, c'est un choix de **vitesse d'oubli**.

**Les relations par proximité.** Elles ne passent pas par le classifieur :
`semantic_edges` (kNN 0,80, layout seulement, jamais renvoyées), la fusion par
embedding (0,85), l'attachement projet (0,30, marge 0,03). Trois seuils dans le
core, aucun prompt. Deux cousines côté classifieur ne sont pas couvertes pour
autant : la relation **déduite** (confiance ≈ 0,6, la seule proximité que le
classifieur produit lui-même) et l'attachement à un projet EXISTANT plutôt que la
création d'un jumeau. `j1` asserte `proj="existing"` mais le scoring ne vérifie
que la présence d'une entrée, pas laquelle : un modèle qui crée un doublon passe.

## 8. Ce que le harnais ne sait pas encore vérifier

Écrire un cas dont l'attente est inerte revient à ne pas l'écrire.

Ouverts le 2026-08-24 dans `score.py` : `needs_review`, `event_date`, `language`,
`forbidden_predicate`, `entity_expected`, `no_entity`, et `drop_guard` qui n'était
vérifié que sur les 12 cas du gate alors que 23 cas le déclarent.

Restent à ouvrir :

1. `type_proposal` attendu vrai ou faux, plus « `type` ∈ liste active ».
2. `evidence_strength`, qui rend mesurables les deux files de faits.
3. `relation_confidence`, pour la file des relations.
4. `proj` doit dire QUEL projet, pas seulement qu'il y en a un.
5. `category`, une fois SYN-190 fait.
6. Le prédicat nommé, inécrivable tant que SYN-190 n'est pas fait.

## 9. Provenance : ce qu'on prend et ce qu'on jette

**Le dogfood donne des énoncés, jamais des étiquettes.** La mémoire de prod est
une bonne source d'entrées et une mauvaise source de sorties : elle contient des
bugs et des arbitrages qu'on a annulés depuis. C'est la contrainte n°1 du ticket
sous une autre forme. Les mesures faites sur elle (91 prédicats, 39 % de
`category` nulle) sont des **symptômes**, jamais des vérités-terrain.

Même règle pour un dataset externe : on prend les énoncés pour la diversité
d'énonciation, on jette leurs étiquettes, on applique la nôtre.

## 10. Composition du premier palier (~150 nouveaux cas)

Deux exigences qui tirent en sens inverse, et le ticket demande les deux :
couvrir les arêtes, et garder une proportion réaliste de cas faciles pour ne pas
détruire la calibration de la confiance.

| Tranche | Cas | Ce que c'est |
|---|---|---|
| Trous complets | ~70 | G-PROGRESS, G-STATUS, R0d, R1c, R3b, R4b, P-TYPE (deux côtés), les 4 familles PERS, NEG-c et NEG-d, PER-a, les miroirs manquants de R3e et R2c, les 4 files assertables. |
| Frontières tenues par un seul cas | ~30 | R1f, R1g, R1h, R1i, R4c, R4d, G-HABIT, R2f, R3g : un deuxième et un troisième objet, une autre formulation. |
| Doute étiqueté | ~15 | Notes et épisodes qui DOIVENT sortir sous 0,7. La tranche que rien ne remplace. |
| Cas faciles, distribution réaliste | ~55 | Les quatre types dans leurs formes ordinaires, plus les captures qui ne laissent rien. |

Langues : viser environ 30 % d'anglais et quelques captures espagnoles ou mêlées,
contre 12 % aujourd'hui. Y inclure du dicté, du tronqué, du mal orthographié.

Les 48 captures existantes ne bougent pas et ne servent jamais à entraîner.

### Ce qui attend un arbitrage

| Famille | Bloquée par |
|---|---|
| NEG-d, événement annulé | SYN-189 phase 2 : demande de retrouver la note antérieure, donc un mécanisme de rappel, pas un champ |
| NEG-e, correction d'une capture antérieure | idem, plus le fil de mémoire de travail (mode scénario) |
| PER-b, PER-c, renommage | SYN-188 |
| Assertion d'un prédicat nommé, `category` | SYN-190 |
| EMO, capture émotionnelle | SYN-191 |
| G-LINK, lien commenté | SYN-186 |

Environ 120 des 150 cas restent écrivables sans rien attendre.
