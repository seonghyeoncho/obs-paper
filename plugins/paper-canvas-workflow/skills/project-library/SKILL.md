---
name: project-library
description: Initialize or import an academic project in a unified Obsidian vault and connect its local paper library to Zotero for search, PDF storage, citation keys, and Canvas citation cards. Use for project setup, migration, paper collection, or Zotero integration; do not use for manuscript prose layout alone.
---

# Project Library

Use one Obsidian vault with one folder per project:

```text
<Vault>/Projects/<Project>/
├── <Project>.canvas
├── project.md
├── CANVAS_ACTION_LOG.md
├── assets/
├── papers/
├── references.bib
└── searches.jsonl
```

The research repository remains separate. `project.md` records its absolute path so the active project can be resolved without scanning unrelated Canvas files.

## Storage access preflight

Before initializing, resolving, or migrating a project, check whether the supplied vault path and every required source file are directly readable and writable from the current environment. Do not assume that a path shown by a cloud-backed file browser is available through the filesystem.

- If direct access works, use the deterministic file commands in this skill.
- If direct access does not work, ask the user to approve access to the exact cloud folder or filesystem path required for the task. Resume only after that path is directly accessible.
- Do not silently copy or relocate the vault to a local folder as a workaround.
- Do not claim a file mutation succeeded unless the changed state can be verified through the same available access route.
- Treat a still-inaccessible path as a blocker rather than substituting UI automation or changing scope.

## Choose one project mode

Choose the mode before changing files:

- **New project:** no existing project Canvas, paper folder, bibliography, or project-specific Zotero Collection. Read [references/new-project.md](references/new-project.md) and follow it.
- **Migration:** any existing Canvas, project folder, PDFs, bibliography, search log, or project-specific Zotero Collection must be preserved. Read [references/migrate-project.md](references/migrate-project.md) and follow it.

Do not mix the two workflows. In particular, do not treat migration as an empty initialization followed by ad-hoc copying.

## Literature source of truth

Create one top-level Zotero Collection with the exact project name. That Collection is the project's literature source of truth: every selected search result must be added to it, and `references.bib` must be exported from that Collection only. Never export the full Zotero library into a project.

For every literature search, append one JSON object to `searches.jsonl` with `provider`, `query`, and the available filters, results, selected items, and rejection reasons. This applies regardless of whether the search used Zotero, a web search, or another scholarly provider.

The required order is:

1. Record the search.
2. Verify metadata and lawful PDF access.
3. Add the item to the project Zotero Collection and save its PDF under `papers/`.
4. Export that Collection to `references.bib`.
5. Audit manuscript citation keys against the exported bibliography.

The exporter refuses to replace `references.bib` when the candidate export would remove a citation key already used by the project. Better BibTeX remains preferred because stable citation keys reduce accidental key changes; the audit is still required.

## Zotero boundary

Zotero searches the user's Zotero library; it is not a scholarly web-search provider. For a new paper, search an authoritative literature source first, verify its metadata and accessible PDF, then pass those artifacts into this workflow.

Prefer Zotero's local API. Read operations need no account API key. Zotero 10+ write operations request a local key at runtime and the user approves it in Zotero; never store or log that key. Older Zotero releases remain read-only and require either an upgrade or a separately configured zotero.org write API key. Better BibTeX is optional but preferred for stable LaTeX citation keys. Without it, use Zotero's BibTeX export fallback.

Keep the project PDF under `papers/`. Zotero linked files are not the default because Zotero mobile clients do not support them reliably; the Zotero item supplies metadata and citations while Canvas links to the project copy.

## Zotero commands

Use `../../scripts/zotero_bridge.py`:

```bash
python ../../scripts/zotero_bridge.py status
python ../../scripts/zotero_bridge.py project-setup <project-folder>
python ../../scripts/zotero_bridge.py search "retrieval enabled agents"
python ../../scripts/zotero_bridge.py record-search <project-folder> <search-record.json>
python ../../scripts/zotero_bridge.py cite <item-key>
python ../../scripts/zotero_bridge.py save <project-folder> <item-key>
python ../../scripts/zotero_bridge.py add <project-folder> <metadata.json> <paper.pdf>
python ../../scripts/zotero_bridge.py save <project-folder> <item-key> --defer-export
python ../../scripts/zotero_bridge.py add <project-folder> <metadata.json> <paper.pdf> --defer-export
python ../../scripts/zotero_bridge.py export <project-folder>
python ../../scripts/zotero_bridge.py audit <project-folder> [manuscript.tex ...]
python ../../scripts/zotero_bridge.py canvas-link <canvas> --group-label paper_v1 --sentence-id <node-id> --item-key <item-key>
```

`project-setup` creates or reuses the exact-name Zotero Collection and records its key in `project.md`. `save` adds an existing Zotero item to that Collection, copies its PDF, and refreshes the bibliography. `add` stores a supplied PDF, creates its verified metadata item directly in the Collection, and refreshes the bibliography. `audit` exits nonzero when a manuscript citation is absent from `references.bib`. `canvas-link` expects the Zotero citation command already present in the sentence, replaces it with `{}`, and creates a grey side card containing the exact command and an `Open in Zotero` link.

Do not create a Zotero item from guessed metadata, bypass paywalls, or download a PDF without a verified lawful source. Record project, paper, and Canvas mutations in `CANVAS_ACTION_LOG.md` and report unavailable PDFs, missing metadata, denied Zotero authorization, and absent citation keys as blockers.
