#!/usr/bin/env python3
"""Append one auditable action to a paper Canvas log."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def append_action(
    log: Path,
    *,
    status: str,
    action: str,
    target: str,
    reason: str,
    result: str,
) -> None:
    if not log.parent.is_dir():
        raise ValueError(f"log parent does not exist: {log.parent}")

    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    header = "# Canvas Action Log\n\nAppend-only record of paper, Canvas, and validation actions.\n"
    entry = (
        f"\n## {timestamp} — {status}: {action}\n\n"
        f"- Target: {target}\n"
        f"- Reason/source: {reason}\n"
        f"- Result: {result}\n"
    )
    with log.open("a", encoding="utf-8") as handle:
        if log.stat().st_size == 0:
            handle.write(header)
        handle.write(entry)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--status", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    try:
        append_action(
            args.log,
            status=args.status,
            action=args.action,
            target=args.target,
            reason=args.reason,
            result=args.result,
        )
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
