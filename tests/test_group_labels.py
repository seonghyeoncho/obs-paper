from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "plugins/obspaper/scripts"
sys.path.insert(0, str(SCRIPTS))

from obs_paper_engine import (  # noqa: E402
    CanvasDocument,
    PlanError,
    apply_patch,
    classify_groups,
    compile_document,
    group_role,
    inspect_canvas,
    plan_group_label_migration,
    plan_group_label_migration_file,
)
from obs_project import (  # noqa: E402
    init_project,
    read_groups,
    record_project_groups,
    resolve_project,
    write_groups,
)


def group(node_id: str, label: str, x: int, y: int, width: int, height: int) -> dict:
    return {"id": node_id, "type": "group", "x": x, "y": y, "width": width, "height": height, "label": label}


def card(node_id: str, x: int, y: int) -> dict:
    return {"id": node_id, "type": "text", "x": x, "y": y, "width": 200, "height": 60, "text": node_id}


def versioned_canvas() -> dict:
    """Three manuscript versions, each with its own `Appendix A`, and a research flow."""
    nodes = [group("flow", "Reasoning Parameter Activation Research Flow", -3000, 0, 2000, 2000)]
    for index, version in enumerate(("paper_v1", "paper_v2", "paper_v3", "paper_camera_ready")):
        x = index * 3000
        nodes.append(group(version, version, x, 0, 2500, 2000))
        nodes.append(group(f"{version}-appendix", "Skill Following · Appendix A", x + 1000, 100, 600, 400))
        nodes.append(group(f"{version}-results", "Results · Appendix B–H", x + 1000, 800, 600, 400))
    nodes.append(group("rebuttal", "Rebuttal", 0, 3000, 1000, 500))
    nodes.append(group("stray", "무제 그룹", 0, 4000, 500, 500))
    for version in ("paper_v1", "paper_v2", "paper_v3", "paper_camera_ready"):
        nodes.append(card(f"{version}-a1", next(n for n in nodes if n["id"] == f"{version}-appendix")["x"] + 20, 120))
    nodes.append(card("q1", -2900, 100))
    return {"nodes": nodes, "edges": []}


def flow_request(target: dict) -> dict:
    return {
        "schema_version": 1,
        "workflow": "research-flow",
        "target": target,
        "actions": [{"op": "add_research_flow", "nodes": [{"key": "q", "kind": "rq", "text": "RQ9", "x": 0, "y": 0}], "links": []}],
    }


class ResearchFlowLabelTest(unittest.TestCase):
    def test_variants_name_the_research_flow(self) -> None:
        for label in (
            "research_flow",
            "research flow",
            "Research Flow",
            "Research Flow — 10k와 50k 학습",
            "Reasoning Parameter Activation Research Flow",
        ):
            self.assertEqual(group_role(label), "research_flow", label)
        for label in ("Phase 0 — 10k 스윕", "Research Flow Appendix", "Appendix (Phase 0)", "paper_v1"):
            self.assertNotEqual(group_role(label), "research_flow", label)
        self.assertEqual(group_role("Phase 1 — 50k 장기 학습 (RQ19–)"), "phase_1")

    def test_one_variant_resolves_from_the_canonical_label(self) -> None:
        document = CanvasDocument({"nodes": [group("flow", "Research Flow — Superposition", 0, 0, 1000, 1000)], "edges": []})
        for label in ("research_flow", "Research Flow", "research flow"):
            self.assertEqual(document.resolve_group({"group_label": label})["id"], "flow")
        patch = compile_document(document.data, flow_request({"group_label": "research_flow"}), document_id="doc")
        self.assertTrue(patch["operations"])

    def test_ambiguous_variants_are_refused(self) -> None:
        document = CanvasDocument(
            {
                "nodes": [
                    group("a", "research flow", 0, 0, 1000, 1000),
                    group("b", "OGen Research Flow", 2000, 0, 1000, 1000),
                ],
                "edges": [],
            }
        )
        with self.assertRaises(PlanError):
            document.resolve_group({"group_label": "research_flow"})

    def test_exact_label_wins_over_variants(self) -> None:
        document = CanvasDocument(
            {
                "nodes": [
                    group("old", "Old Research Flow", 0, 0, 1000, 1000),
                    group("new", "research_flow", 2000, 0, 1000, 1000),
                ],
                "edges": [],
            }
        )
        self.assertEqual(document.resolve_group({"group_label": "research_flow"})["id"], "new")
        self.assertEqual(document.resolve_group({"group_label": "Old Research Flow"})["id"], "old")

    def test_other_labels_stay_exact(self) -> None:
        document = CanvasDocument({"nodes": [group("p", "paper_v1", 0, 0, 100, 100)], "edges": []})
        with self.assertRaises(PlanError):
            document.resolve_group({"group_label": "Paper V1"})


class WithinScopeTest(unittest.TestCase):
    def test_duplicate_appendix_labels_resolve_inside_their_version(self) -> None:
        document = CanvasDocument(versioned_canvas())
        with self.assertRaises(PlanError):
            document.resolve_group({"group_label": "Skill Following · Appendix A"})
        for version in ("paper_v1", "paper_v2", "paper_v3", "paper_camera_ready"):
            resolved = document.resolve_group({"group_label": "Skill Following · Appendix A", "within": version})
            self.assertEqual(resolved["id"], f"{version}-appendix")

    def test_within_checks_group_id_and_unknown_parent(self) -> None:
        document = CanvasDocument(versioned_canvas())
        self.assertEqual(document.resolve_group({"group_id": "paper_v2-appendix", "within": "paper_v2"})["id"], "paper_v2-appendix")
        with self.assertRaisesRegex(PlanError, "not inside"):
            document.resolve_group({"group_id": "paper_v1-appendix", "within": "paper_v2"})
        with self.assertRaisesRegex(PlanError, "within"):
            document.resolve_group({"group_label": "Skill Following · Appendix A", "within": "paper_v9"})
        with self.assertRaises(PlanError):
            document.resolve_group({"group_label": "paper_v2", "within": "paper_v2"})

    def test_inspect_accepts_within(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = Path(directory) / "p.canvas"
            canvas.write_text(json.dumps(versioned_canvas()), encoding="utf-8")
            result = inspect_canvas(canvas, {"group_label": "Skill Following · Appendix A", "within": "paper_v3"})
            self.assertEqual({node["id"] for node in result["nodes"]}, {"paper_v3-appendix", "paper_v3-a1"})


class ClassifyTest(unittest.TestCase):
    def test_versions_past_v2_are_roles(self) -> None:
        self.assertEqual(group_role("paper_v3"), "paper_v3")
        self.assertEqual(group_role("paper_v12"), "paper_v12")
        self.assertIsNone(group_role("paper_v0"))
        classified = classify_groups(versioned_canvas())
        self.assertEqual(
            list(classified["groups"].items()),
            [
                ("research_flow", "flow"),
                ("paper_v1", "paper_v1"),
                ("paper_v2", "paper_v2"),
                ("paper_v3", "paper_v3"),
                ("rebuttal", "rebuttal"),
                ("camera_ready", "paper_camera_ready"),
            ],
        )
        self.assertEqual([item["id"] for item in classified["unclassified"]], ["stray"])

    def test_phases_count_inside_the_container_only(self) -> None:
        inside = {
            "nodes": [
                group("flow", "Research Flow — Superposition", 0, -200, 9000, 46400),
                group("p0", "Phase 0 — 10k 스윕 (RQ0–RQ18)", 100, -100, 8800, 35500),
                group("a0", "Appendix (Phase 0)", 5000, 4584, 1000, 30000),
                group("p1", "Phase 1 — 50k 장기 학습 (RQ19–)", 100, 35480, 8800, 10520),
            ],
            "edges": [],
        }
        classified = classify_groups(inside)
        self.assertEqual(classified["groups"], {"research_flow": "flow", "phase_0": "p0", "phase_1": "p1"})
        self.assertEqual(classified["unclassified"], [])
        loose = {"nodes": [inside["nodes"][1], inside["nodes"][3]], "edges": []}
        self.assertEqual(classify_groups(loose)["groups"], {})
        self.assertEqual(len(classify_groups(loose)["unclassified"]), 2)


class ProjectGroupsTest(unittest.TestCase):
    def test_groups_block_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            project = init_project(vault, "OGen")
            metadata = Path(project["root"]) / "project.md"
            self.assertIsNone(read_groups(metadata))
            groups = {"research_flow": "abc", "paper_v3": "d\"ef"}
            self.assertTrue(write_groups(metadata, groups))
            self.assertEqual(read_groups(metadata), groups)
            self.assertFalse(write_groups(metadata, groups))
            self.assertTrue(write_groups(metadata, {"paper_v1": "x"}))
            self.assertEqual(read_groups(metadata), {"paper_v1": "x"})
            self.assertTrue(write_groups(metadata, {}))
            self.assertEqual(read_groups(metadata), {})
            text = metadata.read_text(encoding="utf-8")
            self.assertIn('paper_dir: "docs/paper"', text)
            self.assertEqual(text.count("groups:"), 1)

    def test_record_project_groups_from_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            project = init_project(vault, "OGen")
            Path(project["canvas"]).write_text(json.dumps(versioned_canvas()), encoding="utf-8")
            dry = record_project_groups(vault, "OGen", write=False)
            self.assertEqual(dry["status"], "dry-run")
            self.assertNotIn("groups", resolve_project(vault, name="OGen"))
            result = record_project_groups(vault, "OGen")
            self.assertEqual(result["status"], "recorded")
            self.assertEqual([item["label"] for item in result["unclassified"]], ["무제 그룹"])
            self.assertEqual(resolve_project(vault, name="OGen")["groups"]["paper_v3"], "paper_v3")
            self.assertEqual(record_project_groups(vault, "OGen")["status"], "unchanged")

    def test_record_reports_a_canvas_without_groups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            project = init_project(vault, "Honorific")
            Path(project["canvas"]).write_text(json.dumps({"nodes": [card("c", 0, 0)], "edges": []}), encoding="utf-8")
            result = record_project_groups(vault, "Honorific")
            self.assertEqual(result["groups"], {})
            self.assertTrue(result["notes"])


class MigrationTest(unittest.TestCase):
    def run_migration(self, data: dict, **options: object) -> tuple[dict, dict, Path]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        canvas = Path(directory.name) / "p.canvas"
        canvas.write_text(json.dumps(data), encoding="utf-8")
        log = Path(directory.name) / "CANVAS_ACTION_LOG.md"
        patch = plan_group_label_migration_file(canvas, **options)
        before = json.loads(canvas.read_text(encoding="utf-8"))
        result = apply_patch(canvas, patch, log)
        replan = plan_group_label_migration_file(canvas, **options)
        self.assertEqual(replan["operations"], [])
        if patch["operations"]:
            self.assertTrue(Path(result["backup"]).is_file())
            self.assertIn("migrate-labels", log.read_text(encoding="utf-8"))
        self.assertEqual({node["id"] for node in before["nodes"]} - {node["id"] for node in json.loads(canvas.read_text())["nodes"]}, set())
        return patch, json.loads(canvas.read_text(encoding="utf-8")), canvas

    def test_dry_run_does_not_touch_the_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = Path(directory) / "p.canvas"
            canvas.write_text(json.dumps(versioned_canvas()), encoding="utf-8")
            original = canvas.read_bytes()
            patch = plan_group_label_migration_file(canvas, prefix_appendix=True)
            self.assertTrue(patch["operations"])
            self.assertEqual(canvas.read_bytes(), original)

    def test_research_flow_is_renamed_and_ids_kept(self) -> None:
        patch, data, _ = self.run_migration(versioned_canvas())
        self.assertEqual(patch["report"]["renamed"], [{"id": "flow", "from": "Reasoning Parameter Activation Research Flow", "to": "research_flow"}])
        flow = next(node for node in data["nodes"] if node["id"] == "flow")
        self.assertEqual(flow["label"], "research_flow")
        labels = [node.get("label") for node in data["nodes"]]
        self.assertEqual(labels.count("Skill Following · Appendix A"), 4)

    def test_appendix_labels_gain_their_version(self) -> None:
        _, data, _ = self.run_migration(versioned_canvas(), prefix_appendix=True)
        document = CanvasDocument(data)
        self.assertEqual(document.node("paper_v2-appendix")["label"], "paper_v2 · Skill Following · Appendix A")
        self.assertEqual(document.node("paper_camera_ready-results")["label"], "paper_camera_ready · Results · Appendix B–H")
        self.assertEqual(document.resolve_group({"group_label": "paper_v3 · Skill Following · Appendix A"})["id"], "paper_v3-appendix")

    def test_ambiguous_flows_are_reported_not_renamed(self) -> None:
        data = {"nodes": [group("a", "research flow", 0, 0, 100, 100), group("b", "Research Flow", 500, 0, 100, 100)], "edges": []}
        patch = plan_group_label_migration(data, document_id="doc")
        self.assertEqual(patch["operations"], [])
        self.assertTrue(patch["report"]["notes"])

    def test_canvas_without_groups_is_reported_or_wrapped(self) -> None:
        cards = {"nodes": [card("c1", 0, 0), card("c2", 400, 300)], "edges": []}
        report = plan_group_label_migration(cards, document_id="doc")
        self.assertEqual(report["operations"], [])
        self.assertIn("no groups", report["report"]["notes"][0])

        patch, data, _ = self.run_migration(cards, create_research_flow="around")
        flow = next(node for node in data["nodes"] if node["type"] == "group")
        self.assertEqual((flow["label"], flow["x"], flow["y"], flow["width"], flow["height"]), ("research_flow", -40, -40, 680, 440))
        self.assertEqual(data["nodes"][0], flow)
        compile_document(data, flow_request({"group_label": "research_flow"}), document_id="doc")

    def test_beside_leaves_manuscript_groups_alone(self) -> None:
        data = {"nodes": [group("p", "paper_v1", 0, 0, 1000, 1000), card("c", 10, 10)], "edges": []}
        with self.assertRaisesRegex(PlanError, "swallow"):
            plan_group_label_migration(data, document_id="doc", create_research_flow="around")
        _, after, _ = self.run_migration(data, create_research_flow="beside")
        flow = next(node for node in after["nodes"] if node.get("label") == "research_flow")
        self.assertEqual((flow["x"], flow["y"]), (1400, 0))


if __name__ == "__main__":
    unittest.main()
