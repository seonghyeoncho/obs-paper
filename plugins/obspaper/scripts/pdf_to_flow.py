#!/usr/bin/env python3
"""Turn a Zotero PDF into the sentence-level paper-flow JSON and Canvas."""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from obs_project import ProjectError, build_paper_flow
from zotero_bridge import ZoteroClient, ZoteroError


@dataclass(frozen=True)
class Line:
    text: str
    page: int
    column: int
    top: float
    indent: float
    height: float
    size: float
    bold_ratio: float


_SECTION = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
_ARTIFACT = re.compile(r"^(?:fig(?:ure)?\.?|table)\s*\d+", re.I)
_LIST = re.compile(r"^(?:\d+[.)]|[-•])\s+")
_NOISE = (
    "thisworkislicensed",
    "license.visit",
    "thislicense.",
    "emailinginfo@",
    "copyrightisheld",
    "licensedtothe",
    "proceedingsofthe",
    "thisicse",
    "pvlDBreferenceformat".lower(),
    "pvlDBartifactavailability".lower(),
)


def _words_to_lines(page: Any, page_number: int, body_size: float) -> list[Line]:
    lines: list[Line] = []
    margin, gutter = 24.0, 7.0
    middle = page.width / 2
    boxes = ((margin, 32, middle - gutter, page.height - 38), (middle + gutter, 32, page.width - margin, page.height - 38))
    for column, box in enumerate(boxes):
        words = page.crop(box).extract_words(
            x_tolerance=1,
            y_tolerance=3,
            use_text_flow=False,
            extra_attrs=["size", "fontname"],
        )
        grouped: list[list[dict[str, Any]]] = []
        for word in sorted(words, key=lambda value: (value["top"], value["x0"])):
            if grouped and abs(grouped[-1][0]["top"] - word["top"]) <= 2:
                grouped[-1].append(word)
            else:
                grouped.append([word])
        for row in grouped:
            row.sort(key=lambda value: value["x0"])
            text = " ".join(word["text"] for word in row).strip()
            compact = re.sub(r"\s+", "", text).lower()
            if not text or text.isdigit() or any(compact.startswith(prefix) for prefix in _NOISE):
                continue
            font_sizes = [float(word["size"]) for word in row]
            bold = sum("bold" in str(word["fontname"]).lower() for word in row) / len(row)
            lines.append(Line(
                text=text,
                page=page_number,
                column=column,
                top=float(row[0]["top"]),
                indent=float(row[0]["x0"] - box[0]),
                height=max(float(word["bottom"] - word["top"]) for word in row),
                size=median(font_sizes) if font_sizes else body_size,
                bold_ratio=bold,
            ))
    return lines


def _join_lines(lines: list[Line]) -> str:
    value = ""
    for line in lines:
        word = line.text.strip()
        if value.endswith("-") and word[:1].islower():
            value = value[:-1] + word
        else:
            value += (" " if value else "") + word
    return re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"\s+", " ", value)).strip()


def _sentences(paragraph: str) -> list[str]:
    protected = paragraph
    for token in ("e.g.", "i.e.", "et al.", "Fig.", "Eq.", "Sec.", "Dr.", "Mr.", "Ms.", "vs."):
        protected = protected.replace(token, token.replace(".", "<DOT>"))
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DOT>", protected)
    parts = re.split(r"(?<=[.!?])\s+(?=[\[\(\"'“‘]*[A-Z0-9])", protected)
    return [part.replace("<DOT>", ".").strip() for part in parts if part.strip()]


def _heading(line: Line, body_size: float, numbered_sections: bool) -> tuple[int, str] | None:
    text = line.text.strip()
    if text.upper() in {"ABSTRACT", "REFERENCES", "ACKNOWLEDGMENT", "ACKNOWLEDGMENTS", "ACKNOWLEDGEMENTS", "APPENDIX"}:
        return 0, text.title()
    match = _SECTION.match(text)
    if match and (line.bold_ratio >= 0.5 or line.size >= body_size + 0.5):
        number, title = match.groups()
        if title[:1].isupper() and not title.startswith(("Identify ", "Validate ", "Design ", "Develop ", "Implement ")):
            return number.count("."), title.strip()
    if line.size >= body_size + 1.5 and len(text) <= 120 and not text.endswith((".", ":")):
        return (1 if numbered_sections else 0), text
    if line.bold_ratio >= 0.75 and line.size >= body_size and len(text) <= 120 and not text.endswith((".", ":")):
        return 1, text
    return None


def _paragraph_break(previous: Line, current: Line) -> bool:
    if current.column != previous.column or current.page != previous.page:
        return current.indent > 5 and previous.text.endswith((".", "?", "!"))
    gap = current.top - previous.top
    return (
        gap > max(previous.height, current.height) * 1.45
        or (_LIST.match(current.text) is not None)
        or (current.indent > 5 and previous.text.endswith((".", "?", "!")))
    )


def parse_pdf(pdf: Path, *, title: str, citekey: str, item_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ProjectError("PDF parsing needs pdfplumber: pip install pdfplumber") from exc
    if not pdf.is_file():
        raise ProjectError(f"PDF does not exist: {pdf}")

    with pdfplumber.open(pdf) as document:
        sizes = [
            float(word["size"])
            for page in document.pages
            for word in page.extract_words(extra_attrs=["size"])
            if 7 <= float(word["size"]) <= 13
        ]
        body_size = median(sizes) if sizes else 10.0
        lines = [line for number, page in enumerate(document.pages, 1) for line in _words_to_lines(page, number, body_size)]
        page_count = len(document.pages)

    abstract_tops = [line.top for line in lines if line.page == 1 and line.text.strip().upper() == "ABSTRACT"]
    if abstract_tops:
        lines = [line for line in lines if line.page != 1 or line.top >= min(abstract_tops)]
    numbered_sections = any(
        (match := _SECTION.match(line.text.strip()))
        and "." not in match.group(1)
        and match.group(2)[:1].isupper()
        and (line.bold_ratio >= 0.5 or line.size >= body_size + 0.5)
        for line in lines
    )

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    paragraph: list[Line] = []
    paragraph_number = 0
    block_number = 0
    artifacts: list[dict[str, Any]] = []
    started = False

    def flush() -> None:
        nonlocal paragraph, paragraph_number, block_number
        if not current or not paragraph:
            paragraph = []
            return
        source_page = paragraph[0].page
        text = _join_lines(paragraph)
        paragraph = []
        if not text:
            return
        paragraph_number += 1
        if _ARTIFACT.match(text):
            artifacts.append({"page": source_page, "caption": text})
        for sentence in _sentences(text):
            block_number += 1
            current["blocks"].append({
                "key": f"b{block_number}",
                "kind": "sentence",
                "paragraph": f"p{paragraph_number}",
                "text": sentence,
            })

    for line in lines:
        heading = _heading(line, body_size, numbered_sections)
        if not started:
            match = _SECTION.match(line.text.strip())
            if heading and (heading[1].lower() == "abstract" or (match and "." not in match.group(1))):
                started = True
            else:
                continue
        if heading:
            flush()
            level, heading_text = heading
            if level == 0 or current is None:
                current = {"key": f"s{len(sections) + 1}", "title": heading_text, "blocks": []}
                sections.append(current)
            else:
                if current["blocks"] and current["blocks"][-1]["kind"] == "heading":
                    current["blocks"][-1]["text"] += " " + heading_text
                    continue
                block_number += 1
                current["blocks"].append({"key": f"b{block_number}", "kind": "heading", "level": level, "text": heading_text})
            continue
        if current and paragraph and _paragraph_break(paragraph[-1], line):
            flush()
        if current:
            paragraph.append(line)
    flush()

    sections = [section for section in sections if section["blocks"]]
    if not sections:
        raise ProjectError(f"no paper sections were parsed from {pdf}")
    spec = {"title": title, "citekey": citekey, "item_key": item_key, "sections": sections}
    stats = {
        "pages": page_count,
        "sections": len(sections),
        "sentences": sum(block["kind"] == "sentence" for section in sections for block in section["blocks"]),
        "headings": sum(block["kind"] == "heading" for section in sections for block in section["blocks"]),
        "artifact_captions": artifacts,
    }
    return spec, stats


def build_from_zotero(project: Path, item_key: str, *, replace: bool = False, spec_output: Path | None = None) -> dict[str, Any]:
    client = ZoteroClient()
    item, _ = client._request(f"users/0/items/{item_key}")
    title = item.get("data", {}).get("title") if isinstance(item, dict) else None
    if not isinstance(title, str) or not title.strip():
        raise ZoteroError(f"Zotero item {item_key} has no title")
    citekey = client.citation(item_key)["citekey"]
    spec, stats = parse_pdf(client.attachment_path(item_key), title=title, citekey=citekey, item_key=item_key)
    if spec_output:
        spec_output.parent.mkdir(parents=True, exist_ok=True)
        spec_output.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        flow = build_paper_flow(project, spec_output, replace=replace)
    else:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper-flow.json"
            path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            flow = build_paper_flow(project, path, replace=replace)
    return {**flow, **stats, "item_key": item_key, "citekey": citekey}
