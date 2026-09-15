#!/usr/bin/env python3
"""Answer, for a fresh agent, whether this host may write its project's Canvas now."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from canvas_lease import LEASE_FILE, LeaseError, device_name, lease_status, write_permission
from obs_project import ProjectError, VaultUnavailable, _vault_config_path, resolve_project, resolve_vault


def _repository_root(path: Path) -> Path:
    """The enclosing git checkout, so preflight from a subfolder maps the same way."""
    resolved = path.expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved


def _vault_source(config_path: Path | None) -> str:
    if os.environ.get("OBS_PAPER_VAULT"):
        return "OBS_PAPER_VAULT"
    if _vault_config_path(config_path).exists():
        return "config"
    return "obsidian-cli"


def _canvas_groups(canvas: Path) -> list[dict[str, Any]]:
    data = json.loads(canvas.read_text(encoding="utf-8"))
    return [
        {"id": node.get("id"), "label": node.get("label")}
        for node in data.get("nodes", [])
        if isinstance(node, dict) and node.get("type") == "group"
    ]


def preflight(
    repository: Path,
    *,
    executable: str = "obsidian",
    config_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Report vault, project, and lease for this host. A missing vault is an answer, not an error."""
    repo = _repository_root(repository)
    config = _vault_config_path(config_path)
    try:
        device, device_source = device_name(config_path)
    except LeaseError as exc:
        device, device_source = None, str(exc)
    vault: dict[str, Any] = {"resolved": False, "path": None, "source": None, "error": None}
    blocked_by: str | None = None
    try:
        path = resolve_vault(None, executable, config_path)
        vault.update(resolved=True, path=str(path), source=_vault_source(config_path))
    except VaultUnavailable as exc:
        vault["error"], blocked_by = str(exc), "no-vault"
    except ProjectError as exc:
        vault["error"], blocked_by = str(exc), "vault-error"

    project: dict[str, Any] | None = None
    lease: dict[str, Any] | None = None
    if vault["resolved"]:
        try:
            project = {"resolved": True, **resolve_project(Path(vault["path"]), repository=repo), "error": None}
            project["groups"] = _canvas_groups(Path(project["canvas"]))
        except (ProjectError, OSError, ValueError) as exc:
            project, blocked_by = {"resolved": False, "error": str(exc)}, "project-unmapped"
    if project and project["resolved"]:
        try:
            status = lease_status(Path(project["canvas"]), device=device, now=now, config_path=config_path)
            error, _ = write_permission(status)
            lease = {key: status[key] for key in ("state", "holder", "acquired_at", "expires_at", "purpose", "required", "lease_file")}
            if error:
                blocked_by = "lease-held-by-other" if status["state"] == "held-by-other" else "lease-required"
        except LeaseError as exc:
            lease, blocked_by = {"state": "unreadable", "error": str(exc)}, "lease-unreadable"

    return {
        "can_write": blocked_by is None,
        "blocked_by": blocked_by,
        "device": {"name": device, "source": device_source},
        "vault": vault,
        "config": {"path": str(config), "exists": config.exists()},
        "obsidian_cli": {"executable": executable, "found": shutil.which(executable) is not None},
        "obsidian_headless": {"found": shutil.which("ob") is not None},
        "repository": str(repo),
        "project": project,
        "lease": lease,
        "next_steps": _next_steps(blocked_by, device, vault, project, lease, repo, config),
    }


def _next_steps(
    blocked_by: str | None,
    device: str | None,
    vault: dict[str, Any],
    project: dict[str, Any] | None,
    lease: dict[str, Any] | None,
    repo: Path,
    config: Path,
) -> list[str]:
    name = device or "<device-name>"
    if blocked_by == "no-vault":
        return [
            "This host has no vault. Propose giving it one with obsidian-headless and wait for the user's approval",
            "After approval: install Node 22 or later, then `npm install -g obsidian-headless`",
            "Ask the user to run `ob login` themselves; never ask for, read, or type Obsidian account credentials",
            f"`ob sync-setup --device-name {name}`, then run `ob sync --continuous` in the background",
            f"`obs_paper.py vault-config /absolute/path/to/local-vault --device {name}` so leases carry the same device name",
            "If a synced vault folder already exists on this host, only the vault-config step is needed",
        ]
    if blocked_by == "vault-error":
        return [f"A vault is configured but did not resolve; fix {config} or the path it names, or rerun vault-config"]
    if blocked_by == "project-unmapped":
        return [
            "No project records this repository. Ask the user which project it belongs to; do not pick one from Canvas text",
            f"Record it: `obs_paper.py project-resolve {vault['path']} --name <project> --add-repository {repo}`",
        ]
    if blocked_by == "lease-unreadable":
        return [f"The lease file could not be read ({lease and lease.get('error')}); ask the user before writing"]
    assert project is not None and lease is not None
    canvas = project["canvas"]
    sync = (
        "Before writing, confirm Sync has settled on this host (the `ob sync` output on a server, the Sync "
        f"indicator on a desktop); a lease protects only once {LEASE_FILE} has reached every host"
    )
    if blocked_by == "lease-held-by-other":
        purpose = f" for {lease['purpose']!r}" if lease.get("purpose") else ""
        return [
            f"Device {lease['holder']!r} holds the lease{purpose} until {lease['expires_at']}; do not write",
            "Wait until then and run preflight again, or ask the user. Never release another device's lease; --force is the user's call",
        ]
    acquire = [
        f"`obs_paper.py lease acquire {canvas} --purpose <what you are about to change>`",
        f"Wait until Sync has uploaded {LEASE_FILE}, then run `obs_paper.py lease status {canvas}` and continue only if it is still held-by-me",
        sync,
        f"inspect, plan, apply --log, validate, plan again; then `obs_paper.py lease release {canvas}` once Sync has uploaded the Canvas",
    ]
    if blocked_by == "lease-required":
        return ["project.md sets canvas_lease: required and this device holds no lease", *acquire]
    if lease["state"] == "held-by-me":
        return [
            f"This device holds the lease until {lease['expires_at']}; renew with lease acquire if the work will take longer",
            sync,
            f"inspect, plan, apply --log, validate, plan again; then `obs_paper.py lease release {canvas}` once Sync has uploaded the Canvas",
        ]
    return [
        "apply is allowed without a lease because project.md does not set canvas_lease: required",
        "If any other host writes this Canvas, take a lease anyway and ask the user to set canvas_lease: required",
        *acquire,
    ]
