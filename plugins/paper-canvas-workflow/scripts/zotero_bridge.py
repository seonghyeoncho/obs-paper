#!/usr/bin/env python3
"""Local Zotero bridge for project papers, citations, and Canvas links."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse, unquote
from urllib.request import Request, urlopen

from obs_paper_engine import apply_patch, compile_request
from obs_project import _frontmatter_value, set_frontmatter_value
from record_action import append_action


class ZoteroError(RuntimeError):
    """Zotero or Better BibTeX did not provide a usable response."""


class ZoteroClient:
    def __init__(self, base_url: str = "http://localhost:23119/api") -> None:
        self.base_url = base_url.rstrip("/")

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Any | None = None,
        headers: dict[str, str] | None = None,
        text: bool = False,
    ) -> tuple[Any, dict[str, str]]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=data,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                payload = raw if text else (json.loads(raw) if raw else {})
                return payload, dict(response.headers.items())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ZoteroError(f"Zotero HTTP {exc.code}: {detail or exc.reason}") from exc
        except URLError as exc:
            raise ZoteroError("Zotero is not reachable; start Zotero and enable its Local API") from exc

    def status(self) -> dict[str, Any]:
        _, headers = self._request("", text=True)
        normalized = {key.lower(): value for key, value in headers.items()}
        server_id = normalized.get("zotero-server-id")
        return {
            "status": "ok",
            "zotero_version": normalized.get("x-zotero-version"),
            "server_id": server_id,
            "api_version": normalized.get("zotero-api-version"),
            "local_writes": bool(server_id),
        }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        params = urlencode({"q": query, "qmode": "everything", "format": "json", "limit": limit})
        payload, _ = self._request(f"users/0/items/top?{params}")
        if not isinstance(payload, list):
            raise ZoteroError("Zotero search returned an unexpected response")
        return [
            {
                "key": item.get("key") or item.get("data", {}).get("key"),
                "title": item.get("data", {}).get("title", ""),
                "date": item.get("data", {}).get("date", ""),
                "doi": item.get("data", {}).get("DOI", ""),
                "creators": item.get("data", {}).get("creators", []),
            }
            for item in payload
        ]

    def _bbt_rpc(self, method: str, params: list[Any]) -> Any:
        request = Request(
            "http://localhost:23119/better-bibtex/json-rpc",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read())
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            raise ZoteroError("Better BibTeX JSON-RPC is unavailable") from exc
        if payload.get("error"):
            raise ZoteroError(f"Better BibTeX error: {payload['error']}")
        return payload.get("result")

    def citation(self, item_key: str) -> dict[str, str]:
        try:
            keys = self._bbt_rpc("item.citationkey", [[item_key]])
            citekey = next(iter(keys.values())) if isinstance(keys, dict) and keys else None
            source = "better-bibtex"
        except ZoteroError:
            raw, _ = self._request(f"users/0/items/{quote(item_key)}?format=bibtex", text=True)
            match = re.search(r"@[A-Za-z]+\s*\{\s*([^,\s]+)", raw)
            citekey = match.group(1) if match else None
            source = "zotero-bibtex"
        if not citekey:
            raise ZoteroError(f"no citation key for Zotero item {item_key}")
        return {
            "item_key": item_key,
            "citekey": citekey,
            "command": f"\\cite{{{citekey}}}",
            "select_uri": f"zotero://select/library/items/{item_key}",
            "source": source,
        }

    def authorize(self, app_name: str = "Obs Paper") -> str:
        status = self.status()
        server_id = status.get("server_id")
        if not server_id:
            version = status.get("zotero_version") or "unknown"
            raise ZoteroError(
                f"Zotero {version} local API is read-only; install Zotero 10+ or use a zotero.org write API key"
            )
        payload, _ = self._request(
            "local/authorize",
            method="POST",
            body={"appName": app_name},
            headers={"Zotero-Server-ID": server_id},
        )
        key = payload.get("key") if isinstance(payload, dict) else None
        if not key:
            raise ZoteroError("Zotero write authorization was not granted")
        return key

    def create_item(self, metadata: dict[str, Any], api_key: str | None = None) -> str:
        title = metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ZoteroError("metadata needs a non-empty title")
        item = dict(metadata)
        item.setdefault("itemType", "journalArticle")
        item.setdefault("creators", [])
        item.setdefault("tags", [])
        item.setdefault("collections", [])
        key = api_key or os.environ.get("ZOTERO_LOCAL_API_KEY") or self.authorize()
        status = self.status()
        payload, _ = self._request(
            "users/0/items",
            method="POST",
            body=[item],
            headers={"Zotero-API-Key": key, "Zotero-Server-ID": status["server_id"]},
        )
        successful = payload.get("successful", {}) if isinstance(payload, dict) else {}
        created = successful.get("0") or successful.get(0)
        item_key = created.get("key") if isinstance(created, dict) else None
        if not item_key:
            raise ZoteroError(f"Zotero did not create the item: {payload}")
        return item_key

    def collections(self) -> list[dict[str, Any]]:
        payload, _ = self._request("users/0/collections?limit=100")
        if not isinstance(payload, list):
            raise ZoteroError("Zotero collections returned an unexpected response")
        return payload

    def ensure_collection(self, name: str) -> str:
        matches = [
            collection
            for collection in self.collections()
            if collection.get("data", {}).get("name") == name
            and not collection.get("data", {}).get("parentCollection")
        ]
        if len(matches) > 1:
            raise ZoteroError(f"multiple top-level Zotero collections named {name!r}")
        if matches:
            collection_key = matches[0].get("key") or matches[0].get("data", {}).get("key")
            if not collection_key:
                raise ZoteroError(f"Zotero collection {name!r} has no key")
            return str(collection_key)
        key = os.environ.get("ZOTERO_LOCAL_API_KEY") or self.authorize()
        status = self.status()
        payload, _ = self._request(
            "users/0/collections",
            method="POST",
            body=[{"name": name, "parentCollection": False}],
            headers={"Zotero-API-Key": key, "Zotero-Server-ID": status["server_id"]},
        )
        created = payload.get("successful", {}).get("0", {}) if isinstance(payload, dict) else {}
        collection_key = created.get("key")
        if not collection_key:
            raise ZoteroError(f"Zotero did not create the collection: {payload}")
        return collection_key

    def add_item_to_collection(self, item_key: str, collection_key: str) -> None:
        item, _ = self._request(f"users/0/items/{quote(item_key)}")
        data = item.get("data", {}) if isinstance(item, dict) else {}
        collections = list(data.get("collections", []))
        if collection_key in collections:
            return
        collections.append(collection_key)
        key = os.environ.get("ZOTERO_LOCAL_API_KEY") or self.authorize()
        status = self.status()
        headers = {"Zotero-API-Key": key, "Zotero-Server-ID": status["server_id"]}
        version = item.get("version") or data.get("version")
        if version is not None:
            headers["If-Unmodified-Since-Version"] = str(version)
        self._request(
            f"users/0/items/{quote(item_key)}",
            method="PATCH",
            body={"collections": collections},
            headers=headers,
        )

    def collection_bibtex(self, collection_key: str) -> str:
        chunks: list[str] = []
        start = 0
        while True:
            raw, headers = self._request(
                f"users/0/collections/{quote(collection_key)}/items/top?format=bibtex&limit=100&start={start}",
                text=True,
            )
            chunks.append(raw)
            total = int(next((value for key, value in headers.items() if key.lower() == "total-results"), start + 100))
            start += 100
            if start >= total:
                return "\n".join(chunk.rstrip() for chunk in chunks if chunk).rstrip() + ("\n" if any(chunks) else "")

    def attachment_path(self, item_key: str) -> Path:
        children, _ = self._request(f"users/0/items/{quote(item_key)}/children")
        for child in children if isinstance(children, list) else []:
            data = child.get("data", {})
            if data.get("itemType") != "attachment" or data.get("contentType") != "application/pdf":
                continue
            child_key = child.get("key") or data.get("key")
            value, _ = self._request(f"users/0/items/{quote(child_key)}/file/view/url", text=True)
            parsed = urlparse(value.strip())
            path = Path(unquote(parsed.path)) if parsed.scheme == "file" else None
            if path and path.is_file():
                return path
        raise ZoteroError(f"Zotero item {item_key} has no readable PDF attachment")


def _safe_pdf_name(path: Path) -> str:
    name = re.sub(r"[^\w.() -]+", "_", path.name, flags=re.UNICODE).strip(" .")
    return name or "paper.pdf"


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_pdf(project: Path, source: Path) -> Path:
    papers = project / "papers"
    if not (project / "project.md").is_file() or not papers.is_dir():
        raise ZoteroError(f"not an Obs Paper project: {project}")
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ZoteroError(f"PDF does not exist: {source}")
    destination = papers / _safe_pdf_name(source)
    if destination.exists() and _file_hash(destination) != _file_hash(source):
        raise ZoteroError(f"different PDF already exists: {destination}")
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


def _project_collection(project: Path, client: ZoteroClient) -> str:
    metadata = project / "project.md"
    if not metadata.is_file():
        raise ZoteroError(f"not an Obs Paper project: {project}")
    collection_key = _frontmatter_value(metadata, "zotero_collection")
    if collection_key:
        return collection_key
    collection_key = client.ensure_collection(project.name)
    set_frontmatter_value(metadata, "zotero_collection", collection_key)
    append_action(
        project / "CANVAS_ACTION_LOG.md",
        status="done",
        action="setup-zotero-collection",
        target=collection_key,
        reason=project.name,
        result=f"Bound project to Zotero collection {project.name}",
    )
    return collection_key


_BIB_KEY = re.compile(r"@[A-Za-z]+\s*\{\s*([^,\s]+)")
_CITE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}")


def bib_keys(text: str) -> set[str]:
    return set(_BIB_KEY.findall(text))


def cited_keys(project: Path, sources: list[Path] | None = None) -> set[str]:
    if sources is None:
        repository = _frontmatter_value(project / "project.md", "repository")
        roots = [project]
        if repository and Path(repository).is_dir() and Path(repository).resolve() != project.resolve():
            roots.append(Path(repository))
        sources = [
            path
            for root in roots
            for suffix in ("*.tex", "*.md", "*.canvas")
            for path in root.rglob(suffix)
            if path.name != "CANVAS_ACTION_LOG.md"
        ]
    found: set[str] = set()
    for path in sources:
        if not path.is_file():
            continue
        for group in _CITE.findall(path.read_text(encoding="utf-8", errors="replace")):
            found.update(key.strip() for key in group.split(",") if key.strip() and key.strip() != "*")
    return found


def audit_citations(project: Path, sources: list[Path] | None = None, bib_text: str | None = None) -> dict[str, list[str]]:
    bibliography = project / (_frontmatter_value(project / "project.md", "bibliography") or "references.bib")
    keys = bib_keys(bib_text if bib_text is not None else (bibliography.read_text(encoding="utf-8") if bibliography.exists() else ""))
    cited = cited_keys(project, sources)
    return {
        "cited": sorted(cited),
        "bib_keys": sorted(keys),
        "missing": sorted(cited - keys),
        "unused": sorted(keys - cited),
    }


def export_bibliography(project: Path, client: ZoteroClient) -> dict[str, Any]:
    collection_key = _project_collection(project, client)
    text = client.collection_bibtex(collection_key)
    audit = audit_citations(project, bib_text=text)
    if audit["missing"]:
        raise ZoteroError(
            "collection export would remove cited keys: " + ", ".join(audit["missing"])
        )
    bibliography = project / (_frontmatter_value(project / "project.md", "bibliography") or "references.bib")
    bibliography.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=bibliography.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, bibliography)
    return {"collection_key": collection_key, "bibliography": str(bibliography), **audit}


def setup_project(project: Path, client: ZoteroClient, *, export: bool = True) -> dict[str, Any]:
    collection_key = _project_collection(project, client)
    if not export:
        return {"collection": project.name, "collection_key": collection_key, "bibliography": None}
    result = export_bibliography(project, client)
    return {"collection": project.name, **result}


def record_search(project: Path, record_path: Path) -> dict[str, Any]:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not all(isinstance(record.get(key), str) and record[key].strip() for key in ("provider", "query")):
        raise ZoteroError("search record needs non-empty provider and query strings")
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), **record}
    log_name = _frontmatter_value(project / "project.md", "search_log") or "searches.jsonl"
    with (project / log_name).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    append_action(
        project / "CANVAS_ACTION_LOG.md",
        status="done",
        action="record-literature-search",
        target=record["provider"],
        reason=record["query"],
        result=f"Recorded search in {log_name}",
    )
    return record


def add_paper(
    project: Path,
    metadata_path: Path,
    pdf: Path,
    client: ZoteroClient,
    *,
    export: bool = True,
) -> dict[str, str]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ZoteroError("metadata JSON root must be an object")
    destination = save_pdf(project, pdf)
    collection_key = _project_collection(project, client)
    metadata["collections"] = sorted(set(metadata.get("collections", [])) | {collection_key})
    item_key = client.create_item(metadata)
    citation = client.citation(item_key)
    record = {**citation, "pdf": destination.relative_to(project).as_posix()}
    index_path = project / "papers" / "index.json"
    records = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    records = [entry for entry in records if entry.get("item_key") != item_key]
    records.append(record)
    index_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_action(
        project / "CANVAS_ACTION_LOG.md",
        status="done",
        action="add-zotero-paper",
        target=item_key,
        reason=str(metadata_path),
        result=f"Saved {record['pdf']} with citation {record['command']}",
    )
    if export:
        export_bibliography(project, client)
    return record


def link_canvas(
    canvas: Path,
    *,
    target: dict[str, str],
    sentence_id: str,
    item_key: str,
    lane: str,
    log: Path | None,
    client: ZoteroClient,
) -> dict[str, Any]:
    citation = client.citation(item_key)
    request = {
        "schema_version": 1,
        "workflow": "paper",
        "target": target,
        "actions": [
            {
                "op": "split_citation",
                "key": f"zotero-{item_key}",
                "sentence_id": sentence_id,
                "command": citation["command"],
                "card_text": f"{citation['command']}\n[Open in Zotero]({citation['select_uri']})",
                "lane": lane,
            }
        ],
    }
    return apply_patch(
        canvas,
        compile_request(canvas, request),
        log or canvas.parent / "CANVAS_ACTION_LOG.md",
    )


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:23119/api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    cite = commands.add_parser("cite")
    cite.add_argument("item_key")
    save = commands.add_parser("save")
    save.add_argument("project", type=Path)
    save.add_argument("item_key")
    save.add_argument("--defer-export", action="store_true")
    setup = commands.add_parser("project-setup")
    setup.add_argument("project", type=Path)
    setup.add_argument("--defer-export", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("project", type=Path)
    audit = commands.add_parser("audit")
    audit.add_argument("project", type=Path)
    audit.add_argument("sources", nargs="*", type=Path)
    record = commands.add_parser("record-search")
    record.add_argument("project", type=Path)
    record.add_argument("record", type=Path)
    add = commands.add_parser("add")
    add.add_argument("project", type=Path)
    add.add_argument("metadata", type=Path)
    add.add_argument("pdf", type=Path)
    add.add_argument("--defer-export", action="store_true")
    link = commands.add_parser("canvas-link")
    link.add_argument("canvas", type=Path)
    group = link.add_mutually_exclusive_group(required=True)
    group.add_argument("--group-id")
    group.add_argument("--group-label")
    link.add_argument("--sentence-id", required=True)
    link.add_argument("--item-key", required=True)
    link.add_argument("--lane", choices=("left", "right"), default="right")
    link.add_argument("--log", type=Path)
    args = parser.parse_args()
    client = ZoteroClient(args.base_url)
    try:
        if args.command == "status":
            _emit(client.status())
        elif args.command == "search":
            _emit(client.search(args.query, args.limit))
        elif args.command == "cite":
            _emit(client.citation(args.item_key))
        elif args.command == "project-setup":
            _emit(setup_project(args.project, client, export=not args.defer_export))
        elif args.command == "export":
            _emit(export_bibliography(args.project, client))
        elif args.command == "audit":
            result = audit_citations(args.project, args.sources or None)
            _emit(result)
            if result["missing"]:
                raise SystemExit(1)
        elif args.command == "record-search":
            _emit(record_search(args.project, args.record))
        elif args.command == "save":
            collection_key = _project_collection(args.project, client)
            client.add_item_to_collection(args.item_key, collection_key)
            source = client.attachment_path(args.item_key)
            destination = save_pdf(args.project, source)
            bibliography = None if args.defer_export else export_bibliography(args.project, client)
            append_action(
                args.project / "CANVAS_ACTION_LOG.md",
                status="done",
                action="save-zotero-pdf",
                target=args.item_key,
                reason=str(source),
                result=f"Saved {destination}" + (f" and refreshed {bibliography['bibliography']}" if bibliography else "; export deferred"),
            )
            _emit({"item_key": args.item_key, "pdf": str(destination), "bibliography": bibliography["bibliography"] if bibliography else None})
        elif args.command == "add":
            _emit(add_paper(args.project, args.metadata, args.pdf, client, export=not args.defer_export))
        else:
            target = {"group_id": args.group_id} if args.group_id else {"group_label": args.group_label}
            _emit(link_canvas(args.canvas, target=target, sentence_id=args.sentence_id, item_key=args.item_key, lane=args.lane, log=args.log, client=client))
    except (ZoteroError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
