# Obs Paper

Obs Paper is a Codex plugin for managing academic-paper workflows in an existing [Obsidian Canvas](https://obsidian.md/canvas).

It provides four skills:

- `paper`: sentence-level manuscript layout inside versioned paper groups
- `research-flow`: RQ, experiment, evidence, and interpretation graphs
- `rebuttal`: reviewer comments organized from source text through final English response
- `camera-ready-mapping`: non-destructive mapping from rebuttal promises to manuscript targets

## Install in Codex

```bash
codex plugin marketplace add seonghyeoncho/obs-paper --ref main
codex plugin add paper-canvas-workflow@obs-paper
```

Start a new Codex task after installation so the skills are loaded.

### Update Codex

```bash
codex plugin marketplace upgrade obs-paper
codex plugin add paper-canvas-workflow@obs-paper
```

Start a new Codex task after updating.

## Install in Claude Code

```bash
claude plugin marketplace add seonghyeoncho/obs-paper
claude plugin install paper-canvas-workflow@obs-paper --scope user
```

Start a new Claude Code session after installation, or run `/reload-plugins` in an existing session.

### Update Claude Code

```bash
claude plugin marketplace update obs-paper
claude plugin update paper-canvas-workflow@obs-paper
```

Restart Claude Code after updating.

## What it edits

The plugin works with existing `.canvas` files and records material operations in an adjacent `CANVAS_ACTION_LOG.md`. It is installed in Codex, not in Obsidian's Community Plugins directory.
