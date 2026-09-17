"""Validate the redacted cross-repository MPA P0 compatibility manifest."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_contract = importlib.import_module("veadk.cli.mpa_p0_contract")
evaluate_mpa_p0_compatibility = _contract.evaluate_mpa_p0_compatibility
load_json_object = _contract.load_json_object


def _report(payload: dict[str, Any], exit_code: int) -> int:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = load_json_object(args.manifest)
        matrix = load_json_object(args.matrix)
    except (OSError, ValueError, json.JSONDecodeError):
        return _report(
            {"status": "invalid_manifest", "errorCode": "manifest_unreadable"},
            2,
        )
    report = evaluate_mpa_p0_compatibility(manifest, matrix)
    if report["status"] == "compatible":
        return _report(report, 0)
    if report["status"] == "invalid_manifest":
        return _report(report, 2)
    return _report(report, 3)


if __name__ == "__main__":
    sys.exit(main())
