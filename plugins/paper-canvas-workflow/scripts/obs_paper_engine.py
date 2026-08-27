#!/usr/bin/env python3
"""Deterministic JSON-plan engine for Obsidian Canvas paper workflows."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from record_action import append_action


class PlanError(ValueError):
    """The request cannot be resolved without guessing."""


class PreconditionError(RuntimeError):
    """The Canvas changed after the patch was compiled."""


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, node: dict[str, Any]) -> bool:
        return (
            node["x"] >= self.x
            and node["y"] >= self.y
            and node["x"] + node["width"] <= self.right
            and node["y"] + node["height"] <= self.bottom
        )


class CanvasDocument:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.validate_integrity()

    @classmethod
    def load(cls, path: Path) -> "CanvasDocument":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def nodes(self) -> list[dict[str, Any]]:
        return self.data["nodes"]

    @property
    def edges(self) -> list[dict[str, Any]]:
        return self.data["edges"]

    def node_map(self) -> dict[str, dict[str, Any]]:
        return {node["id"]: node for node in self.nodes}

    def edge_map(self) -> dict[str, dict[str, Any]]:
        return {edge["id"]: edge for edge in self.edges}

    def node(self, node_id: str) -> dict[str, Any]:
        try:
            return self.node_map()[node_id]
        except KeyError as exc:
            raise PlanError(f"unknown node id: {node_id}") from exc

    def resolve_group(self, target: dict[str, Any]) -> dict[str, Any]:
        group_id = target.get("group_id")
        group_label = target.get("group_label")
        if bool(group_id) == bool(group_label):
            raise PlanError("target needs exactly one of group_id or group_label")
        if group_id:
            group = self.node(group_id)
            if group.get("type") != "group":
                raise PlanError(f"target is not a group: {group_id}")
            return group
        matches = [
            node
            for node in self.nodes
            if node.get("type") == "group" and node.get("label") == group_label
        ]
        if len(matches) != 1:
            raise PlanError(f"group label must resolve once: {group_label!r} ({len(matches)} matches)")
        return matches[0]

    def contained_non_groups(self, rect: Rect) -> list[dict[str, Any]]:
        return [node for node in self.nodes if node.get("type") != "group" and rect.contains(node)]

    def validate_integrity(self) -> None:
        if not isinstance(self.data.get("nodes"), list) or not isinstance(self.data.get("edges"), list):
            raise PlanError("Canvas must contain nodes and edges arrays")
        ids = [item.get("id") for item in [*self.nodes, *self.edges]]
        if any(not isinstance(item_id, str) or not item_id for item_id in ids):
            raise PlanError("every node and edge needs a non-empty string id")
        if len(ids) != len(set(ids)):
            raise PlanError("node and edge ids must be globally unique")
        node_ids = {node["id"] for node in self.nodes}
        for node in self.nodes:
            for key in ("x", "y", "width", "height"):
                if not isinstance(node.get(key), int):
                    raise PlanError(f"node {node['id']} has invalid {key}")
            if node["width"] <= 0 or node["height"] <= 0:
                raise PlanError(f"node {node['id']} has a non-positive size")
        for edge in self.edges:
            if edge.get("fromNode") not in node_ids or edge.get("toNode") not in node_ids:
                raise PlanError(f"edge {edge['id']} has a missing endpoint")


def canvas_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deterministic_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]


def node_rect(node: dict[str, Any]) -> Rect:
    return Rect(node["x"], node["y"], node["width"], node["height"])


def rects_overlap(left: Rect, right: Rect) -> bool:
    return (
        min(left.right, right.right) > max(left.x, right.x)
        and min(left.bottom, right.bottom) > max(left.y, right.y)
    )


def bounding_rect(nodes: list[dict[str, Any]], padding: int) -> Rect:
    if not nodes:
        raise PlanError("group_appendix needs at least one member")
    left = min(node["x"] for node in nodes) - padding
    top = min(node["y"] for node in nodes) - padding
    right = max(node["x"] + node["width"] for node in nodes) + padding
    bottom = max(node["y"] + node["height"] for node in nodes) + padding
    return Rect(left, top, right - left, bottom - top)


def estimate_text_height(text: str, width: int, kind: str) -> int:
    """Estimate Obsidian card height; callers may provide an exact height."""
    # ponytail: heuristic sizing; replace with renderer measurements if real cards clip.
    if kind == "heading":
        return 70
    if kind == "equation":
        return max(100, 40 + 30 * len(text.splitlines()))
    chars_per_line = max(20, width // 8)
    visual_lines = sum(
        max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        for line in text.splitlines() or [""]
    )
    return max(70, ((40 + 20 * visual_lines + 9) // 10) * 10)


def _node_operation(
    document: CanvasDocument,
    node: dict[str, Any],
    *,
    target_group_id: str | None = None,
) -> dict[str, Any] | None:
    existing = document.node_map().get(node["id"])
    operation = {
        "op": "upsert_group" if node.get("type") == "group" else "upsert_node",
        "node_id": node["id"],
        "before": copy.deepcopy(existing) if existing else None,
        "after": copy.deepcopy(node),
    }
    if target_group_id:
        operation["target_group_id"] = target_group_id
    return None if operation["before"] == operation["after"] else operation


def _edge_operation(
    document: CanvasDocument,
    *,
    key_parts: list[str],
    from_node: str,
    to_node: str,
    from_side: str,
    to_side: str,
) -> dict[str, Any] | None:
    document.node(from_node)
    document.node(to_node)
    edge_id = deterministic_id(*key_parts)
    existing = document.edge_map().get(edge_id)
    after = {
        "id": edge_id,
        "fromNode": from_node,
        "fromSide": from_side,
        "toNode": to_node,
        "toSide": to_side,
    }
    operation = {
        "op": "upsert_edge",
        "edge_id": edge_id,
        "before": copy.deepcopy(existing) if existing else None,
        "after": after,
    }
    return None if operation["before"] == operation["after"] else operation


def _append_operation(
    scratch: CanvasDocument,
    operations: list[dict[str, Any]],
    operation: dict[str, Any] | None,
) -> None:
    if operation:
        operations.append(operation)
        _apply_operation(scratch, operation, check_before=False)


def _compile_group_appendix(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    label = action.get("label")
    member_ids = action.get("member_ids")
    padding = action.get("padding", 20)
    if not isinstance(label, str) or not label.strip():
        raise PlanError("group_appendix needs a label")
    if not isinstance(member_ids, list) or not member_ids or len(member_ids) != len(set(member_ids)):
        raise PlanError("group_appendix member_ids must be a non-empty unique list")
    if not isinstance(padding, int) or padding < 0:
        raise PlanError("group_appendix padding must be a non-negative integer")

    members = [document.node(node_id) for node_id in member_ids]
    if any(node.get("type") == "group" for node in members):
        raise PlanError("group_appendix members cannot include groups")
    target_rect = node_rect(target_group)
    if any(not target_rect.contains(node) for node in members):
        raise PlanError("every group_appendix member must be inside the target group")

    rect = bounding_rect(members, padding)
    group_id = action.get("group_id") or deterministic_id(
        target_group["id"], "group_appendix", label
    )
    existing = document.node_map().get(group_id)
    if existing and existing.get("type") != "group":
        raise PlanError(f"group id belongs to a non-group node: {group_id}")

    after = copy.deepcopy(existing) if existing else {"id": group_id, "type": "group"}
    after.update(
        {
            "x": rect.x,
            "y": rect.y,
            "width": rect.width,
            "height": rect.height,
            "label": label,
        }
    )
    if "color" in action:
        after["color"] = action["color"]

    if not target_rect.contains(after):
        raise PlanError("computed Appendix group does not fit inside the target group")
    captured = {node["id"] for node in document.contained_non_groups(rect)}
    unlisted = sorted(captured - set(member_ids))
    if unlisted:
        raise PlanError(f"computed Appendix group would capture unlisted nodes: {unlisted}")

    before = copy.deepcopy(existing) if existing else None
    if before == after:
        return []
    return [
        {
            "op": "upsert_group",
            "node_id": group_id,
            "before": before,
            "after": after,
            "member_ids": member_ids,
            "padding": padding,
            "target_group_id": target_group["id"],
        }
    ]


def _compile_insert_blocks(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    if action.get("position", "after") != "after":
        raise PlanError("insert_blocks currently supports position='after' only")
    blocks = action.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise PlanError("insert_blocks needs a non-empty blocks list")
    keys = [block.get("key") for block in blocks if isinstance(block, dict)]
    if len(keys) != len(blocks) or any(not isinstance(key, str) or not key for key in keys):
        raise PlanError("every inserted block needs a non-empty key")
    if len(keys) != len(set(keys)):
        raise PlanError("inserted block keys must be unique")

    anchor = document.node(action.get("anchor_id", ""))
    target_rect = node_rect(target_group)
    if anchor.get("type") == "group" or not target_rect.contains(anchor):
        raise PlanError("insert_blocks anchor must be a non-group node inside the target group")
    shift_ids = action.get("shift_node_ids", [])
    if not isinstance(shift_ids, list) or len(shift_ids) != len(set(shift_ids)):
        raise PlanError("shift_node_ids must be a unique list")
    shifted = [document.node(node_id) for node_id in shift_ids]
    if any(node.get("type") == "group" or not target_rect.contains(node) for node in shifted):
        raise PlanError("shifted nodes must be non-group nodes inside the target group")
    if anchor["id"] in shift_ids or any(node["y"] < anchor["y"] + anchor["height"] for node in shifted):
        raise PlanError("shifted nodes must start below the anchor")

    fit_group_id = action.get("fit_group_id")
    fit_members: list[str] = []
    if fit_group_id:
        fit_group = document.node(fit_group_id)
        if fit_group.get("type") != "group" or not target_rect.contains(fit_group):
            raise PlanError("fit_group_id must name a group inside the target group")
        fit_rect = node_rect(fit_group)
        if not fit_rect.contains(anchor) or any(not fit_rect.contains(node) for node in shifted):
            raise PlanError("anchor and shifted nodes must be inside fit_group_id")
        fit_members = [node["id"] for node in document.contained_non_groups(fit_rect)]

    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    cursor_bottom = anchor["y"] + anchor["height"]
    predecessor_id = anchor["id"]
    inserted_ids: list[str] = []
    default_gap = action.get("gap", 20)
    gap_after = action.get("gap_after", 20)
    if not isinstance(default_gap, int) or default_gap < 0 or not isinstance(gap_after, int) or gap_after < 0:
        raise PlanError("insert_blocks gaps must be non-negative integers")

    for block in blocks:
        kind = block.get("kind", "sentence")
        if kind not in {"sentence", "paragraph", "heading", "equation"}:
            raise PlanError(f"insert_blocks does not place artifact kind: {kind!r}")
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            raise PlanError("every inserted block needs non-empty text")
        width = block.get("width", anchor["width"])
        x_offset = block.get("x_offset", 0)
        gap_before = block.get("gap_before", default_gap)
        if any(not isinstance(value, int) for value in (width, x_offset, gap_before)):
            raise PlanError("block width, x_offset, and gap_before must be integers")
        if width <= 0 or gap_before < 0:
            raise PlanError("block width must be positive and gap_before non-negative")
        height = block.get("height", estimate_text_height(text, width, kind))
        if not isinstance(height, int) or height <= 0:
            raise PlanError("block height must be a positive integer")
        node_id = block.get("node_id") or deterministic_id(
            target_group["id"], "insert_block", block["key"]
        )
        existing = scratch.node_map().get(node_id)
        if existing and existing.get("type") != "text":
            raise PlanError(f"inserted block id belongs to a non-text node: {node_id}")
        after = copy.deepcopy(existing) if existing else {"id": node_id, "type": "text"}
        after.update(
            {
                "x": anchor["x"] + x_offset,
                "y": cursor_bottom + gap_before,
                "width": width,
                "height": height,
                "text": text,
            }
        )
        if "color" in block:
            after["color"] = block["color"]
        operation = {
            "op": "upsert_node",
            "node_id": node_id,
            "before": copy.deepcopy(existing) if existing else None,
            "after": after,
            "insert_after_id": predecessor_id,
            "target_group_id": target_group["id"],
        }
        if operation["before"] != operation["after"]:
            operations.append(operation)
            _apply_operation(scratch, operation, check_before=False)
        inserted_ids.append(node_id)
        predecessor_id = node_id
        cursor_bottom = after["y"] + after["height"]

    if shifted:
        first_y = min(scratch.node(node_id)["y"] for node_id in shift_ids)
        delta_y = max(0, cursor_bottom + gap_after - first_y)
        if delta_y:
            before_positions = {
                node_id: {"x": scratch.node(node_id)["x"], "y": scratch.node(node_id)["y"]}
                for node_id in shift_ids
            }
            after_positions = {
                node_id: {"x": position["x"], "y": position["y"] + delta_y}
                for node_id, position in before_positions.items()
            }
            operation = {
                "op": "translate_nodes",
                "before": before_positions,
                "after": after_positions,
                "target_group_id": target_group["id"],
            }
            operations.append(operation)
            _apply_operation(scratch, operation, check_before=False)

    if fit_group_id:
        fit_group = scratch.node(fit_group_id)
        group_operations = _compile_group_appendix(
            scratch,
            {
                "op": "group_appendix",
                "group_id": fit_group_id,
                "label": fit_group.get("label", "Appendix"),
                "member_ids": sorted(set(fit_members + inserted_ids)),
                "padding": action.get("group_padding", 20),
            },
            scratch.node(target_group["id"]),
        )
        operations.extend(group_operations)

    affected = set(inserted_ids + shift_ids)
    checked: set[tuple[str, str]] = set()
    for node_id in affected:
        node = scratch.node(node_id)
        for other in scratch.nodes:
            if other.get("type") == "group" or other["id"] == node_id:
                continue
            pair = tuple(sorted((node_id, other["id"])))
            if pair in checked:
                continue
            checked.add(pair)
            if rects_overlap(node_rect(node), node_rect(other)):
                raise PlanError(f"insert_blocks would overlap nodes: {pair}")
    return operations


def _compile_place_artifact(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    kind = action.get("kind")
    if kind not in {"figure", "table"}:
        raise PlanError("place_artifact kind must be figure or table")
    key = action.get("key")
    mention_ids = action.get("mention_ids")
    lane = action.get("lane", "left")
    if not isinstance(key, str) or not key or not isinstance(mention_ids, list) or not mention_ids:
        raise PlanError("place_artifact needs a key and mention_ids")
    if len(mention_ids) != len(set(mention_ids)) or lane not in {"left", "right"}:
        raise PlanError("place_artifact mention_ids must be unique and lane left or right")
    mentions = [document.node(node_id) for node_id in mention_ids]
    target_rect = node_rect(target_group)
    if any(node.get("type") == "group" or not target_rect.contains(node) for node in mentions):
        raise PlanError("artifact mentions must be non-group nodes inside the target")
    first = min(mentions, key=lambda node: (node["y"], node["x"]))
    width = action.get("width")
    height = action.get("height")
    if not isinstance(width, int) or width <= 0 or not isinstance(height, int) or height <= 0:
        raise PlanError("place_artifact needs positive integer width and height")
    node_id = action.get("node_id") or deterministic_id(target_group["id"], "artifact", key)
    if kind == "figure":
        file = action.get("file")
        if not isinstance(file, str) or not file:
            raise PlanError("figure artifact needs a file")
        after: dict[str, Any] = {"id": node_id, "type": "file", "file": file}
    else:
        text = action.get("text")
        if not isinstance(text, str) or "|" not in text:
            raise PlanError("table artifact needs a complete Markdown table")
        after = {"id": node_id, "type": "text", "text": text}
    gap = action.get("gap", 20)
    if not isinstance(gap, int) or gap < 0:
        raise PlanError("artifact gap must be a non-negative integer")
    after.update({
        "x": first["x"] - gap - width if lane == "left" else first["x"] + first["width"] + gap,
        "y": first["y"] + (first["height"] - height) // 2,
        "width": width,
        "height": height,
    })
    if "color" in action:
        after["color"] = action["color"]
    if not target_rect.contains(after):
        raise PlanError("artifact does not fit inside the target group")
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    _append_operation(scratch, operations, _node_operation(scratch, after, target_group_id=target_group["id"]))
    for mention in mentions:
        _append_operation(
            scratch,
            operations,
            _edge_operation(
                scratch,
                key_parts=[target_group["id"], "artifact_edge", key, mention["id"]],
                from_node=node_id,
                to_node=mention["id"],
                from_side="right" if lane == "left" else "left",
                to_side="left" if lane == "left" else "right",
            ),
        )
    for other in scratch.nodes:
        if other.get("type") != "group" and other["id"] != node_id and rects_overlap(node_rect(after), node_rect(other)):
            raise PlanError(f"artifact would overlap node: {other['id']}")
    return operations


def _compile_pair_appendix_columns(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    sections = action.get("sections")
    if not isinstance(sections, list) or not sections:
        raise PlanError("pair_appendix_columns needs sections")
    all_ids: list[str] = []
    for section in sections:
        blocks = section.get("blocks") if isinstance(section, dict) else None
        if not isinstance(blocks, list) or not blocks or any(not isinstance(block, list) or not block for block in blocks):
            raise PlanError("each paired Appendix section needs non-empty blocks")
        all_ids.extend(node_id for block in blocks for node_id in block)
    if len(all_ids) != len(set(all_ids)):
        raise PlanError("paired Appendix member ids must be unique")
    target_rect = node_rect(target_group)
    members = [document.node(node_id) for node_id in all_ids]
    if any(node.get("type") == "group" or not target_rect.contains(node) for node in members):
        raise PlanError("paired Appendix members must be non-groups inside the paper")

    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    moved_ids: set[str] = set()
    for section in sections:
        key, label = section.get("key"), section.get("label")
        x, cursor_y = section.get("x"), section.get("y")
        gap = section.get("gap", 40)
        if not isinstance(key, str) or not key or not isinstance(label, str) or not label:
            raise PlanError("paired Appendix sections need key and label")
        if any(not isinstance(value, int) for value in (x, cursor_y, gap)) or gap < 0:
            raise PlanError("paired Appendix geometry must use integers and a non-negative gap")
        section_ids: list[str] = []
        for block_ids in section["blocks"]:
            block_nodes = [scratch.node(node_id) for node_id in block_ids]
            rect = bounding_rect(block_nodes, 0)
            dx, dy = x - rect.x, cursor_y - rect.y
            before = {node_id: {"x": scratch.node(node_id)["x"], "y": scratch.node(node_id)["y"]} for node_id in block_ids}
            after = {node_id: {"x": position["x"] + dx, "y": position["y"] + dy} for node_id, position in before.items()}
            if before != after:
                _append_operation(
                    scratch,
                    operations,
                    {"op": "translate_nodes", "before": before, "after": after, "target_group_id": target_group["id"]},
                )
            section_ids.extend(block_ids)
            moved_ids.update(block_ids)
            cursor_y = max(scratch.node(node_id)["y"] + scratch.node(node_id)["height"] for node_id in block_ids) + gap
        group_operations = _compile_group_appendix(
            scratch,
            {
                "op": "group_appendix",
                "group_id": section.get("group_id") or deterministic_id(target_group["id"], "section_appendix", key),
                "label": label,
                "member_ids": section_ids,
                "padding": section.get("padding", 20),
            },
            scratch.node(target_group["id"]),
        )
        for operation in group_operations:
            _append_operation(scratch, operations, operation)

    for node_id in moved_ids:
        node = scratch.node(node_id)
        for other in scratch.nodes:
            if other.get("type") == "group" or other["id"] == node_id or other["id"] in moved_ids and other["id"] < node_id:
                continue
            if rects_overlap(node_rect(node), node_rect(other)):
                raise PlanError(f"paired Appendix would overlap nodes: {tuple(sorted((node_id, other['id'])))}")
    return operations


def _compile_split_citation(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    key, sentence_id, command = action.get("key"), action.get("sentence_id"), action.get("command")
    lane = action.get("lane", "right")
    if not isinstance(key, str) or not key or not isinstance(command, str) or not command:
        raise PlanError("split_citation needs key and command")
    if lane not in {"left", "right"}:
        raise PlanError("citation lane must be left or right")
    sentence = document.node(sentence_id or "")
    target_rect = node_rect(target_group)
    if sentence.get("type") != "text" or not target_rect.contains(sentence):
        raise PlanError("citation sentence must be a text node inside the paper")
    card_id = action.get("node_id") or deterministic_id(target_group["id"], "citation", key)
    existing_card = document.node_map().get(card_id)
    if command in sentence["text"]:
        sentence_after = copy.deepcopy(sentence)
        sentence_after["text"] = sentence["text"].replace(command, "{}", 1)
    elif existing_card and "{}" in sentence["text"]:
        sentence_after = copy.deepcopy(sentence)
    else:
        raise PlanError("citation command is absent and no completed split exists")
    width = action.get("width", 300)
    height = action.get("height", estimate_text_height(command, width, "paragraph"))
    gap = action.get("gap", 20)
    if any(not isinstance(value, int) for value in (width, height, gap)) or width <= 0 or height <= 0 or gap < 0:
        raise PlanError("citation geometry is invalid")
    card = {
        "id": card_id,
        "type": "text",
        "x": sentence["x"] - gap - width if lane == "left" else sentence["x"] + sentence["width"] + gap,
        "y": sentence["y"] + (sentence["height"] - height) // 2,
        "width": width,
        "height": height,
        "text": command,
    }
    if not target_rect.contains(card):
        raise PlanError("citation card does not fit inside the paper group")
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    _append_operation(scratch, operations, _node_operation(scratch, sentence_after, target_group_id=target_group["id"]))
    _append_operation(scratch, operations, _node_operation(scratch, card, target_group_id=target_group["id"]))
    _append_operation(
        scratch,
        operations,
        _edge_operation(
            scratch,
            key_parts=[target_group["id"], "citation_edge", key],
            from_node=card_id,
            to_node=sentence["id"],
            from_side="right" if lane == "left" else "left",
            to_side="left" if lane == "left" else "right",
        ),
    )
    return operations


def _compile_connect_reference(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    key, kind = action.get("key"), action.get("kind")
    source = document.node(action.get("source_id", ""))
    target_ids = action.get("target_ids")
    from_side, to_side = action.get("from_side"), action.get("to_side")
    if not isinstance(key, str) or not key or kind not in {"equation", "appendix", "figure", "table", "logical"}:
        raise PlanError("connect_reference needs a key and supported kind")
    if not isinstance(target_ids, list) or not target_ids or len(target_ids) != len(set(target_ids)):
        raise PlanError("connect_reference target_ids must be a non-empty unique list")
    if from_side not in {"top", "bottom", "left", "right"} or to_side not in {"top", "bottom", "left", "right"}:
        raise PlanError("connect_reference sides are invalid")
    if kind == "equation" and not (source.get("text", "").strip().startswith("$$") and source.get("text", "").strip().endswith("$$")):
        raise PlanError("equation references require a complete $$...$$ display block")
    target_rect = node_rect(target_group)
    targets = [document.node(node_id) for node_id in target_ids]
    if not target_rect.contains(source) or any(not target_rect.contains(target) for target in targets):
        raise PlanError("reference endpoints must be inside the target group")
    if not action.get("curved", False):
        for target in targets:
            if from_side in {"top", "bottom"} and 2 * source["x"] + source["width"] != 2 * target["x"] + target["width"]:
                raise PlanError("straight vertical reference edges must be centre-aligned")
            if from_side in {"left", "right"} and 2 * source["y"] + source["height"] != 2 * target["y"] + target["height"]:
                raise PlanError("straight lateral reference edges must be centre-aligned")
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    for target in targets:
        _append_operation(
            scratch,
            operations,
            _edge_operation(
                scratch,
                key_parts=[target_group["id"], "reference", key, target["id"]],
                from_node=source["id"],
                to_node=target["id"],
                from_side=from_side,
                to_side=to_side,
            ),
        )
    return operations


def _compile_fit_section_title(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    title = document.node(action.get("title_id", ""))
    member_ids = action.get("member_ids")
    if title.get("type") != "text" or not title.get("text", "").startswith("# "):
        raise PlanError("fit_section_title needs a heading text node")
    if not isinstance(member_ids, list) or not member_ids or len(member_ids) != len(set(member_ids)):
        raise PlanError("fit_section_title member_ids must be a non-empty unique list")
    members = [document.node(node_id) for node_id in member_ids]
    target_rect = node_rect(target_group)
    if not target_rect.contains(title) or any(not target_rect.contains(node) for node in members):
        raise PlanError("section title and members must be inside the paper group")
    left = min(node["x"] for node in members)
    right = max(node["x"] + node["width"] for node in members)
    after = copy.deepcopy(title)
    after.update({"x": left, "width": right - left})
    operation = _node_operation(document, after, target_group_id=target_group["id"])
    return [operation] if operation else []


def _compile_move_nodes(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    node_ids = action.get("node_ids")
    anchor_id = action.get("anchor_id")
    x, y = action.get("x"), action.get("y")
    if not isinstance(node_ids, list) or not node_ids or len(node_ids) != len(set(node_ids)):
        raise PlanError("move_nodes node_ids must be a non-empty unique list")
    if anchor_id not in node_ids or not isinstance(x, int) or not isinstance(y, int):
        raise PlanError("move_nodes needs an included anchor_id and integer x/y destination")
    target_rect = node_rect(target_group)
    nodes = [document.node(node_id) for node_id in node_ids]
    if any(node["id"] == target_group["id"] or not target_rect.contains(node) for node in nodes):
        raise PlanError("move_nodes members must be inside the target group")
    anchor = document.node(anchor_id)
    dx, dy = x - anchor["x"], y - anchor["y"]
    if not dx and not dy:
        return []
    before = {node["id"]: {"x": node["x"], "y": node["y"]} for node in nodes}
    after = {node_id: {"x": position["x"] + dx, "y": position["y"] + dy} for node_id, position in before.items()}
    moved_rects = [Rect(position["x"], position["y"], document.node(node_id)["width"], document.node(node_id)["height"]) for node_id, position in after.items()]
    if min(rect.x for rect in moved_rects) < target_rect.x or min(rect.y for rect in moved_rects) < target_rect.y:
        raise PlanError("move_nodes cannot expand a target group left or upward")
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    _append_operation(scratch, operations, {"op": "translate_nodes", "before": before, "after": after, "target_group_id": target_group["id"]})
    group_after = copy.deepcopy(scratch.node(target_group["id"]))
    group_after["width"] = max(group_after["width"], max(rect.right for rect in moved_rects) - group_after["x"] + 20)
    group_after["height"] = max(group_after["height"], max(rect.bottom for rect in moved_rects) - group_after["y"] + 20)
    _append_operation(scratch, operations, _node_operation(scratch, group_after))
    moved_non_groups = {node_id for node_id in node_ids if scratch.node(node_id).get("type") != "group"}
    for node_id in moved_non_groups:
        for other in scratch.nodes:
            if other.get("type") == "group" or other["id"] == node_id or other["id"] in moved_non_groups:
                continue
            if rects_overlap(node_rect(scratch.node(node_id)), node_rect(other)):
                raise PlanError(f"move_nodes would overlap node: {other['id']}")
    return operations


def _compile_shift_sibling_group(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    sibling = document.node(action.get("group_id", ""))
    x, y = action.get("x"), action.get("y")
    if sibling.get("type") != "group" or sibling["id"] == target_group["id"]:
        raise PlanError("shift_sibling_group needs a different group")
    if not isinstance(x, int) or not isinstance(y, int):
        raise PlanError("shift_sibling_group x and y must be integers")
    sibling_rect = node_rect(sibling)
    if node_rect(target_group).contains(sibling):
        raise PlanError("shift_sibling_group requires an outer sibling, not a nested group")
    dx, dy = x - sibling["x"], y - sibling["y"]
    if not dx and not dy:
        return []
    members = [node for node in document.nodes if node["id"] != sibling["id"] and sibling_rect.contains(node)]
    moving = [sibling, *members]
    before = {node["id"]: {"x": node["x"], "y": node["y"]} for node in moving}
    after = {node_id: {"x": position["x"] + dx, "y": position["y"] + dy} for node_id, position in before.items()}
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operation = {"op": "translate_nodes", "before": before, "after": after, "target_group_id": sibling["id"]}
    _apply_operation(scratch, operation, check_before=False)
    moved_ids = set(after)
    moved_rect = node_rect(scratch.node(sibling["id"]))
    for group in scratch.nodes:
        if group.get("type") != "group" or group["id"] in moved_ids:
            continue
        if any(
            other.get("type") == "group"
            and other["id"] not in {group["id"], sibling["id"]}
            and node_rect(other).contains(group)
            for other in scratch.nodes
        ):
            continue
        if rects_overlap(moved_rect, node_rect(group)):
            raise PlanError(f"shifted sibling group would overlap group: {group['id']}")
    moved_non_groups = [node for node in members if node.get("type") != "group"]
    for node in moved_non_groups:
        moved_node = scratch.node(node["id"])
        for other in scratch.nodes:
            if other.get("type") == "group" or other["id"] in moved_ids:
                continue
            if rects_overlap(node_rect(moved_node), node_rect(other)):
                raise PlanError(f"shifted sibling content would overlap node: {other['id']}")
    return [operation]


def _compile_normalize_equations(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    node_ids = action.get("node_ids")
    if not isinstance(node_ids, list) or not node_ids or len(node_ids) != len(set(node_ids)):
        raise PlanError("normalize_equations node_ids must be a non-empty unique list")
    target_rect = node_rect(target_group)
    operations: list[dict[str, Any]] = []
    for node_id in node_ids:
        node = document.node(node_id)
        if node.get("type") != "text" or not target_rect.contains(node):
            raise PlanError("normalized equations must be text nodes inside the paper")
        text = node["text"].strip()
        if text.startswith("$$") and text.endswith("$$"):
            continue
        match = re.fullmatch(r"```\s*math\s*\n(.*)\n```", text, re.DOTALL | re.IGNORECASE)
        if not match:
            raise PlanError(f"node is not a fenced or $$ display equation: {node_id}")
        after = copy.deepcopy(node)
        after["text"] = f"$$\n{match.group(1)}\n$$"
        operation = _node_operation(document, after, target_group_id=target_group["id"])
        if operation:
            operations.append(operation)
    return operations


def _compile_remove_items(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    node_ids, edge_ids = action.get("node_ids", []), action.get("edge_ids", [])
    if any(not isinstance(values, list) or len(values) != len(set(values)) for values in (node_ids, edge_ids)):
        raise PlanError("remove_items ids must be unique lists")
    target_rect = node_rect(target_group)
    existing_nodes = [document.node_map()[node_id] for node_id in node_ids if node_id in document.node_map()]
    if any(node.get("type") == "group" or not target_rect.contains(node) for node in existing_nodes):
        raise PlanError("remove_items may remove only non-group nodes inside the target")
    existing_edge_ids = {edge_id for edge_id in edge_ids if edge_id in document.edge_map()}
    removing_nodes = {node["id"] for node in existing_nodes}
    incident = {
        edge["id"]
        for edge in document.edges
        if edge["fromNode"] in removing_nodes or edge["toNode"] in removing_nodes
    }
    if not incident.issubset(existing_edge_ids):
        raise PlanError(f"remove_items must list all incident edges: {sorted(incident - existing_edge_ids)}")
    operations: list[dict[str, Any]] = [
        {"op": "remove_edge", "edge_id": edge_id, "before": copy.deepcopy(document.edge_map()[edge_id])}
        for edge_id in edge_ids
        if edge_id in document.edge_map()
    ]
    operations.extend(
        {"op": "remove_node", "node_id": node_id, "before": copy.deepcopy(document.node_map()[node_id])}
        for node_id in node_ids
        if node_id in document.node_map()
    )
    return operations


def _compile_map_issue(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    required = ("key", "label", "asked", "change", "evidence", "status", "done_when")
    if any(not isinstance(action.get(field), str) or not action[field].strip() for field in required):
        raise PlanError("map_issue requires non-empty key, label, asked, change, evidence, status, and done_when")
    if re.search(r"\bCR[-–— ]?\d+\b", action["label"], re.IGNORECASE):
        raise PlanError("map_issue must use a real reviewer label, not an invented CR identifier")
    if action["status"] not in {"wording", "ready", "pending", "author input", "blocked"}:
        raise PlanError("unsupported mapping status")
    target_ids = action.get("target_ids")
    if not isinstance(target_ids, list) or not target_ids or len(target_ids) != len(set(target_ids)):
        raise PlanError("map_issue target_ids must be a non-empty unique list")
    target_rect = node_rect(target_group)
    targets = [document.node(node_id) for node_id in target_ids]
    if any(node.get("type") == "group" or not target_rect.contains(node) for node in targets):
        raise PlanError("map_issue targets must be non-group nodes inside the mapped paper")
    width = action.get("width", 760)
    x, y = action.get("x"), action.get("y")
    if any(not isinstance(value, int) for value in (x, y, width)) or width <= 0:
        raise PlanError("map_issue x, y, and width must be integers with positive width")
    text = (
        f"# {action['label']}\n"
        f"Asked: {action['asked']}\n"
        f"Change: {action['change']}\n"
        f"Evidence: {action['evidence']}\n"
        f"Status: {action['status']}\n"
        f"Done when: {action['done_when']}"
    )
    node_id = action.get("node_id") or deterministic_id(target_group["id"], "mapping", action["key"])
    after = {
        "id": node_id,
        "type": "text",
        "x": x,
        "y": y,
        "width": width,
        "height": action.get("height", estimate_text_height(text, width, "paragraph")),
        "color": "2",
        "text": text,
    }
    if not target_rect.contains(after):
        raise PlanError("mapping card must remain inside the mapped paper group")
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    _append_operation(scratch, operations, _node_operation(scratch, after, target_group_id=target_group["id"]))
    for target in targets:
        card_center = after["x"] + after["width"] / 2
        target_center = target["x"] + target["width"] / 2
        from_side, to_side = (("right", "left") if card_center <= target_center else ("left", "right"))
        _append_operation(
            scratch,
            operations,
            _edge_operation(
                scratch,
                key_parts=[target_group["id"], "mapping_edge", action["key"], target["id"]],
                from_node=node_id,
                to_node=target["id"],
                from_side=from_side,
                to_side=to_side,
            ),
        )
    return operations


def _compile_mapping_master(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    key, items = action.get("key"), action.get("items")
    manuscript_ids = action.get("manuscript_node_ids")
    x, y, width = action.get("x"), action.get("y"), action.get("width", 800)
    if not isinstance(key, str) or not key or not isinstance(items, list) or not items:
        raise PlanError("mapping_master needs a key and items")
    if not isinstance(manuscript_ids, list) or not manuscript_ids or len(manuscript_ids) != len(set(manuscript_ids)):
        raise PlanError("mapping_master manuscript_node_ids must be a non-empty unique list")
    if any(not isinstance(value, int) for value in (x, y, width)) or width <= 0:
        raise PlanError("mapping_master geometry is invalid")
    allowed_status = {"wording", "ready", "pending", "author input", "blocked"}
    lines = ["# Camera-ready mapping checklist"]
    current_reviewer = None
    for item in items:
        required = ("reviewer", "label", "topic", "status")
        if not isinstance(item, dict) or any(not isinstance(item.get(field), str) or not item[field] for field in required):
            raise PlanError("each mapping master item needs reviewer, label, topic, and status")
        if item["status"] not in allowed_status or re.search(
            r"\bCR[-–— ]?\d+\b", " ".join(item[field] for field in required), re.IGNORECASE
        ):
            raise PlanError("mapping master items must use real reviewer labels and supported statuses")
        if item["reviewer"] != current_reviewer:
            current_reviewer = item["reviewer"]
            lines.extend(["", f"## {current_reviewer}"])
        lines.append(f"- {item['label']} · {item['topic']} · {item['status']}")
    manuscript = [document.node(node_id) for node_id in manuscript_ids]
    target_rect = node_rect(target_group)
    if any(node.get("type") == "group" or not target_rect.contains(node) for node in manuscript):
        raise PlanError("mapping master manuscript nodes must be inside the target paper")
    gap = action.get("gap", 120)
    if not isinstance(gap, int) or gap < 0 or x + width + gap > min(node["x"] for node in manuscript):
        raise PlanError("mapping master must be at the far left of the manuscript")
    text = "\n".join(lines)
    node_id = action.get("node_id") or deterministic_id(target_group["id"], "mapping_master", key)
    after = {
        "id": node_id,
        "type": "text",
        "x": x,
        "y": y,
        "width": width,
        "height": action.get("height", estimate_text_height(text, width, "paragraph")),
        "color": "2",
        "text": text,
    }
    if not target_rect.contains(after):
        raise PlanError("mapping master must remain inside the mapped paper group")
    if any(node_id in {edge["fromNode"], edge["toNode"]} for edge in document.edges):
        raise PlanError("mapping master must remain unconnected")
    operation = _node_operation(document, after, target_group_id=target_group["id"])
    return [operation] if operation else []


def _compile_layout_rebuttal(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    reviewer = action.get("reviewer")
    rows = action.get("rows")
    if rows is None:
        rows = [{"key": action.get("key"), "stages": action.get("stages")}]
    if not isinstance(rows, list) or not rows:
        raise PlanError("layout_rebuttal needs at least one row")
    for row in rows:
        stages = row.get("stages") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("key"), str)
            or not row["key"]
            or not isinstance(stages, list)
            or len(stages) != 6
            or any(not isinstance(text, str) for text in stages)
        ):
            raise PlanError("each rebuttal row needs a key and exactly six stage strings")
    x, y = action.get("x"), action.get("y")
    if not isinstance(reviewer, str) or not reviewer:
        raise PlanError("layout_rebuttal needs a reviewer")
    if not isinstance(x, int) or not isinstance(y, int):
        raise PlanError("layout_rebuttal x and y must be integers")
    widths, gaps = [625, 625, 520, 660, 660, 660], [73, 55, 160, 20, 40]
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    header_id = deterministic_id(target_group["id"], "rebuttal_header", reviewer)
    header = copy.deepcopy(scratch.node_map().get(header_id)) if header_id in scratch.node_map() else {"id": header_id, "type": "text"}
    header.update({"x": x, "y": y, "width": 200, "height": 50, "text": f"# {reviewer}"})
    _append_operation(scratch, operations, _node_operation(scratch, header, target_group_id=target_group["id"]))
    row_y = y + 130
    managed_ids = [header_id]
    for row in rows:
        cursor_x = x
        row_ids: list[str] = []
        for index, (text, width) in enumerate(zip(row["stages"], widths, strict=True)):
            node_id = deterministic_id(target_group["id"], "rebuttal_stage", row["key"], str(index))
            after = copy.deepcopy(scratch.node_map().get(node_id)) if node_id in scratch.node_map() else {"id": node_id, "type": "text"}
            after.update({
                "x": cursor_x,
                "y": row_y,
                "width": width,
                "height": estimate_text_height(text, width, "paragraph"),
                "text": text,
            })
            _append_operation(scratch, operations, _node_operation(scratch, after, target_group_id=target_group["id"]))
            row_ids.append(node_id)
            cursor_x += width + (gaps[index] if index < len(gaps) else 0)
        managed_ids.extend(row_ids)
        row_y += max(scratch.node(node_id)["height"] for node_id in row_ids) + 80
    managed = [scratch.node(node_id) for node_id in managed_ids]
    group_after = copy.deepcopy(scratch.node(target_group["id"]))
    group_after["width"] = max(group_after["width"], max(node["x"] + node["width"] for node in managed) - group_after["x"] + 20)
    group_after["height"] = max(group_after["height"], max(node["y"] + node["height"] for node in managed) - group_after["y"] + 20)
    _append_operation(scratch, operations, _node_operation(scratch, group_after))
    return operations


def _compile_add_research_flow(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    specs, links = action.get("nodes"), action.get("links", [])
    if not isinstance(specs, list) or not specs or not isinstance(links, list):
        raise PlanError("add_research_flow needs nodes and links lists")
    colors = {"rq": "6", "experiment": "4", "answer": "3", "bridge": "2", "thought": "1"}
    keys = [spec.get("key") for spec in specs if isinstance(spec, dict)]
    if len(keys) != len(specs) or len(keys) != len(set(keys)) or any(not isinstance(key, str) or not key for key in keys):
        raise PlanError("research-flow node keys must be unique non-empty strings")
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    entry_ids: dict[str, str] = {}
    exit_ids: dict[str, str] = {}
    kinds: dict[str, str] = {}
    target_rect = node_rect(target_group)
    for spec in specs:
        kind, text = spec.get("kind"), spec.get("text")
        if kind not in {*colors, "source", "table", "figure"} or not isinstance(text, str) or not text.strip():
            raise PlanError("invalid research-flow node kind or text")
        node_id = spec.get("node_id") or deterministic_id(target_group["id"], "research_flow", spec["key"])
        width = spec.get("width", 812)
        x, y = spec.get("x"), spec.get("y")
        if any(not isinstance(value, int) for value in (x, y, width)) or width <= 0:
            raise PlanError("research-flow node geometry must use integers")
        rendered_text = text if kind in {"bridge", "thought", "source", "table", "figure"} or text.startswith("#") else f"# {text}"
        if kind == "figure":
            if not isinstance(spec.get("file"), str) or not spec["file"]:
                raise PlanError("research-flow figures need a file")
            after = {
                "id": node_id,
                "type": "file",
                "file": spec["file"],
                "x": x,
                "y": y,
                "width": width,
                "height": spec.get("height", 400),
            }
        else:
            after = {
                "id": node_id,
                "type": "text",
                "x": x,
                "y": y,
                "width": width,
                "height": spec.get("height", estimate_text_height(rendered_text, width, "heading" if rendered_text.startswith("#") else "paragraph")),
                "text": rendered_text,
            }
        if kind in colors:
            after["color"] = colors[kind]
        if not target_rect.contains(after):
            raise PlanError("research-flow node is outside the target group")
        entry_ids[spec["key"]] = node_id
        exit_ids[spec["key"]] = node_id
        kinds[spec["key"]] = kind
        _append_operation(scratch, operations, _node_operation(scratch, after, target_group_id=target_group["id"]))
        sections = spec.get("sections")
        if sections is not None:
            if kind != "experiment" or not isinstance(sections, list) or not sections:
                raise PlanError("only experiment nodes may have non-empty sections")
            section_y = after["y"] + after["height"] + 20
            for section in sections:
                if (
                    not isinstance(section, dict)
                    or not isinstance(section.get("key"), str)
                    or not section["key"]
                    or not isinstance(section.get("heading"), str)
                    or not isinstance(section.get("text"), str)
                ):
                    raise PlanError("experiment sections need key, heading, and text")
                section_key = f"{spec['key']}:{section['key']}"
                if section_key in entry_ids:
                    raise PlanError("experiment section keys must be unique")
                section_id = deterministic_id(target_group["id"], "research_flow", spec["key"], section["key"])
                section_text = f"## {section['heading']}\n{section['text']}"
                section_node = {
                    "id": section_id,
                    "type": "text",
                    "x": x,
                    "y": section_y,
                    "width": width,
                    "height": section.get("height", estimate_text_height(section_text, width, "paragraph")),
                    "color": "4",
                    "text": section_text,
                }
                if not target_rect.contains(section_node):
                    raise PlanError("research-flow experiment section is outside the target group")
                entry_ids[section_key] = section_id
                exit_ids[section_key] = section_id
                kinds[section_key] = "experiment-section"
                exit_ids[spec["key"]] = section_id
                _append_operation(scratch, operations, _node_operation(scratch, section_node, target_group_id=target_group["id"]))
                section_y += section_node["height"] + 20
    for link in links:
        if not isinstance(link, list) or len(link) != 2 or link[0] not in exit_ids or link[1] not in entry_ids:
            raise PlanError("research-flow links must contain two known keys")
        side = "right" if kinds[link[0]] == "thought" else "bottom"
        target_side = "left" if side == "right" else "top"
        _append_operation(
            scratch,
            operations,
            _edge_operation(
                scratch,
                key_parts=[target_group["id"], "research_edge", *link],
                from_node=exit_ids[link[0]],
                to_node=entry_ids[link[1]],
                from_side=side,
                to_side=target_side,
            ),
        )
    return operations


def _compile_build_camera_ready(
    document: CanvasDocument,
    action: dict[str, Any],
    target_group: dict[str, Any],
) -> list[dict[str, Any]]:
    key, label = action.get("key"), action.get("label")
    source_node_ids = action.get("source_node_ids")
    source_group_ids = action.get("source_group_ids", [])
    source_edge_ids = action.get("source_edge_ids", [])
    x, y = action.get("x"), action.get("y")
    if not isinstance(key, str) or not key or label != "paper_camera_ready":
        raise PlanError("build_camera_ready needs a key and label paper_camera_ready")
    if any(not isinstance(value, list) for value in (source_node_ids, source_group_ids, source_edge_ids)):
        raise PlanError("camera-ready source ids must be lists")
    if not isinstance(x, int) or not isinstance(y, int):
        raise PlanError("camera-ready x and y must be integers")
    final_group_id = action.get("group_id") or deterministic_id("camera_ready", key, "group")
    existing_final = document.node_map().get(final_group_id)
    if existing_final and existing_final.get("type") != "group":
        raise PlanError("camera-ready group_id belongs to a non-group node")
    duplicate_groups = [
        group["id"]
        for group in document.nodes
        if group.get("type") == "group"
        and group.get("label") == "paper_camera_ready"
        and group["id"] != final_group_id
    ]
    if duplicate_groups:
        raise PlanError(f"another paper_camera_ready group already exists: {duplicate_groups}")
    target_rect = node_rect(target_group)
    source_nodes = [document.node(node_id) for node_id in source_node_ids]
    source_groups = [document.node(group_id) for group_id in source_group_ids]
    if any(node.get("type") == "group" or not target_rect.contains(node) for node in source_nodes):
        raise PlanError("camera-ready source nodes must be non-groups inside the source paper")
    if any(group.get("type") != "group" or not target_rect.contains(group) for group in source_groups):
        raise PlanError("camera-ready source groups must be nested groups inside the source paper")
    if any(
        node.get("color") == "2"
        and all(field in node.get("text", "") for field in ("Asked:", "Change:", "Status:"))
        for node in source_nodes
    ):
        raise PlanError("camera-ready source_node_ids cannot include mapping nodes")
    if any("appendix" in group.get("label", "").lower() and "·" not in group.get("label", "") for group in source_groups):
        raise PlanError("camera-ready cannot copy a manuscript-wide Appendix group")
    if len(set(source_node_ids + source_group_ids)) != len(source_node_ids) + len(source_group_ids):
        raise PlanError("camera-ready source ids must be unique")
    changes = action.get("changes", [])
    additions = action.get("additions", [])
    blockers = action.get("blockers", [])
    if not isinstance(changes, list) or not isinstance(additions, list) or not isinstance(blockers, list):
        raise PlanError("camera-ready changes, additions, and blockers must be lists")
    change_map = {change.get("source_id"): change for change in changes if isinstance(change, dict)}
    if len(change_map) != len(changes) or any(source_id not in source_node_ids for source_id in change_map):
        raise PlanError("each camera-ready change needs one known source_id")

    dx, dy = x - target_group["x"], y - target_group["y"]
    clone_ids = {
        source_id: deterministic_id("camera_ready", key, source_id)
        for source_id in source_node_ids + source_group_ids
    }
    scratch = CanvasDocument(copy.deepcopy(document.data))
    operations: list[dict[str, Any]] = []
    desired_node_ids = set(clone_ids.values())
    desired_node_ids.update(
        addition.get("node_id") or deterministic_id("camera_ready", key, "addition", addition.get("key", ""))
        for addition in additions
        if isinstance(addition, dict)
    )
    desired_node_ids.update(
        deterministic_id("camera_ready", key, "blocker", blocker.get("key", ""))
        for blocker in blockers
        if isinstance(blocker, dict)
    )
    desired_edge_ids = {
        deterministic_id("camera_ready", key, edge_id) for edge_id in source_edge_ids
    }
    desired_edge_ids.update(
        deterministic_id("camera_ready", key, "blocker_edge", blocker.get("key", ""))
        for blocker in blockers
        if isinstance(blocker, dict)
    )
    if existing_final:
        existing_rect = node_rect(existing_final)
        existing_members = [
            node for node in scratch.nodes if node["id"] != final_group_id and existing_rect.contains(node)
        ]
        existing_member_ids = {node["id"] for node in existing_members}
        stale_edge_ids = [
            edge["id"]
            for edge in scratch.edges
            if (edge["fromNode"] in existing_member_ids or edge["toNode"] in existing_member_ids)
            and edge["id"] not in desired_edge_ids
        ]
        for edge_id in stale_edge_ids:
            edge = copy.deepcopy(scratch.edge_map()[edge_id])
            operation = {"op": "remove_edge", "edge_id": edge_id, "before": edge}
            _append_operation(scratch, operations, operation)
        for node in existing_members:
            if node["id"] not in desired_node_ids:
                operation = {"op": "remove_node", "node_id": node["id"], "before": copy.deepcopy(node)}
                _append_operation(scratch, operations, operation)
    final_member_ids: list[str] = []
    for source in [*source_groups, *source_nodes]:
        after = copy.deepcopy(source)
        after["id"] = clone_ids[source["id"]]
        after["x"] += dx
        after["y"] += dy
        if source["id"] in change_map:
            change = change_map[source["id"]]
            for field in ("text", "file", "width", "height", "x", "y"):
                if field in change:
                    after[field] = change[field]
                    if field == "x":
                        after[field] += dx
                    elif field == "y":
                        after[field] += dy
            after["color"] = "3"
        _append_operation(scratch, operations, _node_operation(scratch, after))
        if source.get("type") != "group":
            final_member_ids.append(after["id"])

    edge_map = document.edge_map()
    for edge_id in source_edge_ids:
        edge = edge_map.get(edge_id)
        if not edge or edge["fromNode"] not in clone_ids or edge["toNode"] not in clone_ids:
            raise PlanError("camera-ready edges must connect selected source nodes")
        after = copy.deepcopy(edge)
        after["id"] = deterministic_id("camera_ready", key, edge_id)
        after["fromNode"] = clone_ids[edge["fromNode"]]
        after["toNode"] = clone_ids[edge["toNode"]]
        existing = scratch.edge_map().get(after["id"])
        _append_operation(scratch, operations, None if existing == after else {"op": "upsert_edge", "edge_id": after["id"], "before": copy.deepcopy(existing) if existing else None, "after": after})

    for addition in additions:
        required = ("key", "kind", "x", "y", "width", "height")
        if not isinstance(addition, dict) or any(field not in addition for field in required):
            raise PlanError("camera-ready additions need key, kind, x, y, width, and height")
        if addition["kind"] not in {"sentence", "heading", "equation", "table", "figure"}:
            raise PlanError("unsupported camera-ready addition kind")
        if not isinstance(addition["key"], str) or not addition["key"] or any(
            not isinstance(addition[field], int) for field in ("x", "y", "width", "height")
        ) or addition["width"] <= 0 or addition["height"] <= 0:
            raise PlanError("camera-ready addition geometry is invalid")
        addition_id = addition.get("node_id") or deterministic_id("camera_ready", key, "addition", addition["key"])
        if addition["kind"] == "figure":
            if not isinstance(addition.get("file"), str) or not addition["file"]:
                raise PlanError("camera-ready figure additions need a file")
            after = {"id": addition_id, "type": "file", "file": addition["file"]}
        else:
            text = addition.get("text")
            if not isinstance(text, str) or not text.strip():
                raise PlanError("camera-ready text additions need text")
            if addition["kind"] == "equation" and not (text.strip().startswith("$$") and text.strip().endswith("$$")):
                raise PlanError("camera-ready equation additions require $$...$$")
            if addition["kind"] == "table" and "|" not in text:
                raise PlanError("camera-ready table additions need a Markdown table")
            after = {"id": addition_id, "type": "text", "text": text}
        after.update({
            "x": addition["x"] + dx,
            "y": addition["y"] + dy,
            "width": addition["width"],
            "height": addition["height"],
            "color": "3",
        })
        for existing_id in final_member_ids:
            if rects_overlap(node_rect(after), node_rect(scratch.node(existing_id))):
                raise PlanError(f"camera-ready addition would overlap node: {existing_id}")
        _append_operation(scratch, operations, _node_operation(scratch, after))
        final_member_ids.append(addition_id)

    for blocker in blockers:
        required = ("key", "topic", "label", "target_source_id")
        if not isinstance(blocker, dict) or any(not isinstance(blocker.get(field), str) or not blocker[field] for field in required):
            raise PlanError("camera-ready blockers need key, topic, label, and target_source_id")
        if blocker["target_source_id"] not in clone_ids:
            raise PlanError("camera-ready blocker target is not selected")
        target = scratch.node(clone_ids[blocker["target_source_id"]])
        text = f"# Author input required · {blocker['topic']}\n{blocker['label']}"
        blocker_id = deterministic_id("camera_ready", key, "blocker", blocker["key"])
        after = {
            "id": blocker_id,
            "type": "text",
            "x": target["x"] + target["width"] + 20,
            "y": target["y"],
            "width": blocker.get("width", 520),
            "height": blocker.get("height", estimate_text_height(text, blocker.get("width", 520), "paragraph")),
            "color": "3",
            "text": text,
        }
        _append_operation(scratch, operations, _node_operation(scratch, after))
        final_member_ids.append(blocker_id)
        _append_operation(
            scratch,
            operations,
            _edge_operation(
                scratch,
                key_parts=["camera_ready", key, "blocker_edge", blocker["key"]],
                from_node=blocker_id,
                to_node=target["id"],
                from_side="left",
                to_side="right",
            ),
        )

    members = [scratch.node(node_id) for node_id in final_member_ids]
    rect = bounding_rect(members, action.get("padding", 20))
    existing_group = scratch.node_map().get(final_group_id)
    final_group = copy.deepcopy(existing_group) if existing_group else {"id": final_group_id, "type": "group"}
    final_group.update({"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height, "label": label})
    group_operation = _node_operation(scratch, final_group)
    if group_operation:
        group_operation["member_ids"] = final_member_ids
        group_operation["padding"] = action.get("padding", 20)
    _append_operation(scratch, operations, group_operation)
    nested_ids = set(clone_ids[group_id] for group_id in source_group_ids)
    for other in scratch.nodes:
        if other.get("type") == "group" and other["id"] not in {target_group["id"], final_group_id, *nested_ids} and rects_overlap(rect, node_rect(other)):
            raise PlanError(f"camera-ready group would overlap sibling group: {other['id']}")
    return operations


REQUEST_COMPILERS: dict[
    str, Callable[[CanvasDocument, dict[str, Any], dict[str, Any]], list[dict[str, Any]]]
] = {
    "group_appendix": _compile_group_appendix,
    "insert_blocks": _compile_insert_blocks,
    "place_artifact": _compile_place_artifact,
    "pair_appendix_columns": _compile_pair_appendix_columns,
    "split_citation": _compile_split_citation,
    "connect_reference": _compile_connect_reference,
    "fit_section_title": _compile_fit_section_title,
    "move_nodes": _compile_move_nodes,
    "shift_sibling_group": _compile_shift_sibling_group,
    "normalize_equations": _compile_normalize_equations,
    "map_issue": _compile_map_issue,
    "mapping_master": _compile_mapping_master,
    "remove_items": _compile_remove_items,
    "layout_rebuttal": _compile_layout_rebuttal,
    "add_research_flow": _compile_add_research_flow,
    "build_camera_ready": _compile_build_camera_ready,
}

WORKFLOW_ACTIONS = {
    "paper": {
        "group_appendix",
        "insert_blocks",
        "place_artifact",
        "pair_appendix_columns",
        "split_citation",
        "connect_reference",
        "fit_section_title",
        "move_nodes",
        "shift_sibling_group",
        "normalize_equations",
    },
    "camera-ready-mapping": {"map_issue", "mapping_master", "remove_items"},
    "camera-ready": {"build_camera_ready"},
    "rebuttal": {"layout_rebuttal"},
    "research-flow": {"add_research_flow"},
}


def _apply_operation(document: CanvasDocument, operation: dict[str, Any], *, check_before: bool) -> None:
    kind = operation.get("op")
    if kind in {"upsert_group", "upsert_node"}:
        node_id = operation["node_id"]
        current = document.node_map().get(node_id)
        if check_before and current != operation.get("before"):
            raise PreconditionError(f"node changed before apply: {node_id}")
        after = copy.deepcopy(operation["after"])
        if current is None:
            if kind == "upsert_group":
                insert_at = next(
                    (index for index, node in enumerate(document.nodes) if node.get("type") != "group"),
                    len(document.nodes),
                )
            else:
                predecessor_id = operation.get("insert_after_id")
                insert_at = len(document.nodes)
                if predecessor_id:
                    predecessor = document.node(predecessor_id)
                    insert_at = document.nodes.index(predecessor) + 1
            document.nodes.insert(insert_at, after)
        else:
            document.nodes[document.nodes.index(current)] = after
        return
    if kind == "translate_nodes":
        for node_id, before in operation["before"].items():
            node = document.node(node_id)
            current = {"x": node["x"], "y": node["y"]}
            if check_before and current != before:
                raise PreconditionError(f"node moved before apply: {node_id}")
        for node_id, after in operation["after"].items():
            node = document.node(node_id)
            node.update(after)
        return
    if kind == "upsert_edge":
        edge_id = operation["edge_id"]
        current = document.edge_map().get(edge_id)
        if check_before and current != operation.get("before"):
            raise PreconditionError(f"edge changed before apply: {edge_id}")
        after = copy.deepcopy(operation["after"])
        if current is None:
            document.edges.append(after)
        else:
            document.edges[document.edges.index(current)] = after
        return
    if kind == "remove_edge":
        current = document.edge_map().get(operation["edge_id"])
        if check_before and current != operation.get("before"):
            raise PreconditionError(f"edge changed before removal: {operation['edge_id']}")
        if current is not None:
            document.edges.remove(current)
        return
    if kind == "remove_node":
        current = document.node_map().get(operation["node_id"])
        if check_before and current != operation.get("before"):
            raise PreconditionError(f"node changed before removal: {operation['node_id']}")
        if current is not None:
            document.nodes.remove(current)
        return
    raise PlanError(f"unsupported patch operation: {kind!r}")


def _validate_patch_result(document: CanvasDocument, operations: list[dict[str, Any]]) -> None:
    document.validate_integrity()
    removed_node_ids = {operation["node_id"] for operation in operations if operation["op"] == "remove_node"}
    removed_edge_ids = {operation["edge_id"] for operation in operations if operation["op"] == "remove_edge"}
    for operation in operations:
        kind = operation["op"]
        if kind == "upsert_group":
            if operation["node_id"] in removed_node_ids:
                continue
            group = document.node(operation["node_id"])
            if "member_ids" in operation:
                members = [document.node(node_id) for node_id in operation["member_ids"]]
                expected = bounding_rect(members, operation["padding"])
                if node_rect(group) != expected:
                    raise PlanError(f"group bounds do not match members: {group['id']}")
                if "target_group_id" in operation:
                    target = document.node(operation["target_group_id"])
                    if not node_rect(target).contains(group):
                        raise PlanError(f"group is outside target: {group['id']}")
                    captured = {node["id"] for node in document.contained_non_groups(expected)}
                    if captured != set(operation["member_ids"]):
                        raise PlanError(f"group membership mismatch: {group['id']}")
        elif kind == "upsert_node":
            if operation["node_id"] in removed_node_ids:
                continue
            node = document.node(operation["node_id"])
            if "target_group_id" in operation and not node_rect(document.node(operation["target_group_id"])).contains(node):
                raise PlanError(f"inserted node is outside target: {node['id']}")
        elif kind == "translate_nodes":
            target = node_rect(document.node(operation["target_group_id"]))
            if any(
                not target.contains(document.node(node_id))
                for node_id in operation["after"]
                if node_id not in removed_node_ids
            ):
                raise PlanError("translated node is outside target group")
        elif kind == "upsert_edge":
            if operation["edge_id"] in removed_edge_ids:
                continue
            edge = document.edge_map().get(operation["edge_id"])
            if edge != operation["after"]:
                raise PlanError(f"edge does not match patch: {operation['edge_id']}")


def compile_request(canvas: Path, request: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") != 1:
        raise PlanError("unsupported request schema_version")
    workflow = request.get("workflow")
    if workflow not in WORKFLOW_ACTIONS:
        raise PlanError(f"unsupported workflow: {workflow!r}")
    actions = request.get("actions")
    if not isinstance(actions, list):
        raise PlanError("request actions must be a list")

    document = CanvasDocument.load(canvas)
    target_group = document.resolve_group(request.get("target", {}))
    operations: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise PlanError("each action must be an object")
        compiler = REQUEST_COMPILERS.get(action.get("op"))
        if compiler is None or action.get("op") not in WORKFLOW_ACTIONS[workflow]:
            raise PlanError(f"unsupported request action: {action.get('op')!r}")
        try:
            compiled = compiler(document, action, document.node(target_group["id"]))
        except PlanError as exc:
            raise PlanError(f"action[{index}] {action.get('op')}: {exc}") from exc
        for operation in compiled:
            operations.append(operation)
            _apply_operation(document, operation, check_before=False)
    _validate_patch_result(document, operations)
    return {
        "schema_version": 1,
        "workflow": request["workflow"],
        "canvas": str(canvas),
        "expected_sha256": canvas_sha256(canvas),
        "operations": operations,
    }


def _dump_canvas(data: dict[str, Any]) -> str:
    lines = ["{", '\t"nodes":[']
    lines.extend(
        f"\t\t{json.dumps(node, ensure_ascii=False, separators=(',', ':'))}{',' if index < len(data['nodes']) - 1 else ''}"
        for index, node in enumerate(data["nodes"])
    )
    lines.extend(["\t],", '\t"edges":['])
    lines.extend(
        f"\t\t{json.dumps(edge, ensure_ascii=False, separators=(',', ':'))}{',' if index < len(data['edges']) - 1 else ''}"
        for index, edge in enumerate(data["edges"])
    )
    lines.extend(["\t]", "}", ""])
    return "\n".join(lines)


def apply_patch(canvas: Path, patch: dict[str, Any], log: Path | None = None) -> dict[str, Any]:
    expected_hash = patch.get("expected_sha256")
    if canvas_sha256(canvas) != expected_hash:
        raise PreconditionError("Canvas SHA-256 does not match the compiled patch")
    operations = patch.get("operations")
    if not isinstance(operations, list):
        raise PlanError("patch operations must be a list")
    if not operations:
        return {"status": "no-op", "operations": 0, "backup": None}

    document = CanvasDocument.load(canvas)
    for operation in operations:
        _apply_operation(document, operation, check_before=True)
    _validate_patch_result(document, operations)
    rendered = _dump_canvas(document.data)

    history = canvas.parent / ".canvas-history"
    history.mkdir(exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    backup = history / f"{canvas.stem}.{stamp}.before-obs-paper.canvas"
    suffix = 2
    while backup.exists():
        backup = history / f"{canvas.stem}.{stamp}-{suffix}.before-obs-paper.canvas"
        suffix += 1
    shutil.copy2(canvas, backup)

    if canvas_sha256(canvas) != expected_hash:
        raise PreconditionError("Canvas changed while the patch was being applied")
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=canvas.parent, prefix=f".{canvas.name}.", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, canvas)
    finally:
        temporary.unlink(missing_ok=True)

    CanvasDocument.load(canvas)
    result = {
        "status": "applied",
        "operations": len(operations),
        "backup": str(backup),
        "sha256": canvas_sha256(canvas),
    }
    if log is not None:
        append_action(
            log,
            status="done",
            action="apply JSON Canvas patch",
            target=str(canvas),
            reason=f"workflow={patch.get('workflow')}",
            result=f"Applied {len(operations)} operation(s); backup={backup.name}",
        )
    return result


def inspect_canvas(canvas: Path, target: dict[str, Any] | None = None) -> dict[str, Any]:
    document = CanvasDocument.load(canvas)
    nodes = document.nodes
    if target:
        group = document.resolve_group(target)
        rect = node_rect(group)
        nodes = [node for node in nodes if node["id"] == group["id"] or rect.contains(node)]
    return {
        "canvas": str(canvas),
        "sha256": canvas_sha256(canvas),
        "nodes": [
            {
                "id": node["id"],
                "type": node["type"],
                "x": node["x"],
                "y": node["y"],
                "width": node["width"],
                "height": node["height"],
                **({"label": node["label"]} if "label" in node else {}),
                **({"text": node["text"].splitlines()[0]} if "text" in node else {}),
                **({"file": node["file"]} if "file" in node else {}),
            }
            for node in nodes
        ],
        "edge_count": len(document.edges),
    }


def validate_canvas(canvas: Path) -> dict[str, Any]:
    document = CanvasDocument.load(canvas)
    return {
        "status": "valid",
        "nodes": len(document.nodes),
        "edges": len(document.edges),
        "sha256": canvas_sha256(canvas),
    }
