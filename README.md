# Obs Paper

Obs Paper is a Codex plugin for managing academic-paper workflows in an existing [Obsidian Canvas](https://obsidian.md/canvas).

It provides nine skills:

- `project-library`: unified-vault project setup, migration, Zotero library access, PDF storage, and Canvas citation links
- `overleaf`: copy a LaTeX template into a new Overleaf project and pull the manuscript source down
- `paper`: sentence-level manuscript layout inside versioned paper groups
- `research-flow`: RQ, experiment, evidence, and interpretation graphs
- `node`: answer questions about specific cards addressed by their node IDs, fetched by direct lookup
- `literature-flow`: RQ-targeted search, Zotero PDF ingestion, and citation mapping; PDF-to-flow conversion is suspended
- `rebuttal`: reviewer comments organized from source text through final English response
- `camera-ready-mapping`: non-destructive mapping from rebuttal promises to manuscript targets
- `camera-ready`: final manuscript generation from a completed mapping, with yellow diff nodes and explicit blockers

## Install in Codex

```bash
codex plugin marketplace add seonghyeoncho/obs-paper --ref main
codex plugin add obspaper@obs-paper
```

Start a new Codex task after installation so the skills are loaded.

### Update Codex

```bash
codex plugin marketplace upgrade obs-paper
codex plugin add obspaper@obs-paper
```

Start a new Codex task after updating.

## Install in Claude Code

```bash
claude plugin marketplace add seonghyeoncho/obs-paper
claude plugin install obspaper@obs-paper --scope user
```

Start a new Claude Code session after installation, or run `/reload-plugins` in an existing session.

### Update Claude Code

```bash
claude plugin marketplace update obs-paper
claude plugin update obspaper@obs-paper
```

Restart Claude Code after updating.

The plugin was called `paper-canvas-workflow` before 0.9.0. A rename does not upgrade in place, so remove the old one first:

```bash
claude plugin uninstall paper-canvas-workflow@obs-paper
```

## What it edits

The plugin can initialize or import `<Vault>/Projects/<Project>/`, works with its `.canvas` file, and records material operations in the adjacent `CANVAS_ACTION_LOG.md`. It is installed in Codex, not in Obsidian's Community Plugins directory.

## Unified vault and Zotero

```bash
python plugins/obspaper/scripts/obs_paper.py vault-config /path/to/vault --name "Research"
python plugins/obspaper/scripts/obs_paper.py vault-path
python plugins/obspaper/scripts/obs_paper.py project-init /path/to/vault "My Project" --repository /path/to/repo
python plugins/obspaper/scripts/obs_paper.py project-import /path/to/vault "My Project" source.canvas --repository /path/to/repo
python plugins/obspaper/scripts/obs_paper.py project-standardize /path/to/vault "My Project"
python plugins/obspaper/scripts/zotero_bridge.py status
python plugins/obspaper/scripts/zotero_bridge.py project-setup "/path/to/vault/Projects/My Project"
python plugins/obspaper/scripts/zotero_bridge.py search "paper title"
python plugins/obspaper/scripts/zotero_bridge.py record-search "/path/to/vault/Projects/My Project" search.json
python plugins/obspaper/scripts/zotero_bridge.py attach ZOTERO_ITEM_KEY paper.pdf
python plugins/obspaper/scripts/zotero_bridge.py audit "/path/to/vault/Projects/My Project"
python plugins/obspaper/scripts/obs_paper.py paper-flow-build "/path/to/vault/Projects/My Project" paper-flow.json
```

The configured path is stored per host in `~/.config/obs-paper/config.json`, outside Obsidian Sync. Set `OBS_PAPER_VAULT` to override it temporarily.

Each project uses an exact-name Zotero Collection as its literature source of truth. Selected papers and their stored PDF attachments live in Zotero, vault-wide sentence-level paper Canvases live under `Paper/`, only the project Collection is exported to `references.bib`, and searches are appended to `searches.jsonl`. No paper PDF is copied into Obsidian. Export is blocked if it would remove a citation key already used by the project. The Zotero bridge uses the desktop Local API. Reads require no account API key; Zotero 10+ writes request approval in Zotero at runtime. Because that API answers on `localhost:23119` only, a machine without Zotero Desktop — a remote server — sets `ZOTERO_USER_ID` and `ZOTERO_API_KEY` to reach the library over zotero.org instead. Web mode searches, cites, and exports BibTeX; storing and reading PDFs stays on the desktop that holds the files. Better BibTeX is optional and preferred for stable LaTeX citation keys. External scholarly search remains separate from Zotero library search.

## Deterministic Canvas CLI

The CLI compiles a human-readable JSON request into a SHA-bound Canvas patch, applies it atomically with a timestamped backup, and supports deterministic reruns.

`nodes` reads cards by exact ID, returning each card's text, group, colour, geometry, and edges on both sides. `edit_text` writes the other way, replacing a card's prose while leaving its kind, colour, and geometry alone, so settling on a term across a flow does not mean re-declaring every card that uses it. Managed research-flow cards print their own ID as their last line, so a card can be addressed without searching the Canvas.

```bash
python plugins/obspaper/scripts/obs_paper.py nodes "/path/to/Project.canvas" rfparams00000001 rfanswer1rq10001
```

## LaTeX

`paper_tex.py` assembles a `paper_vN` group into a LaTeX body — abstract, headings whose depth comes from the card's colour, paragraphs from the 20/40px gaps, Markdown tables as `booktabs` tabulars, and image cards as figures. Section numbers and cross-references are generated, so the Canvas never states a number that could go stale. An artifact too wide for one column becomes a starred float.

```bash
python plugins/obspaper/scripts/paper_tex.py "/path/to/Project.canvas" --group paper_v1 --out main.tex
```

Each table is written to `tables/tableN.tex` beside it and the body keeps a one-line `\input`, so a seventeen-row tabular does not bury the prose around it. Appendix material — anything in a Canvas sub-group labelled for an appendix — goes to `appendix.tex`. It emits a body fragment, not a whole document: the template keeps the preamble, author block, and bibliography. `paper_pull.py` runs the other way: it compares a manuscript pulled from Overleaf against the Canvas and names the card behind each changed paragraph. It reports only — turning a LaTeX edit back into prose cards is a judgement, so the cards are named and you edit them.

## Overleaf

Overleaf publishes no project API, and its git and Zotero integrations are paid-only. `overleaf.py` therefore drives Overleaf as authenticated HTTP inside a signed-in [Aside](https://docs.aside.com) browser session, which needs the Aside CLI installed. A new project is a copy of your own LaTeX template rather than a blank project, so it arrives with its document class and bibliography file already in place.

```bash
python plugins/obspaper/scripts/overleaf.py list
python plugins/obspaper/scripts/overleaf.py clone <template_id> --name '[ARR 10] Paper Title'
python plugins/obspaper/scripts/overleaf.py download <project_id> --out paper.zip
```

Record the resulting project id as `overleaf_project` in the project's `project.md`. Putting the generated file into Overleaf is left to the author on purpose: the upload endpoint needs a folder id only Overleaf's websocket exposes, so automating it would mean driving the browser — the one non-deterministic step in an otherwise verifiable pipeline — and Overleaf drops comments and track changes on external writes.

| Workflow | Actions |
|---|---|
| `paper` | `group_appendix`, `insert_blocks`, `place_artifact`, `pair_appendix_columns`, `split_citation`, `connect_reference`, `fit_section_title`, `move_nodes`, `shift_sibling_group`, `normalize_equations`, `normalize_paper_colors`, `compact_sections` |
| `camera-ready-mapping` | `mapping_master`, `map_issue`, `remove_items` |
| `camera-ready` | `build_camera_ready` |
| `rebuttal` | `layout_rebuttal` |
| `research-flow` | `add_research_flow`, `edit_text`, `link_literature`, `remove_items` |

```json
{
  "schema_version": 1,
  "workflow": "paper",
  "target": {"group_label": "paper_v1"},
  "actions": [
    {
      "op": "group_appendix",
      "group_id": "existing-group-id-if-any",
      "label": "Results · Appendix B–H",
      "member_ids": ["appendix-heading-id", "sentence-or-artifact-id"],
      "padding": 20
    }
  ]
}
```

`insert_blocks` places keyed prose cards after an exact anchor, shifts an explicit downstream-node set, and optionally refits its Appendix group:

```json
{
  "op": "insert_blocks",
  "anchor_id": "exact-node-id",
  "blocks": [
    {"key": "human-audit-method", "kind": "sentence", "text": "...", "width": 812}
  ],
  "shift_node_ids": ["next-sentence-id", "later-artifact-id"],
  "fit_group_id": "section-appendix-group-id"
}
```

Supported block kinds are `sentence`, `paragraph`, `heading`, and `equation`. Use `place_artifact` for complete Markdown tables or figure files outside the prose stack.

Every destructive migration uses explicit node and edge IDs. `remove_items` rejects deletion when an incident edge is missing from the request. `build_camera_ready` can reuse an existing final-group ID, remove stale contained content, exclude mapping cards, and apply yellow changes, additions, and author-input blockers.

`map_issue` produces a compact orange cluster: one title plus separate Asked, Evidence, Status, Done when, and Change nodes. It accepts exactly one manuscript target and connects only the title. Paper references infer left/right or top/bottom ports from the dominant geometric direction.

```bash
python plugins/obspaper/scripts/obs_paper.py inspect paper.canvas --group-label paper_v1
python plugins/obspaper/scripts/obs_paper.py plan paper.canvas request.json --output patch.json
python plugins/obspaper/scripts/obs_paper.py apply paper.canvas patch.json --log CANVAS_ACTION_LOG.md
python plugins/obspaper/scripts/obs_paper.py validate paper.canvas
```

Re-running `plan` after a successful apply must produce an empty `operations` array.
