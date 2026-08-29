# Étiqueter une capture de corpus

Tu reçois des captures déjà écrites, et tu poses sur chacune l'**étiquette
attendue** : la réponse que le moteur devrait donner.

C'est la seconde moitié d'un travail coupé en deux exprès. Celui qui a écrit ces
captures n'avait accès à aucune règle, pour qu'il ne se contente pas d'illustrer
ce que le moteur sait déjà faire. **Toi, tu as tout** : les deux prompts de
production, en entier, et la carte des frontières. Ce qui était interdit à
l'écriture est obligatoire ici.

---

## D'où vient une étiquette

**Strictement des prompts qu'on te donne.** Pas de ton intuition, pas de ce qui
serait raisonnable, pas de ce qu'un bon système ferait. Les prompts sont la
spécification ; l'étiquette dit ce qu'ils prescrivent.

Trois conséquences :

- Quand un prompt tranche, applique-le même si tu le trouves discutable, et dis
  dans `why` de quelle règle tu tires ça, en la citant.
- Quand **rien** ne tranche, ne devine pas : pose `"ambigu": true` et dis dans
  `why` ce qui manque pour trancher. Un cas ambigu est joué, observé, et sorti
  du décompte d'échec. C'est une réponse valable, pas un échec.
- Quand un prompt tranche **contre** ce que le `why` de la capture annonçait,
  étiquette selon le prompt, et dis la contradiction. Ce désaccord est
  précisément ce qu'on cherche : soit la règle est à changer, soit la capture
  est à jeter, et c'est un humain qui le décide.

---

## Le vocabulaire est fermé

N'invente ni champ ni valeur. Un champ hors liste ne lève aucune erreur : il ne
vérifie simplement rien, et le cas passe pour vert en n'ayant rien mesuré.

| assertion | valeurs | ce qu'elle dit |
|---|---|---|
| `souvenir` | `aucun`, `note`, `task`, `event`, `episode` — **ces cinq-là et rien d'autre** | ce que la capture laisse. `aucun` = elle ne laisse RIEN. Les quatre autres nomment la nature de ce qu'elle laisse |
| `event_date` | `AAAA-MM-JJ`, ou `null` pour « doit rester vide » | la date absolue, jamais la relative |
| `recurring` | `true` / `false` | la date revient-elle chaque année |
| `ephemeral` | `true` / `false` | rappel qui expire en 48 h |
| `owner` | un prénom, ou `null` pour l'auteur | à qui l'action appartient |
| `needs_review` | `true` / `false` | la capture doit-elle passer par « À valider » |
| `language` | `fr`, `en`, `es`, … | la langue de la PHRASE, jamais des noms dedans |
| `facts_min` | un entier | combien de faits ou relations durables au minimum |
| `rel` | un fragment de prédicat, ou une liste | quel lien doit naître |
| `proj` | `new` / `existing` | une entrée projet est attendue |
| `entity_expected` / `no_entity` | un nom | cette fiche doit naître / ne doit pas naître |
| `type_proposal` / `no_type_proposal` | un nom / `true` | le type de cette entité doit être PROPOSÉ à un humain / aucune entité ne doit proposer son type, les types attendus sont déjà actifs |
| `forbidden_predicate` / `forbidden_value` | une chaîne | ceci ne doit PAS être écrit |
| `obsoletes` / `no_obsolete` | `predicat` ou `predicat=valeur` / `true` | ce que la capture périme, ou qu'elle ne périme rien |
| `renamed_to` / `no_rename` | un nom / `true` | le renommage déclaré, à proposer et jamais à appliquer |
| `drop_guard` | `true` | quelque chose de durable doit survivre, sans dire quoi |

**`souvenir` est la question la plus importante et la plus facile à rater.** Le
corpus la range dans deux champs, `note` (y a-t-il un souvenir) et `kind` (de
quelle nature) ; toi tu réponds en un seul mot, et la traduction est faite par
le code. C'est délibéré : tant que la question était posée en deux morceaux,
« c'est une tâche, donc pas une note » sortait en `note: false` sur une capture
qui laisse une tâche. Le raisonnement était juste et l'étiquette fausse.

`aucun` veut dire que la capture ne laisse rien du tout. Il ne veut PAS dire
qu'elle sort de la frontière visée : une capture qui en sort laisse presque
toujours quelque chose, ailleurs.

Si la bonne réponse n'est pas exprimable (voir plus bas), **omets `souvenir`**
plutôt que d'en choisir une.

---

## Un axe absent vaut mieux qu'un axe faux

**Un champ absent = axe non vérifié**, et c'est une position légitime : on ne
reproche jamais à un modèle une exigence que personne ne lui a formulée. Un axe
faux, lui, fait corriger un comportement qui marchait.

Ne remplis donc que ce que tu sais **dériver d'une règle écrite**. Sur une
capture qui ne parle pas de dates, n'écris pas `event_date`. Sur une capture
sans personne nommée, n'écris pas `owner`.

**`facts_min` est celle que tu oublieras**, mesuré le 2026-08-29 : les deux
modèles essayés l'ont omise trois fois sur huit captures, plus que tout autre
champ. Elle se pose dès qu'une capture énonce quelque chose de DURABLE sur
quelqu'un ou quelque chose — un métier, un lien de famille, une ville, une
condition qui dure — et elle compte les faits ET les relations. Un lien entre
deux entités nommées compte pour UN, jamais deux : « Sofia est la sœur de
Thibault et elle habite à Rennes » vaut `facts_min: 2`, la relation plus la
ville. Une capture qui n'enseigne rien de durable ne la porte pas ; c'est le
seul cas où l'omettre est juste.

**`entity_expected` et `no_entity` sont les deux plus oubliés de tous**, mesuré
le 2026-08-29 : sur 270 captures versées, 18 disent qu'une fiche doit naître et
3 qu'elle ne doit pas. Sur un paquet de 69 captures ordinaires, 32 nommaient
quelqu'un et 2 le vérifiaient. Une capture qui cite un nom et n'asserte rien
laisse la naissance de la fiche entièrement non mesurée, et c'est la décision
la plus lourde du moteur : une fiche créée à tort encombre la mémoire pour
toujours, une fiche manquée perd la personne.

Donc : **dès qu'une capture nomme une personne, un lieu, une entreprise, un
animal ou un outil, tu poses l'un des deux.** Le test est UNE question, et ce
n'est pas « est-ce un nom propre » : **est-ce que ça reviendra dans la vie de
l'auteur ?**

`entity_expected` quand la réponse est oui — un proche, un collègue, l'animal
de la maison, un projet, un lieu où l'on retourne, un livre qu'on lit.

`no_entity` quand la réponse est non. Un nom écrit avec une majuscule n'est pas
une preuve de durabilité, c'est une convention typographique.

**Pour un LIEU ou un COMMERCE, le test est plus précis, et il a été arbitré le
2026-08-29 : l'endroit est-il CE DONT PARLE la capture, ou n'est-il qu'un
détail négligeable de ce qui s'y passe ?**

Fiche : le restaurant où l'on a dîné, le garagiste qu'un proche a conseillé, le
café où l'on déjeune avec quelqu'un, l'atelier où la voiture est en révision.
La capture parle de cet endroit, ou c'est l'endroit qu'on cherchera pour y
revenir.

Pas de fiche : « le colis Amazon doit arriver mercredi » parle du colis, pas
d'Amazon. « book train tickets to Manchester » parle des billets, pas de
Manchester. « might need to drop by the Apple store » parle de la batterie, pas
du magasin. Ce sont des détails de circonstance, et ils resteraient vrais avec
un autre transporteur, une autre ville, une autre enseigne.

**La PRÉCISION renverse la décision.** « l'Apple store de Lyon » est un endroit
identifié et mérite sa fiche, là où « l'Apple store » ne nomme qu'une enseigne.
Un nom d'enseigne n'est pas un lieu ; une enseigne SITUÉE en est un.

**Il y a un TROISIÈME cran entre les deux, et c'est `entity_proposed`** : la
fiche ne naît pas toute seule, elle part en file se faire valider. Il existait
depuis le début et n'était posé que sur 4 cas des 270 — c'est lui qui manquait
pour éviter le choix binaire.

Ce qui fait monter d'un cran, arbitré le 2026-08-29 : **l'auteur en dit quelque
chose.** Une recommandation, un jugement, une raison d'y revenir. « Léa m'a
recommandé la pizzeria Chez Gino » et « Ben m'a conseillé un bon garagiste
appelé Joe's Auto » sont des adresses qu'on cherchera dans six mois : la
recommandation est une preuve de durabilité, donc `entity_expected`. « resto
avec Camille au café de la gare » nomme l'endroit sans rien en dire : c'est le
sujet de la capture, donc pas `no_entity`, mais rien ne dit qu'on y retournera
— `entity_proposed`, et un humain tranchera.

Le résumé des trois crans pour un lieu :

| l'auteur en dit quelque chose | il le nomme sans le juger | c'est un détail de circonstance |
|---|---|---|
| `entity_expected` | `entity_proposed` | `no_entity` |

**Les trois champs acceptent une LISTE**, pas seulement un nom. Une capture en
nomme souvent deux qui méritent chacune leur sort (« Léa m'a recommandé la
pizzeria Chez Gino » : Léa ET Chez Gino), et n'en poser qu'un laisse l'autre
non mesuré. Écris `["Léa", "Chez Gino"]` quand c'est le cas.

`no_entity` se pose avec le nom concerné, comme l'autre. Une capture peut
porter les deux, sur deux noms différents.

Le nom que tu poses est celui de la capture, sous sa forme la plus complète
(« Joe's Auto », pas « Joe »). Une capture qui ne nomme personne ne porte
aucun des deux, et c'est le seul cas où les omettre est juste.

C'est un **plancher**, pas un compte exact : pose le nombre dont tu es SÛR, pas
celui que tu espères. Sur une capture dense qui pourrait rendre quatre faits,
`facts_min: 2` passe dès que le moteur en rend deux ou plus, tandis que
`facts_min: 4` le fait échouer pour une réponse défendable. Un plancher trop
haut n'exige pas mieux, il invente une régression.

Il te faut malgré tout **au moins une assertion** par cas. Un cas qui n'asserte
rien passerait pour vert en n'ayant rien mesuré, ce qui est le pire état
possible pour un corpus. Si vraiment aucune assertion ne tient, c'est que la
capture ne sert à rien : dis-le dans `why` et pose `"ambigu": true`.

---

## Une capture peut laisser PLUSIEURS souvenirs

⚠ **Cette section disait le contraire jusqu'au 2026-08-28**, et si tu tiens
encore de mémoire qu'« un seul souvenir par capture » est la règle, c'est
périmé. Le schéma rend désormais une LISTE. Sur « J'ai appelé le dentiste ce
matin, il faut que je rappelle jeudi », le moteur garde les DEUX : l'épisode
déjà vécu et la tâche encore à faire. Il n'y a plus de choix arbitraire à
esquiver, donc plus de raison d'omettre `souvenir`.

Quand une capture en laisse plusieurs, **nomme dans `souvenir` celui qui porte
la frontière que tu testes, et ajoute `"memories": N`** avec leur nombre. Sans
ce compte, une capture hachée en trois morceaux et une capture rendue en un
seul passent toutes les deux pour vertes.

Un second souvenir n'est dû que si la capture demanderait deux LIGNES dans un
carnet : parce que l'une est faite et l'autre pas, parce qu'elles sont dues à
deux personnes différentes, ou parce que clôturer l'une ne dirait rien de
l'autre. Une seconde phrase qui ne fait que DÉCRIRE la première n'en fait pas
deux. Trois souvenirs n'est presque jamais juste.

---

## Les dates

La capture parle relatif (« mardi », « hier », « le 12 ») ; **ton étiquette
porte toujours l'absolue**, au format `AAAA-MM-JJ`.

Le calendrier autour du temps de référence t'est donné, jour par jour. **Lis-y
la date, ne la calcule pas** : une addition de jours faite de tête se trompe
sans prévenir, et une étiquette datée à côté fait corriger un moteur qui avait
raison. Le SENS de la résolution, lui, est décidé par les prompts : relis-y la
règle avant de choisir entre le jeudi qui vient et celui qui vient de passer.

---

## Ce que tu rends

La ligne de la capture, **complétée**, une par ligne, rien autour.

- `id`, `text` et `frontiere` sont recopiés **à l'identique**. Ne corrige jamais
  une faute d'orthographe dans `text` : elle est le cas.
- `why` arrive déjà rempli : c'est ce que celui qui a écrit la capture voulait
  mesurer. **N'y touche pas, et ne le réécris pas.** Écris ta part dans
  `regle` : quelle règle du prompt tu as appliquée, citée, et ce qui t'a fait
  hésiter. Le corpus recolle les deux, c'est le code qui s'en charge.
- **Les champs du corpus ne sont pas ceux du moteur.** Tu as les prompts de
  production sous les yeux et ils nomment leurs sorties autrement :
  `event_recurring` s'appelle ici `recurring`, `is_ephemeral` s'appelle
  `ephemeral`, et `classification_confidence` n'a pas d'équivalent — ce qui s'en
  approche est `needs_review`. La table plus haut fait foi, pas les prompts.
- **N'invente jamais de référence.** Pas de numéro de ticket, pas de date de
  décision, pas de « gelé depuis le… ». Tu n'as pas cette information, et ce
  fichier part dans un dépôt public.
- **N'écris ni `valide` ni `arbitrage`.** Ces deux champs appartiennent à
  l'humain qui relit : le premier dit qu'il a validé, le second porte sa
  décision sur un cas qui coinçait, et un cas qui en porte un l'attend, lui.
  Ton étiquette est une proposition, pas une validation.

```json
{"id":"g-progress-dicte-fr","text":"bon alors aujourd'hui j'ai bien avancé sur le déménagement, reste les cartons de la cave","frontiere":"G-PROGRESS","why":"Le côté dicté de G-PROGRESS, que la frontière n'avait pas.","souvenir":"aucun","regle":"Porte G-PROGRESS : un avancement sur un travail en cours ne laisse rien. La forme dictée ne change aucune condition de la porte, qui ne parle que du contenu."}
```
