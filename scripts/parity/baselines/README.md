# Les baselines, et ce qu'elles ne mesurent plus

Une baseline est une mesure du corpus contre un prompt, à une date. Elle ne vaut
que comparée à une autre — et deux mesures ne se comparent que si leur
**empreinte** coïncide. L'empreinte (`context.py::fingerprint`) hache le contexte
complet tel qu'il part au modèle : le prompt, mais aussi **quel bloc part à quelle
moitié**. C'est ce qui rend un verdict opposable, et c'est aussi ce qui fait qu'un
changement d'assemblage périme silencieusement tout ce qui précède.

`python -m scripts.parity.baseline diff <avant> <après>` avertit quand les
empreintes diffèrent, mais laisse au lecteur le soin de savoir *pourquoi*. Cette
note porte le pourquoi.

## Les ruptures nommées

- **2026-08-24, `309bedc`** — *Le harnais n'assemblait pas le contexte comme la
  prod.* `split.py::_system` envoyait le bloc des types aux DEUX moitiés et celui
  des projets à AUCUNE, quand le core réserve les deux à la moitié graphe. Trois
  blocs sur quatre mal adressés. **Toute baseline `*-split` antérieure au 24/08 ne
  se compare plus à une postérieure** : `e2b-split`, `haiku-split`,
  `haiku-split-v2`, `haiku-v25-decoupe`, `haiku-v26-graphe-sobre`,
  `haiku-v27-fete`, `haiku-v28-final`, `smoke`, `e2b-v2-gate`, `e2b-v2-hard`.
  Conséquence à part : le « +10 % d'échafaudage additif » mesuré en août portait
  sur cette assemblée fausse. **À remesurer avant d'être cité.**
- **2026-08-25, `1b5b59a`** — *Le harnais mesure enfin le prompt qui tourne.*
  Ce qui précède mesurait autre chose que la production.
- **2026-08-25, `4e6d1b2`** — le champ du rappel à 48 h entre dans la mesure.
- **2026-08-26, `e8e012a`** — le champ ressource entre dans la mesure.

Une baseline d'avant une rupture n'est pas fausse : elle est **muette** sur ce
qui a changé après elle. Elle reste lisible comme trace, jamais comme référence.

## Les familles d'empreintes présentes

45 baselines, 28 empreintes. Une ligne = un contexte identique ;
seules les baselines d'une même ligne se comparent entre elles. Les empreintes en
deux parties (`note+graphe`) sont les mesures en deux appels.

| Empreinte | Date | Forme | Fichiers |
|---|---|---|---|
| `09792f4e65f1` | 2026-08-20 | appel unique | haiku-v8-avant-arbitrages.json |
| `0e3887530465` | 2026-08-20 | appel unique | haiku-v19.json |
| `0edf2151fa3d` | 2026-08-20 | appel unique | haiku-v9-lot1b.json |
| `11caca369ff2` | 2026-08-20 | appel unique | haiku-v21.json |
| `64c56129c592` | 2026-08-20 → 2026-08-21 | appel unique | haiku-v23.json, e2b-v23-ctx16k.json, e2b-v23-libre.json, e2b-v23.json |
| `71ee2eb13eb1` | 2026-08-20 | appel unique | haiku-v12-episode-assoupli.json |
| `79616d1b1276` | 2026-08-20 | appel unique | haiku-v18.json |
| `a5eb270c5d1a` | 2026-08-20 | appel unique | haiku-v17.json |
| `c1fd2d9d29f9` | 2026-08-20 | appel unique | haiku-v22.json |
| `dd7c623ca880` | 2026-08-20 | appel unique | haiku-v16-gate.json |
| `e57fa9ad4528` | 2026-08-20 → 2026-08-21 | appel unique | e2b-v14.json, haiku-v14-squelette-en.json, e2b-v14-libre.json |
| `ea4ccf8dc11d` | 2026-08-20 | appel unique | haiku-v10-episode.json |
| `eca5a0ea3375` | 2026-08-20 | appel unique | haiku-v20.json |
| `efdf7e678886` | 2026-08-20 | appel unique | haiku-v15-table.json |
| `f129577bdc9a` | 2026-08-20 | appel unique | haiku-v11-sans-input-type.json |
| `f4490892c82b` | 2026-08-20 | appel unique | haiku-v9-deduction.json |
| `1c6e3e887e5c+3ce3f782dc15` | 2026-08-21 | deux moitiés | e2b-split.json, haiku-split.json, smoke.json |
| `242bfb28d1b9` | 2026-08-21 | appel unique | haiku-v24-syn182.json, syn182-adversarial.json |
| `3a61526df833+3ce3f782dc15` | 2026-08-21 | deux moitiés | e2b-v2-gate.json, e2b-v2-hard.json, haiku-split-v2.json |
| `98a24844fd0b+10bad7b65a32` | 2026-08-21 | deux moitiés | haiku-v26-graphe-sobre.json |
| `98a24844fd0b+1bcc544cf61f` | 2026-08-21 | deux moitiés | haiku-v27-fete.json, haiku-v28-final.json |
| `98a24844fd0b+3ce3f782dc15` | 2026-08-21 | deux moitiés | haiku-v25-decoupe.json |
| `98a24844fd0b+b120cf4a41d2` | 2026-08-24 | deux moitiés | gate-e2b-qat.json, gate-llama3-2-3b.json, gate-phi4-mini.json, qwen25-3b-full-split.json, qwen25-3b-gate-split.json |
| `1bc60482e141+1787327cf49f` | 2026-08-25 → 2026-08-26 | deux moitiés | apres-bissection.json, certification-20260825.json |
| `5a4cdb5232b8+e87c0c38b580` | 2026-08-25 | deux moitiés | corpus-complet-20260825.json, v21-split-neg.json |
| `6b9c619b0aad+2fa9de7680bc` | 2026-08-25 | deux moitiés | apres-corrections-20260825.json |
| `b3962907e3ac+1787327cf49f` | 2026-08-25 | deux moitiés | essai-sans-svo.json |
| `7af4ee039679+887581dbf7d2` | 2026-08-26 | deux moitiés | ressources-20260826.json |

## Régénérer ce tableau

Il est dérivé des fichiers, pas tenu à la main. Après avoir ajouté des baselines :

```bash
python - <<'EOF'
import json, glob, subprocess
from pathlib import Path
for f in sorted(glob.glob("scripts/parity/baselines/*.json")):
    d = json.load(open(f, encoding="utf-8"))
    date = subprocess.run(["git","log","-1","--format=%ad","--date=short","--",f],
                          capture_output=True, text=True).stdout.strip()
    print(date, d.get("fingerprint"), Path(f).name)
EOF
```
