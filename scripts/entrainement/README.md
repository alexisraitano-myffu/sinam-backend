# Jeu d'entraînement

`python -m scripts.entrainement.construire --ecrire`

Produit `jeu/{note,graphe}-{train,test}.jsonl` plus `jeu/provenance.json`.
Le dossier `jeu/` n'est pas suivi par git : il se régénère en trois secondes, et
il changera à chaque fois qu'une étiquette du corpus bouge.

## D'où viennent les sorties

Le corpus ne porte que des **assertions** (`note`, `kind`, `facts_min`,
`entity_expected`…), jamais la réponse JSON attendue. Il n'y a donc rien à
entraîner tel quel.

Mais les baselines gardées stockent la sortie complète du modèle sous `parsed`.
**444 des 495 cas ont déjà une réponse Haiku qui passe toutes leurs
assertions.** Le script les récolte au lieu de repayer une passe : construire le
jeu ne coûte aucun appel API.

Une sortie n'est retenue que si `score.gaps()` la déclare sans écart **contre les
étiquettes d'aujourd'hui**. Les `gaps` figés dans les fichiers de baseline ont
été calculés le jour de la passe, et cinq étiquettes ont changé depuis le 30/08 :
les relire tels quels ferait entrer dans les poids des sorties qu'on a depuis
jugées fausses. Le recalcul se fait en mémoire, aucune baseline n'est réécrite.

## Ce que le filtre garantit, et ce qu'il ne garantit pas

Le filtre est **le corpus**, jamais le prompt. C'est ce qui rend la récolte
légitime malgré la garde anti-distillation : une sortie n'entre dans le jeu que
si des étiquettes écrites à la main la valident.

Sur les axes que le corpus **n'affirme pas**, en revanche, le modèle apprendra
les choix de Haiku, y compris ses défauts. Un résumé mal tourné, un `owner` posé
par habitude, un prédicat approximatif : rien ne les attrape. Cette limite ne se
réduit pas en filtrant mieux, elle se réduit en étiquetant plus.

## Le prompt système, et pourquoi il est court par défaut

`--systeme court` (défaut) ne met dans l'exemple que **l'entête et le bloc
DATES** : 3 205 caractères pour la moitié note contre 19 786, 4 387 contre 16 859
pour la moitié graphe.

Ce que le système dit pendant l'entraînement est ce que le modèle apprend à
attendre. Entraîner avec le prompt complet lui apprendrait à **mieux le suivre**,
pas à s'en passer, et la facture par note ne bougerait pas.

Ce qui reste est exactement ce qui ne peut pas passer dans les poids :

* **l'entête** — le rôle, la consigne de langue, le schéma JSON de sortie. Un
  schéma appris de mémoire dérive au premier champ ajouté au produit ;
* **le bloc DATES** — il énonce le jour courant et les deux semaines autour. Il
  change tous les jours, donc il est du contexte par nature.

`--systeme complet` existe pour une seule mesure : ce que l'entraînement apporte
**à prompt égal**. C'est le témoin, pas la recette.

## La découpe train/test

80/20, graine fixe (13), et une contrainte qui n'est pas négociable : **les deux
côtés de chaque frontière restent à l'entraînement.**

Si on entraîne sur le corpus, le corpus devient la spécification : une règle
qu'il ne démontre pas n'existera pas pour le modèle, puisqu'aucun prompt ne
l'énoncera plus. Déplacer un côté d'une frontière vers le test ne fait pas un
test plus dur, il fait une spécification trouée.

Le test se compose donc des cas sans `frontiere`, tirés à proportion par jeu et
par langue. Conséquence à connaître : **il est fait presque entièrement
d'ordinaire**. Il mesure la généralisation, pas les bords. Mesurer les bords
après entraînement demandera une vague de cas neufs, réservée à ça.

## Deux choses que ce jeu dit du corpus

**Les 51 cas sans sortie propre sont les plus intéressants du corpus.** Haiku ne
les a jamais passés, sur aucune passe. Soit l'étiquette est fausse, soit le
modèle échoue vraiment. Les trier départage les deux, et c'est le seul endroit où
une heure de relecture vaut une passe entière. Ils sont listés par le script et
dans `jeu/provenance.json`.

**La proportion de langues est l'a priori qu'on enseigne.** L'entraînement sort à
271 fr / 79 en, soit 22 % d'anglais, contre la cible de 30 % que le corpus s'était
donnée. Pour une suite de tests c'est sans effet ; dans des poids, ça enseigne
que le français est le défaut.

## Entraîner sur le Mac

```bash
python -m scripts.entrainement.construire --ecrire   # récolte, aucun appel API
python -m scripts.entrainement.vers_mlx              # 637 / 71 / 180
```

Les deux moitiés sont mélangées dans le même jeu. La production les fait tourner
sur le même modèle, avec deux appels que seul le prompt système distingue :
deux adaptateurs séparés apprendraient à deux modèles ce qu'un seul doit savoir,
et doubleraient ce qu'il faut charger sur l'appareil.

```bash
python -m mlx_lm lora \
  --model mlx-community/Qwen2.5-3B-Instruct-4bit \
  --train --data scripts/entrainement/jeu/mlx \
  --fine-tune-type lora --num-layers 8 \
  --batch-size 1 --grad-accumulation-steps 4 \
  --iters 1200 --learning-rate 1e-5 --max-seq-length 2048 \
  --mask-prompt --grad-checkpoint \
  --adapter-path scripts/entrainement/adaptateur \
  --steps-per-eval 100 --save-every 200
```

**Ces valeurs sont un point de départ, pas une mesure.** Rien ici n'a encore été
réglé sur la perte de validation ; la seule chose qui soit décidée par la
machine, c'est `--max-seq-length 2048`, parce que la plus longue conversation du
jeu fait environ 1 430 tokens.

Deux drapeaux ne sont pas négociables :

* `--mask-prompt` — sans lui, le modèle apprend aussi à RÉÉCRIRE le prompt
  système et la capture. On veut qu'il apprenne la réponse, et lui seul.
* `--grad-checkpoint` — la machine a 8 Go partagés CPU/GPU. Sans lui, ça tient
  ou ça ne tient pas selon ce qui tourne à côté, ce qui rend une mesure
  irreproductible.

Le Mac a 8 Go : lancer quand rien d'autre ne tourne dessus, et surtout pas
pendant une passe de parité, qui charge son propre modèle sur le même GPU.

## Mesurer ce que l'entraînement a donné

Le `test.jsonl` de mlx sert à lire une perte, pas à juger le produit. Le vrai
verdict passe par le harnais, qui note les 90 cas de test contre le corpus :

```bash
python -m mlx_lm.server --model mlx-community/Qwen2.5-3B-Instruct-4bit \
  --adapter-path scripts/entrainement/adaptateur
```

Il reste à écrire le provider correspondant dans `scripts/parity/providers.py`.
Il n'existe pas encore : les trois dialectes actuels sont `anthropic`, `ollama`
et `gemini`, et aucun ne sait parler à un adaptateur local.

⚠ Et une mesure faite avec le prompt COMPLET ne dirait rien de ce modèle-là : il
aura été entraîné sur le prompt court, donc il doit être mesuré avec le prompt
court. C'est `SYNAPSE_SPLIT_PROMPTS_DIR` qui permet de pointer le harnais sur un
autre dossier de prompts sans toucher à ceux de production.
