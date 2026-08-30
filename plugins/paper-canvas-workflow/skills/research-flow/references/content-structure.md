# Research-flow node format

Read this when a task involves writing or revising research-flow node text: content reconstruction, node splitting, metadata separation, or Korean editing. Ordinary layout work does not need it.

## Every card declares its type on the first line

| Type | First line | Colour | Body |
|---|---|---|---|
| RQ | `# RQ1` | purple | one question, one sentence |
| Experiment | `# RQ-E3 — <name> (<status>)` | green | title only |
| Setup | `## Setup` | green | what is compared against what, and why |
| Results | `## Results` | green | one paragraph per axis, measured facts only |
| Interpretation | `# RQ1-A` / `# RQ-E4-A` | yellow | conclusion first, then its condition |
| Bridge question | no label | orange | one question; colour carries the type |
| Source | `### Source` | grey | title, cite key, wikilink, Zotero link, one-line relevance |
| Table | `### Table — <caption>` | grey | caption, then the complete table |
| Params | `### Params — <project>` | grey | two-column table, one per project |
| Impl | `### Impl — RQ-E<n>` | grey | two-column table, then an optional `**추가 메모**` paragraph |
| Log | `### Log — RQ-E<n> (<why discarded>)` | grey | a run that produced no usable evidence |
| Thought | free | red | the user's own; never rewrite it |

An interpretation takes the identifier of whatever it interprets, plus `-A`. An experiment that grew out of a bridge question has no RQ number, so its interpretation takes the experiment number. Bridge questions stay unlabelled: they mark why the next experiment started, not a node to be answered by name.

Status belongs in the experiment title and nowhere else. Section headings carry the type name alone.

## Three layers of configuration

Keep them in separate cards. The main downward flow must read correctly when every grey card is mentally hidden.

- **Params** (one per project): thresholds, search budget, model names per role. Values that hold across experiments.
- **Impl** (one per experiment): run grid, paths, commands, commits, outputs, logs. Row vocabulary: `grid`, `설계`, `절차`, `실행`, `검증`, `설정`, `채점`, `산출물`, `log`, `기록`, `commit`. Include only rows that apply. An optional `**추가 메모**` paragraph follows the table.
- **Setup** (in the flow): which variants are compared and why. No counts, no paths, no config.

What broke and how it was fixed is appendix material: it goes in the Impl card's `**추가 메모**`, never in Setup, Results, or Control. That covers reruns, config repairs, harness and scorer defects, archived pre-fix cells, and known measurement limitations with their TODO. Green cards state the condition and the measurement as they now stand, without narrating how they got there.

An invalidated run is not a green experiment. Green means a measurement someone can rely on, so a run whose numbers are being discarded leaves the flow entirely and becomes a `Log` card beside the run that replaced it. Record why it was discarded, what it cost, and where its outputs sit; do not record its measurements. A number nobody will cite is not worth the space, and keeping it invites someone to read it as evidence later.

What survives such a run is whatever changed the next one: the methodological fact that forced a config change, and any caveat it casts on earlier results measured under the same fault. Apply the same test to a run that stayed in the flow — a measurement no interpretation ever cites, taken under a fault you later found, is a discarded number that happens to still be on the page.

There is no validity section. Whether a run was usable — completeness, robustness under a swept parameter, data loss, denominators large enough to divide by — is a property of the run, not a finding about the subject, so it belongs in that experiment's implementation card. A green experiment standing in the flow already asserts that its run was sound; the grey card holds the evidence for that assertion. Do not restate a measurement as a check: a bullet saying the gate made no model calls is the same fact the Results already reports.

A value that changes what is being estimated stays in the flow. A threshold that an RQ sweeps is flow content even though it is also configuration.

Connect Impl and Source cards laterally, `right` → target `left`. Params has no arrow; it applies to everything, and its position carries that.

## Numbers live in Table cards

Results prose states what each axis showed. The measurements themselves go in a `### Table` card beside it. Never print the same number in both — check for duplication before writing.

Every measurement keeps its denominator, pooling unit, cohort, and uncertainty wherever it lands. Tables size to their own content and are exempt from the ordinary card width and height rule.

## One node, one job

Split a card that mixes method with result, result with interpretation, two results with different denominators or cohorts, a claim with reproduction steps, or a current conclusion with a superseded one. Do not split a list whose items jointly define one method, one result set, or one control; use blank lines inside the single card instead.

## Korean prose

Write Korean sentences. Keep technical terms in Latin script rather than transliterating them: `call` not 콜, `tool` not 툴, `cell` not 셀, `agent` not 에이전트, `gate` not 게이트, `ontology` not 온톨로지.

Do not use terms coined for the manuscript. The flow exists for exploration and review, so a reader must not need the paper's vocabulary to follow it. Spell the meaning out instead, naming the actual identifier where one exists. Put coined terms in a glossary group or the manuscript group, never in the flow.

Symbols are not conjunctions. Write the sentence instead of joining fragments with `·`, `—`, `→`, `+`, or `=`. These stay only inside identifiers, table cells, numeric transitions such as `2→0`, statistical notation such as `Δ=`, and title separators.

Avoid Sino-Korean coinages that are English morphemes translated one by one — 비퇴화, 불감, 불채택, 전수, 증적, 기여물. Say what they mean.

Never change a number, denominator, interval, filename, command, commit, or quoted source while editing prose. Preserve `RQ`, `RQ-E`, and `RQ-A` identifiers exactly. Verify mechanically after a bulk edit, not by eye.
