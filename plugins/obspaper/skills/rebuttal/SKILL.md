---
name: rebuttal
description: "Organize academic peer-review material in an existing Obsidian Canvas and develop each reviewer comment through six fixed stages: English original, Korean translation, strategy memo, Korean rebuttal, English rebuttal draft, and English final. Use when the user supplies reviewer feedback, asks to structure a rebuttal, or advances rebuttal drafts. Do not use for RQ/experiment research-flow graphs."
---

# Rebuttal

Use the existing native `Rebuttal` group as a reviewer-by-reviewer working grid. Preserve the group ID and all unrelated cards. Do not rebuild the group or merge similar comments from different reviewers.

## Deterministic automation

- Read `../../references/request-schema.md` before authoring a request.
- Use `../../scripts/obs_paper.py` with workflow `rebuttal` and action `layout_rebuttal`.
- Supply one reviewer, an origin, and ordered `rows`; every row has a stable key, a review kind, and exactly six stage strings.
- The handler creates or updates the 625/625/520/660/660/660 grid, applies review-category colors while preserving later-stage colors, top-aligns each row, uses the tallest card plus 80px for the next row, expands the existing group, and reruns as a no-op.

## Import reviewer material

- When the user supplies the complete review set, split it by reviewer and preserve reviewer order, reviewer IDs, section order, numbering, scores, and confidence.
- Use one reviewer header such as `# R1: KvNE03`. Keep Paper Summary, strengths, weaknesses, comments/suggestions, and evaluation metadata distinct.
- Treat each independently answerable weakness or comment as one row. Do not combine items merely because one rebuttal could mention both.
- Classify every row as `weakness`, `strength` (also accepting `strong` or `props`), `suggestion`, or `neutral` before layout.
- Keep the first-column English text verbatim apart from unavoidable Canvas formatting. The second column is a faithful Korean translation, not a summary.
- If the input is partial, organize only what was supplied and mark the reviewer block as incomplete rather than inferring missing review text.

## Six-stage order

Every answerable reviewer item advances left to right without overwriting earlier stages:

1. **English** — verbatim reviewer text.
2. **한국어** — faithful translation preserving references, numbers, hedges, and emphasis.
3. **메모** — strategy, interpretation, evidence to check, concession/contest decision, and planned paper changes.
4. **한국어 리부탈 내용** — complete Korean response grounded in verified evidence and actual revisions.
5. **영어 리부탈 초안** — accurate English draft; clarity before compression.
6. **영어 리부탈 최종본** — concise polished response consistent across reviewers and limited to claims the paper can support.

Populate stages as the work becomes ready. If the user requests a complete one-pass rebuttal and the evidence is available, populate all six; otherwise leave later-stage placeholders visibly empty. Never silently replace a memo, draft, or prior final with a later version.

## Mechanical Canvas layout

Use the completed R1 block in the current Skill Following Canvas as the reference grid.

- Column widths are fixed at `625, 625, 520, 660, 660, 660` pixels in the six-stage order.
- Starting from the English column, use fixed inter-column gaps of `73, 55, 160, 20, 40` pixels. The 160px gap separates analysis from the rebuttal-writing cluster.
- Lay the six stages out horizontally. Stack one reviewer's independently answerable items vertically in their original order.
- Top-align all cards belonging to the same reviewer item. Fit each card height to its rendered text, then place the next row below the tallest card in the current row with an 80px gap.
- Keep reviewer headers 200×50px and place the first content row 80px below the header. Reviewer blocks remain spatially separate; expand the existing group rather than compressing or overlapping them.
- Use spatial alignment, not arrows, to express the six-stage progression. A lateral arrow may connect the Korean reviewer item to its memo when the memo directly answers that item; do not chain translation, Korean rebuttal, draft, and final with arrows.
- Color both reviewer-content cards (English and Korean) by row kind: weakness is red (`1`), strength/strong/props is green (`4`), and suggestion is yellow (`3`). Neutral rows remain uncoloured. Preserve existing memo and rebuttal-stage colors; empty placeholders remain uncoloured.

## Rebuttal content rules

- The memo must identify what the reviewer is actually asking, whether to concede or contest, what evidence is required, and which manuscript change or response move resolves it.
- Open each rebuttal with a direct answer to the reviewer rather than background. State what was clarified, changed, added, tested, or scoped down.
- Separate completed changes from camera-ready promises. Never write “we have added,” “we verified,” or equivalent unless the artifact or result exists.
- Preserve uncertainty and limitations. Do not convert a diagnostic result into a causal, cross-model, or improvement claim without evidence.
- Reuse one consistent explanation for repeated concerns across reviewers while answering each reviewer locally; do not copy text that fails to address their specific wording.
- The English final must not introduce evidence or commitments absent from the Korean rebuttal and verified paper state.

## Safe updates and logging

Before the first Canvas mutation in a session, make one timestamped backup under `.canvas-history/`. Reparse the JSON after editing and verify unique node/edge IDs, valid endpoints, non-overlap, fixed column widths, and row top-alignment.

Append every material decision and mutation to `CANVAS_ACTION_LOG.md` beside the Canvas using the plugin's `scripts/record_action.py`. Record reviewer import, translation, memo, each rebuttal stage, layout changes, validation, and any missing evidence or blocked finalization separately.
