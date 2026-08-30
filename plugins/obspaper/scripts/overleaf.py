#!/usr/bin/env python3
"""Overleaf operations over the Aside browser session.

Overleaf has no public API, and its git and Zotero integrations are paid-only.
Aside's REPL exposes a `fetch` that carries the signed-in browser session, so
these operations run as authenticated HTTP rather than UI automation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = "https://www.overleaf.com"
MARKER = "__OVERLEAF_JSON__"


class OverleafError(RuntimeError):
    pass


def aside_binary() -> str:
    found = shutil.which("aside")
    if found:
        return found
    fallback = Path.home() / ".local/bin/aside"
    if fallback.exists():
        return str(fallback)
    raise OverleafError("aside CLI not found; install it and re-run (see skills/overleaf/SKILL.md)")


def parse_repl_output(out: str) -> tuple[dict, str]:
    """Pull the marker payload and the session cwd out of REPL output.

    Aside interleaves its own trace lines with anything the code logs, so the
    payload is found by marker rather than by position.
    """
    payload: dict = {}
    cwd = ""
    for line in out.splitlines():
        if MARKER in line:
            payload = json.loads(line.split(MARKER, 1)[1])
        elif "__OVERLEAF_PWD__" in line:
            cwd = line.split("__OVERLEAF_PWD__", 1)[1].strip()
    return payload, cwd


def run_js(body: str, *, account: str | None = None, timeout: int = 180) -> tuple[dict, str]:
    """Run JS in the Aside REPL. Returns (parsed marker payload, session cwd)."""
    code = (
        "const __base = %r;\n"
        "const __csrf = async () => (await (await fetch(__base + '/project')).text())"
        ".match(/<meta name=\"ol-csrfToken\"[^>]*content=\"([^\"]*)\"/)[1];\n"
        "const emit = (o) => console.log(%r + JSON.stringify(o));\n"
        "%s\n"
        "console.log('__OVERLEAF_PWD__' + pwd);\n" % (BASE, MARKER, body)
    )
    cmd = [aside_binary()]
    if account:
        cmd += ["--account", account]
    cmd += ["repl", code]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = proc.stdout + proc.stderr
    if proc.returncode != 0 and MARKER not in out:
        raise OverleafError(f"aside repl failed:\n{out.strip()[:2000]}")
    payload, cwd = parse_repl_output(out)
    if not payload:
        raise OverleafError(f"no result from aside repl:\n{out.strip()[:2000]}")
    if "error" in payload:
        raise OverleafError(payload["error"])
    return payload, cwd


_DECODE_BLOB = """
const __h = await (await fetch(__base + '/project')).text();
const __m = __h.match(/<meta name="ol-prefetchedProjectsBlob"[^>]*content="([^"]*)"/);
if (!__m) { emit({error: 'project list blob not found; is the Aside browser signed in to Overleaf?'}); }
const __j = JSON.parse(__m[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&#39;/g,String.fromCharCode(39)));
const projects = __j.projects || __j;
"""


def list_projects(*, include_trashed: bool = False, account: str | None = None) -> dict:
    body = _DECODE_BLOB + """
const keep = projects.filter(p => %s);
emit({projects: keep.map(p => ({
  id: p.id, name: p.name, owner: p.owner && p.owner.email,
  access: p.accessLevel, trashed: !!p.trashed, archived: !!p.archived,
  lastUpdated: p.lastUpdated,
}))});
""" % ("true" if include_trashed else "!p.trashed && !p.archived")
    return run_js(body, account=account)[0]


def project_info(project_id: str, *, account: str | None = None) -> dict:
    body = """
const h = await (await fetch(__base + '/project/%s')).text();
const g = n => { const m = h.match(new RegExp('<meta name="' + n + '"[^>]*>')); if (!m) return null;
  const c = m[0].match(/content="([^"]*)"/); return c ? c[1] : ''; };
emit({
  id: '%s', name: g('ol-projectName'),
  gitBridgeEnabled: !!g('ol-gitBridgeEnabled'),
  trackChanges: !!g('ol-hasTrackChangesFeature'),
  compileSettings: g('ol-compileSettings'),
});
""" % (project_id, project_id)
    return run_js(body, account=account)[0]


def clone_project(template_id: str, name: str, *, account: str | None = None) -> dict:
    """Copy a template project under a new name. One call does both."""
    body = """
const csrf = await __csrf();
const r = await fetch(__base + '/project/%s/clone', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Accept': 'application/json'},
  body: JSON.stringify({projectName: %s}),
});
if (r.status !== 200) { emit({error: 'clone failed with status ' + r.status}); }
const j = await r.json();
emit({id: j.project_id, name: j.name, url: __base + '/project/' + j.project_id});
""" % (template_id, json.dumps(name))
    return run_js(body, account=account)[0]


def trash_project(project_id: str, *, account: str | None = None) -> dict:
    """Move to Overleaf's trash. Reversible; never permanently deletes."""
    body = """
const csrf = await __csrf();
const r = await fetch(__base + '/project/%s/trash', {method: 'POST',
  headers: {'X-CSRF-Token': csrf, 'Accept': 'application/json'}});
emit({id: '%s', status: r.status, trashed: r.status === 200});
""" % (project_id, project_id)
    return run_js(body, account=account)[0]


def download_zip(project_id: str, out: Path, *, account: str | None = None) -> dict:
    """Pull the project source. The REPL sandbox only writes under its session
    directory, so land it there and move it out."""
    name = f"{project_id}.zip"
    body = """
const r = await fetch(__base + '/project/%s/download/zip');
if (r.status !== 200) { emit({error: 'download failed with status ' + r.status}); }
const b = Buffer.from(await r.arrayBuffer());
await fs.writeFile(%s, b);
emit({bytes: b.length, file: %s});
""" % (project_id, json.dumps(name), json.dumps(name))
    payload, cwd = run_js(body, account=account, timeout=300)
    staged = Path(cwd) / payload["file"]
    if not staged.exists():
        raise OverleafError(f"aside reported writing {staged}, but it is not there")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged), out)
    return {"path": str(out), "bytes": payload["bytes"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", help="Aside account id, for example u0")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list projects (trashed and archived are hidden)")
    p.add_argument("--include-trashed", action="store_true")

    p = sub.add_parser("info", help="read a project's name and entitlements")
    p.add_argument("project_id")

    p = sub.add_parser("clone", help="copy a template project under a new name")
    p.add_argument("template_id")
    p.add_argument("--name", required=True)

    p = sub.add_parser("download", help="download the project source as a zip")
    p.add_argument("project_id")
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("trash", help="move a project to Overleaf's trash (reversible)")
    p.add_argument("project_id")

    args = parser.parse_args()
    try:
        if args.command == "list":
            result = list_projects(include_trashed=args.include_trashed, account=args.account)
        elif args.command == "info":
            result = project_info(args.project_id, account=args.account)
        elif args.command == "clone":
            result = clone_project(args.template_id, args.name, account=args.account)
        elif args.command == "download":
            result = download_zip(args.project_id, args.out, account=args.account)
        else:
            result = trash_project(args.project_id, account=args.account)
    except (OverleafError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
