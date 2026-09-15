from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).parents[1] / "plugins/obspaper/scripts"
sys.path.insert(0, str(SCRIPTS))

from obs_project import (  # noqa: E402
    ProjectError,
    build_paper_flow,
    configure_vault,
    import_project,
    init_project,
    resolve_project,
    resolve_vault,
    standardize_project,
)
from pdf_to_flow import Line, _heading, _join_lines, build_from_pdf, build_words, page_lines, parse_pdf  # noqa: E402
from obs_paper_engine import CanvasDocument, apply_patch, compile_request, node_rect, rects_overlap  # noqa: E402

try:
    import pdfplumber  # noqa: F401
except ImportError:  # the PDF tests need it; everything else does not
    pdfplumber = None
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

    def test_project_standardize_adopts_legacy_canvas_and_localizes_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            project = vault / "Projects" / "Legacy"
            project.mkdir(parents=True)
            figure = vault / "figure.png"
            figure.write_bytes(b"png")
            assets = project / "assets"
            assets.mkdir()
            local_figure = assets / "local.png"
            local_figure.write_bytes(b"local png")
            canvas = project / "Old Name.canvas"
            canvas.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "f", "type": "file", "file": "figure.png"},
                            {"id": "local", "type": "file", "file": "assets/local.png"},
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            result = standardize_project(vault, "Legacy")
            self.assertEqual(result["status"], "standardized")
            self.assertEqual(resolve_project(vault, name="Legacy")["canvas"], str(canvas.resolve()))
            data = json.loads(canvas.read_text(encoding="utf-8"))
            self.assertEqual(data["nodes"][0]["file"], "Projects/Legacy/assets/figure.png")
            self.assertEqual(data["nodes"][1]["file"], "Projects/Legacy/assets/local.png")
            self.assertEqual((project / "assets" / "figure.png").read_bytes(), b"png")
            self.assertEqual(len(list((project / ".canvas-history").glob("*.canvas"))), 1)

    def test_resolve_vault_uses_registered_exact_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "NLP"
            vault.mkdir()
            completed = MagicMock(stdout=f"Other\t/tmp/other\nNLP\t{vault}\n")
            with patch("obs_project.subprocess.run", return_value=completed) as run:
                self.assertEqual(resolve_vault("NLP"), vault.resolve())
            run.assert_called_once_with(["obsidian", "vaults", "verbose"], check=True, capture_output=True, text=True)

    def test_vault_config_is_host_local_and_environment_can_override_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured = root / "configured"
            override = root / "override"
            configured.mkdir()
            override.mkdir()
            config = root / "config.json"
            result = configure_vault(configured, "Research", config)
            self.assertEqual(result["path"], str(configured.resolve()))
            with patch("obs_project.subprocess.run") as run:
                self.assertEqual(resolve_vault(config_path=config), configured.resolve())
                run.assert_not_called()
            with patch.dict("os.environ", {"OBS_PAPER_VAULT": str(override)}):
                self.assertEqual(resolve_vault(config_path=config), override.resolve())

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

    def test_pdf_line_join_removes_line_break_hyphens_and_keeps_sentences_together(self) -> None:
        lines = [
            Line("A multi-agent architec-", 1, 0, 10, 19, 72, 300, 9, 0),
            Line("ture works e.g. under failure.", 1, 0, 20, 29, 72, 280, 9, 0),
            Line("It recovers.", 1, 0, 30, 39, 80, 140, 9, 0),
        ]
        self.assertEqual(_join_lines(lines), "A multi-agent architecture works e.g. under failure. It recovers.")

    def test_two_column_page_is_read_column_by_column(self) -> None:
        def word(text: str, x0: float, top: float) -> dict[str, object]:
            return {"text": text, "x0": x0, "x1": x0 + 40, "top": top, "bottom": top + 10, "size": 10, "fontname": "Times"}

        words = []
        for row in range(8):
            top = 100 + 12 * row
            words += [word(f"l{row}a", 60, top), word(f"l{row}b", 105, top), word(f"l{row}c", 150, top), word(f"l{row}d", 195, top)]
            words += [word(f"r{row}a", 330, top), word(f"r{row}b", 375, top)]
        lines = page_lines(words, 1, 612)
        self.assertEqual([line.column for line in lines], [0] * 8 + [1] * 8)
        self.assertEqual(lines[8].text, "r0a r0b")

    def test_words_come_from_character_gaps_and_keep_subscripts_on_their_line(self) -> None:
        def char(text: str, x0: float, width: float = 5, top: float = 100, size: float = 10, upright: bool = True) -> dict[str, object]:
            return {"text": text, "x0": x0, "x1": x0 + width, "top": top, "bottom": top + size, "size": size, "fontname": "Times", "upright": upright}

        chars = [char("T", 72), char("h", 77), char("e", 82), char("m", 89.5), char("o", 94.5), char("d", 99.7)]
        chars += [char("i", 105, 2, top=106, size=6), char("7", 20, top=300, upright=False)]
        self.assertEqual([word["text"] for word in build_words(chars, 10)], ["The", "modi"])

    def test_headings_need_real_words_and_are_not_run_in_leads(self) -> None:
        def line(text: str, size: float = 10, bold: float = 1.0) -> Line:
            return Line(text, 1, 0, 100, 100 + size, 72, 300, size, bold)

        self.assertEqual(
            _heading(line("3.2.3 Applications of Attention in our Model"), 10, [], True),
            (2, "Applications of Attention in our Model", "numbered"),
        )
        self.assertIsNone(_heading(line("A", size=24), 10, [24.0], True))
        self.assertIsNone(_heading(line("C X", size=14), 10, [14.0], True))
        self.assertIsNone(_heading(line("Masked LM and the Masking Procedure As-"), 10, [], True))
        self.assertNotEqual(_heading(line("A.1 Illustration of the Tasks"), 10, [], True)[2], "numbered")
        self.assertEqual(_heading(line("A.1 Illustration of the Tasks"), 10, [], True, appendix=True)[0], 1)

    def test_paper_flow_colours_paragraph_roles_and_rejects_green_headings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            project = Path(init_project(vault, "Demo")["root"])
            spec = root / "flow.json"
            blocks = [
                {"key": "b1", "kind": "paragraph", "text": "Ordinary paragraph."},
                {"key": "b2", "kind": "paragraph", "role": "contribution", "text": "We propose a thing."},
                {"key": "b3", "kind": "caption", "text": "Figure 1: A thing."},
            ]
            spec.write_text(json.dumps({"title": "T", "citekey": "k", "item_key": "I", "sections": [{"key": "s1", "title": "Intro", "blocks": blocks}]}), encoding="utf-8")
            document = CanvasDocument.load(Path(build_paper_flow(project, spec)["canvas"]))
            colours = {node.get("text"): node.get("color") for node in document.nodes}
            self.assertEqual((colours["Ordinary paragraph."], colours["We propose a thing."], colours["Figure 1: A thing."]), (None, "4", None))
            blocks[0]["kind"] = "heading"
            blocks[0]["role"] = "contribution"
            spec.write_text(json.dumps({"title": "T", "citekey": "k", "item_key": "I", "sections": [{"key": "s1", "title": "Intro", "blocks": blocks}]}), encoding="utf-8")
            with self.assertRaisesRegex(ProjectError, "contribution"):
                build_paper_flow(project, spec, replace=True)

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


def _pdf_string(text: str) -> str:  # noqa: D103
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, pages: list[list[tuple[str, float, float, float, bool]]]) -> Path:
    """Write a minimal PDF from (text, x, baseline y, size, font[, rotated]) items.

    font is False for Helvetica, True for Helvetica-Bold, or "mono" for Courier.
    A list of strings is drawn as one TJ run with kerning gaps and no space
    characters; rotated text is turned 90 degrees like an arXiv side stamp.
    """
    objects: list[bytes] = [b"", b""]
    for base in ("Helvetica", "Helvetica-Bold", "Courier"):
        objects.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>".encode())
    kids: list[int] = []
    for page in pages:
        commands = []
        for item in page:
            text, x, y, size, font = item[:5]
            name = "F3" if font == "mono" else "F2" if font else "F1"
            place = f"0 1 -1 0 {x} {y} Tm" if len(item) > 5 and item[5] else f"{x} {y} Td"
            if isinstance(text, list):
                show = "[" + " -300 ".join(f"({_pdf_string(part)})" for part in text) + "] TJ"
            else:
                show = f"({_pdf_string(text)}) Tj"
            commands.append(f"BT /{name} {size} Tf {place} {show} ET\n")
        stream = "".join(commands).encode("latin-1")
        kids.append(len(objects) + 1)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents {len(objects) + 2} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = ("<< /Type /Pages /Kids [" + " ".join(f"{kid} 0 R" for kid in kids) + f"] /Count {len(kids)} >>").encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))
    return path


PAPER_TITLE = "Semantic Blocks for Reading Papers"
PAPER_PAGES = [
    [
        ("Preprint. Under review.", 72, 760, 8, False),
        (PAPER_TITLE, 72, 690, 18, True),
        ("Ada Lovelace, Example University", 72, 665, 10, False),
        ("1 Introduction", 72, 630, 14, True),
        ("Reading a paper on a canvas needs units that are larger than one", 84, 605, 10, False),
        ("sentence, because an argument spans several of them. The architec-", 72, 593, 10, False),
        ("ture of a paragraph, e.g. its claim and support, should survive.", 72, 581, 10, False),
        ("In this paper we propose a block builder that keeps paragraphs whole", 84, 569, 10, False),
        ("and marks contribution statements. Our contributions are as follows:", 72, 557, 10, False),
        ("1) a paragraph rule that never splits a sentence into cards,", 84, 545, 10, False),
        ("2) a colour pass that marks candidate contribution paragraphs.", 84, 533, 10, False),
        ("Prior tools split every sentence into its own card, which scatters", 72, 509, 10, False),
        ("one line of reasoning across many cards and hides its structure.", 72, 497, 10, False),
        ("1", 300, 40, 9, False),
    ],
    [
        ("Preprint. Under review.", 72, 760, 8, False),
        ("2 Method", 72, 700, 14, True),
        ("2.1 Line grouping", 72, 675, 11, True),
        ("Words are grouped into lines by their vertical position on the page", 72, 650, 10, False),
        ("and lines are joined into blocks by gap, indentation, and line ends.", 72, 638, 10, False),
        ("Figure 1: Blocks built from the first page of this paper.", 72, 614, 9, False),
        ("The builder we introduce never splits a paragraph at a full stop. It", 72, 590, 10, False),
        ("keeps both sentences of this paragraph in one card.", 72, 578, 10, False),
        ("2", 300, 40, 9, False),
    ],
]


TWO_COLUMN_PAGE = [
    ("arXiv:2609.01234v1 [cs.CL] 15 Sep 2026", 36, 300, 14, False, True),
    ("Reading Two Column Papers Without", 150, 740, 16, True),
    ("Losing the Thread", 235, 721, 16, True),
    ("Ada Lovelace and Grace Hopper", 215, 695, 12, False),
    ("{ada,grace}@example.org", 235, 681, 12, False),
    ("Abstract", 150, 650, 12, True),
    ("We introduce a reader that keeps two", 72, 634, 10, False),
    ("columns apart and joins each paragraph", 72, 622, 10, False),
    ("into one card for the author to review.", 72, 610, 10, False),
    ("1 Introduction", 72, 580, 12, True),
    ("Papers set in two columns place their", 72, 562, 10, False),
    ("lines side by side, so a reader that", 72, 550, 10, False),
    ("groups words by height alone mixes the", 72, 538, 10, False),
    ("two columns into nonsense and loses", 72, 526, 10, False),
    ("the thread of every sentence it reads.", 72, 514, 10, False),
    ("The right column continues with its own", 334, 568, 10, False),
    ("paragraph, which must stay whole and", 322, 556, 10, False),
    ("must not be interleaved with the left.", 322, 544, 10, False),
    ("Input =", 322, 520, 10, False),
    (["Tight", "kerning", "still", "yields", "separate", "words", "and"], 322, 496, 10, False),
    ("the paragraph ends on this short line.", 322, 484, 10, False),
    ("System", 100, 440, 10, False), ("Acc", 400, 440, 10, False), ("F1", 480, 440, 10, False),
    ("Baseline", 100, 428, 10, False), ("71.2", 400, 428, 10, False), ("68.4", 480, 428, 10, False),
    ("Reader", 100, 416, 10, False), ("84.6", 400, 416, 10, False), ("80.1", 480, 416, 10, False),
    ("Table 1: Accuracy of the reader against a baseline on two column pages.", 72, 396, 10, False),
    ("encoder to decoder", 330, 370, 10, "mono"),
    ("1", 306, 40, 10, False),
]
UNHEADED_ABSTRACT_PAGE = [
    ("Unheaded Abstracts Still Count", 72, 720, 18, True),
    ("Grace Hopper, Example Laboratory", 72, 695, 10, False),
    ("grace@example.org", 72, 683, 10, False),
    ("This paper presents a reader that keeps an abstract even when the", 72, 650, 10, False),
    ("template prints no heading above it, because the abstract is the", 72, 638, 10, False),
    ("first place a paper states what it contributes to the field.", 72, 626, 10, False),
    ("1 Introduction", 72, 600, 14, True),
    ("The introduction follows the abstract and opens the first section", 72, 580, 10, False),
    ("of the paper, which the reader turns into its own column of cards.", 72, 568, 10, False),
]


@unittest.skipIf(pdfplumber is None, "pdfplumber is not installed")
class PdfFlowTest(unittest.TestCase):
    def test_two_columns_stamp_table_figure_text_and_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = write_pdf(Path(directory) / "two.pdf", [TWO_COLUMN_PAGE])
            spec, stats = parse_pdf(pdf, title="Two", citekey="two", item_key="TWO")
        self.assertEqual(stats["pdf_title"], "Reading Two Column Papers Without Losing the Thread")
        self.assertEqual([section["title"] for section in spec["sections"]], ["Abstract", "Introduction"])
        abstract, intro = (section["blocks"] for section in spec["sections"])
        self.assertEqual(abstract[0]["text"], "We introduce a reader that keeps two columns apart and joins each paragraph into one card for the author to review.")
        self.assertEqual(abstract[0].get("role"), "contribution")
        self.assertEqual([block["kind"] for block in intro], ["paragraph", "paragraph", "paragraph", "caption"])
        self.assertEqual(intro[0]["text"], (
            "Papers set in two columns place their lines side by side, so a reader that groups words by height "
            "alone mixes the two columns into nonsense and loses the thread of every sentence it reads."
        ))
        self.assertEqual(intro[1]["text"], "The right column continues with its own paragraph, which must stay whole and must not be interleaved with the left.")
        self.assertEqual(intro[2]["text"], "Tight kerning still yields separate words and the paragraph ends on this short line.")
        self.assertTrue(intro[3]["text"].startswith("Table 1: Accuracy"))
        every_text = " ".join(block["text"] for section in spec["sections"] for block in section["blocks"])
        for dropped in ("arXiv", "2609", "System", "71.2", "encoder to decoder", "Lovelace", "@", "Input"):
            self.assertNotIn(dropped, every_text)
        filtered = stats["filtered"]
        self.assertGreater(filtered["rotated_chars"], 0)
        self.assertGreaterEqual(filtered["table"], 3)
        self.assertGreaterEqual(filtered["figure_text"], 1)
        self.assertEqual(filtered["fragments_dropped"], 1)

    def test_prose_above_the_first_heading_is_kept_as_the_abstract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = write_pdf(Path(directory) / "unheaded.pdf", [UNHEADED_ABSTRACT_PAGE])
            spec, stats = parse_pdf(pdf, title="Unheaded", citekey="u", item_key="U")
        self.assertEqual([section["title"] for section in spec["sections"]], ["Abstract", "Introduction"])
        abstract = spec["sections"][0]["blocks"]
        self.assertEqual(len(abstract), 1)
        self.assertTrue(abstract[0]["text"].startswith("This paper presents a reader"))
        self.assertEqual(abstract[0].get("role"), "contribution")
        self.assertNotIn("Grace", " ".join(block["text"] for section in spec["sections"] for block in section["blocks"]))
        self.assertEqual(stats["filtered"]["author_block"], 1)

    def test_blocks_headings_and_contribution_marks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = write_pdf(Path(directory) / "paper.pdf", PAPER_PAGES)
            spec, stats = parse_pdf(pdf, title=PAPER_TITLE, citekey="lovelace2026", item_key="ABCD1234")
        self.assertEqual((stats["pages"], stats["dropped_lines"], stats["pdf_title"]), (2, 4, PAPER_TITLE))
        self.assertEqual([section["title"] for section in spec["sections"]], ["Introduction", "Method"])
        intro, method = (section["blocks"] for section in spec["sections"])
        self.assertEqual([block["kind"] for block in intro], ["paragraph"] * 5)
        self.assertEqual(intro[0]["text"], (
            "Reading a paper on a canvas needs units that are larger than one sentence, because an argument "
            "spans several of them. The architecture of a paragraph, e.g. its claim and support, should survive."
        ))
        self.assertEqual(intro[1]["text"], (
            "In this paper we propose a block builder that keeps paragraphs whole and marks contribution "
            "statements. Our contributions are as follows:"
        ))
        self.assertTrue(intro[2]["text"].startswith("1) ") and intro[3]["text"].startswith("2) "))
        self.assertTrue(intro[4]["text"].startswith("Prior tools") and intro[4]["text"].endswith("hides its structure."))
        self.assertEqual([block["kind"] for block in method], ["heading", "paragraph", "caption", "paragraph"])
        self.assertEqual((method[0]["level"], method[0]["text"]), (1, "Line grouping"))
        self.assertEqual(method[2]["text"], "Figure 1: Blocks built from the first page of this paper.")
        self.assertEqual(method[3]["text"], (
            "The builder we introduce never splits a paragraph at a full stop. It keeps both sentences of this paragraph in one card."
        ))
        every_text = " ".join(block["text"] for section in spec["sections"] for block in section["blocks"])
        for dropped in ("Preprint", PAPER_TITLE, "Lovelace"):
            self.assertNotIn(dropped, every_text)
        self.assertFalse(any(block["text"] in {"1", "2"} for section in spec["sections"] for block in section["blocks"]))
        self.assertEqual(stats["contributions"], [intro[1]["key"], intro[2]["key"], intro[3]["key"]])
        self.assertNotIn("role", method[3])

    def test_canvas_is_valid_grouped_coloured_and_linkable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            project = Path(init_project(vault, "Demo")["root"])
            pdf = write_pdf(root / "paper.pdf", PAPER_PAGES)
            result = build_from_pdf(project, pdf, title=PAPER_TITLE, citekey="lovelace2026", item_key="ABCD1234")
            self.assertEqual(result["paper_flow"], f"Paper/{PAPER_TITLE}.canvas")
            self.assertTrue((vault / result["paper_flow"]).is_file())
            document = CanvasDocument.load(Path(result["canvas"]))
            document.validate_integrity()

            groups = [node for node in document.nodes if node["type"] == "group"]
            cards = [node for node in document.nodes if node["type"] != "group"]
            self.assertEqual(len(groups), 1)
            self.assertIn(PAPER_TITLE, groups[0]["label"])
            self.assertTrue(all(node_rect(groups[0]).contains(card) for card in cards))
            for index, left in enumerate(cards):
                for right in cards[index + 1:]:
                    self.assertFalse(rects_overlap(node_rect(left), node_rect(right)), (left["text"], right["text"]))

            green = sorted(card["text"][:2] for card in cards if card.get("color") == "4")
            self.assertEqual(green, ["1)", "2)", "In"])
            for card in cards:
                if card["text"].startswith("# "):
                    self.assertEqual(card.get("color"), "6")
                elif card.get("color") != "4":
                    self.assertNotIn("color", card)
            subheading = next(card for card in cards if card["text"] == "# Line grouping")
            method = next(card for card in cards if card["text"] == "# Method")
            self.assertEqual(subheading["x"], method["x"] + 40)
            intro_column = next(card for card in cards if card["text"] == "# Introduction")
            self.assertGreater(method["x"], intro_column["x"] + intro_column["width"])

            research = root / "research.canvas"
            research.write_text(json.dumps({"nodes": [
                {"id": "flow", "type": "group", "x": 0, "y": 0, "width": 3000, "height": 1200, "label": "Research Flow"},
                {"id": "rq", "type": "text", "x": 1200, "y": 600, "width": 560, "height": 120, "text": "# RQ1", "color": "6"},
            ], "edges": []}), encoding="utf-8")
            apply_patch(research, compile_request(research, {
                "schema_version": 1,
                "workflow": "research-flow",
                "target": {"group_label": "Research Flow"},
                "actions": [{
                    "op": "link_literature", "key": "lovelace-rq1", "target_id": "rq", "title": PAPER_TITLE,
                    "citekey": result["citekey"], "item_key": result["item_key"], "paper_flow": result["paper_flow"],
                }],
            }))
            self.assertTrue(any(f"[[{result['paper_flow']}|Paper flow]]" in node.get("text", "") for node in CanvasDocument.load(research).nodes))

    def test_override_and_replace_keep_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "NLP"
            vault.mkdir()
            project = Path(init_project(vault, "Demo")["root"])
            pdf = write_pdf(root / "paper.pdf", PAPER_PAGES)
            arguments = {"title": PAPER_TITLE, "citekey": "lovelace2026", "item_key": "ABCD1234"}
            build_from_pdf(project, pdf, **arguments)
            with self.assertRaisesRegex(ProjectError, "different content"):
                build_from_pdf(project, pdf, contributions=[], **arguments)
            replaced = build_from_pdf(project, pdf, contributions=["b5"], replace=True, spec_output=root / "flow.json", **arguments)
            self.assertEqual((replaced["status"], replaced["contributions"], replaced["contribution_source"]), ("replaced", ["b5"], "override"))
            self.assertEqual(len(list((vault / "Paper" / ".canvas-history").glob("*.canvas"))), 1)
            green = [node["text"] for node in CanvasDocument.load(Path(replaced["canvas"])).nodes if node.get("color") == "4"]
            self.assertEqual(len(green), 1)
            self.assertTrue(green[0].startswith("Prior tools"))
            self.assertIn('"role": "contribution"', (root / "flow.json").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ProjectError, "b6"):
                parse_pdf(pdf, contributions=["b6"], **arguments)

    def test_pdf_without_text_layer_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = write_pdf(Path(directory) / "scan.pdf", [[]])
            with self.assertRaisesRegex(ProjectError, "no usable text layer"):
                parse_pdf(pdf, title="Scan", citekey="scan", item_key="SCAN")


if __name__ == "__main__":
    unittest.main()


class WebModeTest(unittest.TestCase):
    def test_local_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = ZoteroClient()
        self.assertFalse(client.web)
        self.assertEqual(client.library, "users/0")
        self.assertEqual(client.base_url, "http://127.0.0.1:23119/api")

    def test_web_when_both_variables_are_set(self) -> None:
        env = {"ZOTERO_USER_ID": "19289380", "ZOTERO_API_KEY": "secret"}
        with patch.dict("os.environ", env, clear=True):
            client = ZoteroClient()
        self.assertTrue(client.web)
        self.assertEqual(client.library, "users/19289380")
        self.assertEqual(client.base_url, "https://api.zotero.org")

    def test_a_key_without_a_user_id_stays_local(self) -> None:
        with patch.dict("os.environ", {"ZOTERO_API_KEY": "secret"}, clear=True):
            client = ZoteroClient()
        self.assertFalse(client.web)

    def test_web_mode_carries_the_key_and_needs_no_prompt(self) -> None:
        client = ZoteroClient(user_id="19289380", api_key="secret")
        self.assertEqual(client.authorize(), "secret")
        self.assertEqual(client._write_headers(), {})
        with patch("zotero_bridge.urlopen") as opened:
            opened.return_value.__enter__.return_value.read.return_value = b"{}"
            opened.return_value.__enter__.return_value.headers.items.return_value = []
            client._request("keys/current")
        request = opened.call_args[0][0]
        self.assertEqual(request.full_url, "https://api.zotero.org/keys/current")
        self.assertEqual(request.get_header("Zotero-api-key"), "secret")

    def test_stored_pdfs_stay_on_the_desktop(self) -> None:
        client = ZoteroClient(user_id="19289380", api_key="secret")
        for call in (
            lambda: client.attachment_path("ABCD1234"),
            lambda: client.import_pdf("ABCD1234", Path("paper.pdf")),
        ):
            with self.assertRaises(ZoteroError) as raised:
                call()
            self.assertIn("Zotero Desktop", str(raised.exception))
