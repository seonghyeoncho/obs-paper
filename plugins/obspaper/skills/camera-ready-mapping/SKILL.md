---
name: camera-ready-mapping
description: "Map rebuttal promises, reviewer requests, verified results, and additional camera-ready fixes onto an unchanged manuscript inside an Obsidian Canvas group such as paper_v2. Use for planning and traceability before writing the final camera-ready group; do not rewrite manuscript prose in this stage."
---

# Camera-Ready Mapping

Use an existing manuscript version such as `paper_v2` as a read-only target. This stage shows, in plain language, what each reviewer asked, what will change, and where. Actual rewriting belongs in `paper_camera_ready`.

## Deterministic automation

- Read `../../references/request-schema.md` before authoring a request.
- Use `../../scripts/obs_paper.py` with workflow `camera-ready-mapping`.
- Use `mapping_master` for the unconnected far-left inventory and `map_issue` for each orange reviewer/author-audit cluster and its one exact target edge.
- Use `remove_items` only with the full explicit node list and every incident edge ID, normally when migrating a legacy mapping. The handler rejects an incomplete incident-edge list.
- Run `plan`, inspect the patch, `apply` with the adjacent action log, `validate`, and then rerun `plan` to confirm zero operations.

## Human-readable issue model

- Never invent visible identifiers such as `CR-1`, `CR-10`, or arbitrary issue numbers.
- Use the reviewer's real label when available, such as `R1 · W7` or `R3 · C2`, followed by a short topic. Preserve the original reviewer wording inside the card. Use `Author audit · <topic>` for fixes not requested by a reviewer.
- Keep one unconnected master list at the far left, grouped by reviewer. Each line shows the real reviewer label, short topic, and current status. It is an inventory, not an arrow source.
- Split every reviewer request into the narrowest independently verifiable unit that applies to exactly one sentence, paragraph heading, section title, equation, table, figure, or caption. If the same request touches several targets, repeat its real reviewer label in one issue cluster per target.
- Create one orange title node and five orange detail nodes in this fixed vertical order:

```text
# R3 · W3 · Human audit reliability
Asked: <reviewer request or faithful short quote>
Evidence: <verified result/source, pending fact, or none>
Status: wording | ready | pending | author input | blocked
Done when: <observable completion condition>
Change: <exact manuscript intervention>
```

- Use one width for all six nodes, default 560px. Fit each height to its text. Leave 20px between the title and Asked, then 10px between detail nodes.
- Draw exactly one arrow from the title node to the issue's manuscript target. Detail nodes have no arrows; spatial stacking identifies them as the title's details.

- If several reviewer comments require exactly the same intervention, one card may list all real reviewer labels. Keep every request separately visible in the master list and in the card's `Asked` field.
- Keep evidence inside the mapping card unless it is a full table, figure, or other artifact worth viewing directly. A separate evidence artifact points into the mapping card; the mapping card points to the manuscript target.
- Reserve red for the user's own objections and thoughts. Reviewer mapping cards are orange; verified external evidence artifacts may be green; blockers use the established warning color.

## Mapping to the paper

- Preserve all manuscript node text, formatting, size, color, and internal relations.
- Draw `mapping title -> exact manuscript target`. Target the narrowest sentence, equation, table, figure, caption, or heading. Point to a section title only for a genuinely section-wide change or a missing source element.
- Follow the `paper` skill's paired-section structure. Appendix targets live in the right column of their owning main section, not in a separate Appendix group.
- Keep each six-node issue cluster inside the target's top-level section and close to that target, outside both prose stacks and their artifact lanes. Prefer the nearest free side and a short arrow; do not create section-crossing annotation corridors.
- Inspect both the main and Appendix columns before choosing a target. Map a promised Appendix table, figure, prompt, schema, model note, or sensitivity result directly to that Appendix node.
- Distinguish verified evidence from proposed work. Missing experiments, ethics facts, release artifacts, citations, or author decisions remain explicitly pending or blocked.

## Boundary and validation

Do not rewrite manuscript prose, replace artifacts, resolve citations, or create the final group during mapping. Stable Canvas node IDs provide machine traceability; visible arbitrary IDs are unnecessary.

Before writing, make one timestamped backup and enforce a SHA-256 precondition. Verify unique IDs, valid endpoints, no arrows from the master list or detail nodes, no manuscript-text changes, every master-list item represented by a six-node issue cluster, every title connected to exactly one narrow target, Appendix targets placed in their owning section, no overlaps, and deterministic rerun no-op behavior.

Log inventory sources, mapping cards, statuses, target links, layout changes, and blockers in `CANVAS_ACTION_LOG.md`.
