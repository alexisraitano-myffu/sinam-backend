# Écrire un cas de corpus

Ce fichier est le prompt donné à un modèle pour **écrire des captures**, pas pour
les étiqueter. Il est complété par une seule ligne de la carte des frontières et
par la liste des textes déjà présents dans la famille visée.

---

## Ce que tu produis

Des **captures**, c'est-à-dire ce qu'une personne tape ou dicte dans son second
cerveau, plus une étiquette **proposée** que l'auteur du corpus validera ou
corrigera. Une ligne JSON par cas, rien d'autre, aucun texte autour.

```json
{"id":"g-progress-dicte-fr","text":"bon alors aujourd'hui j'ai bien avancé sur le déménagement, reste les cartons de la cave","note":false,"frontiere":"G-PROGRESS","arbitrage":"Progrès sur un projet en cours, dicté et sans ponctuation. La porte doit le jeter comme les autres progrès. C'est le côté que G-PROGRESS n'a pas."}
```

Champs obligatoires : `id`, `text`, `frontiere`, `arbitrage`, et **au moins une
assertion**. Un cas qui n'assertait rien passerait pour vert en n'ayant rien
mesuré, ce qui est le pire état possible pour un corpus.

**N'écris jamais `valide`.** Ce champ n'est posé que par un humain, à travers
l'outil de revue. Ton étiquette est une proposition, et `arbitrage` est
l'endroit où tu expliques ce que tu as voulu mesurer et pourquoi.

---

## La règle qui prime sur toutes les autres

**Tu n'as pas accès à la table de routage, et c'est délibéré.**

Si tu écrivais des cas à partir des règles du classifieur, tu produirais des cas
que ces règles gèrent déjà. Un corpus dérivé du règlement ne peut pas trouver un
trou que le règlement n'a pas : il grave les défauts existants au lieu de les
révéler. C'est le mode d'échec que ce corpus existe pour éviter.

Tu écris donc à partir de **deux choses seulement** :

1. la frontière qu'on te donne, avec ce qui la couvre déjà et ce qui manque ;
2. ce qu'une personne réelle écrirait dans cette situation.

Quand les deux sont en tension, la personne réelle gagne. Si tu penses qu'un cas
devrait recevoir une réponse que la frontière n'attend pas, **écris-le quand
même et dis-le dans `arbitrage`**. Un désaccord documenté est le signal le plus
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
sans rapport, parce qu'elle isole exactement une variable.

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

**Une capture, une situation.** N'empile pas trois frontières dans une phrase
pour être efficace : quand un cas composite échoue, on ne sait pas laquelle a
lâché. Sauf si la frontière visée EST l'empilement, auquel cas dis-le.

**Le temps de référence est fourni**, et c'est un lundi. Toute date relative
(« mardi », « hier », « le 12 ») se résout par rapport à lui, et ton étiquette
doit porter la date absolue, jamais la relative.

**Pas de doublon.** On te donne les textes déjà présents. Une reformulation
cosmétique d'un cas existant ne mesure rien de plus et coûte le même prix à
chaque passe.

---

## Ce que ton `arbitrage` doit dire

Trois choses, en deux ou trois phrases, en français :

1. **ce que le cas mesure** — quelle frontière, quel côté ;
2. **pourquoi la réponse proposée est celle-là**, du point de vue de la personne
   qui a écrit la capture, jamais du point de vue d'un extracteur ;
3. **ce dont tu n'es pas sûr**, s'il y a lieu, et ce qui trancherait.

Le troisième point est celui qu'on lit en premier à la revue. Une incertitude
nommée fait gagner du temps ; une incertitude tue en fait perdre.

Ne justifie jamais une étiquette par « c'est ce que le classifieur ferait ».
Cette phrase est la définition exacte de ce qu'on ne veut pas.
