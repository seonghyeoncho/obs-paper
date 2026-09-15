---
name: literature-flow
description: Search literature for exact research-flow questions, save selected papers through the project Zotero/PDF/BibTeX pipeline, and connect them back to the relevant RQ or bridge question. Optionally build a paragraph-level paper-flow Canvas from a stored PDF.
---

# Literature Flow

Use this skill with `project-library` and `research-flow`. A literature search starts from one exact RQ or bridge-question node, not from the manuscript or a detached project-wide reading list.

## Required pipeline

1. Resolve and inspect the project research Canvas. Choose the narrowest target RQ or bridge-question and record its node ID.
2. Form a query for that question. Record the provider, query, target Canvas/node ID, candidates, selected items, and rejection reasons in `searches.jsonl`.
3. Verify metadata and lawful full-text access. Add each selected item to the project Zotero Collection, import its PDF as a Zotero stored-file attachment, verify the stored file, and export that Collection to `references.bib`. Do not retain a PDF in the Obsidian vault.
4. When the paper will be read closely against the flow, build its paper flow on the machine running Zotero: `python ../../scripts/zotero_bridge.py paper-flow <project-folder> <item-key> --spec-output <flow.json>`. It creates `<Vault>/Paper/<full paper title>.canvas` with one card per paragraph, never one per sentence, and inherits only the `paper` colour grammar: purple headings, green contribution cards, no colour on ordinary content. Do not use the manuscript paper skill's one-sentence card rule for PDF flows.
5. Contribution cards are candidates marked by explicit phrasing in the Introduction ("we propose", "our contributions", and list items after them). Show the author the `contributions` keys from the result and let them decide. Rebuild with `--contributions <keys>` or `--no-contributions`, or edit `role` in the spec and run `obs_paper.py paper-flow-build --replace`. Never present the marks as the paper's contributions without that review.
6. Expect limits and report them rather than working around them: two-column pages with full-width figures, text inside figures, equations kept as plain text, and scanned PDFs without a text layer, which fail with an error. The block boundary rule is in [../../references/request-schema.md](../../references/request-schema.md). Skip the paper flow when it fails; literature mapping does not depend on it.
7. Add one uncoloured literature card beside the target question with `link_literature`. Include the title, exact citation key, Zotero link, and one sentence explaining relevance. When a paper flow exists, pass the result's `paper_flow` value (for example `Paper/<title>.canvas`) as `paper_flow`. Point the edge to that question.
8. Validate the research Canvas and audit citation keys. Replanning the same request must produce zero operations.

Never pool related literature at the bottom of the research flow. When one paper supports multiple questions, reuse its Zotero item, stored PDF, and BibTeX key but create one target-specific literature card per question. Reuse a vault-level paper Canvas only when one exists. When writing the manuscript, promote only the papers selected for an exact sentence and use the `paper` citation-card rule.
