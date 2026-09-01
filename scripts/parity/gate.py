"""Étage 1 — le gate. Rendre un NO-GO en minutes, pas en soirée.

Ne mesure PAS la qualité : cherche les quatre vices qui rendent un modèle
inutilisable quelle que soit son intelligence, et s'arrête au premier trouvé.

    1. avale-t-il le prompt          (une fenêtre trop courte le tronque en silence)
    2. rend-il du JSON exploitable   (valide, non tronqué)
    3. respecte-t-il l'énumération   (atomic_note_kind ∈ note|task|event|episode)
    4. ne perd-il rien               (drop_guard : une action garde une trace)

Usage :
    python -m scripts.parity.gate ollama:qwen2.5:3b-instruct-q4_K_M
    python -m scripts.parity.gate anthropic:claude-haiku-4-5-20251001   # la référence
    python -m scripts.parity.gate ollama:llama3.2:3b --no-fail-fast     # tout jouer

Prérequis : `ollama serve` pour un modèle local ; une clé Anthropic (env, `.env`
ou `~/.synapse/config.json`) pour la référence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from scripts.parity import context, providers, score  # noqa: E402
from scripts.parity.corpus import AMBIGUOUS, GATE_CASES  # noqa: E402
from scripts.parity.schema import CLASSIFY_SCHEMA  # noqa: E402

VALID_NOTE_KINDS = score.VALID_NOTE_KINDS


def _check_blocking(case: dict, reply: providers.Reply, parsed: dict | None,
                    system_chars: int, num_ctx: int) -> str | None:
    """Renvoie la raison du NO-GO, ou None si le cas passe les axes bloquants."""
    if reply.error:
        return f"appel en échec — {reply.error}"

    # 1. Le prompt a-t-il été avalé ? Deux symptômes distincts.
    if reply.prompt_tokens is not None:
        if reply.prompt_tokens >= num_ctx:
            return (f"prompt tronqué : {reply.prompt_tokens} tokens d'entrée pour une "
                    f"fenêtre de {num_ctx} — le modèle n'a pas reçu toutes les règles")
        # Plancher très conservateur : quel que soit le tokenizer, 8 caractères
        # par token est une borne basse absurde. Passer dessous veut dire qu'une
        # partie du système a disparu en route.
        floor = system_chars // 8
        if reply.prompt_tokens < floor:
            return (f"prompt amputé : {reply.prompt_tokens} tokens d'entrée pour "
                    f"{system_chars} caractères de système (plancher {floor})")

    # 2. JSON exploitable.
    if reply.truncated:
        return "sortie tronquée (budget de sortie épuisé avant la fin du JSON)"
    if parsed is None:
        head = reply.text.strip()[:120].replace("\n", " ")
        return f"sortie non-JSON : {head!r}"

    # 3. Énumération fermée.
    #
    # C'est `atomic_note_kind` qui porte l'enjeu : il décide du stockage, de la
    # décroissance et de l'affichage. Un modèle qui invente une valeur hors
    # énumération fait dégrader la note en "note" par le core (routing.rs:196) —
    # une tâche silencieusement perdue. La valeur n'a de sens qu'avec une note.
    # un kind par souvenir désormais : il suffit d'UN hors énumération
    # pour que le core le dégrade en "note", donc pour perdre une tâche.
    from scripts.parity.score import souvenirs
    for m in souvenirs(parsed):
        if m["kind"] not in VALID_NOTE_KINDS:
            return f"kind hors énumération : {m['kind']!r}"

    # 4. Rien ne se perd — au sens DURABLE du terme.
    #
    # Le harnais de juillet comptait le drapeau de l'éphémère comme « gardé ».
    # C'était faux, et même l'inverse du bug qu'on surveille : une intention
    # vivait 48 h puis expirait, donc une tâche terse classée éphémère ÉTAIT
    # perdue — ce qui arrivait à « Répondre à l'e-mail de Vincent » avant le
    # durcissement de juin. Le drapeau est retiré depuis le 2026-09-01 et ce
    # chemin de perte avec lui ; le contrôle reste, parce que ce qu'il garde
    # n'a jamais été le drapeau mais la question : la capture a-t-elle laissé
    # quelque chose de durable ? Une trace durable = note, entrée projet, fait
    # ou relation.
    if case.get("drop_guard"):
        has_note = bool(souvenirs(parsed))
        facts = sum(len(e.get("facts") or []) for e in (parsed.get("entities") or []))
        kept = (has_note or bool(parsed.get("project_entries"))
                or facts > 0 or bool(parsed.get("relations")))
        if not kept:
            return "capture sans trace durable"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="gate de parité (étage 1)")
    ap.add_argument("model", help="provider:modèle, ex. ollama:qwen2.5:3b-instruct-q4_K_M")
    ap.add_argument("--prompt", help="classifier.md alternatif (variante compacte…)")
    ap.add_argument("--num-ctx", type=int, default=providers.DEFAULT_NUM_CTX)
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="0 = reproductible (défaut). 1.0 reproduit la variance de prod.")
    ap.add_argument("--no-fail-fast", action="store_true",
                    help="jouer les 12 cas même après un vice rédhibitoire")
    ap.add_argument("--schema", action="store_true",
                    help="décodage contraint par le JSON Schema (Ollama seulement) — "
                         "mesure la justesse SANS la conformité de format")
    ap.add_argument("--json", type=Path, help="écrire le détail dans ce fichier")
    args = ap.parse_args()

    system = context.classifier_system(Path(args.prompt) if args.prompt else None)
    system_chars = sum(len(b) for b in system)
    fp = context.fingerprint(system)

    print(f"modèle   : {args.model}")
    print(f"contexte : {system_chars} caractères · empreinte {fp} · today={context.TODAY}")
    print(f"fenêtre  : num_ctx={args.num_ctx}, budget de sortie={context.CLASSIFY_MAX_TOKENS}")
    print(f"décodage : {'contraint par schéma' if args.schema else 'libre'}\n")

    schema = CLASSIFY_SCHEMA if args.schema else None
    records, blockers, notes_count = [], [], 0
    for case in GATE_CASES:
        reply = providers.call(args.model, system, case["text"],
                               context.CLASSIFY_MAX_TOKENS, args.num_ctx, schema,
                               args.temperature)
        parsed = context.parse_classify(reply.text, reply.stop_reason)
        blocking = _check_blocking(case, reply, parsed, system_chars, args.num_ctx)
        quality = score.gaps(case, parsed, skip=("drop_guard",)) if parsed else []
        notes_count += len(quality)

        records.append({"id": case["id"], "text": case["text"], "blocking": blocking,
                        "quality": quality, "latency_s": reply.latency_s,
                        "prompt_tokens": reply.prompt_tokens,
                        "output_tokens": reply.output_tokens, "parsed": parsed})

        # flush : un modèle local prend des minutes par cas ; sans ça, rien ne
        # s'affiche avant la fin quand la sortie est redirigée dans un fichier.
        if blocking and case["id"] not in AMBIGUOUS:
            blockers.append((case["id"], blocking))
            print(f"  ✗ {case['id']:22} {reply.latency_s:6.1f}s  BLOQUANT — {blocking}", flush=True)
            if not args.no_fail_fast:
                print(f"\nNO-GO. Arrêt au premier vice : l'étage 2 n'a pas de sens tant "
                      f"que celui-ci tient.")
                break
        else:
            mark = "•" if quality else "✓"
            detail = f"  ({'; '.join(quality)})" if quality else ""
            print(f"  {mark} {case['id']:22} {reply.latency_s:6.1f}s{detail}", flush=True)

    played = len(records)
    print()
    if blockers:
        print(f"VERDICT : NO-GO — {len(blockers)} vice(s) rédhibitoire(s) sur {played} cas joués.")
        for cid, why in blockers:
            print(f"  · {cid} : {why}")
    else:
        print(f"VERDICT : GO pour l'étage 1 — 12/12 cas sans vice rédhibitoire.")
        print(f"  {notes_count} écart(s) de qualité relevé(s), à trancher à l'étage 2.")

    if args.json:
        args.json.write_text(json.dumps(
            {"model": args.model, "fingerprint": fp, "system_chars": system_chars,
             "num_ctx": args.num_ctx, "schema_constrained": bool(args.schema),
             "blockers": blockers, "cases": records},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n→ détail écrit : {args.json}")

    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
