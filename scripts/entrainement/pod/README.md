# Entraîner Qwen 3.5 sur un GPU loué

Ces cinq fichiers montent sur un pod RunPod et n'ont besoin de rien d'autre que
le jeu (`../jeu/`) et `questions.json`. Le harnais de parité, lui, ne quitte
jamais le Mac : le pod ne fait qu'une boucle d'inférence, et c'est le vrai
`score.py` qui note ici. Voir `scripts/parity/providers.py::_call_rejeu` pour
la raison de ce partage des rôles.

## Ce qui a coûté un entraînement le 03/09/2026

**Le disque d'un pod sans volume est effacé à l'arrêt du pod**, et le scratchpad
de session du Mac est effacé au redémarrage. Un entraînement de deux heures et
sa mesure ont disparu des deux côtés le même jour. Donc : créer le pod AVEC un
volume, et redescendre les résultats DANS CE DÉPÔT avant d'arrêter quoi que ce
soit.

## Régénérer `questions.json` (le jour de la mesure)

Le bloc DATES du prompt suit la date du jour : un `questions.json` d'hier porte
une autre empreinte que les baselines d'aujourd'hui, et la comparaison ne veut
alors plus rien dire. Le régénérer, et vérifier que l'empreinte affichée est
celle de la baseline à laquelle on veut se comparer.

```bash
CAS=$(.venv/bin/python -c "import json; print(','.join(json.load(open(
  'scripts/parity/baselines/echelle-qwen35-4b-awq-barreau4.json'))['cases']))")
SYNAPSE_REJEU_ENREGISTRER=/tmp/q.jsonl .venv/bin/python -m scripts.parity.baseline \
  run "rejeu:Qwen/Qwen3.5-4B" --label tmp-questions --cas "$CAS"
# puis regrouper les blocs système et écrire questions.json (186 questions,
# 2 systèmes, max_tokens 4096)
```

## Sur le pod

```bash
bash preparer.sh          # dépendances + contrôle torch.cuda.is_available()
QUANT=nf4 nohup bash enchainer.sh > tout.log 2>&1 &
```

`enchainer.sh` mesure le NU d'abord, entraîne, s'arrête au point 60, mesure
l'entraîné, puis touche `/workspace/FINI`. Le nu passe en premier parce que
c'est le repère : mesuré le même jour, avec la même quantification et le même
harnais que l'entraîné. Se comparer à un chiffre plus ancien a déjà coûté
quatre cas d'illusion.

`QUANT=nf4` entraîne au-dessus du modèle quantifié 4 bits, celui qu'on
déploiera ; `QUANT=bf16` refait la variante pleine précision.

## Noter le résultat, sur le Mac

```bash
SYNAPSE_REJEU_FICHIER=<reponses.json> .venv/bin/python -m scripts.parity.baseline \
  run "rejeu:Qwen/Qwen3.5-4B" --label <nom> --cas "$CAS"
```

Le format que `mesurer.py` écrit est exactement celui que `_call_rejeu` attend,
indexé par empreinte. Ne jamais scorer ces réponses à la main : le 03/09 ça a
donné 0 cas juste sur 186, alors que le harnais les notait sans broncher.

## Résultat de la passe du 03-04/09/2026

Entraînement au prompt COMPLET sur le modèle QUANTIFIÉ, arrêté au point 60,
mesuré sur les 86 cas étiquetés du jeu de test. Tout est noté par le harnais,
à la même moulinette et aux mêmes étiquettes.

| | routage | écarts totaux |
|---|---|---|
| Haiku v35 (la référence) | 97,7 % | |
| Qwen 3.5 4B bf16 nu | 75/86 = 87,2 % | 25 |
| Qwen 3.5 4B AWQ 4 bits nu | 71/86 = 82,6 % | 33 |
| Qwen 3.5 4B NF4 4 bits nu | 75/86 = 87,2 % | 37 |
| **Qwen 3.5 4B NF4 entraîné** | **79/86 = 91,9 %** | **24** |

**+4 cas de routage**, le seuil exact de la règle d'arrêt, et 13 écarts en moins.

**NF4 vaut le bf16, AWQ perd 4 cas.** Le choix du format de quantification pèse
donc autant que l'entraînement, et il est gratuit.

**D'où vient le gain, et c'est contre-intuitif.** Le modèle nu SUR-PRODUISAIT du
graphe : 1,74 fait par cas contre 0,19 attendu par le corpus et 0,19 chez Haiku,
soit neuf fois trop. L'entraînement l'a aligné sur la référence (0,09), ce qui
fait tomber les écarts d'entités (11 → 6), de dates (9 → 5) et de propriétaire
(4 → 0). Le LoRA n'a pas appris à mieux raisonner, il a appris à SE TAIRE là où
la référence se tait.

Attention en relisant ces chiffres : la production de graphe passe de 162 faits
à 8, et 80 cas sur 93 n'en produisent plus aucun. Comparé au modèle NU, ça
ressemble à un effondrement ; comparé à la RÉFÉRENCE, c'est la cible. Comparer
une production au maître et au corpus, jamais au modèle de départ.

**Le défaut qui reste : 4 cas**, pas 9. Neuf cas portent
`atomicité : 0 fait pour 1 attendu`, mais Haiku en rate cinq lui aussi
(`g-ord-souvenir-barbecue-fr`, `g-ord-en-007`, `g-ord-03`, `o-en-1`, `o-en-4`),
qui sont donc une exigence du corpus que la référence n'atteint pas. Les quatre
vraies régressions sont `a3`, `ord-en-08`, `ord-8-serie-discussion-fr` et
`o-fr-sante-rdv`. Dans sept cas sur neuf l'entité EST créée, elle est seulement
vide : le défaut est de ne plus la remplir, pas de ne plus la faire.

Piste si on y revient : le jeu ne porte que 90 faits pour 366 exemples, dont
71 % sans aucun fait ni relation. Sur-échantillonner les exemples porteurs
avant de réentraîner.

### La courbe de perte (les journaux sont ignorés par git)

```
pas    5    10    15    20    25    30    35    40    45    50    55    60
perte  .299  .219  .152  .136  .159  .121  .152  .161  .142  .108  .134  .156
éval                          .1344                                    .1240
```

Plate dès le pas 20, et l'évaluation ne gagne que 0,010 entre les points 30 et
60 : prolonger jusqu'à l'époque entière n'aurait rien changé. Cadence mesurée
136 s/pas en NF4, soit 3 à 4 fois plus lent qu'en bf16 (`bitsandbytes`
déquantifie à chaque passe). Coût réel : 1,66 $ et 3 h de RTX A6000.
