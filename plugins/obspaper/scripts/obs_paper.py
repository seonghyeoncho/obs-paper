#!/usr/bin/env python3
"""CLI for deterministic Obs Paper Canvas operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from obs_paper_engine import (
    PlanError,
    PreconditionError,
    apply_patch,
    compile_request,
    inspect_canvas,
    read_nodes,
    validate_canvas,
)
from obs_project import (
    ProjectError,
    build_paper_flow,
    import_project,
    init_project,
    resolve_project,
    resolve_vault,
    standardize_project,
)


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PlanError(f"JSON root must be an object: {path}")
    return data


def emit(data: dict[str, Any], output: Path | None = None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("canvas", type=Path)
    inspect_parser.add_argument("--group-id")
    inspect_parser.add_argument("--group-label")
    inspect_parser.add_argument("--output", type=Path)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("canvas", type=Path)
    plan_parser.add_argument("request", type=Path)
    plan_parser.add_argument("--output", type=Path)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("canvas", type=Path)
    apply_parser.add_argument("patch", type=Path)
    apply_parser.add_argument("--log", type=Path)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("canvas", type=Path)
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("--patch-output", type=Path)
    run_parser.add_argument("--log", type=Path)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("canvas", type=Path)

    init_parser = subparsers.add_parser("project-init")
    init_parser.add_argument("vault", type=Path)
    init_parser.add_argument("name")
    init_parser.add_argument("--repository", type=Path)

    import_parser = subparsers.add_parser("project-import")
    import_parser.add_argument("vault", type=Path)
    import_parser.add_argument("name")
    import_parser.add_argument("source_canvas", type=Path)
    import_parser.add_argument("--repository", type=Path)

    resolve_parser = subparsers.add_parser("project-resolve")
    resolve_parser.add_argument("vault", type=Path)
    selector = resolve_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--name")
    selector.add_argument("--repository", type=Path)

    standardize_parser = subparsers.add_parser("project-standardize")
    standardize_parser.add_argument("vault", type=Path)
    standardize_parser.add_argument("name")
    standardize_parser.add_argument("--repository", type=Path)

    vault_parser = subparsers.add_parser("vault-path")
    vault_parser.add_argument("name", nargs="?", default="NLP")
    vault_parser.add_argument("--obsidian", default="obsidian")

    nodes_parser = subparsers.add_parser("nodes")
    nodes_parser.add_argument("canvas", type=Path)
    nodes_parser.add_argument("node_ids", nargs="+")
    nodes_parser.add_argument("--output", type=Path)

    paper_flow_parser = subparsers.add_parser("paper-flow-build")
    paper_flow_parser.add_argument("project", type=Path)
    paper_flow_parser.add_argument("spec", type=Path)
    paper_flow_parser.add_argument("--replace", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "inspect":
            target = None
            if args.group_id or args.group_label:
                target = {"group_id": args.group_id, "group_label": args.group_label}
                target = {key: value for key, value in target.items() if value}
            emit(inspect_canvas(args.canvas, target), args.output)
        elif args.command == "plan":
            emit(compile_request(args.canvas, read_json(args.request)), args.output)
        elif args.command == "apply":
            emit(apply_patch(args.canvas, read_json(args.patch), args.log))
        elif args.command == "run":
            patch = compile_request(args.canvas, read_json(args.request))
            if args.patch_output:
                emit(patch, args.patch_output)
            emit(apply_patch(args.canvas, patch, args.log))
        elif args.command == "validate":
            emit(validate_canvas(args.canvas))
        elif args.command == "nodes":
            emit(read_nodes(args.canvas, args.node_ids), args.output)
        elif args.command == "project-init":
            emit(init_project(args.vault, args.name, args.repository))
        elif args.command == "project-import":
            emit(import_project(args.vault, args.name, args.source_canvas, args.repository))
        elif args.command == "project-resolve":
            emit(resolve_project(args.vault, name=args.name, repository=args.repository))
        elif args.command == "project-standardize":
            emit(standardize_project(args.vault, args.name, args.repository))
        elif args.command == "vault-path":
            emit({"vault": args.name, "path": str(resolve_vault(args.name, args.obsidian))})
        else:
            emit(build_paper_flow(args.project, args.spec, replace=args.replace))
    except (PlanError, PreconditionError, ProjectError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
