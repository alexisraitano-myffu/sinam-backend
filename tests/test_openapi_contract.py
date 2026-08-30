"""
Offline guard against documentation drift.

Two facts about this repo are written down in two places at once, and both
have already diverged in silence:

* `openapi.json` is the contract the mobile and desktop apps code against —
  it was found 11 routes behind `api/app.py`, including the four
  pairing-by-code routes;
* `CLAUDE.md` announces how many endpoints the API exposes — it said "~38"
  while the app served 82.

Neither was caught by a test, because nothing compared the claim to the
thing it describes. These do. No API key, no network, no real database.
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def live_schema(tmp_path, monkeypatch):
    """The schema the running app would serve, built off a throwaway DB."""
    monkeypatch.setenv("SYNAPSE_HOME", str(tmp_path))
    from api.app import app

    return app.openapi()


# ── The committed contract ───────────────────────────────────────────────────


def test_committed_openapi_matches_the_app(live_schema):
    """`openapi.json` must be exactly what `app.openapi()` renders today.

    Compared as a whole document, not route by route: a response model that
    changes shape without adding a route breaks a client just as surely as a
    missing endpoint, and only the full comparison sees it.
    """
    committed_raw = (REPO_ROOT / "openapi.json").read_text(encoding="utf-8")
    committed = json.loads(committed_raw)

    live_paths = {(p, m) for p, ops in live_schema["paths"].items() for m in ops}
    committed_paths = {(p, m) for p, ops in committed["paths"].items() for m in ops}

    missing = sorted(live_paths - committed_paths)
    stale = sorted(committed_paths - live_paths)
    assert not missing, (
        f"{len(missing)} route(s) servies par l'app et absentes du contrat : {missing}. "
        "Régénérer : python -m scripts.regen_openapi"
    )
    assert not stale, (
        f"{len(stale)} route(s) promises par le contrat et disparues de l'app : {stale}. "
        "Régénérer : python -m scripts.regen_openapi"
    )

    assert committed == live_schema, (
        "Les routes correspondent mais le document diffère (modèle, description "
        "ou paramètre). Régénérer : python -m scripts.regen_openapi"
    )


def test_committed_openapi_keeps_its_serialization(live_schema):
    """The file must stay byte-identical to its own regeneration.

    Without this, a regeneration reformats the whole file and every real
    change arrives buried in a 10 000-line diff nobody reads.
    """
    committed_raw = (REPO_ROOT / "openapi.json").read_text(encoding="utf-8")
    rendered = json.dumps(live_schema, indent=2, ensure_ascii=False)
    assert committed_raw == rendered, (
        "openapi.json n'est pas dans le format que produit sa régénération "
        "(indent=2, ensure_ascii=False, sans newline finale). "
        "Régénérer : python -m scripts.regen_openapi"
    )


# ── The claim made in prose ──────────────────────────────────────────────────


def test_claude_md_endpoint_count_is_true(live_schema):
    """`CLAUDE.md` states a number of endpoints; it has to be the real one.

    The count is the one figure in that file a reader takes at face value and
    cannot check without running the app — which is exactly why it drifted to
    less than half the truth.
    """
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    match = re.search(r"\*\*(\d+) endpoints\*\*", claude_md)
    assert match, (
        "CLAUDE.md n'annonce plus de nombre d'endpoints sous la forme "
        "`**N endpoints**` : soit le rétablir, soit retirer ce test."
    )

    claimed = int(match.group(1))
    actual = len(live_schema["paths"])
    assert claimed == actual, (
        f"CLAUDE.md annonce {claimed} endpoints, l'app en expose {actual}. "
        "Corriger la phrase dans CLAUDE.md (§ HTTP API)."
    )
