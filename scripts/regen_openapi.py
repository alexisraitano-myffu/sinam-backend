"""Regenerate `openapi.json` from the live FastAPI app.

The mobile and desktop clients code against the committed file, not against a
running server, so that file — and not `api/app.py` — is the contract they
trust. It drifted 11 routes behind once, including the four pairing-by-code
routes, which is the kind of gap a client only discovers in production.

The serialization has to match the file already committed exactly
(`indent=2`, `ensure_ascii=False`, no trailing newline) so that regenerating
an already-current file produces no diff at all: a regeneration that always
dirties the tree is a regeneration nobody runs.

    python -m scripts.regen_openapi            # rewrite the file
    python -m scripts.regen_openapi --check    # exit 1 if it is stale

`test_openapi_contract.py` runs the same comparison in the suite.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "openapi.json"


def render() -> str:
    """Serialize the live schema in the committed file's exact format.

    `SYNAPSE_HOME` is redirected to a throwaway directory before the import:
    the schema owes nothing to the database, and regenerating a contract is
    no reason to touch the real memory.
    """
    if "SYNAPSE_HOME" not in os.environ:
        os.environ["SYNAPSE_HOME"] = tempfile.mkdtemp(prefix="openapi-regen-")
    sys.path.insert(0, str(REPO_ROOT))
    from api.app import app

    return json.dumps(app.openapi(), indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare without writing; exit 1 if the committed file is stale",
    )
    args = parser.parse_args()

    live = render()
    committed = CONTRACT.read_text(encoding="utf-8") if CONTRACT.exists() else None

    if live == committed:
        print(f"openapi.json à jour ({len(json.loads(live)['paths'])} chemins)")
        return 0

    if args.check:
        print("openapi.json est en retard sur api/app.py.", file=sys.stderr)
        print("Régénérer avec : python -m scripts.regen_openapi", file=sys.stderr)
        return 1

    CONTRACT.write_text(live, encoding="utf-8")
    print(f"openapi.json réécrit ({len(json.loads(live)['paths'])} chemins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
