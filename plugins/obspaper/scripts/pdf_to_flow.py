#!/usr/bin/env python3
"""Turn a paper PDF into semantic prose blocks and a vault-wide paper-flow Canvas.

A PDF flow is for reading someone else's paper beside a research flow. It keeps
the paper's own units: one card per paragraph, never one card per sentence, so an
argument stays in the card that makes it. Only the `paper` colour grammar is
inherited: purple headings, green contribution cards, everything else uncoloured.

Block boundary rule
-------------------
Words become lines by vertical position. A page is read as two columns when at
most a fifth of its multi-word rows cross the page midline and at least three
rows have words right of it; otherwise it is one column. Before blocks are built:

- a line in the top or bottom 8% of a page is dropped when it is a page number
  (`12`, `Page 12`, `12 of 30`, `- 12 -`) or when the same text, digits ignored,
  sits in that band on at least two pages (a running header or footer);
- on page 1 the consecutive lines set in the largest font are the title and are
  dropped, as is everything before the first heading after it (the author block).

A heading (see `_heading`) always closes the open block. Between two body lines
the second line starts a new block when any of these hold:

1. it starts a caption (`Figure 3:`, `Fig. 3.`, `Table 2:`) or a list item
   (`1)`, `2.`, `(a)`, a bullet or dash);
2. its font size differs from the previous line by more than 0.5pt;
3. on the same page and column, its top is more than 1.4 line pitches below the
   previous line's top, the pitch being the median spacing of body lines;
4. the previous line ends a sentence (`.`, `?`, `!`, `:`) and either this line is
   indented by at least 0.8 of the body font size past the column's left edge, or
   the previous line stops at least two body-font sizes short of the right edge.

Rule 3 is not applied across a page or column break, so a paragraph that runs
onto the next page stays one block unless rule 4 says it ended. Lines of a block
are joined with spaces, except that a line ending in `-` followed by a lowercase
letter is joined without the hyphen. A block whose text starts like a caption is
kind `caption`; every other block is kind `paragraph`. Sentences are never split.

Contribution rule
-----------------
Inside the top-level section whose title contains "introduction", a paragraph is
a contribution candidate when it contains explicit contribution phrasing
(`_CONTRIBUTION`). List items that directly follow a candidate are candidates
too. Candidates become green. This is a mark for the author to review, not a
judgement: pass `contributions` with the exact block keys to replace the marks,
or an empty list to leave every block uncoloured.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from urllib.parse import quote

from obs_project import ProjectError, build_paper_flow
from zotero_bridge import ZoteroClient, ZoteroError


@dataclass(frozen=True)
class Line:
    text: str
    page: int
    column: int
    top: float
    bottom: float
    x0: float
    x1: float
    size: float
    bold_ratio: float


_SECTION = re.compile(r"^(\d{1,2}(?:\.\d+)*)\.?\s+(.+)$")
_CAPTION = re.compile(r"^(?:Figure|Fig\.|Table|Tab\.)\s*[A-Z]?\d+(?:\.\d+)?\s*[:.|]")
_LIST = re.compile(r"^(?:[•◦▪‣∙·\-–—]\s+|\(?\d{1,2}[.)]\s+|\([a-z]\)\s+)")
_PAGE_NUMBER = re.compile(r"^(?:page\s+)?-?\s*\d{1,4}\s*-?(?:\s+of\s+\d{1,4})?$", re.I)
_CONTRIBUTION = re.compile(
    r"\b(?:we\s+(?:propose|introduce|present)"
    r"|our\s+(?:main\s+|key\s+|primary\s+)?contributions?"
    r"|(?:main|key|primary)\s+contributions?"
    r"|contributions\s+of\s+this\s+(?:paper|work)"
    r"|this\s+(?:paper|work)\s+(?:proposes|introduces|presents))\b",
    re.I,
)
_TOP_LEVEL_NAMES = {
    "abstract", "references", "bibliography", "acknowledgment", "acknowledgments",
    "acknowledgement", "acknowledgements", "appendix", "appendices",
}
_REFERENCE_NAMES = {"references", "bibliography"}
_SENTENCE_END = (".", "?", "!", ":")
_NOISE = (
    "thisworkislicensed",
    "license.visit",
    "thislicense.",
    "emailinginfo@",
    "copyrightisheld",
    "licensedtothe",
    "proceedingsofthe",
)
BAND = 0.08


def _bold(fontname: str) -> bool:
    name = fontname.lower()
    return any(mark in name for mark in ("bold", "black", "heavy", "cmbx"))


def _crosses(row: list[dict[str, Any]], middle: float) -> bool:
    for word in row:
        if word["x0"] <= middle <= word["x1"]:
            return True
    return any(a["x1"] < middle < b["x0"] and b["x0"] - a["x1"] < 15 for a, b in zip(row, row[1:]))


def _rows(words: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda value: (value["top"], value["x0"])):
        if rows and abs(rows[-1][0]["top"] - word["top"]) <= 2:
            rows[-1].append(word)
        else:
            rows.append([word])
    for row in rows:
        row.sort(key=lambda value: value["x0"])
    return rows


def _line(words: list[dict[str, Any]], page: int, column: int) -> Line:
    return Line(
        text=" ".join(word["text"] for word in words).strip(),
        page=page,
        column=column,
        top=float(words[0]["top"]),
        bottom=max(float(word["bottom"]) for word in words),
        x0=float(words[0]["x0"]),
        x1=float(words[-1]["x1"]),
        size=float(median(float(word["size"]) for word in words)),
        bold_ratio=sum(_bold(str(word["fontname"])) for word in words) / len(words),
    )


def page_lines(words: list[dict[str, Any]], page: int, width: float) -> list[Line]:
    """Group one page's words into lines, splitting a two-column page by column."""
    rows = _rows(words)
    middle = width / 2
    wide = [row for row in rows if len(row) >= 4]
    right_side = sum(any(word["x0"] > middle for word in row) for row in rows)
    two_columns = (
        len(wide) >= 6
        and sum(_crosses(row, middle) for row in wide) <= 0.2 * len(wide)
        and right_side >= 3
    )
    lines: list[Line] = []
    for row in rows:
        if not two_columns:
            lines.append(_line(row, page, 0))
            continue
        left = [word for word in row if (word["x0"] + word["x1"]) / 2 < middle]
        right = [word for word in row if (word["x0"] + word["x1"]) / 2 >= middle]
        lines.extend(_line(part, page, column) for column, part in ((0, left), (1, right)) if part)
    return sorted(lines, key=lambda line: (line.column, line.top, line.x0))


def _band_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", text)).strip().lower()


def drop_running_matter(lines: list[Line], heights: dict[int, float]) -> tuple[list[Line], int]:
    """Drop page numbers, running headers and footers, and licence boilerplate."""

    def in_band(line: Line) -> bool:
        height = heights[line.page]
        return line.top < height * BAND or line.bottom > height * (1 - BAND)

    pages_by_key: dict[str, set[int]] = {}
    for line in lines:
        if in_band(line) and _band_key(line.text):
            pages_by_key.setdefault(_band_key(line.text), set()).add(line.page)
    kept: list[Line] = []
    for line in lines:
        compact = re.sub(r"\s+", "", line.text).lower()
        if not line.text or any(compact.startswith(prefix) for prefix in _NOISE):
            continue
        if in_band(line) and (_PAGE_NUMBER.match(line.text) or len(pages_by_key.get(_band_key(line.text), ())) >= 2):
            continue
        kept.append(line)
    return kept, len(lines) - len(kept)


def _join_lines(lines: list[Line]) -> str:
    value = ""
    for line in lines:
        word = line.text.strip()
        if value.endswith("-") and word[:1].islower():
            value = value[:-1] + word
        else:
            value += (" " if value else "") + word
    return re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"\s+", " ", value)).strip()


def _body_size(lines: list[Line]) -> float:
    counts: Counter[float] = Counter()
    for line in lines:
        counts[round(line.size * 2) / 2] += len(line.text)
    return counts.most_common(1)[0][0] if counts else 10.0


def _heading(line: Line, body_size: float, tiers: list[float], numbered_sections: bool) -> tuple[int, str] | None:
    """Return (depth, text) when a line is a heading; depth 0 opens a section.

    Named top-level sections (Abstract, References, ...) are depth 0. A numbered
    line in bold or a larger font takes its depth from the number of dots. An
    unnumbered line at least 1.5pt above body size takes its depth from its font
    size tier, and a fully bold body-size line sits one tier below the smallest.
    In a numbered paper unnumbered headings go one level deeper.
    """
    text = line.text.strip()
    if len(text) > 120:
        return None
    if text.rstrip(".").lower() in _TOP_LEVEL_NAMES:
        return 0, text.rstrip(".").title()
    if text.endswith((".", ",", ";", ":")):
        return None
    emphasis = line.bold_ratio >= 0.5 or line.size >= body_size + 0.5
    match = _SECTION.match(text)
    if match and emphasis and match.group(2)[:1].isupper():
        return match.group(1).count("."), match.group(2).strip()
    offset = 1 if numbered_sections else 0
    tier = round(line.size * 2) / 2
    if line.size >= body_size + 1.5 and tier in tiers:
        return tiers.index(tier) + offset, text
    if line.bold_ratio >= 0.75 and line.size >= body_size - 0.5 and text[:1].isupper() and len(text) <= 80:
        return len(tiers) + offset, text
    return None


def _starts_block(previous: Line, current: Line, geometry: dict[tuple[int, int], tuple[float, float]], body_size: float, pitch: float) -> bool:
    if _CAPTION.match(current.text) or _LIST.match(current.text):
        return True
    if abs(current.size - previous.size) > 0.5:
        return True
    same_column = (current.page, current.column) == (previous.page, previous.column)
    if same_column and current.top - previous.top > 1.4 * pitch:
        return True
    if not previous.text.rstrip(")\"'”’").endswith(_SENTENCE_END):
        return False
    left, _ = geometry[(current.page, current.column)]
    _, right = geometry[(previous.page, previous.column)]
    return current.x0 - left >= 0.8 * body_size or previous.x1 <= right - 2 * body_size


def _geometry(lines: list[Line], body_size: float) -> dict[tuple[int, int], tuple[float, float]]:
    grouped: dict[tuple[int, int], list[Line]] = {}
    for line in lines:
        grouped.setdefault((line.page, line.column), []).append(line)
    result: dict[tuple[int, int], tuple[float, float]] = {}
    for key, members in grouped.items():
        body = [line for line in members if abs(line.size - body_size) <= 0.5] or members
        lefts = sorted(line.x0 for line in body)
        rights = sorted(line.x1 for line in body)
        result[key] = (lefts[len(lefts) // 10], rights[-(len(rights) // 10) - 1])
    return result


def _pitch(lines: list[Line], body_size: float) -> float:
    spacings = [
        current.top - previous.top
        for previous, current in zip(lines, lines[1:])
        if (previous.page, previous.column) == (current.page, current.column)
        and abs(previous.size - body_size) <= 0.5
        and abs(current.size - body_size) <= 0.5
        and 0 < current.top - previous.top <= 2.5 * body_size
    ]
    return median(spacings) if spacings else 1.2 * body_size


def mark_contributions(sections: list[dict[str, Any]], override: list[str] | None = None) -> list[str]:
    """Set `role: contribution` on candidate blocks and return their keys.

    With `override`, exactly those block keys are marked and no phrase matching
    runs; an empty list leaves every block uncoloured.
    """
    blocks = {block["key"]: block for section in sections for block in section["blocks"]}
    if override is not None:
        unknown = [key for key in override if key not in blocks or blocks[key]["kind"] != "paragraph"]
        if unknown:
            raise ProjectError("contribution overrides must name paragraph block keys: " + ", ".join(unknown))
        marked = list(dict.fromkeys(override))
    else:
        marked = []
        for section in sections:
            if "introduction" not in section["title"].lower():
                continue
            previous_marked = False
            for block in section["blocks"]:
                if block["kind"] != "paragraph":
                    previous_marked = False
                    continue
                if _CONTRIBUTION.search(block["text"]) or (previous_marked and _LIST.match(block["text"])):
                    marked.append(block["key"])
                    previous_marked = True
                else:
                    previous_marked = False
    for key, block in blocks.items():
        if key in marked:
            block["role"] = "contribution"
        else:
            block.pop("role", None)
    return marked


def extract_lines(pdf: Path) -> tuple[list[Line], dict[int, float]]:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ProjectError("PDF parsing needs pdfplumber: python -m pip install pdfplumber") from exc
    if not pdf.is_file():
        raise ProjectError(f"PDF does not exist: {pdf}")
    lines: list[Line] = []
    heights: dict[int, float] = {}
    try:
        with pdfplumber.open(pdf) as document:
            for number, page in enumerate(document.pages, 1):
                heights[number] = float(page.height)
                words = page.extract_words(use_text_flow=False, extra_attrs=["size", "fontname"])
                lines.extend(page_lines(words, number, float(page.width)))
    except Exception as exc:  # pdfminer raises many unrelated types for a broken file
        raise ProjectError(f"cannot read text from PDF {pdf}: {exc}") from exc
    if sum(len(line.text) for line in lines) < 100:
        raise ProjectError(
            f"PDF has no usable text layer: {pdf}; a scanned PDF needs OCR before it can become a paper flow"
        )
    return lines, heights


def parse_pdf(
    pdf: Path,
    *,
    title: str,
    citekey: str,
    item_key: str,
    contributions: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a paper-flow spec of headings and semantic prose blocks from a PDF."""
    raw, heights = extract_lines(pdf)
    lines, dropped = drop_running_matter(raw, heights)
    body_size = _body_size(lines)

    first_page = [line for line in lines if line.page == 1]
    pdf_title = ""
    if first_page:
        largest = max(line.size for line in first_page)
        if largest >= body_size + 2:
            start = next(index for index, line in enumerate(first_page) if abs(line.size - largest) <= 0.5)
            title_lines = [first_page[start]]
            for line in first_page[start + 1:]:
                if abs(line.size - largest) > 0.5:
                    break
                title_lines.append(line)
            pdf_title = _join_lines(title_lines)
            skipped = set(map(id, title_lines))
            lines = [line for line in lines if id(line) not in skipped]

    numbered_sections = any(
        (match := _SECTION.match(line.text.strip())) is not None
        and "." not in match.group(1)
        and match.group(2)[:1].isupper()
        and (line.bold_ratio >= 0.5 or line.size >= body_size + 0.5)
        for line in lines
    )
    tiers = sorted(
        {
            round(line.size * 2) / 2
            for line in lines
            if line.size >= body_size + 1.5
            and not _SECTION.match(line.text.strip())
            and not line.text.strip().endswith((".", ",", ";", ":"))
            and len(line.text) <= 120
        },
        reverse=True,
    )
    geometry = _geometry(lines, body_size)
    pitch = _pitch(lines, body_size)

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    block: list[Line] = []
    counter = 0
    skipping = False
    last_heading: tuple[dict[str, Any], str, Line] | None = None

    def next_key() -> str:
        nonlocal counter
        counter += 1
        return f"b{counter}"

    def flush() -> None:
        nonlocal block
        if current is not None and block and not skipping:
            text = _join_lines(block)
            if text:
                current["blocks"].append({
                    "key": next_key(),
                    "kind": "caption" if _CAPTION.match(text) else "paragraph",
                    "page": block[0].page,
                    "text": text,
                })
        block = []

    for line in lines:
        if last_heading is not None:
            owner, field, heading_line = last_heading
            if (
                not block
                and abs(line.size - heading_line.size) <= 0.3
                and (line.bold_ratio >= 0.5) == (heading_line.bold_ratio >= 0.5)
                and (line.page, line.column) == (heading_line.page, heading_line.column)
                and 0 < line.top - heading_line.top <= 1.6 * line.size
                and not _SECTION.match(line.text.strip())
                and (line.bold_ratio >= 0.5 or line.size >= body_size + 1.5)
            ):
                owner[field] = f"{owner[field]} {line.text.strip()}"
                last_heading = (owner, field, line)
                continue
        heading = _heading(line, body_size, tiers, numbered_sections)
        if heading:
            flush()
            depth, text = heading
            if depth == 0 or current is None:
                skipping = text.lower() in _REFERENCE_NAMES
                current = {"key": f"s{len(sections) + 1}", "title": text, "blocks": []}
                if not skipping:
                    sections.append(current)
                last_heading = (current, "title", line)
            elif not skipping:
                entry = {"key": next_key(), "kind": "heading", "level": depth, "page": line.page, "text": text}
                current["blocks"].append(entry)
                last_heading = (entry, "text", line)
            continue
        last_heading = None
        if current is None or skipping:
            continue
        if block and _starts_block(block[-1], line, geometry, body_size, pitch):
            flush()
        block.append(line)
    flush()

    sections = [section for section in sections if section["blocks"]]
    if not sections:
        raise ProjectError(
            f"no headings with body text were found in {pdf}; the PDF may lack font size or weight "
            "differences, or put its text in an order this reader cannot follow"
        )
    marked = mark_contributions(sections, contributions)
    spec = {"title": title, "citekey": citekey, "item_key": item_key, "sections": sections}
    blocks = [entry for section in sections for entry in section["blocks"]]
    stats = {
        "pages": len(heights),
        "pdf_title": pdf_title,
        "sections": len(sections),
        "headings": sum(entry["kind"] == "heading" for entry in blocks),
        "paragraphs": sum(entry["kind"] == "paragraph" for entry in blocks),
        "captions": sum(entry["kind"] == "caption" for entry in blocks),
        "dropped_lines": dropped,
        "contributions": marked,
        "contribution_source": "override" if contributions is not None else "phrase-match",
    }
    return spec, stats


def build_from_pdf(
    project: Path,
    pdf: Path,
    *,
    title: str,
    citekey: str,
    item_key: str,
    replace: bool = False,
    spec_output: Path | None = None,
    contributions: list[str] | None = None,
) -> dict[str, Any]:
    """Parse a PDF and write `<Vault>/Paper/<title>.canvas` through `build_paper_flow`."""
    spec, stats = parse_pdf(pdf, title=title, citekey=citekey, item_key=item_key, contributions=contributions)
    if spec_output:
        spec_output.parent.mkdir(parents=True, exist_ok=True)
        spec_output.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        flow = build_paper_flow(project, spec_output, replace=replace)
    else:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper-flow.json"
            path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            flow = build_paper_flow(project, path, replace=replace)
    return {**flow, **stats, "paper_flow": flow["vault_link"], "item_key": item_key, "citekey": citekey}


def build_from_zotero(
    project: Path,
    item_key: str,
    *,
    client: ZoteroClient | None = None,
    replace: bool = False,
    spec_output: Path | None = None,
    contributions: list[str] | None = None,
) -> dict[str, Any]:
    """Build a paper flow from a Zotero item's stored PDF and verified title."""
    client = client or ZoteroClient()
    pdf = client.attachment_path(item_key)
    item, _ = client._request(f"{client.library}/items/{quote(item_key)}")
    title = item.get("data", {}).get("title") if isinstance(item, dict) else None
    if not isinstance(title, str) or not title.strip():
        raise ZoteroError(f"Zotero item {item_key} has no title")
    citekey = client.citation(item_key)["citekey"]
    return build_from_pdf(
        project,
        pdf,
        title=title.strip(),
        citekey=citekey,
        item_key=item_key,
        replace=replace,
        spec_output=spec_output,
        contributions=contributions,
    )
