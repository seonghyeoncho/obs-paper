#!/usr/bin/env python3
"""Assemble a LaTeX body from a paper_vN Canvas group.

Emits a body fragment, never a whole document. The template owns the preamble,
author block, and bibliography; the Canvas owns prose, headings, and artifacts.
Keeping them in separate files means a push replaces only the generated file and
leaves what co-authors edit alone.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

COLUMN_TOLERANCE = 100

# Paragraph structure is carried by the gap between prose cards: the skill sets
# 20px inside a paragraph and 40px between them, and the split is visible in the
# Canvas. The risk is silent drift — resize a card and the paragraphs move with
# no sign — so any prose-to-prose gap that is neither is reported rather than
# quietly rounded. Headings and artifacts end a paragraph whatever their gap.
SENTENCE_GAP, PARAGRAPH_GAP = 20, 40
GAP_MIDPOINT = (SENTENCE_GAP + PARAGRAPH_GAP) // 2

# A single ACL column fits roughly this many characters at 11pt. An artifact
# wider than that has to span both columns or it overprints the text beside it.
COLUMN_CHARS = 58
WIDE_ASPECT = 1.8

# Greek and maths symbols are written as plain characters in the Canvas, where
# they render fine. pdflatex needs them in maths mode.
SYMBOLS = {
    "θ": r"$\theta$", "φ": r"$\varphi$", "Δ": r"$\Delta$", "κ": r"$\kappa$",
    "×": r"$\times$", "−": "$-$", "≤": r"$\leq$", "≥": r"$\geq$", "≈": r"$\approx$",
    "→": r"$\rightarrow$", "±": r"$\pm$", "<": "$<$", ">": "$>$",
}
ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
           "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}

# Heading depth is carried by colour, not by a number in the text and not by
# position. Numbering a heading means renumbering every sibling and every
# reference whenever the outline moves, so the Canvas states no numbers and
# LaTeX does the counting.
HEADING_LEVEL = {"6": "section", "5": "subsection", "4": "paragraph"}

NODE_ID = re.compile(r"\n*`[0-9a-f]{16}`\s*$")
HEADING = re.compile(r"^#\s+(.*)$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ARTIFACT = re.compile(r"^\*\*(Table|Figure)\s+(\d+)\*\*\s*[:.]?\s*(.*)$", re.S)
CITATION = re.compile(r"~?\\cite[tp]?(?:\[[^\]]*\])?\{[^}]+\}")
# The placeholder is matched after escaping, where `{}` has become `\{\}`.
PLACEHOLDER = r"\{\}"
SECTION_REF = re.compile(r"(\d+(?:\.\d+)*)절")
TABLE_DIR = "tables"


class TexError(RuntimeError):
    pass


def escape(text: str) -> str:
    """Escape LaTeX specials, then lift bold and loose symbols back out."""
    out = "".join(ESCAPES.get(ch, ch) for ch in text)
    out = out.replace(r"\{\{", "{{").replace(r"\}\}", "}}")
    for raw, tex in SYMBOLS.items():
        out = out.replace(raw, tex)
    # \*\*x\*\* survived escaping as literal asterisks; turn it into \textbf
    return re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", out)


def strip_id(text: str) -> str:
    return NODE_ID.sub("", text).strip()


def load_group(canvas: Path, label: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(canvas.read_text(encoding="utf-8"))
    groups = [n for n in data["nodes"] if n.get("type") == "group" and n.get("label") == label]
    if len(groups) != 1:
        raise TexError(f"expected exactly one group labelled {label!r}, found {len(groups)}")
    g = groups[0]
    nodes = [
        n for n in data["nodes"]
        if n.get("type") != "group"
        and g["x"] <= n["x"] < g["x"] + g["width"]
        and g["y"] <= n["y"] < g["y"] + g["height"]
    ]
    inside = {n["id"] for n in nodes}
    edges = [
        e for e in data.get("edges", [])
        if e.get("fromNode") in inside and e.get("toNode") in inside
    ]
    return nodes, edges


def collect_citations(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[dict[str, list[str]], set[str]]:
    r"""Map each cited sentence to the commands aimed at it.

    A citation is a grey side card holding `~\cite{key}`, and like every side
    card it originates its edge and points at what it supports. The card is
    consumed rather than printed, and its text is passed through unescaped
    because it is already LaTeX.
    """
    by_id = {n["id"]: n for n in nodes}
    cited: dict[str, list[str]] = {}
    consumed: set[str] = set()
    for edge in edges:
        source = by_id.get(edge["fromNode"])
        if source is None or source.get("color") or source.get("type") != "text":
            continue
        commands = CITATION.findall(strip_id(source.get("text", "")))
        if not commands:
            continue
        cited.setdefault(edge["toNode"], []).extend(commands)
        consumed.add(source["id"])
    return cited, consumed


def reading_order(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sections run left to right; each column reads downward."""
    columns: list[int] = []
    for x in sorted(n["x"] for n in nodes):
        if not columns or x - columns[-1] > COLUMN_TOLERANCE:
            columns.append(x)
    def key(n: dict[str, Any]) -> tuple[int, int]:
        col = max(i for i, c in enumerate(columns) if n["x"] >= c)
        return (col, n["y"])
    return sorted(nodes, key=key)


def display_width(text: str) -> int:
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def markdown_table(body: str) -> tuple[str, bool]:
    """Return the tabular and whether it is too wide for one column."""
    rows = [r.strip() for r in body.splitlines() if r.strip().startswith("|")]
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
    cells = [c for c in cells if not all(set(x) <= set("-: ") for x in c)]
    if not cells:
        raise TexError("table card has no rows")
    width = max(len(r) for r in cells)
    head, *rest = cells
    lines = [r"\begin{tabular}{" + "l" * width + "}", r"\toprule"]
    lines.append(" & ".join(escape(c) for c in head) + r" \\")
    lines.append(r"\midrule")
    for row in rest:
        row = row + [""] * (width - len(row))
        lines.append(" & ".join(escape(c) for c in row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    widest = max(sum(display_width(c) for c in row) + 3 * (width - 1) for row in cells)
    return "\n".join(lines), widest > COLUMN_CHARS


def number_headings(nodes: list[dict[str, Any]]) -> dict[str, str]:
    """Assign each heading the number LaTeX will print for it."""
    counter = {"section": 0, "subsection": 0, "paragraph": 0}
    numbers: dict[str, str] = {}
    seen_first = False
    for node in nodes:
        text = strip_id(node.get("text", ""))
        if not text.startswith("# "):
            continue
        level = HEADING_LEVEL.get(node.get("color", ""))
        if level is None:
            continue
        title = text.splitlines()[0][2:].strip()
        if not seen_first and "초록" not in title:
            seen_first = True  # the manuscript title
            continue
        seen_first = True
        if "초록" in title:
            continue
        counter[level] += 1
        if level == "section":
            counter["subsection"] = counter["paragraph"] = 0
        elif level == "subsection":
            counter["paragraph"] = 0
        numbers[node["id"]] = ".".join(
            str(counter[k]) for k in ("section", "subsection", "paragraph")
            if counter[k] or k == "section"
        )
    return numbers


def apply_section_refs(
    escaped: str, targets: list[str], drift: list[str] | None
) -> str:
    """Turn `5.1절` into a reference to the heading the sentence points at.

    The arrow is what the sentence actually means; the number beside it is a
    copy that goes stale the moment the outline moves. Resolving from the arrow
    keeps the printed number right, and a number that no longer matches any
    target is reported rather than silently renumbered.
    """
    remaining = set(targets)
    def swap(match: re.Match[str]) -> str:
        written = match.group(1)
        if written in remaining:
            remaining.discard(written)
            return f"\\ref{{sec:{written}}}절"
        if drift is not None:
            drift.append(
                f"sentence cites {written}절 but its arrows point at "
                f"{sorted(targets) or 'nothing'}"
            )
        return match.group(0)
    out = SECTION_REF.sub(swap, escaped)
    for unused in sorted(remaining):
        if drift is not None:
            drift.append(f"an arrow points at section {unused} but no `{unused}절` names it")
    return out


def apply_citations(escaped: str, commands: list[str]) -> str:
    """Put each command at its placeholder, or after the sentence if none."""
    for command in commands:
        command = command if command.startswith("~") else "~" + command
        if PLACEHOLDER in escaped:
            escaped = escaped.replace(PLACEHOLDER, command, 1)
        else:
            escaped = escaped.rstrip()
            tail = ""
            while escaped and escaped[-1] in ".?!\u201d\")":
                tail, escaped = escaped[-1] + tail, escaped[:-1]
            escaped = escaped + command + tail
    return escaped


def render(nodes: list[dict[str, Any]], cited: dict[str, list[str]] | None = None,
           consumed: set[str] | None = None, refs: dict[str, list[str]] | None = None,
           drift: list[str] | None = None, extras: dict[str, str] | None = None) -> str:
    out: list[str] = []
    paragraph: list[str] = []
    pending_figure: tuple[str, bool] | None = None
    prev: dict[str, Any] | None = None
    in_abstract = False
    seen_heading = False
    counter = {"section": 0, "subsection": 0, "paragraph": 0}

    def flush() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(" ".join(paragraph))
            out.append("")
            paragraph = []

    cited = cited or {}
    consumed = consumed or set()
    refs = refs or {}

    for node in nodes:
        if node["id"] in consumed:
            continue  # a citation card is folded into the sentence it supports
        if node.get("type") == "file":
            flush()
            # A figure keeps the Canvas card's aspect ratio, so the card itself
            # says whether the image needs both columns.
            aspect = node["width"] / max(node["height"], 1)
            pending_figure = (Path(node.get("file", "")).name, aspect > WIDE_ASPECT)
            prev = node
            continue

        text = strip_id(node.get("text", ""))
        if not text:
            continue

        heading = HEADING.match(text.splitlines()[0]) if text.startswith("# ") else None
        if heading:
            level = HEADING_LEVEL.get(node.get("color", ""))
            if level is None:
                raise TexError(
                    f"heading {heading.group(1)[:40]!r} has colour {node.get('color')!r}; "
                    f"a heading must be purple (section), cyan (subsection), or green (paragraph)"
                )
            flush()
            title = heading.group(1).strip()
            if not seen_heading and "초록" not in title:
                out += [f"% title: {title}", ""]  # belongs in the preamble's \title{}
                seen_heading = True
                prev = node
                continue
            seen_heading = True
            if "초록" in title:
                if in_abstract:
                    out.append(r"\end{abstract}")
                out += [r"\begin{abstract}", ""]
                in_abstract = True
            else:
                if in_abstract:
                    out += [r"\end{abstract}", ""]
                    in_abstract = False
                counter[level] += 1
                if level == "section":
                    counter["subsection"] = counter["paragraph"] = 0
                elif level == "subsection":
                    counter["paragraph"] = 0
                tag = ".".join(
                    str(counter[k]) for k in ("section", "subsection", "paragraph")
                    if counter[k] or k == "section"
                )
                out += [f"\\{level}{{{escape(title)}}}\\label{{sec:{tag}}}", ""]
            prev = node
            continue

        artifact = ARTIFACT.match(text)
        if artifact:
            flush()
            kind, number, rest = artifact.group(1), artifact.group(2), artifact.group(3)
            caption = escape(rest.split("\n")[0].strip())
            if kind == "Table":
                tabular, wide = markdown_table(rest)
                env = "table*" if wide else "table"
                float_ = "\n".join([f"\\begin{{{env}}}[t]", r"\centering", tabular,
                                    f"\\caption{{{caption}}}", f"\\label{{tab:{number}}}",
                                    f"\\end{{{env}}}", ""])
                if extras is None:
                    out += [float_]
                else:
                    # A tabular runs to dozens of lines and buries the prose it
                    # sits in, so it lives in its own file and the body keeps a
                    # one-line reference to it.
                    rel = f"{TABLE_DIR}/table{number}"
                    extras[f"{rel}.tex"] = float_
                    out += [f"\\input{{{rel}}}", ""]
            else:
                if pending_figure is None:
                    raise TexError(f"Figure {number} caption has no image card above it")
                env = "figure*" if pending_figure[1] else "figure"
                out += [f"\\begin{{{env}}}[t]", r"\centering",
                        f"\\includegraphics[width=\\linewidth]{{figs/{pending_figure[0]}}}",
                        f"\\caption{{{caption}}}", f"\\label{{fig:{number}}}",
                        f"\\end{{{env}}}", ""]
                pending_figure = None
            prev = node
            continue

        gap = node["y"] - (prev["y"] + prev["height"]) if prev and prev["x"] == node["x"] else None
        if gap is None or gap >= PARAGRAPH_GAP:
            flush()
        sentence = escape(" ".join(text.split()))
        if node["id"] in refs:
            sentence = apply_section_refs(sentence, refs[node["id"]], drift)
        if node["id"] in cited:
            sentence = apply_citations(sentence, cited[node["id"]])
        paragraph.append(sentence)
        prev = node

    flush()
    if in_abstract:
        out.append(r"\end{abstract}")
    return "\n".join(out).rstrip() + "\n"


def build(canvas: Path, label: str = "paper_v1", drift: list[str] | None = None,
          extras: dict[str, str] | None = None) -> str:
    nodes, edges = load_group(canvas, label)
    ordered = reading_order(nodes)
    cited, consumed = collect_citations(nodes, edges)
    numbers = number_headings(ordered)
    refs: dict[str, list[str]] = {}
    for edge in edges:
        if edge["toNode"] in numbers and edge["fromNode"] not in numbers:
            refs.setdefault(edge["fromNode"], []).append(numbers[edge["toNode"]])
    return render(ordered, cited, consumed, refs, drift, extras)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canvas", type=Path)
    parser.add_argument("--group", default="paper_v1")
    parser.add_argument("--out", type=Path, help="written file, normally main.tex")
    parser.add_argument("--inline-tables", action="store_true",
                        help="keep tabulars in the body instead of their own files")
    args = parser.parse_args()
    drift: list[str] = []
    extras: dict[str, str] | None = None if args.inline_tables or not args.out else {}
    try:
        body = build(args.canvas, args.group, drift, extras)
    except (TexError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: {exc}")
    for line in drift:
        print(f"warning: {line}", file=sys.stderr)
    if not args.out:
        print(body, end="")
        return
    args.out.write_text(body, encoding="utf-8")
    written = [f"{args.out} ({args.out.stat().st_size} bytes)"]
    for rel, content in sorted((extras or {}).items()):
        target = args.out.parent / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(f"{target} ({target.stat().st_size} bytes)")
    print("\n".join(written))


if __name__ == "__main__":
    main()
