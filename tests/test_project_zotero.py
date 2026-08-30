from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).parents[1] / "plugins/obspaper/scripts"
sys.path.insert(0, str(SCRIPTS))

from obs_project import ProjectError, build_paper_flow, import_project, init_project, resolve_project  # noqa: E402
from pdf_to_flow import _join_lines, _sentences, Line  # noqa: E402
from obs_paper_engine import CanvasDocument  # noqa: E402
from zotero_bridge import (  # noqa: E402
    ZoteroClient,
    ZoteroError,
    add_paper,
    audit_citations,
    export_bibliography,
    link_canvas,
    record_search,
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

    def import_pdf(self, item_key: str, source: Path, api_key: str | None = None) -> Path:
        self.imported_pdf = (item_key, source)
        return source


class FakeUploadZotero(ZoteroClient):
    def __init__(self, stored: Path) -> None:
        super().__init__()
        self.stored = stored
        self.registered = False
        self.calls: list[tuple[str, str, object]] = []

    def authorize(self, app_name: str = "Obs Paper") -> str:
        return "LOCALKEY"

    def status(self) -> dict[str, object]:
        return {"server_id": "SERVER"}

    def attachment_path(self, item_key: str) -> Path:
        if self.registered:
            return self.stored
        raise ZoteroError("no PDF")

    def _request(self, path: str, *, method: str = "GET", body: object = None, **kwargs: object) -> tuple[object, dict[str, str]]:
        self.calls.append((path, method, body))
        if path == "users/0/items":
            self.attachment_item = body
            return {"successful": {"0": {"key": "ATTACH01"}}}, {}
        if body and b"upload=UPLOAD1" in body:
            self.registered = True
            return "", {}
        return {"url": "http://upload.test/file", "contentType": "application/pdf", "prefix": "", "suffix": "", "uploadKey": "UPLOAD1"}, {}


class ProjectZoteroTest(unittest.TestCase):
    def test_zotero_client_uses_numeric_loopback(self) -> None:
        self.assertEqual(ZoteroClient().base_url, "http://127.0.0.1:23119/api")

    def test_import_pdf_creates_stored_attachment_and_registers_upload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "paper.pdf"
            pdf.write_bytes(b"pdf bytes")
            client = FakeUploadZotero(pdf)
            response = MagicMock(status=201)
            response.__enter__.return_value = response
            with patch("zotero_bridge.urlopen", return_value=response) as upload:
                self.assertEqual(client.import_pdf("PARENT01", pdf), pdf)
            attachment = client.attachment_item[0]
            self.assertEqual((attachment["parentItem"], attachment["linkMode"]), ("PARENT01", "imported_file"))
            self.assertTrue(client.registered)
            self.assertEqual(upload.call_args.args[0].data, b"pdf bytes")

    def test_project_init_resolve_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            repository = root / "repo"
            repository.mkdir()
            initialized = init_project(vault, "Demo", repository)
            self.assertTrue(Path(initialized["canvas"]).is_file())
            self.assertFalse((Path(initialized["root"]) / "papers").exists())
            self.assertTrue((vault / "Paper").is_dir())
            self.assertTrue((Path(initialized["root"]) / "references.bib").is_file())
            self.assertTrue((Path(initialized["root"]) / "searches.jsonl").is_file())
            self.assertIn('paper_flows: "Paper"', (Path(initialized["root"]) / "project.md").read_text(encoding="utf-8"))
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

    def test_build_paper_flow_creates_linked_idempotent_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            project = Path(init_project(vault, "Demo")["root"])
            spec = root / "flow.json"
            spec.write_text(
                json.dumps(
                    {
                        "title": "Paper: One/Two",
                        "citekey": "smith2026",
                        "item_key": "ABCD1234",
                        "sections": [
                            {"key": "intro", "title": "Introduction", "blocks": [
                                {"key": "s1", "kind": "sentence", "paragraph": "p1", "text": "First sentence."},
                                {"key": "s2", "kind": "sentence", "paragraph": "p1", "text": "Second sentence."},
                                {"key": "s3", "kind": "sentence", "paragraph": "p2", "text": "New paragraph."}
                            ]},
                            {"key": "method", "title": "Method", "blocks": [
                                {"key": "sub", "kind": "heading", "level": 1, "text": "Setup"},
                                {"key": "eq", "kind": "equation", "text": "$$x=1$$"}
                            ]}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            first = build_paper_flow(project, spec)
            second = build_paper_flow(project, spec)
            self.assertEqual((first["status"], second["status"]), ("created", "exists"))
            canvas = Path(first["canvas"])
            self.assertEqual(canvas.parent, (vault / "Paper").resolve())
            document = CanvasDocument.load(canvas)
            self.assertFalse(any(".pdf" in node.get("text", "") for node in document.nodes))
            sentences = [document.node(next(node["id"] for node in document.nodes if node.get("text") == text)) for text in ("First sentence.", "Second sentence.", "New paragraph.")]
            self.assertEqual(sentences[1]["y"] - sentences[0]["y"] - sentences[0]["height"], 20)
            self.assertEqual(sentences[2]["y"] - sentences[1]["y"] - sentences[1]["height"], 40)
            setup = next(node for node in document.nodes if node.get("text") == "# Setup")
            equation = next(node for node in document.nodes if node.get("text") == "$$x=1$$")
            self.assertEqual(equation["x"], setup["x"])
            self.assertTrue(all(edge["fromNode"] in document.node_map() and edge["toNode"] in document.node_map() for edge in document.edges))

    def test_pdf_text_cleanup_preserves_sentences(self) -> None:
        lines = [
            Line("A multi-agent architec-", 1, 0, 10, 0, 10, 9, 0),
            Line("ture works e.g. under failure.", 1, 0, 20, 0, 10, 9, 0),
            Line("It recovers.", 1, 0, 30, 8, 10, 9, 0),
        ]
        text = _join_lines(lines)
        self.assertEqual(text, "A multi-agent architecture works e.g. under failure. It recovers.")
        self.assertEqual(_sentences(text), ["A multi-agent architecture works e.g. under failure.", "It recovers."])

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
            self.assertEqual(client.imported_pdf, ("ABCD1234", pdf))
            self.assertFalse((project / "papers").exists())
            self.assertFalse(hasattr(client, "exported_collection"))
            self.assertEqual((project / "references.bib").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
