# Manuscript Korean

Read this before writing or revising `paper_v1` prose. Layout-only work does not need it.

## The versions are stages

`paper_v1` is the Korean draft and the author's own working-out. `paper_v2` is the English translation that gets submitted; `rebuttal` answers reviewers; `camera_ready` folds accepted promises back in. So a Korean v1 under an English venue is correct, not a defect, and v1 is what the translation will be written from — edit it as Korean academic prose, and never translate it in place.

## These rules are not the research-flow rules

`research-flow/references/content-structure.md` says the opposite on three points, deliberately. Do not carry its rules across.

| | research flow | manuscript |
|---|---|---|
| The paper's coined terms (이름표 차단, 이탈원) | spelled out | kept, and defined at first use |
| Technical terms (gate, ontology, agent) | Latin script | Korean 음차 (게이트, 온톨로지, 에이전트) |
| `·` between nouns | removed | kept |

The flow exists so the author can explore and review without needing the paper's vocabulary. The manuscript is where that vocabulary is defined and earned. A term the flow spells out is the same term the manuscript names.

`·` differs because the two uses differ. In the flow it stood in for whole clauses (`baseline 80.5s · block_irr 91.0s`); in the manuscript it coordinates nouns (`검토·승인`, `관계·가중치·근거`), which is ordinary Korean orthography. Coordinating nouns keep it; a `·` standing in for a clause does not.

## What to fix

**The em dash used as English apposition or parenthesis.** This is the most common tell. `우리는 BELAY를 제안한다 — ...는 게이트다` is "We propose BELAY — a gate that…" carried over intact; in Korean the apposition goes in front of the noun: `우리는 …는 게이트인 BELAY를 제안한다`. Where the dash joins two independent statements, end the sentence instead. Where it wraps an insertion (`네 질문 — 무엇을 막았고… — 을`), use parentheses or restructure. A dash is fine in a heading as a separator, and a range (`1.3~6.7초`) is not a dash at all.

**Sino-Korean coinages that are English morphemes translated one by one** — 증적, 기여물, 입력물, 불감, 비퇴화. These are not the paper's terminology; they are stiff renderings of evidence, contribution, input, insensitive, non-degenerate. Say what they mean. A coined term the paper actually defines and uses consistently is different and stays.

**The ordinary translationese patterns**: an inanimate subject driving an active verb, passive stacked where Korean would say who did it, and noun chains that could be a clause. These are rare in this manuscript; fix them where they appear rather than sweeping for them.

## What never changes

Numbers, denominators, uncertainty intervals, citation keys, `\cite` commands, equations, and quoted source text. Terminology the paper has defined stays consistent everywhere, including in the abstract and headings — renaming a term is a manuscript decision, not a copy-edit. Verify mechanically after a bulk pass rather than by eye.
