#!/usr/bin/env python3
"""Run the PDF reader on a development set of arXiv papers and print what it found.

Not part of unittest discovery, and the PDFs are not in the repository. Put the
papers below into one or more directories (any subset works; missing ones are
skipped) and run:

    python tests/manual_real_pdfs.py /path/to/pdfs [/another/dir ...]

  1706.03762  Attention Is All You Need (NeurIPS, single column, has an outline)
  1810.04805  BERT (NAACL two-column, no outline)
  1907.11692  RoBERTa (ACL two-column, no outline)
  2106.09685  LoRA (ICLR single column, capitalised headings, has an outline)
  1512.03385  ResNet (CVPR two-column, no outline)

The expected titles and section lists were written by reading each PDF's text
and outline, not the reader's output. Only top-level and second-level headings
are checked. The script prints the stats, every heading with its depth and
source, and PASS or FAIL per check; the exit status is nonzero on a failure.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/obspaper/scripts"))

from pdf_to_flow import parse_pdf  # noqa: E402


def _tree(*items: object) -> list[tuple[int, str]]:
    """Section titles are depth 0; a nested list holds their depth-1 headings."""
    result: list[tuple[int, str]] = []
    for item in items:
        if isinstance(item, str):
            result.append((0, item))
        else:
            result.extend((1, title) for title in item)
    return result


PAPERS = {
    "1706.03762.pdf": {
        "title": "Attention Is All You Need",
        "headings": _tree(
            "Introduction", "Background", "Model Architecture",
            ["Encoder and Decoder Stacks", "Attention", "Position-wise Feed-Forward Networks", "Embeddings and Softmax", "Positional Encoding"],
            "Why Self-Attention", "Training",
            ["Training Data and Batching", "Hardware and Schedule", "Optimizer", "Regularization"],
            "Results", ["Machine Translation", "Model Variations", "English Constituency Parsing"],
            "Conclusion",
        ),
    },
    "1810.04805.pdf": {
        "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "headings": _tree(
            "Introduction", "Related Work",
            ["Unsupervised Feature-based Approaches", "Unsupervised Fine-tuning Approaches", "Transfer Learning from Supervised Data"],
            "BERT", ["Pre-training BERT", "Fine-tuning BERT"],
            "Experiments", ["GLUE", "SQuAD v1.1", "SQuAD v2.0", "SWAG"],
            "Ablation Studies", ["Effect of Pre-training Tasks", "Effect of Model Size", "Feature-based Approach with BERT"],
            "Conclusion",
            "Additional Details for BERT",
            ["Illustration of the Pre-training Tasks", "Pre-training Procedure", "Fine-tuning Procedure",
             "Comparison of BERT, ELMo, and OpenAI GPT", "Illustrations of Fine-tuning on Different Tasks"],
            "Detailed Experimental Setup", ["Detailed Descriptions for the GLUE Benchmark Experiments."],
            "Additional Ablation Studies", ["Effect of Number of Training Steps", "Ablation for Different Masking Procedures"],
        ),
    },
    "1907.11692.pdf": {
        "title": "RoBERTa: A Robustly Optimized BERT Pretraining Approach",
        "headings": _tree(
            "Introduction", "Background",
            ["Setup", "Architecture", "Training Objectives", "Optimization", "Data"],
            "Experimental Setup", ["Implementation", "Data", "Evaluation"],
            "Training Procedure Analysis",
            ["Static vs. Dynamic Masking", "Model Input Format and Next Sentence Prediction", "Training with large batches", "Text Encoding"],
            "RoBERTa", ["GLUE Results", "SQuAD Results", "RACE Results"],
            "Related Work", "Conclusion",
            "Full results on GLUE", "Pretraining Hyperparameters", "Finetuning Hyperparameters",
        ),
    },
    "2106.09685.pdf": {
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "headings": _tree(
            "Introduction", "Problem Statement", "Aren't Existing Solutions Good Enough?",
            "Our Method", ["Low-Rank-Parametrized Update Matrices", "Applying LoRA to Transformer"],
            "Empirical Experiments", ["Baselines", "RoBERTa base/large", "DeBERTa XXL", "GPT-2 medium/large", "Scaling up to GPT-3 175B"],
            "Related Works",
            "Understanding the Low-Rank Updates",
            ["Which Weight Matrices in Transformer Should We Apply LoRA to?", "What is the Optimal Rank r for LoRA?",
             "How Does the Adaptation Matrix W Compare to W?"],
            "Conclusion and Future Work",
            "Large Language Models Still Need Parameter Updates", "Inference Latency Introduced by Adapter Layers",
            "Dataset Details", "Hyperparameters Used in Experiments", ["RoBERTa", "DeBERTa", "GPT-2", "GPT-3"],
            "Combining LoRA with Prefix Tuning", "Additional Empirical Experiments",
            ["Additional Experiments on GPT-2", "Additional Experiments on GPT-3", "Low-Data Regime"],
            "Measuring Similarity Between Subspaces", "Additional Experiments on Low-Rank Matrices",
            ["Correlation between LoRA Modules", "Effect of r on GPT-2", "Correlation between W and W", "Amplification Factor"],
        ),
    },
    "1512.03385.pdf": {
        "title": "Deep Residual Learning for Image Recognition",
        "headings": _tree(
            "Introduction", "Related Work", "Deep Residual Learning",
            ["Residual Learning", "Identity Mapping by Shortcuts", "Network Architectures", "Implementation"],
            "Experiments", ["ImageNet Classification", "CIFAR-10 and Analysis", "Object Detection on PASCAL and MS COCO"],
            "Object Detection Baselines", "Object Detection Improvements", "ImageNet Localization",
        ),
    },
}
FORBIDDEN = ("7v26730", "9102", "3202")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _table_like(text: str) -> bool:
    """Independent of the reader: three or more tokens, most of them codes or numbers."""
    tokens = text.split()
    codes = [
        token for token in tokens
        if re.search(r"\d", token) or re.fullmatch(r"[A-Z]{2,5}(-\w+)?", token) or re.search(r"[a-z][A-Z]", token)
    ]
    return len(tokens) >= 3 and len(codes) >= 0.6 * len(tokens)


def check(path: Path, expected: dict) -> bool:
    spec, stats = parse_pdf(path, title=expected["title"], citekey="k", item_key="ITEM")
    found = []
    for section in spec["sections"]:
        found.append((0, section["title"], section.get("source")))
        found.extend(
            (block["level"], block["text"], block.get("source"))
            for block in section["blocks"] if block["kind"] == "heading"
        )
    blocks = [block for section in spec["sections"] for block in section["blocks"]]
    prose = [block for block in blocks if block["kind"] != "heading"]
    text = "\n".join(block["text"] for block in blocks)

    print(f"== {path.name}")
    print(json.dumps({key: value for key, value in stats.items() if key != "contributions"}, ensure_ascii=False))
    print("contributions:", stats["contributions"])
    print("headings:")
    for depth, heading, source in found:
        print(f"  {'  ' * depth}[{depth}] {heading}  ({source})")

    wanted = [(_norm(title), depth) for depth, title in expected["headings"]]
    have = Counter_like([(_norm(title), depth) for depth, title, _ in found])
    matched = 0
    for key in wanted:
        if have.get(key, 0):
            have[key] -= 1
            matched += 1
    missing = [f"[{depth}] {title}" for depth, title in expected["headings"] if (_norm(title), depth) not in {(_norm(t), d) for d, t, _ in found}]
    abstract = next((section for section in spec["sections"] if section["title"].lower() == "abstract"), None)
    short = [block["text"] for block in prose if len(block["text"]) < 40]
    glued = sorted({word for word in re.findall(r"[A-Za-z]{25,}", text) if not word.lower().startswith("http")})
    tabular = [heading for _, heading, _ in found if _table_like(heading)]
    results = {
        f"title ({stats['pdf_title']!r})": _norm(stats["pdf_title"]) == _norm(expected["title"]),
        f"headings {matched}/{len(wanted)} at depth 0-1; missing {missing}": matched >= 0.9 * len(wanted),
        f"no table-header headings {tabular}": not tabular,
        "no arXiv stamp text": not any(token in text for token in FORBIDDEN),
        f"short prose blocks {len(short)}/{len(prose)} under 5%": len(short) < 0.05 * max(1, len(prose)),
        f"no glued words {glued[:5]}": not glued,
        "abstract marked as contribution": bool(abstract) and any(block.get("role") == "contribution" for block in abstract["blocks"]),
    }
    for label, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'} {label}")
    if short:
        print("short prose blocks:", short)
    return all(results.values())


def Counter_like(items: list[tuple[str, int]]) -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def main() -> None:
    directories = [Path(value) for value in sys.argv[1:]] or [Path(".")]
    ok = True
    ran = 0
    for name, expected in PAPERS.items():
        path = next((directory / name for directory in directories if (directory / name).is_file()), None)
        if path is None:
            print(f"== {name}: not found, skipped")
            continue
        ran += 1
        ok = check(path, expected) and ok
    raise SystemExit(0 if ok and ran else 1)


if __name__ == "__main__":
    main()
