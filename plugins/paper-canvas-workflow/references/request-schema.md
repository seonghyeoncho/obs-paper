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

- `group_appendix`: `label`, `member_ids`; optional `group_id`, `padding`, `color`.
- `insert_blocks`: `anchor_id`, `blocks`; optional `shift_node_ids`, `fit_group_id`, `gap`, `gap_after`. Every block has `key`, `text`, and `kind` (`sentence`, `paragraph`, `heading`, `equation`); geometry and color are optional.
- `place_artifact`: `key`, `kind` (`figure` or `table`), `mention_ids`, `lane`, `width`, `height`; a figure has `file`, a table has complete Markdown `text`.
- `pair_appendix_columns`: `sections`. Every section has `key`, `label`, `x`, `y`, and ordered `blocks` of explicit member-ID lists; optional `group_id`, `gap`, `padding`.
- `split_citation`: `key`, `sentence_id`, exact `command`; optional `lane`, `width`, `height`, `gap`, `node_id`.
- `connect_reference`: `key`, `kind`, `source_id`, `target_ids`. Ports follow the dominant center-to-center axis automatically. Supply both `from_side` and `to_side` only for an intentional override; set `curved: true` when that override is not center-aligned.
- `fit_section_title`: `title_id`, `member_ids` for the complete semantic section rectangle, excluding mapping annotations.
- `move_nodes`: `anchor_id`, complete `node_ids`, destination `x`, `y`. The destination is absolute and rerunnable.
- `shift_sibling_group`: sibling `group_id` and absolute `x`, `y`. The complete contained group moves rigidly.
- `normalize_equations`: explicit `node_ids` whose text is fenced `math` or already `$$...$$`.

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

`layout_rebuttal` requires `reviewer`, `x`, `y`, and ordered `rows`. Every row has a stable `key` and exactly six `stages` in English, Korean, memo, Korean rebuttal, English draft, and English final order.

## Research-flow action

`add_research_flow` requires keyed `nodes` and explicit two-key `links`.

- Ordinary node: `key`, `kind`, `text`, `x`, `y`; optional geometry.
- Figure: also supply `file`, `width`, and `height`.
- Experiment: optionally supply ordered `sections`, each with `key`, `heading`, `text`, and optional `height`.

## Safe execution

Run `inspect`, `plan`, review the patch, `apply --log CANVAS_ACTION_LOG.md`, `validate`, and a second `plan`. The second plan must contain an empty `operations` list before the next workflow stage mutates that stage's inputs.
