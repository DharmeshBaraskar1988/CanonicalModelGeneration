"""Command-line entry point for the Discovery MVP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from canonical_model_generator.discovery_agent.workflow import event_lines, run_discovery


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canonical-discovery")
    parser.add_argument("--region", required=True)
    parser.add_argument("--system", required=True)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--openapi", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    state = run_discovery(
        region=args.region,
        system=args.system,
        repository=args.repository,
        project=args.project,
        openapi=args.openapi,
        output=args.output,
    )
    for line in event_lines(state):
        print(line, file=sys.stderr)
    if state.get("errors"):
        for error in state["errors"]:
            print(error, file=sys.stderr)
        return 1
    print(state["model"].run.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
