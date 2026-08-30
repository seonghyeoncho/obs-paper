from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "plugins/paper-canvas-workflow/scripts"
sys.path.insert(0, str(SCRIPTS))

from obs_paper_engine import (  # noqa: E402
    CanvasDocument,
    PlanError,
    PreconditionError,
    apply_patch,
    compile_document,
    compile_request,
    deterministic_id,
    estimate_text_height,
    inspect_canvas,
    node_rect,
)


def fixture_canvas(*, existing_group: bool = False, extra_inside: bool = False) -> dict:
    nodes = [
        {"id": "paper", "type": "group", "x": 0, "y": 0, "width": 3000, "height": 3000, "label": "paper_v1"},
        {"id": "b", "type": "text", "x": 1000, "y": 100, "width": 800, "height": 70, "text": "# Appendix B"},
        {"id": "b1", "type": "text", "x": 1000, "y": 190, "width": 800, "height": 70, "text": "B sentence."},
        {"id": "c", "type": "text", "x": 1000, "y": 300, "width": 800, "height": 70, "text": "# Appendix C"},
        {"id": "c1", "type": "text", "x": 1000, "y": 390, "width": 800, "height": 70, "text": "C sentence."},
        {"id": "main", "type": "text", "x": 100, "y": 100, "width": 800, "height": 70, "text": "Main sentence."},
    ]
    if existing_group:
        nodes.insert(1, {"id": "appendix-group", "type": "group", "x": 980, "y": 80, "width": 840, "height": 400, "label": "무제 그룹"})
    if extra_inside:
        nodes.append({"id": "extra", "type": "text", "x": 1200, "y": 250, "width": 200, "height": 40, "text": "Unlisted."})
    return {"nodes": nodes, "edges": []}


def request(*, group_id: str | None = None) -> dict:
    action = {
        "op": "group_appendix",
        "label": "Results · Appendix B–C",
        "member_ids": ["b", "b1", "c", "c1"],
        "padding": 20,
    }
    if group_id:
        action["group_id"] = group_id
    return {
        "schema_version": 1,
        "workflow": "paper",
        "target": {"group_label": "paper_v1"},
        "actions": [action],
    }


class ObsPaperEngineTest(unittest.TestCase):
    def write_canvas(self, root: Path, data: dict) -> Path:
        path = root / "paper.canvas"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_create_group_and_rerun_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canvas = self.write_canvas(root, fixture_canvas())
            patch = compile_request(canvas, request())
            self.assertEqual(len(patch["operations"]), 1)
            result = apply_patch(canvas, patch)
            self.assertEqual(result["status"], "applied")
            group = next(node for node in CanvasDocument.load(canvas).nodes if node.get("label") == "Results · Appendix B–C")
            self.assertEqual((group["x"], group["y"], group["width"], group["height"]), (980, 80, 840, 400))
            self.assertEqual(compile_request(canvas, request())["operations"], [])

    def test_compile_document_needs_no_canvas_file(self) -> None:
        patch = compile_document(
            fixture_canvas(), request(), document_id="blocksuite-doc-1"
        )
        self.assertEqual(patch["document_id"], "blocksuite-doc-1")
        self.assertEqual(len(patch["operations"]), 1)
        self.assertNotIn("canvas", patch)

    def test_existing_group_is_renamed_without_replacing_its_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas(existing_group=True))
            patch = compile_request(canvas, request(group_id="appendix-group"))
            apply_patch(canvas, patch)
            group = CanvasDocument.load(canvas).node("appendix-group")
            self.assertEqual(group["label"], "Results · Appendix B–C")

    def test_unlisted_node_inside_group_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas(extra_inside=True))
            with self.assertRaisesRegex(PlanError, "unlisted nodes"):
                compile_request(canvas, request())

    def test_sha_mismatch_preserves_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas())
            patch = compile_request(canvas, request())
            changed = copy.deepcopy(json.loads(canvas.read_text()))
            changed["nodes"][-1]["text"] = "User edit."
            canvas.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(PreconditionError):
                apply_patch(canvas, patch)
            self.assertEqual(json.loads(canvas.read_text()), changed)

    def test_insert_blocks_shifts_downstream_and_refits_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas(existing_group=True))
            insert_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [
                    {
                        "op": "insert_blocks",
                        "anchor_id": "b1",
                        "blocks": [
                            {"key": "audit-method", "kind": "sentence", "text": "Audit method.", "height": 70},
                            {"key": "audit-result", "kind": "paragraph", "text": "Audit result.", "height": 70},
                        ],
                        "shift_node_ids": ["c", "c1"],
                        "fit_group_id": "appendix-group",
                    }
                ],
            }
            patch = compile_request(canvas, insert_request)
            self.assertEqual(len(patch["operations"]), 4)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            inserted = sorted(
                [node for node in document.nodes if node.get("text") in {"Audit method.", "Audit result."}],
                key=lambda node: node["y"],
            )
            self.assertEqual([node["y"] for node in inserted], [280, 390])
            self.assertEqual([document.node(node_id)["y"] for node_id in ("c", "c1")], [480, 570])
            group = document.node("appendix-group")
            self.assertEqual((group["x"], group["y"], group["width"], group["height"]), (980, 80, 840, 580))
            self.assertEqual(compile_request(canvas, insert_request)["operations"], [])

    def test_insert_blocks_rejects_artifacts_in_prose_stack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas())
            insert_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [
                    {
                        "op": "insert_blocks",
                        "anchor_id": "b1",
                        "blocks": [{"key": "table", "kind": "table", "text": "| A |"}],
                    }
                ],
            }
            with self.assertRaisesRegex(PlanError, "does not place artifact"):
                compile_request(canvas, insert_request)

    def test_paper_colors_are_derived_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][1]["color"] = "1"
            data["nodes"][2]["color"] = "3"
            data["nodes"][-1]["color"] = "2"
            canvas = self.write_canvas(Path(directory), data)
            normalize_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [
                    {
                        "op": "normalize_paper_colors",
                        "node_ids": ["b", "b1", "main"],
                        "contribution_ids": ["b1"],
                    }
                ],
            }
            apply_patch(canvas, compile_request(canvas, normalize_request))
            document = CanvasDocument.load(canvas)
            self.assertEqual(document.node("b").get("color"), "6")
            self.assertEqual(document.node("b1").get("color"), "4")
            self.assertNotIn("color", document.node("main"))
            self.assertEqual(compile_request(canvas, normalize_request)["operations"], [])

            insert_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [
                    {
                        "op": "insert_blocks",
                        "anchor_id": "main",
                        "blocks": [
                            {"key": "methods", "kind": "heading", "text": "# Methods", "height": 70},
                            {"key": "contribution", "kind": "sentence", "role": "contribution", "text": "Contribution.", "height": 70},
                        ],
                    }
                ],
            }
            patch = compile_request(canvas, insert_request)
            inserted = [operation["after"] for operation in patch["operations"] if operation["op"] == "upsert_node"]
            self.assertEqual([node.get("color") for node in inserted], ["6", "4"])

    def test_compact_sections_uses_complete_title_rectangles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = {
                "nodes": [
                    {"id": "paper", "type": "group", "x": 0, "y": 0, "width": 4000, "height": 1000, "label": "paper_v1"},
                    {"id": "s1", "type": "text", "x": 100, "y": 100, "width": 800, "height": 70, "color": "6", "text": "# First"},
                    {"id": "s1-body", "type": "text", "x": 100, "y": 190, "width": 800, "height": 70, "text": "First body."},
                    {"id": "s2", "type": "text", "x": 2200, "y": 100, "width": 1200, "height": 70, "color": "6", "text": "# Second"},
                    {"id": "s2-body", "type": "text", "x": 2400, "y": 190, "width": 800, "height": 70, "text": "Second body."},
                ],
                "edges": [],
            }
            canvas = self.write_canvas(Path(directory), data)
            compact_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [
                    {
                        "op": "compact_sections",
                        "sections": [
                            {"title_id": "s1", "node_ids": ["s1", "s1-body"]},
                            {"title_id": "s2", "node_ids": ["s2", "s2-body"]},
                        ],
                    }
                ],
            }
            apply_patch(canvas, compile_request(canvas, compact_request))
            document = CanvasDocument.load(canvas)
            self.assertEqual(document.node("s2")["x"], 1020)
            self.assertEqual(document.node("s2-body")["x"], 1220)
            self.assertEqual(compile_request(canvas, compact_request)["operations"], [])

    def test_insert_blocks_rejects_missing_downstream_shift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas())
            insert_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [
                    {
                        "op": "insert_blocks",
                        "anchor_id": "b1",
                        "blocks": [
                            {"key": "missing-shift", "kind": "sentence", "text": "Would overlap.", "height": 70}
                        ],
                    }
                ],
            }
            with self.assertRaisesRegex(PlanError, "would overlap nodes"):
                compile_request(canvas, insert_request)

    def test_place_artifact_adds_outside_card_and_reference_edge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].append(
                {"id": "mention", "type": "text", "x": 1000, "y": 600, "width": 800, "height": 70, "text": "Figure 1 shows the result."}
            )
            canvas = self.write_canvas(Path(directory), data)
            artifact_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "place_artifact",
                    "key": "figure-1",
                    "kind": "figure",
                    "file": "fig1.png",
                    "mention_ids": ["mention"],
                    "lane": "left",
                    "width": 600,
                    "height": 400,
                }],
            }
            patch = compile_request(canvas, artifact_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            artifact = next(node for node in document.nodes if node.get("file") == "fig1.png")
            self.assertEqual(artifact["x"] + artifact["width"] + 20, document.node("mention")["x"])
            edge = next(edge for edge in document.edges if edge["fromNode"] == artifact["id"])
            self.assertEqual((edge["fromSide"], edge["toSide"]), ("right", "left"))
            self.assertEqual(compile_request(canvas, artifact_request)["operations"], [])

    def test_mapping_issue_uses_real_label_and_does_not_mutate_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].append(
                {"id": "target", "type": "text", "x": 1800, "y": 600, "width": 800, "height": 70, "text": "Original manuscript sentence."}
            )
            canvas = self.write_canvas(Path(directory), data)
            mapping_request = {
                "schema_version": 1,
                "workflow": "camera-ready-mapping",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "map_issue",
                    "key": "r3-w3-human-audit",
                    "label": "R3 · W3 · Human audit reliability",
                    "asked": "Report a human audit.",
                    "change": "Add the audit result to Appendix G.",
                    "evidence": "50 audited cases.",
                    "status": "ready",
                    "done_when": "The full audit table is present.",
                    "target_ids": ["target"],
                    "x": 1000,
                    "y": 600,
                }],
            }
            patch = compile_request(canvas, mapping_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            cluster = sorted(
                [
                    node
                    for node in document.nodes
                    if node.get("color") == "2" and node["x"] == 1000
                ],
                key=lambda node: node["y"],
            )
            self.assertEqual(
                [node["text"].split(":", 1)[0] for node in cluster],
                ["# R3 · W3 · Human audit reliability", "Asked", "Evidence", "Status", "Done when", "Change"],
            )
            self.assertTrue(all(node["width"] == 560 for node in cluster))
            self.assertEqual(cluster[1]["y"] - cluster[0]["y"] - cluster[0]["height"], 20)
            self.assertTrue(
                all(cluster[index + 1]["y"] - cluster[index]["y"] - cluster[index]["height"] == 10 for index in range(1, 5))
            )
            self.assertNotIn("CR-", cluster[0]["text"])
            self.assertEqual(document.node("target")["text"], "Original manuscript sentence.")
            issue_edges = [edge for edge in document.edges if edge["fromNode"] in {node["id"] for node in cluster}]
            self.assertEqual(len(issue_edges), 1)
            self.assertEqual((issue_edges[0]["fromNode"], issue_edges[0]["toNode"]), (cluster[0]["id"], "target"))
            self.assertEqual(compile_request(canvas, mapping_request)["operations"], [])

    def test_mapping_issue_requires_one_narrow_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas())
            bad = {
                "schema_version": 1,
                "workflow": "camera-ready-mapping",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "map_issue", "key": "wide", "label": "R1 · W1", "asked": "A",
                    "change": "B", "evidence": "C", "status": "ready", "done_when": "D",
                    "target_ids": ["b", "c"], "x": 100, "y": 600,
                }],
            }
            with self.assertRaisesRegex(PlanError, "exactly one"):
                compile_request(canvas, bad)

    def test_mapping_issue_rejects_invented_cr_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = self.write_canvas(Path(directory), fixture_canvas())
            bad = {
                "schema_version": 1,
                "workflow": "camera-ready-mapping",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "map_issue", "key": "bad", "label": "CR-10", "asked": "A",
                    "change": "B", "evidence": "C", "status": "ready", "done_when": "D",
                    "target_ids": ["main"], "x": 100, "y": 300,
                }],
            }
            with self.assertRaisesRegex(PlanError, "CR"):
                compile_request(canvas, bad)

    def test_rebuttal_row_uses_fixed_six_column_grid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0]["label"] = "Rebuttal"
            canvas = self.write_canvas(Path(directory), data)
            rebuttal_request = {
                "schema_version": 1,
                "workflow": "rebuttal",
                "target": {"group_label": "Rebuttal"},
                "actions": [{
                    "op": "layout_rebuttal",
                    "reviewer": "R1: ABC",
                    "kind": "weakness",
                    "key": "r1-w1",
                    "x": 100,
                    "y": 600,
                    "stages": ["English", "한국어", "메모", "한국어 답변", "English draft", "English final"],
                }],
            }
            patch = compile_request(canvas, rebuttal_request)
            apply_patch(canvas, patch)
            cards = sorted(
                [node for node in CanvasDocument.load(canvas).nodes if node.get("text") in rebuttal_request["actions"][0]["stages"]],
                key=lambda node: node["x"],
            )
            self.assertEqual([node["width"] for node in cards], [625, 625, 520, 660, 660, 660])
            self.assertEqual([cards[i + 1]["x"] - cards[i]["x"] - cards[i]["width"] for i in range(5)], [73, 55, 160, 20, 40])
            self.assertEqual(len({node["y"] for node in cards}), 1)
            self.assertEqual([node.get("color") for node in cards], ["1", "1", None, None, None, None])

    def test_research_flow_assigns_colors_and_bottom_top_edges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0]["label"] = "Research Flow"
            canvas = self.write_canvas(Path(directory), data)
            flow_request = {
                "schema_version": 1,
                "workflow": "research-flow",
                "target": {"group_label": "Research Flow"},
                "actions": [{
                    "op": "add_research_flow",
                    "nodes": [
                        {"key": "rq1", "kind": "rq", "text": "RQ1", "x": 100, "y": 600},
                        {"key": "e1", "kind": "experiment", "text": "RQ1-E", "x": 100, "y": 800},
                        {"key": "a1", "kind": "answer", "text": "RQ1-A", "x": 100, "y": 1000},
                    ],
                    "links": [["rq1", "e1"], ["e1", "a1"]],
                }],
            }
            patch = compile_request(canvas, flow_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            added = {node["text"].lstrip("# "): node for node in document.nodes if node.get("text", "").startswith("# RQ1")}
            self.assertEqual([added[key]["color"] for key in ("RQ1", "RQ1-E", "RQ1-A")], ["6", "4", "3"])
            edges = [edge for edge in document.edges if edge["fromNode"] in {node["id"] for node in added.values()}]
            self.assertTrue(all((edge["fromSide"], edge["toSide"]) == ("bottom", "top") for edge in edges))

    def test_research_flow_links_literature_to_exact_question(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0].update({"label": "Research Flow", "width": 3000})
            data["nodes"].append(
                {"id": "rq", "type": "text", "x": 1200, "y": 600, "width": 560, "height": 120, "text": "# RQ1", "color": "6"}
            )
            canvas = self.write_canvas(Path(directory), data)
            request = {
                "schema_version": 1,
                "workflow": "research-flow",
                "target": {"group_label": "Research Flow"},
                "actions": [{
                    "op": "link_literature",
                    "key": "smith2026-rq1",
                    "target_id": "rq",
                    "title": "A Relevant Paper",
                    "citekey": "smith2026",
                    "item_key": "ABCD1234",
                    "relevance": "Defines the comparison used by RQ1.",
                    "lane": "right",
                }],
            }
            patch = compile_request(canvas, request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            card = next(node for node in document.nodes if "zotero://select/library/items/ABCD1234" in node.get("text", ""))
            edge = next(edge for edge in document.edges if edge["fromNode"] == card["id"] and edge["toNode"] == "rq")
            self.assertEqual((edge["fromSide"], edge["toSide"]), ("left", "right"))
            self.assertNotIn("color", card)
            self.assertNotIn("Paper flow", card["text"])
            self.assertEqual(compile_request(canvas, request)["operations"], [])

    def test_camera_ready_clone_excludes_mapping_and_marks_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].extend([
                {"id": "mapping", "type": "text", "x": 100, "y": 600, "width": 760, "height": 180, "color": "2", "text": "# R1 · W1\nAsked: ..."},
                {"id": "target", "type": "text", "x": 1000, "y": 600, "width": 800, "height": 70, "text": "Old sentence."},
            ])
            canvas = self.write_canvas(Path(directory), data)
            ready_request = {
                "schema_version": 1,
                "workflow": "camera-ready",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "build_camera_ready",
                    "key": "final",
                    "label": "paper_camera_ready",
                    "source_node_ids": ["main", "target"],
                    "source_group_ids": [],
                    "source_edge_ids": [],
                    "x": 3200,
                    "y": 0,
                    "changes": [{"source_id": "target", "text": "New sentence."}],
                    "blockers": [{"key": "ethics", "topic": "Ethics facts", "label": "R2 · W4", "target_source_id": "target"}],
                }],
            }
            patch = compile_request(canvas, ready_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            final_group = next(node for node in document.nodes if node.get("label") == "paper_camera_ready")
            final_nodes = document.contained_non_groups(node_rect(final_group))
            self.assertFalse(any("Asked:" in node.get("text", "") for node in final_nodes))
            changed = next(node for node in final_nodes if node.get("text") == "New sentence.")
            self.assertEqual(changed.get("color"), "3")
            blocker = next(node for node in final_nodes if node.get("text", "").startswith("# Author input required"))
            self.assertEqual(blocker.get("color"), "3")
            self.assertEqual(compile_request(canvas, ready_request)["operations"], [])

    def test_pair_appendix_columns_reuses_old_group_and_stacks_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas(existing_group=True)
            data["nodes"][0].update({"width": 6000, "height": 5000})
            canvas = self.write_canvas(Path(directory), data)
            pair_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "pair_appendix_columns",
                    "sections": [{
                        "key": "results",
                        "label": "Results · Appendix B–C",
                        "group_id": "appendix-group",
                        "x": 3000,
                        "y": 200,
                        "blocks": [["b", "b1"], ["c", "c1"]],
                    }],
                }],
            }
            patch = compile_request(canvas, pair_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            self.assertEqual(document.node("appendix-group")["label"], "Results · Appendix B–C")
            self.assertEqual((document.node("b")["x"], document.node("b")["y"]), (3000, 200))
            self.assertEqual(document.node("c")["y"], document.node("b1")["y"] + document.node("b1")["height"] + 40)
            self.assertEqual(compile_request(canvas, pair_request)["operations"], [])

    def test_split_citation_replaces_command_and_connects_side_card(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].append(
                {"id": "cite-sentence", "type": "text", "x": 1000, "y": 600, "width": 800, "height": 70, "text": "Prior work \\cite{smith2024} supports this."}
            )
            canvas = self.write_canvas(Path(directory), data)
            citation_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{"op": "split_citation", "key": "smith", "sentence_id": "cite-sentence", "command": "\\cite{smith2024}", "lane": "right"}],
            }
            patch = compile_request(canvas, citation_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            self.assertEqual(document.node("cite-sentence")["text"], "Prior work {} supports this.")
            card = next(node for node in document.nodes if node.get("text") == "\\cite{smith2024}")
            self.assertNotIn("color", card)
            self.assertTrue(any(edge["fromNode"] == card["id"] and edge["toNode"] == "cite-sentence" for edge in document.edges))
            self.assertEqual(compile_request(canvas, citation_request)["operations"], [])

    def test_connect_equation_requires_display_math_and_centres_straight_edge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].extend([
                {"id": "eq", "type": "text", "x": 1000, "y": 600, "width": 800, "height": 100, "text": "$$\nx=1\n$$"},
                {"id": "eq-mention", "type": "text", "x": 1000, "y": 720, "width": 800, "height": 70, "text": "Equation 1 defines x."},
            ])
            canvas = self.write_canvas(Path(directory), data)
            equation_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{"op": "connect_reference", "key": "eq1", "kind": "equation", "source_id": "eq", "target_ids": ["eq-mention"], "from_side": "bottom", "to_side": "top"}],
            }
            patch = compile_request(canvas, equation_request)
            apply_patch(canvas, patch)
            edge = next(edge for edge in CanvasDocument.load(canvas).edges if edge["fromNode"] == "eq")
            self.assertEqual((edge["fromSide"], edge["toSide"]), ("bottom", "top"))
            self.assertEqual(compile_request(canvas, equation_request)["operations"], [])

    def test_connect_reference_infers_ports_from_dominant_axis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].extend([
                {"id": "source", "type": "text", "x": 100, "y": 700, "width": 500, "height": 70, "text": "See the Appendix."},
                {"id": "side", "type": "text", "x": 1800, "y": 900, "width": 800, "height": 70, "text": "# Appendix D"},
                {"id": "below", "type": "text", "x": 200, "y": 1800, "width": 800, "height": 70, "text": "# Appendix E"},
            ])
            canvas = self.write_canvas(Path(directory), data)
            reference_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [
                    {"op": "connect_reference", "key": "side", "kind": "appendix", "source_id": "source", "target_ids": ["side"]},
                    {"op": "connect_reference", "key": "below", "kind": "appendix", "source_id": "source", "target_ids": ["below"]},
                ],
            }
            patch = compile_request(canvas, reference_request)
            apply_patch(canvas, patch)
            edges = {edge["toNode"]: edge for edge in CanvasDocument.load(canvas).edges}
            self.assertEqual((edges["side"]["fromSide"], edges["side"]["toSide"]), ("right", "left"))
            self.assertEqual((edges["below"]["fromSide"], edges["below"]["toSide"]), ("bottom", "top"))
            self.assertEqual(compile_request(canvas, reference_request)["operations"], [])

    def test_fit_section_title_spans_explicit_section_rectangle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].extend([
                {"id": "title", "type": "text", "x": 1000, "y": 600, "width": 800, "height": 70, "text": "# Results"},
                {"id": "left-artifact", "type": "text", "x": 600, "y": 700, "width": 300, "height": 200, "text": "| A |\n|---|"},
                {"id": "right-appendix", "type": "text", "x": 1900, "y": 700, "width": 800, "height": 70, "text": "# Appendix B"},
            ])
            canvas = self.write_canvas(Path(directory), data)
            fit_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{"op": "fit_section_title", "title_id": "title", "member_ids": ["left-artifact", "right-appendix"]}],
            }
            patch = compile_request(canvas, fit_request)
            apply_patch(canvas, patch)
            title = CanvasDocument.load(canvas).node("title")
            self.assertEqual((title["x"], title["width"]), (600, 2100))

    def test_mapping_master_is_far_left_and_has_no_edges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0].update({"x": -2000, "width": 5000})
            canvas = self.write_canvas(Path(directory), data)
            master_request = {
                "schema_version": 1,
                "workflow": "camera-ready-mapping",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "mapping_master",
                    "key": "master",
                    "x": -1800,
                    "y": 100,
                    "width": 800,
                    "manuscript_node_ids": ["main", "b", "b1", "c", "c1"],
                    "items": [
                        {"reviewer": "R1", "label": "W2", "topic": "Metric definition", "status": "wording"},
                        {"reviewer": "R3", "label": "W3", "topic": "Human audit", "status": "ready"},
                    ],
                }],
            }
            patch = compile_request(canvas, master_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            card = next(node for node in document.nodes if node.get("text", "").startswith("# Camera-ready mapping checklist"))
            self.assertNotIn("CR-", card["text"])
            self.assertFalse(any(card["id"] in {edge["fromNode"], edge["toNode"]} for edge in document.edges))
            self.assertEqual(compile_request(canvas, master_request)["operations"], [])

    def test_camera_ready_clone_supports_yellow_additions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].append(
                {"id": "target", "type": "text", "x": 1000, "y": 600, "width": 800, "height": 70, "text": "Existing sentence."}
            )
            canvas = self.write_canvas(Path(directory), data)
            ready_request = {
                "schema_version": 1,
                "workflow": "camera-ready",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "build_camera_ready",
                    "key": "with-addition",
                    "label": "paper_camera_ready",
                    "source_node_ids": ["main", "target"],
                    "source_group_ids": [],
                    "source_edge_ids": [],
                    "x": 3200,
                    "y": 0,
                    "changes": [],
                    "additions": [{
                        "key": "new-definition",
                        "kind": "sentence",
                        "text": "New definition.",
                        "x": 1000,
                        "y": 700,
                        "width": 800,
                        "height": 70,
                    }],
                    "blockers": [],
                }],
            }
            patch = compile_request(canvas, ready_request)
            apply_patch(canvas, patch)
            final_group = next(node for node in CanvasDocument.load(canvas).nodes if node.get("label") == "paper_camera_ready")
            final_nodes = CanvasDocument.load(canvas).contained_non_groups(node_rect(final_group))
            added = next(node for node in final_nodes if node.get("text") == "New definition.")
            self.assertEqual(added.get("color"), "3")

    def test_camera_ready_rejects_mapping_nodes_and_global_appendix_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas(existing_group=True)
            data["nodes"][1]["label"] = "paper_v1 appendix"
            data["nodes"].append(
                {"id": "mapping", "type": "text", "x": 100, "y": 600, "width": 760, "height": 180, "color": "2", "text": "# R1 · W1\nAsked: A\nChange: B\nEvidence: C\nStatus: ready\nDone when: D"}
            )
            canvas = self.write_canvas(Path(directory), data)
            base_action = {
                "op": "build_camera_ready", "key": "bad", "label": "paper_camera_ready",
                "source_node_ids": ["mapping"], "source_group_ids": [], "source_edge_ids": [],
                "x": 3200, "y": 0, "changes": [], "blockers": [],
            }
            request_data = {"schema_version": 1, "workflow": "camera-ready", "target": {"group_label": "paper_v1"}, "actions": [base_action]}
            with self.assertRaisesRegex(PlanError, "mapping"):
                compile_request(canvas, request_data)
            request_data["actions"][0] = {**base_action, "source_node_ids": ["main"], "source_group_ids": ["appendix-group"]}
            with self.assertRaisesRegex(PlanError, "Appendix"):
                compile_request(canvas, request_data)

    def test_rebuttal_multiple_rows_use_tallest_height_plus_80(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0]["label"] = "Rebuttal"
            canvas = self.write_canvas(Path(directory), data)
            stages1 = ["short", "짧음", "memo " * 200, "답변", "draft", "final"]
            stages2 = ["second", "두번째", "memo", "답변", "draft", "final"]
            rebuttal_request = {
                "schema_version": 1,
                "workflow": "rebuttal",
                "target": {"group_label": "Rebuttal"},
                "actions": [{
                    "op": "layout_rebuttal",
                    "reviewer": "R1: ABC",
                    "x": 100,
                    "y": 600,
                    "rows": [
                        {"key": "w1", "kind": "strength", "stages": stages1},
                        {"key": "w2", "kind": "suggestion", "stages": stages2},
                    ],
                }],
            }
            patch = compile_request(canvas, rebuttal_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            first = [document.node(deterministic_id("paper", "rebuttal_stage", "w1", str(i))) for i in range(6)]
            second = [document.node(deterministic_id("paper", "rebuttal_stage", "w2", str(i))) for i in range(6)]
            self.assertEqual(second[0]["y"], first[0]["y"] + max(node["height"] for node in first) + 80)
            self.assertEqual([node.get("color") for node in first[:2]], ["4", "4"])
            self.assertEqual([node.get("color") for node in second[:2]], ["3", "3"])
            self.assertEqual(compile_request(canvas, rebuttal_request)["operations"], [])

    def test_inspect_accepts_empty_rebuttal_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].append({"id": "empty", "type": "text", "x": 100, "y": 600, "width": 660, "height": 70, "text": ""})
            canvas = self.write_canvas(Path(directory), data)
            inspected = inspect_canvas(canvas)
            self.assertEqual(next(node for node in inspected["nodes"] if node["id"] == "empty")["text"], "")

    def test_research_flow_compound_experiment_has_sections_without_internal_edges_and_real_figure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0]["label"] = "Research Flow"
            canvas = self.write_canvas(Path(directory), data)
            flow_request = {
                "schema_version": 1,
                "workflow": "research-flow",
                "target": {"group_label": "Research Flow"},
                "actions": [{
                    "op": "add_research_flow",
                    "nodes": [
                        {"key": "rq", "kind": "rq", "text": "RQ2", "x": 100, "y": 600},
                        {"key": "exp", "kind": "experiment", "text": "RQ2-E", "x": 100, "y": 800,
                         "sections": [{"key": "setup", "heading": "Setup", "text": "Method."}, {"key": "results", "heading": "Results", "text": "b=7, c=16, n=40."}]},
                        {"key": "fig", "kind": "figure", "text": "Result figure", "file": "result.png", "x": 1000, "y": 890, "width": 600, "height": 400},
                        {"key": "answer", "kind": "answer", "text": "RQ2-A", "x": 100, "y": 1400},
                    ],
                    "links": [["rq", "exp"], ["exp", "answer"]],
                }],
            }
            patch = compile_request(canvas, flow_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            setup_id = deterministic_id("paper", "research_flow", "exp", "setup")
            results_id = deterministic_id("paper", "research_flow", "exp", "results")
            self.assertTrue(document.node(setup_id)["text"].startswith("## Setup"))
            self.assertTrue(document.node(results_id)["text"].startswith("## Results"))
            self.assertFalse(any({edge["fromNode"], edge["toNode"]} == {setup_id, results_id} for edge in document.edges))
            figure = next(node for node in document.nodes if node.get("file") == "result.png")
            self.assertEqual(figure["type"], "file")
            outgoing = next(edge for edge in document.edges if edge["toNode"] == deterministic_id("paper", "research_flow", "answer"))
            self.assertEqual(outgoing["fromNode"], results_id)

    def test_move_nodes_uses_anchor_destination_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0].update({"width": 5000})
            canvas = self.write_canvas(Path(directory), data)
            move_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{"op": "move_nodes", "anchor_id": "b", "node_ids": ["b", "b1"], "x": 3000, "y": 100}],
            }
            patch = compile_request(canvas, move_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            self.assertEqual((document.node("b")["x"], document.node("b1")["x"]), (3000, 3000))
            self.assertEqual(compile_request(canvas, move_request)["operations"], [])

    def test_normalize_equations_converts_fenced_math_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].append(
                {"id": "fenced", "type": "text", "x": 1000, "y": 600, "width": 800, "height": 100, "text": "``` math\nx=1\n```"}
            )
            canvas = self.write_canvas(Path(directory), data)
            normalize_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{"op": "normalize_equations", "node_ids": ["fenced"]}],
            }
            patch = compile_request(canvas, normalize_request)
            apply_patch(canvas, patch)
            self.assertEqual(CanvasDocument.load(canvas).node("fenced")["text"], "$$\nx=1\n$$")
            self.assertEqual(compile_request(canvas, normalize_request)["operations"], [])

    def test_remove_items_requires_all_incident_edges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["edges"].append({"id": "edge", "fromNode": "b", "fromSide": "right", "toNode": "main", "toSide": "left"})
            canvas = self.write_canvas(Path(directory), data)
            remove_request = {
                "schema_version": 1,
                "workflow": "camera-ready-mapping",
                "target": {"group_label": "paper_v1"},
                "actions": [{"op": "remove_items", "node_ids": ["b"], "edge_ids": []}],
            }
            with self.assertRaisesRegex(PlanError, "incident"):
                compile_request(canvas, remove_request)
            remove_request["actions"][0]["edge_ids"] = ["edge"]
            patch = compile_request(canvas, remove_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            self.assertNotIn("b", document.node_map())
            self.assertNotIn("edge", document.edge_map())

    def test_shift_sibling_group_moves_every_contained_node_rigidly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].extend([
                {"id": "sibling", "type": "group", "x": 3200, "y": 0, "width": 1000, "height": 1000, "label": "paper_camera_ready"},
                {"id": "sibling-node", "type": "text", "x": 3300, "y": 100, "width": 800, "height": 70, "text": "Sibling sentence."},
            ])
            canvas = self.write_canvas(Path(directory), data)
            shift_request = {
                "schema_version": 1,
                "workflow": "paper",
                "target": {"group_label": "paper_v1"},
                "actions": [{"op": "shift_sibling_group", "group_id": "sibling", "x": 4500, "y": 0}],
            }
            patch = compile_request(canvas, shift_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            self.assertEqual((document.node("sibling")["x"], document.node("sibling-node")["x"]), (4500, 4600))
            self.assertEqual(compile_request(canvas, shift_request)["operations"], [])

    def test_camera_ready_reuses_existing_group_and_removes_stale_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"].extend([
                {"id": "final", "type": "group", "x": 3200, "y": 0, "width": 1000, "height": 1000, "label": "paper_camera_ready"},
                {"id": "stale", "type": "text", "x": 3300, "y": 100, "width": 800, "height": 70, "text": "Stale sentence."},
            ])
            data["edges"].append({"id": "stale-edge", "fromNode": "stale", "fromSide": "left", "toNode": "main", "toSide": "right"})
            canvas = self.write_canvas(Path(directory), data)
            ready_request = {
                "schema_version": 1,
                "workflow": "camera-ready",
                "target": {"group_label": "paper_v1"},
                "actions": [{
                    "op": "build_camera_ready", "key": "replace", "group_id": "final", "label": "paper_camera_ready",
                    "source_node_ids": ["main"], "source_group_ids": [], "source_edge_ids": [],
                    "x": 3200, "y": 0, "changes": [], "additions": [], "blockers": [],
                }],
            }
            patch = compile_request(canvas, ready_request)
            apply_patch(canvas, patch)
            document = CanvasDocument.load(canvas)
            self.assertEqual(len([node for node in document.nodes if node.get("label") == "paper_camera_ready"]), 1)
            self.assertNotIn("stale", document.node_map())
            self.assertNotIn("stale-edge", document.edge_map())
            self.assertEqual(compile_request(canvas, ready_request)["operations"], [])

    def research_flow_request(self, nodes: list[dict], links: list[list[str]]) -> dict:
        return {
            "schema_version": 1,
            "workflow": "research-flow",
            "target": {"group_label": "Research Flow"},
            "actions": [{"op": "add_research_flow", "nodes": nodes, "links": links}],
        }

    def test_side_cards_are_uncoloured_and_point_into_the_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0]["label"] = "Research Flow"
            canvas = self.write_canvas(Path(directory), data)
            nodes = [
                {"key": "impl", "kind": "implementation", "text": "### Impl\n\n| a | b |", "x": 100, "y": 600},
                {"key": "log", "kind": "log", "text": "### Log — discarded", "x": 100, "y": 900},
                {"key": "exp", "kind": "experiment", "text": "RQ1-E", "x": 1000, "y": 600},
            ]
            links = [["impl", "exp"], ["log", "exp"]]
            apply_patch(canvas, compile_request(canvas, self.research_flow_request(nodes, links)))
            document = CanvasDocument.load(canvas)
            for key, prefix in (("impl", "### Impl"), ("log", "### Log")):
                node = document.node(deterministic_id("paper", "research_flow", key))
                self.assertNotIn("color", node, f"{key} card stays uncoloured")
                self.assertTrue(node["text"].startswith(prefix), f"{key} text is kept verbatim")
                edge = next(edge for edge in document.edges if edge["fromNode"] == node["id"])
                self.assertEqual((edge["fromSide"], edge["toSide"]), ("right", "left"))

    def test_side_card_may_not_receive_a_link_from_the_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0]["label"] = "Research Flow"
            canvas = self.write_canvas(Path(directory), data)
            nodes = [
                {"key": "tbl", "kind": "table", "text": "### Table", "x": 1000, "y": 600},
                {"key": "exp", "kind": "experiment", "text": "RQ1-E", "x": 100, "y": 600},
            ]
            with self.assertRaises(PlanError):
                compile_request(canvas, self.research_flow_request(nodes, [["exp", "tbl"]]))

    def test_experiment_section_heading_rejects_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = fixture_canvas()
            data["nodes"][0]["label"] = "Research Flow"
            canvas = self.write_canvas(Path(directory), data)
            nodes = [{
                "key": "exp", "kind": "experiment", "text": "RQ1-E", "x": 100, "y": 600,
                "sections": [{"key": "r", "heading": "Results (depth 3)", "text": "b=7."}],
            }]
            with self.assertRaises(PlanError):
                compile_request(canvas, self.research_flow_request(nodes, []))

    def test_overleaf_repl_output_is_read_by_marker(self) -> None:
        from overleaf import parse_repl_output

        payload, cwd = parse_repl_output(
            "✔︎ Opened a new tab and set it active: tabs[0]\n"
            '__OVERLEAF_JSON__{"id": "abc", "name": "[ARR 10] Title"}\n'
            "__OVERLEAF_PWD__/Users/x/.aside/u/0/sessions/2026-08-31_ab\n"
            "[ok | 412ms]"
        )
        self.assertEqual(payload["id"], "abc")
        self.assertEqual(cwd, "/Users/x/.aside/u/0/sessions/2026-08-31_ab")

        empty, _ = parse_repl_output("✔︎ trace only\n[ok | 5ms]")
        self.assertEqual(empty, {}, "a run that emitted nothing must not look successful")

    def test_estimate_text_height_counts_cjk_and_tables(self) -> None:
        korean = "가나다라마바사아자차카타파하" * 3
        latin = "abcdefghijklmn" * 3
        self.assertGreater(
            estimate_text_height(korean, 560, "paragraph"),
            estimate_text_height(latin, 560, "paragraph"),
            "CJK glyphs are double width and must wrap sooner",
        )

        one_row = "| a | b |\n|---|---|\n| 1 | 2 |"
        two_rows = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        self.assertEqual(
            estimate_text_height(two_rows, 560, "paragraph") - estimate_text_height(one_row, 560, "paragraph"),
            40,
            "one more table row adds a row's height, rounded to the 10px grid",
        )

        without_rule = "| a | b |\n| 1 | 2 |"
        self.assertEqual(
            estimate_text_height(one_row, 560, "paragraph"),
            estimate_text_height(without_rule, 560, "paragraph"),
            "the |---| rule renders as a border and adds no height",
        )

        self.assertGreater(
            estimate_text_height("| 항목 | 값 |", 560, "paragraph"),
            estimate_text_height("항목 값", 560, "paragraph"),
            "table rows are padded taller than prose lines",
        )


if __name__ == "__main__":
    unittest.main()
