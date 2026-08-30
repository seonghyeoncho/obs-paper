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

`../../scripts/paper_tex.py <canvas> --group paper_vN --out main.tex` reads a manuscript group and emits a LaTeX body.

The output is three kinds of file beside each other:

```
main.tex        body prose, headings, figures
tables/          one file per table
appendix.tex     appendix material, when there is any
```

A tabular runs to dozens of lines — one of POLAR's is seventeen rows — and buries the prose it sits among, so each table goes to `tables/tableN.tex` and the body keeps a one-line `\input`. The float travels whole, so a table can be reworked without touching the prose around it. Figures stay inline at five lines each. `--inline-tables` keeps everything in one file.

Appendix material is whatever sits in a sub-group whose label names an appendix, per the section-paired layout below. It goes to `appendix.tex` with its headings labelled `app:` rather than `sec:`, so an appendix section cannot collide with a body section of the same number. The file holds only what follows `\appendix`; the template declares that. A manuscript with no appendix group produces no such file.

Write the output into the project's paper directory — `<repository>/<paper_dir>` from `project.md`, normally `docs/paper` — so the generated files sit beside the manuscript's own figures and the author compiles in one place. Never leave them in a temporary directory.

It emits a fragment, never a whole document. The body is pasted into `acl_latex.tex` by hand rather than pulled in with `\input`, because a collaborator opening the project has to see the manuscript rather than a one-line include. Tables and the appendix stay separate and *are* included, so the pasted body carries its `\input{tables/…}` lines with it and `tables/` and `figs/` have to be in the project too.

So the template owns everything structural: `\documentclass`, the preamble, the author block, `\begin{document}`, `\bibliography`, and `\appendix`. Never emit any of those. `\appendix` in particular belongs to the template — appendix material, when a manuscript has any, goes to its own file that the template inputs after that declaration, so the generator never decides where the appendix begins.

The Canvas owns the abstract, headings, prose, tables, and figures. Ask what the generated body file should be called and record it as `overleaf_body` in `project.md`. Putting anything into Overleaf is the author's job — see the `overleaf` skill for why that is deliberate.

What the generator reads from the layout: sections run left to right and each column reads downward; heading depth comes from the card's colour, and the first heading is the title while a heading naming the abstract opens it; a gap under 30px keeps a paragraph together and a wider one starts the next. Section numbers in the output are generated, so `\label{sec:5.2.1}` exists even though the Canvas names no numbers. A figure is an image card followed by its caption card. An artifact too wide for one column becomes a starred float, judged from the widest table row and from the image card's aspect ratio — get this wrong and the artifact overprints the text beside it.

Bare Greek and maths characters are moved into maths mode, since the Canvas renders `θ` directly and pdflatex will not. Node ids are stripped as the metadata they are.

## Bringing Overleaf edits back

Co-authors edit the manuscript in Overleaf, and those edits have to reach the Canvas or the next rebuild discards them.

```bash
python /path/to/plugin/scripts/overleaf.py download <project_id> --out paper.zip
python /path/to/plugin/scripts/paper_pull.py <canvas> <the unzipped .tex>
```

`paper_pull.py` regenerates the body from the Canvas, aligns it paragraph by paragraph against the manuscript, and reports what differs. A changed paragraph names the card to edit: a paragraph is several cards joined, and every sentence still present word for word is untouched, so what is left is the one card that changed. A paragraph a co-author added names no card, because none produced it.

It writes nothing. Turning a LaTeX edit back into Korean prose cards is a judgement — unescaping, citations folded back out, a sentence split across cards — and a wrong guess corrupts the manuscript quietly. Naming the cards is the part that can be done correctly; fetch them with the `node` skill and edit them yourself.

Pull before regenerating, always. Rebuilding first overwrites the answer to what changed.

## Manuscript grammar

- Preserve source order and distinguish section, subsection, paragraph, sentence, display equation, citation, table, figure, and Appendix content before laying out nodes.
- Use one prose sentence per card in both the main text and Appendix. Fit card height to rendered text. Use 20px between sentences in one paragraph and 40px between paragraphs.
- Use one ordinary-card width within a version, normally 812px. Headings follow the established indentation hierarchy; tables and figures are width exceptions.
- Indent a subsection or paragraph heading relative to its parent, then keep every prose card owned by that heading on the same left edge as the heading. Content must never sit to the left of its owning structural heading.
- Preserve inline LaTeX as `$...$`. Put every display equation in one card enclosed by `$$` and `$$`; never use fenced `math` code blocks.
- Preserve manuscript wording during layout-only work. Splitting or moving cards does not authorize rewriting or summarizing them.
- Renaming the system a paper describes is not renaming the project. Change it in prose, table headers, and figure labels; leave config identifiers, result keys, project-scoped card labels, directories, and file names alone. A project and the system it studies are separate names that happen to have started out the same.

## Mandatory color grammar

A heading card is written `# <title>` with no number, and its colour carries the outline depth:

- Color `"6"` (purple): section. Also the manuscript title and the abstract heading, which are not sections but sit at the top level.
- Color `"5"` (cyan): subsection.
- Color `"4"` (green): paragraph heading, and separately the contribution lead and its branch cards. The two never collide: a heading starts with `# `, a contribution card does not.
- No `color` field: ordinary prose, display equations, citation/source cards, tables, figures, and embedded prompt or schema content such as `##` lines inside a content block.

Never number a heading. Numbering means renumbering every sibling and every reference whenever the outline moves, and the outline moves often; the Canvas states no numbers and LaTeX does the counting. The outline stops at paragraph — there is no subsubsection.

The paper workflow must not create red `"1"`, orange `"2"`, or yellow `"3"` manuscript nodes. Those colors belong to author thoughts, camera-ready mapping, and camera-ready changes. Preserve such user-authored or stage-specific annotations by excluding them from paper color normalization.

For `insert_blocks`, use `kind: "heading"` with `# ` text and `level` of `section`, `subsection`, or `paragraph`; the colour follows. Use `role: "contribution"` for every contribution card; it becomes green automatically. Do not pass raw `color` values.

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
- A citation is a grey side card holding the command as `~\cite{key}`, connected to the sentence it supports. Like every side card it originates the edge and points into the prose, the same direction a table or figure does. `paper_tex.py` folds the command into that sentence and drops the card, so the command never sits in the prose itself.
- Where the citation belongs mid-sentence, put `{}` in the prose at that position and the command lands there. With no placeholder it lands at the end, inside the closing full stop, which is where a citation usually goes.
- A cross-reference to another section is written in the prose as ordinary text — `5.1절` — and the sentence draws an **outgoing** arrow to that heading. This is the one place a flow card originates an edge: a heading that pointed back at every sentence naming it would tangle the downward read, and the sentence is the one doing the referring. `paper_tex.py` resolves the reference from the arrow, so the printed number is generated and cannot go stale. A written number that matches no arrow is left as text and reported; the arrow is what the sentence means, and the number beside it is only a copy.
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
