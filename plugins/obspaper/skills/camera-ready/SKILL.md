---
name: camera-ready
description: "Create or update the final camera-ready manuscript group in an Obsidian Canvas by applying a completed camera-ready mapping to a source paper version. Use when the user is ready to produce paper_camera_ready; do not use for mapping-only planning or rebuttal drafting."
---

# Camera Ready

Create `paper_camera_ready` from the mapped source version. The final group contains the manuscript only; mapping cards remain in the planning group.

## Deterministic automation

- Read `../../references/request-schema.md` before authoring a request.
- Use `../../scripts/obs_paper.py` with workflow `camera-ready` and action `build_camera_ready`.
- Supply the exact manuscript node, section-group, and internal-edge IDs; exclude the master list and mapping cards explicitly.
- Supply `changes`, `additions`, and `blockers` as separate lists. The handler colors changes, additions, and blocker cards yellow.
- When `paper_camera_ready` already exists, pass its `group_id`. The handler preserves that outer ID, removes stale contained content and incident edges, and reconciles deterministic clones instead of creating a duplicate group.
- Run `plan`, inspect the patch, `apply` with the adjacent action log, `validate`, and rerun `plan` to confirm zero operations.

## Build and apply

- Copy manuscript headings, prose, citations, equations, tables, figures, Appendix content, and internal reference edges. Do not copy the master list, mapping cards, evidence-only cards, or mapping edges.
- Use the `paper` skill's section-paired layout: main text in the left column, its supporting Appendix in the right column, and tables/figures in outside artifact lanes. Do not create `paper_camera_ready appendix` or any separate Appendix group.
- Process every mapping card by its Canvas node ID and visible reviewer label/topic. Do not introduce `CR-*` identifiers.
- Apply every `ready` or `wording` intervention at its exact target. A promised result is complete only when its actual prose, values, table, figure, caption, or definition appears in the final group.
- Color every replaced or newly added manuscript node yellow (`"3"`). Preserve unchanged colors. Yellow marks a camera-ready diff, not uncertainty.
- Keep reviewer wording, strategy notes, mapping fields, and issue labels out of publication prose.
- Reuse verified evidence sources. Never replace a promised table or figure with selected numbers or a placeholder.

## Blocked items

- Never invent experiments, release dates, citations, ethics facts, privacy decisions, or artifact availability.
- For an unresolved item, preserve the safest source wording and add one yellow side card titled `# Author input required · <topic>` beside the exact target. Include the real reviewer label when one exists.
- A blocked item is not completed and must remain listed in validation output.

## Validation

Before writing, make one timestamped backup and enforce a SHA-256 precondition. Use deterministic IDs so reruns are idempotent.

Verify unique IDs, valid endpoints, exactly one `paper_camera_ready` outer group, no separate Appendix group, no mapping-only nodes, every completed mapping card represented by at least one yellow target node, every blocker represented by one yellow author-input card, `$$...$$` display equations, fitted prose and table sizes, outside artifact lanes, section-paired Appendix columns, non-overlapping section rectangles, and deterministic rerun no-op behavior.

Log final-group creation, applied reviewer topics, blockers, layout corrections, and validation results in `CANVAS_ACTION_LOG.md`.
