#!/usr/bin/env python3
"""Report what changed in a LaTeX manuscript relative to its Canvas.

Generation runs Canvas to LaTeX. This runs the other way, but only far enough
to be trustworthy: it says which paragraphs a co-author changed and which cards
produced them. It does not write to the Canvas. Turning a LaTeX edit back into
Korean prose cards is a judgement — unescaping, citation commands folded back
out, a sentence split across cards — and a wrong guess quietly corrupts the
manuscript. Naming the cards is the part a machine can do correctly.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

from paper_tex import TexError, build

# The generated body spans the abstract through the last section. Everything
# outside belongs to the template.
BODY_START = re.compile(r"^\s*\\begin\{abstract\}", re.M)
BODY_END = re.compile(r"^\s*\\bibliography\b|^\s*\\appendix\b|^\s*\\end\{document\}", re.M)
COMMAND = re.compile(r"^\s*(?:%|\\(?:section|subsection|paragraph|begin|end|input|label|clearpage))")


def extract_body(tex: str) -> str:
    start = BODY_START.search(tex)
    if not start:
        raise TexError("no \\begin{abstract} in the file; is this the manuscript?")
    rest = tex[start.start():]
    end = BODY_END.search(rest, 1)
    return rest[: end.start()] if end else rest


def prose_blocks(body: str) -> list[str]:
    """Blank-line separated blocks that are prose, not structural commands."""
    blocks = []
    for raw in body.split("\n\n"):
        block = " ".join(raw.split())
        if block and not COMMAND.match(raw):
            blocks.append(block)
    return blocks


def narrow(pairs: list[tuple[str, str]], latex: str | None) -> list[str]:
    """Name the cards whose sentence no longer appears verbatim.

    A paragraph is several cards joined, and a co-author usually edits one of
    them. Every sentence still there word for word is untouched, so what is left
    is the card that changed. If nothing matches, the whole paragraph is suspect
    and every card is named rather than guessing among them.
    """
    if latex is None:
        return [node for node, _ in pairs]
    missing = [node for node, sentence in pairs if " ".join(sentence.split()) not in latex]
    return missing or [node for node, _ in pairs]


def compare(canvas: Path, tex_file: Path, group: str = "paper_v1") -> dict:
    origins: list[tuple[str, list[tuple[str, str]]]] = []
    build(canvas, group, None, {}, origins)
    expected = [" ".join(b.split()) for b, _ in origins]
    ids = [pairs for _, pairs in origins]

    actual = prose_blocks(extract_body(tex_file.read_text(encoding="utf-8")))

    changed, added, removed = [], [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, expected, actual).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for offset in range(max(i2 - i1, j2 - j1)):
                i, j = i1 + offset, j1 + offset
                pairs = ids[i] if i < i2 else []
                latex = actual[j] if j < j2 else None
                entry = {
                    "cards": narrow(pairs, latex),
                    "canvas": expected[i] if i < i2 else None,
                    "latex": latex,
                }
                (changed if entry["cards"] and entry["latex"] else
                 removed if entry["latex"] is None else added).append(entry)
        elif tag == "delete":
            removed += [{"cards": [n for n, _ in ids[i]], "canvas": expected[i], "latex": None}
                        for i in range(i1, i2)]
        else:
            added += [{"cards": [], "canvas": None, "latex": actual[j]} for j in range(j1, j2)]

    return {
        "canvas_paragraphs": len(expected),
        "latex_paragraphs": len(actual),
        "changed": changed,
        "added": added,
        "removed": removed,
        "in_sync": not (changed or added or removed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canvas", type=Path)
    parser.add_argument("tex", type=Path, help="the manuscript .tex pulled from Overleaf")
    parser.add_argument("--group", default="paper_v1")
    args = parser.parse_args()
    try:
        result = compare(args.canvas, args.tex, args.group)
    except (TexError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: {exc}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["in_sync"]:
        print(
            f"\n{len(result['changed'])} changed, {len(result['added'])} added, "
            f"{len(result['removed'])} removed. Edit the named cards in the Canvas; "
            f"nothing was written.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
