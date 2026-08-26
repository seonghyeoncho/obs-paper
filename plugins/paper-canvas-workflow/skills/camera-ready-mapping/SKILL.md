---
name: camera-ready-mapping
description: "Map rebuttal promises, reviewer requests, verified results, and additional camera-ready fixes onto an unchanged manuscript inside an Obsidian Canvas group such as paper_v2. Use for planning and traceability before writing the final camera-ready group; do not rewrite manuscript prose in this stage."
---

# Camera-Ready Mapping

Use an existing manuscript copy such as `paper_v2` as a read-only target map. This stage identifies what must change and why; actual rewriting belongs in a separate final group such as `paper camera ready`.

## Mapping contract

- Preserve every manuscript card's text, formatting, size, color, and internal relation. Moving a complete section as one rigid body is allowed only to create annotation lanes.
- Preserve the original reviewer/promise IDs in a master checklist even when several items share one implementation change.
- Consolidate promises only when they require the same manuscript intervention. Never let consolidation hide an unresolved promise, result, or blocker.
- Distinguish verified results from proposed work. A result card may state only facts supported by an existing report, dataset, figure, table, source file, or explicit author decision.
- Record unavailable evidence, ethics decisions, release artifacts, or source-only targets as blockers rather than inventing an outcome.

## Canvas grammar

- Put one unconnected master checklist at the far left of the target group. It is an inventory only: do not draw arrows from it.
- Create one orange `Change/Add` card for each actionable bundle, using the same Canvas color as the established `CR-10` card. Include the preserved IDs, exact intended intervention, scope, and completion condition. Reserve red cards for the user's own critiques, objections, and thoughts; generated reviewer or mapping cards must not use red.
- Put a separate result/evidence card with the change. Use green for verified/ready evidence and a warning color for pending decisions, missing artifacts, or blockers.
- Draw `evidence/result → Change/Add → manuscript target` arrows. A change may point to several exact sentences, equations, tables, figures, captions, or section titles.
- Map to the narrowest existing target. Use a section title only when the change is genuinely section-wide or the required source element is absent from the Canvas.
- Inspect both the main text and the submission-time appendix before choosing targets. When the appendix exists, map appendix promises to its exact sentence, table, figure, prompt, schema, or model/source node instead of using a main-text proxy. Use an appendix title only for a genuinely section-wide addition or content that does not yet exist.
- Treat the version-specific Appendix as a nested group below the main manuscript and inside the outer mapped-paper group. Mapping arrows may cross the nested Appendix boundary to an exact target, but both their main-text annotations and Appendix targets remain within the same outer paper-version workspace.
- Keep mapping cards outside the manuscript rectangle. Prefer a fixed-width lane immediately left of the affected top-level section, short lateral arrows, 20px within-card-stack gaps, and 120px between lanes and manuscript sections.
- Preserve the manuscript section's bounding-title behavior. Mapping cards are annotations and do not enlarge the semantic width of its section title.

## Content to capture

For each bundle, retain the chain:

1. reviewer request or camera-ready promise;
2. exact manuscript location(s);
3. change or addition required;
4. verified result/evidence and its source;
5. status: wording-only, ready to insert, pending artifact, author confirmation, or blocker;
6. completion check for the later writing stage.

Include additional non-rebuttal fixes found during the audit—build failures, undefined references, claim-boundary corrections, ethics/privacy conflicts, and release hygiene—without presenting them as reviewer promises.

Appendix-directed items stay in the same master inventory as main-text items. Link corrected full panels, sensitivity analyses, annotations, release metadata, implementation specifications, prompts, tool schemas, and skill-pool details to the corresponding Appendix columns and retain the evidence/result card that justifies each planned change.

## Boundary with final writing

- Do not edit target manuscript prose, replace figures/tables, resolve citations, or mark an item completed during mapping.
- Do not create the final camera-ready group unless the user asks to begin writing.
- When final writing starts, use the map as the change contract and preserve links from completed revisions back to their mapping IDs.

## Safe mutation and validation

Before writing, make one timestamped `.canvas-history` backup and enforce a SHA-256 precondition. After writing, verify unique IDs, valid endpoints, no overlaps, no arrows from the master checklist, complete ID coverage, exact manuscript-text preservation, rigid section shifts, direct coverage of every appendix-directed item, and deterministic rerun no-op behavior.

Append the inventory source, mapping bundles, evidence status, blockers, layout changes, and validation result to `CANVAS_ACTION_LOG.md` with the plugin's `scripts/record_action.py`.
