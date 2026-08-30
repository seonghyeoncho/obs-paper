from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "plugins/paper-canvas-workflow/scripts"
sys.path.insert(0, str(SCRIPTS))

from obs_project import ProjectError, import_project, init_project, resolve_project  # noqa: E402
from obs_paper_engine import CanvasDocument  # noqa: E402
from zotero_bridge import (  # noqa: E402
    ZoteroClient,
    ZoteroError,
    add_paper,
    audit_citations,
    export_bibliography,
    link_canvas,
    record_search,
    save_pdf,
    setup_project,
)


class FakeZotero(ZoteroClient):
    def _bbt_rpc(self, method: str, params: list[object]) -> object:
        self.assert_call = (method, params)
        return {"ABCD1234": "smithSkill2026"}


class FakeProjectZotero(FakeZotero):
    def __init__(self, bibliography: str = "") -> None:
        super().__init__()
        self.bibliography = bibliography

    def ensure_collection(self, name: str) -> str:
        self.collection_name = name
        return "COLLECTION1"

    def collection_bibtex(self, collection_key: str) -> str:
        self.exported_collection = collection_key
        return self.bibliography

    def create_item(self, metadata: dict[str, object], api_key: str | None = None) -> str:
        self.created_metadata = metadata
        return "ABCD1234"


class ProjectZoteroTest(unittest.TestCase):
    def test_project_init_resolve_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            repository = root / "repo"
            repository.mkdir()
            initialized = init_project(vault, "Demo", repository)
            self.assertTrue(Path(initialized["canvas"]).is_file())
            self.assertTrue((Path(initialized["root"]) / "papers").is_dir())
            self.assertTrue((Path(initialized["root"]) / "references.bib").is_file())
            self.assertTrue((Path(initialized["root"]) / "searches.jsonl").is_file())
            self.assertEqual(resolve_project(vault, repository=repository)["project"], "Demo")

            source = root / "source"
            source.mkdir()
            figure = source / "figure.png"
            figure.write_bytes(b"png")
            source_canvas = source / "Research.canvas"
            source_canvas.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "f", "type": "file", "x": 0, "y": 0, "width": 100, "height": 100, "file": "figure.png"}
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )
            imported = import_project(vault, "Imported", source_canvas, repository)
            data = json.loads(Path(imported["canvas"]).read_text(encoding="utf-8"))
            self.assertEqual(data["nodes"][0]["file"], "Projects/Imported/assets/figure.png")
            self.assertEqual((vault / data["nodes"][0]["file"]).read_bytes(), b"png")

    def test_zotero_citation_and_canvas_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canvas = root / "paper.canvas"
            canvas.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "paper", "type": "group", "x": 0, "y": 0, "width": 1800, "height": 800, "label": "paper_v1"},
                            {"id": "sentence", "type": "text", "x": 400, "y": 100, "width": 800, "height": 80, "text": "Prior work \\cite{smithSkill2026}."},
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )
            client = FakeZotero()
            citation = client.citation("ABCD1234")
            self.assertEqual(citation["command"], "\\cite{smithSkill2026}")
            link_canvas(
                canvas,
                target={"group_label": "paper_v1"},
                sentence_id="sentence",
                item_key="ABCD1234",
                lane="right",
                log=None,
                client=client,
            )
            document = CanvasDocument.load(canvas)
            self.assertIn("{}", document.node("sentence")["text"])
            card = next(node for node in document.nodes if "Open in Zotero" in node.get("text", ""))
            self.assertIn("zotero://select/library/items/ABCD1234", card["text"])
            self.assertEqual(len(document.edges), 1)

    def test_import_preflights_missing_assets_before_creating_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            source = root / "source.canvas"
            source.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "f", "type": "file", "x": 0, "y": 0, "width": 10, "height": 10, "file": "missing.png"}
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProjectError, "missing Canvas file reference"):
                import_project(vault, "Broken", source)
            self.assertFalse((vault / "Projects" / "Broken").exists())

    def test_save_pdf_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Demo"
            (project / "papers").mkdir(parents=True)
            (project / "project.md").write_text("---\n---\n", encoding="utf-8")
            source = root / "paper.pdf"
            source.write_bytes(b"pdf")
            first = save_pdf(project, source)
            second = save_pdf(project, source)
            self.assertEqual(first, second)
            self.assertEqual(first.read_bytes(), b"pdf")

    def test_project_collection_export_search_log_and_citation_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            project = Path(init_project(vault, "Demo")["root"])
            client = FakeProjectZotero("@article{knownKey,\n  title={Known}\n}\n")

            setup = setup_project(project, client)
            self.assertEqual(setup["collection_key"], "COLLECTION1")
            self.assertIn('zotero_collection: "COLLECTION1"', (project / "project.md").read_text(encoding="utf-8"))
            self.assertEqual((project / "references.bib").read_text(encoding="utf-8"), client.bibliography)

            search = root / "search.json"
            search.write_text(json.dumps({"provider": "Semantic Scholar", "query": "skill following", "selected": ["knownKey"]}), encoding="utf-8")
            record_search(project, search)
            logged = json.loads((project / "searches.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(logged["selected"], ["knownKey"])

            manuscript = root / "paper.tex"
            manuscript.write_text("Prior work \\cite{knownKey,missingKey}.", encoding="utf-8")
            audit = audit_citations(project, [manuscript])
            self.assertEqual(audit["missing"], ["missingKey"])

    def test_export_refuses_to_break_existing_citations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Demo"
            project.mkdir()
            (project / "project.md").write_text(
                '---\nrepository: ""\nbibliography: "references.bib"\nzotero_collection: "COLLECTION1"\n---\n',
                encoding="utf-8",
            )
            (project / "paper.tex").write_text("\\cite{keepMe}", encoding="utf-8")
            bibliography = project / "references.bib"
            bibliography.write_text("@article{keepMe, title={Keep}}\n", encoding="utf-8")
            client = FakeProjectZotero("@article{otherKey, title={Other}}\n")
            with self.assertRaisesRegex(ZoteroError, "keepMe"):
                export_bibliography(project, client)
            self.assertIn("keepMe", bibliography.read_text(encoding="utf-8"))

    def test_migration_can_defer_bibliography_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            project = Path(init_project(vault, "Demo")["root"])
            metadata = root / "paper.json"
            metadata.write_text(json.dumps({"title": "Paper"}), encoding="utf-8")
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"pdf")
            client = FakeProjectZotero("@article{notYet, title={Deferred}}\n")
            setup_project(project, client, export=False)
            add_paper(project, metadata, pdf, client, export=False)
            self.assertEqual(client.created_metadata["collections"], ["COLLECTION1"])
            self.assertFalse(hasattr(client, "exported_collection"))
            self.assertEqual((project / "references.bib").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
