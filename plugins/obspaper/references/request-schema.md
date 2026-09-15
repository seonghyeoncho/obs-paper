# Request schema

Use one JSON object:

```json
{
  "schema_version": 1,
  "workflow": "paper",
  "target": {"group_id": "..."},
  "actions": [{"op": "group_appendix", "label": "...", "member_ids": ["..."]}]
}
```

Every action names itself under `op`. The action lists below are written as
`op-name`: required fields; optional ones follow a semicolon.

`target` contains exactly one of `group_id` or `group_label`. Resolve IDs with `inspect`. Stable `key` values produce deterministic IDs.

## Paper actions

- `group_appendix`: `label`, `member_ids`; optional `group_id`, `padding`. Paper groups always use the default color.
- `insert_blocks`: `anchor_id`, `blocks`; optional `shift_node_ids`, `fit_group_id`, `gap`, `gap_after`. The default gap is 20; a `paragraph` starts after 40 unless its `gap_before` is explicit. Every block has `key`, `text`, and `kind` (`sentence`, `paragraph`, `heading`, `equation`); geometry and `role` (`ordinary` or `contribution`) are optional. Colors are derived: structural headings use `"6"`, contributions use `"4"`, and other blocks use no color.
- `place_artifact`: `key`, `kind` (`figure` or `table`), `mention_ids`, `lane`, `width`, `height`; a figure has `file`, a table has complete Markdown `text`.
- `pair_appendix_columns`: `sections`. Every section has `key`, `label`, `x`, `y`, and ordered `blocks` of explicit member-ID lists; optional `group_id`, `gap`, `padding`.
- `split_citation`: `key`, `sentence_id`, exact `command`; optional `card_text`, `lane`, `width`, `height`, `gap`, `node_id`. Use `card_text` to retain the command plus a Zotero link in the grey side card.
- `connect_reference`: `key`, `kind`, `source_id`, `target_ids`. Ports follow the dominant center-to-center axis automatically. Supply both `from_side` and `to_side` only for an intentional override; set `curved: true` when that override is not center-aligned.
- `fit_section_title`: `title_id`, `member_ids` for the complete semantic section rectangle, excluding mapping annotations.
- `move_nodes`: `anchor_id`, complete `node_ids`, destination `x`, `y`. The destination is absolute and rerunnable.
- `shift_sibling_group`: sibling `group_id` and absolute `x`, `y`. The complete contained group moves rigidly.
- `normalize_equations`: explicit `node_ids` whose text is fenced `math` or already `$$...$$`.
- `normalize_paper_colors`: complete explicit manuscript-owned `node_ids`; optional `contribution_ids`, which must be a subset. It assigns `"4"` to contributions, `"6"` to remaining `# ` structural headings, and removes color from all other managed nodes. Exclude reviewer, mapping, author-note, and camera-ready annotation nodes.
- `compact_sections`: ordered `sections`, each with a structural `title_id` and the complete explicit `node_ids` for that section, including nested Appendix groups and artifacts; optional `gap`, default 120. Every title must already span its complete section rectangle. The first section stays fixed and later sections translate rigidly to the exact gap.

## Camera-ready mapping actions

- `mapping_master`: `key`, `x`, `y`, `width`, `manuscript_node_ids`, and `items`. Each item has `reviewer`, real `label`, `topic`, and `status`.
- `map_issue`: `key`, real reviewer/topic `label`, `asked`, `change`, `evidence`, `status`, `done_when`, one-element `target_ids`, `x`, `y`; optional title `node_id`, per-field `detail_node_ids`, `width`, and title `height`. It creates one orange title node followed by separate Asked, Evidence, Status, Done when, and Change nodes; only the title connects to the manuscript target.
- `stream` is `main` (default) or `appendix`. The flow reads top to bottom in the main column; the appendix column beside it holds negative results, ruled-out alternatives, and robustness checks, which cannot be deleted because they are why the next card exists. An appendix card keeps its own `y`, so its height still says when in the argument it arrived, and the first one needs `appendix_label` on the action -- containing the word Appendix -- to name the sub-group. The sub-group, not a field on the card, is what records the stream, the same way a card's colour records its kind. A main-stream card that would fall inside that sub-group is refused rather than reclassified.
- Edge colour follows the streams an edge joins: main to main `"4"`, appendix to main `#8a96a1`, appendix to appendix `#c9d2da`. A main card pointing at an appendix card is refused, because that arrow sends the reader out of the argument mid-sentence; evidence points in, as a side card does.
- `move_stream`: `stream`, the destination column `x`, and `node_ids`; optional `appendix_label` when the sub-group does not exist yet. Cards keep their ids and their `y`, so only the column, the sub-group, and the edges around them move. Every edge incident to a moved card is recoloured, and one left pointing the wrong way is turned around rather than refused -- the move is what invalidated it, not the request. When the last appendix card leaves, the sub-group goes with it.
- A card placed past the target group's right or bottom edge grows the group to hold it, so a new question can be appended below an existing flow without resizing anything first. A card placed above or left of the group's origin is refused instead: moving the origin would swallow whatever sits outside.
- `edit_text`: `nodes`, each with `node_id` and the replacement `text`; optional `height`. It rewrites prose and changes nothing else -- kind, colour, and geometry stay as they stand -- which is what settling on a term or polishing a sentence needs. Pass the body; the stamp is handled here, including a stale one carried in from another card. A file node has no text to rewrite.
- `remove_items`: explicit `node_ids` and `edge_ids`. Include every edge incident to a removed node.

Allowed mapping statuses are `wording`, `ready`, `pending`, `author input`, and `blocked`.

## Camera-ready action

`build_camera_ready` requires `key`, `label: "paper_camera_ready"`, exact `source_node_ids`, `source_group_ids`, `source_edge_ids`, destination `x`, `y`, plus `changes`, `additions`, and `blockers`. Pass the existing final `group_id` when updating it.

- Change: `source_id` and any replacement `text`, `file`, or geometry.
- Addition: `key`, `kind`, `x`, `y`, `width`, `height`, and `text` or `file`. Coordinates use the source-paper frame and are translated with the clone.
- Blocker: `key`, `topic`, real reviewer `label`, `target_source_id`; optional size.

## Rebuttal action

`layout_rebuttal` requires `reviewer`, `x`, `y`, and ordered `rows`. Every row has a stable `key`, a `kind` (`weakness`, `strength`, `strong`, `props`, `suggestion`, or `neutral`), and exactly six `stages` in English, Korean, memo, Korean rebuttal, English draft, and English final order. Weakness rows color the English and Korean review cards red, strength/strong/props rows green, and suggestion rows yellow. The six stages run horizontally; reviewer items stack vertically.

## Research-flow action

`add_research_flow` requires keyed `nodes` and explicit two-key `links`. Maintenance uses `edit_text` and `remove_items`.

- Ordinary node: `key`, `kind`, `text`, `x`, `y`; optional geometry and `stream`.
- `kind` is one of `rq`, `experiment`, `answer`, `bridge`, `thought` (coloured, in the flow) or `source`, `table`, `figure`, `implementation`, `params`, `log` (uncoloured side cards). Flow kinds get an H1 prefix when the text has no heading; side cards, bridges, and thoughts keep their text verbatim.
- `implementation`: one per experiment, a two-column table of run grid, paths, commands, commits, and outputs, optionally followed by a `**추가 메모**` paragraph. `params`: one per project, the thresholds and model names that hold across experiments. `log`: a run that produced no usable evidence. Record why it was discarded and where its outputs are, but not its measurements: a discarded number is not worth keeping. A discarded run never stays a green experiment in the flow. See `skills/research-flow/references/content-structure.md`.
- Figure: supply `file`, `width`, and `height` instead of `text`. A figure is a file node, so it takes no text and is the one kind that does not need any.
- Experiment: optionally supply ordered `sections`, each with `key`, `heading`, `text`, and optional `height`. A section is linked as `"<experiment key>:<section key>"` -- section `setup` of experiment `e9` is `"e9:setup"` -- because a section key only has to be unique inside its experiment. An unresolved link key lists the keys that do resolve. `heading` must be exactly `Setup` or `Results`. Status, configuration, and scoring parameters belong in the experiment title or an implementation card, never in a section heading. There is no validity section: whether a run was usable is a property of the run, so completeness, robustness, and data-quality checks go in that experiment's implementation card.
- Every managed card is stamped with its own node id as its last line, so a card can be addressed with `obs_paper.py nodes` without searching. The handler adds it, so supply the body alone; a stamp that arrives anyway is not duplicated, and one carrying another card's id is replaced rather than kept. Figures carry no text to stamp.
- Link direction: a side card originates its link and points into the flow, because the card being referred to aims at the card that refers to it. Write `["impl", "setup"]`, not `["setup", "impl"]`; the reverse is rejected. Side-card links get geometric sides, flow links run bottom to top. The red `thought` card is the only reverse case: it originates a right-to-left link at whatever it questions.
- `link_literature`: `key`, exact research `target_id`, verified `title`, `citekey`, and Zotero `item_key`; optional existing vault-relative `paper_flow`, `relevance`, `lane`, and explicit geometry. It creates one uncoloured source card and a source-to-question edge. Create separate target-specific cards when one paper supports multiple questions.
- `stream` is `main` (default) or `appendix`. The flow reads top to bottom in the main column; the appendix column beside it holds negative results, ruled-out alternatives, and robustness checks, which cannot be deleted because they are why the next card exists. An appendix card keeps its own `y`, so its height still says when in the argument it arrived, and the first one needs `appendix_label` on the action -- containing the word Appendix -- to name the sub-group. The sub-group, not a field on the card, is what records the stream, the same way a card's colour records its kind. A main-stream card that would fall inside that sub-group is refused rather than reclassified.
- Edge colour follows the streams an edge joins: main to main `"4"`, appendix to main `#8a96a1`, appendix to appendix `#c9d2da`. A main card pointing at an appendix card is refused, because that arrow sends the reader out of the argument mid-sentence; evidence points in, as a side card does.
- `move_stream`: `stream`, the destination column `x`, and `node_ids`; optional `appendix_label` when the sub-group does not exist yet. Cards keep their ids and their `y`, so only the column, the sub-group, and the edges around them move. Every edge incident to a moved card is recoloured, and one left pointing the wrong way is turned around rather than refused -- the move is what invalidated it, not the request. When the last appendix card leaves, the sub-group goes with it.
- A card placed past the target group's right or bottom edge grows the group to hold it, so a new question can be appended below an existing flow without resizing anything first. A card placed above or left of the group's origin is refused instead: moving the origin would swallow whatever sits outside.
- `edit_text`: `nodes`, each with `node_id` and the replacement `text`; optional `height`. It rewrites prose and changes nothing else -- kind, colour, and geometry stay as they stand -- which is what settling on a term or polishing a sentence needs. Pass the body; the stamp is handled here, including a stale one carried in from another card. A file node has no text to rewrite.
- `remove_items`: explicit `node_ids` and `edge_ids`. Include every edge incident to a removed node.

## Paper-flow build spec

A paper flow is one Canvas per published paper in the vault-wide `Paper/` folder, laid out for reading beside a research flow. Build it from the Zotero item's stored PDF, or from a reviewed JSON spec:

```bash
python zotero_bridge.py paper-flow <project-folder> <item-key> [--spec-output flow.json] [--contributions b2,b3 | --no-contributions] [--replace]
python obs_paper.py paper-flow-build <project-folder> <paper-flow-spec.json> [--replace]
```

```json
{
  "title": "Verified paper title",
  "citekey": "stableKey",
  "item_key": "ZOTERO1",
  "sections": [
    {
      "key": "s1",
      "title": "Introduction",
      "blocks": [
        {"key": "b1", "kind": "paragraph", "text": "A whole paragraph of the paper."},
        {"key": "b2", "kind": "paragraph", "role": "contribution", "text": "In this paper we propose ..."},
        {"key": "b3", "kind": "heading", "level": 1, "text": "Background"},
        {"key": "b4", "kind": "caption", "text": "Figure 1: ..."},
        {"key": "b5", "kind": "equation", "text": "$$x=1$$"}
      ]
    }
  ]
}
```

Blocks use `heading`, `paragraph`, `caption`, `sentence`, or `equation`. A `paragraph` is one semantic prose block and one card; `sentence` remains for hand-written specs and requires a stable `paragraph` key; equations require `$$` delimiters. A flow `heading` takes an integer `level`, its depth below the section, which indents it and the blocks under it. (A manuscript `heading` block in `insert_blocks` instead takes `level` of `section`, `subsection`, or `paragraph`, which sets its colour.) Only the `paper` colour grammar applies: the title, section titles, and headings are purple `"6"`, a `paragraph` or `sentence` with `role: "contribution"` is green `"4"`, and everything else has no colour. Extra fields such as `page` are ignored.

Each top-level section is one column 812px wide, 120px apart, with card heights from `estimate_text_height`, so no two cards overlap. All cards sit in one group labelled `paper_flow · <title>`, and a source card with the `\cite` command and Zotero link points at the title card. `paper-flow-build` creates `<Vault>/Paper/<sanitized full title>.canvas`, refuses a conflicting overwrite, and `--replace` rebuilds after copying the old Canvas to `Paper/.canvas-history/`. The result's `paper_flow` (the same value as `vault_link`) is what `link_literature` takes as `paper_flow`.

### From a PDF

`paper-flow` reads the Zotero stored PDF with `pdfplumber`, takes the title from Zotero metadata and the citation key from Better BibTeX or Zotero, and never splits a sentence. The full rules are the docstring of `pdf_to_flow.py`; this is the summary.

Reading the page. Only upright characters are read, so the rotated arXiv side stamp and vertical labels never enter the text. A sub- or superscript joins a line only when it sits next to one of that line's characters, so tiny figure labels stay out of body text. A new word starts where the gap between characters exceeds 0.15 of the font size. Words whose vertical centres are within 0.3 of their size form one line, so small capitals stay on their line. A page is two columns when a strip in its middle 30% is crossed by body-size words on at most 15% of body rows; a page that fails this in a two-column document still uses the document's median gutter when most of its rows do not cross it. Words are split at the gutter before lines are formed, full-width lines cut the page into bands, and each band is read left column, then right.

Before blocks are built, and counted in the result's `filtered`: running headers, footers, and page numbers; lines outside the body text's horizontal extent; figure text (lines under 0.8 of body size, or set mostly in a font family that is under 5% of the document and not a math font); table headers (short lines, not numbered headings, of mostly abbreviations in bold or spread apart, or with words more than 2.5 font sizes apart); tables (two or more nearby rows of three or more tokens with at least two numbers, grown to adjacent short lines, plus text inside `find_tables` regions); footnotes (smaller lines under the last body line of their column); and display math.

Title and author block. The largest lines of two or more words on page 1 are the title, continued by close lines at least 0.75 of that size. Everything up to the first named, numbered, or outline heading is the author block and is dropped, except that when that heading is not Abstract, the prose paragraphs right above it are kept as an Abstract section.

Headings. When the PDF has an outline (bookmarks), it is the primary source: each entry is matched to one to three consecutive lines on its destination page or the next whose text, numbering and punctuation ignored, equals the entry, preferring document order and then the line nearest the destination's height. The entry supplies the depth and text, and the outline is used when at least half its entries are found. Lines outside the outline can still be named headings (Abstract, References) or fully bold paragraph headings one level below the current section. Without a usable outline the fonts decide: named sections in bold, larger type, or capitals are top level; a numbered line (`3.2`, and `A`, `A.1` once References has passed or an `A` heading as large as the section headings appears) in bold, larger type, or capitals takes its depth from its dots, in any letter case; an unnumbered line 1.5pt above body size takes its depth from its size tier; a line at least 95% bold of at most eight words is a paragraph heading. A heading needs a word of three letters, does not end in a hyphen or sentence punctuation, has no gaps wider than 1.5 font sizes, sits no closer than three line pitches above a removed table line, and if unnumbered is not mostly abbreviations, numbers, and metric names. Each heading records `source`, `outline` or `font`, and the result counts them under `heading_sources`. Run-in paragraph headings ("Name. Text..." with only the lead in bold) are prose: the lead stays at the start of its paragraph. Repeated headings are kept as they are; nothing is deduplicated. Depth 0 opens a section column; References and Bibliography are left out.

Block boundaries. A heading closes the open block. Otherwise a line starts a new block when (1) it starts a caption (`Figure 3:`, `Fig. 3.`, `Table 2:`) or a list item (`1)`, `2.`, `(a)`, bullet, dash); (2) its font size differs from the previous line by more than 0.5pt; (3) on the same page and column it sits more than 1.4 line pitches below the previous line, the pitch being the median spacing of body lines; or (4) the previous line ends in `.`, `?`, `!`, or `:` and either this line is indented by 0.8 body-font sizes past the column's left edge or the previous line stops two body-font sizes short of the right edge. Rule 3 does not apply across a page or column break. Lines join with spaces; a line ending in a hyphen joins the next without a space, keeping the hyphen when the hyphenated word occurs elsewhere in the document and the joined word does not, and dropping it when the joined word occurs elsewhere or the next line starts in lowercase. A block starting like a caption is kind `caption`, every other block `paragraph`. A fragment (under three words, or a short piece that is neither a list item nor a whole sentence) is joined to the paragraph it continues, before or after, and dropped otherwise.

Contribution cards are marked, not decided. In the Abstract and the section whose title contains "Introduction", a paragraph containing `we propose`, `we introduce`, `we present`, `our contribution(s)`, `main`/`key`/`primary contribution(s)`, `contributions of this/our paper/work`, or `this paper/work proposes/introduces/presents` is green, and so are list items directly after it. The result lists the marked keys under `contributions`. The author reviews them: rerun with `--contributions b2,b3` to colour exactly those paragraph keys, `--no-contributions` to leave everything uncoloured, or edit `role` in the `--spec-output` file and rebuild with `paper-flow-build --replace`.

Limits. Without an outline, heading detection depends on the template setting headings apart by weight, size, capitals, or numbering; a template that sets unnumbered headings in plain body type loses them. A dataset-name paragraph heading made only of abbreviations (`MS COCO`) is not a heading. A centred equation or table cell that shares a row with a column line on a two-column page is read as full width, and three-column layouts are read in the wrong order. Figure text in the body font at body size is kept as paragraphs. Equations are dropped when displayed and kept as extracted text when inline, never as `equation` cards. Code listings and captions set in a rarely used font count as figure text. A paragraph whose last line fills the column and whose next line is neither indented nor spaced apart merges with the next one. Footnotes are dropped, and a references list set as small as footnotes is dropped with them. A PDF with no text layer (a scan) or no detectable headings fails with an error rather than producing a partial flow; OCR it first. Reading a stored PDF needs Zotero Desktop on the same machine, not web mode, and takes several seconds per paper.

## Safe execution

Run `inspect`, `plan`, review the patch, `apply --log CANVAS_ACTION_LOG.md`, `validate`, and a second `plan`. The second plan must contain an empty `operations` list before the next workflow stage mutates that stage's inputs.
