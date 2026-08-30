# New Project

Use this workflow only when the project has no existing Canvas or literature state to preserve.

## Create the project

```bash
python ../../scripts/obs_paper.py project-init <vault> <project> --repository <repo>
python ../../scripts/zotero_bridge.py project-setup <vault>/Projects/<project>
```

`project-init` creates the project Canvas, metadata, action log, `assets/`, `papers/`, `references.bib`, and `searches.jsonl`. It is idempotent and never overwrites an existing Canvas or metadata file. `project-setup` creates or reuses one exact-name top-level Zotero Collection and stores its key in `project.md`.

## Add literature

For each search, record the query before adding selected papers:

```bash
python ../../scripts/zotero_bridge.py record-search <project-folder> <search-record.json>
python ../../scripts/zotero_bridge.py add <project-folder> <metadata.json> <paper.pdf>
```

Use `save <project-folder> <item-key>` instead of `add` when the verified paper already exists in Zotero. Both commands add the item to the project Collection, copy its PDF into `papers/`, and refresh `references.bib`.

Finish by running:

```bash
python ../../scripts/zotero_bridge.py audit <project-folder>
```

The project is ready when the Canvas and support files exist, the Zotero Collection is bound in `project.md`, and the citation audit has no missing keys.
