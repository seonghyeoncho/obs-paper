# Migrate an Existing Project

Use this workflow whenever any Canvas, PDFs, bibliography, search history, or Zotero project Collection already exists.

## Preflight

Identify the exact source Canvas, source project folder, research repository, existing `.bib`, PDF files, search log, and Zotero Collection before changing anything. Stop on an ambiguous project name, duplicate exact-name top-level Zotero Collections, a non-empty destination Canvas, missing Canvas file references, or asset filename collisions.

## Import the Canvas safely

For a Canvas outside the unified vault:

```bash
python ../../scripts/obs_paper.py project-import <vault> <project> <source.canvas> --repository <repo>
```

This requires an empty destination Canvas, copies referenced files into `assets/`, rewrites file nodes to vault-relative paths, and preserves the source. If the project is already under `<vault>/Projects/<project>/`, use idempotent `project-init` only to create missing support files; never import the Canvas onto itself.

When an in-vault project still references files from the vault root or another project, standardize it instead:

```bash
python ../../scripts/obs_paper.py project-standardize <vault> <project> --repository <repo>
```

The command preflights every project Canvas before mutation, preserves a single legacy main-Canvas filename in `project.md`, copies external file-node targets into the project's `assets/` folder, rewrites the Canvas references, and creates `.canvas-history/` backups. After all projects are standardized, remove a vault-root asset only when no Canvas references it and an external archive copy has been verified.

Before Zotero setup, preserve an existing project bibliography as `<project-folder>/references.bib`. Preserve existing `searches.jsonl` records by appending valid JSON lines; never overwrite them. Move per-literature Canvases to the shared `<Vault>/Paper/` library after checking filename collisions. Import every legacy project PDF into its Zotero parent item and verify the stored attachment before removing the Obsidian copy. Do not concatenate bibliographies blindly because duplicate citation keys can mask conflicts.

## Populate Zotero without intermediate exports

Bind the exact-name project Collection:

```bash
python ../../scripts/zotero_bridge.py project-setup <project-folder> --defer-export
```

Deferred setup binds the Collection without touching the preserved bibliography. For every existing paper, use one of:

```bash
python ../../scripts/zotero_bridge.py save <project-folder> <item-key> --defer-export
python ../../scripts/zotero_bridge.py add <project-folder> <metadata.json> <paper.pdf> --defer-export
```

Use `save` for an existing Zotero item and `add` only with verified metadata and a lawful PDF. Deferred export prevents a partially populated Collection from replacing the working bibliography.

## Finalize once

After all retained papers are in the project Collection:

```bash
python ../../scripts/zotero_bridge.py export <project-folder>
python ../../scripts/zotero_bridge.py audit <project-folder>
```

The exporter refuses to replace `references.bib` if the Collection would remove a citation key currently used by the project. Migration is complete only when the final audit has no missing keys and the source material remains intact.
