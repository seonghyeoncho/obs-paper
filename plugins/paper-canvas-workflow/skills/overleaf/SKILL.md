---
name: overleaf
description: Create and read a project's Overleaf manuscript from a research project — copy a LaTeX template into a new project, list projects, read entitlements, download the source, or trash a project. Use when connecting a project to Overleaf or pulling the manuscript down; writing files back into Overleaf is not supported yet.
---

# Overleaf

Overleaf holds the manuscript. The Canvas is where the user thinks, revises, and builds the research flow; Overleaf is where the manuscript officially lives and where co-authors comment and co-edit.

## There is no API and no git

Overleaf publishes no project API, and both git integration and the Zotero reference sync are paid-only. Do not propose them, and do not suggest handing a project to a paid collaborator to unlock them: git and track-changes are per-user entitlements, so an owner's paid plan reaches collaborators as compile budget only. Check with `info` rather than assuming; `gitBridgeEnabled` reports what the signed-in user can actually do.

Instead `../../scripts/overleaf.py` drives Overleaf as authenticated HTTP inside the Aside browser session. Requires the Aside CLI on `PATH` (or at `~/.local/bin/aside`) and that browser signed in to Overleaf.

```bash
python /path/to/plugin/scripts/overleaf.py list
python /path/to/plugin/scripts/overleaf.py info <project_id>
python /path/to/plugin/scripts/overleaf.py clone <template_id> --name '[<venue>] <English title>'
python /path/to/plugin/scripts/overleaf.py download <project_id> --out <path>.zip
python /path/to/plugin/scripts/overleaf.py trash <project_id>
```

Prefer this script to Aside's natural-language agent (`aside "<task>"`). The agent works and recovers from its own errors, but it takes a different path every run; these endpoints do the same thing every time in about a second. Reach for the agent only where no endpoint exists.

## Creating a project

Copy the user's LaTeX template — never create a blank project. `clone` copies and names in one call, so the new project arrives with its document class, style files, and `custom.bib` already in place. That also settles who owns the preamble: the template does, not the Canvas.

Name it `[<venue>] <English title>`. **Always ask for the venue** — it is a submission decision, written either as a conference name or in ARR round form such as `ARR 10`, and it is never derivable from the repository. Titles are always English even when the manuscript is Korean, so translate a Korean title and show the translation for approval instead of committing to it silently.

Record the resulting project id in the project's `project.md` so later work does not have to search for it.

## Reading the manuscript

`download` writes the project source as a zip. Aside's REPL sandbox can only write inside its own session directory, so the script lands the file there and moves it out; that is why the download path is a real local path and not a REPL path.

## Care

`list` hides trashed and archived projects, because Overleaf's project blob includes both and they otherwise show up as phantom duplicates of a live project. Pass `--include-trashed` only when the user asks about the trash.

`trash` is Overleaf's reversible trash, not deletion. Never permanently delete a project, and confirm before trashing anything the user did not ask you to create.

Most of the user's projects are owned by collaborators and reachable with `readWrite`. Treat someone else's project as read-only unless the user says otherwise, and never trash one.

Writing files back into Overleaf is not implemented. The upload endpoint has not been verified, so do not improvise one and do not fall back to driving the UI: pushing a file wholesale would silently overwrite whatever a co-author changed since the last push, and Overleaf loses comments and track changes on external writes. Until a verified path exists with a check for remote changes, tell the user that push is unavailable.
