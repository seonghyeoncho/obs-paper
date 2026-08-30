# Handoff: Research Flow Content Structure and Korean Editing

## Status

Largely completed on 2026-08-30 against the POLAR Canvas. The rules below were settled in practice and codified in `skills/research-flow/references/content-structure.md`; this document remains the design record and rationale.

Done:

- Korean editing pass over all 38 managed POLAR research-flow cards. The dominant problem was not textbook translationese but symbol-as-conjunction telegraphese: `·` 81 occurrences to 0, `—` 41 to 8 title separators, `→` 22 to 4 numeric transitions, `+` 10 to 0. Manuscript-coined terms were spelled out; transliterated technical terms became Latin script.
- Node type format fixed. Every card declares its type on the first line, including the previously indistinguishable grey cards.
- Three configuration layers separated: a project-wide `Params` card, a per-experiment `Impl` card, and `Setup` in the flow.
- Measurements moved from Results prose into `Table` cards; repair and rerun narrative moved into each `Impl` card's `추가 메모`.
- `estimate_text_height` rewritten to count CJK glyphs at double width and to size table rows correctly.
- Node IDs printed as the last line of every managed card, with `obs_paper.py nodes` and the `node` skill for direct lookup.

Remaining:

- Extend `references/request-schema.md` with an implementation/side-card action kind.
- Teach `obs_paper_engine.py` to emit cards in this format rather than passing `## {heading}` through unvalidated.
- Apply the format to the Skill Following Canvas, which has not been migrated.

PDF-to-flow work remains suspended and is outside this task.

## User intent

Improve research-flow content so that the research argument is visible at a glance.

The current problems are:

1. Research content and implementation details are mixed.
2. A node often contains several independent ideas, with insufficient line breaks.
3. Large nodes obscure the flow.
4. Terminology is inconsistent.
5. Korean prose has not been edited. Unnecessary symbols such as `·`, em dashes, and en dashes appear frequently.

## Evidence from current Canvases

Inspect these as the first examples:

- Skill Following: `/Users/joseonghyeon/Library/Mobile Documents/iCloud~md~obsidian/Documents/NLP/Projects/Skill Following/Skill Following.canvas`
  - Research-flow text nodes: 86
  - Nodes longer than 300 characters: 11
  - Longest node: 690 characters
  - `·`: 13 occurrences
  - em dash or en dash: 31 occurrences
- POLAR: `/Users/joseonghyeon/Library/Mobile Documents/iCloud~md~obsidian/Documents/NLP/Projects/POLAR/POLAR.canvas`
  - Research-flow text nodes: 39
  - Nodes longer than 300 characters: 16
  - Nodes longer than 600 characters: 5
  - Longest node: 1,348 characters
  - `·`: 81 occurrences
  - em dash or en dash: 41 occurrences

Representative POLAR nodes to inspect:

- `rfmain2result001`: result values, file/config details, caveats, and interpretation are combined.
- `894fdf665b3fc4a4`: ontology condition, threshold setup, domain state, and gate judgment are combined.
- `713d246912817cb3`: several result claims are combined in one Results card.

## Recommended skill architecture

Do not create a new top-level skill first. Keep `research-flow/SKILL.md` as the router and add one optional reference:

```text
skills/research-flow/
|-- SKILL.md
`-- references/
    `-- content-structure.md
```

`SKILL.md` should require this reference only when the task involves content reconstruction, node splitting, terminology normalization, or Korean editing. This preserves progressive disclosure and avoids increasing the token cost of ordinary layout work.

Create a separate discoverable skill such as `research-flow-content` only if real use shows that users invoke content editing independently from research-flow construction.

## Required semantic separation

The main downward flow contains research reasoning only:

```text
RQ -> experiment question -> method -> measured result -> control -> interpretation -> next question
```

Implementation details must not be mixed into those nodes. Put them in uncoloured grey side cards connected laterally to the narrowest relevant method or result node.

Research content includes:

- the question being answered;
- hypothesis or comparison;
- experimental method at the level required to understand the claim;
- measured result with denominator, cohort, pooling unit, and uncertainty;
- validity control;
- interpretation, limitation, or decision that advances the research.

Implementation detail includes:

- commands and reproduction steps;
- source file paths and output paths;
- run IDs, timestamps, checkpoint names, and log locations;
- low-level configuration and parser details;
- engineering failures and fixes that do not change the scientific claim.

If an implementation detail changes the estimand, cohort, validity, or interpretation, express that consequence in the main flow and keep the low-level mechanics in the side card.

## Atomic-node rule

Use one node for one semantic job, not necessarily one sentence.

Split a node when it contains any of these combinations:

- method and result;
- result and interpretation;
- two results with different denominators, cohorts, or conclusions;
- scientific claim and reproduction instructions;
- current conclusion and superseded conclusion;
- independent claims joined only by a connective phrase.

Do not split a compact list whose items jointly define one method, one result table, or one control. In that case, preserve one node and use explicit line breaks.

Preferred internal layout for a compact multi-line node:

```markdown
## Results

Primary result sentence.

Denominator and uncertainty sentence.
```

Avoid dense inline inventories. Use a blank line between the heading and content, and between semantically distinct parts that must remain in one card.

## Research-flow node grammar

- `RQ`: one exact research question.
- `RQ-E` title: experiment identity only. Do not place method or results in the title.
- `Method`: one comparison or design unit. Keep scientific conditions here.
- `Result`: one measured finding or one inseparable result set.
- `Control`: one validity, sanity, robustness, or manipulation-check conclusion.
- `RQ-A`: one interpretation that follows from linked evidence.
- Bridge question: one question that motivates the next RQ.
- Implementation: grey side card containing commands, paths, run metadata, and engineering notes.
- Source: grey side card containing provenance only.
- Table and figure: separate artifact nodes, never compressed into prose.

The main flow must remain readable when all implementation and source side cards are mentally hidden.

## Terminology normalization

Each project needs a small canonical glossary before bulk rewriting. Recommended location:

```text
Projects/<Project>/research-flow-terms.json
```

Suggested minimal shape:

```json
{
  "preferred": {
    "canonical Korean or English term": ["legacy variant", "abbreviation"]
  },
  "protected": ["RQ", "RQ-E", "RQ-A", "MBPP+", "model-name"]
}
```

Choose terms in this order:

1. repository or manuscript terminology designated as canonical;
2. project glossary;
3. most recent validated research-flow usage;
4. older Canvas wording.

Do not silently replace terms whose distinction affects the claim. Record ambiguous pairs for user review.

## Korean editing rules

- Default to clear Korean declarative prose.
- Keep benchmark names, model identifiers, metric symbols, code identifiers, and established English technical terms when translation would reduce precision.
- Replace `·` with a comma, `및`, or a full sentence according to meaning.
- Replace em dashes and en dashes used as prose connectors with a colon, parentheses, comma, or a new sentence.
- Use a hyphen only when it belongs to an identifier, model name, established compound, or numeric range.
- Avoid long noun chains and stacked parenthetical remarks.
- Put the conclusion first, then its condition or caveat.
- Do not change numbers, denominators, uncertainty intervals, filenames, commands, or quoted source text during Korean editing.
- Preserve `RQ`, `RQ-E`, and `RQ-A` identifiers exactly.

## Color and layout boundary

Retain the existing research-flow color grammar:

- purple: RQ;
- green: experiment and measured facts;
- yellow: interpretation;
- orange: bridge question;
- red: user-authored refutation or personal thought only;
- no color: implementation, source, table, figure, and literature cards.

Implementation and source cards belong outside the main downward stack. Connect them laterally to their exact target. Splitting content must preserve the visible downward reasoning chain.

## Proposed implementation sequence

1. Add `skills/research-flow/references/content-structure.md` using the rules in this handoff.
2. Add one routing sentence to `skills/research-flow/SKILL.md`.
3. Extend `references/request-schema.md` with an explicit `implementation` detail kind or equivalent side-card action.
4. Update `obs_paper_engine.py` so compound experiment input produces separate method, result, control, and implementation cards rather than one dense section card.
5. Add deterministic formatting for blank lines and fitted height.
6. Add optional terminology-map input. Do not perform uncontrolled global substitutions.
7. Pilot the migration on one POLAR RQ chain only.
8. Review the rendered result with the user before applying it to the rest of POLAR or Skill Following.
9. Add tests for semantic separation, side-card routing, line breaks, colors, and idempotent reruns.

## Migration safety

- Do not rewrite every existing research-flow node in one pass.
- Preserve node IDs when one old node maps to one revised node.
- When splitting one old node, retain the old node ID on the first scientific unit and create stable IDs for additional units.
- Preserve the original text in the Canvas history backup and action log.
- Do not convert implementation notes into scientific evidence.
- Do not alter measured values or interpretations merely to make the flow visually balanced.

## Acceptance criteria

The pilot is complete only when:

- no managed main-flow node mixes implementation mechanics with a scientific claim;
- no managed node mixes method, result, and interpretation;
- each result remains traceable to its denominator, cohort/configuration, uncertainty, and source;
- long nodes use intentional paragraph breaks or have been split into atomic semantic nodes;
- the main downward chain is understandable without reading grey side cards;
- canonical terminology is used consistently in the migrated scope;
- unnecessary `·`, em dashes, and en dashes are absent from edited Korean prose;
- protected identifiers, numeric values, source quotations, and commands are unchanged;
- colors and arrow directions follow the existing research-flow grammar;
- the Canvas validates and a second deterministic plan contains zero operations.

## Non-goals

- Do not modify paper manuscript groups.
- Do not resume PDF-to-flow conversion.
- Do not redesign the Canvas as an ontology.
- Do not summarize away raw experimental evidence.
- Do not apply a project-wide migration before the one-RQ pilot is approved.

## Next-session starting point

POLAR is migrated. Read `skills/research-flow/references/content-structure.md` for the settled rules before touching node text.

Two follow-ups remain in the plugin: give `request-schema.md` an explicit side-card action kind, and make the engine emit and validate this format instead of accepting any `heading` string. Until then the format holds by convention, not by construction.

Skill Following has not been migrated. Pilot one RQ chain there and review the rendered result before applying the format to the rest of that Canvas.
