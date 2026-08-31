# Obsidian Sync Topology

Use Obsidian Sync as the only synchronization service for the active research vault.

```text
Obsidian Sync remote vault
├── Mac and iPad: Obsidian
└── remote servers: obsidian-headless

iCloud
└── separate archive vault for inactive projects
```

Never place the active Sync vault inside iCloud Drive or let iCloud, Git, Syncthing, or another sync service manage the same files. Archiving means copying a completed project into the separate iCloud archive, verifying the copy, and then removing it from the active vault after Sync has settled. It does not mean enabling two sync services on one vault.

## Storage boundary

Keep the active vault small:

- Canvas, Markdown, project bibliography, search log, and low-resolution Canvas previews belong in the active vault.
- Zotero remains the only PDF store.
- Source code, datasets, checkpoints, raw experiment outputs, logs, and publication-quality figures remain in their research repositories.
- Copy only an artifact that must be displayed in Canvas into the project's `assets/` folder. For the 1 GB Sync plan, keep every synced file below the plan's 5 MB per-file limit.

The vault-level `Paper/` library contains only paper-flow Canvases needed by active projects. Move inactive project material to the archive without breaking paper-flow links still used by an active project.

## Hosts and repositories

Sync distributes vault files, not research repositories, Claude or Codex sessions, SSH credentials, or agent plugins. Install the obs-paper plugin on every host that may edit the vault and keep each research repository separately available on that host.

Register each host's local Sync folder once; never copy another user's absolute path:

```bash
python obs_paper.py vault-config /absolute/path/to/local-vault --name "Research"
python obs_paper.py vault-path
```

This writes `~/.config/obs-paper/config.json`, outside the vault. `OBS_PAPER_VAULT` overrides it for an ephemeral session. With no setting, desktop auto-discovery is allowed only when the official Obsidian CLI reports exactly one vault.

Repository paths are host-specific. Never trust an absolute `repository` value written by another host. Project metadata and resolution must support a path for the current host before remote execution becomes automatic; until then, require an explicit project and repository path.

## Canvas writer rule

Obsidian Sync transports Canvas files but does not semantically merge them. Treat every `.canvas` file as single-writer state.

Before mutation:

1. Confirm Sync has finished receiving changes on the current host.
2. Confirm no other host or agent is editing the same Canvas.
3. Re-read and validate the current Canvas, then create the normal `.canvas-history/` backup and action-log entry.

After mutation:

1. Apply through the deterministic obs-paper engine and validate the result.
2. Confirm Sync has uploaded the change before another host becomes the writer.
3. On the next host, wait for that revision to arrive and re-read it before editing.

Do not rely on `merge` or conflict-file settings to reconcile concurrent Canvas edits. If writer ownership is uncertain, stop before mutation.

## Server operation

Use `obsidian-headless` only on the server-side local copy of the active vault. Do not run desktop Sync and Headless Sync against the same local folder on one device. Keep the server device name stable, run continuous sync when the server is expected to receive changes, and verify status before and after an agent writes Canvas.

Agent skills and executables live outside the vault and must be installed or updated separately on each server.
