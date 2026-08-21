#!/usr/bin/env python3
"""CLI entry for the full automation suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import AutomationSuite


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoGrantED full automation suite")
    parser.add_argument("--keyword", default="artificial intelligence", help="Grants.gov search keyword")
    parser.add_argument("--index", type=int, default=0, help="Which opportunity to pick from results")
    parser.add_argument("--model", default=None, help="Ollama Cloud model name")
    parser.add_argument("--ollama-key", default=None, help="Ollama Cloud API key (or use env)")
    parser.add_argument("--live-submit", action="store_true", help="Attempt live S2S (requires cert + env)")
    parser.add_argument("--readiness", action="store_true", help="Only print readiness and exit")
    args = parser.parse_args()

    suite = AutomationSuite()

    if args.readiness:
        print(json.dumps(suite.readiness(), indent=2))
        return 0

    result = suite.run(
        keyword=args.keyword,
        opportunity_index=args.index,
        ollama_key=args.ollama_key,
        model=args.model,
        live_submit=args.live_submit,
    )
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
