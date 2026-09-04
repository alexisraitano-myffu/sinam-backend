"""Les 186 questions du harnais, jouees avec transformers. Sans vLLM.

Pourquoi sans vLLM : le pilote de l'hote est en CUDA 12.8, ce qui force un vLLM
ancien, qui epingle un transformers qui ne connait pas Qwen 3.5. Les trois
contraintes s'excluent. transformers genere seul, plus lentement, et
l'entrainement n'a jamais eu besoin de vLLM.

Trois details qui ne se redevinent pas :
* padding a GAUCHE. En generation, un padding a droite met les jetons de
  remplissage entre le prompt et la reponse : le modele continue le
  remplissage.
* tri par longueur avant de faire les lots. Un lot melangeant un prompt court
  et un long paie le long sur toute la largeur du lot.
* QUANT=nf4 par defaut : on mesure la MEME base que celle qu'on
  entraine, sinon la comparaison melange deux effets.
* enable_thinking=False. Le mode reflexion mange le budget de sortie SANS
  apparaitre dans le texte : on recupere du vide en croyant a un echec.
"""
import json, os, sys, time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    modele, nom = sys.argv[1], sys.argv[2]
    adaptateur = sys.argv[3] if len(sys.argv) > 3 else None
    lot = int(os.environ.get("LOT", 4))
    p = json.load(open(os.environ.get("QUESTIONS", "/workspace/questions.json")))
    os.makedirs("/workspace/reponses", exist_ok=True)
    cible = f"/workspace/reponses/{nom}.json"
    if os.path.exists(cible):
        print(f"### {nom} : deja fait", flush=True); return
    print(f"### {nom} ({modele}" + (f" + {adaptateur}" if adaptateur else "") + ")", flush=True)

    tok = AutoTokenizer.from_pretrained(modele, padding_side="left")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    if os.environ.get("QUANT", "nf4") == "bf16":
        m = AutoModelForCausalLM.from_pretrained(modele, dtype=torch.bfloat16,
                                                 device_map="cuda")
    else:
        # La MEME quantification que l'entrainement. Mesurer un bf16 puis lui
        # comparer un entraine 4 bits ne dirait rien : l'ecart melangerait le
        # gain d'entrainement et le cout de quantification.
        from transformers import BitsAndBytesConfig
        m = AutoModelForCausalLM.from_pretrained(
            modele, device_map="cuda", dtype=torch.bfloat16,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True))
    if adaptateur:
        from peft import PeftModel
        m = PeftModel.from_pretrained(m, adaptateur)
    m.eval()

    def gabarit(q):
        msgs = [{"role": "system", "content": p["systemes"][q["sys"]]},
                {"role": "user", "content": q["user"]}]
        try:
            return tok.apply_chat_template(msgs, tokenize=False,
                                           add_generation_prompt=True,
                                           enable_thinking=False)
        except TypeError:
            return tok.apply_chat_template(msgs, tokenize=False,
                                           add_generation_prompt=True)

    textes = [gabarit(q) for q in p["questions"]]
    ordre = sorted(range(len(textes)), key=lambda i: len(textes[i]))
    out = [None] * len(textes)
    t0 = time.time()

    for d in range(0, len(ordre), lot):
        idx = ordre[d:d + lot]
        enc = tok([textes[i] for i in idx], return_tensors="pt",
                  padding=True).to("cuda")
        with torch.no_grad():
            gen = m.generate(**enc, max_new_tokens=p["max_tokens"],
                             do_sample=False, temperature=None, top_p=None,
                             top_k=None, pad_token_id=tok.pad_token_id)
        for k, i in enumerate(idx):
            neufs = gen[k][enc["input_ids"].shape[1]:]
            fini = tok.eos_token_id in neufs.tolist()
            out[i] = {"cle": p["questions"][i]["cle"],
                      "text": tok.decode(neufs, skip_special_tokens=True),
                      "stop_reason": "stop" if fini else "max_tokens",
                      "prompt_tokens": int(enc["attention_mask"][k].sum()),
                      "output_tokens": len(neufs), "latency_s": 0.0}
        fait = d + len(idx)
        print(f"  {fait}/{len(ordre)} en {(time.time()-t0)/60:.1f} min", flush=True)

    json.dump(out, open(cible, "w"), ensure_ascii=False)
    print(f"### {nom} FINI : {len(out)} reponses, "
          f"{sum(1 for r in out if r['stop_reason']=='max_tokens')} tronquees, "
          f"{sum(1 for r in out if not r['text'].strip())} vides, "
          f"{(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()