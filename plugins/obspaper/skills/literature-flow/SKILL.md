---
name: literature-flow
description: Search literature for exact research-flow questions, save selected papers through the project Zotero/PDF/BibTeX pipeline, and connect them back to the relevant RQ or bridge question. Automated PDF-to-flow conversion is currently suspended.
---

# Literature Flow

Use this skill with `project-library` and `research-flow`. A literature search starts from one exact RQ or bridge-question node, not from the manuscript or a detached project-wide reading list.

## Required pipeline

1. Resolve and inspect the project research Canvas. Choose the narrowest target RQ or bridge-question and record its node ID.
2. Form a query for that question. Record the provider, query, target Canvas/node ID, candidates, selected items, and rejection reasons in `searches.jsonl`.
3. Verify metadata and lawful full-text access. Add each selected item to the project Zotero Collection, import its PDF as a Zotero stored-file attachment, verify the stored file, and export that Collection to `references.bib`. Do not retain a PDF in the Obsidian vault.
4. Automated PDF-to-flow conversion is suspended. Do not invoke or propose a PDF parser. Preserve the Zotero PDF and continue with literature mapping and citation work only.
5. A future replacement workflow may create `<Vault>/Paper/<full paper title>.canvas`, but it must use semantic prose blocks rather than sentence splitting and inherit only the `paper` color grammar: purple structural headings, green contribution cards, and no color on ordinary content. Do not use the manuscript paper skill's one-sentence card rule for PDF flows.
6. Add one uncoloured literature card beside the target question with `link_literature`. Include the title, exact citation key, Zotero link, and one sentence explaining relevance. Include `paper_flow` only when a Canvas already exists. Point the edge to that question.
7. Validate the research Canvas and audit citation keys. Replanning the same request must produce zero operations.

Never pool related literature at the bottom of the research flow. When one paper supports multiple questions, reuse its Zotero item, stored PDF, and BibTeX key but create one target-specific literature card per question. Reuse a vault-level paper Canvas only when one exists. When writing the manuscript, promote only the papers selected for an exact sentence and use the `paper` citation-card rule.
