#!/usr/bin/env python3
"""Create, import, and resolve projects in one Obsidian vault."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
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


def _metadata(name: str, repository: Path | None, canvas: str | None = None) -> str:
    repo = str(repository.resolve()) if repository else ""
    canvas = canvas or f"{name}.canvas"
    return (
        "---\n"
        f"project: {json.dumps(name, ensure_ascii=False)}\n"
        f"repository: {json.dumps(repo, ensure_ascii=False)}\n"
        f"canvas: {json.dumps(canvas, ensure_ascii=False)}\n"
        'paper_flows: "Paper"\n'
        'assets: "assets"\n'
        'bibliography: "references.bib"\n'
        'search_log: "searches.jsonl"\n'
        'zotero_collection: ""\n'
        'overleaf_project: ""\n'
        'overleaf_template: ""\n'
        'overleaf_body: ""\n'
        'paper_dir: "docs/paper"\n'
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
    for folder in ("assets",):
        path = root / folder
        if not path.exists():
            path.mkdir()
            created.append(str(path))
    paper_library = vault.resolve() / "Paper"
    if not paper_library.exists():
        paper_library.mkdir()
        created.append(str(paper_library))

    canonical = root / f"{name}.canvas"
    existing = sorted(root.glob("*.canvas"))
    if canonical.is_file():
        canvas = canonical
    elif len(existing) == 1:
        canvas = existing[0]
    elif existing:
        raise ProjectError(f"project Canvas is ambiguous: {root}")
    else:
        canvas = canonical
        canvas.write_text('{\n\t"nodes":[],\n\t"edges":[]\n}\n', encoding="utf-8")
        created.append(str(canvas))

    metadata = root / "project.md"
    if not metadata.exists():
        metadata.write_text(_metadata(name, repository, canvas.name), encoding="utf-8")
        created.append(str(metadata))
    else:
        if not _frontmatter_value(metadata, "canvas"):
            set_frontmatter_value(metadata, "canvas", canvas.name)
        if not _frontmatter_value(metadata, "paper_flows"):
            set_frontmatter_value(metadata, "paper_flows", "Paper")

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
            result=f"Created {name}.canvas, project.md, references.bib, searches.jsonl, assets/, and vault-level Paper/",
        )
        created.append(str(log))

    return {
        "status": "created" if created else "exists",
        "project": name,
        "root": str(root),
        "canvas": str(canvas),
        "created": created,
    }


def resolve_vault(name: str = "NLP", executable: str = "obsidian") -> Path:
    """Resolve a desktop Obsidian vault by its registered name."""
    try:
        result = subprocess.run(
            [executable, "vaults", "verbose"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProjectError(f"cannot query Obsidian CLI: {exc}") from exc
    matches = [Path(path) for vault_name, path in (line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line) if vault_name == name]
    if len(matches) != 1 or not matches[0].is_dir():
        raise ProjectError(f"vault must resolve once by name {name!r} ({len(matches)} matches)")
    return matches[0].resolve()


def standardize_project(vault: Path, name: str, repository: Path | None = None) -> dict[str, Any]:
    """Add project support files and localize every Canvas file node into assets/."""
    if not vault.is_dir():
        raise ProjectError(f"vault does not exist: {vault}")
    name = _project_name(name)
    root = project_root(vault, name)
    if not root.is_dir():
        raise ProjectError(f"project does not exist: {root}")

    canvases = sorted(root.glob("*.canvas"))
    if not canvases:
        raise ProjectError(f"project has no Canvas: {root}")
    vault_root = vault.resolve()
    assets = root / "assets"
    documents: list[tuple[Path, dict[str, Any], list[tuple[dict[str, Any], Path, Path]]]] = []
    for canvas in canvases:
        data = json.loads(canvas.read_text(encoding="utf-8"))
        if not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
            raise ProjectError(f"Canvas needs nodes and edges arrays: {canvas}")
        references: list[tuple[dict[str, Any], Path, Path]] = []
        for node in data["nodes"]:
            if node.get("type") != "file" or not isinstance(node.get("file"), str):
                continue
            raw = Path(node["file"])
            candidates = [raw] if raw.is_absolute() else [vault_root / raw, canvas.parent / raw]
            source = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
            if source is None:
                raise ProjectError(f"missing Canvas file reference: {node['file']} in {canvas.name}")
            destination = source if source.is_relative_to(root.resolve()) else assets / source.name
            expected = destination.relative_to(vault_root).as_posix()
            if node["file"] == expected:
                continue
            if destination.exists() and _sha256(destination) != _sha256(source):
                raise ProjectError(f"asset name collision: {destination.name}")
            references.append((node, source, destination))
        documents.append((canvas, data, references))

    result = init_project(vault, name, repository)
    copied: list[str] = []
    changed: list[str] = []
    history = root / ".canvas-history"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for canvas, data, references in documents:
        if not references:
            continue
        assets.mkdir(exist_ok=True)
        for node, source, destination in references:
            if source != destination and not destination.exists():
                shutil.copy2(source, destination)
                copied.append(str(destination))
            node["file"] = destination.relative_to(vault_root).as_posix()
        history.mkdir(exist_ok=True)
        shutil.copy2(canvas, history / f"{canvas.stem}.{stamp}.canvas")
        canvas.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(str(canvas))

    if changed or result["created"]:
        append_action(
            root / "CANVAS_ACTION_LOG.md",
            status="done",
            action="standardize-project",
            target=str(root),
            reason="Unified Sync vault project structure",
            result=f"Standardized {len(canvases)} Canvas files; localized {len(copied)} assets; changed {len(changed)} Canvas files",
        )
    return {
        **result,
        "status": "standardized" if changed or result["created"] else "exists",
        "canvases": [str(path) for path in canvases],
        "changed": changed,
        "assets": copied,
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


def _paper_flow_filename(title: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " - ", title)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        raise ProjectError("paper flow title cannot produce an empty filename")
    return value[:140].rstrip()


def _paper_flow_id(title: str, key: str) -> str:
    return hashlib.sha256(f"{title}\0{key}".encode("utf-8")).hexdigest()[:16]


def _paper_flow_height(text: str, width: int, *, heading: bool = False) -> int:
    if heading:
        return 70
    chars_per_line = max(20, width // 8)
    lines = sum(max(1, (len(line) + chars_per_line - 1) // chars_per_line) for line in text.splitlines())
    return max(70, ((40 + 20 * lines + 9) // 10) * 10)


def _vault_root(project: Path) -> Path:
    if project.parent.name != "Projects":
        raise ProjectError(f"project must be directly under a Projects folder: {project}")
    return project.parent.parent


def build_paper_flow(project: Path, spec_path: Path, *, replace: bool = False) -> dict[str, Any]:
    """Create one sentence-level paper Canvas in the vault-wide Paper library."""
    project = project.resolve()
    metadata = project / "project.md"
    if not metadata.is_file():
        raise ProjectError(f"not an Obs Paper project: {project}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ProjectError("paper flow spec root must be an object")
    title, citekey, item_key = (spec.get(key) for key in ("title", "citekey", "item_key"))
    if any(not isinstance(value, str) or not value.strip() for value in (title, citekey, item_key)):
        raise ProjectError("paper flow spec needs title, citekey, and item_key")
    sections = spec.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ProjectError("paper flow spec needs non-empty sections")
    section_keys = [section.get("key") for section in sections if isinstance(section, dict)]
    if (
        len(section_keys) != len(sections)
        or len(section_keys) != len(set(section_keys))
        or any(not isinstance(key, str) or not key for key in section_keys)
    ):
        raise ProjectError("paper flow section keys must be unique")
    for section in sections:
        if not isinstance(section.get("title"), str) or not section["title"].strip() or not isinstance(section.get("blocks"), list):
            raise ProjectError("each paper flow section needs a title and blocks")
        block_keys = [block.get("key") for block in section["blocks"] if isinstance(block, dict)]
        if (
            len(block_keys) != len(section["blocks"])
            or len(block_keys) != len(set(block_keys))
            or any(not isinstance(key, str) or not key for key in block_keys)
        ):
            raise ProjectError("paper flow block keys must be unique within a section")
        for block in section["blocks"]:
            kind, text = block.get("kind"), block.get("text")
            if kind not in {"heading", "sentence", "equation"} or not isinstance(text, str) or not text.strip():
                raise ProjectError("paper flow blocks need kind heading, sentence, or equation and non-empty text")
            if kind == "sentence" and not isinstance(block.get("paragraph"), str):
                raise ProjectError("paper flow sentence blocks need a paragraph key")
            if kind == "equation" and not (text.strip().startswith("$$") and text.strip().endswith("$$")):
                raise ProjectError("paper flow equations must use $$ delimiters")

    flow_dir = _vault_root(project) / (_frontmatter_value(metadata, "paper_flows") or "Paper")
    flow_dir.mkdir(exist_ok=True)
    if not _frontmatter_value(metadata, "paper_flows"):
        set_frontmatter_value(metadata, "paper_flows", flow_dir.name)
    filename = _paper_flow_filename(title) + ".canvas"
    canvas = flow_dir / filename
    source_text = (
        f"\\cite{{{citekey}}}\n"
        f"[Open in Zotero](zotero://select/library/items/{item_key})"
    )
    title_id = _paper_flow_id(title, "title")
    source_id = _paper_flow_id(title, "source")
    title_width = len(sections) * 812 + max(0, len(sections) - 1) * 120
    nodes: list[dict[str, Any]] = [
        {"id": title_id, "type": "text", "x": 620, "y": 20, "width": title_width, "height": 70, "text": f"# {title}", "color": "6"},
        {"id": source_id, "type": "text", "x": 20, "y": 110, "width": 560, "height": _paper_flow_height(source_text, 560), "text": source_text},
    ]
    for section_index, section in enumerate(sections):
        x, y = 620 + section_index * (812 + 120), 110
        heading = {
            "id": _paper_flow_id(title, f"section-{section['key']}"),
            "type": "text",
            "x": x,
            "y": y,
            "width": 812,
            "height": 70,
            "text": f"# {section['title'].strip().lstrip('# ').strip()}",
            "color": "6",
        }
        nodes.append(heading)
        y += 90
        previous_paragraph: str | None = None
        current_level = 0
        for block in section["blocks"]:
            kind, raw = block["kind"], block["text"].strip()
            level = int(block.get("level", current_level))
            if level < 0:
                raise ProjectError("paper flow indentation level cannot be negative")
            if kind == "sentence":
                paragraph = block["paragraph"]
                if previous_paragraph is not None and paragraph != previous_paragraph:
                    y += 20
                previous_paragraph = paragraph
                rendered, color = raw, None
            elif kind == "heading":
                if nodes[-1] is not heading:
                    y += 20
                rendered, color = f"# {raw.lstrip('# ').strip()}", "6"
                current_level = level
                previous_paragraph = None
            else:
                rendered, color = raw, None
                previous_paragraph = None
            width = 812
            after: dict[str, Any] = {
                "id": _paper_flow_id(title, f"{section['key']}-{block['key']}"),
                "type": "text",
                "x": x + 40 * level,
                "y": y,
                "width": width,
                "height": _paper_flow_height(rendered, width, heading=kind == "heading"),
                "text": rendered,
            }
            if color:
                after["color"] = color
            nodes.append(after)
            y += after["height"] + 20

    edges = [{"id": _paper_flow_id(title, "source-edge"), "fromNode": source_id, "fromSide": "right", "toNode": title_id, "toSide": "left"}]
    max_x = max(node["x"] + node["width"] for node in nodes)
    max_y = max(node["y"] + node["height"] for node in nodes)
    group = {
        "id": _paper_flow_id(title, "group"),
        "type": "group",
        "x": 0,
        "y": 0,
        "width": max_x + 20,
        "height": max_y + 20,
        "label": f"paper_flow · {title}",
    }
    document = {"nodes": [group, *nodes], "edges": edges}
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    backup: Path | None = None
    if canvas.exists():
        if canvas.read_text(encoding="utf-8") != text and not replace:
            raise ProjectError(f"paper flow already exists with different content: {canvas}")
        if canvas.read_text(encoding="utf-8") != text:
            history = flow_dir / ".canvas-history"
            history.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = history / f"{canvas.stem}.{stamp}.canvas"
            shutil.copy2(canvas, backup)
            canvas.write_text(text, encoding="utf-8")
            status = "replaced"
        else:
            status = "exists"
    else:
        canvas.write_text(text, encoding="utf-8")
        status = "created"
    if status != "exists":
        append_action(
            project / "CANVAS_ACTION_LOG.md",
            status="done",
            action="build-paper-flow",
            target=str(canvas),
            reason=f"{citekey}; Zotero item {item_key}",
            result=f"{status.title()} sentence-level Canvas with {len(nodes)} nodes and {len(edges)} edge"
            + (f"; backup: {backup}" if backup else ""),
        )
    return {
        "status": status,
        "canvas": str(canvas),
        "vault_link": f"{flow_dir.name}/{filename}",
        "nodes": len(nodes) + 1,
        "edges": len(edges),
        "backup": str(backup) if backup else None,
    }


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
