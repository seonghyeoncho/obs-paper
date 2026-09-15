#!/usr/bin/env python3
"""Run the PDF reader on two arXiv papers and print what it found.

Not part of unittest discovery, and the PDFs are not in the repository. Download
https://arxiv.org/pdf/1706.03762 and https://arxiv.org/pdf/1810.04805 into one
directory and run:

    python tests/manual_real_pdfs.py /path/to/pdfs

It needs pdfplumber and prints each paper's stats, every heading with its depth,
and a PASS or FAIL line per acceptance check. The exit status is nonzero when a
check fails.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/obspaper/scripts"))

from pdf_to_flow import parse_pdf  # noqa: E402

PAPERS = {
    "1706.03762.pdf": {
        "title": "Attention Is All You Need",
        "phrase": "The Transformer uses multi-head attention in three different ways",
        "abstract_contribution": False,
        "headings": [
            (0, "Introduction"), (0, "Background"), (0, "Model Architecture"),
            (1, "Encoder and Decoder Stacks"), (1, "Attention"), (2, "Scaled Dot-Product Attention"),
            (2, "Multi-Head Attention"), (2, "Applications of Attention in our Model"),
            (1, "Position-wise Feed-Forward Networks"), (1, "Embeddings and Softmax"), (1, "Positional Encoding"),
            (0, "Why Self-Attention"), (0, "Training"), (1, "Training Data and Batching"),
            (1, "Hardware and Schedule"), (1, "Optimizer"), (1, "Regularization"),
            (0, "Results"), (1, "Machine Translation"), (1, "Model Variations"),
            (1, "English Constituency Parsing"), (0, "Conclusion"),
        ],
    },
    "1810.04805.pdf": {
        "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "phrase": "We introduce a new language representation model called BERT",
        "abstract_contribution": True,
        "headings": [
            (0, "Introduction"), (0, "Related Work"), (1, "Unsupervised Feature-based Approaches"),
            (1, "Unsupervised Fine-tuning Approaches"), (1, "Transfer Learning from Supervised Data"),
            (0, "BERT"), (1, "Pre-training BERT"), (1, "Fine-tuning BERT"),
            (0, "Experiments"), (1, "GLUE"), (1, "SQuAD v1.1"), (1, "SQuAD v2.0"), (1, "SWAG"),
            (0, "Ablation Studies"), (1, "Effect of Pre-training Tasks"), (1, "Effect of Model Size"),
            (1, "Feature-based Approach with BERT"), (0, "Conclusion"),
        ],
    },
}
FORBIDDEN = ("7v26730", "9102", "3202")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def check(directory: Path, name: str, expected: dict) -> bool:
    spec, stats = parse_pdf(directory / name, title=expected["title"], citekey="k", item_key="ITEM")
    found = []
    for section in spec["sections"]:
        found.append((0, section["title"]))
        found.extend((block["level"], block["text"]) for block in section["blocks"] if block["kind"] == "heading")
    blocks = [block for section in spec["sections"] for block in section["blocks"]]
    prose = [block for block in blocks if block["kind"] != "heading"]
    text = "\n".join(block["text"] for block in blocks)

    print(f"== {name}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("headings:")
    for depth, heading in found:
        print(f"  {'  ' * depth}[{depth}] {heading}")

    wanted = {(_norm(title), depth) for depth, title in expected["headings"]}
    have = {(_norm(title), depth) for depth, title in found}
    matched = wanted & have
    missing = [f"[{depth}] {title}" for depth, title in expected["headings"] if (_norm(title), depth) not in have]
    abstract = next((section for section in spec["sections"] if section["title"].lower() == "abstract"), None)
    short = sum(len(block["text"]) < 40 for block in prose)
    results = {
        f"title ({stats['pdf_title']!r})": _norm(stats["pdf_title"]) == _norm(expected["title"]),
        f"headings {len(matched)}/{len(wanted)} with depth; missing {missing}": len(matched) >= 0.9 * len(wanted),
        "no arXiv stamp text": not any(token in text for token in FORBIDDEN),
        f"short prose blocks {short}/{len(prose)} under 5%": short < 0.05 * max(1, len(prose)),
        f"spaced words ({expected['phrase'][:40]}...)": expected["phrase"] in text,
    }
    if expected["abstract_contribution"]:
        results["abstract marked as contribution"] = bool(abstract) and any(
            block.get("role") == "contribution" for block in abstract["blocks"]
        )
    for label, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'} {label}")
    if short:
        print("short prose blocks:", [block["text"] for block in prose if len(block["text"]) < 40])
    return all(results.values())


def main() -> None:
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    ok = all([check(directory, name, expected) for name, expected in PAPERS.items()])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
