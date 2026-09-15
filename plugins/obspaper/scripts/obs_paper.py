#!/usr/bin/env python3
"""CLI for deterministic Obs Paper Canvas operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from obs_paper_engine import (
    LAYOUT_HEIGHT_TOLERANCE,
    LAYOUT_PADDING_SLACK,
    LAYOUT_TABLE_HEIGHT_TOLERANCE,
    PlanError,
    PreconditionError,
    apply_patch,
    compile_request,
    inspect_canvas,
    layout_check,
    layout_render,
    read_nodes,
    validate_canvas,
)
from obs_project import (
    ProjectError,
    build_paper_flow,
    configure_vault,
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

    layout_check_parser = subparsers.add_parser("layout-check")
    layout_render_parser = subparsers.add_parser("layout-render")
    for layout_parser in (layout_check_parser, layout_render_parser):
        layout_parser.add_argument("canvas", type=Path)
        layout_parser.add_argument("--group-id")
        layout_parser.add_argument("--group-label")
        layout_parser.add_argument("--height-tolerance", type=int, default=LAYOUT_HEIGHT_TOLERANCE)
        layout_parser.add_argument("--table-height-tolerance", type=int, default=LAYOUT_TABLE_HEIGHT_TOLERANCE)
        layout_parser.add_argument("--padding-slack", type=int, default=LAYOUT_PADDING_SLACK)
    layout_check_parser.add_argument("--output", type=Path)
    layout_render_parser.add_argument("--output", type=Path, required=True)

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
    vault_parser.add_argument("name", nargs="?")
    vault_parser.add_argument("--obsidian", default="obsidian")
    vault_parser.add_argument("--config", type=Path)

    vault_config_parser = subparsers.add_parser("vault-config")
    vault_config_parser.add_argument("path", type=Path)
    vault_config_parser.add_argument("--name")
    vault_config_parser.add_argument("--config", type=Path)

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
        target = None
        if getattr(args, "group_id", None) or getattr(args, "group_label", None):
            target = {"group_id": args.group_id, "group_label": args.group_label}
            target = {key: value for key, value in target.items() if value}
        if args.command == "inspect":
            emit(inspect_canvas(args.canvas, target), args.output)
        elif args.command in ("layout-check", "layout-render"):
            tolerances = {
                "height_tolerance": args.height_tolerance,
                "table_height_tolerance": args.table_height_tolerance,
                "padding_slack": args.padding_slack,
            }
            if args.command == "layout-check":
                report = layout_check(args.canvas, target, **tolerances)
                emit(report, args.output)
            else:
                report = layout_render(args.canvas, args.output, target, **tolerances)
                emit(report)
            if report["errors"]:
                sys.exit(1)
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
            emit({"vault": args.name, "path": str(resolve_vault(args.name, args.obsidian, args.config))})
        elif args.command == "vault-config":
            emit(configure_vault(args.path, args.name, args.config))
        else:
            emit(build_paper_flow(args.project, args.spec, replace=args.replace))
    except (PlanError, PreconditionError, ProjectError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
