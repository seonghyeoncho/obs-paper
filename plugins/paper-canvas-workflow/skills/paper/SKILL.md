---
name: paper
description: "Create or update a sentence-level academic manuscript view inside versioned Obsidian Canvas groups such as paper_v1 and paper_v2. Use when importing, writing, revising, or mechanically laying out paper prose. Do not use for RQ experiment graphs or reviewer rebuttal grids."
---

# Paper

Treat each native `paper_vN` group as one manuscript-version workspace. The versions are stages, not copies: `paper_v1` is the Korean draft and the author's working-out, `paper_v2` is the English translation that gets submitted, and `rebuttal` and `camera_ready` follow. The Canvas is never the publication source of truth — where a project records an Overleaf project, that manuscript is; otherwise the repository manuscript is.

## Deterministic automation

- Read `../../references/request-schema.md` before authoring a request.
- Read `references/korean-prose.md` before writing or revising Korean manuscript prose. Its rules deliberately differ from the research-flow ones; layout-only work does not need it.
- For supported paper operations, do not edit Canvas JSON directly. Use `../../scripts/obs_paper.py` with a schema-version-1 `paper` request.
- Run `inspect` to resolve exact node IDs, `plan` to produce a SHA-bound patch, `apply` with the adjacent action log, and `validate` after writing. A second `plan` with the same request must contain zero operations.
- `group_appendix` requires the owning `paper_vN` group, the complete explicit member-node list, the section label, and normally 20px padding. If the computed group would capture any unlisted node, stop and correct the request rather than widening the group.
- `insert_blocks` requires an exact anchor node, individually keyed text blocks, and the complete explicit list of downstream nodes that must move. Use `fit_group_id` when inserting into a section-owned Appendix group so its 20px boundary is recomputed. Tables and figures are not prose blocks and must wait for an outside-artifact handler.
- Use `place_artifact`, `split_citation`, and `connect_reference` for side artifacts and explicit references; use `fit_section_title` after the section rectangle changes.
- Use `pair_appendix_columns` for section-owned Appendix lanes, `normalize_equations` for fenced-math conversion, `normalize_paper_colors` for the complete manuscript-owned node set, `compact_sections` for ordered top-level section rectangles, `move_nodes` for an explicit managed set, and `shift_sibling_group` only for a required rigid-body collision shift.
- Every mutation request names exact node IDs. Do not infer a broad deletion or movement set from coordinates alone.

## Assembling the LaTeX

`../../scripts/paper_tex.py <canvas> --group paper_vN --out body.tex` reads a manuscript group and emits a LaTeX body.

It emits a fragment, never a whole document. The template owns the preamble, author block, and bibliography; the Canvas owns the abstract, headings, prose, tables, and figures. They stay in separate files so that pushing a rebuilt body replaces only generated content and leaves what co-authors edit alone. Add `\input{body}` to the template once, in place of its abstract and placeholder section.

What the generator reads from the layout: sections run left to right and each column reads downward; heading level comes from the number in the heading text, so `# 2.1 구조` is a subsection and an unnumbered heading is the abstract; a gap under 30px keeps a paragraph together and a wider one starts the next. A figure is an image card followed by its caption card. An artifact too wide for one column becomes a starred float, judged from the widest table row and from the image card's aspect ratio — get this wrong and the artifact overprints the text beside it.

Bare Greek and maths characters are moved into maths mode, since the Canvas renders `θ` directly and pdflatex will not. Node ids are stripped as the metadata they are.

Generation is one way. Nothing reads LaTeX back into the Canvas, so an edit made in Overleaf is lost on the next rebuild unless it is brought back to the Canvas first.

## Manuscript grammar

- Preserve source order and distinguish section, subsection, paragraph, sentence, display equation, citation, table, figure, and Appendix content before laying out nodes.
- Use one prose sentence per card in both the main text and Appendix. Fit card height to rendered text. Use 20px between sentences in one paragraph and 40px between paragraphs.
- Use one ordinary-card width within a version, normally 812px. Headings follow the established indentation hierarchy; tables and figures are width exceptions.
- Indent a subsection or paragraph heading relative to its parent, then keep every prose card owned by that heading on the same left edge as the heading. Content must never sit to the left of its owning structural heading.
- Preserve inline LaTeX as `$...$`. Put every display equation in one card enclosed by `$$` and `$$`; never use fenced `math` code blocks.
- Preserve manuscript wording during layout-only work. Splitting or moving cards does not authorize rewriting or summarizing them.
- Renaming the system a paper describes is not renaming the project. Change it in prose, table headers, and figure labels; leave config identifiers, result keys, project-scoped card labels, directories, and file names alone. A project and the system it studies are separate names that happen to have started out the same.

## Mandatory color grammar

Match the established `paper_v1` Skill Following palette exactly:

- Color `"6"` (purple): every structural manuscript heading card represented with `# `, including section, subsection, paragraph, and Appendix headings.
- Color `"4"` (green): only the contribution lead and its contribution branch cards.
- No `color` field: ordinary prose, display equations, citation/source cards, tables, figures, and embedded prompt or schema content such as `##` lines inside a content block.

The paper workflow must not create red `"1"`, orange `"2"`, yellow `"3"`, or cyan `"5"` manuscript nodes. Those colors belong to author thoughts, camera-ready mapping, camera-ready changes, or other workflows. Preserve such user-authored or stage-specific annotations by excluding them from paper color normalization.

For `insert_blocks`, use `kind: "heading"` with `# ` text for a structural heading; it becomes purple automatically. Use `role: "contribution"` for every contribution card; it becomes green automatically. Do not pass raw `color` values.

After importing or reconstructing a paper version, run `normalize_paper_colors` once with the complete explicit list of manuscript-owned, non-group node IDs and the contribution subset. Exclude mapping annotations, reviewer cards, author notes, and camera-ready change nodes. A second identical normalization must produce zero operations.

## Section-paired Appendix layout

- Do not create a separate Appendix group or a bottom row of Appendix columns.
- Each top-level section owns up to two vertical text columns: main text on the left and the Appendix material supporting that section on the right. The current `paper_v1` Skill Following section, with Appendix A beside its main text, is the reference geometry.
- Wrap each section's Appendix column and its outside artifacts in one native Canvas group labeled `<Section> · Appendix <letters>`. Keep this section-scoped group inside the owning `paper_vN` group; the prohibition above applies only to a manuscript-wide or bottom Appendix group.
- Assign an Appendix section to the main section that explicitly references it first. If no explicit reference exists, use the section whose topic it documents. Ask only when ownership is genuinely ambiguous.
- Keep each Appendix heading, sentence, paragraph, equation, table, figure, prompt, and schema complete and in source order. Appendix prose follows the same one-sentence and 20/40px rules as main prose.
- Draw a reference edge from a main-text Appendix mention to the exact Appendix heading or narrower target in the right column. When the target is predominantly beside the source, start and end at their facing side ports; use vertical ports only when the target is predominantly above or below.
- A section with no Appendix material needs no empty placeholder column.

## Citations, equations, tables, and figures

- Promote citations from the research-flow literature mapping: the cited item must already belong to the project Zotero Collection, exist in `references.bib`, and have a linked per-paper Canvas. Connect the citation card to the narrowest manuscript sentence supported by that literature; do not bulk-import every collected paper into the manuscript.
- Replace an in-prose citation command with `{}` at the same position. Put the exact command in a grey side card and connect that card laterally to the sentence.
- Keep display equations in their owning prose column. When prose names an equation, connect the equation card to that sentence.
- Tables and figures never sit in the downward sentence stack. Put each artifact in an outside side lane at its first explicit mention and draw `artifact -> mentioning sentence`.
- Prefer the outside-left lane for a main-text artifact and the outside-right lane for an Appendix artifact. Use the other free side when this avoids overlap. Later mentions reuse the same artifact through additional edges.
- A table card contains the complete Markdown table. Set its width independently from prose: use the smallest width at which headers and numeric cells render without clipping, horizontal scrolling, or unintended wrapping. After changing width, refit height. Visually inspect the rendered Canvas and expand in 40px increments until it passes.
- Where a table prints a ratio next to its own denominator, check the arithmetic. `0.126 (31/212)` is wrong and the table itself says so. Do this whenever a table is added, edited, or reviewed; it costs one division per cell and catches errors no amount of reading will.
- A figure's labels come from its plotting code, where they are usually the run-mode keys the results are stored under, not the names the paper uses. So a figure does not follow when the manuscript renames something, and prose can say BELAY while the axis still says `polar`. Read the actual image rather than trusting the caption, and compare its labels and values against the table and prose that cite it. The fix belongs in the plotting code as a display-label map; never rename the key, because the results are keyed by it.
- Regenerating a figure, recomputing a number from results, and editing LaTeX all belong in the project repository, not here. The Canvas is a view. Report the mismatch with enough detail to act on it and leave the artifact to be rebuilt at its source.
- Size a figure to the actual image aspect ratio and readable labels. Do not substitute a caption, number summary, or placeholder for an available table or figure.
- Choose reference ports by the dominant center-to-center axis: horizontal displacement uses facing left/right ports, while vertical displacement uses top/bottom ports. This paper-reference routing is independent of the research-flow convention that reserves side-origin arrows for red thought nodes. Straight lateral edges use equal y-centres; straight vertical edges use equal x-centres. Curve only to route around intentional parallel content.

## Section geometry

- Lay top-level sections left to right and read each section downward. Preserve section/subsection/paragraph indentation within both text columns.
- Keep the main and Appendix text columns parallel. Use horizontal space for their outside artifact lanes rather than inserting artifacts into either prose stack.
- Center deliberate contribution branches beneath their lead card.
- Compute a section rectangle from its main column, Appendix column, citations, equations, tables, figures, and branches. Adjacent sections must be spaced from these complete rectangles.
- Make the top-level section title span the full section rectangle so it visibly marks that section's area.
- Keep exactly 120px of horizontal space between adjacent complete top-level section rectangles. Do not measure from prose columns or title text alone. Run `compact_sections` with ordered sections and complete explicit node sets after title fitting; a second identical run must produce zero operations.
- Spatial order carries ordinary prose flow. Add arrows only for citations, explicit Figure/Table/Equation/Appendix references, or user-authored logical relations.

## Safe mutation and validation

Preserve existing group and node IDs. Before the first Canvas write, make one timestamped backup under `.canvas-history/` and enforce a SHA-256 precondition. Move an overlapping sibling group only as one rigid body.

Verify after editing:

- unique IDs and valid edge endpoints;
- one sentence per prose card and fitted heights;
- 20/40px sentence and paragraph gaps;
- every display equation uses `$$...$$`, including Appendix equations;
- every managed structural `# ` heading is purple, every declared contribution card is green, and every other managed manuscript node has no color field;
- no separate Appendix group remains in a newly built version;
- every populated Appendix column has one correctly labeled section-scoped group inside `paper_vN`;
- each Appendix section is in its owning section's right column and in source order;
- every citation and explicit Appendix/Equation/Figure/Table mention has the required edge;
- every Table/Figure is outside the prose stack, at its first mention, readable at its own width, and non-overlapping;
- every printed ratio agrees with its own denominator, and figure labels agree with the table and prose that cite them;
- section titles span complete section rectangles and sibling sections do not overlap;
- adjacent complete top-level section rectangles have exactly 120px horizontal gaps;
- rerunning the deterministic transform makes no further changes.

Append material layout, correction, validation, and blocker actions to the adjacent `CANVAS_ACTION_LOG.md` with `scripts/record_action.py`.
