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

Repository paths are host-specific. `repository` in `project.md` is a string when one host has recorded its checkout and a list once more than one has, and `project-resolve --repository` matches any entry. Record a checkout with `project-resolve <vault> --name <project> --add-repository <path>`; it appends and never replaces the path another host wrote. When a repository matches no project, the error lists every project and what it records. Ask which project it is. Never pick one by searching Canvas text: two flows can share RQ labels.

## Canvas writer rule

Obsidian Sync transports Canvas files but does not semantically merge them. Treat every `.canvas` file as single-writer state.

Before mutation:

1. Confirm Sync has finished receiving changes on the current host.
2. Confirm no other host or agent is editing the same Canvas: this device holds its lease (see Writer lease).
3. Re-read and validate the current Canvas, then create the normal `.canvas-history/` backup and action-log entry.

After mutation:

1. Apply through the deterministic obs-paper engine and validate the result.
2. Confirm Sync has uploaded the change before another host becomes the writer.
3. On the next host, wait for that revision to arrive and re-read it before editing.

Do not rely on `merge` or conflict-file settings to reconcile concurrent Canvas edits. If writer ownership is uncertain, stop before mutation.

## Writer lease

Writer ownership is recorded, not agreed in conversation. Every host that has the vault may write, but only while it holds the lease on that Canvas.

The lease lives in `CANVAS_LEASE.md` beside the Canvas and its `CANVAS_ACTION_LOG.md`, so for a project Canvas that is `<Vault>/Projects/<Project>/CANVAS_LEASE.md`. It is Markdown on purpose: Obsidian Sync skips dot-files and dot-folders, and syncs other file types only when that setting is on. Each frontmatter line is one Canvas in that folder, keyed by its file name, with a JSON value:

```text
---
"Honorific.canvas": {"canvas": "Honorific.canvas", "device": "sh_con", "acquired_at": "2026-09-15T09:00:00Z", "expires_at": "2026-09-15T09:30:00Z", "purpose": "RQ2 cards"}
---
```

Times are UTC. Never edit the file by hand. The commands:

```bash
python obs_paper.py lease acquire <canvas> [--minutes 30] [--purpose "RQ2 cards"]
python obs_paper.py lease status <canvas>
python obs_paper.py lease release <canvas> [--force]
```

- `acquire` refuses while another device holds an unexpired lease, naming the device and the expiry. Run again by the holder, it renews: `expires_at` moves, `acquired_at` stays.
- An expired lease counts as none, so a host that died does not lock the Canvas for good.
- `release` gives back this device's lease. Releasing another device's unexpired lease needs `--force`, which is logged in `CANVAS_ACTION_LOG.md`. Forcing is the user's decision; an agent never forces a release.
- If Sync merges two hosts' simultaneous acquires into two lines for one Canvas, each host sees the other's line and both are refused until one releases or expires.

The device name is `OBS_PAPER_DEVICE`, else `device` in the obs-paper config (`vault-config <path> --device <name>`), else the hostname. Set it to the same fixed name given to `ob sync-setup --device-name`, so the name in a lease is the device the user sees in Sync.

`apply` checks the lease right after the Canvas hash. It refuses when another device holds the lease. With no lease, it refuses if `project.md` sets `canvas_lease: required`; otherwise it applies and adds a `warning` to its result, so a single-machine project keeps working. Every project written from more than one host should set `canvas_lease: required`. `run` does not take a lease for you, because a lease taken and used in the same second has not reached the other hosts yet.

A lease protects only once every host has it. The order on the writing host is:

1. `lease acquire`, then wait until Sync has uploaded `CANVAS_LEASE.md` (the `ob sync` output on a server, the Sync indicator on a desktop).
2. `lease status` again; continue only if it still says `held-by-me`.
3. Confirm Sync has also finished receiving, then inspect, plan, apply with `--log`, validate, and plan again.
4. Wait for Sync to upload the Canvas, then `lease release`. Renew with `acquire` if the work outlasts the lease.

A host that cannot run headless Sync can still write request JSON and hand it to a host that holds the lease.

## Preflight

Run `obs_paper.py preflight` first on any host, from inside the research repository. It reads local state and the lease file, never writes, and answers whether this device may write the project's Canvas now:

```text
can_write          true when apply would be allowed now
blocked_by         null, no-vault, vault-error, project-unmapped, lease-required, lease-held-by-other, or lease-unreadable
device             name and source (OBS_PAPER_DEVICE, config, or hostname)
vault              resolved, path, source, error
config             path, exists
obsidian_cli       executable, found
obsidian_headless  found (whether `ob` is installed)
repository         the enclosing git checkout
project            null without a vault; else resolved, project, root, canvas, repositories, groups (id, label), error
lease              null until a project resolves; else state (free, held-by-me, held-by-other, expired), holder,
                   acquired_at, expires_at, purpose, required, lease_file
next_steps         what to do: set up headless Sync, record the repository, acquire, wait, or ask the user
```

Nothing about the host's role is asked of the user; it follows from these fields.

## Server operation

Use `obsidian-headless` only on the server-side local copy of the active vault. Do not run desktop Sync and Headless Sync against the same local folder on one device. Keep the server device name stable, run continuous sync when the server is expected to receive changes, and verify status before and after an agent writes Canvas.

A server with the repository but no vault gets one this way, so an agent there can inspect and apply its own requests. The setup needs Node 22 or later:

```bash
npm install -g obsidian-headless
ob login                                   # the user runs this
ob sync-setup --device-name <stable-name>
ob sync --continuous                       # without systemd, run it as a background process
python obs_paper.py vault-config /absolute/path/to/local-vault
```

Use the same `<stable-name>` for `vault-config --device`, or in `OBS_PAPER_DEVICE`, so leases name this device the way Sync does.

Approval boundary: an agent may propose this setup and, once the user approves, install `obsidian-headless` and run the other steps. `ob login` takes the Obsidian account credentials, so the user always runs it; an agent never asks for, reads, stores, or types them. An agent also never force-releases another device's lease.

Agent skills and executables live outside the vault and must be installed or updated separately on each server.
