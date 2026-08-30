# Request schema

Use one JSON object:

```json
{
  "schema_version": 1,
  "workflow": "paper",
  "target": {"group_id": "..."},
  "actions": []
}
```

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

`add_research_flow` requires keyed `nodes` and explicit two-key `links`.

- Ordinary node: `key`, `kind`, `text`, `x`, `y`; optional geometry.
- `kind` is one of `rq`, `experiment`, `answer`, `bridge`, `thought` (coloured, in the flow) or `source`, `table`, `figure`, `implementation`, `params`, `log` (uncoloured side cards). Flow kinds get an H1 prefix when the text has no heading; side cards, bridges, and thoughts keep their text verbatim.
- `implementation`: one per experiment, a two-column table of run grid, paths, commands, commits, and outputs, optionally followed by a `**추가 메모**` paragraph. `params`: one per project, the thresholds and model names that hold across experiments. `log`: a run that produced no usable evidence. Record why it was discarded and where its outputs are, but not its measurements: a discarded number is not worth keeping. A discarded run never stays a green experiment in the flow. See `skills/research-flow/references/content-structure.md`.
- Figure: also supply `file`, `width`, and `height`.
- Experiment: optionally supply ordered `sections`, each with `key`, `heading`, `text`, and optional `height`. `heading` must be exactly `Setup` or `Results`. Status, configuration, and scoring parameters belong in the experiment title or an implementation card, never in a section heading. There is no validity section: whether a run was usable is a property of the run, so completeness, robustness, and data-quality checks go in that experiment's implementation card.
- Every managed card is stamped with its own node id as its last line, so a card can be addressed with `obs_paper.py nodes` without searching. The handler adds it; supply text without one. Stamping is idempotent, so a rerun does not duplicate it, and figures carry no text to stamp.
- Link direction: a side card originates its link and points into the flow, because the card being referred to aims at the card that refers to it. Write `["impl", "setup"]`, not `["setup", "impl"]`; the reverse is rejected. Side-card links get geometric sides, flow links run bottom to top. The red `thought` card is the only reverse case: it originates a right-to-left link at whatever it questions.
- `link_literature`: `key`, exact research `target_id`, verified `title`, `citekey`, and Zotero `item_key`; optional existing vault-relative `paper_flow`, `relevance`, `lane`, and explicit geometry. It creates one uncoloured source card and a source-to-question edge. Create separate target-specific cards when one paper supports multiple questions.
- `remove_items`: explicit `node_ids` and `edge_ids`. Include every edge incident to a removed node.

## Paper-flow build spec

After verifying the Zotero stored PDF, create one sentence-level Canvas in the vault-wide `Paper/` folder with:

```json
{
  "title": "Verified paper title",
  "citekey": "stableKey",
  "item_key": "ZOTERO1",
  "sections": [
    {
      "key": "intro",
      "title": "Introduction",
      "blocks": [
        {"key": "s1", "kind": "sentence", "paragraph": "p1", "text": "First original sentence."},
        {"key": "s2", "kind": "sentence", "paragraph": "p1", "text": "Second original sentence."},
        {"key": "sub", "kind": "heading", "level": 1, "text": "Background"},
        {"key": "eq", "kind": "equation", "text": "$$x=1$$"}
      ]
    }
  ]
}
```

A manuscript `heading` block also takes `level` of `section`, `subsection`, or `paragraph`, which sets its colour; headings are never numbered. Blocks use `heading`, `sentence`, or `equation`; sentences require a stable paragraph key, headings may use indentation `level`, and equations require `$$` delimiters. `paper-flow-build` accepts only a reviewed JSON spec, creates `<Vault>/Paper/<sanitized full title>.canvas`, refuses a conflicting overwrite, and links its source card to Zotero. `--replace` intentionally rebuilds after copying the old Canvas to `Paper/.canvas-history/`. Automated PDF parsing is suspended and must not be invoked. A future PDF-flow workflow must use semantic prose blocks and inherit only the `paper` color grammar rather than the manuscript's sentence-splitting rule.

## Safe execution

Run `inspect`, `plan`, review the patch, `apply --log CANVAS_ACTION_LOG.md`, `validate`, and a second `plan`. The second plan must contain an empty `operations` list before the next workflow stage mutates that stage's inputs.
