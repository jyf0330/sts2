"""Batch-validate JSON cases with the damage validation workbench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sts2_env.damage_lab.service import load_case_input, validate_case, validate_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one case JSON or a directory/suite of case JSON files.")
    parser.add_argument("input", help="Path to a case JSON, suite JSON, or directory of case JSON files.")
    parser.add_argument("--output", help="Optional path to write the resulting JSON report.")
    args = parser.parse_args()

    payload = load_case_input(args.input)
    if "cases" in payload:
        report = validate_suite(payload)
        exit_code = 1 if report["summary"]["failed"] else 0
    else:
        report = validate_case(payload)
        exit_code = 0

    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(serialized)
    else:
        print(serialized)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
