---
name: research-flow
description: Build or update an academic research flow in an existing Obsidian Canvas with RQ, evidence, interpretation, bridge-question, source, table, and figure nodes. Use when reconstructing research reasoning, recording experiments, or organizing a paper's research flow. Do not use for manuscript sentence layout or prose revision alone.
---

# Research Flow

Treat the user's research notes and existing Obsidian Canvas as paired research artifacts. Preserve the user's spatial reasoning style; do not replace it with a new ontology or rebuild the Canvas from scratch.

## Deterministic automation

- Read `../../references/request-schema.md` before authoring a request.
- Read `../../references/sync-topology.md` before mutating a Canvas in the active Obsidian Sync vault. Sync does not make concurrent Canvas editing safe.
- Read `references/content-structure.md` before writing or revising node text: content reconstruction, node splitting, metadata separation, or Korean editing. Ordinary layout work does not need it.
- Use `../../scripts/obs_paper.py` with workflow `research-flow` and actions `add_research_flow`, `edit_text`, `link_literature`, or `remove_items` after inspecting the existing grammar. To change what a card says and nothing else -- a settled term, a polished sentence -- use `edit_text` with the node id; it keeps the kind, colour, and geometry that `add_research_flow` would make you restate, and handles the id stamp itself. Never edit the `.canvas` file by hand to make a card fit: a card past the group's right or bottom edge grows the group.
- Supply stable keyed nodes with exact geometry and explicit links. Use kinds `rq`, `experiment`, `answer`, `bridge`, `thought`, `source`, `table`, or `figure`.
- Give an experiment ordered `sections` for its setup/results/control compound. The handler creates green H2 cards without internal arrows and routes outgoing flow from the final section.
- Supply an actual `file` for a figure and the complete Markdown source for a table. The handler rejects figure placeholders.
- Run `plan`, inspect the patch, `apply` with the adjacent action log, `validate`, and rerun `plan` to confirm zero operations.

## Start every research-flow task

1. Resolve the active project from `<Vault>/Projects/*/project.md`, preferably by matching its `repository` field to the current repository. Use `obs_paper.py project-resolve` when the vault path is known. Fall back to a narrow `rg --files <project-folder> -g '*.canvas'` only for legacy projects; ask only when multiple candidates remain genuinely ambiguous.
2. Read the repository instructions, current manuscript, Canvas JSON, and adjacent `CANVAS_ACTION_LOG.md` before editing.
3. Validate that the Canvas parses and that node and edge IDs are unique and all edge endpoints exist.
4. Infer the Canvas's actual relationship grammar from node positions, colors, text, images, and explicit edges. Spatial adjacency may carry more meaning than arrows; never add edges mechanically.
5. When the Canvas is in the active Sync vault, confirm the current host has received the latest revision and no other host is editing that Canvas.
6. Append a `session-start` entry listing the artifacts inspected and the task objective.

## Preserve the existing flow

- Keep untouched node IDs, positions, sizes, colors, edges, and file references unchanged.
- Edit only cards required by the paper task. Add a card only when no existing card represents the idea.
- Place additions beside the claim, evidence, review, or section they extend, following the surrounding layout and color convention.
- Treat every RQ and bridge question as its own literature-search unit. Link each selected paper beside the narrowest question it answers; never pool project literature in a detached bottom cluster. Reuse one Zotero item, PDF, bibliography entry, and per-paper Canvas, but create a separate target-specific literature card when the same paper supports multiple questions.
- Separate measured facts from interpretation when adding research content. Every numerical claim records its denominator, pooling unit, cohort/configuration, and primary source. Every interpretation remains traceable to the relevant evidence card.
- Do not silently erase superseded reasoning. Keep a concise correction note and connect or position it with the corrected claim.
- The Canvas is never the publication source of truth. Where a project records an Overleaf project, that manuscript is the source; otherwise the repository-defined manuscript is. Canvas edits do not authorize unrelated manuscript rewrites, and manuscript edits do not authorize wholesale Canvas synchronization.

## Canvas grammar

- Never delete and recreate an existing native group just to change its layout; preserve its ID. A new paper starts with empty version/task groups rather than copied cards.
- Within a managed flow, use one width for ordinary text cards and fit each card's height to its rendered text. Tables and figures are exceptions: size each to its own rendered content. Keep cards as close as non-overlap permits, distribute branches laterally, and keep the main reading direction downward.
- Use one sentence per ordinary RQ, RQ-A, and bridge-question card. Render `RQ`, `RQ-E`, and `RQ-A` identifiers as H1 headings. Bridge-question cards contain only the question; their orange color carries the type instead of an explicit label.
- Treat each RQ-E as a compound: an H1 title card followed by one card per H2 section, which is `Setup` and then `Results`. Stack the section cards closely with no arrows between them. Normal flow enters the RQ-E title and leaves its final evidence section. There is no validity section; whether a run was usable belongs in that experiment's implementation card.
- Every managed card prints its own node ID as its last line, so a card can be addressed without searching. The engine appends it; keep it when rewriting a card and never let it drift from the node's actual ID.
- Put each primary source in a separate uncoloured/default-grey card outside the evidence stack, connected laterally to the setup card. Keep citations and provenance out of the setup prose when they can be separated cleanly.
- A related-literature card contains the verified title, exact citation key, Zotero item link, one-sentence relevance, and a wikilink to `Paper/<full paper title>.canvas`. Point its edge to the exact RQ or bridge-question. The paper Canvas links back to the research Canvas so Obsidian backlinks preserve the literature genealogy.
- Include the actual experiment method and results with denominators, pooling unit, controls, and configuration. Put every source Markdown table in its own card, preserving the complete table rather than reducing it to selected numbers or prose. Put every source figure in its own file/image card and display the artifact itself. If the canonical source lacks the raw table or figure, mark it unavailable in the grey source card; never reconstruct or invent it from a headline number.
- When one RQ has multiple RQ-E cards, top-align them on the same y-coordinate. Keep their corresponding RQ-A cards in the same horizontal lanes. For a parallel split/merge, preserve enough vertical space for curved arrows; infer it from the user's nearest edited example. In the current Skill Following Canvas, RQ2 defines 200px before the E row, 40px inside each E→A lane, and 166px before the merged next node.
- Use purple for RQ, green for RQ-E facts, yellow for RQ-A interpretations, and orange for bridge questions. Reserve red exclusively for the user's refutation or personal-thought cards; do not use red merely to mark an open RQ.
- Normal flow arrows leave the source bottom and enter the target top. Only red refutation/thought cards may originate an arrow from the left or right; that red card is the source and the questioned card is the target.

## Record every material action

Use `../../scripts/record_action.py` to append to `CANVAS_ACTION_LOG.md` beside the active Canvas.

Record each of these separately:

- session start and artifacts read;
- interpretation or source-of-truth decision;
- planned Canvas or manuscript mutation, before applying it;
- each card, edge, layout, figure-reference, or manuscript change;
- validation, render, build, or consistency check;
- correction, rollback, skipped change, permission issue, or blocker.

Each entry includes status, action, target, reason/source, and result. Use a Canvas node ID when available. Never rewrite earlier log entries; append a correction. Do not record secrets or full sensitive content in the log.

Before the first direct JSON mutation in a session, make one timestamped copy under `.canvas-history/` and log the backup. Do not create repeated backups when no Canvas mutation occurs.

Example:

```bash
python /path/to/plugin/scripts/record_action.py \
  'obs/Paper/CANVAS_ACTION_LOG.md' \
  --status planned \
  --action edit-card \
  --target 'node:abc123 / Abstract' \
  --reason 'Define aggregate retrieval lift at first mention' \
  --result 'Pending'
```

## Finish the task

Reparse the Canvas, rerun the ID/edge integrity checks, and verify every planned mutation has a matching `done`, `verified`, `skipped`, or `blocked` entry. For a Canvas in the active Sync vault, confirm the change has uploaded before transferring writer ownership to another host. Report the Canvas path, manuscript files changed, validation performed, and remaining blockers.
