---
name: paper
description: "Create or update a sentence-level academic manuscript view inside versioned Obsidian Canvas groups such as paper_v1 and paper_v2. Use when importing, writing, revising, or mechanically laying out paper prose. Do not use for RQ experiment graphs or reviewer rebuttal grids."
---

# Paper

Treat each native `paper_vN` group as one immutable manuscript-version workspace. The repository manuscript remains the publication source of truth; the Canvas is its sentence-level reasoning and revision view.

## Version and task groups

- Keep versions and paper tasks in native Canvas groups. Preserve every existing group ID; never delete and recreate a group to change its layout.
- Apply edits only to the version or task group the user names. Do not silently synchronize another version.
- A new paper starts with empty version/task groups. Do not copy example-paper cards into it.
- Before importing prose, preserve the manuscript's section, subsection, paragraph, sentence, table, equation, figure, citation, and reference order.
- Treat the submission-time appendix as part of every imported paper version. Put it in a version-explicit native group such as `paper_v1 appendix` or `paper_v2 appendix`, positioned below the main manuscript but fully contained inside the corresponding outer `paper_vN` group. Do not stop the import at the bibliography or `\appendix` boundary.

## Sentence-card grammar

- Use exactly one prose sentence per card. A heading, display equation, Markdown table, or figure is its own non-sentence block.
- Use one fixed width for ordinary body cards and subsection headings. Default to 812px, or retain an explicit canonical width already established by the user in that version group. A top-level section title is the exception described under Section layout.
- Fit every ordinary card's height to its rendered text; do not use uniform fixed heights or leave avoidable blank space.
- Use 20px as the default node gap. Keep sentences from the same paragraph 20px apart vertically and use 40px between paragraphs.
- Tables and figures are width exceptions. Size a Markdown table to its rendered columns and preserve it verbatim in one block. Keep a figure as its own file/image card at an appropriate artifact width. Keep a complete display equation in one card even when its source contains blank lines.
- Preserve appendix-only artifacts with the same fidelity as main-text artifacts: full result tables, captions, equations, prompt boxes, tool schemas, model/source notes, and figure panels remain complete blocks rather than summaries.
- Preserve the text and formatting during a layout-only request. Splitting cards does not authorize rewriting, summarizing, correcting, or deleting manuscript content.

## Citations and artifacts

- Replace each in-prose citation command with `{}` at the exact citation position. Put the exact removed citation command in a separate side card; consolidate multiple citations from one sentence in their original order.
- Place a citation card 20px to the side of its sentence and draw a lateral edge from the citation card to that sentence. Citation cards are ordinary gray/default cards, not part of the downward prose chain.
- Keep every referenced Figure and Table as a separate artifact block. If the manuscript mentions an artifact that is absent from the Canvas, materialize the actual figure or full Markdown table from the manuscript source; never substitute a numeric summary or placeholder.
- Draw an edge from each Figure/Table artifact to every sentence that explicitly mentions it. Select the nearest valid sides so a side-by-side artifact uses a lateral edge and a vertically separated artifact uses a bottom-to-top or top-to-bottom edge.
- Place each Figure or Table at its first explicit mention, not at the start of its section. Start a parallel artifact lane at that sentence: artifact on the left, mentioning sentence and the remainder of its local paragraph stack on the right. Later mentions reuse the same artifact through additional edges.
- Keep display equations in the ordinary downward manuscript flow. When prose explicitly references an equation, draw an edge from the complete equation block to each mentioning sentence; do not move the equation into a Figure/Table-style side lane.
- When an edge is geometrically straight, align the connected sides by center: equal y-centers for left/right edges and equal x-centers for top/bottom edges. Offset nodes only when a curved edge is intentional.
- When main-text prose explicitly cites an Appendix section, draw a reference edge from that sentence to the exact Appendix section title or narrower target. Because the Appendix group is below the paper, prefer sentence-bottom to target-top direction; multiple Appendix references in one sentence receive separate edges.

## Section layout

- Preserve the established x-axis indentation hierarchy: section, subsection, paragraph heading, and body levels remain progressively indented like an outline. Never flatten these levels to one x coordinate.
- Lay top-level manuscript sections left to right as separate section columns, with their section headers top-aligned. Within each section, the primary reading direction is downward.
- Do not extend the main-manuscript row horizontally with Appendix columns. Place the version's nested Appendix group below the main manuscript while keeping it inside the outer `paper_vN` group, and keep visibly lettered columns such as `Appendix A · ...` inside that nested group. When another version already establishes the Appendix group's offset, bounds, and one-row or wrapped layout, reproduce that relative geometry for the new version.
- Keep deliberately parallel cards and Figure/Table-to-prose pairs in the same row when the source layout already encodes that relation. Use 20px horizontal gaps and move later top-level sections only as far right as needed to avoid overlap.
- Center a parallel contribution branch under its lead card: the lead card's horizontal center matches the full branch row's center, so an odd middle branch receives a straight centered arrow and the outer arrows curve symmetrically.
- Compute each section's complete bounding rectangle after laying out all indented prose, citation cards, artifacts, and parallel branches. Space adjacent top-level sections from those rectangles, not merely from their headers or main prose columns.
- Make each top-level section title span the full horizontal extent of that complete section rectangle: its left and right edges match the section's leftmost and rightmost managed nodes. The title therefore acts as the visible section-area header, as in the established Skill Following section.
- Preserve existing section order and meaningful parallel rows. Spatial alignment expresses prose order; do not add arrows mechanically. Preserve manual edges unless the user asks to change their relationship.
- Add edges only for explicit citations, Figure/Table mentions, or user-authored logical relations. When an expanded paper group would overlap a lower native group, move the lower group and all its contained nodes as one rigid body. Preserve every internal relative position, size, color, edge, and text.
- Fit the nested Appendix group to that version's Appendix nodes, then expand the outer `paper_vN` group to contain both the complete main-manuscript area and the complete Appendix group. Never shrink the outer paper group to the main manuscript alone.

## Safe mutation

Before the first Canvas write in a session, make one timestamped backup under `.canvas-history/`. Use a SHA-256 precondition or equivalent concurrency check before replacing Canvas JSON.

After editing, verify:

- unique node and edge IDs;
- every edge endpoint exists;
- ordinary text widths are consistent;
- each prose card contains one sentence;
- sentence and paragraph gaps follow 20/40px;
- every removed citation has one side card and a card-to-sentence edge;
- every available Figure/Table reference has an artifact-to-mention edge, and every unavailable referenced artifact is reported as a blocker;
- every Figure/Table begins at its first mention row, every explicit equation reference has an equation-to-mention edge, and every straight edge is center-aligned;
- parallel contribution rows are centered under their lead card, each top-level title spans its section rectangle, and top-level section rectangles do not overlap;
- every source appendix section is present in order inside the correct version-specific nested group, every appendix table/figure is complete, and each explicit main-text Appendix reference has a main-text-to-Appendix edge;
- each Appendix group is fully contained by its corresponding outer paper group; sibling outer groups and managed cards do not overlap, while this intentional parent-child containment is not treated as a collision;
- untouched version/task groups are unchanged except for an explicitly logged rigid-body collision shift;
- rerunning a deterministic layout transform makes no further changes.

Append the import, split, layout, group shift, validation, correction, and blocker actions to the adjacent `CANVAS_ACTION_LOG.md` with the plugin's `scripts/record_action.py`.
