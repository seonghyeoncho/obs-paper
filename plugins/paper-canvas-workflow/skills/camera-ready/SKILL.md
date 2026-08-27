---
name: camera-ready
description: "Create or update the final camera-ready manuscript group in an Obsidian Canvas by applying a completed camera-ready mapping to a source paper version. Use when the user is ready to produce paper_camera_ready; do not use for mapping-only planning or rebuttal drafting."
---

# Camera Ready

Create `paper_camera_ready` as the final sentence-level manuscript view. Treat the mapped source group, normally `paper_v2`, as immutable input and apply the mapping in a new outer group.

## Build the final group

- Copy only manuscript headings, prose, equations, citations, figures, tables, the nested Appendix group, and their internal reference edges.
- Do not copy the camera-ready inventory, section lanes, Change/Add cards, Evidence/Result cards, or their mapping edges.
- Name the outer group `paper_camera_ready` and the nested group `paper_camera_ready appendix`. Keep the Appendix below the main manuscript and fully inside the outer group.
- Preserve source order and use the `paper` skill's sentence-card, citation, artifact, equation, hierarchy, spacing, section-title, and Appendix rules.
- Place the new outer group beside the source with a non-overlapping gap. When mapping lanes expanded the source horizontally, restore the compact manuscript geometry instead of copying empty lane space.

## Apply mapped changes

- Process every mapping item by stable ID. A `ready` or `wording` item is complete only when its promised prose, result, table, figure, caption, or definition appears at the mapped target in the final group.
- Color every replaced or newly added manuscript node yellow (`"3"`). Preserve the original color of unchanged nodes. A changed Figure or Table is yellow too.
- Yellow means camera-ready diff in this group. It does not mean uncertainty.
- Keep final prose publication-ready: do not put mapping IDs, reviewer notes, strategy notes, or implementation commentary inside completed manuscript sentences.
- Evidence tables must contain the actual reported values. Reuse verified result sources; never replace a promised table or figure with a numeric summary.

## Blocked items

- Never invent missing experiments, release dates, citations, ethics facts, privacy decisions, or artifact availability.
- If a mapped item is still blocked, keep the safest defensible source wording and add one yellow side card headed `# Author input required · CR-XX` beside the narrow target. State the exact missing fact or action and connect the blocker laterally to its target.
- A blocked item is not counted as applied. Keep it visibly separate from the downward manuscript flow and list it in validation output.

## Safe mutation and validation

Before the first write, make one timestamped backup under `.canvas-history/` and enforce a SHA-256 precondition. Preserve all existing IDs and groups outside the new final group. Use deterministic IDs for cloned and added nodes so a rerun is idempotent.

Verify:

- unique node and edge IDs and valid edge endpoints;
- exactly one outer `paper_camera_ready` group and one contained `paper_camera_ready appendix` group;
- no mapping-only nodes or mapping edges inside the final group;
- every completed mapping item has at least one yellow changed node at its mapped target;
- every blocked item has one yellow author-input card and is not presented as completed evidence;
- ordinary card width, fitted height, 20/40px spacing, section rectangles, artifact placement, and Appendix reference edges follow the `paper` skill;
- no sibling paper group overlaps the new outer group;
- rerunning the transform makes no further changes.

Append creation, applied item IDs, blockers, layout correction, and validation results to `CANVAS_ACTION_LOG.md` with `scripts/record_action.py`.
