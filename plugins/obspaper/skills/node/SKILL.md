---
name: node
description: Answer a question about specific Obsidian Canvas nodes named by their IDs. Use whenever the user supplies one or more canvas node IDs followed by a question or instruction, or pastes card text ending in a backticked node ID. Fetches those exact nodes by direct lookup; do not use for finding nodes whose IDs are unknown.
---

# Canvas node lookup

The user addresses cards by ID: `<node ids> <question>`. Every managed research-flow card prints its own ID as the last line, so the ID is exact and already verified.

## Fetch, never search

```bash
python /path/to/plugin/scripts/obs_paper.py nodes <canvas> <id> [<id> ...]
```

This is a direct lookup. Do not grep the canvas, do not read the whole `.canvas` file, and do not dispatch a search agent. The user gave you the address; use it.

Resolve the canvas with `obs_paper.py project-resolve` when the project is not already known from this session. Fall back to asking only if several projects match.

Each returned node carries its text, group, colour, geometry, and the edges on both sides. The colour tells you the type: purple RQ, green evidence, yellow interpretation, orange bridge question, red the user's own note, uncoloured a grey side card.

## Answer from what came back

Answer using the fetched nodes and the conversation. When the answer needs a neighbour the user did not name, fetch it by the ID shown in that node's `incoming`/`outgoing` list rather than searching for it.

Report a missing ID plainly. It is a typo or a deleted node, never a cue to go looking for something similar.

Stay read-only. A question is a question; if the user then asks for a change, hand off to `research-flow` (or `paper`, `rebuttal`, `camera-ready` for those groups) and follow its logging and backup rules.

## Node IDs in card text

Managed research-flow cards end with their ID in backticks on the last line. It is metadata, not content: ignore it when summarising a card, keep it when rewriting one, and never let it drift from the node's actual ID. File nodes such as figures carry no text and therefore no printed ID; they are still fetchable by ID.
