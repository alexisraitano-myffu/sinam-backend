"""LoRA sur Qwen 3.5 4B, au prompt COMPLET, les deux moities dans le meme jeu.

QUANT=nf4 (defaut) entraine AU-DESSUS du modele quantifie 4 bits, ce qui est le
modele qu'on deploiera vraiment ; l'adaptateur apprend alors aussi a compenser
les erreurs de quantification. QUANT=bf16 refait la variante pleine precision.

Ce que ce script fait de non evident, et pourquoi :

* le masque, pose au niveau du TEXTE et pas des JETONS. Le prompt finit par
  `<think>\n` tandis que la sequence complete porte `<think>\n\n</think>` : en
  jetons le prompt n'est PAS un prefixe, en texte il l'est. Un masque pose sur
  les jetons serait decale d'un jeton, sans rien faire planter, et
  l'entrainement tournerait des heures sur une frontiere fausse. D'ou le
  garde-fou plus bas, qui refuse l'exemple plutot que de deviner.
* on n'apprend QUE la reponse. Sans le masque le modele apprendrait aussi a
  reecrire les 20 000 caracteres de systeme, identiques sur les 366 exemples :
  il passerait son budget a memoriser le prompt qu'on lui donne deja.
* une sauvegarde tous les 30 pas, pas par epoque. La perte tombe de 80 % dans
  les 30 premiers pas puis reste plate ; garder les points intermediaires
  permet de CHOISIR l'arret apres coup au lieu de croire au dernier.
* les deux moities (note et graphe) dans un seul adaptateur. La production les
  fait tourner sur le meme modele, seul le systeme les distingue ; deux
  adaptateurs apprendraient a deux modeles ce qu'un seul doit savoir.
"""
import json, os, sys
import torch
from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer,
                          TrainingArguments)
from peft import LoraConfig, get_peft_model

BASE = os.environ.get("BASE", "Qwen/Qwen3.5-4B")
MAXLEN = int(os.environ.get("MAXLEN", 6144))
SORTIE = os.environ.get("SORTIE", "/workspace/adaptateur")
EPOQUES = float(os.environ.get("EPOQUES", 3))
QUANT = os.environ.get("QUANT", "nf4")

tok = AutoTokenizer.from_pretrained(BASE)
# La fin de tour telle que le gabarit l'ecrit. `eos_token` ne suffit pas :
# sur ces modeles il peut differer du marqueur de fin de tour.
FIN = "<|im_end|>"


def lire(*fichiers):
    ex = []
    for f in fichiers:
        for l in open(f):
            ex.append(json.loads(l)["messages"])
    return ex


def _ids(x):
    """apply_chat_template(tokenize=True) rend un BatchEncoding sous
    transformers 5, pas une liste. Correctif du 03/09."""
    if hasattr(x, "input_ids"):
        x = x["input_ids"]
    if x and isinstance(x[0], list):
        x = x[0]
    return list(x)


REJETS = {"trop_long": 0, "pas_prefixe": 0}


def _prompt(msgs):
    """LE prompt, construit EXACTEMENT comme mesurer.py le construira.

    Piege mesure le 03/09 : sans `enable_thinking=False`, le gabarit finit le
    prompt sur `<think>\n` et la cible commence donc par `</think>`. A
    l'inference, ou mesurer.py passe `enable_thinking=False`, le gabarit a deja
    ecrit `<think>\n\n</think>\n\n` : le modele entraine emettrait un
    `</think>` en trop des le premier jeton. On entrainerait sur un enonce que
    la mesure ne pose jamais. Les deux constructions doivent etre la MEME.
    """
    try:
        return tok.apply_chat_template(msgs, tokenize=False,
                                       add_generation_prompt=True,
                                       enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(msgs, tokenize=False,
                                       add_generation_prompt=True)


def encoder(msgs):
    """Prompt masque, reponse apprise, frontiere trouvee sur le TEXTE.

    On ne compare PAS les jetons du prompt a ceux de la sequence complete : le
    gabarit de chat peut fusionner des jetons a la jointure. On cherche donc le
    plus petit k dont le decodage couvre exactement le texte du prompt. La
    longueur du decodage croit avec k, donc dichotomie.
    """
    t_prompt = _prompt(msgs[:-1])
    plein = tok(t_prompt + msgs[-1]["content"] + FIN,
                add_special_tokens=False)["input_ids"]
    if len(plein) > MAXLEN:
        REJETS["trop_long"] += 1
        return None

    if not tok.decode(plein).startswith(t_prompt):
        REJETS["pas_prefixe"] += 1
        return None

    bas, haut = 0, len(plein)
    while bas < haut:
        mil = (bas + haut) // 2
        if len(tok.decode(plein[:mil])) < len(t_prompt):
            bas = mil + 1
        else:
            haut = mil
    k = bas
    if k <= 0 or k >= len(plein):
        REJETS["pas_prefixe"] += 1
        return None
    return {"input_ids": plein, "labels": [-100] * k + plein[k:]}


class Jeu(torch.utils.data.Dataset):
    def __init__(self, msgs):
        avant = dict(REJETS)
        self.d = [e for e in (encoder(m) for m in msgs) if e]
        perdus = {k: REJETS[k] - avant[k] for k in REJETS}
        print(f"  {len(self.d)}/{len(msgs)} exemples retenus "
              f"(trop longs : {perdus['trop_long']}, "
              f"frontiere introuvable : {perdus['pas_prefixe']})", flush=True)
        # LE garde-fou. Si la frontiere se derobe, l'entrainement tournerait
        # des heures sur un masque faux sans lever la moindre erreur.
        if perdus["pas_prefixe"] > len(msgs) * 0.02:
            sys.exit(f"ARRET : {perdus['pas_prefixe']} exemples sans frontiere "
                     f"de masque. Le gabarit de chat a change, ne pas entrainer.")
        if not self.d:
            sys.exit("ARRET : aucun exemple retenu.")
    def __len__(self): return len(self.d)
    def __getitem__(self, i): return self.d[i]


def collate(lot):
    n = max(len(x["input_ids"]) for x in lot)
    pad = tok.pad_token_id or tok.eos_token_id
    return {
        "input_ids": torch.tensor([x["input_ids"] + [pad]*(n-len(x["input_ids"])) for x in lot]),
        "labels": torch.tensor([x["labels"] + [-100]*(n-len(x["labels"])) for x in lot]),
        "attention_mask": torch.tensor([[1]*len(x["input_ids"]) + [0]*(n-len(x["input_ids"])) for x in lot]),
    }


def charger():
    """Le modele de base, quantifie ou non. En 4 bits il faut passer par
    prepare_model_for_kbit_training : sans lui les normalisations restent en
    4 bits et l'entrainement diverge silencieusement."""
    if QUANT == "bf16":
        print("base en bf16", flush=True)
        return AutoModelForCausalLM.from_pretrained(
            BASE, dtype=torch.bfloat16, device_map="cuda")

    from transformers import BitsAndBytesConfig
    from peft import prepare_model_for_kbit_training
    print("base quantifiee en NF4 4 bits", flush=True)
    m = AutoModelForCausalLM.from_pretrained(
        BASE, device_map="cuda", dtype=torch.bfloat16,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True))
    return prepare_model_for_kbit_training(m, use_gradient_checkpointing=True)


def main():
    d = os.environ.get("JEU", "/workspace/jeu")
    print("train :", flush=True)
    tr = Jeu(lire(f"{d}/note-train.jsonl", f"{d}/graphe-train.jsonl"))
    print("eval :", flush=True)
    ev = Jeu(lire(f"{d}/note-test.jsonl", f"{d}/graphe-test.jsonl"))

    m = charger()
    m.config.use_cache = False
    m = get_peft_model(m, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj","k_proj","v_proj","o_proj",
                        "gate_proj","up_proj","down_proj"]))
    m.print_trainable_parameters()

    Trainer(
        model=m, data_collator=collate, train_dataset=tr, eval_dataset=ev,
        args=TrainingArguments(
            output_dir=SORTIE, num_train_epochs=EPOQUES,
            per_device_train_batch_size=1, gradient_accumulation_steps=8,
            per_device_eval_batch_size=1,
            # warmup_ratio n'existe plus sous transformers 5. Correctif du 03/09.
            learning_rate=1e-4, warmup_steps=10, lr_scheduler_type="cosine",
            bf16=True, gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            logging_steps=5,
            # tous les 30 pas, pour pouvoir choisir l'arret apres coup
            eval_strategy="steps", eval_steps=30,
            save_strategy="steps", save_steps=30,
            save_total_limit=6, report_to=[]),
    ).train()

    m.save_pretrained(f"{SORTIE}/final")
    print("### ENTRAINEMENT FINI", flush=True)


if __name__ == "__main__":
    main()
