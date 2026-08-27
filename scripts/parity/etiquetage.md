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
- Quand un prompt tranche **contre** ce que dit l'`arbitrage` de la capture,
  étiquette selon le prompt, et signale la contradiction dans `why`. Ce
  désaccord est précisément ce qu'on cherche : soit la règle est à changer, soit
  la capture est à jeter, et c'est un humain qui le décide.

---

## Le vocabulaire est fermé

N'invente ni champ ni valeur. Un champ hors liste ne lève aucune erreur : il ne
vérifie simplement rien, et le cas passe pour vert en n'ayant rien mesuré.

| assertion | valeurs | ce qu'elle dit |
|---|---|---|
| `note` | `true` / `false` | **un `atomic_note` est-il produit**, de n'importe quelle nature. ⚠ Le champ s'appelle `note` et `note` est aussi une valeur de `kind` : ce sont deux choses différentes. Une tâche, un événement et un épisode ont tous `note: true`. `note: false` veut dire que la capture ne laisse RIEN, pas qu'elle ne laisse pas un `kind: note`, et pas non plus qu'elle sort de la frontière visée |
| `kind` | `note`, `task`, `event`, `episode` — **ces quatre-là et rien d'autre** | de quelle nature. Jamais sans `note: true` |
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
| `forbidden_predicate` / `forbidden_value` | une chaîne | ceci ne doit PAS être écrit |
| `obsoletes` / `no_obsolete` | `predicat` ou `predicat=valeur` / `true` | ce que la capture périme, ou qu'elle ne périme rien |
| `renamed_to` / `no_rename` | un nom / `true` | le renommage déclaré, à proposer et jamais à appliquer |
| `drop_guard` | `true` | quelque chose de durable doit survivre, sans dire quoi |

---

## Un axe absent vaut mieux qu'un axe faux

**Un champ absent = axe non vérifié**, et c'est une position légitime : on ne
reproche jamais à un modèle une exigence que personne ne lui a formulée. Un axe
faux, lui, fait corriger un comportement qui marchait.

Ne remplis donc que ce que tu sais **dériver d'une règle écrite**. Sur une
capture qui ne parle pas de dates, n'écris pas `event_date`. Sur une capture
sans personne nommée, n'écris pas `owner`.

Il te faut malgré tout **au moins une assertion** par cas. Un cas qui n'asserte
rien passerait pour vert en n'ayant rien mesuré, ce qui est le pire état
possible pour un corpus. Si vraiment aucune assertion ne tient, c'est que la
capture ne sert à rien : dis-le dans `why` et pose `"ambigu": true`.

---

## Les cas où la bonne réponse n'est pas exprimable

Le schéma de sortie n'accepte **qu'un seul souvenir par capture** (« exactly ONE
atomic_note per capture, or none »). Sur « J'ai appelé le dentiste ce matin, il
faut que je rappelle jeudi », le moteur garde la tâche et perd l'appel déjà
passé : les deux réponses sont défendables et aucune n'est juste.

Sur ces cas : **n'asserte ni `note` ni `kind`**. Une étiquette posée là mesure
un choix arbitraire, pas une règle. Asserte ce qui **survit** quoi qu'il arrive
(`drop_guard`, `facts_min`, `entity_expected`), et dis dans `why` ce que la
capture aurait dû laisser en entier.

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
- `arbitrage` est recopié tel quel. C'est la parole de celui qui a écrit la
  capture, elle ne t'appartient pas.
- `why` est le tien : d'où vient l'étiquette, quelle règle, et ce qui t'a fait
  hésiter.
- **N'écris jamais `valide`.** Ce champ n'est posé que par un humain, à travers
  l'outil de revue. Ton étiquette est une proposition.

```json
{"id":"g-progress-dicte-fr","text":"bon alors aujourd'hui j'ai bien avancé sur le déménagement, reste les cartons de la cave","frontiere":"G-PROGRESS","arbitrage":"…","note":false,"why":"Porte G-PROGRESS : un avancement sur un travail en cours ne laisse rien. La forme dictée ne change aucune condition de la porte, qui ne parle que du contenu."}
```
