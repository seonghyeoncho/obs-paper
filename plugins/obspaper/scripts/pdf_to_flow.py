#!/usr/bin/env python3
"""Turn a paper PDF into semantic prose blocks and a vault-wide paper-flow Canvas.

A PDF flow is for reading someone else's paper beside a research flow. It keeps
the paper's own units: one card per paragraph, never one card per sentence, so an
argument stays in the card that makes it. Only the `paper` colour grammar is
inherited: purple headings, green contribution cards, everything else uncoloured.

Reading the page
----------------
Only upright characters are read, so rotated side stamps (the arXiv identifier)
and vertical labels are ignored. Characters at least 0.8 of the body font size
form rows; a smaller character (a sub- or superscript) joins a row only when it
sits within that row's height and within 1.5 body sizes of one of its
characters, so tiny figure labels never join body text. Within a row a new word
starts where the gap to the previous character exceeds 0.15 of the font size.
Words whose vertical centres lie within 0.3 of their font size form one line, so
small capitals stay on the line they belong to.

A page has two columns when a vertical strip in its middle 30% is crossed by
body-size words (0.8 to 1.2 of body size) on at most 15% of body rows, with
words on both sides of it. When a page fails that test but other pages pass, the
median gutter of those pages is used if at least 60% of the page's body rows do
not cross it and three or more have words right of it. Words are split at the
gutter before lines are formed. A row whose words cross the gutter, or whose right part starts well inside the
right column, is a full-width line (title, table, wide caption). Full-width
lines cut the page into bands, and each band is read left column, then right.

Lines that are not prose are removed before blocks are built, and counted:

- running matter: a line in the top or bottom 8% of a page that is a page number
  or whose text, digits ignored, recurs in that band on two or more pages;
- margins: lines wholly outside the body text's horizontal extent;
- figure text: lines smaller than 0.8 of body size, or set mostly (60%) in a font
  family that makes up under 5% of the document and is not a math font;
- table headers: body-size lines of three to ten tokens, not a numbered heading,
  that are mostly abbreviations and bold or spread apart, or whose words are
  more than 2.5 font sizes apart and mostly not lowercase words;
- tables: two or more nearby rows of three or more tokens with at least two
  numbers, where numbers are half the tokens or words of three letters are under
  40% of them; grown to adjacent short lines that do not end a sentence and are
  not styled like a heading unless their cells are spread apart; plus text inside
  regions pdfplumber's `find_tables` reports;
- footnotes: lines at least 1pt below body size under the last body line of
  their column, unless a caption starts there;
- display math: a line set 40% or more in math fonts that is indented, set apart,
  or does not continue an unfinished sentence.

On page 1 the largest lines of two or more words are the title; following lines
at least 0.75 of that size and close below it continue it. Everything before the
first heading that is named (Abstract, Introduction, ...), numbered, or taken
from the outline is the author block and is dropped, except that when that
heading is not Abstract, the prose paragraphs directly above it are kept as an
Abstract section.

Headings
--------
When the PDF has an outline (bookmarks), it is the primary heading source: each
entry is matched to one to three consecutive lines on its destination page (or
the next) whose text, numbering and punctuation ignored, equals the entry, the
one nearest the destination's height winning. The entry gives the heading's
depth and text. The outline is used when at least half its entries are found.
Lines that match no entry can still be named headings (Abstract, References)
or fully bold paragraph headings, one level below the last section heading.
Without a usable outline, `_heading` decides from the fonts. Each heading in the
spec records `source`, `outline` or `font`.

Run-in paragraph headings ("Name. Text..." with only the name in bold) are
treated as prose: a line is a bold heading only when 95% of its characters are
bold, so the lead stays in its paragraph.

Block boundary rule
-------------------
A heading always closes the open block. Between two body lines the second line
starts a new block when any of these hold:

1. it starts a caption (`Figure 3:`, `Fig. 3.`, `Table 2:`) or a list item
   (`1)`, `2.`, `(a)`, a bullet or dash);
2. its font size differs from the previous line by more than 0.5pt;
3. on the same page and column, its top is more than 1.4 line pitches below the
   previous line's top, the pitch being the median spacing of body lines;
4. the previous line ends a sentence (`.`, `?`, `!`, `:`) and either this line is
   indented by at least 0.8 of the body font size past the column's left edge, or
   the previous line stops at least two body-font sizes short of the right edge.

Rule 3 is not applied across a page or column break, so a paragraph that runs
onto the next column stays one block unless rule 4 says it ended. Lines of a
block are joined with spaces. A line ending in a hyphen is joined to the next
without a space: the hyphen is kept when the hyphenated word occurs elsewhere
in the document and the joined word does not, and dropped when the joined word
occurs elsewhere or the next line starts in lowercase. A block whose text starts
like a caption is kind `caption`; every other block is kind `paragraph`.
Sentences are never split. A paragraph is a fragment when it has fewer than
three words, or is under 40 characters, not a list item, and not a sentence that
starts in capitals and ends in punctuation. A fragment that does not end a
sentence is put in front of the next paragraph when that one starts in
lowercase; otherwise it is merged into the paragraph before it when it continues
that paragraph (it starts in lowercase or the paragraph has not ended a
sentence), and dropped when neither holds.

Contribution rule
-----------------
Inside the Abstract and the section whose title contains "introduction", a
paragraph is a contribution candidate when it contains explicit contribution
phrasing (`_CONTRIBUTION`). List items that directly follow a candidate are
candidates too. Candidates become green. This is a mark for the author to
review, not a judgement: pass `contributions` with the exact block keys to
replace the marks, or an empty list to leave every block uncoloured.
"""

from __future__ import annotations

import bisect
import json
import re
import tempfile
import unicodedata
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
    chars: int = 0
    math: int = 0
    minor: int = 0
    max_gap: float = 0.0


_SECTION = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.?\s+(.+)$")
_APPENDIX_SECTION = re.compile(r"^([A-H](?:\.\d{1,2})*)\.?\s+(.+)$")
_NUMBER_TOKEN = re.compile(r"^(?:[A-Z]|\d{1,2})(?:\.\d{1,2})*\.?$")
_OUTLINE_NUMBER = re.compile(r"^\s*(?:\d{1,2}|[A-Z](?=\.\d))(?:\.\d{1,2})*\.?\s+")
_OUTLINE_LETTER = re.compile(r"^\s*[A-Z]\.?\s+(?=\S)")
_CAPTION = re.compile(r"^(?:Figure|Fig\.|Table|Tab\.)\s*[A-Z]?\d+(?:\.\d+)?\s*[:.|]")
_LIST = re.compile(r"^(?:[•◦▪‣∙·\-–—]\s*|\(?\d{1,2}[.)]\s+|\([a-z]\)\s+)")
_PAGE_NUMBER = re.compile(r"^(?:page\s+)?-?\s*\d{1,4}\s*-?(?:\s+of\s+\d{1,4})?$", re.I)
_WORD = re.compile(r"[^\W\d_]{3,}")
_TWO_LETTERS = re.compile(r"[^\W\d_]{2,}")
_VOCABULARY_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")
_CONTRIBUTION = re.compile(
    r"\b(?:we\s+(?:propose|introduce|present)"
    r"|our\s+(?:main\s+|key\s+|primary\s+)?contributions?"
    r"|(?:main|key|primary)\s+contributions?"
    r"|contributions\s+of\s+(?:this|our)\s+(?:paper|work)"
    r"|this\s+(?:paper|work)\s+(?:proposes|introduces|presents))\b",
    re.I,
)
_TOP_LEVEL_NAMES = {
    "abstract", "introduction", "references", "bibliography", "acknowledgment", "acknowledgments",
    "acknowledgement", "acknowledgements", "appendix", "appendices",
}
_REFERENCE_NAMES = {"references", "bibliography"}
_CONTRIBUTION_SECTIONS = ("abstract", "introduction")
_SENTENCE_END = (".", "?", "!", ":")
_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_MATH_FAMILY = re.compile(r"^(?:CMMI|CMSY|CMEX|CMR|MSBM|MSAM|EUFM|EUSM|EUEX|RSFS|Symbol|STIX|LMMath|MTMI|MTSY|txsy|txex|rtxmi)", re.I)
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


def _family(fontname: str) -> str:
    name = str(fontname).split("+", 1)[-1]
    name = re.split(r"[-,]", name)[0]
    name = re.sub(r"(?:PS)?MT$|PS$", "", name)
    name = re.sub(r"\d+$", "", name)
    if re.match(r"^CM(?:R|BX|TI|SL|CSC|SS|SSBX|SSI|B|U)$", name):
        return "CMR"
    return name


def _bold(fontname: str) -> bool:
    name = str(fontname).lower()
    return any(mark in name for mark in ("bold", "black", "heavy", "medi", "demi", "cmbx"))


def _ends_sentence(text: str) -> bool:
    return text.rstrip(")\"'”’").endswith(_SENTENCE_END)


def _capitals(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return len(letters) >= 4 and sum(char.isupper() for char in letters) >= 0.9 * len(letters)


def _rows(words: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group words into rows by vertical centre, tolerant of small capitals."""
    rows: list[tuple[float, float, list[dict[str, Any]]]] = []
    for word in sorted(words, key=lambda value: ((value["top"] + value["bottom"]) / 2, value["x0"])):
        centre = (word["top"] + word["bottom"]) / 2
        size = float(word.get("size", word["bottom"] - word["top"]))
        if rows and abs(rows[-1][0] - centre) <= max(2.0, 0.3 * min(size, rows[-1][1])):
            rows[-1][2].append(word)
        else:
            rows.append((centre, size, [word]))
    result = []
    for _, _, row in rows:
        row.sort(key=lambda value: value["x0"])
        result.append(row)
    return result


def build_words(
    chars: list[dict[str, Any]],
    body_size: float,
    math_families: set[str] = frozenset(),
    minor_families: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Build words from upright characters with a gap threshold relative to font size."""
    chars = [char for char in chars if char.get("upright", True) and char["text"].strip()]
    main = sorted((char for char in chars if char["size"] >= 0.8 * body_size), key=lambda char: (char["top"], char["x0"]))
    small = [char for char in chars if char["size"] < 0.8 * body_size]
    rows: list[dict[str, Any]] = []
    for char in main:
        centre = (char["top"] + char["bottom"]) / 2
        if rows and rows[-1]["top"] - 1 <= centre <= rows[-1]["bottom"] + 1:
            rows[-1]["chars"].append(char)
        else:
            rows.append({"top": char["top"], "bottom": char["bottom"], "chars": [char]})
    for row in rows:
        row["spans"] = sorted((char["x0"], char["x1"]) for char in row["chars"])
        row["starts"] = [span[0] for span in row["spans"]]
    tops = [row["top"] for row in rows]
    reach = 1.5 * body_size
    orphans: list[dict[str, Any]] = []
    for char in small:
        centre = (char["top"] + char["bottom"]) / 2
        best, distance = None, None
        index = bisect.bisect_right(tops, centre + 2)
        while index > 0:
            index -= 1
            row = rows[index]
            if row["top"] < centre - 3 * body_size:
                break
            if not row["top"] - 2 <= centre <= row["bottom"] + 2:
                continue
            position = bisect.bisect_left(row["starts"], char["x0"])
            near = [row["spans"][k] for k in (position - 1, position) if 0 <= k < len(row["spans"])]
            if not any(max(0.0, x0 - char["x1"], char["x0"] - x1) <= reach for x0, x1 in near):
                continue
            gap = abs(centre - (row["top"] + row["bottom"]) / 2)
            if distance is None or gap < distance:
                best, distance = row, gap
        if best is None:
            orphans.append(char)
        else:
            best["chars"].append(char)
    extra: list[dict[str, Any]] = []
    for char in sorted(orphans, key=lambda value: (value["top"], value["x0"])):
        centre = (char["top"] + char["bottom"]) / 2
        if extra and extra[-1]["top"] - 1 <= centre <= extra[-1]["bottom"] + 1:
            extra[-1]["chars"].append(char)
        else:
            extra.append({"top": char["top"], "bottom": char["bottom"], "chars": [char]})

    words: list[dict[str, Any]] = []
    for row in rows + extra:
        current: list[dict[str, Any]] = []
        right = 0.0
        for char in sorted(row["chars"], key=lambda value: value["x0"]):
            if current and char["x0"] - right > 0.15 * max(char["size"], current[-1]["size"]):
                words.append(_word(current, body_size, math_families, minor_families))
                current = []
            current.append(char)
            right = max(right, char["x1"]) if len(current) > 1 else char["x1"]
        if current:
            words.append(_word(current, body_size, math_families, minor_families))
    return words


def _word(chars: list[dict[str, Any]], body_size: float, math_families: set[str], minor_families: set[str]) -> dict[str, Any]:
    main = [char for char in chars if char["size"] >= 0.8 * body_size] or chars
    families = [_family(char.get("fontname", "")) for char in chars]
    fonts = Counter(str(char.get("fontname", "")) for char in main)
    return {
        "text": "".join(_LIGATURES.get(char["text"], char["text"]) for char in chars),
        "x0": min(char["x0"] for char in chars),
        "x1": max(char["x1"] for char in chars),
        "top": min(char["top"] for char in main),
        "bottom": max(char["bottom"] for char in main),
        "size": max(char["size"] for char in main),
        "fontname": fonts.most_common(1)[0][0],
        "chars": len(chars),
        "bold": sum(_bold(str(char.get("fontname", ""))) for char in chars),
        "math": sum(family in math_families for family in families),
        "minor": sum(family in minor_families for family in families),
    }


def _line(words: list[dict[str, Any]], page: int, column: int) -> Line:
    chars = sum(int(word.get("chars", len(word["text"]))) for word in words)
    bold = sum(
        int(word["bold"]) if "bold" in word else (len(word["text"]) if _bold(str(word.get("fontname", ""))) else 0)
        for word in words
    )
    gaps = [
        (right["x0"] - left["x1"]) / max(float(right["size"]), 1.0)
        for index, (left, right) in enumerate(zip(words, words[1:]))
        if not (index == 0 and _NUMBER_TOKEN.match(left["text"]))
    ]
    return Line(
        text=" ".join(word["text"] for word in words).strip(),
        page=page,
        column=column,
        top=float(min(word["top"] for word in words)),
        bottom=float(max(word["bottom"] for word in words)),
        x0=float(words[0]["x0"]),
        x1=float(max(word["x1"] for word in words)),
        size=float(median(float(word["size"]) for word in words)),
        bold_ratio=bold / chars if chars else 0.0,
        chars=chars,
        math=sum(int(word.get("math", 0)) for word in words),
        minor=sum(int(word.get("minor", 0)) for word in words),
        max_gap=max(gaps) if gaps else 0.0,
    )


def _body_words(words: list[dict[str, Any]], body_size: float) -> list[dict[str, Any]]:
    return [word for word in words if 0.8 * body_size <= float(word["size"]) <= 1.2 * body_size]


def _gutter(words: list[dict[str, Any]], width: float, body_size: float) -> float | None:
    body = _body_words(words, body_size)
    if len(body) < 30:
        return None
    low, high = int(width * 0.35), int(width * 0.65)
    cover = [0] * (high - low + 2)
    for word in body:
        start = max(low, int(word["x0"] - 1))
        end = min(high, int(word["x1"] + 1))
        if start <= end:
            cover[start - low] += 1
            cover[end - low + 1] -= 1
    running, values = 0, []
    for delta in cover[:-1]:
        running += delta
        values.append(running)
    least = min(values)
    if least > max(2, 0.15 * len(_rows(body))):
        return None
    best_start, best_length, start = 0, 0, None
    for index, value in enumerate(values + [least + 1]):
        if value == least and start is None:
            start = index
        elif value != least and start is not None:
            if index - start > best_length:
                best_start, best_length = start, index - start
            start = None
    gutter = low + best_start + best_length / 2
    left = sum(word["x1"] < gutter for word in body)
    right = sum(word["x0"] > gutter for word in body)
    if left < 0.15 * len(body) or right < 0.15 * len(body):
        return None
    return gutter


def _gutter_fits(words: list[dict[str, Any]], gutter: float, body_size: float) -> bool:
    """Whether a two-column document's gutter also splits this page's rows."""
    rows = _rows(_body_words(words, body_size))
    clean = right_side = 0
    for row in rows:
        left = [word for word in row if word["x1"] <= gutter]
        right = [word for word in row if word["x0"] >= gutter]
        if len(left) + len(right) < len(row):
            continue
        if left and right and right[0]["x0"] - left[-1]["x1"] < body_size:
            continue
        clean += 1
        right_side += bool(right)
    return bool(rows) and right_side >= 3 and clean >= 0.6 * len(rows)


def page_lines(
    words: list[dict[str, Any]],
    page: int,
    width: float,
    body_size: float | None = None,
    gutter_hint: float | None = None,
) -> list[Line]:
    """Group one page's words into lines in reading order, column by column."""
    if not words:
        return []
    if body_size is None:
        counts = Counter(round(float(word["size"]) * 2) / 2 for word in words)
        body_size = counts.most_common(1)[0][0]
    rows = _rows(words)
    gutter = _gutter(words, width, body_size)
    if gutter is None and gutter_hint is not None and _gutter_fits(words, gutter_hint, body_size):
        gutter = gutter_hint
    if gutter is None:
        return sorted((_line(row, page, 0) for row in rows), key=lambda line: (line.top, line.x0))
    right_words = sorted(word["x0"] for word in _body_words(words, body_size) if word["x0"] > gutter)
    right_edge = right_words[len(right_words) // 20] if right_words else gutter
    columns: list[Line] = []
    spanning: list[Line] = []
    for row in rows:
        left = [word for word in row if word["x1"] <= gutter]
        right = [word for word in row if word["x0"] >= gutter]
        crossing = len(left) + len(right) < len(row)
        if not crossing and left and right:
            gap = right[0]["x0"] - left[-1]["x1"]
            crossing = gap < float(right[0]["size"]) or right[0]["x0"] - right_edge > 2.5 * body_size
        if crossing:
            spanning.append(_line(row, page, 2))
        else:
            columns.extend(_line(part, page, column) for column, part in ((0, left), (1, right)) if part)
    ordered: list[Line] = []
    remaining = columns
    for line in sorted(spanning, key=lambda value: value.top):
        before = [value for value in remaining if value.top < line.top]
        remaining = [value for value in remaining if value.top >= line.top]
        ordered.extend(sorted(before, key=lambda value: (value.column, value.top)))
        ordered.append(line)
    ordered.extend(sorted(remaining, key=lambda value: (value.column, value.top)))
    return ordered


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


def _vocabulary(lines: Iterable[Line]) -> set[str]:
    words: set[str] = set()
    for line in lines:
        text = line.text[:-1] if line.text.endswith("-") else line.text
        words.update(_VOCABULARY_WORD.findall(text.lower()))
    return words


def _join_text(value: str, addition: str, vocabulary: set[str] | None = None) -> str:
    addition = addition.strip()
    if value.endswith("-") and addition[:1].isalpha():
        head = re.search(r"([^\W\d_]+)-$", value)
        tail = re.match(r"[^\W\d_]+", addition)
        if head and tail:
            joined = (head.group(1) + tail.group(0)).lower()
            hyphenated = f"{head.group(1)}-{tail.group(0)}".lower()
            known = vocabulary if vocabulary is not None else set()
            if hyphenated in known and joined not in known:
                return value + addition
            if joined in known or addition[:1].islower():
                return value[:-1] + addition
            return value + addition
    return value + (" " if value else "") + addition


def _join_lines(lines: list[Line], vocabulary: set[str] | None = None) -> str:
    value = ""
    for line in lines:
        value = _join_text(value, line.text, vocabulary)
    return re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"\s+", " ", value)).strip()


def _abbreviation(token: str) -> bool:
    """A number, a symbol, a capital code of up to five letters (VOC), or a mixed-case code (SQuAD, MNLI-m)."""
    core = token.strip("()[]{},;:.")
    letters = re.sub(r"[^A-Za-z]", "", core)
    if not letters or re.search(r"\d", core):
        return True
    if letters.isupper():
        return len(letters) <= 5
    return re.search(r"[A-Z]{2}", letters) is not None


def _tabular(text: str) -> bool:
    """A run of mostly abbreviations, numbers, and metric names, like a table header."""
    tokens = text.split()
    return bool(tokens) and sum(_abbreviation(token) for token in tokens) >= 0.6 * len(tokens)


def _heading(
    line: Line,
    body_size: float,
    tiers: list[float],
    numbered_sections: bool,
    appendix: bool = False,
) -> tuple[int, str, str] | None:
    """Return (depth, text, how) when a line is a heading by its fonts; depth 0 opens a section.

    Named sections (Abstract, Introduction, References, ...) are depth 0 when set
    in bold, a larger font, or capitals. A numbered line (`3.2`, or `A.1` once
    the appendix has begun: after References, or at an `A` heading set at least
    as large as the numbered section headings) in bold, a larger font, or capitals takes its depth
    from the number of dots. An unnumbered line at least 1.5pt above body size
    takes its depth from its font size tier, and a body-size line whose
    characters are at least 95% bold, of at most eight words, sits one tier below
    the smallest. In a numbered paper unnumbered headings go one level below the
    numbered heading they follow.

    Never a heading: a line without a word of three letters (a drop cap, a stray
    glyph, a math symbol); a line ending in a hyphen or sentence punctuation; a
    line whose words are spread apart by more than 1.5 font sizes (table cells);
    an unnumbered line that is mostly abbreviations, numbers, and metric names;
    and a line within three line pitches above a removed table line or just
    below one. A run-in lead followed by prose on the same line fails the 95% bold
    test and stays prose.
    """
    text = line.text.strip()
    words = text.split()
    if len(text) > 120 or len(words) > 14:
        return None
    emphasis = line.bold_ratio >= 0.5 or line.size >= body_size + 0.5 or _capitals(text)
    name = text.rstrip(":").strip()
    if name.lower() in _TOP_LEVEL_NAMES and emphasis:
        return 0, name[:1].upper() + name[1:].lower(), "named"
    if text.endswith((".", ",", ";", ":", "-")) or not _WORD.search(text) or line.max_gap > 1.5:
        return None
    match = _SECTION.match(text) or (_APPENDIX_SECTION.match(text) if appendix else None)
    if match:
        number, title = match.groups()
        if emphasis and title[:1].isupper() and _WORD.search(title) and len(title.split()) <= 12:
            return number.count("."), title.strip(), "numbered"
        return None
    if not text[:1].isupper() or _tabular(text):
        return None
    offset = 1 if numbered_sections else 0
    tier = round(line.size * 2) / 2
    if line.size >= body_size + 1.5 and tier in tiers and len(words) <= 12:
        return tiers.index(tier) + offset, text, "tier"
    if line.bold_ratio >= 0.95 and line.size >= body_size - 0.5 and len(words) <= 8:
        return len(tiers) + offset, text, "bold"
    return None


def _outline_key(text: str) -> str:
    text = _OUTLINE_NUMBER.sub("", text)
    text = _OUTLINE_LETTER.sub("", text)
    text = unicodedata.normalize("NFKD", text).lower()
    return re.sub(r"[^0-9a-z]", "", text)


def match_outline(entries: list[dict[str, Any]], lines: list[Line]) -> tuple[dict[int, tuple[int, str]], set[int], list[str]]:
    """Locate outline entries among lines.

    Returns the heading for the first line of each match as (depth, title), the
    indexes of continuation lines of multi-line headings, and the titles of
    entries that were not found. An entry matches one to three consecutive lines
    on its destination page or the next one whose normalised text equals the
    entry's; among several matches the first one after the previous entry wins,
    then the one on the destination page, then the one nearest its height.
    """
    keyed = [entry for entry in entries if _outline_key(str(entry.get("title", "")))]
    if not keyed:
        return {}, set(), []
    base = min(int(entry.get("level", 1)) for entry in keyed)
    letters = {
        match.group(1)
        for entry in keyed
        if int(entry.get("level", 1)) == base and (match := re.match(r"^\s*([A-Z])\.?\s+\S", str(entry["title"])))
    }
    by_page: dict[int, list[int]] = {}
    for index, line in enumerate(lines):
        by_page.setdefault(line.page, []).append(index)
    headings: dict[int, tuple[int, str]] = {}
    continuation: set[int] = set()
    unmatched: list[str] = []
    used: set[int] = set()
    last = -1
    for entry in keyed:
        title = str(entry["title"]).strip()
        key = _outline_key(title)
        page = entry.get("page")
        pages = [page, page + 1] if isinstance(page, int) else sorted(by_page)
        candidates: list[list[int]] = []
        for number in pages:
            indexes = by_page.get(number, [])
            for position, index in enumerate(indexes):
                text = _outline_key(lines[index].text)
                if index in used or not text or not key.startswith(text):
                    continue
                span, joined = [index], text
                while joined != key and len(span) < 3 and position + len(span) < len(indexes):
                    following = indexes[position + len(span)]
                    addition = _outline_key(lines[following].text)
                    if following in used or not addition or not key.startswith(joined + addition):
                        break
                    span.append(following)
                    joined += addition
                if joined == key:
                    candidates.append(span)
        if not candidates:
            unmatched.append(title)
            continue
        top = entry.get("top")

        def score(span: list[int]) -> tuple[int, int, float, int]:
            first = lines[span[0]]
            distance = abs(first.top - top) if isinstance(top, (int, float)) and first.page == page else 1e6
            return (0 if span[0] > last else 1, 0 if first.page == page else 1, distance, span[0])

        best = min(candidates, key=score)
        display = _OUTLINE_NUMBER.sub("", title)
        if len(letters) >= 2:
            display = _OUTLINE_LETTER.sub("", display)
        headings[best[0]] = (int(entry.get("level", 1)) - base, display.strip() or title)
        continuation.update(best[1:])
        used.update(best)
        last = best[0]
    return headings, continuation, unmatched


def _starts_block(previous: Line, current: Line, geometry: dict[tuple[int, int], tuple[float, float]], body_size: float, pitch: float) -> bool:
    if _CAPTION.match(current.text) or _LIST.match(current.text):
        return True
    if abs(current.size - previous.size) > 0.5:
        return True
    same_column = (current.page, current.column) == (previous.page, previous.column)
    if same_column and current.top - previous.top > 1.4 * pitch:
        return True
    if not _ends_sentence(previous.text):
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


def _by_column(lines: list[Line]) -> dict[tuple[int, int], list[int]]:
    grouped: dict[tuple[int, int], list[int]] = {}
    for index, line in enumerate(lines):
        grouped.setdefault((line.page, line.column), []).append(index)
    for indexes in grouped.values():
        indexes.sort(key=lambda index: lines[index].top)
    return grouped


def _numbered_heading_like(line: Line) -> bool:
    match = _SECTION.match(line.text.strip()) or re.match(r"^([A-H](?:\.\d{1,2})*)\.?\s+([A-Z].*)$", line.text.strip())
    return bool(match) and match.group(2)[:1].isupper() and (line.bold_ratio >= 0.5 or _capitals(match.group(2)))


def _table_header(line: Line, body_size: float) -> bool:
    """A short body-size line of cells: codes and metric names in bold or spread apart, or words far apart."""
    tokens = line.text.split()
    if len(tokens) < 3 or len(tokens) > 10 or line.size > body_size + 1 or _ends_sentence(line.text) or _numbered_heading_like(line):
        return False
    if _tabular(line.text) and (line.bold_ratio >= 0.5 or line.max_gap > 1.5):
        return True
    lowercase = sum(bool(re.fullmatch(r"[a-z][a-z,.;:'’-]*", token)) for token in tokens)
    return line.max_gap > 2.5 and lowercase < 0.5 * len(tokens)


def _table_row(line: Line) -> bool:
    if _numbered_heading_like(line):
        return False
    tokens = line.text.split()
    numbers = [token for token in tokens if re.search(r"\d", token) and not re.search(r"[^\W\d_]{3,}", token)]
    words = [token for token in tokens if re.search(r"[^\W\d_]{3,}", token)]
    return len(tokens) >= 3 and len(numbers) >= 2 and (len(numbers) >= 0.5 * len(tokens) or len(words) < 0.4 * len(tokens))


def _table_lines(lines: list[Line], pitch: float) -> set[int]:
    marked: set[int] = set()
    for indexes in _by_column(lines).values():
        rows = [position for position, index in enumerate(indexes) if _table_row(lines[index])]
        seeds = {
            indexes[position]
            for position in rows
            if any(other != position and abs(other - position) <= 2 for other in rows)
        }
        grown = set(seeds)
        changed = True
        while changed:
            changed = False
            for position, index in enumerate(indexes):
                if index in grown:
                    continue
                line = lines[index]
                if _CAPTION.match(line.text) or _ends_sentence(line.text) or len(line.text.split()) > 10:
                    continue
                if line.bold_ratio >= 0.5 and line.max_gap <= 1.5 and not _tabular(line.text):
                    continue
                neighbours = [indexes[other] for other in (position - 1, position + 1) if 0 <= other < len(indexes)]
                if any(other in grown and abs(lines[other].top - line.top) <= 2.2 * pitch for other in neighbours):
                    grown.add(index)
                    changed = True
        marked |= grown
    return marked


def _footnote_lines(lines: list[Line], body_size: float) -> set[int]:
    marked: set[int] = set()
    for indexes in _by_column(lines).values():
        body = [position for position, index in enumerate(indexes) if abs(lines[index].size - body_size) <= 0.5]
        if not body:
            continue
        for index in indexes[max(body) + 1:]:
            line = lines[index]
            if _CAPTION.match(line.text):
                break
            if line.size <= body_size - 1:
                marked.add(index)
    return marked


def _near_table(line: Line, tables: dict[int, list[Line]], pitch: float) -> bool:
    for table in tables.get(line.page, ()):
        if table.x1 < line.x0 or table.x0 > line.x1:
            continue
        distance = table.top - line.top
        if 0 < distance <= 3 * pitch or -1.5 * pitch <= distance <= 0:
            return True
    return False


def _fragment(text: str) -> bool:
    """Under three words, or a short piece that neither starts nor ends a sentence properly."""
    words = text.split()
    if len(words) < 3:
        return True
    return len(text) < 40 and not _LIST.match(text) and not (text[:1].isupper() and _ends_sentence(text))


def _prose(text: str) -> bool:
    words = text.split()
    return (
        len(words) >= 20
        and "@" not in text
        and text.rstrip(")\"'”’").endswith((".", "?", "!"))
        and sum(word[:1].islower() for word in words) >= 0.4 * len(words)
    )


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
            if not any(name in section["title"].lower() for name in _CONTRIBUTION_SECTIONS):
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


def _outline(pdf: Any) -> list[dict[str, Any]]:
    """Read outline entries as level, title, page number, and destination top."""
    try:
        from pdfminer.pdftypes import resolve1
        from pdfminer.psparser import PSLiteral

        document = pdf.doc
        pages = {page.page_obj.pageid: number for number, page in enumerate(pdf.pages, 1)}
        heights = {number: float(page.height) for number, page in enumerate(pdf.pages, 1)}
        entries = []
        for level, title, dest, action, _ in document.get_outlines():
            target = dest
            if target is None and action is not None:
                resolved = resolve1(action)
                target = resolved.get("D") if isinstance(resolved, dict) else None
            target = resolve1(target)
            if isinstance(target, (bytes, str, PSLiteral)):
                name = target.name if isinstance(target, PSLiteral) else target
                try:
                    target = resolve1(document.get_dest(name))
                except Exception:
                    target = None
            if isinstance(target, dict):
                target = resolve1(target.get("D"))
            page = top = None
            if isinstance(target, list) and target:
                page = pages.get(getattr(target[0], "objid", None))
                kind = getattr(resolve1(target[1]), "name", None) if len(target) > 1 else None
                value = None
                if kind == "XYZ" and len(target) > 3:
                    value = resolve1(target[3])
                elif kind in {"FitH", "FitBH"} and len(target) > 2:
                    value = resolve1(target[2])
                if page and isinstance(value, (int, float)):
                    top = heights[page] - float(value)
            if isinstance(title, bytes):
                title = title.decode("utf-8", "replace")
            if isinstance(title, str) and title.strip():
                entries.append({"level": int(level), "title": title.strip(), "page": page, "top": top})
        return entries
    except Exception:  # no outline, or one pdfminer cannot resolve
        return []


def extract_lines(pdf: Path) -> tuple[list[Line], dict[int, float], dict[str, Any]]:
    """Read every page into ordered lines; report body size, outline, and dropped counts."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ProjectError("PDF parsing needs pdfplumber: python -m pip install pdfplumber") from exc
    if not pdf.is_file():
        raise ProjectError(f"PDF does not exist: {pdf}")
    heights: dict[int, float] = {}
    pages: list[tuple[int, float, list[dict[str, Any]], list[tuple[float, float, float, float]]]] = []
    rotated = 0
    try:
        with pdfplumber.open(pdf) as document:
            outline = _outline(document)
            for number, page in enumerate(document.pages, 1):
                heights[number] = float(page.height)
                chars = []
                for char in page.chars:
                    if not char["text"].strip():
                        continue
                    if not char.get("upright", True):
                        rotated += 1
                        continue
                    if char["x0"] < 0 or char["top"] < 0 or char["x1"] > page.width or char["bottom"] > page.height:
                        continue
                    chars.append(char)
                tables = [table.bbox for table in page.find_tables()] if chars else []
                pages.append((number, float(page.width), chars, tables))
    except Exception as exc:  # pdfminer raises many unrelated types for a broken file
        raise ProjectError(f"cannot read text from PDF {pdf}: {exc}") from exc
    total = sum(len(chars) for _, _, chars, _ in pages)
    if total < 100:
        raise ProjectError(
            f"PDF has no usable text layer: {pdf}; a scanned PDF needs OCR before it can become a paper flow"
        )

    families = Counter(_family(char.get("fontname", "")) for _, _, chars, _ in pages for char in chars)
    text_families = [family for family, _ in families.most_common() if not _MATH_FAMILY.match(family)]
    body_family = text_families[0] if text_families else ""
    math_families = {family for family in families if _MATH_FAMILY.match(family) and family != body_family}
    minor_families = {
        family for family, count in families.items()
        if family not in math_families and family != body_family and count < 0.05 * total
    }
    sizes = Counter(
        round(char["size"] * 2) / 2
        for _, _, chars, _ in pages
        for char in chars
        if _family(char.get("fontname", "")) == body_family
    )
    body_size = sizes.most_common(1)[0][0] if sizes else 10.0

    page_words: list[tuple[int, float, list[dict[str, Any]]]] = []
    table_words = 0
    for number, width, chars, tables in pages:
        words = build_words(chars, body_size, math_families, minor_families)
        if tables:
            kept = [
                word for word in words
                if not any(x0 <= (word["x0"] + word["x1"]) / 2 <= x1 and top <= (word["top"] + word["bottom"]) / 2 <= bottom for x0, top, x1, bottom in tables)
            ]
            table_words += len(words) - len(kept)
            words = kept
        page_words.append((number, width, words))
    gutters = [gutter for number, width, words in page_words if (gutter := _gutter(words, width, body_size)) is not None]
    text_pages = sum(len(_body_words(words, body_size)) >= 30 for _, _, words in page_words)
    hint = median(gutters) if len(gutters) >= 2 and len(gutters) >= 0.3 * max(1, text_pages) else None
    lines: list[Line] = []
    for number, width, words in page_words:
        lines.extend(page_lines(words, number, width, body_size, hint))
    return lines, heights, {"body_size": body_size, "rotated_chars": rotated, "table_words": table_words, "outline": outline}


def _filter_lines(lines: list[Line], heights: dict[int, float], body_size: float, counts: Counter[str]) -> tuple[list[Line], list[Line]]:
    lines, counts["running_matter"] = drop_running_matter(lines, heights)
    body = [line for line in lines if abs(line.size - body_size) <= 0.5]
    if body:
        lefts = sorted(line.x0 for line in body)
        rights = sorted(line.x1 for line in body)
        left, right = lefts[len(lefts) // 20], rights[-(len(rights) // 20) - 1]
        kept = [line for line in lines if not (line.x1 < left - 0.5 * body_size or line.x0 > right + 0.5 * body_size)]
        counts["margin"] = len(lines) - len(kept)
        lines = kept
    kept = [
        line for line in lines
        if line.size >= 0.8 * body_size and not (line.chars and line.minor >= 0.6 * line.chars)
    ]
    counts["figure_text"] = len(lines) - len(kept)
    lines = kept
    pitch = _pitch(lines, body_size)
    tables = _table_lines(lines, pitch)
    tables |= {index for index, line in enumerate(lines) if _table_header(line, body_size)}
    counts["table"] = len(tables)
    removed = [line for index, line in enumerate(lines) if index in tables]
    lines = [line for index, line in enumerate(lines) if index not in tables]
    footnotes = _footnote_lines(lines, body_size)
    counts["footnote"] = len(footnotes)
    return [line for index, line in enumerate(lines) if index not in footnotes], removed


def _take_title(lines: list[Line], body_size: float, vocabulary: set[str] | None = None) -> tuple[list[Line], str]:
    first_page = [line for line in lines if line.page == 1 and len(line.text.split()) >= 2 and len(re.findall(r"[^\W\d_]", line.text)) >= 8]
    if not first_page:
        return lines, ""
    largest = max(line.size for line in first_page)
    if largest < body_size + 2:
        return lines, ""
    page_one = [line for line in lines if line.page == 1]
    start = next(index for index, line in enumerate(page_one) if line in first_page and abs(line.size - largest) <= 0.5)
    title = [page_one[start]]
    for line in page_one[start + 1:]:
        if not 0.75 * largest <= line.size <= largest + 0.5 or not 0 < line.top - title[-1].top <= 1.8 * largest:
            break
        title.append(line)
    skipped = set(map(id, title))
    return [line for line in lines if id(line) not in skipped], _join_lines(title, vocabulary)


def parse_pdf(
    pdf: Path,
    *,
    title: str,
    citekey: str,
    item_key: str,
    contributions: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a paper-flow spec of headings and semantic prose blocks from a PDF."""
    raw, heights, info = extract_lines(pdf)
    body_size = float(info["body_size"])
    counts: Counter[str] = Counter()
    lines, removed_tables = _filter_lines(raw, heights, body_size, counts)
    vocabulary = _vocabulary(lines)
    lines, pdf_title = _take_title(lines, body_size, vocabulary)
    pitch = _pitch(lines, body_size)
    tables: dict[int, list[Line]] = {}
    for line in removed_tables:
        tables.setdefault(line.page, []).append(line)

    outline_entries = info["outline"]
    outline_headings, outline_continuation, outline_unmatched = match_outline(outline_entries, lines)
    outline_used = bool(outline_headings) and len(outline_headings) >= 0.5 * (len(outline_headings) + len(outline_unmatched))
    if not outline_used:
        outline_headings, outline_continuation = {}, set()
    unmatched_keys = {_outline_key(title) for title in outline_unmatched} if outline_used else set()

    numbered_sections = any(
        (match := _SECTION.match(line.text.strip())) is not None
        and "." not in match.group(1)
        and match.group(2)[:1].isupper()
        and (line.bold_ratio >= 0.5 or line.size >= body_size + 0.5 or _capitals(line.text))
        for line in lines
    )
    tiers = sorted(
        {
            round(line.size * 2) / 2
            for line in lines
            if line.size >= body_size + 1.5
            and not _SECTION.match(line.text.strip())
            and not line.text.strip().endswith((".", ",", ";", ":"))
            and _WORD.search(line.text)
            and len(line.text.split()) <= 12
        },
        reverse=True,
    )
    geometry = _geometry(lines, body_size)

    sections: list[dict[str, Any]] = []
    preamble: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    block: list[Line] = []
    skipping = False
    appendix = False
    numbered_depth = 0
    section_size: float | None = None
    last_heading: tuple[dict[str, Any], str, Line] | None = None

    def flush() -> None:
        nonlocal block
        if block and not skipping:
            text = _join_lines(block, vocabulary)
            if text:
                (preamble if current is None else current["blocks"]).append({
                    "kind": "caption" if _CAPTION.match(text) else "paragraph",
                    "page": block[0].page,
                    "text": text,
                })
        block = []

    for index, line in enumerate(lines):
        if index in outline_continuation:
            continue
        if index in outline_headings:
            depth, text = outline_headings[index]
            heading: tuple[int, str, str] | None = (depth, text, "outline")
        else:
            if last_heading is not None:
                owner, field, heading_line = last_heading
                if (
                    not block
                    and abs(line.size - heading_line.size) <= 0.3
                    and (line.bold_ratio >= 0.5) == (heading_line.bold_ratio >= 0.5)
                    and (line.page, line.column) == (heading_line.page, heading_line.column)
                    and 0 < line.top - heading_line.top <= 1.6 * line.size
                    and not _SECTION.match(line.text.strip())
                    and line.text.strip().rstrip(".:").lower() not in _TOP_LEVEL_NAMES
                    and (line.bold_ratio >= 0.5 or line.size >= body_size + 1.5)
                    and line.max_gap <= 1.5
                ):
                    owner[field] = _join_text(owner[field], line.text.strip(), vocabulary)
                    last_heading = (owner, field, line)
                    continue
            opens_appendix = (
                not appendix
                and section_size is not None
                and line.size >= section_size - 0.5
                and re.match(r"^A\.?\s+[A-Z]", line.text.strip()) is not None
            )
            heading = _heading(line, body_size, tiers, numbered_sections, appendix or opens_appendix)
            if heading and opens_appendix:
                if heading[2] == "numbered" and heading[0] == 0:
                    appendix = True
                elif heading[2] == "numbered":
                    heading = _heading(line, body_size, tiers, numbered_sections, False)
            if heading and heading[2] != "named" and _near_table(line, tables, pitch):
                heading = None
            if heading and outline_used:
                if heading[2] == "numbered" and _outline_key(line.text) in unmatched_keys:
                    pass
                elif heading[2] == "bold":
                    heading = (numbered_depth + 1, heading[1], "bold")
                elif heading[2] != "named":
                    heading = None
        if heading and current is None and not (heading[0] == 0 and heading[2] in {"named", "numbered", "outline"}):
            heading = None
        if heading:
            flush()
            depth, text, how = heading
            source = "outline" if how == "outline" else "font"
            if how in {"numbered", "outline"}:
                numbered_depth = depth
                if depth == 0:
                    section_size = line.size
            elif how in {"tier", "bold"} and numbered_sections and depth > 0 and not outline_used:
                depth = max(depth, numbered_depth + 1)
            if current is None:
                if text.lower() != "abstract":
                    abstract: list[dict[str, Any]] = []
                    for entry in reversed(preamble):
                        if entry["kind"] != "paragraph" or not _prose(entry["text"]):
                            break
                        abstract.insert(0, entry)
                    if abstract:
                        sections.append({"title": "Abstract", "source": "font", "blocks": abstract})
                    counts["author_block"] = len(preamble) - len(abstract)
                else:
                    counts["author_block"] = len(preamble)
            if depth == 0 or current is None:
                skipping = text.lower() in _REFERENCE_NAMES
                appendix = appendix or skipping or text.lower().startswith("appendi")
                current = {"title": text, "source": source, "blocks": []}
                numbered_depth = 0
                if not skipping:
                    sections.append(current)
                last_heading = None if how == "outline" else (current, "title", line)
            elif not skipping:
                entry = {"kind": "heading", "level": depth, "page": line.page, "text": text, "source": source}
                current["blocks"].append(entry)
                last_heading = None if how == "outline" else (entry, "text", line)
            continue
        last_heading = None
        if skipping:
            continue
        if line.chars and line.math >= 0.4 * line.chars:
            previous = block[-1] if block else None
            left, _ = geometry[(line.page, line.column)]
            if (
                previous is None
                or _ends_sentence(previous.text)
                or line.x0 - left >= 2 * body_size
                or ((previous.page, previous.column) == (line.page, line.column) and line.top - previous.top > 1.4 * pitch)
            ):
                counts["equation"] += 1
                continue
        if block and _starts_block(block[-1], line, geometry, body_size, pitch):
            flush()
        block.append(line)
    flush()

    for section in sections:
        kept: list[dict[str, Any]] = []
        prefix: str | None = None
        blocks_in_section = section["blocks"]
        for position, entry in enumerate(blocks_in_section):
            if prefix is not None:
                entry["text"] = _join_text(prefix, entry["text"], vocabulary)
                prefix = None
            text = entry["text"]
            if entry["kind"] == "paragraph" and _fragment(text):
                previous = kept[-1] if kept else None
                following = blocks_in_section[position + 1] if position + 1 < len(blocks_in_section) else None
                if not _TWO_LETTERS.search(text):
                    counts["fragments_dropped"] += 1
                elif following is not None and following["kind"] == "paragraph" and following["text"][:1].islower() and not _ends_sentence(text):
                    prefix = text
                    counts["fragments_merged"] += 1
                elif previous is not None and previous["kind"] == "paragraph" and (text[:1].islower() or not _ends_sentence(previous["text"])):
                    previous["text"] = _join_text(previous["text"], text, vocabulary)
                    counts["fragments_merged"] += 1
                else:
                    counts["fragments_dropped"] += 1
                continue
            kept.append(entry)
        section["blocks"] = kept

    sections = [section for section in sections if section["blocks"]]
    if not sections:
        raise ProjectError(
            f"no headings with body text were found in {pdf}; the PDF may lack font size or weight "
            "differences, or put its text in an order this reader cannot follow"
        )
    counter = 0
    sources: Counter[str] = Counter()
    for number, section in enumerate(sections, 1):
        ordered: dict[str, Any] = {"key": f"s{number}", "title": section["title"], "source": section["source"], "blocks": []}
        sources[section["source"]] += 1
        for entry in section["blocks"]:
            counter += 1
            ordered["blocks"].append({"key": f"b{counter}", **entry})
            if entry["kind"] == "heading":
                sources[entry["source"]] += 1
        section.clear()
        section.update(ordered)
    marked = mark_contributions(sections, contributions)
    spec = {"title": title, "citekey": citekey, "item_key": item_key, "sections": sections}
    blocks = [entry for section in sections for entry in section["blocks"]]
    prose = [entry for entry in blocks if entry["kind"] != "heading"]
    stats = {
        "pages": len(heights),
        "pdf_title": pdf_title,
        "body_size": body_size,
        "sections": len(sections),
        "headings": sum(entry["kind"] == "heading" for entry in blocks),
        "paragraphs": sum(entry["kind"] == "paragraph" for entry in blocks),
        "captions": sum(entry["kind"] == "caption" for entry in blocks),
        "short_blocks": sum(len(entry["text"]) < 40 for entry in prose),
        "dropped_lines": counts["running_matter"],
        "heading_sources": {"outline": sources["outline"], "font": sources["font"]},
        "outline": {
            "entries": len(outline_entries),
            "used": outline_used,
            "unmatched": outline_unmatched,
        },
        "filtered": {
            "rotated_chars": info["rotated_chars"],
            "table_words": info["table_words"],
            **{key: counts[key] for key in (
                "running_matter", "margin", "figure_text", "table", "footnote", "equation",
                "author_block", "fragments_merged", "fragments_dropped",
            )},
        },
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
