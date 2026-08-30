# Les baselines gardées, et pourquoi

Une baseline est la sortie complète du modèle sur un lot de cas du corpus, figée
avec l'empreinte du prompt qui l'a produite. Elle sert à deux choses : comparer
deux prompts à corpus égal, et nourrir `pilote.py`, qui exporte le jeu
d'entraînement à partir des cas dont TOUTES les assertions passent.

**Une passe coûte de l'argent réel** : environ 1,60 $ pour 500 cas sur Haiku,
0,45 $ pour 150. C'est la raison d'en garder, et la raison de ne pas en garder
115 dont plus personne ne sait ce qu'elles mesuraient.

## Ce qui reste ici, et ce que ça mesure

**La courbe historique du prompt.** Ces cinq-là se comparent entre elles :
elles ont toutes été RENOTÉES avec les étiquettes du 30/08, donc leurs taux de
conformité veulent dire la même chose. Sans ça, un prompt d'il y a huit jours est
jugé sur des étiquettes qui ont changé depuis, et la comparaison ne dit rien.

| baseline | ce que c'est | tokens/moitié |
|---|---|---|
| `haiku-v28-final` | l'appel unique, avant le découpage en deux moitiés | (un seul appel) |
| `corpus-complet-20260825` | le découpage, première version | 3 453 |
| `corpus-complet-20260828` | le découpage mûri | 5 101 |
| `apres-225-224` | la veille de la réécriture par nœuds | 6 600 |
| `ordinaire-apres-revue` | après la revue des cas ordinaires | 6 210 |
| `apres-reecriture-30-08` | le prompt réécrit depuis les règles, 495 cas | 6 168 |

`apres-reecriture-30-08` est la plus large jamais produite et c'est la référence
pour `pilote.py`.

**Les contrôles ciblés du 30/08.** Ils ne rejouent que les cas en écart d'une
famille, pour vérifier un correctif sans repayer une passe entière.
`controle-3-correctifs` (dates, graphes vides, porte fermée) et
`controle-porte-et-graphe` (ce qui résistait après).

**L'expérience « d'où vient la performance ».** Quatre passes sur les MÊMES 150
cas, ceux présents dans les quatre ancres historiques, donc directement
comparables entre elles et à la courbe ci-dessus.

| baseline | le prompt joué | conformes |
|---|---|---|
| `sans-exemples-150` | la production, exemples en apposition retirés | 122/150 |
| `regles-seules-150` | tiré des 88 règles seules, aucune accrétion | 121/150 |
| `regles-v2-150` | idem, après l'écriture des 5 règles manquantes | 136/150 |
| `regles-v3-150` | idem, rang du bloc anniversaire corrigé | 134/150 |

La production faisait 132/150 sur ce même lot. Ce que ces quatre passes ont
établi est écrit dans `regles-journal.md` : la production ne gagnait pas parce
qu'elle en disait plus, elle gagnait parce qu'elle disait cinq choses que le
document ne disait pas.

**La trace du verdict on-device.** `e2b-v23` et `qwen25-3b-full-split` sont les
deux mesures les plus abouties sur modèle local. Elles sont gardées parce que le
verdict qu'elles ont produit se relit mieux avec ses chiffres qu'avec son
résumé.

## Ce qui a été supprimé le 30/08, et le critère

115 fichiers, 7 Mo. Le critère n'était pas le poids, c'était qu'on ne pouvait
plus dire ce qu'ils mesuraient. Y compris 43 sondes de moins de vingt cas, du
type `dtw-1`, `eph-2`, `controle-r3b` : des diagnostics d'un quart d'heure dont
la conclusion est dans le journal et dont la sortie brute ne servait plus.

**Avant d'en ajouter une, se demander si elle sera lisible dans huit jours.** Un
nom qui dit la question posée (`regles-seules-150`) vaut mieux qu'un numéro
d'essai (`syn224-essai4`). Une sonde qui répond à une question du jour n'a pas
besoin d'être commitée.
