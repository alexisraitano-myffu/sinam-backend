# carte des frontières de décision

À quoi ça sert : le ticket demande de couvrir **les arêtes**, pas d'être exhaustif
sur ce que les gens écriront. Encore faut-il savoir où elles sont. Ce document
énumère chaque frontière énoncée par les deux prompts de production
(`classifier-note.md`, `classifier-graph.md`), dit ce qui la couvre aujourd'hui,
et nomme les trous. C'est lui qui décide quoi écrire, pas l'inspiration.

## Ce qu'est une frontière

Une **règle du prompt prise par son bord**. Pas un thème, pas un type de
capture : une phrase précise, et la condition exacte sous laquelle elle bascule.

`G-ROUTINE` dit qu'une activité routinière faite seul et déjà faite ne laisse
rien. Son centre est « j'ai sorti les poubelles » : personne n'hésite, et un cas
de test posé là sera vert aujourd'hui, vert dans six mois, sans jamais rien
apprendre. Son bord est ailleurs :

```
J'ai acheté du pain hier                    →  rien
J'ai pris une douche chez la mère de Léa    →  un épisode
```

Les deux sont routinières, solitaires, déjà faites. La règle devrait jeter les
deux. Mais la seconde nomme un lieu, et un lieu que l'auteur a pris la peine de
nommer casse la ligne à lui tout seul. Cette ligne entre les deux EST la
frontière ; `G-ROUTINE` est son nom.

On ne couvre que les bords parce qu'un moteur ne se trompe pas au centre. Il se
trompe au bord, et dans les deux sens : il garde ce qu'il devrait jeter, et la
mémoire se remplit de bruit ; il jette ce qu'il devrait garder, et la perte est
silencieuse.

Règle de lecture : une frontière n'est couverte que si **les deux côtés** sont
étiquetés. Un seul côté n'apprend rien, il autorise la règle paresseuse (« tout
ce qui ressemble à X est X ») à passer pour la bonne réponse. Et la bonne paire
ne fait varier **qu'une seule chose** : si le lieu est le seul écart entre les
deux captures et que le moteur les traite pareil, on sait quelle règle a lâché.
Deux phrases sans rapport n'apprennent rien.

## Comment lire un code

Le code est une **adresse**, pas une catégorie : il ne dit pas de quoi la
frontière parle, il dit **où** la règle se lit dans les prompts. `R1c` ne veut
pas dire « les tâches courtes », il veut dire « ligne 1 du tableau, troisième
règle », c'est-à-dire cette phrase-là, qu'on peut aller relire.

| préfixe | où |
|---|---|
| `G-…` | **la porte**, testée AVANT tout le reste, et qui peut faire sortir la capture sans rien laisser |
| `R<n><lettre>` | **la table de routage**. Le chiffre est la DESTINATION : `R0` projet · `R1` tâche · `R2` événement · `R3` épisode · `R4` note. La lettre n'est qu'un rang dans la ligne |
| `X-…` | **les règles transverses**, qui s'appliquent quelle que soit la ligne atteinte |
| `P-…` | **le prompt graphe**, l'autre appel, celui qui sort les fiches et les faits |
| `PERS-` `NEG-` `PER-` `EMO` `RES-` | les familles thématiques ajoutées le 2026-08-24 : les personnes, les négations, la péremption, l'émotion, les ressources |

`R1c` se lit donc « ligne 1, tâche, troisième règle », et `R3b` « ligne 3,
épisode, deuxième règle ». Rien de plus.

## La colonne « Verdict » est la cible, et elle se tient à jour

C'est elle qui décide quoi écrire, pas le champ `frontiere` des cas. La plupart
des cas qui couvrent une frontière ne le portent pas, donc les compter mène à
générer pour du déjà-couvert. Constaté le 2026-08-27, sur cinq frontières d'un
coup.

Corollaire : **toute vague qui ajoute des cas met à jour cette colonne**, sinon
la carte ment à la vague suivante.

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
| G-DATE | une date FAIT PASSER la porte à une capture que la porte écarterait sans elle : un progrès, un statut, une corvée, une habitude portent une date et sortent quand même, dans les deux sens de formulation | `e4`, `x-birthday-bare`, les 5 scénarios | **Toujours ouvert.** `g-date-statut-date-sans-date` (« Promotion de Léa : elle est directrice maintenant ») ferme la paire du STATUT, face au cas daté qui existait. Manque toujours le progrès daté et la corvée datée : la vague du 28/08 a produit un jumeau de `g-progress-fr` et une tâche ordinaire, aucune des deux n'étant une capture que la porte écarterait. |
| G-ATTR | énoncé entièrement attributif (« X a / est / fait Y ») ⇒ pas de note | `f1`, `f2`, `g-type-fact`, `r1`, `r2` | Le miroir est écrit dans la porte depuis le 2026-08-26 : ENTIER est la condition, une prise de position sur l'attribut n'en fait pas partie, donc la capture garde sa note. `g-attr-with-stance` basculait une fois sur deux avant ça, et tient 3/3 après. L'attribut devient un fait dans les deux cas ; ce que l'auteur en pense est la part qu'aucun fait ne porte. |
| G-LINK | lien nu sans prise de position | `u1`, `g-type-resource`, `res-bare-fr`, `res-place-fr`, `res-tool-fr` ; miroir `res-commented-en` | **Tranché le 2026-08-26**, en deux branches. On retire l'URL et on regarde ce qui reste : plus aucun mot ⇒ pas de note. Des mots restent ⇒ ce que le lien EST décide. S'il est la chose elle-même (article, vidéo, papier, fil), la note est gardée ; s'il pointe vers quelque chose qui a sa propre identité (lieu, boutique, outil, société), la ressource et la fiche portent tout, et il n'y a pas de note. Le gel du 21/08 est levé. |
| G-PROGRESS | progrès sur un projet ⇒ pas de note | `g-progress-fr`, `g-progress-en` | **Le miroir est écrit et il attend un arbitrage.** `g-progress-decision-fr` porte `ambigu: true` : rien dans les prompts ne dit si une décision prise en avançant laisse une note. Le moteur garde le fait `launch_month=September` sur le projet et ne rend aucune note. Deux formes de plus au passage, une métrique en anglais et un progrès tronqué, toutes deux du côté « rien ». |
| G-STATUS | statut nu (« j'ai déjà mangé », « c'est envoyé ») ⇒ rien | `g-status-sent-fr`, `g-status-eaten-en` ; miroir `g-status-sent-named-fr` | **Tranché le 2026-08-26**, et Alexis a tranché contre la lecture que la mesure lui proposait : ce qui fait l'occurrence est le MOMENT, pas le nom. Les deux devis sortent en épisode daté. Un statut ne tombe donc plus que s'il n'est accroché à rien (« c'est envoyé », « j'ai déjà mangé »). Le risque assumé est le débordement sur la corvée : « J'ai acheté du pain ce matin » porte la même ancre et doit continuer de ne rien laisser, ce que seule la ligne G-ROUTINE retient désormais. Cette paire est le contrôle à surveiller à chaque passe. |
| G-ROUTINE | activité routinière solitaire déjà faite | `ep2`, `g-type-episodic`, `x-past-errand` ; miroirs `ep1`, `x-pure-episode`, `x-episode-first-time` | Correctement couvert, sauf la sortie « lieu digne d'être nommé » (voir R3b). |
| G-HABIT | habitude ou trait biographique sans moment situé | `x-habitual-past` | **Les deux côtés, et verts depuis la réécriture de la porte du 28/08.** « Je suis matinal, je me lève toujours avant 6h » ne laisse rien, « Hier j'ai remarqué que je suis matinal, j'ai réussi à être debout avant 6h » sort un épisode : c'est l'accomplissement qui ouvre la porte, pas le moment. |
| G-SVO | garde-fou SVO : si tout se reformule en triplets, c'est un fait | `f1`, `f2`, `r1`, `r2` (indirect) | **Couvert et vert depuis la réécriture de la porte du 28/08.** Les trois cas passent : la documentation pure ne laisse rien, l'opinion et le changement d'avis laissent une note. Le garde-fou SVO n'y était pour rien, il a été blanchi deux fois par la mesure. C'était le RANG de l'exception, écrite dans la ligne qu'elle contredit au lieu d'être au-dessus de la porte. |

## 2. La table de routage

### Ligne 0, projet

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R0a | entreprise multi-étapes ⇒ projet, jamais simple tâche | `j1`, `j2`, `j3`, `g-project-new` | Un seul côté. Manque ce qui RESSEMBLE à un projet et n'en est pas. |
| R0b | l'énoncé fondateur sort en `kind="note"` | `j2`, `j3` n'assertent que `proj` | **Assertion manquante** : aucun cas ne vérifie que la note fondatrice existe. |
| R0c | nommer le projet par son DOMAINE durable, pas l'action ponctuelle | `j1` (implicite) | Jamais asserté. |
| R0d | plusieurs projets dans une même capture ⇒ une entrée chacun | `r0d-two-projects` | **Un seul côté** depuis le 26/08 : deux projets déjà existants, `note=False`. Manque le cas où l'un des deux est neuf, seul moyen de voir si chacun reçoit vraiment son entrée plutôt qu'un rattachement au premier nommé. |

### Ligne 1, tâche

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R1a | verbe d'action à l'infinitif ou impératif | `t1`..`t7` | Bien couvert. |
| R1b | action adressée à une personne ou une organisation, démarche administrative | `t1`, `t2`, `t4`, `g-english-task` | Bien couvert. |
| R1c | deux mots suffisent (impératif, 2ᵉ personne) | `r1c-two-words` | **Les deux côtés depuis le 28/08.** « Appeler Marc » sort une tâche ; « Nadia rigole », deux mots sans action, ne doit pas en sortir une. Le second ne rend RIEN du tout, à confiance 1,0, alors qu'une autre personne y est nommée. |
| R1d | tâche AVEC échéance : reste `task`, remplit `event_date` | `t6` | Un cas, et `event_date` n'est asserté nulle part. |
| R1e | discours rapporté ⇒ `owner` = la personne | `x-reported-speech` | **Complet depuis le 28/08** : les deux manques sont écrits, le discours rapporté d'un ÉVÉNEMENT (deux cas, dont un dicté) et celui où deux personnes sont nommées. Les deux événements rapportés échouent, `owner` reste vide là où la source est nommée. La tâche à deux noms passe : c'est donc l'événement rapporté, pas le discours rapporté, qui perd sa source. |
| R1f | action annulée ⇒ ligne 4 | `x-negation` | Un seul cas. |
| R1g | micro-course triviale ⇒ pas de note ET éphémère | `p1`, `p3`, `g-ephemeral-trivial` | **La corvée ménagère est couverte depuis le 28/08**, trois cas dont un imbriqué dans un progrès de projet. Un seul écart, et c'est un arbitrage : « Vider les poubelles avant le ramassage jeudi » sort en vraie tâche datée alors que l'étiquette la voulait éphémère comme sa jumelle sans échéance. |
| R1h | l'équipement durable n'est PAS un consommable | `p2`, `g-type-ephemeral` | Toute la frontière tient sur un seul objet, le harnais. Le prompt en nomme trois autres. |
| R1i | course au passé : faite, donc jamais un rappel | `x-past-errand` | Un seul cas. |
| R1j | envoyé / payé / classé / déclaré ⇒ engagement, même terse, même nom inconnu | `t2`, `t4` | **Couvert depuis le 28/08**, et les trois cas passent : le nom opaque (« déclarer ça à la boîte »), l'absence totale de nom (« faut que je paie ») et le rôle générique (« envoyer l'attestation au client avant jeudi »). L'engagement sans nom ne disparaît donc PAS ici, contrairement à ce que la perte silencieuse mesurée sur « Payer le loyer » laissait craindre. |

### Ligne 2, événement

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R2a | occurrence datée à laquelle l'auteur assiste | `e1`, `e2`, `e3`, `x-attend-verb`, `x-attend-noun` | Bien couvert. |
| R2b | syntagme nominal sans verbe ⇒ quand même la note | `e1`, `e2`, `e3` | Bien couvert. |
| R2c | on FAIT une tâche, on ASSISTE à un événement ; le verbe ne prouve rien | `x-attend-verb`, `x-attend-noun` | **Couvert depuis le 25/08** : `r2c-verb-event` (« Je participe au forum des associations le 26 ») est le miroir dur, un événement porté par un vrai verbe d'action. On FAIT une tâche, on ASSISTE à un événement ; le verbe ne prouve rien. |
| R2d | `event_date` absolue, résolution du relatif via `{today}` | `e2`, `e3` portent du relatif | **Jamais asserté, et le harnais ne sait pas le vérifier.** Un modèle qui rendrait « mardi » tel quel passerait. |
| R2e | anniversaire, trois formulations, trois réponses | `x-birthday-party`, `x-birthday-birth`, `x-birthday-bare`, `e4`, `g-atomicity-mixed` | La meilleure frontière du corpus. Mais `event_recurring` n'est asserté sur aucun des trois, alors que le champ est scoré. |
| R2f | déjà passé ⇒ ligne 3 | `x-mixed-tense` (partiel) | Faible. |

### Ligne 3, épisode

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R3a | une autre personne NOMMÉE ⇒ épisode, si ordinaire soit-il | `ep1`, `x-pure-episode` | Couvert. |
| R3b | personne d'autre, mais un LIEU digne d'être nommé | `r3b-place-alone`, plus trois cas du 28/08 (présence nue, dicté, tronqué) | **Couvert, et il en sort un défaut isolé.** « Cinémathèque hier » et « J'ai passé l'après-midi au Jardin des Plantes » sortent bien en épisode ; « J'étais seul à la Bibliothèque Forney hier » ne sort RIEN, à confiance 1,0, alors que le moteur crée la fiche du lieu. La seule variable entre les trois est le mot « seul ». |
| R3c | accomplissement : première fois, record, résultat mesurable | `ep1`, `x-episode-first-time` ; contre-exemple `ep2` (un ressenti n'est pas un accomplissement) | Couvert. |
| R3d | l'épisode établit aussi du durable : la note ET le fait | `a3`, `x-mixed-tense` | **Couvert depuis le 25/08** : `r3d-plumber` est l'exemple du prompt lui-même. Le durable attendu est la DATE portée par la note d'épisode, pas un fait, Alexis ayant retiré son propre `facts_min` le 25/08. |
| R3e | un épisode A une date, et une date passée qui REVIENT prend `event_recurring` | `x-past-recurring-date`, plus la paire yoga / piano du 28/08 | **Revenu à zéro cas le 28/08, et pour une bonne raison.** La paire yoga / piano a été écrite puis retirée : Alexis a arbitré qu'une habitude est durable et PÉRISSABLE, donc un fait, jamais un épisode. Une date passée qui revient demande donc un vrai épisode daté, du type « j'ai fêté l'anniversaire de X le 12 juin », et le corpus n'en a aucun. |
| R3f | jamais éphémère | quatre cas du 28/08 (voiture, repas, et leurs deux voisins) | **Écrit, à moitié bloqué.** Le repas avec Thomas asserte enfin `ephemeral=False` et passe. Les deux captures solitaires ne rendent aucune note, donc l'axe n'est pas atteint : même arbitrage en attente que R3e. |
| R3g | pas encore vécu ⇒ ligne 0 ou 1 | `t7`, plus deux paires du 28/08 (dentiste, poterie) | **Les deux paires sont écrites**, chacune isolant la seule variable « déjà vécu ». Les côtés futurs passent tous les deux (tâche et note fondatrice) ; les deux côtés passés ne rendent aucune note, même arbitrage en attente. |

### Ligne 4, note

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| R4a | première personne réflexive | `n1`, `n3`, `g-note-reflexive` | Bien couvert. |
| R4b | citation, ou œuvre / auteur / idée externe sur laquelle l'auteur prend position | six cas `r4b-*` | **Couvert depuis le 26/08**, les deux côtés : la prise de position laisse une note (Descartes, le podcast, Sophie, le documentaire, le désaccord tronqué), et l'œuvre citée SANS position ne laisse qu'une tâche de lecture (`r4b-article-sans-critique`). C'est la position qui décide, pas la présence de l'œuvre. |
| R4c | observation contemplative qui ne se réduit à aucun fait | `n2` | Un cas. |
| R4d | une décision, y compris celle de renoncer | `x-negation` | Un cas. |
| R4e | énoncé fondateur d'un projet | voir R0b | Non asserté. |

## 3. Règles transverses (`classifier-note.md`)

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| X-EPH | les QUATRE conditions d'`is_ephemeral`, une seule qui manque suffit | `p1`, `p2`, `x-past-errand`, `n1`..`n3` | Le mécanisme est couvert. La **coexistence** note + éphémère, autorisée aux seules lignes 1 et 2, n'a aucun cas. |
| X-CONF | la confiance doit tomber sous 0,6 quand le modèle hésite vraiment | quatre cas `conf-*`, plus `x-birthday-bare` (non scoré) et les scénarios | **Les deux côtés existent depuis le 26/08** : `conf-cryptic` et `conf-minimal-action` attendent `needs_review=True`, `conf-clear-task` et `conf-clear-event` attendent False. Reste le défaut mesuré le 21/08, qui n'est pas un trou de corpus : 0 sur ~90 épisodes et 0 sur ~200 notes ne sont jamais passés sous 0,7, donc la file « À valider » reste décorative sur deux des quatre types. |
| X-LANG | détecter la langue, écrire la note dans la MÊME langue, ne jamais traduire | 5 cas EN, 1 ES | `language` n'est asserté nulle part. Aucune capture à cheval sur deux langues, aucune mal orthographiée, aucune tronquée. |
| X-ONE | COMBIEN de souvenirs une capture laisse | `a2`, `a3`, `g-atomicity-mixed`, les six cas `x2-*`, et les captures ordinaires portant `memories: N` | **La définition d'avant le 2026-08-28 disait « exactement UNE note par capture, ou aucune » : c'est périmé et c'était l'inverse de la règle.** Le schéma rend une LISTE. Un second souvenir est dû quand la capture demanderait deux LIGNES dans un carnet : l'une faite et l'autre à faire, dues à deux personnes, ou dont clôturer l'une ne dirait rien de l'autre. Arbitré le 2026-08-29 : les articles d'une même course font UNE tâche, des corvées sans rapport entre elles en font une CHACUNE. Trois souvenirs est rare mais légitime (« pick up dry cleaning, check oil level in the car, pay water bill »), et le prompt de production le décourage encore : écart connu, porté par l'entraînement et non par une nouvelle édition de prose. |

## 4. Le prompt graphe (`classifier-graph.md`)

| # | Frontière | Ce qui la couvre | Verdict |
|---|---|---|---|
| P-DUR | un fait n'existe que pour du DURABLE ; `facts: []` est une bonne réponse | `f1`, `f2`, plus quatre cas du 28/08 | **Couvert des deux côtés.** Le durable sort en graphe (le chat de Marie, la date de naissance), le ponctuel sort en note sans fait, avec `forbidden_predicate` sur l'appel et sur le concert. Reste non couvert le troisième interdit du prompt, redire la phrase de la capture. |
| P-DEDUC | déduire oui, inventer non | `g-atomicity-mixed`, `a1`, `x-no-invention` | Couvert sur le principe. La confiance ≈ 0,6 d'une relation déduite n'est jamais assertée. |
| P-FR | fait contre relation, anti-redite | `r1`, `r2`, `g-relation` | Couvert. |
| P-PERS | l'échelle de persistance décide du nœud | `x-pet-owned`, `x-pet-incidental` | Les deux côtés existent, **mais aucun des deux n'est scoré** (`entity_expected`, `no_entity` sont inertes). |
| P-HEDGE | `evidence_strength` : explicite / prudent / implicite | `h1`, `h2` | N'assertent que `note=False`. Le champ lui-même n'est jamais vérifié. |
| P-BDAY | une date de naissance est un fait, et la FORMULATION dit à quel point elle est sûre | `x-birthday-birth`, `x-birthday-bare`, `bday-bare-review-en`, `e4` (énoncée) ; `x-birthday-party`, `date-birthday-party-recurring` (lue sur une fête, axe `fact_proposed`) ; `bday-party-no-fact`, `bday-age-not-birthdate` (`forbidden_predicate`) | **Complet depuis le 2026-08-26.** Échelle à trois marches arbitrée par Alexis : énoncée ⇒ assertée, lue sur une fête ⇒ **proposée** (la fête tombe souvent le jour même, pas toujours), ni l'un ni l'autre ⇒ aucun fait. Les trois marches sont mesurées, les deux extrêmes par les axes qui existaient, celle du milieu par `fact_proposed`. |
| P-TYPE | le type d'une ENTITÉ nommée reste dans la liste active (personne, lieu, projet, concept, organisation, animal, plus les validés) ; une entité qui n'y rentre pas sort en `concept` avec un `type_proposal` que l'humain valide | rien | La première vague du 28/08 est partie sur « type de note » : la ligne ne disait pas de quoi « type » était le type. La seconde a proposé un concept, qui rentre : le côté adverse demande une entité nommée qui n'est AUCUN des six, ni personne ni lieu ni projet ni concept ni organisation ni animal — un plat, un modèle de voiture, un médicament, une œuvre. **Couvert des deux côtés depuis le 28/08.** Quatre cas du côté « le type existe déjà » (personne, organisation, animal, concept) et un du côté adverse, `p-type-medicament-proposal` : Doliprane et Advil ne sont aucun des six, le moteur pose `concept` et remplit `type_proposal`, il passe. Les deux axes `type_proposal` / `no_type_proposal` ont été ajoutés au scoreur le même jour — sans eux la frontière était inerte, comme P-PERS l'est encore. Un cinquième cas, la bouillabaisse, a migré vers P-PERS : un plat mangé une fois ne franchit pas le seuil de persistance, donc il ne mesure pas le type. |
| P-PROJF | fait de projet (total, budget, palier atteint) ⇒ le projet devient aussi une entité | quatre cas du 28/08 (budget, palier, dicté, plus le voisin sans projet) | **Couvert des deux côtés** depuis le 28/08 : le budget et le palier font naître l'entité projet avec ses faits, la dépense sans projet nommé ne fait naître personne. Le cas dicté est le premier du corpus à faire naître un projet NEUF. |

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
| P-CREATE | entité NOMMÉE sans preuve dans une capture qui laisse une note durable ⇒ **proposée**, pas créée | **ouvert le 2026-08-26**, axe `entity_proposed`, un cas (`ez-coffee-fr`, Hugo). Miroir de la porte du core, à faire bouger avec elle. Manque le côté adverse : une entité que le modèle ferait naître en gonflant la persistance d'un fait |
| P-CREATE′ | un LIEN vaut-il preuve de naissance ? | **tranché le 2026-08-26 : oui, il la fait naître sans demander.** Un lien ne s'écrit que si ses DEUX bouts existent : proposer l'un des deux ferait perdre le lien. Le choix était entre une fiche de trop et un lien perdu. Mesuré sur les 155 cas : 27 entités naissent par un fait durable, 27 par un lien seul, 18 passent en file |
| PERS-b | personne désignée par un rôle et non par un nom (« ma mère », « mon dentiste ») | `f2` existe et n'asserte que `note=False` : personne ne dit si « ma mère » mérite un nœud |
| PERS-c | homonymes : deux Marie dans la même mémoire | trou complet |
| PERS-d | `aliases` : nom partiel puis nom complet | jamais asserté, et **jamais gouverné** (voir la gouvernance des prédicats) |

### NEG, les négations

`x-negation` couvre l'action annulée et c'est tout. C'est une famille, pas une
frontière.

Les propositions de négation ont ouvert `obsoleted_facts` dans la moitié graphe, et avec lui les deux
axes `obsoletes` et `no_obsolete` de `score.py`. NEG-b et NEG-c sont donc
écrivables. Les deux se valent en importance et doivent être écrits ENSEMBLE :
une négation manquée laisse un faux durable sur la fiche, une négation de trop
retire une vérité, et personne ne remarque qu'un fait a disparu.

| # | Frontière | Verdict |
|---|---|---|
| NEG-a | action annulée ⇒ la décision se garde, la tâche non | couvert, 1 cas |
| NEG-b | négation d'un FAIT (« Pierre ne travaille plus chez Acme ») | **débloqué** : asserter `obsoletes="works_at=Acme"`. Trou complet, écrivable dès maintenant |
| NEG-c | négation d'existence (« Marie n'a pas de chat ») | **débloqué** : asserter `no_obsolete=True` ET aucun fait. Une absence énoncée pour la première fois ne nie rien |
| NEG-b′ | un REMPLACEMENT (« il a quitté Acme pour Globex ») | **tranché le 2026-08-26** : l'ancien passe en péremption ET le nouveau est créé avec la bonne valeur, les deux. L'étiquette du 25/08 disait le contraire (`no_obsolete`, le supersede faisant le reste) et comptait un succès comme un écart. Se mesure sur un sujet NOMMÉ : avec un pronom sans antécédent, rien ne s'attache, `entity_canonical` étant requis |
| NEG-b″ | négation nuancée (« je crois qu'il a quitté Acme ») | **débloqué** : `no_obsolete=True`. Retirer une connaissance sur un peut-être est pire que la garder |
| NEG-d | action annulée : la tâche déjà enregistrée doit partir | **débloquée le 2026-08-28** et couverte à moitié. Le POINTEUR (`cancels_action`, l'action annulée nommée dans les mots de la capture) se mesure ici : 7 cas, dont 3 sosies qui ne doivent PAS le remplir (une reprise en dictant, une tâche faite, une correction de fait) et un quatrième dans la table (le report, qui garde sa tâche). La RECHERCHE de la tâche visée ne se mesure pas ici : elle demande un état antérieur, que le contexte figé du harnais n'a pas. Elle est couverte par les tests du core. |
| NEG-e | correction d'une capture antérieure (« en fait c'était mercredi ») | trou complet, toujours bloqué : même rappel, plus le fil de mémoire de travail (mode scénario) |

### PEREMPTION, ce qui remplace ce qui était vrai

| # | Frontière | Verdict |
|---|---|---|
| PER-a | une capture qui périme un fait antérieur doit émettre le NOUVEAU fait, sur les 7 familles mono-valuées de `routing.rs:45` | trou complet, écrivable dès maintenant |
| PER-b | renommage d'entité déclaré en capture | **débloqué** : asserter `renamed_to="Sinam"`, et `no_rename=True` pour les deux confusions voisines — la simple mention du nom, et le surnom, qui est un alias |
| PER-c | un état transitoire ne doit pas devenir un fait durable (`planned_new_name`) | **débloqué** : asserter `forbidden_predicate="planned"`. Le prompt interdit désormais tout prédicat qui encode une intention, `planned_*`, `future_*`, `upcoming_*`, `will_*` |

La moitié qui relève du core ne peut pas être testée ici : le harnais fige le
contexte exprès, donc il n'a aucun état antérieur.

### EMO, la capture émotionnelle

**Tranché le 2026-08-25, 8 cas dans `emotion.jsonl`.** Le prompt ne
disait qu'une chose, « A FEELING IS NOT AN ACHIEVEMENT », et seulement pour un
ressenti collé à une activité routinière (`ep2`). La capture émotionnelle pure
tombait en ligne 5 par défaut, sans que personne ne l'ait décidé.

L'arbitrage tient en un discriminant, le même que celui de la ligne épisode :
**un ressenti rattaché à une CAUSE devient une note, un état nu ne laisse rien.**
« Ça m'angoisse de devoir présenter devant le comité » a une cause ; « je me sens
mal » n'en a pas, et le resservir trois semaines plus tard n'apporte rien.

Trois conséquences, toutes assumées :

* **La règle ne s'applique que si aucune ligne au-dessus n'a pris la capture.**
  L'ordre de la table EST la règle, et c'était le piège : « ce que Marc a dit m'a
  blessé » nomme une personne et raconte du vécu, donc la ligne épisode le prend
  d'abord. Écrire la règle sans cette réserve aurait cassé une règle voisine, ce
  que le ticket annonçait précisément.
* **Une capture émotionnelle qui sort en épisode décroît en 10 jours au lieu de
  30.** Sans effet réel : la décroissance ne supprime rien, elle fait descendre
  dans le classement et dans la recherche.
* **Aucun fait durable sur un état psychique**, interdit explicitement côté
  graphe. Une CONDITION physique durable reste autorisée, et la base en contient
  déjà deux à juste titre. Une condition est un fait, un état est la météo.

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
5. `category`, une fois la gouvernance des prédicats faite.
6. Le prédicat nommé, inécrivable tant que la gouvernance des prédicats n'est pas faite.

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
| Trous complets | ~70 | G-PROGRESS, G-STATUS, R0d, R1c, R3b, R4b, P-TYPE (deux côtés), les 4 familles PERS, NEG-c, PER-a, les miroirs manquants de R3e et R2c, les 4 files assertables. |
| Frontières tenues par un seul cas | ~30 | R1f, R1g, R1h, R1i, R4c, R4d, G-HABIT, R2f, R3g : un deuxième et un troisième objet, une autre formulation. |
| Doute étiqueté | ~15 | Notes et épisodes qui DOIVENT sortir sous 0,7. La tranche que rien ne remplace. |
| Cas faciles, distribution réaliste | ~55 | Les quatre types dans leurs formes ordinaires, plus les captures qui ne laissent rien. |

Langues : viser environ 30 % d'anglais et quelques captures espagnoles ou mêlées,
contre 12 % aujourd'hui. Y inclure du dicté, du tronqué, du mal orthographié.

Les 48 captures existantes ne bougent pas et ne servent jamais à entraîner.

### Premier lot écrit, le 2026-08-25

44 cas ajoutés, en visant l'inverse de ce que le corpus avait : il comptait 75
assertions de routage pour 3 sur les relations, 1 sur la confiance, et zéro sur
la date résolue, la langue et la négation.

| Fichier | Cas | Frontières ouvertes |
|---|---|---|
| `neg.jsonl` | 13 | NEG-b, NEG-c, plus les deux pièges de la famille : le remplacement et la négation nuancée |
| `dates.jsonl` | 11 | R2d dans les deux sens, y compris les deux miroirs « doit rester vide » |
| `langue.jsonl` | 7 | X-LANG, fr/en/es/de, et les deux cas où un prénom ou un anglicisme fait basculer la détection à tort |
| `graphe.jsonl` | 9 | P-BDAY (les trois formulations), P-DEDUC (déduire oui, inventer non), P-PERS (les deux bouts de l'échelle), P-FR |
| `confiance.jsonl` | 4 | X-CONF dans les deux sens : le doute dû, et le doute de trop qui noie la file |

### Deuxième lot, le même jour

31 cas de plus, cette fois sur les trous que la carte nommait sans qu'aucun cas
ne les touche.

| Fichier | Cas | Ce qui s'ouvre |
|---|---|---|
| `porte.jsonl` | 7 | G-PROGRESS et G-STATUS, deux trous complets ; plus les miroirs manquants de G-ATTR, G-HABIT et G-SVO |
| `taches.jsonl` | 9 | R1c (deux mots suffisent), R1g (la corvée ménagère), R1h (deux objets durables de plus), R1j (l'engagement sans nom, et au nom opaque), R1e (deux personnes nommées) |
| `episodes.jsonl` | 4 | R3b (un lieu, personne d'autre), R3d (l'exemple du prompt), R2c (le miroir dur), R2f |
| `projets.jsonl` | 3 | R0b (la note fondatrice), R0d, et le miroir de R0a |
| `facile.jsonl` | 8 | La tranche ordinaire, sans laquelle la confiance se calibre sur un corpus fait uniquement d'arêtes |

### Troisième lot : ce que les arbitrages ont débloqué

`emotion.jsonl` (8 cas) et `renommage.jsonl` (6 cas). Ces deux
familles n'étaient pas des trous d'écriture mais des trous de DÉCISION : rien
n'y était étiquetable tant que le prompt ne tranchait pas.

**État** : 155 cas pour 138 textes distincts, contre 66 pour 49 ce matin, et
16 axes de scoring exercés contre 10.

Lire la couverture par FRONTIÈRE plutôt que par axe : deux axes,
`forbidden_value` et `forbidden_predicate`, sont génériques (« ceci ne doit pas
naître ») et servent aujourd'hui quatre familles à la fois. Les compter par axe
gonflait une frontière avec les cas des autres, ce que le rapport faisait
jusqu'au 25/08.

Deux écarts assumés, à combler dans le palier suivant :

* **L'anglais est à ~19 % des textes**, l'espagnol à ~4 %, l'allemand à un seul
  cas. La cible est 30 % d'anglais. Il manque aussi tout le dicté, le tronqué et
  le mal orthographié.
* **`r0d-two-projects` ne mesure que la moitié de sa règle.** L'axe `proj`
  vérifie qu'au moins une entrée projet existe, jamais leur nombre. Compter les
  entrées est un axe à ouvrir dans `score.py`.

**Toutes les dates de ces cas se déduisent du contexte figé** : lundi
2026-07-13. Un cas dont la résolution dépendrait du jour où on le joue ne
mesurerait rien. « lundi » a d'ailleurs été écarté à dessein — le contexte étant
figé un lundi, le prompt ne dit pas si c'est aujourd'hui ou dans huit jours.

**À trancher, trouvé en écrivant ce lot** : `e4` (« L'anniversaire de Léa est le
16 juin ») est marqué ambigu depuis juillet, au motif que « le prompt ne tranche
pas entre anniversaire-événement et anniversaire-fait ». Le prompt tranche
désormais, explicitement, dans son bloc BIRTHDAYS : une date d'anniversaire nue
donne la note event, récurrente, sous 0,6 de confiance. Le marquage `ambigu` est
donc périmé, et il exclut ce cas du décompte d'échec sans raison. À passer en
revue.

### Ce qui attend un arbitrage

| Famille | Bloquée par |
|---|---|
| ~~NEG-d~~ | débloquée le 2026-08-28 : le pointeur se mesure sans état antérieur, seule la recherche de la cible reste hors du harnais |
| NEG-e, correction d'une capture antérieure | idem, plus le fil de mémoire de travail (mode scénario) |
| Assertion d'un prédicat nommé, `category` | la file des prédicats proposés |

Environ 120 des 150 cas restent écrivables sans rien attendre.
