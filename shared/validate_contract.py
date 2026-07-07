#!/usr/bin/env python3
"""
Aegis contract validator.

Validate that a module's JSON payload (Fraud Shield / Counterfeit Vision / Fraud
Graph / Command Centre fusion) conforms to its schema in ../contracts/ BEFORE
handing it off. Catches contract drift early so integration doesn't break during
the crunch.

Usage:
    python shared/validate_contract.py scam      path/to/output.json
    python shared/validate_contract.py counterfeit path/to/output.json
    python shared/validate_contract.py graph      path/to/output.json
    python shared/validate_contract.py fusion     path/to/output.json

    # or validate the bundled samples as a smoke test:
    python shared/validate_contract.py --check-samples

Requires: pip install jsonschema
"""
import json
import sys
from pathlib import Path

try:
    from jsonschema import validate, ValidationError
except ImportError:
    sys.exit("Missing dependency. Run: pip install jsonschema")

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"

SCHEMAS = {
    "scam": CONTRACTS / "scam_detection.schema.json",
    "counterfeit": CONTRACTS / "counterfeit.schema.json",
    "graph": CONTRACTS / "fraud_graph.schema.json",
    "fusion": CONTRACTS / "fusion_output.schema.json",
}

SAMPLES = {
    "scam": CONTRACTS / "samples" / "scam_detection.sample.json",
    "counterfeit": CONTRACTS / "samples" / "counterfeit.sample.json",
    "graph": CONTRACTS / "samples" / "fraud_graph.sample.json",
}


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(kind: str, payload_path: Path) -> bool:
    schema = load(SCHEMAS[kind])
    payload = load(payload_path)
    try:
        validate(instance=payload, schema=schema)
    except ValidationError as e:
        print(f"[FAIL] {payload_path} does not match '{kind}' contract:\n  {e.message}")
        print(f"  at: {'/'.join(str(p) for p in e.absolute_path) or '<root>'}")
        return False
    print(f"[OK]   {payload_path} matches '{kind}' contract.")
    return True


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)

    if args[0] == "--check-samples":
        ok = all(check(kind, path) for kind, path in SAMPLES.items())
        sys.exit(0 if ok else 1)

    if len(args) != 2 or args[0] not in SCHEMAS:
        sys.exit(__doc__)

    sys.exit(0 if check(args[0], Path(args[1])) else 1)


if __name__ == "__main__":
    main()
