#!/usr/bin/env python3
"""Append one auditable action to a paper Canvas log."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--status", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    if not args.log.parent.is_dir():
        parser.error(f"log parent does not exist: {args.log.parent}")

    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    header = "# Canvas Action Log\n\nAppend-only record of paper, Canvas, and validation actions.\n"
    entry = (
        f"\n## {timestamp} — {args.status}: {args.action}\n\n"
        f"- Target: {args.target}\n"
        f"- Reason/source: {args.reason}\n"
        f"- Result: {args.result}\n"
    )
    with args.log.open("a", encoding="utf-8") as handle:
        if args.log.stat().st_size == 0:
            handle.write(header)
        handle.write(entry)


if __name__ == "__main__":
    main()
