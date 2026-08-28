"""SYN-171 — extraire le CHEMIN DE DÉCISION pris par chaque modèle, cas par cas.

Le score dit « 10 sur 12 ». Il ne dit pas *où* le modèle a bifurqué. Or les trois
axes que `classifier.md` déclare ORTHOGONAUX — `atomic_note`,
`is_ephemeral` — sont exactement là où les petits modèles se trompent : ils les
traitent comme un choix unique et recopient l'un dans l'autre.

Ce module réduit chaque réponse aux branches empruntées, pour qu'on puisse
superposer le trafic réel au graphe déclaré.

Usage :
    python -m scripts.parity.paths gate-haiku.json gate-qwen.json … > paths.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

VALID_NOTE_KINDS = {"note", "task", "event", "episode"}


def path_of(parsed: dict | None) -> dict:
    """Les branches prises. `None` = le modèle n'a rien produit d'exploitable."""
    if not parsed:
        return {"parsed": False}
    # SYN-207 — la liste plutôt que le scalaire, avec le repli sur l'ancienne
    # forme : une baseline enregistrée avant ce jour doit rester relisible.
    from scripts.parity.score import souvenirs
    liste = souvenirs(parsed)
    has_note = bool(liste)
    raw_kind = liste[0]["kind"] if liste else parsed.get("atomic_note_kind")
    kind = raw_kind if isinstance(raw_kind, str) and raw_kind else "note"
    facts = sum(len(e.get("facts") or []) for e in (parsed.get("entities") or []))
    return {
        "parsed": True,
        "kind_valid": (not has_note) or all(m["kind"] in VALID_NOTE_KINDS for m in liste),
        "has_note": has_note,
        "kind": kind if has_note else None,
        # Combien la capture en a laissé : c'est le chiffre qui montre une
        # sur-découpe, invisible sur tous les autres axes.
        "memories": len(liste),
        "kind_defaulted": False,
        "ephemeral": bool(parsed.get("is_ephemeral")),
        "facts": facts,
        "relations": len(parsed.get("relations") or []),
        "projects": len(parsed.get("project_entries") or []),
        "fields": len(parsed),
    }


def main() -> int:
    out: dict = {"models": {}}
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"absent, ignoré : {p}", file=sys.stderr)
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        label = d["model"] + (" +schéma" if d.get("schema_constrained") else "")
        out["models"][label] = {
            "fingerprint": d.get("fingerprint"),
            "schema_constrained": bool(d.get("schema_constrained")),
            "blockers": {b[0]: b[1] for b in d.get("blockers", [])},
            "cases": {c["id"]: {**path_of(c.get("parsed")),
                                "latency_s": c.get("latency_s"),
                                "blocking": c.get("blocking"),
                                "quality": c.get("quality", [])}
                      for c in d.get("cases", [])},
        }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
