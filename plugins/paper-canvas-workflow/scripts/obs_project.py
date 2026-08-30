#!/usr/bin/env python3
"""Create, import, and resolve projects in one Obsidian vault."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from record_action import append_action


class ProjectError(ValueError):
    """A project operation is ambiguous or unsafe."""


def _project_name(name: str) -> str:
    value = name.strip()
    if not value or value in {".", ".."} or any(part in value for part in ("/", "\\", "\0")):
        raise ProjectError("project name must be one folder name")
    return value


def project_root(vault: Path, name: str) -> Path:
    return vault.resolve() / "Projects" / _project_name(name)


def _metadata(name: str, repository: Path | None) -> str:
    repo = str(repository.resolve()) if repository else ""
    return (
        "---\n"
        f"project: {json.dumps(name, ensure_ascii=False)}\n"
        f"repository: {json.dumps(repo, ensure_ascii=False)}\n"
        f"canvas: {json.dumps(name + '.canvas', ensure_ascii=False)}\n"
        'papers: "papers"\n'
        'assets: "assets"\n'
        'bibliography: "references.bib"\n'
        'search_log: "searches.jsonl"\n'
        'zotero_collection: ""\n'
        "---\n\n"
        f"# {name}\n"
    )


def init_project(vault: Path, name: str, repository: Path | None = None) -> dict[str, Any]:
    if not vault.is_dir():
        raise ProjectError(f"vault does not exist: {vault}")
    name = _project_name(name)
    root = project_root(vault, name)
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for folder in ("assets", "papers"):
        path = root / folder
        if not path.exists():
            path.mkdir()
            created.append(str(path))

    canvas = root / f"{name}.canvas"
    if not canvas.exists():
        canvas.write_text('{\n\t"nodes":[],\n\t"edges":[]\n}\n', encoding="utf-8")
        created.append(str(canvas))

    metadata = root / "project.md"
    if not metadata.exists():
        metadata.write_text(_metadata(name, repository), encoding="utf-8")
        created.append(str(metadata))

    for filename in ("references.bib", "searches.jsonl"):
        path = root / filename
        if not path.exists():
            path.touch()
            created.append(str(path))

    log = root / "CANVAS_ACTION_LOG.md"
    if not log.exists():
        log.touch()
        append_action(
            log,
            status="done",
            action="initialize-project",
            target=str(root),
            reason="Unified NLP vault project structure",
            result=f"Created {name}.canvas, project.md, references.bib, searches.jsonl, assets/, and papers/",
        )
        created.append(str(log))

    return {
        "status": "created" if created else "exists",
        "project": name,
        "root": str(root),
        "canvas": str(canvas),
        "created": created,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_project(
    vault: Path,
    name: str,
    source_canvas: Path,
    repository: Path | None = None,
) -> dict[str, Any]:
    if not source_canvas.is_file():
        raise ProjectError(f"source Canvas does not exist: {source_canvas}")
    data = json.loads(source_canvas.read_text(encoding="utf-8"))
    if not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
        raise ProjectError("source Canvas needs nodes and edges arrays")

    root = project_root(vault, name)
    canvas = root / f"{_project_name(name)}.canvas"
    if canvas.exists():
        current = json.loads(canvas.read_text(encoding="utf-8"))
        if current.get("nodes") or current.get("edges"):
            raise ProjectError(f"destination Canvas is not empty: {canvas}")

    references: list[tuple[dict[str, Any], Path, Path]] = []
    for node in data["nodes"]:
        if node.get("type") != "file" or not isinstance(node.get("file"), str):
            continue
        source = Path(node["file"])
        if not source.is_absolute():
            source = source_canvas.parent / source
        source = source.resolve()
        if not source.is_file():
            raise ProjectError(f"missing Canvas file reference: {node['file']}")
        destination = root / "assets" / source.name
        if destination.exists() and _sha256(destination) != _sha256(source):
            raise ProjectError(f"asset name collision: {destination.name}")
        references.append((node, source, destination))

    result = init_project(vault, name, repository)
    root, canvas = Path(result["root"]), Path(result["canvas"])
    copied: list[str] = []
    vault_root = vault.resolve()
    for node, source, destination in references:
        if not destination.exists():
            shutil.copy2(source, destination)
            copied.append(str(destination))
        node["file"] = destination.relative_to(vault_root).as_posix()

    canvas.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_action(
        root / "CANVAS_ACTION_LOG.md",
        status="done",
        action="import-project",
        target=str(canvas),
        reason=str(source_canvas),
        result=f"Imported {len(data['nodes'])} nodes, {len(data['edges'])} edges, and {len(copied)} assets",
    )
    return {
        **result,
        "status": "imported",
        "nodes": len(data["nodes"]),
        "edges": len(data["edges"]),
        "assets": copied,
    }


def _frontmatter_value(path: Path, key: str) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            break
        if line.startswith(f"{key}:"):
            value = line.split(":", 1)[1].strip()
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, str) else None
            except json.JSONDecodeError:
                return value.strip('"\'')
    return None


def set_frontmatter_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ProjectError(f"missing YAML frontmatter: {path}")
    encoded = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            lines.insert(index, encoded)
            break
        if line.startswith(f"{key}:"):
            lines[index] = encoded
            break
    else:
        raise ProjectError(f"unterminated YAML frontmatter: {path}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_project(vault: Path, *, name: str | None = None, repository: Path | None = None) -> dict[str, str]:
    projects = vault.resolve() / "Projects"
    if name:
        root = project_root(vault, name)
        matches = [root] if (root / "project.md").is_file() else []
    elif repository:
        wanted = str(repository.resolve())
        matches = [
            metadata.parent
            for metadata in projects.glob("*/project.md")
            if _frontmatter_value(metadata, "repository") == wanted
        ]
    else:
        raise ProjectError("resolve needs a project name or repository")
    if len(matches) != 1:
        raise ProjectError(f"project must resolve once ({len(matches)} matches)")
    root = matches[0]
    canvas_name = _frontmatter_value(root / "project.md", "canvas") or f"{root.name}.canvas"
    canvas = root / canvas_name
    if not canvas.is_file():
        raise ProjectError(f"project Canvas does not exist: {canvas}")
    return {"project": root.name, "root": str(root), "canvas": str(canvas)}
