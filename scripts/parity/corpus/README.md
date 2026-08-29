# Le corpus, famille par famille

Une ligne JSON par cas, un fichier par famille. Le format et la liste des
champs sont documentés dans `../corpus.py` ; ici c'est le contexte qui porte
sur une famille entière, celui qu'une ligne ne peut pas raconter.

Ajouter un fichier `<nom>.jsonl` suffit à créer un jeu : `corpus.py` le charge,
`baseline.py` le rejoue. Rien à déclarer ailleurs.

**Les identifiants sont des clés.** Les baselines sont indexées dessus :
renommer un cas, c'est perdre son historique de mesure. Le chargeur refuse les
doublons pour la même raison.

## `gate.jsonl` — douze cas, douze modes de défaillance rédhibitoires

L'étage 1. Son but n'est pas de mesurer la qualité, c'est de rendre un NO-GO en
minutes plutôt qu'en soirée. Un modèle qui échoue ici ne mérite pas les
quarante-neuf autres cas.

Il vérifie sur les douze, en plus des assertions : la validité du JSON, la
troncature, et le respect des énumérations fermées.

Un cas instable n'a rien à faire ici — l'étage 1 doit être capricieux sur les
modèles, jamais sur lui-même. C'est pourquoi `u1` vit dans `hard.jsonl` et pas
ici, alors qu'il teste la même chose que `g-type-resource`.

## `hard.jsonl` — les vingt-neuf cas durs

Portés depuis le harnais de juillet 2026, qui ne survivait que
recopié dans un document Linear. Ils couvrent les familles de routage une par
une : tâche adressée, événement nominal, intention triviale, note réflexive,
projet, fait contre relation, formulation prudente, ressource, épisode.

## `atomicity.jsonl` — une capture, plusieurs sorties

Ajoutés avec le classifieur en deux appels : l'atomicité n'était couverte
par aucun cas du harnais de juillet. La règle qu'ils protègent est toujours la même — une capture mixte
doit produire la note ET les faits, jamais l'un À LA PLACE de l'autre.

## `adversarial.jsonl` — ce que le prompt ne dit nulle part

Issus des arbitrages des 19 et 20 août 2026. Plusieurs portent des attentes que
le scoring ne savait pas vérifier au moment où ils ont été écrits : ils étaient
là quand même, pour observer ce que les modèles font quand personne ne leur dit
rien. Un cas qu'on n'a pas encore joué est un cas dont on ne sait rien.

Depuis la mise en corpus étiqueté, `score.py` sait lire tous leurs axes.

## `scenario.jsonl` — la capture n'est pas seule

Les autres étages classent une capture dans le vide. La production, elle, ajoute
la MÉMOIRE DE TRAVAIL : le fil des captures récentes, avec la consigne
explicite « n'extrais rien de ce bloc ». La consigne est respectée à la lettre —
rien n'est extrait du bloc — et pourtant le bloc DÉPLACE la décision prise sur
la capture courante.

Mesuré le 2026-08-20 sur l'installation réelle, deux fois, sur deux règles
différentes. C'est ce qui rend ce mode nécessaire : ces cas passent les étages 1
et 2 sans broncher, et échouent en prod.

* `wm` — les captures antérieures du fil, dans l'ordre.
* `repeat` — le nombre de passes. La défaillance est une INSTABILITÉ (3 fois sur
  5, pas 5 sur 5) : une seule passe ne la voit pas.
* `expect` — la branche attendue, celle que le même prompt produit de façon
  100 % stable quand la capture est seule.

Chaque cas instable est accompagné d'un TÉMOIN : la même capture avec un fil
sans rapport, ou sans fil du tout. Sans lui, on attribuerait au mauvais coupable
— « la mémoire de travail déstabilise » et « ces captures contiennent des
quasi-jumelles » ne se distinguent pas autrement.

## Ce que le corpus ne fait pas

**Il ne s'entraîne sur rien.** C'est une suite de régression et un jeu
d'arbitrage, pas un jeu d'entraînement.

**Il ne prend pas ses étiquettes dans la mémoire de production.** Le dogfood
donne des ÉNONCÉS, jamais des ÉTIQUETTES : la base réelle contient des bugs, et
mesurer contre elle reviendrait à figer ce qu'on veut corriger.
