# Écrire une capture de corpus

Ce fichier est le prompt donné à un modèle pour **écrire des captures**. Il ne
les étiquette pas : c'est une seconde étape, faite par quelqu'un d'autre qui a
lu les règles du moteur. Toi, tu ne les as pas, et ce n'est pas un oubli.

Il est complété par une ligne de la carte des frontières et par la liste des
textes déjà présents dans la famille visée.

---

## Ce que tu produis

Des **captures**, c'est-à-dire ce qu'une personne tape ou dicte dans son second
cerveau. Une ligne JSON par cas, rien d'autre, aucun texte autour.

```json
{"id":"g-progress-dicte-fr","text":"bon alors aujourd'hui j'ai bien avancé sur le déménagement, reste les cartons de la cave","frontiere":"G-PROGRESS","why":"Progrès sur un projet en cours, dicté et sans ponctuation. C'est le côté que G-PROGRESS n'a pas : tous ses cas existants sont ponctués. Je m'attends à ce que ça ne laisse aucun souvenir, comme les autres progrès, mais la forme dictée est ce qui est mesuré ici."}
```

Quatre champs, exactement ceux-là :

| champ | ce qu'il porte |
|---|---|
| `id` | un identifiant en minuscules, mots séparés par des tirets, qui dit la frontière et la variante |
| `text` | la capture elle-même, telle qu'une personne l'aurait écrite |
| `frontiere` | le code qu'on t'a donné, recopié |
| `why` | pourquoi ce cas existe (voir la dernière section) |

**N'écris aucun autre champ.** Pas `note`, pas `kind`, pas `event_date`. Ce
n'est pas de la modestie : une étiquette écrite sans les règles est une
étiquette fausse, et une étiquette fausse fait corriger ce qui marchait.

Deux champs te sont interdits pour une autre raison : `valide` et `arbitrage`
appartiennent à l'humain qui relit. Le premier dit qu'il a validé, le second
porte sa décision sur un cas qui coinçait, et un cas qui en porte un l'attend,
lui. En écrire un reviendrait à signer à sa place.

---

## La règle qui prime sur toutes les autres

**Tu n'as pas accès aux règles du classifieur, et c'est délibéré.**

Si tu écrivais des cas à partir de ces règles, tu produirais des cas que ces
règles gèrent déjà. Un corpus dérivé du règlement ne peut pas trouver un trou
que le règlement n'a pas : il grave les défauts existants au lieu de les
révéler. C'est le mode d'échec que ce corpus existe pour éviter.

Tu écris donc à partir de **deux choses seulement** :

1. la frontière qu'on te donne, avec ce qui la couvre déjà et ce qui manque ;
2. ce qu'une personne réelle écrirait dans cette situation.

Quand les deux sont en tension, la personne réelle gagne. Si tu penses qu'un cas
mérite une réponse que la frontière n'a pas l'air d'attendre, **écris-le quand
même et dis-le dans `why`**. Un désaccord documenté est le signal le plus
précieux que tu puisses produire : il pointe soit une règle à changer, soit une
frontière mal décrite. Le taire pour rendre une copie propre fait perdre les
deux.

---

## Une frontière n'est couverte que si ses DEUX côtés le sont

Un seul côté n'apprend rien : il autorise la règle paresseuse « tout ce qui
ressemble à X est X » à passer pour la bonne réponse.

Pour chaque frontière, écris donc par paires :

- le cas **qui déclenche** la règle ;
- le cas **voisin qui ne la déclenche pas**, aussi proche que possible du
  premier. Plus la différence est petite, plus la paire est utile.

La bonne paire ne diffère que par ce qui compte. « Le devis pour Acme est parti
ce matin » contre « Le devis est parti ce matin » vaut mieux que deux phrases
sans rapport, parce qu'elle isole exactement une variable. Dis dans `why`
de quel côté tu es et quelle est la variable.

---

## Comment les gens écrivent vraiment

Le corpus actuel a **une seule plume** : du français correct, ponctué,
grammatical, écrit par la même personne. C'est sa faiblesse principale et c'est
là que tu apportes le plus. Distribue tes cas :

- **dicté** — pas de ponctuation, des « euh », des faux départs, des reprises :
  « faut que je rappelle euh le dentiste enfin non le kiné pour jeudi » ;
- **tronqué** — deux ou trois mots, sans verbe, sans sujet : « rdv kiné jeudi »,
  « relancer sophie » ;
- **mal orthographié** — accents manquants, doigts pressés, correction
  automatique qui a mal corrigé : « aplé le plombié il vien mardi » ;
- **à cheval sur deux langues** — la formulation naturelle d'un bilingue :
  « meeting avec Sophie demain 14h », « j'ai fini le sprint planning » ;
- **en anglais** — vise environ 30 % du total, contre 12 % aujourd'hui ;
- **registres autres** — quelqu'un de plus âgé, de plus jeune, de plus formel,
  de plus sec. Pas seulement toi avec un accent.

Ne rends pas tout difficile pour autant. Un corpus où tout est ambigu enseigne
un monde où tout est ambigu, et la confiance du modèle devient inexploitable.
Or c'est cette confiance qui alimente la file de validation, seul garde-fou
contre la perte silencieuse. Écris des cas **ordinaires** en proportion
réaliste.

---

## Contraintes de fond

**Synthétique et anonyme.** Le corpus vit dans un dépôt public. Aucun nom réel,
aucune adresse, aucun numéro, aucune donnée d'un testeur, aucune URL interne.
Invente des prénoms courants et des sociétés fictives, et varie-les : le corpus
actuel tourne en boucle sur les mêmes cinq prénoms, ce qui apprend les prénoms
plutôt que les formes.

**N'empile pas par commodité, empile par intention.** Mettre trois frontières
dans une phrase pour aller plus vite rend le cas illisible : quand il échoue, on
ne sait pas laquelle a lâché.

Mais la **capture qui porte plusieurs choses est elle-même une famille à
couvrir**, et c'est une des plus fréquentes dans la vraie vie. Trois formes, à
écrire toutes les trois, en disant dans `why` laquelle tu vises :

- **plusieurs faits ou relations** sur les mêmes personnes : « Marc est né le
  3 mars, c'est le neveu de Julie et il vit à Nantes » ;
- **plusieurs projets** dans une même phrase ;
- **plusieurs souvenirs de nature différente** — un épisode passé ET une tâche
  future, une note ET un événement : « J'ai appelé le dentiste ce matin, il faut
  que je rappelle jeudi ». Ceux-là sont les plus intéressants et les plus mal
  couverts. Dis dans `why` ce que la capture devrait laisser **en
  entier**, sans te demander si le moteur en est capable : ce n'est pas ta
  question, et une capture écrite pour ménager le moteur ne mesure plus rien.

**Le temps de référence est fourni**, et c'est un lundi. Écris tes dates comme
une personne les écrit, c'est-à-dire relatives : « mardi », « hier », « le 12 ».
Les résoudre est le travail de l'étape suivante, pas le tien.

**Pas de doublon.** On te donne les textes déjà présents. Une reformulation
cosmétique d'un cas existant ne mesure rien de plus et coûte le même prix à
chaque passe.

---

## Ce que ton `why` doit dire

C'est le seul endroit où tu parles, et il est lu deux fois : par celui qui
étiquettera ta capture, qui le complétera avec la règle qu'il a appliquée, et
par l'humain qui relira les deux. Trois choses, en deux ou trois phrases, en
français :

1. **ce que le cas mesure** — quelle frontière, quel côté, quelle variable
   change par rapport à son voisin ;
2. **ce que la capture devrait laisser en mémoire**, du point de vue de la
   personne qui l'a écrite, jamais du point de vue d'un extracteur. Dis-le en
   français ordinaire, pas en noms de champs ;
3. **ce dont tu n'es pas sûr**, s'il y a lieu, et ce qui trancherait.

Le troisième point est celui qu'on lit en premier à la revue. Une incertitude
nommée fait gagner du temps ; une incertitude tue en fait perdre.

Ne justifie jamais un cas par « c'est ce que le classifieur ferait ». Tu ne sais
pas ce qu'il ferait, et cette phrase est la définition exacte de ce qu'on ne
veut pas.
